# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
09_leaderboard.py - Production leaderboard for Bat+.

Three views, in order of usefulness:
1. Player-half: every (batter, half) row with Bat+ and components.
2. Player-season: half-season rollup, weighted by swing count.
3. Player-career (within sample): all halves combined.

Reliability weighting:
- A player with 1200 swings has a more reliable Bat+ than one with 200.
- We regress toward the mean (100) by 1 - n/(n + k), where k is the
  half-swing count at which we trust the estimate ~50%.
- k=180 (our floor) gives 50% weight at the minimum threshold. Use 360
  (a full season for a partial player) - players above that get >67% weight.

Notes on what this is and isn't:
- This is a SWING-PATH grade. It does not equal hitting value. A player
  with elite plate discipline who rarely swings can have a mediocre Bat+
  and still be productive. Use Bat+ alongside other metrics, not instead.
- Reliability k=360 is a choice, not a derived value. Robert Orr / SIS
  publish their reliability work but the exact constants differ. Document
  yours and stick with it.
"""

import pandas as pd
import numpy as np
from pybaseball import playerid_reverse_lookup
from pathlib import Path

# ---------- Config ----------
RELIABILITY_K = 360  # swings at which Bat+ gets ~67% weight; rest goes to 100
HALVES_ORDER = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
SEASONS = {"2024": ["2024_H1", "2024_H2"], "2025": ["2025_H1", "2025_H2"]}

# ---------- Load adjusted grades ----------

# We need to rebuild the graded frame from 07_adjusted_model output and
# bring in n_swings for the reliability weighting.
profiles = pd.read_parquet("data/processed/profiles_adjusted.parquet")
comparison = pd.read_parquet("data/processed/bat_plus_comparison.parquet")

# Use the adjusted Bat+ from 07; that's our production metric.
graded = comparison.merge(
    profiles[["batter", "half", "n_swings", "n_bip", "xwobacon_obs",
              "bat_speed_mean", "attack_angle_mean", "swing_length_mean"]],
    on=["batter", "half"], how="left",
)
graded = graded.rename(columns={"bat_plus_adj": "bat_plus"})


# ---------- Reliability weighting ----------

def regress_to_mean(bp_raw: pd.Series, n: pd.Series, k: int = RELIABILITY_K,
                    pop_mean: float = 100.0) -> pd.Series:
    """Empirical-Bayes-style shrinkage toward population mean."""
    weight = n / (n + k)
    return weight * bp_raw + (1 - weight) * pop_mean


graded["bat_plus_reliable"] = regress_to_mean(graded["bat_plus"], graded["n_swings"])
graded["reliability_weight"] = graded["n_swings"] / (graded["n_swings"] + RELIABILITY_K)


# ---------- Attach player names (all unique IDs) ----------

all_ids = graded["batter"].unique().tolist()
print(f"Looking up names for {len(all_ids)} unique batters...")
name_table = playerid_reverse_lookup(all_ids, key_type="mlbam")
name_table["name"] = (
    name_table["name_first"].str.title() + " " + name_table["name_last"].str.title()
)
name_map = dict(zip(name_table["key_mlbam"], name_table["name"]))
graded["name"] = graded["batter"].map(name_map)


# ---------- View 1: Player-half ----------

view_half = graded[[
    "name", "batter", "half", "stand",
    "bat_plus", "bat_plus_reliable",
    "n_swings", "n_bip", "reliability_weight",
    "p_bip_adj", "rv_bip_adj",
    "bat_speed_mean", "attack_angle_mean", "swing_length_mean",
    "xwobacon_obs",
]].sort_values("bat_plus_reliable", ascending=False).reset_index(drop=True)

view_half.to_parquet("data/processed/leaderboard_half.parquet")
view_half.to_csv("data/processed/leaderboard_half.csv", index=False)


# ---------- View 2: Player-season (swing-weighted) ----------

def aggregate_to_season(df: pd.DataFrame, season_halves: list[str], season: str) -> pd.DataFrame:
    """Swing-weighted average of Bat+ across the two halves of a season."""
    sub = df[df["half"].isin(season_halves)].copy()
    grouped = sub.groupby(["batter", "name", "stand"]).agg(
        n_swings_season=("n_swings", "sum"),
        n_bip_season=("n_bip", "sum"),
        # Swing-weighted Bat+
        bat_plus_raw=("bat_plus", lambda x: np.average(
            x, weights=sub.loc[x.index, "n_swings"])),
        # Components
        p_bip=("p_bip_adj", lambda x: np.average(
            x, weights=sub.loc[x.index, "n_swings"])),
        rv_bip=("rv_bip_adj", lambda x: np.average(
            x, weights=sub.loc[x.index, "n_swings"])),
        bat_speed=("bat_speed_mean", lambda x: np.average(
            x, weights=sub.loc[x.index, "n_swings"])),
        attack_angle=("attack_angle_mean", lambda x: np.average(
            x, weights=sub.loc[x.index, "n_swings"])),
        n_halves=("half", "count"),
    ).reset_index()
    grouped["bat_plus"] = regress_to_mean(
        grouped["bat_plus_raw"], grouped["n_swings_season"])
    grouped["season"] = season
    return grouped


season_views = []
for season, halves in SEASONS.items():
    s = aggregate_to_season(graded, halves, season)
    season_views.append(s)
view_season = pd.concat(season_views, ignore_index=True)
view_season = view_season.sort_values(["season", "bat_plus"], ascending=[True, False])
view_season.to_parquet("data/processed/leaderboard_season.parquet")
view_season.to_csv("data/processed/leaderboard_season.csv", index=False)


# ---------- View 3: Full sample (all 5 halves) ----------

view_all = graded.groupby(["batter", "name", "stand"]).agg(
    n_swings_total=("n_swings", "sum"),
    n_halves=("half", "count"),
    bat_plus_raw=("bat_plus", lambda x: np.average(
        x, weights=graded.loc[x.index, "n_swings"])),
    p_bip=("p_bip_adj", lambda x: np.average(
        x, weights=graded.loc[x.index, "n_swings"])),
    rv_bip=("rv_bip_adj", lambda x: np.average(
        x, weights=graded.loc[x.index, "n_swings"])),
    bat_speed=("bat_speed_mean", lambda x: np.average(
        x, weights=graded.loc[x.index, "n_swings"])),
    attack_angle=("attack_angle_mean", lambda x: np.average(
        x, weights=graded.loc[x.index, "n_swings"])),
).reset_index()
view_all["bat_plus"] = regress_to_mean(view_all["bat_plus_raw"], view_all["n_swings_total"])
view_all = view_all.sort_values("bat_plus", ascending=False).reset_index(drop=True)
view_all.to_parquet("data/processed/leaderboard_alltime.parquet")
view_all.to_csv("data/processed/leaderboard_alltime.csv", index=False)


# ---------- Print summaries ----------

print(f"\n{'='*72}")
print(f"BAT+ LEADERBOARD: Full sample (2023 H2 - 2025 H2)")
print(f"Reliability weighted toward 100 with k={RELIABILITY_K}")
print(f"{'='*72}\n")

cols = ["name", "stand", "bat_plus", "n_swings_total", "n_halves",
        "p_bip", "rv_bip", "bat_speed", "attack_angle"]
fmt = view_all.head(25)[cols].copy()
fmt["bat_plus"] = fmt["bat_plus"].round(1)
fmt["p_bip"] = fmt["p_bip"].round(3)
fmt["rv_bip"] = fmt["rv_bip"].round(3)
fmt["bat_speed"] = fmt["bat_speed"].round(1)
fmt["attack_angle"] = fmt["attack_angle"].round(1)
print("TOP 25:")
print(fmt.to_string(index=False))

print("\nBOTTOM 15:")
fmt2 = view_all.tail(15)[cols].copy()
for c in ["bat_plus", "bat_speed", "attack_angle"]:
    fmt2[c] = fmt2[c].round(1)
for c in ["p_bip", "rv_bip"]:
    fmt2[c] = fmt2[c].round(3)
print(fmt2.to_string(index=False))


print(f"\n{'='*72}")
print(f"2025 SEASON BAT+ LEADERBOARD (Top 20)")
print(f"{'='*72}\n")
s25 = view_season[view_season["season"] == "2025"].head(20).copy()
for c in ["bat_plus", "bat_speed", "attack_angle"]:
    s25[c] = s25[c].round(1)
for c in ["p_bip", "rv_bip"]:
    s25[c] = s25[c].round(3)
print(s25[["name", "stand", "bat_plus", "n_swings_season",
           "p_bip", "rv_bip", "bat_speed", "attack_angle"]].to_string(index=False))


# ---------- Save a clean "ranked" CSV with rank columns ----------
final = view_all.copy()
final["rank_overall"] = final["bat_plus"].rank(method="min", ascending=False).astype(int)
final_2025 = view_season[view_season["season"] == "2025"].copy()
final_2025["rank_2025"] = final_2025["bat_plus"].rank(method="min", ascending=False).astype(int)

final.to_csv("data/processed/leaderboard_alltime.csv", index=False)
final_2025.to_csv("data/processed/leaderboard_2025.csv", index=False)

print(f"\n\nFiles written:")
print(f"  /home/claude/data/processed/leaderboard_alltime.csv ({len(final)} players)")
print(f"  /home/claude/data/processed/leaderboard_2025.csv ({len(final_2025)} players)")
print(f"  /home/claude/data/processed/leaderboard_season.csv (all seasons)")
print(f"  /home/claude/data/processed/leaderboard_half.csv (every player-half row)")
