# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Part 11 / Module A — Career survivorship by position.

Question (no identification problem — purely descriptive & directly actionable):
what offensive level keeps a player in MLB, and does it differ by position?
I.e. the POSITION-SPECIFIC OFFENSIVE REPLACEMENT LEVEL. Hypothesis: SS/CF/C survive
at materially lower offensive thresholds than 1B/LF/RF — defense as career insurance.

Spine : playing_time_model usage_spine (position via gs_*, PA, survival) 2000-2026
Offense: projection_engine deep_mlb (wOBA), era-adjusted to a wRC+-like wOBA+ scale
Model  : logistic survive(t->t+1) ~ wOBA+ + position + age + log(PA); threshold =
         wOBA+ where P(survive)=0.5 per position, at reference age/PA. Bootstrap CIs.
CAVEAT : defense is NOT controlled here, so the threshold is the *population-average*
         offensive bar given typical defense at that position (exactly the actionable
         'replacement level'); a low-offense SS who survives is likely an elite glove.
"""
import os, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)

HOME = os.path.expanduser("~")
REP = os.path.join(HOME, "defense_plus/reports")
POS = ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "DH"]
PREMIUM = ["C", "SS", "CF", "2B"]          # up-the-middle / premium defense
BAT = ["1B", "LF", "RF", "DH"]             # bat-first

# ---------- spine: position + PA + survival ----------
u = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/usage_spine.parquet"))
gs = {p: f"gs_{p.lower()}" for p in POS}
for p, c in gs.items():
    if c not in u.columns: u[c] = 0
u["primary_pos"] = u[[gs[p] for p in POS]].idxmax(axis=1).str.replace("gs_", "").str.upper()
u["gs_pos"] = u[[gs[p] for p in POS]].max(axis=1)
u = u[(u["gs_pos"] >= 10)]                  # at least a part-time fielder/DH this year
spine = u[["mlbam_id", "season", "pa", "primary_pos"]].copy()

# survival = >=50 PA in MLB next season
nxt = spine[["mlbam_id", "season", "pa"]].rename(columns={"season": "s1", "pa": "pa1"})
nxt["season"] = nxt["s1"] - 1
spine = spine.merge(nxt[["mlbam_id", "season", "pa1"]], on=["mlbam_id", "season"], how="left")
spine["survive"] = (spine["pa1"].fillna(0) >= 50).astype(int)

# ---------- offense: wOBA -> era-adjusted wOBA+ ----------
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))
dm = dm.rename(columns={"batter": "mlbam_id"})[["mlbam_id", "season", "woba", "age", "pa"]]
lg = dm.assign(w=dm.woba * dm.pa).groupby("season").apply(
    lambda g: g.w.sum() / g.pa.sum()).rename("lg_woba").reset_index()
dm = dm.merge(lg, on="season")
dm["woba_plus"] = 100 * dm["woba"] / dm["lg_woba"]
spine = spine.merge(dm[["mlbam_id", "season", "woba_plus", "age"]], on=["mlbam_id", "season"], how="inner")

# ---------- sample: position players, PA>=200, observed t+1 (t<=2024) ----------
df = spine[(spine.pa >= 200) & (spine.season <= 2024) & spine.primary_pos.isin(POS)].dropna(
    subset=["woba_plus", "age"]).copy()
df["logpa"] = np.log(df["pa"])
print(f"sample: {len(df)} player-seasons (2000-2024, PA>=200), survival rate={df.survive.mean():.3f}\n")

# ---------- model-free: survival rate by position x wOBA+ band ----------
df["wband"] = pd.cut(df.woba_plus, [0, 85, 95, 105, 115, 200],
                     labels=["<85", "85-95", "95-105", "105-115", "115+"])
tab = df.pivot_table(index="primary_pos", columns="wband", values="survive", aggfunc="mean").reindex(POS)
print("=== survival rate (>=50 PA next yr) by position x wOBA+ band (model-free) ===")
print((tab * 100).round(0).astype("Int64").to_string())

# ---------- logistic: threshold wOBA+ where P(survive)=0.5 ----------
TARGET = 0.80   # "likely to stick" survival prob; P=0.5 lands in extrapolated left tail
def fit_thresholds(d, ref_age=28.0, ref_logpa=None, target=TARGET):
    ref_logpa = ref_logpa if ref_logpa is not None else np.log(450)
    logit_t = np.log(target / (1 - target))
    X = pd.get_dummies(d["primary_pos"], prefix="p")
    X["woba_plus"] = d.woba_plus.values; X["age"] = d.age.values; X["logpa"] = d.logpa.values
    m = LogisticRegression(max_iter=2000, C=1e6)
    m.fit(X.values, d.survive.values)
    coef = dict(zip(list(X.columns), m.coef_[0])); b0 = m.intercept_[0]
    bw = coef["woba_plus"]
    thr = {}
    for p in POS:
        pc = f"p_{p}"
        if pc not in coef: continue
        # b0 + coef[pos] + bw*woba + bage*age + blogpa*logpa = logit(target) -> solve woba
        lin = b0 + coef[pc] + coef["age"] * ref_age + coef["logpa"] * ref_logpa
        thr[p] = (logit_t - lin) / bw
    return thr, m, X, bw

thr, model, Xall, bw = fit_thresholds(df)
# bootstrap CIs
rng = np.random.default_rng(0); boot = {p: [] for p in POS}
for _ in range(300):
    s = df.sample(len(df), replace=True, random_state=rng.integers(1e9))
    try:
        t, *_ = fit_thresholds(s)
        for p in POS:
            if p in t: boot[p].append(t[p])
    except Exception: pass
rows = []
for p in POS:
    if p not in thr: continue
    lo, hi = np.percentile(boot[p], [16, 84]) if boot[p] else (np.nan, np.nan)
    rows.append(dict(pos=p, threshold_wobaplus=round(thr[p], 1),
                     ci68=f"[{lo:.0f},{hi:.0f}]", n=int((df.primary_pos == p).sum())))
T = pd.DataFrame(rows).sort_values("threshold_wobaplus")
T.to_csv(os.path.join(REP, "11a_survival_thresholds.csv"), index=False)

# OOS validation
tr = df[df.season <= 2016]; te = df[df.season >= 2017]
_, m2, Xtr, _ = fit_thresholds(tr)
Xte = pd.get_dummies(te["primary_pos"], prefix="p").reindex(columns=[c for c in Xtr.columns if c.startswith("p_")], fill_value=0)
Xte["woba_plus"] = te.woba_plus.values; Xte["age"] = te.age.values; Xte["logpa"] = te.logpa.values
auc = roc_auc_score(te.survive.values, m2.predict_proba(Xte.values)[:, 1])

print(f"\n=== POSITION-SPECIFIC OFFENSIVE SURVIVAL THRESHOLD (wOBA+ for {int(TARGET*100)}% survival, age 28, ~450 PA) ===")
print("  lower = stays in MLB on less offense = more defensive 'career insurance'")
print(T.to_string(index=False))
prem = np.mean([thr[p] for p in PREMIUM if p in thr])
bat = np.mean([thr[p] for p in BAT if p in thr])
print(f"\npremium-defense (C/SS/CF/2B) mean threshold = {prem:.0f} wOBA+")
print(f"bat-first      (1B/LF/RF/DH) mean threshold = {bat:.0f} wOBA+")
print(f"--> defensive offensive DISCOUNT = {bat-prem:.0f} wOBA+ points")
print(f"\nOOS AUC (train<=2016, test>=2017): {auc:.3f}   (wOBA+ slope per logit: {bw:.3f})")
print(f"\nwrote {os.path.join(REP,'11a_survival_thresholds.csv')}")
