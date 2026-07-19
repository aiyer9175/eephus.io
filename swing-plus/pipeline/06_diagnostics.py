# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
06_diagnostics.py - Two checks before declaring Phase 1 done.

Test A: Swing-change cohort. Among players whose Bat+ moved a lot between
halves, did their observed xwOBAcon move with it? If yes, Bat+ is tracking
real swing changes, not just persistent player labels. If no, the metric
might be a glorified player ID.

Test B: Feature ablation. How much of the r=0.876 stability comes from
bat_speed alone? Fit Bat+_BS_only (bat speed mean as sole feature) and
compare its stability and predictive performance against full Bat+.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from scipy.stats import pearsonr, spearmanr
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import KFold, cross_val_score

# Load everything we built.
graded = pd.read_parquet("data/processed/bat_plus_grades.parquet")
pairs = pd.read_parquet("data/processed/stability_pairs.parquet")
profiles = pd.read_parquet("data/processed/profiles_all_halves.parquet")

# Reattach observed next-half outcomes to pairs (recompute cleanly).
obs_lookup = graded.set_index(["batter", "half"])[
    ["xwobacon_obs", "rv_per_swing_obs"]
]
pairs = pairs.merge(
    obs_lookup.rename(columns={
        "xwobacon_obs": "xwoba_t_obs",
        "rv_per_swing_obs": "rv_t_obs",
    }),
    left_on=["batter", "h1"], right_index=True, how="left",
).merge(
    obs_lookup.rename(columns={
        "xwobacon_obs": "xwoba_t1_obs",
        "rv_per_swing_obs": "rv_t1_obs",
    }),
    left_on=["batter", "h2"], right_index=True, how="left",
)

# Drop rows missing either side's observed xwOBAcon for fair comparisons.
pairs = pairs.dropna(subset=["xwoba_t_obs", "xwoba_t1_obs"])
print(f"Working with {len(pairs)} consecutive-half pairs with full observed data.\n")


# ============================================================
# TEST A: Swing-change cohort
# ============================================================
print("=" * 64)
print("TEST A: Among players whose Bat+ moved, did xwOBAcon move with it?")
print("=" * 64)

pairs["bat_plus_delta"] = pairs["bat_plus_t1"] - pairs["bat_plus_t"]
pairs["xwoba_delta"] = pairs["xwoba_t1_obs"] - pairs["xwoba_t_obs"]
pairs["abs_bp_delta"] = pairs["bat_plus_delta"].abs()

# Threshold the population into "stable" vs "changed".
# Using the 80th percentile of |delta| as the "changed" cohort.
threshold = pairs["abs_bp_delta"].quantile(0.80)
print(f"\n|Bat+ delta| at 80th percentile: {threshold:.2f}")
print(f"Median |Bat+ delta|:               {pairs['abs_bp_delta'].median():.2f}")
print(f"Max |Bat+ delta|:                  {pairs['abs_bp_delta'].max():.2f}")

stable = pairs[pairs["abs_bp_delta"] < threshold]
changed = pairs[pairs["abs_bp_delta"] >= threshold]

print(f"\nStable cohort:  n = {len(stable):4d}")
print(f"Changed cohort: n = {len(changed):4d}")

# Within each cohort: does delta_BatPlus correlate with delta_xwOBAcon?
# This is THE test - if Bat+ tracks real swing changes, the changed
# cohort should show strong correlation between the two deltas.
r_stable, p_stable = pearsonr(stable["bat_plus_delta"], stable["xwoba_delta"])
r_changed, p_changed = pearsonr(changed["bat_plus_delta"], changed["xwoba_delta"])
r_all, p_all = pearsonr(pairs["bat_plus_delta"], pairs["xwoba_delta"])

print(f"\nCorrelation between Δ Bat+ and Δ xwOBAcon:")
print(f"  All pairs:       r = {r_all:.3f}   (n={len(pairs)},   p={p_all:.1e})")
print(f"  Stable cohort:   r = {r_stable:.3f}   (n={len(stable)},   p={p_stable:.1e})")
print(f"  Changed cohort:  r = {r_changed:.3f}   (n={len(changed)},   p={p_changed:.1e})")
print(f"\n  Interpretation: when the metric says a player's swing got better,")
print(f"  did their actual contact quality also get better? If r > 0.4 in")
print(f"  the 'changed' cohort, Bat+ is capturing real swing changes, not")
print(f"  just persistent player identity.")

# Show the largest movers, both directions.
print(f"\nTop 10 largest POSITIVE Bat+ deltas (and their xwOBAcon deltas):")
top_gain = pairs.nlargest(10, "bat_plus_delta")[
    ["batter", "h1", "h2", "bat_plus_t", "bat_plus_t1",
     "bat_plus_delta", "xwoba_t_obs", "xwoba_t1_obs", "xwoba_delta"]
]
print(top_gain.to_string(index=False))

print(f"\nTop 10 largest NEGATIVE Bat+ deltas:")
top_loss = pairs.nsmallest(10, "bat_plus_delta")[
    ["batter", "h1", "h2", "bat_plus_t", "bat_plus_t1",
     "bat_plus_delta", "xwoba_t_obs", "xwoba_t1_obs", "xwoba_delta"]
]
print(top_loss.to_string(index=False))


# ============================================================
# TEST B: Feature ablation - bat speed only vs full feature set
# ============================================================
print("\n" + "=" * 64)
print("TEST B: How much does the full feature set add over bat speed alone?")
print("=" * 64)

FULL_FEATURES = [
    "bat_speed_mean", "swing_length_mean", "attack_angle_mean",
    "attack_direction_mean", "swing_path_tilt_mean",
    "intercept_ball_minus_batter_pos_x_inches_mean",
    "intercept_ball_minus_batter_pos_y_inches_mean",
    "bat_speed_std", "attack_angle_std",
]
BS_ONLY = ["bat_speed_mean"]


def make_pipe(degree: int = 2) -> Pipeline:
    return Pipeline([
        ("scale", StandardScaler()),
        ("poly", PolynomialFeatures(degree=degree, include_bias=False)),
        ("ridge", RidgeCV(alphas=(0.1, 1.0, 10.0, 100.0))),
    ])


def fit_score_two_models(profiles_df, feature_cols, label):
    df = profiles_df.dropna(subset=feature_cols + ["bip_rate", "rv_given_bip"]).copy()

    X = df[feature_cols].values
    cv = KFold(n_splits=5, shuffle=True, random_state=42)

    pipe_bip = make_pipe()
    r2_bip = cross_val_score(pipe_bip, X, df["bip_rate"], cv=cv, scoring="r2")
    pipe_bip.fit(X, df["bip_rate"])

    pipe_pow = make_pipe()
    r2_pow = cross_val_score(pipe_pow, X, df["rv_given_bip"], cv=cv, scoring="r2")
    pipe_pow.fit(X, df["rv_given_bip"])

    print(f"\n[{label}] features: {len(feature_cols)}")
    print(f"  P(BIP)   CV R² = {r2_bip.mean():.3f} (±{r2_bip.std():.3f})")
    print(f"  RV|BIP   CV R² = {r2_pow.mean():.3f} (±{r2_pow.std():.3f})")
    return pipe_bip, pipe_pow, df


# Need rv_given_bip on profiles - we already saved it via 04_driveline.
# But the saved profiles_all_halves doesn't have it. Recompute.
print("\nReloading pitch data to recompute rv_given_bip on profiles...")
swings_list = []
for label in ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]:
    s = pd.read_parquet(f"data/raw/statcast_{label}.parquet")
    s = s[s["bat_speed"].notna() & s["swing_length"].notna()].copy()
    s["half"] = label
    s["bip"] = (s["type"] == "X").astype(int)
    swings_list.append(s)
swings = pd.concat(swings_list, ignore_index=True)
rv_given_bip = (
    swings[swings["bip"] == 1]
    .groupby(["batter", "half"])["delta_run_exp"].mean()
    .rename("rv_given_bip")
)
profiles_with_rv = profiles.merge(rv_given_bip, on=["batter", "half"], how="left")
rv_nonbip = swings.loc[swings["bip"] == 0, "delta_run_exp"].mean()

# Fit both models.
bip_full, pow_full, df_full = fit_score_two_models(
    profiles_with_rv, FULL_FEATURES, "FULL FEATURES")
bip_bs, pow_bs, df_bs = fit_score_two_models(
    profiles_with_rv, BS_ONLY, "BAT-SPEED ONLY")


def compute_bat_plus(df_in, feature_cols, pipe_bip, pipe_pow, rv_nonbip):
    X = df_in[feature_cols].values
    p_bip = np.clip(pipe_bip.predict(X), 0.0, 1.0)
    rv_bip = pipe_pow.predict(X)
    xrv = p_bip * rv_bip + (1 - p_bip) * rv_nonbip
    return 100 + (xrv - xrv.mean()) / xrv.std() * 10


# Score both versions on all profiles.
clean = profiles_with_rv.dropna(subset=FULL_FEATURES).copy()
clean["bat_plus_full"] = compute_bat_plus(
    clean, FULL_FEATURES, bip_full, pow_full, rv_nonbip)
clean["bat_plus_bs"] = compute_bat_plus(
    clean, BS_ONLY, bip_bs, pow_bs, rv_nonbip)


# Stability comparison.
def stability(df, col):
    """r between consecutive halves for the given Bat+ column."""
    HALVES_ORDER = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
    pairs_data = []
    d = df.sort_values(["batter", "half"])
    for batter, g in d.groupby("batter"):
        halves_present = g["half"].tolist()
        for i in range(len(halves_present) - 1):
            i1 = HALVES_ORDER.index(halves_present[i])
            i2 = HALVES_ORDER.index(halves_present[i + 1])
            if i2 - i1 != 1:
                continue
            r1 = g[g["half"] == halves_present[i]][col].iloc[0]
            r2 = g[g["half"] == halves_present[i + 1]][col].iloc[0]
            pairs_data.append((r1, r2))
    arr = np.array(pairs_data)
    return pearsonr(arr[:, 0], arr[:, 1])[0], len(pairs_data)


r_full, n_full = stability(clean, "bat_plus_full")
r_bs, n_bs = stability(clean, "bat_plus_bs")

print(f"\nStability (half-to-half r):")
print(f"  Full Bat+:           r = {r_full:.3f}  (n={n_full})")
print(f"  Bat speed only Bat+: r = {r_bs:.3f}  (n={n_bs})")
print(f"  Difference: {r_full - r_bs:+.3f}")

# Correlation between the two metrics - how distinct are they really?
r_overlap, _ = pearsonr(clean["bat_plus_full"], clean["bat_plus_bs"])
print(f"\nCorrelation between Full and Bat-speed-only Bat+: r = {r_overlap:.3f}")
print(f"  (If r ≈ 1.0, the path features add nothing - bat speed IS the metric.")
print(f"   If r < 0.85, the path features are doing real distinctive work.)")

# Show where they disagree most - which players does the path-based model
# reward over the bat-speed-only baseline?
clean["delta"] = clean["bat_plus_full"] - clean["bat_plus_bs"]
print(f"\nLargest path-bonus players (Full Bat+ much higher than bat speed alone):")
print(clean.nlargest(10, "delta")[
    ["batter", "half", "bat_plus_full", "bat_plus_bs", "delta", "bat_speed_mean"]
].to_string(index=False))

print(f"\nLargest path-penalty players (Full Bat+ much lower than bat speed alone):")
print(clean.nsmallest(10, "delta")[
    ["batter", "half", "bat_plus_full", "bat_plus_bs", "delta", "bat_speed_mean"]
].to_string(index=False))
