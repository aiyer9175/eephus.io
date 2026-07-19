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
import os
import tempfile
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


# detailedState values that mean the game IS complete, and ones that mean it is
# explicitly NOT (a suspended/postponed game gets resumed or replayed later).
_FINAL_DETAILED = {"Final", "Game Over", "Completed Early"}
_NONFINAL_DETAILED = {"Suspended", "Postponed"}


def _looks_final(data) -> bool:
    """Best-effort: does this feed's OWN status say the game is truly complete?

    FINAL_TTL is chosen from the game's date alone, but date is not proof of
    finality: a game suspended (e.g. rain) and resumed days later keeps its
    original date, so a feed cached mid-suspension would be frozen under the
    ~10y FINAL_TTL and serve a partial play list for years after the game
    actually completes. This gate lets get_game_feed trust FINAL_TTL only for a
    feed whose status is genuinely final. Unknown/odd shapes return False
    ('not proven final' -> re-fetch), which is safe (just a network cost)."""
    if not isinstance(data, dict):
        return False
    game_data = data.get("gameData")
    status = (game_data or {}).get("status") if isinstance(game_data, dict) else None
    if not isinstance(status, dict):
        return False
    detailed = status.get("detailedState")
    if detailed in _NONFINAL_DETAILED:
        return False
    if status.get("abstractGameState") == "Final":
        return True
    if detailed in _FINAL_DETAILED:
        return True
    return status.get("codedGameState") in {"F", "O"}


def atomic_write_json(path: Path, data) -> None:
    """Write `data` as JSON to `path` atomically and concurrency-safely.

    Each writer gets its OWN temp file in the same directory (so os.replace is a
    same-filesystem atomic rename) - never a per-game shared name that two
    same-game writers would race on and corrupt / crash renaming. A lost race
    (a peer already promoted a valid file onto `path`) is treated as success
    rather than an unhandled error. Shared so statcast_metrics et al. reuse it.
    """
    payload = json.dumps(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmpname = tempfile.mkstemp(dir=str(path.parent),
                                   prefix=f"{path.stem}.", suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmpname, path)
    except OSError:
        # Lost race or transient FS error: if a peer already produced a valid
        # file at `path`, treat it as success; otherwise clean up and re-raise.
        try:
            os.unlink(tmpname)
        except OSError:
            pass
        if not path.exists():
            raise


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
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cached = None  # corrupt/partial cache file — re-fetch below
        if cached is not None:
            # A long FINAL_TTL is only trustworthy for a feed that is actually
            # final; a suspended-then-resumed game keeps its original date, so
            # date-derived TTL alone would serve a stale partial feed for years.
            # SHORT_TTL (recent games) is served within its 24h window as before.
            if ttl < FINAL_TTL or _looks_final(cached):
                return cached
    time.sleep(_FETCH_SLEEP)
    resp = SESSION.get(f"{MLB_GAME_FEED_API}/{game_pk}/feed/live", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Writer-unique temp + atomic replace: never leave a half-written feed for a
    # concurrent reader, and never race two same-game writers on one tmp name.
    atomic_write_json(path, data)
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
