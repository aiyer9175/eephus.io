# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
sweetspot_test.py — Does launch-angle sweet-spot % add real signal?

Sweet-spot % = share of balls in play with launch angle in [8, 32] deg
(Statcast's definition). The user's hypothesis: it captures how well a
hitter deploys his swing against the pitches he actually sees, and that
should sharpen EV / LA / batted-ball predictions.

METHODOLOGICAL WARNING — leakage:
  Sweet-spot % is computed FROM launch angle on balls in play. Using it to
  predict SAME-HALF avg_la / xwOBAcon / Barrel% is partly circular: those
  targets are also functions of the same-half LA distribution. So the
  CONCURRENT gains on LA-derived targets are NOT trustworthy signal.

  The clean test is PREDICTIVE: sweet-spot %(H_t) -> outcome(H_{t+1}).
  There, sweet-spot is a lagged skill measure in a different time period,
  so any lift is real out-of-period signal.

Four feature sets, evaluated both ways, GroupKFold(5) on batter:
  base9    : 9 bat-tracking features
  base+SS  : base9 + sweet_spot_pct          (user's direct hypothesis)
  appr17   : base9 + 8 approach features
  appr+SS  : appr17 + sweet_spot_pct         (marginal value over approach)
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from augmented_model_test import (
    APPROACH_FEATS, BASELINE_FEATS, approach_per_half, cv_eval, woba_per_half,
)
from validate_predictions import observed_per_half

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
PROCESSED = PROJECT / "data" / "processed"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]

# (target col, label, decimals, is_LA_derived) — LA-derived targets are the
# ones where concurrent sweet-spot gains are mechanically contaminated.
TARGETS = [
    ("obs_avg_ev",       "Avg EV (mph)",    1, False),
    ("obs_hard_hit_pct", "Hard-Hit %",      1, False),
    ("obs_barrel_pct",   "Barrel %",        1, True),
    ("obs_avg_la",       "Avg LA (deg)",    1, True),
    ("obs_xwobacon",     "xwOBAcon",        3, True),
    ("wOBA",             "wOBA (full PA)",  3, False),
    ("xwOBA",            "xwOBA (full PA)", 3, True),
]


def sweetspot_per_half(label: str) -> pd.DataFrame:
    df = pd.read_parquet(
        RAW / f"statcast_{label}.parquet",
        columns=["batter", "type", "launch_angle"],
    )
    bip = df[df["type"] == "X"].dropna(subset=["launch_angle"]).copy()
    bip["ss"] = bip["launch_angle"].between(8, 32).astype(float)
    agg = bip.groupby("batter", as_index=False).agg(sweet_spot_pct=("ss", "mean"))
    agg["sweet_spot_pct"] *= 100.0
    agg["half"] = label
    return agg


def next_half(h: str) -> str:
    season, sh = h.split("_")
    return f"{season}_H2" if sh == "H1" else f"{int(season) + 1}_H1"


def build_master() -> pd.DataFrame:
    base = pd.read_parquet(PROCESSED / "leaderboard_half.parquet")
    base = base[["batter", "half", "n_swings"] + BASELINE_FEATS]
    approach = pd.concat([approach_per_half(h) for h in HALVES], ignore_index=True)
    sweet = pd.concat([sweetspot_per_half(h) for h in HALVES], ignore_index=True)
    obs = pd.concat([observed_per_half(h) for h in HALVES], ignore_index=True)
    woba = pd.concat([woba_per_half(h) for h in HALVES], ignore_index=True)

    m = (base
         .merge(approach, on=["batter", "half"], how="inner")
         .merge(sweet, on=["batter", "half"], how="inner")
         .merge(obs, on=["batter", "half"], how="inner")
         .merge(woba, on=["batter", "half"], how="inner"))
    m = m[m["n_pa"] >= 50]
    return m


def eval_set(frame: pd.DataFrame, feats: list[str], target: str) -> dict:
    sub = frame.dropna(subset=feats + [target])
    return cv_eval(sub[feats], sub[target], sub["batter"])


def main() -> None:
    print("Building master feature/target frame...")
    m = build_master()
    print(f"  {len(m):,} player-halves, {m['batter'].nunique()} batters\n")

    feature_sets = {
        "base9":   BASELINE_FEATS,
        "base+SS": BASELINE_FEATS + ["sweet_spot_pct"],
        "appr17":  BASELINE_FEATS + APPROACH_FEATS,
        "appr+SS": BASELINE_FEATS + APPROACH_FEATS + ["sweet_spot_pct"],
    }

    # ---- Correlation of sweet_spot with targets (context) ----
    print("Sweet-spot %% raw correlation with each target (same half):")
    for tcol, label, _, la in TARGETS:
        s = m.dropna(subset=["sweet_spot_pct", tcol])
        r = float(np.corrcoef(s["sweet_spot_pct"], s[tcol])[0, 1])
        flag = "  <- LA-derived (leakage risk)" if la else ""
        print(f"   {label:<16} r = {r:+.3f}{flag}")

    # ---- Concurrent ----
    print("\n" + "=" * 104)
    print("CONCURRENT — features(H) -> target(H).  ** LA-derived gains are partly circular **")
    print("=" * 104)
    rows = []
    for tcol, label, dec, la in TARGETS:
        r = {"target": label + (" †" if la else "")}
        for name, feats in feature_sets.items():
            r[name] = round(eval_set(m, feats, tcol)["r"], 3)
        r["SS|base"] = round(r["base+SS"] - r["base9"], 3)
        r["SS|appr"] = round(r["appr+SS"] - r["appr17"], 3)
        rows.append(r)
    conc = pd.DataFrame(rows)
    print(conc.to_string(index=False))
    print("  † LA-derived target — treat concurrent sweet-spot lift as suspect.")
    print("  SS|base = lift from adding sweet-spot to bat-tracking only.")
    print("  SS|appr = lift from adding sweet-spot on top of approach features.")

    # ---- Predictive (the honest test) ----
    m2 = m.copy()
    m2["next_half"] = m2["half"].map(next_half)
    tgt_next = m[["batter", "half"] + [t for t, _, _, _ in TARGETS]].rename(
        columns={"half": "next_half",
                 **{t: t + "_next" for t, _, _, _ in TARGETS}})
    pf = m2.merge(tgt_next, on=["batter", "next_half"], how="inner")
    print("\n" + "=" * 104)
    print(f"PREDICTIVE — features(H_t) -> target(H_t+1).  CLEAN TEST.  "
          f"({len(pf):,} half->half rows)")
    print("=" * 104)
    rows = []
    for tcol, label, dec, la in TARGETS:
        r = {"target": label}
        for name, feats in feature_sets.items():
            r[name] = round(eval_set(pf, feats, tcol + "_next")["r"], 3)
        r["SS|base"] = round(r["base+SS"] - r["base9"], 3)
        r["SS|appr"] = round(r["appr+SS"] - r["appr17"], 3)
        rows.append(r)
    pred = pd.DataFrame(rows)
    print(pred.to_string(index=False))

    conc.to_csv(PROCESSED / "sweetspot_concurrent.csv", index=False)
    pred.to_csv(PROCESSED / "sweetspot_predictive.csv", index=False)
    print(f"\nSaved sweetspot_concurrent.csv and sweetspot_predictive.csv")


if __name__ == "__main__":
    main()
