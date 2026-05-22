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

import logging
import re
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


def scrape_fg_player_stats(fg_player_id: str,
                            force: bool = False) -> list[dict]:
    """Fetch + parse one FG player page. Returns a list of per-season
    dicts ready for `upsert_overseas_statlines`.

    The URL takes any slug; FG resolves by the trailing ID. We use 'x'
    as the placeholder slug so the cache key is stable per ID.
    """
    if not fg_player_id:
        return []
    url = FG_PLAYER_STATS_URL.format(player_id=fg_player_id)
    cache_key = f"fg_player_{fg_player_id}"
    fr = _fetch(url, cache_key, force=force)
    if fr.status != 200 or not fr.body:
        log.info("fg_player_stats %s: HTTP %d", fg_player_id, fr.status)
        return []
    soup = BeautifulSoup(fr.body, "html.parser")
    rows = _pick_dashboard_table(soup)
    return rows


def refresh_overseas_stats(force: bool = False, max_players: int | None = None) -> int:
    """For every overseas_player with a fg_player_id, scrape their FG
    page and upsert per-season stats into overseas_statlines.

    Returns the count of season-rows inserted. Idempotent."""
    players = load_overseas_players()
    targets = [(pk, p) for pk, p in players.items() if p.get("fg_player_id")]
    if max_players is not None:
        targets = targets[:max_players]
    if not targets:
        log.info("refresh_overseas_stats: no overseas players with FG IDs")
        return 0
    total = 0
    for pk, p in targets:
        try:
            rows = scrape_fg_player_stats(p["fg_player_id"], force=force)
        except Exception:
            log.exception("refresh_overseas_stats: %s scrape crashed", pk)
            continue
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
            log.info("refresh_overseas_stats: %s -> %d season rows",
                     pk, len(payloads))
    log.info("refresh_overseas_stats: %d total season rows upserted across %d players",
             total, len(targets))
    return total
