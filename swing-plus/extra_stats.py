# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
extra_stats.py — swing-based predictions for K%, HR%, ISO.

These three outcome rates carry real swing-PATH signal (validated, swing-only
GroupKFold-by-batter): HR% R²≈0.39, K% R²≈0.39, ISO R²≈0.35. BB% was dropped
(R²≈0.06 — a pure swing-decision stat the path can't see) and sprint speed was
dropped from ISO (adds ~0 — ISO is power, not infield singles).

Model family matches Swing+ / predicted_stats: StandardScaler → Poly(2) → RidgeCV
on the 9 bat-tracking features. One pipeline per target. Trained on player-halves.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd, joblib
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).parent
PROC = ROOT / "data" / "processed"
ARTIFACT = ROOT / "extra_stats_models.joblib"

SWING_FEATS = [
    "bat_speed_mean", "swing_length_mean", "attack_angle_mean", "attack_direction_mean",
    "swing_path_tilt_mean", "intercept_ball_minus_batter_pos_x_inches_mean",
    "intercept_ball_minus_batter_pos_y_inches_mean", "bat_speed_std", "attack_angle_std",
]
TARGETS = ["k_pct", "hr_pct", "iso"]          # display units: K%/HR% in %, ISO as rate
DEC = {"k_pct": 1, "hr_pct": 1, "iso": 3}

# raw Statcast event sets
_K = {"strikeout", "strikeout_double_play"}
_BB = {"walk", "intent_walk"}; _HBP = {"hit_by_pitch"}
_SAC = {"sac_fly", "sac_fly_double_play", "sac_bunt", "sac_bunt_double_play"}
_NONPA = {"truncated_pa"}
_HALVES = {"2023_H2": "2023", "2024_H1": "2024", "2024_H2": "2024",
           "2025_H1": "2025", "2025_H2": "2025", "2026_H1": "2026"}


def _half_counts() -> pd.DataFrame:
    """Per (batter, stand, half, season): PA-outcome counts from raw Statcast."""
    rows = []
    for h, season in _HALVES.items():
        f = ROOT / "data" / "raw" / f"statcast_{h}.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f, columns=["batter", "stand", "events"])
        d = d[d["events"].notna() & ~d["events"].isin(_NONPA)]
        e = d["events"]
        g = (d.assign(k=e.isin(_K), bb=e.isin(_BB), hbp=e.isin(_HBP), sac=e.isin(_SAC),
                      s1=e.eq("single"), s2=e.eq("double"), s3=e.eq("triple"), hr=e.eq("home_run"))
             .groupby(["batter", "stand"])
             .agg(PA=("events", "size"), Ks=("k", "sum"), BBs=("bb", "sum"), HBPs=("hbp", "sum"),
                  SACs=("sac", "sum"), S1=("s1", "sum"), S2=("s2", "sum"), S3=("s3", "sum"),
                  HR=("hr", "sum")).reset_index())
        g["half"] = h; g["season"] = season
        rows.append(g)
    return pd.concat(rows, ignore_index=True)


def _rates(c: pd.DataFrame) -> pd.DataFrame:
    """Add obs_k_pct / obs_hr_pct / obs_iso from summed counts."""
    c = c.copy()
    c["AB"] = c["PA"] - c["BBs"] - c["HBPs"] - c["SACs"]
    H = c["S1"] + c["S2"] + c["S3"] + c["HR"]
    TB = c["S1"] + 2 * c["S2"] + 3 * c["S3"] + 4 * c["HR"]
    c["obs_k_pct"] = np.where(c["PA"] > 0, c["Ks"] / c["PA"] * 100, np.nan)
    c["obs_hr_pct"] = np.where(c["PA"] > 0, c["HR"] / c["PA"] * 100, np.nan)
    c["obs_iso"] = np.where(c["AB"] > 0, (TB - H) / c["AB"], np.nan)
    c["n_pa_obs"] = c["PA"]
    return c


def observed(grain: str) -> pd.DataFrame:
    """Observed K%/HR%/ISO at a board grain: 'half' | 'season' | 'alltime'."""
    counts = _half_counts()
    keys = {"half": ["batter", "stand", "half"],
            "season": ["batter", "stand", "season"],
            "alltime": ["batter", "stand"]}[grain]
    sum_cols = ["PA", "Ks", "BBs", "HBPs", "SACs", "S1", "S2", "S3", "HR"]
    agg = counts.groupby(keys, as_index=False)[sum_cols].sum()
    return _rates(agg)[keys + ["obs_k_pct", "obs_hr_pct", "obs_iso", "n_pa_obs"]]


def train(min_pa: int = 100) -> dict:
    """Fit one Poly(2)+Ridge pipeline per target on player-halves; save + return."""
    half = pd.read_parquet(PROC / "leaderboard_half.parquet")
    obs = observed("half")
    df = half.merge(obs, on=["batter", "stand", "half"], how="inner")
    df = df.dropna(subset=SWING_FEATS)
    df = df[df["n_pa_obs"].fillna(0) >= min_pa]
    models = {}
    for t in TARGETS:
        sub = df.dropna(subset=[f"obs_{t}"])
        pipe = make_pipeline(StandardScaler(), PolynomialFeatures(2, include_bias=False),
                             RidgeCV(alphas=np.logspace(-2, 4, 25)))
        pipe.fit(sub[SWING_FEATS].values, sub[f"obs_{t}"].values)
        models[t] = pipe
    bundle = {"features": SWING_FEATS, "targets": TARGETS, "models": models}
    joblib.dump(bundle, ARTIFACT)
    return bundle


class ExtraStatsModel:
    def __init__(self, path: Path = ARTIFACT):
        b = joblib.load(path)
        self.features = b["features"]; self.targets = b["targets"]; self.models = b["models"]

    def predict_into(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add pred_k_pct / pred_hr_pct / pred_iso to a frame with the swing features."""
        out = df.copy()
        ok = out[self.features].notna().all(axis=1)
        X = out.loc[ok, self.features].values
        for t in self.targets:
            col = f"pred_{t}"; out[col] = np.nan
            if ok.any():
                out.loc[ok, col] = np.round(self.models[t].predict(X), DEC[t])
        return out


def augment(board: pd.DataFrame, grain: str, model: "ExtraStatsModel") -> pd.DataFrame:
    """Add obs_/pred_/diff columns for K%/HR%/ISO to a leaderboard frame."""
    keys = {"half": ["batter", "stand", "half"],
            "season": ["batter", "stand", "season"],
            "alltime": ["batter", "stand"]}[grain]
    b = board.merge(observed(grain).drop(columns=["n_pa_obs"]), on=keys, how="left")
    b = model.predict_into(b)
    for t in TARGETS:
        d = DEC[t]
        b[f"xdiff_{t}"] = (b[f"obs_{t}"] - b[f"pred_{t}"]).round(d)
    return b


def add_to_boards(half: pd.DataFrame, season: pd.DataFrame, alltime: pd.DataFrame):
    """Retrain on the in-memory half board + augment all three (for run_leaderboard)."""
    obs = observed("half")
    df = half.merge(obs, on=["batter", "stand", "half"], how="inner").dropna(subset=SWING_FEATS)
    df = df[df["n_pa_obs"].fillna(0) >= 100]
    models = {}
    for t in TARGETS:
        sub = df.dropna(subset=[f"obs_{t}"])
        pipe = make_pipeline(StandardScaler(), PolynomialFeatures(2, include_bias=False),
                             RidgeCV(alphas=np.logspace(-2, 4, 25)))
        pipe.fit(sub[SWING_FEATS].values, sub[f"obs_{t}"].values)
        models[t] = pipe
    joblib.dump({"features": SWING_FEATS, "targets": TARGETS, "models": models}, ARTIFACT)
    m = ExtraStatsModel()
    return (augment(half, "half", m), augment(season, "season", m), augment(alltime, "alltime", m))


if __name__ == "__main__":
    b = train()
    print("trained extra_stats models:", b["targets"])
    # quick in-sample sanity (not CV) just to confirm wiring
    half = pd.read_parquet(PROC / "leaderboard_half.parquet")
    pred = ExtraStatsModel().predict_into(half.dropna(subset=SWING_FEATS))
    print(pred[["name", "pred_k_pct", "pred_hr_pct", "pred_iso"]].head(6).to_string())
