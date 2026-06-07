# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
pa_features.py — Canonical computation of the plate-discipline / approach
features and observed full-PA value stats.

This is the SINGLE source used by both training (train_pa_value.py) and
scoring (run_leaderboard.py), so the appr17 feature definitions can't drift
between the two.

Approach features (8) — computed over ALL pitches seen (discipline rates) and
all competitive swings (timing). These are NOT derived from launch metrics,
so they carry no leakage when predicting batted-ball / PA outcomes:
    swing_rate, whiff_rate, chase_rate, z_swing_rate, z_contact_rate,
    o_contact_rate, aa_dev_from_ideal, contact_depth_std

Observed PA value:
    n_pa, obs_woba, obs_xwoba   (per PA-ending event; xwOBA uses
    estimated_woba_using_speedangle on BIP, woba_value otherwise)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SWING_DESCS = {"hit_into_play", "foul", "swinging_strike",
               "swinging_strike_blocked", "foul_tip"}
WHIFF_DESCS = {"swinging_strike", "swinging_strike_blocked"}

APPROACH_FEATS = [
    "whiff_rate", "swing_rate", "chase_rate",
    "z_swing_rate", "z_contact_rate", "o_contact_rate",
    "aa_dev_from_ideal", "contact_depth_std",
]

IY = "intercept_ball_minus_batter_pos_y_inches"
IDEAL_ATTACK_ANGLE = 12.0


def compute_approach_features(pitches: pd.DataFrame,
                              keys: list[str]) -> pd.DataFrame:
    """Per-(keys) discipline + timing features from raw pitch rows."""
    df = pitches.copy()
    df["_swing"] = df["description"].isin(SWING_DESCS)
    df["_whiff"] = df["description"].isin(WHIFF_DESCS)
    df["_in"] = df["zone"].between(1, 9).fillna(False)
    df["_out"] = ~df["_in"]
    df["_zsw"] = df["_swing"] & df["_in"]
    df["_ozsw"] = df["_swing"] & df["_out"]
    df["_zwh"] = df["_whiff"] & df["_in"]
    df["_ozwh"] = df["_whiff"] & df["_out"]

    g = df.groupby(keys, observed=True)
    a = g.agg(
        n_pitches=("description", "size"),
        n_swings=("_swing", "sum"),
        n_whiffs=("_whiff", "sum"),
        n_in=("_in", "sum"),
        n_out=("_out", "sum"),
        n_zsw=("_zsw", "sum"),
        n_ozsw=("_ozsw", "sum"),
        n_zwh=("_zwh", "sum"),
        n_ozwh=("_ozwh", "sum"),
    )
    a["swing_rate"] = a["n_swings"] / a["n_pitches"]
    a["whiff_rate"] = a["n_whiffs"] / a["n_swings"]
    a["chase_rate"] = a["n_ozsw"] / a["n_out"]
    a["z_swing_rate"] = a["n_zsw"] / a["n_in"]
    a["z_contact_rate"] = 1.0 - a["n_zwh"] / a["n_zsw"]
    a["o_contact_rate"] = 1.0 - a["n_ozwh"] / a["n_ozsw"]

    sw = df[df["bat_speed"].notna()].copy()
    sw["_aadev"] = (sw["attack_angle"] - IDEAL_ATTACK_ANGLE).abs()
    t = sw.groupby(keys, observed=True).agg(
        aa_dev_from_ideal=("_aadev", "mean"),
        contact_depth_std=(IY, "std"),
    )
    out = (a[["whiff_rate", "swing_rate", "chase_rate", "z_swing_rate",
              "z_contact_rate", "o_contact_rate"]]
           .join(t).reset_index())
    return out


def compute_observed_pa_stats(pitches: pd.DataFrame,
                              keys: list[str]) -> pd.DataFrame:
    """Per-(keys) full-PA wOBA / xwOBA over PA-ending events."""
    df = pitches
    pa = df[df["woba_denom"] == 1].copy()
    pa["_xwoba"] = pa["estimated_woba_using_speedangle"]
    non_bip = pa["type"] != "X"
    pa.loc[non_bip, "_xwoba"] = pa.loc[non_bip, "woba_value"]
    out = pa.groupby(keys, observed=True).agg(
        n_pa=("woba_denom", "sum"),
        obs_woba=("woba_value", "mean"),
        obs_xwoba=("_xwoba", "mean"),
    ).reset_index()
    return out


def compute_observed_bip_stats(pitches: pd.DataFrame,
                               keys: list[str]) -> pd.DataFrame:
    """Observed batted-ball outcomes per (keys), to sit beside the model's
    predicted EV / Hard-Hit% / Barrel% / LA / xwOBAcon. Computed on balls in
    play; rates returned on a 0-100 scale to match the predictions."""
    bip = pitches[(pitches["type"] == "X") & pitches["launch_speed"].notna()].copy()
    bip["_hh"] = (bip["launch_speed"] >= 95).astype(float)
    bip["_brl"] = (bip["launch_speed_angle"] == 6).astype(float)
    out = bip.groupby(keys, observed=True).agg(
        n_bip_obs=("launch_speed", "size"),
        obs_avg_ev=("launch_speed", "mean"),
        obs_avg_ev90=("launch_speed", lambda s: s.quantile(0.90)),
        obs_hard_hit_pct=("_hh", "mean"),
        obs_barrel_pct=("_brl", "mean"),
        obs_avg_la=("launch_angle", "mean"),
        obs_xwobacon=("estimated_woba_using_speedangle", "mean"),
    ).reset_index()
    out["obs_hard_hit_pct"] *= 100.0
    out["obs_barrel_pct"] *= 100.0
    return out


# Columns needed from a raw Statcast frame to compute everything above.
REQUIRED_COLUMNS = [
    "batter", "description", "zone", "type",
    "bat_speed", "attack_angle", IY,
    "events", "woba_value", "woba_denom", "estimated_woba_using_speedangle",
]
