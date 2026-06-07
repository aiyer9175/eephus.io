# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
woba_validity.py — Is the full-PA wOBA / xwOBA prediction statistically
valid SIGNAL, or just noise that happens to correlate?

A real validity check answers three things, not one:
  1. Is the out-of-fold predictive r reliably > 0?  (cluster-bootstrap CI)
  2. Does it beat the obvious baseline — last half's OBSERVED wOBA
     (persistence)?  (bootstrap CI of the r difference)
  3. Does the model add INCREMENTAL signal beyond persistence?  (partial
     correlation of model prediction with the outcome, controlling for
     last-half observed value; cluster-bootstrap CI + combined R^2)

All CIs use a CLUSTER bootstrap on batter: rows are player-halves and the
same player appears many times, so naive row-resampling understates the SE.
We resample players with replacement.

Model: appr17 (9 bat-tracking + 8 approach), GroupKFold(5) OOF predictions
of NEXT-half wOBA / xwOBA. Persistence = THIS-half observed wOBA / xwOBA.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from augmented_model_test import (
    APPROACH_FEATS, BASELINE_FEATS, approach_per_half, make_pipe, woba_per_half,
)

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).parent
PROCESSED = PROJECT / "data" / "processed"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
FEATS = BASELINE_FEATS + APPROACH_FEATS
PA_MIN = 100
N_BOOT = 2000
RNG = np.random.default_rng(7)


def next_half(h: str) -> str:
    season, sh = h.split("_")
    return f"{season}_H2" if sh == "H1" else f"{int(season) + 1}_H1"


def cv_oof(X: pd.DataFrame, y: pd.Series, groups: pd.Series, k: int = 5) -> np.ndarray:
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(k).split(X, y, groups):
        pipe = make_pipe().fit(X.iloc[tr], y.iloc[tr])
        oof[te] = pipe.predict(X.iloc[te])
    return oof


def pearson(a, b):
    return float(np.corrcoef(a, b)[0, 1])


def partial_r(actual, model, persist):
    """corr(actual, model | persist): correlation of residuals after removing persist."""
    def resid(y, x):
        x1 = np.column_stack([np.ones_like(x), x])
        beta, *_ = np.linalg.lstsq(x1, y, rcond=None)
        return y - x1 @ beta
    return pearson(resid(actual, persist), resid(model, persist))


def cluster_boot(df, fn, n=N_BOOT):
    """Cluster bootstrap on batter. fn(sub_df) -> scalar. Returns (lo, hi, p0)."""
    players = df["batter"].unique()
    by = {p: df[df["batter"] == p] for p in players}
    stats = []
    for _ in range(n):
        samp = RNG.choice(players, size=len(players), replace=True)
        sub = pd.concat([by[p] for p in samp], ignore_index=True)
        try:
            stats.append(fn(sub))
        except Exception:
            stats.append(np.nan)
    stats = np.array([s for s in stats if np.isfinite(s)])
    return np.percentile(stats, 2.5), np.percentile(stats, 97.5)


def build() -> pd.DataFrame:
    base = pd.read_csv(PROCESSED / "validation_concurrent.csv")
    approach = pd.concat([approach_per_half(h) for h in HALVES], ignore_index=True)
    woba = pd.concat([woba_per_half(h) for h in HALVES], ignore_index=True)
    m = base.merge(approach, on=["batter", "half"], how="inner") \
            .merge(woba, on=["batter", "half"], how="inner")
    m["next_half"] = m["half"].map(next_half)
    nxt = woba.rename(columns={"half": "next_half", "wOBA": "wOBA_next",
                               "xwOBA": "xwOBA_next", "n_pa": "n_pa_next"})
    pf = m.merge(nxt[["batter", "next_half", "wOBA_next", "xwOBA_next", "n_pa_next"]],
                 on=["batter", "next_half"], how="inner")
    pf = pf[(pf["n_pa"] >= PA_MIN) & (pf["n_pa_next"] >= PA_MIN)]
    return pf.dropna(subset=FEATS).reset_index(drop=True)


def assess(pf: pd.DataFrame, this: str, nxt: str, label: str) -> None:
    pf = pf.dropna(subset=[this, nxt]).reset_index(drop=True)
    pf = pf.assign(_oof=cv_oof(pf[FEATS], pf[nxt], pf["batter"]))
    pf = pf.dropna(subset=["_oof"]).reset_index(drop=True)

    r_model = pearson(pf["_oof"], pf[nxt])
    r_persist = pearson(pf[this], pf[nxt])
    pr = partial_r(pf[nxt].to_numpy(), pf["_oof"].to_numpy(), pf[this].to_numpy())

    ci_m = cluster_boot(pf, lambda d: pearson(cv_oof(d[FEATS], d[nxt], d["batter"]), d[nxt])
                        if d["batter"].nunique() > 6 else np.nan, n=400)
    ci_p = cluster_boot(pf, lambda d: pearson(d[this], d[nxt]))
    ci_diff = cluster_boot(pf, lambda d: pearson(d[this], d[nxt]) - r_model)  # persist - model
    ci_pr = cluster_boot(pf, lambda d: partial_r(d[nxt].to_numpy(), d["_oof"].to_numpy(),
                                                 d[this].to_numpy()))

    # combined R^2 vs persistence-only R^2
    def r2_combined(d):
        X = np.column_stack([np.ones(len(d)), d["_oof"], d[this]])
        b, *_ = np.linalg.lstsq(X, d[nxt], rcond=None)
        pred = X @ b
        ss = 1 - np.sum((d[nxt] - pred) ** 2) / np.sum((d[nxt] - d[nxt].mean()) ** 2)
        return ss
    r2_comb = r2_combined(pf)
    r2_persist = r_persist ** 2

    print(f"\n{'='*72}\n{label}   (n={len(pf)} player-half→next, "
          f"{pf['batter'].nunique()} players, PA≥{PA_MIN})\n{'='*72}")
    print(f"  model (appr17) predictive r : {r_model:.3f}   95% CI [{ci_m[0]:.3f}, {ci_m[1]:.3f}]")
    print(f"  persistence (last-half obs) r: {r_persist:.3f}   95% CI [{ci_p[0]:.3f}, {ci_p[1]:.3f}]")
    print(f"  persistence - model (Δr)     : {r_persist - r_model:+.3f}   "
          f"95% CI [{ci_diff[0]:+.3f}, {ci_diff[1]:+.3f}]")
    print(f"  INCREMENTAL partial r        : {pr:.3f}   95% CI [{ci_pr[0]:.3f}, {ci_pr[1]:.3f}]")
    print(f"    (model's correlation with outcome AFTER removing persistence)")
    print(f"  R²: persistence-only {r2_persist:.3f}  →  model+persistence {r2_comb:.3f}  "
          f"(+{r2_comb - r2_persist:.3f})")

    sig0 = "YES" if ci_m[0] > 0 else "no"
    sig_inc = "YES" if ci_pr[0] > 0 else "no"
    beats = "YES" if ci_diff[1] < 0 else ("no" if ci_diff[0] > 0 else "tie")
    print(f"  --> signal > 0? {sig0}.  adds beyond persistence? {sig_inc}.  "
          f"beats persistence outright? {beats}.")


def main() -> None:
    pf = build()
    print(f"Built {len(pf)} predictive rows ({pf['batter'].nunique()} players).")
    assess(pf, "xwOBA", "xwOBA_next", "xwOBA (full PA) — predicting next half")
    assess(pf, "wOBA", "wOBA_next", "wOBA (full PA) — predicting next half")


if __name__ == "__main__":
    main()
