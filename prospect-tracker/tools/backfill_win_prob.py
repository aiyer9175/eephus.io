# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Parallel cache-warmer for the StatsAPI winProbability feed - the REM+
historical backfill (leverage-variant bake-off + raw-WPA baseline + AAV market
check all need multi-season gmLI / WPA).

Fetches and caches `/game/{pk}/winProbability` for every FINAL game across the
given seasons so mlb_leverage.fetch_season_leverage(year) then runs from the
on-disk cache. RESUMABLE (already-cached games are skipped) and BEST-EFFORT
(a game that 404s / errors is skipped, never aborts). Concurrency is bounded and
rides feed_cache's hardened, 429-retrying session.

Run: python tools/backfill_win_prob.py [season ...]   (default: 2018-2025 ex-2020)
"""
from __future__ import annotations

import concurrent.futures as cf
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mlb_leverage as ml  # noqa: E402

DEFAULT_SEASONS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
WORKERS = 12


def warm(seasons: list[int], workers: int = WORKERS) -> None:
    tasks: list[tuple[int, str]] = []
    for y in seasons:
        try:
            pks = ml.season_game_pks(y)
        except Exception as e:
            print(f"  schedule {y} failed: {e}", flush=True)
            continue
        print(f"  {y}: {len(pks)} final games", flush=True)
        tasks.extend(pks)

    todo = [(pk, gd) for (pk, gd) in tasks
            if not (ml.CACHE_DIR / f"{pk}.json").exists()]
    print(f"  total {len(tasks)} games across {len(seasons)} seasons; "
          f"{len(todo)} to fetch ({len(tasks) - len(todo)} already cached)", flush=True)

    def _one(pkgd):
        pk, gd = pkgd
        try:
            ml.get_win_probability(pk, game_date=gd)
            return True
        except Exception:
            return False

    done = fail = 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for ok in ex.map(_one, todo):
            done += 1
            if not ok:
                fail += 1
            if done % 500 == 0:
                print(f"    {done}/{len(todo)} fetched ({fail} failed)", flush=True)
    print(f"  DONE: {done} fetched this run, {fail} failed", flush=True)


if __name__ == "__main__":
    yrs = [int(a) for a in sys.argv[1:]] or DEFAULT_SEASONS
    warm(yrs)
