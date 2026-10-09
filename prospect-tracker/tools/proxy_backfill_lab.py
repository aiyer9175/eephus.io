# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""TL_8 proxy backfill lab: efv_proxy refit backward on debut cohorts 2016 to 2021.

Plan: Part 9, section 9.4.6 'Prospect stat-line projections' (LANE_C.md 1.5 and 2.6).
Gate: docs/proj-prospect-2026-10/PROSPECT_STATLINE_GATE.md (baseline B3 and the xwOBA
prior of 1.1 are this refit; its guard reads Part 13 of that file).

What it does. The served proxy (efv_proxy.py, COHORT_YEARS 2024 to 2026, artifact
data/xfv_proxy_eval.json, registry row xfv_proxy) has its only out-of-sample read on the
2025 and 2026 debut cohorts, which are R-VM. This lab reuses efv_proxy._build_pairs and
efv_proxy._eval_forward with the years passed in: pairs are built for debut cohorts 2016
to 2021 and scored forward-chained on test years 2018 to 2021, each test year fit on the
cohorts strictly earlier (ridge alpha 3.0 on standardized eFV features, the served
estimator unchanged). It reports per test year and pooled out-of-sample r and Spearman
rho per side with n; the 2020 cohort (a 60-game season) is flagged.

Frames.
- R-VM (debut cohorts 2025 and later, efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR) always
  raises ReservedFrameError, before anything is read. No argument opens it.
- Holdout H of the stat-line gate (debut cohorts 2022 to 2024) raises HoldoutFrameError
  until Part 13 'Results' of the gate carries TL_17's look record AND the look's artifact
  (data/prospect_statline_eval.json) exists.
- List vintages 2020 and 2021 enter only as the as-of points of the 2020 and 2021 debut
  cohorts (gate 0.6); this lab scores no eFV, consensus or source value.
- No statistic here is cut by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md): the only
  groupings are side, debut cohort and test year.

Role 'development'. Writes data/_labs/proxy_backfill_eval.json, which ships in neither
deploy consumer; the served proxy file and its registry row are not touched.
Run: python tools/proxy_backfill_lab.py
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

DATA_DIR = _ROOT / "data"
OUT_PATH = DATA_DIR / "_labs" / "proxy_backfill_eval.json"
GATE_DOC = _ROOT / "docs" / "proj-prospect-2026-10" / "PROSPECT_STATLINE_GATE.md"
STATLINE_EVAL = DATA_DIR / "prospect_statline_eval.json"
SAVANT_DIR = _ROOT / ".cache" / "savant_mlb"

#: Debut cohorts the backfill reads, and the test years scored forward-chained.
BACKFILL_COHORTS: tuple[int, ...] = (2016, 2017, 2018, 2019, 2020, 2021)
TEST_YEARS: tuple[int, ...] = (2018, 2019, 2020, 2021)
#: Holdout H of the stat-line gate (3.2): debut cohorts 2022 to 2024, touched once by TL_17.
HOLDOUT_FIRST_DEBUT_YEAR = 2022
#: Season flags printed beside a test year (not a stratum; descriptive only).
SEASON_FLAGS = {2020: "60-game season: the 2020 cohort's first MLB season is the shortened 2020 season"}

_DATE_RE = re.compile(r"\b20\d\d-\d\d-\d\d\b")


class HoldoutFrameError(RuntimeError):
    """A read of the stat-line gate's holdout H before TL_17's look record exists."""


def _part13(text: str) -> str | None:
    """The body of '## Part 13. Results' up to the next '## ' heading, or None."""
    m = re.search(r"^## Part 13\. Results[^\n]*\n", text, flags=re.M)
    if not m:
        return None
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, flags=re.M)
    return rest[:nxt.start()] if nxt else rest


def holdout_look_recorded(text: str | None = None, eval_path: Path = STATLINE_EVAL) -> bool:
    """True only when the gate's Part 13 carries a dated look entry heading (a '###' line
    naming a look and a date, not an amendment or a freeze) beyond the registration
    paragraph, AND the look's artifact exists. Anything less reads as no record, which
    keeps the holdout closed (the safe direction)."""
    if text is None:
        try:
            text = GATE_DOC.read_text(encoding="utf-8")
        except OSError:
            return False
    body = _part13(text)
    if body is None:
        return False
    body = re.sub(r"EMPTY AT REGISTRATION\..*?(\n\s*\n|\Z)", "", body, flags=re.S)
    entry = False
    for line in body.splitlines():
        low = line.lower()
        if (line.startswith("###") and _DATE_RE.search(line) and "look" in low
                and "amendment" not in low and "freeze" not in low):
            entry = True
            break
    return entry and Path(eval_path).exists()


def guard_years(cohort_years, test_years, *, gate_text: str | None = None,
                eval_path: Path = STATLINE_EVAL) -> None:
    """Raise before any read: R-VM always; holdout H until TL_17's record; a test year
    outside the cohorts or with no earlier cohort to train on."""
    from efv_vintage_frame import R_VM_FIRST_DEBUT_YEAR, ReservedFrameError
    years = {int(y) for y in cohort_years} | {int(y) for y in test_years}
    rvm = sorted(y for y in years if y >= R_VM_FIRST_DEBUT_YEAR)
    if rvm:
        raise ReservedFrameError(
            f"debut cohorts {rvm} are reserved (R-VM, from {R_VM_FIRST_DEBUT_YEAR}); "
            "the proxy backfill never reads them")
    hold = sorted(y for y in years if y >= HOLDOUT_FIRST_DEBUT_YEAR)
    if hold and not holdout_look_recorded(gate_text, eval_path):
        raise HoldoutFrameError(
            f"debut cohorts {hold} are the stat-line gate's holdout H; closed until "
            "PROSPECT_STATLINE_GATE.md Part 13 carries TL_17's look record")
    cohorts = {int(y) for y in cohort_years}
    for t in test_years:
        if int(t) not in cohorts:
            raise ValueError(f"test year {t} is not a backfill cohort")
        if not any(c < int(t) for c in cohorts):
            raise ValueError(f"test year {t} has no strictly earlier cohort to train on")


def _check_pairs(pairs: list[dict], cohort_years) -> None:
    """Defence in depth: every built pair sits in a requested cohort."""
    allowed = {int(y) for y in cohort_years}
    bad = sorted({p["year"] for p in pairs if p["year"] not in allowed})
    if bad:
        raise RuntimeError(f"pairs outside the requested cohorts: {bad}")


def _train_years(pairs: list[dict], test_y: int) -> list[int]:
    """The debut cohorts efv_proxy._eval_forward trains on for test_y (strictly earlier)."""
    return sorted({p["year"] for p in pairs if p["year"] < test_y})


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _input_hashes(cohort_years) -> dict:
    out = {"data/debuts.json": _sha256(DATA_DIR / "debuts.json"),
           "efv_proxy.py": _sha256(_ROOT / "efv_proxy.py")}
    for y in cohort_years:
        for s in ("batter", "pitcher"):
            name = f"expected_{s}_{y}.csv"
            out[f".cache/savant_mlb/{name}"] = _sha256(SAVANT_DIR / name)
    return out


def evaluate_side(side: str, pairs: list[dict], keys: list[str], test_years) -> dict:
    """Per test year and pooled out-of-sample r and rho through efv_proxy._eval_forward."""
    import efv_proxy as P
    per_year = {}
    for y in test_years:
        ev = P._eval_forward(pairs, keys, test_years=(int(y),))
        tr_years = _train_years(pairs, int(y))
        row = {"n": ev["n"], "r": ev["r"], "spearman": ev["spearman"],
               "train_n": sum(1 for p in pairs if p["year"] < int(y)),
               "test_cohort_n": sum(1 for p in pairs if p["year"] == int(y)),
               "train_cohorts": tr_years}
        if int(y) in SEASON_FLAGS:
            row["flag"] = SEASON_FLAGS[int(y)]
        flagged_train = sorted(set(tr_years) & set(SEASON_FLAGS))
        if flagged_train:
            row["train_includes_flagged"] = flagged_train
        per_year[str(y)] = row
    pooled = P._eval_forward(pairs, keys, test_years=tuple(int(y) for y in test_years))
    return {"per_year": per_year,
            "pooled": {"n": pooled["n"], "r": pooled["r"], "spearman": pooled["spearman"]}}


def run(persist: bool = True, cohort_years=BACKFILL_COHORTS, test_years=TEST_YEARS) -> dict:
    guard_years(cohort_years, test_years)
    import efv_proxy as P
    from efv_model import _feature_spec
    cohort_years = tuple(int(y) for y in cohort_years)
    test_years = tuple(int(y) for y in test_years)
    report = {
        "role": "development",
        "task": "TL_8_PROXY_BACKFILL",
        "lab": "tools/proxy_backfill_lab.py",
        "gate": "docs/proj-prospect-2026-10/PROSPECT_STATLINE_GATE.md",
        "model": "efv_proxy refit backward (pre-debut eFV features -> first-MLB Savant est_woba)",
        "estimator": "efv_proxy._eval_forward: StandardScaler + Ridge(alpha=3.0), "
                     "a test year is skipped under 25 training or 10 test pairs",
        "cohort_years": list(cohort_years),
        "test_years": list(test_years),
        "min_pa": P.MIN_PA,
        "served_cohort_years": list(P.COHORT_YEARS),
        "season_flags": {str(k): v for k, v in SEASON_FLAGS.items()},
        "frames": ("Debut cohorts 2016 to 2021 only. R-VM (2025 and later) and holdout H "
                   "(2022 to 2024) are never read. List vintages 2020 and 2021 enter only as "
                   "as-of points of the 2020 and 2021 debut cohorts (gate 0.6). No statistic "
                   "is cut by consensus-FV level."),
        "survivorship": ("Debuts only: every number is accuracy among players who reached the "
                         "majors and posted a first-season Savant line at the PA floor."),
        "served_untouched": "data/xfv_proxy_eval.json and registry row xfv_proxy are not read or written",
        "generated": date.today().isoformat(),
        "sides": {},
    }
    for side in ("hit", "pit"):
        keys, _m = _feature_spec(side)
        pairs = P._build_pairs(side, cohort_years)
        _check_pairs(pairs, cohort_years)
        ev = evaluate_side(side, pairs, keys, test_years)
        ev["target"] = P._TARGET[side]
        ev["pairs"] = len(pairs)
        ev["per_cohort"] = {str(y): sum(1 for p in pairs if p["year"] == y) for y in cohort_years}
        report["sides"][side] = ev
        log.info("proxy backfill %s: %d pairs | pooled OOS r=%s rho=%s n=%s", side, len(pairs),
                 ev["pooled"]["r"], ev["pooled"]["spearman"], ev["pooled"]["n"])
    report["inputs_sha256"] = _input_hashes(cohort_years)
    if persist:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        log.info("wrote %s", OUT_PATH)
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    for side, ev in rep["sides"].items():
        for y, row in ev["per_year"].items():
            print(f"{side} {y}: n={row['n']} r={row['r']} rho={row['spearman']} "
                  f"train_n={row['train_n']}{' [' + row['flag'] + ']' if row.get('flag') else ''}")
        p = ev["pooled"]
        print(f"{side} pooled: n={p['n']} r={p['r']} rho={p['spearman']} pairs={ev['pairs']}")
