# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E16 — Defense/speed for prospects (scouting grades).

MLB Savant OAA/sprint have 0% coverage of pre-debut prospects, so the
prospect-level defense/speed signal is the SCOUTING grade (field, throw/arm,
speed) from the tracker — exactly what the framework specifies. Tests whether
they add to the E11 prospect model, especially for GLOVE-FIRST prospects (a
defensive prospect debuts for the glove even with a modest bat).

Leakage-safe: scouting grades from snapshots dated <= Mar 31 of the target
year and within the prior 14 months (same cutoff as parent Module 6 FV).

Baseline = E11 prospect stack (perf + draft + 40man + OD-roster + FV).
Split: train target<=2022, test 2023-25 (Savant-style fixed split).

Output: research/E16_prospect_def_speed.md
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

lines = ["# Expansion E16 — Prospect Defense/Speed (scouting grades)", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---------- prospect universe + E11 features (mirror E20 prospect block)
mn = pd.read_parquet(DEEP_MIN)
sp = pd.read_parquet(f"{PT}/data/processed/usage_spine.parquet")[
    ["mlbam_id", "season", "pa"]]
mlb = sp.sort_values("season"); mlb["career_pa"] = mlb.groupby("mlbam_id").pa.cumsum()
upm = mn[mn.sport.isin([11, 12])].copy()
lvl = upm.sort_values("sport").groupby(["batter", "season"]).first().reset_index() \
         .rename(columns={"batter": "mlbam_id"})
tot = (mn.groupby(["batter", "season"]).pa.sum().rename("pa_milb_t")
         .reset_index().rename(columns={"batter": "mlbam_id"}))
u = lvl.merge(tot, on=["mlbam_id", "season"]); u = u[u.age <= 30]
u = u.merge(mlb[["mlbam_id", "season", "career_pa"]], on=["mlbam_id", "season"], how="left")
u["career_pa"] = u.sort_values("season").groupby("mlbam_id").career_pa.ffill()
u = u[u.career_pa.isna() | (u.career_pa == 0)]
t2 = tot.copy(); t2["season"] += 1; t2 = t2.rename(columns={"pa_milb_t": "pa_milb_l1"})
u = u.merge(t2, on=["mlbam_id", "season"], how="left")
nxt = sp.rename(columns={"pa": "pa_next"}).copy(); nxt["season"] -= 1
u = u.merge(nxt, on=["mlbam_id", "season"], how="left")
u["pa_next"] = u.pa_next.fillna(0); u["debut_next"] = (u.pa_next > 0).astype(int)
u["target_year"] = u.season + 1
dr = pd.read_parquet(f"{PT}/data/raw/draft_history.parquet")
u = u.merge(dr[["mlbam_id", "draft_year", "overall_pick", "signing_bonus"]], on="mlbam_id", how="left")
u["drafted"] = u.draft_year.notna().astype(int); u["years_since_draft"] = u.season - u.draft_year
u["log_bonus"] = np.log1p(u.signing_bonus)
tx = pd.read_parquet(f"{PT}/data/raw/transactions.parquet")
tx = tx[tx.mlbam_id.notna()].astype({"mlbam_id": int}); tx["date"] = pd.to_datetime(tx.date)
se = tx[tx.type_code == "SE"].groupby("mlbam_id").date.min().rename("first_se")
u = u.merge(se, on="mlbam_id", how="left")
u["selected_40man"] = (u.first_se <= pd.to_datetime(u.target_year.astype(str) + "-03-25")).astype(int)
od = pd.read_parquet(f"{PT}/data/processed/od_features.parquet")
u = u.merge(od, on=["mlbam_id", "target_year"], how="left")
ko = u.target_year >= 2004
u.loc[ko, ["on_40man_od", "on_active_od"]] = u.loc[ko, ["on_40man_od", "on_active_od"]].fillna(0)
ped = pd.read_parquet(f"{PT}/data/processed/pedigree_features.parquet")
u = u.merge(ped[["mlbam_id", "season", "fv_latest", "top100_rank", "org_rank"]],
            on=["mlbam_id", "season"], how="left")

# ---------- scouting field/speed/arm, leakage-safe per target year
g = pd.read_parquet(f"{PT}/data/processed/grades_long.parquet")
g = g[g.mlbam_id.notna()].copy(); g["mlbam_id"] = g.mlbam_id.astype(int)
g["snapshot_date"] = pd.to_datetime(g.snapshot_date)
rows = []
for ty in range(2022, 2026):
    cut = pd.Timestamp(f"{ty}-03-31"); floor = cut - pd.DateOffset(months=14)
    win = g[(g.snapshot_date <= cut) & (g.snapshot_date >= floor)].sort_values("snapshot_date")
    agg = win.groupby("mlbam_id")[["field", "speed", "throw"]].last()
    agg["season"] = ty - 1   # feature year
    rows.append(agg.reset_index())
scout = pd.concat(rows, ignore_index=True).rename(
    columns={"field": "scout_field", "speed": "scout_speed", "throw": "scout_arm"})
u = u.merge(scout, on=["mlbam_id", "season"], how="left")

E11_F = ["age", "sport", "pa", "pa_milb_t", "pa_milb_l1", "woba", "k_pct",
         "bb_pct", "iso", "overall_pick", "log_bonus", "drafted",
         "years_since_draft", "selected_40man", "on_40man_od", "on_active_od",
         "od_pos_depth", "od_team_pos_players", "fv_latest", "top100_rank",
         "org_rank"]
DS = ["scout_field", "scout_speed", "scout_arm"]

tr = u[u.target_year <= 2022]; te = u[u.target_year.isin([2023, 2024, 2025])].copy()
cov = te.scout_field.notna()
log(f"- prospect test n={len(te)}; with scouting grades {cov.mean():.0%} "
    f"(n={int(cov.sum())}) — limited, like FV")


def hurdle(F, tr=tr, te=te):
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                                         random_state=7).fit(tr[F], tr.debut_next)
    deb = tr[tr.debut_next == 1]
    reg = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05,
                                        random_state=7).fit(deb[F], deb.pa_next)
    p = clf.predict_proba(te[F])[:, 1]
    ep = p * np.clip(reg.predict(te[F]), 0, None)
    return p, ep


def score(p, ep, t):
    y = t.pa_next.values
    return (roc_auc_score(t.debut_next, p),
            float(np.abs(ep - y).mean()),
            float(spearmanr(ep, y).statistic))


pb, eb = hurdle(E11_F)
pg, eg = hurdle(E11_F + DS)
log("\n## Pooled (test 2023-25)")
for nm, (p, e) in [("E11 base", (pb, eb)), ("+scout def/speed", (pg, eg))]:
    a, m, r = score(p, e, te)
    log(f"- {nm:18s} debut_AUC {a:.4f}  PA_MAE {m:.1f}  PA_rho {r:.4f}")

log("\n## On scouting-covered prospects only (fair test)")
cidx = te[cov].index
sub = te.loc[cidx]
for nm, (p, e) in [("E11 base", (pb, eb)), ("+scout def/speed", (pg, eg))]:
    pp = pd.Series(p, index=te.index).loc[cidx].values
    ee = pd.Series(e, index=te.index).loc[cidx].values
    a, m, r = score(pp, ee, sub)
    log(f"- {nm:18s} debut_AUC {a:.4f}  PA_MAE {m:.1f}  PA_rho {r:.4f}")

# glove-first: high field grade, modest bat (low FV or low minors woba)
gf = cov & (te.scout_field >= 55) & (te.woba < te.woba.median())
log(f"\n## Glove-first prospects (field>=55, below-median bat; n={int(gf.sum())})")
if gf.sum() >= 20:
    gidx = te[gf].index; subg = te.loc[gidx]
    for nm, (p, e) in [("E11 base", (pb, eb)), ("+scout def/speed", (pg, eg))]:
        pp = pd.Series(p, index=te.index).loc[gidx].values
        ee = pd.Series(e, index=te.index).loc[gidx].values
        a, m, r = score(pp, ee, subg)
        log(f"- {nm:18s} debut_AUC {a:.4f}  PA_MAE {m:.1f}  PA_rho {r:.4f}")
else:
    log("- n too small")

with open(f"{EXP}/research/E16_prospect_def_speed.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
