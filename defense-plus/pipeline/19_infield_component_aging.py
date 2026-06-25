# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ — infield component aging (the IF analog of the OF jump-component work).

Infield OAA decomposes directionally: infront (charging slow rollers = hands/transfer/
reactions), lateral toward 3b/1b (side-to-side RANGE = athleticism), behind. Plus arm
strength (mph) as a separate tool. We fit how each ages (joint-dropout) so Career+ can
age an IF by their value profile: a range-driven SS ages fast (athletic), a hands/arm
infielder ages slow — the IF version of burst-vs-reads.
"""
import os, sys, warnings
import numpy as np, pandas as pd, requests, time
from io import StringIO
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.expanduser("~/mlb-aging-curves")); import bayesian_curves as bc

HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw"); REP = os.path.join(HOME, "defense_plus/reports")
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
YEARS = list(range(2016, 2026))
DIR = {"in": "outs_above_average_infront", "lat3b": "outs_above_average_lateral_toward3bline",
       "lat1b": "outs_above_average_lateral_toward1bline", "behind": "outs_above_average_behind"}

# load infield directional OAA + FG innings (weight) + age
fr = []
for y in YEARS:
    d = pd.read_csv(os.path.join(RAW, f"if_oaa_dir_{y}.csv")); d["year"] = y; fr.append(d)
I = pd.concat(fr, ignore_index=True).rename(columns={"player_id": "id", "primary_pos_formatted": "Pos"})
for k, c in DIR.items(): I[k] = pd.to_numeric(I[c], errors="coerce")
I["OAA"] = pd.to_numeric(I["outs_above_average"], errors="coerce")
I["lateral"] = I["lat3b"] + I["lat1b"]
fg = []
for y in YEARS:
    f = os.path.join(RAW, f"fg_field_full_{y}.csv")
    if os.path.exists(f):
        d = pd.read_csv(f).rename(columns={"xMLBAMID": "id"}); d["year"] = y
        d["Inn"] = pd.to_numeric(d["Inn"], errors="coerce"); fg.append(d[["id", "Pos", "year", "Inn"]])
FG = pd.concat(fg)
I = I.merge(FG, on=["id", "Pos", "year"], how="left")
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]]
I = I.merge(dm.rename(columns={"batter": "id", "season": "year"}), on=["id", "year"], how="left")
I = I[I.Pos.isin(["SS", "2B", "3B"]) & (I.Inn >= 300)].dropna(subset=["age"])
for c in ["in", "lateral", "behind", "OAA"]:
    I[c + "z"] = I.groupby(["Pos", "year"])[c].transform(lambda x: (x - x.mean()) / x.std())

def fit(df, col):
    d = df.dropna(subset=[col + "z", "Inn", "age"]).rename(
        columns={"id": "player_id", "year": "Season", "age": "Age", col + "z": "skill", "Inn": "wt"})
    dp = bc.prepare(d, "skill", "wt", min_weight=300)
    res = bc.fit_joint_dropout(dp, "skill", "wt", draws=500, tune=600, chains=2, cores=2, random_seed=1)
    g = res["age_grid"]
    c27 = res["curve_mean"][int(np.argmin(np.abs(g - 27)))]
    c33 = res["curve_mean"][int(np.argmin(np.abs(g - 33)))]
    return round(c33 - c27, 2)

print("=== infield component aging (joint-dropout, 27->33 in SD vs peers) ===")
rows = []
for name, col in [("infront (hands/charge)", "in"), ("lateral (range/athletic)", "lateral"),
                  ("behind", "behind"), ("OAA total", "OAA")]:
    decl = fit(I, col)
    rows.append((name, decl)); print(f"  {name:26} 27->33 = {decl:+.2f} SD")

# ---- arm strength aging (separate tool, 2020-2025) ----
def arm_year(y):
    fp = os.path.join(RAW, f"arm_{y}.csv")
    if not os.path.exists(fp):
        url = f"https://baseballsavant.mlb.com/leaderboard/arm-strength?type=player&year={y}&minThrows=50&csv=true"
        pd.read_csv(StringIO(requests.get(url, headers=H, timeout=45).text)).to_csv(fp, index=False); time.sleep(0.3)
    return pd.read_csv(fp)
af = []
for y in range(2020, 2026):
    d = arm_year(y); d["year"] = y; af.append(d)
A = pd.concat(af, ignore_index=True).rename(columns={"player_id": "id"})
A = A[A.primary_position.isin([6, 4, 5])].copy()   # SS/2B/3B
A["arm"] = pd.to_numeric(A["arm_overall"], errors="coerce")
A = A.merge(dm.rename(columns={"batter": "id", "season": "year"}), on=["id", "year"], how="left").dropna(subset=["arm", "age"])
A["armz"] = A.groupby(["primary_position", "year"])["arm"].transform(lambda x: (x - x.mean()) / x.std())
A["wt"] = pd.to_numeric(A["total_throws"], errors="coerce").fillna(50)
ad = A.dropna(subset=["armz"]).rename(columns={"id": "player_id", "year": "Season", "age": "Age", "armz": "skill"})
dp = bc.prepare(ad, "skill", "wt", min_weight=50)
res = bc.fit_joint_dropout(dp, "skill", "wt", draws=500, tune=600, chains=2, cores=2, random_seed=1)
g = res["age_grid"]; arm_decl = round(res["curve_mean"][int(np.argmin(np.abs(g-33)))] - res["curve_mean"][int(np.argmin(np.abs(g-27)))], 2)
rows.append(("arm strength (mph tool)", arm_decl))
print(f"  {'arm strength (mph tool)':26} 27->33 = {arm_decl:+.2f} SD")

pd.DataFrame(rows, columns=["component", "decline_27_33_SD"]).to_csv(os.path.join(REP, "19_infield_component_aging.csv"), index=False)
print("\nRead: lateral (range/athletic) should age FAST; infront (hands) + arm SLOW -> IF aging multiplier.")
print(f"wrote reports/19_infield_component_aging.csv")
