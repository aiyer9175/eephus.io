# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
predicted_stats.py - Inference wrapper for the predicted batted-ball stats models.

A companion to swing_plus.py. Given the SAME 9 player-half profile features
that Swing+ uses, this predicts five batted-ball outcome stats:

    avg_ev        Average Exit Velocity (mph)
    hard_hit_pct  Hard-Hit % (EV >= 95)
    barrel_pct    Barrel %
    avg_la        Average Launch Angle (deg)
    xwobacon      xwOBAcon

Each is an independent StandardScaler -> PolynomialFeatures(2) -> RidgeCV
pipeline. Holdout test correlations (test_r): barrel 0.80, hard-hit 0.77,
xwOBAcon 0.75, avg_ev 0.70, avg_la 0.64.

Usage:
    from predicted_stats import PredictedStatsModel
    ps = PredictedStatsModel("predicted_stats_models.joblib")
    df = ps.predict_into(profiles_df)   # adds pred_* columns in place-of-copy
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

# model key -> output column name on the leaderboard
OUTPUT_COLS = {
    "avg_ev": "pred_avg_ev",
    "hard_hit_pct": "pred_hard_hit_pct",
    "barrel_pct": "pred_barrel_pct",
    "avg_la": "pred_avg_la",
    "xwobacon": "pred_xwobacon",
}


class PredictedStatsModel:
    """Loaded predicted batted-ball stats models."""

    def __init__(self, artifact_path: str | Path):
        self.artifact_path = Path(artifact_path)
        art = joblib.load(self.artifact_path)
        self.models = art["models"]
        self.features = list(art["features"])
        self.targets = art["targets"]
        self.results = art.get("results", {})

    @property
    def output_cols(self) -> list[str]:
        return [OUTPUT_COLS[k] for k in self.models]

    def predict_into(self, profiles: pd.DataFrame) -> pd.DataFrame:
        """
        Append predicted-stat columns to a profiles dataframe.

        `profiles` must contain the 9 feature columns (same set Swing+ uses).
        Rows with any missing feature get NaN predictions rather than erroring,
        so a partial leaderboard still renders.
        """
        missing = [c for c in self.features if c not in profiles.columns]
        if missing:
            raise ValueError(f"Missing feature columns for predicted stats: {missing}")

        df = profiles.copy()
        feat = df[self.features]
        valid = feat.notna().all(axis=1)
        X = feat[valid].values

        for key, model in self.models.items():
            col = OUTPUT_COLS[key]
            df[col] = np.nan
            if len(X):
                df.loc[valid, col] = model.predict(X)
        return df


if __name__ == "__main__":
    import sys

    ps = PredictedStatsModel(sys.argv[1] if len(sys.argv) > 1 else "predicted_stats_models.joblib")
    print(f"features ({len(ps.features)}): {ps.features}")
    for k, label in ps.targets.items():
        r = ps.results.get(k, {})
        print(f"  {OUTPUT_COLS[k]:<22} <- {label:<28} "
              f"test_r={r.get('test_r', float('nan')):.3f}")
