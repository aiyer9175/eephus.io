# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ CAPSTONE — Career+ : career defensive-value projection.

Monte-Carlo combine the parts into a per-player remaining-career defensive projection:
  current talent (Part 2)  +  aging (Part 4)  +  migration/retention (Part 5)  +
  exit hazard (Part 5 longevity)  ->  career defensive runs / WAR with credible interval.

Each simulated career-year: age the position-relative talent by the position's slope, add
the positional adjustment, accrue value scaled by playing time; then maybe migrate down the
spectrum (posadj drops, range talent carries) and maybe exit. Answers the program's 5 Qs.

Assumptions (documented): pt=0.85 of a full season when active; migration is down-spectrum to
the modal destination; talent carries on a move (range transfers); 10 runs = 1 WAR.
"""
import os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)
rng = np.random.default_rng(7)

HOME = os.path.expanduser("~"); REP = os.path.join(HOME, "defense_plus/reports")
POSADJ = {"C": 12.5, "SS": 7.5, "2B": 2.5, "3B": 2.5, "CF": 2.5, "LF": -7.5, "RF": -7.5, "1B": -12.5, "DH": -17.5}
SLOPE = {"C": 0.80, "CF": 0.73, "SS": 0.62, "RF": 0.37, "2B": 0.37, "3B": 0.23, "LF": 0.15, "1B": -0.07, "DH": 0.0}  # Part 4 runs/yr
MOVE = {"C": 0.03, "SS": 0.20, "CF": 0.26, "2B": 0.25, "3B": 0.20, "RF": 0.22, "LF": 0.28, "1B": 0.12, "DH": 0.05}  # Part 5
MIG = {"SS": "2B", "2B": "3B", "3B": "1B", "CF": "LF", "RF": "LF", "LF": "1B", "C": "1B", "1B": "DH", "DH": "DH"}
# exit hazard for established REGULARS (PA>=400 -> >=200 PA next yr), by age (Part 5 longevity)
EXIT_AGE = {22: .10, 23: .10, 24: .13, 25: .08, 26: .12, 27: .11, 28: .10, 29: .08, 30: .09,
            31: .11, 32: .11, 33: .17, 34: .19, 35: .18, 36: .28, 37: .25, 38: .22, 39: .30, 40: .35}
PT = 0.85

def exit_haz(age):
    a = int(round(age));
    return EXIT_AGE.get(a, 0.10 if a < 22 else 0.50)
def move_rate(pos, age):
    r = MOVE.get(pos, 0.15)
    if pos in ("SS", "CF") and age >= 32: r *= 1.5   # Part 5: rises with age at early-peak pos
    return min(r, 0.6)

def sim_one(pos0, age0, talent0, sd0, M=2000):
    runs = np.empty(M); yrs = np.empty(M)
    for m in range(M):
        pos, age, tal = pos0, age0, rng.normal(talent0, max(sd0, 0.1))
        tot, y = 0.0, 0
        while age <= 41:
            if rng.random() < exit_haz(age): break
            tot += (tal + POSADJ.get(pos, 0)) * PT
            y += 1
            age += 1
            tal -= SLOPE.get(pos, 0.3)                       # age the talent
            if rng.random() < move_rate(pos, age):
                pos = MIG.get(pos, "DH")                     # migrate down-spectrum (talent carries)
        runs[m] = tot; yrs[m] = y
    return runs, yrs

# ---- current MLB defenders (2025 Defense+ board) + age ----
b = pd.read_csv(os.path.join(REP, "06_defense_plus_2025.csv"))
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))
age25 = dm[dm.season == 2025][["batter", "age"]].rename(columns={"batter": "id", "age": "age"})
b = b.merge(age25, on="id", how="left").dropna(subset=["age", "dplus_runs", "Pos"])
print(f"projecting {len(b)} current MLB defenders...\n")

rows = []
for _, r in b.iterrows():
    runs, yrs = sim_one(r["Pos"], float(r["age"]), float(r["dplus_runs"]), float(r.get("sd_runs", 3.0)))
    rows.append(dict(name=r["PlayerName"], pos=r["Pos"], age=round(r["age"]),
                     now_runs=round(r["dplus_total"], 1),
                     career_def_runs=round(runs.mean(), 0),
                     p10=round(np.percentile(runs, 10), 0), p90=round(np.percentile(runs, 90), 0),
                     career_def_WAR=round(runs.mean() / 10, 1), exp_years=round(yrs.mean(), 1)))
C = pd.DataFrame(rows).sort_values("career_def_runs", ascending=False)
C.to_csv(os.path.join(REP, "17_career_plus.csv"), index=False)

print("=== CAREER+ — remaining career defensive value, top 15 ===")
print(C.head(15)[["name", "pos", "age", "now_runs", "career_def_runs", "p10", "p90", "career_def_WAR", "exp_years"]].to_string(index=False))

print("\n=== the program's 5 questions, example players ===")
for nm in ["Patrick Bailey", "Bobby Witt Jr.", "Pete Crow-Armstrong", "Ke'Bryan Hayes"]:
    r = C[C.name == nm]
    if len(r):
        r = r.iloc[0]
        print(f"\n{nm} ({r['pos']}, age {r['age']}):")
        print(f"  1) how good now?      {r['now_runs']:+.0f} def runs/yr")
        print(f"  2) good in 5 yrs?     talent ages ~{SLOPE[r['pos']]*5:.1f} runs over 5 yr at {r['pos']}")
        print(f"  3) what position?     starts {r['pos']}; down-spectrum drift modeled")
        print(f"  4) how certain?       career def runs 80% CI [{r['p10']:.0f}, {r['p90']:.0f}]")
        print(f"  5) career def value?  {r['career_def_runs']:.0f} runs ({r['career_def_WAR']:.1f} dWAR) over ~{r['exp_years']:.0f} yrs")
print(f"\nwrote reports/17_career_plus.csv")
