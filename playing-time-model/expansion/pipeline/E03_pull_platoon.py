# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E03 — Platoon-split + handedness pull (Bucket 13 / role work).

statsapi hitting statSplits with sitCodes vl/vr gives PA vs LHP / vs RHP per
player-season (pulled separately per code). Plus batSide (L/R/S) bulk via
/people?personIds. Together these define platoon usage: a player's exposure
to SAME-handed pitching vs the league baseline (~28% of PA are vs LHP).

Output:
  data/raw/platoon_splits.parquet  (mlbam_id, season, vs_hand, pa, ab)
  data/raw/bat_side.parquet        (mlbam_id, bat_side)
"""
import time

import pandas as pd
import requests

OUT = "/Users/willcahoon/playing_time_model/expansion/data/raw"


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


rows = []
for season in range(2009, 2026):
    for code in ("vl", "vr"):
        offset = 0
        while True:
            d = get("https://statsapi.mlb.com/api/v1/stats",
                    {"stats": "statSplits", "group": "hitting",
                     "season": season, "sportId": 1, "sitCodes": code,
                     "playerPool": "ALL", "limit": 1000, "offset": offset})
            stats = d.get("stats", [])
            splits = stats[0]["splits"] if stats else []
            total = stats[0].get("totalSplits", 0) if stats else 0
            for s in splits:
                rows.append({"mlbam_id": s["player"]["id"], "season": season,
                             "vs_hand": "L" if code == "vl" else "R",
                             "pa": s["stat"].get("plateAppearances"),
                             "ab": s["stat"].get("atBats")})
            offset += 1000
            if offset >= total or not splits:
                break
            time.sleep(0.3)
    print(f"{season}: {len(rows)} split rows", flush=True)
    time.sleep(0.3)

pl = pd.DataFrame(rows)
pl.to_parquet(f"{OUT}/platoon_splits.parquet", index=False)
print("saved platoon_splits:", pl.shape, flush=True)

# batSide bulk
ids = sorted(pl.mlbam_id.unique())
bs = []
for i in range(0, len(ids), 100):
    chunk = ids[i:i + 100]
    d = get("https://statsapi.mlb.com/api/v1/people",
            {"personIds": ",".join(map(str, chunk))})
    for p in d.get("people", []):
        bs.append({"mlbam_id": p["id"],
                   "bat_side": p.get("batSide", {}).get("code")})
    time.sleep(0.3)
pd.DataFrame(bs).to_parquet(f"{OUT}/bat_side.parquet", index=False)
print("saved bat_side:", len(bs))
