# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Module 04 — Latent RANGE talent (Part 2, first factor).

Thesis: a latent estimate that COMBINES the three range indicators (OAA=Statcast,
rPM=DRS plus/minus, RngR=UZR range), weighted by their Part-1 reliability, should
estimate true range talent better than any single metric. Range is the universal,
highest-value defensive skill (all positions but C), so we nail it first; arm /
double-play / framing factors follow the same template.

Outputs:
  1. Single-factor measurement model -> loadings + variance decomposition
     (shared "true-talent" variance vs metric-specific uniqueness).
  2. Four talent estimators compared OUT-OF-SAMPLE (predict next-year range):
     each single metric, equal-weight composite, reliability-weighted composite,
     factor score. Whichever best predicts the future is the best talent estimate.
  3. Latent range-talent score + per-player uncertainty, shrunk by innings.

NOTE the model only removes METRIC-SPECIFIC noise (what the indicators disagree on).
Variance SHARED across all three (team positioning, park, opportunity) survives in
the common factor -> that is the Part-3 confound problem, not solvable here.
"""
import os, warnings
import numpy as np, pandas as pd
from sklearn.decomposition import FactorAnalysis
warnings.filterwarnings("ignore"); pd.set_option("display.width", 220)

ROOT = os.path.expanduser("~/defense_plus")
RAW = os.path.join(ROOT, "data/raw"); REP = os.path.join(ROOT, "reports")
YEARS = list(range(2021, 2026))
RANGE_POS = ["SS", "2B", "3B", "CF", "LF", "RF"]
IND = ["OAA", "rPM", "RngR"]                       # Statcast / DRS / UZR range
REL = {"OAA": 0.83, "rPM": 0.71, "RngR": 0.46}     # Part-1 full-season reliabilities
MIN_INN = 400

# ---- load ----
fr = []
for y in YEARS:
    d = pd.read_csv(os.path.join(RAW, f"fg_field_full_{y}.csv"))
    d = d.rename(columns={"xMLBAMID": "id"})
    for c in ["id", "Inn"] + IND:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[(d.id.notna()) & d.Pos.isin(RANGE_POS) & (d.Inn >= MIN_INN)].dropna(subset=IND)
    d["id"] = d.id.astype(int); d["year"] = y
    fr.append(d[["id", "PlayerName", "Pos", "year", "Inn"] + IND])
L = pd.concat(fr, ignore_index=True)
# z-score each indicator within position-year (comparable scale across positions)
for c in IND:
    L[c + "z"] = L.groupby(["Pos", "year"])[c].transform(lambda x: (x - x.mean()) / x.std())
L = L.dropna(subset=[c + "z" for c in IND])
print(f"sample: {len(L)} player-position-seasons, {L.Pos.nunique()} positions, {L.year.nunique()} years\n")

# ---- 1. single-factor measurement model + variance decomposition ----
Z = L[[c + "z" for c in IND]].values
fa = FactorAnalysis(n_components=1, random_state=0).fit(Z)
load = fa.components_[0]                      # loadings on the common factor
noise = fa.noise_variance_                    # metric-specific uniqueness
comm = load ** 2                              # communality (shared/true-talent variance)
print("=== RANGE measurement model (1 common factor) ===")
print(f"{'indicator':10}{'loading':>9}{'communality':>13}{'uniqueness':>12}{'(Part1 Rel)':>13}")
for j, c in enumerate(IND):
    print(f"{c:10}{load[j]:9.2f}{comm[j]:13.2f}{noise[j]:12.2f}{REL[c]:13.2f}")
print(f"\nmean communality (shared 'true-talent' variance share) = {comm.mean():.2f}")
print("  -> the rest is metric-specific noise the latent removes.")
print("  -> CAUTION: shared variance still contains shared confounds (positioning/park) -> Part 3.\n")

# ---- estimators ----
def estimators(df):
    e = {}
    for c in IND: e[c] = df[c + "z"].values
    e["equal"] = df[[c + "z" for c in IND]].mean(axis=1).values
    w = np.array([REL[c] for c in IND]); w = w / w.sum()
    e["relwt"] = (df[[c + "z" for c in IND]].values * w).sum(axis=1)
    e["factor"] = fa.transform(df[[c + "z" for c in IND]].values)[:, 0]
    return e

# ---- 2. OUT-OF-SAMPLE: estimator_t predicts next-year range ----
# build adjacent-year pairs (same player, same position)
pairs = []
for pos, g in L.groupby("Pos"):
    for y in YEARS[:-1]:
        a = g[g.year == y]; b = g[g.year == y + 1]
        m = a.merge(b, on="id", suffixes=("", "_n"))
        m["Pos"] = pos; pairs.append(m)
P = pd.concat(pairs, ignore_index=True)
est = estimators(P)
targets = {"next OAA": P["OAAz_n"].values, "next rPM (DRS)": P["rPMz_n"].values,
           "next RngR (UZR)": P["RngRz_n"].values,
           "next AVG(3)": P[[c + "z_n" for c in IND]].mean(axis=1).values}
print(f"=== OUT-OF-SAMPLE: predict next-year range  (n={len(P)} season pairs, Inn>={MIN_INN} both yrs) ===")
hdr = f"{'estimator_t':14}" + "".join(f"{t:>16}" for t in targets)
print(hdr)
rows = []
for name in ["OAA", "rPM", "RngR", "equal", "relwt", "factor"]:
    line = f"{name:14}"
    rec = {"estimator": name}
    for t, yv in targets.items():
        r = np.corrcoef(est[name], yv)[0, 1]
        line += f"{r:16.3f}"; rec[t] = round(r, 3)
    print(line); rows.append(rec)
pd.DataFrame(rows).to_csv(os.path.join(REP, "04_range_oos.csv"), index=False)

best_single = max(["OAA", "rPM", "RngR"], key=lambda n: np.corrcoef(est[n], targets["next AVG(3)"])[0, 1])
r_best = np.corrcoef(est[best_single], targets["next AVG(3)"])[0, 1]
r_rel = np.corrcoef(est["relwt"], targets["next AVG(3)"])[0, 1]
r_fac = np.corrcoef(est["factor"], targets["next AVG(3)"])[0, 1]
print(f"\nbest single metric ({best_single}) vs broad future: r={r_best:.3f}")
print(f"reliability-weighted composite:            r={r_rel:.3f}   ({(r_rel-r_best)/r_best*+100:+.1f}% vs best single)")
print(f"factor score:                              r={r_fac:.3f}   ({(r_fac-r_best)/r_best*+100:+.1f}% vs best single)")

# ---- 3. ship latent range talent + uncertainty (current season = 2025) ----
# UZR/RngR is not yet published for 2025 (publication lag) -> use the two timely
# indicators OAA + rPM(DRS), reliability-weighted and renormalized.
CUR_IND = ["OAA", "rPM"]
cur = pd.read_csv(os.path.join(RAW, "fg_field_full_2025.csv")).rename(columns={"xMLBAMID": "id"})
for c in ["id", "Inn"] + CUR_IND:
    cur[c] = pd.to_numeric(cur[c], errors="coerce")
cur = cur[cur.id.notna() & cur.Pos.isin(RANGE_POS) & (cur.Inn >= MIN_INN)].dropna(subset=CUR_IND)
cur["id"] = cur.id.astype(int); cur["year"] = 2025
for c in CUR_IND:
    cur[c + "z"] = cur.groupby("Pos")[c].transform(lambda x: (x - x.mean()) / x.std())
wc = np.array([REL[c] for c in CUR_IND]); wc = wc / wc.sum()
cur["range_talent_z"] = (cur[[c + "z" for c in CUR_IND]].values * wc).sum(axis=1)
# uncertainty: shrink toward 0 by innings reliability; posterior sd ~ sqrt(1-rel_n)
cur["rel_n"] = cur["Inn"] / (cur["Inn"] + 269.0)          # OAA-anchored stabilization (Part1 n0)
cur["range_talent_shrunk"] = cur["range_talent_z"] * cur["rel_n"]
cur["talent_sd"] = np.sqrt(1 - cur["rel_n"]) * cur["range_talent_z"].std()
out = cur.sort_values("range_talent_shrunk", ascending=False)
out[["id", "PlayerName", "Pos", "Inn", "range_talent_z", "range_talent_shrunk", "talent_sd"]] \
   .to_csv(os.path.join(REP, "04_range_talent_2025.csv"), index=False)
print("\n=== 2025 latent range talent — top 10 (shrunk by innings) ===")
print(out.head(10)[["PlayerName", "Pos", "Inn", "range_talent_shrunk", "talent_sd"]].to_string(index=False))
print(f"\nwrote reports/04_range_oos.csv, reports/04_range_talent_2025.csv")
