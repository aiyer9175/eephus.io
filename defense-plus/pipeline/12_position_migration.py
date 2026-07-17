# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Part 5 — position migration matrices + directionality (the empirical backbone).

Primary position per player-season from usage_spine (gs_* argmax), 2000-2026. Build the
year-over-year transition matrix pos_t -> pos_t+1 (+ EXIT = no MLB next year), test whether
migration runs DOWN the defensive spectrum, and show migration rate rises past each
position's aging peak (links to Part 4).

Spectrum rank (more demanding = higher): C8 SS7 CF6 2B5 3B4 RF3 LF2 1B1 DH0.
"""
import os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)

HOME = os.path.expanduser("~"); REP = os.path.join(HOME, "defense_plus/reports")
POS = ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "DH"]
RANK = {"C": 8, "SS": 7, "CF": 6, "2B": 5, "3B": 4, "RF": 3, "LF": 2, "1B": 1, "DH": 0}
PEAK = {"CF": 23, "RF": 21, "LF": 21, "SS": 27, "2B": 26, "3B": 26, "C": 28, "1B": 31}  # Part 4

u = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/usage_spine.parquet"))
for p in POS:
    c = f"gs_{p.lower()}"
    if c not in u.columns: u[c] = 0
gs = [f"gs_{p.lower()}" for p in POS]
u["primary"] = u[gs].idxmax(axis=1).str.replace("gs_", "").str.upper()
u["gs_max"] = u[gs].max(axis=1)
u = u[u["gs_max"] >= 20]                       # real primary position (>=20 starts)
sp = u[["mlbam_id", "season", "primary", "pa"]].copy()

# add age
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]]
sp = sp.merge(dm.rename(columns={"batter": "mlbam_id"}), on=["mlbam_id", "season"], how="left")

# transitions t -> t+1
nxt = sp[["mlbam_id", "season", "primary"]].rename(columns={"season": "s1", "primary": "pos1"})
nxt["season"] = nxt["s1"] - 1
T = sp.merge(nxt[["mlbam_id", "season", "pos1"]], on=["mlbam_id", "season"], how="left")
T = T[T.season <= 2024].copy()                 # observed t+1
T["pos1"] = T["pos1"].fillna("EXIT")

# ---- transition matrix (row = pos_t, normalized; incl EXIT) ----
M = pd.crosstab(T["primary"], T["pos1"], normalize="index").reindex(POS)
cols = [c for c in POS if c in M.columns] + (["EXIT"] if "EXIT" in M.columns else [])
M = M[cols]
print("=== POSITION TRANSITION MATRIX  P(pos_t+1 | pos_t)  (%, rows=this year) ===")
print((M * 100).round(0).astype("Int64").to_string())

# ---- retention (stay at same position) ----
print("\n=== retention P(same position next year) ===")
ret = T.groupby("primary").apply(lambda g: (g["pos1"] == g.name).mean()).reindex(POS)
for p in POS:
    print(f"  {p:3} stay {ret[p]*100:4.0f}%   (peak age {PEAK.get(p,'-')})")

# ---- directionality: among movers (changed position, not exit), down vs up spectrum ----
mv = T[(T.pos1 != "EXIT") & (T.pos1 != T.primary)].copy()
mv["rank0"] = mv["primary"].map(RANK); mv["rank1"] = mv["pos1"].map(RANK)
down = (mv["rank1"] < mv["rank0"]).mean(); up = (mv["rank1"] > mv["rank0"]).mean()
print(f"\n=== migration directionality (movers only, n={len(mv)}) ===")
print(f"  DOWN-spectrum (toward easier): {down*100:.0f}%   UP-spectrum: {up*100:.0f}%   -> migration is {'mostly DOWN' if down>0.6 else 'mixed'}")

# ---- migration rate vs age, for premium positions ----
print("\n=== move-rate by age (premium positions), vs Part-4 peak ===")
prem = T[T.primary.isin(["SS", "CF", "C", "2B"]) & T.pos1.ne("EXIT") & T.age.notna()].copy()
prem["moved"] = (prem.pos1 != prem.primary).astype(int)
prem["ageband"] = pd.cut(prem.age, [0, 25, 28, 31, 99], labels=["<=25", "26-28", "29-31", "32+"])
piv = prem.pivot_table(index="primary", columns="ageband", values="moved", aggfunc="mean").reindex(["C", "SS", "CF", "2B"])
print((piv * 100).round(0).astype("Int64").to_string())

M.to_csv(os.path.join(REP, "12_transition_matrix.csv"))
pd.DataFrame({"pos": POS, "retain": ret.values, "peak_age": [PEAK.get(p) for p in POS]}).to_csv(
    os.path.join(REP, "12_retention.csv"), index=False)
print(f"\nwrote reports/12_transition_matrix.csv, reports/12_retention.csv")
print(f"sample: {len(T)} player-season transitions, {int(sp.season.min())}-2024")
