# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E05 — Savant defensive quality (OAA/FRV) + sprint speed pull.

Defensive Floor+ (candidate 1) and speed (candidate 3). Per player-season:
  OAA  outs_above_average, fielding_runs_prevented (FRV)   2016-2025
  sprint_speed (ft/s)                                       2015-2025
player_id is MLBAM. These are year-t features for projecting PA in t+1.

Output: data/raw/savant_oaa.parquet, data/raw/sprint_speed.parquet
"""
import io
import time

import pandas as pd
import requests

OUT = "/Users/willcahoon/playing_time_model/expansion/data/raw"
H = {"User-Agent": "Mozilla/5.0"}


def fetch(url):
    for a in range(5):
        try:
            r = requests.get(url, headers=H, timeout=40)
            r.raise_for_status()
            return pd.read_csv(io.StringIO(r.text))
        except Exception:
            if a == 4:
                raise
            time.sleep(6 * (a + 1))


oaa = []
for y in range(2016, 2026):
    df = fetch(f"https://baseballsavant.mlb.com/leaderboard/outs_above_average"
               f"?type=Fielder&year={y}&min=1&csv=true")
    df = df.rename(columns={"player_id": "mlbam_id"})
    keep = df[["mlbam_id", "outs_above_average", "fielding_runs_prevented"]].copy()
    keep["season"] = y
    oaa.append(keep)
    print(f"OAA {y}: {len(keep)}", flush=True)
    time.sleep(1)
oaa = pd.concat(oaa, ignore_index=True)
oaa = oaa.groupby(["mlbam_id", "season"], as_index=False).agg(
    oaa=("outs_above_average", "sum"), frv=("fielding_runs_prevented", "sum"))
oaa.to_parquet(f"{OUT}/savant_oaa.parquet", index=False)
print("saved savant_oaa:", oaa.shape, flush=True)

sp = []
for y in range(2015, 2026):
    df = fetch(f"https://baseballsavant.mlb.com/leaderboard/sprint_speed"
               f"?year={y}&min=10&csv=true")
    df = df.rename(columns={"player_id": "mlbam_id"})
    keep = df[["mlbam_id", "sprint_speed"]].copy()
    keep["season"] = y
    sp.append(keep)
    print(f"sprint {y}: {len(keep)}", flush=True)
    time.sleep(1)
sp = pd.concat(sp, ignore_index=True)
sp.to_parquet(f"{OUT}/sprint_speed.parquet", index=False)
print("saved sprint_speed:", sp.shape)
