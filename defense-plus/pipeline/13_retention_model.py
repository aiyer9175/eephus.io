# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Part 5 — position-retention model: what predicts STAYING at a premium position?

For SS / CF (premium, OAA-covered), model P(stay next year) ~ age + defensive quality
(OAA) + arm strength. Does being a *good* defender buy you the position, net of age?
Joint with the migration matrices (Module 12). Logistic + bootstrap.
"""
import os, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)

HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw"); REP = os.path.join(HOME, "defense_plus/reports")
YEARS = list(range(2016, 2026))
POS = ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "DH"]

# primary position + survival from usage_spine
u = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/usage_spine.parquet"))
for p in POS:
    if f"gs_{p.lower()}" not in u.columns: u[f"gs_{p.lower()}"] = 0
gs = [f"gs_{p.lower()}" for p in POS]
u["primary"] = u[gs].idxmax(axis=1).str.replace("gs_", "").str.upper()
u = u[u[gs].max(axis=1) >= 20]
sp = u[["mlbam_id", "season", "primary"]].copy()
nxt = sp.rename(columns={"season": "s1", "primary": "pos1"}); nxt["season"] = nxt["s1"] - 1
T = sp.merge(nxt[["mlbam_id", "season", "pos1"]], on=["mlbam_id", "season"], how="left")
T = T[(T.season <= 2024)].copy(); T["pos1"] = T["pos1"].fillna("EXIT")

# OAA + age
fr = []
for y in YEARS:
    d = pd.read_csv(os.path.join(RAW, f"fg_field_full_{y}.csv")).rename(columns={"xMLBAMID": "id"})
    d["year"] = y; fr.append(d[["id", "Pos", "year", "OAA", "Inn"]])
F = pd.concat(fr, ignore_index=True)
for c in ["id", "OAA", "Inn"]: F[c] = pd.to_numeric(F[c], errors="coerce")
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]]

def model_pos(pos):
    d = T[T.primary == pos].merge(
        F[(F.Pos == pos)].rename(columns={"id": "mlbam_id", "year": "season"}),
        on=["mlbam_id", "season"], how="inner")
    d = d.merge(dm.rename(columns={"batter": "mlbam_id"}), on=["mlbam_id", "season"], how="left")
    d = d[(d.Inn >= 300)].dropna(subset=["OAA", "age"]).copy()
    d["stay"] = (d.pos1 == pos).astype(int)            # stay at this position (vs move OR exit)
    d["oaa_z"] = (d.OAA - d.OAA.mean()) / d.OAA.std()
    d["age_c"] = d.age - 28
    X = d[["age_c", "oaa_z"]].values; y = d["stay"].values
    m = LogisticRegression(max_iter=2000).fit(X, y)
    b_age, b_oaa = m.coef_[0]
    # marginal effect: P(stay) at avg-age for a -1SD vs +1SD defender
    base = np.array([[0, 0]])
    p_lo = m.predict_proba(np.array([[0, -1]]))[0, 1]
    p_hi = m.predict_proba(np.array([[0, +1]]))[0, 1]
    p_young = m.predict_proba(np.array([[-4, 0]]))[0, 1]   # age 24
    p_old = m.predict_proba(np.array([[+4, 0]]))[0, 1]     # age 32
    return dict(pos=pos, n=len(d), base_stay=round(y.mean(), 2),
                b_age=round(b_age, 3), b_oaa=round(b_oaa, 3),
                stay_badD=round(p_lo, 2), stay_goodD=round(p_hi, 2),
                stay_age24=round(p_young, 2), stay_age32=round(p_old, 2))

print("=== position RETENTION model: P(stay) ~ age + OAA (Inn>=300, 2016-24) ===")
print("  b_oaa>0: better defenders stay; b_age<0: older players leave\n")
rows = [model_pos(p) for p in ["SS", "CF", "2B", "3B"]]
R = pd.DataFrame(rows)
print(R.to_string(index=False))
print("\nReadout (holding the other fixed):")
for r in rows:
    print(f"  {r['pos']}: bad glove(-1SD) stay {r['stay_badD']:.0%} -> good glove(+1SD) {r['stay_goodD']:.0%} | "
          f"age24 {r['stay_age24']:.0%} -> age32 {r['stay_age32']:.0%}")
R.to_csv(os.path.join(REP, "13_retention_model.csv"), index=False)
print(f"\nwrote reports/13_retention_model.csv")
