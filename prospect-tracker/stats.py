"""
Minor-league stats fetcher.

Why this module is split out from scrapers
------------------------------------------
The seven prospect-ranking sources tell us "who is on the list and what
do they think of him." This module answers the orthogonal question:
"what is he actually doing on the field right now?"

Architecture
------------
Two-step process per prospect:
  1. Resolve player name -> MLBAM ID using pybaseball's Chadwick Bureau
     lookup. The lookup is cached permanently to disk (player IDs don't
     change) so the monthly run hits pybaseball at most once per new
     prospect ever.
  2. Fetch current-season minor-league stat line from the official MLB
     Stats API (statsapi.mlb.com/api/v1/people/{id}/stats).

Why not pybaseball for the stats themselves?
--------------------------------------------
pybaseball's strength is MLB-level Statcast and FanGraphs scraping. Its
MiLB coverage is incomplete — there isn't a clean `statcast_batter_milb`
that returns season-level lines. The MLB Stats API endpoint we hit is
the same one mlb.com uses for player pages: free, unauthenticated,
returns clean JSON with one record per (player, season, league level),
and supports the `sportIds` query to filter to MiLB-only.

For Statcast-level data (exit velo, fastball spin) at the AAA level,
pybaseball.statcast_search with sportId=11 would work — but for a
monthly tracker, season-level slash lines and rate stats are the right
granularity. We expose `fetch_savant_summary` for future expansion.

What this module returns
------------------------
StatLine — one record per prospect representing the highest-level
minor-league line of the current season. If a player has been promoted
mid-season (e.g. High-A → Double-A), we report the highest level
reached, since that's what scouts are reacting to.

Failure modes
-------------
- Unknown player (no Chadwick match): logged, stat_line is None.
- Player has only MLB stats this season (i.e. graduated): stat_line is
  None and the consensus engine marks them graduated independently.
- Network failure / Stats API hiccup: logged, stat_line is None, monthly
  run continues. Stats are best-effort, not gating.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Iterable

import requests as _requests
import concurrent.futures
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Shared persistent Session with retries and connection pooling.
SESSION = _requests.Session()
retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500,502,503,504])
adapter = HTTPAdapter(max_retries=retries, pool_connections=100, pool_maxsize=100)
SESSION.mount("https://", adapter)
SESSION.mount("http://", adapter)

# Per-run cache TTL (seconds)
import hashlib
CACHE_TTL_SECONDS = 24 * 3600  # 24 hours

# Flag to globally force bypassing the on-disk cache. Run_monthly sets this
# when --force is used.
FORCE_REFETCH = False

# Proxy object named 'requests' so tests that patch stats.requests.get still work.
class _ReqProxy:
    def get(self, url, *args, force: bool = False, ttl: int | None = None, timeout: int = 15, **kwargs):
        """GET with simple on-disk caching keyed by URL.

        If FORCE_REFETCH is True or force is True, bypasses the cache.
        Returns a requests.Response-like object (actual requests.Response).
        """
        # Use module-level CACHE_TTL_SECONDS if not explicitly provided
        if ttl is None:
            ttl = CACHE_TTL_SECONDS
        # Resolve final force decision
        do_force = force or FORCE_REFETCH
        # Cache path derived from URL hash
        try:
            key = hashlib.md5(url.encode("utf-8")).hexdigest()
        except Exception:
            key = str(abs(hash(url)))
        cache_path = CACHE_DIR / f"mlb_{key}.json"

        # Cache hit
        if cache_path.exists() and not do_force:
            age = time.time() - cache_path.stat().st_mtime
            if age <= ttl:
                try:
                    text = cache_path.read_text(encoding="utf-8")
                    resp = _requests.Response()
                    resp.status_code = 200
                    resp._content = text.encode("utf-8")
                    resp.encoding = "utf-8"
                    resp.url = url
                    return resp
                except Exception:
                    # fall through to network fetch
                    pass

        # Network fetch (respects module rate limit)
        time.sleep(RATE_LIMIT_SECONDS)
        resp = SESSION.get(url, timeout=timeout, *args, **kwargs)
        try:
            resp.raise_for_status()
        except Exception as e:
            log.warning("HTTP request failed for %s: %s", url, e)
            # Fallback to stale cache if present
            if cache_path.exists():
                try:
                    text = cache_path.read_text(encoding="utf-8")
                    r = _requests.Response()
                    r.status_code = 200
                    r._content = text.encode("utf-8")
                    r.encoding = "utf-8"
                    r.url = url
                    return r
                except Exception:
                    pass
            raise

        # Write fresh cache (best-effort)
        try:
            cache_path.write_text(resp.text, encoding="utf-8")
        except Exception as e:
            log.debug("failed writing cache for %s: %s", url, e)
        return resp

    def __getattr__(self, name):
        return getattr(_requests, name)

requests = _ReqProxy()
import concurrent.futures

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
ID_CACHE_FILE = CACHE_DIR / "mlbam_ids.json"

MLB_STATS_API = "https://statsapi.mlb.com/api/v1"
RATE_LIMIT_SECONDS = 0.1

# MLB rookie eligibility thresholds (official rules).
# Exceeding either one means the player has lost prospect status.
ROOKIE_AB_THRESHOLD = 130    # career MLB at-bats
ROOKIE_IP_THRESHOLD = 50.0   # career MLB innings pitched

# Session-level cache for the full MLB+MiLB player name index.
# Built lazily on first call to resolve_mlbam_id that needs it.
# {normalized_key: (mlbam_id, birth_date_iso_or_empty)}
_FULL_PLAYER_INDEX: dict[str, tuple[int, str]] | None = None

# Alternate names to try in Path 3 when the prospect's full birth name
# differs from the name the MLB API uses (nickname, shortened first name, etc.)
# key = player_key used in our DB, value = alternate name to look up in the
# full player index.
_NAME_ALIASES: dict[str, str] = {
    "leodalis_de_vries": "Leo De Vries",
    "dominic_keegan":    "Dom Keegan",         # 681371 born 2000-08-01
    "leonardo_bernal":   "Leo Bernal",         # 699024 born 2004-02-13
    "markevian_hence":   "Tink Hence",         # 693311 born 2002-08-06
    "samuel_stafura":    "Sammy Stafura",      # 806230 born 2004-11-15
    "zachary_root":      "Zach Root",          # 702539 born 2004-02-06
}


def _build_full_player_index(season: int) -> dict[str, tuple[int, str]]:
    """
    Fetch all active affiliated-baseball players across every level for the
    season: MLB (sportId=1) plus AAA/AA/A+/A/Rk (11-16).

    Returns {normalized_name_key: (mlbam_id, birth_date)}.

    We search from lowest to highest level so that if the same player
    appears in multiple lists the MLB entry takes precedence (last write
    wins, and we iterate lowest→highest).

    Also walks back one season — early in the year the current-season MiLB
    rosters aren't fully published, and some prospects (Charlee Soto,
    Travis Sykora, Noble Meyer in May 2026) only appear in the prior-season
    rosters. Current-season entries overwrite prior-season ones.

    Called once per process; result is module-level cached.
    """
    global _FULL_PLAYER_INDEX
    if _FULL_PLAYER_INDEX is not None:
        return _FULL_PLAYER_INDEX

    index: dict[str, tuple[int, str]] = {}
    # Walk prior season first so current-season entries (newer affiliations)
    # win when both have the same player; lowest→highest per season so the
    # MLB record beats the MiLB record for the same player.
    for idx_season in (season - 1, season):
        for sport_id in (16, 14, 13, 12, 11, 1):
            url = f"{MLB_STATS_API}/sports/{sport_id}/players?season={idx_season}"
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                people = resp.json().get("people", [])
            except Exception as e:
                log.debug("player index fetch failed (sportId=%s, season=%s): %s",
                          sport_id, idx_season, e)
                time.sleep(RATE_LIMIT_SECONDS)
                continue
            for p in people:
                name = p.get("fullName", "")
                if not name:
                    continue
                # Skip placeholder API entries that have only a last name
                # (no firstName). These are stub records — matching them
                # caused false-positive ID resolutions like "JoJo Parker"
                # -> id=817866 ("Parker" with no first name).
                if not p.get("firstName"):
                    continue
                key = _norm_key(name)
                index[key] = (int(p["id"]), p.get("birthDate") or "")
            time.sleep(RATE_LIMIT_SECONDS)

    _FULL_PLAYER_INDEX = index
    log.info("full player index: %d players across all levels (seasons=%d,%d)",
             len(index), season - 1, season)
    return index


def compute_age_decimal(birth_date: str | None,
                        as_of: date | None = None) -> float | None:
    """
    Convert a birth date string ('YYYY-MM-DD') to a decimal age.

    Examples (as_of=2026-05-15):
        '2006-05-03' -> 20.0     (just turned 20)
        '2006-08-15' -> 19.7     (eight months from 20)
        '2008-01-10' -> 18.3

    Uses 365.25 as the year length to handle leap years correctly —
    matches the convention used by FanGraphs and Baseball-Reference for
    prospect age display.
    """
    if not birth_date:
        return None
    try:
        bd = date.fromisoformat(birth_date)
    except (ValueError, TypeError):
        return None
    if as_of is None:
        as_of = date.today()
    days = (as_of - bd).days
    if days < 0:
        return None  # birth date in the future; data error
    return round(days / 365.25, 1)


# Map MiLB level codes / league names -> short labels.
# When the API returns league.sport.name we get codes like "Triple-A".
# When it only returns league.name we get the actual league name like
# "Southern League" — we have to map those too.
LEVEL_LABELS = {
    # MLB
    "MLB": "MLB", "Major League Baseball": "MLB", "The Show": "MLB",
    "American League": "MLB", "National League": "MLB",
    # Sport codes
    "Triple-A": "AAA", "Double-A": "AA", "High-A": "A+", "Single-A": "A",
    "AAA": "AAA", "AA": "AA", "A+": "A+", "A": "A", "Rk": "Rk",
    # AAA leagues
    "International League": "AAA", "Pacific Coast League": "AAA",
    # AA leagues
    "Eastern League": "AA", "Southern League": "AA", "Texas League": "AA",
    # A+ leagues
    "Northwest League": "A+", "South Atlantic League": "A+",
    # A leagues
    "Carolina League": "A",  "California League": "A",
    "Midwest League": "A",   "Florida State League": "A",
    # Rookie / complex
    "Rookie": "Rk", "FCL": "CPX", "ACL": "CPX",
    "Florida Complex League": "CPX", "Arizona Complex League": "CPX",
    # DSL
    "Dominican Summer League": "DSL", "DSL": "DSL",
}
# MLB is highest; order matters — _highest_level picks lowest index = highest level
LEVEL_ORDER = ["MLB", "AAA", "AA", "A+", "A", "Rk", "CPX", "DSL"]


@dataclass
class StatLine:
    player_key: str
    mlbam_id: int
    level: str            # highest level reached this season ("MLB", "AAA", etc.)
    games: int
    # Hitting
    avg: str | None       # ".287"
    obp: str | None
    slg: str | None
    ops: str | None
    hr: int | None
    sb: int | None
    bb_pct: float | None
    k_pct: float | None
    # Pitching
    era: str | None
    fip: str | None
    ip: float | None
    k_per_9: float | None
    bb_per_9: float | None
    # Meta
    is_pitcher: bool
    fetched_at: str       # ISO date
    # Season this stat line is from. Usually the current season, but when a
    # player has no current-season stats (injury, late call-up, etc.) we fall
    # back to the most recent season that has any MiLB/MLB data.
    season: int | None = None
    # True when we couldn't find current-season stats and fell back to a
    # prior year. The UI surfaces this so users know they're seeing last year.
    is_prior_season: bool = False


@dataclass
class PitchArsenal:
    """Pitch-type breakdown for a pitcher — velocity and usage per pitch."""
    player_key: str
    mlbam_id: int
    season: int
    # List of {"pitch_type": "FF", "pitch_name": "4-Seam Fastball",
    #          "avg_speed": 96.2, "usage_pct": 0.42}
    pitches: list[dict]
    # Derived: fastball velocity (highest-usage "hard" pitch avg_speed)
    fb_velo: float | None
    fetched_at: str


@dataclass
class StatcastMetrics:
    """
    Batted-ball and quality-of-contact metrics from the MLB Stats API's
    sabermetrics stat type.  Available at AAA for most of the Statcast era
    (2020+); coverage at AA and below is spottier.

    For hitters:
      exit_velo       — avg exit velocity on contact (mph)
      hard_hit_pct    — % of batted balls ≥ 95 mph EV
      launch_angle    — avg launch angle (degrees)
      barrel_pct      — % of batted balls classified as barrels

    For pitchers (metrics are "against"):
      exit_velo       — avg EV allowed
      hard_hit_pct    — hard-hit rate allowed
      launch_angle    — avg LA allowed
      barrel_pct      — barrel rate allowed
    """
    player_key: str
    mlbam_id: int
    season: int
    is_pitcher: bool
    exit_velo: float | None
    hard_hit_pct: float | None
    launch_angle: float | None
    barrel_pct: float | None
    fetched_at: str


# ---------------------------------------------------------------------------
# ID resolution
# ---------------------------------------------------------------------------

def _load_id_cache() -> dict[str, int | None]:
    if ID_CACHE_FILE.exists():
        return json.loads(ID_CACHE_FILE.read_text())
    return {}


def _save_id_cache(cache: dict[str, int | None]):
    ID_CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True))


def _is_historical_stub(record: dict) -> bool:
    """
    True if an MLB Stats API people record looks like a 1920s-1940s player
    stub (no birthDate, plus a debut or lastPlayed year < 2010). Caching
    these instead of the real prospect causes silent stat-fetch failures.
    """
    if record.get("birthDate"):
        return False
    debut = record.get("mlbDebutDate") or ""
    last_played = record.get("lastPlayedDate") or ""
    for v in (debut, last_played):
        try:
            yr = int(v[:4]) if len(v) >= 4 else None
        except ValueError:
            yr = None
        if yr is not None and yr < 2010:
            return True
    return False


def _last_names_align(query_name: str, api_full_name: str) -> bool:
    """
    True if the MLB API result's name plausibly matches the query's last name.

    The /people/search endpoint does loose token matching, so a query for
    "Ricardo Yan" returns "Yandel Ricardo" because "Ricardo" matched as a
    first name. Require the query's last token to appear somewhere in the
    API name — checking the reverse direction would accept "ricardo" in
    "Yandel Ricardo" matching "Ricardo Yan" since both share the token.
    """
    q = _norm_key(query_name).replace("_", " ")
    a = _norm_key(api_full_name).replace("_", " ")
    if not q or not a:
        return True
    q_parts = q.split()
    a_parts = a.split()
    if not q_parts or not a_parts:
        return True
    return q_parts[-1] in a_parts


def _search_mlbam_via_api(player_name: str) -> tuple[int | None, str | None]:
    """
    Search the MLB Stats API for a player by name.

    Returns (mlbam_id, birth_date_iso) or (None, None).

    Two-pass strategy:
      1. active=true  — fastest; covers MLB 40-man roster players.
      2. No active filter — catches MiLB-only prospects not on a 40-man yet.
         We validate birth year >= 1994 on this pass to avoid matching
         historical players with the same name.

    Both passes reject:
      - historical-stub records (no birthDate, debut < 2010),
      - token-false-positive matches where the returned last name has no
        overlap with the queried last name (e.g. query "Ricardo Yan" →
        result "Yandel Ricardo": "Ricardo" matched as a first name).
    """
    import urllib.parse
    encoded = urllib.parse.quote_plus(player_name)

    for params in (
        f"names={encoded}&active=true",   # pass 1: active MLB roster
        f"names={encoded}",               # pass 2: all players (MiLB / recent signings)
    ):
        url = f"{MLB_STATS_API}/people/search?{params}"
        time.sleep(RATE_LIMIT_SECONDS)
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            people = resp.json().get("people", [])
        except Exception as e:
            log.debug("MLB people search failed for %s: %s", player_name, e)
            continue

        # Score every candidate and pick the best one in this pass. Both
        # passes can return multiple same-name hits (e.g. Wilmer Flores ID
        # 527038 = MLB veteran born 1991 + ID 695865 = MiLB prospect born
        # 2001). Always prefer the candidate with a prospect-era birth year.
        best: tuple[int, dict] | None = None
        for p in people:
            if _is_historical_stub(p):
                continue
            full_name = p.get("fullName", "")
            if not _last_names_align(player_name, full_name):
                continue
            bd = p.get("birthDate") or ""
            try:
                by = int(bd[:4]) if len(bd) >= 4 else None
            except ValueError:
                by = None
            # Drop pre-1994 births in every pass — no current prospect is
            # 32+ years old, regardless of active-roster status.
            if by is not None and by < 1994:
                continue
            score = 0
            if by is not None and by >= 1994:
                score += 10
            if p.get("active"):
                score += 1
            if best is None or score > best[0]:
                best = (score, p)
        if best is not None:
            p = best[1]
            return int(p["id"]), p.get("birthDate") or None

    return None, None


def resolve_mlbam_id(player_key: str, player_name: str) -> int | None:
    """
    Resolve 'konnor_griffin' / 'Konnor Griffin' -> MLBAM ID (e.g. 700000).

    Resolution order:
      1. Disk cache (instant, permanent once resolved)
      2. MLB Stats API people search (most up-to-date for current prospects;
         scores candidates so the prospect-era birth year wins same-name
         collisions like Wilmer Flores 1991 vs 2001)
      3. pybaseball Chadwick Bureau lookup (historical-player coverage as
         a fallback when API search returns nothing)
      4. Full MLB+MiLB sports/{id}/players index (last resort for prospects
         not in either of the above)
    """
    cache = _load_id_cache()
    if player_key in cache:
        return cache[player_key]

    mlbam_id = None

    # --- Path 1: MLB Stats API people search ---
    # Tried first because the API has better same-name disambiguation than
    # Chadwick (it knows birth years for current prospects; Chadwick often
    # only has the historical version of a shared name).
    api_id, _ = _search_mlbam_via_api(player_name)
    if api_id is not None:
        log.info("resolved %s via MLB people search (id=%s)", player_name, api_id)
        mlbam_id = api_id

    # --- Path 2: pybaseball Chadwick Bureau (exact match only) ---
    # NOTE: fuzzy=True is intentionally disabled here. The Chadwick fuzzy
    # matcher routinely returns wrong players (e.g. "Bryce Rainer" → Bryce
    # Miller, "Arjun Nimmala" → Aaron Nola).
    #
    # Filter out same-name historical players (mlb_played_last < 2018) so we
    # don't cache "Jamie Arnold" → 150374 (a 1974-born pitcher).
    if mlbam_id is None:
        try:
            from pybaseball import playerid_lookup
            parts = player_name.split(maxsplit=1)
            if len(parts) >= 2:
                first, last = parts[0], parts[1]
                try:
                    df = playerid_lookup(last, first, fuzzy=False)
                    if df is not None and not df.empty:
                        df_sorted = df.sort_values("key_mlbam", ascending=False)
                        if "mlb_played_last" in df_sorted.columns:
                            df_sorted = df_sorted[
                                df_sorted["mlb_played_last"].isna()
                                | (df_sorted["mlb_played_last"] >= 2018)
                            ]
                        if not df_sorted.empty:
                            mlbam_id = int(df_sorted.iloc[0]["key_mlbam"])
                except Exception as e:
                    log.debug("Chadwick exact lookup failed for %s: %s",
                              player_name, e)
        except ImportError:
            log.debug("pybaseball not installed; skipping Chadwick lookup")

    # --- Path 3: Full MLB+MiLB player index (all sport levels) ---
    # Covers prospects not on 40-man rosters who don't appear in the people
    # search endpoint (e.g. A+/AA players like Bryce Rainer, Liam Doyle).
    if mlbam_id is None:
        season = date.today().year
        full_idx = _build_full_player_index(season)
        entry = full_idx.get(_norm_key(player_name))
        if entry is None:
            # Try stripping Jr./Sr./II suffixes
            import re as _re2
            stripped = _re2.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$",
                                "", player_name, flags=_re2.IGNORECASE).strip()
            if stripped != player_name:
                entry = full_idx.get(_norm_key(stripped))
        if entry is None:
            # Try explicit name alias (e.g. "Leodalis De Vries" -> "Leo De Vries")
            alias = _NAME_ALIASES.get(player_key)
            if alias:
                entry = full_idx.get(_norm_key(alias))
        if entry is not None:
            cand_id, cand_bd = entry
            try:
                by = int(cand_bd[:4]) if len(cand_bd) >= 4 else None
            except ValueError:
                by = None
            if by is None or by >= 1994:
                log.info("resolved %s via full player index (id=%s)", player_name, cand_id)
                mlbam_id = cand_id

    if mlbam_id is None:
        log.warning(
            "could not resolve MLBAM ID for %s — caching null; "
            "delete entry from .cache/mlbam_ids.json to retry",
            player_name,
        )
        cache[player_key] = None  # suppress retries on future runs
        _save_id_cache(cache)
        return None

    cache[player_key] = mlbam_id
    _save_id_cache(cache)
    return mlbam_id


# ---------------------------------------------------------------------------
# Stat-line fetch via MLB Stats API
# ---------------------------------------------------------------------------

def _highest_level(splits: list[dict]) -> dict | None:
    """Pick the highest level from a list of season-stats splits.

    Now includes MLB as the highest possible level. The label lookup
    uses longest-match to avoid 'A' incorrectly matching 'Triple-A'.
    """
    by_level = {}
    for split in splits:
        league = split.get("league", {})
        level_code = (league.get("sport", {}) or {}).get("name") or league.get("name", "")
        if not level_code:
            continue
        # Find the best (longest key) label match to avoid 'A' matching 'Triple-A'
        label = None
        best_len = 0
        for key, lbl in LEVEL_LABELS.items():
            if key.lower() in level_code.lower() and len(key) > best_len:
                label = lbl
                best_len = len(key)
        if label is None or label not in LEVEL_ORDER:
            continue
        if label not in by_level or LEVEL_ORDER.index(label) < LEVEL_ORDER.index(by_level[label]["_level"]):
            split["_level"] = label
            by_level[label] = split
    if not by_level:
        return None
    return min(by_level.values(), key=lambda s: LEVEL_ORDER.index(s["_level"]))


def fetch_birth_date_by_name(player_name: str) -> tuple[int | None, str | None]:
    """
    One-shot: search for a player by name and return (mlbam_id, birth_date).

    This is the fallback path used by run_monthly when pybaseball can't
    resolve an ID. The MLB Stats API people-search endpoint often returns
    birthDate directly in the search result, so we can skip the second
    /people/{id} call entirely.
    """
    return _search_mlbam_via_api(player_name)


def fetch_birth_date(mlbam_id: int) -> str | None:
    """
    Fetch a player's birth date from the MLB Stats API people endpoint.
    Returns ISO date string ('YYYY-MM-DD') or None if unavailable.

    This is a separate call from fetch_statline because:
      - Birth date is immutable — fetch once, cache forever in the DB
      - Some players will have a birth date but no current stat line
        (graduated, on the 60-day IL, etc.)
    """
    url = f"{MLB_STATS_API}/people/{mlbam_id}"
    time.sleep(RATE_LIMIT_SECONDS)
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("birth date fetch failed for %s: %s", mlbam_id, e)
        return None

    people = data.get("people", [])
    if not people:
        return None
    return people[0].get("birthDate")  # e.g. "2006-05-03"


def _fetch_splits_for_season(mlbam_id: int, season: int,
                             is_pitcher: bool) -> list[dict]:
    """Fetch every split (MLB + every MiLB level) the player has in `season`.

    Two calls when needed: leagueListId=milb_full first (covers all MiLB
    levels); if the response is empty we retry without the filter to catch
    players whose only activity that year was at the MLB level.
    """
    group = "pitching" if is_pitcher else "hitting"
    # IMPORTANT: leagueListId=milb_full is required to get MiLB splits.
    # Without it, the API silently returns MLB-only stats.
    url = (
        f"{MLB_STATS_API}/people/{mlbam_id}/stats"
        f"?stats=season&group={group}&season={season}"
        f"&leagueListId=milb_full"
    )
    time.sleep(RATE_LIMIT_SECONDS)
    splits: list[dict] = []
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        for block in resp.json().get("stats", []):
            splits.extend(block.get("splits", []))
    except Exception as e:
        log.debug("MiLB fetch failed for %s season=%s: %s", mlbam_id, season, e)

    if splits:
        return splits

    # MLB fallback: player may have only MLB activity this season.
    mlb_url = (
        f"{MLB_STATS_API}/people/{mlbam_id}/stats"
        f"?stats=season&group={group}&season={season}"
    )
    time.sleep(RATE_LIMIT_SECONDS)
    try:
        resp = requests.get(mlb_url, timeout=15)
        resp.raise_for_status()
        for block in resp.json().get("stats", []):
            splits.extend(block.get("splits", []))
    except Exception as e:
        log.debug("MLB fallback fetch failed for %s season=%s: %s",
                  mlbam_id, season, e)
    return splits


# How many prior seasons to walk back to when the requested season has no
# stats. 3 covers most "no current-year data" cases (injury, college, holdout)
# without dragging in genuinely stale lines from 4+ years ago.
PRIOR_SEASON_LOOKBACK = 3


def fetch_statline(player_key: str, mlbam_id: int,
                   season: int, is_pitcher: bool = False,
                   for_mlb: bool = False) -> StatLine | None:
    """
    Fetch a player's stat line for the requested season.

    If the requested season has no stats anywhere (MLB or MiLB), walk back
    up to PRIOR_SEASON_LOOKBACK seasons looking for the most recent year
    with data. The returned StatLine carries `season` and `is_prior_season`
    so the UI can label fallbacks clearly.

    If the highest level is MLB:
      - for_mlb=True  → return the MLB stat line (used for graduates)
      - for_mlb=False → fall through and still return the MLB line; the
                        caller auto-graduates the player when level="MLB"
    """
    splits: list[dict] = []
    found_season = season
    is_prior = False
    for offset in range(PRIOR_SEASON_LOOKBACK + 1):
        try_season = season - offset
        splits = _fetch_splits_for_season(mlbam_id, try_season, is_pitcher)
        if splits:
            found_season = try_season
            is_prior = offset > 0
            break

    if not splits:
        return None

    best = _highest_level(splits)
    if best is None:
        return None

    if is_prior:
        log.info("%s: no %d stats — using %d (level=%s)",
                 player_key, season, found_season, best["_level"])

    at_mlb = best["_level"] == "MLB"

    # Active prospect detected at MLB level — caller should auto-graduate.
    # Return a minimal StatLine with level="MLB" as the signal; the stat
    # line itself will be populated correctly on the next run when the
    # player is fetched as a graduate.
    if at_mlb and not for_mlb:
        log.info("%s detected at MLB level — flagged for auto-graduation", player_key)
        # Still build and return the stat line so it's persisted
        # (the graduation logic in run_monthly handles the status change)
        pass  # fall through to stat line construction below

    stat = best.get("stat", {})
    if is_pitcher:
        return StatLine(
            player_key=player_key, mlbam_id=mlbam_id,
            level=best["_level"], games=int(stat.get("gamesPlayed", 0) or 0),
            avg=None, obp=None, slg=None, ops=None, hr=None, sb=None,
            bb_pct=None, k_pct=None,
            era=str(stat.get("era") or "—"),
            fip=None,                       # MLB Stats API doesn't expose FIP
            ip=float(stat.get("inningsPitched") or 0) if stat.get("inningsPitched") else None,
            k_per_9=_safe_float(stat.get("strikeoutsPer9Inn")),
            bb_per_9=_safe_float(stat.get("walksPer9Inn")),
            is_pitcher=True,
            fetched_at=date_today_iso(),
            season=found_season,
            is_prior_season=is_prior,
        )
    pa = stat.get("plateAppearances", 0) or 0
    bb = stat.get("baseOnBalls", 0) or 0
    so = stat.get("strikeOuts", 0) or 0
    return StatLine(
        player_key=player_key, mlbam_id=mlbam_id,
        level=best["_level"], games=int(stat.get("gamesPlayed", 0) or 0),
        avg=str(stat.get("avg") or "—"),
        obp=str(stat.get("obp") or "—"),
        slg=str(stat.get("slg") or "—"),
        ops=str(stat.get("ops") or "—"),
        hr=int(stat.get("homeRuns", 0) or 0),
        sb=int(stat.get("stolenBases", 0) or 0),
        bb_pct=round(100 * bb / pa, 1) if pa else None,
        k_pct=round(100 * so / pa, 1) if pa else None,
        era=None, fip=None, ip=None, k_per_9=None, bb_per_9=None,
        is_pitcher=False,
        fetched_at=date_today_iso(),
        season=found_season,
        is_prior_season=is_prior,
    )


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def date_today_iso() -> str:
    from datetime import date
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Pitch arsenal fetch
# ---------------------------------------------------------------------------

# These pitch-type codes represent "hard" pitches for fastball velo extraction
_HARD_PITCH_CODES = {"FF", "SI", "FC", "FT"}

def fetch_pitch_arsenal(player_key: str, mlbam_id: int,
                        season: int) -> PitchArsenal | None:
    """
    Fetch pitch-type breakdown for a pitcher.

    Hits:
      GET /api/v1/people/{id}/stats
        ?stats=pitchArsenal&group=pitching&season=YEAR

    Each split in the response has:
      split.stat.pitchType  : {"code": "FF", "description": "4-Seam Fastball"}
      split.stat.avgSpeed   : 96.2
      split.stat.percentage : 0.42
      split.stat.totalPitches / split.stat.pitchesPerGame (sometimes present)

    Returns None if the player has no arsenal data (common at A/A+).
    """
    url = (
        f"{MLB_STATS_API}/people/{mlbam_id}/stats"
        f"?stats=pitchArsenal&group=pitching&season={season}"
    )
    time.sleep(RATE_LIMIT_SECONDS)
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("pitchArsenal API failed for %s (%s): %s", player_key, mlbam_id, e)
        return None

    splits = []
    for block in data.get("stats", []):
        splits.extend(block.get("splits", []))
    if not splits:
        return None

    pitches = []
    for split in splits:
        stat = split.get("stat", {})
        pt = stat.get("pitchType") or {}
        code = pt.get("code", "")
        name = pt.get("description", code)
        avg_speed = _safe_float(stat.get("avgSpeed"))
        pct = _safe_float(stat.get("percentage"))
        if not code:
            continue
        pitches.append({
            "pitch_type": code,
            "pitch_name": name,
            "avg_speed": avg_speed,
            "usage_pct": round(pct, 3) if pct is not None else None,
        })

    if not pitches:
        return None

    # Fastball velo = avg speed of highest-usage hard pitch
    hard = [p for p in pitches if p["pitch_type"] in _HARD_PITCH_CODES
            and p["avg_speed"] is not None]
    fb_velo = None
    if hard:
        best = max(hard, key=lambda p: p["usage_pct"] or 0)
        fb_velo = round(best["avg_speed"], 1)

    return PitchArsenal(
        player_key=player_key, mlbam_id=mlbam_id, season=season,
        pitches=sorted(pitches, key=lambda p: -(p["usage_pct"] or 0)),
        fb_velo=fb_velo,
        fetched_at=date_today_iso(),
    )


# ---------------------------------------------------------------------------
# Statcast / sabermetrics fetch
# ---------------------------------------------------------------------------

def fetch_statcast_metrics(player_key: str, mlbam_id: int,
                           season: int,
                           is_pitcher: bool = False) -> StatcastMetrics | None:
    """
    Fetch Statcast batted-ball metrics via the MLB Stats API's sabermetrics
    stat type.

    Hits:
      GET /api/v1/people/{id}/stats
        ?stats=sabermetrics&group=hitting&season=YEAR   (hitters)
        ?stats=sabermetrics&group=pitching&season=YEAR  (pitchers)

    Key fields in split.stat:
      exitVelocity      : avg EV (mph)
      hardHitPercent    : hard-hit rate (0–1 float)
      launchAngle       : avg LA (degrees)
      barrelPercent     : barrel rate (0–1 float)

    Coverage: reliable at AAA/AA (2020+), spottier at A+/A.
    Returns None when no data is available at the player's level.
    """
    group = "pitching" if is_pitcher else "hitting"
    url = (
        f"{MLB_STATS_API}/people/{mlbam_id}/stats"
        f"?stats=sabermetrics&group={group}&season={season}"
    )
    time.sleep(RATE_LIMIT_SECONDS)
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("sabermetrics API failed for %s (%s): %s", player_key, mlbam_id, e)
        return None

    splits = []
    for block in data.get("stats", []):
        splits.extend(block.get("splits", []))
    if not splits:
        return None

    # Use the most recent / highest split (last in list is usually most recent)
    stat = splits[-1].get("stat", {})

    ev = _safe_float(stat.get("exitVelocity"))
    hh = _safe_float(stat.get("hardHitPercent"))
    la = _safe_float(stat.get("launchAngle"))
    bp = _safe_float(stat.get("barrelPercent"))

    # Return None if the API gave us nothing useful (no Statcast at this level)
    if all(v is None for v in [ev, hh, la, bp]):
        return None

    return StatcastMetrics(
        player_key=player_key, mlbam_id=mlbam_id, season=season,
        is_pitcher=is_pitcher,
        exit_velo=round(ev, 1) if ev is not None else None,
        hard_hit_pct=round(hh * 100, 1) if hh is not None else None,
        launch_angle=round(la, 1) if la is not None else None,
        barrel_pct=round(bp * 100, 1) if bp is not None else None,
        fetched_at=date_today_iso(),
    )


# ---------------------------------------------------------------------------
# Bulk fetch
# ---------------------------------------------------------------------------

def fetch_statlines_for(
    players: Iterable[tuple[str, str, bool]],
    season: int,
    for_mlb: bool = False,
    max_workers: int | None = None,
) -> dict[str, StatLine]:
    """
    Bulk-fetch stat lines.

    Strategy: resolve MLBAM IDs sequentially (cached, fast), then fetch
    stat lines concurrently using a ThreadPoolExecutor to overlap network I/O.

    Args:
      max_workers: optional cap on worker threads; if None, uses a safe default.
    """
    out: dict[str, StatLine] = {}

    # First, resolve MLBAM IDs (sequential to avoid racey cache writes)
    id_map: dict[str, tuple[int, bool]] = {}
    for key, name, is_pitcher in players:
        mlbam = resolve_mlbam_id(key, name)
        if mlbam is None:
            continue
        id_map[key] = (mlbam, is_pitcher)

    if not id_map:
        return out

    # Determine worker count
    if max_workers is None:
        worker_count = min(10, max(1, len(id_map)))
    else:
        worker_count = max(1, min(max(1, max_workers), len(id_map)))

    # Parallelize stat-line fetches (network-bound)
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as ex:
        future_to_key = {
            ex.submit(fetch_statline, key, mlbam, season,
                      is_pitcher=is_pitcher, for_mlb=for_mlb): key
            for key, (mlbam, is_pitcher) in id_map.items()
        }
        for fut in concurrent.futures.as_completed(future_to_key):
            key = future_to_key[fut]
            try:
                sl = fut.result()
                if sl is not None:
                    out[key] = sl
            except Exception as e:
                log.debug("statline fetch failed for %s: %s", key, e)

    return out


def statline_to_dict(sl: StatLine | None) -> dict | None:
    return asdict(sl) if sl is not None else None


# ---------------------------------------------------------------------------
# Bulk graduation detection
# ---------------------------------------------------------------------------

import re as _re
import unicodedata as _uc


def _norm_key(name: str) -> str:
    """Normalize a player name to the same key format used by scrapers.normalize_key."""
    s = _uc.normalize("NFKD", name)
    s = "".join(c for c in s if not _uc.combining(c))
    s = s.lower().strip()
    s = _re.sub(r"[^a-z0-9\s]", "", s)
    s = _re.sub(r"\s+", "_", s)
    return s


def fetch_mlb_player_index(season: int) -> dict[str, dict]:
    """
    Bulk fetch: all active MLB-roster players for the season in one request.

    Returns {normalized_player_key: info_dict} where info_dict contains:
        id, fullName, birthDate, mlbDebutDate, isPitcher

    This is the backbone of bulk graduation detection. One call covers the
    entire 40-man-roster universe (~1 100 players) so we don't need to make
    one HTTP request per prospect to check if they've reached the majors.

    Also doubles as a free bulk birth-date source for any player currently on
    an MLB roster.
    """
    url = f"{MLB_STATS_API}/sports/1/players?season={season}"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        people = resp.json().get("people", [])
    except Exception as e:
        log.warning("MLB player index fetch failed: %s", e)
        return {}

    index: dict[str, dict] = {}
    for p in people:
        name = p.get("fullName", "")
        if not name:
            continue
        key = _norm_key(name)
        info = {
            "id":           int(p["id"]),
            "fullName":     name,
            "birthDate":    p.get("birthDate"),
            "mlbDebutDate": p.get("mlbDebutDate"),
            "isPitcher":    p.get("primaryPosition", {}).get("type") == "Pitcher",
        }
        index[key] = info
        # Secondary index by ID so we can look up by cached MLBAM ID too
        index[f"__id_{p['id']}"] = info

    log.info("MLB player index loaded: %d players for %d", len(index) // 2, season)
    return index


def check_rookie_threshold(mlbam_id: int, is_pitcher: bool) -> tuple[bool, str | None]:
    """
    Check career MLB stats against the rookie eligibility thresholds.

    Returns (exceeded, debut_date):
        exceeded   — True if this player should be considered graduated
        debut_date — mlbDebutDate ISO string if we have it, else None
    """
    group = "pitching" if is_pitcher else "hitting"
    url = (f"{MLB_STATS_API}/people/{mlbam_id}/stats"
           f"?stats=career&group={group}&sportId=1")
    time.sleep(RATE_LIMIT_SECONDS)
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.debug("career stats check failed for mlbam %s: %s", mlbam_id, e)
        return False, None

    for block in data.get("stats", []):
        for split in block.get("splits", []):
            stat = split.get("stat", {})
            if is_pitcher:
                try:
                    ip = float(stat.get("inningsPitched") or 0)
                except ValueError:
                    ip = 0.0
                if ip >= ROOKIE_IP_THRESHOLD:
                    return True, None
            else:
                ab = int(stat.get("atBats") or 0)
                if ab >= ROOKIE_AB_THRESHOLD:
                    return True, None
    return False, None


def bulk_detect_graduations(
    active_players: list[tuple[str, str, bool]],
    season: int,
) -> dict[str, str | None]:
    """
    Efficiently detect which active prospects have graduated to MLB.

    Steps:
      1. One bulk call to get all current MLB players (~1 100 entries).
      2. Match each active prospect to the MLB index by normalised name key
         OR by a cached MLBAM ID.
      3. For each match, fetch career MLB stats to confirm the rookie
         threshold (130 AB / 50 IP) has been exceeded.
      4. Also cache any birth dates found in the bulk payload.

    Returns:
        {player_key: debut_date_or_None}
        where debut_date is the mlbDebutDate from the API (ISO string) or
        None if we couldn't determine the exact debut (uses today as
        fallback in run_monthly).

    Network cost: 1 bulk call + N targeted career-stats calls, where N is
    the number of matched prospects (typically 5-30 per run vs ~3 700
    individual stat calls for the naive approach).
    """
    id_cache = _load_id_cache()
    mlb_index = fetch_mlb_player_index(season)
    id_to_info = {info["id"]: info for key, info in mlb_index.items()
                  if not key.startswith("__id_")}

    graduates: dict[str, str | None] = {}
    birth_date_updates: dict[str, str] = {}

    for player_key, player_name, is_pitcher in active_players:
        # --- Try to find this prospect in the MLB player index ---
        info = None
        mlbam_id = id_cache.get(player_key)

        if mlbam_id is not None:
            # ID-based match — look up by MLBAM ID
            info = mlb_index.get(f"__id_{mlbam_id}")
            # Two sanity checks to guard against name-collision IDs that pybaseball
            # fuzzy matching may have put in the cache:
            # 1. Birth year must be >= 1994 (all prospects are born ~1994+).
            # 2. The MLB player's normalized name must match the prospect's player_key.
            #    Both checks use the full name so "Bryce Rainer" ≠ "Bryce Miller"
            #    and "Kade Anderson" ≠ "Drew Anderson" are correctly rejected.
            if info is not None:
                bd0 = info.get("birthDate") or ""
                try:
                    by0 = int(bd0[:4]) if len(bd0) >= 4 else None
                except ValueError:
                    by0 = None
                mlb_norm_key = _norm_key(info.get("fullName", ""))

                birth_ok = (by0 is None) or (by0 >= 1994)
                name_ok = (mlb_norm_key == player_key or
                           # Allow minor suffix differences (e.g. "Jr." variants)
                           mlb_norm_key.replace("_jr", "").replace("_ii", "")
                               == player_key.replace("_jr", "").replace("_ii", ""))

                if not birth_ok or not name_ok:
                    log.debug(
                        "Evicting cached ID for %s (mlbam=%s): "
                        "MLB player is '%s' born %s — name/age mismatch",
                        player_name, mlbam_id,
                        info.get("fullName", "?"), bd0,
                    )
                    del id_cache[player_key]
                    mlbam_id = None
                    info = None

        if info is None:
            # Name-based match: find candidate in MLB index
            candidate = mlb_index.get(_norm_key(player_name))
            if candidate is None:
                # Fallback: strip common suffixes (Jr., Sr., II, III)
                stripped = _re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "",
                                   player_name, flags=_re.IGNORECASE).strip()
                if stripped != player_name:
                    candidate = mlb_index.get(_norm_key(stripped))

            if candidate is not None:
                # Verify birth year and that the normalized names actually match
                # (not just a partial/fuzzy collision).
                bd = candidate.get("birthDate") or ""
                try:
                    birth_year = int(bd[:4]) if len(bd) >= 4 else None
                except ValueError:
                    birth_year = None
                cand_key = _norm_key(candidate.get("fullName", ""))
                birth_ok = (birth_year is None) or (birth_year >= 1994)
                name_ok = (cand_key == player_key or
                           cand_key.replace("_jr", "").replace("_ii", "")
                               == player_key.replace("_jr", "").replace("_ii", ""))
                if not birth_ok or not name_ok:
                    log.debug(
                        "Skipping name match for %s: MLB player is '%s' born %s "
                        "(name or birth-year mismatch)",
                        player_name, candidate.get("fullName", "?"), bd,
                    )
                    candidate = None

            if candidate is not None:
                info = candidate
                # Cache the resolved ID so future runs use the faster ID path
                id_cache[player_key] = info["id"]

        if info is None:
            continue  # not matched to any current MLB player

        # Cache the MLBAM ID if we didn't already have it
        mid = info["id"]
        if player_key not in id_cache:
            id_cache[player_key] = mid

        # Grab birth date while we have it for free
        if info.get("birthDate"):
            birth_date_updates[player_key] = info["birthDate"]

        # --- Check career MLB stats against rookie thresholds ---
        pit = is_pitcher or info.get("isPitcher", False)
        exceeded, debut_date = check_rookie_threshold(mid, pit)
        if exceeded:
            grad_date = info.get("mlbDebutDate") or debut_date
            graduates[player_key] = grad_date
            log.info("GRADUATED (auto-detect): %s  debut=%s", player_name, grad_date)

    _save_id_cache(id_cache)
    return graduates, birth_date_updates
