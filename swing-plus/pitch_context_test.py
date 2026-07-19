# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
pitch_context_test.py — Does pitch-context add real predictive signal for
batted-ball outcomes and offensive value?

Pitch-context features are built to AVOID the sweet-spot leakage trap:
none are derived from launch_speed / launch_angle (the BIP target metrics).

Two kinds:
  ENVIRONMENT (exogenous — what pitchers throw him; the hitter doesn't
  control this within a half):
     fastball_rate, breaking_rate, avg_velo_faced, avg_spin_faced, zone_rate
  SWING-DECISION (computed from swing/whiff, NOT from BIP launch metrics —
  same clean category as the approach features that legitimately helped):
     whiff_rate_fastball, whiff_rate_breaking

Feature sets, GroupKFold(5) on batter:
  base9   : 9 bat-tracking features
  base+PC : base9 + 7 pitch-context
  appr17  : base9 + 8 approach features (current best)
  appr+PC : appr17 + 7 pitch-context

Reported both CONCURRENT (features(H) -> target(H)) and PREDICTIVE
(features(H_t) -> target(H_t+1)). Predictive is the verdict.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from augmented_model_test import (
    APPROACH_FEATS, BASELINE_FEATS, SWING_DESCS, WHIFF_DESCS,
    approach_per_half, cv_eval, woba_per_half,
)
from validate_predictions import observed_per_half

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
PROCESSED = PROJECT / "data" / "processed"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]

FASTBALLS = {"FF", "SI", "FC", "FA", "FT"}
BREAKING = {"SL", "ST", "CU", "KC", "SV", "CS", "KN", "SC", "EP"}

PITCHCTX_FEATS = [
    "fastball_rate", "breaking_rate", "avg_velo_faced", "avg_spin_faced",
    "zone_rate", "whiff_rate_fastball", "whiff_rate_breaking",
]

TARGETS = [
    ("obs_avg_ev",       "Avg EV (mph)",    1),
    ("obs_hard_hit_pct", "Hard-Hit %",      1),
    ("obs_barrel_pct",   "Barrel %",        1),
    ("obs_avg_la",       "Avg LA (deg)",    1),
    ("obs_xwobacon",     "xwOBAcon",        3),
    ("wOBA",             "wOBA (full PA)",  3),
    ("xwOBA",            "xwOBA (full PA)", 3),
]


def pitch_context_per_half(label: str) -> pd.DataFrame:
    df = pd.read_parquet(
        RAW / f"statcast_{label}.parquet",
        columns=["batter", "pitch_type", "release_speed",
                 "release_spin_rate", "zone", "description"],
    )
    df["is_fb"] = df["pitch_type"].isin(FASTBALLS)
    df["is_br"] = df["pitch_type"].isin(BREAKING)
    df["in_zone"] = df["zone"].between(1, 9).fillna(False)
    df["is_swing"] = df["description"].isin(SWING_DESCS)
    df["is_whiff"] = df["description"].isin(WHIFF_DESCS)

    g = df.groupby("batter")
    out = pd.DataFrame({
        "fastball_rate": g["is_fb"].mean(),
        "breaking_rate": g["is_br"].mean(),
        "avg_velo_faced": g["release_speed"].mean(),
        "avg_spin_faced": g["release_spin_rate"].mean(),
        "zone_rate": g["in_zone"].mean(),
    })
    fb = df[df["is_fb"]].groupby("batter")
    br = df[df["is_br"]].groupby("batter")
    out["whiff_rate_fastball"] = fb["is_whiff"].sum() / fb["is_swing"].sum()
    out["whiff_rate_breaking"] = br["is_whiff"].sum() / br["is_swing"].sum()
    out = out.reset_index()
    out["half"] = label
    return out


def next_half(h: str) -> str:
    season, sh = h.split("_")
    return f"{season}_H2" if sh == "H1" else f"{int(season) + 1}_H1"


def build_master() -> pd.DataFrame:
    base = pd.read_parquet(PROCESSED / "leaderboard_half.parquet")
    base = base[["batter", "half", "n_swings"] + BASELINE_FEATS]
    approach = pd.concat([approach_per_half(h) for h in HALVES], ignore_index=True)
    pctx = pd.concat([pitch_context_per_half(h) for h in HALVES], ignore_index=True)
    obs = pd.concat([observed_per_half(h) for h in HALVES], ignore_index=True)
    woba = pd.concat([woba_per_half(h) for h in HALVES], ignore_index=True)
    m = (base
         .merge(approach, on=["batter", "half"], how="inner")
         .merge(pctx, on=["batter", "half"], how="inner")
         .merge(obs, on=["batter", "half"], how="inner")
         .merge(woba, on=["batter", "half"], how="inner"))
    m = m[m["n_pa"] >= 50]
    return m


def eval_set(frame: pd.DataFrame, feats: list[str], target: str) -> float:
    sub = frame.dropna(subset=feats + [target])
    return cv_eval(sub[feats], sub[target], sub["batter"])["r"]


def run_block(frame: pd.DataFrame, target_suffix: str, sets: dict) -> pd.DataFrame:
    rows = []
    for tcol, label, dec in TARGETS:
        r = {"target": label}
        for name, feats in sets.items():
            r[name] = round(eval_set(frame, feats, tcol + target_suffix), 3)
        r["PC|base"] = round(r["base+PC"] - r["base9"], 3)
        r["PC|appr"] = round(r["appr+PC"] - r["appr17"], 3)
        rows.append(r)
    return pd.DataFrame(rows)


def main() -> None:
    print("Building master frame (bat-tracking + approach + pitch-context + targets)...")
    m = build_master()
    print(f"  {len(m):,} player-halves, {m['batter'].nunique()} batters")
    # report any rows dropped for missing pitch-ctx
    miss = m[PITCHCTX_FEATS].isna().any(axis=1).sum()
    print(f"  rows with any missing pitch-ctx feature: {miss}")

    print("\nPitch-context raw correlation with each target (same half):")
    for tcol, label, _ in TARGETS:
        cors = {f: round(float(m[[f, tcol]].dropna().corr().iloc[0, 1]), 2)
                for f in PITCHCTX_FEATS}
        print(f"  {label:<16} {cors}")

    sets = {
        "base9":   BASELINE_FEATS,
        "base+PC": BASELINE_FEATS + PITCHCTX_FEATS,
        "appr17":  BASELINE_FEATS + APPROACH_FEATS,
        "appr+PC": BASELINE_FEATS + APPROACH_FEATS + PITCHCTX_FEATS,
    }

    print("\n" + "=" * 96)
    print("CONCURRENT — features(H) -> target(H)")
    print("=" * 96)
    conc = run_block(m, "", sets)
    print(conc.to_string(index=False))

    m2 = m.copy()
    m2["next_half"] = m2["half"].map(next_half)
    tgt_next = m[["batter", "half"] + [t for t, _, _ in TARGETS]].rename(
        columns={"half": "next_half",
                 **{t: t + "_next" for t, _, _ in TARGETS}})
    pf = m2.merge(tgt_next, on=["batter", "next_half"], how="inner")

    print("\n" + "=" * 96)
    print(f"PREDICTIVE — features(H_t) -> target(H_t+1).  VERDICT.  ({len(pf):,} rows)")
    print("=" * 96)
    pred = run_block(pf, "_next", sets)
    print(pred.to_string(index=False))
    print("\n  PC|base = lift from adding pitch-context to bat-tracking only.")
    print("  PC|appr = lift from adding pitch-context on top of approach features.")

    conc.to_csv(PROCESSED / "pitch_context_concurrent.csv", index=False)
    pred.to_csv(PROCESSED / "pitch_context_predictive.csv", index=False)
    print(f"\nSaved pitch_context_concurrent.csv and pitch_context_predictive.csv")


if __name__ == "__main__":
    main()
