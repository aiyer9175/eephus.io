# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
swing_plus.py - Standalone inference module for Swing+.

Usage:
    from swing_plus import SwingPlusModel
    
    model = SwingPlusModel("swing_plus_model_v1.joblib")
    
    # Score new pitch-level Statcast data
    scores = model.score_pitch_level(pitch_df)
    
    # Or aggregate to player-half/season directly  
    leaderboard = model.score_to_leaderboard(pitch_df, group_by="season")

The module is self-contained: no training-time dependencies beyond
joblib/numpy/pandas/sklearn. Drop this file plus the .joblib artifact
into your backend and you're set up to score new data as it comes in.

Required input columns (must come from Statcast bat-tracking, all per-pitch):
    batter           int   MLBAM player ID
    bat_speed        float mph
    swing_length     float feet
    attack_angle     float degrees
    attack_direction float degrees
    swing_path_tilt  float degrees
    intercept_ball_minus_batter_pos_x_inches  float
    intercept_ball_minus_batter_pos_y_inches  float
    type             str   'X' = ball in play, 'S' = strike, 'B' = ball

Optional columns (used if present):
    half             str   e.g., '2026_H1' - season-half label
    season           int   e.g., 2026
    name             str   player name for the output leaderboard
    home_team        str   for optional park adjustment (not applied by default)
"""

import joblib
import numpy as np
import pandas as pd
from pathlib import Path


class SwingPlusModel:
    """Loaded Swing+ inference model."""

    def __init__(self, artifact_path: str | Path):
        self.artifact_path = Path(artifact_path)
        self._artifact = joblib.load(self.artifact_path)
        self.version = self._artifact["version"]
        self.features = self._artifact["features"]
        self.tracking_cols = self._artifact["tracking_cols"]
        self.min_swings = self._artifact["min_swings"]
        self.reliability_k = self._artifact["reliability_k"]
        self.rv_nonbip = self._artifact["rv_nonbip_constant"]
        self.train_xrv_mean = self._artifact["train_xrv_mean"]
        self.train_xrv_std = self._artifact["train_xrv_std"]
        self.pipe_bip = self._artifact["pipe_bip"]
        self.pipe_pow = self._artifact["pipe_pow"]
        self.filter_thresholds = self._artifact["real_swing_filter"]

    # ----------------------------------------------------------------
    # Step 1: filter pitches to real competitive swings
    # ----------------------------------------------------------------
    def filter_swings(self, pitch_df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply the same competitive-swing filter used during training.
        Drops takes, check-swings, and out-of-range measurements.
        """
        df = pitch_df.copy()
        # bat_speed.notna() filters out non-swings (Statcast only computes
        # bat tracking on real swings)
        df = df[df["bat_speed"].notna() & df["swing_length"].notna()]
        f = self.filter_thresholds
        mask = (
            (df["bat_speed"] >= f["bat_speed_min"]) &
            (df["bat_speed"] <= f["bat_speed_max"]) &
            (df["swing_length"] >= f["swing_length_min"]) &
            (df["swing_length"] <= f["swing_length_max"]) &
            (df["attack_angle"].abs() <= f["attack_angle_abs_max"]) &
            (df["swing_path_tilt"] >= f["swing_path_tilt_min"]) &
            (df["swing_path_tilt"] <= f["swing_path_tilt_max"]) &
            (df["attack_direction"].abs() <= f["attack_direction_abs_max"])
        )
        return df[mask].copy()

    # ----------------------------------------------------------------
    # Step 2: build player-half (or other grouping) profiles
    # ----------------------------------------------------------------
    def build_profiles(self, swing_df: pd.DataFrame,
                       group_by: list[str] | None = None) -> pd.DataFrame:
        """
        Aggregate competitive swings to (batter, group) profiles with the
        mean and std of each tracking column.

        group_by: list of additional columns to group by. Defaults to
                  ["half"] if "half" is present in swing_df, else just
                  groups by batter.
        """
        if group_by is None:
            group_by = ["half"] if "half" in swing_df.columns else []
        keys = ["batter"] + group_by

        # bip flag for downstream rate
        if "type" in swing_df.columns:
            swing_df = swing_df.assign(bip=(swing_df["type"] == "X").astype(int))
        else:
            swing_df = swing_df.assign(bip=0)

        agg = {col: ["mean", "std"] for col in self.tracking_cols}
        profiles = swing_df.groupby(keys).agg(agg)
        profiles.columns = [f"{c}_{stat}" for c, stat in profiles.columns]

        profiles["n_swings"] = swing_df.groupby(keys).size()
        profiles["n_bip"] = swing_df.groupby(keys)["bip"].sum()
        profiles["bip_rate_obs"] = profiles["n_bip"] / profiles["n_swings"]

        profiles = profiles[profiles["n_swings"] >= self.min_swings].reset_index()
        return profiles

    # ----------------------------------------------------------------
    # Step 3: score profiles → Swing+
    # ----------------------------------------------------------------
    def score_profiles(self, profiles: pd.DataFrame,
                       reliability_weight: bool = True) -> pd.DataFrame:
        """
        Apply the fitted models to a profile dataframe to get Swing+ scores.

        Returns the input profiles with these new columns:
          p_bip_pred:        predicted P(BIP)
          rv_bip_pred:       predicted RV given BIP
          xrv_per_swing:     combined expected RV per competitive swing
          swing_plus_raw:    raw Swing+ score (100-centered, sd 10)
          reliability:       weighting toward 100 (only if reliability_weight=True)
          swing_plus:        reliability-weighted Swing+ (if requested)
        """
        df = profiles.copy()
        missing = [c for c in self.features if c not in df.columns]
        if missing:
            raise ValueError(f"Missing feature columns: {missing}")
        df = df.dropna(subset=self.features)

        X = df[self.features].values
        df["p_bip_pred"] = np.clip(self.pipe_bip.predict(X), 0, 1)
        df["rv_bip_pred"] = self.pipe_pow.predict(X)
        df["xrv_per_swing"] = (
            df["p_bip_pred"] * df["rv_bip_pred"]
            + (1 - df["p_bip_pred"]) * self.rv_nonbip
        )
        # Scale using training-time mean/std for stable, comparable scores
        df["swing_plus_raw"] = 100 + (
            (df["xrv_per_swing"] - self.train_xrv_mean) / self.train_xrv_std * 10
        )

        if reliability_weight:
            w = df["n_swings"] / (df["n_swings"] + self.reliability_k)
            df["reliability"] = w
            df["swing_plus"] = w * df["swing_plus_raw"] + (1 - w) * 100
        else:
            df["swing_plus"] = df["swing_plus_raw"]

        return df

    # ----------------------------------------------------------------
    # Combined pipeline: pitch data → leaderboard
    # ----------------------------------------------------------------
    def score_pitch_level(self, pitch_df: pd.DataFrame,
                          group_by: list[str] | None = None,
                          reliability_weight: bool = True) -> pd.DataFrame:
        """
        Full pipeline: pitch-level Statcast data → ranked leaderboard.
        """
        swings = self.filter_swings(pitch_df)
        profiles = self.build_profiles(swings, group_by=group_by)
        scored = self.score_profiles(profiles, reliability_weight=reliability_weight)
        return scored.sort_values("swing_plus", ascending=False).reset_index(drop=True)


# ----------------------------------------------------------------
# CLI for quick verification: python swing_plus.py path/to/pitches.parquet
# ----------------------------------------------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python swing_plus.py <artifact.joblib> <pitches.parquet>")
        sys.exit(1)
    model = SwingPlusModel(sys.argv[1])
    pitch_df = pd.read_parquet(sys.argv[2])
    print(f"Loaded model v{model.version}, {len(pitch_df):,} pitches")
    leaderboard = model.score_pitch_level(pitch_df)
    print(f"\nLeaderboard: {len(leaderboard)} qualifying players")
    print(leaderboard.head(20)[["batter", "n_swings", "swing_plus", "reliability"]]
          .to_string(index=False))
