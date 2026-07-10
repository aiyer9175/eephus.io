# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Shared, game_pk-keyed cache for MLB Stats API `/feed/live` payloads.

Several modules (`statcast_metrics`, `zone_metrics`, `export_aaa_ball_by_ball`,
`vaa`) each used to fetch and parse the SAME `/feed/live` game feed into their
own private `.cache/<module>/` directory keyed by an md5 of the URL. A single
AAA game that three prospects appeared in was downloaded and stored three
times. This module collapses all of that onto one on-disk dir
(`.cache/game_feeds/<game_pk>.json`) so each unique game is fetched once.

Two properties make this safe and fast:

1. **Completed game feeds are immutable.** A finished game's box score never
   changes, so a feed reached via a game LOG (logs only list played games) can
   be cached effectively forever. `get_game_feed` decides the TTL from the
   game's date: games older than `RECENT_WINDOW_DAYS` get `FINAL_TTL`
   (~10 years); only very recent games keep the 24h TTL that absorbs stat
   corrections and suspended-then-resumed games. This turns a monthly,
   cold-every-time run into an incremental one — only the trailing ~month of
   new games is ever re-fetched.

2. **The raw payload is module-agnostic.** Every consumer reads from the same
   `gameData` / `liveData.plays.allPlays` shape, so one cached file serves all.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_log = logging.getLogger(__name__)

MLB_GAME_FEED_API = "https://statsapi.mlb.com/api/v1.1/game"

CACHE_DIR = Path(__file__).parent / ".cache" / "game_feeds"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Games this many days old (or older) are treated as final/immutable and
# cached with FINAL_TTL. Anything newer keeps the short TTL so late
# finalization, stat corrections, and suspended-then-resumed games are
# picked up on the next run.
RECENT_WINDOW_DAYS = 3
SHORT_TTL = 86400          # 24h — recent / in-flux games
FINAL_TTL = 3650 * 86400   # ~10y — completed, immutable games

# Hardened session: unlike the per-module sessions this one retries 429
# (rate-limit) responses with backoff and honors Retry-After, so callers can
# raise their worker counts on a cold build without unretried failures.
SESSION = requests.Session()
_retries = Retry(
    total=4,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset({"GET"}),
    respect_retry_after_header=True,
)
_adapter = HTTPAdapter(max_retries=_retries, pool_connections=80, pool_maxsize=80)
SESSION.mount("https://", _adapter)
SESSION.mount("http://", _adapter)

# Small politeness delay before a *network* fetch (cache hits skip it).
_FETCH_SLEEP = 0.04


def _ttl_for_date(game_date: str | None) -> int:
    """Pick the cache TTL from a game's date string ('YYYY-MM-DD').

    Older-than-RECENT_WINDOW_DAYS → FINAL_TTL (immutable). Unknown or recent
    dates fall back to SHORT_TTL, which is always correct (just less cached).
    """
    if not game_date:
        return SHORT_TTL
    try:
        gd = date.fromisoformat(str(game_date)[:10])
    except (ValueError, TypeError):
        return SHORT_TTL
    age_days = (date.today() - gd).days
    return FINAL_TTL if age_days >= RECENT_WINDOW_DAYS else SHORT_TTL


def get_game_feed(game_pk: int, *, game_date: str | None = None) -> dict:
    """Return the `/feed/live` payload for one game, cached on disk by game_pk.

    `game_date` (the game's 'YYYY-MM-DD', available for free from the game log
    split that yielded this game_pk) selects the TTL. Omit it and the feed is
    cached for SHORT_TTL only — correct but not permanent.
    """
    game_pk = int(game_pk)
    path = CACHE_DIR / f"{game_pk}.json"
    ttl = _ttl_for_date(game_date)
    if path.exists() and time.time() - path.stat().st_mtime <= ttl:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass  # corrupt/partial cache file — re-fetch below
    time.sleep(_FETCH_SLEEP)
    resp = SESSION.get(f"{MLB_GAME_FEED_API}/{game_pk}/feed/live", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)  # atomic: never leave a half-written feed for a concurrent reader
    return data


def prune_old_feeds(max_age_days: int = 400, *, cache_dir: Path | None = None) -> int:
    """Delete cached feed files whose mtime is older than max_age_days.

    With FINAL_TTL feeds never expire by TTL, so this keeps the permanent cache
    bounded: a final game keeps its original write mtime, so stale seasons age
    out while anything re-touched this run survives. Returns the count removed.
    """
    target = cache_dir or CACHE_DIR
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    try:
        entries = list(target.glob("*.json"))
    except OSError:
        return 0
    for p in entries:
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        _log.info("feed cache: pruned %d feeds older than %dd from %s",
                  removed, max_age_days, target.name)
    return removed
