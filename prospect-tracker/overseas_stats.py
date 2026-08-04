# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""FG player-page stats scraper for overseas prospects.

FanGraphs ships full per-season stats for NPB / KBO / CPBL players
on their player pages (`/players/<slug>/<playerId>/stats`). The page
is server-rendered HTML with `<table>` elements per stat group
(Dashboard / Standard / Advanced for both hitter and pitcher views).
We use the **Dashboard** table for each prospect since it carries the
best mix of headline metrics (AVG/OBP/SLG/wRC+ for hitters,
ERA/FIP/K%/BB%/WAR for pitchers).

Column headers in the page source come glyph-duplicated:
  `WW - Wins`  →  abbreviation 'W'  (the first "W" is the column glyph,
the second is the start of the tooltip "Wins" description).
We strip the `XX - Description` suffix to recover the canonical
abbreviation, then map to our short keys.

Caching reuses `scrapers._fetch` so we get the same on-disk cache + rate
limiting story as every other scraper in the project.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from scrapers import (
    HEADERS as _DEFAULT_HEADERS,
    _fetch,
    fix_mojibake,
)
from storage import load_overseas_players, upsert_overseas_statlines

log = logging.getLogger(__name__)


_BASE = Path(__file__).parent
CACHE_DIR = _BASE / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

FG_PLAYER_STATS_URL = "https://www.fangraphs.com/players/x/{player_id}/stats"


# ---------------------------------------------------------------------------
# Loud failure types (2026-08-03).
#
# Every failure in this module used to collapse to `return []`: a blocked
# fetch, a login wall, an FG markup restructure and a player who genuinely
# has no seasons were all the same value. `refresh_overseas_stats` skips
# empty results, so a dead source reads as a clean run with nothing to do.
# That is the silent-empty class that froze the 2027 FA board once already.
# The three cases now have distinct, named outcomes.
# ---------------------------------------------------------------------------
class OverseasStatsError(RuntimeError):
    """Base class for FG player-page scrape failures."""


class OverseasFetchError(OverseasStatsError):
    """The FG player page could not be retrieved at all (non-200 or empty
    body) and no cached copy existed to fall back on."""


class OverseasParseError(OverseasStatsError):
    """A page WAS retrieved, its own payload says it carries seasons, and
    the table parser still found none. Always a page-shape change, never a
    player with an empty career."""


# Strip the FG tooltip suffix from a header cell: "WW - Wins" → "W",
# "K/9K/9 - Strikeouts per 9 Innings ((SO*9)/IP)" → "K/9".
def _clean_header(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip()
    # If the header has " - " (tooltip suffix), keep only the bit before
    # the duplicated abbreviation token.
    if " - " in s:
        token = s.split(" - ", 1)[0]
        # The token is the abbreviation duplicated: take the first half.
        half = len(token) // 2
        if half >= 1 and token[:half] == token[half:]:
            return token[:half]
        return token
    return s


def _to_num(v: str | None):
    """Best-effort numeric coerce. Returns float for percentages /
    decimals, int for plain integers, None for empty / non-numeric."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == "-" or s == "—":
        return None
    pct = s.endswith("%")
    if pct:
        s = s[:-1].strip()
    try:
        f = float(s)
    except ValueError:
        return s  # surface as string (Team / Level / Season columns)
    if pct:
        return round(f / 100.0, 4)
    if f.is_integer() and "." not in str(v):
        return int(f)
    return f


# Canonical key map for stat columns we care about. Anything not in
# this list flows through as-is under its cleaned header name.
HITTER_KEYS = {
    "Season": "season", "Team": "team", "Level": "level", "Age": "age",
    "G": "g", "PA": "pa", "AB": "ab", "H": "h", "1B": "b1", "2B": "b2",
    "3B": "b3", "HR": "hr", "R": "r", "RBI": "rbi", "BB": "bb", "SO": "so",
    "SB": "sb", "CS": "cs", "AVG": "avg", "OBP": "obp", "SLG": "slg",
    "OPS": "ops", "ISO": "iso", "BABIP": "babip", "BB%": "bb_pct",
    "K%": "k_pct", "wOBA": "woba", "wRC+": "wrc_plus", "WAR": "war",
}

PITCHER_KEYS = {
    "Season": "season", "Team": "team", "Level": "level", "Age": "age",
    "W": "w", "L": "l", "SV": "sv", "G": "g", "GS": "gs", "QS": "qs",
    "IP": "ip", "TBF": "tbf", "H": "h", "R": "r", "ER": "er", "HR": "hr",
    "BB": "bb", "SO": "so", "K/9": "k_per_9", "BB/9": "bb_per_9",
    "HR/9": "hr_per_9", "K%": "k_pct", "BB%": "bb_pct", "K-BB%": "k_bb_pct",
    "WHIP": "whip", "BABIP": "babip", "LOB%": "lob_pct", "GB%": "gb_pct",
    "HR/FB": "hr_fb", "ERA": "era", "xERA": "xera", "FIP": "fip",
    "xFIP": "xfip", "ERA-": "era_minus", "FIP-": "fip_minus",
    "vFA": "fb_velo", "AVG": "avg_against", "WAR": "war",
}


def _is_pitcher_table_headers(headers: list[str]) -> bool:
    """Distinguish a pitcher dashboard from a hitter dashboard by
    looking for ERA / FIP / IP — those never appear on a hitter row."""
    return any(h in headers for h in ("ERA", "FIP", "IP", "K/9"))


def _parse_stats_table(table) -> list[dict]:
    """Parse one stat-table element into a list of per-row dicts."""
    rows = table.find_all("tr")
    if len(rows) < 2:
        return []
    raw_headers = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
    headers = [_clean_header(h) for h in raw_headers]
    if not headers or "Season" not in headers:
        return []

    is_pitcher = _is_pitcher_table_headers(headers)
    keymap = PITCHER_KEYS if is_pitcher else HITTER_KEYS

    out: list[dict] = []
    for r in rows[1:]:
        cells = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
        if len(cells) < len(headers):
            continue
        rec: dict = {}
        for h, v in zip(headers, cells):
            if not h or h == "divider":
                continue
            key = keymap.get(h, h)
            rec[key] = _to_num(v)
        # Skip totals / career summary rows (Season cell is non-numeric).
        season = rec.get("season")
        if not isinstance(season, int):
            continue
        # Skip rows below 2000 (defensive — historical league overlay rows
        # FG sometimes injects with "Season" labels like "2 Yrs").
        if season < 2000 or season > date.today().year + 1:
            continue
        rec["_is_pitcher"] = is_pitcher
        out.append(rec)
    return out


def _pick_dashboard_table(soup: BeautifulSoup) -> list[dict]:
    """Find the first table that looks like a Dashboard (has Season +
    Level + an FG league code in the body), parse it, and return rows.

    Walks all tables in document order and picks the first one whose
    parsed output contains overseas-league levels (NPB / KBO / CPBL).
    If none match (e.g., FG hides overseas pages behind login), falls
    back to the first table with Season+Level."""
    candidates: list[list[dict]] = []
    for t in soup.find_all("table"):
        rows = _parse_stats_table(t)
        if not rows:
            continue
        # Prefer tables whose rows include overseas levels.
        levels = {r.get("level") for r in rows}
        if levels & {"NPB", "NPBF", "KBO", "CPBL", "Cuba", "TWN"}:
            return rows
        candidates.append(rows)
    return candidates[0] if candidates else []


_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _payload_season_count(html: str) -> int | None:
    """How many season rows FG's OWN page payload says the page carries.

    The FG player page is a Next.js app: the seasons rendered into the
    `<table>` markup are also shipped verbatim in the `__NEXT_DATA__` JSON
    under `props.pageProps.dataStats.data`. That makes the payload a free
    REFEREE for the table parser. It answers "was there anything to parse?"
    without depending on the table markup at all, which is precisely the
    thing a restructure changes.

    Returns the season count, or None when the page carries no usable
    payload block (itself a page-shape change worth shouting about).

    MEASURED over all 259 cached FG player pages on 2026-08-03: the table
    parse yields rows for exactly the pages whose payload is non-empty, and
    the single payload-empty page (Raidel Martinez, sa3023350 - FG serves
    that route with no `dataStats.data` key at all) really does render no
    stat tables. So "payload > 0 with zero parsed rows" cannot be an empty
    career; it can only be a markup change.
    """
    m = _NEXT_DATA_RE.search(html or "")
    if not m:
        return None
    try:
        doc = json.loads(m.group(1))
    except ValueError:
        return None
    props = (doc.get("props") or {}).get("pageProps")
    if not isinstance(props, dict):
        return None
    stats = props.get("dataStats")
    if not isinstance(stats, dict):
        return None                      # payload renamed -> shape change
    data = stats.get("data")
    return len(data) if isinstance(data, list) else 0


def _cached_page(cache_key: str) -> str:
    """The on-disk copy `scrapers._fetch` keeps for this cache key, or ''.

    Read directly so a FAILED refetch can fall back to a STALE copy. The
    cache key 'fg_player_<id>' carries no 20xx token, so
    `scrapers._cache_ttl_for_key` hands it the 24h current-year TTL: once
    the copy is a day old `_fetch` goes to the network, and any FG block or
    offline run then turns a perfectly good cached page into zero rows.
    A day-stale overseas season line beats no season line.
    """
    p = CACHE_DIR / f"{cache_key}.html"
    try:
        return p.read_text(encoding="utf-8") if p.exists() else ""
    except OSError:
        return ""


def scrape_fg_player_stats(fg_player_id: str,
                            force: bool = False,
                            strict: bool = True) -> list[dict]:
    """Fetch + parse one FG player page. Returns a list of per-season
    dicts ready for `upsert_overseas_statlines`.

    The URL takes any slug; FG resolves by the trailing ID. We use 'x'
    as the placeholder slug so the cache key is stable per ID.

    LOUD ON EMPTY (2026-08-03). Every failure used to `return []`, so the
    callers (which skip empty results) could not tell a dead source from a
    player with nothing to report. The outcomes are now separated, with
    FG's own page payload as the referee (see `_payload_season_count`):

      * fetch failed AND no cached copy on disk -> OverseasFetchError
      * page payload carries N > 0 seasons, or has no payload block at all,
        and the table parse still found nothing -> OverseasParseError
      * page genuinely carries no seasons -> `[]`, logged at WARNING

    Pass `strict=False` to get the old return-empty behaviour with the
    diagnosis logged instead of raised.
    """
    if not fg_player_id:
        return []
    url = FG_PLAYER_STATS_URL.format(player_id=fg_player_id)
    cache_key = f"fg_player_{fg_player_id}"
    fr = _fetch(url, cache_key, force=force)

    body = fr.body if (fr.status == 200 and fr.body) else ""
    origin = "cached" if fr.from_cache else "fetched"
    if not body:
        body = _cached_page(cache_key)
        origin = "stale-cached"
        if body:
            log.warning("fg_player_stats %s: HTTP %d - falling back to the "
                        "stale cached page (%d bytes)",
                        fg_player_id, fr.status, len(body))
        else:
            msg = (f"fg_player_stats {fg_player_id}: HTTP {fr.status} and no "
                   f"cached page on disk - nothing to parse")
            if strict:
                raise OverseasFetchError(msg)
            log.warning("%s", msg)
            return []

    soup = BeautifulSoup(body, "html.parser")
    rows = _pick_dashboard_table(soup)
    if rows:
        return rows

    n_payload = _payload_season_count(body)
    detail = (f"fg_player_stats {fg_player_id}: parsed ZERO season rows from "
              f"the {origin} page ({len(body)} bytes, "
              f"{len(soup.find_all('table'))} tables, payload says "
              f"{'no payload block' if n_payload is None else n_payload} "
              f"seasons)")
    if n_payload is None or n_payload > 0:
        shape = f"{detail} - the FG player page shape has changed"
        if strict:
            raise OverseasParseError(shape)
        log.error("%s", shape)
        return []
    log.warning("%s - FG serves no seasons for this player", detail)
    return []


def _fetch_one_overseas(pk_fg_id: tuple[str, str],
                        force: bool) -> tuple[str, list[dict], str | None]:
    """Thread-pool worker. Returns (player_key, rows, failure_class).

    failure_class is None on success, 'parse' when the FG page shape broke
    and 'fetch' when the page could not be retrieved at all. One bad player
    never aborts the batch, but the batch can now tell an honestly-empty
    result from a source that stopped delivering."""
    pk, fg_id = pk_fg_id
    try:
        rows = scrape_fg_player_stats(fg_id, force=force)
    except OverseasParseError as e:
        log.error("overseas_stats: %s (%s)", e, pk)
        return (pk, [], "parse")
    except OverseasFetchError as e:
        log.warning("overseas_stats: %s (%s)", e, pk)
        return (pk, [], "fetch")
    except Exception:
        log.exception("overseas_stats fetch crashed for %s (%s)", pk, fg_id)
        return (pk, [], "fetch")
    return (pk, rows, None)


def refresh_overseas_stats(force: bool = False,
                            max_players: int | None = None,
                            workers: int = 8) -> int:
    """For every overseas_player with a fg_player_id, scrape their FG
    page and upsert per-season stats into overseas_statlines.

    v31.7 — Concurrent fetching via ThreadPoolExecutor (default 8
    workers; pass workers=1 for sequential). FG tolerates this rate
    well when paired with the on-disk cache. Returns count of
    season-rows inserted. Idempotent."""
    players = load_overseas_players()
    targets = [(pk, p["fg_player_id"]) for pk, p in players.items()
                if p.get("fg_player_id")]
    if max_players is not None:
        targets = targets[:max_players]
    if not targets:
        log.info("refresh_overseas_stats: no overseas players with FG IDs")
        return 0

    log.info("refresh_overseas_stats: fetching %d overseas players (%d workers)",
             len(targets), workers)

    results: dict[str, list[dict]] = {}
    failures: dict[str, int] = {"fetch": 0, "parse": 0}

    def _take(triple: tuple[str, list[dict], str | None]) -> None:
        pk, rows, err = triple
        results[pk] = rows
        if err:
            failures[err] = failures.get(err, 0) + 1

    if workers <= 1:
        for t in targets:
            _take(_fetch_one_overseas(t, force))
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_fetch_one_overseas, t, force): t[0] for t in targets}
            for fut in as_completed(futures):
                _take(fut.result())

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
            # Drop FG's synthetic non-actual-season rows: ROS (rest-of-
            # season), PROJ (projections), ST (spring training).
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
            n = upsert_overseas_statlines(payloads)
            total += n
    log.info("refresh_overseas_stats: %d total season rows upserted across %d players",
             total, len(targets))

    # Do NOT let a dead source read as a clean run. An empty refresh upserts
    # nothing and used to log the cheerful line above and stop.
    if failures.get("parse"):
        log.error("refresh_overseas_stats: %d/%d FG pages parsed ZERO rows "
                  "while their own page payload carried seasons - the FG "
                  "player page markup has changed and overseas stats are NOT "
                  "refreshing", failures["parse"], len(targets))
    if failures.get("fetch"):
        log.warning("refresh_overseas_stats: %d/%d FG pages could not be "
                    "retrieved at all", failures["fetch"], len(targets))
    if total == 0:
        log.error("refresh_overseas_stats: ZERO season rows upserted across "
                  "%d players (%d fetch failures, %d parse failures) - treat "
                  "this as a dead source, not a quiet no-op",
                  len(targets), failures.get("fetch", 0), failures.get("parse", 0))
    return total
