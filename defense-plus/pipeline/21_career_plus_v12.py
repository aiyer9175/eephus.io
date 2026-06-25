# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Career+ v1.2 — wire in the three new findings on top of v1.1:
  (a) INFIELD aging multiplier (module 19): hands(infront)-driven IF age slow, range/arm fast.
  (b) TALENT TRANSFER on down-spectrum migration (+~2.5 runs position-relative; range plays up).
  (c) VERSATILITY optionality: 4+ position players get a small premium-coverage upside.
Reuses v1.1's quality-conditioned migration + OF component aging.
"""
import os, sys, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)
rng = np.random.default_rng(7)
HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw"); REP = os.path.join(HOME, "defense_plus/reports")
POSADJ = {"C": 12.5, "SS": 7.5, "2B": 2.5, "3B": 2.5, "CF": 2.5, "LF": -7.5, "RF": -7.5, "1B": -12.5, "DH": -17.5}
SLOPE = {"C": 0.80, "CF": 0.73, "SS": 0.62, "RF": 0.37, "2B": 0.37, "3B": 0.23, "LF": 0.15, "1B": -0.07, "DH": 0.0}
MIG = {"SS": "2B", "2B": "3B", "3B": "1B", "CF": "LF", "RF": "LF", "LF": "1B", "C": "1B", "1B": "DH", "DH": "DH"}
EXIT_AGE = {22: .10, 23: .10, 24: .13, 25: .08, 26: .12, 27: .11, 28: .10, 29: .08, 30: .09, 31: .11, 32: .11, 33: .17, 34: .19, 35: .18, 36: .28, 37: .25, 38: .22, 39: .30, 40: .35}
CAGE = {"reaction": -0.060, "burst": -0.121, "route": +0.064}; AVG_JUMP = -0.095
IFAGE = {"in": -0.13 / 6, "lateral": -0.18 / 6, "behind": -0.28 / 6}; AVG_IF = -0.26 / 6
PT = 0.85; TRANSFER = 2.5
def exit_haz(a): a = int(round(a)); return EXIT_AGE.get(a, 0.10 if a < 22 else 0.50)

# --- retention (quality-conditioned), OAA (DRS for C) ---
u = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/usage_spine.parquet"))
POS = list(POSADJ)
for p in POS:
    if f"gs_{p.lower()}" not in u.columns: u[f"gs_{p.lower()}"] = 0
gs = [f"gs_{p.lower()}" for p in POS]
u["primary"] = u[gs].idxmax(axis=1).str.replace("gs_", "").str.upper()
u2 = u[u[gs].max(axis=1) >= 20]
sp = u2[["mlbam_id", "season", "primary"]]
nx = sp.rename(columns={"season": "s1", "primary": "pos1"}); nx["season"] = nx["s1"] - 1
T = sp.merge(nx[["mlbam_id", "season", "pos1"]], on=["mlbam_id", "season"], how="left")
T = T[T.season <= 2024]; T["pos1"] = T["pos1"].fillna("EXIT")
fr = []
for y in range(2016, 2026):
    f = os.path.join(RAW, f"fg_field_full_{y}.csv")
    if os.path.exists(f):
        d = pd.read_csv(f).rename(columns={"xMLBAMID": "id"})
        for c in ["id", "OAA", "DRS", "Inn"]: d[c] = pd.to_numeric(d[c], errors="coerce")
        d["year"] = y; fr.append(d[["id", "Pos", "year", "OAA", "DRS", "Inn"]])
F = pd.concat(fr); F = F[F.Inn >= 300]
F["qual"] = np.where(F.Pos == "C", F.DRS, F.OAA); F = F.dropna(subset=["qual"])
F["oaa_z"] = F.groupby(["Pos", "year"])["qual"].transform(lambda x: (x - x.mean()) / x.std())
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]]
RET = {}
for pos in POS:
    d = T[T.primary == pos].merge(F[F.Pos == pos].rename(columns={"id": "mlbam_id", "year": "season"}), on=["mlbam_id", "season"], how="inner")
    d = d.merge(dm.rename(columns={"batter": "mlbam_id"}), on=["mlbam_id", "season"], how="left").dropna(subset=["oaa_z", "age"])
    d["stay"] = (d.pos1 == pos).astype(int)
    if d.stay.nunique() < 2 or len(d) < 40: RET[pos] = (1.6, -0.05, 0.3); continue
    m = LogisticRegression(max_iter=2000).fit(d.assign(a=d.age - 28)[["a", "oaa_z"]].values, d.stay.values)
    RET[pos] = (float(m.intercept_[0]), float(m.coef_[0][0]), float(m.coef_[0][1]))
def p_stay(pos, age, z):
    b0, ba, bo = RET.get(pos, (0.5, -0.05, 0.3)); return 1 / (1 + np.exp(-(b0 + ba * (age - 28) + bo * z)))
pos_sd = F.groupby("Pos")["qual"].std().to_dict()

# --- OF jump multiplier + IF directional multiplier + versatility ---
J = pd.concat([pd.read_csv(os.path.join(RAW, f"ofjump_{y}.csv")).rename(columns={"resp_fielder_id": "id"}) for y in [2023, 2024, 2025]])
for k, c in {"reaction": "rel_league_reaction_distance", "burst": "rel_league_burst_distance", "route": "rel_league_routing_distance"}.items():
    J[k] = pd.to_numeric(J[c], errors="coerce")
ofp = J.groupby("id")[["reaction", "burst", "route"]].mean()
IF = pd.concat([pd.read_csv(os.path.join(RAW, f"if_oaa_dir_{y}.csv")).rename(columns={"player_id": "id"}) for y in [2023, 2024, 2025]])
IF["in"] = pd.to_numeric(IF["outs_above_average_infront"], errors="coerce")
IF["lateral"] = pd.to_numeric(IF["outs_above_average_lateral_toward3bline"], errors="coerce") + pd.to_numeric(IF["outs_above_average_lateral_toward1bline"], errors="coerce")
IF["behind"] = pd.to_numeric(IF["outs_above_average_behind"], errors="coerce")
ifp = IF.groupby("id")[["in", "lateral", "behind"]].mean()
def of_mult(pid):
    if pid not in ofp.index: return 1.0
    w = {k: max(ofp.loc[pid, k], 0) for k in CAGE}; s = sum(w.values())
    return float(np.clip(sum(w[k] * CAGE[k] for k in CAGE) / s / AVG_JUMP, 0.2, 1.6)) if s > 0 else 1.0
def if_mult(pid):
    if pid not in ifp.index: return 1.0
    w = {k: max(ifp.loc[pid, k], 0) for k in IFAGE}; s = sum(w.values())
    return float(np.clip(sum(w[k] * IFAGE[k] for k in IFAGE) / s / AVG_IF, 0.4, 1.3)) if s > 0 else 1.0
vers = pd.read_csv(os.path.join(REP, "20_team_needs.csv")).set_index("mlbam_id")["versatility"].to_dict()

def sim(pos0, age0, tal0, sd0, pid, M=2000):
    omult = of_mult(pid) if pos0 in ("CF", "LF", "RF") else (if_mult(pid) if pos0 in ("SS", "2B", "3B") else 1.0)
    v = vers.get(pid, 2); opt = 1.5 if v >= 5 else (0.7 if v >= 4 else 0.0)   # versatility optionality (runs/yr)
    runs = np.empty(M)
    for m in range(M):
        pos, age, tal = pos0, age0, rng.normal(tal0, max(sd0, 0.1)); tot = 0.0
        while age <= 41:
            if rng.random() < exit_haz(age): break
            tot += (tal + POSADJ[pos]) * PT + opt
            age += 1
            tal -= SLOPE[pos] * (omult if pos in ("CF", "LF", "RF", "SS", "2B", "3B") else 1.0)
            z = tal / pos_sd.get(pos, 6.0)
            if rng.random() > p_stay(pos, age, z) and rng.random() < (1 - exit_haz(age)):
                newpos = MIG[pos]
                if POSADJ[newpos] < POSADJ[pos]: tal += TRANSFER   # range plays up at easier pos
                pos = newpos
        runs[m] = tot
    return runs, omult

b = pd.read_csv(os.path.join(REP, "06_defense_plus_2025.csv"))
b = b.merge(dm[dm.season == 2025][["batter", "age"]].rename(columns={"batter": "id"}), on="id", how="left").dropna(subset=["age", "dplus_runs", "Pos"])
rows = []
for _, r in b.iterrows():
    runs, mult = sim(r["Pos"], float(r["age"]), float(r["dplus_runs"]), float(r.get("sd_runs", 3.0)), int(r["id"]))
    rows.append(dict(name=r["PlayerName"], pos=r["Pos"], age=round(r["age"]), career_runs=round(runs.mean()),
                     p10=round(np.percentile(runs, 10)), p90=round(np.percentile(runs, 90)), dWAR=round(runs.mean() / 10, 1), mult=round(mult, 2)))
C = pd.DataFrame(rows).sort_values("career_runs", ascending=False)
C.to_csv(os.path.join(REP, "21_career_plus_v12.csv"), index=False)
print("=== Career+ v1.2 — top 12 ===")
print(C.head(12)[["name", "pos", "age", "career_runs", "p10", "p90", "dWAR"]].to_string(index=False))
v11 = pd.read_csv(os.path.join(REP, "18_career_plus_v11.csv")).set_index("name")["career_runs"]
print("\n=== v1.1 -> v1.2 (PCA + comparators) ===")
for nm in ["Pete Crow-Armstrong", "Bobby Witt Jr.", "Ceddanne Rafaela", "Ke'Bryan Hayes", "Masyn Winn", "Nico Hoerner"]:
    n = C[C.name == nm]
    if len(n):
        n = n.iloc[0]; o = v11.get(nm, np.nan)
        print(f"  {nm:22} {n['pos']} v{vers.get(int(b[b.PlayerName==nm].id.iloc[0]),2)}pos: v1.1 {o:.0f} -> v1.2 {n['career_runs']:.0f} ({n['dWAR']} dWAR) mult={n['mult']}")
print(f"\nwrote reports/21_career_plus_v12.csv")
