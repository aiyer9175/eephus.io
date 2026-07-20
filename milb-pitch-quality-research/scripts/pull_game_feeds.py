"""Step 3: pull the live-feed JSON (pitch-by-pitch data) for every sampled
game, cached and resumable.

Each game is written to data_cache/{level}/{gamePk}.json. Already-cached
games are skipped, so this script can be re-run safely if interrupted.

Usage: python pull_game_feeds.py [--limit N] [--sample-suffix SUFFIX]
  --limit N            only pull the first N *missing* games per level (for
                        smoke testing before running the full pilot).
  --sample-suffix S    read data_cache/samples/{level}_{S}.json instead of
                        {level}.json (e.g. "team_stratified" for Phase 1B's
                        sample, built by phase1b/sample_team_stratified.py).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    LEVELS,
    DATA_CACHE,
    DEFAULT_DELAY_SECONDS,
    cache_path,
    game_feed_url,
    get_json,
    load_json,
    save_json,
)


def pull_level(level: str, limit: int | None, suffix: str = "") -> tuple[int, int]:
    filename = f"{level}_{suffix}.json" if suffix else f"{level}.json"
    samples_path = DATA_CACHE / "samples" / filename
    samples = load_json(samples_path)

    pulled = 0
    skipped = 0
    for s in samples:
        game_pk = s["gamePk"]
        out_path = cache_path(level, game_pk)
        if out_path.exists():
            skipped += 1
            continue
        if limit is not None and pulled >= limit:
            break
        feed = get_json(game_feed_url(game_pk))
        save_json(out_path, feed)
        pulled += 1
        time.sleep(DEFAULT_DELAY_SECONDS)

    return pulled, skipped


def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        limit = int(sys.argv[idx + 1])

    suffix = ""
    if "--sample-suffix" in sys.argv:
        idx = sys.argv.index("--sample-suffix")
        suffix = sys.argv[idx + 1]

    for level in LEVELS:
        print(f"Pulling game feeds for {level}" + (f" (limit={limit})" if limit else "") + "...")
        pulled, skipped = pull_level(level, limit, suffix)
        print(f"  {level}: pulled {pulled} new, {skipped} already cached")


if __name__ == "__main__":
    main()
