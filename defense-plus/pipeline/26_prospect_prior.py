# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ #3 — assembled MiLB -> MLB Defense+ PROSPECT PRIOR.
Combines the three pure-defense signals into a per-prospect projection:
  - position history (Part 6: does he hold the position?)
  - scouting grades (Part 7: field/speed -> MLB range quality)
  - frame (Part 8: lighter -> more range; heavier -> slides down + ages faster)
Outputs, per prospect: projected MLB defensive QUALITY (OAA-z) + P(holds premium position).
Trained on graduated players (prospect-era inputs -> realized MLB defense), applied to current prospects.
"""
import os, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.model_selection import cross_val_score, KFold
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)
HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw"); REP = os.path.join(HOME, "defense_plus/reports")
PREM = ["C", "SS", "CF", "2B"]

# ---- inputs ----
g = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/grades_long.parquet"))
g["mlbam_id"] = pd.to_numeric(g["mlbam_id"], errors="coerce"); g = g.dropna(subset=["mlbam_id"]); g["mlbam_id"] = g["mlbam_id"].astype(int)
g_early = g.dropna(subset=["field"]).sort_values("snapshot_date").groupby("mlbam_id").first().reset_index()
g_late = g.dropna(subset=["field"]).sort_values("snapshot_date").groupby("mlbam_id").last().reset_index()
body = pd.read_parquet(os.path.join(RAW, "body.parquet")).rename(columns={"id": "mlbam_id"})

# MLB OAA quality outcome (within-position z, Inn-weighted) — graduated players
fr = []
for y in range(2016, 2026):
    f = os.path.join(RAW, f"fg_field_full_{y}.csv")
    if os.path.exists(f):
        d = pd.read_csv(f).rename(columns={"xMLBAMID": "id"})
        for c in ["id", "OAA", "Inn"]: d[c] = pd.to_numeric(d[c], errors="coerce")
        d["year"] = y; fr.append(d[["id", "Pos", "year", "OAA", "Inn"]])
F = pd.concat(fr); F = F[F.Inn >= 300].dropna(subset=["OAA"])
F["oaa_z"] = F.groupby(["Pos", "year"])["OAA"].transform(lambda x: (x - x.mean()) / x.std())
q = F.groupby("id").apply(lambda x: np.average(x.oaa_z, weights=x.Inn)).rename("mlb_oaa_z").reset_index().rename(columns={"id": "mlbam_id"})
mlbpos = F.groupby("id").apply(lambda x: x.groupby("Pos").Inn.sum().idxmax()).rename("mlb_pos").reset_index().rename(columns={"id": "mlbam_id"})

# ---- training set ----
tr = g_early[["mlbam_id", "position", "field", "throw", "speed", "fv"]].rename(columns={"position": "scout_pos"})
tr = tr.merge(body[["mlbam_id", "bmi", "height_in"]], on="mlbam_id").merge(q, on="mlbam_id").merge(mlbpos, on="mlbam_id")
tr = tr.dropna(subset=["field", "speed", "bmi", "mlb_oaa_z"])
print(f"training set: {len(tr)} graduated players (grades + frame + MLB OAA)\n")

# ---- QUALITY model: does frame ADD over grades? (Part7 + Part8 assembled) ----
print("=== projected MLB defensive QUALITY (OAA-z) — 5-fold CV R^2 ===")
y = tr["mlb_oaa_z"].values; kf = KFold(5, shuffle=True, random_state=0)
sets = {"field only (Part7)": tr[["field"]], "+ speed": tr[["field", "speed"]],
        "+ FRAME (bmi,ht)": tr[["field", "speed", "bmi", "height_in"]]}
for nm, X in sets.items():
    r2 = cross_val_score(LinearRegression(), X.values, y, cv=kf, scoring="r2").mean()
    print(f"  {nm:22} CV R^2 = {r2:+.3f}")
qmod = LinearRegression().fit(tr[["field", "speed", "bmi", "height_in"]].values, y)
print(f"  coefs: field {qmod.coef_[0]*10:+.2f}/10grade, speed {qmod.coef_[1]*10:+.2f}/10, bmi {qmod.coef_[2]:+.2f}/pt, ht {qmod.coef_[3]:+.2f}/in")

# ---- POSITION-HOLD model: P(holds premium scout position in MLB) ~ field + bmi + speed ----
trp = tr[tr.scout_pos.isin(PREM)].copy(); trp["held"] = (trp.mlb_pos == trp.scout_pos).astype(int)
hmod = LogisticRegression(max_iter=1000).fit(trp[["field", "speed", "bmi"]].values, trp["held"].values)
print(f"\n=== P(hold premium position) ~ field + speed + bmi (n={len(trp)}, hold rate {trp.held.mean():.0%}) ===")
print(f"  coefs: field {hmod.coef_[0][0]:+.2f}, speed {hmod.coef_[0][1]:+.2f}, bmi {hmod.coef_[0][2]:+.2f} (heavier -> lower hold)")

# ---- APPLY to current prospects (latest snapshot, premium pos, grades+frame, not established MLB) ----
u = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/usage_spine.parquet"))
career_gs = u.groupby("mlbam_id")["gs_total"].sum()
estab = set(career_gs[career_gs >= 150].index)   # established = 150+ career MLB starts (all positions)
cur = g_late[["mlbam_id", "player_name", "position", "field", "throw", "speed", "fv"]].rename(columns={"position": "scout_pos"})
cur = cur.merge(body[["mlbam_id", "bmi", "height_in"]], on="mlbam_id").dropna(subset=["field", "speed", "bmi"])
cur = cur[~cur.mlbam_id.isin(estab) & cur.scout_pos.isin(PREM) & cur.bmi.between(20, 34)]
cur["proj_oaa_z"] = qmod.predict(cur[["field", "speed", "bmi", "height_in"]].values)
# position-aware hold: Part-6 base rate by position + Part-8 frame penalty for SS/CF only
# (catchers stick ~regardless of frame; 2B is a landing spot — frame less relevant)
BASE_HOLD = {"C": 0.92, "SS": 0.57, "CF": 0.70, "2B": 0.56}
def hold(r):
    h = BASE_HOLD.get(r.scout_pos, 0.6)
    if r.scout_pos in ("SS", "CF"):
        h -= 0.022 * (r.bmi - 26)   # Part 8: ~ -0.11 per +5 BMI
    return float(np.clip(h, 0.1, 0.95))
cur["p_hold"] = cur.apply(hold, axis=1)
cur["defense_plus_prior"] = 100 + 10 * cur["proj_oaa_z"]   # 100±10 scale
out = cur.sort_values("defense_plus_prior", ascending=False)
out[["mlbam_id", "player_name", "scout_pos", "field", "speed", "bmi", "defense_plus_prior", "p_hold"]].to_csv(os.path.join(REP, "26_prospect_prior.csv"), index=False)
print(f"\n=== current premium-position prospects — top 12 by projected Defense+ ===")
print(out.head(12)[["player_name", "scout_pos", "field", "speed", "bmi", "defense_plus_prior", "p_hold"]].round(2).to_string(index=False))
print(f"\nwrote reports/26_prospect_prior.csv ({len(out)} prospects)")
