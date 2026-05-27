# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""NCAA Division-I college box scores for draft prospects (stats.ncaa.org).

The FanGraphs draft path (`draft_stats`) only covers the ~12% of board
prospects that already carry an `fg_player_id`. This module fills the long
tail with official NCAA D-I box scores. Verified data path:

  1. school -> NCAA team id (HTTP, server-rendered):
       stats.ncaa.org/team/inst_team_list?sport_code=MBA&academic_year=YYYY&division=1
     parses to {normalized_school: team_id} (e.g. Alabama -> 614848).

  2. team id -> player batting + pitching grids (JS-rendered, needs a
     headless browser):
       stats.ncaa.org/teams/{team_id}/season_to_date_stats
       ...?year_stat_category_id={pitching_cat}   (pitching split)
     Both render `table#stat_grid`. We render once per team via Playwright
     (cached to disk) and parse with BeautifulSoup.

Prospects are matched to a team's grid by normalized name. Rows are written
to `draft_statlines` with `payload["source"]="ncaa"`. Gap-fill only: we skip
prospects that already have a statline (FG-sourced), so sources don't clash.

The MLB draft-prospects API (statsapi) carries NO college stats, but it is a
clean identity source — `refresh_pipeline_identity` uses it to backfill
`mlbam_id` + canonical school on `draft_players`, which sharpens NCAA matching.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict

from bs4 import BeautifulSoup

from scrapers import _fetch, CACHE_DIR
from storage import (
    backfill_draft_player_fields,
    load_draft_players,
    load_draft_statlines,
    upsert_draft_statlines,
)

try:
    from fangraphs_csv import normalize_key as _normalize_name
except Exception:  # pragma: no cover - fallback if import shape changes
    def _normalize_name(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())

log = logging.getLogger(__name__)

NCAA_BASE = "https://stats.ncaa.org"
INST_TEAM_LIST = (NCAA_BASE +
                  "/team/inst_team_list?sport_code=MBA&academic_year={year}&division=1")
TEAM_STATS_URL = NCAA_BASE + "/teams/{team_id}/season_to_date_stats"
MLB_DRAFT_PROSPECTS = "https://statsapi.mlb.com/api/v1/draft/prospects/{year}?limit=2000"

# Sentinel league label for NCAA D-I rows (the conference is filled in when
# known; otherwise this generic tag keeps the UI's level column sensible).
NCAA_LEAGUE = "NCAA D-I"

# Browser-like UA — stats.ncaa.org 403s the project's honest bot UA, and the
# headless renderer presents as a real browser too.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


# ---------------------------------------------------------------------------
# School-name normalization (match draft_players.school to NCAA institutions)
# ---------------------------------------------------------------------------
# Conservative: drop only generic boilerplate ('University', 'of', 'the').
# We deliberately KEEP distinguishing tokens like 'State' and 'College'
# ("Michigan" vs "Michigan State", "Boston College" vs "Boston University"
# are different schools), so normalization never merges two real programs.
_SCHOOL_NOISE = re.compile(r"\b(university|univ|of|the|at)\b", re.IGNORECASE)


def _norm_school(name: str | None) -> str:
    """Normalize a school name for matching: lowercase, strip punctuation and
    generic boilerplate, collapse whitespace. Conservative — never drops the
    tokens that distinguish two programs ('State', 'College')."""
    if not name:
        return ""
    s = name.lower().replace("&", " and ")
    s = re.sub(r"[().,'`\-]", " ", s)
    s = _SCHOOL_NOISE.sub(" ", s)
    return re.sub(r"\s+", "", s)


# stats.ncaa.org rejects the project's honest bot UA (403), so NCAA HTTP
# calls use a browser-like UA + Referer. We still cache to the shared
# CACHE_DIR so re-runs are cheap and offline-friendly.
_NCAA_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://stats.ncaa.org/",
}


def _ncaa_get(url: str, cache_key: str, force: bool = False) -> str | None:
    """Cached HTTP GET for stats.ncaa.org with browser headers. Returns the
    body text, or None on failure. Caches to CACHE_DIR/<cache_key>.html."""
    import time
    import urllib.request
    cache_path = CACHE_DIR / f"{cache_key}.html"
    if cache_path.exists() and not force:
        age = time.time() - cache_path.stat().st_mtime
        if age < 7 * 24 * 3600:   # 7-day TTL (in-season freshness)
            return cache_path.read_text(encoding="utf-8")
    try:
        req = urllib.request.Request(url, headers=_NCAA_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception as e:
        log.warning("ncaa GET %s failed: %s", url, e)
        return None
    cache_path.write_text(body, encoding="utf-8")
    return body


class _NcaaBrowser:
    """One headless-Chrome session for a whole NCAA refresh. stats.ncaa.org
    sits behind Incapsula, which a real browser clears (cookie/JS challenge)
    but plain urllib cannot — so every NCAA fetch (team list + stat grids)
    goes through this shared session, clearing the challenge once. Results
    cache to CACHE_DIR so re-runs are cheap and the parsers stay offline-
    testable. `available` is False when Playwright/Chrome can't launch, so
    callers degrade gracefully."""

    # Resource types we never need (we only read table#stat_grid). Aborting
    # them makes every page load markedly faster with no effect on the data
    # or the JS that builds the grid (scripts/xhr/fetch are kept).
    _BLOCK_TYPES = {"image", "font", "media", "stylesheet"}

    def __init__(self):
        self._pw = self._browser = self.page = None
        self.available = False
        self._navigated = False     # True iff the last html() call hit the network
        self._pit_cat = None        # season-wide pitching year_stat_category_id (cached once)

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(channel="chrome", headless=True)
            self.page = self._browser.new_page(user_agent=_UA)
            # Drop images/fonts/css/media — pure speed, zero data impact.
            self.page.route(
                "**/*",
                lambda route: (route.abort()
                               if route.request.resource_type in self._BLOCK_TYPES
                               else route.continue_()))
            self.available = True
        except Exception:
            log.warning("playwright/chrome unavailable — NCAA stats skipped")
            self.available = False
        return self

    def __exit__(self, *exc):
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()

    def html(self, url: str, cache_key: str, force: bool = False,
             wait_selector: str | None = None,
             extract_selector: str | None = None) -> str | None:
        """Load `url` in the session and return page HTML (or one element's
        outerHTML via `extract_selector`). 7-day disk cache."""
        import time
        self._navigated = False
        cache_path = CACHE_DIR / f"{cache_key}.html"
        if cache_path.exists() and not force:
            if time.time() - cache_path.stat().st_mtime < 7 * 24 * 3600:
                return cache_path.read_text(encoding="utf-8")
        if not self.available:
            return None
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            self._navigated = True
            if wait_selector:
                # Waiting on the *data-bearing* selector (e.g. a populated grid
                # row, or a real team link past the Incapsula challenge) lets us
                # proceed the instant content is ready — no blind sleep.
                try:
                    self.page.wait_for_selector(wait_selector, timeout=15000)
                except Exception:
                    return None
            out = (self.page.eval_on_selector(extract_selector, "el => el.outerHTML")
                   if extract_selector and self.page.query_selector(extract_selector)
                   else self.page.content())
        except Exception:
            log.exception("ncaa session load failed: %s", url)
            return None
        if out:
            cache_path.write_text(out, encoding="utf-8")
        return out

    def pitching_category(self) -> str | None:
        """Read the pitching split's year_stat_category_id from the currently
        loaded team page's category nav."""
        for a in self.page.query_selector_all("a[href*='year_stat_category_id']"):
            if "pitch" in (a.text_content() or "").lower():
                m = re.search(r"year_stat_category_id=(\d+)", a.get_attribute("href") or "")
                if m:
                    return m.group(1)
        return None

    def ensure_pit_cat(self, team_id: int) -> str | None:
        """The pitching category id is season-wide (same across D-I teams), so
        we discover it once and cache it. Only navigates when it's unknown and
        we couldn't read it off a team page we'd already loaded."""
        if self._pit_cat is not None or not self.available:
            return self._pit_cat
        try:
            self.page.goto(TEAM_STATS_URL.format(team_id=team_id),
                           wait_until="domcontentloaded", timeout=45000)
            self.page.wait_for_selector("a[href*='year_stat_category_id']", timeout=10000)
            self._pit_cat = self.pitching_category()
        except Exception:
            pass
        return self._pit_cat


# ---------------------------------------------------------------------------
# 1. school -> NCAA team-id map (HTTP, server-rendered)
# ---------------------------------------------------------------------------
def fetch_d1_team_map(year: int, force: bool = False,
                      browser: "_NcaaBrowser | None" = None) -> dict[str, int]:
    """Return {normalized_school: ncaa_team_id} for D-I baseball in `year`.

    The institution list is server-rendered HTML, but Incapsula gates it, so
    we fetch it through the shared browser session when one is supplied
    (falling back to a cached copy / plain HTTP otherwise)."""
    url = INST_TEAM_LIST.format(year=year)
    cache_key = f"ncaa_inst_team_list_{year}"
    # Wait for real team links so we read the post-Incapsula content, not the
    # challenge shell (replaces the old blind delay).
    body = (browser.html(url, cache_key, force=force,
                         wait_selector="a[href*='/teams/']") if browser is not None
            else _ncaa_get(url, cache_key, force=force))
    if not body:
        log.warning("ncaa inst_team_list %s: fetch failed", year)
        return {}
    soup = BeautifulSoup(body, "html.parser")
    out: dict[str, int] = {}
    for a in soup.find_all("a", href=re.compile(r"/teams/\d+")):
        m = re.search(r"/teams/(\d+)", a["href"])
        if not m:
            continue
        school = a.get_text(strip=True)
        if not school:
            continue
        out[_norm_school(school)] = int(m.group(1))
    log.info("ncaa team map %s: %d D-I schools", year, len(out))
    return out


# ---------------------------------------------------------------------------
# 2. stat-grid parsing (pure — testable against saved fixtures)
# ---------------------------------------------------------------------------
def _to_float(s: str | None):
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if s in ("", "-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(s):
    f = _to_float(s)
    return int(f) if f is not None else None


def _ip_to_float(s: str | None):
    """NCAA innings use baseball notation: '12.1' = 12 1/3, '12.2' = 12 2/3."""
    f = _to_float(s)
    if f is None:
        return None
    whole = int(f)
    frac = round(f - whole, 1)
    if frac == 0.1:
        return whole + 1 / 3
    if frac == 0.2:
        return whole + 2 / 3
    return float(f)


def _grid_rows(html: str) -> tuple[list[str], list[dict]]:
    """Return (header_labels, [ {col_label: cell_text, '_pid': ncaa_id} ])."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="stat_grid") or soup.find("table")
    if not table:
        return [], []
    header = [th.get_text(strip=True) for th in table.select("thead th")]
    rows: list[dict] = []
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        vals = [c.get_text(strip=True) for c in cells]
        row = {header[i]: vals[i] for i in range(min(len(header), len(vals)))}
        a = tr.find("a", href=re.compile(r"/players/\d+"))
        if a:
            m = re.search(r"/players/(\d+)", a["href"])
            row["_pid"] = m.group(1) if m else None
        rows.append(row)
    return header, rows


def _batting_payload(r: dict) -> dict:
    """Map an NCAA batting grid row to the canonical draft_statlines payload
    (keys the export/UI already render: avg/obp/slg/ops/hr/sb/ab/bb/k_pct...)."""
    ab = _to_int(r.get("AB"))
    bb = _to_int(r.get("BB"))
    hbp = _to_int(r.get("HBP")) or 0
    sf = _to_int(r.get("SF")) or 0
    sh = _to_int(r.get("SH")) or 0
    k = _to_int(r.get("K"))
    avg = _to_float(r.get("BA"))
    obp = _to_float(r.get("OBPct"))
    slg = _to_float(r.get("SlgPct"))
    pa = (ab + bb + hbp + sf + sh) if ab is not None and bb is not None else None
    out = {
        "is_pitcher": False,
        "games": _to_int(r.get("GP")),
        "ab": ab,
        "h": _to_int(r.get("H")),
        "hr": _to_int(r.get("HR")),
        "rbi": _to_int(r.get("RBI")),
        "bb": bb,
        "sb": _to_int(r.get("SB")),
        "avg": avg,
        "obp": obp,
        "slg": slg,
        "ops": round(obp + slg, 3) if obp is not None and slg is not None else None,
        "iso": round(slg - avg, 3) if slg is not None and avg is not None else None,
        "pa": pa,
        "bb_pct": round(100 * bb / pa, 1) if bb is not None and pa else None,
        "k_pct": round(100 * k / pa, 1) if k is not None and pa else None,
    }
    return {k_: v for k_, v in out.items() if v is not None}


def _pitching_payload(r: dict) -> dict:
    ip = _ip_to_float(r.get("IP"))
    so = _to_int(r.get("SO"))
    bb = _to_int(r.get("BB"))
    h = _to_int(r.get("H"))
    hra = _to_int(r.get("HR-A"))
    out = {
        "is_pitcher": True,
        "games": _to_int(r.get("App")),
        "gs": _to_int(r.get("GS")),
        "ip": round(ip, 1) if ip is not None else None,
        "era": _to_float(r.get("ERA")),
        "so": so,
        "bb": bb,
        "h": h,
        "er": _to_int(r.get("ER")),
        "k_per_9": round(so * 9 / ip, 1) if so is not None and ip else None,
        "bb_per_9": round(bb * 9 / ip, 1) if bb is not None and ip else None,
        "hr_per_9": round(hra * 9 / ip, 1) if hra is not None and ip else None,
        "whip": round((bb + h) / ip, 2) if bb is not None and h is not None and ip else None,
    }
    return {k_: v for k_, v in out.items() if v is not None}


def parse_team_grids(batting_html: str | None, pitching_html: str | None,
                     season: int) -> dict[str, dict]:
    """Parse a team's batting + pitching grids into
    {normalized_name: {name, ncaa_id, season, batting{}, pitching{}}}."""
    by_name: dict[str, dict] = {}

    def _ingest(html, payload_fn, key):
        if not html:
            return
        _hdr, rows = _grid_rows(html)
        for r in rows:
            name = (r.get("Player") or "").strip()
            if not name:
                continue
            # NCAA renders "Last, First" — flip to "First Last" for matching.
            if "," in name:
                last, _, first = name.partition(",")
                name = f"{first.strip()} {last.strip()}".strip()
            payload = payload_fn(r)
            if len(payload) <= 1:  # only is_pitcher flag -> empty line, skip
                continue
            nk = _normalize_name(name)
            entry = by_name.setdefault(nk, {"name": name, "season": season,
                                            "ncaa_id": r.get("_pid")})
            entry[key] = payload
            entry.setdefault("ncaa_id", r.get("_pid"))

    _ingest(batting_html, _batting_payload, "batting")
    _ingest(pitching_html, _pitching_payload, "pitching")
    return by_name


# ---------------------------------------------------------------------------
# 3. headless render of a team's stat grids (shared browser session)
# ---------------------------------------------------------------------------
def render_team_grids(team_id: int, browser: "_NcaaBrowser", force: bool = False,
                      sides: set | None = None) -> tuple[str | None, str | None]:
    """Render only the stat sides this team actually needs (`sides` ⊆
    {"batting","pitching"}; defaults to both). Each render extracts just the
    `table#stat_grid`, waiting on a populated row so it returns the moment the
    data is ready. Disk-cached per team. Returns (batting_html, pitching_html)."""
    sides = sides or {"batting", "pitching"}
    base = TEAM_STATS_URL.format(team_id=team_id)
    GRID, ROW = "table#stat_grid", "table#stat_grid tbody tr"
    batting = pitching = None

    if "batting" in sides:
        batting = browser.html(base, f"ncaa_team_{team_id}_bat", force=force,
                               wait_selector=ROW, extract_selector=GRID)
        # If we actually loaded the (default=hitting) page, grab the season's
        # pitching category off its nav for free — saves a load on later teams.
        if browser._navigated and browser._pit_cat is None:
            browser._pit_cat = browser.pitching_category()

    if "pitching" in sides:
        cat = browser._pit_cat or browser.ensure_pit_cat(team_id)
        if cat:
            pitching = browser.html(f"{base}?year_stat_category_id={cat}",
                                    f"ncaa_team_{team_id}_pit", force=force,
                                    wait_selector=ROW, extract_selector=GRID)
    return (batting, pitching)


# ---------------------------------------------------------------------------
# 4. MLB draft-prospects API — identity backfill (no stats; sharpens matching)
# ---------------------------------------------------------------------------
def refresh_pipeline_identity(draft_year: int, force: bool = False) -> int:
    """Backfill `mlbam_id` (+ school when blank) on draft_players from the
    MLB draft-prospects feed. Conservative: exact normalized-name match,
    corroborated by school when both sides have one. Returns rows enriched."""
    fr = _fetch(MLB_DRAFT_PROSPECTS.format(year=draft_year),
                f"mlb_draft_prospects_{draft_year}", force=force, accept_json=True)
    if fr.status != 200 or not fr.body:
        log.warning("mlb draft prospects %s: HTTP %s", draft_year, fr.status)
        return 0
    try:
        feed = json.loads(fr.body)
    except (ValueError, TypeError):
        return 0
    prospects = feed.get("prospects") or []
    by_name: dict[str, dict] = {}
    for p in prospects:
        per = p.get("person") or {}
        nm = per.get("fullName")
        if not nm:
            continue
        by_name.setdefault(_normalize_name(nm), {
            "mlbam_id": per.get("id"),
            "school": (p.get("school") or {}).get("name"),
        })

    players = load_draft_players(draft_year=draft_year)
    updates = []
    for pk, dp in players.items():
        if dp.get("mlbam_id"):
            continue
        cand = by_name.get(_normalize_name(dp.get("player_name") or ""))
        if not cand or not cand.get("mlbam_id"):
            continue
        # Corroborate by school when both have one (conservative).
        ps, cs = dp.get("school"), cand.get("school")
        if ps and cs and _norm_school(ps) != _norm_school(cs):
            continue
        updates.append({
            "player_key": pk,
            "mlbam_id": cand["mlbam_id"],
            "school": dp.get("school") or cs,
        })
    if updates:
        backfill_draft_player_fields(updates)
    log.info("pipeline identity %s: enriched %d players", draft_year, len(updates))
    return len(updates)


# ---------------------------------------------------------------------------
# 5. NCAA D-I stats refresh (gap-fill) + orchestrator
# ---------------------------------------------------------------------------
def _players_needing_stats(draft_year: int | None) -> dict[str, dict]:
    """draft_players (optionally one class) that have NO draft_statlines yet."""
    players = load_draft_players(draft_year=draft_year)
    have = {r["player_key"] for r in load_draft_statlines()}
    return {pk: p for pk, p in players.items() if pk not in have}


def _prospect_sides(p: dict) -> set:
    """Which stat side(s) a prospect needs rendered — {"batting"} for a hitter,
    {"pitching"} for a pitcher, both for a two-way / unknown. Lets us skip the
    pitching page for an all-hitters team (and vice-versa). A position token
    ending in 'P' (RHP/LHP/SP/RP/P/SIRP…) marks the pitching side; anything
    else marks batting."""
    toks = [t for t in re.split(r"[/,\s]+", (p.get("position") or "").upper()) if t]
    if not toks:
        return {"batting", "pitching"}
    sides = set()
    for t in toks:
        sides.add("pitching" if t.endswith("P") else "batting")
    return sides or {"batting", "pitching"}


def refresh_ncaa_stats(draft_year: int, force: bool = False,
                       max_teams: int | None = None) -> int:
    """Fetch NCAA D-I box scores for `draft_year` prospects that still lack
    any statline. Renders only the teams that actually have a needed
    prospect. Returns the count of player season-rows upserted."""
    gap = _players_needing_stats(draft_year)
    if not gap:
        log.info("ncaa stats %s: no prospects need stats", draft_year)
        return 0

    total = 0
    with _NcaaBrowser() as browser:
        if not browser.available:
            return 0
        team_map = fetch_d1_team_map(draft_year, force=force, browser=browser)
        if not team_map:
            return 0

        # Group needed prospects by their (resolved) NCAA team id.
        by_team: dict[int, list[tuple[str, dict]]] = defaultdict(list)
        unresolved = 0
        for pk, p in gap.items():
            tid = team_map.get(_norm_school(p.get("school")))
            if tid is None:
                unresolved += 1
                continue
            by_team[tid].append((pk, p))
        log.info("ncaa stats %s: %d prospects across %d D-I teams (%d schools unresolved)",
                 draft_year, sum(len(v) for v in by_team.values()), len(by_team), unresolved)

        teams = list(by_team.items())
        if max_teams is not None:
            teams = teams[:max_teams]

        for tid, needers in teams:
            # Only render the side(s) some needed prospect actually uses.
            sides = set().union(*(_prospect_sides(p) for _pk, p in needers))
            batting, pitching = render_team_grids(tid, browser, force=force, sides=sides)
            if not batting and not pitching:
                continue
            roster = parse_team_grids(batting, pitching, season=draft_year)
            payloads = []
            for pk, p in needers:
                entry = roster.get(_normalize_name(p.get("player_name") or ""))
                if not entry:
                    log.info("ncaa: %s not found on team %s roster", pk, tid)
                    continue
                # Write whichever side(s) the player has (batting and/or pitching).
                for side_key in ("batting", "pitching"):
                    payload = entry.get(side_key)
                    if not payload:
                        continue
                    # Skip an empty side (a pitcher who shows up in the batting
                    # grid with no AB, or vice-versa) so we don't write a row
                    # of dashes.
                    if side_key == "batting" and not payload.get("ab"):
                        continue
                    if side_key == "pitching" and not payload.get("ip"):
                        continue
                    payload = dict(payload)
                    payload["source"] = "ncaa"
                    payload["ncaa_player_id"] = entry.get("ncaa_id")
                    payloads.append({
                        "player_key": pk,
                        "season": draft_year,
                        # distinct league suffix avoids a hitter/pitcher PK clash
                        "league": NCAA_LEAGUE + ("" if side_key == "batting" else " (P)"),
                        "team": p.get("school"),
                        "payload": payload,
                    })
            if payloads:
                total += upsert_draft_statlines(payloads)
    log.info("ncaa stats %s: upserted %d season rows", draft_year, total)
    return total


def refresh_college_fallback_stats(draft_year: int | None = None,
                                   force: bool = False) -> dict:
    """Orchestrate the second-source fill for prospects FG can't cover:
    (1) MLB-API identity backfill, then (2) NCAA D-I box scores. Runs for the
    given class, or the current + next draft year when `draft_year` is None.
    Returns per-step counts."""
    from datetime import date
    years = [draft_year] if draft_year else [date.today().year, date.today().year + 1]
    out = {"identity": 0, "ncaa": 0}
    for y in years:
        try:
            out["identity"] += refresh_pipeline_identity(y, force=force)
        except Exception:
            log.exception("pipeline identity crashed for %s", y)
        try:
            out["ncaa"] += refresh_ncaa_stats(y, force=force)
        except Exception:
            log.exception("ncaa stats crashed for %s", y)
    return out
