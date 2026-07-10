# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""eFV grade-space monotone recalibration, production-relevant gate (E-ISO3).

EXPERIMENT (pre-registered gate: docs/audit-2026-07/AUDIT_FINDINGS.md, section E-ISO3):
the SAME strictly-increasing grade-space monotone recalibration as E-ISO2 (that lab's
build machinery is imported and reused verbatim, so the recalibrated rows are identical
by construction), re-evaluated under the redesigned production-relevant gate. Redesign
rationale, stated a priori in the registration: in production every player is scored by
the SAME season's map, so cross-year map drift (the entire E-ISO2 pooled-Spearman
deficit) never manifests on any surface; and E-ISO2's per-tier worse-tolerance (1e-4
absolute) was far tighter than tier-gap estimation noise. The board DOES rank hitters
and pitchers together, so cross-side stability WITHIN a season is real and stays in
the gate.

GATE (ALL must hold; pre-registered BEFORE this run; marginal = FAIL, owner policy):
  1. Pooled AND per-side AND per-bucket Brier/log-loss improve; no bucket materially
     worse on EITHER side (MATERIAL_TOL relative, checked per side explicitly).
  2. Within-(side, year) rank preservation is EXACT (strict monotonicity in grade
     space; measured per cell, never assumed).
  3. Cross-side within-YEAR pooled Spearman delta >= -0.002 vs the shipped grade for
     EVERY evaluation year 2020-2023 (never pooled across years).
  4. Per-tier reliability: every FV 45+ tier improves; no tier's gap worsens by more
     than 0.005 absolute.

This is an EXPERIMENT HARNESS ONLY -- nothing wires into the pipeline; ship wiring
happens orchestrator-side only on a clear gate pass (expected-CHANGED output-diff
discipline: xfv.json + trade_values.json + direct downstreams).

Artifact: data/xfv_grade_recal3_eval.json (same reliability-curve schema as the
E-ISO2 artifact so the PROSPX reliability diagram could render either).

Run: python tools/efv_grade_recal3_lab.py        SEED=7, fully deterministic.
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
import efv_grade_recal_lab as e2         # E-ISO2 lab: the recalibration itself, verbatim
from prospect_path import _spearman

SEED = 7                                 # matches X-ISO/E-ISO2; pipeline is deterministic
np.random.seed(SEED)

BUCKETS = base.BUCKETS
EVAL_YEARS = base.EVAL_YEARS             # 2020-2023 (canonical eval cohorts)
MATERIAL_TOL = base.MATERIAL_TOL         # 0.01 relative, as X-ISO/E-ISO2
CROSS_SIDE_TOL = 0.002                   # condition 3 per-year tolerance (gate text)
TIER_WORSE_ABS = 0.005                   # condition 4 absolute worse-tolerance (gate text)
FV45_PLUS = 45                           # condition 4 must-improve tier floor

OUT_PATH = ROOT / "data" / "xfv_grade_recal3_eval.json"


def _mids():
    return {"hit": np.asarray(vf._calibrated_midpoints("hitter")),
            "pit": np.asarray(vf._calibrated_midpoints("pitcher"))}


# ---------------------------------------------------------------------------
# condition 3: cross-side, within-year pooled Spearman (never pooled across years)
# ---------------------------------------------------------------------------

def cross_side_by_year(eval_rows: list[dict]) -> dict:
    """Per evaluation year: pool BOTH sides' rows for that year only, then Spearman
    vs realized target. Baseline = shipped OOF grade (FV scale, side-comparable);
    candidate = expected WAR under p_after (side-specific calibrated midpoints);
    identity = expected WAR under p_before (the metric's own noise floor)."""
    mids = _mids()
    out = {}
    for yr in EVAL_YEARS:
        sub = [r for r in eval_rows if r["decision_year"] == yr]
        if not sub:
            continue
        t = [r["target"] for r in sub]
        rho_shipped = _spearman([r["grade"] for r in sub], t)
        rho_before = _spearman([float(np.dot(r["p_before"], mids[r["side"]])) for r in sub], t)
        rho_after = _spearman([float(np.dot(r["p_after"], mids[r["side"]])) for r in sub], t)
        out[str(yr)] = {
            "n": len(sub),
            "n_hit": sum(1 for r in sub if r["side"] == "hit"),
            "n_pit": sum(1 for r in sub if r["side"] == "pit"),
            "shipped_grade_rho": round(rho_shipped, 4),
            "identity_rho": round(rho_before, 4),
            "recal_rho": round(rho_after, 4),
            "delta_vs_shipped": round(rho_after - rho_shipped, 4),
            "identity_delta_vs_shipped": round(rho_before - rho_shipped, 4),
            "pass": bool((rho_after - rho_shipped) >= -CROSS_SIDE_TOL),
        }
    return out


# ---------------------------------------------------------------------------
# the E-ISO3 gate
# ---------------------------------------------------------------------------

def gate_e_iso3(res: dict, cells: dict, by_year: dict) -> dict:
    """res = base.evaluate() output (pooled/per_side/per_bucket/tiers/curves);
    cells = e2.rank_preservation_by_cell(); by_year = cross_side_by_year()."""
    pooled, per_side, tiers = res["pooled"], res["per_side"], res["per_tier_reliability"]

    # --- condition 1: pooled AND per-side AND per-bucket, materiality per side ---
    def _improves(blk):
        return bool(blk["brier"]["after"] < blk["brier"]["before"]
                    and blk["log_loss"]["after"] < blk["log_loss"]["before"])

    pooled_improves = _improves(pooled)
    side_improves = {s: _improves(per_side[s]) for s in ("hit", "pit")}
    pooled_buckets_improve = all(v["brier_improved"] and v["logloss_improved"]
                                 for v in pooled["per_bucket"].values())
    pooled_no_material = not any(v["materially_worse"] for v in pooled["per_bucket"].values())
    side_material = {s: [name for name, v in per_side[s]["per_bucket"].items()
                         if v["materially_worse"]] for s in ("hit", "pit")}
    side_buckets_improve = {s: all(v["brier_improved"] and v["logloss_improved"]
                                   for v in per_side[s]["per_bucket"].values())
                            for s in ("hit", "pit")}
    no_material_either_side = not any(side_material[s] for s in ("hit", "pit"))
    cond1 = {
        "pass": bool(pooled_improves and all(side_improves.values())
                     and pooled_buckets_improve and pooled_no_material
                     and no_material_either_side),
        "definition": "pooled Brier AND log-loss improve; each side's pooled Brier AND "
                      "log-loss improve; every pooled bucket improves on both metrics; "
                      "no bucket materially worse (rel > 0.01 on either metric) pooled "
                      "OR on either side (the per-side materiality check is the E-ISO3 "
                      "addition, stated per-side explicitly in the registration)",
        "pooled_improves": pooled_improves,
        "per_side_improves": side_improves,
        "pooled_all_buckets_improve": pooled_buckets_improve,
        "pooled_no_bucket_materially_worse": pooled_no_material,
        "per_side_all_buckets_improve_diagnostic": side_buckets_improve,
        "per_side_buckets_materially_worse": side_material,
        "material_tolerance_rel": MATERIAL_TOL,
    }

    # --- condition 2: within-(side, year) rank preservation EXACT ---------------
    flat = [(s, yr, c) for s, yrs in cells.items() for yr, c in yrs.items()]
    cond2 = {
        "pass": bool(flat) and all(c["preserved"] for _, _, c in flat),
        "definition": "measured within-(side, eval-year) Spearman of the recalibrated "
                      "expected-WAR rank equals the shipped grade Spearman exactly "
                      "(abs diff < 1e-9) in every cell",
        "n_cells": len(flat),
        "n_preserved": sum(1 for _, _, c in flat if c["preserved"]),
        "cells_not_preserved": [f"{s}/{yr}" for s, yr, c in flat if not c["preserved"]],
    }

    # --- condition 3: cross-side within-YEAR pooled Spearman, every year --------
    years_failed = [yr for yr, v in by_year.items() if not v["pass"]]
    cond3 = {
        "pass": bool(by_year) and len(by_year) == len(EVAL_YEARS) and not years_failed,
        "definition": "for EVERY evaluation year 2020-2023, the cross-side pooled "
                      "Spearman (both sides, that year only, never pooled across years) "
                      "of the recalibrated rank vs the shipped grade baseline has "
                      "delta >= -0.002",
        "tolerance": -CROSS_SIDE_TOL,
        "per_year_delta": {yr: v["delta_vs_shipped"] for yr, v in by_year.items()},
        "per_year_pass": {yr: v["pass"] for yr, v in by_year.items()},
        "years_failed": years_failed,
        "identity_per_year_delta": {yr: v["identity_delta_vs_shipped"]
                                    for yr, v in by_year.items()},
    }

    # --- condition 4: FV45+ tiers improve; no tier worse by > 0.005 absolute ----
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


# ---------------------------------------------------------------------------
# artifact
# ---------------------------------------------------------------------------

def run(persist: bool = True) -> dict:
    rows_by_side = {s: base.oof_rows(s) for s in ("hit", "pit")}   # identical splits to X-ISO
    eval_rows, map_diag = e2.build_recalibrated(rows_by_side)      # identical recal to E-ISO2
    strict = e2.strictness_check(map_diag, rows_by_side)
    cells = e2.rank_preservation_by_cell(eval_rows)
    by_year = cross_side_by_year(eval_rows)

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

    res = base.evaluate(eval_rows)       # pooled/per-side/per-bucket/tiers/curves (X-ISO gate ignored)
    res.pop("gate", None)                # the X-ISO gate does not apply here
    gate = gate_e_iso3(res, cells, by_year)
    fitted_method = (vf._fitted().get("method") or {})

    out = {
        "generated_at": date.today().isoformat(),
        "experiment": "E-ISO3: eFV bucket-distribution calibration under the redesigned "
                      "production-relevant gate (same monotone grade-space recalibration "
                      "as E-ISO2, re-gated)",
        "spec": "gate pre-registered in docs/audit-2026-07/AUDIT_FINDINGS.md section E-ISO3; "
                "predecessors: E-ISO2 loss ledger in data/xfv_grade_recal_eval.json, X-ISO "
                "loss ledger in data/xfv_isotonic_eval.json",
        "method": {
            "base_distribution": "shipped seam, forward-chained OOF (reused verbatim from "
                                 "tools/efv_isotonic_lab.py oof_rows): lean ridge + in-fold "
                                 "linear scale calibration -> xfv_war -> realized_implied_fv "
                                 "-> p_bucket_given_fv (uncalibrated 'before')",
            "recalibration": "IDENTICAL to E-ISO2 (tools/efv_grade_recal_lab.py "
                             "build_recalibrated, imported and reused): strictly-increasing "
                             "monotone grade map f = binned effective-grade inversion + "
                             "weighted PAVA + strict identity blend (eps=0.01); "
                             "p_after = p_bucket_given_fv(f(grade))",
            "oof_protocol": "map for eval cohort Y fit ONLY on OOF rows with decision_year < Y; "
                            "chain years 2016-2023; no row ever calibrates itself; no "
                            "same-player leakage (each player appears in exactly one cohort)",
            "realized_bucket": "6yr-average annual WAR (target_censored/6) binned by the engine "
                               "bands: <0.5 bust / 0.5-1.5 bench / 1.5-2.5 regular / 2.5-4.0 "
                               "good / 4.0+ star",
            "pool": "full labeled matrix per side (debuted + busts, bust_recent excluded), "
                    "matching efv_model.oos_grades",
            "rank_metric": "expected WAR under the distribution (bucket probs x calibrated "
                           "bucket midpoints); shipped baseline = OOF eFV grade",
            "gate_redesign": "condition 2 replaces E-ISO2's cross-year pooled Spearman with "
                             "exact within-(side, year) preservation (production scores every "
                             "player with the same season's map, so cross-year drift never "
                             "manifests); condition 3 keeps cross-side stability but within "
                             "each year only; condition 1 adds per-side pooled and per-side "
                             "materiality; condition 4 widens the tier worse-tolerance from "
                             "1e-4 to 0.005 absolute and requires improvement at FV 45+ only",
            "anchor_table_method": fitted_method,
            "eval_years": list(EVAL_YEARS),
            "chain_years": [base.CHAIN_YEARS[0], base.CHAIN_YEARS[-1]],
            "min_calibrator_rows": base.MIN_CAL_ROWS,
            "grid": [e2.GRID_LO, e2.GRID_HI, e2.GRID_STEP],
            "bin_target": e2.BIN_TARGET, "bin_min": e2.BIN_MIN, "strict_eps": e2.STRICT_EPS,
        },
        "seed": SEED,
        "cohort_splits": splits,
        "grade_maps": map_diag,
        "strict_monotonicity_check": strict,
        "rank_preservation_by_cell": cells,
        "cross_side_spearman_by_year": by_year,
        "results": res,
        "gate": gate,
    }

    if gate["verdict"] != "PASS":
        failed = [k for k in ("condition_1_brier_logloss", "condition_2_rank_preservation",
                              "condition_3_cross_side_by_year", "condition_4_tier_reliability")
                  if not gate[k]["pass"]]
        c1, c3, c4 = (gate["condition_1_brier_logloss"],
                      gate["condition_3_cross_side_by_year"],
                      gate["condition_4_tier_reliability"])
        out["loss_ledger"] = {
            "date": date.today().isoformat(),
            "experiment": "E-ISO3: grade-space monotone recalibration of the eFV 5-bucket "
                          "distribution, production-relevant gate",
            "hypothesis": "the E-ISO2 recalibration, whose real calibration gain was rejected "
                          "only by a cross-year rank metric that production never exercises, "
                          "clears a gate scoped to production-relevant behavior",
            "what_was_tried": "the identical E-ISO2 recalibration (imported, not refit) "
                              "re-evaluated under the four-condition E-ISO3 gate",
            "result": {
                "failed_conditions": failed,
                "pooled_brier_before_after": [res["pooled"]["brier"]["before"],
                                              res["pooled"]["brier"]["after"]],
                "pooled_logloss_before_after": [res["pooled"]["log_loss"]["before"],
                                                res["pooled"]["log_loss"]["after"]],
                "per_side_buckets_materially_worse": c1["per_side_buckets_materially_worse"],
                "pit_bench_bucket": res["per_side"]["pit"]["per_bucket"]["bench"],
                "cross_side_per_year_delta": c3["per_year_delta"],
                "cross_side_years_failed": c3["years_failed"],
                "identity_per_year_delta": c3["identity_per_year_delta"],
                "rank_preservation": f"{gate['condition_2_rank_preservation']['n_preserved']}/"
                                     f"{gate['condition_2_rank_preservation']['n_cells']}",
                "fv45_plus_not_improved": c4["fv45_plus_not_improved"],
                "tiers_worse_beyond_0p005": c4["tiers_worse_beyond_0p005"],
                "tier_gap_delta_abs": c4["tier_gap_delta_abs"],
            },
            "diagnosis": "two independent failures. CONDITION 1: the newly-explicit per-side "
                         "materiality check catches the pitcher BENCH bucket (brier 0.07019 -> "
                         "0.0703, log-loss 0.25642 -> 0.25999, +1.4% relative vs the 1% "
                         "tolerance): the pit maps pull mid-grade pitchers' probability mass "
                         "toward bust at bench's expense, which the pooled view (hitters' large "
                         "bench gain) masked in E-ISO2. CONDITION 3: within-year cross-side "
                         "Spearman is unstable under the recalibration; 2020 and 2022 improve "
                         "(+0.0123, +0.0060) but 2021 (-0.0264) and 2023 (-0.0252) blow through "
                         "the -0.002 bar by an order of magnitude. This is NOT the E-ISO2 "
                         "metric-floor artifact: in 2021 the IDENTITY transform scores +0.0141 "
                         "ABOVE the shipped-grade baseline within-year, so the recalibration "
                         "itself degrades cross-side interleaving there by ~0.04 rho. Mechanism "
                         "as diagnosed in E-ISO2: the pit maps compress the top end toward "
                         "~FV 44-45, dropping top pitchers below top hitters, and whether that "
                         "helps or hurts depends on which side's elite cohort hit in a given "
                         "year, hence the sign flips. The calibration gain itself remains real "
                         "and large (conditions 2 and 4 pass cleanly: 8/8 within-cell rank "
                         "preservation; every FV45+ tier improves, tier-45 gap 0.0946 -> "
                         "0.0156, tier-55 0.1616 -> 0.0436; FV-35 worse by only 0.00087 vs the "
                         "0.005 tolerance).",
            "reading": "the redesigned gate did exactly what it was built to do: it removed the "
                       "two E-ISO2 objections that production never exercises (cross-year map "
                       "drift, 1e-4 tier noise) and the method STILL fails on two effects a "
                       "reader of the board would actually see: a genuinely worse pitcher "
                       "bench-probability and year-dependent cross-side rank churn. This is a "
                       "clean rejection of the recalibration, not of the gate.",
            "disposition": "NO SHIP. Per the pre-registration, this is the FINAL loss ledger: "
                           "no further calibration attempts against this data vintage. Harness "
                           "(tools/efv_grade_recal3_lab.py) + this artifact are the committed "
                           "loss.",
        }

    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"wrote {OUT_PATH}")
    return out


if __name__ == "__main__":
    rep = run(persist="--dry" not in sys.argv)
    g = rep["gate"]
    p = rep["results"]["pooled"]
    print(f"\nE-ISO3 gate verdict: {g['verdict']}")
    print(f"  n eval rows: {p['n']}")
    c1 = g["condition_1_brier_logloss"]
    print(f"  cond1 (brier/logloss pooled+per-side+per-bucket): {c1['pass']} | "
          f"pooled brier {p['brier']['before']} -> {p['brier']['after']} | "
          f"logloss {p['log_loss']['before']} -> {p['log_loss']['after']} | "
          f"per-side materially worse: {c1['per_side_buckets_materially_worse']}")
    c2 = g["condition_2_rank_preservation"]
    print(f"  cond2 (within-cell rank preservation exact): {c2['pass']} | "
          f"{c2['n_preserved']}/{c2['n_cells']} cells")
    c3 = g["condition_3_cross_side_by_year"]
    print(f"  cond3 (cross-side within-year spearman): {c3['pass']}")
    for yr, v in rep["cross_side_spearman_by_year"].items():
        print(f"    {yr}: shipped {v['shipped_grade_rho']} -> recal {v['recal_rho']} "
              f"(delta {v['delta_vs_shipped']}, identity delta "
              f"{v['identity_delta_vs_shipped']}, n={v['n']}) "
              f"{'PASS' if v['pass'] else 'FAIL'}")
    c4 = g["condition_4_tier_reliability"]
    print(f"  cond4 (tier reliability, FV45+ improve, worse<=0.005): {c4['pass']} | "
          f"delta by tier {c4['tier_gap_delta_abs']}")
    for side in ("hit", "pit"):
        blk = rep["results"]["per_side"][side]
        print(f"  {side}: brier {blk['brier']['before']} -> {blk['brier']['after']} | "
              f"logloss {blk['log_loss']['before']} -> {blk['log_loss']['after']}")
        for name, v in blk["per_bucket"].items():
            print(f"    {name:8s} brier {v['brier_before']} -> {v['brier_after']} | "
                  f"logloss {v['logloss_before']} -> {v['logloss_after']}"
                  f"{'  MATERIALLY WORSE' if v['materially_worse'] else ''}")
