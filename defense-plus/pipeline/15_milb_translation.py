# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Part 6 — MiLB -> MLB position translation (flagship).

No MiLB tracking exists, so position HISTORY is the signal. Build the AAA -> MLB primary-
position transition matrix and test the prompt's hypothesis: does holding a position (esp.
SS) at AAA predict holding it in MLB? Cohort = MLB position players who debuted 2015-2024.

AAA fielding from statsapi (sportId=11; AA=12 fallback). Cached to data/raw/milb_fielding.parquet.
"""
import os, time, json, warnings
import numpy as np, pandas as pd, requests
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)

HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw"); REP = os.path.join(HOME, "defense_plus/reports")
H = {"User-Agent": "Mozilla/5.0"}
POS = ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "DH"]

# ---- MLB cohort + MLB primary position (from usage_spine) ----
u = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/usage_spine.parquet"))
for p in POS:
    if f"gs_{p.lower()}" not in u.columns: u[f"gs_{p.lower()}"] = 0
gs = [f"gs_{p.lower()}" for p in POS]
career = u.groupby("mlbam_id").agg(first=("season", "min"), gs_total=("gs_total", "sum"),
                                   **{p: (f"gs_{p.lower()}", "sum") for p in POS})
career["mlb_pos"] = career[POS].idxmax(axis=1)
career["mlb_gs_primary"] = career[POS].max(axis=1)
cohort = career[(career["first"] >= 2015) & (career["mlb_gs_primary"] >= 100) & (career["mlb_pos"] != "P")]
ids = cohort.index.tolist()
print(f"MLB cohort: {len(ids)} position players (debut>=2015, >=100 career GS at primary)")

# ---- pull AAA (then AA) primary position from statsapi, cached ----
CACHE = os.path.join(RAW, "milb_fielding.parquet")
done = {}
if os.path.exists(CACHE):
    done = {int(r.mlbam_id): r._asdict() for r in pd.read_parquet(CACHE).itertuples(index=False)}

def milb_primary(pid, sport):
    url = f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=yearByYear&group=fielding&sportId={sport}"
    try:
        j = requests.get(url, headers=H, timeout=20).json()
        sp = j.get("stats", [{}])[0].get("splits", []) if j.get("stats") else []
    except Exception:
        return None
    gsd = {}
    for s in sp:
        p = s.get("position", {}).get("abbreviation"); g = s.get("stat", {}).get("gamesStarted") or 0
        if p and p != "P": gsd[p] = gsd.get(p, 0) + g
    if not gsd: return None
    prim = max(gsd, key=gsd.get)
    return dict(pos=prim, gs=gsd[prim], total=sum(gsd.values()),
                played_ss=gsd.get("SS", 0), played_cf=gsd.get("CF", 0), played_c=gsd.get("C", 0))

rows = []
todo = [i for i in ids if i not in done]
print(f"pulling AAA/AA fielding for {len(todo)} uncached players...")
for k, pid in enumerate(todo):
    rec = milb_primary(pid, 11); lvl = "AAA"
    if rec is None:
        rec = milb_primary(pid, 12); lvl = "AA"
    if rec is None:
        rec = dict(pos=None, gs=0, total=0, played_ss=0, played_cf=0, played_c=0); lvl = "none"
    rec.update(mlbam_id=pid, milb_level=lvl)
    done[pid] = rec
    time.sleep(0.25)
    if (k + 1) % 100 == 0:
        pd.DataFrame(done.values()).to_parquet(CACHE); print(f"  {k+1}/{len(todo)}")
pd.DataFrame(done.values()).to_parquet(CACHE)

M = pd.DataFrame([done[i] for i in ids if i in done])
M = M.merge(cohort[["mlb_pos"]].reset_index(), on="mlbam_id", how="left").rename(columns={"pos": "milb_pos"})
M = M[M.milb_pos.notna() & (M.total >= 20)]
print(f"\nusable: {len(M)} players with AAA/AA primary pos + MLB pos\n")

# ---- transition matrix AAA -> MLB ----
T = pd.crosstab(M["milb_pos"], M["mlb_pos"], normalize="index").reindex([p for p in POS if p in M.milb_pos.values])
T = T[[p for p in POS if p in T.columns]]
print("=== MiLB(AAA) primary pos -> MLB primary pos  P(%) ===")
print((T * 100).round(0).astype("Int64").to_string())

# ---- hypothesis: does holding SS at AAA predict MLB SS? ----
print("\n=== position-hold rate MiLB(AAA) -> MLB (premium positions) ===")
for p in ["C", "SS", "CF", "2B", "3B"]:
    sub = M[M.milb_pos == p]
    if len(sub) < 8: continue
    held = (sub.mlb_pos == p).mean()
    print(f"  AAA {p:3} -> MLB {p:3}: {held*100:4.0f}%  (n={len(sub)})")
# SS specifically: of AAA-SS, where do they end up
ss = M[M.milb_pos == "SS"]
print(f"\n  AAA shortstops (n={len(ss)}) MLB landing: " +
      ", ".join(f"{k} {v*100:.0f}%" for k, v in ss.mlb_pos.value_counts(normalize=True).head(5).items()))
M.to_parquet(os.path.join(REP.replace("reports","data/processed"), "milb_translation.parquet")) if os.path.isdir(REP.replace("reports","data/processed")) else None
T.to_csv(os.path.join(REP, "15_milb_transition.csv"))
print(f"\nwrote reports/15_milb_transition.csv (cache: data/raw/milb_fielding.parquet)")
