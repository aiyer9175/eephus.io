# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 14a — Opening Day roster pull.

For each team-season 2004-2026 (2020 skipped, COVID):
  40-man roster as of Mar 25, active roster as of Apr 2.
Roster entries carry person + position + status — gives 40-man/Opening Day
status and same-position depth at the prediction date.

Output: data/raw/od_rosters.parquet
"""
import time

import pandas as pd
import requests

OUT = "/Users/willcahoon/playing_time_model/data/raw"
BASE = "https://statsapi.mlb.com/api/v1"


def get(url, params=None):
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == 4:
                raise
            time.sleep(6 * (attempt + 1))


rows = []
for year in range(2004, 2027):
    if year == 2020:
        continue
    teams = get(f"{BASE}/teams", {"sportId": 1, "season": year})["teams"]
    for tm in teams:
        for rtype, date in [("40Man", f"{year}-03-25"),
                            ("active", f"{year}-04-02")]:
            d = get(f"{BASE}/teams/{tm['id']}/roster",
                    {"rosterType": rtype, "date": date})
            for e in d.get("roster", []):
                rows.append({
                    "target_year": year,
                    "team_id": tm["id"],
                    "roster_type": rtype,
                    "mlbam_id": e.get("person", {}).get("id"),
                    "position": e.get("position", {}).get("abbreviation"),
                    "status": e.get("status", {}).get("code"),
                })
            time.sleep(0.25)
    print(year, len(rows), flush=True)

df = pd.DataFrame(rows).drop_duplicates()
df.to_parquet(f"{OUT}/od_rosters.parquet", index=False)
print("saved:", df.shape)
