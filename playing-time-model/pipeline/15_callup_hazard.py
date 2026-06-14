# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 15 — Call-up universe + debut hazard (Model D, v1).

Universe: upper-minors player-seasons (AA/AAA, age <= 30) with ZERO career
MLB PA through year t. Targets:
  debut_next   any MLB PA in year t+1 (classification)
  pa_next      MLB PA in year t+1 (regression, mostly 0)

This is where Prospect Pedigree+ and Service-Time live: tracker FV/top-100
coverage is dense here (unlike the incumbent ladder, Module 6), draft
pedigree covers all years, and the 40-man "Selected" transaction before
the season is the service-time tell.

Feature blocks (all known by Mar 25 of target year):
  PERF   age, top level, AAA/AA PA + wOBA/K/BB/ISO (year t), 2-yr minors PA
  DRAFT  overall_pick, log_bonus, drafted, years_since_draft
  TX     selected_40man (SE event <= Mar 25 t+1), n_asg_career
  FV     fv_latest, top100_rank, org_rank (2022+ targets only; NaN earlier)

Splits: train targets 2010-2019, 2022 (2020/2021 dropped: COVID wiped the
2020 minors season). Test targets 2023-2025.

Ablation reported: PERF -> +DRAFT -> +TX -> +FV (FV scored only on 2023+
where coverage exists, vs same model without FV).

Output: reports/15_callup_hazard.md, data/processed/callup_pairs.parquet
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import (HistGradientBoostingClassifier,
                              HistGradientBoostingRegressor)
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

OUT = "/Users/willcahoon/playing_time_model"
DEEP_MIN = "/Users/willcahoon/projection_engine/data/deep_minors.parquet"
SPINE = f"{OUT}/data/processed/usage_spine.parquet"
DRAFT = f"{OUT}/data/raw/draft_history.parquet"
TX = f"{OUT}/data/raw/transactions.parquet"
PED = f"{OUT}/data/processed/pedigree_features.parquet"

lines = ["# Module 15 — Call-up / Debut Hazard (Model D v1)", ""]


def log(s=""):
    lines.append(s)
    print(s)


mn = pd.read_parquet(DEEP_MIN)
sp = pd.read_parquet(SPINE)[["mlbam_id", "season", "pa"]]

# career MLB PA through year t
mlb = sp.sort_values("season")
mlb["career_pa"] = mlb.groupby("mlbam_id").pa.cumsum()

# universe: AA/AAA seasons, age<=30
up = mn[mn.sport.isin([11, 12])].copy()
lvl = (up.sort_values("sport")                       # 11=AAA preferred
         .groupby(["batter", "season"]).first().reset_index())
lvl = lvl.rename(columns={"batter": "mlbam_id"})
tot = (mn.groupby(["batter", "season"]).pa.sum()
         .rename("pa_milb_t").reset_index()
         .rename(columns={"batter": "mlbam_id"}))
u = lvl.merge(tot, on=["mlbam_id", "season"])
u = u[u.age <= 30]

# exclude anyone with career MLB PA through t
u = u.merge(mlb[["mlbam_id", "season", "career_pa"]],
            on=["mlbam_id", "season"], how="left")
grp = u.sort_values("season")
u["career_pa"] = (grp.groupby("mlbam_id").career_pa.ffill()
                  if "career_pa" in u else 0)
u = u[u.career_pa.isna() | (u.career_pa == 0)]

# 2-yr minors PA
tot2 = tot.copy()
tot2["season"] = tot2.season + 1
tot2 = tot2.rename(columns={"pa_milb_t": "pa_milb_l1"})
u = u.merge(tot2, on=["mlbam_id", "season"], how="left")

# targets
nxt = sp.rename(columns={"pa": "pa_next"}).copy()
nxt["season"] = nxt.season - 1
u = u.merge(nxt, on=["mlbam_id", "season"], how="left")
u["pa_next"] = u.pa_next.fillna(0)
u["debut_next"] = (u.pa_next > 0).astype(int)
u["target_year"] = u.season + 1

# draft pedigree
dr = pd.read_parquet(DRAFT)
u = u.merge(dr[["mlbam_id", "draft_year", "overall_pick", "signing_bonus"]],
            on="mlbam_id", how="left")
u["drafted"] = u.draft_year.notna().astype(int)
u["years_since_draft"] = u.season - u.draft_year
u["log_bonus"] = np.log1p(u.signing_bonus)

# transactions: selected to 40-man before Mar 25 of target year
tx = pd.read_parquet(TX)
tx = tx[tx.mlbam_id.notna()].copy()
tx["mlbam_id"] = tx.mlbam_id.astype(int)
tx["date"] = pd.to_datetime(tx.date)
se = tx[tx.type_code == "SE"][["mlbam_id", "date"]]
u["cutoff"] = pd.to_datetime((u.target_year).astype(str) + "-03-25")
se_first = se.groupby("mlbam_id").date.min().rename("first_se")
u = u.merge(se_first, on="mlbam_id", how="left")
u["selected_40man"] = (u.first_se <= u.cutoff).astype(int)

# tracker FV (targets 2022+ only)
ped = pd.read_parquet(PED)
u = u.merge(ped[["mlbam_id", "season", "fv_latest", "top100_rank",
                 "org_rank"]], on=["mlbam_id", "season"], how="left")

u[["mlbam_id", "season", "target_year", "debut_next", "pa_next"]].to_parquet(
    f"{OUT}/data/processed/callup_pairs.parquet", index=False)

PERF = ["age", "sport", "pa", "pa_milb_t", "pa_milb_l1", "woba", "k_pct",
        "bb_pct", "iso"]
DRAFTF = ["overall_pick", "log_bonus", "drafted", "years_since_draft"]
TXF = ["selected_40man"]
FVF = ["fv_latest", "top100_rank", "org_rank"]

train = u[u.target_year.isin(list(range(2010, 2020)) + [2022])]
test = u[u.target_year.isin([2023, 2024, 2025])]
log(f"- universe: {len(u)} AA/AAA pre-debut player-seasons "
    f"({u.mlbam_id.nunique()} players)")
log(f"- train {len(train)} (targets 2010-19+2022, debut rate "
    f"{train.debut_next.mean():.1%}), test {len(test)} (2023-25, "
    f"{test.debut_next.mean():.1%})")
log(f"- FV coverage in test: {test.fv_latest.notna().mean():.1%}")


def clf_eval(name, F, tr=train, te=test):
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                                       random_state=7)
    m.fit(tr[F], tr.debut_next)
    p = m.predict_proba(te[F])[:, 1]
    return {"model": name,
            "AUC": round(roc_auc_score(te.debut_next, p), 4),
            "Brier": round(brier_score_loss(te.debut_next, p), 4),
            "LogLoss": round(log_loss(te.debut_next, p), 4)}, p


log("\n## Debut-in-t+1 classification (ablation ladder)")
res = []
ladders = [("PERF", PERF), ("+DRAFT", PERF + DRAFTF),
           ("+TX(40-man)", PERF + DRAFTF + TXF),
           ("+FV", PERF + DRAFTF + TXF + FVF)]
probs = {}
for name, F in ladders:
    r, p = clf_eval(name, F)
    probs[name] = p
    res.append(r)
log(pd.DataFrame(res).to_string(index=False))

# calibration of best model
best = "+FV"
p = probs[best]
log(f"\n## Calibration ({best}, test)")
qs = pd.qcut(p, 10, duplicates="drop")
cal = test.assign(p=p).groupby(qs, observed=True).agg(
    pred=("p", "mean"), actual=("debut_next", "mean"), n=("p", "size"))
log(cal.round(3).to_string())

# PA among predicted debuts (regression, two-stage expected PA)
reg = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05,
                                    random_state=7)
F = PERF + DRAFTF + TXF + FVF
reg.fit(train[F], train.pa_next)
pa_hat = np.clip(reg.predict(test[F]), 0, None)
err = pa_hat - test.pa_next.values
log(f"\n## PA_next regression (same features): MAE "
    f"{np.abs(err).mean():.1f}, RMSE {np.sqrt((err**2).mean()):.1f}")

# does FV add among covered players (2023-25 all covered-era)?
sub = test[test.fv_latest.notna()]
if len(sub) > 100:
    r_no, p_no = clf_eval("no-FV on FV-covered", PERF + DRAFTF + TXF,
                          train, sub)
    r_fv, p_fv = clf_eval("FV on FV-covered", PERF + DRAFTF + TXF + FVF,
                          train, sub)
    log(f"\n## FV incremental on FV-covered test rows (n={len(sub)})")
    log(pd.DataFrame([r_no, r_fv]).to_string(index=False))

with open(f"{OUT}/reports/15_callup_hazard.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
