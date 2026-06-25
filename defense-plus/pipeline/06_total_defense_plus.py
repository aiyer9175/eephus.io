# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Module 06 — total positional Defense+ talent (Part 2 capstone).

Combine the per-skill picture into ONE talent number per player-position-season, in
runs, validated against future total defensive value and shipped with uncertainty.

Spine of the total = the two independent TOTAL-defense systems plus the range tool:
  OAA  (Statcast range, most reliable, fast/changeable)
  DRS  (BIS total, stickier, carries arm/GDP/error/throwing components)
  FRP  (Statcast total fielding run value)
Reliability-weighted blend (Module-04 lesson: weight by reliability, not factor loadings),
shrunk by innings. OOS: does the blend predict next-year total defense better than any
single system? Then convert to runs + positional adjustment for a cross-position board.
"""
import os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)

RAW = os.path.expanduser("~/defense_plus/data/raw"); REP = os.path.expanduser("~/defense_plus/reports")
YEARS = list(range(2021, 2026))
POS = ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B"]
TOT = ["OAA", "DRS", "FRP"]
# standard positional adjustment (runs / 162 G), for cross-position comparison
POSADJ = {"C": 12.5, "SS": 7.5, "2B": 2.5, "3B": 2.5, "CF": 2.5, "LF": -7.5, "RF": -7.5, "1B": -12.5}
MIN_INN = 300

fr = []
for y in YEARS:
    d = pd.read_csv(os.path.join(RAW, f"fg_field_full_{y}.csv")).rename(columns={"xMLBAMID": "id"})
    d["year"] = y; fr.append(d)
F = pd.concat(fr, ignore_index=True)
for c in ["id", "Inn"] + TOT:
    F[c] = pd.to_numeric(F[c], errors="coerce")
F = F[F.id.notna() & F.Pos.isin(POS) & (F.Inn >= MIN_INN)].copy()
F["id"] = F.id.astype(int)
# catchers have no OAA/FRP-range -> for C, DRS carries the load; keep OAA/FRP where present
for c in TOT:
    F[c + "z"] = F.groupby(["Pos", "year"])[c].transform(lambda x: (x - x.mean()) / x.std())

def yoy(d, col):
    pr = []
    for y in YEARS[:-1]:
        a = d[d.year == y][["id", col]]; b = d[d.year == y + 1][["id", col]].rename(columns={col: "v2"})
        pr.append(a.merge(b, on="id"))
    P = pd.concat(pr).dropna()
    return P[col].corr(P["v2"]) if len(P) >= 25 else np.nan

rel = {c: yoy(F, c) for c in TOT}
print("=== total-defense system reliabilities (y2y, Inn>=300) ===")
for c in TOT: print(f"   {c:4} r={rel[c]:.3f}")

# reliability-weighted blend over the systems available for each row
def blend(df):
    w = {c: max(rel[c], 0.05) for c in TOT}
    zs = df[[c + "z" for c in TOT]].values
    wv = np.array([w[c] for c in TOT])
    mask = ~np.isnan(zs)
    wmat = np.where(mask, wv, 0.0); zfill = np.where(mask, zs, 0.0)
    return (zfill * wmat).sum(1) / np.where(wmat.sum(1) == 0, np.nan, wmat.sum(1))

F["dplus_z"] = blend(F)

# ---- OOS: blend_t vs next-year total defense ----
pairs = []
for pos, g in F.groupby("Pos"):
    for y in YEARS[:-1]:
        a = g[g.year == y]; b = g[g.year == y + 1]
        pairs.append(a.merge(b, on="id", suffixes=("", "_n")))
P = pd.concat(pairs, ignore_index=True)
tgt_all = P[[c + "z_n" for c in TOT]].mean(axis=1)
targets = {"next DRS": P["DRSz_n"], "next FRP": P["FRPz_n"], "next OAA": P["OAAz_n"], "next AVG": tgt_all}
print(f"\n=== OOS: predict next-year total defense (n={len(P)} pairs) ===")
print(f"{'estimator_t':12}" + "".join(f"{t:>11}" for t in targets))
rows = []
for name in ["OAA", "DRS", "FRP", "dplus"]:
    col = name + "z" if name != "dplus" else "dplus_z"
    line = f"{name:12}"; rec = {"estimator": name}
    for t, yv in targets.items():
        m = P[[col, yv.name if hasattr(yv, 'name') else None]] if False else None
        ok = P[col].notna() & yv.notna()
        r = np.corrcoef(P.loc[ok, col], yv[ok])[0, 1]
        line += f"{r:11.3f}"; rec[t] = round(r, 3)
    print(line); rows.append(rec)
pd.DataFrame(rows).to_csv(os.path.join(REP, "06_total_oos.csv"), index=False)
best = max(["OAA", "DRS", "FRP"], key=lambda n: np.corrcoef(*[a[P[n+'z'].notna() & tgt_all.notna()] for a in (P[n+'z'], tgt_all)])[0,1])
rb = np.corrcoef(P.loc[P[best+'z'].notna()&tgt_all.notna(), best+'z'], tgt_all[P[best+'z'].notna()&tgt_all.notna()])[0,1]
rd = np.corrcoef(P.loc[P.dplus_z.notna()&tgt_all.notna(), 'dplus_z'], tgt_all[P.dplus_z.notna()&tgt_all.notna()])[0,1]
print(f"\nbest single system ({best}) vs next AVG: r={rb:.3f}")
print(f"Defense+ blend          vs next AVG: r={rd:.3f}   ({(rd-rb)/rb*100:+.1f}%)")

# ---- ship 2025 cross-position Defense+ talent (runs) ----
cur = F[F.year == 2025].copy()
cur["rel_n"] = cur["Inn"] / (cur["Inn"] + 269.0)
# scale z to runs via within-position DRS sd (runs/season at that position), then shrink + posadj
drs_sd = F.groupby("Pos")["DRS"].std()
cur["dplus_runs_raw"] = cur["dplus_z"] * cur["Pos"].map(drs_sd)
cur["dplus_runs"] = cur["dplus_runs_raw"] * cur["rel_n"]                      # shrink by innings
cur["dplus_total"] = cur["dplus_runs"] + cur["Pos"].map(POSADJ) * cur["Inn"] / 1350.0  # posadj prorated by full-season innings (~1350)
cur["sd_runs"] = np.sqrt(1 - cur["rel_n"]) * cur["Pos"].map(drs_sd)
board = cur.sort_values("dplus_total", ascending=False)
board[["id", "PlayerName", "Pos", "Inn", "dplus_runs", "dplus_total", "sd_runs"]].to_csv(
    os.path.join(REP, "06_defense_plus_2025.csv"), index=False)
print("\n=== 2025 TOTAL Defense+ talent (runs vs avg + positional adj), top 12 ===")
print(board.head(12)[["PlayerName", "Pos", "Inn", "dplus_runs", "dplus_total", "sd_runs"]].round(1).to_string(index=False))
print(f"\nwrote reports/06_total_oos.csv, reports/06_defense_plus_2025.csv")
