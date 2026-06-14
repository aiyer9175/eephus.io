# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 10 — Public projection pull (benchmark systems).

The FG projections API serves archived PRESEASON runs via type suffixes
(steamer_2023, zips_2024, ...). Vintage authenticated: steamer_2023 contains
Votto (PA 536) / Cabrera (PA 346), absent from current runs, and pre-debut
Chourio at 1 PA. NOTE the Team field is refreshed to current rosters — do
not use it; only the projection values are archival.

The plain `season` parameter is IGNORED by the API (returns current run) —
that was a trap. fangraphsdc/atc/thebat archives are member-only (HTTP 500
publicly); revisit via membership or Wayback member-API captures if needed.

Pulls: steamer_{2023,2024,2025}, zips_{2023,2024,2025} + current 2026
steamer/zips/fangraphsdc. Hitters only.

Output: data/raw/public_projections.parquet
"""
import time

import pandas as pd
import requests

OUT = "/Users/willcahoon/playing_time_model/data/raw"
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
KEEP = ["xMLBAMID", "PlayerName", "PA", "G", "AB", "wOBA", "WAR"]

PULLS = ([(f"steamer_{y}", "steamer", y) for y in range(2010, 2026)]
         + [(f"zips_{y}", "zips", y) for y in (2023, 2024, 2025)]
         + [(s, s, 2026) for s in ("steamer", "zips", "fangraphsdc")])

rows = []
for t, system, season in PULLS:
    r = None
    for attempt in range(4):
        try:
            r = requests.get("https://www.fangraphs.com/api/projections",
                             params={"type": t, "stats": "bat", "pos": "all"},
                             headers=H, timeout=60)
            if r.status_code == 500:   # archive year not served publicly
                print(t, "unavailable (500)", flush=True)
                r = None
                break
            r.raise_for_status()
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(10 * (attempt + 1))
    if r is None:
        continue
    df = pd.DataFrame(r.json())
    df = df[[c for c in KEEP if c in df.columns]].copy()
    df["system"] = system
    df["season"] = season
    rows.append(df)
    print(t, len(df), flush=True)
    time.sleep(2)

out = pd.concat(rows, ignore_index=True)
out = out.rename(columns={"xMLBAMID": "mlbam_id", "PA": "pa_proj",
                          "G": "g_proj", "wOBA": "woba_proj"})
out = out[pd.to_numeric(out.mlbam_id, errors="coerce").fillna(0) > 0]
out["mlbam_id"] = out.mlbam_id.astype(int)
# a few duplicate ids per system-season (two-way/encoding quirks): keep max-PA row
out = (out.sort_values("pa_proj")
          .drop_duplicates(["system", "season", "mlbam_id"], keep="last"))
out.to_parquet(f"{OUT}/public_projections.parquet", index=False)
print("saved:", out.shape)
