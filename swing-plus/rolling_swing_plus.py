# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
rolling_swing_plus.py — Swing+ over time via a trailing-window profile.

Per-game Swing+ is meaningless (3-6 competitive swings/game -> unstable mean/SD,
and reliability weighting pins it at ~100). Instead we roll a window of the last
W competitive swings and score the RAW Swing+ (no cross-player shrinkage needed
when tracking a single hitter's trajectory).

Usage: edit PLAYERS / WINDOW. Saves data/processed/swing_plus_over_time.png
"""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from swing_plus import SwingPlusModel

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
PROC = PROJECT / "data" / "processed"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2", "2026_H1"]
MODEL = SwingPlusModel(PROJECT / "swing_plus_model_v1.joblib")
WINDOW = 150     # trailing competitive swings per point
PLAYERS = ["Aaron Judge", "Bo Bichette", "Steven Kwan"]


def player_ids(names):
    at = pd.read_parquet(PROC / "leaderboard_alltime.parquet")[["name", "batter"]]
    m = dict(zip(at["name"], at["batter"]))
    return {n: m[n] for n in names if n in m}


def all_swings(bid):
    frames = []
    for h in HALVES:
        df = pd.read_parquet(RAW / f"statcast_{h}.parquet")
        f = df[df["batter"] == bid]
        if len(f):
            sw = MODEL.filter_swings(f)
            frames.append(sw)
    sw = pd.concat(frames, ignore_index=True)
    sw["game_date"] = pd.to_datetime(sw["game_date"])
    # order within season; sort by date then by pitch order if present
    sort_cols = ["game_date"] + [c for c in ["at_bat_number", "pitch_number"] if c in sw.columns]
    return sw.sort_values(sort_cols).reset_index(drop=True)


def rolling_swing_plus(sw, window=WINDOW):
    """Rolling raw Swing+ on a trailing window of `window` swings."""
    prof = pd.DataFrame(index=sw.index)
    for col in MODEL.tracking_cols:
        prof[f"{col}_mean"] = sw[col].rolling(window).mean()
        prof[f"{col}_std"] = sw[col].rolling(window).std()
    prof["n_swings"] = window
    prof = prof.dropna(subset=MODEL.features)
    scored = MODEL.score_profiles(prof, reliability_weight=False)
    out = pd.DataFrame({"game_date": sw.loc[scored.index, "game_date"].values,
                        "swing_plus_raw": scored["swing_plus_raw"].values})
    # one point per game (last window value that day)
    return out.groupby("game_date", as_index=False).last()


def main():
    ids = player_ids(PLAYERS)
    print(f"players: {ids}")
    fig, ax = plt.subplots(figsize=(13, 6))
    colors = ["#e6a83c", "#4f9eff", "#cc5555"]
    summary = []
    for (name, bid), c in zip(ids.items(), colors):
        sw = all_swings(bid)
        ts = rolling_swing_plus(sw)
        ax.plot(ts["game_date"], ts["swing_plus_raw"], lw=1.6, color=c, label=name, alpha=0.9)
        summary.append((name, len(sw), ts["swing_plus_raw"].min(), ts["swing_plus_raw"].max()))
    # half boundaries
    for h in HALVES:
        y, half = h.split("_")
        d = pd.Timestamp(f"{y}-07-15") if half == "H2" else pd.Timestamp(f"{y}-03-28")
        ax.axvline(d, color="#333", ls=":", lw=0.6)
    ax.axhline(100, color="#888", ls="--", lw=1)
    ax.set_title(f"Swing+ over time — trailing {WINDOW}-swing window (raw, no reliability shrinkage)")
    ax.set_ylabel("Swing+ (raw)"); ax.set_xlabel("date")
    ax.legend(frameon=False)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    out = PROC / "swing_plus_over_time.png"
    fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="white")
    print(f"\nsaved {out}")
    print(f"{'player':<16}{'swings':>8}{'min':>8}{'max':>8}")
    for name, n, lo, hi in summary:
        print(f"{name:<16}{n:>8}{lo:>8.1f}{hi:>8.1f}")


if __name__ == "__main__":
    main()
