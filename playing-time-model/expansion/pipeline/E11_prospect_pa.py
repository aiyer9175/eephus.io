# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E11 — Prospect playing-time projection + incremental value audit.

The point of the whole expansion: project PROSPECT playing time (next-year
MLB PA for AA/AAA pre-debut hitters) and quantify what each signal adds.

Universe: AA/AAA pre-debut hitter-seasons (career MLB PA == 0 through t),
age <= 30. Target: MLB PA next year (pa_next; ~88% are 0, debut rate 12%,
median debut PA 78). Forward-chained OOF; eval focus targets 2023-2025.

Model: hurdle / two-stage expected PA
  p_debut  = P(pa_next > 0)                 HGB classifier
  e_pa     = E[pa_next | debut]             HGB regressor on debuts only
  E[PA]    = p_debut * e_pa
(direct single-stage GBM regression reported as a challenger.)

Incremental value ladder (each adds a block, OOS on the SAME universe):
  M0 age+level -> M1 +minors perf -> M2 +draft pedigree -> M3 +40-man
  -> M4 +tracker FV (coverage-limited; also tested on FV-covered subset).

Benchmark: vs preseason Steamer PA on the prospect universe (Steamer covers
99.7% of actual debuts) — "what does our prospect model add over public?"

Output: data/processed/prospect_pa_proj.parquet, research/E11_prospect_pa.md
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import (HistGradientBoostingClassifier,
                              HistGradientBoostingRegressor)
from sklearn.metrics import roc_auc_score

PT = "/Users/willcahoon/playing_time_model"
EXP = f"{PT}/expansion"
DEEP_MIN = "/Users/willcahoon/projection_engine/data/deep_minors.parquet"

lines = ["# Expansion E11 — Prospect Playing-Time Projection + Value Audit", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---------- universe
mn = pd.read_parquet(DEEP_MIN)
sp = pd.read_parquet(f"{PT}/data/processed/usage_spine.parquet")[
    ["mlbam_id", "season", "pa"]]
mlb = sp.sort_values("season")
mlb["career_pa"] = mlb.groupby("mlbam_id").pa.cumsum()
up = mn[mn.sport.isin([11, 12])].copy()
lvl = up.sort_values("sport").groupby(["batter", "season"]).first().reset_index() \
        .rename(columns={"batter": "mlbam_id"})
tot = (mn.groupby(["batter", "season"]).pa.sum().rename("pa_milb_t")
         .reset_index().rename(columns={"batter": "mlbam_id"}))
u = lvl.merge(tot, on=["mlbam_id", "season"])
u = u[u.age <= 30]
u = u.merge(mlb[["mlbam_id", "season", "career_pa"]],
            on=["mlbam_id", "season"], how="left")
u["career_pa"] = u.sort_values("season").groupby("mlbam_id").career_pa.ffill()
u = u[u.career_pa.isna() | (u.career_pa == 0)]
# 2-yr minors PA
tot2 = tot.copy(); tot2["season"] += 1
tot2 = tot2.rename(columns={"pa_milb_t": "pa_milb_l1"})
u = u.merge(tot2, on=["mlbam_id", "season"], how="left")
nxt = sp.rename(columns={"pa": "pa_next"}).copy(); nxt["season"] -= 1
u = u.merge(nxt, on=["mlbam_id", "season"], how="left")
u["pa_next"] = u.pa_next.fillna(0)
u["debut_next"] = (u.pa_next > 0).astype(int)
u["target_year"] = u.season + 1

# ---------- features
dr = pd.read_parquet(f"{PT}/data/raw/draft_history.parquet")
u = u.merge(dr[["mlbam_id", "draft_year", "overall_pick", "signing_bonus"]],
            on="mlbam_id", how="left")
u["drafted"] = u.draft_year.notna().astype(int)
u["years_since_draft"] = u.season - u.draft_year
u["log_bonus"] = np.log1p(u.signing_bonus)
tx = pd.read_parquet(f"{PT}/data/raw/transactions.parquet")
tx = tx[tx.mlbam_id.notna()].astype({"mlbam_id": int}); tx["date"] = pd.to_datetime(tx.date)
se = tx[tx.type_code == "SE"].groupby("mlbam_id").date.min().rename("first_se")
u = u.merge(se, on="mlbam_id", how="left")
u["selected_40man"] = (
    u.first_se <= pd.to_datetime(u.target_year.astype(str) + "-03-25")).astype(int)
ped = pd.read_parquet(f"{PT}/data/processed/pedigree_features.parquet")
u = u.merge(ped[["mlbam_id", "season", "fv_latest", "top100_rank", "org_rank"]],
            on=["mlbam_id", "season"], how="left")

BLOCKS = {
    "M0 age+level": ["age", "sport"],
    "M1 +minors perf": ["age", "sport", "pa", "pa_milb_t", "pa_milb_l1",
                        "woba", "k_pct", "bb_pct", "iso"],
    "M2 +draft": ["age", "sport", "pa", "pa_milb_t", "pa_milb_l1", "woba",
                  "k_pct", "bb_pct", "iso", "overall_pick", "log_bonus",
                  "drafted", "years_since_draft"],
    "M3 +40-man": ["age", "sport", "pa", "pa_milb_t", "pa_milb_l1", "woba",
                   "k_pct", "bb_pct", "iso", "overall_pick", "log_bonus",
                   "drafted", "years_since_draft", "selected_40man"],
    "M4 +FV": ["age", "sport", "pa", "pa_milb_t", "pa_milb_l1", "woba",
               "k_pct", "bb_pct", "iso", "overall_pick", "log_bonus",
               "drafted", "years_since_draft", "selected_40man",
               "fv_latest", "top100_rank", "org_rank"],
}
years = sorted(u.target_year.unique())


def oof_expected_pa(F):
    """forward-chained two-stage expected PA, returns col aligned to u."""
    out = pd.Series(np.nan, index=u.index)
    pdebut = pd.Series(np.nan, index=u.index)
    for ty in years:
        tr = u[u.target_year < ty]
        if len(tr) < 500 or tr.debut_next.nunique() < 2:
            continue
        te_idx = u.index[u.target_year == ty]
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                                             random_state=7).fit(tr[F], tr.debut_next)
        deb = tr[tr.debut_next == 1]
        reg = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05,
                                            random_state=7).fit(deb[F], deb.pa_next)
        pd_ = clf.predict_proba(u.loc[te_idx, F])[:, 1]
        ep = np.clip(reg.predict(u.loc[te_idx, F]), 0, None)
        out.loc[te_idx] = pd_ * ep
        pdebut.loc[te_idx] = pd_
    return out, pdebut


def score(name, pred, mask):
    s = u[mask]
    p = pred[mask]
    y = s.pa_next.values
    err = p.values - y
    return {"model": name, "n": int(mask.sum()),
            "MAE": round(float(np.abs(err).mean()), 1),
            "RMSE": round(float(np.sqrt((err ** 2).mean())), 1),
            "rho": round(float(spearmanr(p, y).statistic), 4)}


EVAL = u.target_year.isin([2023, 2024, 2025])
log(f"- prospect universe: {len(u)} AA/AAA pre-debut seasons; "
    f"eval (2023-25) n={int(EVAL.sum())}, debut rate "
    f"{u[EVAL].debut_next.mean():.1%}, median debut PA "
    f"{int(u[EVAL & (u.debut_next==1)].pa_next.median())}")

log("\n## Incremental value ladder (expected PA, OOS targets 2023-25)")
rows, preds = [], {}
for name, F in BLOCKS.items():
    ep, pdb = oof_expected_pa(F)
    preds[name] = (ep, pdb)
    r = score(name, ep, EVAL)
    r["debut_AUC"] = round(roc_auc_score(u[EVAL].debut_next,
                                         pdb[EVAL]), 4)
    rows.append(r)
log(pd.DataFrame(rows).to_string(index=False))

# FV increment on FV-covered subset (fair test)
fvmask = EVAL & u.fv_latest.notna()
log(f"\n## FV increment on FV-covered prospects only (n={int(fvmask.sum())})")
for name in ["M3 +40-man", "M4 +FV"]:
    ep, pdb = preds[name]
    r = score(name, ep, fvmask)
    r["debut_AUC"] = round(roc_auc_score(u[fvmask].debut_next, pdb[fvmask]), 4)
    log(str(r))

# ---------- Steamer benchmark on prospects
pub = pd.read_parquet(f"{PT}/data/raw/public_projections.parquet")
stm = (pub[pub.system == "steamer"][["mlbam_id", "season", "pa_proj"]]
       .rename(columns={"season": "target_year", "pa_proj": "pa_steamer"}))
u2 = u.merge(stm, on=["mlbam_id", "target_year"], how="left")
champ_ep = preds["M3 +40-man"][0]      # FV too thin to be the champion
u2["ours"] = champ_ep
both = EVAL & u2.pa_steamer.notna() & champ_ep.notna()
s = u2[both]
log(f"\n## Prospect benchmark vs Steamer (n={int(both.sum())}, targets 2023-25)")
def sc(name, p):
    y = s.pa_next.values; err = p - y
    return {"model": name, "MAE": round(float(np.abs(err).mean()), 1),
            "RMSE": round(float(np.sqrt((err**2).mean())), 1),
            "rho": round(float(spearmanr(p, y).statistic), 4)}
rows = [sc("Ours (M3, prospect-trained)", s.ours.values),
        sc("Steamer", s.pa_steamer.values),
        sc("blend (ours+Steamer)/2", 0.5*s.ours.values + 0.5*s.pa_steamer.values)]
log(pd.DataFrame(rows).to_string(index=False))

# save projection
u2[["mlbam_id", "season", "target_year", "pa_next", "debut_next", "ours"]] \
    .to_parquet(f"{EXP}/data/processed/prospect_pa_proj.parquet", index=False)

log("\n## Read")
log("- debut_AUC = stage-1 ranking of WHO debuts; rho = ranking of how much PA.")
log("- ladder shows which signals actually move prospect playing time.")
log("- Steamer comparison = what a prospect-specific model adds over the "
    "public system that already projects these players.")

with open(f"{EXP}/research/E11_prospect_pa.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
