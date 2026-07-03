# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""eFV JOINT side-symmetric grade recalibration (E-ISO4, FINAL calibration attempt).

EXPERIMENT (pre-registered gate: docs/audit-2026-07/AUDIT_FINDINGS.md, section E-ISO4):
X-ISO, E-ISO2 and E-ISO3 all fit each SIDE's grade recalibration map INDEPENDENTLY. The
two side maps move differently, so the POOLED cross-side ranking (the board interleaves
hitters and pitchers by grade) churns year-to-year -- the one failure mode shared by all
three prior attempts, even though the FV45+ calibration gain is real and large. E-ISO4
ties the two sides so cross-side ranking is preserved BY CONSTRUCTION:

  (a) SHARED grade map: fit ONE strictly-increasing monotone function g(grade) -> grade',
      applied IDENTICALLY to both sides, minimizing the POOLED calibration loss (weighted
      bucket log-likelihood under each row's own-side anchor table, evaluated at the SAME
      shared effective grade). Because g is a single shared monotone map, for any two
      players (either side) with grades a <= b, g(a) <= g(b): the pooled cross-side rank
      order equals the shipped-grade order EXACTLY, so cross-side Spearman delta is 0 by
      construction. Primary candidate. p_after = p_bucket_given_fv(g(grade), side).

  (b) SHARED grade map (drives the RANKING, identical g to (a)) + side-specific RESIDUAL
      bucket tables (per-side OOF per-bucket isotonic on the shared-map base distribution,
      renormalized) that adjust the DISPLAYED/surplus bucket probabilities but do NOT
      change the ranking grade order (ranking is g(grade), not the distribution). Tests
      whether (b) recovers the per-side per-bucket calibration a pure shared map might
      sacrifice.

The RANKING under E-ISO4 is the shared recalibrated grade g(grade) (the board ranks by
grade). Conditions 2 and 3 are therefore measured on g(grade); a single shared strictly-
increasing map makes both hold by construction (measured, never assumed, to confirm the
implementation preserves order with no numerical leak). The verbatim E-ISO3 expected-WAR
cross-side instrument is ALSO reported as a diagnostic (the surplus/expected-WAR ordering,
which the shared map does NOT guarantee to preserve cross-side) so the numbers stay
comparable to E-ISO3.

GATE (ALL must hold, per formulation; pre-registered BEFORE this run; marginal = FAIL):
  1. Pooled AND per-side AND per-bucket Brier/log-loss improve; NO bucket materially worse
     on EITHER side (MATERIAL_TOL relative, checked per side explicitly). [E-ISO3 failed
     here: pit BENCH +1.4% relative.]
  2. Within-(side, year) rank preservation EXACT (measured on the ranking grade g(grade)).
  3. Cross-side within-YEAR pooled Spearman delta >= -0.002 for EVERY eval year 2020-2023
     (on the ranking grade; ~0 by construction under the shared map).
  4. Per-tier reliability: every FV45+ tier improves; no tier worsens by > 0.005 absolute
     (FV-35 reported).

EXPERIMENT HARNESS ONLY -- nothing wires into the pipeline; ship wiring happens
orchestrator-side only on a clear gate pass. Artifact: data/xfv_grade_recal4_eval.json
(same reliability-curve schema as data/xfv_grade_recal3_eval.json so the PROSPX
reliability diagram could render it).

Run: python tools/efv_grade_recal4_lab.py        SEED=7, fully deterministic.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import os; os.chdir(ROOT)  # noqa: E702

import numpy as np

import value_framework as vf
import efv_isotonic_lab as base          # X-ISO harness: cohort splits + metrics verbatim
import efv_grade_recal_lab as e2         # E-ISO2 lab: strict-blend apply_map + table_matrix
import efv_grade_recal3_lab as e3        # E-ISO3 lab: verbatim expected-WAR cross-side instrument
from prospect_path import _spearman

SEED = 7                                 # matches X-ISO/E-ISO2/E-ISO3; pipeline deterministic
np.random.seed(SEED)

BUCKETS = base.BUCKETS
EVAL_YEARS = base.EVAL_YEARS             # 2020-2023 (canonical eval cohorts)
CHAIN_YEARS = base.CHAIN_YEARS           # 2016-2023 OOF chain
MIN_CAL_ROWS = base.MIN_CAL_ROWS         # 150; pooled floor for the shared map
MIN_RESID_ROWS = base.MIN_CAL_ROWS       # 150; per-side floor for formulation (b) residual
MATERIAL_TOL = base.MATERIAL_TOL         # 0.01 relative, as X-ISO/E-ISO2/E-ISO3
CROSS_SIDE_TOL = e3.CROSS_SIDE_TOL       # 0.002 (condition 3 per-year tolerance)
TIER_WORSE_ABS = e3.TIER_WORSE_ABS       # 0.005 (condition 4 absolute worse-tolerance)
FV45_PLUS = e3.FV45_PLUS                 # 45 (condition 4 must-improve tier floor)

# shared grade-map hyperparameters (same grid/bin/blend family as E-ISO2)
GRID_LO, GRID_HI, GRID_STEP = e2.GRID_LO, e2.GRID_HI, e2.GRID_STEP
BIN_TARGET, BIN_MIN, STRICT_EPS = e2.BIN_TARGET, e2.BIN_MIN, e2.STRICT_EPS
P_CLIP = e2.P_CLIP

OUT_PATH = ROOT / "data" / "xfv_grade_recal4_eval.json"
SIDES = ("hit", "pit")


def _mids():
    return {"hit": np.asarray(vf._calibrated_midpoints("hitter")),
            "pit": np.asarray(vf._calibrated_midpoints("pitcher"))}


# ---------------------------------------------------------------------------
# SHARED (side-symmetric) grade map: ONE monotone g(grade) for both sides
# ---------------------------------------------------------------------------

def _side_tables():
    """Anchor-table log-probabilities on the SHARED dense grade grid, per side.
    Both sides use the identical grid so grid indices align in the pooled fit."""
    grid_h, T_h = e2.table_matrix("hit")
    grid_p, T_p = e2.table_matrix("pit")
    assert np.array_equal(grid_h, grid_p)          # shared grid: indices must align
    logT = {"hit": np.log(np.clip(T_h, P_CLIP, 1.0)),
            "pit": np.log(np.clip(T_p, P_CLIP, 1.0))}
    return grid_h, {"hit": T_h, "pit": T_p}, logT


def fit_shared_grade_map(cal_rows: list[dict], grid: np.ndarray, logT: dict) -> dict:
    """Pooled binned effective-grade inversion + weighted PAVA -> ONE shared map.

    Rows from BOTH sides are pooled and sorted by grade into contiguous bins. For each
    bin the effective grade is the grid grade maximizing the POOLED KM-weighted realized-
    bucket log-likelihood, where every row is scored under its OWN side's anchor table at
    the SAME candidate grade -- so the single shared grade the bin resolves to is the one
    that best calibrates hitters and pitchers jointly. Weighted PAVA of effective grade vs
    bin-mean grade gives a nondecreasing map; apply_map's identity blend makes it strict."""
    from sklearn.isotonic import IsotonicRegression

    rows = sorted(cal_rows, key=lambda r: (r["grade"], r["side"], r["player_key"]))
    n = len(rows)
    size = max(BIN_MIN, n // BIN_TARGET)

    centers, effs, wts, bin_ns, bin_hit, bin_pit = [], [], [], [], [], []
    i = 0
    while i < n:
        j = min(n, i + size)
        if n - j < BIN_MIN:                          # fold a short tail into the last bin
            j = n
        grp = rows[i:j]
        ll = np.zeros(len(grid))                     # pooled weighted log-lik over the grid
        wsum = gsum = 0.0
        nh = npi = 0
        for r in grp:
            w = max(float(r["weight"]), 1e-6)
            ll += w * logT[r["side"]][:, r["y"]]     # score under this row's own-side table
            wsum += w
            gsum += w * float(r["grade"])
            if r["side"] == "hit":
                nh += 1
            else:
                npi += 1
        centers.append(gsum / wsum)
        effs.append(float(grid[int(np.argmax(ll))]))
        wts.append(wsum)
        bin_ns.append(len(grp))
        bin_hit.append(nh)
        bin_pit.append(npi)
        i = j

    iso = IsotonicRegression(out_of_bounds="clip")   # weighted PAVA, nondecreasing
    iso.fit(np.array(centers), np.array(effs), sample_weight=np.array(wts))
    return {
        "iso": iso,
        "bin_centers": [round(c, 3) for c in centers],
        "eff_raw": [round(e, 2) for e in effs],
        "eff_iso": [round(float(iso.predict([c])[0]), 3) for c in centers],
        "bin_n": bin_ns, "bin_hit": bin_hit, "bin_pit": bin_pit,
    }


# apply_map (strict identity blend) is IDENTICAL to E-ISO2; reuse verbatim.
apply_map = e2.apply_map


# ---------------------------------------------------------------------------
# formulation (a): shared map only
# ---------------------------------------------------------------------------

def build_shared(rows_by_side: dict) -> tuple[list[dict], dict]:
    """Attach grade_recal = g(grade) (shared map) and p_after = anchor table at g(grade)
    (own side) to every EVAL-year row; the map for eval year Y is fit ONLY on POOLED OOF
    rows (both sides) with decision_year < Y."""
    grid, T, logT = _side_tables()
    eval_rows, map_diag = [], {}
    for yr in EVAL_YEARS:
        cal = [r for s in SIDES for r in rows_by_side[s] if r["decision_year"] < yr]
        te = [r for s in SIDES for r in rows_by_side[s] if r["decision_year"] == yr]
        if not te or len(cal) < MIN_CAL_ROWS:
            continue                                 # never calibrate on a thin prior sample
        gmap = fit_shared_grade_map(cal, grid, logT)
        for r in te:
            r = dict(r)
            g2 = apply_map(gmap, r["grade"])
            r["grade_recal"] = g2
            r["p_after"] = np.asarray(vf.p_bucket_given_fv(g2, r["side"] == "pit"), dtype=float)
            r["n_cal"] = len(cal)
            eval_rows.append(r)
        map_diag[str(yr)] = {
            "n_cal": len(cal),
            "n_cal_hit": sum(1 for r in cal if r["side"] == "hit"),
            "n_cal_pit": sum(1 for r in cal if r["side"] == "pit"),
            "bin_centers": gmap["bin_centers"], "bin_n": gmap["bin_n"],
            "bin_hit": gmap["bin_hit"], "bin_pit": gmap["bin_pit"],
            "eff_raw": gmap["eff_raw"], "eff_iso": gmap["eff_iso"],
            "sample_map": {str(g): round(apply_map(gmap, float(g)), 2)
                           for g in (25, 30, 35, 40, 45, 50, 55, 60, 65)},
        }
    return eval_rows, map_diag


# ---------------------------------------------------------------------------
# formulation (b): shared map (ranking) + side-specific residual bucket tables
# ---------------------------------------------------------------------------

def _fit_resid_isotonics(rows: list[dict], base_key: str):
    """Per-bucket sklearn isotonic on the shared-map base probability vs realized 1{y==b},
    KM-weighted. A DISPLAY/surplus residual: it never touches the ranking grade."""
    from sklearn.isotonic import IsotonicRegression
    isos = []
    for b in range(len(BUCKETS)):
        x = np.array([r[base_key][b] for r in rows])
        y = np.array([1.0 if r["y"] == b else 0.0 for r in rows])
        w = np.array([r["weight"] for r in rows])
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        iso.fit(x, y, sample_weight=w)
        isos.append(iso)
    return isos


def build_shared_plus_residual(rows_by_side: dict) -> tuple[list[dict], dict]:
    """Same shared map g as (a) drives grade_recal; the DISPLAYED distribution is the
    shared-map base p_bucket_given_fv(g(grade), side) further corrected by a per-side OOF
    per-bucket isotonic residual (fit on decision_year < Y rows' shared-map base), then
    renormalized. Ranking order is unchanged (still g(grade))."""
    grid, T, logT = _side_tables()
    eval_rows, resid_diag = [], {}
    for yr in EVAL_YEARS:
        cal = [r for s in SIDES for r in rows_by_side[s] if r["decision_year"] < yr]
        te = [r for s in SIDES for r in rows_by_side[s] if r["decision_year"] == yr]
        if not te or len(cal) < MIN_CAL_ROWS:
            continue
        gmap = fit_shared_grade_map(cal, grid, logT)     # identical shared map to (a)
        # shared-map base distribution for the calibration rows, split by side
        cal_by_side = {s: [] for s in SIDES}
        for r in cal:
            g2 = apply_map(gmap, r["grade"])
            rr = dict(r)
            rr["p_shared"] = np.asarray(vf.p_bucket_given_fv(g2, r["side"] == "pit"), dtype=float)
            cal_by_side[r["side"]].append(rr)
        isos_by_side, resid_n = {}, {}
        for s in SIDES:
            resid_n[s] = len(cal_by_side[s])
            if len(cal_by_side[s]) >= MIN_RESID_ROWS:
                isos_by_side[s] = _fit_resid_isotonics(cal_by_side[s], "p_shared")
        for r in te:
            r = dict(r)
            g2 = apply_map(gmap, r["grade"])
            r["grade_recal"] = g2
            p_shared = np.asarray(vf.p_bucket_given_fv(g2, r["side"] == "pit"), dtype=float)
            isos = isos_by_side.get(r["side"])
            r["p_after"] = base.apply_isotonics(isos, p_shared) if isos else p_shared.copy()
            r["n_cal"] = len(cal)
            eval_rows.append(r)
        resid_diag[str(yr)] = {"resid_train_rows": resid_n,
                               "residual_applied": {s: s in isos_by_side for s in SIDES}}
    return eval_rows, resid_diag


# ---------------------------------------------------------------------------
# strict-monotonicity of the shared map (verify, do not assume)
# ---------------------------------------------------------------------------

def strictness_check_shared(rows_by_side: dict) -> dict:
    grid, T, logT = _side_tables()
    out = {}
    for yr in EVAL_YEARS:
        cal = [r for s in SIDES for r in rows_by_side[s] if r["decision_year"] < yr]
        if len(cal) < MIN_CAL_ROWS:
            continue
        gmap = fit_shared_grade_map(cal, grid, logT)
        gs = np.arange(GRID_LO, GRID_HI + 1e-9, 0.25)
        fs = np.array([apply_map(gmap, float(g)) for g in gs])
        d = np.diff(fs)
        out[str(yr)] = {"strictly_increasing": bool((d > 0).all()),
                        "min_step": round(float(d.min()), 6)}
    return out


# ---------------------------------------------------------------------------
# ranking-grade instruments (the E-ISO4 ranking is the shared grade g(grade))
# ---------------------------------------------------------------------------

def rank_preservation_grade(eval_rows: list[dict]) -> dict:
    """Condition 2: within-(side, year) Spearman of the ranking grade. Baseline = shipped
    grade; candidate = g(grade). A shared strictly-increasing map preserves ranks exactly
    (Spearman is rank-invariant under a monotone transform), so these are EQUAL by
    construction; measured per cell to confirm."""
    out = {}
    for s in SIDES:
        out[s] = {}
        for yr in EVAL_YEARS:
            sub = [r for r in eval_rows if r["side"] == s and r["decision_year"] == yr]
            if not sub:
                continue
            t = [r["target"] for r in sub]
            rs = _spearman([r["grade"] for r in sub], t)
            ra = _spearman([r["grade_recal"] for r in sub], t)
            out[s][str(yr)] = {"n": len(sub),
                               "shipped_grade_rho": round(rs, 4),
                               "recal_grade_rho": round(ra, 4),
                               "preserved": bool(abs(ra - rs) < 1e-9)}
    return out


def cross_side_grade_by_year(eval_rows: list[dict]) -> dict:
    """Condition 3: cross-side, within-year pooled Spearman of the RANKING grade (both
    sides, one year only). Baseline = shipped grade; candidate = g(grade). Under the
    shared strictly-increasing map the pooled rank order is identical to the shipped-grade
    order, so delta is 0 by construction; measured per year to confirm no numerical leak."""
    out = {}
    for yr in EVAL_YEARS:
        sub = [r for r in eval_rows if r["decision_year"] == yr]
        if not sub:
            continue
        t = [r["target"] for r in sub]
        rs = _spearman([r["grade"] for r in sub], t)
        ra = _spearman([r["grade_recal"] for r in sub], t)
        out[str(yr)] = {
            "n": len(sub),
            "n_hit": sum(1 for r in sub if r["side"] == "hit"),
            "n_pit": sum(1 for r in sub if r["side"] == "pit"),
            "shipped_grade_rho": round(rs, 4),
            "recal_grade_rho": round(ra, 4),
            "delta_vs_shipped": round(ra - rs, 4),
            "pass": bool((ra - rs) >= -CROSS_SIDE_TOL),
        }
    return out


# ---------------------------------------------------------------------------
# the E-ISO4 gate (cond1/cond4 logic IDENTICAL to E-ISO3; cond2/cond3 on ranking grade)
# ---------------------------------------------------------------------------

def gate_e_iso4(res: dict, cells_grade: dict, by_year_grade: dict) -> dict:
    pooled, per_side, tiers = res["pooled"], res["per_side"], res["per_tier_reliability"]

    # --- condition 1: pooled AND per-side AND per-bucket, materiality per side ---
    def _improves(blk):
        return bool(blk["brier"]["after"] < blk["brier"]["before"]
                    and blk["log_loss"]["after"] < blk["log_loss"]["before"])

    pooled_improves = _improves(pooled)
    side_improves = {s: _improves(per_side[s]) for s in SIDES}
    pooled_buckets_improve = all(v["brier_improved"] and v["logloss_improved"]
                                 for v in pooled["per_bucket"].values())
    pooled_no_material = not any(v["materially_worse"] for v in pooled["per_bucket"].values())
    side_material = {s: [name for name, v in per_side[s]["per_bucket"].items()
                         if v["materially_worse"]] for s in SIDES}
    side_buckets_improve = {s: all(v["brier_improved"] and v["logloss_improved"]
                                   for v in per_side[s]["per_bucket"].values())
                            for s in SIDES}
    no_material_either_side = not any(side_material[s] for s in SIDES)
    cond1 = {
        "pass": bool(pooled_improves and all(side_improves.values())
                     and pooled_buckets_improve and pooled_no_material
                     and no_material_either_side),
        "definition": "pooled Brier AND log-loss improve; each side's pooled Brier AND "
                      "log-loss improve; every pooled bucket improves on both metrics; "
                      "no bucket materially worse (rel > 0.01 on either metric) pooled OR "
                      "on either side",
        "pooled_improves": pooled_improves,
        "per_side_improves": side_improves,
        "pooled_all_buckets_improve": pooled_buckets_improve,
        "pooled_no_bucket_materially_worse": pooled_no_material,
        "per_side_all_buckets_improve_diagnostic": side_buckets_improve,
        "per_side_buckets_materially_worse": side_material,
        "material_tolerance_rel": MATERIAL_TOL,
    }

    # --- condition 2: within-(side, year) ranking-grade preservation EXACT -------
    flat = [(s, yr, c) for s, yrs in cells_grade.items() for yr, c in yrs.items()]
    cond2 = {
        "pass": bool(flat) and all(c["preserved"] for _, _, c in flat),
        "definition": "within-(side, eval-year) Spearman of the ranking grade g(grade) "
                      "equals the shipped grade Spearman exactly (abs diff < 1e-9) in "
                      "every cell",
        "n_cells": len(flat),
        "n_preserved": sum(1 for _, _, c in flat if c["preserved"]),
        "cells_not_preserved": [f"{s}/{yr}" for s, yr, c in flat if not c["preserved"]],
    }

    # --- condition 3: cross-side within-YEAR ranking-grade Spearman, every year --
    years_failed = [yr for yr, v in by_year_grade.items() if not v["pass"]]
    cond3 = {
        "pass": bool(by_year_grade) and len(by_year_grade) == len(EVAL_YEARS)
                and not years_failed,
        "definition": "for EVERY evaluation year 2020-2023, the cross-side pooled Spearman "
                      "of the ranking grade g(grade) (both sides, that year only) has delta "
                      ">= -0.002 vs the shipped grade (0 by construction under the shared map)",
        "tolerance": -CROSS_SIDE_TOL,
        "per_year_delta": {yr: v["delta_vs_shipped"] for yr, v in by_year_grade.items()},
        "per_year_pass": {yr: v["pass"] for yr, v in by_year_grade.items()},
        "years_failed": years_failed,
    }

    # --- condition 4: FV45+ tiers improve; no tier worse by > 0.005 absolute -----
    fv45 = {tk: v for tk, v in tiers.items() if int(tk) >= FV45_PLUS}
    fv45_not_improved = [tk for tk, v in fv45.items() if not v["improved"]]
    abs_worse = {tk: round(v["gap_after"] - v["gap_before"], 5) for tk, v in tiers.items()}
    tiers_over_tol = [tk for tk, d in abs_worse.items() if d > TIER_WORSE_ABS]
    cond4 = {
        "pass": bool(fv45) and not fv45_not_improved and not tiers_over_tol,
        "definition": "every FV tier >= 45 improves (gap_after < gap_before); no tier "
                      "(any grade) worsens by more than 0.005 absolute",
        "fv45_plus_tiers": sorted(fv45),
        "fv45_plus_not_improved": fv45_not_improved,
        "tier_gap_delta_abs": abs_worse,
        "tiers_worse_beyond_0p005": tiers_over_tol,
        "worse_tolerance_abs": TIER_WORSE_ABS,
    }

    verdict = "PASS" if all(c["pass"] for c in (cond1, cond2, cond3, cond4)) else "FAIL"
    return {
        "condition_1_brier_logloss": cond1,
        "condition_2_rank_preservation": cond2,
        "condition_3_cross_side_by_year": cond3,
        "condition_4_tier_reliability": cond4,
        "verdict": verdict,
    }


def evaluate_formulation(eval_rows: list[dict], label: str) -> dict:
    """Metrics (base.evaluate: pooled/per-side/per-bucket/tiers/curves), ranking-grade
    condition-2/3 instruments, verbatim E-ISO3 expected-WAR cross-side diagnostic, gate."""
    res = base.evaluate(eval_rows)
    res.pop("gate", None)                            # the X-ISO gate does not apply here
    cells_grade = rank_preservation_grade(eval_rows)
    by_year_grade = cross_side_grade_by_year(eval_rows)
    by_year_ew = e3.cross_side_by_year(eval_rows)    # verbatim E-ISO3 expected-WAR instrument
    gate = gate_e_iso4(res, cells_grade, by_year_grade)
    return {
        "label": label,
        "results": res,
        "rank_preservation_grade": cells_grade,
        "cross_side_grade_by_year": by_year_grade,
        "cross_side_expected_war_by_year_diagnostic": by_year_ew,
        "gate": gate,
    }


# ---------------------------------------------------------------------------
# artifact
# ---------------------------------------------------------------------------

def run(persist: bool = True) -> dict:
    rows_by_side = {s: base.oof_rows(s) for s in SIDES}            # identical splits to X-ISO
    ev_a, map_diag = build_shared(rows_by_side)                    # formulation (a)
    ev_b, resid_diag = build_shared_plus_residual(rows_by_side)   # formulation (b)
    strict = strictness_check_shared(rows_by_side)

    form_a = evaluate_formulation(ev_a, "a_shared_map")
    form_b = evaluate_formulation(ev_b, "b_shared_map_plus_residual")

    splits = {}
    for s in SIDES:
        cnt = defaultdict(int)
        for r in rows_by_side[s]:
            cnt[r["decision_year"]] += 1
        splits[s] = {
            "chain_oof_rows_by_year": {str(y): cnt[y] for y in sorted(cnt)},
            "eval_rows": sum(1 for r in ev_a if r["side"] == s),
            "calibrator_train_rows_by_eval_year": {
                str(y): len([r for r in rows_by_side[s] if r["decision_year"] < y])
                for y in EVAL_YEARS},
        }
    splits["pooled_calibrator_train_rows_by_eval_year"] = {
        str(y): sum(len([r for r in rows_by_side[s] if r["decision_year"] < y]) for s in SIDES)
        for y in EVAL_YEARS}

    passes = {"a": form_a["gate"]["verdict"] == "PASS",
              "b": form_b["gate"]["verdict"] == "PASS"}
    overall = "PASS" if (passes["a"] or passes["b"]) else "FAIL"
    ships = [k for k in ("a", "b") if passes[k]]
    fitted_method = (vf._fitted().get("method") or {})

    out = {
        "generated_at": date.today().isoformat(),
        "experiment": "E-ISO4: joint side-symmetric (SHARED) grade-map recalibration of the "
                      "eFV 5-bucket distribution -- FINAL calibration attempt against this "
                      "data vintage (owner: one more attempt)",
        "spec": "gate pre-registered in docs/audit-2026-07/AUDIT_FINDINGS.md section E-ISO4; "
                "predecessors: E-ISO3 data/xfv_grade_recal3_eval.json, E-ISO2 "
                "data/xfv_grade_recal_eval.json, X-ISO data/xfv_isotonic_eval.json",
        "method": {
            "base_distribution": "shipped seam, forward-chained OOF (reused verbatim from "
                                 "tools/efv_isotonic_lab.py oof_rows): lean ridge + in-fold "
                                 "linear scale calibration -> xfv_war -> realized_implied_fv "
                                 "-> p_bucket_given_fv (uncalibrated 'before')",
            "shared_grade_map": "ONE strictly-increasing monotone map g(grade) fit on the "
                                "POOLED (both sides) OOF rows: pooled binned effective-grade "
                                "inversion (per grade bin, argmax over the dense grade grid of "
                                "the KM-weighted realized-bucket log-likelihood, each row "
                                "scored under its OWN side's anchor table at the SAME candidate "
                                "grade) + weighted PAVA + strict identity blend "
                                "f(g)=(1-eps)*iso(g)+eps*g, eps=0.01; applied IDENTICALLY to "
                                "both sides so cross-side rank order == shipped-grade order",
            "formulation_a": "p_after = p_bucket_given_fv(g(grade), side); the anchor table is "
                             "untouched, only the shared grade it is evaluated at moves",
            "formulation_b": "ranking grade = g(grade) (identical to a); DISPLAYED distribution "
                             "= shared-map base further corrected by a per-side OOF per-bucket "
                             "isotonic residual (fit on decision_year<Y rows' shared-map base), "
                             "renormalized onto the simplex; residual never affects ranking order",
            "ranking": "the board ranks by the shared recalibrated grade g(grade); conditions 2 "
                       "and 3 are measured on g(grade) (0 by construction under a shared strictly-"
                       "increasing map); the verbatim E-ISO3 expected-WAR cross-side instrument "
                       "is reported as a diagnostic only",
            "oof_protocol": "shared map (and formulation-b residual) for eval cohort Y fit ONLY "
                            "on rows with decision_year < Y (pooled across sides for the map, "
                            "per side for the residual); chain years 2016-2023; no row ever "
                            "calibrates itself; no same-player leakage",
            "realized_bucket": "6yr-average annual WAR (target_censored/6) binned by the engine "
                               "bands: <0.5 bust / 0.5-1.5 bench / 1.5-2.5 regular / 2.5-4.0 "
                               "good / 4.0+ star",
            "pool": "full labeled matrix per side (debuted + busts, bust_recent excluded), "
                    "matching efv_model.oos_grades",
            "rank_metric": "ranking grade g(grade); shipped baseline = OOF eFV grade",
            "anchor_table_method": fitted_method,
            "eval_years": list(EVAL_YEARS),
            "chain_years": [CHAIN_YEARS[0], CHAIN_YEARS[-1]],
            "min_calibrator_rows": MIN_CAL_ROWS, "min_residual_rows": MIN_RESID_ROWS,
            "grid": [GRID_LO, GRID_HI, GRID_STEP],
            "bin_target": BIN_TARGET, "bin_min": BIN_MIN, "strict_eps": STRICT_EPS,
        },
        "seed": SEED,
        "cohort_splits": splits,
        "shared_grade_map": map_diag,
        "residual_diag": resid_diag,
        "strict_monotonicity_check": strict,
        # primary (formulation a) surfaced at the E-ISO3 top-level keys so the PROSPX
        # reliability diagram (results.reliability_curves_pooled) renders unchanged:
        "rank_preservation_by_cell": form_a["rank_preservation_grade"],
        "cross_side_spearman_by_year": form_a["cross_side_grade_by_year"],
        "results": form_a["results"],
        "gate": form_a["gate"],
        "formulations": {
            "a_shared_map": {k: form_a[k] for k in
                             ("gate", "results", "rank_preservation_grade",
                              "cross_side_grade_by_year",
                              "cross_side_expected_war_by_year_diagnostic")},
            "b_shared_map_plus_residual": {k: form_b[k] for k in
                             ("gate", "results", "rank_preservation_grade",
                              "cross_side_grade_by_year",
                              "cross_side_expected_war_by_year_diagnostic")},
        },
        "overall_verdict": overall,
        "formulation_verdicts": {"a_shared_map": form_a["gate"]["verdict"],
                                 "b_shared_map_plus_residual": form_b["gate"]["verdict"]},
        "ships": ships,
    }

    if overall != "PASS":
        def _ledger_for(form):
            g, r = form["gate"], form["results"]
            failed = [k for k in ("condition_1_brier_logloss", "condition_2_rank_preservation",
                                  "condition_3_cross_side_by_year", "condition_4_tier_reliability")
                      if not g[k]["pass"]]
            return {
                "failed_conditions": failed,
                "pooled_brier_before_after": [r["pooled"]["brier"]["before"],
                                              r["pooled"]["brier"]["after"]],
                "pooled_logloss_before_after": [r["pooled"]["log_loss"]["before"],
                                                r["pooled"]["log_loss"]["after"]],
                "per_side_buckets_materially_worse":
                    g["condition_1_brier_logloss"]["per_side_buckets_materially_worse"],
                "pit_bench_bucket": r["per_side"]["pit"]["per_bucket"]["bench"],
                "hit_bench_bucket": r["per_side"]["hit"]["per_bucket"]["bench"],
                "cross_side_grade_per_year_delta":
                    g["condition_3_cross_side_by_year"]["per_year_delta"],
                "cross_side_expected_war_per_year_delta":
                    {yr: v["delta_vs_shipped"]
                     for yr, v in form["cross_side_expected_war_by_year_diagnostic"].items()},
                "rank_preservation": f"{g['condition_2_rank_preservation']['n_preserved']}/"
                                     f"{g['condition_2_rank_preservation']['n_cells']}",
                "fv45_plus_not_improved": g["condition_4_tier_reliability"]["fv45_plus_not_improved"],
                "tiers_worse_beyond_0p005":
                    g["condition_4_tier_reliability"]["tiers_worse_beyond_0p005"],
                "tier_gap_delta_abs": g["condition_4_tier_reliability"]["tier_gap_delta_abs"],
            }

        out["loss_ledger"] = {
            "date": date.today().isoformat(),
            "experiment": "E-ISO4: joint side-symmetric SHARED grade-map recalibration of the "
                          "eFV 5-bucket distribution (both formulations)",
            "hypothesis": "tying the two sides to ONE shared monotone grade map removes the "
                          "cross-side rank churn that killed X-ISO/E-ISO2/E-ISO3, so the real, "
                          "large FV45+ calibration gain finally clears every gate condition",
            "what_was_tried": "(a) one shared strictly-increasing grade map minimizing pooled "
                              "calibration loss, applied identically to both sides; (b) the same "
                              "shared map for ranking + per-side OOF per-bucket isotonic residual "
                              "bucket tables for the displayed distribution",
            "result_formulation_a": _ledger_for(form_a),
            "result_formulation_b": _ledger_for(form_b),
            "disposition": "NO SHIP. Per the pre-registration this is the FINAL calibration "
                           "attempt against this data vintage across all formulations. Harness "
                           "(tools/efv_grade_recal4_lab.py) + this artifact are the committed "
                           "loss; revisit only with 2024+ cohorts.",
        }

    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"wrote {OUT_PATH}")
    return out


def _print_formulation(tag: str, form: dict):
    g, r = form["gate"], form["results"]
    p = r["pooled"]
    print(f"\n=== formulation {tag}: {g['verdict']} ===")
    print(f"  n eval rows: {p['n']}")
    c1 = g["condition_1_brier_logloss"]
    print(f"  cond1 (brier/logloss pooled+per-side+per-bucket): {c1['pass']} | "
          f"pooled brier {p['brier']['before']} -> {p['brier']['after']} | "
          f"logloss {p['log_loss']['before']} -> {p['log_loss']['after']}")
    print(f"        per-side materially worse: {c1['per_side_buckets_materially_worse']}")
    c2 = g["condition_2_rank_preservation"]
    print(f"  cond2 (within-cell grade rank preservation exact): {c2['pass']} | "
          f"{c2['n_preserved']}/{c2['n_cells']} cells")
    c3 = g["condition_3_cross_side_by_year"]
    print(f"  cond3 (cross-side within-year GRADE spearman): {c3['pass']} | "
          f"per-year delta {c3['per_year_delta']}")
    ew = form["cross_side_expected_war_by_year_diagnostic"]
    print(f"        [diagnostic] expected-WAR cross-side per-year delta: "
          f"{ {yr: v['delta_vs_shipped'] for yr, v in ew.items()} }")
    c4 = g["condition_4_tier_reliability"]
    print(f"  cond4 (tier reliability FV45+ improve, worse<=0.005): {c4['pass']} | "
          f"delta by tier {c4['tier_gap_delta_abs']}")
    for side in SIDES:
        blk = r["per_side"][side]
        print(f"  {side}: brier {blk['brier']['before']} -> {blk['brier']['after']} | "
              f"logloss {blk['log_loss']['before']} -> {blk['log_loss']['after']}")
        for name, v in blk["per_bucket"].items():
            print(f"    {name:8s} brier {v['brier_before']} -> {v['brier_after']} | "
                  f"logloss {v['logloss_before']} -> {v['logloss_after']}"
                  f"{'  MATERIALLY WORSE' if v['materially_worse'] else ''}")


if __name__ == "__main__":
    rep = run(persist="--dry" not in sys.argv)
    print(f"\nE-ISO4 overall verdict: {rep['overall_verdict']}  ships={rep['ships']}")
    _print_formulation("a", rep["formulations"]["a_shared_map"])
    _print_formulation("b", rep["formulations"]["b_shared_map_plus_residual"])
    st = rep["strict_monotonicity_check"]
    print("\nstrict-monotonicity (shared map): " +
          ", ".join(f"{yr}:{v['strictly_increasing']}(min_step {v['min_step']})"
                    for yr, v in st.items()))
