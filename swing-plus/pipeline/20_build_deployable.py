# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
20_build_deployable.py - Package Phase 1 Swing+ for deployment.

Produces:
  - swing_plus_model.joblib: the two-model artifact (P(BIP) and RV|BIP pipelines
    + normalization constants + feature list + metadata)
  - swing_plus.py: standalone inference module that loads the artifact and
    exposes compute_swing_plus(swings_df) → DataFrame with Swing+ scores

The artifact contains everything needed to score new data: feature names,
fitted pipelines, league constants, and reliability parameters. The
inference module has no training-time dependencies — it just transforms
new Statcast data and applies the saved models.

Design notes:
  - 2026 data: when new halves of 2026 data become available, the user
    runs the same featurization (compute player-half profiles with mean/std
    of tracking features over competitive swings ≥ 180) and feeds them into
    the inference function. The artifact is trained on 2023H2-2025H2 and
    does not need to be retrained to score 2026 data.
  - Periodically retraining (e.g., after each season) is a separate step
    and should be done deliberately, not automatically — it would change
    the calibration of the 100-mean Swing+ scale.
"""

import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import Pipeline


# Phase 1 features (final set)
PHASE1_FEATURES = [
    "bat_speed_mean", "swing_length_mean", "attack_angle_mean",
    "attack_direction_mean", "swing_path_tilt_mean",
    "intercept_ball_minus_batter_pos_x_inches_mean",
    "intercept_ball_minus_batter_pos_y_inches_mean",
    "bat_speed_std", "attack_angle_std",
]

# Tracking columns we aggregate over per player-half
TRACKING_COLS = [
    "bat_speed", "swing_length", "attack_angle", "attack_direction",
    "swing_path_tilt",
    "intercept_ball_minus_batter_pos_x_inches",
    "intercept_ball_minus_batter_pos_y_inches",
]

MIN_SWINGS = 180
RELIABILITY_K = 360
PARK_ADJUSTED = True   # we use the adjusted profiles


# ===================================================================
# Load training data and fit the models
# ===================================================================

profiles = pd.read_parquet("data/processed/profiles_adjusted.parquet")
d = profiles.dropna(subset=PHASE1_FEATURES + ["bip_rate", "rv_given_bip_adj"]).copy()
print(f"Training rows: {len(d)}")

X = d[PHASE1_FEATURES].values

def make_pipe():
    return Pipeline([
        ("scale", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, include_bias=False)),
        ("ridge", RidgeCV(alphas=(0.1, 1.0, 10.0, 100.0))),
    ])

print("Fitting P(BIP) model...")
pipe_bip = make_pipe().fit(X, d["bip_rate"].values)

print("Fitting RV|BIP model...")
pipe_pow = make_pipe().fit(X, d["rv_given_bip_adj"].values)


# ===================================================================
# Calibration constants
# ===================================================================

# rv_nonbip: mean delta_run_exp on non-BIP competitive swings (whiffs+fouls)
# We computed this in module 07 as -0.0659 from full 5-half data
RV_NONBIP_CONSTANT = -0.0659

# Compute scaling constants from training xRV distribution
p = np.clip(pipe_bip.predict(X), 0, 1)
rv = pipe_pow.predict(X)
xrv = p * rv + (1 - p) * RV_NONBIP_CONSTANT
TRAIN_XRV_MEAN = float(xrv.mean())
TRAIN_XRV_STD = float(xrv.std())
print(f"Training xRV: mean = {TRAIN_XRV_MEAN:.4f}, sd = {TRAIN_XRV_STD:.4f}")


# ===================================================================
# Package the artifact
# ===================================================================

artifact = {
    "version": "1.0.0",
    "trained_through": "2025_H2",
    "model_type": "swing_plus_phase_1",
    "features": PHASE1_FEATURES,
    "tracking_cols": TRACKING_COLS,
    "min_swings": MIN_SWINGS,
    "reliability_k": RELIABILITY_K,
    "rv_nonbip_constant": RV_NONBIP_CONSTANT,
    "train_xrv_mean": TRAIN_XRV_MEAN,
    "train_xrv_std": TRAIN_XRV_STD,
    "pipe_bip": pipe_bip,
    "pipe_pow": pipe_pow,
    "real_swing_filter": {
        "bat_speed_min": 40, "bat_speed_max": 90,
        "swing_length_min": 4, "swing_length_max": 12,
        "attack_angle_abs_max": 45,
        "swing_path_tilt_min": 10, "swing_path_tilt_max": 50,
        "attack_direction_abs_max": 60,
    },
    "notes": (
        "Trained on Statcast bat-tracking data, 2023 H2 through 2025 H2. "
        "Targets: park+pitch-quality-adjusted P(BIP) and RV|BIP. "
        "Swing+ scaled to mean 100, SD 10 over training set. "
        "Reliability-weighted with k=360 toward population mean."
    ),
}

output_path = Path("/mnt/user-data/outputs/swing_plus_model_v1.joblib")
joblib.dump(artifact, output_path)
print(f"\nArtifact saved: {output_path} ({output_path.stat().st_size/1024:.0f} KB)")


# ===================================================================
# Sanity-check: load it back and reproduce known scores
# ===================================================================
print("\nSanity check: load artifact and reproduce a few known Swing+ scores")
loaded = joblib.load(output_path)
sample = d.head(5)
X_sample = sample[loaded["features"]].values
p = np.clip(loaded["pipe_bip"].predict(X_sample), 0, 1)
rv = loaded["pipe_pow"].predict(X_sample)
xrv = p * rv + (1 - p) * loaded["rv_nonbip_constant"]
sp_raw = 100 + (xrv - loaded["train_xrv_mean"]) / loaded["train_xrv_std"] * 10

for i in range(5):
    bid = sample["batter"].iloc[i]
    half = sample["half"].iloc[i]
    print(f"  batter={bid}, half={half}: Swing+ raw = {sp_raw[i]:.2f}")
