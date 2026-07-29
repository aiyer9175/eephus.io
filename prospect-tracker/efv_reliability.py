# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""C1 — forward-chained reliability/ECE regen for the SHIPPED eFV outcome
distribution, with a drift tripwire.

Background (audit 2026-07-19): `regen_all` refreshes every eFV artifact EXCEPT
the reliability curves — `data/xfv_reliability.json` was last written by the
one-off isotonic lab (`tools/efv_isotonic_lab.py`, a failed pre-registered gate)
and had gone stale (2026-07-01), while showing a real bust-bucket miscalibration
(the low-probability bin predicts ~0.06 but realizes ~0.31). This module makes
the "before"/shipped reliability curves a first-class, nightly-refreshed
artifact and adds a tripwire so a widening calibration gap surfaces.

SAFE / rank-neutral by construction: the reliability curves are a DIAGNOSTIC of
the already-shipped 5-bucket distribution `p_bucket_given_fv`. Nothing here feeds
back into any served eFV/WAR/grade/surplus number — it only measures them. So
this refresh cannot move a published number; it changes only the diagnostic
artifact (which the box regenerates canonically — never commit a locally
regenerated copy, per the degraded-local-data rule).

The heavy OOF machinery is shared with the isotonic lab, but that module does an
`os.chdir(ROOT)` at import time, so we import the underlying pieces directly here
rather than importing the lab (no CWD side effect in the production pipeline)."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "xfv_reliability.json"

BUCKETS = ("bust", "bench", "regular", "good", "star")
CHAIN_YEARS = tuple(range(2016, 2024))   # OOF chain (2016-19 seed the calibrators)
MIN_TRAIN, MIN_TEST = 60, 10
MIN_TIER_N = 15
# Realized-outcome bucketing — MUST match tools/efv_isotonic_lab.py exactly, so
# the curves measure the shipped distribution. The bucket is the 6yr-average
# ANNUAL WAR (target_war_6yr / TARGET_SEASONS) binned by the config band edges.
BUCKET_EDGES = (0.5, 1.5, 2.5, 4.0)      # 6yr-avg annual WAR band edges
TARGET_SEASONS = 6.0

# Tripwire: the pooled bust-bucket ECE at which the reliability regen flags a
# miscalibration for review. The 2026-07-01 baseline read ~0.12 (a known,
# documented low-p under-prediction), so the tripwire trips ABOVE that to catch
# genuine WIDENING, not the standing gap. Rank-neutral: this only sets a flag.
BUST_ECE_TRIPWIRE = 0.14


def _tier(fv: float) -> int:
    """Consensus-FV tier = FV rounded to the nearest 5 (matches the isotonic lab)."""
    return int(round(float(fv) / 5) * 5)


def _realized_bucket(target_war_6yr: float) -> int:
    """The shipped 5-bucket realized-outcome map (matches the isotonic lab):
    bin the 6yr-AVERAGE annual WAR by the config band edges."""
    import bisect
    return bisect.bisect_right(BUCKET_EDGES, float(target_war_6yr) / TARGET_SEASONS)


def _oof_rows(side: str) -> list[dict]:
    """Forward-chained out-of-fold rows for one side: the shipped pipeline's
    predicted 5-bucket distribution (uncalibrated) + realized bucket + fv/weight.
    Mirrors tools/efv_isotonic_lab.oof_rows but with no chdir side effect."""
    import numpy as np
    import value_framework as vf
    # TARGET_SEASONS = the model's exposure window (efv_dataset, =6). Imported from
    # efv_dataset (not the module-level 6.0 above, which is the realized-bucket
    # divisor pinned to the isotonic lab) so the grade-map inversion below tracks
    # whatever window efv_score ships. Shadows the module global inside this
    # function only; _realized_bucket keeps its own module-level divisor.
    from efv_dataset import matrix_path, TARGET_SEASONS
    from efv_model import _prep, _feature_spec
    from efv_score import _age_at, _grade_map_age
    from prospect_path import _fit_ridge, _predict, _fit_linear_calibration

    is_pit = side == "pit"
    keys, _mono = _feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r["kind"] == "bust" and r.get("bust_recent"))]
    data = _prep(pool, "target_censored", side)
    by_key = {r["player_key"]: r for r in pool}

    out: list[dict] = []
    for yr in CHAIN_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < MIN_TEST or len(tr) < MIN_TRAIN:
            continue
        ridge = _fit_ridge(tr, keys)
        if not ridge:
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in te:
            src = by_key[r["player_key"]]
            xfv_war = max(-2.0, a + b * _predict(ridge, r["feats"]))
            dyear = src.get("debut_year") or 2020
            age = _age_at(src.get("birth_date"), dyear)
            # exposure_seasons=TARGET_SEASONS so these reliability/ECE curves measure
            # the SHIPPED 6yr-window grade (efv_score.run/run_live/run_backgrade all
            # pass it); omitting it defaulted to control_years=7 and the diagnostic
            # described a bucket distribution the site never shows (2026-07-19 fix).
            # Age placement via _grade_map_age (bughunt F5, 2026-07-23): mirror the
            # scorer - `age` is measured at the debut year, so eta_to_debut = 0.0;
            # the raw pre-debut age placed the inversion's curve at debut_age =
            # age - 6, a curve the site never prices.
            pos = src.get("position")
            _gm_age = _grade_map_age(age, 0.0)
            grade = vf.realized_implied_fv(xfv_war, is_pit, age=_gm_age, position=pos,
                                           exposure_seasons=TARGET_SEASONS)
            if grade is None:
                continue
            probs = vf.p_bucket_given_fv(grade, is_pit)
            if not probs or len(probs) != len(BUCKETS):
                continue
            out.append({
                "player_key": r["player_key"], "side": side,
                "decision_year": yr, "fv": r["fv"],
                "p_before": np.asarray(probs, dtype=float),
                "y": _realized_bucket(r["target"]),
                "weight": float(r["weight"]),
            })
    return out


def _reliability_bins(rows, n_bins: int = 10) -> dict:
    """Pooled per-bucket reliability curve (equal-width prob bins) + ECE, over the
    shipped `p_before` distribution. Identical binning to the isotonic lab."""
    import numpy as np
    out = {}
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    for bi, name in enumerate(BUCKETS):
        p = np.array([r["p_before"][bi] for r in rows])
        y = np.array([1.0 if r["y"] == bi else 0.0 for r in rows])
        curve, ece = [], 0.0
        for i in range(n_bins):
            m = (p >= edges[i]) & (p < edges[i + 1] if i < n_bins - 1 else p <= 1.0)
            if m.sum() < 5:
                continue
            mp, fr = float(p[m].mean()), float(y[m].mean())
            curve.append({"bin": [round(float(edges[i]), 2), round(float(edges[i + 1]), 2)],
                          "n": int(m.sum()), "mean_p": round(mp, 4), "freq": round(fr, 4)})
            ece += (m.sum() / len(p)) * abs(mp - fr)
        out[name] = {"ece": round(float(ece), 5), "curve": curve}
    return out


def _tier_reliability(rows) -> dict:
    """Per consensus-FV tier: mean |mean predicted p_b - realized freq_b| gap."""
    import numpy as np

    def _onehot(k: int):
        v = np.zeros(len(BUCKETS)); v[k] = 1.0; return v

    by_tier = defaultdict(list)
    for r in rows:
        by_tier[_tier(r["fv"])].append(r)
    out = {}
    for tk in sorted(by_tier):
        grp = by_tier[tk]
        if len(grp) < MIN_TIER_N:
            continue
        freq = np.mean([_onehot(r["y"]) for r in grp], axis=0)
        mb = np.mean([r["p_before"] for r in grp], axis=0)
        gap = float(np.mean(np.abs(mb - freq)))
        out[str(tk)] = {
            "n": len(grp), "gap": round(gap, 5),
            "realized_freq": {BUCKETS[i]: round(float(freq[i]), 4) for i in range(len(BUCKETS))},
            "mean_p": {BUCKETS[i]: round(float(mb[i]), 4) for i in range(len(BUCKETS))},
        }
    return out


def build(persist: bool = True) -> dict:
    """Regenerate the shipped-distribution reliability curves + tripwire. Returns
    the payload; writes data/xfv_reliability.json when persist. Best-effort: on
    any failure (matrix absent, degraded local build) it logs and returns {},
    leaving the existing artifact untouched — the box produces the canonical one."""
    from datetime import date
    try:
        rows = {s: _oof_rows(s) for s in ("hit", "pit")}
    except Exception:                                          # noqa: BLE001
        log.exception("efv_reliability: OOF build failed — skipping regen")
        return {}
    pooled = [r for side_rows in rows.values() for r in side_rows]
    if not pooled:
        log.warning("efv_reliability: no OOF rows — skipping regen")
        return {}
    curves = _reliability_bins(pooled)
    tiers = _tier_reliability(pooled)
    bust_ece = curves.get("bust", {}).get("ece", 0.0)
    tripwire = {
        "bust_ece": bust_ece,
        "threshold": BUST_ECE_TRIPWIRE,
        "tripped": bool(bust_ece > BUST_ECE_TRIPWIRE),
        "note": ("bust-bucket ECE exceeded the drift threshold — the low-p bin "
                 "under-prediction has widened; review calibration"
                 if bust_ece > BUST_ECE_TRIPWIRE else
                 "within the documented standing miscalibration band"),
    }
    payload = {
        "generated_at": date.today().isoformat(),
        "note": ("Reliability curves for the SHIPPED eFV 5-bucket outcome "
                 "distribution (forward-chained out-of-fold, the 'before' "
                 "baseline). Regenerated by efv_reliability.build (C1); diagnostic "
                 "only — no served number depends on these curves. A raised "
                 "tripwire.tripped flags a widening bust-bucket calibration gap."),
        "reliability_curves_pooled": {"before": curves},
        "per_tier_reliability": tiers,
        "tripwire": tripwire,
        "pooled_n": len(pooled),
        "n_by_side": {s: len(v) for s, v in rows.items()},
    }
    if tripwire["tripped"]:
        log.warning("efv_reliability TRIPWIRE: bust ECE %.4f > %.4f",
                    bust_ece, BUST_ECE_TRIPWIRE)
    if persist:
        OUT_PATH.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        log.info("efv_reliability: wrote %s (pooled n=%d, bust ECE %.4f)",
                 OUT_PATH.name, len(pooled), bust_ece)
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = build(persist="--no-persist" not in __import__("sys").argv)
    if rep:
        print(f"reliability regen: pooled n={rep['pooled_n']}, "
              f"bust ECE={rep['reliability_curves_pooled']['before']['bust']['ece']}, "
              f"tripwire={'TRIPPED' if rep['tripwire']['tripped'] else 'ok'}")
