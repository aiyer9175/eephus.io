# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""LANE A1 -- blend-lambda RE-SELECT on the wave-B repaired matrices (2026-07-24b).

The 2026-07-14 lambda-band raise was RETRACTED on CORRUPTED labels; wave-B repaired
them, so the lambda selection is re-opened. This lab reconstructs the shipped
forward-chained OOS lambda-selection protocol INDEPENDENTLY (does not trust any
pre-existing lab/artifact/verdict) and sweeps the blend lambda per side over the full
[0.50, 1.00] range (including the pure-model 1.0 endpoint), well past the hardcoded
rank_calibration band [0.50, 0.70] that currently CAPS the hit lambda at its upper edge.

Protocol == efv_model.rank_calibration / efv_lab_runner (the canonical selector that
SETS the shipped lambda): debuted-only pool, forward-chained SCORED_YEARS (train
decision_year < Y, test == Y), fold gate len(te) >= 15 and len(tr) >= 60, RAW ridge leg
(_predict, no a/b calibration) blended with the consensus OLS anchor
cons = max(0, _pred_ols(ols, fv)). Reproduces the same-run baseline (hit pooled Spearman
0.3787 / pit 0.302) at the shipped lambdas (hit 0.70 / pit 0.61).

For each lambda: pooled OOS Spearman, contributor AUC (target >= 3.0 WAR) + star AUC
(target >= 10.0), per-era, per-tier. Ships the pooled-Spearman-maximizing lambda per side
with an AUC co-check (must not be worse at the chosen point). Player-clustered bootstrap
(seed 20260724, 2000 reps) on the chosen-vs-shipped pooled-Spearman delta -> lo95 > 0 bar.
Nested per-fold forward-chain selection (leakage-free) reported as an agreement co-check.
Also reports the CALIBRATED production-blend curve (a + b*model, -2.0 floor -- the leg
run_live actually ships) as a robustness co-check.

Run:  python tools/efv_lambda_reselect_lab.py            # full sweep + write artifact
      python tools/efv_lambda_reselect_lab.py --quick    # sweep only, no bootstrap
"""
from __future__ import annotations
import sys, json, math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)

import efv_model as XM
from prospect_path import _spearman, _fit_ridge, _predict
from efv_model import (_prep, _fit_ols_fv, _pred_ols, _feature_spec, blend_lambda,
                       _fit_linear_calibration, SCORED_YEARS)
from efv_dataset import matrix_path

SEED = 20260724
N_BOOT = 2000
CONTRIB_WAR = XM._CONTRIB_WAR   # 3.0
STAR_WAR = XM._STAR_WAR         # 10.0
SHIPPED = {"hit": None, "pit": None}   # filled from blend_lambda at runtime

# lambda grid: task-required {0.50,0.55,...,1.00} for the headline curve; a fine 0.01
# grid is also swept so the argmax is not quantized to the coarse step.
GRID_COARSE = [round(0.50 + 0.05 * i, 2) for i in range(11)]          # 0.50..1.00
GRID_FINE = [round(0.50 + 0.01 * i, 2) for i in range(51)]            # 0.50..1.00


def _tier(fv): return round(fv / 5) * 5
def _era(yr): return "<=2018" if yr <= 2018 else ("2019-2021" if yr <= 2021 else "2022-2023")


def _auc(scores, labels):
    """Mann-Whitney AUC with average ranks for ties. labels in {0,1}."""
    pos = [i for i, y in enumerate(labels) if y == 1]
    neg = [i for i, y in enumerate(labels) if y == 0]
    npos, nneg = len(pos), len(neg)
    if npos == 0 or nneg == 0:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0   # 1-based average rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    sum_pos = sum(ranks[i] for i in pos)
    return (sum_pos - npos * (npos + 1) / 2.0) / (npos * nneg)


def build_folds(side, calibrated=False):
    """Forward-chained fold predictions on the debuted-only pool. Returns a list of
    per-player dicts: {player_key, decision_year, cons, model, target, fv}. Fit ridge +
    consensus OLS ONCE per fold; the lambda sweep is then a cheap reweighting.

    calibrated=False -> RAW ridge leg (the canonical selector / same-run baseline).
    calibrated=True  -> a + b*ridge with -2.0 floor (the leg run_live actually ships)."""
    keys, _m = _feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    data = _prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)
    out = []
    for yr in SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = _fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        a, b = 0.0, 1.0
        if calibrated:
            cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
            if cal:
                a, b = cal["a"], cal["b"]
        for r in te:
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            mp = _predict(ridge, r["feats"])
            model = max(-2.0, a + b * mp) if calibrated else mp
            out.append({"player_key": r["player_key"], "decision_year": yr,
                        "cons": cons, "model": model, "target": r["target"], "fv": r["fv"]})
    return out


def metrics_at(folds, lam):
    """Full metric block for the blend at a fixed lambda."""
    scored = [((1 - lam) * f["cons"] + lam * f["model"], f["target"], f["fv"], f["decision_year"])
              for f in folds]
    s = [x[0] for x in scored]; t = [x[1] for x in scored]
    rho = _spearman(s, t)
    contrib_auc = _auc(s, [1 if x[1] >= CONTRIB_WAR else 0 for x in scored])
    star_auc = _auc(s, [1 if x[1] >= STAR_WAR else 0 for x in scored])
    # per-tier
    byt = defaultdict(list)
    for sc, tt, fv, _ in scored:
        byt[_tier(fv)].append((sc, tt))
    per_tier = {}
    wsum = wn = 0.0; t45 = None
    for tk, grp in byt.items():
        if len(grp) < 15:
            continue
        r = _spearman([a for a, _ in grp], [b for _, b in grp])
        if r is None:
            continue
        per_tier[tk] = {"n": len(grp), "rho": round(r, 4)}
        wsum += r * len(grp); wn += len(grp)
        if tk == 45:
            t45 = round(r, 4)
    # per-era
    bye = defaultdict(list)
    for sc, tt, fv, yr in scored:
        bye[_era(yr)].append((sc, tt))
    era = {}
    for k, g in bye.items():
        if len(g) >= 15:
            r = _spearman([a for a, _ in g], [b for _, b in g])
            if r is not None:
                era[k] = round(r, 4)
    return {"lam": lam, "n": len(scored),
            "spearman": round(rho, 4) if rho is not None else None,
            "contrib_auc": round(contrib_auc, 4) if contrib_auc is not None else None,
            "star_auc": round(star_auc, 4) if star_auc is not None else None,
            "within_tier_wm": round(wsum / wn, 4) if wn else None,
            "t45": t45, "per_tier": per_tier, "era": era}


def sweep(folds, grid):
    return [metrics_at(folds, lam) for lam in grid]


def _pooled_rho_at(folds, lam):
    s = [(1 - lam) * f["cons"] + lam * f["model"] for f in folds]
    t = [f["target"] for f in folds]
    return _spearman(s, t)


def bootstrap_delta(folds, lam_a, lam_b, n_pos_contrib):
    """Player-clustered bootstrap of the PAIRED delta (lam_a - lam_b) in pooled Spearman
    and contributor AUC. One row per player (forward-chain gives each player a single
    decision year), so player-clustered == row resampling with replacement."""
    import random
    rng = random.Random(SEED)
    n = len(folds)
    s_a = [(1 - lam_a) * f["cons"] + lam_a * f["model"] for f in folds]
    s_b = [(1 - lam_b) * f["cons"] + lam_b * f["model"] for f in folds]
    t = [f["target"] for f in folds]
    lab = [1 if x >= CONTRIB_WAR else 0 for x in t]
    d_rho, d_auc = [], []
    for _ in range(N_BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        sa = [s_a[i] for i in idx]; sb = [s_b[i] for i in idx]
        tt = [t[i] for i in idx]; ll = [lab[i] for i in idx]
        ra = _spearman(sa, tt); rb = _spearman(sb, tt)
        if ra is not None and rb is not None:
            d_rho.append(ra - rb)
        aa = _auc(sa, ll); ab = _auc(sb, ll)
        if aa is not None and ab is not None:
            d_auc.append(aa - ab)
    def _pct(xs, p):
        if not xs:
            return None
        ys = sorted(xs); k = (len(ys) - 1) * p
        lo = int(math.floor(k)); hi = int(math.ceil(k))
        if lo == hi:
            return ys[lo]
        return ys[lo] + (ys[hi] - ys[lo]) * (k - lo)
    return {
        "d_rho_mean": round(sum(d_rho) / len(d_rho), 5) if d_rho else None,
        "d_rho_lo95_2sided": round(_pct(d_rho, 0.025), 5) if d_rho else None,
        "d_rho_lo95_1sided": round(_pct(d_rho, 0.05), 5) if d_rho else None,
        "d_rho_hi95": round(_pct(d_rho, 0.975), 5) if d_rho else None,
        "d_rho_p_gt0": round(sum(1 for x in d_rho if x > 0) / len(d_rho), 4) if d_rho else None,
        "d_auc_mean": round(sum(d_auc) / len(d_auc), 5) if d_auc else None,
        "d_auc_lo95_2sided": round(_pct(d_auc, 0.025), 5) if d_auc else None,
        "d_auc_lo95_1sided": round(_pct(d_auc, 0.05), 5) if d_auc else None,
        "d_auc_hi95": round(_pct(d_auc, 0.975), 5) if d_auc else None,
        "n_reps": len(d_rho),
    }


def nested_fwdchain(folds, cand):
    """Leakage-free nested selection: for each test year Y pick the lambda that maximizes
    pooled Spearman on decision_year < Y, apply to Y, pool. Agreement co-check on whether
    a per-fold selector lands near the pooled argmax."""
    by_year = defaultdict(list)
    for f in folds:
        by_year[f["decision_year"]].append(f)
    yrs = sorted(by_year)

    def rho_on(years, lam):
        s, t = [], []
        for y in years:
            for f in by_year[y]:
                s.append((1 - lam) * f["cons"] + lam * f["model"]); t.append(f["target"])
        return _spearman(s, t) if len(s) >= 8 else None

    chosen, pooled_s, pooled_t = {}, [], []
    for y in yrs:
        prior = [yy for yy in yrs if yy < y]
        if not prior:
            lam = _CUR_SHIPPED   # first scored cohort: fall back to shipped lambda
        else:
            lam = max(cand, key=lambda L: (rho_on(prior, L) or -9))
        chosen[y] = lam
        for f in by_year[y]:
            pooled_s.append((1 - lam) * f["cons"] + lam * f["model"]); pooled_t.append(f["target"])
    rho = _spearman(pooled_s, pooled_t)
    return {"fwdchain_rho": round(rho, 4) if rho is not None else None,
            "per_year_lambda": {int(k): v for k, v in chosen.items()}, "n": len(pooled_s)}


_CUR_SHIPPED = 0.70


def run_side(side, do_boot=True):
    global _CUR_SHIPPED
    shipped = round(blend_lambda(side), 4)
    SHIPPED[side] = shipped
    _CUR_SHIPPED = shipped
    folds = build_folds(side, calibrated=False)
    folds_cal = build_folds(side, calibrated=True)
    n_contrib = sum(1 for f in folds if f["target"] >= CONTRIB_WAR)
    n_star = sum(1 for f in folds if f["target"] >= STAR_WAR)

    curve_coarse = sweep(folds, GRID_COARSE)
    curve_fine = sweep(folds, GRID_FINE)
    curve_cal = sweep(folds_cal, GRID_COARSE)

    # shipped metrics (exact shipped lambda, may be off-grid e.g. 0.61)
    shipped_m = metrics_at(folds, shipped)

    # unconstrained argmax on pooled Spearman over the fine grid (reported)
    valid = [m for m in curve_fine if m["spearman"] is not None]
    argmax = max(valid, key=lambda m: m["spearman"])
    argmax_lam = argmax["lam"]
    argmax_m = metrics_at(folds, argmax_lam)
    argmax_boot = None
    if do_boot and abs(argmax_lam - shipped) > 1e-9:
        argmax_boot = bootstrap_delta(folds, argmax_lam, shipped, n_contrib)

    # SHIP selection = the pooled-Spearman-MAXIMIZING lambda whose player-clustered bootstrap
    # clears the bar vs shipped: one-sided-95 lower bound > 0 on BOTH pooled Spearman AND
    # contributor AUC (the AUC co-check "must not be worse"). Coarse grid ascending; keep the
    # highest-pooled lambda that clears. If none clears -> no move (keep shipped).
    ship_lam = shipped
    ship_boot = None
    ship_cands = []
    if do_boot:
        for m in sorted([c for c in curve_coarse if c["lam"] > shipped + 1e-9],
                        key=lambda c: c["spearman"] or -9):
            b = bootstrap_delta(folds, m["lam"], shipped, n_contrib)
            clears = (b["d_rho_lo95_1sided"] is not None and b["d_rho_lo95_1sided"] > 0
                      and b["d_auc_lo95_1sided"] is not None and b["d_auc_lo95_1sided"] > 0)
            ship_cands.append({"lam": m["lam"], "spearman": m["spearman"],
                               "d_rho_lo95_1sided": b["d_rho_lo95_1sided"],
                               "d_auc_lo95_1sided": b["d_auc_lo95_1sided"],
                               "d_rho_p_gt0": b["d_rho_p_gt0"], "clears": clears})
            if clears and (m["spearman"] or -9) >= (metrics_at(folds, ship_lam)["spearman"] or -9):
                ship_lam = m["lam"]; ship_boot = b
    ship_m = metrics_at(folds, ship_lam)

    nested = nested_fwdchain(folds, GRID_FINE)

    return {
        "side": side, "shipped_lambda": shipped,
        "n_pooled": len(folds), "n_contrib": n_contrib, "n_star": n_star,
        "shipped_metrics": shipped_m,
        "argmax_lambda": argmax_lam, "argmax_metrics": argmax_m, "argmax_bootstrap": argmax_boot,
        "ship_lambda": ship_lam, "ship_metrics": ship_m, "ship_bootstrap": ship_boot,
        "ship_moved": bool(abs(ship_lam - shipped) > 1e-9),
        "ship_candidates_ascending_pooled": ship_cands,
        "delta_spearman_ship": round((ship_m["spearman"] or 0) - (shipped_m["spearman"] or 0), 4),
        "delta_contrib_auc_ship": round((ship_m["contrib_auc"] or 0) - (shipped_m["contrib_auc"] or 0), 4),
        "delta_star_auc_ship": round((ship_m["star_auc"] or 0) - (shipped_m["star_auc"] or 0), 4),
        "nested_fwdchain": nested,
        "curve_coarse": curve_coarse,
        "curve_fine_spearman": {str(m["lam"]): m["spearman"] for m in curve_fine},
        "curve_fine_contrib_auc": {str(m["lam"]): m["contrib_auc"] for m in curve_fine},
        "curve_calibrated_coarse": curve_cal,
    }


if __name__ == "__main__":
    do_boot = "--quick" not in sys.argv
    out = {"seed": SEED, "n_boot": N_BOOT, "scored_years": list(SCORED_YEARS),
           "contrib_war": CONTRIB_WAR, "star_war": STAR_WAR,
           "protocol": "debuted-only forward-chained; raw ridge leg; canonical rank_calibration selector",
           "sides": {}}
    for side in ("hit", "pit"):
        r = run_side(side, do_boot=do_boot)
        out["sides"][side] = r
        print(f"\n===== {side} =====")
        print(f"shipped lambda={r['shipped_lambda']}  pooled rho={r['shipped_metrics']['spearman']}  "
              f"contribAUC={r['shipped_metrics']['contrib_auc']}  starAUC={r['shipped_metrics']['star_auc']}")
        print(f"unconstrained pooled-argmax lambda={r['argmax_lambda']}  rho={r['argmax_metrics']['spearman']}  "
              f"contribAUC={r['argmax_metrics']['contrib_auc']}")
        if r["argmax_bootstrap"]:
            b = r["argmax_bootstrap"]
            print(f"  argmax boot d_rho mean={b['d_rho_mean']} 1sided95lo={b['d_rho_lo95_1sided']} "
                  f"2sided95lo={b['d_rho_lo95_2sided']} P(>0)={b['d_rho_p_gt0']}  d_auc 1sided95lo={b['d_auc_lo95_1sided']}")
        print(f"SHIP lambda={r['ship_lambda']} (moved={r['ship_moved']})  rho={r['ship_metrics']['spearman']}  "
              f"contribAUC={r['ship_metrics']['contrib_auc']}  starAUC={r['ship_metrics']['star_auc']}")
        print(f"  SHIP delta rho={r['delta_spearman_ship']}  d_contribAUC={r['delta_contrib_auc_ship']}  d_starAUC={r['delta_star_auc_ship']}")
        if r["ship_bootstrap"]:
            b = r["ship_bootstrap"]
            print(f"  SHIP boot d_rho mean={b['d_rho_mean']} 1sided95lo={b['d_rho_lo95_1sided']} P(>0)={b['d_rho_p_gt0']}  "
                  f"d_auc mean={b['d_auc_mean']} 1sided95lo={b['d_auc_lo95_1sided']}")
        print("  ship candidates (asc pooled): " + ", ".join(
            f"{c['lam']}[rho_lo={c['d_rho_lo95_1sided']},auc_lo={c['d_auc_lo95_1sided']},clr={c['clears']}]"
            for c in r["ship_candidates_ascending_pooled"]))
        print(f"nested fwdchain rho={r['nested_fwdchain']['fwdchain_rho']} per-year={r['nested_fwdchain']['per_year_lambda']}")
        print("coarse curve (lam: rho / contribAUC):")
        for m in r["curve_coarse"]:
            print(f"  {m['lam']:.2f}: rho={m['spearman']}  cAUC={m['contrib_auc']}  sAUC={m['star_auc']}  wm={m['within_tier_wm']}  t45={m['t45']}")
    Path("data/xfv_lambda_reselect_eval.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\nwrote data/xfv_lambda_reselect_eval.json")
