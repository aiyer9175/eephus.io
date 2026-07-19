# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E02 — Manager history pull (Bucket 6 prerequisite).

statsapi /teams/{id}/coaches?season=Y carries the field manager
(job == "Manager"). Pulled per MLB team-season 2009-2026. This is the
end-of-season staff snapshot — midseason managerial changes are NOT
captured here (flagged; refine later via game-level boxscore managers if
the manager-effect research warrants it).

GM history is NOT available from statsapi — left as an external-collection
task (Wikipedia franchise GM tables / Baseball-Reference).

Output: data/raw/managers.parquet (team_id, season, manager_id, manager_name)
"""
import time

import pandas as pd
import requests

OUT = "/Users/willcahoon/playing_time_model/expansion/data/raw"


def get(url, params=None):
    for a in range(5):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception:
            if a == 4:
                raise
            time.sleep(6 * (a + 1))


rows = []
for season in range(2009, 2027):
    teams = get("https://statsapi.mlb.com/api/v1/teams",
                {"sportId": 1, "season": season})["teams"]
    for tm in teams:
        c = get(f"https://statsapi.mlb.com/api/v1/teams/{tm['id']}/coaches",
                {"season": season})
        for x in c.get("roster", []):
            if x.get("job") == "Manager":
                rows.append({"team_id": tm["id"], "season": season,
                             "manager_id": x["person"]["id"],
                             "manager_name": x["person"]["fullName"]})
        time.sleep(0.2)
    print(f"{season}: {len(rows)} manager rows", flush=True)

df = pd.DataFrame(rows).drop_duplicates()
df.to_parquet(f"{OUT}/managers.parquet", index=False)
print("saved managers:", df.shape)
