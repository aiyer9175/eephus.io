# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
02_features.py - Aggregate pitch-level Statcast to player-half-season swing profiles.

Key decisions documented inline:
- "Competitive swing" = bat_speed is populated AND swing_length is populated.
  Statcast only computes these on real swings, so this filter cleanly drops
  takes, bunts, check-swings the system rejected.
- Min 180 competitive swings per half (matches Driveline's threshold from
  Cronbach's alpha reliability analysis).
- Target = mean xwOBA on batted balls (xwOBAcon). Computed as the average of
  estimated_woba_using_speedangle on rows where type == 'X' (ball in play).
- Features = means of each tracking metric on competitive swings, plus a few
  spread terms (SD) to capture consistency.
"""

import pandas as pd
import numpy as np

MIN_SWINGS = 180

# Statcast bat tracking columns we care about.
TRACKING_COLS = [
    "bat_speed",
    "swing_length",
    "attack_angle",
    "attack_direction",
    "swing_path_tilt",
    "intercept_ball_minus_batter_pos_x_inches",  # depth-of-contact lateral
    "intercept_ball_minus_batter_pos_y_inches",  # depth-of-contact toward mound
]


def filter_competitive(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows where Statcast computed bat tracking (real swings)."""
    mask = df["bat_speed"].notna() & df["swing_length"].notna()
    return df.loc[mask].copy()


def build_player_profiles(df: pd.DataFrame, half_label: str) -> pd.DataFrame:
    """One row per batter for this half-season."""
    swings = filter_competitive(df)

    # Aggregate tracking features (mean + SD per batter).
    agg_dict = {col: ["mean", "std"] for col in TRACKING_COLS}
    profiles = swings.groupby("batter").agg(agg_dict)
    profiles.columns = [f"{c}_{stat}" for c, stat in profiles.columns]

    # Swing volume and contact-rate features.
    profiles["n_swings"] = swings.groupby("batter").size()
    bip_mask = swings["type"] == "X"
    profiles["n_bip"] = swings.loc[bip_mask].groupby("batter").size()
    profiles["bip_rate"] = profiles["n_bip"] / profiles["n_swings"]

    # Target: mean xwOBA on contact.
    bip = swings.loc[bip_mask & swings["estimated_woba_using_speedangle"].notna()]
    profiles["xwobacon"] = bip.groupby("batter")["estimated_woba_using_speedangle"].mean()
    profiles["n_xwoba_balls"] = bip.groupby("batter").size()

    # Apply minimum reliability filter.
    profiles = profiles[profiles["n_swings"] >= MIN_SWINGS]
    profiles["half"] = half_label
    return profiles.reset_index()


def combine_halves(half_dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    parts = [build_player_profiles(df, label) for label, df in half_dfs.items()]
    return pd.concat(parts, ignore_index=True)


if __name__ == "__main__":
    # Smoke test on a single cached half.
    df = pd.read_parquet("data/raw/statcast_2024_H2.parquet")
    profiles = build_player_profiles(df, "2024_H2")
    print(f"Players passing {MIN_SWINGS}-swing filter: {len(profiles)}")
    print(f"\nFeature columns: {[c for c in profiles.columns if c.endswith('_mean')]}")
    print(f"\nTop 5 by xwOBAcon:")
    print(profiles.nlargest(5, "xwobacon")[["batter", "n_swings", "xwobacon", "bat_speed_mean"]])
