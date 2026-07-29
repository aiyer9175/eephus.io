"""AM-PROJ (d): redundancy audit of the proj_lgbm feature block.

Loads the ACTUAL training frame the shipped bundle was fit on and reports, per
side: pairwise |Pearson| >= 0.90, variance-inflation-style R2 of each feature on
all the others (ridge-regularised), and zero-variance / near-constant columns.
Measurement only; nothing is fitted or shipped.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fa_projection as fp  # noqa: E402
import proj_ml  # noqa: E402

corpus = fp.build_corpus()
frame = proj_ml.build_training_frame(corpus, 2003, 2024)

out = {}
for side in ("hit", "pit"):
    names = proj_ml.feature_names(side)
    X = frame[side]["X"]
    rows = frame[side]["rows"][1]
    X = X[rows]
    print(f"===== {side}: X {X.shape}, {len(names)} names =====")
    sd = X.std(axis=0)
    const = [names[i] for i in range(len(names)) if sd[i] < 1e-9]
    print("near-constant columns:", const)
    Z = (X - X.mean(axis=0)) / np.where(sd < 1e-9, 1.0, sd)
    C = np.corrcoef(Z, rowvar=False)
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if sd[i] < 1e-9 or sd[j] < 1e-9:
                continue
            if abs(C[i, j]) >= 0.90:
                pairs.append((round(float(C[i, j]), 4), names[i], names[j]))
    pairs.sort(key=lambda t: -abs(t[0]))
    print(f"pairs |r| >= 0.90: {len(pairs)}")
    for r, a, b in pairs:
        print(f"   r={r:+.4f}  {a:<16} {b}")
    # R2 of each column on all the others (ridge 1e-6), the multicollinearity read
    r2 = {}
    keep = [i for i in range(len(names)) if sd[i] >= 1e-9]
    for i in keep:
        others = [j for j in keep if j != i]
        A = Z[:, others]
        y = Z[:, i]
        G = A.T @ A + 1e-6 * np.eye(len(others))
        beta = np.linalg.solve(G, A.T @ y)
        resid = y - A @ beta
        r2[names[i]] = round(float(1.0 - resid.var() / y.var()), 4)
    top = sorted(r2.items(), key=lambda kv: -kv[1])[:14]
    print("highest R2-on-the-rest (1.0 = exactly reproducible from the others):")
    for k, v in top:
        vif = (1.0 / (1.0 - v)) if v < 0.999999 else float("inf")
        print(f"   {k:<16} R2={v:.4f}  VIF={vif:,.1f}")
    out[side] = {"n": int(X.shape[0]), "const": const,
                 "pairs_ge_090": pairs, "r2_on_rest": r2}

json.dump(out, open(ROOT / "tools" / "_am_proj_out_redund.json", "w"), indent=1)
print("saved")
