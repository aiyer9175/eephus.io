# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
concurrent_analysis.py — How well do the predicted stats match what those
exact swings actually produced?

Uses data/processed/validation_concurrent.csv (predicted + observed joined
at the player-half level).

Reports:
  1. Headline fit (r, R², MAE, RMSE, bias)
  2. Decile calibration — does the prediction ranking hold up?
  3. Sample players: top of the predicted board with side-by-side actuals
  4. Where the model is wrong — biggest over- and under-predictions
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).parent
PROCESSED = PROJECT / "data" / "processed"

STATS = [
    # (pred col, obs col, label, decimals)
    ("pred_avg_ev",       "obs_avg_ev",       "Avg EV (mph)",  1),
    ("pred_hard_hit_pct", "obs_hard_hit_pct", "Hard-Hit %",    1),
    ("pred_barrel_pct",   "obs_barrel_pct",   "Barrel %",      1),
    ("pred_avg_la",       "obs_avg_la",       "Avg LA (deg)",  1),
    ("pred_xwobacon",     "obs_xwobacon",     "xwOBAcon",      3),
]


def headline(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for p, o, label, dec in STATS:
        sub = df.dropna(subset=[p, o])
        x, y = sub[p].to_numpy(), sub[o].to_numpy()
        r = float(np.corrcoef(x, y)[0, 1])
        # R² of obs by pred via linear fit (== r² when 1-D linear)
        diff = x - y
        rows.append({
            "stat": label,
            "n": len(sub),
            "r": round(r, 3),
            "R²": round(r ** 2, 3),
            "MAE": round(float(np.abs(diff).mean()), dec + 1),
            "RMSE": round(float(np.sqrt((diff ** 2).mean())), dec + 1),
            "bias (pred-obs)": round(float(diff.mean()), dec + 1),
            "obs SD": round(float(np.std(y)), dec + 1),
        })
    return pd.DataFrame(rows)


def decile_calibration(df: pd.DataFrame, pcol: str, ocol: str, dec: int) -> pd.DataFrame:
    sub = df.dropna(subset=[pcol, ocol]).copy()
    sub["decile"] = pd.qcut(sub[pcol], 10,
                            labels=[f"D{i}" for i in range(1, 11)])
    rows = []
    for d, g in sub.groupby("decile"):
        rows.append({
            "decile": d,
            "n": len(g),
            "pred mean": round(g[pcol].mean(), dec),
            "obs mean": round(g[ocol].mean(), dec),
            "obs median": round(g[ocol].median(), dec),
            "Δ (pred-obs)": round(g[pcol].mean() - g[ocol].mean(), dec + 1),
        })
    return pd.DataFrame(rows)


def main():
    df = pd.read_csv(PROCESSED / "validation_concurrent.csv")
    print(f"loaded {len(df):,} player-halves\n")

    # 1. Headline
    print("=" * 84)
    print("1. HEADLINE FIT — pred vs obs on the same swings")
    print("=" * 84)
    print(headline(df).to_string(index=False))

    # 2. Decile calibration for each stat (concise: just xwOBAcon + Barrel%
    #    fully; the others get one summary line on Q10-Q1 spread)
    print("\n" + "=" * 84)
    print("2. DECILE CALIBRATION — does the ranking translate to outcome?")
    print("=" * 84)
    for p, o, label, dec in STATS:
        tbl = decile_calibration(df, p, o, dec)
        spread_pred = tbl["pred mean"].iloc[-1] - tbl["pred mean"].iloc[0]
        spread_obs  = tbl["obs mean"].iloc[-1]  - tbl["obs mean"].iloc[0]
        print(f"\n{label}:  D10-D1 pred spread = {spread_pred:+.{dec+1}f},  "
              f"obs spread = {spread_obs:+.{dec+1}f}")
        print(tbl.to_string(index=False))

    # 3. Sample: top 12 by predicted xwOBAcon, side by side w/ all 5 actuals
    print("\n" + "=" * 84)
    print("3. SAMPLE PLAYERS — top 12 by predicted xwOBAcon (any half),")
    print("   each row = one player-half; predicted vs observed")
    print("=" * 84)
    top = df.nlargest(12, "pred_xwobacon").copy()
    show_cols = ["name", "half", "n_swings"]
    for p, o, _, dec in STATS:
        top[f"{p}_r"] = top[p].round(dec)
        top[f"{o}_r"] = top[o].round(dec)
        show_cols += [f"{p}_r", f"{o}_r"]
    rename = {}
    for p, o, label, _ in STATS:
        short = {"Avg EV (mph)": "EV", "Hard-Hit %": "HH%", "Barrel %": "Brl%",
                 "Avg LA (deg)": "LA", "xwOBAcon": "xwOBAcon"}[label]
        rename[f"{p}_r"] = f"P_{short}"
        rename[f"{o}_r"] = f"O_{short}"
    print(top[show_cols].rename(columns=rename).to_string(index=False))

    # 4. Where the model is wrong — biggest miss on xwOBAcon
    print("\n" + "=" * 84)
    print("4. WHERE THE MODEL IS WRONG — biggest xwOBAcon misses")
    print("   (player-halves with ≥ 400 swings to filter sample-size noise)")
    print("=" * 84)
    sub = df.dropna(subset=["pred_xwobacon", "obs_xwobacon"]).copy()
    sub = sub[sub["n_swings"] >= 400]
    sub["resid"] = sub["pred_xwobacon"] - sub["obs_xwobacon"]
    print("\nTop 10 OVER-predictions (model thinks better than they hit):")
    cols = ["name", "half", "n_swings",
            "pred_xwobacon", "obs_xwobacon", "resid"]
    over = sub.nlargest(10, "resid")[cols].copy()
    for c in ["pred_xwobacon", "obs_xwobacon", "resid"]:
        over[c] = over[c].round(3)
    print(over.to_string(index=False))

    print("\nTop 10 UNDER-predictions (player hit better than swing suggested):")
    under = sub.nsmallest(10, "resid")[cols].copy()
    for c in ["pred_xwobacon", "obs_xwobacon", "resid"]:
        under[c] = under[c].round(3)
    print(under.to_string(index=False))


if __name__ == "__main__":
    main()
