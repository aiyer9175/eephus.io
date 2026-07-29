# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE recalibrate -- STEP 2: the headline coefficients + CIs, per regime.

Fit on the REGISTERED fit window (resolved 2017-2019, gate on raw so pool
membership is held fixed at the registered n=2,236) so the new coefficients are
directly comparable to linearmap-v5. Player-clustered bootstrap REFITS the map on
every draw. Also reports what each map does to the pool's aggregate dollars, and
a permutation null on the coefficient itself.
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _dpw_RECAL_fit import (SCRATCH, SHIPPED, apply_map, fit_floored_linear,   # noqa: E402
                            metrics, prep, set_regime)

N_BOOT = 2000
SEED = 20260725


def ci(a, lo=2.5, hi=97.5):
    return round(float(np.percentile(a, lo)), 4), round(float(np.percentile(a, hi)), 4)


def one(pool, dpw, anchors, anch_tbl, scale, gate="raw", target="today"):
    info = set_regime(dpw, anchors, anch_tbl)
    d = prep(pool, scale=scale, gate=gate, target=target, draws=1)
    a, b = fit_floored_linear(d["pred"], d["real"])
    rng = np.random.default_rng(SEED)
    n = len(d["pred"])
    bs_a, bs_b, bs_agg = [], [], []
    for _ in range(N_BOOT):
        j = rng.integers(0, n, n)
        c = fit_floored_linear(d["pred"][j], d["real"][j])
        bs_a.append(c[0]); bs_b.append(c[1])
        bs_agg.append(float(apply_map(c, d["pred"]).sum()))
    perm_a = []
    for _ in range(400):
        c = fit_floored_linear(d["pred"], rng.permutation(d["real"]))
        perm_a.append(c[0])
    new_agg = float(apply_map((a, b), d["pred"]).sum())
    ship_agg = float(apply_map(SHIPPED, d["pred"]).sum())
    return {
        "dpw": dpw, "anchors": anchors, "scale": scale, "n": int(n),
        "flat_usd_per_war": info["flat_usd_per_war"],
        "slope": round(a, 6), "intercept": round(b, 6),
        "slope_ci": ci(np.array(bs_a)), "intercept_ci": ci(np.array(bs_b)),
        "pred_mean": round(float(d["pred"].mean()), 4),
        "real_mean": round(float(d["real"].mean()), 4),
        "agg_new_musd": round(new_agg, 1), "agg_shipped_musd": round(ship_agg, 1),
        "agg_real_musd": round(float(d["real"].sum()), 1),
        "agg_new_ci": ci(np.array(bs_agg)),
        "shipped_vs_real_pct": round(100 * (ship_agg / float(d["real"].sum()) - 1), 2),
        "new_vs_real_pct": round(100 * (new_agg / float(d["real"].sum()) - 1), 2),
        "perm_slope_mean": round(float(np.mean(perm_a)), 4),
        "perm_slope_p95abs": round(float(np.percentile(np.abs(perm_a), 95)), 4),
        "insample_shipped": {k: round(v, 4) for k, v in
                             metrics(apply_map(SHIPPED, d["pred"]), d["real"]).items()},
        "insample_new": {k: round(v, 4) for k, v in
                         metrics(apply_map((a, b), d["pred"]), d["real"]).items()},
    }


if __name__ == "__main__":
    pool = pickle.loads((SCRATCH / "recal_pool_2017_2019.pkl").read_bytes())
    anch_tbl = json.loads((SCRATCH / "recal_anchors.json").read_text())["norm"]["anchors"]
    rows = []
    for dpw in ("current", "recon_lvl", "recon_full"):
        for anchors in ("shipped", "norm"):
            for scale in ("norm", "raw"):
                rows.append(one(pool, dpw, anchors, anch_tbl, scale))
    set_regime("current", "shipped")
    print(f"{'dpw':10s} {'anch':8s} {'scale':5s} {'n':>5s} {'slope':>8s} "
          f"{'slope 95% CI':>20s} {'intcpt':>8s} {'intcpt 95% CI':>20s} "
          f"{'predM':>7s} {'realM':>7s} {'ship/real':>10s} {'new/real':>9s}")
    for r in rows:
        print(f"{r['dpw']:10s} {r['anchors']:8s} {r['scale']:5s} {r['n']:5d} "
              f"{r['slope']:8.4f} [{r['slope_ci'][0]:8.4f},{r['slope_ci'][1]:8.4f}] "
              f"{r['intercept']:8.4f} [{r['intercept_ci'][0]:8.4f},{r['intercept_ci'][1]:8.4f}] "
              f"{r['pred_mean']:7.3f} {r['real_mean']:7.3f} "
              f"{r['shipped_vs_real_pct']:9.2f}% {r['new_vs_real_pct']:8.2f}%")
    print("\npermutation null on the fitted slope (labels shuffled, refit per draw):")
    for r in rows[:2]:
        print(f"  {r['dpw']}/{r['anchors']}/{r['scale']}: mean {r['perm_slope_mean']:+.4f} "
              f"p95|a| {r['perm_slope_p95abs']:.4f}   (observed {r['slope']:.4f})")
    print("\nin-sample, production stack (dpw=current, anchors=shipped, scale=norm):")
    r = [x for x in rows if x["dpw"] == "current" and x["anchors"] == "shipped"
         and x["scale"] == "norm"][0]
    print("  shipped map:", r["insample_shipped"])
    print("  new map    :", r["insample_new"])
    print(f"  aggregate: shipped ${r['agg_shipped_musd']:,.0f}M  new ${r['agg_new_musd']:,.0f}M "
          f"realized ${r['agg_real_musd']:,.0f}M")
    (SCRATCH / "recal_coef.json").write_text(json.dumps(rows, indent=1))
    print("\nwrote", SCRATCH / "recal_coef.json")
