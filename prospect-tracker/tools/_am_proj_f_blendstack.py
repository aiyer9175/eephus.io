"""AM-PROJ (d/coherence): the two stacked mean-recenter stages in
proj_ml.predict_path.

Stage 1 (GLOBAL mean_blend, lift-only) moves by_q[0.50][t] toward the
quantile-implied mean M1. Stage 2 (STAR star_blend) then RECOMPUTES the implied
mean from by_q[0.10..0.90] -- but q50 has already moved, and _implied_mean gives
q50 weight 2/8, so stage 2's target is M2 = M1 + 0.25*(q50' - q50), not M1.
Stage 2 is also NOT lift-guarded while stage 1 is.

This measures, on the LIVE bundle over real feature vectors:
  * how far the shipped q50 lands past the intended implied mean
  * how many star rows stage 2 pulls DOWN (contradicting stage 1's stated
    lift-only intent)
Measurement only.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fa_projection as fp  # noqa: E402
import proj_ml  # noqa: E402

models = proj_ml.load()
meta = models["meta"]
gblend = meta.get("mean_blend") or {}
sblend = meta.get("star_blend") or {}
print("mean_blend", gblend, "\nstar_blend", sblend)

corpus = fp.build_corpus()
frame = proj_ml.build_training_frame(corpus, 2003, 2025)
QS = tuple(meta.get("quantiles") or proj_ml.QUANTILES)
IM = proj_ml._implied_mean

rep = {}
for side in ("hit", "pit"):
    X = frame[side]["X"][frame[side]["rows"][1]]
    star_mask = X[:, proj_ml._STAR_FLAG_IDX] >= 1.0
    idx = np.where(star_mask)[0]
    rng = np.random.default_rng(11)
    if len(idx) > 1200:
        idx = rng.choice(idx, 1200, replace=False)
    rows = []
    for i in idx:
        x = X[i].reshape(1, -1)
        q = {}
        ok = True
        for h in range(1, proj_ml.HORIZONS + 1):
            heads = models[side].get(h)
            if not heads or not all(qq in heads for qq in QS):
                ok = False
                break
            q[h] = sorted(proj_ml._predict1(heads[qq], x) for qq in QS)
        if not ok:
            continue
        for h in range(1, proj_ml.HORIZONS + 1):
            q10, q25, q50, q75, q90 = q[h]
            lg = float(gblend.get(str(h)) or 0.0)
            ls = float(sblend.get(str(h)) or 0.0)
            if lg <= 0 and ls <= 0:
                continue
            M1 = IM(q10, q25, q50, q75, q90)
            # SHIPPED sequencing
            v = q50
            if lg > 0:
                s = lg * (M1 - v)
                if s > 0:
                    v = v + s
            after_global = v
            if ls > 0:
                M2 = IM(q10, q25, v, q75, q90)
                v = v + ls * (M2 - v)
            shipped = v
            # INTENDED sequencing: both stages target the SAME M1, stage 2
            # lift-guarded like stage 1
            w = q50
            if lg > 0:
                s = lg * (M1 - w)
                if s > 0:
                    w = w + s
            if ls > 0:
                s = ls * (M1 - w)
                if s > 0:
                    w = w + s
            rows.append({"h": h, "q50": q50, "M1": M1, "shipped": shipped,
                         "intended": w, "after_global": after_global,
                         "pulled_down": 1 if shipped < after_global else 0})
    if not rows:
        continue
    rep[side] = {}
    for h in sorted({r["h"] for r in rows}):
        R = [r for r in rows if r["h"] == h]
        d = np.array([r["shipped"] - r["intended"] for r in R])
        past = np.array([r["shipped"] - r["M1"] for r in R])
        down = sum(r["pulled_down"] for r in R)
        rep[side][h] = {
            "n_star": len(R), "mean_shipped_minus_intended": round(float(d.mean()), 5),
            "max_abs": round(float(np.abs(d).max()), 5),
            "mean_shipped_minus_M1": round(float(past.mean()), 5),
            "frac_stage2_pulls_down": round(down / len(R), 4),
            "mean_q50": round(float(np.mean([r["q50"] for r in R])), 4),
            "mean_shipped": round(float(np.mean([r["shipped"] for r in R])), 4),
        }
        print(f"{side} h{h}: " + json.dumps(rep[side][h]))

json.dump(rep, open(ROOT / "tools" / "_am_proj_out_blendstack.json", "w"), indent=1)
print("saved")
