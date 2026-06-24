# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
pa_value.py — Inference for the blended full-PA xwOBA / wOBA estimate.

The headline leaderboard value is a sample-size-aware blend of a player's
observed value and the model's skill-based prediction:

    blended = w * observed + (1 - w) * model_pred,    w = n_pa / (n_pa + k)

Small PA sample -> trust the stable model estimate; large PA sample -> trust
the observed value. k was calibrated (train_pa_value.py) to maximize
next-half prediction: blended beats both observed-only and model-only.

Usage:
    from pa_value import PAValueModel
    pv = PAValueModel("pa_value_models.joblib")
    df = pv.predict(profiles)                  # adds pred_xwoba, pred_woba
    df = pv.add_blended(df, n_pa_col="n_pa",
                        obs={"xwoba": "obs_xwoba", "woba": "obs_woba"})
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PRED_COL = {"xwoba": "pred_xwoba", "woba": "pred_woba"}
BLEND_COL = {"xwoba": "blended_xwoba", "woba": "blended_woba"}


class PAValueModel:
    def __init__(self, artifact_path: str | Path):
        art = joblib.load(Path(artifact_path))
        self.version = art["version"]
        self.features = list(art["features"])
        self.models = art["models"]            # {"xwoba": pipe, "woba": pipe}
        self.blend_k = art["blend_k"]          # {"xwoba": k, "woba": k}
        self.targets = art["targets"]
        self.validation = art.get("validation", {})

    # --- model prediction from appr17 profiles ---
    def predict(self, profiles: pd.DataFrame) -> pd.DataFrame:
        missing = [c for c in self.features if c not in profiles.columns]
        if missing:
            raise ValueError(f"Missing PA-value feature columns: {missing}")
        df = profiles.copy()
        feat = df[self.features]
        valid = feat.notna().all(axis=1)
        X = feat[valid].values
        for key, model in self.models.items():
            col = PRED_COL[key]
            df[col] = np.nan
            if len(X):
                df.loc[valid, col] = model.predict(X)
        return df

    # --- sample-size blend with observed value ---
    def blend(self, key: str, observed: pd.Series, predicted: pd.Series,
              n_pa: pd.Series) -> pd.Series:
        k = self.blend_k[key]
        w = n_pa / (n_pa + k)
        obs = observed.astype(float)
        pred = predicted.astype(float)
        # NaN-robust: if one side missing, use the other.
        blended = w * obs + (1 - w) * pred
        blended = blended.where(obs.notna(), pred)        # no observed -> model
        blended = blended.where(pred.notna(), obs)        # no model -> observed
        return blended

    def add_blended(self, df: pd.DataFrame, n_pa_col: str,
                    obs: dict[str, str]) -> pd.DataFrame:
        out = df.copy()
        for key, obs_col in obs.items():
            pred_col = PRED_COL[key]
            if pred_col not in out.columns or obs_col not in out.columns:
                continue
            out[BLEND_COL[key]] = self.blend(
                key, out[obs_col], out[pred_col], out[n_pa_col])
            out[f"{key}_blend_weight"] = out[n_pa_col] / (out[n_pa_col] + self.blend_k[key])
        return out


if __name__ == "__main__":
    pv = PAValueModel(Path(__file__).parent / "pa_value_models.joblib")
    print(f"PAValueModel v{pv.version}")
    print(f"  features ({len(pv.features)}): {pv.features}")
    print(f"  blend k: {pv.blend_k}")
    for k, m in pv.validation.items():
        print(f"  {k}: next-half r obs={m['r_obs_only']} model={m['r_model_only']} "
              f"blended={m['r_blended_best']} (k={m['best_k']})")
