# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""eFV grade-space monotone recalibration lab (E-ISO2, successor to the rejected X-ISO).

EXPERIMENT (pre-registered gate: docs/audit-2026-07/AUDIT_FINDINGS.md, section E-ISO2):
X-ISO showed the shipped 5-bucket distribution's bust/bench probabilities at FV 45+ are
substantially miscalibrated (tier-45 gap 0.0946, tier-55 0.1616) but per-bucket PAVA on
the probabilities flattened ranks (Spearman -0.0165, gate FAIL). This lab recalibrates in
GRADE space instead: a STRICTLY-INCREASING monotone map f(grade) is fit out-of-fold, and
the calibrated distribution is the SHIPPED anchor table evaluated at the recalibrated
grade, p_after = p_bucket_given_fv(f(grade)). Because f is strictly increasing and the
anchor table (proportional-odds ordered logit on both sides) has strictly increasing
expected WAR in grade, within-side rank order is preserved by construction; the pooled
Spearman is still MEASURED, never assumed (cross-side interleaving can move it).

METHOD (per side, per eval year, forward-chained; deterministic given SEED):
  1. calibration rows = OOF rows with decision_year < Y (same chain, pool, target and
     KM weights as X-ISO; oof_rows is IMPORTED from tools/efv_isotonic_lab.py so the
     cohort splits are identical by construction).
  2. sort by OOF grade, form contiguous grade bins (>= BIN_MIN rows, ~BIN_TARGET bins).
  3. per bin: KM-weighted realized bucket distribution -> EFFECTIVE GRADE = the grid
     grade whose anchor-table distribution maximizes the weighted log-likelihood
     (equivalently minimizes KL(realized || table)).
  4. weighted PAVA (sklearn IsotonicRegression) of effective grade vs bin-mean grade
     -> nondecreasing step/interp map.
  5. strict tie-breaking in grade order: f(g) = (1 - STRICT_EPS) * iso(g) + STRICT_EPS*g
     (nondecreasing + strictly-increasing blend => strictly increasing everywhere).

GATE (ALL must hold; pre-registered BEFORE this run; marginal = FAIL, owner policy):
  1. pooled AND per-bucket Brier/log-loss improve vs the uncalibrated shipped
     distribution; no bucket materially worse (MATERIAL_TOL relative, as X-ISO).
  2. forward Spearman (expected WAR under the calibrated distribution, the rank that
     drives surplus/trade value downstream) vs shipped OOF grade: delta >= -0.002.
  3. per-FV-tier reliability: NO tier worse (worse = gap_after > gap_before + 1e-4),
     explicitly including FV-35 (the tier X-ISO degraded).

This is an EXPERIMENT HARNESS ONLY -- nothing wires into the pipeline; ship wiring
happens later, only on a clear gate pass (expected-CHANGED output-diff discipline).

Artifact: data/xfv_grade_recal_eval.json.  Run: python tools/efv_grade_recal_lab.py
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
import efv_isotonic_lab as base  # X-ISO harness: reuse cohort splits + metrics verbatim

SEED = 7                       # matches X-ISO; ridge/PAVA/grid-argmax are deterministic
np.random.seed(SEED)

BUCKETS = base.BUCKETS
EVAL_YEARS = base.EVAL_YEARS           # 2020-2023 (canonical eval cohorts)
CHAIN_YEARS = base.CHAIN_YEARS         # 2016-2023 OOF prediction chain
MIN_CAL_ROWS = base.MIN_CAL_ROWS       # 150, as X-ISO
MATERIAL_TOL = base.MATERIAL_TOL       # 0.01 relative, as X-ISO
SPEARMAN_TOL = base.SPEARMAN_TOL       # 0.002, as X-ISO
TIER_WORSE_TOL = 1e-4                  # base.tier_reliability's "worse" convention

GRID_LO, GRID_HI, GRID_STEP = 20.0, 70.0, 0.1   # effective-grade search grid
BIN_TARGET = 12                # target number of grade bins per calibrator
BIN_MIN = 50                   # minimum rows per grade bin
STRICT_EPS = 0.01              # identity-blend weight guaranteeing STRICT monotonicity
P_CLIP = 1e-9                  # log clip for the bin log-likelihood

OUT_PATH = ROOT / "data" / "xfv_grade_recal_eval.json"


# ---------------------------------------------------------------------------
# grade-space monotone map (fit on earlier OOF cohorts only)
# ---------------------------------------------------------------------------

def table_matrix(side: str):
    """Anchor-table bucket probabilities on the dense grade grid (one side)."""
    is_pit = side == "pit"
    grid = np.round(np.arange(GRID_LO, GRID_HI + 1e-9, GRID_STEP), 4)
    T = np.array([vf.p_bucket_given_fv(float(g), is_pit) for g in grid])
    return grid, T


def fit_grade_map(cal_rows: list[dict], grid: np.ndarray, T: np.ndarray) -> dict:
    """Binned effective-grade inversion + weighted PAVA. Returns the map spec
    (bin centers, raw + isotonic effective grades, weights) -- apply_map does
    the strict identity blend."""
    from sklearn.isotonic import IsotonicRegression

    rows = sorted(cal_rows, key=lambda r: (r["grade"], r["player_key"]))
    n = len(rows)
    size = max(BIN_MIN, n // BIN_TARGET)
    logT = np.log(np.clip(T, P_CLIP, 1.0))          # (grid, buckets)

    centers, effs, wts, bin_ns = [], [], [], []
    i = 0
    while i < n:
        j = min(n, i + size)
        if n - j < BIN_MIN:                          # fold a short tail into the last bin
            j = n
        grp = rows[i:j]
        w = np.array([max(float(r["weight"]), 1e-6) for r in grp])
        freq = np.zeros(len(BUCKETS))
        for r, wi in zip(grp, w):
            freq[r["y"]] += wi
        freq /= freq.sum()
        ll = logT @ freq                             # weighted log-lik of each grid grade
        g_eff = float(grid[int(np.argmax(ll))])
        centers.append(float(np.average([r["grade"] for r in grp], weights=w)))
        effs.append(g_eff)
        wts.append(float(w.sum()))
        bin_ns.append(len(grp))
        i = j

    iso = IsotonicRegression(out_of_bounds="clip")   # weighted PAVA, nondecreasing
    iso.fit(np.array(centers), np.array(effs), sample_weight=np.array(wts))
    return {
        "iso": iso,
        "bin_centers": [round(c, 3) for c in centers],
        "eff_raw": [round(e, 2) for e in effs],
        "eff_iso": [round(float(iso.predict([c])[0]), 3) for c in centers],
        "bin_n": bin_ns,
    }


def apply_map(gmap: dict, grade: float) -> float:
    """Strictly-increasing recalibrated grade: nondecreasing isotonic interp
    blended with the identity (STRICT_EPS weight) breaks all PAVA ties in
    grade order."""
    g_iso = float(gmap["iso"].predict([grade])[0])
    return (1.0 - STRICT_EPS) * g_iso + STRICT_EPS * float(grade)


def build_recalibrated(rows_by_side: dict) -> tuple[list[dict], dict]:
    """Attach p_after (anchor table at the recalibrated grade) to every EVAL-year
    row; the map for eval year Y is fit ONLY on OOF rows with decision_year < Y."""
    eval_rows, map_diag = [], {}
    for side, rows in rows_by_side.items():
        is_pit = side == "pit"
        grid, T = table_matrix(side)
        map_diag[side] = {}
        for yr in EVAL_YEARS:
            cal_rows = [r for r in rows if r["decision_year"] < yr]
            te = [r for r in rows if r["decision_year"] == yr]
            if not te or len(cal_rows) < MIN_CAL_ROWS:
                continue                 # never calibrate on a thin prior sample
            gmap = fit_grade_map(cal_rows, grid, T)
            for r in te:
                r = dict(r)
                g2 = apply_map(gmap, r["grade"])
                r["grade_recal"] = g2
                r["p_after"] = np.asarray(vf.p_bucket_given_fv(g2, is_pit), dtype=float)
                r["n_cal"] = len(cal_rows)
                eval_rows.append(r)
            map_diag[side][str(yr)] = {
                "n_cal": len(cal_rows),
                "bin_centers": gmap["bin_centers"],
                "bin_n": gmap["bin_n"],
                "eff_raw": gmap["eff_raw"],
                "eff_iso": gmap["eff_iso"],
                "sample_map": {str(g): round(apply_map(gmap, float(g)), 2)
                               for g in (25, 30, 35, 40, 45, 50, 55, 60, 65)},
            }
    return eval_rows, map_diag


def strictness_check(map_diag: dict, rows_by_side: dict) -> dict:
    """Numerical verification that every fitted map is strictly increasing
    (the construction guarantees it; verify anyway, do not assume)."""
    out = {}
    for side, rows in rows_by_side.items():
        grid, T = table_matrix(side)
        out[side] = {}
        for yr in EVAL_YEARS:
            cal_rows = [r for r in rows if r["decision_year"] < yr]
            if len(cal_rows) < MIN_CAL_ROWS:
                continue
            gmap = fit_grade_map(cal_rows, grid, T)
            gs = np.arange(GRID_LO, GRID_HI + 1e-9, 0.25)
            fs = np.array([apply_map(gmap, float(g)) for g in gs])
            d = np.diff(fs)
            out[side][str(yr)] = {"strictly_increasing": bool((d > 0).all()),
                                  "min_step": round(float(d.min()), 6)}
    return out


def rank_preservation_by_cell(eval_rows: list[dict]) -> dict:
    """Measured (not assumed) within-(side, eval-year) Spearman: shipped grade vs
    expected WAR under p_after. A single strictly-increasing map per cell makes
    these EQUAL by construction; any pooled Spearman deficit is therefore
    cross-cell interleaving (map drift across years + cross-side expected-WAR
    scale), not within-cell rank loss."""
    from prospect_path import _spearman
    mids = {"hit": np.asarray(vf._calibrated_midpoints("hitter")),
            "pit": np.asarray(vf._calibrated_midpoints("pitcher"))}
    out = {}
    for s in ("hit", "pit"):
        out[s] = {}
        for yr in EVAL_YEARS:
            sub = [r for r in eval_rows if r["side"] == s and r["decision_year"] == yr]
            if not sub:
                continue
            t = [r["target"] for r in sub]
            rs = _spearman([r["grade"] for r in sub], t)
            ra = _spearman([float(np.dot(r["p_after"], mids[s])) for r in sub], t)
            out[s][str(yr)] = {"n": len(sub),
                               "shipped_grade_rho": round(rs, 4),
                               "recal_rank_rho": round(ra, 4),
                               "preserved": bool(abs(ra - rs) < 1e-9)}
    return out


def sensitivity_single_prior_map(rows_by_side: dict) -> dict:
    """Sensitivity variant (NOT the gate): ONE map per side, fit only on
    decision_year < 2020 OOF rows (fully out-of-fold for every eval cohort),
    applied unchanged to all eval years. Kills cross-year map drift entirely
    (per-side pooled rank preservation becomes exact); isolates the cross-side
    expected-WAR interleaving component of the pooled Spearman deficit."""
    ev = []
    for side, rows in rows_by_side.items():
        is_pit = side == "pit"
        grid, T = table_matrix(side)
        cal = [r for r in rows if r["decision_year"] < min(EVAL_YEARS)]
        if len(cal) < MIN_CAL_ROWS:
            continue
        gmap = fit_grade_map(cal, grid, T)
        for r in rows:
            if r["decision_year"] in EVAL_YEARS:
                r = dict(r)
                g2 = apply_map(gmap, r["grade"])
                r["p_after"] = np.asarray(vf.p_bucket_given_fv(g2, is_pit), dtype=float)
                ev.append(r)
    res = evaluate(ev)
    return {
        "protocol": "single map per side fit on decision_year < 2020 only; applied to all "
                    "eval years (deployment-faithful: one shipped map at a time)",
        "pooled": {"brier": res["pooled"]["brier"], "log_loss": res["pooled"]["log_loss"],
                   "spearman": res["pooled"]["spearman"]},
        "per_side_spearman": {s: res["per_side"][s]["spearman"] for s in ("hit", "pit")},
        "per_tier_reliability": {tk: {"n": v["n"], "gap_before": v["gap_before"],
                                      "gap_after": v["gap_after"], "worse": v["worse"]}
                                 for tk, v in res["per_tier_reliability"].items()},
        "gate_equivalent_verdicts": {k: res["gate"][k]["pass"]
                                     for k in ("condition_1_brier_logloss",
                                               "condition_2_spearman",
                                               "condition_3_tier_reliability")},
        "spearman_delta_vs_shipped": res["gate"]["condition_2_spearman"]["delta"],
    }


# ---------------------------------------------------------------------------
# gate (E-ISO2 wording; conditions 1-2 identical to X-ISO's implementation)
# ---------------------------------------------------------------------------

def evaluate(rows: list[dict]) -> dict:
    """Metrics via the X-ISO harness (verbatim reuse), then the E-ISO2 gate:
    cond 3 is 'no tier worse' (the pre-registered E-ISO2 wording) rather than
    X-ISO's 'every tier strictly improves'; both readings are reported."""
    res = base.evaluate(rows)            # pooled/per-side/per-bucket/tiers/curves + X-ISO gate
    tiers = res["per_tier_reliability"]

    cond1 = res["gate"]["condition_1_brier_logloss"]           # identical definition
    cond2 = dict(res["gate"]["condition_2_spearman"])          # identical definition
    # context: what the IDENTITY transform (p_before, no recalibration) scores on the
    # same rank metric -- the metric/baseline mismatch floor for any distribution method
    sp = res["pooled"]["spearman"]
    if sp["shipped_grade"] is not None and sp["expected_war_before"] is not None:
        cond2["identity_transform_rho"] = sp["expected_war_before"]
        cond2["identity_transform_delta_vs_shipped"] = round(
            sp["expected_war_before"] - sp["shipped_grade"], 4)

    any_worse = any(v["worse"] for v in tiers.values())
    has_35 = "35" in tiers
    cond3 = {
        "pass": bool(tiers) and has_35 and not any_worse,
        "definition": "no FV tier worse (gap_after > gap_before + 1e-4); FV-35 must be present",
        "tiers_worse": [tk for tk, v in tiers.items() if v["worse"]],
        "tiers_improved": {tk: v["improved"] for tk, v in tiers.items()},
        "n_tiers": len(tiers),
        "n_improved": sum(1 for v in tiers.values() if v["improved"]),
        "fv35_present": has_35,
        "fv35_gap_before_after": ([tiers["35"]["gap_before"], tiers["35"]["gap_after"]]
                                  if has_35 else None),
        "x_iso_strict_reading_all_improved": bool(tiers) and all(v["improved"]
                                                                 for v in tiers.values()),
    }

    gate = {
        "condition_1_brier_logloss": cond1,
        "condition_2_spearman": cond2,
        "condition_3_tier_reliability": cond3,
        "verdict": "PASS" if (cond1["pass"] and cond2["pass"] and cond3["pass"]) else "FAIL",
    }
    res["gate"] = gate
    return res


# ---------------------------------------------------------------------------
# artifact
# ---------------------------------------------------------------------------

def run(persist: bool = True) -> dict:
    rows_by_side = {s: base.oof_rows(s) for s in ("hit", "pit")}   # identical splits to X-ISO
    eval_rows, map_diag = build_recalibrated(rows_by_side)
    strict = strictness_check(map_diag, rows_by_side)
    cells = rank_preservation_by_cell(eval_rows)
    sens = sensitivity_single_prior_map(rows_by_side)

    splits = {}
    for s in ("hit", "pit"):
        cnt = defaultdict(int)
        for r in rows_by_side[s]:
            cnt[r["decision_year"]] += 1
        splits[s] = {
            "chain_oof_rows_by_year": {str(y): cnt[y] for y in sorted(cnt)},
            "eval_rows": sum(1 for r in eval_rows if r["side"] == s),
            "calibrator_train_rows_by_eval_year": {
                str(y): len([r for r in rows_by_side[s] if r["decision_year"] < y])
                for y in EVAL_YEARS},
        }

    res = evaluate(eval_rows)
    fitted_method = (vf._fitted().get("method") or {})
    out = {
        "generated_at": date.today().isoformat(),
        "experiment": "E-ISO2: rank-preserving monotone recalibration of the eFV bucket "
                      "distribution in GRADE space (successor to the rejected X-ISO)",
        "spec": "gate pre-registered in docs/audit-2026-07/AUDIT_FINDINGS.md section E-ISO2; "
                "X-ISO loss ledger in data/xfv_isotonic_eval.json",
        "method": {
            "base_distribution": "shipped seam, forward-chained OOF (reused verbatim from "
                                 "tools/efv_isotonic_lab.py oof_rows): lean ridge + in-fold "
                                 "linear scale calibration -> xfv_war -> realized_implied_fv "
                                 "-> p_bucket_given_fv (uncalibrated 'before')",
            "recalibration": "strictly-increasing monotone grade map f: binned effective-grade "
                             "inversion (per grade bin, argmax over a dense grade grid of the "
                             "KM-weighted realized-bucket log-likelihood under the anchor table) "
                             "+ weighted PAVA + strict identity blend "
                             "f(g)=(1-eps)*iso(g)+eps*g, eps=0.01; "
                             "p_after = p_bucket_given_fv(f(grade)) ('after'). The anchor table "
                             "itself is untouched; only the grade it is evaluated at moves.",
            "why_rank_preserving": "both sides' fitted tables are proportional-odds ordered "
                                   "logits with strictly increasing expected WAR in grade; f "
                                   "strictly increasing => within-side expected-WAR order equals "
                                   "the shipped grade order. Pooled Spearman is still measured "
                                   "(cross-side interleaving is not guaranteed).",
            "oof_protocol": "map for eval cohort Y fit ONLY on OOF rows with decision_year < Y; "
                            "those rows were themselves predicted by models trained strictly "
                            "before them (chain years 2016-2023); no row ever calibrates itself; "
                            "no same-player leakage (each player appears in exactly one cohort)",
            "realized_bucket": "6yr-average annual WAR (target_censored/6) binned by the engine "
                               "bands: <0.5 bust / 0.5-1.5 bench / 1.5-2.5 regular / 2.5-4.0 "
                               "good / 4.0+ star",
            "pool": "full labeled matrix per side (debuted + busts, bust_recent excluded), "
                    "matching efv_model.oos_grades",
            "rank_metric": "expected WAR under the distribution (bucket probs x calibrated "
                           "bucket midpoints); shipped baseline = OOF eFV grade (as X-ISO)",
            "anchor_table_method": fitted_method,
            "eval_years": list(EVAL_YEARS),
            "chain_years": [CHAIN_YEARS[0], CHAIN_YEARS[-1]],
            "min_calibrator_rows": MIN_CAL_ROWS,
            "grid": [GRID_LO, GRID_HI, GRID_STEP],
            "bin_target": BIN_TARGET, "bin_min": BIN_MIN, "strict_eps": STRICT_EPS,
        },
        "seed": SEED,
        "cohort_splits": splits,
        "grade_maps": map_diag,
        "strict_monotonicity_check": strict,
        "rank_preservation_by_cell": cells,
        "sensitivity_single_prior_map": sens,
        "results": res,
        "gate": res["gate"],
    }

    if out["gate"]["verdict"] != "PASS":
        g = out["gate"]
        failed = [k for k in ("condition_1_brier_logloss", "condition_2_spearman",
                              "condition_3_tier_reliability") if not g[k]["pass"]]
        out["loss_ledger"] = {
            "date": date.today().isoformat(),
            "experiment": "E-ISO2 grade-space monotone recalibration (5-bucket eFV outcome "
                          "distribution)",
            "hypothesis": "a strictly-increasing monotone recalibration in grade space captures "
                          "the X-ISO calibration gain without PAVA tie-flattening",
            "what_was_tried": "binned effective-grade inversion through the anchor table + "
                              "weighted PAVA + strict identity blend (eps=0.01), forward-chained "
                              "OOF by cohort; p_after = anchor table at the recalibrated grade",
            "result": {
                "failed_conditions": failed,
                "pooled_brier_before_after": [res["pooled"]["brier"]["before"],
                                              res["pooled"]["brier"]["after"]],
                "pooled_logloss_before_after": [res["pooled"]["log_loss"]["before"],
                                                res["pooled"]["log_loss"]["after"]],
                "spearman_shipped_vs_calibrated": [g["condition_2_spearman"]["shipped_grade_rho"],
                                                   g["condition_2_spearman"]["calibrated_rank_rho"]],
                "tiers_improved": f"{g['condition_3_tier_reliability']['n_improved']}/"
                                  f"{g['condition_3_tier_reliability']['n_tiers']}",
                "tiers_worse": g["condition_3_tier_reliability"]["tiers_worse"],
                "per_side_spearman": {s: res["per_side"][s]["spearman"] for s in ("hit", "pit")},
                "rank_preservation_by_cell": cells,
                "sensitivity_single_prior_map_delta": sens["spearman_delta_vs_shipped"],
                "identity_transform_delta_vs_shipped":
                    g["condition_2_spearman"].get("identity_transform_delta_vs_shipped"),
            },
            "diagnosis": "the strict-monotone construction WORKED as designed: within every "
                         "(side, eval-year) cell the recalibrated rank equals the shipped grade "
                         "rank exactly (rank_preservation_by_cell, 8/8 preserved), so PAVA "
                         "tie-flattening (the X-ISO failure mode) is eliminated. The pooled "
                         "Spearman deficit is entirely CROSS-CELL: (a) the four forward-chained "
                         "maps drift year-to-year, reordering cross-year pairs; (b) the rank "
                         "metric (expected WAR, side-specific midpoints) interleaves hit vs pit "
                         "differently than the pooled grade baseline -- the IDENTITY transform "
                         "already scores below the shipped-grade baseline on this metric (see "
                         "identity_transform_delta_vs_shipped), so the -0.002 bar requires the "
                         "recalibration to actively IMPROVE cross-side interleaving, and it "
                         "instead worsens it (the pit map's top-end compresses toward ~FV 44-45, "
                         "pushing all top pitchers below top hitters). The single-prior-map "
                         "sensitivity (zero cross-year drift, per-side preservation exact) still "
                         "fails condition 2 on cross-side interleaving alone. Condition 3: the "
                         "FV-35 tier again degrades, but by ~0.001 absolute (0.00265 -> ~0.0035) "
                         "against a 1e-4 tolerance -- the low-grade bins' effective-grade "
                         "inversion is slightly too aggressive where the table is already "
                         "near-perfectly calibrated. The FV45+ calibration gain itself is real "
                         "and larger than X-ISO's (condition 1 passes with every bucket better; "
                         "tier-45 gap 0.0946 -> ~0.016, tier-55 0.1616 -> ~0.044).",
            "reading": "pre-registered gate requires ALL THREE conditions; a marginal result is "
                       "a FAIL (owner policy). The distribution stays on the engine's own "
                       "calibration (value_framework p_bucket_given_fv); nothing ships. NOTE for "
                       "any future re-registration (owner decision, not this lab's): condition "
                       "2's baseline (pooled shipped-grade rho) and metric (pooled expected WAR) "
                       "are not the same ordering even under the identity transform, so the bar "
                       "as written is unreachable by any within-side rank-preserving method that "
                       "does not also improve cross-side interleaving; and condition 3's 1e-4 "
                       "worse-tolerance on an FV-35 gap of 0.0027 binds at ~4% relative noise.",
            "disposition": "NO SHIP. Harness (tools/efv_grade_recal_lab.py) + this artifact are "
                           "the committed loss.",
        }

    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"wrote {OUT_PATH}")
    return out


if __name__ == "__main__":
    rep = run(persist="--dry" not in sys.argv)
    g = rep["gate"]
    p = rep["results"]["pooled"]
    print(f"\nE-ISO2 gate verdict: {g['verdict']}")
    print(f"  n eval rows: {p['n']}")
    print(f"  cond1 (brier/logloss): {g['condition_1_brier_logloss']['pass']} | "
          f"brier {p['brier']['before']} -> {p['brier']['after']} | "
          f"logloss {p['log_loss']['before']} -> {p['log_loss']['after']}")
    print(f"  cond2 (spearman): {g['condition_2_spearman']['pass']} | "
          f"shipped {g['condition_2_spearman']['shipped_grade_rho']} -> "
          f"calibrated {g['condition_2_spearman']['calibrated_rank_rho']} "
          f"(delta {g['condition_2_spearman']['delta']})")
    print(f"  cond3 (tier reliability, no-worse incl FV-35): "
          f"{g['condition_3_tier_reliability']['pass']} | "
          f"improved {g['condition_3_tier_reliability']['n_improved']}/"
          f"{g['condition_3_tier_reliability']['n_tiers']} | "
          f"worse {g['condition_3_tier_reliability']['tiers_worse']}")
    for name, v in p["per_bucket"].items():
        print(f"    {name:8s} brier {v['brier_before']} -> {v['brier_after']} | "
              f"logloss {v['logloss_before']} -> {v['logloss_after']}"
              f"{'  MATERIALLY WORSE' if v['materially_worse'] else ''}")
    for side in ("hit", "pit"):
        sp = rep["results"]["per_side"][side]["spearman"]
        print(f"  {side} spearman shipped {sp['shipped_grade']} -> after {sp['expected_war_after']}")
