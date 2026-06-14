# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 1 — Usage spine pull.

Pulls MLB per-player-season usage from statsapi for 2000-2026:
  - hitting:  G, PA, AB (one row per player-team stint)
  - fielding: G, GS, innings per position (one row per player-team-position stint)

These are the raw materials for the core targets (PA, games, starts) and for
Historical Usage / Defensive Flexibility / Position Lifecycle features.

Outputs:
  data/raw/usage_hitting.parquet
  data/raw/usage_fielding.parquet

Stint-level rows are kept as-is (traded players have one row per team);
aggregation to player-season happens in 02_build_spine.py.
"""
import time

import pandas as pd
import requests

BASE = "https://statsapi.mlb.com/api/v1/stats"
SEASONS = range(2000, 2027)
LIMIT = 1000
OUT = "/Users/willcahoon/playing_time_model/data/raw"


def pull_group(season: int, group: str) -> list[dict]:
    rows, offset = [], 0
    while True:
        for attempt in range(4):
            try:
                r = requests.get(BASE, params={
                    "stats": "season", "group": group, "season": season,
                    "sportId": 1, "playerPool": "ALL",
                    "limit": LIMIT, "offset": offset}, timeout=30)
                r.raise_for_status()
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        stats = r.json().get("stats", [])
        splits = stats[0]["splits"] if stats else []
        total = stats[0].get("totalSplits", len(splits)) if stats else 0
        for s in splits:
            st = s["stat"]
            row = {
                "season": season,
                "mlbam_id": s["player"]["id"],
                "player_name": s["player"].get("fullName"),
                "team_id": s.get("team", {}).get("id"),
                "team_name": s.get("team", {}).get("name"),
                "num_teams": s.get("numTeams"),
                "games": st.get("gamesPlayed"),
            }
            if group == "hitting":
                row.update(pa=st.get("plateAppearances"), ab=st.get("atBats"))
            else:
                row.update(
                    position=s.get("position", {}).get("abbreviation"),
                    games_started=st.get("gamesStarted"),
                    innings=st.get("innings"),
                )
            rows.append(row)
        offset += LIMIT
        if offset >= total or not splits:
            return rows
        time.sleep(0.4)


def main():
    for group, fname in [("hitting", "usage_hitting"), ("fielding", "usage_fielding")]:
        all_rows = []
        for season in SEASONS:
            rows = pull_group(season, group)
            all_rows.extend(rows)
            print(f"{group} {season}: {len(rows)} rows", flush=True)
            time.sleep(0.4)
        df = pd.DataFrame(all_rows)
        df.to_parquet(f"{OUT}/{fname}.parquet", index=False)
        print(f"saved {fname}: {df.shape}", flush=True)


if __name__ == "__main__":
    main()
