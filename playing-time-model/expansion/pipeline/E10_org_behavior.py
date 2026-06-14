# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E10 — Organizational promotion behavior (Bucket 4 / Q5).

THE question: do orgs have *persistent* promotion tendencies, and can those
tendencies *predict future* debut behavior beyond player talent?

Leakage-safe empirical design (no org dummies fit on the test period):

  1. PLAYER-ONLY debut model. Universe = AA/AAA pre-debut hitter-seasons
     (parent callup_pairs). Features: age, level, minors PA + rates, draft
     pedigree, 40-man-selected-by-Mar25. Out-of-fold debut probabilities via
     forward-chained CV → residual = debut_next − p_hat. Residual strips
     talent/pedigree, leaving "promoted faster/slower than the player merited".

  2. ORG AGGRESSIVENESS = mean residual of an org's prospects per season
     (org from minors_affiliation, primary = most-PA team that season).

  3. PERSISTENCE. (a) year-over-year AR(1) of org aggressiveness;
     (b) split-half: org mean residual odd vs even seasons;
     (c) variance share: between-org vs residual (is org a real, stable axis?).

  4. OOS PREDICTIVE VALUE (the decisive test). For held-out target years,
     attach each org's TRAILING-3yr aggressiveness (seasons strictly < t),
     add to the player-only model, test debut AUC/Brier lift. "Can past org
     behavior predict future promotions?" — yes only if this improves OOS.

Output: data/processed/org_aggressiveness.parquet, research/E10_org_behavior.md
"""
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score

PT = "/Users/willcahoon/playing_time_model"
EXP = f"{PT}/expansion"
DEEP_MIN = "/Users/willcahoon/projection_engine/data/deep_minors.parquet"

lines = ["# Expansion E10 — Organizational Promotion Behavior", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---------- universe + player features (compact rebuild of parent Module 15)
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

nxt = sp.rename(columns={"pa": "pa_next"}).copy()
nxt["season"] = nxt.season - 1
u = u.merge(nxt, on=["mlbam_id", "season"], how="left")
u["debut_next"] = (u.pa_next.fillna(0) > 0).astype(int)
u["target_year"] = u.season + 1

dr = pd.read_parquet(f"{PT}/data/raw/draft_history.parquet")
u = u.merge(dr[["mlbam_id", "draft_year", "overall_pick", "signing_bonus"]],
            on="mlbam_id", how="left")
u["drafted"] = u.draft_year.notna().astype(int)
u["years_since_draft"] = u.season - u.draft_year
u["log_bonus"] = np.log1p(u.signing_bonus)

tx = pd.read_parquet(f"{PT}/data/raw/transactions.parquet")
tx = tx[tx.mlbam_id.notna()].astype({"mlbam_id": int})
tx["date"] = pd.to_datetime(tx.date)
se = tx[tx.type_code == "SE"].groupby("mlbam_id").date.min().rename("first_se")
u = u.merge(se, on="mlbam_id", how="left")
u["selected_40man"] = (
    u.first_se <= pd.to_datetime(u.target_year.astype(str) + "-03-25")).astype(int)

PF = ["age", "sport", "pa", "pa_milb_t", "woba", "k_pct", "bb_pct", "iso",
      "overall_pick", "log_bonus", "drafted", "years_since_draft",
      "selected_40man"]

# ---------- org affiliation (primary org = most-PA team that season)
aff = pd.read_parquet(f"{EXP}/data/raw/minors_affiliation.parquet")
org = pd.read_parquet(f"{EXP}/data/raw/team_parent_org.parquet")
aff = aff.merge(org[["team_id", "season", "parent_org_id"]],
                on=["team_id", "season"], how="left")
aff = aff.dropna(subset=["parent_org_id", "pa"])
prim = (aff.sort_values("pa").groupby(["mlbam_id", "season"]).last()
           .reset_index()[["mlbam_id", "season", "parent_org_id"]])
u = u.merge(prim, on=["mlbam_id", "season"], how="left")
log(f"- universe: {len(u)} AA/AAA pre-debut seasons, "
    f"org attributed to {u.parent_org_id.notna().mean():.0%}")
u = u.dropna(subset=["parent_org_id"]).copy()
u["parent_org_id"] = u.parent_org_id.astype(int)

# ---------- 1. out-of-fold player-only debut probabilities (forward chaining)
u = u.sort_values("target_year").reset_index(drop=True)
u["p_hat"] = np.nan
years = sorted(u.target_year.unique())
for ty in years:
    tr = u[u.target_year < ty]
    if tr.debut_next.nunique() < 2 or len(tr) < 500:
        continue
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                                       random_state=7)
    m.fit(tr[PF], tr.debut_next)
    mask = u.target_year == ty
    u.loc[mask, "p_hat"] = m.predict_proba(u.loc[mask, PF])[:, 1]
ev = u.dropna(subset=["p_hat"]).copy()
ev["resid"] = ev.debut_next - ev.p_hat
log(f"- player-only OOF debut model on {len(ev)} seasons "
    f"(target years {ev.target_year.min()}-{ev.target_year.max()}); "
    f"AUC {roc_auc_score(ev.debut_next, ev.p_hat):.3f}")

# ---------- 2. org aggressiveness per season
oa = (ev.groupby(["parent_org_id", "target_year"])
        .agg(n=("resid", "size"), agg=("resid", "mean")).reset_index())
oa = oa[oa.n >= 5]
oa.to_parquet(f"{EXP}/data/processed/org_aggressiveness.parquet", index=False)

ORGN = org.dropna(subset=["parent_org_id"]).drop_duplicates("parent_org_id") \
          .set_index("parent_org_id").parent_org_name


def wmean_by(df, key, val, wt):
    g = df.assign(_w=df[val] * df[wt]).groupby(key)
    return (g._w.sum() / g[wt].sum())


career = wmean_by(oa, "parent_org_id", "agg", "n").rename("career_agg").to_frame()
career["name"] = career.index.map(ORGN)
log("\n## Org aggressiveness leaderboard (mean debut residual, all years)")
log("(+ = promotes prospects FASTER than talent predicts)")
top = career.sort_values("career_agg", ascending=False)
log("Most aggressive:")
for oid, r in top.head(6).iterrows():
    log(f"   {r['name']:24s} {r.career_agg:+.3f}")
log("Most conservative:")
for oid, r in top.tail(6).iterrows():
    log(f"   {r['name']:24s} {r.career_agg:+.3f}")

# ---------- 3. persistence
piv = oa.pivot(index="parent_org_id", columns="target_year", values="agg")
# AR(1): stack consecutive-year pairs
pairs_ar = []
for oid, row in piv.iterrows():
    for y in row.index[:-1]:
        if y + 1 in row.index and pd.notna(row[y]) and pd.notna(row[y + 1]):
            pairs_ar.append((row[y], row[y + 1]))
ar = pd.DataFrame(pairs_ar, columns=["t", "t1"])
log(f"\n## Persistence")
log(f"- year-over-year AR(1) of org aggressiveness: r = "
    f"{ar.t.corr(ar.t1):.3f} (n={len(ar)} org-year pairs)")
odd = ev[ev.target_year % 2 == 1].groupby("parent_org_id").resid.mean()
evn = ev[ev.target_year % 2 == 0].groupby("parent_org_id").resid.mean()
sh = pd.concat([odd.rename("odd"), evn.rename("evn")], axis=1).dropna()
log(f"- split-half (odd vs even seasons): r = {sh.odd.corr(sh.evn):.3f} "
    f"(n={len(sh)} orgs)")
# variance share: between-org vs total of org-season aggressiveness
gm = (oa["agg"] * oa.n).sum() / oa.n.sum()
org_mean = wmean_by(oa, "parent_org_id", "agg", "n")
org_n = oa.groupby("parent_org_id").n.sum()
between = ((org_mean - gm) ** 2 * org_n).sum() / oa.n.sum()
total = ((oa["agg"] - gm) ** 2 * oa.n).sum() / oa.n.sum()
log(f"- between-org variance share of org-season aggressiveness: "
    f"{between/total:.1%} (rest = year-to-year noise)")

# ---------- 4. OOS predictive value
log("\n## OOS predictive value — does PAST org behavior predict FUTURE debut?")
HOLD = [y for y in years if y >= 2019]
rows_oos = []
for ty in HOLD:
    tr = ev[ev.target_year < ty]
    te = ev[ev.target_year == ty]
    if len(te) < 50 or tr.debut_next.nunique() < 2:
        continue
    # trailing-3yr org aggressiveness from seasons strictly < ty
    prior = oa[(oa.target_year < ty) & (oa.target_year >= ty - 3)]
    trail = wmean_by(prior, "parent_org_id", "agg", "n").rename("org_trail")
    trX = tr.merge(trail, on="parent_org_id", how="left")
    teX = te.merge(trail, on="parent_org_id", how="left")
    trX["org_trail"] = trX.org_trail.fillna(0)
    teX["org_trail"] = teX.org_trail.fillna(0)
    base = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                                          random_state=7).fit(trX[PF], trX.debut_next)
    withorg = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                                             random_state=7).fit(
        trX[PF + ["org_trail"]], trX.debut_next)
    pb = base.predict_proba(teX[PF])[:, 1]
    pw = withorg.predict_proba(teX[PF + ["org_trail"]])[:, 1]
    rows_oos.append({"year": ty, "n": len(te),
                     "AUC_base": roc_auc_score(te.debut_next, pb),
                     "AUC_org": roc_auc_score(te.debut_next, pw),
                     "Brier_base": brier_score_loss(te.debut_next, pb),
                     "Brier_org": brier_score_loss(te.debut_next, pw)})
res = pd.DataFrame(rows_oos)
log(res.round(4).to_string(index=False))
log(f"\n  pooled AUC: base {res.AUC_base.mean():.4f} -> +org "
    f"{res.AUC_org.mean():.4f}  (Δ {res.AUC_org.mean()-res.AUC_base.mean():+.4f})")
log(f"  pooled Brier: base {res.Brier_base.mean():.4f} -> +org "
    f"{res.Brier_org.mean():.4f}  (Δ {res.Brier_org.mean()-res.Brier_base.mean():+.4f})")

log("\n## Verdict")
log("See AR(1)/split-half (is it stable?) + OOS Δ (does it predict?). "
    "Feature ships to Playing Time+ ONLY if OOS AUC/Brier improves.")

with open(f"{EXP}/research/E10_org_behavior.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
