# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
augmented_model_test.py — Does adding plate-discipline / timing features
to the bat-tracking-only feature set actually improve predictions?

Hypothesis:
  - Adding approach features should NOT help much for BIP-only outcomes
    (EV, Barrel%, xwOBAcon) — those are 'given contact' stats.
  - Adding approach features SHOULD help a lot for full-PA wOBA, because
    wOBA depends on contact rate / K% / BB% in ways bat tracking can't see.

Protocol:
  1. Compute per-(batter, half) features:
       - BASELINE: 9 bat-tracking features already in leaderboard_half.parquet.
       - APPROACH: whiff%, swing%, chase% (O-Swing), Z-Swing%, Z-Contact%,
                   O-Contact%, plus 2 timing/swing-quality metrics
                   (mean|attack_angle - 12|, contact-depth std).
  2. Compute per-(batter, half) targets:
       - BIP-LEVEL: avg_ev, hard_hit_pct, barrel_pct, avg_la, xwOBAcon
                    (re-uses validation_concurrent.csv)
       - FULL-PA:   wOBA, xwOBA (computed from raw Statcast)
  3. For each (target × feature set), train Scaler -> Poly(2) -> RidgeCV
     with GroupKFold(5) on batter (no player in both train and test).
  4. Report test Pearson r, R^2, MAE. Delta = AUGMENTED - BASELINE.

K% and BB% are deliberately excluded from features when predicting wOBA —
they are wOBA components, so including them would be partly circular.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
PROCESSED = PROJECT / "data" / "processed"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]

BASELINE_FEATS = [
    "bat_speed_mean", "swing_length_mean", "attack_angle_mean",
    "attack_direction_mean", "swing_path_tilt_mean",
    "intercept_ball_minus_batter_pos_x_inches_mean",
    "intercept_ball_minus_batter_pos_y_inches_mean",
    "bat_speed_std", "attack_angle_std",
]

# Approach / timing features added on top of baseline.
APPROACH_FEATS = [
    "whiff_rate", "swing_rate", "chase_rate",
    "z_swing_rate", "z_contact_rate", "o_contact_rate",
    "aa_dev_from_ideal", "contact_depth_std",
]

# (target_col, label, decimals)
TARGETS_BIP = [
    ("obs_avg_ev",       "Avg EV (mph)", 1),
    ("obs_hard_hit_pct", "Hard-Hit %",   1),
    ("obs_barrel_pct",   "Barrel %",     1),
    ("obs_avg_la",       "Avg LA (deg)", 1),
    ("obs_xwobacon",     "xwOBAcon",     3),
]
TARGETS_PA = [
    ("wOBA",  "wOBA (full PA)",  3),
    ("xwOBA", "xwOBA (full PA)", 3),
]

SWING_DESCS = {"hit_into_play", "foul", "swinging_strike",
               "swinging_strike_blocked", "foul_tip"}
WHIFF_DESCS = {"swinging_strike", "swinging_strike_blocked"}


def approach_per_half(label: str) -> pd.DataFrame:
    """Compute discipline + timing features per batter for one half."""
    df = pd.read_parquet(
        RAW / f"statcast_{label}.parquet",
        columns=[
            "batter", "description", "zone",
            "attack_angle",
            "intercept_ball_minus_batter_pos_y_inches",
            "bat_speed",
        ],
    )
    df["is_swing"] = df["description"].isin(SWING_DESCS)
    df["is_whiff"] = df["description"].isin(WHIFF_DESCS)
    df["in_zone"] = df["zone"].between(1, 9).fillna(False)
    df["out_zone"] = ~df["in_zone"]

    # Counts per batter
    agg = df.groupby("batter", as_index=False).agg(
        n_pitches=("description", "size"),
        n_swings=("is_swing", "sum"),
        n_whiffs=("is_whiff", "sum"),
        n_in=("in_zone", "sum"),
        n_out=("out_zone", "sum"),
        n_zswings=("is_swing", lambda s: (s & df.loc[s.index, "in_zone"]).sum()),
        n_ozswings=("is_swing", lambda s: (s & df.loc[s.index, "out_zone"]).sum()),
        n_zwhiffs=("is_whiff", lambda s: (s & df.loc[s.index, "in_zone"]).sum()),
        n_ozwhiffs=("is_whiff", lambda s: (s & df.loc[s.index, "out_zone"]).sum()),
    )
    agg["swing_rate"] = agg["n_swings"] / agg["n_pitches"]
    agg["whiff_rate"] = agg["n_whiffs"] / agg["n_swings"]
    agg["chase_rate"] = agg["n_ozswings"] / agg["n_out"]
    agg["z_swing_rate"] = agg["n_zswings"] / agg["n_in"]
    agg["z_contact_rate"] = 1.0 - (agg["n_zwhiffs"] / agg["n_zswings"])
    agg["o_contact_rate"] = 1.0 - (agg["n_ozwhiffs"] / agg["n_ozswings"])

    # Timing features (over bat-tracking rows only)
    swings = df[df["bat_speed"].notna()].copy()
    swings["aa_dev"] = (swings["attack_angle"] - 12).abs()
    timing = swings.groupby("batter", as_index=False).agg(
        aa_dev_from_ideal=("aa_dev", "mean"),
        contact_depth_std=("intercept_ball_minus_batter_pos_y_inches", "std"),
    )
    agg = agg.merge(timing, on="batter", how="left")
    agg["half"] = label
    return agg[["batter", "half"] + APPROACH_FEATS]


def woba_per_half(label: str) -> pd.DataFrame:
    df = pd.read_parquet(
        RAW / f"statcast_{label}.parquet",
        columns=["batter", "events", "type", "woba_value", "woba_denom",
                 "estimated_woba_using_speedangle"],
    )
    pa = df[df["woba_denom"] == 1].copy()
    pa["xwoba_event"] = pa["estimated_woba_using_speedangle"]
    pa.loc[pa["type"] != "X", "xwoba_event"] = pa.loc[pa["type"] != "X", "woba_value"]
    agg = pa.groupby("batter", as_index=False).agg(
        n_pa=("woba_denom", "sum"),
        wOBA=("woba_value", "mean"),
        xwOBA=("xwoba_event", "mean"),
        k_rate=("events", lambda s: (s == "strikeout").mean()),
        bb_rate=("events", lambda s: (s == "walk").mean()),
    )
    agg["half"] = label
    return agg


def make_pipe() -> Pipeline:
    return Pipeline([
        ("scale", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, include_bias=False)),
        ("ridge", RidgeCV(alphas=np.logspace(-3, 3, 19))),
    ])


def cv_eval(X: pd.DataFrame, y: pd.Series, groups: pd.Series, n_splits: int = 5):
    """Out-of-fold predictions via GroupKFold on batter."""
    kf = GroupKFold(n_splits=n_splits)
    oof = np.full(len(y), np.nan)
    for tr, te in kf.split(X, y, groups):
        pipe = make_pipe()
        pipe.fit(X.iloc[tr], y.iloc[tr])
        oof[te] = pipe.predict(X.iloc[te])
    mask = ~np.isnan(oof)
    yy = y.to_numpy()[mask]
    pp = oof[mask]
    r = float(np.corrcoef(yy, pp)[0, 1])
    return {
        "r": r,
        "R2": r ** 2,
        "MAE": float(np.abs(yy - pp).mean()),
        "RMSE": float(np.sqrt(((yy - pp) ** 2).mean())),
        "n": int(mask.sum()),
    }


def main() -> None:
    print("Loading concurrent validation frame (predictions, observed BIP stats, baseline feats)...")
    base = pd.read_csv(PROCESSED / "validation_concurrent.csv")

    print("Computing approach + timing features per (batter, half)...")
    approach = pd.concat([approach_per_half(h) for h in HALVES], ignore_index=True)
    print(f"  {len(approach):,} rows of approach features")

    print("Computing full-PA wOBA / xwOBA per (batter, half)...")
    woba = pd.concat([woba_per_half(h) for h in HALVES], ignore_index=True)
    print(f"  {len(woba):,} rows of PA features")

    df = base.merge(approach, on=["batter", "half"], how="inner")
    df = df.merge(woba, on=["batter", "half"], how="inner")
    df = df[df["n_pa"] >= 50]   # keep enough PAs for stable wOBA
    print(f"\nFinal merged: {len(df):,} player-halves "
          f"({df['batter'].nunique()} unique batters)")

    # ----- Train + evaluate each (target × feature_set) -----
    feature_sets = {
        "baseline (9)": BASELINE_FEATS,
        f"augmented ({len(BASELINE_FEATS) + len(APPROACH_FEATS)})":
            BASELINE_FEATS + APPROACH_FEATS,
    }
    results = []
    for target, label, dec in TARGETS_BIP + TARGETS_PA:
        sub = df.dropna(subset=[target] + BASELINE_FEATS + APPROACH_FEATS)
        groups = sub["batter"]
        y = sub[target]
        row = {"target": label, "n": len(sub), "dec": dec}
        for fs_name, fs_cols in feature_sets.items():
            X = sub[fs_cols]
            res = cv_eval(X, y, groups)
            row[f"{fs_name} r"] = round(res["r"], 3)
            row[f"{fs_name} R²"] = round(res["R2"], 3)
            row[f"{fs_name} MAE"] = round(res["MAE"], dec + 1)
        # delta
        b = f"baseline (9) r"
        a = [k for k in row if k.startswith("augmented") and k.endswith(" r")][0]
        row["Δ r"] = round(row[a] - row[b], 3)
        row["Δ R²"] = round(
            row[a.replace(" r", " R²")] - row[b.replace(" r", " R²")], 3
        )
        results.append(row)

    out = pd.DataFrame(results)
    # Drop the helper col
    out = out.drop(columns=["dec"])
    # Reorder for readability
    out = out[["target", "n",
               "baseline (9) r", f"augmented ({len(BASELINE_FEATS)+len(APPROACH_FEATS)}) r", "Δ r",
               "baseline (9) R²", f"augmented ({len(BASELINE_FEATS)+len(APPROACH_FEATS)}) R²", "Δ R²",
               "baseline (9) MAE", f"augmented ({len(BASELINE_FEATS)+len(APPROACH_FEATS)}) MAE"]]

    print("\n" + "=" * 110)
    print("OUT-OF-FOLD CV (GroupKFold k=5 on batter — no player in both train and test)")
    print("=" * 110)
    print(out.to_string(index=False))

    print("\nInterpretation:")
    print("  - BIP targets (EV..xwOBAcon): approach features SHOULDN'T help — these stats")
    print("    are about contact quality, not whether contact happens. Small or zero Δ expected.")
    print("  - PA targets (wOBA, xwOBA): approach features SHOULD help substantially —")
    print("    contact rate, chase, whiff% all enter PA outcomes through K%/BB%.")
    out.to_csv(PROCESSED / "augmented_model_results.csv", index=False)
    print(f"\nSaved {PROCESSED / 'augmented_model_results.csv'}")


if __name__ == "__main__":
    main()
