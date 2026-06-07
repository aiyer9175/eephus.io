# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
19_augmented_stability.py - Stability check for the top-down-augmented model.

Phase 1 stability was r = 0.88 half-to-half. If the augmented model trades
stability for that +3.5pp R² gain on P(BIP), it's probably not worth it.

We compare:
  - Phase 1 Swing+ stability (already known, ~0.88)
  - Augmented Swing+ stability with top-down features added
  - Predictive lift on next-half xwOBAcon (the real-world test)
"""
import sys
sys.path.insert(0, "/home/claude")
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import KFold
from scipy.stats import pearsonr
import importlib.util

spec = importlib.util.spec_from_file_location("td", "/home/claude/17_path_topdown.py")
td = importlib.util.module_from_spec(spec)
spec.loader.exec_module(td)
reconstruct_topdown = td.reconstruct_topdown


HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
TRACKING = [
    "bat_speed", "swing_length", "attack_angle", "attack_direction",
    "swing_path_tilt",
    "intercept_ball_minus_batter_pos_x_inches",
    "intercept_ball_minus_batter_pos_y_inches",
]
TOPDOWN_FEAT_NAMES = [
    "lateral_coverage_ft", "depth_at_min_x",
    "x_at_downswing", "x_at_contact_zone", "x_at_followthrough",
    "haa_at_downswing", "haa_at_contact_zone", "haa_at_contact",
    "depth_range_ft",
]
PHASE1 = [f"{c}_mean" for c in TRACKING] + ["bat_speed_std", "attack_angle_std"]
TD_MEANS = [f"{c}_mean" for c in TOPDOWN_FEAT_NAMES]
AUGMENTED = PHASE1 + TD_MEANS


# Build profiles (replays 18_topdown_coverage_test but cached)
profiles_path = Path("data/processed/profiles_with_topdown.parquet")
if profiles_path.exists():
    print(f"Loading cached profiles from {profiles_path}")
    profiles = pd.read_parquet(profiles_path)
else:
    print("Rebuilding profiles with top-down features...")
    needed = ["bat_speed", "swing_length", "attack_angle", "attack_direction",
              "swing_path_tilt",
              "intercept_ball_minus_batter_pos_x_inches",
              "intercept_ball_minus_batter_pos_y_inches",
              "plate_z", "stand", "type", "delta_run_exp",
              "estimated_woba_using_speedangle"]
    all_swings = []
    for label in HALVES:
        df = pd.read_parquet(f"data/raw/statcast_{label}.parquet")
        df = df[df["bat_speed"].notna() & df["swing_length"].notna()].copy()
        df = df.dropna(subset=needed[:-2])
        mask = (
            (df["bat_speed"] >= 40) & (df["bat_speed"] <= 90) &
            (df["swing_length"] >= 4) & (df["swing_length"] <= 12) &
            (df["attack_angle"].abs() <= 45) &
            (df["swing_path_tilt"] >= 10) & (df["swing_path_tilt"] <= 50) &
            (df["attack_direction"].abs() <= 60)
        )
        df = df[mask].copy()
        df["half"] = label
        df["bip"] = (df["type"] == "X").astype(int)
        all_swings.append(df)
    swings = pd.concat(all_swings, ignore_index=True)

    def extract(row):
        p = reconstruct_topdown(
            attack_direction_deg=row["attack_direction"],
            swing_length_ft=row["swing_length"],
            intercept_x_in=row["intercept_ball_minus_batter_pos_x_inches"],
            intercept_y_in=row["intercept_ball_minus_batter_pos_y_inches"],
            handedness=row["stand"],
        )
        pts = p.sample(18)
        xs = pts[:, 0]; ys = pts[:, 1]
        return {
            "lateral_coverage_ft":  xs.max() - xs.min(),
            "depth_at_min_x":       ys[np.argmin(xs)],
            "x_at_downswing":       xs[2],
            "x_at_contact_zone":    xs[15],
            "x_at_followthrough":   xs[17],
            "haa_at_downswing":     p.haa_at(0.17),
            "haa_at_contact_zone":  p.haa_at(0.83),
            "haa_at_contact":       p.haa_at(1.00),
            "depth_range_ft":       ys.max() - ys.min(),
        }
    import time
    t0 = time.time()
    feats = []
    for i in range(0, len(swings), 10000):
        chunk = swings.iloc[i:i+10000]
        feats.extend(chunk.apply(extract, axis=1).tolist())
    td_df = pd.DataFrame(feats, index=swings.index)
    swings = pd.concat([swings, td_df], axis=1)
    print(f"Feature extraction: {time.time()-t0:.0f}s")

    agg = {c: ["mean", "std"] for c in TRACKING + TOPDOWN_FEAT_NAMES}
    profiles = swings.groupby(["batter", "half"]).agg(agg)
    profiles.columns = [f"{c}_{s}" for c, s in profiles.columns]
    profiles["n_swings"] = swings.groupby(["batter", "half"]).size()
    profiles["n_bip"] = swings.groupby(["batter", "half"])["bip"].sum()
    profiles["bip_rate"] = profiles["n_bip"] / profiles["n_swings"]
    bip = swings[swings["bip"] == 1]
    profiles["rv_given_bip"] = bip.groupby(["batter", "half"])["delta_run_exp"].mean()
    profiles["xwobacon_obs"] = bip.groupby(["batter", "half"])[
        "estimated_woba_using_speedangle"].mean()
    profiles = profiles[profiles["n_swings"] >= 180].reset_index()
    profiles.to_parquet(profiles_path)

print(f"Profiles: {len(profiles)} player-halves")


# ===================================================================
# Build two Swing+ versions: Phase 1 and Augmented
# ===================================================================

def make_pipe():
    return Pipeline([
        ("scale", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, include_bias=False)),
        ("ridge", RidgeCV(alphas=(0.1, 1.0, 10.0, 100.0))),
    ])


def fit_and_score(d, feats):
    """Returns Swing+ scores (100-centered, sigma=10) given a feature set."""
    pipe_bip = make_pipe().fit(d[feats].values, d["bip_rate"].values)
    pipe_pow = make_pipe().fit(d[feats].values, d["rv_given_bip"].values)
    # rv_nonbip constant - approximate from typical league avg
    rv_nonbip = -0.0659
    p = np.clip(pipe_bip.predict(d[feats].values), 0, 1)
    rv = pipe_pow.predict(d[feats].values)
    xrv = p * rv + (1 - p) * rv_nonbip
    mu, sigma = xrv.mean(), xrv.std()
    return 100 + (xrv - mu) / sigma * 10, pipe_bip, pipe_pow


d = profiles.dropna(subset=AUGMENTED + ["bip_rate", "rv_given_bip"]).copy()
print(f"Modeling rows: {len(d)}")

d["swing_plus_p1"], pipe_bip_p1, pipe_pow_p1 = fit_and_score(d, PHASE1)
d["swing_plus_aug"], pipe_bip_aug, pipe_pow_aug = fit_and_score(d, AUGMENTED)


# ===================================================================
# Half-to-half stability
# ===================================================================
HALVES_ORDER = HALVES

def consec_pairs(d, col):
    pts = []
    for batter, g in d.sort_values(["batter", "half"]).groupby("batter"):
        hs = g["half"].tolist()
        for i in range(len(hs) - 1):
            if HALVES_ORDER.index(hs[i+1]) - HALVES_ORDER.index(hs[i]) != 1:
                continue
            pts.append((
                g[g["half"]==hs[i]][col].iloc[0],
                g[g["half"]==hs[i+1]][col].iloc[0],
                g[g["half"]==hs[i+1]]["xwobacon_obs"].iloc[0] if "xwobacon_obs" in g.columns else np.nan,
            ))
    return pd.DataFrame(pts, columns=["t", "t1", "xwoba_t1"])


print("\n" + "="*72)
print("STABILITY: half-to-half correlation")
print("="*72)

p1_pairs = consec_pairs(d, "swing_plus_p1")
aug_pairs = consec_pairs(d, "swing_plus_aug")
r_p1, _ = pearsonr(p1_pairs["t"], p1_pairs["t1"])
r_aug, _ = pearsonr(aug_pairs["t"], aug_pairs["t1"])

print(f"\n  Phase 1 Swing+ stability:    r = {r_p1:.3f}  (n={len(p1_pairs)})")
print(f"  Augmented Swing+ stability:  r = {r_aug:.3f}  (n={len(aug_pairs)})")
print(f"  Delta: {r_aug - r_p1:+.3f}")


# ===================================================================
# Predictive lift on next-half xwOBAcon
# ===================================================================
print("\n" + "="*72)
print("PREDICTIVE LIFT: Swing+ at t vs observed xwOBAcon at t+1")
print("="*72)

p1_pairs_clean = p1_pairs.dropna(subset=["xwoba_t1"])
aug_pairs_clean = aug_pairs.dropna(subset=["xwoba_t1"])

r_p1_pred, _ = pearsonr(p1_pairs_clean["t"], p1_pairs_clean["xwoba_t1"])
r_aug_pred, _ = pearsonr(aug_pairs_clean["t"], aug_pairs_clean["xwoba_t1"])

print(f"\n  Phase 1 Swing+ → xwOBAcon next half:    r = {r_p1_pred:.3f}")
print(f"  Augmented Swing+ → xwOBAcon next half:  r = {r_aug_pred:.3f}")
print(f"  Delta: {r_aug_pred - r_p1_pred:+.3f}")


# ===================================================================
# Leaderboard movement: do the contested players actually move?
# ===================================================================
print("\n" + "="*72)
print("LEADERBOARD MOVEMENT: 2025 season (swing-weighted across H1+H2)")
print("="*72)

from pybaseball import playerid_reverse_lookup
d_2025 = d[d["half"].isin(["2025_H1", "2025_H2"])].copy()

# Swing-weighted aggregate
def agg_season(d_season, col):
    out = d_season.groupby("batter").apply(
        lambda x: np.average(x[col], weights=x["n_swings"])
    ).reset_index(name=col)
    out["n"] = d_season.groupby("batter")["n_swings"].sum().values
    # Reliability-weight toward 100 (k=360)
    w = out["n"] / (out["n"] + 360)
    out[col] = w * out[col] + (1 - w) * 100
    return out

s_p1 = agg_season(d_2025, "swing_plus_p1")
s_aug = agg_season(d_2025, "swing_plus_aug")
merged = s_p1.merge(s_aug[["batter", "swing_plus_aug"]], on="batter")
merged["delta"] = merged["swing_plus_aug"] - merged["swing_plus_p1"]

# Look up names
names = playerid_reverse_lookup(merged["batter"].tolist(), key_type="mlbam")
names["name"] = names["name_first"].str.title() + " " + names["name_last"].str.title()
nm = dict(zip(names["key_mlbam"], names["name"]))
merged["name"] = merged["batter"].map(nm)

# Track contested players
contested = ["Matt Wallner", "James Wood", "Jo Adell", "Giancarlo Stanton",
             "Ronald Acuña", "Oneil Cruz", "Aaron Judge", "Nick Kurtz",
             "Riley Greene", "Steven Kwan"]
print(f"\n  {'Player':<22}{'Phase 1':>10}{'Augmented':>12}{'Delta':>9}")
print("  " + "-"*52)
for name in contested:
    row = merged[merged["name"].str.contains(name, case=False, na=False, regex=False)]
    if len(row) == 0: continue
    r = row.iloc[0]
    print(f"  {r['name']:<22}{r['swing_plus_p1']:>10.1f}{r['swing_plus_aug']:>12.1f}{r['delta']:>+9.1f}")

# Largest movers overall
print(f"\n  Largest upward movers (Augmented gains most over Phase 1):")
top_up = merged.nlargest(10, "delta")[["name", "swing_plus_p1", "swing_plus_aug", "delta", "n"]]
print(top_up.to_string(index=False))
print(f"\n  Largest downward movers:")
top_dn = merged.nsmallest(10, "delta")[["name", "swing_plus_p1", "swing_plus_aug", "delta", "n"]]
print(top_dn.to_string(index=False))
