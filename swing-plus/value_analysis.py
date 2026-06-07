# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
value_analysis.py — Translate the predictive r values into something
baseball-decision-relevant.

Three questions:

1. **Quintile separation.** Bin players by predicted stat at half H_t; look
   at their observed value at half H_{t+1}. The Q5 - Q1 spread is the
   number a front office would care about.

2. **Versus the actual better baseline.** For each stat, compare:
       (a) model:        pred(stat | bat-tracking_t)   → obs(stat)_{t+1}
       (b) persistence:  obs(stat)_t                    → obs(stat)_{t+1}
   If (a) loses to (b), the model isn't pulling its weight.

3. **Hitting value, not just batted-ball quality.** Predicted xwOBAcon is
   BIP-only. The thing that shows up in the box score is full-PA wOBA
   (includes K, BB, HBP). Correlate predicted xwOBAcon at H_t with
   observed wOBA at H_t and at H_{t+1}.

Inputs (already on disk):
   data/processed/validation_predictive.csv   pred(H_t) joined to obs(H_{t+1})
   data/raw/statcast_*.parquet                for full-PA wOBA computation
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from validate_predictions import observed_per_half

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
PROCESSED = PROJECT / "data" / "processed"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]

STATS = [
    ("pred_avg_ev",       "obs_avg_ev",       "Avg EV (mph)",  1),
    ("pred_hard_hit_pct", "obs_hard_hit_pct", "Hard-Hit %",    1),
    ("pred_barrel_pct",   "obs_barrel_pct",   "Barrel %",      1),
    ("pred_avg_la",       "obs_avg_la",       "Avg LA (deg)",  1),
    ("pred_xwobacon",     "obs_xwobacon",     "xwOBAcon",      3),
]


# ---------- 1. Quintile separation ----------

def quintile_table(df: pd.DataFrame, pcol: str, ocol: str, label: str, dec: int) -> str:
    sub = df.dropna(subset=[pcol, ocol]).copy()
    sub["q"] = pd.qcut(sub[pcol], 5, labels=["Q1 (low)", "Q2", "Q3", "Q4", "Q5 (high)"])
    rows = []
    for q, g in sub.groupby("q"):
        rows.append({
            "quintile": q,
            "n": len(g),
            "pred mean": round(g[pcol].mean(), dec),
            "obs next-half mean": round(g[ocol].mean(), dec),
            "obs next-half median": round(g[ocol].median(), dec),
        })
    out = pd.DataFrame(rows)
    spread = out["obs next-half mean"].iloc[-1] - out["obs next-half mean"].iloc[0]
    return f"\n{label} — Q5 - Q1 spread = {spread:+.{dec+1}f}\n" + out.to_string(index=False)


# ---------- 2. Model vs persistence ----------

def head_to_head(pred: pd.DataFrame, obs: pd.DataFrame) -> pd.DataFrame:
    """
    For each stat, compare model and persistence on the SAME rows:
        model:        pred(stat)_t   → obs(stat)_{t+1}
        persistence:  obs(stat)_t    → obs(stat)_{t+1}
    """
    def next_half(h):
        season, sh = h.split("_")
        return f"{season}_H2" if sh == "H1" else f"{int(season)+1}_H1"

    df = pred.copy()
    df["next_half"] = df["half"].map(next_half)
    df = df.merge(obs, on=["batter", "half"], how="inner")
    obs_next = obs.rename(columns={c: c + "_next" for c in obs.columns
                                   if c.startswith("obs_") or c == "n_bip_obs"})
    obs_next = obs_next.rename(columns={"half": "next_half"})
    df = df.merge(obs_next, on=["batter", "next_half"], how="inner")

    rows = []
    for pcol, ocol, label, _ in STATS:
        prev_col, next_col = ocol, ocol + "_next"
        sub = df.dropna(subset=[pcol, prev_col, next_col])
        if len(sub) < 10:
            continue
        rm = float(np.corrcoef(sub[pcol], sub[next_col])[0, 1])
        rp = float(np.corrcoef(sub[prev_col], sub[next_col])[0, 1])
        rows.append({
            "stat": label,
            "n": len(sub),
            "model r": round(rm, 3),
            "persistence r": round(rp, 3),
            "Δr": round(rm - rp, 3),
            "model R²": round(rm ** 2, 3),
            "persistence R²": round(rp ** 2, 3),
            "Δ var explained": round(rm ** 2 - rp ** 2, 3),
        })
    return pd.DataFrame(rows)


# ---------- 3. Connection to actual hitting value (full-PA wOBA) ----------

def observed_woba_per_half(label: str) -> pd.DataFrame:
    """
    Compute full-PA wOBA and xwOBA per batter from Statcast event rows.
    Statcast's woba_value/woba_denom encode per-PA wOBA components.
    """
    df = pd.read_parquet(
        RAW / f"statcast_{label}.parquet",
        columns=[
            "batter", "events",
            "woba_value", "woba_denom",
            "estimated_woba_using_speedangle",
            "type",
        ],
    )
    # PA-ending rows: woba_denom == 1
    pa = df[df["woba_denom"] == 1].copy()
    pa["xwoba_event"] = pa["estimated_woba_using_speedangle"]
    # For non-BIP PAs (K, BB, HBP), xwOBA = woba_value (no contact to estimate)
    pa.loc[pa["type"] != "X", "xwoba_event"] = pa.loc[pa["type"] != "X", "woba_value"]

    agg = pa.groupby("batter", as_index=False).agg(
        pa_count=("woba_denom", "sum"),
        wOBA=("woba_value", "mean"),
        xwOBA=("xwoba_event", "mean"),
    )
    agg["half"] = label
    return agg


# ---------- Run ----------

def main() -> None:
    predictive = pd.read_csv(PROCESSED / "validation_predictive.csv")

    # 1. Quintile separation — predictive task
    print("=" * 78)
    print("1. QUINTILE SEPARATION — bin by predicted stat at H_t,")
    print("   report observed value at H_{t+1}.")
    print("=" * 78)
    for pcol, ocol, label, dec in STATS:
        print(quintile_table(predictive, pcol, ocol + "_next", label, dec))

    # 2. Model vs persistence on the same rows
    print("\n" + "=" * 78)
    print("2. MODEL vs PERSISTENCE (same rows, same task: predict next half)")
    print("=" * 78)
    obs = pd.concat([observed_per_half(h) for h in HALVES], ignore_index=True)
    pred = pd.read_parquet(PROCESSED / "leaderboard_half.parquet")
    h2h = head_to_head(pred, obs)
    print(h2h.to_string(index=False))

    # 3. Hitting value: predicted xwOBAcon vs observed full-PA wOBA
    print("\n" + "=" * 78)
    print("3. PREDICTED xwOBAcon vs OBSERVED FULL-PA wOBA")
    print("   (does bat-tracking-derived BIP quality track total offense?)")
    print("=" * 78)
    woba = pd.concat([observed_woba_per_half(h) for h in HALVES], ignore_index=True)
    pred = pd.read_parquet(PROCESSED / "leaderboard_half.parquet")

    # Concurrent: pred xwOBAcon at H vs obs wOBA at H
    c = pred.merge(woba, on=["batter", "half"], how="inner")
    c = c[c["pa_count"] >= 100]  # filter players w/ a real sample
    r_conc_woba  = float(np.corrcoef(c["pred_xwobacon"], c["wOBA"])[0, 1])
    r_conc_xwoba = float(np.corrcoef(c["pred_xwobacon"], c["xwOBA"])[0, 1])
    print(f"\nConcurrent (same half, {len(c)} rows, PA >= 100):")
    print(f"   pred xwOBAcon  vs obs wOBA   r = {r_conc_woba:.3f}  R² = {r_conc_woba**2:.3f}")
    print(f"   pred xwOBAcon  vs obs xwOBA  r = {r_conc_xwoba:.3f}  R² = {r_conc_xwoba**2:.3f}")

    # Predictive: pred xwOBAcon at H_t vs obs wOBA at H_{t+1}
    def next_half(h):
        season, sh = h.split("_")
        return f"{season}_H2" if sh == "H1" else f"{int(season)+1}_H1"

    pred2 = pred.copy()
    pred2["next_half"] = pred2["half"].map(next_half)
    woba_next = woba.rename(columns={
        "half": "next_half", "wOBA": "wOBA_next", "xwOBA": "xwOBA_next",
        "pa_count": "pa_count_next",
    })
    n = pred2.merge(woba_next, on=["batter", "next_half"], how="inner")
    n = n[n["pa_count_next"] >= 100]
    r_pred_woba  = float(np.corrcoef(n["pred_xwobacon"], n["wOBA_next"])[0, 1])
    r_pred_xwoba = float(np.corrcoef(n["pred_xwobacon"], n["xwOBA_next"])[0, 1])
    print(f"\nPredictive (next half, {len(n)} rows, PA >= 100):")
    print(f"   pred xwOBAcon at H_t  vs obs wOBA at H_{{t+1}}   r = {r_pred_woba:.3f}  R² = {r_pred_woba**2:.3f}")
    print(f"   pred xwOBAcon at H_t  vs obs xwOBA at H_{{t+1}}  r = {r_pred_xwoba:.3f}  R² = {r_pred_xwoba**2:.3f}")

    # Baseline: what does just using last half's observed wOBA give?
    woba_prev = woba.rename(columns={
        "wOBA": "wOBA_prev", "xwOBA": "xwOBA_prev", "pa_count": "pa_count_prev",
    })
    woba_prev["next_half"] = woba_prev["half"].map(next_half)
    woba_prev = woba_prev.drop(columns=["half"])
    persist = woba_prev.merge(
        woba.rename(columns={
            "wOBA": "wOBA_next", "xwOBA": "xwOBA_next",
            "pa_count": "pa_count_next", "half": "next_half",
        }),
        on=["batter", "next_half"], how="inner",
    )
    persist = persist[(persist["pa_count_prev"] >= 100) & (persist["pa_count_next"] >= 100)]
    r_pers_woba  = float(np.corrcoef(persist["wOBA_prev"],  persist["wOBA_next"])[0, 1])
    r_pers_xwoba = float(np.corrcoef(persist["xwOBA_prev"], persist["xwOBA_next"])[0, 1])
    print(f"\nPersistence baseline ({len(persist)} rows, PA >= 100 both halves):")
    print(f"   obs wOBA at H_t   vs obs wOBA at H_{{t+1}}    r = {r_pers_woba:.3f}  R² = {r_pers_woba**2:.3f}")
    print(f"   obs xwOBA at H_t  vs obs xwOBA at H_{{t+1}}   r = {r_pers_xwoba:.3f}  R² = {r_pers_xwoba**2:.3f}")

    print(f"\nSummary lift (predicting NEXT HALF wOBA):")
    print(f"   pred xwOBAcon model:     r = {r_pred_woba:.3f}")
    print(f"   last-half observed wOBA: r = {r_pers_woba:.3f}")
    print(f"   lift                   = {r_pred_woba - r_pers_woba:+.3f}")


if __name__ == "__main__":
    main()
