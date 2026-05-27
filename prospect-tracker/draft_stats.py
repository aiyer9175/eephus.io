# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""FG player-page stats scraper for DRAFT (college + HS) prospects.

FanGraphs hosts amateur stats at the same `/players/<slug>/<playerId>/
stats/batting|pitching` URL pattern used for overseas players. For
college players the LEVEL column carries conference codes (e.g. SEC,
ACC, B12, AAC) instead of NPB/KBO/CPBL; for HS / showcase players
the level reads "HS" / "Cape Cod" / "USA U18" / etc.

The HTML structure + cell-cleaning logic is identical to
`overseas_stats` — we reuse `scrape_fg_player_stats` from that module
and just filter the output to amateur-level rows + upsert into
`draft_statlines` (instead of `overseas_statlines`).

Speed: v31.7 — concurrent fetching via ThreadPoolExecutor (matches
the pattern used by `scrapers.bulk_fetch_*`). Each FG page is one
HTTP roundtrip (~300ms cached / ~1.5s uncached); previously the
sequential loop was the bottleneck on a full refresh.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from overseas_stats import scrape_fg_player_stats
from storage import load_draft_players, upsert_draft_statlines

log = logging.getLogger(__name__)


# Levels we consider "draft prospect" (vs overseas pro). FG tags
# college conferences with their conference abbrev; HS / showcase /
# summer-league rows surface a handful of distinct level codes.
_DRAFT_LEVEL_PREFIXES = (
    # College conferences (high-major + mid-major selection)
    "SEC", "ACC", "B12", "BIG", "AAC", "PAC", "P12", "MAC", "MWC",
    "C-USA", "CUSA", "AS", "ASUN", "CAA", "SoCon", "WCC", "WAC",
    "Sun Belt", "OVC", "Horizon", "MVC", "Patriot", "Ivy", "MEAC",
    "SWAC", "Big West", "Big South", "NEC", "Summit", "Atlantic 10",
    "A10", "America East", "Metro Atlantic", "MAAC", "Big East",
    # Catch-all college aggregates
    "NCAA", "DI", "D-I", "NAIA", "JUCO",
    # HS + showcase / summer-league
    "HS", "Cape Cod", "Northwoods", "Coastal Plain", "Prospect League",
    "Appalachian", "USA U18", "USA U17", "Perfect Game",
    # International amateur tournaments
    "WBSC", "Pan Am", "World Cup",
)


def _is_draft_level(level: str | None) -> bool:
    """True if the FG-tagged level reads as a college / HS / showcase
    row (vs an overseas pro level like NPB/KBO/CPBL or a MiLB level
    like AAA/AA/A+ which are already in the main statlines table)."""
    if not level:
        return False
    s = str(level).strip()
    # Reject MiLB / MLB rows — those flow through the main statlines
    # path (FG player pages also list those, but for already-drafted
    # players who later pro'd).
    if s in {"MLB", "AAA", "AA", "A+", "A", "CPX", "DSL", "Rk", "Rk2"}:
        return False
    # Reject the four overseas codes; they belong in overseas_statlines.
    if s in {"NPB", "NPBF", "KBO", "CPBL", "Cuba", "TWN"}:
        return False
    # Accept anything that starts with one of our known draft-side
    # prefixes (case-sensitive — FG uses consistent casing).
    for prefix in _DRAFT_LEVEL_PREFIXES:
        if s.startswith(prefix):
            return True
    # Conservative fallback: accept any level containing common
    # college markers so a rare conference label doesn't drop the row.
    s_low = s.lower()
    if any(tag in s_low for tag in ("college", "conf", "ncaa", "naia",
                                     "juco", " hs", "high school")):
        return True
    return False


def _fetch_one(pk_player_id: tuple[str, str], force: bool = False) -> tuple[str, list[dict]]:
    """Worker for the thread pool. Returns (player_key, rows)."""
    pk, fg_id = pk_player_id
    try:
        rows = scrape_fg_player_stats(fg_id, force=force)
    except Exception:
        log.exception("draft_stats fetch crashed for %s (%s)", pk, fg_id)
        return (pk, [])
    return (pk, rows)


def refresh_draft_stats(force: bool = False,
                         max_players: int | None = None,
                         draft_year: int | None = None,
                         workers: int = 8) -> int:
    """For every draft_player with an fg_player_id, scrape their FG
    page and upsert per-season stats into draft_statlines.

    v31.7 — Concurrent: fetches up to `workers` pages in parallel via
    a ThreadPoolExecutor (default 8; FG seems tolerant to this rate
    when paired with the on-disk cache). Set `workers=1` for the
    sequential fallback.

    Returns the count of season-rows inserted. Idempotent.
    """
    players = load_draft_players(draft_year=draft_year)
    targets = [(pk, p["fg_player_id"]) for pk, p in players.items()
                if p.get("fg_player_id")]
    if max_players is not None:
        targets = targets[:max_players]
    if not targets:
        log.info("refresh_draft_stats: no draft players with FG IDs (year=%s)",
                 draft_year)
        return 0

    log.info("refresh_draft_stats: fetching %d draft prospects (%d workers)",
             len(targets), workers)

    results: dict[str, list[dict]] = {}
    if workers <= 1:
        # Sequential fallback.
        for t in targets:
            pk, rows = _fetch_one(t, force=force)
            results[pk] = rows
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_fetch_one, t, force): t[0] for t in targets}
            for fut in as_completed(futures):
                pk, rows = fut.result()
                results[pk] = rows

    total = 0
    for pk, rows in results.items():
        if not rows:
            continue
        payloads = []
        for r in rows:
            season = r.get("season")
            league = r.get("level")
            if not (season and league):
                continue
            # Keep only draft-side (amateur) rows; overseas-pro + MiLB
            # rows for the same FG ID go to their respective tables
            # via the existing pipelines.
            if not _is_draft_level(league):
                continue
            # Drop FG's synthetic non-season rows (projections, ROS,
            # spring training).
            if league in {"ROS", "PROJ", "ST"}:
                continue
            payload = {k: v for k, v in r.items() if not k.startswith("_")}
            payloads.append({
                "player_key": pk,
                "season":     season,
                "league":     league,
                "team":       r.get("team"),
                "payload":    payload,
            })
        if payloads:
            n = upsert_draft_statlines(payloads)
            total += n
    log.info("refresh_draft_stats: %d total season rows upserted across %d players",
             total, len(targets))
    return total
