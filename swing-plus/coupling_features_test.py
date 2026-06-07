# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
coupling_features_test.py — Do WITHIN-SWING coupling features beat the
appr17 ceiling for batted-ball prediction?

The diagnosis from ev_residual_decomp.py: the model only sees half-level
MEANS, so it loses whether a hitter pairs his fast swings WITH square
contact (Judge's signature). These features try to recover that joint
structure — strictly from swing geometry, never from launch metrics, so
there is no sweet-spot-style leakage.

Per player-half, over the model's filtered competitive swings:
  WITHIN-SWING CORRELATIONS (does geometry hold up when he swings hard?):
    corr_bs_aa   corr(bat_speed, attack_angle)
    corr_bs_tilt corr(bat_speed, swing_path_tilt)
    corr_bs_iy   corr(bat_speed, contact_depth)
    corr_bs_ix   corr(bat_speed, contact_x)
    corr_bs_sl   corr(bat_speed, swing_length)
  HARD-SWING GEOMETRY (geometry on top-third-by-bat-speed swings):
    aa_on_fast      mean attack angle on hard swings
    aa_std_on_fast  consistency of attack angle on hard swings
    iy_on_fast      mean contact depth on hard swings

Verdict is the PREDICTIVE (next-half) test, GroupKFold(5) on batter.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from augmented_model_test import (
    APPROACH_FEATS, BASELINE_FEATS, approach_per_half, cv_eval, woba_per_half,
)
from swing_plus import SwingPlusModel

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
PROCESSED = PROJECT / "data" / "processed"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]

MODEL = SwingPlusModel(PROJECT / "swing_plus_model_v1.joblib")

IY = "intercept_ball_minus_batter_pos_y_inches"
IX = "intercept_ball_minus_batter_pos_x_inches"

COUPLING_FEATS = [
    "corr_bs_aa", "corr_bs_tilt", "corr_bs_iy", "corr_bs_ix", "corr_bs_sl",
    "aa_on_fast", "aa_std_on_fast", "iy_on_fast",
]

TARGETS = [
    ("obs_avg_ev",       "Avg EV (mph)", 1),
    ("obs_hard_hit_pct", "Hard-Hit %",   1),
    ("obs_barrel_pct",   "Barrel %",     1),
    ("obs_avg_la",       "Avg LA (deg)", 1),
    ("obs_xwobacon",     "xwOBAcon",     3),
]


def _safe_corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 5 or np.std(a) == 0 or np.std(b) == 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def _group_feats(g: pd.DataFrame) -> pd.Series:
    bs = g["bat_speed"].to_numpy()
    out = {
        "corr_bs_aa":   _safe_corr(bs, g["attack_angle"].to_numpy()),
        "corr_bs_tilt": _safe_corr(bs, g["swing_path_tilt"].to_numpy()),
        "corr_bs_iy":   _safe_corr(bs, g[IY].to_numpy()),
        "corr_bs_ix":   _safe_corr(bs, g[IX].to_numpy()),
        "corr_bs_sl":   _safe_corr(bs, g["swing_length"].to_numpy()),
    }
    thr = np.quantile(bs, 2 / 3)
    hard = g[g["bat_speed"] >= thr]
    aa = hard["attack_angle"].to_numpy(dtype="float64")
    iy = hard[IY].to_numpy(dtype="float64")
    out["aa_on_fast"] = float(np.nanmean(aa)) if len(aa) else np.nan
    out["aa_std_on_fast"] = float(np.nanstd(aa, ddof=1)) if len(aa) > 1 else np.nan
    out["iy_on_fast"] = float(np.nanmean(iy)) if len(iy) else np.nan
    return pd.Series(out)


def coupling_per_half(label: str) -> pd.DataFrame:
    df = pd.read_parquet(
        RAW / f"statcast_{label}.parquet",
        columns=["batter", "bat_speed", "swing_length", "attack_angle",
                 "attack_direction", "swing_path_tilt", IX, IY, "type"],
    )
    sw = MODEL.filter_swings(df)            # exactly the model's competitive swings
    feats = (sw.groupby("batter").apply(_group_feats, include_groups=False)
             .reset_index())
    feats["half"] = label
    return feats


def build_master() -> pd.DataFrame:
    base = pd.read_csv(PROCESSED / "validation_concurrent.csv")  # base feats + obs BIP targets
    approach = pd.concat([approach_per_half(h) for h in HALVES], ignore_index=True)
    coup = pd.concat([coupling_per_half(h) for h in HALVES], ignore_index=True)
    woba = pd.concat([woba_per_half(h) for h in HALVES], ignore_index=True)
    m = (base
         .merge(approach, on=["batter", "half"], how="inner")
         .merge(coup, on=["batter", "half"], how="inner")
         .merge(woba, on=["batter", "half"], how="inner"))
    m = m[m["n_pa"] >= 50]
    return m


def next_half(h: str) -> str:
    season, sh = h.split("_")
    return f"{season}_H2" if sh == "H1" else f"{int(season) + 1}_H1"


def eval_set(frame: pd.DataFrame, feats: list[str], target: str) -> float:
    sub = frame.dropna(subset=feats + [target])
    return cv_eval(sub[feats], sub[target], sub["batter"])["r"]


def run_block(frame: pd.DataFrame, suffix: str, sets: dict) -> pd.DataFrame:
    rows = []
    for tcol, label, _ in TARGETS:
        r = {"target": label}
        for name, feats in sets.items():
            r[name] = round(eval_set(frame, feats, tcol + suffix), 3)
        r["CV|base"] = round(r["base+CV"] - r["base9"], 3)
        r["CV|appr"] = round(r["appr+CV"] - r["appr17"], 3)
        rows.append(r)
    return pd.DataFrame(rows)


def main() -> None:
    print("Building per-swing coupling features (this reads all 5 raw halves)...")
    m = build_master()
    miss = m[COUPLING_FEATS].isna().any(axis=1).sum()
    print(f"  {len(m):,} player-halves, {m['batter'].nunique()} batters "
          f"({miss} rows missing a coupling feature)\n")

    # Do the coupling features even correlate with the EV residual? (sanity)
    if {"obs_avg_ev", "pred_avg_ev"}.issubset(m.columns):
        m["_ev_resid"] = m["obs_avg_ev"] - m["pred_avg_ev"]
        print("Coupling feature correlation with EV residual (obs-pred):")
        for f in COUPLING_FEATS:
            s = m.dropna(subset=[f, "_ev_resid"])
            print(f"  {f:<16} r = {np.corrcoef(s[f], s['_ev_resid'])[0,1]:+.3f}")

    sets = {
        "base9":   BASELINE_FEATS,
        "base+CV": BASELINE_FEATS + COUPLING_FEATS,
        "appr17":  BASELINE_FEATS + APPROACH_FEATS,
        "appr+CV": BASELINE_FEATS + APPROACH_FEATS + COUPLING_FEATS,
    }

    print("\n" + "=" * 92)
    print("CONCURRENT — features(H) -> target(H)")
    print("=" * 92)
    print(run_block(m, "", sets).to_string(index=False))

    m2 = m.copy()
    m2["next_half"] = m2["half"].map(next_half)
    tgt_next = m[["batter", "half"] + [t for t, _, _ in TARGETS]].rename(
        columns={"half": "next_half", **{t: t + "_next" for t, _, _ in TARGETS}})
    pf = m2.merge(tgt_next, on=["batter", "next_half"], how="inner")

    print("\n" + "=" * 92)
    print(f"PREDICTIVE — features(H_t) -> target(H_t+1).  VERDICT.  ({len(pf):,} rows)")
    print("=" * 92)
    pred = run_block(pf, "_next", sets)
    print(pred.to_string(index=False))
    print("\n  CV|base = lift from coupling features on top of bat-tracking only.")
    print("  CV|appr = lift from coupling features on top of the appr17 best model.")

    pred.to_csv(PROCESSED / "coupling_predictive.csv", index=False)
    print(f"\nSaved coupling_predictive.csv")


if __name__ == "__main__":
    main()
