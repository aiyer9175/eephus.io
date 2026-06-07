# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
rolling_components.py — Track Swing+ AND its normalized input components on one
graph, so you can see which input is driving the rise/fall.

Each component is z-scored vs the league (player-half distribution): +1 = one SD
above the typical hitter. Swing+ (raw) is overlaid on a second axis. Components
whose line moves WITH the Swing+ line are the drivers.

(Exact & stable — unlike an additive 'portion of Swing+' split, which isn't
valid because Swing+ is nonlinear; see note in chat.)
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
WINDOW = 100
MIN_PERIODS = 40
PLAYER = "Aaron Judge"
SEASON = "2024"

COMPONENTS = [
    ("bat_speed_mean", "Bat speed", "#1f6fd6"),
    ("attack_angle_mean", "Attack angle", "#e6a83c"),
    ("swing_length_mean", "Swing length", "#2e9e6b"),
    ("attack_direction_mean", "Attack direction", "#9b59b6"),
    ("swing_path_tilt_mean", "Swing tilt", "#cc5555"),
    ("intercept_ball_minus_batter_pos_y_inches_mean", "Contact depth", "#777777"),
]


def main():
    h = pd.read_parquet(PROC / "leaderboard_half.parquet")
    lg = {c: (h[c].mean(), h[c].std()) for c, _, _ in COMPONENTS}

    at = pd.read_parquet(PROC / "leaderboard_alltime.parquet")
    bid = int(at.loc[at["name"] == PLAYER, "batter"].iloc[0])
    frames = []
    for hf in HALVES:
        df = pd.read_parquet(RAW / f"statcast_{hf}.parquet")
        f = df[df["batter"] == bid]
        if len(f):
            frames.append(MODEL.filter_swings(f))
    sw = pd.concat(frames, ignore_index=True)
    sw["game_date"] = pd.to_datetime(sw["game_date"])
    order = ["game_date"] + [c for c in ["at_bat_number", "pitch_number"] if c in sw.columns]
    sw = sw.sort_values(order)
    sw = sw[sw["game_date"].dt.year == int(SEASON)].reset_index(drop=True)   # one season

    prof = pd.DataFrame(index=sw.index)
    for col in MODEL.tracking_cols:
        prof[f"{col}_mean"] = sw[col].rolling(WINDOW, min_periods=MIN_PERIODS).mean()
        prof[f"{col}_std"] = sw[col].rolling(WINDOW, min_periods=MIN_PERIODS).std()
    prof["game_date"] = sw["game_date"].values
    prof = prof.dropna(subset=MODEL.features).reset_index(drop=True)
    prof = prof.groupby("game_date", as_index=False).last()

    p = prof.copy(); p["n_swings"] = WINDOW
    prof["swing_plus"] = MODEL.score_profiles(p, reliability_weight=False)["swing_plus_raw"].values

    x = prof["game_date"].values
    fig, ax = plt.subplots(figsize=(13, 6.4), facecolor="white")
    for col, label, color in COMPONENTS:
        mu, sd = lg[col]
        z = (prof[col] - mu) / sd
        ax.plot(x, z, color=color, lw=1.6, alpha=0.9, label=label)
    ax.axhline(0, color="#bbb", lw=1, ls="--")
    ax.set_ylabel("component z-score  (vs league: +1 = one SD above average hitter)")
    ax.set_xlabel("date")

    ax2 = ax.twinx()
    ax2.plot(x, prof["swing_plus"], color="#111", lw=2.6, label="Swing+ (raw)")
    ax2.set_ylabel("Swing+ (raw)", color="#111")

    ax.set_title(f"{PLAYER} {SEASON} — Swing+ and its normalized components "
                 f"(rolling {WINDOW}-swing)")
    l1, lab1 = ax.get_legend_handles_labels()
    l2, lab2 = ax2.get_legend_handles_labels()
    ax.legend(l1 + l2, lab1 + lab2, frameon=False, ncol=4, fontsize=9,
              loc="upper center", bbox_to_anchor=(0.5, -0.08))
    for s in ["top"]:
        ax.spines[s].set_visible(False); ax2.spines[s].set_visible(False)
    fig.tight_layout()
    out = PROC / "swing_plus_components.png"
    fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="white")
    print(f"saved {out}")
    # which component correlates most with Swing+ over time?
    print("\ncorrelation of each component (z) with Swing+ over this player's timeline:")
    for col, label, _ in COMPONENTS:
        r = np.corrcoef(prof[col], prof["swing_plus"])[0, 1]
        print(f"  {label:<18} r = {r:+.2f}")


if __name__ == "__main__":
    main()
