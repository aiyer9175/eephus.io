# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Part 6 (quality) / Part 7 (scouting) — do scouting grades predict MLB defensive
QUALITY out-of-sample, over and above position + age?

Outcome = within-position MLB OAA (OAA z-scored within Pos-year, Inn-weighted mean per
player) — so we test whether scouts see *quality at the position*, which position alone
can't encode. Predictors = scouting field / throw / speed grades (earliest snapshot, to
keep it a genuine prospect-time prediction) + debut age. The prompt's bar: grades only
earn their place if they beat position+age OOS.
"""
import os, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import cross_val_score, KFold
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)

HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw"); REP = os.path.join(HOME, "defense_plus/reports")

# ---- MLB OAA quality outcome (within-position z), Inn-weighted per player ----
fr = []
for y in range(2016, 2026):
    f = os.path.join(RAW, f"fg_field_full_{y}.csv")
    if os.path.exists(f):
        d = pd.read_csv(f).rename(columns={"xMLBAMID": "id"})
        for c in ["id", "OAA", "Inn"]: d[c] = pd.to_numeric(d[c], errors="coerce")
        d["year"] = y; fr.append(d[["id", "Pos", "year", "OAA", "Inn"]])
F = pd.concat(fr); F = F[(F.Inn >= 300)].dropna(subset=["OAA", "id"])
F["oaa_z"] = F.groupby(["Pos", "year"])["OAA"].transform(lambda x: (x - x.mean()) / x.std())
F = F.dropna(subset=["oaa_z"])
q = F.groupby("id").apply(lambda g: np.average(g.oaa_z, weights=g.Inn)).rename("mlb_oaa_z").reset_index()
q["id"] = q["id"].astype(int)

# ---- scouting grades: earliest snapshot per player ----
g = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/grades_long.parquet"))
g = g.dropna(subset=["mlbam_id", "field"]).copy()
g["mlbam_id"] = pd.to_numeric(g["mlbam_id"], errors="coerce")
g = g.dropna(subset=["mlbam_id"]); g["mlbam_id"] = g["mlbam_id"].astype(int)
g = g.sort_values("snapshot_date").groupby("mlbam_id").first().reset_index()  # earliest grade
g = g[["mlbam_id", "position", "field", "throw", "speed", "fv"]].rename(columns={"mlbam_id": "id", "position": "scout_pos"})

# ---- debut age ----
u = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/usage_spine.parquet"))
first = u.groupby("mlbam_id")["season"].min().rename("first").reset_index()
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]]
first = first.merge(dm.rename(columns={"batter": "mlbam_id", "season": "first"}), on=["mlbam_id", "first"], how="left")
first = first.rename(columns={"mlbam_id": "id", "age": "debut_age"})[["id", "debut_age"]]

D = q.merge(g, on="id").merge(first, on="id", how="left").dropna(subset=["field", "throw", "speed", "debut_age"])
print(f"sample: {len(D)} players with scouting grades + MLB OAA quality + debut age\n")

# ---- raw correlations with within-position MLB quality ----
print("=== correlation of scouting grade with WITHIN-POSITION MLB OAA quality ===")
for gr in ["field", "throw", "speed", "fv"]:
    if gr in D.columns and D[gr].notna().sum() > 30:
        r = D[[gr, "mlb_oaa_z"]].dropna().corr().iloc[0, 1]
        print(f"  {gr:6} r = {r:+.3f}")

# ---- OOS incremental: does field/speed add over position+age? (5-fold CV R2) ----
print("\n=== OOS prediction of within-position MLB OAA (5-fold CV R^2) ===")
pos_d = pd.get_dummies(D["scout_pos"], prefix="p")
feat_sets = {
    "position only": pos_d,
    "+ debut age": pd.concat([pos_d, D[["debut_age"]]], axis=1),
    "+ FIELD grade": pd.concat([pos_d, D[["debut_age", "field"]]], axis=1),
    "+ field+speed+throw": pd.concat([pos_d, D[["debut_age", "field", "speed", "throw"]]], axis=1),
}
y = D["mlb_oaa_z"].values
kf = KFold(5, shuffle=True, random_state=0)
for name, X in feat_sets.items():
    r2 = cross_val_score(LinearRegression(), X.values.astype(float), y, cv=kf, scoring="r2").mean()
    print(f"  {name:22} CV R^2 = {r2:+.3f}")

# coefficient on field grade (per +10 grade points) in the full simple model
m = LinearRegression().fit(D[["field", "speed", "throw", "debut_age"]].values, y)
print(f"\n  field-grade coef: {m.coef_[0]*10:+.2f} OAA-z per +10 grade pts; "
      f"speed {m.coef_[1]*10:+.2f}; throw {m.coef_[2]*10:+.2f}")
D.to_csv(os.path.join(REP, "16_scouting_quality.csv"), index=False)
print(f"\nwrote reports/16_scouting_quality.csv")
