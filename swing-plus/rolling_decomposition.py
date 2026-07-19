# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
rolling_decomposition.py — What drives Swing+ over time?

Swing+ is nonlinear (two poly models combined), so there's no exact additive
split. We use a league-baseline marginal attribution: at each rolling point,
score the profile with ALL features at league average (=> ~100), then flip ONE
feature to its actual value and measure the change. That change is that
feature's marginal contribution. Contributions are normalized to sum to the
point's actual (Swing+ - 100), then grouped and stacked so you can see whether
bat speed / attack angle / contact / etc. is driving the rise or fall.

Prototype: one player, continuous career rolling window. Saves a stacked-area
PNG with the total Swing+ line overlaid.
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
FEATS = MODEL.features
WINDOW = 150
PLAYER = "Bo Bichette"

# group the 9 features for a legible stacked chart
GROUPS = {
    "Bat speed": ["bat_speed_mean", "bat_speed_std"],
    "Attack angle": ["attack_angle_mean", "attack_angle_std"],
    "Swing length": ["swing_length_mean"],
    "Attack direction": ["attack_direction_mean"],
    "Swing tilt": ["swing_path_tilt_mean"],
    "Contact point": ["intercept_ball_minus_batter_pos_x_inches_mean",
                      "intercept_ball_minus_batter_pos_y_inches_mean"],
}
COLORS = {"Bat speed": "#1f6fd6", "Attack angle": "#e6a83c", "Swing length": "#2e9e6b",
          "Attack direction": "#9b59b6", "Swing tilt": "#cc5555", "Contact point": "#888888"}


def league_baseline():
    h = pd.read_parquet(PROC / "leaderboard_half.parquet")
    w = h["n_swings"]
    return {f: float(np.average(h[f].dropna(), weights=w[h[f].notna()])) for f in FEATS}


def sp_raw(profiles):
    p = profiles.copy(); p["n_swings"] = WINDOW
    return MODEL.score_profiles(p, reliability_weight=False)["swing_plus_raw"].values


def main():
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
    sw = sw.sort_values(order).reset_index(drop=True)

    # rolling profile (means/stds) over the career
    prof = pd.DataFrame(index=sw.index)
    for col in MODEL.tracking_cols:
        prof[f"{col}_mean"] = sw[col].rolling(WINDOW).mean()
        prof[f"{col}_std"] = sw[col].rolling(WINDOW).std()
    prof["game_date"] = sw["game_date"].values
    prof = prof.dropna(subset=FEATS).reset_index(drop=True)
    prof = prof.groupby("game_date", as_index=False).last()      # one point per date

    base = league_baseline()
    sp0 = sp_raw(pd.DataFrame([base]))[0]                         # baseline Swing+ (~100)

    # batched marginal attribution: per point -> full row + 9 single-feature rows
    rows, tag = [], []
    for _, r in prof.iterrows():
        rows.append({f: r[f] for f in FEATS}); tag.append("full")
        for f in FEATS:
            row = dict(base); row[f] = r[f]; rows.append(row); tag.append(f)
    scored = sp_raw(pd.DataFrame(rows))
    scored = scored.reshape(len(prof), len(FEATS) + 1)           # col0=full, rest=features
    sp_full = scored[:, 0]
    contrib = scored[:, 1:] - sp0                                # marginal per feature
    # normalize so contributions sum to (sp_full - sp0)
    s = contrib.sum(axis=1, keepdims=True)
    scale = np.where(np.abs(s) > 1e-6, (sp_full[:, None] - sp0) / s, 0)
    contrib = contrib * scale
    cdf = pd.DataFrame(contrib, columns=FEATS)
    grp = pd.DataFrame({g: cdf[cols].sum(axis=1) for g, cols in GROUPS.items()})

    # ---- plot: stacked contributions (from baseline ~100) + total Swing+ ----
    x = prof["game_date"].values
    fig, ax = plt.subplots(figsize=(13, 6.2), facecolor="white")
    pos = np.full(len(x), sp0, dtype=float)
    neg = np.full(len(x), sp0, dtype=float)
    for g in GROUPS:
        v = grp[g].values
        up = np.where(v >= 0, v, 0); dn = np.where(v < 0, v, 0)
        ax.fill_between(x, pos, pos + up, color=COLORS[g], alpha=0.85, label=g, linewidth=0)
        ax.fill_between(x, neg + dn, neg, color=COLORS[g], alpha=0.85, linewidth=0)
        pos += up; neg += dn
    ax.plot(x, sp_full, color="#111", lw=2, label="Swing+ (total)")
    ax.axhline(sp0, color="#666", ls="--", lw=1)
    ax.set_title(f"{PLAYER} — what drives Swing+ (rolling {WINDOW}-swing, league-baseline attribution)")
    ax.set_ylabel("Swing+  (bands = each component's contribution vs league avg)")
    ax.set_xlabel("date")
    ax.legend(frameon=False, ncol=4, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.08))
    for s2 in ["top", "right"]:
        ax.spines[s2].set_visible(False)
    fig.tight_layout()
    out = PROC / "swing_plus_decomposition.png"
    fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="white")
    print(f"saved {out}")
    print(f"baseline (league-avg) Swing+ = {sp0:.1f}")
    print(f"\nmean contribution by component (career):")
    print(grp.mean().round(2).sort_values(ascending=False).to_string())


if __name__ == "__main__":
    main()
