# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
train_pa_value.py — Train the deployable full-PA xwOBA / wOBA models and
calibrate the blend weight, then save pa_value_models.joblib.

Model: appr17 features (9 bat-tracking + 8 approach) -> obs_xwoba / obs_woba,
StandardScaler -> PolynomialFeatures(2) -> RidgeCV. Trained on all qualifying
2023H2-2025H2 player-halves.

Blend: the leaderboard column is NOT the raw model output. It is
    blended = w * observed + (1 - w) * model_pred,   w = n_pa / (n_pa + k)
which shrinks a player's noisy observed value toward the model's stable
skill estimate when the PA sample is small. k is chosen to MAXIMISE
out-of-fold next-half prediction (honest: model_pred is OOF).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

from pa_features import (
    APPROACH_FEATS, REQUIRED_COLUMNS,
    compute_approach_features, compute_observed_pa_stats,
)
from swing_plus import SwingPlusModel

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]

BASELINE_FEATS = [
    "bat_speed_mean", "swing_length_mean", "attack_angle_mean",
    "attack_direction_mean", "swing_path_tilt_mean",
    "intercept_ball_minus_batter_pos_x_inches_mean",
    "intercept_ball_minus_batter_pos_y_inches_mean",
    "bat_speed_std", "attack_angle_std",
]
FEATS = BASELINE_FEATS + APPROACH_FEATS
PA_MIN = 100
K_GRID = [50, 75, 100, 150, 200, 250, 300, 400, 500, 700, 1000]

EXTRA_COLS = ["swing_length", "swing_path_tilt", "attack_direction",
              "intercept_ball_minus_batter_pos_x_inches", "launch_speed"]
READ_COLS = sorted(set(REQUIRED_COLUMNS + EXTRA_COLS))

MODEL = SwingPlusModel(PROJECT / "swing_plus_model_v1.joblib")


def make_pipe() -> Pipeline:
    return Pipeline([
        ("scale", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, include_bias=False)),
        ("ridge", RidgeCV(alphas=np.logspace(-3, 3, 19))),
    ])


def build_training_frame() -> pd.DataFrame:
    parts = []
    for label in HALVES:
        df = pd.read_parquet(RAW / f"statcast_{label}.parquet", columns=READ_COLS)
        df["half"] = label
        prof = MODEL.build_profiles(MODEL.filter_swings(df), group_by=["half"])
        appr = compute_approach_features(df, keys=["batter", "half"])
        pas = compute_observed_pa_stats(df, keys=["batter", "half"])
        merged = (prof.merge(appr, on=["batter", "half"], how="inner")
                  .merge(pas, on=["batter", "half"], how="inner"))
        parts.append(merged)
    frame = pd.concat(parts, ignore_index=True)
    frame = frame[frame["n_pa"] >= PA_MIN].dropna(subset=FEATS).reset_index(drop=True)
    return frame


def next_half(h: str) -> str:
    season, sh = h.split("_")
    return f"{season}_H2" if sh == "H1" else f"{int(season) + 1}_H1"


def oof_predict(X: pd.DataFrame, y: pd.Series, groups: pd.Series) -> np.ndarray:
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(X, y, groups):
        oof[te] = make_pipe().fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
    return oof


def calibrate_k(frame: pd.DataFrame, target: str) -> tuple[int, dict]:
    """Pick k maximizing next-half correlation of the blended estimate."""
    f = frame.dropna(subset=[target]).copy()
    f["_oof"] = oof_predict(f[FEATS], f[target], f["batter"])
    f["next_half"] = f["half"].map(next_half)
    nxt = f[["batter", "half", target]].rename(
        columns={"half": "next_half", target: target + "_next"})
    pf = f.merge(nxt, on=["batter", "next_half"], how="inner").dropna(
        subset=["_oof", target, target + "_next"])

    actual = pf[target + "_next"].to_numpy()
    obs = pf[target].to_numpy()
    pred = pf["_oof"].to_numpy()
    pa = pf["n_pa"].to_numpy()

    def r(x):
        return float(np.corrcoef(x, actual)[0, 1])

    curve = {}
    best_k, best_r = None, -np.inf
    for k in K_GRID:
        w = pa / (pa + k)
        blended = w * obs + (1 - w) * pred
        rk = r(blended)
        curve[k] = round(rk, 4)
        if rk > best_r:
            best_r, best_k = rk, k
    metrics = {
        "r_obs_only": round(r(obs), 4),
        "r_model_only": round(r(pred), 4),
        "r_blended_best": round(best_r, 4),
        "best_k": best_k,
        "k_curve": curve,
        "n_pairs": len(pf),
    }
    return best_k, metrics


def main() -> None:
    print(f"Building training frame (PA >= {PA_MIN})...")
    frame = build_training_frame()
    print(f"  {len(frame):,} player-halves, {frame['batter'].nunique()} batters")

    artifact = {
        "version": "1.0.0",
        "features": FEATS,
        "baseline_features": BASELINE_FEATS,
        "approach_features": APPROACH_FEATS,
        "pa_min": PA_MIN,
        "models": {},
        "blend_k": {},
        "targets": {"xwoba": "xwOBA (full PA)", "woba": "wOBA (full PA)"},
        "validation": {},
    }

    for key, target in [("xwoba", "obs_xwoba"), ("woba", "obs_woba")]:
        sub = frame.dropna(subset=[target])
        pipe = make_pipe().fit(sub[FEATS], sub[target])
        artifact["models"][key] = pipe
        k, metrics = calibrate_k(frame, target)
        artifact["blend_k"][key] = k
        artifact["validation"][key] = metrics
        print(f"\n[{key}] trained on {len(sub):,} rows")
        print(f"  next-half r: obs-only={metrics['r_obs_only']}  "
              f"model-only={metrics['r_model_only']}  "
              f"blended(k={k})={metrics['r_blended_best']}")
        print(f"  k curve: {metrics['k_curve']}")

    out = PROJECT / "pa_value_models.joblib"
    joblib.dump(artifact, out)
    print(f"\nSaved {out.name} "
          f"(blend_k: {artifact['blend_k']})")


if __name__ == "__main__":
    main()
