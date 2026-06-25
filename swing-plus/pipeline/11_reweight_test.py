# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
11_reweight_test.py - Path B diagnostic: can we close the gap to Driveline
                      just by downweighting bat speed, without new features?

Approach: instead of a single Ridge regularizer, use feature-specific
penalties. Apply a heavier penalty to bat_speed terms (linear + all
polynomial cross-terms involving bat_speed). This forces the model to
lean on other features for signal where they exist.

If after downweighting:
  - Wallner / Wood / Acuña / Cruz climb meaningfully
  - Adell / Stanton fall
  - Top of board remains plausible (Judge, Kurtz, Ohtani, Schwarber stay top)
... then the issue is coefficient balance, and Phase 2 will amplify a
real signal that's already there.

If they barely move, the path features genuinely don't carry enough
distinct signal in the contact-point representation, and we NEED Phase 2.
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import KFold, cross_val_score
from pybaseball import playerid_reverse_lookup

profiles = pd.read_parquet("data/processed/profiles_adjusted.parquet")

FEATURES = [
    "bat_speed_mean", "swing_length_mean", "attack_angle_mean",
    "attack_direction_mean", "swing_path_tilt_mean",
    "intercept_ball_minus_batter_pos_x_inches_mean",
    "intercept_ball_minus_batter_pos_y_inches_mean",
    "bat_speed_std", "attack_angle_std",
]

d = profiles.dropna(subset=FEATURES + ["bip_rate", "rv_given_bip_adj"]).copy()
X = d[FEATURES].values

# Recompute rv_nonbip
swings_list = []
for label in ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]:
    s = pd.read_parquet(f"data/raw/statcast_{label}.parquet")
    s = s[s["bat_speed"].notna() & s["swing_length"].notna()]
    s = s.assign(bip=(s["type"] == "X").astype(int))
    swings_list.append(s[["delta_run_exp", "bip"]])
allsw = pd.concat(swings_list, ignore_index=True)
rv_nonbip = allsw.loc[allsw["bip"] == 0, "delta_run_exp"].mean()


def make_weighted_pipe(bat_speed_penalty_multiplier=1.0, alpha_base=1.0):
    """
    Build a pipeline where bat_speed-related features get a heavier ridge
    penalty than other features.

    sklearn's Ridge uses a single alpha. To approximate feature-specific
    regularization, we SCALE bat_speed terms DOWN before fitting. That makes
    their coefficients (in standardized space) effectively penalized harder,
    because Ridge minimizes coef^2 — smaller-scaled features need larger
    coefs to have the same effect, which Ridge punishes.

    Equivalently: shrinking a feature's variance reduces the signal Ridge
    sees from it, so the model leans on other features.
    """
    return Pipeline([
        ("scale", StandardScaler()),
        ("downweight_bs", BatSpeedDownweighter(
            FEATURES, multiplier=bat_speed_penalty_multiplier)),
        ("poly", PolynomialFeatures(degree=2, include_bias=False)),
        ("ridge", Ridge(alpha=alpha_base)),
    ])


from sklearn.base import BaseEstimator, TransformerMixin
class BatSpeedDownweighter(BaseEstimator, TransformerMixin):
    """Shrink bat_speed_mean column by `multiplier` (e.g., 0.5 halves its scale)."""
    def __init__(self, feature_names, multiplier=0.5):
        self.feature_names = feature_names
        self.multiplier = multiplier
    def fit(self, X, y=None):
        self.bs_idx_ = self.feature_names.index("bat_speed_mean")
        self.bs_std_idx_ = self.feature_names.index("bat_speed_std")
        return self
    def transform(self, X):
        X = X.copy()
        X[:, self.bs_idx_] *= self.multiplier
        X[:, self.bs_std_idx_] *= self.multiplier
        return X


def fit_and_grade(multiplier, label):
    """Fit the two-model system with given bat-speed downweight, return graded df."""
    cv = KFold(n_splits=5, shuffle=True, random_state=42)

    pipe_bip = make_weighted_pipe(multiplier)
    r2_bip = cross_val_score(pipe_bip, X, d["bip_rate"], cv=cv, scoring="r2").mean()
    pipe_bip.fit(X, d["bip_rate"])

    pipe_pow = make_weighted_pipe(multiplier)
    r2_pow = cross_val_score(pipe_pow, X, d["rv_given_bip_adj"], cv=cv, scoring="r2").mean()
    pipe_pow.fit(X, d["rv_given_bip_adj"])

    # Score
    p = np.clip(pipe_bip.predict(X), 0, 1)
    rv = pipe_pow.predict(X)
    xrv = p * rv + (1 - p) * rv_nonbip
    mu, sigma = xrv.mean(), xrv.std()
    bp = 100 + (xrv - mu) / sigma * 10

    print(f"\n[{label}: bat_speed multiplier = {multiplier}]")
    print(f"  CV R² — P(BIP): {r2_bip:.3f}  |  RV|BIP: {r2_pow:.3f}")

    return pd.DataFrame({
        "batter": d["batter"].values,
        "half": d["half"].values,
        "n_swings": d["n_swings"].values,
        "bat_plus": bp,
        "bat_speed_mean": d["bat_speed_mean"].values,
        "attack_angle_mean": d["attack_angle_mean"].values,
    })


# Run three variants
g_baseline = fit_and_grade(1.0, "BASELINE (no downweight)")
g_half = fit_and_grade(0.5, "DOWNWEIGHT 0.5")
g_quarter = fit_and_grade(0.25, "DOWNWEIGHT 0.25 (aggressive)")


# Aggregate to 2025 season-level (swing-weighted)
def season_agg(graded, season_halves=("2025_H1", "2025_H2")):
    sub = graded[graded["half"].isin(season_halves)].copy()
    g = sub.groupby("batter").apply(
        lambda x: pd.Series({
            "bat_plus_raw": np.average(x["bat_plus"], weights=x["n_swings"]),
            "n_swings": x["n_swings"].sum(),
            "bat_speed": np.average(x["bat_speed_mean"], weights=x["n_swings"]),
            "attack_angle": np.average(x["attack_angle_mean"], weights=x["n_swings"]),
        }), include_groups=False
    ).reset_index()
    # Reliability weighting (k=360 to match production)
    k = 360
    w = g["n_swings"] / (g["n_swings"] + k)
    g["bat_plus"] = 100 * (1 - w) + g["bat_plus_raw"] * w
    return g


s_baseline = season_agg(g_baseline)
s_half = season_agg(g_half)
s_quarter = season_agg(g_quarter)

# Resolve names
ids = s_baseline["batter"].unique().tolist()
names = playerid_reverse_lookup(ids, key_type="mlbam")
names["name"] = names["name_first"].str.title() + " " + names["name_last"].str.title()
name_map = dict(zip(names["key_mlbam"], names["name"]))
for s in [s_baseline, s_half, s_quarter]:
    s["name"] = s["batter"].map(name_map)

# Compare the three top-15s
def top15(s, label):
    print(f"\n{'='*72}")
    print(f"TOP 15 — {label}")
    print(f"{'='*72}")
    out = s.nlargest(15, "bat_plus").copy()
    out["rank"] = range(1, 16)
    for c in ["bat_plus", "bat_speed", "attack_angle"]:
        out[c] = out[c].round(1)
    print(out[["rank", "name", "bat_plus", "bat_speed", "attack_angle", "n_swings"]].to_string(index=False))


top15(s_baseline, "BASELINE")
top15(s_half, "DOWNWEIGHT 0.5")
top15(s_quarter, "DOWNWEIGHT 0.25 (aggressive)")


# Track key players across the three weightings
print(f"\n{'='*72}")
print(f"KEY PLAYER MOVEMENT (Driveline top 10 + Adell + Stanton)")
print(f"{'='*72}")
print("Driveline's top 10 (rank in their leaderboard) + flagged players")
print(f"{'name':<22} {'BL rank':>8} {'BL S+':>7}   {'0.5 rank':>9} {'0.5 S+':>7}   {'0.25 rank':>10} {'0.25 S+':>7}")
print("-" * 100)

driveline = [("Nick Kurtz", 1), ("Aaron Judge", 2), ("James Wood", 3),
             ("Riley Greene", 4), ("Ronald Acuña", 5), ("Oneil Cruz", 6),
             ("Matt Wallner", 7), ("Kyle Schwarber", 8), ("Shohei Ohtani", 9),
             ("Pete Alonso", 10), ("Jo Adell", None), ("Giancarlo Stanton", None)]

def find_rank_and_sp(s, name_sub):
    s_ranked = s.sort_values("bat_plus", ascending=False).reset_index(drop=True)
    s_ranked["rank"] = range(1, len(s_ranked) + 1)
    matches = s_ranked[s_ranked["name"].str.contains(name_sub, case=False, na=False, regex=False)]
    if len(matches) == 0:
        return None, None
    row = matches.iloc[0]
    return int(row["rank"]), float(row["bat_plus"])

for name, dr_rank in driveline:
    r1, sp1 = find_rank_and_sp(s_baseline, name)
    r2, sp2 = find_rank_and_sp(s_half, name)
    r3, sp3 = find_rank_and_sp(s_quarter, name)
    dr_str = f"(DL#{dr_rank})" if dr_rank else "(not DL top10)"
    name_with_dr = f"{name} {dr_str}"
    print(f"{name_with_dr:<22} {r1 or '--':>8} {sp1 or 0:>7.1f}   "
          f"{r2 or '--':>9} {sp2 or 0:>7.1f}   "
          f"{r3 or '--':>10} {sp3 or 0:>7.1f}")
