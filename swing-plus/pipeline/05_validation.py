# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
05_validation.py - Does Bat+ measure skill or noise?

Three tests, in order of how seriously you should take them:

1. Half-to-half stability (within-player): regress H_{t+1} Bat+ on H_t Bat+
   for players appearing in consecutive halves. r > 0.7 = real skill,
   0.5-0.7 = mixed, < 0.5 = mostly noise.

2. Year-over-year stability: same idea but full-year averages.

3. Discrimination: do Bat+ tiers actually predict next-half wOBA/xwOBA?
   This is the "does it matter" test. A stable but meaningless metric
   (like player height) would pass test 1 but fail test 3.
"""

import pandas as pd
import numpy as np
from scipy.stats import pearsonr, spearmanr

HALVES_ORDER = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]

graded = pd.read_parquet("data/processed/bat_plus_grades.parquet")
print(f"Total player-halves graded: {len(graded)}")
print(f"Unique batters: {graded['batter'].nunique()}")


# -------- Test 1: Consecutive-half stability --------

def consecutive_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """For each player, pair each half with their next half."""
    pairs = []
    df = df.sort_values(["batter", "half"])
    for batter, group in df.groupby("batter"):
        halves_present = group["half"].tolist()
        for i in range(len(halves_present) - 1):
            h1, h2 = halves_present[i], halves_present[i + 1]
            # Only consider truly consecutive halves
            idx1 = HALVES_ORDER.index(h1)
            idx2 = HALVES_ORDER.index(h2)
            if idx2 - idx1 != 1:
                continue
            row1 = group[group["half"] == h1].iloc[0]
            row2 = group[group["half"] == h2].iloc[0]
            pairs.append({
                "batter": batter,
                "h1": h1, "h2": h2,
                "bat_plus_t": row1["bat_plus"],
                "bat_plus_t1": row2["bat_plus"],
                "p_bip_t": row1["p_bip_pred"],
                "p_bip_t1": row2["p_bip_pred"],
                "rv_bip_t": row1["rv_bip_pred"],
                "rv_bip_t1": row2["rv_bip_pred"],
            })
    return pd.DataFrame(pairs)


pairs = consecutive_pairs(graded)
print(f"\n=== Test 1: Consecutive half-to-half stability ===")
print(f"Player-pairs of consecutive halves: {len(pairs)}")

r_bat, _ = pearsonr(pairs["bat_plus_t"], pairs["bat_plus_t1"])
r_pbip, _ = pearsonr(pairs["p_bip_t"], pairs["p_bip_t1"])
r_rvbip, _ = pearsonr(pairs["rv_bip_t"], pairs["rv_bip_t1"])
print(f"  Bat+        half-to-half r = {r_bat:.3f}")
print(f"  P(BIP) pred half-to-half r = {r_pbip:.3f}")
print(f"  RV|BIP pred half-to-half r = {r_rvbip:.3f}")
print(f"  (Interpretation: r > 0.7 = stable skill;")
print(f"                    0.5 - 0.7 = real but noisy;")
print(f"                    < 0.5 = mostly noise)")


# -------- Test 2: Discrimination - does Bat+ predict NEXT half's xwOBAcon? --------

print(f"\n=== Test 2: Does Bat+_t predict actual xwOBAcon_t+1? ===")
# Merge in next-half observed xwOBAcon
nxt = graded[["batter", "half", "xwobacon_obs", "rv_per_swing_obs"]].copy()
nxt = nxt.rename(columns={"xwobacon_obs": "xwoba_t1", "rv_per_swing_obs": "rv_obs_t1"})
nxt_lookup = nxt.set_index(["batter", "half"])

merged = pairs.copy()
merged["xwoba_t1_obs"] = merged.apply(
    lambda r: nxt_lookup.loc[(r["batter"], r["h2"]), "xwoba_t1"] if (r["batter"], r["h2"]) in nxt_lookup.index else np.nan,
    axis=1,
)
merged["rv_t1_obs"] = merged.apply(
    lambda r: nxt_lookup.loc[(r["batter"], r["h2"]), "rv_obs_t1"] if (r["batter"], r["h2"]) in nxt_lookup.index else np.nan,
    axis=1,
)

m = merged.dropna(subset=["xwoba_t1_obs"])
r_xwoba, _ = pearsonr(m["bat_plus_t"], m["xwoba_t1_obs"])
r_rv, _ = pearsonr(m["bat_plus_t"], m["rv_t1_obs"])
print(f"  Bat+_t -> observed xwOBAcon_t+1:   r = {r_xwoba:.3f}")
print(f"  Bat+_t -> observed RV/swing_t+1:   r = {r_rv:.3f}")

# Compare against just using observed xwoba_t (the dumb baseline)
m_full = merged.dropna(subset=["xwoba_t1_obs"]).copy()
m_full["xwoba_t_obs"] = m_full.apply(
    lambda r: nxt_lookup.loc[(r["batter"], r["h1"]), "xwoba_t1"] if (r["batter"], r["h1"]) in nxt_lookup.index else np.nan,
    axis=1,
)
m_full = m_full.dropna(subset=["xwoba_t_obs"])
r_baseline, _ = pearsonr(m_full["xwoba_t_obs"], m_full["xwoba_t1_obs"])
r_batplus_pred, _ = pearsonr(m_full["bat_plus_t"], m_full["xwoba_t1_obs"])
print(f"\n  Baseline (just use last half's xwOBAcon to predict next):")
print(f"    xwOBAcon_t -> xwOBAcon_t+1:  r = {r_baseline:.3f}")
print(f"    Bat+_t      -> xwOBAcon_t+1: r = {r_batplus_pred:.3f}")
print(f"  (Bat+ should beat or match this. If it loses badly, it's not")
print(f"   adding information beyond observed contact quality.)")


# -------- Test 3: Tier discrimination --------

print(f"\n=== Test 3: Bat+ tier vs next-half outcomes ===")
m_full["bat_plus_tier"] = pd.qcut(m_full["bat_plus_t"], q=5, labels=["Q1 (low)", "Q2", "Q3", "Q4", "Q5 (high)"])
tier_summary = m_full.groupby("bat_plus_tier", observed=True).agg(
    n=("batter", "size"),
    mean_bat_plus_t=("bat_plus_t", "mean"),
    mean_xwoba_t1=("xwoba_t1_obs", "mean"),
    mean_rv_t1=("rv_t1_obs", "mean"),
)
print(tier_summary.to_string())


# -------- Save full results for inspection --------
pairs.to_parquet("data/processed/stability_pairs.parquet")
print(f"\nSaved {len(pairs)} pairs -> data/processed/stability_pairs.parquet")
