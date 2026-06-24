# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
comps.py — Similar hitters by SWING PATH, using the SVM RBF (Gaussian) kernel as
the similarity metric.

Why RBF kernel: "find similar players" is a distance problem. The RBF kernel
    sim(i,j) = exp(-gamma * ||x_i - x_j||^2)
is exactly a smooth Gaussian similarity on standardized features — the same kernel
an SVM uses. vs plain KNN it (a) requires standardized features (which we do),
(b) gives a calibrated 0-1 similarity that decays smoothly, and (c) is robust to
the choice of "k". We rank neighbors by this similarity.

Features = the swing-path profile (the 9 bat-tracking means/sds). Built on the
career all-time board (one vector per batter+stand). Returns top-N comps with a
0-100 similarity score.
"""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.preprocessing import StandardScaler

PROC = Path(__file__).parent / "data" / "processed"

# swing-path features for similarity (the bat-tracking profile)
FEATS = [
    "bat_speed_mean", "swing_length_mean", "attack_angle_mean",
    "attack_direction_mean", "swing_path_tilt_mean",
    "intercept_ball_minus_batter_pos_x_inches_mean",
    "intercept_ball_minus_batter_pos_y_inches_mean",
    "bat_speed_std", "attack_angle_std",
]
# SHAPE-ONLY: drop bat-speed magnitude/variability so comps match swing GEOMETRY,
# not how hard the player swings (a soft and a hard swinger can share a shape).
SHAPE_FEATS = [f for f in FEATS if not f.startswith("bat_speed")]


def build_index(min_pa=200, shape_only=False):
    feats = SHAPE_FEATS if shape_only else FEATS
    at = pd.read_parquet(PROC / "leaderboard_alltime.parquet")
    df = at.dropna(subset=feats).copy()
    if "n_pa" in df.columns:
        df = df[df["n_pa"].fillna(0) >= min_pa]
    df = df.reset_index(drop=True)
    X = StandardScaler().fit_transform(df[feats].values)
    # gamma = 1/n_features (sklearn 'scale'-ish default on standardized data)
    gamma = 1.0 / X.shape[1]
    return df, X, gamma


def comps_for(batter, stand=None, n=10, min_pa=200, shape_only=False):
    df, X, gamma = build_index(min_pa, shape_only)
    mask = df["batter"] == batter
    if stand and "stand" in df.columns and (df["stand"] == stand).any():
        mask &= df["stand"] == stand
    if not mask.any():
        return None
    i = int(np.where(mask.values)[0][0])
    me_stand = df.iloc[i].get("stand")
    d2 = np.sum((X - X[i]) ** 2, axis=1)            # squared distance to all
    sim = np.exp(-gamma * d2)                         # RBF kernel similarity
    order = np.argsort(-sim)
    out = []
    for j in order:
        if j == i:
            continue
        r = df.iloc[j]
        # Only comp like-handed swings: a RHB and LHB are mirror images, so a
        # cross-handed "match" is misleading (esp. attack direction / contact x).
        # Switch hitters' (L) and (R) rows each match their own side.
        if me_stand is not None and "stand" in df.columns and r.get("stand") != me_stand:
            continue
        out.append({
            "name": r["name"], "batter": int(r["batter"]),
            "stand": r.get("stand"),
            "similarity": round(float(sim[j]) * 100, 1),
            "swing_plus": round(float(r["swing_plus"]), 1),
            "bat_speed": round(float(r["bat_speed_mean"]), 1),
            "attack_angle": round(float(r["attack_angle_mean"]), 1),
        })
        if len(out) >= n:
            break
    return {"player": df.iloc[i]["name"], "comps": out}


if __name__ == "__main__":
    for nm, bid in [("Aaron Judge", 592450), ("Steven Kwan", 680757),
                    ("Luis Arraez", 650333)]:
        res = comps_for(bid, n=6)
        if not res: print(nm, "-> not in index"); continue
        print(f"\nMost similar swing paths to {res['player']}:")
        for c in res["comps"]:
            print(f"  {c['similarity']:5.1f}%  {c['name']:<22} "
                  f"Swing+ {c['swing_plus']:>5}  bat {c['bat_speed']}  AA {c['attack_angle']}")
