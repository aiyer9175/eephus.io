"""Step 1: pull the full 2025 regular-season schedule for each MiLB level and
enumerate the distinct venues that hosted games.

Output: data_cache/schedules/{level}.json -- one row per completed game with
gamePk, venue id/name, officialDate.

Usage: python pull_schedule.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LEVELS, SEASON, DATA_CACHE, get_json, save_json, schedule_url  # noqa: E402


def pull_level_schedule(level: str, sport_id: int) -> list[dict]:
    payload = get_json(schedule_url(sport_id))
    rows = []
    for date_entry in payload.get("dates", []):
        for game in date_entry.get("games", []):
            status = game.get("status", {})
            if status.get("codedGameState") != "F":
                continue  # only completed games are useful for a coverage audit
            venue = game.get("venue", {})
            rows.append(
                {
                    "gamePk": game["gamePk"],
                    "officialDate": game.get("officialDate", date_entry.get("date")),
                    "venue_id": venue.get("id"),
                    "venue_name": venue.get("name"),
                    "home_team": game.get("teams", {}).get("home", {}).get("team", {}).get("name"),
                    "away_team": game.get("teams", {}).get("away", {}).get("team", {}).get("name"),
                }
            )
    return rows


def main() -> None:
    schedules_dir = DATA_CACHE / "schedules"
    for level, sport_id in LEVELS.items():
        print(f"Pulling {SEASON} schedule for {level} (sportId={sport_id})...")
        rows = pull_level_schedule(level, sport_id)
        out_path = schedules_dir / f"{level}.json"
        save_json(out_path, rows)
        venues = {r["venue_id"] for r in rows if r["venue_id"] is not None}
        print(f"  {level}: {len(rows)} completed games across {len(venues)} venues -> {out_path}")


if __name__ == "__main__":
    main()
