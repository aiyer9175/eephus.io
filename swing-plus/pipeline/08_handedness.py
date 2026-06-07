# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
08_handedness.py - Should we split Bat+ by handedness?

Two specific questions:
1. Do the swing-tracking features have different DISTRIBUTIONS by handedness?
   (e.g., attack direction is mirrored for L vs R - this is mechanical)
2. Do the same features have different RELATIONSHIPS to RV by handedness?
   (this is what matters - if a 12-degree attack angle is good for both L and R,
    one model is fine; if it's optimal for R but suboptimal for L, we need splits)

The answer to #1 is almost certainly yes (mechanical mirroring).
The answer to #2 is the empirical question we need to test.

If #2 is yes, we either:
- Mirror attack_direction for lefties to use one model (cheap), or
- Fit separate L and R models (more accurate, less data per model)
"""

import pandas as pd
import numpy as np
from scipy.stats import pearsonr
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import KFold, cross_val_score

profiles = pd.read_parquet("data/processed/profiles_adjusted.parquet")
print(f"Total profiles: {len(profiles)}")
print(f"Handedness split: {profiles['stand'].value_counts().to_dict()}")

TRACKING = [
    "bat_speed_mean", "swing_length_mean", "attack_angle_mean",
    "attack_direction_mean", "swing_path_tilt_mean",
    "intercept_ball_minus_batter_pos_x_inches_mean",
    "intercept_ball_minus_batter_pos_y_inches_mean",
]


# ============================================================
# Question 1: How do feature distributions differ by handedness?
# ============================================================
print("\n" + "=" * 70)
print("Q1: Feature distribution differences (mean ± SD by handedness)")
print("=" * 70)
print(f"{'feature':<55} {'L mean':>10} {'R mean':>10} {'diff':>8}")
print("-" * 90)
for col in TRACKING:
    l = profiles.loc[profiles["stand"] == "L", col].dropna()
    r = profiles.loc[profiles["stand"] == "R", col].dropna()
    print(f"{col:<55} {l.mean():>10.3f} {r.mean():>10.3f} {l.mean() - r.mean():>+8.3f}")


# ============================================================
# Question 2: Do feature->outcome relationships differ by handedness?
# Test: fit separate L and R models. Does pooled R² < weighted L,R R²?
# ============================================================
print("\n" + "=" * 70)
print("Q2: Does splitting by handedness improve model fit?")
print("=" * 70)

FEATURES = TRACKING + ["bat_speed_std", "attack_angle_std"]
TARGETS = ["bip_rate", "rv_given_bip_adj"]


def make_pipe():
    return Pipeline([
        ("scale", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, include_bias=False)),
        ("ridge", RidgeCV(alphas=(0.1, 1.0, 10.0, 100.0))),
    ])


def cv_r2(df, feats, target):
    d = df.dropna(subset=feats + [target])
    if len(d) < 50:
        return np.nan, 0
    X = d[feats].values
    y = d[target].values
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    return cross_val_score(make_pipe(), X, y, cv=cv, scoring="r2").mean(), len(d)


for target in TARGETS:
    print(f"\nTarget: {target}")
    r2_pooled, n_pooled = cv_r2(profiles, FEATURES, target)
    r2_L, n_L = cv_r2(profiles[profiles["stand"] == "L"], FEATURES, target)
    r2_R, n_R = cv_r2(profiles[profiles["stand"] == "R"], FEATURES, target)
    # Weighted average of the two split models
    r2_split = (r2_L * n_L + r2_R * n_R) / (n_L + n_R)
    print(f"  Pooled model: R² = {r2_pooled:.3f}  (n={n_pooled})")
    print(f"  L-only model: R² = {r2_L:.3f}  (n={n_L})")
    print(f"  R-only model: R² = {r2_R:.3f}  (n={n_R})")
    print(f"  Weighted split avg: R² = {r2_split:.3f}")
    delta = r2_split - r2_pooled
    print(f"  Split improvement: {delta:+.3f}")
    print(f"  Verdict: {'split is meaningfully better' if delta > 0.02 else 'pooled is fine'}")


# ============================================================
# Question 3: Does MIRRORING (just flipping attack_direction sign for L)
# get most of the benefit without splitting the model?
# ============================================================
print("\n" + "=" * 70)
print("Q3: Does mirroring attack_direction for L hitters help?")
print("=" * 70)

mirrored = profiles.copy()
# For L hitters: attack direction sign flips because the strike zone /
# pull direction is mirrored. Mirror the depth-x intercept too for symmetry.
mask_L = mirrored["stand"] == "L"
mirrored.loc[mask_L, "attack_direction_mean"] *= -1
mirrored.loc[mask_L, "intercept_ball_minus_batter_pos_x_inches_mean"] *= -1

for target in TARGETS:
    r2_mirrored, n_m = cv_r2(mirrored, FEATURES, target)
    r2_pooled, n_p = cv_r2(profiles, FEATURES, target)
    print(f"\nTarget: {target}")
    print(f"  Pooled (no mirroring):     R² = {r2_pooled:.3f}")
    print(f"  Pooled (with mirroring):   R² = {r2_mirrored:.3f}")
    print(f"  Mirroring delta: {r2_mirrored - r2_pooled:+.3f}")


# ============================================================
# Show the largest L vs R coefficient differences interpretably.
# For each feature, compute its simple correlation with the target in each split.
# ============================================================
print("\n" + "=" * 70)
print("Q4: Per-feature correlation with rv_given_bip_adj, by handedness")
print("=" * 70)

for col in TRACKING:
    l_data = profiles.loc[profiles["stand"] == "L", [col, "rv_given_bip_adj"]].dropna()
    r_data = profiles.loc[profiles["stand"] == "R", [col, "rv_given_bip_adj"]].dropna()
    if len(l_data) < 30 or len(r_data) < 30:
        continue
    r_L, _ = pearsonr(l_data[col], l_data["rv_given_bip_adj"])
    r_R, _ = pearsonr(r_data[col], r_data["rv_given_bip_adj"])
    flag = "  <-- different sign!" if (r_L * r_R) < 0 and min(abs(r_L), abs(r_R)) > 0.1 else ""
    print(f"  {col:<55} L: r={r_L:+.3f}  R: r={r_R:+.3f}{flag}")
