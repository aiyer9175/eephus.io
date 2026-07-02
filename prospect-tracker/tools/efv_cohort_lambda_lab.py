# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""E-LAMBDA lab: per-cohort blend lambda for the eFV/consensus blend.

Gate pre-registered in docs/audit-2026-07/AUDIT_FINDINGS.md section E-LAMBDA
(written 2026-07-02, before any run):
  1. Pooled OOS Spearman does not decrease on either side.
  2. At least one cohort improves rho by +0.010 or better and NO cohort degrades
     by more than 0.005 (evaluated on cohorts with pooled scored n >= 25).
  3. Selected lambdas are stable across folds (per-fold choices reported).

METHOD (declared in this header before the first run; not tuned on results):
- Reuses the shipped forward-chained OOS protocol from tools/efv_ml_lab.py and
  tools/efv_lab_runner.py: for each fold year, the lean-feature ridge and the
  consensus OLS anchor are fit ONLY on rows with decision_year < fold year;
  predictions are made on the fold-year rows; eval truth is the canonical
  KM-censored first-6yr summed WAR (target_censored). Fold thresholds match the
  harness (test >= 12, train >= 50).
- Cohort labels (hs / college / ifa / draft / other) come from
  efv_lab_runner._cohort_of (acquisitions method + draft-age split).
- Per-cohort lambda selection is OUT OF FOLD and forward chained by cohort-year:
  for scoring year Y and cohort c, lambda_c(Y) maximizes the blended-score
  Spearman on the pooled OOF predictions of cohort c from fold years strictly
  before Y. Grid 0.00..1.00 step 0.05. Ties break toward the shipped global
  lambda, then toward the lower lambda. If the selection pool has fewer than
  MIN_SEL_N = 25 rows, the shipped global lambda is used (fallback = current
  production behavior, exactly).
- PRIMARY variant "all_prior": the selection pool also includes OOF seed folds
  from pre-2020 decision years (each still trained only on strictly earlier
  years), because a production re-tune would use all labeled data available at
  selection time. SENSITIVITY variant "scored_only": selection restricted to
  SCORED_YEARS folds (parity with efv_ml_lab.lambda_fwdchain); the first scored
  year then always falls back to shipped. The ship gate is evaluated on the
  PRIMARY variant; the sensitivity run is reported alongside.
- Stability rule (gate condition 3): for each cohort with >= 2 selected
  (non-fallback) folds, the selected-lambda range must be <= 0.20 and there
  must be no reversal where consecutive selected-fold deltas exceed 0.10 in
  opposite directions. Cohorts with <= 1 selected fold cannot oscillate.
- The pipeline is fully deterministic (closed-form ridge, in-train alpha pick);
  SEED = 7 is set anyway for discipline. Hindsight per-cohort constant-lambda
  optima are reported as DIAGNOSTIC ONLY (test-tuned, never shippable).

Run:    python tools/efv_cohort_lambda_lab.py
Writes: data/xfv_cohort_lambda_eval.json
"""
from __future__ import annotations

import json
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.chdir(ROOT)

import numpy as np

import efv_model as XM
from efv_model import _feature_spec, _fit_ols_fv, _pred_ols, blend_lambda
from prospect_path import _fit_ridge, _predict, _spearman

import efv_lab_runner as LAB

SEED = 7
SCORED_YEARS = tuple(XM.SCORED_YEARS)
MIN_TE, MIN_TR = 12, 50          # harness fold thresholds (efv_ml_lab convention)
MIN_SEL_N = 25                   # min OOF rows to select a cohort lambda
GRID = [round(0.05 * i, 2) for i in range(21)]
STAB_RANGE_MAX = 0.20            # gate-3 stability: selected-lambda range cap
STAB_REVERSAL = 0.10             # gate-3 stability: opposite-sign step cap
GATE_IMPROVE = 0.010             # gate-2: at least one cohort up by this much
GATE_DEGRADE = 0.005             # gate-2: no cohort down by more than this
EPS = 1e-9

OUT_PATH = ROOT / "data" / "xfv_cohort_lambda_eval.json"


# ---------------------------------------------------------------------------
# forward-chained OOF fold predictions (shipped machinery, shipped protocol)
# ---------------------------------------------------------------------------

def build_folds(side: str, years) -> dict:
    """{year: [ {cons, pred, truth, fv, cohort, pk} ]} -- each fold trained ONLY
    on decision_year < year, so every prediction is out of fold."""
    keys = _feature_spec(side)[0]
    rows = LAB.data_for(side)
    folds = {}
    for yr in years:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < MIN_TE or len(tr) < MIN_TR:
            continue
        ols = _fit_ols_fv([{"fv": r["fv"], "target": r["target_censored"]} for r in tr])
        ridge = _fit_ridge([{"feats": r["feats"], "target": r["target_censored"]} for r in tr], keys)
        if not (ols and ridge):
            continue
        folds[yr] = [{
            "cons": max(0.0, _pred_ols(ols, r["fv"])),
            "pred": float(_predict(ridge, r["feats"])),
            "truth": float(r["target_censored"]),
            "fv": r["fv"], "cohort": r["cohort"], "pk": r["player_key"],
        } for r in te]
    return folds


def seed_years(side) -> list:
    return sorted({r["decision_year"] for r in LAB.data_for(side)
                   if r["decision_year"] < min(SCORED_YEARS)})


# ---------------------------------------------------------------------------
# lambda selection
# ---------------------------------------------------------------------------

def pool_rho(recs, lam):
    if len(recs) < 8:
        return None
    return _spearman([(1 - lam) * r["cons"] + lam * r["pred"] for r in recs],
                     [r["truth"] for r in recs])


def select_lambda(pool, shipped):
    """(lambda, mode, pool_rho_at_choice, pool_rho_at_shipped). Argmax of the
    blend Spearman on the OOF pool over GRID; ties break toward shipped, then
    lower lambda. Below MIN_SEL_N rows: fallback to the shipped global lambda."""
    r_ship = pool_rho(pool, shipped)
    if len(pool) < MIN_SEL_N:
        return shipped, "fallback_shipped", None, r_ship
    best = None
    for lam in GRID:
        r = pool_rho(pool, lam)
        if r is None:
            continue
        key = (r, -abs(lam - shipped), -lam)
        if best is None or key > best[0]:
            best = (key, lam, r)
    if best is None:
        return shipped, "fallback_shipped", None, r_ship
    return best[1], "selected", best[2], r_ship


def stability(path):
    sel = [p["lambda"] for p in path if p["mode"] == "selected"]
    out = {"n_selected": len(sel), "selected_lambdas": sel}
    if len(sel) <= 1:
        out.update({"range": (0.0 if sel else None), "reversal": False, "stable": True,
                    "note": "fewer than 2 selected folds; cannot oscillate"})
        return out
    rng = max(sel) - min(sel)
    deltas = [round(sel[i + 1] - sel[i], 4) for i in range(len(sel) - 1)]
    rev = any((deltas[i] > STAB_REVERSAL + EPS and deltas[i + 1] < -(STAB_REVERSAL + EPS)) or
              (deltas[i] < -(STAB_REVERSAL + EPS) and deltas[i + 1] > STAB_REVERSAL + EPS)
              for i in range(len(deltas) - 1))
    out.update({"range": round(rng, 2), "step_deltas": deltas, "reversal": rev,
                "stable": (rng <= STAB_RANGE_MAX + EPS) and not rev})
    return out


# ---------------------------------------------------------------------------
# variant runner
# ---------------------------------------------------------------------------

def run_side(side: str, use_seed_folds: bool) -> dict:
    shipped = blend_lambda(side)
    folds_score = build_folds(side, SCORED_YEARS)
    folds_sel = dict(folds_score)
    seed_used = []
    if use_seed_folds:
        sf = build_folds(side, seed_years(side))
        seed_used = sorted(sf)
        folds_sel.update(sf)

    lambda_paths = defaultdict(list)
    scored = []   # (cohort, year, base_score, treat_score, truth)
    for yr in sorted(folds_score):
        recs = folds_score[yr]
        lam_by_c = {}
        for c in sorted({r["cohort"] for r in recs}):
            pool = [r for y2, rs in folds_sel.items() if y2 < yr
                    for r in rs if r["cohort"] == c]
            lam, mode, r_choice, r_ship = select_lambda(pool, shipped)
            lam_by_c[c] = lam
            lambda_paths[c].append({
                "year": yr, "lambda": round(lam, 3), "mode": mode, "pool_n": len(pool),
                "pool_rho_at_choice": (round(r_choice, 4) if r_choice is not None else None),
                "pool_rho_at_shipped": (round(r_ship, 4) if r_ship is not None else None),
            })
        for r in recs:
            lam = lam_by_c[r["cohort"]]
            base = (1 - shipped) * r["cons"] + shipped * r["pred"]
            treat = (1 - lam) * r["cons"] + lam * r["pred"]
            scored.append((r["cohort"], yr, base, treat, r["truth"]))

    rho_base = _spearman([b for _, _, b, _, _ in scored], [t for _, _, _, _, t in scored])
    rho_treat = _spearman([tr for _, _, _, tr, _ in scored], [t for _, _, _, _, t in scored])

    byc = defaultdict(list)
    for c, _, b, tr, t in scored:
        byc[c].append((b, tr, t))
    per_cohort = {}
    for c, grp in sorted(byc.items()):
        rb = _spearman([b for b, _, _ in grp], [t for _, _, t in grp])
        rt = _spearman([tr for _, tr, _ in grp], [t for _, _, t in grp])
        per_cohort[c] = {
            "n": len(grp), "gated": len(grp) >= MIN_SEL_N,
            "baseline_rho": (round(rb, 4) if rb is not None else None),
            "treatment_rho": (round(rt, 4) if rt is not None else None),
            "delta": (round(rt - rb, 4) if (rb is not None and rt is not None) else None),
        }

    stab = {c: stability(p) for c, p in sorted(lambda_paths.items())}
    return {
        "shipped_lambda": round(shipped, 3),
        "n_scored": len(scored),
        "fold_years_scored": sorted(folds_score),
        "seed_fold_years_used_for_selection": seed_used,
        "pooled": {
            "baseline_rho": round(rho_base, 4),
            "treatment_rho": round(rho_treat, 4),
            "delta": round(rho_treat - rho_base, 4),
        },
        "per_cohort": per_cohort,
        "lambda_paths": {c: p for c, p in sorted(lambda_paths.items())},
        "stability": stab,
    }


def evaluate_gate(res_by_side: dict) -> dict:
    c1 = {s: {"delta": r["pooled"]["delta"], "pass": r["pooled"]["delta"] >= -EPS}
          for s, r in res_by_side.items()}
    cohort_deltas = {}
    for s, r in res_by_side.items():
        for c, blk in r["per_cohort"].items():
            if blk["gated"] and blk["delta"] is not None:
                cohort_deltas[f"{s}:{c}"] = blk["delta"]
    improved = {k: v for k, v in cohort_deltas.items() if v >= GATE_IMPROVE - EPS}
    degraded = {k: v for k, v in cohort_deltas.items() if v < -(GATE_DEGRADE + EPS)}
    c2 = {"improved_cohorts": improved, "degraded_cohorts": degraded,
          "pass": bool(improved) and not degraded}
    unstable = {f"{s}:{c}": blk for s, r in res_by_side.items()
                for c, blk in r["stability"].items() if not blk["stable"]}
    c3 = {"unstable_cohorts": {k: {kk: vv for kk, vv in v.items()
                                   if kk in ("selected_lambdas", "range", "reversal")}
                               for k, v in unstable.items()},
          "pass": not unstable}
    return {"condition_1_pooled_no_decrease": c1,
            "condition_2_cohort_improvement": c2,
            "condition_3_lambda_stability": c3,
            "pass": all(x["pass"] for x in c1.values()) and c2["pass"] and c3["pass"]}


# ---------------------------------------------------------------------------
# diagnostics (test-tuned, never shippable; sizes the headroom only)
# ---------------------------------------------------------------------------

def diagnostics(side: str) -> dict:
    shipped = blend_lambda(side)
    folds = build_folds(side, SCORED_YEARS)
    byc = defaultdict(list)
    for rs in folds.values():
        for r in rs:
            byc[r["cohort"]].append(r)
    out = {}
    for c, grp in sorted(byc.items()):
        if len(grp) < MIN_SEL_N:
            continue
        r_ship = pool_rho(grp, shipped)
        r_cons = pool_rho(grp, 0.0)
        r_pure = pool_rho(grp, 1.0)
        best = max(GRID, key=lambda L: ((pool_rho(grp, L) or -9), -abs(L - shipped), -L))
        out[c] = {
            "n": len(grp),
            "rho_at_shipped": (round(r_ship, 4) if r_ship is not None else None),
            "rho_consensus_only_lam0": (round(r_cons, 4) if r_cons is not None else None),
            "rho_pure_model_lam1": (round(r_pure, 4) if r_pure is not None else None),
            "hindsight_best_constant_lambda": best,
            "rho_at_hindsight_best": round(pool_rho(grp, best), 4),
        }
    return out


def _observations(variants: dict, diag: dict) -> list:
    """Factual findings extracted from the run for the loss ledger."""
    obs = []
    pv = variants["all_prior"]["sides"]
    sv = variants["scored_only"]["sides"]

    def _path(v, side, c):
        return [(p["year"], p["lambda"]) for p in v[side]["lambda_paths"][c]
                if p["mode"] == "selected"]

    pi_p = pv["pit"]["per_cohort"].get("ifa", {})
    pi_s = sv["pit"]["per_cohort"].get("ifa", {})
    obs.append({
        "finding": "pit:ifa is the one cohort with consistent forward evidence: selection "
                   "moves toward the pure model in every full-pool fold of BOTH variants "
                   "and the cohort improves past the +0.010 bar both times; the intl-arm "
                   "consensus anchor is the weakest of any gated cohort",
        "delta_all_prior": pi_p.get("delta"), "delta_scored_only": pi_s.get("delta"),
        "selected_path_all_prior": _path(pv, "pit", "ifa"),
        "selected_path_scored_only": _path(sv, "pit", "ifa"),
        "consensus_only_rho": diag["pit"]["ifa"]["rho_consensus_only_lam0"],
        "pure_model_rho": diag["pit"]["ifa"]["rho_pure_model_lam1"],
    })
    obs.append({
        "finding": "the hypothesis's target cohort (intl BATS) did not deliver: hit:ifa "
                   "delta is small and its forward-selected lambda oscillates; on this OOF "
                   "protocol consensus does NOT beat the shipped blend for intl bats "
                   "(consensus-only rho trails the blend), so the premise itself weakened",
        "delta_all_prior": pv["hit"]["per_cohort"].get("ifa", {}).get("delta"),
        "selected_path_all_prior": _path(pv, "hit", "ifa"),
        "consensus_only_rho": diag["hit"]["ifa"]["rho_consensus_only_lam0"],
        "blend_rho_at_shipped": diag["hit"]["ifa"]["rho_at_shipped"],
    })
    obs.append({
        "finding": "per-cohort argmax on 25-160 row OOF pools is too noisy to select "
                   "lambda: 5 of 6 gated cohorts breached the pre-declared stability rule "
                   "and the noise-driven picks dragged pooled pit rho below baseline",
        "unstable_cohorts": sorted(variants["all_prior"]["gate"]
                                   ["condition_3_lambda_stability"]["unstable_cohorts"]),
        "pit_pooled_delta": pv["pit"]["pooled"]["delta"],
    })
    obs.append({
        "finding": "hindsight (test-tuned) constant-lambda headroom is modest outside "
                   "pit:ifa; a per-cohort scheme has little to win even with an oracle",
        "hindsight_headroom_vs_shipped": {
            f"{s}:{c}": round(d["rho_at_hindsight_best"] - d["rho_at_shipped"], 4)
            for s in ("hit", "pit") for c, d in diag[s].items()},
    })
    return obs


def harness_parity() -> dict:
    """Ties this harness to the shipped eval numbers so the baseline is auditable.
    pit at the live lambda reproduces the shipped 0.2787; hit at lambda 0.9
    reproduces the 0.3699 recorded in data/xfv_eval.json. The LIVE
    blend_lambda('hit') is WAG-calibrated from current storage and can drift
    from the lambda recorded when that eval artifact was generated; the drift
    is reported here as context only (out of scope for this experiment)."""
    out = {}
    for side, probes in (("hit", (0.9,)), ("pit", ())):
        folds = build_folds(side, SCORED_YEARS)
        allr = [r for rs in folds.values() for r in rs]
        live = blend_lambda(side)
        blk = {"n": len(allr), "live_lambda": round(live, 3),
               "pooled_rho_at_live_lambda": round(pool_rho(allr, live), 4)}
        for lam in probes:
            blk[f"pooled_rho_at_lambda_{lam}"] = round(pool_rho(allr, lam), 4)
        out[side] = blk
    out["note"] = ("pit at live lambda 0.66 reproduces the shipped 0.2787; hit at 0.9 "
                   "reproduces the 0.3699 in data/xfv_eval.json (that artifact records "
                   "shipped_lambda 0.9 while live blend_lambda('hit') currently returns "
                   "a lower WAG-calibrated value; drift flagged upstream, not part of "
                   "this experiment's gate)")
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    random.seed(SEED)
    np.random.seed(SEED)

    variants = {}
    for vid, use_seed in (("all_prior", True), ("scored_only", False)):
        res = {s: run_side(s, use_seed) for s in ("hit", "pit")}
        variants[vid] = {"sides": res, "gate": evaluate_gate(res)}

    diag = {s: diagnostics(s) for s in ("hit", "pit")}
    primary = variants["all_prior"]
    gate = primary["gate"]

    artifact = {
        "generated_at": "2026-07-02",
        "experiment": "E-LAMBDA: per-cohort blend lambda for the eFV/consensus blend",
        "spec": "gate pre-registered in docs/audit-2026-07/AUDIT_FINDINGS.md section E-LAMBDA",
        "seed": SEED,
        "method": {
            "protocol": "forward-chained OOS, shipped lean ridge + consensus OLS anchor "
                        "(efv_model machinery via efv_lab_runner rows), eval truth = "
                        "target_censored, fold thresholds test>=12/train>=50",
            "cohorts": "hs / college / ifa / draft / other from efv_lab_runner._cohort_of",
            "selection": "per cohort-year, out of fold: lambda_c(Y) = argmax blend Spearman "
                         "on pooled OOF predictions of cohort c from fold years < Y; grid "
                         "0.00..1.00 step 0.05; ties break toward shipped then lower; "
                         f"pools under {MIN_SEL_N} rows fall back to the shipped global lambda",
            "primary_variant": "all_prior (selection pool includes pre-2020 OOF seed folds; "
                               "a production re-tune would use all labeled data available at "
                               "selection time); scored_only kept as harness-parity sensitivity",
            "stability_rule": f"per cohort with >=2 selected folds: selected-lambda range <= "
                              f"{STAB_RANGE_MAX} and no opposite-sign consecutive steps > "
                              f"{STAB_REVERSAL}",
            "gate_thresholds": {"pooled_no_decrease": 0.0,
                                "cohort_improve_at_least": GATE_IMPROVE,
                                "cohort_degrade_no_more_than": GATE_DEGRADE,
                                "cohort_min_n": MIN_SEL_N},
            "declared_before_first_run": True,
        },
        "shipped_lambda": {s: round(blend_lambda(s), 3) for s in ("hit", "pit")},
        "harness_parity": harness_parity(),
        "variants": variants,
        "diagnostics_test_tuned_do_not_ship": diag,
        "gate": gate,
    }

    if not gate["pass"]:
        failed = [k for k, v in gate.items()
                  if k.startswith("condition") and not (
                      v["pass"] if "pass" in v else all(x["pass"] for x in v.values()))]
        artifact["loss_ledger"] = {
            "verdict": "NO SHIP",
            "failed_conditions": failed,
            "summary": "Per-cohort forward-chained blend-lambda selection did not clear the "
                       "pre-registered E-LAMBDA gate on the primary (all_prior) variant.",
            "detail": {
                "pooled_deltas": {s: variants["all_prior"]["sides"][s]["pooled"]["delta"]
                                  for s in ("hit", "pit")},
                "cohort_deltas": {f"{s}:{c}": blk["delta"]
                                  for s in ("hit", "pit")
                                  for c, blk in variants["all_prior"]["sides"][s]["per_cohort"].items()
                                  if blk["gated"]},
                "sensitivity_scored_only_pooled_deltas": {
                    s: variants["scored_only"]["sides"][s]["pooled"]["delta"]
                    for s in ("hit", "pit")},
            },
            "observations": _observations(variants, diag),
            "keep_alive": "See diagnostics_test_tuned_do_not_ship for the hindsight per-cohort "
                          "constant-lambda headroom (test-tuned upper bound). If headroom exists "
                          "but forward selection cannot capture it, a future gated attempt should "
                          "use a shrunk or hierarchical lambda estimator (cohort posterior toward "
                          "the global lambda) rather than per-cohort argmax, and should wait for "
                          "more scored fold years.",
        }

    OUT_PATH.write_text(json.dumps(artifact, indent=1), encoding="utf-8")

    # compact stdout summary
    print(f"E-LAMBDA gate (primary=all_prior): {'PASS' if gate['pass'] else 'FAIL'}")
    for s in ("hit", "pit"):
        r = variants["all_prior"]["sides"][s]
        print(f"  {s}: shipped_lam={r['shipped_lambda']} pooled base={r['pooled']['baseline_rho']} "
              f"treat={r['pooled']['treatment_rho']} delta={r['pooled']['delta']}")
        for c, blk in r["per_cohort"].items():
            if blk["gated"]:
                path = [(p['year'], p['lambda'], p['mode'][:4]) for p in r['lambda_paths'][c]]
                print(f"    {c:8s} n={blk['n']:3d} base={blk['baseline_rho']} "
                      f"treat={blk['treatment_rho']} delta={blk['delta']} path={path}")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
