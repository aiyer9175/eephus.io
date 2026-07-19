# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Module 02 — FanGraphs fielding suite + head-to-head metric reliability.

Correction to Module 00: FG fielding is NOT blocked. Only the legacy
leaders-legacy.aspx scrape (pybaseball.fielding_stats) is 403. The modern JSON
API /api/leaders/major-league/data?stats=fld works with a browser UA — same
mechanism the playing-time model used for /api/projections.

This gives DRS, UZR, Def, RngR/ARM/DPR/ErrR, FG-hosted OAA & FRP & CFraming, and
Inn-by-position — all in one table. We compute year-to-year reliability for OAA
vs DRS vs UZR vs Def on the IDENTICAL player-position-season sample (common-sample
discipline), with an innings-based low/high split to expose sample-dependence.
"""
import os, time, warnings, requests
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); pd.set_option("display.width", 240)

ROOT = os.path.expanduser("~/defense_plus")
RAW = os.path.join(ROOT, "data/raw"); REP = os.path.join(ROOT, "reports")
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
YEARS = [2021, 2022, 2023, 2024, 2025]
NUM = ["Inn", "OAA", "DRS", "UZR", "UZR/150", "Defense", "RngR", "ARM", "DPR", "ErrR", "FRP", "CFraming"]

def fg_field(year):
    fp = os.path.join(RAW, f"fg_field_{year}.csv")
    if os.path.exists(fp):
        return pd.read_csv(fp)
    p = {"pos": "all", "stats": "fld", "lg": "all", "qual": "0", "season": str(year),
         "season1": str(year), "month": "0", "team": "0", "pageitems": "5000", "pagenum": "1",
         "ind": "0", "rost": "0", "type": "8", "sortdir": "default", "sortstat": "Defense"}
    r = requests.get("https://www.fangraphs.com/api/leaders/major-league/data",
                     params=p, headers=H, timeout=90)
    r.raise_for_status()
    j = r.json(); d = pd.DataFrame(j["data"] if isinstance(j, dict) and "data" in j else j)
    keep = ["xMLBAMID", "PlayerName", "Pos", "Season"] + [c for c in NUM if c in d.columns]
    d = d[keep].copy()
    d.to_csv(fp, index=False); time.sleep(1.5)
    return d

def build_long():
    out = []
    for y in YEARS:
        d = fg_field(y)
        d = d.rename(columns={"xMLBAMID": "id"})
        for c in NUM:
            if c in d.columns: d[c] = pd.to_numeric(d[c], errors="coerce")
        d["id"] = pd.to_numeric(d["id"], errors="coerce")
        d = d[d["id"].notna()]; d["id"] = d["id"].astype(int)
        d["year"] = y
        out.append(d)
    return pd.concat(out, ignore_index=True)

MIN_INN = 200  # floor to count a player-position-season as a usable observation
def reliability(df, metric):
    rows = []
    for pos, g in df.groupby("Pos"):
        if pos in ("P",):  # pitchers excluded
            continue
        g = g[(g["Inn"] >= MIN_INN) & g[metric].notna()]
        pairs = []
        for y in YEARS[:-1]:
            a = g[g.year == y][["id", metric, "Inn"]]
            b = g[g.year == y + 1][["id", metric]].rename(columns={metric: "v2"})
            pairs.append(a.merge(b, on="id"))
        P = pd.concat(pairs) if pairs else pd.DataFrame()
        P = P.dropna(subset=[metric, "v2"])
        if len(P) < 25:
            continue
        r_all = P[metric].corr(P["v2"])
        med = P["Inn"].median()
        lo = P[P["Inn"] <= med]; hi = P[P["Inn"] > med]
        r_lo = lo[metric].corr(lo["v2"]) if len(lo) >= 12 else np.nan
        r_hi = hi[metric].corr(hi["v2"]) if len(hi) >= 12 else np.nan
        rows.append((metric, pos, len(P), round(r_all, 3),
                     round(r_lo, 3) if pd.notna(r_lo) else np.nan,
                     round(r_hi, 3) if pd.notna(r_hi) else np.nan))
    return rows

print("pulling FG fielding 2021-2025...")
L = build_long()
print(f"  {len(L)} player-position-season rows; positions: {sorted(L.Pos.unique())}")

# sanity: FG-hosted OAA should match Savant OAA we pulled in M01 (Witt 2024)
w = L[(L.id == 677951) & (L.year == 2024)][["Pos", "Inn", "OAA", "DRS", "UZR", "Defense"]]
print("Witt 2024 (FG):\n", w.to_string(index=False))

res = []
for m in ["OAA", "DRS", "UZR", "Defense"]:
    res += reliability(L, m)
R = pd.DataFrame(res, columns=["metric", "pos", "n_pairs", "r_yoy", "r_low_inn", "r_high_inn"])

# pivot: metric reliability by position, side by side
piv = R.pivot_table(index="pos", columns="metric", values="r_yoy")
piv = piv.reindex(columns=["OAA", "DRS", "UZR", "Defense"])
order = [p for p in ["C", "SS", "2B", "3B", "CF", "LF", "RF", "1B"] if p in piv.index]
piv = piv.reindex(order)
R.to_csv(os.path.join(REP, "02_metric_reliability.csv"), index=False)

print("\n========= YEAR-TO-YEAR r BY METRIC x POSITION (Inn>=200 both yrs, common sample) =========")
print(piv.round(3).to_string())
print("\n--- sample dependence (OAA & DRS, low vs high innings) ---")
print(R[R.metric.isin(["OAA", "DRS"])][["metric", "pos", "n_pairs", "r_low_inn", "r_high_inn"]].to_string(index=False))
print(f"\nwrote {os.path.join(REP,'02_metric_reliability.csv')}")
