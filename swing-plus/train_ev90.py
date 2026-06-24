# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
train_ev90.py — Train a 90th-percentile EV model (top-end power), parallel to
the existing predicted batted-ball stats. Same recipe: 9 bat-tracking features
-> StandardScaler -> PolynomialFeatures(2) -> RidgeCV. Saves ev90_model.joblib.
"""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import joblib, numpy as np, pandas as pd
from sklearn.model_selection import GroupKFold
from swing_plus import SwingPlusModel
from train_pa_value import make_pipe

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
MODEL = SwingPlusModel(PROJECT / "swing_plus_model_v1.joblib")
FEATS = MODEL.features
READ = sorted(set(MODEL.tracking_cols + ["batter", "type", "launch_speed"]))


def build():
    parts = []
    for h in HALVES:
        df = pd.read_parquet(RAW / f"statcast_{h}.parquet", columns=READ)
        df["half"] = h
        prof = MODEL.build_profiles(MODEL.filter_swings(df), group_by=["half"])
        bip = df[(df["type"] == "X") & df["launch_speed"].notna()]
        ev90 = (bip.groupby("batter")["launch_speed"].quantile(0.90)
                .rename("obs_ev90").reset_index())
        ev90["half"] = h
        parts.append(prof.merge(ev90, on=["batter", "half"], how="inner"))
    frame = pd.concat(parts, ignore_index=True)
    frame = frame[frame["n_bip"] >= 50].dropna(subset=FEATS + ["obs_ev90"]).reset_index(drop=True)
    return frame


def main():
    frame = build()
    print(f"training rows: {len(frame)}  ({frame['batter'].nunique()} batters)")
    X, y, g = frame[FEATS], frame["obs_ev90"], frame["batter"]

    # out-of-fold CV fit (GroupKFold on batter)
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(X, y, g):
        oof[te] = make_pipe().fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
    r = float(np.corrcoef(oof, y)[0, 1])
    mae = float(np.abs(oof - y).mean())
    print(f"OOF fit: r={r:.3f}  R^2={r**2:.3f}  MAE={mae:.2f} mph")
    print(f"(for reference, avg-EV model is ~r 0.66)")

    pipe = make_pipe().fit(X, y)
    artifact = {"version": "1.0.0", "features": FEATS,
                "target": "90th percentile EV (mph)",
                "model": pipe, "oof_r": round(r, 3)}
    out = PROJECT / "ev90_model.joblib"
    joblib.dump(artifact, out)
    print(f"saved {out.name}")


if __name__ == "__main__":
    main()
