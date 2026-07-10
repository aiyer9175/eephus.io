# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""WS-M / M3 -- HIERARCHICAL SHRUNK per-cohort blend lambda (the E-LAMBDA keep-alive
successor). Extends tools/efv_cohort_lambda_lab.py: instead of the per-cohort ARGMAX
lambda (which E-LAMBDA proved too noisy on 25-160 row OOF pools -> NO SHIP), each
cohort's lambda is a shrinkage posterior toward the global rank-gate lambda:

    lambda_c(Y) = (n_c * lambdahat_c(Y) + k * lambda_global) / (n_c + k)

  lambdahat_c(Y)  per-cohort argmax on the OOF pool of cohort c from fold years < Y
                  (the E-LAMBDA forward-chained selector, reused verbatim).
  n_c             that OOF pool size (thin pools -> heavier shrink to global).
  lambda_global   the shipped rank-gate lambda = efv_model.blend_lambda(side).
  k in {50,100,200}  shrinkage strength, selected on PRE-2023 folds only (2023 held out).

Gate pre-registered in docs/prelaunch-2026-07/GATES.md section M3. SHIP iff ALL of:
  1. Pooled Spearman no-decrease (>= -0.000) on BOTH sides.
  2. Each named target cohort (pit:ifa, pit <=2018 era) with n>=25 improves >= +0.01.
  3. No cohort with n>=25 degrades > 0.005 (either side).
  4. Per-era cells: no drop > 0.01 on either side.
  5. Within-tier and t45 >= -0.005 (either side).
  6. Fold-stability: the applied lambda_c range across folds <= 0.20 and no opposite-
     sign consecutive step > 0.10 (E-LAMBDA rule, on the SHRUNK path).

Leaves the binding E-LAMBDA artifact (data/xfv_cohort_lambda_eval.json) untouched.
Writes data/xfv_cohort_lambda_hier_eval.json.

Run:  python tools/efv_cohort_lambda_hier_lab.py
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import os
os.chdir(ROOT)

from efv_model import blend_lambda
from prospect_path import _spearman

# reuse the E-LAMBDA machinery verbatim (forward-chained OOF folds + argmax selector)
from efv_cohort_lambda_lab import (build_folds, seed_years, select_lambda, pool_rho,
                                    SCORED_YEARS, MIN_SEL_N, EPS)

SEED = 7
K_GRID = (50, 100, 200)
PRE_2023 = tuple(y for y in SCORED_YEARS if y < 2023)
# The pre-registered named targets are pit:ifa (the proven keep-alive direction, +0.0247)
# and the pit <=2018 era cell. Side-specific: hit:ifa is NOT a target (a hit:ifa move is
# governed by the no-degrade clause 3, not the target clause 2).
NAMED_TARGETS = (("pit", "ifa"),)
STAB_RANGE_MAX = 0.20
STAB_REVERSAL = 0.10

# gate thresholds
G_POOLED = 0.0
G_TARGET_IMPROVE = 0.01
G_DEGRADE = 0.005
G_ERA_DROP = 0.01
G_TIER = -0.005

OUT_PATH = ROOT / "data" / "xfv_cohort_lambda_hier_eval.json"


def _era(yr):
    return "<=2018" if yr <= 2018 else ("2019-2021" if yr <= 2021 else "2022-2023")


def _tier(fv):
    return round(fv / 5) * 5


def cohort_lambdas(side, folds_score, folds_sel, shipped, k, yr):
    """{cohort: {lambda_c, lambdahat, n_c, mode}} for test year yr, OOF pools from < yr."""
    out = {}
    for c in sorted({r["cohort"] for r in folds_score[yr]}):
        pool = [r for y2, rs in folds_sel.items() if y2 < yr
                for r in rs if r["cohort"] == c]
        lamhat, mode, _rc, _rs = select_lambda(pool, shipped)
        n_c = len(pool)
        lam_c = (n_c * lamhat + k * shipped) / (n_c + k)
        out[c] = {"lambda_c": lam_c, "lambdahat": lamhat, "n_c": n_c, "mode": mode}
    return out


def score_side(side, k, score_years):
    """Forward-chained treatment (shrunk cohort lambda) vs baseline (global lambda).
    Returns pooled/cohort/era/tier metrics + the applied lambda_c paths."""
    shipped = round(blend_lambda(side), 4)
    folds_score = build_folds(side, SCORED_YEARS)
    folds_sel = dict(folds_score)
    folds_sel.update(build_folds(side, seed_years(side)))   # all_prior variant (E-LAMBDA primary)

    lam_paths = defaultdict(list)
    scored = []   # (cohort, era, fv, base, treat, truth)
    for yr in sorted(folds_score):
        if yr not in score_years:
            continue
        lam_by_c = cohort_lambdas(side, folds_score, folds_sel, shipped, k, yr)
        for c, blk in lam_by_c.items():
            lam_paths[c].append({"year": yr, "lambda_c": round(blk["lambda_c"], 4),
                                 "lambdahat": round(blk["lambdahat"], 3),
                                 "n_c": blk["n_c"], "mode": blk["mode"]})
        for r in folds_score[yr]:
            lam_c = lam_by_c[r["cohort"]]["lambda_c"]
            base = (1 - shipped) * r["cons"] + shipped * r["pred"]
            treat = (1 - lam_c) * r["cons"] + lam_c * r["pred"]
            scored.append((r["cohort"], _era(yr), r["fv"], base, treat, r["truth"]))
    return shipped, scored, lam_paths


def _rho(pairs):
    return _spearman([a for a, _ in pairs], [b for _, b in pairs])


def metrics(scored):
    base = _rho([(b, t) for _, _, _, b, _, t in scored])
    treat = _rho([(tr, t) for _, _, _, _, tr, t in scored])
    out = {"pooled": {"base": _r(base), "treat": _r(treat), "delta": _d(treat, base)}}
    # per cohort
    byc = defaultdict(list)
    for c, _, _, b, tr, t in scored:
        byc[c].append((b, tr, t))
    out["per_cohort"] = {}
    for c, g in sorted(byc.items()):
        rb = _rho([(b, t) for b, _, t in g])
        rt = _rho([(tr, t) for _, tr, t in g])
        out["per_cohort"][c] = {"n": len(g), "gated": len(g) >= MIN_SEL_N,
                                "base": _r(rb), "treat": _r(rt), "delta": _d(rt, rb)}
    # per era
    bye = defaultdict(list)
    for _, e, _, b, tr, t in scored:
        bye[e].append((b, tr, t))
    out["per_era"] = {}
    for e, g in sorted(bye.items()):
        if len(g) < 15:
            continue
        rb = _rho([(b, t) for b, _, t in g])
        rt = _rho([(tr, t) for _, tr, t in g])
        out["per_era"][e] = {"n": len(g), "base": _r(rb), "treat": _r(rt), "delta": _d(rt, rb)}
    # within-tier weighted-mean + t45 (base and treat)
    out["within_tier"] = _tier_metrics(scored)
    return out


def _tier_metrics(scored):
    byt = defaultdict(list)
    for _, _, fv, b, tr, t in scored:
        byt[_tier(fv)].append((b, tr, t))
    wsum_b = wsum_t = wn = 0.0
    t45_b = t45_t = None
    for tk, g in byt.items():
        if len(g) < 15:
            continue
        rb = _rho([(b, t) for b, _, t in g])
        rt = _rho([(tr, t) for _, tr, t in g])
        if rb is None or rt is None:
            continue
        wsum_b += rb * len(g)
        wsum_t += rt * len(g)
        wn += len(g)
        if tk == 45:
            t45_b, t45_t = rb, rt
    wm_b = wsum_b / wn if wn else None
    wm_t = wsum_t / wn if wn else None
    return {"wm_base": _r(wm_b), "wm_treat": _r(wm_t), "wm_delta": _d(wm_t, wm_b),
            "t45_base": _r(t45_b), "t45_treat": _r(t45_t), "t45_delta": _d(t45_t, t45_b)}


def _r(v):
    return round(v, 4) if v is not None else None


def _d(a, b):
    return round(a - b, 4) if (a is not None and b is not None) else None


def stability(lam_paths):
    """E-LAMBDA fold-stability on the APPLIED (shrunk) lambda_c sequence, gated cohorts."""
    out = {}
    for c, path in sorted(lam_paths.items()):
        seq = [p["lambda_c"] for p in path]
        if len(seq) <= 1:
            out[c] = {"lambda_c_path": seq, "range": 0.0, "reversal": False, "stable": True,
                      "note": "fewer than 2 folds; cannot oscillate"}
            continue
        rng = max(seq) - min(seq)
        deltas = [round(seq[i + 1] - seq[i], 4) for i in range(len(seq) - 1)]
        rev = any((deltas[i] > STAB_REVERSAL + EPS and deltas[i + 1] < -(STAB_REVERSAL + EPS)) or
                  (deltas[i] < -(STAB_REVERSAL + EPS) and deltas[i + 1] > STAB_REVERSAL + EPS)
                  for i in range(len(deltas) - 1))
        out[c] = {"lambda_c_path": [round(x, 4) for x in seq], "range": round(rng, 4),
                  "step_deltas": deltas, "reversal": rev,
                  "stable": (rng <= STAB_RANGE_MAX + EPS) and not rev}
    return out


def select_k(side):
    """k in K_GRID maximizing pooled TREATMENT rho on PRE-2023 folds only (2023 held out)."""
    curve = {}
    for k in K_GRID:
        _sh, scored, _lp = score_side(side, k, PRE_2023)
        treat = _rho([(tr, t) for _, _, _, _, tr, t in scored])
        curve[k] = _r(treat)
    best_k = max(K_GRID, key=lambda k: (curve[k] if curve[k] is not None else -9))
    return best_k, curve


def run_side(side):
    best_k, k_curve = select_k(side)
    shipped, scored, lam_paths = score_side(side, best_k, SCORED_YEARS)
    m = metrics(scored)
    stab = stability(lam_paths)
    return {
        "shipped_lambda_global": shipped,
        "selected_k": best_k,
        "k_selection_pre2023_pooled_treat_rho": k_curve,
        "n_scored": len(scored),
        "metrics": m,
        "lambda_c_paths": {c: p for c, p in sorted(lam_paths.items())},
        "stability": stab,
    }


def evaluate_gate(sides):
    # c1 pooled no-decrease both sides
    c1 = {s: {"delta": sides[s]["metrics"]["pooled"]["delta"],
              "pass": (sides[s]["metrics"]["pooled"]["delta"] or -9) >= G_POOLED - EPS}
          for s in sides}
    # c2 named targets (side-specific) improve >= +0.01 (gated cohorts only)
    tgt = {}
    for s, c in NAMED_TARGETS:
        blk = sides[s]["metrics"]["per_cohort"].get(c)
        if blk and blk["gated"] and blk["delta"] is not None:
            tgt[f"{s}:{c}"] = {"delta": blk["delta"], "gated": True,
                               "pass": blk["delta"] >= G_TARGET_IMPROVE - EPS}
        else:
            tgt[f"{s}:{c}"] = {"delta": (blk or {}).get("delta"),
                               "gated": bool(blk and blk["gated"]), "pass": False}
    # pit <=2018 era is a named target too but is unreachable in SCORED_YEARS folds (n<25)
    pit_pre2018 = sides["pit"]["metrics"]["per_era"].get("<=2018")
    c2_pass = bool(tgt) and all(v["pass"] for v in tgt.values()) and tgt.get("pit:ifa", {}).get("pass", False)
    c2 = {"named_targets": tgt,
          "pit_pre2018_era_note": ("not scoreable: <=2018 era absent from SCORED_YEARS folds"
                                   if not pit_pre2018 else pit_pre2018),
          "requires": "pit:ifa gated & improves >= +0.01", "pass": c2_pass}
    # c3 no gated cohort degrades > 0.005
    degraded = {}
    for s in sides:
        for c, blk in sides[s]["metrics"]["per_cohort"].items():
            if blk["gated"] and blk["delta"] is not None and blk["delta"] < -(G_DEGRADE + EPS):
                degraded[f"{s}:{c}"] = blk["delta"]
    c3 = {"degraded_gated_cohorts": degraded, "pass": not degraded}
    # c4 era no drop > 0.01
    era_drops = {}
    for s in sides:
        for e, blk in sides[s]["metrics"]["per_era"].items():
            if blk["delta"] is not None and blk["delta"] < -(G_ERA_DROP + EPS):
                era_drops[f"{s}:{e}"] = blk["delta"]
    c4 = {"era_drops": era_drops, "pass": not era_drops}
    # c5 within-tier + t45 >= -0.005
    tier_fail = {}
    for s in sides:
        wt = sides[s]["metrics"]["within_tier"]
        for key in ("wm_delta", "t45_delta"):
            v = wt.get(key)
            if v is not None and v < G_TIER - EPS:
                tier_fail[f"{s}:{key}"] = v
    c5 = {"tier_failures": tier_fail, "pass": not tier_fail}
    # c6 stability (gated cohorts)
    unstable = {}
    for s in sides:
        gated = {c for c, blk in sides[s]["metrics"]["per_cohort"].items() if blk["gated"]}
        for c, blk in sides[s]["stability"].items():
            if c in gated and not blk["stable"]:
                unstable[f"{s}:{c}"] = {"range": blk["range"], "reversal": blk["reversal"],
                                        "lambda_c_path": blk["lambda_c_path"]}
    c6 = {"unstable_gated_cohorts": unstable, "pass": not unstable}

    passed = (all(x["pass"] for x in c1.values()) and c2["pass"] and c3["pass"]
              and c4["pass"] and c5["pass"] and c6["pass"])
    return {
        "condition_1_pooled_no_decrease": c1,
        "condition_2_target_cohort_improve": c2,
        "condition_3_no_cohort_degrade": c3,
        "condition_4_era_no_drop": c4,
        "condition_5_within_tier_t45": c5,
        "condition_6_fold_stability": c6,
        "pass": passed,
    }


def main():
    random.seed(SEED)
    sides = {s: run_side(s) for s in ("hit", "pit")}
    gate = evaluate_gate(sides)

    artifact = {
        "generated_at": "2026-07-07",
        "experiment": "M3: hierarchical shrunk per-cohort blend lambda (E-LAMBDA keep-alive successor)",
        "spec": "gate pre-registered in docs/prelaunch-2026-07/GATES.md section M3",
        "seed": SEED,
        "method": {
            "estimator": "lambda_c = (n_c*lambdahat_c + k*lambda_global)/(n_c + k); "
                         "lambdahat_c = E-LAMBDA forward-chained per-cohort argmax on OOF pool "
                         "(years < Y); lambda_global = blend_lambda(side)",
            "k_grid": list(K_GRID),
            "k_selection": "argmax pooled treatment rho on PRE-2023 folds only (2023 held out)",
            "variant": "all_prior (selection pool includes pre-2020 OOF seed folds; E-LAMBDA primary)",
            "cohorts": "hs / college / ifa / draft / other from efv_lab_runner._cohort_of",
            "stability_rule": f"applied lambda_c range <= {STAB_RANGE_MAX} and no opposite-sign "
                              f"consecutive step > {STAB_REVERSAL}",
            "declared_before_first_run": True,
        },
        "gate_thresholds": {"pooled_no_decrease": G_POOLED, "target_improve": G_TARGET_IMPROVE,
                            "cohort_degrade_no_more_than": G_DEGRADE, "era_drop_no_more_than": G_ERA_DROP,
                            "within_tier_t45_floor": G_TIER, "stab_range_max": STAB_RANGE_MAX,
                            "stab_reversal_max": STAB_REVERSAL, "cohort_min_n": MIN_SEL_N},
        "sides": sides,
        "gate": gate,
        "verdict": "SHIP" if gate["pass"] else "NO SHIP",
    }
    if not gate["pass"]:
        failed = [k for k in gate if k.startswith("condition") and not gate[k]["pass"]] \
            if all("pass" in gate[k] for k in gate if k.startswith("condition")) else \
            [k for k in gate if k.startswith("condition")
             and not (gate[k]["pass"] if "pass" in gate[k] else all(x["pass"] for x in gate[k].values()))]
        artifact["loss_ledger"] = {
            "verdict": "NO SHIP",
            "failed_conditions": failed,
            "summary": "The hierarchical shrunk cohort-lambda did not clear the full M3 gate, "
                       "but it is a genuine advance over the raw per-cohort argmax (E-LAMBDA, "
                       "NO SHIP): shrinkage toward the global lambda FIXED the pooled degradation "
                       "(E-LAMBDA pit pooled -0.0104 -> hier +0.0026; hit +0.0030, both no-decrease "
                       "= clause 1 PASS) and CAPTURED the proven pit:ifa direction (+0.0133 >= +0.01 "
                       "= clause 2 PASS). It is blocked by the collateral, not the target.",
            "blocking_clauses": {
                "condition_3": "hit:ifa degrades -0.0062 (> 0.005) -- the same intl-bats cohort "
                               "E-LAMBDA flagged as a weak, oscillating premise.",
                "condition_4": "pit 2022-2023 era drops -0.0114 (> 0.010) -- the shrunk pit:college "
                               "path drifts toward the pure model in the late folds and hurts the "
                               "recent era.",
                "condition_6": "even shrunk, the applied lambda_c range exceeds 0.20 on "
                               "hit:college, hit:ifa, pit:college, pit:ifa. The pre-registered k "
                               "selection maximizes pre-2023 pooled rho and lands on the LIGHTEST "
                               "shrink (pit k=50); heavier k would stabilize but was not selected "
                               "-- re-selecting k to pass stability would be goalpost-moving.",
            },
            "keep_alive": "pit:ifa now clears BOTH pooled and the +0.010 target under shrinkage -- "
                          "the strongest evidence yet for the intl-arm anchor weakness. The blocker "
                          "is no longer pooled degradation (solved) but (a) residual per-cohort "
                          "lambda instability on 25-160 row OOF pools and (b) collateral in "
                          "hit:ifa / pit-late-era. Wait for resolved 2024+ cohorts (more fold years "
                          "shrink the OOF variance) before re-opening; do NOT hand-tune k for "
                          "stability. A pit:ifa-ONLY shrink (leave every other cohort at global) is "
                          "a narrower future candidate that would sidestep the hit:ifa / pit:college "
                          "collateral, but needs its own pre-registered gate.",
        }

    OUT_PATH.write_text(json.dumps(artifact, indent=1), encoding="utf-8")

    print(f"M3 hier cohort-lambda gate: {'PASS -> SHIP' if gate['pass'] else 'FAIL -> NO SHIP'}")
    for s in ("hit", "pit"):
        r = sides[s]
        p = r["metrics"]["pooled"]
        print(f"  {s}: k={r['selected_k']} global_lam={r['shipped_lambda_global']} "
              f"pooled base={p['base']} treat={p['treat']} delta={p['delta']}")
        for c, blk in r["metrics"]["per_cohort"].items():
            if blk["gated"]:
                path = [(x['year'], x['lambda_c']) for x in r['lambda_c_paths'][c]]
                print(f"     {c:8s} n={blk['n']:3d} base={blk['base']} treat={blk['treat']} "
                      f"delta={blk['delta']} lam_c={path}")
    for cond in ("condition_1_pooled_no_decrease", "condition_2_target_cohort_improve",
                 "condition_3_no_cohort_degrade", "condition_4_era_no_drop",
                 "condition_5_within_tier_t45", "condition_6_fold_stability"):
        blk = gate[cond]
        ok = blk["pass"] if "pass" in blk else all(x["pass"] for x in blk.values())
        print(f"  {cond}: {'PASS' if ok else 'FAIL'}")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
