# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Scratch: (c) calibration of the comp-implied outcome + family-wide max PARTIAL rho.

Read-only. Companion to tools/_comb_comps.py.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("cc", ROOT / "tools" / "_comb_comps.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)


def preds_for(cache, cfg):
    out = []
    for yr, F in cache.items():
        Ztr, Zte, _ = F["per"][cfg["axis_set"]]
        w = cc.fit_weights(Ztr, F["ytr"], cfg["weighting"])
        g = cfg["gate"] == "G1_LEVEL_BAND"
        out.extend(cc.comp_predict(Ztr, F["ytr"], Zte, w, cfg["k"],
                                   F["lvl_tr"] if g else None,
                                   F["lvl_te"] if g else None).tolist())
    return np.array(out)


def main(side="hit"):
    pool = cc.load_pool(side, track_record=True)
    cache = cc.precompute(pool, side, cc.FOLD_YEARS)
    ship = cc.shipped_oof(cache, side)
    fam = cc.family()
    y, b = [], []
    for yr, F in cache.items():
        y.extend(F["yte"].tolist())
        b.extend(ship[yr]["blend"].tolist())
    y, b = np.array(y), np.array(b)

    # ---- family-wide max PARTIAL rho (the incremental-signal statistic) ----
    part = {}
    for c in fam:
        p = preds_for(cache, c)
        part[c["id"]] = cc.partial_spearman(p, y, b)
    best_id = max(part, key=lambda k: part[k])
    nullf = json.loads((cc.OUT / f"null_{side}.json").read_text(encoding="utf-8"))
    mpn = nullf["maxstat_partial_null"]
    print(f"== FAMILY-WIDE MAX PARTIAL RHO  side={side}")
    print(f"   best observed partial rho : {part[best_id]:+.4f}   ({best_id})")
    print(f"   permutation max-partial   : p95 {mpn['p95']:.4f}   max {mpn['max']:.4f}")
    print(f"   -> observed best {'CLEARS' if part[best_id] > mpn['p95'] else 'FAILS'} "
          f"the noise bar")

    # ---- (c) calibration of the shipped-product metrics ----
    out = {"side": side, "family_max_partial": {"id": best_id, "rho": part[best_id]},
            "maxstat_partial_null": mpn, "calibration": {}}
    for label, cfg in (("M_MODEL", cc.M_MODEL), ("M_ARCH", cc.M_ARCH)):
        p = preds_for(cache, cfg)
        q = np.quantile(p, np.linspace(0, 1, 6))
        q[0] -= 1e-9
        binid = np.clip(np.digitize(p, q[1:-1]), 0, 4)
        rows = []
        for i in range(5):
            m = binid == i
            if m.sum() < 5:
                continue
            rows.append({"quintile": i + 1, "n": int(m.sum()),
                         "mean_predicted": round(float(p[m].mean()), 2),
                         "mean_realized": round(float(y[m].mean()), 2),
                         "median_realized": round(float(np.median(y[m])), 2),
                         "bust_rate": round(float((y[m] < 0.5).mean()), 3)})
        num = float(((p - p.mean()) * (y - y.mean())).sum())
        den = float(((p - p.mean()) ** 2).sum())
        out["calibration"][label] = {
            "id": cfg["id"], "rho": cc.spearman(p, y),
            "partial_rho_given_blend": part[cfg["id"]],
            "regression_slope_realized_on_predicted": round(num / den, 3) if den else None,
            "mae": round(float(np.abs(p - y).mean()), 3),
            "quintiles": rows}
        print(f"\n   [{label}] {cfg['id']}")
        print(f"      rho {cc.spearman(p, y):+.4f}   partial rho | blend "
              f"{part[cfg['id']]:+.4f}   slope {num/den:.3f}   MAE "
              f"{float(np.abs(p-y).mean()):.2f}")
        print(f"      {'quintile':>8s} {'n':>5s} {'pred':>7s} {'realized':>9s} "
              f"{'median':>7s} {'bust':>6s}")
        for r in rows:
            print(f"      {r['quintile']:8d} {r['n']:5d} {r['mean_predicted']:7.2f} "
                  f"{r['mean_realized']:9.2f} {r['median_realized']:7.2f} "
                  f"{r['bust_rate']:6.1%}")
    (cc.OUT / f"calib_{side}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "hit")
