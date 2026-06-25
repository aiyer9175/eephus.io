# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Part 11 / M11-A round 2 — (a) regular-retention variant, (b) Defense+ decomposition.

(a) Re-run the position survival thresholds with a tougher bar: survive = >=400 PA next
    year ("remain a REGULAR") vs M11-A's >=50 PA ("stay in MLB"). Expect WIDER gaps.

(b) Add the Module-06 Defense+ talent number as a covariate and ask: how much of the
    premium-position survival discount is genuine DEFENSIVE VALUE vs pure positional
    SCARCITY? Compare the premium discount with vs without dplus_total.
    (Defense+ only exists 2021-2024 -> small sample; directional.)
"""
import os, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)

HOME = os.path.expanduser("~"); REP = os.path.join(HOME, "defense_plus/reports")
RAW = os.path.join(HOME, "defense_plus/data/raw")
POS = ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "DH"]
PREMIUM = ["C", "SS", "CF", "2B"]; BAT = ["1B", "LF", "RF", "DH"]
POSADJ = {"C": 12.5, "SS": 7.5, "2B": 2.5, "3B": 2.5, "CF": 2.5, "LF": -7.5, "RF": -7.5, "1B": -12.5}

# ---------- survivorship spine (same as M11-A) ----------
u = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/usage_spine.parquet"))
for p in POS:
    if f"gs_{p.lower()}" not in u.columns: u[f"gs_{p.lower()}"] = 0
gscols = [f"gs_{p.lower()}" for p in POS]
u["primary_pos"] = u[gscols].idxmax(axis=1).str.replace("gs_", "").str.upper()
u = u[u[gscols].max(axis=1) >= 10]
sp = u[["mlbam_id", "season", "pa", "primary_pos"]].copy()
nxt = sp[["mlbam_id", "season", "pa"]].rename(columns={"season": "s1", "pa": "pa1"}); nxt["season"] = nxt["s1"] - 1
sp = sp.merge(nxt[["mlbam_id", "season", "pa1"]], on=["mlbam_id", "season"], how="left")
sp["surv50"] = (sp["pa1"].fillna(0) >= 50).astype(int)
sp["surv400"] = (sp["pa1"].fillna(0) >= 400).astype(int)

dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet")).rename(columns={"batter": "mlbam_id"})
lg = dm.assign(w=dm.woba * dm.pa).groupby("season").apply(lambda g: g.w.sum() / g.pa.sum()).rename("lg_woba").reset_index()
dm = dm.merge(lg, on="season"); dm["woba_plus"] = 100 * dm["woba"] / dm["lg_woba"]
sp = sp.merge(dm[["mlbam_id", "season", "woba_plus", "age"]], on=["mlbam_id", "season"], how="inner")
df = sp[(sp.pa >= 200) & (sp.season <= 2024) & sp.primary_pos.isin(POS)].dropna(subset=["woba_plus", "age"]).copy()
df["logpa"] = np.log(df["pa"])

# ---------- helper: premium discount in wOBA+ points from a logistic ----------
def premium_discount(d, ycol, extra=None):
    d = d.copy(); d["prem"] = d.primary_pos.isin(PREMIUM).astype(int)
    cols = ["woba_plus", "prem", "age", "logpa"] + (extra or [])
    d = d.dropna(subset=cols + [ycol])
    X = d[cols].values.astype(float); y = d[ycol].values
    m = LogisticRegression(max_iter=3000, C=1e6).fit(X, y)
    c = dict(zip(cols, m.coef_[0]))
    # premium advantage expressed as wOBA+ points = prem_coef / woba_plus_coef
    disc = c["prem"] / c["woba_plus"]
    return disc, c, len(d)

# ================= (a) regular-retention variant (full sample) =================
print("===== (a) survival bar: stay in MLB (>=50 PA) vs remain a REGULAR (>=400 PA) =====")
for ycol, lab in [("surv50", ">=50 PA  (M11-A)"), ("surv400", ">=400 PA (regular)")]:
    disc, c, n = premium_discount(df, ycol)
    base = df[ycol].mean()
    print(f"  {lab:20} base-rate={base:.2f}  premium discount = {disc:.1f} wOBA+ pts  (n={n})")
print("  (discount = how many wOBA+ points less a premium-position player needs to survive at equal age/PA)\n")

# ================= (b) Defense+ decomposition (recent sample) =================
# rebuild Module-06 Defense+ talent per (id, year) primary position, 2021-2024
YEARS = list(range(2021, 2026)); TOT = ["OAA", "DRS", "FRP"]
fr = []
for yY in YEARS:
    d = pd.read_csv(os.path.join(RAW, f"fg_field_full_{yY}.csv")).rename(columns={"xMLBAMID": "id"}); d["year"] = yY; fr.append(d)
FG = pd.concat(fr, ignore_index=True)
for col in ["id", "Inn"] + TOT: FG[col] = pd.to_numeric(FG[col], errors="coerce")
FG = FG[FG.id.notna() & FG.Pos.isin([p for p in POS if p != "DH"]) & (FG.Inn >= 300)].copy(); FG["id"] = FG.id.astype(int)
for col in TOT: FG[col + "z"] = FG.groupby(["Pos", "year"])[col].transform(lambda x: (x - x.mean()) / x.std())
def yoy(d, col):
    pr = [d[d.year == y][["id", col]].merge(d[d.year == y + 1][["id", col]].rename(columns={col: "v2"}), on="id") for y in YEARS[:-1]]
    P = pd.concat(pr).dropna(); return P[col].corr(P["v2"]) if len(P) >= 25 else np.nan
rel = {col: max(yoy(FG, col), 0.05) for col in TOT}
zs = FG[[c + "z" for c in TOT]].values; wv = np.array([rel[c] for c in TOT]); mask = ~np.isnan(zs)
wmat = np.where(mask, wv, 0); FG["dplus_z"] = (np.where(mask, zs, 0) * wmat).sum(1) / np.where(wmat.sum(1) == 0, np.nan, wmat.sum(1))
drs_sd = FG.groupby("Pos")["DRS"].std()
FG["dplus_runs"] = FG["dplus_z"] * FG["Pos"].map(drs_sd)
FG["dplus_total"] = FG["dplus_runs"] + FG["Pos"].map(POSADJ) * FG["Inn"] / 1350.0
# primary position row per (id, year) = max innings
prim = FG.sort_values("Inn").groupby(["id", "year"]).tail(1)[["id", "year", "dplus_runs", "dplus_total"]]
prim = prim.rename(columns={"year": "season", "id": "mlbam_id"})
rec = df.merge(prim, on=["mlbam_id", "season"], how="inner")
print(f"===== (b) Defense+ decomposition of the discount (2021-2024 sample, n={len(rec)}) =====")
for ycol, lab in [("surv50", "stay in MLB (>=50 PA)"), ("surv400", "remain regular (>=400 PA)")]:
    dA, _, n = premium_discount(rec, ycol)
    dC, cC, _ = premium_discount(rec, ycol, extra=["dplus_total"])
    expl = dA - dC
    pct = expl / dA * 100 if dA != 0 else np.nan
    print(f"\n  [{lab}]  base premium discount (no defense control) = {dA:.1f} wOBA+ pts")
    print(f"     after controlling total Defense+ runs:           = {dC:.1f} wOBA+ pts (residual = SCARCITY)")
    print(f"     explained by measured defensive value            = {expl:.1f} pts ({pct:.0f}%)")
    print(f"     Defense+ survival effect: {cC['dplus_total']:+.3f} logit / def-run "
          f"(={cC['dplus_total']/cC['woba_plus']:.2f} wOBA+ pts per def-run)")
pd.DataFrame([{"note": "see stdout"}]).to_csv(os.path.join(REP, "11a2_round2.csv"), index=False)
print("\nCAVEAT: (b) sample is Statcast-era only (2021-24), thin per position -> directional, not definitive.")
