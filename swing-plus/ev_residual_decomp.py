# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
ev_residual_decomp.py — What's in the EV prediction error?

Our predicted EV comes from swing geometry (bat speed, swing length, attack
angle, contact point, etc.). The residual (obs EV - pred EV) is everything
about the bat-ball collision the swing aggregates can't see.

This script decomposes that residual:
  1. Judge case study — is he systematically under-predicted, and is it
     collision efficiency?
  2. Residual autocorrelation (resid_t vs resid_{t+1}) — is the error a
     STABLE player trait (a real missing feature) or random NOISE?
  3. What stable trait is it? Cross-half: does collision efficiency
     (smash factor) at H_t predict the EV under-prediction at H_{t+1}?
     (Cross-half avoids the mechanical same-half EV-in-both circularity.)
  4. Between-player vs within-player variance of the residual.

smash_factor = EV / bat_speed on each ball in play, averaged per half.
A rough collision-efficiency proxy (true smash factor also folds in pitch
speed; we report mean pitch speed on contact separately).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
PROCESSED = PROJECT / "data" / "processed"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]


def collision_per_half(label: str) -> pd.DataFrame:
    df = pd.read_parquet(
        RAW / f"statcast_{label}.parquet",
        columns=["batter", "type", "launch_speed", "bat_speed", "release_speed"],
    )
    bip = df[(df["type"] == "X") & df["bat_speed"].notna()
             & df["launch_speed"].notna() & (df["bat_speed"] > 30)].copy()
    bip["smash"] = bip["launch_speed"] / bip["bat_speed"]
    agg = bip.groupby("batter", as_index=False).agg(
        n_bip_coll=("launch_speed", "size"),
        ev_bip=("launch_speed", "mean"),
        batspeed_bip=("bat_speed", "mean"),
        smash_factor=("smash", "mean"),
        ev_bip_std=("launch_speed", "std"),
        pitch_speed_bip=("release_speed", "mean"),
        ev_max=("launch_speed", lambda s: s.quantile(0.90)),  # top-end EV
    )
    agg["half"] = label
    return agg


def next_half(h: str) -> str:
    season, sh = h.split("_")
    return f"{season}_H2" if sh == "H1" else f"{int(season) + 1}_H1"


def main() -> None:
    base = pd.read_csv(PROCESSED / "validation_concurrent.csv")
    coll = pd.concat([collision_per_half(h) for h in HALVES], ignore_index=True)
    df = base.merge(coll, on=["batter", "half"], how="inner")
    df = df[df["n_bip_coll"] >= 40].copy()
    df["resid"] = df["obs_avg_ev"] - df["pred_avg_ev"]
    print(f"{len(df):,} player-halves with >= 40 BIP\n")

    # ---- 1. Judge case study ----
    print("=" * 84)
    print("1. AARON JUDGE — predicted vs observed EV, with collision metrics")
    print("=" * 84)
    judge = df[df["name"] == "Aaron Judge"].sort_values("half")
    cols = ["half", "n_bip_coll", "pred_avg_ev", "obs_avg_ev", "resid",
            "batspeed_bip", "smash_factor", "pitch_speed_bip"]
    jt = judge[cols].copy()
    for c in ["pred_avg_ev", "obs_avg_ev", "resid", "batspeed_bip", "pitch_speed_bip"]:
        jt[c] = jt[c].round(2)
    jt["smash_factor"] = jt["smash_factor"].round(3)
    print(jt.to_string(index=False))
    # smash factor percentile of Judge vs league
    lg_smash = df.groupby("batter")["smash_factor"].mean()
    judge_id = judge["batter"].iloc[0]
    pct = (lg_smash < lg_smash.loc[judge_id]).mean() * 100
    print(f"\nJudge career smash factor (EV/bat_speed) = {lg_smash.loc[judge_id]:.3f}"
          f"  → {pct:.0f}th percentile of {len(lg_smash)} hitters")
    print(f"League mean smash factor = {lg_smash.mean():.3f}, SD = {lg_smash.std():.3f}")

    # ---- 2. Residual autocorrelation: stable trait or noise? ----
    print("\n" + "=" * 84)
    print("2. EV RESIDUAL: stable player trait or noise?")
    print("=" * 84)
    nx = df.copy()
    nx["next_half"] = nx["half"].map(next_half)
    nxt = df[["batter", "half", "resid"]].rename(
        columns={"half": "next_half", "resid": "resid_next"})
    pair = nx.merge(nxt, on=["batter", "next_half"], how="inner")
    r_auto = float(np.corrcoef(pair["resid"], pair["resid_next"])[0, 1])
    print(f"  resid(H_t) vs resid(H_t+1):  r = {r_auto:.3f}   (n={len(pair)})")
    print(f"  → {r_auto**2*100:.0f}% of the EV residual is a REPEATABLE player trait")
    print(f"    (a real feature we're missing); the rest is half-to-half noise.")

    # ---- 3. What is the stable part? Cross-half smash -> resid ----
    print("\n" + "=" * 84)
    print("3. IS THE STABLE PART COLLISION EFFICIENCY? (cross-half, non-circular)")
    print("=" * 84)
    smash_t = df[["batter", "half", "smash_factor", "pitch_speed_bip"]].copy()
    smash_t["next_half"] = smash_t["half"].map(next_half)
    smash_t = smash_t.rename(columns={"smash_factor": "smash_t",
                                      "pitch_speed_bip": "pitch_t"})
    cross = smash_t.merge(
        df[["batter", "half", "resid"]].rename(columns={"half": "next_half"}),
        on=["batter", "next_half"], how="inner")
    r_sm = float(np.corrcoef(cross["smash_t"], cross["resid"])[0, 1])
    r_ps = float(np.corrcoef(cross["pitch_t"], cross["resid"])[0, 1])
    print(f"  smash_factor(H_t)  vs  EV residual(H_t+1):  r = {r_sm:.3f}")
    print(f"    → last half's collision efficiency predicts this half's EV under-prediction.")
    print(f"  pitch_speed_on_contact(H_t) vs EV residual(H_t+1): r = {r_ps:.3f}")

    # ---- 4. Between vs within player variance ----
    print("\n" + "=" * 84)
    print("4. VARIANCE DECOMPOSITION of the EV residual")
    print("=" * 84)
    multi = df.groupby("batter").filter(lambda g: len(g) >= 3)
    player_mean = multi.groupby("batter")["resid"].mean()
    between_var = float(player_mean.var())
    within_var = float(multi.groupby("batter")["resid"].var().mean())
    total = between_var + within_var
    print(f"  (players with >= 3 halves: {multi['batter'].nunique()})")
    print(f"  between-player variance (systematic, missing skill): {between_var:.3f} "
          f"({between_var/total*100:.0f}%)")
    print(f"  within-player variance  (half-to-half noise):        {within_var:.3f} "
          f"({within_var/total*100:.0f}%)")
    print(f"  residual SD overall: {df['resid'].std():.2f} mph")

    # ---- 5. Who else beats / misses their predicted EV most (stable) ----
    print("\n" + "=" * 84)
    print("5. MOST UNDER-PREDICTED hitters (career mean resid, >=3 halves)")
    print("   — these are the elite-collision guys the swing model can't fully credit")
    print("=" * 84)
    career = (multi.groupby(["batter"])
              .agg(name=("name", "first"),
                   halves=("half", "size"),
                   mean_resid=("resid", "mean"),
                   smash=("smash_factor", "mean"),
                   batspeed=("batspeed_bip", "mean"),
                   ev=("obs_avg_ev", "mean"))
              .reset_index())
    top = career.nlargest(12, "mean_resid")[
        ["name", "halves", "mean_resid", "ev", "batspeed", "smash"]].copy()
    for c in ["mean_resid", "ev", "batspeed"]:
        top[c] = top[c].round(2)
    top["smash"] = top["smash"].round(3)
    print(top.to_string(index=False))


if __name__ == "__main__":
    main()
