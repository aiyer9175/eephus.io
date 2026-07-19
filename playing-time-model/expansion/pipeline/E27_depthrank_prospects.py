# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E27 — Depth-rank for PROSPECTS (the right universe).

E26 showed depth-rank is redundant for incumbents (a 600-PA regular is always
his team's listed starter -> no new info vs usage history). But the depth
chart's whole value is resolving roles for players WITHOUT a track record —
the prospect slice. A pre-debut prospect listed as the Opening-Day STARTER
(e.g., Volpe = SS#1, 2023) is about to play every day; our prospect model,
blind to the depth chart, can't see that. This is factual published info, not
a projection.

Adds depth_rank (Opening-Day, 1 = projected starter; absent = not on the MLB
depth chart) to the E11 prospect model. Tests debut AUC + PA on the prospect
universe, pooled and on prospects who ARE on an Opening-Day depth chart.

Output: research/E27_depthrank_prospects.md
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

lines = ["# Expansion E27 — Depth-Rank for Prospects", ""]


def log(s=""):
    lines.append(s)
    print(s)


# prospect universe + E11 features (mirror E16)
mn = pd.read_parquet(DEEP_MIN)
sp = pd.read_parquet(f"{PT}/data/processed/usage_spine.parquet")[["mlbam_id", "season", "pa"]]
mlb = sp.sort_values("season"); mlb["career_pa"] = mlb.groupby("mlbam_id").pa.cumsum()
upm = mn[mn.sport.isin([11, 12])].copy()
lvl = upm.sort_values("sport").groupby(["batter", "season"]).first().reset_index().rename(columns={"batter": "mlbam_id"})
tot = mn.groupby(["batter", "season"]).pa.sum().rename("pa_milb_t").reset_index().rename(columns={"batter": "mlbam_id"})
u = lvl.merge(tot, on=["mlbam_id", "season"]); u = u[u.age <= 30]
u = u.merge(mlb[["mlbam_id", "season", "career_pa"]], on=["mlbam_id", "season"], how="left")
u["career_pa"] = u.sort_values("season").groupby("mlbam_id").career_pa.ffill(); u = u[u.career_pa.isna() | (u.career_pa == 0)]
t2 = tot.copy(); t2["season"] += 1; t2 = t2.rename(columns={"pa_milb_t": "pa_milb_l1"}); u = u.merge(t2, on=["mlbam_id", "season"], how="left")
nxt = sp.rename(columns={"pa": "pa_next"}).copy(); nxt["season"] -= 1; u = u.merge(nxt, on=["mlbam_id", "season"], how="left")
u["pa_next"] = u.pa_next.fillna(0); u["debut_next"] = (u.pa_next > 0).astype(int); u["target_year"] = u.season + 1
dr = pd.read_parquet(f"{PT}/data/raw/draft_history.parquet")
u = u.merge(dr[["mlbam_id", "draft_year", "overall_pick", "signing_bonus"]], on="mlbam_id", how="left")
u["drafted"] = u.draft_year.notna().astype(int); u["years_since_draft"] = u.season - u.draft_year; u["log_bonus"] = np.log1p(u.signing_bonus)
tx = pd.read_parquet(f"{PT}/data/raw/transactions.parquet"); tx = tx[tx.mlbam_id.notna()].astype({"mlbam_id": int}); tx["date"] = pd.to_datetime(tx.date)
se = tx[tx.type_code == "SE"].groupby("mlbam_id").date.min().rename("first_se"); u = u.merge(se, on="mlbam_id", how="left")
u["selected_40man"] = (u.first_se <= pd.to_datetime(u.target_year.astype(str) + "-03-25")).astype(int)
od = pd.read_parquet(f"{PT}/data/processed/od_features.parquet")
u = u.merge(od, on=["mlbam_id", "target_year"], how="left")
ko = u.target_year >= 2004; u.loc[ko, ["on_40man_od", "on_active_od"]] = u.loc[ko, ["on_40man_od", "on_active_od"]].fillna(0)
ped = pd.read_parquet(f"{PT}/data/processed/pedigree_features.parquet")
u = u.merge(ped[["mlbam_id", "season", "fv_latest", "top100_rank", "org_rank"]], on=["mlbam_id", "season"], how="left")

# depth-rank (Opening-Day, target year) — the new factual feature
dc = pd.read_parquet(f"{EXP}/data/processed/depth_rank.parquet")
u = u.merge(dc[["mlbam_id", "target_year", "depth_rank"]], on=["mlbam_id", "target_year"], how="left")
u["on_dc"] = u.depth_rank.notna().astype(int)
u["dc_starter"] = (u.depth_rank == 1).astype(int)
u["dc_rank"] = u.depth_rank.fillna(9).clip(upper=9)
DC = ["on_dc", "dc_starter", "dc_rank"]

E11_F = ["age", "sport", "pa", "pa_milb_t", "pa_milb_l1", "woba", "k_pct", "bb_pct", "iso",
         "overall_pick", "log_bonus", "drafted", "years_since_draft", "selected_40man",
         "on_40man_od", "on_active_od", "od_pos_depth", "od_team_pos_players",
         "fv_latest", "top100_rank", "org_rank"]
tr = u[u.target_year <= 2022]; te = u[u.target_year.isin([2023, 2024, 2025])].copy()
log(f"- prospects test n={len(te)}; on OD depth chart {te.on_dc.mean():.0%}; "
    f"of those listed as starter {(te[te.on_dc==1].dc_starter).mean():.0%}")
log(f"- prospects on a DC: debut rate {te[te.on_dc==1].debut_next.mean():.0%} "
    f"vs not-on-DC {te[te.on_dc==0].debut_next.mean():.0%}; "
    f"DC-STARTERS debut rate {te[te.dc_starter==1].debut_next.mean():.0%}")


def hurdle(F):
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=7).fit(tr[F], tr.debut_next)
    deb = tr[tr.debut_next == 1]
    reg = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=7).fit(deb[F], deb.pa_next)
    p = clf.predict_proba(te[F])[:, 1]
    return p, p * np.clip(reg.predict(te[F]), 0, None)


def sc(p, ep, mask=None):
    d = te if mask is None else te[mask]
    pp = p if mask is None else p[mask.values]
    ee = ep if mask is None else ep[mask.values]
    return (roc_auc_score(d.debut_next, pp), float(np.abs(ee - d.pa_next).mean()),
            float(spearmanr(ee, d.pa_next).statistic))


pb, eb = hurdle(E11_F)
pg, eg = hurdle(E11_F + DC)
log("\n## Pooled prospect universe (test 2023-25)")
for nm, (p, e) in [("E11 base", (pb, eb)), ("+depth-rank", (pg, eg))]:
    a, m, r = sc(p, e)
    log(f"- {nm:14s} debut_AUC {a:.4f}  PA_MAE {m:.1f}  PA_rho {r:.4f}")

cov = te.on_dc == 1
log(f"\n## Prospects ON an Opening-Day depth chart (n={int(cov.sum())} — where the signal lives)")
for nm, (p, e) in [("E11 base", (pb, eb)), ("+depth-rank", (pg, eg))]:
    a, m, r = sc(p, e, cov)
    log(f"- {nm:14s} debut_AUC {a:.4f}  PA_MAE {m:.1f}  PA_rho {r:.4f}")

with open(f"{EXP}/research/E27_depthrank_prospects.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
