# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
attack_direction_test.py — Does pull tendency carry UNUSED signal?

attack_direction_mean is already a baseline feature, and poly(2) already has
attack_direction^2 and its interactions. So this tests what's NOT in the model:
  - attack_direction_std (consistency of pull aim) — absent from the 9 features
  - pull_rate / pull-and-lift rate (the actual damage combo)
  - bat speed & attack angle ON the most-pulled swings

PART 1 grounds the 'pulling -> higher EV' claim two ways:
  (a) swing-aim pull (attack_direction)  -> EV
  (b) spray pull (where the ball lands)  -> EV, split by air vs ground
PART 2 runs the clean swing-geometry pull features through concurrent +
predictive CV (GroupKFold on batter). Verdict is predictive.

All PART 2 features are swing geometry only — no launch metrics, no spray —
so no leakage. Spray pull% (PART 1) is a batted-ball outcome and is used
for diagnosis only, never as a model feature.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from augmented_model_test import (
    APPROACH_FEATS, BASELINE_FEATS, approach_per_half, cv_eval, woba_per_half,
)
from swing_plus import SwingPlusModel

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
PROCESSED = PROJECT / "data" / "processed"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
MODEL = SwingPlusModel(PROJECT / "swing_plus_model_v1.joblib")

# Note: attack_direction_std already exists in leaderboard_half (build_profiles
# computes a std for every tracking col) — it's just not one of the 9 model
# features. We include it here under its own name to test it, plus new pull feats.
AD_FEATS = ["ad_std", "pull_rate", "bs_on_pull", "aa_on_pull", "pull_lift_rate"]

TARGETS = [
    ("obs_avg_ev",       "Avg EV (mph)", 1),
    ("obs_hard_hit_pct", "Hard-Hit %",   1),
    ("obs_barrel_pct",   "Barrel %",     1),
    ("obs_avg_la",       "Avg LA (deg)", 1),
    ("obs_xwobacon",     "xwOBAcon",     3),
]


def _group_feats(g: pd.DataFrame) -> pd.Series:
    ad = g["attack_direction"].to_numpy(dtype="float64")
    aa = g["attack_angle"].to_numpy(dtype="float64")
    bs = g["bat_speed"].to_numpy(dtype="float64")
    thr = np.quantile(ad, 2 / 3)
    pull = ad >= thr
    return pd.Series({
        "ad_std": float(np.nanstd(ad, ddof=1)) if len(ad) > 1 else np.nan,
        "pull_rate": float(np.mean(ad > 10)),
        "bs_on_pull": float(np.nanmean(bs[pull])) if pull.any() else np.nan,
        "aa_on_pull": float(np.nanmean(aa[pull])) if pull.any() else np.nan,
        "pull_lift_rate": float(np.mean((ad > 10) & (aa > 10))),
    })


def ad_features_per_half(label: str) -> pd.DataFrame:
    df = pd.read_parquet(
        RAW / f"statcast_{label}.parquet",
        columns=["batter", "bat_speed", "swing_length", "attack_angle",
                 "attack_direction", "swing_path_tilt",
                 "intercept_ball_minus_batter_pos_x_inches",
                 "intercept_ball_minus_batter_pos_y_inches", "type"],
    )
    sw = MODEL.filter_swings(df)
    feats = sw.groupby("batter").apply(_group_feats, include_groups=False).reset_index()
    feats["half"] = label
    return feats


def grounding() -> None:
    print("=" * 84)
    print("PART 1 — Does pulling -> higher EV?")
    print("=" * 84)
    frames = []
    for label in HALVES:
        df = pd.read_parquet(
            RAW / f"statcast_{label}.parquet",
            columns=["type", "launch_speed", "launch_angle",
                     "estimated_woba_using_speedangle",
                     "attack_direction", "bat_speed", "swing_length",
                     "attack_angle", "swing_path_tilt", "hc_x", "hc_y", "stand"],
        )
        sw = MODEL.filter_swings(df)
        bip = sw[(sw["type"] == "X") & sw["launch_speed"].notna()].copy()
        frames.append(bip)
    bip = pd.concat(frames, ignore_index=True)

    # (a) swing-aim pull
    bip["ad_q"] = pd.qcut(bip["attack_direction"], 5,
                          labels=["Q1 oppo", "Q2", "Q3", "Q4", "Q5 pull"])
    print("\n(a) SWING-AIM pull (attack_direction) -> EV, all BIP:")
    print(bip.groupby("ad_q")["launch_speed"].mean().round(2).to_string())

    # pull x lift cell table
    bip["aim"] = pd.cut(bip["attack_direction"], [-90, -8, 8, 90],
                        labels=["oppo aim", "center", "pull aim"])
    bip["traj"] = pd.cut(bip["launch_angle"], [-90, 10, 40, 90],
                         labels=["ground", "drive (10-40)", "pop"])
    print("\n   mean EV by aim x trajectory:")
    print(bip.pivot_table("launch_speed", "aim", "traj", aggfunc="mean").round(1).to_string())
    print("\n   mean xwOBAcon by aim x trajectory:")
    print(bip.pivot_table("estimated_woba_using_speedangle", "aim", "traj",
                          aggfunc="mean").round(3).to_string())

    # (b) spray pull
    spray = np.degrees(np.arctan2(bip["hc_x"] - 125.42, 198.27 - bip["hc_y"]))
    bip["pull_side"] = np.where(bip["stand"] == "L", spray, -spray)
    bip["spray_bucket"] = pd.cut(bip["pull_side"], [-90, -10, 10, 90],
                                 labels=["oppo", "center", "pull"])
    bip["air"] = bip["launch_angle"] >= 10
    print("\n(b) SPRAY pull (where ball lands) -> EV:")
    print(bip.groupby("spray_bucket")["launch_speed"].mean().round(2).to_string())
    print("\n   mean EV by spray x air/ground:")
    print(bip.pivot_table("launch_speed", "spray_bucket",
                          bip["air"].map({True: "air", False: "ground"}),
                          aggfunc="mean").round(1).to_string())
    print("\n   mean xwOBAcon by spray x air/ground:")
    print(bip.pivot_table("estimated_woba_using_speedangle", "spray_bucket",
                          bip["air"].map({True: "air", False: "ground"}),
                          aggfunc="mean").round(3).to_string())


def next_half(h: str) -> str:
    season, sh = h.split("_")
    return f"{season}_H2" if sh == "H1" else f"{int(season) + 1}_H1"


def eval_set(frame: pd.DataFrame, feats: list[str], target: str) -> float:
    sub = frame.dropna(subset=feats + [target])
    return cv_eval(sub[feats], sub[target], sub["batter"])["r"]


def run_block(frame: pd.DataFrame, suffix: str, sets: dict) -> pd.DataFrame:
    rows = []
    for tcol, label, _ in TARGETS:
        r = {"target": label}
        for name, feats in sets.items():
            r[name] = round(eval_set(frame, feats, tcol + suffix), 3)
        r["AD|base"] = round(r["base+AD"] - r["base9"], 3)
        r["AD|appr"] = round(r["appr+AD"] - r["appr17"], 3)
        rows.append(r)
    return pd.DataFrame(rows)


def main() -> None:
    grounding()

    print("\nBuilding clean attack-direction features...")
    base = pd.read_csv(PROCESSED / "validation_concurrent.csv")
    approach = pd.concat([approach_per_half(h) for h in HALVES], ignore_index=True)
    adf = pd.concat([ad_features_per_half(h) for h in HALVES], ignore_index=True)
    woba = pd.concat([woba_per_half(h) for h in HALVES], ignore_index=True)
    m = (base.merge(approach, on=["batter", "half"], how="inner")
         .merge(adf, on=["batter", "half"], how="inner")
         .merge(woba, on=["batter", "half"], how="inner"))
    m = m[m["n_pa"] >= 50]
    m["_ev_resid"] = m["obs_avg_ev"] - m["pred_avg_ev"]
    print(f"  {len(m):,} player-halves\n")
    print("Attack-direction feature correlation with EV residual (obs-pred):")
    for f in AD_FEATS:
        s = m.dropna(subset=[f, "_ev_resid"])
        print(f"  {f:<22} r = {np.corrcoef(s[f], s['_ev_resid'])[0,1]:+.3f}")

    sets = {
        "base9":   BASELINE_FEATS,
        "base+AD": BASELINE_FEATS + AD_FEATS,
        "appr17":  BASELINE_FEATS + APPROACH_FEATS,
        "appr+AD": BASELINE_FEATS + APPROACH_FEATS + AD_FEATS,
    }
    print("\n" + "=" * 88)
    print("PART 2 CONCURRENT — features(H) -> target(H)")
    print("=" * 88)
    print(run_block(m, "", sets).to_string(index=False))

    m2 = m.copy()
    m2["next_half"] = m2["half"].map(next_half)
    tgt_next = m[["batter", "half"] + [t for t, _, _ in TARGETS]].rename(
        columns={"half": "next_half", **{t: t + "_next" for t, _, _ in TARGETS}})
    pf = m2.merge(tgt_next, on=["batter", "next_half"], how="inner")
    print("\n" + "=" * 88)
    print(f"PART 2 PREDICTIVE — features(H_t) -> target(H_t+1).  VERDICT.  ({len(pf):,} rows)")
    print("=" * 88)
    pred = run_block(pf, "_next", sets)
    print(pred.to_string(index=False))
    print("\n  AD|base = lift from pull features on bat-tracking only.")
    print("  AD|appr = lift from pull features on top of appr17.")
    pred.to_csv(PROCESSED / "attack_direction_predictive.csv", index=False)
    print("\nSaved attack_direction_predictive.csv")


if __name__ == "__main__":
    main()
