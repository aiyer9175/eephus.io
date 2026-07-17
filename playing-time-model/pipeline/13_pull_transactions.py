# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 13a — League-wide transaction log pull.

statsapi transactions endpoint, month windows 2002-01 .. 2026-06. Dated
option/recall/select/outright/DFA/release/trade events for ALL players —
the raw material for timestamp-valid reconstruction of 40-man status,
option churn, and offseason roster context (the information gap vs
preseason public projections identified in Module 11).

Output: data/raw/transactions.parquet
"""
import time

import pandas as pd
import requests

OUT = "/Users/willcahoon/playing_time_model/data/raw"

rows = []
for year in range(2002, 2027):
    for month in range(1, 13):
        if year == 2026 and month > 6:
            break
        start = f"{year}-{month:02d}-01"
        end = f"{year}-{month:02d}-{28 if month == 2 else 30}"
        for attempt in range(5):
            try:
                r = requests.get(
                    "https://statsapi.mlb.com/api/v1/transactions",
                    params={"startDate": start, "endDate": end}, timeout=60)
                r.raise_for_status()
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(8 * (attempt + 1))
        for t in r.json().get("transactions", []):
            rows.append({
                "date": t.get("date"),
                "type_code": t.get("typeCode"),
                "type_desc": t.get("typeDesc"),
                "mlbam_id": t.get("person", {}).get("id"),
                "from_team_id": t.get("fromTeam", {}).get("id"),
                "to_team_id": t.get("toTeam", {}).get("id"),
                "description": t.get("description"),
            })
        time.sleep(0.3)
    print(year, len(rows), flush=True)

df = pd.DataFrame(rows).drop_duplicates()
df.to_parquet(f"{OUT}/transactions.parquet", index=False)
print("saved:", df.shape)
