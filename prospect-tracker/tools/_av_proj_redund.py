"""ADVERSARIAL check of the redundancy claims on the real training frame."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import fa_projection as fp  # noqa: E402
import proj_ml  # noqa: E402

corpus = fp.build_corpus()
frame = proj_ml.build_training_frame(corpus, 2003, 2025)
for side in ("hit", "pit"):
    names = proj_ml.feature_names(side)
    X = frame[side]["X"][np.unique(frame[side]["rows"][1])]
    print(f"\n=== {side} n={X.shape[0]} p={X.shape[1]} (names {len(names)}) ===")
    sd = X.std(axis=0)
    dead = [(names[i], float(sd[i])) for i in range(len(names)) if sd[i] < 1e-9]
    print("CONSTANT columns:", dead)
    # expo_trend identity
    if all(k in names for k in ("expo_trend", "expo_l1", "expo_l2")):
        t, a, b = (X[:, names.index(k)] for k in ("expo_trend", "expo_l1", "expo_l2"))
        print("max|expo_trend-(expo_l1-expo_l2)| =", float(np.abs(t - (a - b)).max()))
    # champ stack adjacent correlations
    ci = [names.index(f"champ_h{h}") for h in range(1, 6)]
    C = np.corrcoef(X[:, ci].T)
    print("champ adjacent |r|:", [round(float(C[i, i + 1]), 4) for i in range(4)])
    if side == "hit":
        for a, b in (("m_iso", "m_hr_pa"), ("rel_iso", "rel_hr_pa")):
            if a in names and b in names:
                print(f"r({a},{b}) =", round(float(np.corrcoef(
                    X[:, names.index(a)], X[:, names.index(b)])[0, 1]), 4))
