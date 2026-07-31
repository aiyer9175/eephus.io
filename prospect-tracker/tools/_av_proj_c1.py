"""ADVERSARIAL re-derivation of the C1 stacked-recenter claim.

Written from scratch against proj_ml's own arithmetic; does NOT import or read
the audited harness. Measures, on the LIVE bundle over real training-frame
feature vectors, what stage 2 (star_blend) does on top of stage 1 (mean_blend).
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fa_projection as fp  # noqa: E402
import proj_ml as pm  # noqa: E402

M = pm.load()
meta = M["meta"]
G = meta.get("mean_blend") or {}
S = meta.get("star_blend") or {}
QS = tuple(meta.get("quantiles") or pm.QUANTILES)
im = pm._implied_mean

corpus = fp.build_corpus()
frame = pm.build_training_frame(corpus, 2003, 2025)

rep = {"mean_blend": G, "star_blend": S, "sides": {}}
for side in ("hit", "pit"):
    X = frame[side]["X"]
    rows = np.unique(frame[side]["rows"][1])
    Xs = X[rows]
    star = Xs[:, pm._STAR_FLAG_IDX] >= 1.0
    Xstar = Xs[star]
    per_h = {}
    for h in range(1, pm.HORIZONS + 1):
        lam_g = float(G.get(str(h)) or 0.0)
        lam_s = float(S.get(str(h)) or 0.0)
        heads = M[side].get(h)
        d_ship, d_int, down_after_refuse, down_vs_stage1 = [], [], 0, 0
        n = 0
        for i in range(Xstar.shape[0]):
            x = Xstar[i].reshape(1, -1)
            q = sorted(pm._predict1(heads[qq], x) for qq in QS)
            q10, q25, q50, q75, q90 = q
            M1 = im(q10, q25, q50, q75, q90)
            # stage 1: lift-only
            s1 = lam_g * (M1 - q50)
            q50p = q50 + s1 if s1 > 0 else q50
            # stage 2 SHIPPED: recompute implied mean from the MOVED q50, no guard
            M2 = im(q10, q25, q50p, q75, q90)
            ship = q50p + lam_s * (M2 - q50p) if lam_s > 0 else q50p
            # stage 2 INTENDED: target M1 (pre-recenter q50), lift-only
            s2 = lam_s * (M1 - q50p) if lam_s > 0 else 0.0
            intend = q50p + s2 if s2 > 0 else q50p
            d_ship.append(ship)
            d_int.append(intend)
            if lam_s > 0:
                if ship < q50p - 1e-12:
                    down_vs_stage1 += 1
                    if s1 <= 0:
                        down_after_refuse += 1
            n += 1
        a, b = np.array(d_ship), np.array(d_int)
        per_h[h] = {
            "lam_mean": lam_g, "lam_star": lam_s, "n_star": n,
            "mean_ship_minus_intended": float(np.mean(a - b)),
            "max_abs_diff": float(np.max(np.abs(a - b))),
            "pct_stage2_pulls_down": 100.0 * down_vs_stage1 / max(n, 1),
            "pct_down_after_stage1_refused": 100.0 * down_after_refuse / max(n, 1),
        }
    rep["sides"][side] = per_h
    print(side, json.dumps(per_h, indent=1))

out = ROOT / "tools" / "_av_proj_out_c1.json"
out.write_text(json.dumps(rep, indent=1))
print("wrote", out)
