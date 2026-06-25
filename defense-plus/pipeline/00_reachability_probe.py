# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Module 00 — Data Reachability Probe
Goal: confirm, from THIS machine, which defensive data sources actually pull.
Binding question for the whole program: do we have FG metrics, or are we Savant-only?

Each source is wrapped in its own try/except with a short timeout so one block
doesn't kill the run. Writes a status table to reports/00_reachability.csv and
caches any successful pull to data/raw/ so later modules don't re-fetch.
"""
import os, sys, time, json, traceback, warnings
import pandas as pd
import requests
warnings.filterwarnings("ignore")

ROOT = os.path.expanduser("~/defense_plus")
RAW = os.path.join(ROOT, "data/raw")
REP = os.path.join(ROOT, "reports")
os.makedirs(RAW, exist_ok=True); os.makedirs(REP, exist_ok=True)

YEAR = 2024
results = []

def rec(source, kind, fn):
    t0 = time.time()
    try:
        df = fn()
        ok = df is not None and len(df) > 0
        ncols = (df.shape[1] if hasattr(df, "shape") else None)
        nrows = (len(df) if df is not None else 0)
        cols = (", ".join(map(str, list(df.columns)[:14])) if hasattr(df, "columns") else "")
        if ok:
            safe = source.replace("/", "_").replace(" ", "_")
            try: df.to_parquet(os.path.join(RAW, f"probe_{safe}.parquet"))
            except Exception: df.to_csv(os.path.join(RAW, f"probe_{safe}.csv"), index=False)
        status = "OK" if ok else "EMPTY"
        results.append(dict(source=source, kind=kind, status=status, rows=nrows,
                            cols=ncols, secs=round(time.time()-t0,1), note=cols[:240]))
        print(f"[{status:5}] {source:38} rows={nrows:>6} cols={ncols} ({round(time.time()-t0,1)}s)")
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        results.append(dict(source=source, kind=kind, status="FAIL", rows=0,
                            cols=None, secs=round(time.time()-t0,1), note=msg[:240]))
        print(f"[FAIL ] {source:38} {msg[:120]}")

import pybaseball as pb

# ---- 1. FanGraphs family (expected BLOCKED from this IP) ----
rec("FG fielding_stats", "fangraphs", lambda: pb.fielding_stats(YEAR, YEAR, qual=1))
rec("FG team_fielding", "fangraphs", lambda: pb.team_fielding(YEAR, YEAR))

# ---- 2. Baseball-Reference ----
rec("BRef team_fielding_bref", "bref", lambda: pb.team_fielding_bref(YEAR))

# ---- 3. Baseball Savant via pybaseball ----
rec("Savant catcher_framing", "savant", lambda: pb.statcast_catcher_framing(YEAR))
rec("Savant catcher_poptime", "savant", lambda: pb.statcast_catcher_poptime(YEAR))
rec("Savant OF directional_oaa", "savant", lambda: pb.statcast_outfield_directional_oaa(YEAR))
rec("Savant OF jump", "savant", lambda: pb.statcast_outfielder_jump(YEAR))
rec("Savant OF catch_prob", "savant", lambda: pb.statcast_outfield_catch_prob(YEAR))

# ---- 4. Baseball Savant direct CSV endpoints (infield OAA, FRV, arm) ----
HDRS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
def savant_csv(url):
    r = requests.get(url, headers=HDRS, timeout=45)
    r.raise_for_status()
    from io import StringIO
    return pd.read_csv(StringIO(r.text))

# Infield OAA leaderboard (all infield positions, min attempts)
rec("Savant CSV infield OAA", "savant_csv", lambda: savant_csv(
    f"https://baseballsavant.mlb.com/leaderboard/outs_above_average?type=Fielder&startYear={YEAR}&endYear={YEAR}"
    f"&split=no&team=&range=year&min=q&pos=if&roles=&viz=hide&csv=true"))

# Fielding Run Value leaderboard
rec("Savant CSV fielding_run_value", "savant_csv", lambda: savant_csv(
    f"https://baseballsavant.mlb.com/leaderboard/fielding_run_value?type=Fielder&year={YEAR}"
    f"&position=&team=&min=q&sortColumn=runs_fielding&sortDirection=desc&csv=true"))

# Arm strength (outfield + infield)
rec("Savant CSV arm_strength", "savant_csv", lambda: savant_csv(
    f"https://baseballsavant.mlb.com/leaderboard/arm-strength?type=player&season={YEAR}&minThrows=q&csv=true"))

# ---- 5. MLB Stats API (fielding by position, MLB + MiLB) ----
def statsapi_fielding(person_id, season, sport_id):
    url = (f"https://statsapi.mlb.com/api/v1/people/{person_id}/stats"
           f"?stats=season&group=fielding&season={season}&sportId={sport_id}")
    r = requests.get(url, headers=HDRS, timeout=30); r.raise_for_status()
    js = r.json()
    splits = js.get("stats", [{}])[0].get("splits", []) if js.get("stats") else []
    rows = []
    for s in splits:
        st = s.get("stat", {}); pos = s.get("position", {})
        rows.append(dict(position=pos.get("abbreviation"), games=st.get("games"),
                         gs=st.get("gamesStarted"), innings=st.get("innings"),
                         putOuts=st.get("putOuts"), assists=st.get("assists"),
                         errors=st.get("errors"), dp=st.get("doublePlays")))
    return pd.DataFrame(rows)

# Bobby Witt Jr (677951) MLB fielding by position — case study + endpoint test
rec("statsapi MLB fielding (Witt)", "statsapi", lambda: statsapi_fielding(677951, YEAR, 1))
# A MiLB season for a prospect — sportId 11=AAA; use a known MiLB season player id
rec("statsapi MiLB fielding (AAA)", "statsapi", lambda: statsapi_fielding(677951, 2022, 11))

# ---- write status table ----
out = pd.DataFrame(results)[["source","kind","status","rows","cols","secs","note"]]
out.to_csv(os.path.join(REP, "00_reachability.csv"), index=False)
print("\n=== SUMMARY ===")
print(out[["source","kind","status","rows","cols"]].to_string(index=False))
print(f"\nwrote {os.path.join(REP,'00_reachability.csv')}")
