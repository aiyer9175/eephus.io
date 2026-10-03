"""EFV3_A9_LABEL_HORIZON_2026: what RESOLVED_THROUGH 2025 -> 2026 adds to the eFV label
pool, and the first-three and first-four-season label views as SECONDARY labels.

Owner ask (2026-10-02, verbatim): "On the eFV stuff - we are in the epoch now, the 2026
regular season is over, so we should be able to use more recent seasons for calibrating
eFV vs. prospect WAR". Plan: EFV3_PLAN.md s3 (the label pool) and LANE_A.md s4; this
task extends lane A's label-view item. Record: docs/efv-v2/LABEL_HORIZON_2026.md.

Writes data/efv_label_horizon_2026.json (tracked, development, nothing served reads it).

What it computes, and from what:

1. THE BUILDER'S OWN TERMS. For every debut cohort 2014 to 2025 the observed season
   count, observed fraction, row weight and censored flag under RESOLVED_THROUGH 2025
   (shipped) and 2026 (the epoch's F2 factor), each taken by calling
   efv_dataset._label_6yr with an EMPTY seasons dict while RESOLVED_THROUGH is set to
   that year for the call. The terms depend on the calendar only, so no outcome is read
   to produce them. The shipped matrices' stored (observed_seasons, weight, censored)
   must equal the RESOLVED_THROUGH 2025 terms row for row; the tool counts mismatches
   and the test pins them at zero.
2. THE 2026 GAIN. Rows and weight mass per (cohort, side) before and after, on every
   debuted matrix row and on the scored pool (consensus present, cohort in
   efv_model.SCORED_YEARS), the rows that move from censored to fully observed (the
   2021 cohort, counted and never read), the per-fold train and test mass of the
   forward-chained folds, and the floor arithmetic: the one-sided mde95 of
   data/xfv_mde_floor.json rescaled by sqrt(W_before / W_after). The rescaling is
   arithmetic on the resampler's published sd, not a measured floor; the measured floor
   after the epoch is step G's.
3. THE VIEWS. first3 and first4 (summed WAR over the first k seasons from the debut
   year, the builder's window convention with SERVICE_ALIGNED_WINDOW off): when each
   resolves, the cohorts and rows it resolves without projection at 2025 and 2026, the
   rows beyond L6, the share of six-season WAR mass the first k seasons carry, the
   projection bias the view removes (copied from LABEL_CENSORING_GATE.md s6.2), and
   the label-to-label correlation of each view with the six-season label on the
   development debut cohorts 2014 to 2019 (fully observed under both clocks), on the
   served ewar_v2 series and on the frozen fWAR vintage joined by MLBAM id. Percentile
   bootstrap over rows (one row per player per side), B 2000, seed 20260906. No rater
   enters anywhere: nothing here is scored against a grade.

GUARDS. The reserved debut cohorts 2020 and 2021 (their outcomes sit inside R-LV's
W3 seasons) and 2025 and later (R-VM) are never read for a value: outcome_guard raises
for them, the outcome cohorts are 2014 to 2019 only, and the newest season any value is
read from is 2024 (2019 + 5). No 2025 or 2026 season line is read, so the frozen vintage
is read for label-to-label arithmetic only, as the task permits once EPOCH_E3 landed.
No statistic is grouped by a consensus-FV cell (docs/PROSPECT_ANCHOR_GATE.md).

Run: python tools/efv_label_horizon_2026.py [--out PATH] [--summary]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import efv_dataset as D  # noqa: E402
import efv_labels as L  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import fwar_vintage as FV  # noqa: E402
import war_source  # noqa: E402

TASK = "EFV3_A9_LABEL_HORIZON_2026"
SCHEMA = "efv_label_horizon_2026/1"
OUT = ROOT / "data" / "efv_label_horizon_2026.json"
DOC = ROOT / "docs" / "efv-v2" / "LABEL_HORIZON_2026.md"
MATRICES = {"hit": ROOT / "data" / "xfv_hitter_matrix.json",
            "pit": ROOT / "data" / "xfv_pitcher_matrix.json"}
CENSUS = ROOT / "data" / "efv_label_pool_census.json"
MDE_FLOOR = ROOT / "data" / "xfv_mde_floor.json"
DEBUTS = ROOT / "data" / "debuts.json"
OVERRIDES = ROOT / "data" / "sources" / "mlbam_id_overrides.json"
CENSORING_GATE = "docs/efv-2026-08-07b/LABEL_CENSORING_GATE.md"

SIDES = ("hit", "pit")
SIDE_GROUP = {"hit": "hitting", "pit": "pitching"}

RT_BEFORE = 2025           # shipped: efv_dataset.RESOLVED_THROUGH
RT_AFTER = 2026            # the epoch's F2 factor (FWAR_LABEL_EPOCH_GATE.md part 1 item 2)
COHORTS: tuple[int, ...] = tuple(range(2014, 2025))     # the scored pool's cohorts
ENTERING_COHORT = 2025     # admitted by DEBUT_YEARS at RT 2026; R-VM, counts only
TERM_COHORTS: tuple[int, ...] = COHORTS + (ENTERING_COHORT,)

#: Debut cohorts whose outcomes are never read here: 2020 and 2021 (their W3 seasons
#: are R-LV's), and R-VM (2025 and later).
RESERVED_DEBUT_COHORTS: frozenset[int] = frozenset({2020, 2021})
#: The development debut cohorts whose outcomes may be read: six-season windows that
#: closed under RESOLVED_THROUGH 2025 and are outside the reserved set.
DEV_OUTCOME_COHORTS: tuple[int, ...] = tuple(range(2014, 2020))
MAX_SEASON_READ = max(DEV_OUTCOME_COHORTS) + D.TARGET_SEASONS - 1    # 2024

VIEWS: dict[str, int] = {"first3": 3, "first4": 4}
B_BOOT = 2000
SEED = 20260906

#: LABEL_CENSORING_GATE.md s6.2, `by_n_obs_and_side`, projected minus true in WAR: the
#: flat-rate tail projection's mean signed bias at n_obs observed seasons. A view that
#: sums exactly k observed seasons carries none of the bias at n_obs = k because it
#: projects nothing; it measures a different quantity instead.
CENSORING_BIAS = {
    3: {"hit": {"mean_bias": -0.964, "ci95": [-1.267, -0.658], "n": 460},
        "pit": {"mean_bias": -0.450, "ci95": [-0.706, -0.208], "n": 528}},
    4: {"hit": {"mean_bias": -0.340, "ci95": [-0.541, -0.135], "n": 460},
        "pit": {"mean_bias": -0.184, "ci95": [-0.347, -0.028], "n": 528}},
}
#: The same document, `season_share_profile_diagnostic`, pooled: the share of
#: six-season WAR realized in seasons 1 to 6 on 988 fully resolved debuts.
SEASON_SHARE_PROFILE = (0.080, 0.138, 0.185, 0.215, 0.202, 0.179)

#: The one prior first-k measurement on record: lane E2's probe (PROGRAM.md s3.3 cites
#: [E2] `debuted_frame_firstk_vs_L6` for first-2). Debut cohorts 2011 to 2020 on the
#: ewar_v2 label, so it INCLUDES the 2020 cohort this tool treats as reserved; copied
#: as a prior, never recomputed here.
E2_PRIOR = {
    "path": "_finalpass_2026-09-24/efv2/E2_data_labels/probe_labels.json (bundle, outside the repo)",
    "key": "debuted_frame_firstk_vs_L6", "cohorts": [2011, 2020], "label": "ewar_v2",
    "rows": {"hit.first2": {"n": 491, "rho_vs_L6": 0.739},
             "hit.first3": {"n": 491, "rho_vs_L6": 0.8711},
             "pit.first2": {"n": 543, "rho_vs_L6": 0.7051},
             "pit.first3": {"n": 543, "rho_vs_L6": 0.876}},
}


class ReservedCohortError(RuntimeError):
    """An outcome read was asked for a reserved debut cohort."""


# ---------------------------------------------------------------------------
# helpers

def _sha(path: Path) -> str | None:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return None


def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def outcome_guard(cohort: int) -> int:
    """Raise unless `cohort` is a development debut cohort whose outcomes may be read."""
    c = int(cohort)
    if c in RESERVED_DEBUT_COHORTS or c >= F.R_VM_FIRST_DEBUT_YEAR:
        raise ReservedCohortError(f"debut cohort {c} is reserved; its outcomes are not read")
    if c not in DEV_OUTCOME_COHORTS:
        raise ReservedCohortError(f"debut cohort {c} is not a development outcome cohort")
    return c


# ---------------------------------------------------------------------------
# 1. the builder's own terms

def builder_terms(debut_year: int, resolved_through: int) -> dict:
    """(observed_seasons, observed_fraction, weight, censored) straight from
    efv_dataset._label_6yr, called with an EMPTY seasons dict while RESOLVED_THROUGH is
    set to `resolved_through` for the call. The terms are a function of the calendar
    only, so nothing is read from any outcome."""
    if D.SERVICE_ALIGNED_WINDOW:
        raise RuntimeError("SERVICE_ALIGNED_WINDOW is on; the calendar window is the pinned regime")
    saved = D.RESOLVED_THROUGH
    try:
        D.RESOLVED_THROUGH = int(resolved_through)
        _resolved, _censored_target, censored, weight, n_obs = D._label_6yr({}, int(debut_year))
    finally:
        D.RESOLVED_THROUGH = saved
    return {"observed_seasons": int(n_obs),
            "observed_fraction": round(n_obs / D.TARGET_SEASONS, 3),
            "weight": float(weight), "censored": bool(censored)}


def terms_table() -> dict:
    return {str(rt): {str(c): builder_terms(c, rt) for c in TERM_COHORTS if c <= rt - 1}
            for rt in (RT_BEFORE, RT_AFTER)}


# ---------------------------------------------------------------------------
# 2. the 2026 gain on the matrices

def load_matrices(paths: dict[str, Path] | None = None) -> dict[str, list[dict]]:
    paths = paths or MATRICES
    return {s: [r for r in _load(paths[s]) if r.get("kind") == "debuted"] for s in SIDES}


def _scored_years() -> tuple[int, ...]:
    import efv_model
    return tuple(int(y) for y in efv_model.SCORED_YEARS)


def cohort_census(mats: dict[str, list[dict]], terms: dict) -> dict:
    """Rows, scored rows, censoring and weight mass per (cohort, side) under both clocks,
    plus the pins against the stored matrix terms."""
    scored_years = _scored_years()
    rows_out, mism = [], {"weight": 0, "observed_seasons": 0, "censored_flag": 0}
    for c in COHORTS:
        t25, t26 = terms[str(RT_BEFORE)][str(c)], terms[str(RT_AFTER)][str(c)]
        for s in SIDES:
            rs = [r for r in mats[s] if int(r.get("debut_year") or 0) == c]
            sc = [r for r in rs if r.get("consensus_fv_raw") is not None and c in scored_years]
            cens = [r for r in rs if bool(r.get("censored"))]
            for r in cens:
                if abs(float(r.get("weight", 1.0)) - t25["weight"]) > 1e-9:
                    mism["weight"] += 1
                if int(r.get("observed_seasons") or 0) != t25["observed_seasons"]:
                    mism["observed_seasons"] += 1
            if t25["censored"] is False and cens:
                mism["censored_flag"] += len(cens)
            # a row the matrix resolved while the calendar says censored is a terminal
            # event (retirement, lifetime ban): it keeps weight 1.0 under both clocks
            terminal = [r for r in rs if not bool(r.get("censored"))] if t25["censored"] else []

            def mass(pool, rt_terms):
                return round(sum(rt_terms["weight"] if bool(r.get("censored"))
                                 else float(r.get("weight", 1.0)) for r in pool), 3)
            moves = len(cens) if (t25["censored"] and not t26["censored"]) else 0
            rows_out.append({
                "debut_cohort": c, "side": s, "rows": len(rs), "scored_rows": len(sc),
                "censored_rows_at_2025": len(cens), "resolved_by_terminal_event": len(terminal),
                "rt_2025": {**t25, "weight_mass_all": mass(rs, t25),
                            "weight_mass_scored": mass(sc, t25)},
                "rt_2026": {**t26, "weight_mass_all": mass(rs, t26),
                            "weight_mass_scored": mass(sc, t26)},
                "delta_weight_mass_all": round(mass(rs, t26) - mass(rs, t25), 3),
                "delta_weight_mass_scored": round(mass(sc, t26) - mass(sc, t25), 3),
                "moves_censored_to_resolved_at_2026": moves,
            })
    totals = {}
    for s in SIDES:
        rr = [r for r in rows_out if r["side"] == s]
        totals[s] = {
            "rows": sum(r["rows"] for r in rr),
            "scored_rows": sum(r["scored_rows"] for r in rr),
            "weight_mass_all_2025": round(sum(r["rt_2025"]["weight_mass_all"] for r in rr), 3),
            "weight_mass_all_2026": round(sum(r["rt_2026"]["weight_mass_all"] for r in rr), 3),
            "weight_mass_scored_2025": round(sum(r["rt_2025"]["weight_mass_scored"] for r in rr), 3),
            "weight_mass_scored_2026": round(sum(r["rt_2026"]["weight_mass_scored"] for r in rr), 3),
            "rows_censored_to_resolved_at_2026": sum(r["moves_censored_to_resolved_at_2026"] for r in rr),
            "censored_rows_2025": sum(r["censored_rows_at_2025"] for r in rr),
            "censored_rows_2026": sum(r["censored_rows_at_2025"] - r["moves_censored_to_resolved_at_2026"]
                                      for r in rr),
        }
        totals[s]["delta_weight_mass_all"] = round(
            totals[s]["weight_mass_all_2026"] - totals[s]["weight_mass_all_2025"], 3)
        totals[s]["delta_weight_mass_scored"] = round(
            totals[s]["weight_mass_scored_2026"] - totals[s]["weight_mass_scored_2025"], 3)
    return {"by": ["debut_cohort", "side"], "scored_years": list(scored_years),
            "rule": ("rows: debuted matrix rows by debut_year; scored_rows: consensus_fv_raw "
                     "present and the cohort in efv_model.SCORED_YEARS (the forward-chained "
                     "pool); weight: the stored row weight for a resolved row, the builder's "
                     "term for a censored row; moves: censored rows whose builder term turns "
                     "resolved at 2026 (counted, never read)"),
            "pins_against_stored_matrix_terms": mism, "rows": rows_out, "totals": totals}


def fold_mass(census: dict) -> list[dict]:
    """Per forward-chained fold Y: train (cohorts < Y) and test (cohort Y) rows and
    weight mass on the scored pool, before and after."""
    out = []
    rows = census["rows"]
    for y in census["scored_years"]:
        rec = {"fold": y}
        for s in SIDES:
            tr = [r for r in rows if r["side"] == s and r["debut_cohort"] < y]
            te = [r for r in rows if r["side"] == s and r["debut_cohort"] == y]
            rec[s] = {"train_rows": sum(r["scored_rows"] for r in tr),
                      "train_mass_2025": round(sum(r["rt_2025"]["weight_mass_scored"] for r in tr), 3),
                      "train_mass_2026": round(sum(r["rt_2026"]["weight_mass_scored"] for r in tr), 3),
                      "test_rows": sum(r["scored_rows"] for r in te),
                      "test_mass_2025": round(sum(r["rt_2025"]["weight_mass_scored"] for r in te), 3),
                      "test_mass_2026": round(sum(r["rt_2026"]["weight_mass_scored"] for r in te), 3)}
        out.append(rec)
    return out


def entering_cohort(census_doc: dict | None, terms: dict) -> dict:
    """The 2025 cohort: admitted by DEBUT_YEARS at RT 2026 at the builder's term, R-VM
    reserved (efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR), counts copied from the label
    pool census, never built or read here."""
    row = None
    if census_doc:
        for r in census_doc["debut_cohorts"]["rows"]:
            if int(r.get("debut_cohort") or 0) == ENTERING_COHORT:
                row = r
    return {"debut_cohort": ENTERING_COHORT, "reserved_vm": True,
            "admitted_by_DEBUT_YEARS_at_2026": ENTERING_COHORT in range(2011, RT_AFTER),
            "builder_terms_at_2026": terms[str(RT_AFTER)][str(ENTERING_COHORT)],
            "debuts": (row or {}).get("debuts"),
            "in_window_consensus_read": (row or {}).get("in_window_consensus_read"),
            "with_career_war_row": (row or {}).get("with_career_war_row"),
            "pins": F.reserved_vm_pins(),
            "note": ("enters the matrix at the epoch's step F at weight 0.333; "
                     "reserved_vm_pins keep it out of SCORED_YEARS and CANDIDATE_YEARS until "
                     "the R-VM look record exists, so it is not in W_after")}


def margin_arithmetic(census: dict, floor_doc: dict | None) -> dict:
    """The resampler's published floor rescaled by the weight mass: arithmetic, not a
    measured floor."""
    out = {"source": "data/xfv_mde_floor.json (tools/efv_mde_lab.py mde 2000: paired "
                     "bootstrap over the whole pool, train and test resampled together, "
                     "refit every draw, seed 20260807; one-sided 95% = 1.645 x sd)",
           "formula": "mde95_after = mde95_onesided_before x sqrt(W_before / W_after), W the "
                      "pair-weight mass of the scored pool (row weight = observed_seasons / 6)",
           "rule": ("the sqrt rescaling PROGRAM.md s2.5 and the census floor curve already use; "
                    "it is arithmetic on a published sd, not a measured floor, and the measured "
                    "floor on the fWAR label is the epoch's step G"),
           "sides": {}}
    if not floor_doc:
        return out
    for s in SIDES:
        w = (floor_doc.get("weighted") or {}).get(s) or {}
        pe = ((floor_doc.get("point_estimates") or {}).get("weighted") or {}).get(s) or {}
        t = census["totals"][s]
        wb, wa = t["weight_mass_scored_2025"], t["weight_mass_scored_2026"]
        m1 = float(w.get("mde95_onesided") or 0.0)
        out["sides"][s] = {
            "n_ref_rows": pe.get("n"), "matrix_rows_ref": (floor_doc.get("basis") or {}).get(
                "matrix_rows", {}).get(s), "sd_ref": w.get("sd"),
            "mde95_onesided_ref": m1, "scored_rows_today": t["scored_rows"],
            "W_before": wb, "W_after": wa,
            "W_ratio": round(wa / wb, 4) if wb else None,
            "mde95_onesided_after": round(m1 * math.sqrt(wb / wa), 4) if (wb and wa) else None,
            "rows_version": "the scored row count is unchanged by the clock, so a row-count "
                            "floor does not move; only the mass moves",
        }
    return out


# ---------------------------------------------------------------------------
# 3. the views

def view_resolution(k: int, rt: int) -> list[int]:
    """Cohorts whose first-k window closed under rt: debut + k - 1 <= rt."""
    return [c for c in COHORTS if c + k - 1 <= rt]


def l6_resolution(rt: int) -> list[int]:
    return [c for c in COHORTS if c + D.TARGET_SEASONS - 1 <= rt]


def _rankdata(a: np.ndarray) -> np.ndarray:
    """Average ranks (ties share the mean rank)."""
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    sa = a[order]
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sa[j + 1] == sa[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or x.std() == 0 or y.std() == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    return _pearson(_rankdata(x), _rankdata(y))


def correlate(x: list[float], y: list[float], *, b: int = B_BOOT, seed: int = SEED) -> dict:
    """Spearman and Pearson of x against y with percentile bootstrap CI95 over rows."""
    xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    n = len(xa)
    rng = np.random.default_rng(seed)
    sp, pe = [], []
    for _ in range(b):
        idx = rng.integers(0, n, n)
        sp.append(_spearman(xa[idx], ya[idx]))
        pe.append(_pearson(xa[idx], ya[idx]))
    sp, pe = np.asarray(sp), np.asarray(pe)
    return {"n": n, "B": b, "seed": seed, "cluster": "row (one row per player per side)",
            "spearman": round(_spearman(xa, ya), 4),
            "spearman_ci95": [round(float(np.nanpercentile(sp, 2.5)), 4),
                              round(float(np.nanpercentile(sp, 97.5)), 4)],
            "pearson": round(_pearson(xa, ya), 4),
            "pearson_ci95": [round(float(np.nanpercentile(pe, 2.5)), 4),
                             round(float(np.nanpercentile(pe, 97.5)), 4)]}


def _window_sum(seasons: dict[int, float], start: int, k: int) -> float:
    years = range(start, start + k)
    if max(years) > MAX_SEASON_READ:
        raise ReservedCohortError(f"season {max(years)} is past MAX_SEASON_READ {MAX_SEASON_READ}")
    return round(sum(float(seasons.get(y, 0.0) or 0.0) for y in years), 3)


def dev_rows(mats: dict[str, list[dict]]) -> dict[str, list[dict]]:
    out = {}
    for s in SIDES:
        rs = [r for r in mats[s] if int(r.get("debut_year") or 0) in DEV_OUTCOME_COHORTS]
        for r in rs:
            outcome_guard(int(r["debut_year"]))
        if len({r["player_key"] for r in rs}) != len(rs):
            raise RuntimeError(f"{s}: a player appears twice among the development rows")
        out[s] = rs
    return out


def ewar_series() -> dict[str, dict[int, float]]:
    """{player_key: {season: war}} on the served provider, the builder's own input."""
    return L.war_seasons_table()


def id_map(mats: dict[str, list[dict]], debuts: list[dict] | None,
           overrides: dict | None) -> dict[str, int]:
    """player_key -> mlbam id: the matrix row's id, else debuts.json, else the
    validated override asset. Identity only; no outcome."""
    out: dict[str, int] = {}
    for s in SIDES:
        for r in mats[s]:
            if r.get("mlbam_id"):
                out.setdefault(r["player_key"], int(r["mlbam_id"]))
    for rec in debuts or []:
        if rec.get("mlbam_id") and rec.get("player_key"):
            out.setdefault(rec["player_key"], int(rec["mlbam_id"]))
    ov = overrides or {}
    items = ov.get("overrides", ov) if isinstance(ov, dict) else {}
    if isinstance(items, dict):
        for pk, v in items.items():
            mid = v.get("mlbam_id") if isinstance(v, dict) else v
            try:
                if mid:
                    out.setdefault(str(pk), int(mid))
            except (TypeError, ValueError):
                continue
    return out


def fwar_series(blob: dict, ids: set[int], group: str) -> dict[int, dict[int, float]]:
    """{mlbam: {season: war}} from the frozen vintage, seasons up to MAX_SEASON_READ
    only (no 2025 or 2026 line is read), one side group."""
    out: dict[int, dict[int, float]] = {i: {} for i in ids}
    for season in range(min(DEV_OUTCOME_COHORTS), MAX_SEASON_READ + 1):
        table = FV.war_by_group(blob, season, group)
        for i in ids:
            if i in table:
                out[i][season] = float(table[i])
    return out


def views_census(mats: dict[str, list[dict]], terms: dict, *, census_doc: dict | None,
                 ewar: dict[str, dict[int, float]] | None, fwar_blob: dict | None,
                 ids: dict[str, int] | None) -> dict:
    dev = dev_rows(mats)
    coh_rows = {r["debut_cohort"]: r for r in (census_doc or {}).get("debut_cohorts", {}).get("rows", [])}
    # per-side series on both providers, development cohorts only
    series = {"ewar_v2": {}, "fwar_frozen": {}}
    coverage = {"ewar_v2": {}, "fwar_frozen": {}}
    reconcile = {}
    for s in SIDES:
        rows = dev[s]
        if ewar is not None:
            ser = {r["player_key"]: ewar.get(r["player_key"]) for r in rows}
            series["ewar_v2"][s] = {pk: v for pk, v in ser.items() if v is not None}
            coverage["ewar_v2"][s] = {"rows": len(rows), "with_series": len(series["ewar_v2"][s])}
            ok = sum(1 for r in rows if r["player_key"] in series["ewar_v2"][s]
                     and abs(_window_sum(series["ewar_v2"][s][r["player_key"]], int(r["debut_year"]),
                                         D.TARGET_SEASONS) - float(r["target_resolved"])) < 0.0015)
            reconcile[s] = {"six_season_sum_equals_target_resolved": ok,
                            "of": coverage["ewar_v2"][s]["with_series"]}
        if fwar_blob is not None and ids is not None:
            mids = {ids[r["player_key"]] for r in rows if r["player_key"] in ids}
            fs = fwar_series(fwar_blob, mids, SIDE_GROUP[s])
            series["fwar_frozen"][s] = {r["player_key"]: fs[ids[r["player_key"]]]
                                        for r in rows if r["player_key"] in ids}
            coverage["fwar_frozen"][s] = {
                "rows": len(rows), "with_mlbam_id": len(mids),
                "with_a_line_in_window": sum(1 for r in rows if r["player_key"] in ids
                                             and fs[ids[r["player_key"]]]),
                "note": "joined by MLBAM id (matrix row, debuts.json, override asset); a row "
                        "with an id and no line in its window is a zero label, like the builder"}
    out = {"by": ["label_view", "side"], "resolved_through": {"before": RT_BEFORE, "after": RT_AFTER},
           "window_convention": "debut_year .. debut_year + k - 1 (SERVICE_ALIGNED_WINDOW off)",
           "outcome_cohorts_read": list(DEV_OUTCOME_COHORTS), "max_season_read": MAX_SEASON_READ,
           "coverage": coverage, "ewar_reconciliation_to_matrix_label": reconcile,
           "prior_measurement": E2_PRIOR, "views": {}}
    for name, k in VIEWS.items():
        v = {"definition": f"summed WAR over the first {k} MLB seasons from the debut year",
             "k": k, "resolves_when": f"debut_year + {k - 1} <= RESOLVED_THROUGH",
             "resolved_cohorts": {str(rt): view_resolution(k, rt) for rt in (RT_BEFORE, RT_AFTER)},
             "l6_resolved_cohorts": {str(rt): l6_resolution(rt) for rt in (RT_BEFORE, RT_AFTER)},
             "rows_resolved_without_projection": {}, "rows_beyond_l6": {},
             "debuts_json": {}, "share_of_six_season_mass": {}, "projection_bias_removed": {},
             "correlation_with_l6": {}}
        for rt in (RT_BEFORE, RT_AFTER):
            vc, lc = set(view_resolution(k, rt)), set(l6_resolution(rt))
            v["rows_resolved_without_projection"][str(rt)] = {
                s: sum(1 for r in mats[s] if int(r.get("debut_year") or 0) in vc) for s in SIDES}
            v["rows_beyond_l6"][str(rt)] = {
                "cohorts": sorted(vc - lc),
                **{s: sum(1 for r in mats[s] if int(r.get("debut_year") or 0) in (vc - lc))
                   for s in SIDES}}
            v["debuts_json"][str(rt)] = {
                "cohorts_beyond_l6": sorted(vc - lc),
                "debuts": sum(int(coh_rows[c]["debuts"]) for c in sorted(vc - lc) if c in coh_rows),
                "with_career_war_row": sum(int(coh_rows[c]["with_career_war_row"])
                                           for c in sorted(vc - lc) if c in coh_rows),
                "source": "data/efv_label_pool_census.json debut_cohorts (presence only)"}
        v["share_of_six_season_mass"]["censoring_gate_profile"] = {
            "first_k_share": round(sum(SEASON_SHARE_PROFILE[:k]), 3),
            "profile": list(SEASON_SHARE_PROFILE), "path": CENSORING_GATE,
            "key": "season_share_profile_diagnostic (988 fully resolved debuts, pooled)"}
        v["projection_bias_removed"] = {"at_n_obs": k, "path": CENSORING_GATE,
                                        "section": "6.2 by_n_obs_and_side",
                                        **CENSORING_BIAS[k]}
        for prov in ("ewar_v2", "fwar_frozen"):
            if not series[prov]:
                continue
            v["correlation_with_l6"][prov] = {}
            for s in SIDES:
                ser = series[prov][s]
                rows = [r for r in dev[s] if r["player_key"] in ser]
                x = [_window_sum(ser[r["player_key"]], int(r["debut_year"]), k) for r in rows]
                y = [_window_sum(ser[r["player_key"]], int(r["debut_year"]), D.TARGET_SEASONS)
                     for r in rows]
                c = correlate(x, y)
                c["label_to_label"] = True
                c["cohorts"] = list(DEV_OUTCOME_COHORTS)
                sy = sum(y)
                v["share_of_six_season_mass"].setdefault("development_rows", {})[f"{prov}.{s}"] = (
                    round(sum(x) / sy, 3) if sy else None)
                v["correlation_with_l6"][prov][s] = c
        out["views"][name] = v
    return out


# ---------------------------------------------------------------------------
# 4. the admission rule and the calibration record (recorded design, no computation)

ADMISSION_RULE = {
    "standing": "SECONDARY label views, reported beside the primary, never a frame change",
    "primary": {"vm": "L6, the six-season label (efv_dataset._label_6yr), censored tail "
                      "projected at the observed rate, weight observed_seasons / 6",
                "lv": "W3 (efv_labels.labels_for), WAR over the first three seasons, 0 if no "
                      "debut in V..V+3"},
    "rules": [
        "A secondary view is reported beside the primary in the same table, with its own n, "
        "its own floor from the same resampler, and the word SECONDARY; it never replaces the "
        "primary before a reserved read, and no ship decision, weight, order or claim reads it.",
        "A view enters the screening lab (EFV3_B1) as a label family 'label_view' with members "
        "first3 and first4: the candidate arm is the base assembly scored against the view "
        "instead of the primary, on the same development folds, with the same statistic, the "
        "same noise-column floors and its own Holm family; it admits nothing to the assembly.",
        "A view enters the matrix (EFV3_D1 / D2) as a LABEL-VIEW axis beside the outcome "
        "thresholds (1, 2, 3, 4 career WAR): every cell declares which label it was scored "
        "against, and a cell on a secondary view carries the word SECONDARY and its target-"
        "validity note.",
        "Target validity is stated plainly wherever a view is printed: the industry FV frame is "
        "six-year value (the five FanGraphs FV-to-WAR tables, the Clemens kernel and the served "
        "grade are all six-season quantities), so a first-k view measures a different quantity, "
        "and its gain is rows resolved without projection, not accuracy.",
        "On a reserved frame a view is read only by the look that owns the frame, in the same "
        "run, as a secondary row; a view never opens a reserved frame on its own.",
        "The 2026 season is a label season only after the epoch's step D+U moves "
        "RESOLVED_THROUGH; before that no view reads a 2025 or 2026 line (this tool reads "
        "through 2024).",
    ],
}

CALIBRATION_RECORD = [
    {"surface": "the training label (efv_dataset._label_6yr; efv_model fits target_censored)",
     "file": "efv_dataset.py", "clock": "RESOLVED_THROUGH = 2025 (DEBUT_YEARS derived from it)",
     "reads_2026_after_epoch": "yes, at step D+U when the constant moves and step F rebuilds "
                               "both matrices", "task": "EPOCH_RUN (steps D+U, F)"},
    {"surface": "W3, W2, R3 and the never-resolution labels on the list-vintage frames "
                "(efv_labels.labels_for; the V2 P5 re-derivation and DS-16 re-run read them)",
     "file": "efv_labels.py", "clock": "resolved_through() returns efv_dataset.RESOLVED_THROUGH",
     "reads_2026_after_epoch": "yes, with efv_dataset; P5 re-derives data/efv_v2_assembly.json "
                               "once on the frozen label", "task": "EPOCH_RUN then EFV_V2_GATE P5"},
    {"surface": "the FV-to-WAR anchors (value_framework fv_to_6yr_avg_war; empirical_anchors)",
     "file": "value_framework.py, empirical_anchors.py",
     "clock": "no RESOLVED_THROUGH: the cohort is snapshot years reference_year - 9 to - 6 "
              "(2017 to 2020 in 2026) and realized is the first six stored MLB seasons as the "
              "career_war table holds them",
     "reads_2026_after_epoch": "yes, once step C rebases career_war to fwar and step J runs "
                               "value_framework.py --fit (then re-applies the sub-45 knots); "
                               "note the window is calendar-lagged, not clock-gated, so a 2020 "
                               "listing's late debut is summed short", "task": "EPOCH_RUN (steps C, J)"},
    {"surface": "the pooled FV -> outcome curve, THE eFV grade map (fv_outcome_pooled_grade)",
     "file": "tools/fv_outcome_curve_pooled.py", "clock": "no own clock: matrix rows with "
                                                         "censored == False",
     "reads_2026_after_epoch": "yes, through the rebuilt matrices; the 2021 cohort joins the "
                               "uncensored pool", "task": "EPOCH_RUN (step I after F)"},
    {"surface": "the calibration knots (backtest.fit_calibration_knots; CAL_KNOTS_REFIT_17M)",
     "file": "backtest.py", "clock": "no RESOLVED_THROUGH: realized seasons priced from the "
                                     "PlayerRecord's realized series as stored",
     "reads_2026_after_epoch": "yes, through the career_war table after step C; the refit is "
                               "its own queued task and must run after step C to read 2026",
     "task": "CAL_KNOTS_REFIT_17M (after EPOCH_RUN step C)"},
    {"surface": "the star label and star_odds_model",
     "file": "tools/build_star_odds_artifacts.py", "clock": "_RESOLVED_THROUGH = 2025, moved "
                                                           "with efv_dataset's by decision O2",
     "reads_2026_after_epoch": "yes, at step N", "task": "EPOCH_RUN (step N)"},
    {"surface": "the consensus accuracy backtest and the Source Comparison ledger stamp",
     "file": "source_backtest.py, efv_progress.py", "clock": "stamps efv_dataset.RESOLVED_THROUGH "
                                                             "into the receipt and model_version",
     "reads_2026_after_epoch": "yes, at step Q and the ledger refresh", "task": "EPOCH_RUN (step Q)"},
    {"surface": "the Clemens anchors (clemens_2026 valuation set: the published FV-to-outcome "
                "and $/WAR tables)",
     "file": "value_framework.py", "clock": "none: a published external table, never "
                                           "re-measured on our label",
     "reads_2026_after_epoch": "not applicable; coherence with the label is by construction "
                               "once the label is published fWAR (gate part 1)", "task": "none"},
]


# ---------------------------------------------------------------------------
# build

def build(*, now: datetime | None = None, matrices: dict[str, Path] | None = None,
          with_outcomes: bool = True) -> dict:
    now = now or datetime.now(timezone.utc)
    if int(D.RESOLVED_THROUGH) != RT_BEFORE:
        raise RuntimeError(f"efv_dataset.RESOLVED_THROUGH is {D.RESOLVED_THROUGH}, not {RT_BEFORE}: "
                           "the epoch has moved the clock; this census is a pre-epoch read")
    terms = terms_table()
    mats = load_matrices(matrices)
    census = cohort_census(mats, terms)
    census_doc = _load(CENSUS) if CENSUS.exists() else None
    floor_doc = _load(MDE_FLOOR) if MDE_FLOOR.exists() else None
    ewar = fwar_blob = ids = None
    if with_outcomes:
        ewar = ewar_series()
        if FV.available():
            fwar_blob = FV.load()
            debuts = _load(DEBUTS) if DEBUTS.exists() else None
            overrides = _load(OVERRIDES) if OVERRIDES.exists() else None
            ids = id_map(mats, debuts, overrides)
    views = views_census(mats, terms, census_doc=census_doc, ewar=ewar, fwar_blob=fwar_blob, ids=ids)
    vintage = None
    if fwar_blob is not None:
        vintage = {"path": "data/fwar_vintage.json", "vintage_id": fwar_blob.get("vintage_id"),
                   "fwar_seasons": [min(FV.fwar_seasons(fwar_blob)), max(FV.fwar_seasons(fwar_blob))],
                   "seasons_read_here": [min(DEV_OUTCOME_COHORTS), MAX_SEASON_READ],
                   "sha256": _sha(FV.VINTAGE_PATH)}
    return {
        "schema": SCHEMA, "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "produced_by": "tools/efv_label_horizon_2026.py", "task": TASK,
        "model_id": "efv_label_horizon", "role": "development",
        "adjudicates": "nothing; the label builder's own terms, counts, and label-to-label "
                       "correlations; no rater enters and nothing is grouped by an FV cell",
        "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                  "resolved_through_after": RT_AFTER,
                  "id": f"{L.provider()}@{(census_doc or {}).get('label', {}).get('id', '').split('@')[-1]}"
                        if census_doc else L.provider(),
                  "frozen_fwar_vintage": vintage},
        "guards": {"reserved_debut_cohorts_never_read": sorted(RESERVED_DEBUT_COHORTS) +
                   [F.R_VM_FIRST_DEBUT_YEAR, F.R_VM_FIRST_DEBUT_YEAR + 1],
                   "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
                   "reserved_lv": sorted(F.RESERVED_LV), "reserved_vm_pins": F.reserved_vm_pins(),
                   "outcome_cohorts_read": list(DEV_OUTCOME_COHORTS),
                   "max_season_read": MAX_SEASON_READ, "no_rater_score": True,
                   "anchor_gate": "no statistic by consensus-FV cell (docs/PROSPECT_ANCHOR_GATE.md)",
                   "service_aligned_window": bool(D.SERVICE_ALIGNED_WINDOW)},
        "code": {"commit": _git_commit(), "tool_sha256": _sha(Path(__file__)),
                 "efv_dataset_sha256": _sha(ROOT / "efv_dataset.py")},
        "inputs": {"matrices": {s: {"path": str(Path(p).relative_to(ROOT)).replace("\\", "/"),
                                    "sha256": _sha(p)} for s, p in (matrices or MATRICES).items()},
                   "census": {"path": "data/efv_label_pool_census.json", "sha256": _sha(CENSUS)},
                   "mde_floor": {"path": "data/xfv_mde_floor.json", "sha256": _sha(MDE_FLOOR)}},
        "builder_terms": terms,
        "cohorts": census,
        "folds": fold_mass(census),
        "entering_cohort": entering_cohort(census_doc, terms),
        "margin_arithmetic": margin_arithmetic(census, floor_doc),
        "label_views": views,
        "admission_rule": ADMISSION_RULE,
        "calibration_record": CALIBRATION_RECORD,
        "progress_ledger": {"appended": False,
                            "reason": "data/efv_progress.json rows are frame rows (a row is "
                                      "added when a frame's measured content changes) and the "
                                      "frame registry has no label-pool frame; no row type for "
                                      "a label-pool note exists, so none is appended"},
        "epoch": "the eFV label is in an epoch (docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md): "
                 "label.resolved_through stamps this read; a run after step D+U is a new read, "
                 "never an edit",
    }


def write_artifact(doc: dict, out: Path = OUT) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def summary(doc: dict) -> dict:
    t = doc["cohorts"]["totals"]
    views = {name: {prov: {s: (c["spearman"], c["spearman_ci95"], c["n"])
                           for s, c in by.items()}
                    for prov, by in v["correlation_with_l6"].items()}
             for name, v in doc["label_views"]["views"].items()}
    return {"generated_at": doc["generated_at"], "label": doc["label"]["id"],
            "pins": doc["cohorts"]["pins_against_stored_matrix_terms"],
            "totals": t, "margin": {s: doc["margin_arithmetic"]["sides"].get(s) for s in SIDES},
            "views": views}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--no-outcomes", action="store_true",
                    help="terms and counts only; no series is read")
    a = ap.parse_args(argv)
    doc = build(with_outcomes=not a.no_outcomes)
    p = write_artifact(doc, Path(a.out))
    print(f"wrote {p}")
    if a.summary:
        print(json.dumps(summary(doc), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
