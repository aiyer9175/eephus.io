# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Build the game manifest: every completed regular-season game per level-season.

Game-centric extraction universe — every hitter in every game is captured,
so player coverage is complete by construction (the old player-centric
pipeline only reached ~21% of the union spine).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import API_BASE, DATA_RAW, SPORT_LEVELS, get_json, log_run, make_session


def fetch_season_schedule(session, sport_id: int, season: int) -> pd.DataFrame:
    params = {
        "sportId": sport_id,
        "season": season,
        "startDate": f"{season}-01-01",
        "endDate": f"{season}-12-31",
        "gameTypes": "R",
        "fields": "dates,date,games,gamePk,gameType,status,codedGameState,teams,team,id,name,"
                  "home,away,venue,officialDate,seriesDescription",
    }
    data = get_json(session, f"{API_BASE}/schedule", params=params, timeout=60)
    rows = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            if g.get("gameType") != "R":
                continue
            # F = final, O = game over
            if g.get("status", {}).get("codedGameState") not in ("F", "O"):
                continue
            rows.append({
                "gamePk": g["gamePk"],
                "date": g.get("officialDate") or day.get("date"),
                "sport_id": sport_id,
                "level": SPORT_LEVELS[sport_id],
                "season": season,
                "home_team_id": g.get("teams", {}).get("home", {}).get("team", {}).get("id"),
                "home_team": g.get("teams", {}).get("home", {}).get("team", {}).get("name"),
                "away_team_id": g.get("teams", {}).get("away", {}).get("team", {}).get("id"),
                "away_team": g.get("teams", {}).get("away", {}).get("team", {}).get("name"),
                "venue_id": g.get("venue", {}).get("id"),
                "venue": g.get("venue", {}).get("name"),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["gamePk"]).reset_index(drop=True)
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, nargs="+", default=[2021, 2022, 2023, 2024, 2025, 2026])
    ap.add_argument("--sports", type=int, nargs="+", default=[1, 11, 12, 13, 14, 16])
    args = ap.parse_args()

    session = make_session()
    out_dir = DATA_RAW / "game_manifest"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_frames = []
    for season in args.seasons:
        for sport_id in args.sports:
            df = fetch_season_schedule(session, sport_id, season)
            level = SPORT_LEVELS[sport_id]
            print(f"{season} {level:>4}: {len(df):5d} completed regular-season games", flush=True)
            if not df.empty:
                all_frames.append(df)

    manifest = pd.concat(all_frames, ignore_index=True)
    manifest = manifest.drop_duplicates(subset=["gamePk"]).reset_index(drop=True)
    out_path = out_dir / "game_manifest.parquet"
    manifest.to_parquet(out_path, index=False)
    print(f"\nTOTAL {len(manifest)} games -> {out_path}")
    log_run("game_manifest_v1", seasons=args.seasons, sports=args.sports,
            n_games=len(manifest), out=str(out_path))


if __name__ == "__main__":
    main()
