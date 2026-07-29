# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE recalibrate -- STEP 1: reproduce the shipped calibration before touching it.

If the lab cannot land on linearmap-v5's own coefficients from its own stated
recipe (raw-scale pool, resolved 2017-2019, today-priced targets, shipped
config), then nothing the lab says afterwards can be trusted. Prints the
reproduction plus the same fit on every other scale/anchor/level regime.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _dpw_RECAL_fit import (SCRATCH, SHIPPED, apply_map, fit_floored_linear,   # noqa: E402
                            metrics, prep, set_regime)
import json                                                                    # noqa: E402

POOL = pickle.loads((SCRATCH / "recal_pool_2017_2019.pkl").read_bytes())
ANCH = json.loads((SCRATCH / "recal_anchors.json").read_text())

if __name__ == "__main__":
    print("== STEP 1: reproduce linearmap-v5 (raw scale, resolved 2017-2019, today-priced) ==")
    info = set_regime("current", "shipped")
    print("   regime:", {k: v for k, v in info.items() if k != "anchors"})
    d = prep(POOL, scale="raw", gate="raw", target="today", draws=1)
    a, b = fit_floored_linear(d["pred"], d["real"])
    print(f"   n={len(d['pred'])}  fit  slope {a:.6f}  intercept {b:.6f}")
    print(f"   shipped                slope {SHIPPED[0]:.6f}  intercept {SHIPPED[1]:.6f}")
    print(f"   pred mean {d['pred'].mean():.4f}M  real mean {d['real'].mean():.4f}M")
    m = metrics(apply_map((a, b), d["pred"]), d["real"])
    print("   in-sample corrected:", {k: round(v, 4) for k, v in m.items()})

    print("\n== STEP 1b: the same fit under era-priced targets (the committed artifact's convention) ==")
    d2 = prep(POOL, scale="raw", gate="raw", target="era", draws=1)
    a2, b2 = fit_floored_linear(d2["pred"], d2["real"])
    print(f"   n={len(d2['pred'])}  slope {a2:.6f}  intercept {b2:.6f}  real mean {d2['real'].mean():.4f}M")

    print("\n== STEP 2: fits across the axes (today-priced, resolved, gate=raw) ==")
    rows = []
    for dpw in ("current", "recon_lvl", "recon_full"):
        for anch in ("shipped", "norm"):
            tbl = ANCH["norm"]["anchors"] if anch == "norm" else None
            inf = set_regime(dpw, anch, tbl)
            for scale in ("raw", "norm"):
                dd = prep(POOL, scale=scale, gate="raw", target="today", draws=1)
                aa, bb = fit_floored_linear(dd["pred"], dd["real"])
                rows.append({"dpw": dpw, "anchors": anch, "scale": scale,
                             "n": int(len(dd["pred"])), "slope": aa, "intercept": bb,
                             "pred_mean": float(dd["pred"].mean()),
                             "real_mean": float(dd["real"].mean()),
                             "corrected_mean": float(apply_map((aa, bb), dd["pred"]).mean()),
                             "flat": inf["flat_usd_per_war"]})
    hdr = f"{'dpw':11s} {'anch':8s} {'scale':5s} {'n':>5s} {'slope':>8s} {'intcpt':>9s} {'predM':>8s} {'realM':>8s} {'corrM':>8s}"
    print(hdr)
    for r in rows:
        print(f"{r['dpw']:11s} {r['anchors']:8s} {r['scale']:5s} {r['n']:5d} "
              f"{r['slope']:8.4f} {r['intercept']:9.4f} {r['pred_mean']:8.3f} "
              f"{r['real_mean']:8.3f} {r['corrected_mean']:8.3f}")
    (SCRATCH / "recal_repro.json").write_text(json.dumps(rows, indent=1))
    set_regime("current", "shipped")
