# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Part 8 — Frame / body type. Does height/weight/BMI predict defensive quality,
position retention/migration, and defensive aging? (Frame+ inputs.)
"""
import os, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)
HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw")
POS = ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "DH"]
body = pd.read_parquet(os.path.join(RAW, "body.parquet")).dropna(subset=["bmi", "weight", "height_in"])

# fielding (OAA) + primary pos + age
fr = []
for y in range(2016, 2026):
    f = os.path.join(RAW, f"fg_field_full_{y}.csv")
    if os.path.exists(f):
        d = pd.read_csv(f).rename(columns={"xMLBAMID": "id"})
        for c in ["id", "OAA", "Inn"]: d[c] = pd.to_numeric(d[c], errors="coerce")
        d["year"] = y; fr.append(d[["id", "Pos", "year", "OAA", "Inn"]])
F = pd.concat(fr).dropna(subset=["id", "OAA"])
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]]
F = F.merge(dm.rename(columns={"batter": "id", "season": "year"}), on=["id", "year"], how="left").merge(body, on="id", how="left")
Fq = F[(F.Inn >= 400) & F.bmi.notna()]

# ---- 1. body type by position ----
print("=== 1. frame by position (full-time, mean) ===")
prim = Fq.loc[Fq.groupby(["id", "year"])["Inn"].idxmax()]
t = prim.groupby("Pos").agg(ht=("height_in", "mean"), wt=("weight", "mean"), bmi=("bmi", "mean"), n=("id", "size")).reindex(POS).dropna()
for p, r in t.iterrows():
    print(f"  {p:3} {r.ht//12:.0f}'{r.ht%12:.0f}\"  {r.wt:.0f} lb  BMI {r.bmi:.1f}  (n={int(r.n)})")

# ---- 2. body -> within-position OAA quality ----
print("\n=== 2. does frame predict defensive QUALITY (OAA) within position? ===")
for p in ["SS", "CF", "2B", "3B"]:
    g = Fq[Fq.Pos == p].copy()
    g["oaa_z"] = (g.OAA - g.OAA.mean()) / g.OAA.std()
    print(f"  {p}: corr(BMI,OAA)={g.bmi.corr(g.OAA):+.2f}  corr(weight,OAA)={g.weight.corr(g.OAA):+.2f}  corr(height,OAA)={g.height_in.corr(g.OAA):+.2f}")
print("  (negative = leaner/lighter players have more range)")

# ---- 3. body -> migration off premium positions ----
print("\n=== 3. does frame predict sliding OFF a premium position? ===")
u = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/usage_spine.parquet"))
for p in POS:
    if f"gs_{p.lower()}" not in u.columns: u[f"gs_{p.lower()}"] = 0
gs = [f"gs_{p.lower()}" for p in POS]
u["primary"] = u[gs].idxmax(axis=1).str.replace("gs_", "").str.upper()
u = u[u[gs].max(axis=1) >= 20]
nx = u[["mlbam_id", "season", "primary"]].rename(columns={"season": "s1", "primary": "pos1"}); nx["season"] = nx["s1"] - 1
T = u[["mlbam_id", "season", "primary"]].merge(nx[["mlbam_id", "season", "pos1"]], on=["mlbam_id", "season"], how="left")
T = T[T.season <= 2024].merge(dm.rename(columns={"batter": "mlbam_id"}), on=["mlbam_id", "season"], how="left")
T = T.merge(body.rename(columns={"id": "mlbam_id"}), on="mlbam_id", how="left").dropna(subset=["bmi", "age"])
for p in ["SS", "CF", "2B"]:
    g = T[(T.primary == p) & (T.pos1.notna()) & (T.pos1 != "EXIT")].copy()
    g["moved"] = (g.pos1 != p).astype(int)
    m = LogisticRegression(max_iter=1000).fit(g[["age", "bmi"]].assign(age=g.age - 28).values, g.moved.values)
    # P(move) at BMI 25 vs 30 (age 28)
    p25 = m.predict_proba([[0, 25]])[0, 1]; p30 = m.predict_proba([[0, 30]])[0, 1]
    print(f"  {p}: P(move off) lean BMI25 {p25*100:.0f}% -> heavy BMI30 {p30*100:.0f}%  (bmi coef {m.coef_[0][1]:+.2f}, n={len(g)})")

# ---- 4. body -> defensive aging (heavier age faster?) ----
print("\n=== 4. does frame predict faster defensive AGING (within-player ΔOAA)? ===")
F2 = F[(F.Inn >= 300) & F.bmi.notna()].sort_values(["id", "year"])
pr = []
for pid, gg in F2.groupby("id"):
    gg = gg.sort_values("year")
    for i in range(1, len(gg)):
        a, b = gg.iloc[i-1], gg.iloc[i]
        if a.Pos == b.Pos and b.year - a.year == 1:
            pr.append((a.age, a.bmi, b.OAA - a.OAA))
P = pd.DataFrame(pr, columns=["age", "bmi", "dOAA"]).dropna()
P["age_c"] = P.age - 28
m = LinearRegression().fit(P[["age_c", "bmi", "age_c"]].assign(axb=P.age_c * (P.bmi - 27))[["age_c", "bmi", "axb"]].values, P.dOAA)
print(f"  ΔOAA ~ age + BMI + age×BMI:  age×BMI coef = {m.coef_[2]:+.3f}  (negative = heavy players decline faster with age)")
hi = P[(P.bmi >= 29) & (P.age >= 30)]; lo = P[(P.bmi <= 26) & (P.age >= 30)]
print(f"  at age 30+: heavy(BMI>=29) mean ΔOAA {hi.dOAA.mean():+.2f} vs lean(BMI<=26) {lo.dOAA.mean():+.2f}")
print(f"\nwrote nothing persistent; body cached at data/raw/body.parquet")
