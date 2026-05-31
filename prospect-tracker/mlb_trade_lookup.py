# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""v31.8 — MLB trade-player resolver.

Walks every trade in the `trades` table, parses the description for
player names, and for any name NOT already in our actives / grads /
inactives database, fetches that player's career WAR + position via
the MLB Stats API + pybaseball's BBRef WAR tables. Results are
cached in `mlb_trade_players` so the trade audit on the frontend
can value Brendan-Donovan-style MLB veterans involved in prospect
trades (previously they showed up as "PTBNL / no tracked players"
since they weren't tracked-prospect data).

This is a one-time-per-trade cost: subsequent runs only fetch new
names. The MLB Stats API search endpoint is the same one stats.py's
`_search_mlbam_via_api` uses, so we get consistent name resolution
across the project.

v31.8b — Pipeline-safe defaults:
  * `max_new` defaults to 50 per run so first runs don't try to
    resolve 600+ names + download the 5MB BBRef CSV in one stall.
    Subsequent runs continue chipping through the backlog.
  * `time_budget_seconds` hard cap (default 90s) — the resolver
    aborts and returns whatever it's resolved so far if the budget
    is exhausted, so the rest of the pipeline keeps moving.
  * pybaseball BBRef download is wrapped in a timeout + try/except
    that downgrades to "skip WAR backfill" instead of hanging.
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from storage import (
    connect as _storage_connect,
    load_mlb_trade_players,
    load_trades,
    upsert_mlb_trade_player,
)


def _load_known_tracked_names() -> set[str]:
    """Return name-slug set for every player_name currently in the
    snapshots / draft_players / overseas_players tables (anything we
    consider 'tracked'). Used to skip resolution for names already in
    our database."""
    names: set[str] = set()
    queries = (
        "SELECT DISTINCT player_name FROM snapshots WHERE player_name IS NOT NULL",
        "SELECT DISTINCT player_name FROM draft_players WHERE player_name IS NOT NULL",
        "SELECT DISTINCT player_name FROM overseas_players WHERE player_name IS NOT NULL",
    )
    try:
        with _storage_connect() as con:
            for q in queries:
                try:
                    for r in con.execute(q).fetchall():
                        nm = r[0] if isinstance(r, tuple) else r["player_name"]
                        slug = re.sub(r"[^a-z0-9]+", "_", (nm or "").lower()).strip("_")
                        if slug:
                            names.add(slug)
                except Exception:
                    continue
    except Exception:
        pass
    return names

log = logging.getLogger(__name__)


# Position-token classifier — first token before each player name in a
# trade description (`2B Brendan Donovan`, `SHP Jurrangelo Cijntje`,
# `CF Colton Ledbetter`, `OF/1B Joey Gallo`, etc.). MLB Stats API
# returns standardized positions; we use this to identify likely
# player tokens in descriptions before name extraction.
_POSITION_TOKENS = (
    "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "DH",
    "P", "SP", "RP", "RHP", "LHP", "SHP", "MIRP", "SIRP", "TWP",
    "INF", "IF", "MI", "UTIL",
)
# Build a regex that finds "<POS> <Capitalized Name>" patterns. Names
# allow up to 4 tokens (e.g. "Vladimir Guerrero Jr." or "Luis Garcia
# Sr."). Pos prefix can be multi-position like "OF/1B".
_POS_PATTERN = r"(?:" + "|".join(p for p in sorted(_POSITION_TOKENS, key=len, reverse=True)) + r")"
_MULTIPOS_PATTERN = rf"(?:{_POS_PATTERN}(?:/{_POS_PATTERN})*)"
# Player names: capitalized tokens, optional periods/apostrophes,
# optional Jr./Sr./II/III suffix.
_NAME_TOKEN = r"[A-Z][A-Za-zÀ-ÿ.'´-]+"
_NAME_PATTERN = rf"(?:{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,3}})(?:\s+(?:Jr\.?|Sr\.?|II|III|IV))?"
_TRADE_PLAYER_RE = re.compile(
    rf"\b({_MULTIPOS_PATTERN})\s+({_NAME_PATTERN})"
)


def extract_player_names_from_description(description: str) -> list[str]:
    """Parse a trade description for `<POS> <Player Name>` patterns.

    Returns a deduplicated list of player names in the order they
    appear. Doesn't care about which side of the trade each player
    is on — the caller resolves that via the from/to org context.
    """
    if not description:
        return []
    seen = set()
    out: list[str] = []
    for m in _TRADE_PLAYER_RE.finditer(description):
        name = m.group(2).strip()
        # Strip trailing punctuation (commas, periods, semicolons) that
        # got pulled in by the name token regex.
        name = re.sub(r"[.,;:!?]+$", "", name).strip()
        if not name:
            continue
        # Drop common false positives (city names that look like
        # players, league acronyms, etc).
        if name.lower() in _NON_PLAYER_PHRASES:
            continue
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


_NON_PLAYER_PHRASES = {
    "san diego", "san francisco", "los angeles", "new york",
    "tampa bay", "kansas city", "chicago white", "white sox",
    "national league", "american league", "all star", "all-star",
    "world series", "minor league", "major league", "spring training",
}


def _search_mlbam_vet(name: str) -> int | None:
    """Vet-friendly MLB Stats API search. Mirrors stats._search_mlbam_via_api
    but DROPS the 1994 birth-year filter (which excludes most MLB
    veterans — Sonny Gray b. 1989, Justin Verlander b. 1983, etc.)
    and prefers the candidate with the latest MLB activity. We accept
    any player whose lastPlayedDate is within the last 6 years OR
    whose mlbDebutDate is post-2010 (still active-era).
    """
    import time
    import urllib.parse
    import requests
    try:
        from stats import (
            MLB_STATS_API, RATE_LIMIT_SECONDS,
            _norm_key, _last_names_align,
        )
    except ImportError:
        return None
    from datetime import date as _date
    encoded = urllib.parse.quote_plus(name)
    today_yr = _date.today().year
    for params in (
        f"names={encoded}&active=true",
        f"names={encoded}",
    ):
        url = f"{MLB_STATS_API}/people/search?{params}"
        time.sleep(RATE_LIMIT_SECONDS)
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            people = r.json().get("people", []) or []
        except Exception:
            continue
        best = None
        for p in people:
            full = p.get("fullName", "") or ""
            if not _last_names_align(name, full):
                continue
            debut = (p.get("mlbDebutDate") or "")[:4]
            last  = (p.get("lastPlayedDate") or "")[:4]
            try:
                debut_yr = int(debut) if debut else 0
                last_yr  = int(last)  if last  else 0
            except ValueError:
                debut_yr = last_yr = 0
            # Score: recent MLB activity wins. Active flag adds extra.
            score = 0
            if last_yr >= today_yr - 6: score += 100
            if debut_yr >= 2000:         score += 20
            if p.get("active"):          score += 10
            # Active-era last-played beats anything else.
            if last_yr:                  score += last_yr  # tiebreak by year
            if best is None or score > best[0]:
                best = (score, p)
        if best is not None:
            return int(best[1]["id"])
    return None


def _resolve_one(name: str) -> dict | None:
    """Resolve a single name → {player_name, mlbam_id, primary_position,
    career_war, is_pitcher, surplus_mm, ...}.

    v31.9c — Also fetches age + current contract (AAV + years remaining)
    and computes a contract-based surplus = projected_remaining_WAR ×
    $/WAR_tier(avg_per_yr) − sum(remaining_AAV). This trumps the naive
    career_war × overall-rate valuation in the frontend trade audit
    when contract data is on file (more accurate for evaluating future
    value being acquired). The $/WAR tier comes from value_framework,
    which uses the rolling 3yr (2024-2026) non-linear 3-tier model.
    """
    try:
        mlbam_id = _search_mlbam_vet(name)
    except Exception:
        log.debug("MLB search crashed for %s", name, exc_info=True)
        mlbam_id = None
    if not mlbam_id:
        return {
            "player_name":    name,
            "mlbam_id":       None,
            "primary_position": None,
            "career_war":     None,
            "war_seasons":    None,
            "last_team":      None,
            "is_pitcher":     False,
            "resolve_status": "not_found",
        }
    # Fetch position + age via Stats API.
    pos, is_pit, last_team, age = _fetch_position_team_age(mlbam_id)
    # Career WAR via pybaseball (BBRef).
    career_war, war_seasons = _fetch_career_war_one(mlbam_id, is_pit)
    # v31.9c — Contract lookup (Spotrac via storage.load_spotrac_contracts).
    # Falls back to None when no match — surplus stays NULL and the
    # frontend uses the career-WAR fallback.
    aav, years_rem, total = _lookup_spotrac_contract(name, mlbam_id)
    proj_war_rem, surplus_mm = _compute_surplus(
        career_war, war_seasons, age, aav, years_rem,
    )
    return {
        "player_name":      name,
        "mlbam_id":         mlbam_id,
        "primary_position": pos,
        "career_war":       career_war,
        "war_seasons":      war_seasons,
        "last_team":        last_team,
        "is_pitcher":       is_pit,
        "resolve_status":   "resolved",
        "current_aav_usd":  aav,
        "years_remaining":  years_rem,
        "contract_total_usd": total,
        "age":              age,
        "projected_war_remaining": proj_war_rem,
        "surplus_mm":       surplus_mm,
    }


# v31.9c — Lazy module-level cache of Spotrac contracts indexed by
# name slug. Built on first lookup so the resolver pool can share the
# scrape; failures are swallowed (surplus_mm just stays NULL).
_SPOTRAC_BY_SLUG: dict[str, dict] | None = None


def _load_spotrac_by_slug() -> dict[str, dict]:
    global _SPOTRAC_BY_SLUG
    if _SPOTRAC_BY_SLUG is not None:
        return _SPOTRAC_BY_SLUG
    out: dict[str, dict] = {}
    try:
        from spotrac import scrape_all_spotrac_contracts, build_contracts_by_key
        rows = scrape_all_spotrac_contracts(force=False) or []
        # build_contracts_by_key expects (rows, lookup_dict) — but for
        # MLB-vet resolution we don't have a tracked-key lookup, so we
        # just walk the raw rows by name.
        for r in rows:
            nm = (r or {}).get("player_name") or ""
            slug = re.sub(r"[^a-z0-9]+", "_", nm.lower()).strip("_")
            if not slug:
                continue
            # Keep the highest-AAV row when a name appears multiple
            # times (rare — usually same player on multiple teams within
            # a year via mid-season trade).
            existing = out.get(slug)
            if not existing or (r.get("aav_usd") or 0) > (existing.get("aav_usd") or 0):
                out[slug] = r
    except Exception:
        log.debug("spotrac scrape failed during MLB vet resolution", exc_info=True)
    _SPOTRAC_BY_SLUG = out
    log.info("_load_spotrac_by_slug: cached %d contracts by name slug", len(out))
    return out


def _lookup_spotrac_contract(name: str, mlbam_id: int) -> tuple[int | None, int | None, int | None]:
    """Look up Spotrac contract data by name slug. Returns (aav_usd,
    years_remaining, total_usd) or (None, None, None) on miss."""
    by_slug = _load_spotrac_by_slug()
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    rec = by_slug.get(slug)
    if not rec:
        return (None, None, None)
    return (rec.get("aav_usd"), rec.get("years_remaining"), rec.get("total_usd"))


def _compute_surplus(career_war: float | None, war_seasons: int | None,
                     age: int | None, aav_usd: int | None,
                     years_remaining: int | None,
                     ) -> tuple[float | None, float | None]:
    """Project remaining WAR + compute contract surplus_mm, PER SEASON.

    Commensurable with the prospect-side surplus (value_framework's career-path
    mixture): each remaining season is valued on ITS OWN WAR through the convex
    tiered $/WAR, the season's salary (AAV) is subtracted, and each future
    season's surplus is discounted to present value -- never averaging WAR first
    (E[f(X)] != f(E[X])). Fixes docs/sv-audit.md FLAG 12 (vet surplus was on a
    different basis -- avg-WAR tier dispatch, no discounting -- than prospect SV).

    Projected remaining WAR per season: recent rate (career_war / war_seasons,
    capped at 6 to avoid out-of-sample) minus a -0.4 WAR/yr aging penalty per
    year past 29, floored at 0. A declining year sits at the fringe tier, a star
    year at the premium tier -- the tier is chosen per season, not off the
    average. Salary is the contract AAV each year. Surplus is the discounted sum
    of (season value - season salary), in $M.

    Returns (proj_war_remaining, surplus_mm) or (None, None) when insufficient
    inputs (no career WAR or no contract data).
    """
    from value_framework import dollars_per_war, present_value
    if career_war is None or war_seasons is None or war_seasons <= 0:
        return (None, None)
    if aav_usd is None or years_remaining is None or years_remaining <= 0:
        return (None, None)
    rate = max(0.0, min(6.0, float(career_war) / float(war_seasons)))
    aav_mm = aav_usd / 1_000_000.0
    base_age = age if age is not None else 28
    proj_war = 0.0
    surplus_mm = 0.0
    for i in range(int(years_remaining)):
        yr_age = base_age + i
        # Aging penalty: 0 below age 29, then -0.4 per year above 29.
        decline = max(0.0, 0.4 * (yr_age - 29))
        season_war = max(0.0, rate - decline)
        proj_war += season_war
        # Value THIS season's WAR at its own convex tier rate ($M/WAR), then
        # net out that season's salary and discount to present value.
        season_value_mm = season_war * dollars_per_war(season_war)
        surplus_mm += present_value(season_value_mm - aav_mm, i)
    return (round(proj_war, 2), round(surplus_mm, 1))


def _fetch_position_team_age(mlbam_id: int) -> tuple[str | None, bool, str | None, int | None]:
    """Hit MLB Stats API /people/{id} for position + current team + age."""
    import time
    import requests
    from datetime import date as _date
    try:
        from stats import MLB_STATS_API, RATE_LIMIT_SECONDS
    except ImportError:
        return (None, False, None, None)
    time.sleep(RATE_LIMIT_SECONDS)
    try:
        r = requests.get(
            f"{MLB_STATS_API}/people/{mlbam_id}?hydrate=currentTeam",
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return (None, False, None, None)
    people = data.get("people") or []
    if not people:
        return (None, False, None, None)
    p = people[0]
    pos_info = p.get("primaryPosition") or {}
    pos_abbr = pos_info.get("abbreviation")
    is_pit = (pos_info.get("code") == "1") or (pos_abbr in ("P", "SP", "RP"))
    team_info = p.get("currentTeam") or {}
    team_abbr = team_info.get("abbreviation")
    age = None
    bd = p.get("birthDate") or ""
    if bd:
        try:
            yr = int(bd[:4])
            age = _date.today().year - yr
        except ValueError:
            age = None
    return (pos_abbr, is_pit, team_abbr, age)


# v31.9c — `_fetch_position_and_team` superseded by `_fetch_position
# _team_age` which also returns age (for surplus aging-curve calc).


_BWAR_BAT_CACHE = None
_BWAR_PIT_CACHE = None
_BWAR_BAT_FAILED = False     # sticky: once a download fails, stop retrying this run
_BWAR_PIT_FAILED = False


def _ensure_bwar_loaded(is_pitcher: bool, timeout_seconds: float = 30.0) -> bool:
    """Lazy-load the BBRef WAR CSV for one side (bat / pitch). Returns
    True if the cache is ready, False if the download failed (caller
    should skip WAR backfill for this name).

    Wraps pybaseball's bwar_bat / bwar_pitch in a thread + join with
    timeout, since the underlying urllib.request call can hang
    indefinitely on a slow / unreliable connection.
    """
    global _BWAR_BAT_CACHE, _BWAR_PIT_CACHE, _BWAR_BAT_FAILED, _BWAR_PIT_FAILED
    cache_ref = _BWAR_PIT_CACHE if is_pitcher else _BWAR_BAT_CACHE
    failed_ref = _BWAR_PIT_FAILED if is_pitcher else _BWAR_BAT_FAILED
    if cache_ref is not None:
        return True
    if failed_ref:
        return False
    try:
        import pybaseball as pyb
    except ImportError:
        if is_pitcher: _BWAR_PIT_FAILED = True
        else:           _BWAR_BAT_FAILED = True
        return False
    # Download in a thread so we can enforce a timeout. Module-level
    # caches are touched directly on success.
    import threading
    result: dict[str, object] = {}
    def _worker():
        try:
            result["df"] = pyb.bwar_pitch() if is_pitcher else pyb.bwar_bat()
        except Exception as e:
            result["err"] = e
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout_seconds)
    if t.is_alive():
        log.warning("BBRef %s WAR download timed out after %.0fs — skipping WAR backfill",
                    "pitch" if is_pitcher else "bat", timeout_seconds)
        if is_pitcher: _BWAR_PIT_FAILED = True
        else:           _BWAR_BAT_FAILED = True
        return False
    if "err" in result:
        log.warning("BBRef %s WAR download crashed: %s — skipping WAR backfill",
                    "pitch" if is_pitcher else "bat", result["err"])
        if is_pitcher: _BWAR_PIT_FAILED = True
        else:           _BWAR_BAT_FAILED = True
        return False
    df = result.get("df")
    if df is None:
        if is_pitcher: _BWAR_PIT_FAILED = True
        else:           _BWAR_BAT_FAILED = True
        return False
    if is_pitcher:
        _BWAR_PIT_CACHE = df
    else:
        _BWAR_BAT_CACHE = df
    return True


def _fetch_career_war_one(mlbam_id: int, is_pitcher: bool) -> tuple[float | None, int | None]:
    """Fetch career WAR + season count via pybaseball BBRef tables.

    Returns (career_war_sum, season_count) or (None, None) on failure.
    Uses the timeout-wrapped lazy loader above so a single hung
    download can't stall the whole pipeline.
    """
    if not _ensure_bwar_loaded(is_pitcher):
        return (None, None)
    df = _BWAR_PIT_CACHE if is_pitcher else _BWAR_BAT_CACHE
    if df is None:
        return (None, None)
    try:
        rows = df[df["mlb_ID"] == int(mlbam_id)]
        if rows.empty:
            return (0.0, 0)
        war_col = "WAR" if "WAR" in rows.columns else "WAR_total"
        if war_col not in rows.columns:
            return (None, None)
        total = float(rows[war_col].sum())
        seasons = int(rows["year_ID"].nunique()) if "year_ID" in rows.columns else len(rows)
        return (round(total, 2), seasons)
    except Exception:
        log.debug("career WAR lookup failed for mlbam=%s", mlbam_id, exc_info=True)
        return (None, None)


def refresh_mlb_trade_players(force: bool = False, workers: int = 4,
                               max_new: int | None = 50,
                               time_budget_seconds: float = 90.0) -> int:
    """For every trade in the `trades` table, parse its description for
    player names, and for any name not in our tracked player map nor
    already cached, resolve + fetch + upsert.

    `force=True` re-resolves every name (refreshes career WAR).
    `workers` controls the parallel resolver pool size.
    `max_new` caps NEW lookups per run (default 50 — pipeline-safe,
       subsequent runs chip through the backlog). Pass None to attempt
       all pending names in one shot.
    `time_budget_seconds` hard upper bound (default 90s). When the
       budget runs out we abort the remaining lookups and persist
       whatever we resolved; pipeline keeps moving.
    """
    deadline = time.monotonic() + max(10.0, time_budget_seconds)
    # Existing tracked-prospect names (slug set) so we skip them.
    known_names = _load_known_tracked_names()
    # Existing MLB trade-player cache.
    cached = load_mlb_trade_players()
    # Walk trades + extract. load_trades() returns {player_key: [trade_dict, ...]}.
    try:
        trades_by_player = load_trades()
    except Exception:
        log.warning("load_trades failed; skipping MLB trade lookup")
        return 0
    pending: set[str] = set()
    seen_descs: set[str] = set()
    for plist in trades_by_player.values():
        for t in plist:
            desc = t.get("description") or ""
            if not desc or desc in seen_descs:
                continue
            seen_descs.add(desc)
            for nm in extract_player_names_from_description(desc):
                slug = re.sub(r"[^a-z0-9]+", "_", nm.lower()).strip("_")
                if not slug or slug in known_names:
                    continue
                if (not force) and slug in cached:
                    continue
                pending.add(nm)
    if max_new is not None and len(pending) > max_new:
        # Stable subset so multiple runs cover the backlog deterministically.
        pending = set(sorted(pending)[:max_new])
    if not pending:
        log.info("refresh_mlb_trade_players: nothing new to resolve "
                 "(%d cached, %d tracked-prospect names)",
                 len(cached), len(known_names))
        return 0
    log.info("refresh_mlb_trade_players: resolving up to %d new MLB names "
             "(%d workers, %.0fs budget)",
             len(pending), workers, time_budget_seconds)
    resolved = 0
    aborted = False
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_resolve_one, nm): nm for nm in pending}
        for fut in as_completed(futures):
            # Hard time budget: persist what we have + bail.
            if time.monotonic() > deadline:
                aborted = True
                # Cancel any not-yet-started futures.
                for f in futures:
                    if not f.done():
                        f.cancel()
                break
            try:
                rec = fut.result(timeout=max(1.0, deadline - time.monotonic()))
            except Exception:
                log.debug("_resolve_one crashed for %s",
                          futures.get(fut), exc_info=True)
                continue
            if rec:
                upsert_mlb_trade_player(rec)
                resolved += 1
    if aborted:
        log.warning("refresh_mlb_trade_players: time budget exhausted at "
                    "%d resolutions — remaining names will retry next run",
                    resolved)
    else:
        log.info("refresh_mlb_trade_players: cached %d new MLB names",
                 resolved)
    return resolved
