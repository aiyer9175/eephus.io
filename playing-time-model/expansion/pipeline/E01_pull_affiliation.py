# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E01 — Minor-league org affiliation pull.

For the org-behavior research we need (player, season, level, parent_org)
for upper-minors hitters. statsapi minors hitting splits carry the team id;
/teams?sportId=N&season=Y maps each minor team -> parentOrgId. AAA=11, AA=12.

Output:
  data/raw/minors_affiliation.parquet   (mlbam_id, season, sport, team_id, pa)
  data/raw/team_parent_org.parquet      (team_id, season, parent_org_id, name)
"""
import time

import pandas as pd
import requests

OUT = "/Users/willcahoon/playing_time_model/expansion/data/raw"
SPORTS = {11: "AAA", 12: "AA"}
SEASONS = range(2009, 2026)


def get(url, params):
    for a in range(5):
        try:
            r = requests.get(url, params=params, timeout=40)
            r.raise_for_status()
            return r.json()
        except Exception:
            if a == 4:
                raise
            time.sleep(6 * (a + 1))


# team -> parent org map
org_rows = []
for season in SEASONS:
    for sid in SPORTS:
        d = get("https://statsapi.mlb.com/api/v1/teams",
                {"sportId": sid, "season": season})
        for t in d.get("teams", []):
            org_rows.append({"team_id": t["id"], "season": season,
                             "sport": sid,
                             "parent_org_id": t.get("parentOrgId"),
                             "parent_org_name": t.get("parentOrgName")})
    time.sleep(0.3)
pd.DataFrame(org_rows).to_parquet(f"{OUT}/team_parent_org.parquet", index=False)
print("saved team_parent_org:", len(org_rows), flush=True)

# player-season affiliation
rows = []
for season in SEASONS:
    for sid in SPORTS:
        offset = 0
        while True:
            d = get("https://statsapi.mlb.com/api/v1/stats",
                    {"stats": "season", "group": "hitting", "season": season,
                     "sportId": sid, "playerPool": "ALL",
                     "limit": 1000, "offset": offset})
            stats = d.get("stats", [])
            splits = stats[0]["splits"] if stats else []
            total = stats[0].get("totalSplits", 0) if stats else 0
            for s in splits:
                rows.append({"mlbam_id": s["player"]["id"], "season": season,
                             "sport": sid,
                             "team_id": s.get("team", {}).get("id"),
                             "pa": s["stat"].get("plateAppearances")})
            offset += 1000
            if offset >= total or not splits:
                break
            time.sleep(0.3)
    print(f"{season}: {len(rows)} rows", flush=True)
    time.sleep(0.3)

pd.DataFrame(rows).to_parquet(f"{OUT}/minors_affiliation.parquet", index=False)
print("saved minors_affiliation:", len(rows))
