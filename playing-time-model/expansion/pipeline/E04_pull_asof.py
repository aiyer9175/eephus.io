# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E04 — As-of-date cumulative hitting (in-season updating support).

statsapi byDateRange gives season-start -> cutoff cumulative stats. Pulled at
two midseason cutoffs (May 31, Jun 30) per season 2017-2025 (skip 2020). This
is the information available at an in-season prediction date; the rest-of-
season target is full-season PA (spine) minus PA-to-date.

Output: data/raw/asof_hitting.parquet (mlbam_id, season, cutoff, pa_td, ab_td, g_td)
"""
import time

import pandas as pd
import requests

OUT = "/Users/willcahoon/playing_time_model/expansion/data/raw"
SEASONS = [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
CUTOFFS = ["05-31", "06-30"]


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
for season in SEASONS:
    for cut in CUTOFFS:
        offset = 0
        while True:
            d = get("https://statsapi.mlb.com/api/v1/stats",
                    {"stats": "byDateRange", "group": "hitting",
                     "season": season, "sportId": 1, "playerPool": "ALL",
                     "startDate": f"{season}-03-15", "endDate": f"{season}-{cut}",
                     "limit": 1000, "offset": offset})
            stats = d.get("stats", [])
            splits = stats[0]["splits"] if stats else []
            total = stats[0].get("totalSplits", 0) if stats else 0
            for s in splits:
                rows.append({"mlbam_id": s["player"]["id"], "season": season,
                             "cutoff": cut,
                             "pa_td": s["stat"].get("plateAppearances"),
                             "ab_td": s["stat"].get("atBats"),
                             "g_td": s["stat"].get("gamesPlayed")})
            offset += 1000
            if offset >= total or not splits:
                break
            time.sleep(0.3)
        print(f"{season} {cut}: {len(rows)}", flush=True)
        time.sleep(0.3)

pd.DataFrame(rows).to_parquet(f"{OUT}/asof_hitting.parquet", index=False)
print("saved asof_hitting:", len(rows))
