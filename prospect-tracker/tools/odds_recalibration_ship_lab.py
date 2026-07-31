# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE-ODDS-SHIP: re-fit and re-measure efv_odds_calibration on the CURRENT tree.

MEASUREMENT ONLY. This module imports production code read-only, edits nothing, and
writes exactly one artifact (data/xfv_odds_recalibration_ship_eval.json). It is never
imported by the site or by any exporter.

Pre-registration (written to disk BEFORE this lab existed, and not altered afterwards):
docs/efv-2026-07-30/ODDS_RECALIBRATION_SHIP_GATE.md. Gate: docs/EFV_GATE_STANDARD.md.

THE CONTEST
-----------
    INC    p_bucket_given_fv(realized_implied_fv(war, is_pit, age, pos))[bust]
    CAL    INC through a forward-chained per-side Platt map, logit(p') = a + b*logit(p),
           fit ONLY on out-of-fold rows from decision years strictly before the test fold
           and ONLY within the cut's own population (so the served arm is production)
    CONST  a flat constant at the same cut's prior-fold base rate

SHIP CRITERION (pre-registered, section 1.8): CAL must beat BOTH baselines on Brier AND
log loss with the paired refit bootstrap CI95 excluding zero, on `pooled` AND on
`pooled_served`, and both deltas must sit outside their permutation null bands. Beating
the incumbent alone is a NULL.

Run:  python -m tools.odds_recalibration_ship_lab            (from the repo root)
      python -m tools.odds_recalibration_ship_lab --quick    (B=60, smoke check)
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

from tools.odds_grade_basis_lab import (                     # noqa: E402
    CAL_YEARS, SEED, N_BINS,
    load_side, score_chain, training_base_rates,
    brier, logloss, murphy, calibration_ab, auc, reliability_curve,
    irls_logit, _logit, platt_apply,
)

B_BOOT = 1000
B_PERM = 1000

# POST-HOC sensitivity switch (see prepare_cut). OFF is the pre-registered gate.
FITTED_FOLDS_ONLY = bool(os.environ.get("EEPHUS_ODDS_FITTED_FOLDS_ONLY"))
_ARTIFACT = ("xfv_odds_recalibration_ship_fittedfolds_eval.json" if FITTED_FOLDS_ONLY
             else "xfv_odds_recalibration_ship_eval.json")

# Cut -> (side filter, track filter). None means "no restriction".
CUTS = {
    "hit":            ("hit", None),
    "pit":            ("pit", None),
    "pooled":         (None, None),
    "hit_served":     ("hit", True),
    "pit_served":     ("pit", True),
    "pooled_served":  (None, True),
    "pooled_no_track": (None, False),      # the population the production guard EXCLUDES
}
# The cuts whose CAL arm uses the SERVED (applied-population) Platt chain.
_SERVED_CUTS = {"hit_served", "pit_served", "pooled_served"}
GATE_CUTS = ("pooled", "pooled_served")
ARMS = ("INC", "CAL", "CONST", "CONST_all")


def _select(rows, cut):
    side, track = CUTS[cut]
    out = rows
    if side is not None:
        out = [r for r in out if r["side"] == side]
    if track is not None:
        out = [r for r in out if bool(r["has_track"]) is track]
    return out


# ===========================================================================
# the two arms that have to be fit: CAL (Platt) and CONST (climatology)
# ===========================================================================
def attach_platt_chain(rows: list[dict], *, population: str) -> None:
    """Forward-chained per-SIDE Platt, fit within `population`.

    population "all"    -> fit on every prior-fold row of that side
    population "served" -> fit on prior-fold rows of that side WITH a track record,
                           which is what the production guard (`not src.get("milb")`)
                           actually admits.

    Writes CAL_all / CAL_served onto every row of that side. Fold CAL_YEARS[0] carries
    no prior rows, so it falls back to INC unchanged (a tie by construction, which costs
    the candidate).
    """
    field = f"CAL_{population}"
    for side in ("hit", "pit"):
        srows = [r for r in rows if r["side"] == side]
        for yr in CAL_YEARS:
            hist = [r for r in srows if r["fold"] < yr
                    and (population == "all" or r["has_track"])]
            cur = [r for r in srows if r["fold"] == yr]
            if not cur:
                continue
            ab = None
            if len(hist) >= 25:
                ab = irls_logit(_logit([r["INC"] for r in hist]),
                                np.array([r["y"] for r in hist], float))
            vals = platt_apply([r["INC"] for r in cur], ab)
            for r, v in zip(cur, vals):
                r[field] = float(v)
                r[f"{field}_fitted"] = ab is not None
                r[f"{field}_ab"] = None if ab is None else [round(ab[0], 4), round(ab[1], 4)]


def attach_constants(rows: list[dict], base_all: dict) -> None:
    """CONST_all is the basis gate's arm C: the fold's FULL resolved-training base rate.

    CONST is the within-cut climatology and is attached per cut by `_const_for_cut`,
    because the honest zero-information forecast for a population is that population's
    own prior-fold base rate, not the whole frame's.
    """
    for r in rows:
        # training_base_rates returns {"bust": {fold: rate}, "star": {...}} -- index the
        # BUST map, not the outer dict (a .get(fold) on the outer dict silently returns
        # the 0.5 default and turns arm C into a coin flip).
        r["CONST_all"] = float(base_all[r["side"]]["bust"].get(r["fold"], 0.5))


def _const_for_cut(rows_in_cut: list[dict]) -> None:
    """Attach CONST = the cut's own prior-fold base rate, forward-chained.

    Fold CAL_YEARS[0] has no prior folds inside the cut, so it falls back to CONST_all
    (the honest information set at that point), exactly as CAL falls back to INC there.
    """
    by_fold: dict = {}
    for r in rows_in_cut:
        by_fold.setdefault(r["fold"], []).append(r)
    for yr in sorted(by_fold):
        hist = [r for r in rows_in_cut if r["fold"] < yr]
        if len(hist) >= 25:
            br = float(np.mean([r["y"] for r in hist]))
            for r in by_fold[yr]:
                r["CONST"] = br
        else:
            for r in by_fold[yr]:
                r["CONST"] = r["CONST_all"]


# ===========================================================================
# one full pass: score the chain, attach both arms
# ===========================================================================
def build_frame(bundles, resampled=None) -> list[dict]:
    """Out-of-fold rows for both sides with INC, CAL_all, CAL_served and CONST_all."""
    rows: list[dict] = []
    base_all = {}
    for side, bundle in bundles.items():
        data = None if resampled is None else resampled[side]
        base_all[side] = training_base_rates(bundle, data)
        for r in score_chain(bundle, data, with_platt=False):
            rows.append({
                "player_key": r["player_key"], "side": side, "fold": r["fold"],
                "has_track": bool(r["has_track"]),
                "INC": float(r["A_bust"]), "y": int(r["y_bust"]),
                "xfv_war": float(r["xfv_war"]), "grade_odds": float(r["grade_old"]),
                "target_resolved": float(r["target_resolved"]),
            })
    attach_constants(rows, base_all)
    attach_platt_chain(rows, population="all")
    attach_platt_chain(rows, population="served")
    return rows


def _cal_field(cut: str) -> str:
    return "CAL_served" if cut in _SERVED_CUTS else "CAL_all"


def prepare_cut(rows: list[dict], cut: str) -> list[dict]:
    """COPIES the selected rows before stamping CONST and CAL.

    The cuts OVERLAP (a served hitter is in `hit`, `pooled`, `hit_served` and
    `pooled_served`), and both of those fields are cut-dependent: CONST is the cut's own
    climatology and CAL is the served chain on served cuts and the all chain elsewhere.
    Stamping them in place would let the last cut prepared overwrite every earlier cut's
    arms on the shared row objects, so every report would silently describe the last cut.
    """
    sub = [dict(r) for r in _select(rows, cut)]
    if not sub:
        return sub
    fld = _cal_field(cut)
    if FITTED_FOLDS_ONLY:
        # POST-HOC SENSITIVITY, not part of the pre-registered criterion. Drops the
        # early folds where the forward chain had too few prior rows to fit a Platt
        # map and CAL therefore falls back to INC. Production has no such fold: it
        # carries one map fitted on all history. This asks whether the verdict is an
        # artifact of that fallback. Run via EEPHUS_ODDS_FITTED_FOLDS_ONLY=1, which
        # writes a SEPARATE artifact so the primary gate is never overwritten.
        sub = [r for r in sub if r.get(f"{fld}_fitted")]
        if not sub:
            return sub
    _const_for_cut(sub)
    for r in sub:
        r["CAL"] = float(r.get(fld, r["INC"]))
    return sub


# ===========================================================================
# reporting
# ===========================================================================
def arm_report(sub: list[dict], arm: str) -> dict:
    p = np.array([r[arm] for r in sub], float)
    y = np.array([r["y"] for r in sub], float)
    m = murphy(p, y, N_BINS)
    a, b = calibration_ab(p, y)
    au = auc(p, y)
    return {
        "n": int(p.size), "n_pos": int(y.sum()),
        "brier": round(brier(p, y), 6), "logloss": round(logloss(p, y), 6),
        "ece": round(m["ece"], 6), "reliability": round(m["reliability"], 6),
        "resolution": round(m["resolution"], 6), "uncertainty": round(m["uncertainty"], 6),
        "cal_slope": (None if b is None else round(b, 4)),
        "cal_intercept": (None if a is None else round(a, 4)),
        "cal_in_the_large": round(float(p.mean() - y.mean()), 6),
        "mean_p": round(float(p.mean()), 6), "base_rate": round(float(y.mean()), 6),
        "auc": (None if au is None else round(au, 4)),
    }


def cut_report(sub: list[dict]) -> dict:
    if not sub:
        return {}
    out = {"arms": {a: arm_report(sub, a) for a in ARMS}}
    out["reliability_curve"] = {
        a: reliability_curve([r[a] for r in sub], [r["y"] for r in sub])
        for a in ("INC", "CAL")}
    per_fold = {}
    for yr in CAL_YEARS:
        f = [r for r in sub if r["fold"] == yr]
        if len(f) < 10:
            continue
        y = [r["y"] for r in f]
        row = {"n": len(f), "base_rate": round(float(np.mean(y)), 4),
               "platt_fitted": any(r["CAL"] != r["INC"] for r in f)}
        for a in ARMS:
            row[f"brier_{a}"] = round(brier([r[a] for r in f], y), 6)
            row[f"logloss_{a}"] = round(logloss([r[a] for r in f], y), 6)
        row["d_inc_brier"] = round(row["brier_INC"] - row["brier_CAL"], 6)
        row["d_inc_logloss"] = round(row["logloss_INC"] - row["logloss_CAL"], 6)
        row["d_const_brier"] = round(row["brier_CONST"] - row["brier_CAL"], 6)
        row["d_const_logloss"] = round(row["logloss_CONST"] - row["logloss_CAL"], 6)
        per_fold[str(yr)] = row
    out["per_fold"] = per_fold
    return out


# ===========================================================================
# controls
# ===========================================================================
def _deltas(sub: list[dict]) -> dict:
    """d = metric(baseline) - metric(CAL); POSITIVE means the recalibration is better."""
    y = [r["y"] for r in sub]
    cal = [r["CAL"] for r in sub]
    inc = [r["INC"] for r in sub]
    con = [r["CONST"] for r in sub]
    bc, lc = brier(cal, y), logloss(cal, y)
    return {
        "d_inc_brier": brier(inc, y) - bc,
        "d_inc_logloss": logloss(inc, y) - lc,
        "d_const_brier": brier(con, y) - bc,
        "d_const_logloss": logloss(con, y) - lc,
        "d_inc_ece": murphy(inc, y, N_BINS)["ece"] - murphy(cal, y, N_BINS)["ece"],
    }


_DKEYS = ("d_inc_brier", "d_inc_logloss", "d_const_brier", "d_const_logloss", "d_inc_ece")


def _ci(vals) -> dict:
    if not vals:
        return {"n_draws": 0}
    a = np.asarray(vals, float)
    return {"n_draws": int(a.size), "mean": round(float(a.mean()), 6),
            "sd": round(float(a.std(ddof=1)), 6) if a.size > 1 else None,
            "ci95": [round(float(np.percentile(a, 2.5)), 6),
                     round(float(np.percentile(a, 97.5)), 6)],
            "p_cal_better": round(float((a > 0).mean()), 4)}


def paired_bootstrap(bundles, B: int, seed: int = SEED, verbose: bool = True) -> dict:
    """Player-clustered paired bootstrap resampling TRAIN AND TEST with a full refit of
    the ridge + linear-calibration + consensus-OLS chain AND a full re-fit of the
    forward-chained Platt maps on every draw."""
    draws = {c: {k: [] for k in _DKEYS} for c in CUTS}
    t0 = time.time()
    for i in range(B):
        rng = np.random.RandomState(seed + i)
        resampled = {}
        for side, bundle in bundles.items():
            data = bundle["data"]
            idx = rng.randint(0, len(data), len(data))
            resampled[side] = [data[j] for j in idx]
        rows = build_frame(bundles, resampled)
        for cut in CUTS:
            sub = prepare_cut(rows, cut)
            if len(sub) < 30 or len(set(r["y"] for r in sub)) < 2:
                continue
            for k, v in _deltas(sub).items():
                if v == v:
                    draws[cut][k].append(v)
        if verbose and (i + 1) % 25 == 0:
            el = time.time() - t0
            print(f"    bootstrap {i+1}/{B}  {el:.0f}s elapsed, "
                  f"~{el/(i+1)*(B-i-1):.0f}s left", flush=True)
    return {c: {k: _ci(v) for k, v in d.items()} for c, d in draws.items()}


def _null_band(vals) -> dict:
    if not vals:
        return {"n_draws": 0}
    a = np.asarray(vals, float)
    return {"n_draws": int(a.size), "mean": round(float(a.mean()), 6),
            "band95": [round(float(np.percentile(a, 2.5)), 6),
                       round(float(np.percentile(a, 97.5)), 6)]}


def permutation_null(cuts_rows: dict, B: int, seed: int = SEED) -> dict:
    """Label permuted WITHIN fold, all three forecasts held fixed.

    LOAD-BEARING HERE. A Platt map shrinks toward the base rate, so under labels that
    carry no information the shrunk arm beats the sharp one automatically: the INC - CAL
    null is POSITIVE by construction. The CONST - CAL null is NEGATIVE by the mirror
    argument (a constant is optimal when nothing is knowable). An observed delta inside
    its band is a null whatever its bootstrap CI says.
    """
    out = {}
    for cut, sub in cuts_rows.items():
        if len(sub) < 30:
            out[cut] = {"n_draws": 0}
            continue
        by_fold: dict = {}
        for i, r in enumerate(sub):
            by_fold.setdefault(r["fold"], []).append(i)
        ys = [r["y"] for r in sub]
        inc = [r["INC"] for r in sub]
        cal = [r["CAL"] for r in sub]
        con = [r["CONST"] for r in sub]
        rng = random.Random(seed + 104729)
        acc = {k: [] for k in ("d_inc_brier", "d_inc_logloss",
                               "d_const_brier", "d_const_logloss")}
        for _ in range(B):
            yp = list(ys)
            for _f, idxs in by_fold.items():
                vals = [ys[i] for i in idxs]
                rng.shuffle(vals)
                for i, v in zip(idxs, vals):
                    yp[i] = v
            if len(set(yp)) < 2:
                continue
            bc, lc = brier(cal, yp), logloss(cal, yp)
            acc["d_inc_brier"].append(brier(inc, yp) - bc)
            acc["d_inc_logloss"].append(logloss(inc, yp) - lc)
            acc["d_const_brier"].append(brier(con, yp) - bc)
            acc["d_const_logloss"].append(logloss(con, yp) - lc)
        out[cut] = {k: _null_band(v) for k, v in acc.items()}
    return out


def test_only_bootstrap(cuts_rows: dict, B: int, seed: int = SEED) -> dict:
    """Row-resample-only. Reported ONLY to document how far it understates sd."""
    out = {}
    for cut, sub in cuts_rows.items():
        if len(sub) < 30:
            out[cut] = {"n_draws": 0}
            continue
        rng = np.random.RandomState(seed + 7919)
        acc = {k: [] for k in _DKEYS}
        n = len(sub)
        for _ in range(B):
            idx = rng.randint(0, n, n)
            s2 = [sub[j] for j in idx]
            if len(set(r["y"] for r in s2)) < 2:
                continue
            for k, v in _deltas(s2).items():
                if v == v:
                    acc[k].append(v)
        out[cut] = {k: _ci(v) for k, v in acc.items()}
    return out


# ===========================================================================
# the constants that would actually ship
# ===========================================================================
def production_fits(rows: list[dict]) -> dict:
    """The single GLOBAL per-side Platt map production would carry, plus the per-fold
    trajectory the pre-registration (1.8.6) requires so the global value can be taken
    from the conservative end of the measured range if the slopes trend.

    Three candidate frames per side:
      served  - rows with a track record, i.e. the APPLIED population (the production
                guard is `not src.get("milb")`, which is the same rows to within 1)
      all     - every resolved out-of-fold row
      notrack - the excluded population, for information only
    """
    out = {}
    for side in ("hit", "pit"):
        srows = [r for r in rows if r["side"] == side]
        frames = {
            "served": [r for r in srows if r["has_track"]],
            "all": srows,
            "no_track": [r for r in srows if not r["has_track"]],
        }
        side_out = {}
        for nm, fr in frames.items():
            if len(fr) < 25:
                side_out[nm] = {"n": len(fr), "ab": None}
                continue
            ab = irls_logit(_logit([r["INC"] for r in fr]),
                            np.array([r["y"] for r in fr], float))
            side_out[nm] = {"n": len(fr), "base_rate": round(float(np.mean([r["y"] for r in fr])), 4),
                            "ab": None if ab is None else [round(ab[0], 4), round(ab[1], 4)]}
        # per-fold trajectory on the APPLIED frame: cumulative prior folds
        traj = []
        for yr in CAL_YEARS:
            hist = [r for r in srows if r["fold"] < yr and r["has_track"]]
            if len(hist) < 25:
                traj.append({"through": yr - 1, "n": len(hist), "ab": None})
                continue
            ab = irls_logit(_logit([r["INC"] for r in hist]),
                            np.array([r["y"] for r in hist], float))
            traj.append({"through": yr - 1, "n": len(hist),
                         "ab": None if ab is None else [round(ab[0], 4), round(ab[1], 4)]})
        side_out["trajectory_applied_frame"] = traj
        out[side] = side_out
    return out


# ===========================================================================
# main
# ===========================================================================
def main(quick: bool = False) -> dict:
    b_boot = 60 if quick else B_BOOT
    b_perm = 200 if quick else B_PERM
    t_start = time.time()

    print("LANE-ODDS-SHIP: re-fit + re-measure efv_odds_calibration on the current tree")
    print("  pre-registration: docs/efv-2026-07-30/ODDS_RECALIBRATION_SHIP_GATE.md")
    bundles = {s: load_side(s) for s in ("hit", "pit")}
    rows = build_frame(bundles)
    print(f"  frame: {len(rows)} resolved OOF rows "
          f"(hit {sum(1 for r in rows if r['side']=='hit')}, "
          f"pit {sum(1 for r in rows if r['side']=='pit')}), "
          f"track {sum(1 for r in rows if r['has_track'])}")

    cuts_rows = {c: prepare_cut(rows, c) for c in CUTS}
    report = {c: cut_report(sub) for c, sub in cuts_rows.items()}

    print("  permutation null ...", flush=True)
    perm = permutation_null(cuts_rows, b_perm)
    print("  test-only bootstrap (diagnostic) ...", flush=True)
    testonly = test_only_bootstrap(cuts_rows, b_boot)
    print(f"  paired refit bootstrap B={b_boot} ...", flush=True)
    boot = paired_bootstrap(bundles, b_boot)

    fits = production_fits(rows)

    # --- the pre-registered verdict, computed rather than narrated -----------
    verdict = {}
    for cut in GATE_CUTS:
        c1 = boot[cut]["d_inc_brier"]["ci95"][0] > 0 and boot[cut]["d_inc_logloss"]["ci95"][0] > 0
        c2 = boot[cut]["d_const_brier"]["ci95"][0] > 0 and boot[cut]["d_const_logloss"]["ci95"][0] > 0
        pn = perm[cut]
        d_ib = report[cut]["arms"]["INC"]["brier"] - report[cut]["arms"]["CAL"]["brier"]
        d_il = report[cut]["arms"]["INC"]["logloss"] - report[cut]["arms"]["CAL"]["logloss"]
        d_cb = report[cut]["arms"]["CONST"]["brier"] - report[cut]["arms"]["CAL"]["brier"]
        d_cl = report[cut]["arms"]["CONST"]["logloss"] - report[cut]["arms"]["CAL"]["logloss"]
        c4 = (d_ib > pn["d_inc_brier"]["band95"][1] and d_il > pn["d_inc_logloss"]["band95"][1]
              and d_cb > pn["d_const_brier"]["band95"][1]
              and d_cl > pn["d_const_logloss"]["band95"][1])
        verdict[cut] = {
            "beats_incumbent_ci_excludes_zero": bool(c1),
            "beats_constant_ci_excludes_zero": bool(c2),
            "outside_permutation_null_both_baselines": bool(c4),
            "observed": {"d_inc_brier": round(d_ib, 6), "d_inc_logloss": round(d_il, 6),
                         "d_const_brier": round(d_cb, 6), "d_const_logloss": round(d_cl, 6)},
            "pass": bool(c1 and c2 and c4),
        }
    verdict["SHIP"] = all(verdict[c]["pass"] for c in GATE_CUTS)

    out = {
        "line": "LANE-ODDS-SHIP 2026-07-30: re-fit + re-measure of efv_odds_calibration "
                "on the current tree, against BOTH the incumbent and a flat base rate.",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "lab": "tools/odds_recalibration_ship_lab.py",
        "pre_registration": "docs/efv-2026-07-30/ODDS_RECALIBRATION_SHIP_GATE.md",
        "gate_standard": "docs/EFV_GATE_STANDARD.md",
        "registry_row": "xfv_odds_recalibration_ship",
        "recalibrates": "p_bust ONLY; the four non-bust buckets rescale proportionally so "
                        "the 5-vector still sums to 1. No star map is fitted: the frame "
                        "carries 9 hitter stars and 2 pitcher stars.",
        "frame": {
            "pool": "xfv_{hitter,pitcher}_matrix.json minus (kind=bust AND bust_recent), "
                    "prepped on target_censored (efv_score.run's own pool + target)",
            "test_restriction": "censored is False AND target_resolved numeric",
            "folds": list(CAL_YEARS),
            "n_rows": len(rows),
            "n_hit": sum(1 for r in rows if r["side"] == "hit"),
            "n_pit": sum(1 for r in rows if r["side"] == "pit"),
            "n_track": sum(1 for r in rows if r["has_track"]),
            "applied_population": "rows with a milb block (the production guard "
                                  "`provisional=not src.get('milb')`), which on today's "
                                  "matrices is 906/907 hit and 920/920 pit the same rows "
                                  "as rates_missing == 0",
        },
        "arms": {
            "INC": "p_bucket_given_fv(realized_implied_fv(war, is_pit, age, pos))[bust] "
                   "- efv_score.py:1188-1196 verbatim",
            "CAL": "INC through a forward-chained per-side Platt map fit on out-of-fold "
                   "rows of decision years < fold, within the cut's own population",
            "CONST": "flat constant at the cut's own prior-fold base rate",
            "CONST_all": "flat constant at the fold's FULL resolved-training base rate "
                         "(the basis gate's arm C)",
        },
        "sign_convention": "d = metric(baseline) - metric(CAL); POSITIVE means the "
                           "recalibration is better.",
        "ship_criterion": "CAL beats BOTH the incumbent AND the within-cut flat base rate "
                          "on Brier AND logloss, paired refit bootstrap CI95 excluding "
                          "zero, on `pooled` AND `pooled_served`, and both observed deltas "
                          "outside their permutation null bands.",
        "verdict": verdict,
        "report": report,
        "production_fits": fits,
        "controls": {
            "paired_refit_bootstrap": boot,
            "permutation_null": perm,
            "test_only_bootstrap_diagnostic": testonly,
        },
        "caveats": [
            "Fold 2014 carries no prior out-of-fold rows, so CAL falls back to INC and "
            "CONST falls back to CONST_all there: a tie by construction that costs the "
            "candidate.",
            "Per-fold Platt maps make CAL a globally non-monotone transform of INC, so "
            "CAL's AUC is not guaranteed to equal INC's here. The SHIPPED map is one "
            "global monotone transform per side and preserves every ranking exactly; "
            "that is verified separately at the wiring seam.",
        ],
        "post_hoc_fitted_folds_only": FITTED_FOLDS_ONLY,
        "changes_served_output": False,
        "runtime_s": round(time.time() - t_start, 1),
    }
    (DATA / _ARTIFACT).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"  wrote data/{_ARTIFACT} ({out['runtime_s']}s)")
    print(f"  VERDICT: {'SHIP' if verdict['SHIP'] else 'NULL'}")
    return out


if __name__ == "__main__":
    main(quick="--quick" in sys.argv)
