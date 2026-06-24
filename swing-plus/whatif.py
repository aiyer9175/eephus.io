# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
whatif.py — Score a (possibly adjusted) swing profile through the model family.

Given the 9-feature swing profile, returns predicted Swing+ and batted-ball
stats (EV, EV90, Barrel%, Hard-Hit%, LA, xwOBAcon). Used by the adjustment tool
to show how changing bat speed / attack angle / etc. moves the predictions.
"""

from __future__ import annotations
from pathlib import Path
import joblib, numpy as np, pandas as pd
from swing_plus import SwingPlusModel
from predicted_stats import PredictedStatsModel, OUTPUT_COLS
from pa_value import PAValueModel

# stat key -> decimals. xwoba (full-PA, approach held fixed) sits beside xwobacon.
STAT_FMT = {"avg_ev": 1, "avg_ev90": 1, "hard_hit_pct": 1,
            "barrel_pct": 1, "avg_la": 1, "xwobacon": 3, "xwoba": 3}


class WhatIfScorer:
    def __init__(self, root: Path):
        self.sp = SwingPlusModel(root / "swing_plus_model_v1.joblib")
        self.ps = PredictedStatsModel(root / "predicted_stats_models.joblib")
        self.ev90 = joblib.load(root / "ev90_model.joblib")
        self.pv = PAValueModel(root / "pa_value_models.joblib")
        self.feats = list(self.sp.features)          # 9 bat-tracking
        self.appr_feats = list(self.pv.features)      # 17 (9 + 8 approach)

    def score(self, profile: dict) -> dict:
        """profile: dict with the appr17 features (9 bat-tracking + 8 approach).
        Returns predicted swing/contact outputs + xwOBA (approach held fixed)."""
        # attack_direction is stored/displayed pull-POSITIVE (Savant convention);
        # the trained models expect raw Statcast sign (pull-negative), so flip back.
        profile = dict(profile)
        if "attack_direction_mean" in profile:
            profile["attack_direction_mean"] = -float(profile["attack_direction_mean"])
        df = pd.DataFrame([{f: float(profile[f]) for f in self.feats}])
        df["n_swings"] = 400          # nominal full sample (raw score, no shrink)
        sp = self.sp.score_profiles(df, reliability_weight=False)["swing_plus_raw"].iloc[0]
        ps = self.ps.predict_into(df)
        out = {"swing_plus": round(float(sp), 1)}
        for key, col in OUTPUT_COLS.items():           # avg_ev->pred_avg_ev, ...
            out[key] = round(float(ps[col].iloc[0]), 3 if key == "xwobacon" else 1)
        out["avg_ev90"] = round(float(self.ev90["model"].predict(df[self.feats].values)[0]), 1)
        # full-PA xwOBA via the pa_value model — approach features held at the
        # player's values, so the change reflects only the swing/contact change.
        dfa = pd.DataFrame([{f: float(profile[f]) for f in self.appr_feats}])
        out["xwoba"] = round(float(self.pv.predict(dfa)["pred_xwoba"].iloc[0]), 3)
        return out
