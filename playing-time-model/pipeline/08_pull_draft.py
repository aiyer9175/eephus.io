# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 8a — Draft pedigree pull.

statsapi draft endpoint: every pick 1990-2025 with overall pick number,
round, and signing bonus, keyed by MLBAM person id. Unlike prospect lists,
this pedigree source exists for EVERY training year and is timestamp-valid
forever (draft facts never change after draft day).

Output: data/raw/draft_history.parquet
"""
import time

import pandas as pd
import requests

OUT = "/Users/willcahoon/playing_time_model/data/raw"

rows = []
for year in range(1990, 2026):
    for attempt in range(4):
        try:
            r = requests.get(f"https://statsapi.mlb.com/api/v1/draft/{year}",
                             timeout=30)
            r.raise_for_status()
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    for rd in r.json()["drafts"]["rounds"]:
        for p in rd.get("picks", []):
            pid = p.get("person", {}).get("id")
            if pid is None:
                continue
            rows.append({
                "draft_year": year,
                "mlbam_id": pid,
                "round": p.get("pickRound"),
                "overall_pick": p.get("pickNumber"),
                "signing_bonus": pd.to_numeric(p.get("signingBonus"),
                                               errors="coerce"),
                "signed": p.get("isPass") is not True,
            })
    print(year, len(rows), flush=True)
    time.sleep(0.4)

df = pd.DataFrame(rows)
# keep the LAST time a player was drafted (re-drafts overwrite earlier ones;
# the pick that led to signing is the relevant pedigree)
df = (df.sort_values(["mlbam_id", "draft_year"])
        .groupby("mlbam_id").last().reset_index())
df.to_parquet(f"{OUT}/draft_history.parquet", index=False)
print("saved:", df.shape)
