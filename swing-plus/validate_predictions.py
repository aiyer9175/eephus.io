# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
validate_predictions.py — Compare the predicted batted-ball stats from
predicted_stats_models.joblib to the observed values per player-half.

Two views:
  1. Concurrent: pred(H) vs obs(H). Tests model fit. In-sample if the
     model was trained on these halves — expect r close to artifact's
     train_r.
  2. Predictive: pred(H_t) vs obs(H_{t+1}). True forward test of
     whether the predictions carry signal beyond the half in which the
     features were measured.

Outputs:
  data/processed/validation_concurrent.csv
  data/processed/validation_predictive.csv
  data/processed/validation_scatter_concurrent.png
  data/processed/validation_scatter_predictive.png
"""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
PROCESSED = PROJECT / "data" / "processed"

HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]

# (predicted_col, observed_col, label, decimals_for_mae_print)
STATS = [
    ("pred_avg_ev",       "obs_avg_ev",       "Avg EV (mph)",  1),
    ("pred_hard_hit_pct", "obs_hard_hit_pct", "Hard-Hit %",    1),
    ("pred_barrel_pct",   "obs_barrel_pct",   "Barrel %",      1),
    ("pred_avg_la",       "obs_avg_la",       "Avg LA (deg)",  1),
    ("pred_xwobacon",     "obs_xwobacon",     "xwOBAcon",      3),
]


def observed_per_half(label: str) -> pd.DataFrame:
    df = pd.read_parquet(
        RAW / f"statcast_{label}.parquet",
        columns=[
            "batter", "type",
            "launch_speed", "launch_angle",
            "launch_speed_angle", "estimated_woba_using_speedangle",
        ],
    )
    bip = df[df["type"] == "X"].copy()
    bip["hard_hit"] = (bip["launch_speed"] >= 95).astype(float)
    bip["barrel"] = (bip["launch_speed_angle"] == 6).astype(float)
    agg = (
        bip.groupby("batter", as_index=False)
        .agg(
            n_bip_obs=("launch_speed", "size"),
            obs_avg_ev=("launch_speed", "mean"),
            obs_hard_hit_pct=("hard_hit", "mean"),
            obs_barrel_pct=("barrel", "mean"),
            obs_avg_la=("launch_angle", "mean"),
            obs_xwobacon=("estimated_woba_using_speedangle", "mean"),
        )
    )
    # match the predicted scale: pct stats in 0–100, not 0–1
    agg["obs_hard_hit_pct"] *= 100
    agg["obs_barrel_pct"] *= 100
    agg["half"] = label
    return agg


def summarize(df: pd.DataFrame, pairs: list[tuple[str, str, str, int]],
              weights: str | None = None) -> pd.DataFrame:
    rows = []
    for pcol, ocol, label, dec in pairs:
        sub = df.dropna(subset=[pcol, ocol])
        if len(sub) < 3:
            rows.append({"stat": label, "n": len(sub), "r": np.nan,
                         "MAE": np.nan, "RMSE": np.nan, "bias": np.nan})
            continue
        x, y = sub[pcol].to_numpy(), sub[ocol].to_numpy()
        if weights:
            w = sub[weights].to_numpy().astype(float)
            mx, my = np.average(x, weights=w), np.average(y, weights=w)
            cov = np.average((x - mx) * (y - my), weights=w)
            vx = np.average((x - mx) ** 2, weights=w)
            vy = np.average((y - my) ** 2, weights=w)
            r = cov / np.sqrt(vx * vy) if vx > 0 and vy > 0 else np.nan
        else:
            r = float(np.corrcoef(x, y)[0, 1])
        diff = x - y
        rows.append({
            "stat": label,
            "n": len(sub),
            "r": round(r, 3),
            "MAE": round(float(np.abs(diff).mean()), dec + 1),
            "RMSE": round(float(np.sqrt((diff ** 2).mean())), dec + 1),
            "bias": round(float(diff.mean()), dec + 1),
        })
    return pd.DataFrame(rows)


def next_half(h: str) -> str | None:
    season, sh = h.split("_")
    if sh == "H1":
        return f"{season}_H2"
    return f"{int(season) + 1}_H1"


def scatter_grid(df: pd.DataFrame, pairs, title: str, outpath: Path) -> None:
    fig, axes = plt.subplots(1, len(pairs), figsize=(4 * len(pairs), 4))
    if len(pairs) == 1:
        axes = [axes]
    for ax, (pcol, ocol, label, _) in zip(axes, pairs):
        sub = df.dropna(subset=[pcol, ocol])
        x, y = sub[pcol], sub[ocol]
        ax.scatter(x, y, s=8, alpha=0.4, color="#4f9eff", edgecolors="none")
        lo = float(min(x.min(), y.min()))
        hi = float(max(x.max(), y.max()))
        ax.plot([lo, hi], [lo, hi], "--", color="#bbb", lw=1)
        r = float(np.corrcoef(x, y)[0, 1])
        ax.set_title(f"{label}\nn={len(sub)}, r={r:.3f}", fontsize=10)
        ax.set_xlabel("predicted")
        ax.set_ylabel("observed")
        ax.tick_params(labelsize=8)
    fig.suptitle(title, fontsize=12)
    fig.tight_layout()
    fig.savefig(outpath, dpi=130, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    print(f"Computing observed stats from cached halves: {HALVES}")
    obs = pd.concat([observed_per_half(h) for h in HALVES], ignore_index=True)
    print(f"  {len(obs):,} (batter, half) rows of observed stats")

    pred = pd.read_parquet(PROCESSED / "leaderboard_half.parquet")
    print(f"  {len(pred):,} (batter, half) rows of predictions")

    # ----- Concurrent: same half -----
    merged = pred.merge(obs, on=["batter", "half"], how="inner")
    print(f"\nConcurrent merged: {len(merged):,} player-halves")

    pairs = [(p, o, l, d) for p, o, l, d in STATS]
    print("\nCONCURRENT — pred(H) vs obs(H)  [in-sample]")
    print("  Unweighted Pearson r, MAE, RMSE, bias (pred - obs)")
    concur = summarize(merged, pairs)
    print(concur.to_string(index=False))

    print("\n  Weighted by n_swings:")
    concur_w = summarize(merged, pairs, weights="n_swings")
    print(concur_w.to_string(index=False))

    merged.to_csv(PROCESSED / "validation_concurrent.csv", index=False)
    scatter_grid(
        merged, pairs,
        "Concurrent: predicted vs observed (same half)",
        PROCESSED / "validation_scatter_concurrent.png",
    )

    # ----- Predictive: pred at H_t vs obs at H_{t+1} -----
    pred = pred.copy()
    pred["next_half"] = pred["half"].map(next_half)
    obs_next = obs.rename(
        columns={c: c + "_next" for c in obs.columns
                 if c.startswith("obs_") or c == "n_bip_obs"}
    )
    obs_next = obs_next.rename(columns={"half": "next_half"})
    pred_next = pred.merge(obs_next, on=["batter", "next_half"], how="inner")
    print(f"\nPredictive merged: {len(pred_next):,} player-half -> next-half rows")

    next_pairs = [(p, o + "_next", l, d) for p, o, l, d in STATS]
    print("\nPREDICTIVE — pred(H_t) vs obs(H_{t+1})  [forward test]")
    print("  Unweighted Pearson r, MAE, RMSE, bias")
    pred_summary = summarize(pred_next, next_pairs)
    print(pred_summary.to_string(index=False))

    pred_next.to_csv(PROCESSED / "validation_predictive.csv", index=False)
    scatter_grid(
        pred_next, next_pairs,
        "Predictive: pred at half t vs observed at half t+1",
        PROCESSED / "validation_scatter_predictive.png",
    )

    # ----- Baseline: same-stat persistence (obs_t vs obs_t+1) -----
    # Useful context: does the model beat just looking at last half's stat?
    obs_prev = obs.copy()
    obs_prev["next_half"] = obs_prev["half"].map(next_half)
    obs_prev = obs_prev.rename(
        columns={c: c + "_prev" for c in obs.columns
                 if c.startswith("obs_") or c == "n_bip_obs"}
    )
    obs_prev = obs_prev.drop(columns=["half"])
    persistence = obs_prev.merge(
        obs.rename(columns={c: c + "_next" for c in obs.columns
                            if c.startswith("obs_") or c == "n_bip_obs"})
        .rename(columns={"half": "next_half"}),
        on=["batter", "next_half"], how="inner",
    )
    pers_pairs = [(o + "_prev", o + "_next", l, d) for _, o, l, d in STATS]
    print("\nPERSISTENCE BASELINE — obs(H_t) vs obs(H_{t+1})")
    print("  How well does last half's value alone predict next half's value?")
    pers_summary = summarize(persistence, pers_pairs)
    print(pers_summary.to_string(index=False))


if __name__ == "__main__":
    main()
