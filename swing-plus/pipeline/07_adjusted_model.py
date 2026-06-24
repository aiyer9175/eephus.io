# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
07_adjusted_model.py - Park and pitch-quality adjustments for Bat+.

What this fixes:
- A hitter who happens to face a tough pitch mix (or hits in a pitcher's park)
  will have suppressed xwOBAcon and RV. That bias bleeds into the RV|BIP model
  and makes their swing look worse than it is.
- We control for pitch quality at the PITCH level by predicting expected
  outcome from the pitch characteristics alone (no batter features), then
  taking the residual (actual - expected) as the "swing contribution".
- Park adjustment is a fixed effect per home_team: subtract the park's mean
  residual so a Coors hitter doesn't get extra credit.

Important honest caveats:
1. Pitch-quality control is a LEAGUE-LEVEL expectation given pitch characteristics.
   It doesn't separate pitcher talent from pitch quality on the day - just
   levels the playing field for "what kind of pitches did this hitter see".
2. Park adjustment via home_team mean residual conflates park with the home
   team's pitching staff. Coors gives up more contact damage because of altitude
   AND because Colorado has historically had below-average pitching. The clean
   fix needs a multi-year park factor; we're using a rougher within-sample
   approximation. Good enough for first pass.
3. Adjustments are applied to the TARGET (RV per swing, RV|BIP), not to
   features. Features (bat tracking) are not park/pitch-dependent.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.linear_model import RidgeCV
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import KFold, cross_val_score
from scipy.stats import pearsonr

HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
MIN_SWINGS = 180

TRACKING = [
    "bat_speed", "swing_length", "attack_angle", "attack_direction",
    "swing_path_tilt",
    "intercept_ball_minus_batter_pos_x_inches",
    "intercept_ball_minus_batter_pos_y_inches",
]
PITCH_QUALITY_FEATURES = [
    "release_speed", "pfx_x", "pfx_z", "plate_x", "plate_z",
    "release_spin_rate",
]


# ---------- Load competitive swings with adjustment features ----------

def load_competitive_swings() -> pd.DataFrame:
    parts = []
    for label in HALVES:
        df = pd.read_parquet(f"data/raw/statcast_{label}.parquet")
        df = df[df["bat_speed"].notna() & df["swing_length"].notna()].copy()
        df["half"] = label
        df["bip"] = (df["type"] == "X").astype(int)
        # Stand: 'L' or 'R' - the batter's handedness
        # (sometimes Statcast calls this 'stand' or 'b_stand')
        parts.append(df)
    out = pd.concat(parts, ignore_index=True)
    print(f"Loaded {len(out):,} competitive swings across {len(HALVES)} halves")
    print(f"Handedness col 'stand' present: {'stand' in out.columns}")
    if 'stand' in out.columns:
        print(out["stand"].value_counts(dropna=False))
    return out


# ---------- Pitch-quality model: predicts RV per swing from pitch chars ----------

def fit_pitch_quality_model(swings: pd.DataFrame) -> pd.DataFrame:
    """
    Predict delta_run_exp per competitive swing using ONLY pitch features.
    No batter info, no count info. The residual = swing contribution.

    Uses GBM because pitch-quality-to-outcome is highly non-linear
    (zone edges, breaking ball drop, etc.).
    """
    feats = PITCH_QUALITY_FEATURES
    df = swings.dropna(subset=feats + ["delta_run_exp"]).copy()
    X = df[feats].values
    y = df["delta_run_exp"].values

    print(f"\nFitting pitch-quality model on {len(df):,} swings...")
    # Use a held-out scoring to avoid bias - but for production residuals,
    # we'd want out-of-fold predictions. Cross-fit pattern:
    from sklearn.model_selection import KFold
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    df["expected_rv"] = np.nan

    for fold, (train_idx, test_idx) in enumerate(cv.split(X)):
        m = HistGradientBoostingRegressor(
            max_iter=200, max_depth=6, learning_rate=0.05,
            random_state=42,
        )
        m.fit(X[train_idx], y[train_idx])
        df.iloc[test_idx, df.columns.get_loc("expected_rv")] = m.predict(X[test_idx])
        print(f"  fold {fold + 1}/5 fit")

    df["rv_residual"] = df["delta_run_exp"] - df["expected_rv"]
    # Sanity: residuals should be ~mean 0
    print(f"  Mean residual:  {df['rv_residual'].mean():+.5f} (should be ~0)")
    print(f"  Std  residual:  {df['rv_residual'].std():.4f}")
    print(f"  Mean expected:  {df['expected_rv'].mean():+.4f}")
    print(f"  Mean actual:    {df['delta_run_exp'].mean():+.4f}")

    # Merge residual back to full swings dataframe.
    swings = swings.merge(
        df[["pitch_id" if "pitch_id" in df.columns else df.index.name or "index",
            "expected_rv", "rv_residual"]] if False else df[["expected_rv", "rv_residual"]],
        left_index=True, right_index=True, how="left",
    )
    return swings


# ---------- Park adjustment ----------

def apply_park_adjustment(swings: pd.DataFrame) -> pd.DataFrame:
    """
    Subtract each park's mean RV residual from every swing in that park.
    After this, a swing's adjusted residual is "value above what an average
    hitter would have produced on the same pitch in a neutral park".

    Caveat noted in module docstring: this conflates park with home pitching.
    """
    park_effect = swings.groupby("home_team")["rv_residual"].mean().rename("park_effect")
    swings = swings.merge(park_effect, on="home_team", how="left")
    swings["rv_adjusted"] = swings["rv_residual"] - swings["park_effect"]

    print(f"\nPark effects (RV per swing, vs league avg):")
    print(park_effect.sort_values(ascending=False).head(5).to_string())
    print("  ...")
    print(park_effect.sort_values(ascending=True).head(5).to_string())
    return swings


# ---------- Player-half aggregation on ADJUSTED outcomes ----------

def build_adjusted_profiles(swings: pd.DataFrame) -> pd.DataFrame:
    agg = {col: ["mean", "std"] for col in TRACKING}
    profiles = swings.groupby(["batter", "half"]).agg(agg)
    profiles.columns = [f"{c}_{stat}" for c, stat in profiles.columns]

    profiles["n_swings"] = swings.groupby(["batter", "half"]).size()
    profiles["n_bip"] = swings.groupby(["batter", "half"])["bip"].sum()
    profiles["bip_rate"] = profiles["n_bip"] / profiles["n_swings"]

    # ADJUSTED targets
    bip = swings[swings["bip"] == 1]
    profiles["rv_per_swing_adj"] = swings.groupby(["batter", "half"])["rv_adjusted"].mean()
    profiles["rv_given_bip_adj"] = bip.groupby(["batter", "half"])["rv_adjusted"].mean()
    # Keep observed unadjusted for comparison
    profiles["rv_per_swing_obs"] = swings.groupby(["batter", "half"])["delta_run_exp"].mean()
    profiles["rv_given_bip_obs"] = bip.groupby(["batter", "half"])["delta_run_exp"].mean()
    profiles["xwobacon_obs"] = bip.groupby(["batter", "half"])[
        "estimated_woba_using_speedangle"].mean()

    # Handedness: most common stance per player-half
    if "stand" in swings.columns:
        stand_mode = (
            swings.groupby(["batter", "half"])["stand"]
            .agg(lambda x: x.mode()[0] if len(x.mode()) else np.nan)
        )
        profiles["stand"] = stand_mode

    profiles = profiles[profiles["n_swings"] >= MIN_SWINGS].reset_index()
    return profiles


# ---------- Two-model fit, using ADJUSTED targets ----------

FEATURE_COLS = [f"{c}_mean" for c in TRACKING] + ["bat_speed_std", "attack_angle_std"]


def make_pipe():
    return Pipeline([
        ("scale", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, include_bias=False)),
        ("ridge", RidgeCV(alphas=(0.1, 1.0, 10.0, 100.0))),
    ])


def fit_two_models(profiles: pd.DataFrame, target_col: str):
    df = profiles.dropna(subset=FEATURE_COLS + ["bip_rate", target_col]).copy()
    X = df[FEATURE_COLS].values
    cv = KFold(n_splits=5, shuffle=True, random_state=42)

    pipe_bip = make_pipe()
    r2_bip = cross_val_score(pipe_bip, X, df["bip_rate"], cv=cv, scoring="r2")
    pipe_bip.fit(X, df["bip_rate"])

    pipe_pow = make_pipe()
    r2_pow = cross_val_score(pipe_pow, X, df[target_col], cv=cv, scoring="r2")
    pipe_pow.fit(X, df[target_col])

    print(f"\nTwo-model fit (target = {target_col}):")
    print(f"  P(BIP)   CV R² = {r2_bip.mean():.3f} (±{r2_bip.std():.3f})")
    print(f"  RV|BIP   CV R² = {r2_pow.mean():.3f} (±{r2_pow.std():.3f})")
    return pipe_bip, pipe_pow


def compute_bat_plus(profiles, pipe_bip, pipe_pow, rv_nonbip_constant, label):
    df = profiles.dropna(subset=FEATURE_COLS).copy()
    X = df[FEATURE_COLS].values
    p_bip = np.clip(pipe_bip.predict(X), 0, 1)
    rv_bip = pipe_pow.predict(X)
    xrv = p_bip * rv_bip + (1 - p_bip) * rv_nonbip_constant
    bp = 100 + (xrv - xrv.mean()) / xrv.std() * 10
    df[f"bat_plus_{label}"] = bp
    df[f"p_bip_{label}"] = p_bip
    df[f"rv_bip_{label}"] = rv_bip
    df[f"xrv_{label}"] = xrv
    return df


# ---------- Main ----------

if __name__ == "__main__":
    swings = load_competitive_swings()

    # 1. Fit pitch-quality model and compute residuals.
    swings = fit_pitch_quality_model(swings)
    # 2. Park adjustment on residuals.
    swings = apply_park_adjustment(swings)

    Path("data/processed").mkdir(parents=True, exist_ok=True)
    print(f"\nSaving adjusted pitch-level data...")
    swings[["batter", "half", "bip", "home_team", "delta_run_exp",
            "expected_rv", "rv_residual", "park_effect", "rv_adjusted",
            "estimated_woba_using_speedangle", "stand"]].to_parquet(
        "data/processed/swings_adjusted.parquet")

    # 3. Build profiles.
    profiles = build_adjusted_profiles(swings)
    profiles.to_parquet("data/processed/profiles_adjusted.parquet")
    print(f"Profiles passing 180-swing filter: {len(profiles)}")

    # 4. Constants for combining.
    rv_nonbip_adj = swings.loc[swings["bip"] == 0, "rv_adjusted"].mean()
    rv_nonbip_obs = swings.loc[swings["bip"] == 0, "delta_run_exp"].mean()

    # 5. Fit BOTH versions: unadjusted vs adjusted, so we can compare.
    print("\n" + "=" * 60)
    print("BASELINE (unadjusted, for comparison)")
    print("=" * 60)
    pb_o, pp_o = fit_two_models(profiles, "rv_given_bip_obs")
    graded_o = compute_bat_plus(profiles, pb_o, pp_o, rv_nonbip_obs, "obs")

    print("\n" + "=" * 60)
    print("ADJUSTED (park + pitch-quality residual)")
    print("=" * 60)
    pb_a, pp_a = fit_two_models(profiles, "rv_given_bip_adj")
    graded_a = compute_bat_plus(profiles, pb_a, pp_a, rv_nonbip_adj, "adj")

    # 6. Merge for comparison.
    keep_cols = ["batter", "half", "stand", "bat_plus_obs", "bat_plus_adj",
                 "p_bip_obs", "p_bip_adj", "rv_bip_obs", "rv_bip_adj"]
    merged = graded_o[["batter", "half", "stand", "bat_plus_obs", "p_bip_obs",
                       "rv_bip_obs"]].merge(
        graded_a[["batter", "half", "bat_plus_adj", "p_bip_adj", "rv_bip_adj"]],
        on=["batter", "half"], how="inner",
    )
    merged["delta_bp"] = merged["bat_plus_adj"] - merged["bat_plus_obs"]
    merged.to_parquet("data/processed/bat_plus_comparison.parquet")

    print(f"\nOverall agreement between adjusted and unadjusted Bat+:")
    r_overall, _ = pearsonr(merged["bat_plus_obs"], merged["bat_plus_adj"])
    print(f"  r = {r_overall:.3f}")
    print(f"  Mean |delta|: {merged['delta_bp'].abs().mean():.2f}")
    print(f"  Max  |delta|: {merged['delta_bp'].abs().max():.2f}")
