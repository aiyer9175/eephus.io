# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Career+ v1.1 — two refinements prompted by the PCA/CF review:

(1) QUALITY-CONDITIONED MIGRATION. v1 used a flat position move-rate. But Part 5's
    retention model shows defensive quality strongly governs staying (CF: bad glove 38%
    -> good glove 77%). So elite CF (Kiermaier/Taylor/JBJ) almost never move. We now draw
    P(stay) each year from the per-position retention logistic, conditioned on the player's
    current OAA-z; migration = 1 - P(stay) - P(exit).

(2) COMPONENT-PROFILE OF AGING. v1 aged every CF at the position-average (-0.73 runs/yr).
    But Part 4: burst (athletic) ages fast, reaction/route (cognitive) hold/improve. So we
    scale each OF's aging slope by their jump-component value profile. A burst-driven CF
    (PCA: 98-99th pct burst) ages at ~the athletic rate (no bonus); a reads/routes CF ages
    much slower. Non-OF / no-jump players keep the position-average slope.
"""
import os, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)
rng = np.random.default_rng(7)

HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw"); REP = os.path.join(HOME, "defense_plus/reports")
POSADJ = {"C": 12.5, "SS": 7.5, "2B": 2.5, "3B": 2.5, "CF": 2.5, "LF": -7.5, "RF": -7.5, "1B": -12.5, "DH": -17.5}
SLOPE = {"C": 0.80, "CF": 0.73, "SS": 0.62, "RF": 0.37, "2B": 0.37, "3B": 0.23, "LF": 0.15, "1B": -0.07, "DH": 0.0}
MIG = {"SS": "2B", "2B": "3B", "3B": "1B", "CF": "LF", "RF": "LF", "LF": "1B", "C": "1B", "1B": "DH", "DH": "DH"}
EXIT_AGE = {22: .10, 23: .10, 24: .13, 25: .08, 26: .12, 27: .11, 28: .10, 29: .08, 30: .09,
            31: .11, 32: .11, 33: .17, 34: .19, 35: .18, 36: .28, 37: .25, 38: .22, 39: .30, 40: .35}
CAGE = {"reaction": -0.060, "burst": -0.121, "route": +0.064}   # Part 4 SD/yr
AVG_JUMP_RATE = -0.095
PT = 0.85
def exit_haz(a): a = int(round(a)); return EXIT_AGE.get(a, 0.10 if a < 22 else 0.50)

# ---- (1) fit per-position retention logistic: P(stay) ~ age_c + oaa_z ----
u = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/usage_spine.parquet"))
POS = list(POSADJ)
for p in POS:
    if f"gs_{p.lower()}" not in u.columns: u[f"gs_{p.lower()}"] = 0
gs = [f"gs_{p.lower()}" for p in POS]
u["primary"] = u[gs].idxmax(axis=1).str.replace("gs_", "").str.upper()
u = u[u[gs].max(axis=1) >= 20]
sp = u[["mlbam_id", "season", "primary"]]
nx = sp.rename(columns={"season": "s1", "primary": "pos1"}); nx["season"] = nx["s1"] - 1
T = sp.merge(nx[["mlbam_id", "season", "pos1"]], on=["mlbam_id", "season"], how="left")
T = T[T.season <= 2024]; T["pos1"] = T["pos1"].fillna("EXIT")
fr = []
for y in range(2016, 2026):
    f = os.path.join(RAW, f"fg_field_full_{y}.csv")
    if os.path.exists(f):
        d = pd.read_csv(f).rename(columns={"xMLBAMID": "id"})
        for c in ["id", "OAA", "Inn"]: d[c] = pd.to_numeric(d[c], errors="coerce")
        d["year"] = y
        for c in ["DRS"]: d[c] = pd.to_numeric(d[c], errors="coerce")
        fr.append(d[["id", "Pos", "year", "OAA", "DRS", "Inn"]])
F = pd.concat(fr); F = F[F.Inn >= 300]
# catchers have no OAA -> use DRS as their quality metric; everyone else OAA
F["qual"] = np.where(F.Pos == "C", F["DRS"], F["OAA"])
F = F.dropna(subset=["qual"])
F["oaa_z"] = F.groupby(["Pos", "year"])["qual"].transform(lambda x: (x - x.mean()) / x.std())
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]]
RET = {}
for pos in POS:
    d = T[T.primary == pos].merge(F[F.Pos == pos].rename(columns={"id": "mlbam_id", "year": "season"}),
                                  on=["mlbam_id", "season"], how="inner")
    d = d.merge(dm.rename(columns={"batter": "mlbam_id"}), on=["mlbam_id", "season"], how="left").dropna(subset=["oaa_z", "age"])
    d["stay"] = (d.pos1 == pos).astype(int)
    if d.stay.nunique() < 2 or len(d) < 40:
        RET[pos] = (1.6, -0.05, 0.3); continue   # sticky fallback (DH only)
    m = LogisticRegression(max_iter=2000).fit(d[["age", "oaa_z"]].assign(age=d.age - 28)[["age", "oaa_z"]].values, d.stay.values)
    RET[pos] = (float(m.intercept_[0]), float(m.coef_[0][0]), float(m.coef_[0][1]))
def p_stay(pos, age, oaa_z):
    b0, ba, bo = RET.get(pos, (0.5, -0.05, 0.3))
    z = b0 + ba * (age - 28) + bo * oaa_z
    return 1 / (1 + np.exp(-z))
pos_sd = F.groupby("Pos")["qual"].std().to_dict()   # for runs<->z (C uses DRS sd)

# ---- (2) component-profile OF aging multiplier ----
jf = []
for y in [2023, 2024, 2025]:
    d = pd.read_csv(os.path.join(RAW, f"ofjump_{y}.csv")).rename(columns={"resp_fielder_id": "id"})
    jf.append(d)
J = pd.concat(jf)
JC = {"reaction": "rel_league_reaction_distance", "burst": "rel_league_burst_distance", "route": "rel_league_routing_distance"}
for k, c in JC.items(): J[k] = pd.to_numeric(J[c], errors="coerce")
prof = J.groupby("id")[["reaction", "burst", "route"]].mean()
def of_aging_mult(pid):
    if pid not in prof.index: return 1.0
    w = {k: max(prof.loc[pid, k], 0) for k in JC}     # only components they're above-avg in drive value
    s = sum(w.values())
    if s <= 0: return 1.0
    rate = sum(w[k] * CAGE[k] for k in JC) / s
    return float(np.clip(rate / AVG_JUMP_RATE, 0.2, 1.6))

# ---- Career+ sim with both refinements ----
def sim(pos0, age0, talent0, sd0, pid, M=2000):
    of_mult = of_aging_mult(pid) if pos0 in ("CF", "LF", "RF") else 1.0
    runs = np.empty(M)
    for m in range(M):
        pos, age, tal = pos0, age0, rng.normal(talent0, max(sd0, 0.1)); tot = 0.0
        while age <= 41:
            if rng.random() < exit_haz(age): break
            tot += (tal + POSADJ[pos]) * PT
            age += 1
            slope = SLOPE[pos] * (of_mult if pos in ("CF", "LF", "RF") else 1.0)
            tal -= slope
            oaa_z = tal / pos_sd.get(pos, 6.0)
            stay = p_stay(pos, age, oaa_z)
            if rng.random() > stay and rng.random() < (1 - exit_haz(age)):
                pos = MIG[pos]
        runs[m] = tot
    return runs, of_mult

b = pd.read_csv(os.path.join(REP, "06_defense_plus_2025.csv"))
age25 = dm[dm.season == 2025][["batter", "age"]].rename(columns={"batter": "id"})
b = b.merge(age25, on="id", how="left").dropna(subset=["age", "dplus_runs", "Pos"])
b["oaa_z0"] = b.groupby("Pos")["dplus_runs"].transform(lambda x: (x - x.mean()) / x.std())

rows = []
for _, r in b.iterrows():
    runs, mult = sim(r["Pos"], float(r["age"]), float(r["dplus_runs"]), float(r.get("sd_runs", 3.0)), int(r["id"]))
    rows.append(dict(name=r["PlayerName"], pos=r["Pos"], age=round(r["age"]),
                     career_runs=round(runs.mean()), p10=round(np.percentile(runs, 10)),
                     p90=round(np.percentile(runs, 90)), dWAR=round(runs.mean() / 10, 1), of_age_mult=round(mult, 2)))
C = pd.DataFrame(rows).sort_values("career_runs", ascending=False)
C.to_csv(os.path.join(REP, "18_career_plus_v11.csv"), index=False)
print("=== Career+ v1.1 (quality-conditioned migration + component OF aging) — top 12 ===")
print(C.head(12)[["name", "pos", "age", "career_runs", "p10", "p90", "dWAR"]].to_string(index=False))
print("\n=== PCA + comparators: v1 vs v1.1 ===")
old = pd.read_csv(os.path.join(REP, "17_career_plus.csv")).set_index("name")
for nm in ["Pete Crow-Armstrong", "Bobby Witt Jr.", "Ceddanne Rafaela", "Patrick Bailey"]:
    n = C[C.name == nm]
    if len(n):
        n = n.iloc[0]; o = old.loc[nm, "career_def_runs"] if nm in old.index else np.nan
        print(f"  {nm:22} {n['pos']} age{n['age']}: v1 {o:.0f} -> v1.1 {n['career_runs']:.0f} runs "
              f"({n['dWAR']} dWAR) [{n['p10']:.0f},{n['p90']:.0f}]  OF-age-mult={n['of_age_mult']}")
pca = prof.loc[691718] if 691718 in prof.index else None
print(f"\nPCA jump profile (mean rel-league): reaction {pca['reaction']:+.2f}, burst {pca['burst']:+.2f}, route {pca['route']:+.2f}")
print(f"  -> OF aging multiplier {of_aging_mult(691718):.2f} (>=1 = ages at/above CF average; burst-driven, NO slow-aging bonus)")
print(f"\nwrote reports/18_career_plus_v11.csv")
