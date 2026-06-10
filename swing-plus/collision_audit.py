# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
collision_audit.py — rigorous audit of the new Savant collision dataset against
every model in the framework (Swing+, Decision+, Contact+, B2B+, DC+).

Steps (per the universal model-development framework):
  8  REDUNDANCY    same-season corr: collision features x model scores
  4  PROJECTABILITY feature(t) -> outcome(t+1) univariate r
  5  INCREMENTAL   per model: baseline (model score) vs baseline + collision,
                   ridge, leave-one-transition-year-out CV (23->24, 24->25, 25->26),
                   out-of-sample R^2. Also vs the FULL framework (all 5 scores).

Sample: year t needs >=150 competitive swings; year t+1 needs >=200 PA.
Reproducibility: deterministic (no random seed needed — exact CV folds by year).
"""
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge

FEAT = ["miss_distance", "perfect_percent", "flawed_percent",
        "tied_up_percent", "centered_percent", "flailed_percent", "horiz_bias",
        "early_percent", "on_time_percent", "late_percent", "timing_bias",
        "over_percent", "lined_up_percent", "under_percent", "vert_bias",
        "timing_entropy", "horiz_entropy", "vert_entropy", "collision_entropy"]
MODELS = {"Swing+": "swing_plus", "Decision+": "decision_plus_mlb",
          "Contact+": "contact_plus_b2b", "B2B+": "b2b_plus", "DC+": "dc_plus_b2b"}
OUTS = ["obs_iso", "obs_avg_ev90", "obs_k_pct", "whiff_rate", "obs_bb_pct",
        "obs_avg", "obs_woba", "obs_xwobacon"]
# which future outcomes each model is accountable for
TARGETS = {"Swing+": ["obs_iso", "obs_avg_ev90"],
           "Decision+": ["obs_bb_pct", "obs_woba"],
           "Contact+": ["whiff_rate", "obs_k_pct", "obs_avg"],
           "B2B+": ["obs_xwobacon", "obs_woba"],
           "DC+": ["obs_woba", "obs_iso"]}


def build():
    F = pd.read_parquet("data/processed/savant_collision.parquet")
    b = pd.read_parquet("data/processed/leaderboard_season.parquet")
    b["year"] = b["season"].astype(int)
    rates = pd.read_parquet("data/processed/obs_rates.parquet")
    keep = ["batter", "year", "n_pa", "obs_iso", "obs_avg_ev90", "obs_k_pct",
            "obs_woba", "obs_xwobacon"] + list(MODELS.values())
    # board has stand-split rows -> collapse to one row per (batter, year)
    bk = b[keep].groupby(["batter", "year"], as_index=False).mean()
    d = F.merge(bk, left_on=["id", "year"], right_on=["batter", "year"], how="left")
    d = d.merge(rates[["batter", "year", "pa", "obs_bb_pct", "obs_avg"]],
                left_on=["id", "year"], right_on=["batter", "year"], how="left")
    return d


def pairs(d):
    t = d[d.n_swings >= 150].copy()
    t["yr1"] = t.year + 1
    o = d[d.pa >= 200][["id", "year", "pa"] + OUTS]
    p = t.merge(o, left_on=["id", "yr1"], right_on=["id", "year"],
                suffixes=("", "_next"))
    p["trans"] = p["year"].astype(str)  # transition fold = source year
    return p


def cv_r2(p, Xcols, ycol):
    """leave-one-transition-year-out CV R^2 (ridge on standardized X)."""
    y = p[ycol + "_next"]
    ok = p[Xcols].notna().all(axis=1) & y.notna()
    p, y = p[ok], y[ok]
    if len(p) < 150:
        return np.nan, 0
    sst, sse = 0.0, 0.0
    for yr in sorted(p.trans.unique()):
        tr, te = p[p.trans != yr], p[p.trans == yr]
        mu, sd = tr[Xcols].mean(), tr[Xcols].std().replace(0, 1)
        Xtr, Xte = (tr[Xcols] - mu) / sd, (te[Xcols] - mu) / sd
        mdl = Ridge(alpha=1.0).fit(Xtr, y.loc[tr.index])
        pred = mdl.predict(Xte)
        yt = y.loc[te.index]
        sse += ((yt - pred) ** 2).sum()
        sst += ((yt - y.loc[tr.index].mean()) ** 2).sum()
    return 1 - sse / sst, len(p)


if __name__ == "__main__":
    d = build()
    p = pairs(d)
    print(f"master n={len(d)}; t->t+1 pairs n={len(p)} "
          f"(transitions: {dict(p.trans.value_counts().sort_index())})\n")

    print("=== STEP 8: REDUNDANCY — same-season corr (collision x model scores) ===")
    hdr = f"{'feature':20s}" + "".join(f"{k:>10s}" for k in MODELS)
    print(hdr)
    for c in FEAT:
        row = f"{c:20s}"
        for k, col in MODELS.items():
            sub = d[[c, col]].dropna()
            row += f"{sub[c].corr(sub[col]):>10.2f}"
        print(row)

    print("\n=== STEP 4: PROJECTABILITY — feature(t) -> outcome(t+1) univariate r ===")
    print(f"{'feature':20s}" + "".join(f"{o.replace('obs_',''):>10s}" for o in OUTS))
    for c in FEAT:
        row = f"{c:20s}"
        for o in OUTS:
            sub = p[[c, o + "_next"]].dropna()
            row += f"{sub.iloc[:, 0].corr(sub.iloc[:, 1]):>10.2f}"
        print(row)

    print("\n=== STEP 5: INCREMENTAL VALUE — out-of-sample R^2 (leave-transition-out CV) ===")
    print(f"{'model':10s}{'target':14s}{'base R2':>9s}{'+coll R2':>9s}{'dR2':>8s}{'n':>6s}")
    for mname, mcol in MODELS.items():
        for tgt in TARGETS[mname]:
            r2b, n = cv_r2(p, [mcol], tgt)
            r2c, _ = cv_r2(p, [mcol] + FEAT, tgt)
            print(f"{mname:10s}{tgt.replace('obs_',''):14s}{r2b:>9.3f}{r2c:>9.3f}"
                  f"{r2c - r2b:>+8.3f}{n:>6d}")
    print()
    allm = list(MODELS.values())
    for tgt in ["obs_woba", "obs_iso", "obs_k_pct", "obs_avg", "obs_bb_pct"]:
        r2b, n = cv_r2(p, allm, tgt)
        r2c, _ = cv_r2(p, allm + FEAT, tgt)
        print(f"{'FULL(5)':10s}{tgt.replace('obs_',''):14s}{r2b:>9.3f}{r2c:>9.3f}"
              f"{r2c - r2b:>+8.3f}{n:>6d}")
