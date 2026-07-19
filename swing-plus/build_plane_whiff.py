# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
build_plane_whiff.py — Step 1 of the swing-path-aware Decision+ rebuild.

Engine: per-pitch expected whiff P(whiff | swing) from bat/pitch PLANE GEOMETRY
plus location. This is the validated mechanism (plane mismatch drives whiff
18%->44%). It must beat a location-only baseline to justify the build.

VAA (pitch vertical approach angle at the plate) from the trajectory params;
plane_mismatch = |attack_angle - (-VAA)| (squared-up when bat plane meets the
ball's incoming line). Evaluation is GroupKFold-by-batter (no identity leak).

Outputs:
  models/plane_whiff_lgb.joblib        — the engine
  data/processed/plane_whiff_swings.parquet — per-swing P(whiff) + geometry
"""

import glob
import numpy as np
import pandas as pd
from pathlib import Path
import joblib
import lightgbm as lgb
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score, log_loss

ROOT = Path(__file__).parent
RAW = sorted(glob.glob(str(ROOT / "data/raw/statcast_202*_H*.parquet")))
PROC = ROOT / "data" / "processed"
MODELS = ROOT / "models"; MODELS.mkdir(exist_ok=True)

SWING = ["swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play"]
WHIFF = ["swinging_strike", "swinging_strike_blocked", "foul_tip"]
COLS = ["batter", "attack_angle", "swing_length", "bat_speed", "plate_x", "plate_z",
        "vy0", "vz0", "ay", "az", "release_speed", "pitch_type", "description"]


def load() -> pd.DataFrame:
    d = pd.concat([pd.read_parquet(f, columns=COLS) for f in RAW], ignore_index=True)
    yf = 17 / 12
    d["vy_f"] = -np.sqrt(np.clip(d["vy0"] ** 2 - 2 * d["ay"] * (50 - yf), 0, None))
    t = (d["vy_f"] - d["vy0"]) / d["ay"]
    d["VAA"] = np.degrees(np.arctan2(d["vz0"] + d["az"] * t, -d["vy_f"]))
    s = d[d["description"].isin(SWING) & d["attack_angle"].notna()
          & d["VAA"].between(-15, 2) & d["plate_z"].between(0.0, 5.0)].copy()
    s["whiff"] = s["description"].isin(WHIFF).astype(int)
    s["plane_mismatch"] = (s["attack_angle"] - (-s["VAA"])).abs()
    s["px_abs"] = s["plate_x"].abs()
    return s


def race(s: pd.DataFrame):
    y = s["whiff"].values
    g = s["batter"].values
    base = ["plate_z", "px_abs", "release_speed"]          # location/velo only
    full = base + ["VAA", "attack_angle", "plane_mismatch", "swing_length", "bat_speed"]
    gkf = GroupKFold(5)
    out = {}
    for name, feats in [("location-only", base), ("+plane geometry", full)]:
        X = s[feats].astype("float64").values
        pred = np.zeros(len(y))
        for tr, te in gkf.split(X, y, g):
            m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                                   min_child_samples=200, subsample=0.8, colsample_bytree=0.8,
                                   verbosity=-1)
            m.fit(X[tr], y[tr])
            pred[te] = m.predict_proba(X[te])[:, 1]
        out[name] = (roc_auc_score(y, pred), log_loss(y, pred))
        print(f"  {name:16s} AUC={out[name][0]:.4f}  logloss={out[name][1]:.4f}")
    return full


def main():
    s = load()
    print(f"competitive swings w/ bat-tracking: {len(s):,} | whiff rate {s['whiff'].mean():.3f}")
    print("\n[ENGINE RACE] predict whiff, GroupKFold-by-batter:")
    full = race(s)

    # fit final engine on all data + score every swing
    m = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=31,
                           min_child_samples=200, subsample=0.8, colsample_bytree=0.8,
                           verbosity=-1)
    Xfull = s[full].astype("float64").values
    m.fit(Xfull, s["whiff"].values)
    imp = pd.Series(m.feature_importances_, index=full).sort_values(ascending=False)
    print("\nfeature importance (gain split count):")
    print(imp.to_string())
    joblib.dump({"model": m, "features": full}, MODELS / "plane_whiff_lgb.joblib")
    s["xwhiff"] = m.predict_proba(Xfull)[:, 1]
    keep = ["batter", "plate_x", "plate_z", "VAA", "attack_angle", "plane_mismatch",
            "pitch_type", "whiff", "xwhiff"]
    s[keep].to_parquet(PROC / "plane_whiff_swings.parquet", index=False)
    print(f"\nsaved engine + {len(s):,} scored swings")


if __name__ == "__main__":
    main()
