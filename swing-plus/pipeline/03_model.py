# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
03_model.py - Fit xwOBAcon model and produce Bat+ grades.

Modeling notes:
- Linear model with quadratic polynomial features (matches Driveline's approach).
  The squared terms let the model learn that extreme attack angles (very steep
  OR very flat) underperform optimal mid-range values - a pure linear model
  can't capture that.
- We use Ridge instead of OLS because PolynomialFeatures(degree=2) creates
  heavy multicollinearity (every feature gets an x_i * x_j cross-term).
  OLS coefficients become unstable; Ridge regularizes them. Switch to OLS
  via statsmodels if you want p-values, but expect inflated standard errors.
- Bat+ uses the multiplicative wRC+ convention: 100 * (predicted / league_avg).
  100 = average, 110 = 10% better than league, etc.

IMPORTANT - what this model does NOT do:
- It does not separate "swing quality" from "outcome luck on batted balls".
  xwOBAcon already strips most luck (it's expected wOBA from EV+LA), but
  not all - sequencing into good pitches to hit also boosts xwOBAcon, and
  this model can't disentangle that from pure path quality.
- It does not yet incorporate the 18-point reconstructed path. This is a
  "Bat+ at contact" - same inputs as Statcast gives publicly, no path
  reconstruction. That's Phase 2.
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge, LinearRegression
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import KFold, cross_val_score

# Features used to predict xwOBAcon.
FEATURE_COLS = [
    "bat_speed_mean",
    "swing_length_mean",
    "attack_angle_mean",
    "attack_direction_mean",
    "swing_path_tilt_mean",
    "intercept_ball_minus_batter_pos_x_inches_mean",
    "intercept_ball_minus_batter_pos_y_inches_mean",
    # Spread terms - consistency matters too.
    "bat_speed_std",
    "attack_angle_std",
]


def fit_model(profiles: pd.DataFrame, alpha: float = 1.0) -> Pipeline:
    """Fit a Ridge regression with quadratic features on player-half profiles."""
    df = profiles.dropna(subset=FEATURE_COLS + ["xwobacon"]).copy()
    X = df[FEATURE_COLS].values
    y = df["xwobacon"].values

    pipe = Pipeline([
        ("scale", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, interaction_only=False, include_bias=False)),
        ("ridge", Ridge(alpha=alpha)),
    ])

    # Honest CV - report what to actually expect on held-out players.
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    r2_scores = cross_val_score(pipe, X, y, cv=cv, scoring="r2")
    print(f"5-fold CV R²: {r2_scores.mean():.3f} (±{r2_scores.std():.3f})")
    print(f"  Per-fold: {[f'{s:.3f}' for s in r2_scores]}")

    # Refit on all data for final coefficients.
    pipe.fit(X, y)
    print(f"In-sample R²: {pipe.score(X, y):.3f}")
    return pipe, df


def compute_bat_plus(model: Pipeline, profiles: pd.DataFrame) -> pd.DataFrame:
    """Apply the model and convert predictions to a 100-centered scale."""
    df = profiles.dropna(subset=FEATURE_COLS).copy()
    X = df[FEATURE_COLS].values
    df["predicted_xwobacon"] = model.predict(X)

    # League average from the players in the training pool (weighted by swings
    # would be more correct - using simple mean here for transparency).
    league_avg = df["predicted_xwobacon"].mean()
    df["bat_plus"] = 100 * (df["predicted_xwobacon"] / league_avg)
    return df.sort_values("bat_plus", ascending=False)


def sanity_check(graded: pd.DataFrame) -> None:
    """Bat speed alone explains a lot - make sure our model adds signal beyond it."""
    from scipy.stats import pearsonr
    r_bs, _ = pearsonr(graded["bat_speed_mean"], graded["bat_plus"])
    r_xwoba, _ = pearsonr(graded["xwobacon"], graded["bat_plus"])
    print(f"\nSanity checks:")
    print(f"  Bat+ vs bat speed: r = {r_bs:.3f}")
    print(f"  Bat+ vs actual xwOBAcon: r = {r_xwoba:.3f}")
    print(f"  (Expect bat speed correlation high but <0.95; expect xwOBAcon")
    print(f"   correlation high but <1.0 - if either hits 1.0 you've leaked.)")


if __name__ == "__main__":
    profiles = pd.read_parquet("data/processed/profiles.parquet")
    model, fit_df = fit_model(profiles)
    graded = compute_bat_plus(model, profiles)
    sanity_check(graded)
    print(f"\nTop 10 Bat+:")
    print(graded.head(10)[["batter", "half", "bat_plus", "xwobacon", "bat_speed_mean"]])
