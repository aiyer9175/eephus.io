# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
10_partial_dependence.py - How much is Swing+ driven by bat speed vs the path features?

Three diagnostics:
1. Partial dependence: hold all other features at their mean, vary bat speed and
   attack angle independently. Plot the response surface. If Swing+ moves a lot
   with bat speed and little with attack angle, the metric is "bat speed in a
   trench coat".
2. Feature importance via permutation: how much CV R² drops when each feature's
   values are shuffled. Less arbitrary than coefficient magnitudes (which depend
   on scale and multicollinearity).
3. Counterfactual: take Jo Adell's profile, swap his attack angle to Wallner's,
   recompute. How much does his Swing+ change?

If diagnostic 1 shows a steep bat-speed gradient and shallow attack-angle gradient,
the concern is real and the fix is re-weighting (not necessarily new features).
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.inspection import permutation_importance

profiles = pd.read_parquet("data/processed/profiles_adjusted.parquet")

FEATURES = [
    "bat_speed_mean", "swing_length_mean", "attack_angle_mean",
    "attack_direction_mean", "swing_path_tilt_mean",
    "intercept_ball_minus_batter_pos_x_inches_mean",
    "intercept_ball_minus_batter_pos_y_inches_mean",
    "bat_speed_std", "attack_angle_std",
]

# Build the same two models 07 built. Need rv_nonbip from pitch data.
swings_list = []
for label in ["2023_H2","2024_H1","2024_H2","2025_H1","2025_H2"]:
    s = pd.read_parquet(f"data/raw/statcast_{label}.parquet")
    s = s[s["bat_speed"].notna() & s["swing_length"].notna()].copy()
    s["bip"] = (s["type"] == "X").astype(int)
    swings_list.append(s[["delta_run_exp","bip"]])
allsw = pd.concat(swings_list, ignore_index=True)
rv_nonbip = allsw.loc[allsw["bip"]==0, "delta_run_exp"].mean()


def make_pipe():
    return Pipeline([
        ("scale", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, include_bias=False)),
        ("ridge", RidgeCV(alphas=(0.1, 1.0, 10.0, 100.0))),
    ])


d = profiles.dropna(subset=FEATURES + ["bip_rate", "rv_given_bip_adj"]).copy()
X = d[FEATURES].values

pipe_bip = make_pipe().fit(X, d["bip_rate"])
pipe_pow = make_pipe().fit(X, d["rv_given_bip_adj"])

def compute_swing_plus(rows):
    """Vectorized Swing+ for an array of feature rows."""
    p = np.clip(pipe_bip.predict(rows), 0, 1)
    rv = pipe_pow.predict(rows)
    xrv = p * rv + (1 - p) * rv_nonbip
    sigma = d.apply(lambda r: None, axis=1)  # placeholder
    # Use empirical league-level mean+sd from the full training set
    p_all = np.clip(pipe_bip.predict(X), 0, 1)
    rv_all = pipe_pow.predict(X)
    xrv_all = p_all * rv_all + (1 - p_all) * rv_nonbip
    mu, sig = xrv_all.mean(), xrv_all.std()
    return 100 + (xrv - mu) / sig * 10


# ----------------------------------------------------------------------
# Diagnostic 1: PARTIAL DEPENDENCE on bat speed and attack angle
# ----------------------------------------------------------------------
print("=" * 72)
print("Diagnostic 1: Partial dependence")
print("=" * 72)

# Base profile = league mean for everything
base = d[FEATURES].mean().to_dict()
print("\nLeague-mean baseline profile:")
for f, v in base.items():
    print(f"  {f:<55} = {v:.3f}")

# Sweep bat speed from 60 to 80 (typical range), hold others at mean
bs_grid = np.linspace(60, 80, 21)
bs_rows = np.tile([base[f] for f in FEATURES], (len(bs_grid), 1))
bs_idx = FEATURES.index("bat_speed_mean")
bs_rows[:, bs_idx] = bs_grid
bs_response = compute_swing_plus(bs_rows)

# Sweep attack angle from -5 to 25, hold others at mean
aa_grid = np.linspace(-5, 25, 21)
aa_rows = np.tile([base[f] for f in FEATURES], (len(aa_grid), 1))
aa_idx = FEATURES.index("attack_angle_mean")
aa_rows[:, aa_idx] = aa_grid
aa_response = compute_swing_plus(aa_rows)

print(f"\nBAT SPEED partial dependence (all other features at league mean):")
print(f"{'Bat speed':>10} | {'Swing+':>8}")
for bs, sp in zip(bs_grid, bs_response):
    bar = "█" * int(max(0, (sp - 75) / 1.5))
    print(f"{bs:>10.1f} | {sp:>8.1f} {bar}")

print(f"\nBat speed range: {bs_response.min():.1f} - {bs_response.max():.1f}")
print(f"Swing+ swing over 20 mph of bat speed: {bs_response.max() - bs_response.min():.1f} points")

print(f"\nATTACK ANGLE partial dependence (all other features at league mean):")
print(f"{'Att. angle':>10} | {'Swing+':>8}")
for aa, sp in zip(aa_grid, aa_response):
    bar = "█" * int(max(0, (sp - 90) / 0.8))
    print(f"{aa:>10.1f} | {sp:>8.1f} {bar}")

print(f"\nAttack angle range: {aa_response.min():.1f} - {aa_response.max():.1f}")
print(f"Swing+ swing over 30° of attack angle: {aa_response.max() - aa_response.min():.1f} points")

# The honest comparison: how big a swing in each dimension matters?
# Bat speed standard deviation in the data:
bs_sd = d["bat_speed_mean"].std()
aa_sd = d["attack_angle_mean"].std()
print(f"\nLeague SD: bat_speed = {bs_sd:.2f} mph, attack_angle = {aa_sd:.2f}°")

# Swing+ per 1-SD change
def sp_at(feature, delta_in_sd, base_dict):
    row = np.array([base_dict[f] for f in FEATURES])
    sd = d[feature].std()
    idx = FEATURES.index(feature)
    row[idx] = base_dict[feature] + delta_in_sd * sd
    return compute_swing_plus(row.reshape(1, -1))[0]

sp_baseline = compute_swing_plus(np.array([base[f] for f in FEATURES]).reshape(1,-1))[0]
print(f"\nSwing+ at league-mean profile: {sp_baseline:.1f}")
print(f"Swing+ at +1 SD bat speed:     {sp_at('bat_speed_mean', 1, base):.1f}  (delta: {sp_at('bat_speed_mean',1,base) - sp_baseline:+.1f})")
print(f"Swing+ at +1 SD attack angle:  {sp_at('attack_angle_mean', 1, base):.1f}  (delta: {sp_at('attack_angle_mean',1,base) - sp_baseline:+.1f})")
print(f"Swing+ at +1 SD swing length:  {sp_at('swing_length_mean', 1, base):.1f}  (delta: {sp_at('swing_length_mean',1,base) - sp_baseline:+.1f})")
print(f"Swing+ at +1 SD tilt:          {sp_at('swing_path_tilt_mean', 1, base):.1f}  (delta: {sp_at('swing_path_tilt_mean',1,base) - sp_baseline:+.1f})")


# ----------------------------------------------------------------------
# Diagnostic 2: PERMUTATION IMPORTANCE
# ----------------------------------------------------------------------
print("\n" + "=" * 72)
print("Diagnostic 2: Permutation feature importance")
print("=" * 72)
print("How much CV R² drops when each feature is shuffled (kills its signal)")
print()

for target_label, target_col, pipe in [("P(BIP)", "bip_rate", pipe_bip),
                                         ("RV|BIP", "rv_given_bip_adj", pipe_pow)]:
    y = d[target_col].values
    pi = permutation_importance(pipe, X, y, n_repeats=10, random_state=42, scoring="r2")
    imp = pd.Series(pi.importances_mean, index=FEATURES).sort_values(ascending=False)
    print(f"\n{target_label} model permutation importance:")
    for f, v in imp.items():
        bar = "█" * max(1, int(v * 400)) if v > 0 else ""
        print(f"  {f:<55} {v:>+.4f} {bar}")


# ----------------------------------------------------------------------
# Diagnostic 3: COUNTERFACTUAL — swap Adell's attack angle to Wallner's
# ----------------------------------------------------------------------
print("\n" + "=" * 72)
print("Diagnostic 3: Counterfactual swaps")
print("=" * 72)

graded = pd.read_parquet("data/processed/bat_plus_comparison.parquet")
profs_2025 = profiles[profiles["half"].isin(["2025_H1","2025_H2"])].copy()

# Aggregate to season for these specific players (swing-weighted means)
def get_2025_profile(name_substr, profiles_df):
    """Find a player's 2025 swing-weighted profile."""
    from pybaseball import playerid_reverse_lookup
    # Pull all batter IDs in 2025 and reverse-lookup
    all_b = profiles_df["batter"].unique().tolist()
    names = playerid_reverse_lookup(all_b, key_type="mlbam")
    names["full"] = names["name_first"].str.lower() + " " + names["name_last"].str.lower()
    matches = names[names["full"].str.contains(name_substr.lower())]
    if len(matches) == 0:
        return None
    batter_id = matches.iloc[0]["key_mlbam"]
    sub = profiles_df[profiles_df["batter"] == batter_id]
    if len(sub) == 0:
        return None
    # Swing-weighted means
    w = sub["n_swings"].values
    row = {}
    for f in FEATURES + ["bip_rate", "rv_given_bip_adj", "n_swings"]:
        if f in sub.columns:
            vals = sub[f].values
            row[f] = float(np.average(vals, weights=w)) if f != "n_swings" else int(w.sum())
    return row, batter_id, matches.iloc[0]["name_first"] + " " + matches.iloc[0]["name_last"]

adell_data = get_2025_profile("adell", profs_2025)
wallner_data = get_2025_profile("wallner", profs_2025)
wood_data = get_2025_profile("wood", profs_2025)
kurtz_data = get_2025_profile("kurtz", profs_2025)

if adell_data and wallner_data:
    adell, _, _ = adell_data
    wallner, _, _ = wallner_data

    print(f"\nADELL 2025 vs WALLNER 2025 profiles:")
    print(f"{'feature':<55}{'Adell':>10}{'Wallner':>10}")
    for f in FEATURES:
        print(f"  {f:<53}{adell[f]:>10.2f}{wallner[f]:>10.2f}")

    # Compute Swing+ for both
    adell_row = np.array([adell[f] for f in FEATURES]).reshape(1,-1)
    wallner_row = np.array([wallner[f] for f in FEATURES]).reshape(1,-1)
    adell_sp = compute_swing_plus(adell_row)[0]
    wallner_sp = compute_swing_plus(wallner_row)[0]
    print(f"\nSwing+ — Adell: {adell_sp:.1f},  Wallner: {wallner_sp:.1f}")

    # Counterfactual 1: give Adell Wallner's attack angle
    adell_swap = adell_row.copy()
    aa_i = FEATURES.index("attack_angle_mean")
    adell_swap[0, aa_i] = wallner["attack_angle_mean"]
    sp_adell_aa_swap = compute_swing_plus(adell_swap)[0]
    print(f"\nCounterfactual: Adell with Wallner's 11.4° attack angle (was 7.8°):")
    print(f"  Swing+: {adell_sp:.1f} -> {sp_adell_aa_swap:.1f}  (delta: {sp_adell_aa_swap - adell_sp:+.1f})")

    # Counterfactual 2: give Wallner Adell's bat speed
    wallner_swap = wallner_row.copy()
    bs_i = FEATURES.index("bat_speed_mean")
    wallner_swap[0, bs_i] = adell["bat_speed_mean"]
    sp_wallner_bs_swap = compute_swing_plus(wallner_swap)[0]
    print(f"\nCounterfactual: Wallner with Adell's 75.3 mph bat speed (was 74.4):")
    print(f"  Swing+: {wallner_sp:.1f} -> {sp_wallner_bs_swap:.1f}  (delta: {sp_wallner_bs_swap - wallner_sp:+.1f})")

    # Counterfactual 3: full swap of path features (attack angle + tilt + intercept)
    adell_pathswap = adell_row.copy()
    for pf in ["attack_angle_mean", "swing_path_tilt_mean", "swing_length_mean",
               "intercept_ball_minus_batter_pos_x_inches_mean",
               "intercept_ball_minus_batter_pos_y_inches_mean"]:
        i = FEATURES.index(pf)
        adell_pathswap[0, i] = wallner[pf]
    sp_adell_full = compute_swing_plus(adell_pathswap)[0]
    print(f"\nCounterfactual: Adell with Wallner's FULL path geometry (keep Adell's bat speed):")
    print(f"  Swing+: {adell_sp:.1f} -> {sp_adell_full:.1f}  (delta: {sp_adell_full - adell_sp:+.1f})")
EOF
