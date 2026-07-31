# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE recalibrate -- driver. Forward-chained validation + paired TRAIN/TEST
bootstrap with a REFIT on every draw.

python tools/_dpw_RECAL_run.py <pool> <dpw> <anchors> [target] [mode] [n_boot]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _dpw_RECAL_fit import SCRATCH, SHIPPED, apply_map, fit_floored_linear   # noqa: E402
from _dpw_RECAL_validate import ARMS, fit_lad, pooled, run                    # noqa: E402


def paired_bootstrap(res, n_boot=1000, seed=20260725):
    """Per draw: resample the TRAIN block (REFIT both maps), resample the TEST
    block, score every arm on the SAME resampled test rows (paired). Forward-
    chained structure preserved -- each fold resampled inside its own blocks."""
    d = res["d"]
    rng = np.random.default_rng(seed)
    keys = ["ols_slope", "ols_intercept", "lad_slope", "lad_intercept"]
    acc = {k: [] for k in keys}
    for a in ("refit_ols", "refit_lad", "shipped", "identity"):
        acc[f"mae_{a}"] = []; acc[f"rmse_{a}"] = []; acc[f"bias_{a}"] = []
    folds = [(f["idx_tr"], f["idx_te"]) for f in res["folds"]]
    for _ in range(n_boot):
        n_all = 0
        sums = {a: {"ae": 0.0, "se": 0.0, "e": 0.0}
                for a in ("refit_ols", "refit_lad", "shipped", "identity")}
        w = 0.0
        cw = {k: 0.0 for k in keys}
        for idx_tr, idx_te in folds:
            jt = idx_tr[rng.integers(0, len(idx_tr), len(idx_tr))]
            ols = fit_floored_linear(d["pred"][jt], d["real"][jt])
            lad = fit_lad(d["pred"][jt], d["real"][jt], start=ols)
            je = idx_te[rng.integers(0, len(idx_te), len(idx_te))]
            r = d["real"][je]; p = d["pred"][je]
            for a, coef in (("refit_ols", ols), ("refit_lad", lad),
                            ("shipped", SHIPPED), ("identity", (1.0, 0.0))):
                e = r - apply_map(coef, p)
                sums[a]["ae"] += np.abs(e).sum()
                sums[a]["se"] += (e ** 2).sum()
                sums[a]["e"] += e.sum()
            n_all += len(je)
            cw["ols_slope"] += ols[0] * len(idx_tr); cw["ols_intercept"] += ols[1] * len(idx_tr)
            cw["lad_slope"] += lad[0] * len(idx_tr); cw["lad_intercept"] += lad[1] * len(idx_tr)
            w += len(idx_tr)
        for k in keys:
            acc[k].append(cw[k] / w)
        for a in sums:
            acc[f"mae_{a}"].append(sums[a]["ae"] / n_all)
            acc[f"rmse_{a}"].append(np.sqrt(sums[a]["se"] / n_all))
            acc[f"bias_{a}"].append(sums[a]["e"] / n_all)
    return {k: np.array(v) for k, v in acc.items()}


def ci(a, lo=2.5, hi=97.5):
    return float(np.percentile(a, lo)), float(np.percentile(a, hi))


if __name__ == "__main__":
    pool = sys.argv[1] if len(sys.argv) > 1 else "2012_2019"
    dpw = sys.argv[2] if len(sys.argv) > 2 else "current"
    anch = sys.argv[3] if len(sys.argv) > 3 else "shipped"
    target = sys.argv[4] if len(sys.argv) > 4 else "today"
    mode = sys.argv[5] if len(sys.argv) > 5 else "expanding"
    nb = int(sys.argv[6]) if len(sys.argv) > 6 else 1000
    res = run(pool, dpw, anch, target=target, mode=mode)
    print(f"== regime {res['regime']} ==")
    print("   ", {k: v for k, v in res["info"].items() if k not in ("anchors", "reanchor")})
    print("    anchors", res["info"]["anchors"])
    d = res["d"]
    print(f"    pool n={len(d['pred'])}  years {res['years']}")
    for y in res["years"]:
        s = d["year"] == y
        print(f"      {y}: n={int(s.sum()):5d}  fv {d['fv'][s].mean():.2f}  "
              f"pred {d['pred'][s].mean():7.3f}M  real {d['real'][s].mean():7.3f}M  "
              f"zero-real {float((d['real'][s]==0).mean()):.3f}")

    print(f"\n== forward-chained folds ({mode}) ==")
    print(f"{'test':>5s} {'n_tr':>6s} {'n_te':>5s} | {'OLS a':>7s} {'OLS b':>7s} "
          f"{'LAD a':>7s} {'LAD b':>7s} | " +
          " ".join(f"{'MAE_'+a[:9]:>13s}" for a in ARMS))
    for f in res["folds"]:
        a = f["arms"]
        print(f"{f['test_year']:5d} {f['n_train']:6d} {f['n_test']:5d} | "
              f"{f['ols'][0]:7.4f} {f['ols'][1]:7.3f} {f['lad'][0]:7.4f} {f['lad'][1]:7.3f} | " +
              " ".join(f"{a[k]['mae']:13.3f}" for k in ARMS))

    P = pooled(res)
    print("\n== pooled held-out ==")
    print(f"  {'arm':10s} {'n':>5s} {'MAE':>8s} {'RMSE':>8s} {'bias':>8s} {'slope':>7s} "
          f"{'intcpt':>8s} {'r2':>6s} {'spear':>6s} {'cov':>6s} {'floor0':>7s} {'aggPred$M':>10s}")
    for arm in ARMS:
        m = P[arm]["metrics"]
        print(f"  {arm:10s} {m['n']:5d} {m['mae']:8.3f} {m['rmse']:8.3f} {m['bias']:+8.3f} "
              f"{m['slope']:7.4f} {m['intercept']:+8.3f} {m['r2']:6.4f} {m['spearman']:6.4f} "
              f"{P[arm].get('coverage_marginal', float('nan')):6.3f} "
              f"{P[arm]['floored_frac']:7.3f} {P[arm]['aggregate_pred_musd']:10.0f}")
    print(f"  {'REALIZED':10s} {'':5s} {'':8s} {'':8s} {'':8s} {'':7s} {'':8s} {'':6s} "
          f"{'':6s} {'':6s} {'':7s} {P['shipped']['aggregate_real_musd']:10.0f}")

    print("\n== conditional coverage ==")
    for arm in ("refit_ols", "refit_lad", "shipped", "identity"):
        print(f"  {arm}: marginal {P[arm]['coverage_marginal']:.3f}")
        print("     tier   ", {k: (v["n"], round(v["cov"], 3))
                               for k, v in P[arm]["coverage_by_tier"].items()})
        print("     role   ", {k: (v["n"], round(v["cov"], 3))
                               for k, v in P[arm]["coverage_by_role"].items()})
        print("     outcome", {k: (v["n"], round(v["cov"], 3))
                               for k, v in P[arm]["coverage_by_outcome"].items()})

    print("\n== reliability by FV tier (pooled held-out) ==")
    for arm in ("refit_ols", "refit_lad", "shipped"):
        print(f"  {arm}")
        for k, v in P[arm]["reliability_by_tier"].items():
            print(f"     {k:8s} n={v['n']:5d} corrected {v['pred_mean']:8.3f}M  "
                  f"realized {v['real_mean']:8.3f}M  ratio {v['pred_mean']/max(v['real_mean'],1e-9):5.3f}  "
                  f"MAE {v['mae']:8.3f}M")

    B = paired_bootstrap(res, n_boot=nb)
    print(f"\n== paired bootstrap ({nb} draws, REFIT per draw, train+test resampled) ==")
    for k in ("ols_slope", "ols_intercept", "lad_slope", "lad_intercept"):
        lo, hi = ci(B[k])
        print(f"  {k:16s} mean {B[k].mean():9.4f}  95% [{lo:9.4f}, {hi:9.4f}]")
    for a in ("refit_ols", "refit_lad", "shipped", "identity"):
        print(f"  {a:10s} MAE {B['mae_'+a].mean():8.3f} {ci(B['mae_'+a])}  "
              f"RMSE {B['rmse_'+a].mean():8.3f} {ci(B['rmse_'+a])}  "
              f"bias {B['bias_'+a].mean():+8.3f} {ci(B['bias_'+a])}")
    print("\n  paired deltas vs shipped (negative = the refit is better):")
    for a in ("refit_ols", "refit_lad", "identity"):
        for met in ("mae", "rmse"):
            dd = B[f"{met}_{a}"] - B[f"{met}_shipped"]
            print(f"    d_{met}({a} - shipped) mean {dd.mean():+8.4f} 95% {ci(dd)}  "
                  f"P(better) {float((dd<0).mean()):.4f}")
        dd = np.abs(B[f"bias_{a}"]) - np.abs(B["bias_shipped"])
        print(f"    d_|bias|({a} - shipped) mean {dd.mean():+8.4f} 95% {ci(dd)}  "
              f"P(better) {float((dd<0).mean()):.4f}")

    pm = np.concatenate([f["perm"]["mae"] for f in res["folds"]])
    pr = np.concatenate([f["perm"]["rmse"] for f in res["folds"]])
    pb = np.concatenate([f["perm"]["bias"] for f in res["folds"]])
    print(f"\n  permutation null (TRAIN labels shuffled, refit per draw, held-out):")
    print(f"    MAE  mean {pm.mean():.3f}  p05 {np.percentile(pm,5):.3f}  p95 {np.percentile(pm,95):.3f}")
    print(f"    RMSE mean {pr.mean():.3f}  p05 {np.percentile(pr,5):.3f}  p95 {np.percentile(pr,95):.3f}")
    print(f"    bias mean {pb.mean():+.3f} p05 {np.percentile(pb,5):+.3f} p95 {np.percentile(pb,95):+.3f}")

    out = {"regime": res["regime"],
           "info": {k: v for k, v in res["info"].items()},
           "folds": [{k: v for k, v in f.items()
                      if k not in ("arms", "idx_te", "idx_tr", "perm")}
                     for f in res["folds"]],
           "pooled": {a: {k: v for k, v in P[a].items()} for a in P},
           "bootstrap": {k: {"mean": float(B[k].mean()), "ci": ci(B[k])} for k in B},
           "perm_null": {"mae_mean": float(pm.mean()), "rmse_mean": float(pr.mean()),
                         "bias_mean": float(pb.mean())}}
    fn = SCRATCH / f"recal_val_{pool}_{dpw}_{anch}_{target}_{mode}.json"
    fn.write_text(json.dumps(out, indent=1, default=lambda o: None))
    print("\nwrote", fn)
