# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
shapley_decomposition.py — TRUE additive contribution stack for Swing+.

Group-level Shapley values (6 component groups => 2^6=64 coalitions). Shapley
fairly distributes the nonlinear interaction effects and sums EXACTLY to
(Swing+ - league baseline), so a stacked-area chart is mathematically valid
(no blow-ups). f(S) = Swing+ with groups in S at their actual rolling values
and groups not in S at league average.

Prototype: one player, continuous career rolling window. Stacked area + total.
"""

import warnings; warnings.filterwarnings("ignore")
from math import factorial
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
FEATS = MODEL.features
WINDOW = 100
MIN_PERIODS = 40
PLAYER = "Aaron Judge"
SEASON = "2024"

GROUPS = [
    ("Bat speed", ["bat_speed_mean", "bat_speed_std"], "#1f6fd6"),
    ("Attack angle", ["attack_angle_mean", "attack_angle_std"], "#e6a83c"),
    ("Swing length", ["swing_length_mean"], "#2e9e6b"),
    ("Attack direction", ["attack_direction_mean"], "#9b59b6"),
    ("Swing tilt", ["swing_path_tilt_mean"], "#cc5555"),
    ("Contact point", ["intercept_ball_minus_batter_pos_x_inches_mean",
                       "intercept_ball_minus_batter_pos_y_inches_mean"], "#777777"),
]
NG = len(GROUPS)


def main():
    h = pd.read_parquet(PROC / "leaderboard_half.parquet")
    w = h["n_swings"]
    base = np.array([float(np.average(h[f].dropna(), weights=w[h[f].notna()])) for f in FEATS])
    gcols = [[FEATS.index(f) for f in feats] for _, feats, _ in GROUPS]

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
    prof = prof.dropna(subset=FEATS).reset_index(drop=True)
    prof = prof.groupby("game_date", as_index=False).last()
    X = prof[FEATS].values
    P = len(X)

    # build all 64 coalition profiles x P points, score in one batch
    big = np.empty((64 * P, 9))
    for si in range(64):
        M = np.tile(base, (P, 1))
        for gi in range(NG):
            if si & (1 << gi):
                for c in gcols[gi]:
                    M[:, c] = X[:, c]
        big[si * P:(si + 1) * P] = M
    sdf = pd.DataFrame(big, columns=FEATS); sdf["n_swings"] = WINDOW
    sp = MODEL.score_profiles(sdf, reliability_weight=False)["swing_plus_raw"].values
    f = sp.reshape(64, P)

    # Shapley per group
    shap = np.zeros((NG, P))
    for gi in range(NG):
        bit = 1 << gi
        for si in range(64):
            if si & bit:
                continue
            s = bin(si).count("1")
            wt = factorial(s) * factorial(NG - s - 1) / factorial(NG)
            shap[gi] += wt * (f[si | bit] - f[si])
    sp_base = f[0]            # all-baseline (constant ~100)
    sp_full = f[63]
    err = np.abs(shap.sum(0) - (sp_full - sp_base)).max()
    print(f"baseline Swing+={sp_base[0]:.1f}  | Shapley sum-to-total max error: {err:.4f} (should ~0)")

    x = prof["game_date"].values
    fig, ax = plt.subplots(figsize=(13, 6.4), facecolor="white")
    pos = sp_base.copy(); neg = sp_base.copy()
    for gi, (name, _, color) in enumerate(GROUPS):
        v = shap[gi]
        up = np.clip(v, 0, None); dn = np.clip(v, None, 0)
        ax.fill_between(x, pos, pos + up, color=color, alpha=0.85, label=name, lw=0)
        ax.fill_between(x, neg + dn, neg, color=color, alpha=0.85, lw=0)
        pos += up; neg += dn
    ax.plot(x, sp_full, color="#111", lw=2.4, label="Swing+ (total)")
    ax.axhline(sp_base[0], color="#666", ls="--", lw=1)
    ax.set_title(f"{PLAYER} {SEASON} — Swing+ contribution stack (Shapley, sums exactly to Swing+)")
    ax.set_ylabel("Swing+  (bands = each component's contribution vs league avg)")
    ax.set_xlabel("date")
    ax.legend(frameon=False, ncol=4, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.08))
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    out = PROC / "swing_plus_shapley.png"
    fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="white")
    print(f"saved {out}")
    print("\nmean Shapley contribution (career):")
    for gi, (name, _, _) in enumerate(GROUPS):
        print(f"  {name:<18} {shap[gi].mean():+.1f}")


if __name__ == "__main__":
    main()
