# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""06b_ablation_only.py - Re-run just Test B with the bug fixed."""

import pandas as pd
import numpy as np
from scipy.stats import pearsonr
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import KFold, cross_val_score

profiles = pd.read_parquet("data/processed/profiles_all_halves.parquet")
# rv_given_bip is already on this file from the 04_driveline_model.py run.

# Recompute rv_nonbip constant from pitch data.
swings_list = []
for label in ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]:
    s = pd.read_parquet(f"data/raw/statcast_{label}.parquet")
    s = s[s["bat_speed"].notna() & s["swing_length"].notna()].copy()
    s["bip"] = (s["type"] == "X").astype(int)
    swings_list.append(s[["delta_run_exp", "bip"]])
swings = pd.concat(swings_list, ignore_index=True)
rv_nonbip = swings.loc[swings["bip"] == 0, "delta_run_exp"].mean()
print(f"rv_nonbip constant: {rv_nonbip:.4f}\n")

FULL = [
    "bat_speed_mean", "swing_length_mean", "attack_angle_mean",
    "attack_direction_mean", "swing_path_tilt_mean",
    "intercept_ball_minus_batter_pos_x_inches_mean",
    "intercept_ball_minus_batter_pos_y_inches_mean",
    "bat_speed_std", "attack_angle_std",
]
BS_ONLY = ["bat_speed_mean"]


def make_pipe():
    return Pipeline([
        ("scale", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, include_bias=False)),
        ("ridge", RidgeCV(alphas=(0.1, 1.0, 10.0, 100.0))),
    ])


def fit_pair(df, feat_cols, label):
    d = df.dropna(subset=feat_cols + ["bip_rate", "rv_given_bip"]).copy()
    X = d[feat_cols].values
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    pb = make_pipe()
    r2_b = cross_val_score(pb, X, d["bip_rate"], cv=cv, scoring="r2")
    pb.fit(X, d["bip_rate"])
    pp = make_pipe()
    r2_p = cross_val_score(pp, X, d["rv_given_bip"], cv=cv, scoring="r2")
    pp.fit(X, d["rv_given_bip"])
    print(f"[{label}] n_feats={len(feat_cols)}")
    print(f"  P(BIP)  CV R² = {r2_b.mean():.3f} (±{r2_b.std():.3f})")
    print(f"  RV|BIP  CV R² = {r2_p.mean():.3f} (±{r2_p.std():.3f})")
    return pb, pp


bip_full, pow_full = fit_pair(profiles, FULL, "FULL (9 feats, degree=2)")
bip_bs, pow_bs = fit_pair(profiles, BS_ONLY, "BAT-SPEED ONLY (degree=2)")


def score(df, feats, pb, pp, rv_nonbip):
    X = df[feats].values
    p = np.clip(pb.predict(X), 0, 1)
    rv = pp.predict(X)
    xrv = p * rv + (1 - p) * rv_nonbip
    return 100 + (xrv - xrv.mean()) / xrv.std() * 10


clean = profiles.dropna(subset=FULL + ["rv_given_bip"]).copy()
clean["bat_plus_full"] = score(clean, FULL, bip_full, pow_full, rv_nonbip)
clean["bat_plus_bs"] = score(clean, BS_ONLY, bip_bs, pow_bs, rv_nonbip)


def stability(df, col):
    ORDER = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
    pts = []
    for _, g in df.sort_values(["batter", "half"]).groupby("batter"):
        hs = g["half"].tolist()
        for i in range(len(hs) - 1):
            if ORDER.index(hs[i + 1]) - ORDER.index(hs[i]) != 1:
                continue
            pts.append((
                g[g["half"] == hs[i]][col].iloc[0],
                g[g["half"] == hs[i + 1]][col].iloc[0],
            ))
    a = np.array(pts)
    return pearsonr(a[:, 0], a[:, 1])[0], len(pts)


r_full, n_full = stability(clean, "bat_plus_full")
r_bs, n_bs = stability(clean, "bat_plus_bs")
print(f"\nStability (half-to-half r):")
print(f"  Full Bat+:           r = {r_full:.3f}  (n={n_full})")
print(f"  Bat-speed-only Bat+: r = {r_bs:.3f}  (n={n_bs})")
print(f"  Δ: {r_full - r_bs:+.3f}")

r_overlap, _ = pearsonr(clean["bat_plus_full"], clean["bat_plus_bs"])
print(f"\nFull vs Bat-speed-only correlation: r = {r_overlap:.3f}")

clean["delta"] = clean["bat_plus_full"] - clean["bat_plus_bs"]
print(f"\nLargest POSITIVE path adjustment (path features boost grade most):")
print(clean.nlargest(10, "delta")[
    ["batter", "half", "bat_plus_full", "bat_plus_bs", "delta", "bat_speed_mean"]
].to_string(index=False))
print(f"\nLargest NEGATIVE path adjustment (path features penalize most):")
print(clean.nsmallest(10, "delta")[
    ["batter", "half", "bat_plus_full", "bat_plus_bs", "delta", "bat_speed_mean"]
].to_string(index=False))

# Also test: does the FULL model predict NEXT half's xwoba better than BS-only?
print(f"\nNext-half xwOBAcon prediction (using each Bat+ as predictor):")
ORDER = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
pred_rows = []
for _, g in clean.sort_values(["batter", "half"]).groupby("batter"):
    hs = g["half"].tolist()
    for i in range(len(hs) - 1):
        if ORDER.index(hs[i + 1]) - ORDER.index(hs[i]) != 1:
            continue
        r1 = g[g["half"] == hs[i]].iloc[0]
        r2 = g[g["half"] == hs[i + 1]].iloc[0]
        pred_rows.append({
            "bp_full": r1["bat_plus_full"],
            "bp_bs": r1["bat_plus_bs"],
            "xwoba_t": r1["xwobacon_obs"],
            "xwoba_t1": r2["xwobacon_obs"],
        })
pp = pd.DataFrame(pred_rows).dropna()
r_full_pred = pearsonr(pp["bp_full"], pp["xwoba_t1"])[0]
r_bs_pred = pearsonr(pp["bp_bs"], pp["xwoba_t1"])[0]
r_obs_pred = pearsonr(pp["xwoba_t"], pp["xwoba_t1"])[0]
print(f"  Full Bat+_t       -> xwOBAcon_t+1:  r = {r_full_pred:.3f}")
print(f"  BS-only Bat+_t    -> xwOBAcon_t+1:  r = {r_bs_pred:.3f}")
print(f"  Observed xwOBAcon -> xwOBAcon_t+1:  r = {r_obs_pred:.3f}  (baseline)")
