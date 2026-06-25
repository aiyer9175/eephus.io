# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
18_topdown_coverage_test.py - Compute top-down path-coverage features and
test whether they add anything to the model beyond Phase 1's existing features.

Features extracted from the top-down reconstruction:
  - lateral_coverage_ft: max X minus min X along the path (how much
    lateral ground does the bat cover?)
  - x_at_downswing, x_at_contact_zone, x_at_followthrough: lateral
    position at three buckets along the path. (Contact is the contact
    point; the others are interpolations.)
  - haa_at_downswing, haa_at_contact_zone, haa_at_followthrough:
    horizontal attack angle at three buckets. (We KNOW these are
    deterministic offsets from attack_direction under the circular-arc
    model; including for honest validation that they add nothing.)
  - depth_at_min_x: Y coordinate when X is at its minimum (how deep
    in the zone is the bat at its furthest oppo extent?)

Test: do these features predict P(BIP) or RV|BIP better than features
we already have?

Honest expectation, going in:
  - HAA-at-buckets features will be useless (deterministic).
  - lateral_coverage and depth_at_min_x might add something because they
    combine swing_length and attack_direction nonlinearly, but they're
    still functions of inputs the Phase 1 model can see via quadratic
    interactions.
  - Net: I expect ~zero improvement. If R² doesn't move, we've confirmed
    the top-down view doesn't help and we should drop it.
"""

import sys
sys.path.insert(0, "/home/claude")
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import KFold, cross_val_score
import importlib.util

spec = importlib.util.spec_from_file_location("td", "/home/claude/17_path_topdown.py")
td = importlib.util.module_from_spec(spec)
spec.loader.exec_module(td)
reconstruct_topdown = td.reconstruct_topdown


# ===================================================================
# Step 1: Extract features per swing
# ===================================================================

def extract_topdown_features(row) -> dict:
    """Build top-down path features from one swing's Statcast inputs."""
    p = reconstruct_topdown(
        attack_direction_deg=row["attack_direction"],
        swing_length_ft=row["swing_length"],
        intercept_x_in=row["intercept_ball_minus_batter_pos_x_inches"],
        intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
        handedness=row["stand"],
    )
    pts = p.sample(18)
    xs = pts[:, 0]
    ys = pts[:, 1]
    return {
        # Coverage features
        "lateral_coverage_ft":  xs.max() - xs.min(),
        "depth_at_min_x":       ys[np.argmin(xs)],
        # X position at three buckets along the path
        "x_at_downswing":       xs[2],   # ~t=0.12
        "x_at_contact_zone":    xs[15],  # ~t=0.88
        "x_at_followthrough":   xs[17],  # contact itself
        # HAA at three buckets (we expect zero variance after subtracting
        # attack_direction; included for honest documentation)
        "haa_at_downswing":     p.haa_at(0.17),
        "haa_at_contact_zone":  p.haa_at(0.83),
        "haa_at_contact":       p.haa_at(1.00),
        # Path depth range
        "depth_range_ft":       ys.max() - ys.min(),
    }


# ===================================================================
# Step 2: Build the augmented profiles
# ===================================================================

print("Loading 5 halves of competitive swings...")
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
needed = ["bat_speed", "swing_length", "attack_angle", "attack_direction",
          "swing_path_tilt",
          "intercept_ball_minus_batter_pos_x_inches",
          "intercept_ball_minus_batter_pos_y_inches",
          "plate_z", "stand", "type", "delta_run_exp",
          "estimated_woba_using_speedangle"]

all_swings = []
for label in HALVES:
    df = pd.read_parquet(f"data/raw/statcast_{label}.parquet")
    df = df[df["bat_speed"].notna() & df["swing_length"].notna()].copy()
    df = df.dropna(subset=needed[:-2])
    mask = (
        (df["bat_speed"] >= 40) & (df["bat_speed"] <= 90) &
        (df["swing_length"] >= 4) & (df["swing_length"] <= 12) &
        (df["attack_angle"].abs() <= 45) &
        (df["swing_path_tilt"] >= 10) & (df["swing_path_tilt"] <= 50) &
        (df["attack_direction"].abs() <= 60)
    )
    df = df[mask].copy()
    df["half"] = label
    df["bip"] = (df["type"] == "X").astype(int)
    all_swings.append(df)
swings = pd.concat(all_swings, ignore_index=True)
print(f"Total filtered competitive swings: {len(swings):,}")


# Extract top-down features per swing - this is the slow part
print("Extracting top-down features per swing...")
import time
t0 = time.time()

# Vectorize what we can. Most computation is per-row matrix math, but
# the reconstruct_topdown call is per-row Python overhead. To keep this
# tractable on 770K rows, batch in chunks of 10K.
results = []
for i in range(0, len(swings), 10000):
    chunk = swings.iloc[i:i+10000]
    feats = chunk.apply(extract_topdown_features, axis=1).tolist()
    results.extend(feats)
    if (i // 10000) % 5 == 0:
        elapsed = time.time() - t0
        print(f"  {i+len(chunk):,}/{len(swings):,} ({elapsed:.0f}s)")

td_feats = pd.DataFrame(results, index=swings.index)
swings = pd.concat([swings, td_feats], axis=1)
print(f"Done in {time.time() - t0:.0f}s. Sample of features:")
print(swings[list(td_feats.columns)].describe())


# ===================================================================
# Step 3: Aggregate to player-half profiles, including new features
# ===================================================================

TRACKING_FEATURES = [
    "bat_speed", "swing_length", "attack_angle", "attack_direction",
    "swing_path_tilt",
    "intercept_ball_minus_batter_pos_x_inches",
    "intercept_ball_minus_batter_pos_y_inches",
]
TOPDOWN_FEATURES = list(td_feats.columns)

agg = {col: ["mean", "std"] for col in TRACKING_FEATURES + TOPDOWN_FEATURES}
profiles = swings.groupby(["batter", "half"]).agg(agg)
profiles.columns = [f"{c}_{stat}" for c, stat in profiles.columns]
profiles["n_swings"] = swings.groupby(["batter", "half"]).size()
profiles["n_bip"] = swings.groupby(["batter", "half"])["bip"].sum()
profiles["bip_rate"] = profiles["n_bip"] / profiles["n_swings"]
bip_swings = swings[swings["bip"] == 1]
profiles["rv_given_bip"] = bip_swings.groupby(["batter", "half"])["delta_run_exp"].mean()
profiles = profiles[profiles["n_swings"] >= 180].reset_index().dropna(
    subset=["rv_given_bip"]
)
print(f"\nPlayer-halves with n>=180: {len(profiles)}")


# ===================================================================
# Step 4: Compare model performance with and without top-down features
# ===================================================================

def make_pipe():
    return Pipeline([
        ("scale", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, include_bias=False)),
        ("ridge", RidgeCV(alphas=(0.1, 1.0, 10.0, 100.0))),
    ])

# Baseline feature set: Phase 1's set
PHASE1_FEATS = [
    "bat_speed_mean", "swing_length_mean", "attack_angle_mean",
    "attack_direction_mean", "swing_path_tilt_mean",
    "intercept_ball_minus_batter_pos_x_inches_mean",
    "intercept_ball_minus_batter_pos_y_inches_mean",
    "bat_speed_std", "attack_angle_std",
]
# Augmented: Phase 1 + top-down means
TD_FEAT_MEANS = [f"{f}_mean" for f in TOPDOWN_FEATURES]
AUGMENTED = PHASE1_FEATS + TD_FEAT_MEANS

# Drop NA rows for fair comparison
d = profiles.dropna(subset=AUGMENTED + ["bip_rate", "rv_given_bip"]).copy()
print(f"\nClean rows for model comparison: {len(d)}")

cv = KFold(n_splits=5, shuffle=True, random_state=42)

def evaluate(features, target_col, label):
    X = d[features].values
    y = d[target_col].values
    r2 = cross_val_score(make_pipe(), X, y, cv=cv, scoring="r2")
    print(f"  [{label}] CV R² = {r2.mean():.4f} (±{r2.std():.4f}), "
          f"n_feats={len(features)}")
    return r2.mean()


print("\n" + "="*72)
print(f"COMPARISON: P(BIP) model")
print("="*72)
r2_p1_bip = evaluate(PHASE1_FEATS,  "bip_rate", "Phase 1 only")
r2_aug_bip = evaluate(AUGMENTED,    "bip_rate", "Phase 1 + top-down")
print(f"  Delta from adding top-down features: {r2_aug_bip - r2_p1_bip:+.4f}")

print("\n" + "="*72)
print(f"COMPARISON: RV|BIP model")
print("="*72)
r2_p1_pow = evaluate(PHASE1_FEATS,  "rv_given_bip", "Phase 1 only")
r2_aug_pow = evaluate(AUGMENTED,    "rv_given_bip", "Phase 1 + top-down")
print(f"  Delta from adding top-down features: {r2_aug_pow - r2_p1_pow:+.4f}")


# ===================================================================
# Step 5: Honest diagnostics on the new features themselves
# ===================================================================
print("\n" + "="*72)
print("Feature-by-feature diagnostic: how informative is each new feature?")
print("="*72)
print("Each row: marginal R² gain from adding ONLY this feature to Phase 1.")

for new_feat in TD_FEAT_MEANS:
    feats = PHASE1_FEATS + [new_feat]
    d_sub = d.dropna(subset=feats + ["rv_given_bip"])
    if len(d_sub) < 100:
        continue
    X = d_sub[feats].values
    y = d_sub["rv_given_bip"].values
    r2 = cross_val_score(make_pipe(), X, y, cv=cv, scoring="r2").mean()
    delta = r2 - r2_p1_pow
    print(f"  + {new_feat:<40} R² = {r2:.4f}  (Δ = {delta:+.4f})")


# Also: how much variance does each new feature have AFTER controlling
# for Phase 1 features? If a feature is fully explained by Phase 1, its
# residual variance is zero — it's redundant.
print("\n" + "="*72)
print("How much unique info does each new feature carry?")
print("(R² of Phase 1 features predicting each new feature; higher = more redundant)")
print("="*72)
for new_feat in TD_FEAT_MEANS:
    d_sub = d.dropna(subset=PHASE1_FEATS + [new_feat])
    if len(d_sub) < 100:
        continue
    X = d_sub[PHASE1_FEATS].values
    y = d_sub[new_feat].values
    r2 = cross_val_score(make_pipe(), X, y, cv=cv, scoring="r2").mean()
    print(f"  {new_feat:<40} Phase1 → predicts at R² = {r2:.4f}")
