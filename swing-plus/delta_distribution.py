# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
delta_distribution.py — Distribution of the xwOBA delta (obs - pred).

Reports, at each aggregation level:
  center (mean/median bias), spread (SD, MAE, RMSE), shape (skew, excess
  kurtosis), percentile spread, % of players within tolerance bands, and the
  directional split (how many over- vs under-predicted, and tail sizes).

Two flavours at the half level:
  - IN-SAMPLE: the delta exactly as shown on the leaderboard (model fit on
    all halves, scoring the same halves).
  - OUT-OF-FOLD: honest generalization error (GroupKFold on batter, no player
    in train+test). This is the spread you'd see on a NEW player-half.

Also shows how the spread tightens from half -> season -> all-time as the PA
sample grows (less observed-side sampling noise).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.model_selection import GroupKFold

from pa_value import PAValueModel
from train_pa_value import make_pipe

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).parent
PROCESSED = PROJECT / "data" / "processed"
PV = PAValueModel(PROJECT / "pa_value_models.joblib")


def describe(x: np.ndarray, label: str, weights: np.ndarray | None = None) -> None:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if weights is not None:
        w = np.asarray(weights, dtype=float)[:len(x)]
        mean = np.average(x, weights=w)
        sd = np.sqrt(np.average((x - mean) ** 2, weights=w))
    else:
        mean, sd = x.mean(), x.std(ddof=1)
    mae = np.abs(x).mean()
    rmse = np.sqrt((x ** 2).mean())
    skew = stats.skew(x)
    kurt = stats.kurtosis(x)              # excess (normal = 0)
    pos = (x > 0).mean() * 100
    within = {f"±{t:.3f}": (np.abs(x) <= t).mean() * 100 for t in (.010, .020, .030, .050)}
    p = np.percentile(x, [1, 5, 25, 50, 75, 95, 99])
    print(f"\n{label}  (n={len(x)})")
    print(f"  mean(bias)={mean:+.4f}  median={np.median(x):+.4f}  SD={sd:.4f}")
    print(f"  MAE={mae:.4f}  RMSE={rmse:.4f}")
    print(f"  skew={skew:+.2f}  excess_kurtosis={kurt:+.2f}  (+skew = elite tail under-predicted)")
    print(f"  % over-predicted(Δ<0)={100-pos:.1f}   % under-predicted(Δ>0)={pos:.1f}")
    print(f"  within: " + "  ".join(f"{k}:{v:.0f}%" for k, v in within.items()))
    print(f"  pctiles  1%={p[0]:+.3f}  5%={p[1]:+.3f}  25%={p[2]:+.3f}  "
          f"50%={p[3]:+.3f}  75%={p[4]:+.3f}  95%={p[5]:+.3f}  99%={p[6]:+.3f}")


def oof_resid(df: pd.DataFrame) -> np.ndarray:
    sub = df.dropna(subset=PV.features + ["obs_xwoba"]).reset_index(drop=True)
    X, y, g = sub[PV.features], sub["obs_xwoba"], sub["batter"]
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(X, y, g):
        oof[te] = make_pipe().fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
    return (sub["obs_xwoba"].to_numpy() - oof)


def main() -> None:
    half = pd.read_parquet(PROCESSED / "leaderboard_half.parquet")
    season = pd.read_parquet(PROCESSED / "leaderboard_season.parquet")
    alltime = pd.read_parquet(PROCESSED / "leaderboard_alltime.parquet")

    print("=" * 80)
    print("xwOBA DELTA (obs - pred) DISTRIBUTION")
    print("=" * 80)

    describe(half["xwoba_resid"], "HALF — in-sample (the leaderboard column), all rows")
    hi = half[half["n_pa"] >= 250]
    describe(hi["xwoba_resid"], "HALF — in-sample, PA>=250 (less observed-side noise)")
    describe(half["xwoba_resid"].to_numpy(), "HALF — in-sample, PA-weighted",
             weights=half["n_pa"].to_numpy())

    describe(oof_resid(half), "HALF — OUT-OF-FOLD (honest error on a new player-half)")

    describe(season["xwoba_resid"], "SEASON — in-sample")
    describe(alltime["xwoba_resid"], "ALL-TIME — in-sample (career, most stable)")
    at = alltime[alltime["n_pa"] >= 1000]
    describe(at["xwoba_resid"], "ALL-TIME — in-sample, PA>=1000 (true talent miss)")

    # correlation of |delta| with PA -> confirms shrinking-with-sample
    h = half.dropna(subset=["xwoba_resid", "n_pa"])
    r = np.corrcoef(h["n_pa"], h["xwoba_resid"].abs())[0, 1]
    print(f"\ncorr(|delta|, n_pa) at half level = {r:+.3f}  "
          f"(negative => miss shrinks as sample grows, i.e. much of half-level "
          f"delta is observed-side sampling noise)")

    # histogram
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].hist(half["xwoba_resid"].dropna(), bins=50, color="#e6a83c", alpha=.8)
    ax[0].axvline(0, color="#888", ls="--", lw=1)
    ax[0].set_title("Half-level xwOBA delta (in-sample)")
    ax[0].set_xlabel("obs - pred")
    ax[1].hist(alltime["xwoba_resid"].dropna(), bins=40, color="#4f9eff", alpha=.8)
    ax[1].axvline(0, color="#888", ls="--", lw=1)
    ax[1].set_title("All-time (career) xwOBA delta")
    ax[1].set_xlabel("obs - pred")
    fig.tight_layout()
    fig.savefig(PROCESSED / "delta_distribution.png", dpi=130, bbox_inches="tight")
    print(f"\nSaved {PROCESSED/'delta_distribution.png'}")


if __name__ == "__main__":
    main()
