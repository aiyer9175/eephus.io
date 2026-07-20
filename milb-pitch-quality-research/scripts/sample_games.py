"""Step 2: venue-stratified game sampling.

For each level, group the season schedule by venue and pick up to 3 games per
venue -- one each from early (Apr-May), mid (Jun-Jul), and late (Aug-Sep)
season -- so a venue whose tracking install changed mid-season isn't
represented by a single snapshot. Selection within a window is deterministic
(the median-dated game in that window), not random, so re-running this script
reproduces the same sample.

Output: data_cache/samples/{level}.json -- list of {gamePk, venue_id,
venue_name, officialDate, window}.

Usage: python sample_games.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LEVELS, DATA_CACHE, load_json, save_json  # noqa: E402

WINDOWS = {
    "early": (date(2025, 4, 1), date(2025, 5, 31)),
    "mid": (date(2025, 6, 1), date(2025, 7, 31)),
    "late": (date(2025, 8, 1), date(2025, 9, 30)),
}


def in_window(d: date, window: tuple[date, date]) -> bool:
    return window[0] <= d <= window[1]


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def pick_median(games: list[dict]) -> dict:
    games_sorted = sorted(games, key=lambda g: g["officialDate"])
    return games_sorted[len(games_sorted) // 2]


def sample_level(level: str) -> list[dict]:
    schedule_path = DATA_CACHE / "schedules" / f"{level}.json"
    rows = load_json(schedule_path)

    by_venue = defaultdict(list)
    for r in rows:
        if r["venue_id"] is None:
            continue
        by_venue[r["venue_id"]].append(r)

    sampled = []
    for venue_id, games in by_venue.items():
        venue_name = games[0]["venue_name"]
        for window_name, window in WINDOWS.items():
            in_win = [g for g in games if in_window(parse_date(g["officialDate"]), window)]
            if not in_win:
                continue
            chosen = pick_median(in_win)
            sampled.append(
                {
                    "gamePk": chosen["gamePk"],
                    "venue_id": venue_id,
                    "venue_name": venue_name,
                    "officialDate": chosen["officialDate"],
                    "window": window_name,
                }
            )
    return sampled


def main() -> None:
    samples_dir = DATA_CACHE / "samples"
    total = 0
    for level in LEVELS:
        sampled = sample_level(level)
        out_path = samples_dir / f"{level}.json"
        save_json(out_path, sampled)
        n_venues = len({s["venue_id"] for s in sampled})
        print(f"{level}: {len(sampled)} games sampled across {n_venues} venues -> {out_path}")
        total += len(sampled)
    print(f"Total pilot games across all levels: {total}")


if __name__ == "__main__":
    main()
