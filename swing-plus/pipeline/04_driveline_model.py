# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
04_driveline_model.py - Two-model Bat+ following the Driveline framework.

Models built:
1. P(BIP) - probability a competitive swing results in a ball in play
   (vs. foul or whiff). Target: binary ball-in-play indicator.
2. Power | BIP - expected run value when contact is made.
   Target: delta_run_exp on BIP swings (or xwOBAcon translated to RV).

Combined objective per Driveline:
   E[RV per swing] = P(BIP) * E[RV | BIP] + P(~BIP) * RV_avg_whiff_foul

The whiff/foul constant comes from the empirical mean run value of non-BIP
competitive swings in the dataset. This is what Driveline calls "v~BIP".

Bat+ = 100 * (player_xRV / league_avg_xRV)

This properly credits both Kwan (high P(BIP), modest power) and Judge
(modest P(BIP), elite power). Pure xwOBAcon target would only credit Judge.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.linear_model import Ridge, RidgeCV
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import KFold, cross_val_score, GroupKFold

# -------- Config --------

MIN_SWINGS = 180
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]

TRACKING_COLS = [
    "bat_speed",
    "swing_length",
    "attack_angle",
    "attack_direction",
    "swing_path_tilt",
    "intercept_ball_minus_batter_pos_x_inches",
    "intercept_ball_minus_batter_pos_y_inches",
]

FEATURE_COLS = [f"{c}_mean" for c in TRACKING_COLS] + [
    "bat_speed_std",
    "attack_angle_std",
]

# -------- Pitch-level prep --------

def is_competitive_swing(df: pd.DataFrame) -> pd.Series:
    """Statcast computes bat_speed only on real swings - cleanest filter."""
    return df["bat_speed"].notna() & df["swing_length"].notna()


def is_bip(df: pd.DataFrame) -> pd.Series:
    """Ball-in-play flag for competitive swings."""
    return df["type"] == "X"


def load_all_halves() -> pd.DataFrame:
    parts = []
    for label in HALVES:
        df = pd.read_parquet(f"data/raw/statcast_{label}.parquet")
        df = df.loc[is_competitive_swing(df)].copy()
        df["half"] = label
        df["bip"] = is_bip(df).astype(int)
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


# -------- Player-half aggregation --------

def build_profiles(swings: pd.DataFrame) -> pd.DataFrame:
    """One row per (batter, half) with mean/std of tracking features."""
    agg = {col: ["mean", "std"] for col in TRACKING_COLS}
    profiles = swings.groupby(["batter", "half"]).agg(agg)
    profiles.columns = [f"{c}_{stat}" for c, stat in profiles.columns]

    # Counts and rates.
    profiles["n_swings"] = swings.groupby(["batter", "half"]).size()
    profiles["n_bip"] = swings.groupby(["batter", "half"])["bip"].sum()
    profiles["bip_rate"] = profiles["n_bip"] / profiles["n_swings"]

    # Observed targets (for validation, not as model inputs).
    bip_swings = swings.loc[swings["bip"] == 1]
    profiles["xwobacon_obs"] = bip_swings.groupby(["batter", "half"])[
        "estimated_woba_using_speedangle"
    ].mean()

    # Run value per swing (avg delta_run_exp on competitive swings).
    profiles["rv_per_swing_obs"] = swings.groupby(["batter", "half"])[
        "delta_run_exp"
    ].mean()

    profiles = profiles[profiles["n_swings"] >= MIN_SWINGS].reset_index()
    return profiles


# -------- Two-model fit --------

def make_pipe(alpha_options=(0.1, 1.0, 10.0, 100.0)) -> Pipeline:
    """RidgeCV picks regularization strength via internal CV."""
    return Pipeline([
        ("scale", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, interaction_only=False, include_bias=False)),
        ("ridge", RidgeCV(alphas=alpha_options)),
    ])


def fit_two_models(profiles: pd.DataFrame):
    """
    Fit P(BIP) and E[RV|BIP] models on player-half profiles.

    Note: targets here are aggregated to player-half level (bip_rate and
    mean RV on BIP). This is a deliberate choice - we're modeling the
    SWING PROFILE's expected production, not predicting pitch-level
    outcomes. Pitch-level modeling would conflate path with pitch quality
    and approach, which is what we want to abstract away from.
    """
    df = profiles.dropna(subset=FEATURE_COLS + ["bip_rate"]).copy()

    # Compute RV | BIP per player-half from pitch-level data.
    # (This is loaded fresh below to get the conditional mean correctly.)
    X = df[FEATURE_COLS].values

    # ---- Model 1: P(BIP) on competitive swings ----
    y_bip = df["bip_rate"].values
    pipe_bip = make_pipe()
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    r2_bip = cross_val_score(pipe_bip, X, y_bip, cv=cv, scoring="r2")
    print(f"P(BIP) model:    CV R² = {r2_bip.mean():.3f} (±{r2_bip.std():.3f})")
    pipe_bip.fit(X, y_bip)

    # ---- Model 2: RV per BIP (power) ----
    df_pow = df.dropna(subset=["rv_given_bip"]).copy()
    X_pow = df_pow[FEATURE_COLS].values
    y_pow = df_pow["rv_given_bip"].values
    pipe_pow = make_pipe()
    r2_pow = cross_val_score(pipe_pow, X_pow, y_pow, cv=cv, scoring="r2")
    print(f"RV | BIP model:  CV R² = {r2_pow.mean():.3f} (±{r2_pow.std():.3f})")
    pipe_pow.fit(X_pow, y_pow)

    return pipe_bip, pipe_pow


# -------- Combine to Bat+ --------

def compute_bat_plus(profiles: pd.DataFrame, pipe_bip, pipe_pow, rv_nonbip: float):
    """
    Objective = P(BIP) * E[RV|BIP] + (1 - P(BIP)) * rv_nonbip

    Then Bat+ = 100 * (player_xRV / league_avg_xRV)
    """
    df = profiles.dropna(subset=FEATURE_COLS).copy()
    X = df[FEATURE_COLS].values

    df["p_bip_pred"] = np.clip(pipe_bip.predict(X), 0.0, 1.0)
    df["rv_bip_pred"] = pipe_pow.predict(X)
    df["xrv_per_swing"] = (
        df["p_bip_pred"] * df["rv_bip_pred"]
        + (1 - df["p_bip_pred"]) * rv_nonbip
    )

    # Center on league average so Bat+ = 100 means average.
    # Using simple mean of player-half xRVs - swing-weighted would be more
    # "correct" but obscures the per-player normalization the user expects.
    league_avg = df["xrv_per_swing"].mean()
    # Multiplicative scaling (wRC+ style) breaks when values can be negative.
    # RV per swing IS negative on average for non-BIP. Use additive scaling:
    #   Bat+ = 100 + (xRV - league_avg) / std * 10
    sigma = df["xrv_per_swing"].std()
    df["bat_plus"] = 100 + (df["xrv_per_swing"] - league_avg) / sigma * 10

    return df.sort_values("bat_plus", ascending=False)


# -------- Main --------

if __name__ == "__main__":
    print("Loading all halves...")
    swings = load_all_halves()
    print(f"Total competitive swings across 5 halves: {len(swings):,}")

    # Constant: mean RV when contact NOT made.
    rv_nonbip = swings.loc[swings["bip"] == 0, "delta_run_exp"].mean()
    print(f"League avg RV on whiff/foul: {rv_nonbip:+.4f}")

    print("\nBuilding profiles...")
    profiles = build_profiles(swings)
    print(f"Player-half rows passing {MIN_SWINGS}-swing filter: {len(profiles)}")

    # Add RV | BIP target.
    rv_given_bip = (
        swings.loc[swings["bip"] == 1]
        .groupby(["batter", "half"])["delta_run_exp"]
        .mean()
        .rename("rv_given_bip")
    )
    profiles = profiles.merge(rv_given_bip, on=["batter", "half"], how="left")

    Path("data/processed").mkdir(parents=True, exist_ok=True)
    profiles.to_parquet("data/processed/profiles_all_halves.parquet")

    print("\nFitting two-model system...")
    pipe_bip, pipe_pow = fit_two_models(profiles)

    print("\nComputing Bat+...")
    graded = compute_bat_plus(profiles, pipe_bip, pipe_pow, rv_nonbip)
    graded.to_parquet("data/processed/bat_plus_grades.parquet")

    print(f"\nBat+ stats: mean={graded['bat_plus'].mean():.1f}, "
          f"std={graded['bat_plus'].std():.1f}, "
          f"range=[{graded['bat_plus'].min():.1f}, {graded['bat_plus'].max():.1f}]")
