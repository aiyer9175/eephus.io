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
import re as _re
import time
import unicodedata as _uc
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
PLAYER_INDEX_CACHE_FILE = CACHE_DIR / "player_index.json"
PLAYER_INDEX_TTL_SECONDS = 24 * 3600

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


_PITCHER_POS_TOKENS = {"RHP", "LHP", "SP", "RP", "MIRP", "SIRP", "P"}
_INFIELD_POS_TOKENS = {"1B", "2B", "3B", "SS", "IF", "INF"}
_OUTFIELD_POS_TOKENS = {"OF", "CF", "LF", "RF"}


def _position_classes(pos: str | None) -> set[str]:
    """Map an MLB/MiLB position abbreviation to a coarse class for matching."""
    if not pos:
        return set()
    p = pos.upper().split("/")[0].strip()
    if p in _PITCHER_POS_TOKENS:
        return {"pitcher"}
    if p == "C":
        return {"catcher"}
    if p in _INFIELD_POS_TOKENS:
        return {"infield"}
    if p in _OUTFIELD_POS_TOKENS:
        return {"outfield"}
    if p == "DH":
        return {"infield", "outfield"}
    return {p}


def _position_matches(prospect_pos: str | None, api_pos: str | None) -> bool:
    """Loose match — pitcher vs hitter, infield vs outfield."""
    a = _position_classes(prospect_pos)
    b = _position_classes(api_pos)
    if not a or not b:
        return False
    return bool(a & b)


def _first_name_compatible(a: str, b: str) -> bool:
    """True if two normalized first names plausibly refer to the same person."""
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if long_.startswith(short) and len(short) >= 2:
        return True
    return len(a) >= 3 and len(b) >= 3 and a[:3] == b[:3]


# Targets the bulk player-index fetch hits. Sport IDs:
# 1=MLB, 11=AAA, 12=AA, 13=A+, 14=A, 16=Rookie complex.
_PLAYER_INDEX_SPORT_IDS = (1, 11, 12, 13, 14, 16)


class PlayerIndex:
    """
    In-memory + disk-cached index of every MLB/MiLB player from the
    /sports/{id}/players endpoints across the current + prior season.

    Holds full per-player metadata (id, fullName, birthDate, position,
    active, sport_id) and offers score-based candidate selection so that
    same-name collisions are resolved by birth-year, active flag, and
    position class — instead of "whoever the API search returns first."

    Bulk-fetched in parallel (12 concurrent calls completes in ~1.5s) and
    pickled to disk so subsequent process runs reuse it for ~50ms.
    """

    def __init__(self, season: int):
        self.season = season
        self.players: list[dict] = []
        self.by_name: dict[str, list[dict]] = {}
        self.by_last: dict[str, list[dict]] = {}

    # -- Loading ----------------------------------------------------------

    @classmethod
    def load_or_build(cls, season: int, force_rebuild: bool = False) -> "PlayerIndex":
        idx = cls(season)
        if not force_rebuild and PLAYER_INDEX_CACHE_FILE.exists():
            try:
                age = time.time() - PLAYER_INDEX_CACHE_FILE.stat().st_mtime
                if age <= PLAYER_INDEX_TTL_SECONDS:
                    data = json.loads(PLAYER_INDEX_CACHE_FILE.read_text(encoding="utf-8"))
                    players = data.get("players") or []
                    # Reject older caches that don't carry currentTeam — we
                    # rely on team info downstream for the affiliate roster
                    # view, so an upgrade requires a fresh fetch.
                    has_team_info = bool(players) and "current_team_id" in players[0]
                    if (data.get("season") == season and players and has_team_info):
                        idx._build_lookups(players)
                        log.info("loaded player index from disk: %d players (%.1f min old)",
                                 len(idx.players), age / 60)
                        return idx
            except Exception as e:
                log.debug("could not load cached player index: %s", e)
        idx._fetch_parallel()
        try:
            PLAYER_INDEX_CACHE_FILE.write_text(
                json.dumps({"season": season, "players": idx.players}),
                encoding="utf-8",
            )
        except Exception as e:
            log.debug("could not persist player index: %s", e)
        return idx

    def _fetch_parallel(self) -> None:
        """Fetch every (season, sport_id) combination concurrently."""
        targets: list[tuple[int, int]] = []
        # Walk prior season first so current-season records overwrite when
        # the same player appears in both.
        for s in (self.season - 1, self.season):
            for sport_id in _PLAYER_INDEX_SPORT_IDS:
                targets.append((s, sport_id))

        def fetch_one(t: tuple[int, int]) -> tuple[tuple[int, int], list[dict]]:
            season_, sport_id = t
            url = f"{MLB_STATS_API}/sports/{sport_id}/players?season={season_}"
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                return t, resp.json().get("people", [])
            except Exception as e:
                log.debug("player index fetch failed (sport=%s season=%s): %s",
                          sport_id, season_, e)
                return t, []

        # Collapse to one record per id, preferring the highest level
        # (MLB > AAA > AA > ...) and most recent season.
        by_id: dict[int, dict] = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(targets))) as ex:
            futures = [ex.submit(fetch_one, t) for t in targets]
            for fut in concurrent.futures.as_completed(futures):
                (season_, sport_id), people = fut.result()
                for p in people:
                    if not p.get("id") or not p.get("fullName"):
                        continue
                    # Skip placeholder entries (no firstName) — these caused
                    # bogus matches like "JoJo Parker" → id 817866 ("Parker").
                    if not p.get("firstName"):
                        continue
                    pid = int(p["id"])
                    ct = p.get("currentTeam") or {}
                    rec = {
                        "id": pid,
                        "fullName": p["fullName"],
                        "firstName": p.get("firstName", ""),
                        "lastName": p.get("lastName", ""),
                        "birthDate": p.get("birthDate") or "",
                        # MLB debut date when available — sport=1 returns it
                        # consistently, MiLB endpoints sometimes don't.
                        # We use it as the graduation_date when the bulk
                        # graduation scanner promotes a player.
                        "mlbDebutDate": p.get("mlbDebutDate") or "",
                        "position": (p.get("primaryPosition") or {}).get("abbreviation") or "",
                        "active": bool(p.get("active")),
                        "sport_id": sport_id,
                        "season": season_,
                        # currentTeam captured for the affiliate-roster view
                        # on the farm-system page. Pairs with the team
                        # affiliation map (fetch_team_affiliations) so we
                        # can group players by parent org + level.
                        "current_team_id":   int(ct.get("id")) if ct.get("id") else None,
                        "current_team_name": ct.get("name") or "",
                    }
                    existing = by_id.get(pid)
                    if existing is None or _is_better_record(rec, existing):
                        by_id[pid] = rec

        self._build_lookups(list(by_id.values()))
        log.info("built player index: %d unique players (seasons=%d,%d)",
                 len(self.players), self.season - 1, self.season)

    def _build_lookups(self, records: list[dict]) -> None:
        self.players = records
        self.by_name = {}
        self.by_last = {}
        self.by_id: dict[int, dict] = {}
        for r in records:
            self.by_name.setdefault(_norm_key(r["fullName"]), []).append(r)
            last = r.get("lastName") or ""
            if last:
                self.by_last.setdefault(_norm_key(last), []).append(r)
            self.by_id[r["id"]] = r

    def get_debut_date(self, mlbam_id: int) -> str | None:
        """Return the player's mlbDebutDate (ISO string), or None if unknown."""
        rec = self.by_id.get(mlbam_id)
        if rec and rec.get("mlbDebutDate"):
            return rec["mlbDebutDate"]
        return None

    # -- Lookup ------------------------------------------------------------

    def candidates_for(self, name: str) -> list[dict]:
        """Return every record that plausibly matches `name`."""
        norm = _norm_key(name)
        if norm in self.by_name:
            return list(self.by_name[norm])
        # Strip Jr./Sr./II-V suffixes
        stripped = _re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv|v)$",
                           "", name, flags=_re.IGNORECASE).strip()
        if stripped != name:
            stripped_key = _norm_key(stripped)
            if stripped_key in self.by_name:
                return list(self.by_name[stripped_key])
        # Last-name lookup with first-name prefix compatibility check
        # (handles "Dom Keegan" ↔ "Dominic Keegan").
        parts = stripped.split()
        if len(parts) >= 2:
            first_norm = _norm_key(parts[0])
            last_norm = _norm_key(parts[-1])
            same_last = self.by_last.get(last_norm, [])
            return [r for r in same_last
                    if _first_name_compatible(first_norm, _norm_key(r.get("firstName", "")))]
        return []

    def best_match(self, name: str, position: str | None = None,
                   player_key: str | None = None) -> dict | None:
        """
        Resolve a (name, position, player_key) tuple to the best candidate.

        Honors `_NAME_ALIASES` first. Then scores candidates by birth-year
        plausibility, position class match, and active flag.
        """
        if player_key:
            alias = _NAME_ALIASES.get(player_key)
            if alias:
                aliased = self.candidates_for(alias)
                if aliased:
                    return self._pick_best(aliased, position)
        candidates = self.candidates_for(name)
        if not candidates:
            return None
        return self._pick_best(candidates, position)

    @staticmethod
    def _pick_best(candidates: list[dict], position: str | None) -> dict | None:
        best_score = None
        best_rec = None
        for r in candidates:
            score = _score_candidate(r, position)
            if score is None:
                continue
            if best_score is None or score > best_score:
                best_score = score
                best_rec = r
        return best_rec


def _is_better_record(new: dict, existing: dict) -> bool:
    """When the same MLBAM id appears in multiple (season, sport) lists,
    keep the most-recent + highest-level record."""
    if new["season"] != existing["season"]:
        return new["season"] > existing["season"]
    # sport_id ascending = MLB(1) < AAA(11) < AA(12) < ...; lower wins.
    return new["sport_id"] < existing["sport_id"]


def _score_candidate(r: dict, position: str | None) -> int | None:
    """
    Score a candidate record for prospect-resolution; None means reject.

    Rejection rules:
      - Birth year < 1994 (no current prospect is 32+).

    Otherwise: more positive = better match. Position class match is the
    strongest signal (15), then prospect-era birth year (10), active (5).
    MLB-level records win slim margins so graduates resolve to their MLB id.
    """
    bd = r.get("birthDate") or ""
    try:
        by = int(bd[:4]) if len(bd) >= 4 else None
    except ValueError:
        by = None
    if by is not None and by < 1994:
        return None
    score = 0
    if bd:
        score += 20  # real player with known birth date
    if by is not None and by >= 1994:
        score += 10  # prospect-era
    if r.get("active"):
        score += 5
    if position and r.get("position") and _position_matches(position, r["position"]):
        score += 15
    if r.get("sport_id") == 1:
        score += 1   # MLB record beats MiLB on otherwise-tied scores
    return score


# Legacy alias for code that still expects a {name_key: (id, birth)} dict.
def _build_full_player_index(season: int) -> dict[str, tuple[int, str]]:
    """Compatibility shim around the new `PlayerIndex` class."""
    global _FULL_PLAYER_INDEX
    if _FULL_PLAYER_INDEX is not None:
        return _FULL_PLAYER_INDEX
    idx = PlayerIndex.load_or_build(season)
    flat: dict[str, tuple[int, str]] = {}
    for r in idx.players:
        flat[_norm_key(r["fullName"])] = (r["id"], r["birthDate"])
    _FULL_PLAYER_INDEX = flat
    return flat


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
    # A+ leagues (post-2021 realignment: Midwest moved to High-A)
    "Northwest League": "A+", "South Atlantic League": "A+",
    "Midwest League": "A+",
    # A leagues
    "Carolina League": "A",  "California League": "A",
    "Florida State League": "A",
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
class Sabermetrics:
    """
    Sabermetric quality stats from the MLB Stats API's sabermetrics
    stat type. Coverage: MLB only — the endpoint returns nothing for
    minor-league seasons. The UI falls back to level-relative proxies
    (OPS+ vs level / ERA- vs level) when these aren't available.

    Hitters (group=hitting):
      wrc_plus    — wRC+ (park & league adjusted; 100 = league average)
      woba        — wOBA (linear weights, scaled to OBP)
      war         — Wins Above Replacement (FanGraphs flavor via wRAA)

    Pitchers (group=pitching, metrics are "against the pitcher"):
      xfip        — Expected Fielding Independent Pitching
      fip         — Fielding Independent Pitching
      fip_minus   — FIP- (100 = league avg, lower is better)
      era_minus   — ERA- (100 = league avg, lower is better)
      war         — Wins Above Replacement (pitching)
    """
    player_key: str
    mlbam_id: int
    season: int
    is_pitcher: bool
    # Hitter sabermetrics
    wrc_plus: float | None
    woba: float | None
    # Pitcher sabermetrics
    xfip: float | None
    fip: float | None
    fip_minus: float | None
    era_minus: float | None
    # Shared
    war: float | None
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


def resolve_mlbam_id(player_key: str, player_name: str,
                     position: str | None = None) -> int | None:
    """
    Resolve 'konnor_griffin' / 'Konnor Griffin' -> MLBAM ID (e.g. 700000).

    Resolution order:
      1. Disk cache (instant, permanent once resolved)
      2. PlayerIndex (in-memory, bulk-prefetched at pipeline start). Disk-
         cached for 24h so subsequent process runs reuse it.
      3. MLB Stats API people search (for prospects not in any 2024-2026
         roster — pulls in just-signed J2s and similar edge cases).
      4. Chadwick Bureau (last-resort historical coverage).

    `position` (e.g. 'SS', 'RHP') is used to disambiguate same-name hits
    like Wilmer Flores (1B) vs Wilmer Flores (P) in step 2.
    """
    cache = _load_id_cache()
    if player_key in cache:
        return cache[player_key]

    mlbam_id = None

    # --- Path 1: PlayerIndex (bulk-fetched, in-memory) ---
    # The vast majority of resolutions land here. The index covers every
    # affiliated player in current + prior season and scores candidates by
    # birth year + position to avoid same-name collisions.
    try:
        idx = PlayerIndex.load_or_build(date.today().year)
        rec = idx.best_match(player_name, position=position, player_key=player_key)
        if rec is not None:
            mlbam_id = rec["id"]
            log.info("resolved %s via PlayerIndex (id=%s)", player_name, mlbam_id)
    except Exception as e:
        log.debug("PlayerIndex lookup failed for %s: %s", player_name, e)

    # --- Path 2: MLB Stats API people search ---
    # Catches prospects not on any 2024-2026 roster (J2 signings before
    # rosters are published, recent international amateur additions).
    if mlbam_id is None:
        api_id, _ = _search_mlbam_via_api(player_name)
        if api_id is not None:
            log.info("resolved %s via MLB people search (id=%s)", player_name, api_id)
            mlbam_id = api_id

    # --- Path 3: pybaseball Chadwick Bureau (exact match only) ---
    # Last-resort historical coverage. Filter out same-name retired players
    # (mlb_played_last < 2018) so "Jamie Arnold" → 150374 (a 1974-born
    # pitcher) doesn't sneak into the cache.
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


def bulk_resolve_ids(
    players: Iterable[tuple[str, str, str | None]],
    season: int | None = None,
    force_rebuild_index: bool = False,
    fallback_workers: int = 8,
) -> tuple[dict[str, int], dict[str, str], "PlayerIndex"]:
    """
    Resolve MLBAM IDs + birth dates for a batch of prospects in one pass.

    Args:
        players: iterable of (player_key, player_name, position).
                 `position` may be None; when provided it disambiguates
                 same-name hits in the player index.
        season: defaults to today's calendar year.
        force_rebuild_index: ignore the disk-cached PlayerIndex and refetch.
        fallback_workers: thread pool size for the MLB people-search fallback.

    Returns:
        (ids_by_key, birth_dates_by_key, player_index)

        ids_by_key contains every successfully-resolved prospect (both new
        and previously-cached). birth_dates_by_key only contains dates we
        just collected from the index — callers can upsert them directly.
        player_index is the built/loaded PlayerIndex so callers can reuse
        it for downstream lookups (e.g. mlbDebutDate) without rebuilding.

    Performance: ~1.5s one-time index fetch (or ~50ms on a warm cache),
    plus parallel /people/search fallbacks for prospects not in any roster.
    Replaces ~300ms-per-prospect of sequential API search calls.
    """
    if season is None:
        season = date.today().year

    triples = [(k, n, p) for k, n, p in players]
    cache = _load_id_cache()

    ids_out: dict[str, int] = {}
    bds_out: dict[str, str] = {}
    fallback_triples: list[tuple[str, str, str | None]] = []

    # Build / load the player index once for everyone
    idx = PlayerIndex.load_or_build(season, force_rebuild=force_rebuild_index)

    # Build a {id: birthDate} lookup so we can refresh birth dates even
    # for prospects whose MLBAM ID is already cached. This catches the
    # stale-DOB case where an earlier bad ID seeded the wrong birth date.
    bd_by_id: dict[int, str] = {r["id"]: r.get("birthDate") or ""
                                for r in idx.players if r.get("birthDate")}

    new_cache_entries = 0
    for key, name, position in triples:
        if key in cache:
            cid = cache[key]
            if cid is not None:
                ids_out[key] = cid
                # Refresh birth date from the index when available — covers
                # prospects whose DB birth_date is stale from a prior bad ID.
                idx_bd = bd_by_id.get(cid)
                if idx_bd:
                    bds_out[key] = idx_bd
            continue
        rec = idx.best_match(name, position=position, player_key=key)
        if rec is None:
            fallback_triples.append((key, name, position))
            continue
        ids_out[key] = rec["id"]
        cache[key] = rec["id"]
        new_cache_entries += 1
        if rec.get("birthDate"):
            bds_out[key] = rec["birthDate"]

    # Parallelize the MLB people-search fallback for prospects missing
    # from every roster.
    if fallback_triples:
        def _search(triple: tuple[str, str, str | None]):
            key, name, _ = triple
            return key, _search_mlbam_via_api(name)

        worker_count = max(1, min(fallback_workers, len(fallback_triples)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as ex:
            for key, (api_id, bd) in ex.map(_search, fallback_triples):
                if api_id is not None:
                    ids_out[key] = api_id
                    cache[key] = api_id
                    new_cache_entries += 1
                    if bd:
                        bds_out[key] = bd
                else:
                    cache[key] = None  # remember "unresolvable"

    if new_cache_entries:
        _save_id_cache(cache)

    log.info(
        "bulk_resolve_ids: %d resolved, %d new, %d via people-search fallback",
        len(ids_out), new_cache_entries, len(fallback_triples),
    )
    return ids_out, bds_out, idx


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

    Always issues BOTH calls and merges the results:
      - leagueListId=milb_full → every MiLB level (filter excludes MLB)
      - no filter              → MLB-only line for prospects who've debuted

    A previous version called these sequentially with a short-circuit
    ("MiLB first; only hit MLB if MiLB was empty"). That short-circuit
    silently dropped MLB splits for prospects with stints at BOTH levels,
    so `_highest_level` never saw an MLB record and auto-graduation by
    `level == "MLB"` was skipped — leaving freshly-debuted prospects on
    their org's farm summary indefinitely.
    """
    group = "pitching" if is_pitcher else "hitting"
    base = f"{MLB_STATS_API}/people/{mlbam_id}/stats?stats=season&group={group}&season={season}"
    urls = [
        f"{base}&leagueListId=milb_full",   # MiLB splits across all levels
        base,                                # MLB-only line
    ]

    splits: list[dict] = []
    seen_keys: set[tuple] = set()
    for url in urls:
        time.sleep(RATE_LIMIT_SECONDS)
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            for block in resp.json().get("stats", []):
                for s in block.get("splits", []):
                    # Dedup on (season, sport-or-league-name) so the
                    # MiLB-and-MLB calls don't double-count an A+ split that
                    # appears in both responses (rare but happens).
                    league = s.get("league") or {}
                    level_name = (league.get("sport") or {}).get("name") \
                                 or league.get("name", "")
                    key = (s.get("season"), level_name)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    splits.append(s)
        except Exception as e:
            log.debug("stats fetch failed for %s season=%s url=%s: %s",
                      mlbam_id, season, url, e)
    if not splits:
        # The season endpoint currently omits some complex-league lines
        # (notably ACL/FCL) even though yearByYear returns them. Fall back
        # to yearByYear for the requested season so the player card can show
        # the same current slash line as the career table.
        yy_url = (
            f"{MLB_STATS_API}/people/{mlbam_id}/stats"
            f"?stats=yearByYear&group={group}&leagueListId=mlb_milb"
        )
        try:
            resp = requests.get(yy_url, timeout=15)
            resp.raise_for_status()
            for block in resp.json().get("stats", []):
                for s in block.get("splits", []):
                    if str(s.get("season") or "") == str(season):
                        splits.append(s)
        except Exception as e:
            log.debug("yearByYear stats fallback failed for %s season=%s url=%s: %s",
                      mlbam_id, season, yy_url, e)
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
# Career year-by-year fetch
# ---------------------------------------------------------------------------

# How many recent seasons to keep when building the prospect-page career
# table. The yearByYear endpoint returns every season the player has on
# record (incl. amateur lookalikes for some players); we cap to the most
# recent N so the table stays scannable.
CAREER_SEASONS_KEPT = 5


def fetch_career_stats(player_key: str, mlbam_id: int,
                       is_pitcher: bool = False) -> list[dict] | None:
    """
    Pull year-by-year MiLB + MLB splits for one player in a single call.

    Returns a list of {season, level, level_label, games, ip / pa, ...}
    one row per (season, highest level reached that year). Returns None
    if the API gave us nothing.

    The yearByYear endpoint returns one split per (season, league/level),
    so a player with stints at A+/AA in 2025 produces two rows. We
    collapse to the HIGHEST level per season since that's what scouts
    react to — the per-level breakdown rarely matters on the profile
    page and would clutter the table.

    Single-call: `leagueListId=mlb_milb` returns MLB + every MiLB level in
    one response, replacing the prior two-URL pattern (milb_full + MLB).
    Falls back to the two-URL pattern only if the combined call yields no
    splits (defensive for API edge cases).
    """
    group = "pitching" if is_pitcher else "hitting"
    base = f"{MLB_STATS_API}/people/{mlbam_id}/stats?stats=yearByYear&group={group}"
    combined_url = f"{base}&leagueListId=mlb_milb"

    raw_splits: list[dict] = []
    try:
        resp = requests.get(combined_url, timeout=15)
        resp.raise_for_status()
        for block in resp.json().get("stats", []):
            raw_splits.extend(block.get("splits", []))
    except Exception as e:
        log.debug("career fetch failed for %s url=%s: %s", mlbam_id, combined_url, e)

    # Fallback: if the combined call returned nothing, try the legacy
    # two-URL pattern. This protects against the API silently rejecting
    # leagueListId=mlb_milb for some players/seasons.
    if not raw_splits:
        for url in (f"{base}&leagueListId=milb_full", base):
            try:
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                for block in resp.json().get("stats", []):
                    raw_splits.extend(block.get("splits", []))
            except Exception as e:
                log.debug("career fetch fallback failed for %s url=%s: %s",
                          mlbam_id, url, e)

    if not raw_splits:
        return None

    # Group by season and pick the highest level per year.
    by_season: dict[str, dict] = {}
    for s in raw_splits:
        season = str(s.get("season") or "")
        if not season:
            continue
        league = s.get("league") or {}
        level_name = (league.get("sport") or {}).get("name") \
                     or league.get("name", "")
        # Map to short label using same logic as _highest_level
        label = None
        best_len = 0
        for key, lbl in LEVEL_LABELS.items():
            if key.lower() in level_name.lower() and len(key) > best_len:
                label = lbl
                best_len = len(key)
        if label is None or label not in LEVEL_ORDER:
            continue
        existing = by_season.get(season)
        if existing is None or LEVEL_ORDER.index(label) < LEVEL_ORDER.index(existing["_level"]):
            s["_level"] = label
            s["_level_label"] = level_name
            by_season[season] = s

    if not by_season:
        return None

    out: list[dict] = []
    for season in sorted(by_season, reverse=True):
        s = by_season[season]
        stat = s.get("stat", {})
        row = {
            "season": int(season),
            "level": s["_level"],
            "level_label": s["_level_label"],
            "games": int(stat.get("gamesPlayed", 0) or 0),
        }
        if is_pitcher:
            row.update({
                "era": str(stat.get("era") or "—"),
                "ip": float(stat.get("inningsPitched") or 0)
                       if stat.get("inningsPitched") else None,
                "k_per_9": _safe_float(stat.get("strikeoutsPer9Inn")),
                "bb_per_9": _safe_float(stat.get("walksPer9Inn")),
                "whip": _safe_float(stat.get("whip")),
                "wins": int(stat.get("wins", 0) or 0),
                "losses": int(stat.get("losses", 0) or 0),
                "is_pitcher": True,
            })
        else:
            pa = stat.get("plateAppearances", 0) or 0
            bb = stat.get("baseOnBalls", 0) or 0
            so = stat.get("strikeOuts", 0) or 0
            row.update({
                "avg": str(stat.get("avg") or "—"),
                "obp": str(stat.get("obp") or "—"),
                "slg": str(stat.get("slg") or "—"),
                "ops": str(stat.get("ops") or "—"),
                "hr":  int(stat.get("homeRuns", 0) or 0),
                "sb":  int(stat.get("stolenBases", 0) or 0),
                "rbi": int(stat.get("rbi", 0) or 0),
                # Raw at-bats — kept for the bulk graduation pass so we can
                # sum MLB-level rows against the 130-AB rookie threshold
                # without making a separate `/people/{id}/stats?stats=career`
                # call per prospect.
                "ab":  int(stat.get("atBats", 0) or 0),
                "bb_pct": round(100 * bb / pa, 1) if pa else None,
                "k_pct":  round(100 * so / pa, 1) if pa else None,
                "is_pitcher": False,
            })
        out.append(row)
    return out[:CAREER_SEASONS_KEPT]


# ---------------------------------------------------------------------------
# Bulk season-stats fetch
# ---------------------------------------------------------------------------

# Sport-id → short level label. Mirrors the per-player path's LEVEL_LABELS
# mapping but keyed on the unambiguous sport id, which the bulk season
# endpoint returns directly. Avoids the league-name parsing the per-player
# path needs (where "INT" can mean International League / AAA).
_SPORT_ID_TO_LEVEL = {
    1:  "MLB",
    11: "AAA",
    12: "AA",
    13: "A+",
    14: "A",
    16: "Rk",
}

# Sports covered by the bulk season-stats path. Matches the per-player
# leagueListId=mlb_milb coverage for the level set that all five FV
# sources actually grade. Complex-league levels (CPX) and DSL fall through
# to per-player career fetch, same as the existing behavior.
BULK_STATS_SPORT_IDS: tuple[int, ...] = (1, 11, 12, 13, 14, 16)


def _career_row_from_bulk_split(split: dict, group: str) -> dict | None:
    """Turn one /stats?stats=season split into a row in the same shape as
    fetch_career_stats output, so the rest of the pipeline (career table,
    statline derivation, graduation threshold) can consume it without
    branching on origin."""
    sport = split.get("sport") or {}
    sport_id = sport.get("id")
    label = _SPORT_ID_TO_LEVEL.get(sport_id)
    if label is None or label not in LEVEL_ORDER:
        return None
    season = split.get("season")
    if not season:
        return None
    stat = split.get("stat") or {}
    is_pitcher = (group == "pitching")
    row: dict = {
        "season": int(season),
        "level": label,
        # Use the human-readable sport abbreviation/name for the detail-page
        # tooltip (e.g. "AAA"); falls back to the short label.
        "level_label": sport.get("abbreviation") or label,
        "games": int(stat.get("gamesPlayed", 0) or 0),
    }
    if is_pitcher:
        row.update({
            "era":     str(stat.get("era") or "—"),
            "ip":      float(stat.get("inningsPitched") or 0)
                       if stat.get("inningsPitched") else None,
            "k_per_9": _safe_float(stat.get("strikeoutsPer9Inn")),
            "bb_per_9":_safe_float(stat.get("walksPer9Inn")),
            "whip":    _safe_float(stat.get("whip")),
            "wins":    int(stat.get("wins", 0) or 0),
            "losses":  int(stat.get("losses", 0) or 0),
            "is_pitcher": True,
        })
    else:
        pa = stat.get("plateAppearances", 0) or 0
        bb = stat.get("baseOnBalls", 0) or 0
        so = stat.get("strikeOuts", 0) or 0
        row.update({
            "avg":    str(stat.get("avg") or "—"),
            "obp":    str(stat.get("obp") or "—"),
            "slg":    str(stat.get("slg") or "—"),
            "ops":    str(stat.get("ops") or "—"),
            "hr":     int(stat.get("homeRuns", 0) or 0),
            "sb":     int(stat.get("stolenBases", 0) or 0),
            "rbi":    int(stat.get("rbi", 0) or 0),
            "ab":     int(stat.get("atBats", 0) or 0),
            "bb_pct": round(100 * bb / pa, 1) if pa else None,
            "k_pct":  round(100 * so / pa, 1) if pa else None,
            "is_pitcher": False,
        })
    return row


def bulk_fetch_season_stats(
    season: int,
    group: str,
    sport_ids: Iterable[int] = BULK_STATS_SPORT_IDS,
    page_size: int = 5000,
) -> dict[int, dict]:
    """Bulk-fetch one season of stats for every player across the given
    sports, returning {mlbam_id: career_row}.

    Replaces ~3000 per-player /people/{id}/stats?stats=yearByYear calls
    with one paginated call per (sport, group) — typically 1-2 pages per
    combo. The returned rows match the shape fetch_career_stats produces
    so they can be merged into career_cache directly.

    When a player has stints at multiple levels in the same season, the
    HIGHEST level (per LEVEL_ORDER) wins — same rule the per-player path
    uses when collapsing yearByYear splits.
    """
    out: dict[int, dict] = {}
    for sport_id in sport_ids:
        offset = 0
        while True:
            url = (
                f"{MLB_STATS_API}/stats?stats=season"
                f"&group={group}&season={season}"
                f"&sportIds={sport_id}"
                f"&limit={page_size}&offset={offset}"
            )
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log.debug(
                    "bulk season stats fetch failed (sport=%s season=%s "
                    "group=%s offset=%d): %s",
                    sport_id, season, group, offset, e,
                )
                break
            splits: list[dict] = []
            for block in data.get("stats", []):
                splits.extend(block.get("splits", []))
            if not splits:
                break
            for s in splits:
                player = s.get("player") or {}
                pid = player.get("id")
                if not pid:
                    continue
                row = _career_row_from_bulk_split(s, group)
                if row is None:
                    continue
                pid = int(pid)
                existing = out.get(pid)
                if (existing is None
                        or LEVEL_ORDER.index(row["level"])
                        < LEVEL_ORDER.index(existing["level"])):
                    out[pid] = row
            if len(splits) < page_size:
                break
            offset += page_size
    log.info("bulk_fetch_season_stats season=%d group=%s sports=%s: %d players",
             season, group, list(sport_ids), len(out))
    return out


def merge_bulk_into_career_cache(
    bulk_by_mlbam: dict[int, dict],
    career_cache: dict[str, list[dict]],
    id_cache: dict[str, int],
    season: int,
    eligible_keys: set[str] | None = None,
) -> dict[str, list[dict]]:
    """Splice the bulk fetch's current-season rows into the per-player
    career cache and return the {key: rows} subset that changed so the
    caller can persist it.

    For each player with a bulk row: drop any existing row for `season`,
    insert the bulk row at the top of the list, cap to CAREER_SEASONS_KEPT.
    Players are skipped if `eligible_keys` is provided and they aren't in
    it (used to exclude graduates from the in-season update).
    """
    updates: dict[str, list[dict]] = {}
    for key, mlbam in id_cache.items():
        if eligible_keys is not None and key not in eligible_keys:
            continue
        if mlbam is None:
            continue
        bulk_row = bulk_by_mlbam.get(int(mlbam))
        if bulk_row is None:
            continue
        existing = career_cache.get(key) or []
        filtered = [r for r in existing if r.get("season") != season]
        filtered.insert(0, bulk_row)
        merged = filtered[:CAREER_SEASONS_KEPT]
        updates[key] = merged
        career_cache[key] = merged
    return updates


# ---------------------------------------------------------------------------
# Per-player transactions fetch  →  drives level-change detection AND the
# options / debut-date / service-time heuristics.
# ---------------------------------------------------------------------------

# How many seasons of transaction history to pull. Six covers the full
# pre-arb + arbitration window for any active prospect; older rows aren't
# load-bearing for any downstream derivation.
TRANSACTIONS_LOOKBACK_SEASONS = 7


def fetch_player_transactions(player_key: str, mlbam_id: int,
                              start_year: int | None = None,
                              end_year: int | None = None) -> list[dict]:
    """
    Pull every transaction touching one player in a window of seasons.

    Hits `/api/v1/transactions?playerId={id}&startDate=...&endDate=...`.
    The endpoint accepts a playerId filter (undocumented but supported)
    and returns minor-league affiliate assignments, contract selections,
    options, recalls, IL placements, etc. We normalize each record to a
    minimal flat shape so downstream consumers don't have to walk the
    nested API JSON every time.

    The MLB Stats API description field is latin-1 in places (accented
    names like "Jesús" come through as garbage) — we decode best-effort
    so we don't store mojibake.
    """
    today = date.today()
    if start_year is None:
        start_year = today.year - TRANSACTIONS_LOOKBACK_SEASONS
    if end_year is None:
        end_year = today.year
    url = (f"{MLB_STATS_API}/transactions"
           f"?playerId={mlbam_id}"
           f"&startDate={start_year}-01-01"
           f"&endDate={end_year}-12-31")
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.debug("player transactions fetch failed for %s (id=%s): %s",
                  player_key, mlbam_id, e)
        return []
    out: list[dict] = []
    for tx in data.get("transactions", []):
        ft = tx.get("fromTeam") or {}
        tt = tx.get("toTeam") or {}
        desc = tx.get("description") or ""
        # MLB Stats API ships accented names as latin-1 in some descriptions;
        # try a best-effort decode pass before storing.
        if "�" in desc or any(ord(c) > 127 for c in desc):
            try:
                desc = desc.encode("latin-1", "ignore").decode("utf-8", "ignore") or desc
            except Exception:
                pass
        out.append({
            "date": tx.get("date") or tx.get("effectiveDate") or "",
            "type_code": tx.get("typeCode") or "",
            "type_desc": tx.get("typeDesc") or "",
            "description": desc,
            "from_team_id": ft.get("id"),
            "from_team_name": ft.get("name") or "",
            "to_team_id": tt.get("id"),
            "to_team_name": tt.get("name") or "",
        })
    out.sort(key=lambda r: r.get("date") or "")
    return out


def bulk_fetch_player_transactions(
        tasks: list[tuple[str, int]],
        max_workers: int = 8,
) -> dict[str, list[dict]]:
    """Concurrent per-player transactions fetcher.

    `tasks` is a list of (player_key, mlbam_id). Returns
    {player_key: [tx_rows]} for every player whose fetch produced at
    least one row (empty results are dropped to keep the cache lean).
    """
    if not tasks:
        return {}
    out: dict[str, list[dict]] = {}
    worker_count = max(1, min(max_workers, len(tasks)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as ex:
        future_to_key = {
            ex.submit(fetch_player_transactions, key, mlbam): key
            for key, mlbam in tasks if mlbam is not None
        }
        for fut in concurrent.futures.as_completed(future_to_key):
            key = future_to_key[fut]
            try:
                rows = fut.result()
                if rows:
                    out[key] = rows
            except Exception as e:
                log.debug("player transactions fetch failed for %s: %s", key, e)
    return out


# ---------------------------------------------------------------------------
# Level-change derivation — turn transactions + team affiliations into
# {date, from_level, to_level, kind} events the front-end can render as
# promotion/demotion markers on each prospect's chart.
# ---------------------------------------------------------------------------

# Lower index = higher level. Reused from LEVEL_ORDER above for callers
# that want to import this directly (level_changes works on the same set).
_LEVEL_RANK = {lvl: i for i, lvl in enumerate(LEVEL_ORDER)}


def _level_rank(level: str | None) -> int | None:
    """Return position in LEVEL_ORDER (0 = MLB ... N = DSL). Lower is higher level."""
    if not level:
        return None
    return _LEVEL_RANK.get(level)


# Transaction type_code values we treat as "this row changed the player's
# affiliation/level". The MLB Stats API codes:
#   ASG — Assignment (most MiLB affiliate moves)
#   SC  — Status change (optioned, recalled, activated, status change)
#   SE  — Selected contract (MLB call-up — 40-man addition + roster move)
#   OPT — Optioned to MiLB
#   REC — Recalled to MLB
#   TR  — Trade
#   PUR — Purchased contract
#   CLM — Waiver claim
#   REL — Released
#   RET — Returned to org (Rule 5)
#   OUT — Sent outright off 40-man to MiLB
_LEVEL_AFFECTING_TYPE_CODES = {
    "ASG", "SC", "SE", "OPT", "REC", "TR", "PUR", "CLM", "RET", "REL", "OUT",
}

# Phrases in transaction descriptions that mark a row as exhibition /
# administrative — NOT a real affiliate move. Spring training invites
# and Futures-Game roster blips are the big false positives; we filter
# them out so a prospect's chart doesn't show a fake Rk → MLB →
# whatever blip every February.
_NON_LEVEL_CHANGE_PHRASES = (
    "spring training",
    "non-roster",
    "invited",
    "all-star",
    "futures",
    " futures ",
    "exhibition",
    # Rehab assignments don't change a player's roster status — they're
    # an IL stint where the player plays MiLB games to ramp back up.
    # Filter them so an injured MLB player doesn't get a fake AAA/AA
    # "demotion" marker every July.
    "sent on a rehab",
    "sent on rehab",
    "rehab assignment",
    "rehabilitation assignment",
    "transferred to a rehab",
    # Affiliate "Prospects" rosters (e.g. "Milwaukee Brewers Prospects
    # activated SS X.") are template placeholder teams the API uses for
    # back-fields and offseason instructionals; they're never the actual
    # parent club. Match the verb that always pairs with them.
    "prospects activated",
    "prospects assigned",
)

# Team-name suffixes that mark non-affiliate placeholders (e.g. "Brewers
# Prospects" stand-ins, "National League Futures" rosters). We never
# treat moves TO one of these as a level change.
_PLACEHOLDER_TEAM_PHRASES = (
    " prospects",
    " futures",
    "all-stars",
    "all-star",
)

# Verbs that MUST appear in the description for a move TO the parent MLB
# club to count as a real call-up. Without one of these, "X assigned to
# <Parent MLB Team>" is always spring training / exhibition. Affiliate
# moves don't go through this gate — only the MLB destination.
_REAL_MLB_PROMOTION_VERBS = (
    "selected the contract",
    "purchased the contract",
    "recalled",
    "called up",
    "claimed off waivers",
    "returned ",          # Rule 5 returns to drafting team
)


def _is_placeholder_team(name: str | None) -> bool:
    if not name:
        return False
    low = name.lower()
    return any(p in low for p in _PLACEHOLDER_TEAM_PHRASES)


def derive_level_changes(transactions: list[dict],
                          team_affiliations: dict[int, dict]) -> list[dict]:
    """
    Walk a player's transactions in date order, resolve each move's
    from/to level via the team_affiliations map, and emit one record per
    actual level change.

    Returns events shaped like:
      {date, kind: 'promotion'|'demotion', from_level, to_level,
       from_team, to_team}

    The function tracks a "current level" cursor so back-to-back
    same-level affiliate swaps (e.g. AA → AA for a trade) don't produce
    spurious events. Spring-training invites, Futures-Game roster blips
    and the affiliate "Prospects" placeholder teams are filtered out
    because they'd otherwise produce ghost promotions every February.
    """
    out: list[dict] = []
    current_level: str | None = None
    current_team_id: int | None = None
    current_team_name: str | None = None
    for tx in transactions:
        date_iso = tx.get("date") or ""
        if not date_iso:
            continue
        type_code = tx.get("type_code") or ""
        if type_code and type_code not in _LEVEL_AFFECTING_TYPE_CODES:
            continue
        desc_low = (tx.get("description") or "").lower()
        if any(p in desc_low for p in _NON_LEVEL_CHANGE_PHRASES):
            # Spring training / exhibition / placeholder row — never a
            # real affiliate move, even when the API team_id resolves.
            continue
        to_id = tx.get("to_team_id")
        from_id = tx.get("from_team_id")
        to_info = team_affiliations.get(int(to_id)) if to_id else None
        from_info = team_affiliations.get(int(from_id)) if from_id else None
        to_name = (to_info or {}).get("name") or tx.get("to_team_name")
        from_name = (from_info or {}).get("name") or tx.get("from_team_name")
        to_level = (to_info or {}).get("level")
        from_level = (from_info or {}).get("level") or current_level
        if not to_level:
            continue
        if _is_placeholder_team(to_name) or _is_placeholder_team(tx.get("to_team_name")):
            continue
        # Moves TO the parent MLB team need an explicit promotion verb,
        # otherwise they're spring training / non-roster invites which
        # don't represent a real level change.
        if to_level == "MLB":
            if not any(v in desc_low for v in _REAL_MLB_PROMOTION_VERBS):
                continue
        # First move ever — seed the cursor without emitting unless we
        # also have a different from_level recorded explicitly via a
        # resolvable from-team.
        if current_level is None:
            current_level = to_level
            current_team_id = to_id
            current_team_name = to_name
            if from_info and from_level and from_level != to_level:
                rk_to = _level_rank(to_level)
                rk_from = _level_rank(from_level)
                if rk_to is not None and rk_from is not None:
                    out.append({
                        "date": date_iso,
                        "kind": "promotion" if rk_to < rk_from else "demotion",
                        "from_level": from_level,
                        "to_level": to_level,
                        "from_team": from_name,
                        "to_team":   to_name,
                    })
            continue
        if to_level == current_level:
            # Same-level move (cross-affiliate trade, lateral assignment) —
            # update the team cursor but don't emit a level event.
            current_team_id = to_id
            current_team_name = to_name
            continue
        rk_to = _level_rank(to_level)
        rk_from = _level_rank(current_level)
        if rk_to is None or rk_from is None:
            current_level = to_level
            current_team_id = to_id
            current_team_name = to_name
            continue
        out.append({
            "date": date_iso,
            "kind": "promotion" if rk_to < rk_from else "demotion",
            "from_level": current_level,
            "to_level": to_level,
            # Prefer the API's from-team when it told us one; otherwise
            # fall back to the cursor (which tracks where the player WAS
            # before this row, e.g. for SC activations that omit fromTeam).
            "from_team": from_name if from_info else current_team_name,
            "to_team":   to_name,
        })
        current_level = to_level
        current_team_id = to_id
        current_team_name = to_name
    return out


# ---------------------------------------------------------------------------
# Roster-status derivation — MLB debut, 40-man state, options used,
# career-year bucket, and an approximate service phase. All driven by the
# per-player transactions cache + career_stats (which we already have).
# Pure CPU pass, no HTTP. The heuristic intentionally rounds the
# real-world rules — those depend on day-by-day roster status the public
# Stats API doesn't expose — but it gets us the visualization that drives
# "options remaining" on each prospect card.
# ---------------------------------------------------------------------------

# Rookie-status exhaustion thresholds (current MLB rules):
#   - Position players: 130 MLB at-bats
#   - Pitchers: 50 MLB innings pitched
# A player who crosses either threshold loses rookie eligibility and is
# considered "graduated" by every consensus prospect-tracking source.
ROOKIE_AB_THRESHOLD = 130
ROOKIE_IP_THRESHOLD = 50.0

# Standard MLB option allotment. Players added to a 40-man get three
# option YEARS — distinct seasons in which they spend >20 days on an
# optional MiLB assignment. A small subset of players get a fourth
# option granted; we don't try to detect that case automatically.
DEFAULT_OPTIONS = 3


def derive_roster_status(transactions: list[dict],
                          career_rows: list[dict] | None,
                          today: date | None = None,
                          *,
                          api_debut_date: str | None = None) -> dict:
    """
    Build the MLB roster-status snapshot for one player.

    Returns:
      {
        mlb_debut_date     : ISO date of the first `selected the contract`
                              event into the parent MLB team (or None).
        on_40_man          : True after a `selected the contract` and not
                              yet `sent outright` off the 40-man.
        options_used       : count of distinct seasons in which an `OPT`
                              row fired (max 3 with default rules).
        options_used_years : sorted list of the option years above.
        options_remaining  : max(0, DEFAULT_OPTIONS - options_used).
        mlb_seasons        : list of seasons (ascending) with any MLB
                              games on file from career_stats.
        career_mlb_ab      : sum of MLB at-bats from career_stats.
        career_mlb_ip      : sum of MLB innings pitched from career_stats.
        rookie_exhausted   : True once the AB threshold, IP threshold,
                              OR options-exhaustion rule fires.
        graduation_reason  : 'ab_threshold' | 'ip_threshold' |
                              'options_exhausted' | None — explains which
                              gate flipped rookie_exhausted on. None when
                              the player is still a prospect.
        service_phase      : 'none' | 'pre_arb' | 'arb_eligible' | 'post_arb'
                              — best-effort bucket from MLB seasons + debut.
      }

    `transactions` should be the cached payload from
    fetch_player_transactions. `career_rows` is the cached career_stats
    list for the same player (highest-level-per-season rows).
    """
    today = today or date.today()
    career_rows = career_rows or []

    # 40-man selection isn't an MLB debut — a Rule 5 protection add in
    # November selects a player to the 40-man without them ever playing.
    # We separately track the contract-selection date (used to gate
    # options-exhaustion's "has the team committed?" question) and the
    # actual MLB debut date (used as the display marker). When the MLB
    # Stats API surfaces an authoritative mlbDebutDate via PlayerIndex
    # we prefer that; otherwise we fall back to the first contract-
    # selection event but ONLY if the career rows actually show MLB
    # activity (games / AB / IP > 0).
    selection_date: str | None = None
    on_40_man = False
    options_seasons: set[int] = set()

    for tx in transactions or []:
        date_iso = tx.get("date") or ""
        desc_low = (tx.get("description") or "").lower()
        type_code = tx.get("type_code") or ""
        if not date_iso:
            continue
        # Skip exhibition / spring training rows so they don't claim a
        # debut date or flip the 40-man flag.
        if any(p in desc_low for p in _NON_LEVEL_CHANGE_PHRASES):
            continue
        # 40-man add (typeCode "SE" or any row with "selected the contract").
        if type_code == "SE" or "selected the contract" in desc_low \
                or "purchased the contract" in desc_low:
            on_40_man = True
            if not selection_date:
                selection_date = date_iso
        # 40-man drop — "sent outright" clears once the player passes
        # through waivers off the 40-man roster.
        elif "sent outright" in desc_low or "removed from the 40" in desc_low:
            on_40_man = False
        # Option year — count any optioning event by season.
        if type_code == "OPT" or "optioned" in desc_low:
            try:
                yr = int(date_iso[:4])
                # Don't count September call-down / instructional moves
                # before active rosters expanded — but the public API
                # doesn't distinguish, so we accept any optioning in the
                # season as a used option.
                options_seasons.add(yr)
            except ValueError:
                pass

    # MLB games played by season (from career_stats) — drives both the
    # service-phase bucket and the rookie-exhaustion threshold check.
    mlb_seasons: list[int] = []
    mlb_ab_total = 0
    mlb_ip_total = 0.0
    for row in career_rows:
        if row.get("level") != "MLB":
            continue
        try:
            yr = int(row.get("season"))
        except (TypeError, ValueError):
            continue
        if (row.get("games") or 0) > 0 or (row.get("ab") or 0) > 0 \
                or (row.get("ip") or 0) > 0:
            mlb_seasons.append(yr)
        mlb_ab_total += int(row.get("ab") or 0)
        ip_raw = row.get("ip")
        if ip_raw:
            try:
                mlb_ip_total += float(ip_raw)
            except (TypeError, ValueError):
                pass
    mlb_seasons = sorted(set(mlb_seasons))
    has_mlb_activity = bool(mlb_seasons) or mlb_ab_total > 0 or mlb_ip_total > 0

    # Resolve the displayed debut date. The MLB API's mlbDebutDate (passed
    # in as `api_debut_date` via PlayerIndex) is authoritative when set.
    # Without that we fall back to the first contract-selection event,
    # BUT only if the player has actually appeared in an MLB game — a
    # Rule 5 protection in November selects a player to the 40-man
    # without ever putting them on the field, and we don't want that
    # date to render as a "debut" in the transaction history.
    if api_debut_date:
        debut_date = api_debut_date
    elif selection_date and has_mlb_activity:
        debut_date = selection_date
    else:
        debut_date = None

    # Rookie / prospect status is lost when the player crosses any of:
    #   * 130 career MLB at-bats         (hitters)
    #   * 50  career MLB innings pitched (pitchers)
    #   * has burned all minor-league options AND has at least debuted
    #     in MLB — a player with no options left can't be sent down
    #     without clearing waivers, so the team has effectively committed
    #     the roster spot. The 45-day active-roster MLB rule from the
    #     official rookie definition isn't tractable via the public API,
    #     so options-exhaustion is the practical proxy.
    options_exhausted = (len(options_seasons) >= DEFAULT_OPTIONS
                         and debut_date is not None)
    if mlb_ab_total > ROOKIE_AB_THRESHOLD:
        graduation_reason: str | None = "ab_threshold"
    elif mlb_ip_total > ROOKIE_IP_THRESHOLD:
        graduation_reason = "ip_threshold"
    elif options_exhausted:
        graduation_reason = "options_exhausted"
    else:
        graduation_reason = None
    rookie_exhausted = graduation_reason is not None

    # Service phase: a rough bucket from MLB seasons played.
    #   none         → 0 MLB seasons
    #   pre_arb      → 1–3 MLB seasons since debut
    #   arb_eligible → 4–6 MLB seasons since debut
    #   post_arb     → 7+ MLB seasons since debut
    n_mlb = len(mlb_seasons)
    if n_mlb == 0 and not debut_date:
        service_phase = "none"
    elif n_mlb >= 7:
        service_phase = "post_arb"
    elif n_mlb >= 4:
        service_phase = "arb_eligible"
    else:
        service_phase = "pre_arb"

    options_used = min(DEFAULT_OPTIONS, len(options_seasons))
    options_remaining = max(0, DEFAULT_OPTIONS - options_used)

    return {
        "mlb_debut_date":     debut_date,
        "on_40_man":          bool(on_40_man),
        "options_used":       options_used,
        "options_used_years": sorted(options_seasons),
        "options_remaining":  options_remaining,
        "mlb_seasons":        mlb_seasons,
        "career_mlb_ab":      mlb_ab_total,
        "career_mlb_ip":      round(mlb_ip_total, 1),
        "rookie_exhausted":   bool(rookie_exhausted),
        "graduation_reason":  graduation_reason,
        "service_phase":      service_phase,
        "injury_history":     derive_injury_history(transactions or []),
    }


# ---------------------------------------------------------------------------
# Injury history derivation — walk transactions to extract every IL stint.
# Reuses the placement / transfer / activation / rehab regexes defined
# below for fetch_il_status (same parsing rules, same edge-case handling).
# ---------------------------------------------------------------------------


def _il_stint_reason(desc: str | None) -> str | None:
    """Return the injury phrase ('Right elbow sprain') from the trailing
    sentence of an IL placement description. The API always puts the
    diagnosis after the period that ends the verb clause, when known."""
    if not desc:
        return None
    # Split at the LAST period before any trailing whitespace and take
    # the final non-empty fragment.
    parts = [p.strip() for p in desc.rstrip(".").split(". ")]
    if len(parts) < 2:
        return None
    tail = parts[-1]
    # Sanity guard: skip if the tail still reads like a verb clause.
    low = tail.lower()
    if low.startswith(("placed", "transferred", "activated", "reinstated", "sent")):
        return None
    return tail or None


def derive_injury_history(transactions: list[dict]) -> list[dict]:
    """
    Walk a player's transactions in date order to extract IL stints.

    Returns a list of {since, until, type, reason, description, days,
    active} dicts, oldest first. `since` carries the retroactive date
    when the placement specified one (the real injury date); otherwise
    it's the placement-row date. `until` is None for the currently-open
    stint; `days` is computed if both ends are known.

    `type` is the IL type the stint ENDED at — i.e. "60-day" if a
    15-day stint got transferred to the 60-day. Consolidates a player's
    "transferred to 60-day" follow-up into the original stint rather
    than treating it as a second injury.

    Reuses _IL_PLACE_RE / _IL_TRANSFER_RE / _IL_ACTIVATE_RE / _REHAB_RE
    from the fetch_il_status path so placement-vs-rehab detection stays
    consistent across the codebase.
    """
    out: list[dict] = []
    open_stint: dict | None = None
    for tx in transactions or []:
        date_iso = tx.get("date") or ""
        desc = (tx.get("description") or "").strip()
        if not desc or not date_iso:
            continue
        if (tx.get("type_code") or "").upper() != "SC":
            # IL events are always SC. ASG/SE rows can't open or close
            # an IL stint, even when their descriptions happen to mention
            # 'rehab' (e.g. "sent on a rehab assignment to Norfolk Tides"
            # comes back as ASG and would otherwise muddle the logic).
            continue
        if _REHAB_RE.search(desc):
            # Rehab assignments leave the player on IL — neither open
            # nor close a stint.
            continue
        m_act = _IL_ACTIVATE_RE.search(desc)
        m_trans = _IL_TRANSFER_RE.search(desc)
        m_place = _IL_PLACE_RE.search(desc)
        if m_act and open_stint is not None:
            open_stint["until"] = date_iso
            open_stint["active"] = False
            try:
                s = date.fromisoformat(open_stint["since"])
                e = date.fromisoformat(date_iso)
                open_stint["days"] = (e - s).days
            except ValueError:
                pass
            out.append(open_stint)
            open_stint = None
            continue
        if m_trans and open_stint is not None:
            open_stint["type"] = m_trans.group(1)
            if not open_stint.get("reason"):
                open_stint["reason"] = _il_stint_reason(desc)
            open_stint["description"] = desc
            continue
        if m_place:
            # Close any prior open stint defensively (should not happen
            # under normal API ordering, but a missed activation row
            # would otherwise leave an old stint dangling forever).
            if open_stint is not None:
                open_stint["until"] = date_iso
                open_stint["active"] = False
                try:
                    s = date.fromisoformat(open_stint["since"])
                    e = date.fromisoformat(date_iso)
                    open_stint["days"] = (e - s).days
                except ValueError:
                    pass
                out.append(open_stint)
            retro_iso = _parse_il_retro_date(m_place.group(2))
            open_stint = {
                "since":       retro_iso or date_iso,
                "until":       None,
                "type":        m_place.group(1),
                "reason":      _il_stint_reason(desc),
                "description": desc,
                "days":        None,
                "active":      True,
            }
    if open_stint is not None:
        out.append(open_stint)
    return out


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
      split.stat.type          : {"code": "FF", "description": "Four-seam FB"}
      split.stat.averageSpeed  : 96.2
      split.stat.percentage    : 0.42
      split.stat.count / split.stat.totalPitches (sometimes present)

    Returns None if the player has no arsenal data (common at A/A+).

    NB: The MLB Stats API renamed `pitchType` → `type` and `avgSpeed` →
    `averageSpeed` at some point. Earlier versions of this function read
    the old field names and silently returned no pitches for every call.
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
        # MLB Stats API uses `type` (with `code`/`description`) and
        # `averageSpeed`. Older versions of this API used `pitchType` and
        # `avgSpeed` — keep them as fallbacks in case any cached responses
        # or older endpoints still surface the legacy shape.
        pt = stat.get("type") or stat.get("pitchType") or {}
        code = pt.get("code", "")
        name = pt.get("description", code)
        avg_speed = _safe_float(stat.get("averageSpeed"))
        if avg_speed is None:
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
# Sabermetrics fetch (wRC+, xFIP, wOBA, FIP, etc.)
# ---------------------------------------------------------------------------

def fetch_sabermetrics(player_key: str, mlbam_id: int,
                       season: int,
                       is_pitcher: bool = False) -> Sabermetrics | None:
    """
    Fetch sabermetric quality stats via the MLB Stats API.

    Hits:
      GET /api/v1/people/{id}/stats
        ?stats=sabermetrics&group=hitting&season=YEAR   (hitters)
        ?stats=sabermetrics&group=pitching&season=YEAR  (pitchers)

    Hitter fields in split.stat:
      wRcPlus   : wRC+ (park & league-adjusted, 100 = league avg)
      woba      : wOBA (linear weights, scaled to OBP)
      war       : Wins Above Replacement

    Pitcher fields in split.stat:
      xfip      : Expected Fielding Independent Pitching
      fip       : Fielding Independent Pitching
      fipMinus  : FIP- (100 = league avg, lower is better)
      eraMinus  : ERA- (same scale)
      war       : Wins Above Replacement (pitching)

    Coverage: MLB only. Minor leagues are not in this endpoint, so this
    will return None for any prospect that has not yet played in the
    majors. The UI handles that with a level-relative proxy (OPS+ /
    ERA-) computed in storage.py.
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

    # Use the most recent split (last in list is usually most recent season slice)
    stat = splits[-1].get("stat", {})

    if is_pitcher:
        xfip       = _safe_float(stat.get("xfip"))
        fip        = _safe_float(stat.get("fip"))
        fip_minus  = _safe_float(stat.get("fipMinus"))
        era_minus  = _safe_float(stat.get("eraMinus"))
        war        = _safe_float(stat.get("war"))
        if all(v is None for v in (xfip, fip, fip_minus, era_minus, war)):
            return None
        return Sabermetrics(
            player_key=player_key, mlbam_id=mlbam_id, season=season,
            is_pitcher=True,
            wrc_plus=None, woba=None,
            xfip=round(xfip, 2) if xfip is not None else None,
            fip=round(fip, 2) if fip is not None else None,
            fip_minus=round(fip_minus, 1) if fip_minus is not None else None,
            era_minus=round(era_minus, 1) if era_minus is not None else None,
            war=round(war, 2) if war is not None else None,
            fetched_at=date_today_iso(),
        )

    # Hitters
    wrc_plus = _safe_float(stat.get("wRcPlus"))
    woba     = _safe_float(stat.get("woba"))
    war      = _safe_float(stat.get("war"))
    if all(v is None for v in (wrc_plus, woba, war)):
        return None
    return Sabermetrics(
        player_key=player_key, mlbam_id=mlbam_id, season=season,
        is_pitcher=False,
        wrc_plus=round(wrc_plus, 1) if wrc_plus is not None else None,
        woba=round(woba, 3) if woba is not None else None,
        xfip=None, fip=None, fip_minus=None, era_minus=None,
        war=round(war, 2) if war is not None else None,
        fetched_at=date_today_iso(),
    )


# ---------------------------------------------------------------------------
# Bulk derive — current-season statline from cached career_stats
# ---------------------------------------------------------------------------
# `fetch_career_stats` already returns every season the player has on
# record in a SINGLE HTTP call (mlb_milb combined endpoint). So once the
# career cache is warm, we can derive the current-season StatLine without
# any further API traffic — including the "no current-year stats; walk
# back to the most recent season with data" fallback that used to fire a
# fresh HTTP call per prospect per year.
#
# Strategy:
#   - For each (key, is_pitcher), look up career_cache[key] (already
#     deduped to highest-level-per-season by fetch_career_stats).
#   - Pick the most recent row whose season ≤ target_season, within
#     PRIOR_SEASON_LOOKBACK years.
#   - Map that row's fields onto a StatLine (same shape fetch_statline
#     would have returned), tagging is_prior_season when the chosen row
#     pre-dates the target season.
#
# Graduates aren't passed through this path (run_monthly skips them); the
# `for_mlb=True` call site continues to use fetch_statline.

def derive_statline_from_career(
    player_key: str, mlbam_id: int,
    career_rows: list[dict],
    target_season: int,
    is_pitcher: bool | None = None,
) -> StatLine | None:
    """Build a StatLine from cached career_stats rows. No HTTP."""
    if not career_rows:
        return None
    # career_stats is already collapsed to one row per (season, highest
    # level reached). Sort descending so the freshest in-range season wins.
    sorted_rows = sorted(
        (r for r in career_rows if r.get("season") is not None),
        key=lambda r: r["season"],
        reverse=True,
    )
    chosen = None
    for row in sorted_rows:
        s = row["season"]
        if s > target_season:
            continue
        if (target_season - s) > PRIOR_SEASON_LOOKBACK:
            break  # sorted desc, no point looking further
        chosen = row
        break
    if chosen is None:
        return None

    found_season = chosen["season"]
    is_prior = found_season < target_season
    is_p = bool(is_pitcher if is_pitcher is not None else chosen.get("is_pitcher"))
    level = chosen.get("level") or "?"

    if is_p:
        return StatLine(
            player_key=player_key, mlbam_id=mlbam_id,
            level=level, games=int(chosen.get("games", 0) or 0),
            avg=None, obp=None, slg=None, ops=None, hr=None, sb=None,
            bb_pct=None, k_pct=None,
            era=str(chosen["era"]) if chosen.get("era") is not None else None,
            fip=None,
            ip=_safe_float(chosen.get("ip")),
            k_per_9=_safe_float(chosen.get("k_per_9")),
            bb_per_9=_safe_float(chosen.get("bb_per_9")),
            is_pitcher=True,
            fetched_at=date_today_iso(),
            season=found_season,
            is_prior_season=is_prior,
        )
    return StatLine(
        player_key=player_key, mlbam_id=mlbam_id,
        level=level, games=int(chosen.get("games", 0) or 0),
        avg=str(chosen["avg"]) if chosen.get("avg") is not None else None,
        obp=str(chosen["obp"]) if chosen.get("obp") is not None else None,
        slg=str(chosen["slg"]) if chosen.get("slg") is not None else None,
        ops=str(chosen["ops"]) if chosen.get("ops") is not None else None,
        hr=int(chosen.get("hr") or 0),
        sb=int(chosen.get("sb") or 0),
        bb_pct=_safe_float(chosen.get("bb_pct")),
        k_pct=_safe_float(chosen.get("k_pct")),
        era=None, fip=None, ip=None, k_per_9=None, bb_per_9=None,
        is_pitcher=False,
        fetched_at=date_today_iso(),
        season=found_season,
        is_prior_season=is_prior,
    )


def derive_statlines_from_career(
    players: Iterable[tuple[str, str, bool]],
    career_cache: dict[str, list[dict]],
    target_season: int,
    id_cache: dict[str, int],
) -> dict[str, StatLine]:
    """Bulk-derive statlines from the cached career_stats payload.

    Replaces the previous bulk-fetch-statlines call (which made up to 8
    HTTP calls per prospect with no current-year stats while walking
    back through prior seasons). Returns the same shape dict.
    """
    out: dict[str, StatLine] = {}
    fallback_count = 0
    missing_count = 0
    no_career_count = 0
    for key, _name, is_pitcher in players:
        mlbam = id_cache.get(key)
        if mlbam is None:
            continue
        career = career_cache.get(key) or []
        if not career:
            no_career_count += 1
            continue
        sl = derive_statline_from_career(
            key, mlbam, career, target_season, is_pitcher=is_pitcher
        )
        if sl is None:
            missing_count += 1
            continue
        out[key] = sl
        if sl.is_prior_season:
            fallback_count += 1
    log.info(
        "derived %d stat lines from career cache (%d via prior-season fallback, "
        "%d in cache but out-of-range, %d with no career rows on file)",
        len(out), fallback_count, missing_count, no_career_count,
    )
    return out


# ---------------------------------------------------------------------------
# Bulk fetch
# ---------------------------------------------------------------------------

def fetch_statlines_for(
    players: Iterable[tuple[str, str, bool]],
    season: int,
    for_mlb: bool = False,
    max_workers: int | None = None,
    id_cache: dict[str, int] | None = None,
) -> dict[str, StatLine]:
    """
    Bulk-fetch stat lines.

    Strategy: resolve MLBAM IDs sequentially (cached, fast), then fetch
    stat lines concurrently using a ThreadPoolExecutor to overlap network I/O.

    Args:
      max_workers: optional cap on worker threads; if None, uses a safe default.
      id_cache: optional {player_key: mlbam_id} from a prior bulk_resolve_ids
                call. Skips the per-player resolve_mlbam_id pass when provided.
    """
    out: dict[str, StatLine] = {}

    # First, resolve MLBAM IDs (sequential to avoid racey cache writes).
    # If caller passed in a pre-built id_cache (from bulk_resolve_ids), use
    # it directly — saves ~3000 redundant cache lookups during the run.
    id_map: dict[str, tuple[int, bool]] = {}
    for key, name, is_pitcher in players:
        if id_cache is not None:
            mlbam = id_cache.get(key)
        else:
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


def detect_graduations_from_career(
    career_stats: dict[str, list[dict]],
    active_players: list[tuple[str, str, bool]],
    player_index: "PlayerIndex | None" = None,
    id_cache: dict[str, int | None] | None = None,
    statlines: dict[str, "StatLine"] | dict[str, dict] | None = None,
) -> dict[str, str | None]:
    """
    Identify graduated prospects by checking career MLB stats against the
    MLB rookie-eligibility thresholds.

    A player has lost rookie / prospect status (and is therefore graduated)
    when their CAREER MLB totals exceed either:

        - Position player: > 130 at-bats
        - Pitcher        : > 50 innings pitched

    (The third official criterion — > 45 days on an active MLB roster
    outside September — requires day-by-day transaction data that the
    public API doesn't expose cleanly, so we approximate by AB/IP only.)

    A player who has *debuted* in MLB but not yet crossed either threshold
    remains an active prospect. Their `mlb_debut_date` is still surfaced
    by `collect_mlb_debut_dates` so the UI can pin it on the transaction
    timeline as its own marker.

    Pre-filter: when `player_index` is supplied, we restrict the candidate
    set to prospects whose index record has a non-empty `mlbDebutDate`. A
    prospect without an MLB debut date cannot have crossed the rookie
    threshold by definition, so we skip the threshold sum for them. This
    typically narrows ~3000 active prospects down to <50 candidates.

    Args:
        career_stats : {player_key: [season_row, ...]} from `load_career_stats`.
                       Each season_row should include `level`, `is_pitcher`,
                       and either `ab` (hitters) or `ip` (pitchers).
        active_players: (player_key, player_name, is_pitcher_hint). The hint
                       fills in if a career_stats row has no `is_pitcher` flag.
        player_index : optional `PlayerIndex` used to look up an accurate
                       `mlbDebutDate` for the graduation_date AND to
                       pre-filter the candidate set. Falls back to
                       "{earliest-MLB-season}-07-01" when the index has no
                       debut date for this player.
        id_cache     : optional MLBAM ID cache so we can find the prospect's
                       record in `player_index`. Defaults to disk cache.
        statlines    : optional {player_key: StatLine | dict} of current-season
                       statlines. When provided, a prospect whose statline
                       level == "MLB" is also flagged graduated, mirroring the
                       previous per-player auto-grad pass in run_monthly.

    Returns:
        {player_key: debut_date_or_None}
    """
    if id_cache is None:
        id_cache = _load_id_cache()
    pitcher_by_key = {key: bool(pit) for key, _, pit in active_players}
    active_keys = set(pitcher_by_key)

    # Pre-filter: when we have a PlayerIndex, restrict to prospects with an
    # mlbDebutDate. The pre-filter is the bulk-equivalent of "did this player
    # ever play in MLB?" — no debut date means no possible graduation.
    debut_by_key: dict[str, str] = {}
    if player_index is not None:
        for key in active_keys:
            mid = id_cache.get(key)
            if mid is None:
                continue
            debut = player_index.get_debut_date(mid)
            if debut:
                debut_by_key[key] = debut
        candidate_keys = set(debut_by_key)
        log.info(
            "graduation pre-filter: %d/%d active prospects have an mlbDebutDate",
            len(candidate_keys), len(active_keys),
        )
    else:
        candidate_keys = active_keys

    graduates: dict[str, str | None] = {}

    def _resolve_debut(player_key: str, mlb_rows: list[dict] | None) -> str:
        """Pick the best graduation_date: index → earliest MLB season → today-ish."""
        debut = debut_by_key.get(player_key)
        if debut:
            return debut
        if player_index is not None:
            mid = id_cache.get(player_key)
            if mid is not None:
                idx_debut = player_index.get_debut_date(mid)
                if idx_debut:
                    return idx_debut
        if mlb_rows:
            earliest_season = min(r["season"] for r in mlb_rows)
            return f"{earliest_season}-07-01"
        return date.today().isoformat()

    debuted_below_threshold = 0
    for player_key in candidate_keys:
        rows = career_stats.get(player_key) or []
        if not rows:
            continue
        # Per-row is_pitcher is set by fetch_career_stats based on whether
        # we hit the hitting or pitching endpoint; fall back to the hint.
        is_pitcher = bool(rows[0].get("is_pitcher", pitcher_by_key[player_key]))
        mlb_rows = [r for r in rows if r.get("level") == "MLB"]
        if not mlb_rows:
            continue

        # Sum career MLB AB / IP and compare to the rookie thresholds.
        if is_pitcher:
            career_total = sum(_safe_float(r.get("ip")) or 0.0 for r in mlb_rows)
            crossed = career_total > ROOKIE_IP_THRESHOLD
            metric_label = f"{career_total:.1f} IP"
        else:
            career_total = sum(int(r.get("ab") or 0) for r in mlb_rows)
            crossed = career_total > ROOKIE_AB_THRESHOLD
            metric_label = f"{career_total} AB"

        if not crossed:
            debuted_below_threshold += 1
            continue

        debut = _resolve_debut(player_key, mlb_rows)
        graduates[player_key] = debut
        log.info("GRADUATED (rookie threshold passed: %s): %s  debut=%s",
                 metric_label, player_key, debut)

    # Second pass: current-season statline at MLB level. Catches the
    # recently-called-up case the career-threshold sum misses (career
    # cache might be slightly stale for this very current season). Runs
    # over all active prospects (not just candidate_keys) because a
    # prospect whose PlayerIndex record lacks a debut date but who shows
    # up with an MLB statline this season is also a candidate. Still
    # subject to the rookie threshold — a player with 1 MLB AB does NOT
    # graduate.
    if statlines:
        for player_key in active_keys:
            if player_key in graduates:
                continue
            sl = statlines.get(player_key)
            if sl is None:
                continue
            level = sl.level if hasattr(sl, "level") else sl.get("level")
            if level != "MLB":
                continue
            # Threshold check from the statline. StatLine doesn't carry
            # AB directly; use career_stats MLB sum if available, else
            # fall back to "must have at least the threshold worth of
            # games" as a conservative proxy.
            rows = career_stats.get(player_key) or []
            mlb_rows = [r for r in rows if r.get("level") == "MLB"]
            is_pitcher = bool(
                rows[0].get("is_pitcher", pitcher_by_key.get(player_key, False))
                if rows else pitcher_by_key.get(player_key, False)
            )
            if is_pitcher:
                career_total = sum(_safe_float(r.get("ip")) or 0.0 for r in mlb_rows)
                crossed = career_total > ROOKIE_IP_THRESHOLD
            else:
                career_total = sum(int(r.get("ab") or 0) for r in mlb_rows)
                crossed = career_total > ROOKIE_AB_THRESHOLD
            if not crossed:
                continue
            debut = _resolve_debut(player_key, mlb_rows or None)
            graduates[player_key] = debut
            log.info("GRADUATED (current-statline MLB + threshold): %s  debut=%s",
                     player_key, debut)

    if debuted_below_threshold:
        log.info(
            "%d prospects debuted in MLB but remain below the rookie threshold "
            "(>%d AB or >%g IP); kept as active",
            debuted_below_threshold, ROOKIE_AB_THRESHOLD, ROOKIE_IP_THRESHOLD,
        )

    return graduates


def collect_mlb_debut_dates(
    tracked_players: list[tuple[str, str]] | list[str],
    player_index: "PlayerIndex | None" = None,
    id_cache: dict[str, int | None] | None = None,
    career_stats: dict[str, list[dict]] | None = None,
) -> dict[str, str]:
    """
    Return `{player_key: mlb_debut_date}` for every tracked player who has
    appeared in an MLB game.

    Resolution priority for the debut date:
      1. `player_index.mlbDebutDate` (precise, from MLB Stats API)
      2. Earliest career_stats MLB-row season → `{season}-07-01` (approx)

    The function is intentionally agnostic about graduation status — a
    player who's debuted but hasn't crossed the rookie threshold still
    has a debut date, and the UI needs to render it as a transaction
    marker for both active prospects and graduates.
    """
    if id_cache is None:
        id_cache = _load_id_cache()
    # Accept either a list of keys or (key, name) tuples.
    keys: list[str] = []
    for item in tracked_players:
        keys.append(item if isinstance(item, str) else item[0])

    out: dict[str, str] = {}
    career_stats = career_stats or {}

    for key in keys:
        # Path 1: PlayerIndex (authoritative)
        if player_index is not None:
            mid = id_cache.get(key)
            if mid is not None:
                debut = player_index.get_debut_date(mid)
                if debut:
                    out[key] = debut
                    continue
        # Path 2: career_stats fallback — pick the earliest MLB season.
        rows = career_stats.get(key) or []
        mlb_rows = [r for r in rows if r.get("level") == "MLB"]
        if mlb_rows:
            earliest = min(r["season"] for r in mlb_rows if r.get("season"))
            out[key] = f"{earliest}-07-01"
    return out


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


# ---------------------------------------------------------------------------
# Draft data — bulk fetch /draft/{year} for acquisition info
# ---------------------------------------------------------------------------


def fetch_draft_year(year: int) -> list[dict]:
    """Fetch every pick from one draft year. Returns a flat list with our
    normalized field names; matching to tracked prospects happens downstream.

    Each pick contains:
      mlbam_id, year, round_label, pick_round, pick_overall, bonus_usd,
      team_name, school, fullName
    """
    url = f"{MLB_STATS_API}/draft/{year}"
    try:
        resp = requests.get(url, timeout=30, ttl=30 * 86400)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("draft fetch failed for %d: %s", year, e)
        return []

    picks: list[dict] = []
    rounds = (data.get("drafts") or {}).get("rounds") or []
    for rnd in rounds:
        round_label = str(rnd.get("round") or "")
        for pk in rnd.get("picks", []):
            pers = pk.get("person") or {}
            pid = pers.get("id")
            if not pid:
                continue
            bonus_raw = pk.get("signingBonus")
            try:
                bonus = int(bonus_raw) if bonus_raw not in (None, "") else None
            except (TypeError, ValueError):
                bonus = None
            # `school` arrives as an object with name/city/state — flatten
            # to "Oregon State (OR)" for display.
            school_obj = pk.get("school") or {}
            if isinstance(school_obj, dict):
                school_name = school_obj.get("name") or ""
                state = school_obj.get("state") or ""
                school_str = f"{school_name} ({state})" if (school_name and state) else school_name
            else:
                school_str = str(school_obj) if school_obj else ""
            picks.append({
                "mlbam_id":     int(pid),
                "fullName":     pers.get("fullName") or "",
                "year":         year,
                "round_label":  round_label,
                "pick_round":   pk.get("pickRound"),
                "pick_overall": pk.get("pickNumber"),
                "bonus_usd":    bonus,
                "team_name":    (pk.get("team") or {}).get("name"),
                "school":       school_str or None,
            })
    return picks


def bulk_fetch_drafts(years: Iterable[int],
                      max_workers: int = 6) -> dict[int, dict]:
    """Fetch many draft years concurrently. Returns {mlbam_id: pick_dict}.

    The first pick we see for a given mlbam_id wins; nobody is drafted
    twice in practice, but defensive in case of API hiccup."""
    years_list = list(years)
    if not years_list:
        return {}

    by_id: dict[int, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(max_workers, len(years_list))) as ex:
        for picks in ex.map(fetch_draft_year, years_list):
            for pk in picks:
                if pk["mlbam_id"] not in by_id:
                    by_id[pk["mlbam_id"]] = pk
    log.info("bulk_fetch_drafts: %d picks indexed across %d years",
             len(by_id), len(years_list))
    return by_id


# ---------------------------------------------------------------------------
# International FA signings — fetch /transactions?playerId=... per prospect
# ---------------------------------------------------------------------------

# Transaction typeCodes that indicate the original IFA signing. SFA is the
# modern code ("Signed as Free Agent"); SGN is the older one. Both arrive
# with a `toTeam` block carrying the signing org.
_IFA_SIGN_TYPE_CODES = {"SFA", "SGN"}


def fetch_ifa_signing(mlbam_id: int) -> dict | None:
    """Look up the original international-amateur signing event for one
    player. Hits /transactions?playerId={id} and returns the EARLIEST
    free-agent signing transaction, normalized to:

      {year, team_name, signing_date}

    Returns None when the API returns no qualifying transaction (e.g.
    the player has no signing on record, or was actually drafted and
    the IFA path was a false-positive in run_monthly's draft lookup).

    Signing-bonus dollars are not exposed by the public Stats API and
    stay None for IFAs — the frontend already handles that gracefully.
    """
    url = f"{MLB_STATS_API}/transactions?playerId={mlbam_id}"
    try:
        # IFA signing dates don't change once recorded, so cache aggressively.
        resp = requests.get(url, timeout=20, ttl=30 * 86400)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.debug("transactions fetch failed for %s: %s", mlbam_id, e)
        return None

    txs = data.get("transactions") or []
    signings = [
        tx for tx in txs
        if (tx.get("typeCode") or "").upper() in _IFA_SIGN_TYPE_CODES
        and tx.get("date")
    ]
    if not signings:
        return None

    # Earliest signing event = the original amateur signing. Later "SFA"
    # entries (e.g. minor-league re-signings after a release) would shadow
    # the real one if we took the most recent.
    signings.sort(key=lambda tx: tx.get("date") or "")
    first = signings[0]
    signing_date = first.get("date")
    year = None
    if signing_date and len(signing_date) >= 4:
        try:
            year = int(signing_date[:4])
        except ValueError:
            year = None
    to_team = first.get("toTeam") or {}
    team_name = to_team.get("name")

    return {
        "year":         year,
        "team_name":    team_name,
        "signing_date": signing_date,
    }


def bulk_fetch_ifa_signings(mlbam_ids: Iterable[int],
                            max_workers: int = 8) -> dict[int, dict]:
    """Concurrently fetch IFA signing info for many players. Returns
    {mlbam_id: signing_dict}, omitting players with no signing on record.

    Hits one /transactions request per player — these payloads are small
    and cached for 30 days, so monthly reruns are effectively free after
    the first pass."""
    ids = [int(mid) for mid in mlbam_ids if mid is not None]
    if not ids:
        return {}
    out: dict[int, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(max_workers, len(ids))) as ex:
        for mid, rec in zip(ids, ex.map(fetch_ifa_signing, ids)):
            if rec is not None:
                out[mid] = rec
    log.info("bulk_fetch_ifa_signings: resolved %d/%d signings",
             len(out), len(ids))
    return out


# ---------------------------------------------------------------------------
# Injured List — detect current IL stint from /transactions per player
# ---------------------------------------------------------------------------

# Regex set for parsing the free-text description of MLB Stats API "SC"
# (Status Change) transactions. The IL ecosystem has many edge cases:
#   - retroactive placement: "placed X on the 15-day IL retroactive to Mar 24"
#   - transfer between lists: "transferred X from 15-day to 60-day"
#   - rehab assignment: "sent X on a rehab assignment" — does NOT end the
#     stint; only "activated" or "reinstated" does
# Patterns are case-insensitive; we let the SC typeCode filter cut the
# transaction stream down before we run regex.
_IL_PLACE_RE = _re.compile(
    r"placed.+?on the\s+(\S+?)\s+(?:injured|disabled)\s+list"
    r"(?:\s+retroactive to\s+([A-Za-z]+\s+\d+,?\s+\d{4}))?",
    _re.IGNORECASE,
)
_IL_TRANSFER_RE = _re.compile(
    r"transferred.+?from the\s+\S+?\s+(?:injured|disabled)\s+list\s+"
    r"to the\s+(\S+?)\s+(?:injured|disabled)\s+list",
    _re.IGNORECASE,
)
_IL_ACTIVATE_RE = _re.compile(
    r"(?:activated|reinstated)\s.+?from the\s+\S+?\s+(?:injured|disabled)\s+list",
    _re.IGNORECASE,
)
# Bare-activation pattern — "Team activated Player" with no further detail.
# The MLB API uses this wording for some IL returns (instead of the more
# explicit "activated from the X-day injured list"). We only honor this as
# an IL clear when we already know the player is currently on IL; otherwise
# normal roster activations (e.g. activating an option) would falsely
# zero out the IL state.
_BARE_ACTIVATE_RE = _re.compile(
    r"\bactivated\s+(?:[A-Z]{1,4}\s+)?[A-Z][A-Za-z]",
    _re.IGNORECASE,
)
# Rehab assignments do NOT end the IL stint — the player is still on IL,
# just playing in the minors to rebuild. Catch the verbiage explicitly so
# we never let it through the bare-activation fallback.
_REHAB_RE = _re.compile(r"sent.+?on a rehab assignment", _re.IGNORECASE)


def _parse_il_retro_date(retro: str | None) -> str | None:
    """Convert 'March 24, 2025' (the API's retroactive-to format) to an
    ISO date string. Returns None if the date can't be parsed."""
    if not retro:
        return None
    from datetime import datetime as _dt
    cleaned = retro.strip().rstrip(",")
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y"):
        try:
            return _dt.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def fetch_il_status(mlbam_id: int) -> dict | None:
    """Determine the player's current IL stint by walking their full
    transactions history chronologically.

    Returns a dict when the player is currently on IL:
      {
        is_on_il:    True
        since:       ISO date of the placement (retroactive when given)
        type:        '10-day' | '15-day' | '60-day' | '7-day' | ...
        description: full text of the placement transaction
      }

    Returns None when the player is not on IL.

    Cache TTL is 7 days — IL stints can flip more often than IFA records,
    but daily refresh on a monthly pipeline is overkill.
    """
    url = f"{MLB_STATS_API}/transactions?playerId={mlbam_id}"
    try:
        resp = requests.get(url, timeout=20, ttl=7 * 86400)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.debug("IL transactions fetch failed for %s: %s", mlbam_id, e)
        return None

    txs = sorted(
        data.get("transactions") or [],
        key=lambda t: t.get("date") or "",
    )

    is_on_il = False
    il_since: str | None = None
    il_type:  str | None = None
    il_desc:  str | None = None

    for tx in txs:
        if (tx.get("typeCode") or "").upper() != "SC":
            continue
        desc = (tx.get("description") or "").strip()
        if not desc:
            continue
        # Rehab assignment — player stays on IL while rehabbing. Skip
        # before the bare-activation match so "sent on a rehab assignment"
        # isn't mistaken for an activation by sloppy wording.
        if _REHAB_RE.search(desc):
            continue
        # Explicit activation: "activated from the X-day injured list".
        # Highest-confidence end-of-stint signal.
        if _IL_ACTIVATE_RE.search(desc):
            is_on_il = False
            il_since = il_type = il_desc = None
            continue
        m_t = _IL_TRANSFER_RE.search(desc)
        if m_t:
            if is_on_il:
                il_type = m_t.group(1)
                il_desc = desc
            continue
        m_p = _IL_PLACE_RE.search(desc)
        if m_p:
            is_on_il = True
            il_type = m_p.group(1)
            retro_iso = _parse_il_retro_date(m_p.group(2))
            il_since = retro_iso or tx.get("date")
            il_desc = desc
            continue
        # Fallback: bare "<team> activated <player>" when we know they
        # were on IL. MLB sometimes drops the "from the X-day IL" clause
        # — Painter's 2024-10-11 activation is the canonical example.
        if is_on_il and _BARE_ACTIVATE_RE.search(desc):
            is_on_il = False
            il_since = il_type = il_desc = None

    if not is_on_il:
        return None
    return {
        "is_on_il":    True,
        "since":       il_since,
        "type":        il_type,
        "description": il_desc,
    }


def bulk_fetch_il_status(mlbam_ids: Iterable[int],
                         max_workers: int = 8) -> dict[int, dict]:
    """Concurrent IL-status lookup for many players. Returns
    {mlbam_id: il_dict} only for players currently on IL.

    Uses the same /transactions endpoint that the IFA + trade pipelines
    already hit, so cached payloads (30 days for IFA) are reused — only
    players whose cache TTL has elapsed cost a network call here."""
    ids = [int(mid) for mid in mlbam_ids if mid is not None]
    if not ids:
        return {}
    out: dict[int, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(max_workers, len(ids))) as ex:
        for mid, rec in zip(ids, ex.map(fetch_il_status, ids)):
            if rec is not None:
                out[mid] = rec
    log.info("bulk_fetch_il_status: %d/%d players currently on IL",
             len(out), len(ids))
    return out


# ---------------------------------------------------------------------------
# Affiliation map — fetch /teams?sportId=... to get team→parent_org links
# ---------------------------------------------------------------------------

# sport_id → level label we expose to the front-end. Drives the per-level
# roster grouping on the farm detail page.
_LEVEL_BY_SPORT_ID = {
    1:  "MLB",
    11: "AAA",
    12: "AA",
    13: "A+",
    14: "A",
    16: "Rk",
    17: "Rk",   # complex-level / DSL sometimes report under 17
    21: "DSL",
}


def fetch_team_affiliations(season: int) -> dict[int, dict]:
    """Return {team_id: {name, level, parent_org_id, parent_org_abbr}} for
    every MLB + MiLB team in the given season. One call per sport level
    (~6 total) covers the affiliate hierarchy in full.

    parent_org_abbr is the 3-letter MLB code (e.g. NYM, TOR), pulled from
    the MLB-team record's `abbreviation` field. Some MiLB records carry a
    different abbreviation than their parent — we canonicalize via the
    parent's MLB record so downstream code can compare to player.org."""
    sport_ids = (1, 11, 12, 13, 14, 16)
    team_info: dict[int, dict] = {}
    mlb_abbr_by_id: dict[int, str] = {}

    def _fetch(sport_id: int) -> list[dict]:
        url = f"{MLB_STATS_API}/teams?sportId={sport_id}&season={season}"
        try:
            resp = requests.get(url, timeout=20, ttl=7 * 86400)
            resp.raise_for_status()
            return resp.json().get("teams", []) or []
        except Exception as e:
            log.warning("teams fetch failed (sport=%d): %s", sport_id, e)
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(_fetch, sport_ids))

    # First pass: collect MLB-level abbreviations so we can resolve parents
    for teams, sid in zip(results, sport_ids):
        if sid != 1:
            continue
        for t in teams:
            mlb_abbr_by_id[int(t["id"])] = t.get("abbreviation") or ""

    # Second pass: every team (MLB + affiliates) → metadata
    for teams, sid in zip(results, sport_ids):
        level = _LEVEL_BY_SPORT_ID.get(sid)
        for t in teams:
            tid = int(t["id"])
            parent_id = t.get("parentOrgId")
            team_info[tid] = {
                "id":              tid,
                "name":            t.get("name") or "",
                "level":           level,
                "parent_org_id":   parent_id if parent_id else tid,
                "parent_org_abbr": mlb_abbr_by_id.get(parent_id or tid, ""),
            }

    log.info("team affiliations: %d teams across %d sport levels",
             len(team_info), len(sport_ids))
    return team_info
