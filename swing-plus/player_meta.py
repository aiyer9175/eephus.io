# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
player_meta.py — build player_meta.parquet with team + position from MLB Stats API.

Run:
    python player_meta.py
Produces:
    data/processed/player_meta.parquet  (batter, team, position)
"""

import json
import urllib.request
from pathlib import Path

import pandas as pd

PROC = Path(__file__).parent / "data" / "processed"
OUT = PROC / "player_meta.parquet"

POS_ORDER = {"C": 0, "1B": 1, "2B": 2, "SS": 3, "3B": 4,
             "LF": 5, "CF": 6, "RF": 7, "OF": 8, "DH": 9,
             "SP": 10, "RP": 11, "P": 12}


def team_abbr_map(season: int) -> dict:
    """The season-stats split only carries team id + name (no abbreviation),
    so build an id -> abbreviation map from the teams endpoint."""
    url = f"https://statsapi.mlb.com/api/v1/teams?sportId=1&season={season}"
    data = json.loads(urllib.request.urlopen(url, timeout=30).read())
    return {t["id"]: t.get("abbreviation", "") for t in data.get("teams", [])}


def pull(season: int = 2026) -> pd.DataFrame:
    abbr = team_abbr_map(season)
    url = (f"https://statsapi.mlb.com/api/v1/stats?stats=season&group=hitting"
           f"&season={season}&sportId=1&playerPool=ALL&limit=2000")
    data = json.loads(urllib.request.urlopen(url, timeout=30).read())
    rows = []
    for s in data["stats"][0]["splits"]:
        tid = s.get("team", {}).get("id")
        rows.append({
            "batter": int(s["player"]["id"]),
            "name": s["player"]["fullName"],
            "team": abbr.get(tid, "") if tid is not None else "",
            "position": s.get("position", {}).get("abbreviation", ""),
        })
    df = (pd.DataFrame(rows)
          .sort_values("batter")
          .drop_duplicates("batter", keep="first")
          .reset_index(drop=True))
    df.to_parquet(OUT, index=False)
    print(f"saved {OUT.name}: {len(df)} players")
    return df


if __name__ == "__main__":
    pull()
