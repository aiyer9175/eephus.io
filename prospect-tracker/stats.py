# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

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
        # Cache path derived from URL hash. md5() can't actually fail on
        # a bytes input; the fallback is defensive against future caller
        # bugs that feed in a non-str url. Log so the surface isn't silent.
        try:
            key = hashlib.md5(url.encode("utf-8")).hexdigest()
        except Exception as e:
            log.debug("md5 hash failed for cache key %r: %s — falling back to builtin hash", url, e)
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
                except Exception as e:
                    # Corrupt cache file (truncated, bad encoding) → log so
                    # a recurring issue surfaces in run notes, and fall
                    # through to a fresh network fetch.
                    log.debug("cache read failed for %s: %s — refetching", url, e)

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

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
ID_CACHE_FILE = CACHE_DIR / "mlbam_ids.json"
PLAYER_INDEX_CACHE_FILE = CACHE_DIR / "player_index.json"
# v24 — Shortened from 24h → 1h so freshly-posted mlbDebutDates are
# picked up on any same-day re-run (debut detection in run_monthly.py
# step 3c reads from this index). Cold/cross-day runs still rebuild.
PLAYER_INDEX_TTL_SECONDS = 3600

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
    "luis_de_avila":     "Luinder Avila",      # 679883 born 2001-08-21
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
    return a == b


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


def _strip_name_suffix(name: str) -> str:
    return _re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv|v)$", "", name,
                   flags=_re.IGNORECASE).strip()


def _cached_id_matches_request(idx: PlayerIndex, cached_id: int,
                               name: str, player_key: str | None) -> bool:
    """Validate a cached MLBAM id against the current player index.

    Cache hits bypass `best_match()`, so they need a stricter guard than
    the fuzzy resolver. If the cached id is present in the index, require
    an exact normalized name match or an explicit alias match. If the id is
    not in the warm index, keep the cache entry; older inactive players may
    be absent from current-season roster indexes.
    """
    try:
        rec = idx.by_id.get(int(cached_id))
    except (TypeError, ValueError):
        return False
    if not rec:
        return True
    rec_name = _norm_key(_strip_name_suffix(rec.get("fullName") or ""))
    allowed = {_norm_key(_strip_name_suffix(name))}
    if player_key and player_key in _NAME_ALIASES:
        allowed.add(_norm_key(_strip_name_suffix(_NAME_ALIASES[player_key])))
    return rec_name in allowed


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
#
# Rookie-level handling: post-2021 realignment, US-based rookie ball is
# exclusively the Complex Leagues (FCL + ACL), and DSL is a distinct
# foreign rookie league with its own age curve. We no longer expose a
# generic "Rk" bucket — the bulk-fetch fallback used to dump everything
# from sport-id 16 there, hiding CPX vs DSL splits. Now anything that
# would have landed in Rk classifies as CPX by default and gets
# overridden to DSL when the league name says so. Legacy aliases stay
# in the map so historical career rows still resolve to the new bucket.
LEVEL_LABELS = {
    # MLB
    "MLB": "MLB", "Major League Baseball": "MLB", "The Show": "MLB",
    "American League": "MLB", "National League": "MLB",
    # Sport codes
    "Triple-A": "AAA", "Double-A": "AA", "High-A": "A+", "Single-A": "A",
    "AAA": "AAA", "AA": "AA", "A+": "A+", "A": "A",
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
    # Complex / rookie. "Rookie" / "Rk" / "ROK" all roll into CPX so the
    # default sport-name match doesn't bypass the CPX label. League-name
    # matches override later in the loop because their substring is longer.
    "Rookie": "CPX", "Rk": "CPX", "ROK": "CPX",
    "FCL": "CPX", "ACL": "CPX",
    "Florida Complex League": "CPX", "Arizona Complex League": "CPX",
    "Complex": "CPX", "Complex League": "CPX",
    # DSL — keep as its own bucket; the age curve at DSL is meaningfully
    # younger than CPX and the run environment is different.
    "Dominican Summer League": "DSL", "DSL": "DSL",
}
# MLB is highest; order matters — _highest_level picks lowest index = highest level
LEVEL_ORDER = ["MLB", "AAA", "AA", "A+", "A", "CPX", "DSL"]


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
    # Derived hitter power metric: SLG - AVG. Carried on the StatLine so
    # the prospect-page flag computation can read it off without re-deriving
    # from the slash line string each time.
    iso: float | None = None
    # Pitching peripherals used to surface red/green scouting flags. WHIP
    # comes straight from the API; HR/9 is either the API's `homeRunsPer9`
    # or a derivation of HR allowed × 9 / IP — see fetch_career_stats.
    whip: float | None = None
    hr_per_9: float | None = None


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

# v23 — mlbam_id cache TTL. Previously the cache was permanent: a
# wrong same-name resolution (Fernando Cruz → MLB-veteran pitcher)
# stayed cached forever. Now stale entries get re-resolved every 30
# days so the PlayerIndex scoring gets another chance to pick the
# right candidate as it sees new prospect data. Cache mtime is the
# proxy for entry age — the whole file is re-written on every save,
# but that's fine: a stale entry forces a fresh re-resolve at most
# every 30 days, which is cheap compared to the resolution cost.
ID_CACHE_TTL_DAYS = 30

def _load_id_cache() -> dict[str, int | None]:
    if not ID_CACHE_FILE.exists():
        return {}
    age_days = (time.time() - ID_CACHE_FILE.stat().st_mtime) / 86400.0
    if age_days > ID_CACHE_TTL_DAYS:
        log.info("mlbam_id cache stale (%.0f days > %d-day TTL) — clearing for re-resolution",
                 age_days, ID_CACHE_TTL_DAYS)
        try:
            ID_CACHE_FILE.unlink()
        except OSError:
            pass
        return {}
    return json.loads(ID_CACHE_FILE.read_text())


def _save_id_cache(cache: dict[str, int | None]):
    ID_CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# NEGATIVE-RESULT TTL (2026-08-03)
# ---------------------------------------------------------------------------
# A resolved id is permanent: MLBAM ids do not change, so caching a HIT
# forever is correct. A MISS is not the same kind of fact. "Not in StatsAPI"
# is a statement about today, and for a just-drafted amateur it is guaranteed
# true on the day of the draft and false a few weeks later once he signs and
# is assigned to an affiliate.
#
# Caching misses with the same permanence as hits is what left the entire 2026
# draft class without stats: every one of the 199 active 2026 draftees was
# resolved once at ingest (before any of them appeared on a roster), cached
# null, and never retried, so they carried no mlbam_id and the stat fetch had
# nothing to key on. Measured on the served board: of 4,550 active players,
# every one of the 4,296 WITH an id had stats and every one of the 254 without
# an id had none. Roch Cholowsky and Vahn Lackey were two of them, and both
# resolve fine through PlayerIndex today (800604 / 822518).
#
# Misses are therefore stamped in a sidecar and expire quickly. Entries with
# no stamp (everything cached before this change) read as expired, so the
# existing poisoned nulls heal themselves on the next resolution pass.
NEG_ID_CACHE_TTL_DAYS = 3
MISS_STAMP_FILE = CACHE_DIR / "mlbam_id_misses.json"


def _load_miss_stamps() -> dict[str, float]:
    """{player_key: epoch_seconds} for cached negative resolutions. Kept in a
    sidecar so the id cache keeps its plain {key: int|None} on-disk contract
    for every other reader."""
    try:
        return json.loads(MISS_STAMP_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _miss_is_fresh(player_key: str) -> bool:
    """True when this key was recorded as unresolvable recently enough that
    re-querying would just repeat the same miss. An unstamped miss is treated
    as expired so pre-existing nulls get one retry."""
    ts = _load_miss_stamps().get(player_key)
    if not isinstance(ts, (int, float)):
        return False
    return (time.time() - ts) < NEG_ID_CACHE_TTL_DAYS * 86400.0


def _record_miss(player_key: str) -> None:
    stamps = _load_miss_stamps()
    stamps[player_key] = time.time()
    try:
        MISS_STAMP_FILE.parent.mkdir(parents=True, exist_ok=True)
        MISS_STAMP_FILE.write_text(json.dumps(stamps, indent=2, sort_keys=True))
    except OSError:
        pass    # advisory only; a failed stamp costs a retry, never correctness


def _clear_miss(player_key: str) -> None:
    stamps = _load_miss_stamps()
    if stamps.pop(player_key, None) is not None:
        try:
            MISS_STAMP_FILE.write_text(json.dumps(stamps, indent=2, sort_keys=True))
        except OSError:
            pass


def _update_miss_stamps(add=(), clear=()) -> None:
    """Batch form of _record_miss/_clear_miss. bulk_resolve_ids walks thousands
    of keys per run, so stamping one at a time would be one read plus one write
    per player."""
    add, clear = set(add), set(clear)
    if not add and not clear:
        return
    stamps = _load_miss_stamps()
    now = time.time()
    for k in add:
        stamps[k] = now
    for k in clear:
        stamps.pop(k, None)
    try:
        MISS_STAMP_FILE.parent.mkdir(parents=True, exist_ok=True)
        MISS_STAMP_FILE.write_text(json.dumps(stamps, indent=2, sort_keys=True))
    except OSError:
        pass


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


def _split_key_for(player_key: str, mlbam_id) -> str | None:
    """Lazy wrapper around scrapers.split_key_for_mlbam (avoids a module-load
    cycle). Returns the discriminated key when (player_key, mlbam_id) is a
    known name-slug collision, else None."""
    try:
        from scrapers import split_key_for_mlbam
        return split_key_for_mlbam(player_key, mlbam_id)
    except Exception:
        return None


def _durable_mlbam_bindings() -> tuple[dict[str, int], dict[int, str]]:
    """({player_key: mlbam_id}, {mlbam_id: player_key}) from the persisted
    player_photos mapping — the durable key<->id index the DB already holds.
    Read-only; consumed by the slug-collision guard below."""
    try:
        import storage
        raw = storage.load_mlbam_player_keys()  # {mlbam_id(str): player_key}
    except Exception as e:
        log.debug("collision guard: durable mlbam mapping unavailable: %s", e)
        return {}, {}
    by_key: dict[str, int] = {}
    by_id: dict[int, str] = {}
    for mid_s, key in raw.items():
        try:
            mid = int(mid_s)
        except (TypeError, ValueError):
            continue
        by_id[mid] = key
        by_key[key] = mid
    return by_key, by_id


def _apply_collision_guard(
    cache: dict[str, int | None],
    player_key: str,
    mlbam_id: int,
    durable: tuple[dict[str, int], dict[int, str]] | None = None,
) -> int | None:
    """Write the player_key -> mlbam_id binding into `cache`, forking the
    key when the pair is a known or detected name-slug collision.

    Two different humans can normalize to the same slug (the Jose Valdez
    case: the retired Tigers RHP "Jose A. Valdez" and the 2026 DSL Giants
    OF signee, mlbam 838649, both -> "jose_a_valdez"). Binding a resolved
    id onto a key that durably belongs to a DIFFERENT person merges the two
    identities in every downstream keyed write (statlines, career_stats,
    player_transactions, roster_status, player_photos).

    Returns the id the REQUESTED key should resolve to (None when the
    resolved id belongs to a different identity). Mutates `cache` in place;
    the caller persists it.
    """
    # 1) Allowlisted split (scrapers._SPLIT_KEYS): the resolved id is a
    #    known slug-collision newcomer — its rows live under the split key.
    split = _split_key_for(player_key, mlbam_id)
    if split and split != player_key:
        log.warning(
            "mlbam key collision (allowlisted): %s resolved to id %s, which "
            "belongs to %r — binding under the split key; %s stays unbound",
            player_key, mlbam_id, split, player_key,
        )
        cache[split] = mlbam_id
        cache[player_key] = None   # not this identity's id; stop re-resolving
        return None

    if durable is None:
        durable = _durable_mlbam_bindings()
    by_key, by_id = durable

    # 2) Key already durably bound to a DIFFERENT id: the resolved id is a
    #    newcomer with a colliding slug. Fork the newcomer to a
    #    discriminated key; the requested key keeps its durable id.
    durable_id = by_key.get(player_key)
    if durable_id is not None and durable_id != mlbam_id:
        forked = f"{player_key}_{mlbam_id}"
        log.warning(
            "mlbam key collision: %s is durably bound to id %s but resolved "
            "to %s — forking the newcomer to %r",
            player_key, durable_id, mlbam_id, forked,
        )
        cache[forked] = mlbam_id
        cache[player_key] = durable_id
        return durable_id

    # 3) Resolved id durably bound to a DIFFERENT key: the id belongs to
    #    that identity — refuse the merge; this key resolves to nothing.
    owner = by_id.get(mlbam_id)
    if owner is not None and owner != player_key:
        log.warning(
            "mlbam key collision: id %s is durably bound to %r — refusing to "
            "bind it to %r", mlbam_id, owner, player_key,
        )
        cache[player_key] = None
        return None

    cache[player_key] = mlbam_id
    return mlbam_id


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
        cached = cache[player_key]
        if cached is not None and _split_key_for(player_key, cached):
            # Stale pre-split binding: the cached id belongs to a known
            # slug-collision newcomer (scrapers._SPLIT_KEYS), not to this
            # key. Heal the binding through the guard instead of serving it.
            healed = _apply_collision_guard(cache, player_key, cached)
            _save_id_cache(cache)
            return healed
        # A cached MISS only holds for NEG_ID_CACHE_TTL_DAYS. Past that we fall
        # through and re-resolve, because "StatsAPI does not have him" is a
        # fact about the day it was recorded, not about the player. Hits are
        # still returned straight from cache and never expire here.
        if cached is None:
            if _miss_is_fresh(player_key):
                return None
            log.info("mlbam_id miss for %s has expired - re-resolving", player_key)
        else:
            return cached

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
            "could not resolve MLBAM ID for %s - caching null for %d days "
            "(a just-drafted player resolves once he is assigned)",
            player_name, NEG_ID_CACHE_TTL_DAYS,
        )
        cache[player_key] = None
        _save_id_cache(cache)
        _record_miss(player_key)      # expires; see NEG_ID_CACHE_TTL_DAYS
        return None

    # Slug-collision guard: never bind a resolved id onto a key that
    # durably belongs to a different identity (see _apply_collision_guard).
    mlbam_id = _apply_collision_guard(cache, player_key, mlbam_id)
    _save_id_cache(cache)
    _clear_miss(player_key)           # resolved: drop any stale miss stamp
    return mlbam_id


# ---------------------------------------------------------------------------
# F2 vintage guard (audit 2026-07-24): dormant-identity id mis-resolution
# ---------------------------------------------------------------------------
# A dormant prospect record (a 2013-listed bust) re-resolved against the
# CURRENT PlayerIndex can bind a same-name kid whose first pro season
# postdates the record's entire list era (luke_jackson, listed 2012-2017,
# was bound to a Luke Jackson born 2004 whose first pro season is 2026).
# The wrong id then leaks a wrong ladder + birth date into the eFV
# training feeds. The guard rejects any candidate id whose first cached
# pro season postdates the record's last list year by more than one season.
_VINTAGE_PROVABLE_FLOOR = 2015   # milb_stats caches start 2014: earlier
#   seasons are not provably missing, so pre-floor gaps never reject.
_FIRST_CACHE_SEASON_MEMO: dict[int, int] | None = None


def _first_cache_seasons() -> dict[int, int]:
    """{mlbam_id: first season with any cached stat line} across the whole
    affiliated ladder incl. MLB (milb_history caches, fetch=False so this
    stays offline-safe). Built lazily, once per process."""
    global _FIRST_CACHE_SEASON_MEMO
    if _FIRST_CACHE_SEASON_MEMO is None:
        import milb_history as _mh
        first: dict[int, int] = {}
        for season in range(2014, date.today().year + 1):   # ascending: first wins
            for sport in _mh.ALL_SPORTS:
                for group in ("hitting", "pitching"):
                    for r in _mh.season_splits(sport, season, group, fetch=False):
                        m = r.get("mlbam")
                        if m and int(m) not in first:
                            first[int(m)] = season
        _FIRST_CACHE_SEASON_MEMO = first
    return _FIRST_CACHE_SEASON_MEMO


def vintage_guard_rejects(mlbam_id, last_list_year, first_season=None) -> bool:
    """True when `mlbam_id` cannot plausibly belong to a record last listed
    in `last_list_year`: the id's first pro season (first cached stat line,
    MLB included) postdates that year by more than one season. EXEMPT: gaps
    explained by the cancelled 2020 MiLB season - a gap spanning 2020
    tolerates one extra missing season (the TJ-plus-COVID class: 2018/19
    listees first cached in 2021 pass). No cached seasons = no evidence =
    never reject."""
    if mlbam_id is None or last_list_year is None:
        return False
    lly = int(last_list_year)
    if first_season is None:
        first_season = _first_cache_seasons().get(int(mlbam_id))
    if first_season is None or int(first_season) <= lly + 1:
        return False
    fs = int(first_season)
    gap = [y for y in range(max(lly + 1, _VINTAGE_PROVABLE_FLOOR), fs)
           if y != 2020]
    spans_2020 = lly < 2020 < fs
    return len(gap) > (1 if spans_2020 else 0)


def bulk_resolve_ids(
    players: Iterable[tuple[str, str, str | None]],
    season: int | None = None,
    force_rebuild_index: bool = False,
    fallback_workers: int = 8,
    last_list_year_by_key: dict[str, int] | None = None,
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
        last_list_year_by_key: optional {player_key: last list year} for
                 DORMANT identities (inactive busts / long-graduated players).
                 Enables the vintage guard: a candidate id whose first cached
                 pro season postdates the record's list era is rejected (and
                 a cached one evicted) instead of bound - see
                 vintage_guard_rejects. Keys absent from the map resolve
                 exactly as before.

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
    # Durable key<->id index for the slug-collision guard, loaded once for
    # the whole batch (see _apply_collision_guard).
    durable = _durable_mlbam_bindings()

    # F2 vintage guard closure: only fires for keys the caller marked as
    # dormant identities (last_list_year_by_key); everyone else is exempt.
    _lly_map = last_list_year_by_key or {}
    vintage_rejected = 0

    def _vintage_rejects(k: str, cand_id: int) -> bool:
        lly = _lly_map.get(k)
        return lly is not None and vintage_guard_rejects(cand_id, lly)

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
    cache_dirty = False
    expired_misses = 0
    miss_add: set[str] = set()
    for key, name, position in triples:
        if key in cache:
            cid = cache[key]
            if cid is not None:
                if _split_key_for(key, cid):
                    # Stale pre-split binding (see resolve_mlbam_id): the
                    # cached id belongs to a slug-collision newcomer.
                    rid = _apply_collision_guard(cache, key, cid, durable)
                    cache_dirty = True
                    if rid is not None:
                        ids_out[key] = rid
                    continue
                if not _cached_id_matches_request(idx, cid, name, key):
                    log.warning(
                        "evicting stale MLBAM cache hit for %s (%s -> %s)",
                        key, name, cid,
                    )
                    cache.pop(key, None)
                    cache_dirty = True
                elif _vintage_rejects(key, cid):
                    log.warning(
                        "vintage guard: evicting implausible MLBAM cache hit "
                        "for %s (%s -> %s; first cached pro season postdates "
                        "the record's list era)", key, name, cid,
                    )
                    cache.pop(key, None)
                    cache_dirty = True
                    vintage_rejected += 1
                else:
                    ids_out[key] = cid
                    # Refresh birth date from the index when available — covers
                    # prospects whose DB birth_date is stale from a prior bad ID.
                    idx_bd = bd_by_id.get(cid)
                    if idx_bd:
                        bds_out[key] = idx_bd
                    continue
            else:
                # A cached MISS. This used to `continue` unconditionally, which
                # is what actually starved the 2026 draft class: run_monthly
                # resolves ids ONLY through this function (the per-player
                # resolve_mlbam_id loop was removed for performance), so a null
                # written at draft ingest - before anyone had signed or been
                # assigned - was never revisited by the pipeline. Honour the
                # same negative TTL resolve_mlbam_id uses and fall through to
                # the index / people-search below once it expires.
                if _miss_is_fresh(key):
                    continue
                expired_misses += 1
        if key in ids_out:
            continue
        rec = idx.best_match(name, position=position, player_key=key)
        if rec is None:
            fallback_triples.append((key, name, position))
            continue
        if _vintage_rejects(key, rec["id"]):
            log.warning(
                "vintage guard: refusing index match for %s (%s -> %s; first "
                "cached pro season postdates the record's list era)",
                key, name, rec["id"],
            )
            vintage_rejected += 1
            continue    # leave unresolved - never bind a younger same-name id
        rid = _apply_collision_guard(cache, key, rec["id"], durable)
        new_cache_entries += 1
        if rid is not None:
            ids_out[key] = rid
            # Only take the index birth date when the requested key actually
            # resolved to the index record (a collision fork returns the
            # durable id of a DIFFERENT person than `rec`).
            if rec.get("birthDate") and rid == rec["id"]:
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
                if api_id is not None and _vintage_rejects(key, api_id):
                    log.warning(
                        "vintage guard: refusing people-search match for %s "
                        "(-> %s; first cached pro season postdates the "
                        "record's list era)", key, api_id,
                    )
                    vintage_rejected += 1
                    cache[key] = None  # remember "unresolvable" (vintage-rejected)
                    miss_add.add(key)
                    new_cache_entries += 1
                    continue
                if api_id is not None:
                    rid = _apply_collision_guard(cache, key, api_id, durable)
                    new_cache_entries += 1
                    if rid is not None:
                        ids_out[key] = rid
                        if bd and rid == api_id:
                            bds_out[key] = bd
                else:
                    cache[key] = None  # remember "unresolvable"
                    miss_add.add(key)

    # Stamp every null this run wrote, and drop the stamp for anything that
    # resolved. Without the stamps the expiry check above would re-query every
    # cached miss on every run instead of once per NEG_ID_CACHE_TTL_DAYS.
    _update_miss_stamps(add=miss_add, clear=set(ids_out))

    if new_cache_entries or cache_dirty:
        _save_id_cache(cache)

    log.info(
        "bulk_resolve_ids: %d resolved, %d new, %d via people-search fallback",
        len(ids_out), new_cache_entries, len(fallback_triples),
    )
    if expired_misses:
        log.info("bulk_resolve_ids: retried %d expired negative cache entries "
                 "(a just-drafted player resolves once he is assigned)",
                 expired_misses)
    if vintage_rejected:
        log.info("bulk_resolve_ids: vintage guard rejected %d dormant-identity "
                 "candidate ids", vintage_rejected)
    return ids_out, bds_out, idx


# ---------------------------------------------------------------------------
# Stat-line fetch via MLB Stats API
# ---------------------------------------------------------------------------

def _highest_level(splits: list[dict]) -> dict | None:
    """Pick the highest level from a list of season-stats splits.

    Now includes MLB as the highest possible level. The label lookup
    uses longest-match to avoid 'A' incorrectly matching 'Triple-A'.
    League-name (e.g. "Dominican Summer League") wins over sport-name
    (e.g. "Rookie") so the more specific signal classifies.
    """
    by_level = {}
    for split in splits:
        league = split.get("league", {})
        sport_name = (league.get("sport", {}) or {}).get("name") or ""
        league_name = league.get("name") or ""
        # Try the more specific name first.
        label = None
        for candidate in (league_name, sport_name):
            if not candidate:
                continue
            best_len = 0
            cand_lower = candidate.lower()
            for key, lbl in LEVEL_LABELS.items():
                if key.lower() in cand_lower and len(key) > best_len:
                    label = lbl
                    best_len = len(key)
            if label is not None and label in LEVEL_ORDER:
                break
        if label is None or label not in LEVEL_ORDER:
            continue
        if label not in by_level or LEVEL_ORDER.index(label) < LEVEL_ORDER.index(by_level[label]["_level"]):
            split["_level"] = label
            by_level[label] = split
    if not by_level:
        return None
    return min(by_level.values(), key=lambda s: LEVEL_ORDER.index(s["_level"]))


def bulk_fetch_mlb_debut_dates(
    mlbam_ids: "Iterable[int]",
    max_workers: int = 8,
) -> dict[int, str]:
    """Fetch `mlbDebutDate` for each MLBAM id via /people/{id} in parallel.

    Use this to backfill graduates whose PlayerIndex record has no debut
    date — typically players who left the current MiLB+MLB roster pool
    a few seasons ago, so the sport-id sweep that builds PlayerIndex
    doesn't include them anymore.

    Returns `{mlbam_id: 'YYYY-MM-DD'}` for IDs the API returned a debut
    for; players with no MLB debut on file are omitted from the dict.
    """
    ids = [int(m) for m in mlbam_ids if m]
    out: dict[int, str] = {}
    if not ids:
        return out

    def _one(mid: int) -> tuple[int, str | None]:
        url = f"{MLB_STATS_API}/people/{mid}"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.debug("mlb debut fetch failed for %s: %s", mid, e)
            return mid, None
        people = data.get("people") or []
        if not people:
            return mid, None
        return mid, people[0].get("mlbDebutDate")

    worker_count = max(1, min(max_workers, len(ids)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as ex:
        for mid, debut in ex.map(_one, ids):
            if debut:
                out[mid] = debut
    log.info("bulk_fetch_mlb_debut_dates: resolved %d/%d via /people/{id}",
             len(out), len(ids))
    return out


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
        ip_val = (float(stat.get("inningsPitched"))
                  if stat.get("inningsPitched") else None)
        hr_allowed = int(stat.get("homeRuns", 0) or 0)
        hr_per_9 = _safe_float(stat.get("homeRunsPer9"))
        if hr_per_9 is None and ip_val and ip_val > 0:
            hr_per_9 = round(hr_allowed * 9.0 / ip_val, 2)
        # Pitcher K% / BB% — per batter faced. Populated alongside the
        # K/9 / BB/9 holdovers so the frontend can show whichever rate
        # convention is preferred. K%/BB% are the more workload-stable
        # numbers (a reliever K/9 of 14 vs. a starter K/9 of 11 looks
        # dominant but normalizes in K%).
        tbf = int(stat.get("battersFaced", 0) or 0)
        so_p = int(stat.get("strikeOuts", 0) or 0)
        bb_p = int(stat.get("baseOnBalls", 0) or 0)
        return StatLine(
            player_key=player_key, mlbam_id=mlbam_id,
            level=best["_level"], games=int(stat.get("gamesPlayed", 0) or 0),
            avg=None, obp=None, slg=None, ops=None, hr=None, sb=None,
            bb_pct=round(100 * bb_p / tbf, 1) if tbf else None,
            k_pct=round(100 * so_p / tbf, 1) if tbf else None,
            era=str(stat.get("era") or "—"),
            fip=None,                       # MLB Stats API doesn't expose FIP
            ip=ip_val,
            k_per_9=_safe_float(stat.get("strikeoutsPer9Inn")),
            bb_per_9=_safe_float(stat.get("walksPer9Inn")),
            whip=_safe_float(stat.get("whip")),
            hr_per_9=hr_per_9,
            is_pitcher=True,
            fetched_at=date_today_iso(),
            season=found_season,
            is_prior_season=is_prior,
        )
    pa = stat.get("plateAppearances", 0) or 0
    bb = stat.get("baseOnBalls", 0) or 0
    so = stat.get("strikeOuts", 0) or 0
    avg_str = str(stat.get("avg") or "")
    slg_str = str(stat.get("slg") or "")
    iso_val = None
    try:
        if avg_str and slg_str and avg_str != "—" and slg_str != "—":
            iso_val = round(float(slg_str) - float(avg_str), 3)
    except (TypeError, ValueError):
        iso_val = None
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
        iso=iso_val,
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

# Sport id -> level for a yearByYear split. The sport id carries the
# classification the league had IN THAT SEASON, which a league name cannot:
# before the 2021 realignment the Midwest and South Atlantic leagues were
# Class A (sport 14) and the Florida State, Carolina and California leagues
# were High-A (sport 13), the reverse of today. Reading the name gave Leandro
# Cedeno's 2019 Midwest League season (sport 14, 396 PA) as A+, and the name
# table's one-letter key 'A' matched the 'a' in 'Gulf Coast League'. Sport 15
# (short-season A, retired after 2020) folds to A and sport 16 splits DSL from
# CPX by league, the same convention milb_history uses for the league cache.
_YBY_SPORT_LEVEL = {1: "MLB", 11: "AAA", 12: "AA", 13: "A+", 14: "A", 15: "A",
                    16: "CPX"}


def _is_dsl_league(league_name: str | None) -> bool:
    """True for the foreign rookie leagues (Dominican and Venezuelan Summer
    Leagues). The season endpoint names the Dominican league 'DSL', the
    yearByYear endpoint 'Dominican Summer League'; both must read as DSL."""
    name = (league_name or "").strip()
    low = name.lower()
    return name.upper() in ("DSL", "VSL") or "dominican" in low or "venezuelan" in low


def _level_from_sport(sport_id, league_name: str | None) -> str | None:
    """Level for a split whose sport id is known, else None (the caller falls
    back to the league-name table)."""
    try:
        label = _YBY_SPORT_LEVEL.get(int(sport_id))
    except (TypeError, ValueError):
        return None
    if label == "CPX" and _is_dsl_league(league_name):
        return "DSL"
    return label


def _level_label_from(league_name: str, sport_name: str) -> str | None:
    """Map a split's league/sport name to a short level label (MLB/AAA/…/DSL).
    League name takes precedence over the generic sport name so 'Florida
    Complex League' → CPX rather than the Rookie default."""
    for candidate in (league_name, sport_name):
        if not candidate:
            continue
        best_len, label = 0, None
        cand_lower = candidate.lower()
        for key, lbl in LEVEL_LABELS.items():
            if key.lower() in cand_lower and len(key) > best_len:
                label, best_len = lbl, len(key)
        if label is not None and label in LEVEL_ORDER:
            return label
    return None


def _row_from_split(s: dict, is_pitcher: bool) -> dict:
    """Build one career-table row from a single yearByYear split (one team, one
    level, one season). Carries `org` = the canonical parent club so a mid-season
    stint at a AA affiliate resolves to its big-league org."""
    stat = s.get("stat", {})
    row = {
        "season": int(s.get("season") or 0),
        "level": s.get("_level"),
        "level_label": s.get("_level_label"),
        "org": s.get("_org"),
        "games": int(stat.get("gamesPlayed", 0) or 0),
    }
    if is_pitcher:
        ip_val = (float(stat.get("inningsPitched"))
                  if stat.get("inningsPitched") else None)
        hr_allowed = int(stat.get("homeRuns", 0) or 0)
        hr_per_9 = _safe_float(stat.get("homeRunsPer9"))
        if hr_per_9 is None and ip_val and ip_val > 0:
            hr_per_9 = round(hr_allowed * 9.0 / ip_val, 2)
        tbf = int(stat.get("battersFaced", 0) or 0)
        so_p = int(stat.get("strikeOuts", 0) or 0)
        bb_p = int(stat.get("baseOnBalls", 0) or 0)
        row.update({
            "era": str(stat.get("era") or "—"),
            "ip": ip_val,
            "k_per_9":  _safe_float(stat.get("strikeoutsPer9Inn")),
            "bb_per_9": _safe_float(stat.get("walksPer9Inn")),
            "k_pct":  round(100 * so_p / tbf, 1) if tbf else None,
            "bb_pct": round(100 * bb_p / tbf, 1) if tbf else None,
            "tbf": tbf,
            "hr_per_9": hr_per_9,
            "hr_allowed": hr_allowed,
            "whip": _safe_float(stat.get("whip")),
            "wins": int(stat.get("wins", 0) or 0),
            "losses": int(stat.get("losses", 0) or 0),
            "is_pitcher": True,
        })
    else:
        pa = stat.get("plateAppearances", 0) or 0
        bb = stat.get("baseOnBalls", 0) or 0
        so = stat.get("strikeOuts", 0) or 0
        avg_str = str(stat.get("avg") or "")
        slg_str = str(stat.get("slg") or "")
        iso_val = None
        try:
            if avg_str and slg_str and avg_str != "—" and slg_str != "—":
                iso_val = round(float(slg_str) - float(avg_str), 3)
        except (TypeError, ValueError):
            iso_val = None
        row.update({
            "avg": str(stat.get("avg") or "—"),
            "obp": str(stat.get("obp") or "—"),
            "slg": str(stat.get("slg") or "—"),
            "ops": str(stat.get("ops") or "—"),
            "iso": iso_val,
            "hr":  int(stat.get("homeRuns", 0) or 0),
            "sb":  int(stat.get("stolenBases", 0) or 0),
            "rbi": int(stat.get("rbi", 0) or 0),
            "ab":  int(stat.get("atBats", 0) or 0),
            "bb_pct": round(100 * bb / pa, 1) if pa else None,
            "k_pct":  round(100 * so / pa, 1) if pa else None,
            "is_pitcher": False,
        })
    return row


def _fmt_rate(v: float) -> str:
    """Format a rate the way the API does: '.293', or '1.050' when >= 1."""
    s = f"{v:.3f}"
    return s[1:] if s.startswith("0.") else s


def _ip_outs(ip) -> int:
    """Innings-pitched string ('48.1' = 48⅓ IP) → integer outs."""
    try:
        whole, _, frac = str(ip).partition(".")
        return int(whole or 0) * 3 + (int(frac) if frac else 0)
    except (TypeError, ValueError):
        return 0


def _combine_stints(splits: list[dict], is_pitcher: bool) -> dict:
    """Sum a multi-team (season, level) into one combined line that reconciles to
    its per-org stints. Counting stats add; rate stats are recomputed from the
    summed components (an average of rates would be wrong)."""
    first = splits[0]
    S = [s.get("stat") or {} for s in splits]
    _sum = lambda f: sum(int(st.get(f, 0) or 0) for st in S)
    base = {
        "season": int(first.get("season") or 0),
        "level": first.get("_level"),
        "level_label": first.get("_level_label"),
        "org": None,                          # multi-org — the chip uses `stints`
        "games": _sum("gamesPlayed"),
    }
    if is_pitcher:
        outs = sum(_ip_outs(st.get("inningsPitched")) for st in S)
        ip_real = outs / 3 if outs else 0.0
        er, bb, h = _sum("earnedRuns"), _sum("baseOnBalls"), _sum("hits")
        hr, so, tbf = _sum("homeRuns"), _sum("strikeOuts"), _sum("battersFaced")
        base.update({
            "era": f"{(9 * er / ip_real):.2f}" if ip_real else "—",
            "ip": round(outs // 3 + (outs % 3) / 10.0, 1) if outs else None,
            "k_per_9":  round(9 * so / ip_real, 2) if ip_real else None,
            "bb_per_9": round(9 * bb / ip_real, 2) if ip_real else None,
            "k_pct":  round(100 * so / tbf, 1) if tbf else None,
            "bb_pct": round(100 * bb / tbf, 1) if tbf else None,
            "tbf": tbf,
            "hr_per_9": round(9 * hr / ip_real, 2) if ip_real else None,
            "hr_allowed": hr,
            "whip": round((bb + h) / ip_real, 2) if ip_real else None,
            "wins": _sum("wins"), "losses": _sum("losses"),
            "is_pitcher": True,
        })
    else:
        ab, h, tb = _sum("atBats"), _sum("hits"), _sum("totalBases")
        bb, hbp, sf = _sum("baseOnBalls"), _sum("hitByPitch"), _sum("sacFlies")
        pa, so = _sum("plateAppearances"), _sum("strikeOuts")
        obp_den = ab + bb + hbp + sf
        avg = h / ab if ab else 0.0
        slg = tb / ab if ab else 0.0
        obp = (h + bb + hbp) / obp_den if obp_den else 0.0
        base.update({
            "avg": _fmt_rate(avg) if ab else "—",
            "obp": _fmt_rate(obp) if obp_den else "—",
            "slg": _fmt_rate(slg) if ab else "—",
            # OPS by convention = (rounded OBP) + (rounded SLG), matching how the
            # API + single-org rows report it (not a re-rounded full-precision sum).
            "ops": _fmt_rate(round(obp, 3) + round(slg, 3)) if ab else "—",
            "iso": round(slg - avg, 3) if ab else None,
            "hr": _sum("homeRuns"), "sb": _sum("stolenBases"), "rbi": _sum("rbi"),
            "ab": ab,
            "bb_pct": round(100 * bb / pa, 1) if pa else None,
            "k_pct":  round(100 * so / pa, 1) if pa else None,
            "is_pitcher": False,
        })
    return base


def fetch_career_stats(player_key: str, mlbam_id: int,
                       is_pitcher: bool = False) -> list[dict] | None:
    """
    Pull year-by-year MiLB + MLB splits for one player in a single call.

    Returns one row per (season, level) tuple so a player who played
    A+/AA in 2025 surfaces BOTH levels. Rows sorted by season descending,
    then highest level first within each season. Returns None if the
    API gave us nothing.

    Callers that want the most-recent / highest level per season can
    use the first row per season; consumers that want the full ladder
    (the prospect-detail career table, the boom-bust sample floor) get
    every (season, level) split they need.

    Single-call: `leagueListId=mlb_milb` returns MLB + every MiLB level in
    one response, replacing the prior two-URL pattern (milb_full + MLB).
    Falls back to the two-URL pattern only if the combined call yields no
    splits (defensive for API edge cases).
    """
    group = "pitching" if is_pitcher else "hitting"
    base = f"{MLB_STATS_API}/people/{mlbam_id}/stats?stats=yearByYear&group={group}&hydrate=team"
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

    # Group the raw yearByYear splits by (season, level), keeping EVERY per-team
    # stint so a mid-season trade surfaces both orgs. The API also returns an
    # aggregate ("team": null) row per level — we skip it and recompute the
    # combined line ourselves by summing the stints, which reconciles to the
    # parts and dodges the aggregate row's null-league level ambiguity. Each
    # split resolves to the canonical PARENT org (a AA affiliate → its big club).
    from collections import OrderedDict
    from trades import canonical_org          # lazy import: trades imports stats
    groups: "OrderedDict[tuple, list]" = OrderedDict()
    for s in raw_splits:
        season = str(s.get("season") or "")
        if not season:
            continue
        team = s.get("team") or {}
        if not team.get("id"):
            continue                          # API aggregate row — recomputed below
        league = s.get("league") or {}
        sport_name = (league.get("sport") or {}).get("name") or ""
        league_name = league.get("name") or ""
        # The split's own sport id first (the level that season, see
        # _YBY_SPORT_LEVEL); the league-name table only when no id is given.
        sport_id = ((s.get("sport") or {}).get("id")
                    or (team.get("sport") or {}).get("id"))
        label = (_level_from_sport(sport_id, league_name)
                 or _level_label_from(league_name, sport_name))
        if label is None or label not in LEVEL_ORDER:
            continue
        s["_level"] = label
        s["_level_label"] = league_name or sport_name
        s["_org"] = canonical_org(team.get("parentOrgName") or team.get("name"))
        groups.setdefault((int(season), label), []).append(s)

    if not groups:
        return None

    # One row per (season, level), sorted season desc then level rank asc. A
    # single stint stays a plain row; 2+ stints collapse to a summed combined
    # line carrying the per-org `stints` breakdown in chronological (old → new)
    # order — the order the API returns them, which the consumer renders as the
    # dual-org chip + per-org split.
    out: list[dict] = []
    for skey in sorted(groups, key=lambda k: (-k[0], LEVEL_ORDER.index(k[1]))):
        splits = groups[skey]
        stint_rows = [_row_from_split(s, is_pitcher) for s in splits]
        if len(stint_rows) == 1:
            out.append(stint_rows[0])
        else:
            combined = _combine_stints(splits, is_pitcher)
            combined["stints"] = stint_rows   # per-org lines (old → new)
            out.append(combined)

    # Cap at CAREER_SEASONS_KEPT UNIQUE seasons (not rows) so the multi-level
    # ladder doesn't truncate the table. Walk collecting rows until the season
    # set hits the cap.
    kept_seasons: set[int] = set()
    capped: list[dict] = []
    for r in out:
        kept_seasons.add(r["season"])
        if len(kept_seasons) > CAREER_SEASONS_KEPT:
            break
        capped.append(r)
    return capped


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
    # Sport-id 16 covers all "Rookie" leagues including the Complex
    # Leagues (FCL/ACL) AND the Dominican Summer League. We default the
    # label to CPX and let `_career_row_from_bulk_split` override to DSL
    # when the per-split league name confirms it.
    16: "CPX",
    17: "DSL",  # MLB Stats API occasionally exposes DSL under sport-id 17
    21: "DSL",  # and 21
}

# Sports covered by the bulk season-stats path. We now include DSL
# sport-ids (17 + 21) so DSL prospects are picked up by the bulk path
# instead of falling to the slower per-player career fetch. Sport-id 16
# rows get the CPX-vs-DSL refinement via league-name inspection.
BULK_STATS_SPORT_IDS: tuple[int, ...] = (1, 11, 12, 13, 14, 16, 17, 21)


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
    # Refine rookie-level rows by inspecting the league name. Sport-id 16
    # lumps the US complex leagues together with DSL on some API responses;
    # checking the league name kicks DSL rows out of CPX into the correct
    # bucket. (No-op for non-rookie sports since the labels won't match.)
    league = split.get("league") or {}
    league_name = league.get("name") or ""
    # This endpoint names the Dominican league 'DSL', not 'Dominican Summer
    # League', so a substring test for 'dominican' never fired and 160 current-
    # season DSL lines were cached as CPX (2026-10-02).
    if label == "CPX" and _is_dsl_league(league_name):
        label = "DSL"
    season = split.get("season")
    if not season:
        return None
    stat = split.get("stat") or {}
    is_pitcher = (group == "pitching")
    row: dict = {
        "season": int(season),
        "level": label,
        # Prefer the actual league name when available (e.g.
        # "Dominican Summer League"); fall back to sport abbreviation or
        # the short label so the career-table tooltip is never empty.
        "level_label": league_name or sport.get("abbreviation") or label,
        "org": None,
        "games": int(stat.get("gamesPlayed", 0) or 0),
    }
    team = split.get("team") or {}
    if team.get("id"):
        try:
            from trades import canonical_org
            row["org"] = canonical_org(team.get("parentOrgName") or team.get("name"))
        except Exception:
            row["org"] = team.get("parentOrgName") or team.get("name")
    if is_pitcher:
        ip_val = (float(stat.get("inningsPitched"))
                  if stat.get("inningsPitched") else None)
        hr_allowed = int(stat.get("homeRuns", 0) or 0)
        # Same HR/9 derivation as the per-player career path — prefer the
        # API's per-9 metric when surfaced, fall back to the count/IP
        # computation. See fetch_career_stats for why this matters.
        hr_per_9 = _safe_float(stat.get("homeRunsPer9"))
        if hr_per_9 is None and ip_val and ip_val > 0:
            hr_per_9 = round(hr_allowed * 9.0 / ip_val, 2)
        tbf = int(stat.get("battersFaced", 0) or 0)
        so_p = int(stat.get("strikeOuts", 0) or 0)
        bb_p = int(stat.get("baseOnBalls", 0) or 0)
        row.update({
            "era":     str(stat.get("era") or "—"),
            "ip":      ip_val,
            "k_per_9":  _safe_float(stat.get("strikeoutsPer9Inn")),
            "bb_per_9": _safe_float(stat.get("walksPer9Inn")),
            "k_pct":   round(100 * so_p / tbf, 1) if tbf else None,
            "bb_pct":  round(100 * bb_p / tbf, 1) if tbf else None,
            "tbf":     tbf,
            "hr_per_9": hr_per_9,
            "hr_allowed": hr_allowed,
            "whip":    _safe_float(stat.get("whip")),
            "wins":    int(stat.get("wins", 0) or 0),
            "losses":  int(stat.get("losses", 0) or 0),
            "is_pitcher": True,
        })
    else:
        pa = stat.get("plateAppearances", 0) or 0
        bb = stat.get("baseOnBalls", 0) or 0
        so = stat.get("strikeOuts", 0) or 0
        avg_str = str(stat.get("avg") or "")
        slg_str = str(stat.get("slg") or "")
        iso_val = None
        try:
            if avg_str and slg_str and avg_str != "—" and slg_str != "—":
                iso_val = round(float(slg_str) - float(avg_str), 3)
        except (TypeError, ValueError):
            iso_val = None
        row.update({
            "avg":    str(stat.get("avg") or "—"),
            "obp":    str(stat.get("obp") or "—"),
            "slg":    str(stat.get("slg") or "—"),
            "ops":    str(stat.get("ops") or "—"),
            "iso":    iso_val,
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
) -> dict[int, list[dict]]:
    """Bulk-fetch one season of stats for every player across the given
    sports, returning {mlbam_id: [career_row, ...]}.

    Replaces ~3000 per-player /people/{id}/stats?stats=yearByYear calls
    with one paginated call per (sport, group) — typically 1-2 pages per
    combo. The returned rows match the shape fetch_career_stats produces
    so they can be merged into career_cache directly.

    When a player has stints at multiple levels in the same season, every
    (season, level) row the endpoint returns is retained. When a player has
    multiple org stints at the same level, the row carries the same `stints`
    payload as the per-player yearByYear path.

    The endpoint answers with the QUALIFIED pool only (no playerPool
    parameter): measured 2026-10-02, 124 Triple-A hitters for 2026 against
    927 under playerPool=ALL. So a player qualified at one level and not at
    another comes back with one of his levels, and the merge below replaces
    his whole season with it. run_monthly's per-player pass re-fetches every
    such player from yearByYear (_career_missing_league_lines), which is
    where the missing level lines come back.
    """
    from collections import OrderedDict

    groups: "OrderedDict[tuple[int, int, str], list[dict]]" = OrderedDict()
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
                s["_level"] = row["level"]
                s["_level_label"] = row["level_label"]
                s["_org"] = row.get("org")
                groups.setdefault((int(pid), row["season"], row["level"]), []).append(s)
            if len(splits) < page_size:
                break
            offset += page_size
    out: dict[int, list[dict]] = {}
    is_pitcher = (group == "pitching")
    for (pid, _season, _level), splits in groups.items():
        stint_rows = [_row_from_split(s, is_pitcher) for s in splits]
        if len(stint_rows) == 1:
            row = stint_rows[0]
        else:
            row = _combine_stints(splits, is_pitcher)
            row["stints"] = stint_rows
        out.setdefault(pid, []).append(row)
    for rows in out.values():
        rows.sort(key=lambda r: (-int(r.get("season") or 0), LEVEL_ORDER.index(r["level"])))
    log.info("bulk_fetch_season_stats season=%d group=%s sports=%s: %d players",
             season, group, list(sport_ids), len(out))
    return out


def merge_bulk_into_career_cache(
    bulk_by_mlbam: dict[int, dict | list[dict]],
    career_cache: dict[str, list[dict]],
    id_cache: dict[str, int],
    season: int,
    eligible_keys: set[str] | None = None,
) -> dict[str, list[dict]]:
    """Splice the bulk fetch's current-season rows into the per-player
    career cache and return the {key: rows} subset that changed so the
    caller can persist it.

    For each player with bulk rows: drop any existing row for `season`,
    insert the bulk row(s) at the top of the list, cap to
    CAREER_SEASONS_KEPT unique seasons.
    Players are skipped if `eligible_keys` is provided and they aren't in
    it (used to exclude graduates from the in-season update).
    """
    updates: dict[str, list[dict]] = {}
    for key, mlbam in id_cache.items():
        if eligible_keys is not None and key not in eligible_keys:
            continue
        if mlbam is None:
            continue
        bulk_rows_raw = bulk_by_mlbam.get(int(mlbam))
        if bulk_rows_raw is None:
            continue
        bulk_rows = bulk_rows_raw if isinstance(bulk_rows_raw, list) else [bulk_rows_raw]
        bulk_rows = [r for r in bulk_rows if isinstance(r, dict)]
        if not bulk_rows:
            continue
        bulk_rows.sort(key=lambda r: (-int(r.get("season") or 0), LEVEL_ORDER.index(r["level"])))
        existing = career_cache.get(key) or []
        filtered = [r for r in existing if r.get("season") != season]
        candidate = bulk_rows + filtered
        kept_seasons: set[int] = set()
        merged: list[dict] = []
        for r in candidate:
            kept_seasons.add(int(r.get("season") or 0))
            if len(kept_seasons) > CAREER_SEASONS_KEPT:
                break
            merged.append(r)
        updates[key] = merged
        career_cache[key] = merged
    return updates


# ---------------------------------------------------------------------------
# Per-player transactions fetch  →  drives level-change detection AND the
# options / debut-date / service-time heuristics.
# ---------------------------------------------------------------------------

# How many seasons of transaction history to pull.
#
# WAS 7, RAISED 2026-09-04. The old comment said six covers the pre-arb plus arbitration
# window and that "older rows aren't load-bearing for any downstream derivation". That was
# true when it was written and stopped being true when the health-profile lane started
# reading injured-list history off this table: the eFV label window opens at debut year
# 2011, so a 7-season window left pre-decision injury coverage at exactly 0 percent for
# every 2016-2018 debut and about 34 percent overall. The endpoint was never the limit;
# probed with an explicit start_year it returns injured-list events back to 2014 for Byron
# Buxton and 2016 for Aaron Nola. Widening it recovered 16,678 pre-2019 events across 1,684
# players and took coverage to about 60 percent per side.
#
# The cost is payload SIZE, not request count: it is still one request per player, and the
# fetch is already TTL-gated. Keep this at or above the span between the eFV label window's
# first debut year and today, or the health lane silently loses its early cohorts again.
TRANSACTIONS_LOOKBACK_SEASONS = 16


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
            # Entry order and the effective day. _walk_il_stints needs both
            # to sequence late-entered, backdated IL placements.
            "id": tx.get("id"),
            "effective_date": tx.get("effectiveDate") or "",
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
# Pre-2021-reorg rookie/complex aliases share the modern complex (CPX) tier so
# point-in-time level changes built on era-correct names (a 2019 AZL / GCL move
# now labeled "Rk") still rank correctly for promotion/demotion direction.
# Mirrors the frontend LEVEL_RANK, which already collapses these onto one tier.
_LEVEL_RANK.update({a: _LEVEL_RANK["CPX"]
                    for a in ("Rk", "R", "ROK", "FCL", "ACL", "AZL", "GCL")})


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

# Arizona Fall League / showcase teams use real team ids in the MLB Stats
# API and can be returned from the same team endpoint as DSL/rookie teams.
# They are development/exhibition assignments, not affiliate level moves.
_AFL_TEAM_PHRASES = (
    "arizona fall league",
    "mesa solar sox",
    "salt river rafters",
    "glendale desert dogs",
    "peoria javelinas",
    "scottsdale scorpions",
    "surprise saguaros",
    "fall stars",
)


def _is_exhibition_team(name: str | None) -> bool:
    if not name:
        return False
    low = name.lower()
    return any(p in low for p in _AFL_TEAM_PHRASES)

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
                          affil_by_year: dict[int, dict]) -> list[dict]:
    """
    Walk a player's transactions in date order, resolve each move's from/to level
    + team name POINT-IN-TIME (against the affiliation map for the event's OWN
    year), and emit one record per actual level change.

    `affil_by_year` is {year: {team_id: info}} — one season-aware affiliation map
    per event year (the 2021 MiLB reorg renamed & re-leveled many clubs) — so a
    pre-2021 move resolves to the name/league/level in effect THEN ("AZL Rangers"
    / Rk), not the current post-reorg naming ("ACL Rangers" / CPX).

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
        # Point-in-time: resolve this move against the affiliation map for ITS
        # OWN year so pre-2021 events get era-correct team names + levels.
        _yr = int(date_iso[:4]) if date_iso[:4].isdigit() else None
        team_affiliations = affil_by_year.get(_yr) or {}
        type_code = tx.get("type_code") or ""
        if type_code and type_code not in _LEVEL_AFFECTING_TYPE_CODES:
            continue
        desc_low = (tx.get("description") or "").lower()
        if any(p in desc_low for p in _NON_LEVEL_CHANGE_PHRASES):
            # Spring training / exhibition / placeholder row — never a
            # real affiliate move, even when the API team_id resolves.
            continue
        if _is_exhibition_team(desc_low):
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
        if (_is_exhibition_team(to_name) or _is_exhibition_team(tx.get("to_team_name"))
                or _is_exhibition_team(from_name) or _is_exhibition_team(tx.get("from_team_name"))):
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
# Transaction classification — non-trade events that are still worth
# surfacing on the prospect detail page. Trades themselves come from the
# `trades.py` pipeline; everything else (waiver claims, releases,
# contract purchases, Rule 5 selections/returns, free-agent signings, DFA
# events) flows through here so the UI can keep "trades" semantically
# strict while still showing the full transaction history.
# ---------------------------------------------------------------------------

# typeCode → (kind, polite_label). Anything not in this map is filtered
# out by derive_transactions (it's either a level change — already in
# level_changes — an IL placement, or noise like spring-training invites).
#
# References:
#   TR  = Trade                                    (handled by trades.py)
#   CU  = Claimed Off Waivers                      → waiver_claim
#   CLM = Claim (older alias)                      → waiver_claim
#   PU/PUR = Purchased Contract / Selection of Contract → contract_purchase
#   REL = Released                                 → released
#   DES = Designated for Assignment                → dfa
#   OUT = Outrighted (off 40-man, kept by org)     → outrighted
#   SE  = Selection (Rule 5 / contract selection)  → rule_5_selection
#         (only emitted when from_team differs from to_team — a within-
#         org "selection of contract" is just an MLB call-up that
#         level_changes already covers.)
#   SC  = Selected (newer alias on some records)   → rule_5_selection
#   RET = Returned to Org (Rule 5)                 → rule_5_return
#   SFA = Signed as Free Agent                     → signed_free_agent
#   SGN = Signed (free agent / minor-league deal)  → signed_free_agent
# MLB Stats API typeCode → (event kind, polite label). Derived empirically
# from what the cached payloads actually look like in our DB. Notable
# pitfalls embedded here:
#   * CU is "Recalled" (roster recall from MiLB) — NOT a waiver claim.
#     The real waiver-claim code is CLW.
#   * SE / SC are "Selection" / "Status Change" — used for routine
#     activations, IL bookkeeping, fall-league rows. None of these are
#     events worth surfacing on a prospect page.
#   * OPT / REC (option / recall) are level changes — already covered by
#     level_changes, so deliberately omitted here.
#   * Trades (TR) live in `trades.py` with their own pipeline + snapshot-
#     inference fallback; including them here would double-emit.
_TRANSACTION_TYPE_TO_KIND: dict[str, tuple[str, str]] = {
    "CLW": ("waiver_claim",       "Waiver claim"),
    "PU":  ("contract_purchase",  "Contract purchase"),
    "PUR": ("contract_purchase",  "Contract purchase"),
    "R5":  ("contract_purchase",  "Rule 5 pick"),
    "R5M": ("contract_purchase",  "Rule 5 pick (MLB)"),
    "REL": ("released",           "Released"),
    "DES": ("dfa",                "Designated for assignment"),
    "DFA": ("dfa",                "Designated for assignment"),
    "OUT": ("outrighted",         "Outrighted to MiLB"),
    "RET": ("rule_5_return",      "Rule 5 return"),
    "RTN": ("rule_5_return",      "Rule 5 return"),
    "SFA": ("signed_free_agent",  "Signed as free agent"),
    "SGN": ("signed_free_agent",  "Signed"),
}

# Additional noise phrases scrubbed specifically by derive_transactions.
# These appear in rows whose `type_code` lands in our keep-set but whose
# `description` makes clear the event isn't worth surfacing — usually
# routine roster bookkeeping already reflected in roster_status.
_NON_TRANSACTION_PHRASES = (
    "injured list",
    "temporarily inactive",
    "bereavement",
    "paternity",
    "restricted list",
    "roster status changed",
    "college workout",
    "high school workout",
)


def derive_transactions(transactions: list[dict]) -> list[dict]:
    """Turn one player's `/transactions` rows into the cleaned-up
    NON-TRADE event list that feeds `player.transactions` on the export.

    Trades stay in their own pipeline (`trades.py`) because they're
    surfaced as first-class events on the FV chart with their own
    bracketing logic + reconciliation. The list returned here covers
    everything else worth showing on the timeline: waiver claims, DFAs,
    releases, outrights, contract purchases, Rule 5 moves, and free-agent
    signings. Level changes and IL placements are deliberately excluded
    because they already have dedicated structures (`level_changes`,
    `roster_status.injury_history`).

    Output shape (per row, sorted oldest to newest):
        {
          "date":        "YYYY-MM-DD",
          "kind":        "waiver_claim" | "released" | "dfa" | ...,
          "type_code":   "CU",                # original API code
          "type_desc":   "Claimed Off Waivers",
          "description": full text from the API,
          "from_team":   str | None,          # canonical when resolvable
          "to_team":     str | None,
        }
    """
    out: list[dict] = []
    for tx in transactions:
        type_code = (tx.get("type_code") or "").upper()
        mapped = _TRANSACTION_TYPE_TO_KIND.get(type_code)
        if mapped is None:
            continue
        kind, _polite = mapped
        # Skip noise: spring-training invites, rehab assignments, and
        # placeholder-team rows (mirrors derive_level_changes filters),
        # plus the transaction-specific filters for IL bookkeeping and
        # workout activations.
        desc_low = (tx.get("description") or "").lower()
        if any(p in desc_low for p in _NON_LEVEL_CHANGE_PHRASES):
            continue
        if _is_exhibition_team(desc_low):
            continue
        if any(p in desc_low for p in _NON_TRANSACTION_PHRASES):
            continue
        to_name   = tx.get("to_team_name")   or ""
        from_name = tx.get("from_team_name") or ""
        if _is_placeholder_team(to_name) or _is_placeholder_team(from_name):
            continue
        if _is_exhibition_team(to_name) or _is_exhibition_team(from_name):
            continue
        out.append({
            "date":        tx.get("date") or "",
            "kind":        kind,
            "type_code":   type_code,
            "type_desc":   tx.get("type_desc") or "",
            "description": tx.get("description") or "",
            "from_team":   from_name or None,
            "to_team":     to_name or None,
        })
    out.sort(key=lambda r: r.get("date") or "")
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

# Rookie-status exhaustion thresholds (current MLB rules per
# https://www.mlb.com/glossary/rules/rookie-eligibility):
#   - Position players: more than 130 MLB at-bats
#   - Pitchers: more than 50 MLB innings pitched
#   - Either: more than 45 days on the active MLB roster, EXCLUDING days
#     on the IL and EXCLUDING days after September 1 (rosters expand).
# A player who crosses ANY of these loses rookie eligibility.
ROOKIE_AB_THRESHOLD = 130
ROOKIE_IP_THRESHOLD = 50.0
ROOKIE_ACTIVE_DAYS_THRESHOLD = 45   # v15 — official third rule

# Standard MLB option allotment. Players added to a 40-man get three
# option YEARS — distinct seasons in which they spend >20 days on an
# optional MiLB assignment. A small subset of players get a fourth
# option granted; we don't try to detect that case automatically.
DEFAULT_OPTIONS = 3


# v15 — Transaction descriptors that move a player ONTO the active MLB
# roster. We treat each as the START of an "active" segment.
_ACTIVATING_DESCRIPTORS = (
    "selected the contract",
    "purchased the contract",
    "recalled",
    "reinstated",
    "activated",
)
# Transaction descriptors that move a player OFF the active MLB roster.
# Each ENDS an "active" segment.
_DEACTIVATING_DESCRIPTORS = (
    "optioned",
    "sent outright",
    "designated for assignment",
    "placed on the 10-day il",
    "placed on the 15-day il",
    "placed on the 60-day il",
    "placed on the injured list",
    "released",
    "traded",            # ends segment with current org; new org's add starts a fresh one
    "claimed off waivers",
    "removed from the 40-man",
    "elected free agency",
    "suspended",
    "retired",
)


def _count_active_roster_days(transactions: list[dict],
                              today: date | None = None) -> int:
    """Estimate days a player has been on the active MLB roster, summed
    across all stints, EXCLUDING days on the injured list and EXCLUDING
    any days after Sept 1 of each season (active-roster expansion).

    Walks transactions chronologically. Maintains a simple state machine
    with an "active_since" date that gets set on activating events and
    accumulated-then-cleared on deactivating events. If a player is
    currently active (last event activated them) we accumulate through
    today's date.

    Heuristic and imperfect, but captures the spirit of the official
    rookie-eligibility rule for the common case. Cup-of-coffee callups
    that bounce in and out across IL stints are handled correctly; the
    main gap is players whose transactions log doesn't reflect a real
    activation event (rare since the API exposes SE / Active codes).
    """
    today = today or date.today()
    rows: list[tuple[str, str, str]] = []  # (date, kind, lowercased description)
    for tx in transactions or []:
        d_iso = (tx.get("date") or "").strip()
        if not d_iso:
            continue
        desc = (tx.get("description") or "").lower()
        kind: str | None = None
        if any(p in desc for p in _ACTIVATING_DESCRIPTORS):
            kind = "activate"
        elif any(p in desc for p in _DEACTIVATING_DESCRIPTORS):
            kind = "deactivate"
        if kind is None:
            continue
        rows.append((d_iso, kind, desc))
    rows.sort(key=lambda r: r[0])

    total_days = 0
    active_since: date | None = None

    def _clip_to_window(start: date, end: date) -> int:
        """Return the number of days in [start, end] that fall ON or BEFORE
        Sept 1 of each year (excluding the post-expansion window)."""
        if end < start:
            return 0
        days = 0
        cursor = start
        while cursor <= end:
            year = cursor.year
            season_cap = date(year, 9, 1)
            if cursor > season_cap:
                # Jump to Jan 1 of next year (skip the post-expansion days)
                next_jan = date(year + 1, 1, 1)
                if next_jan > end:
                    break
                cursor = next_jan
                continue
            # Add days from cursor up to min(end, season_cap), then jump past
            segment_end = min(end, season_cap)
            days += (segment_end - cursor).days + 1
            cursor = segment_end + (date(year, 9, 2) - segment_end)
        return days

    for d_iso, kind, _desc in rows:
        try:
            d = date.fromisoformat(d_iso[:10])
        except (ValueError, TypeError):
            continue
        if kind == "activate":
            if active_since is None:
                active_since = d
        else:  # deactivate
            if active_since is not None:
                total_days += _clip_to_window(active_since, d)
                active_since = None
    # If the player is currently on the active roster, accumulate through today.
    if active_since is not None:
        total_days += _clip_to_window(active_since, today)
    return total_days


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
    # v31.13 — Defensive chronological sort so the on_40_man gate +
    # option-window state machine see events in the correct order
    # regardless of caller input. fetch_player_transactions already
    # date-sorts; this protects tests / ad-hoc callers passing
    # unordered lists.
    transactions = sorted(transactions or [],
                          key=lambda r: (r.get("date") or ""))

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
    # v31.13 — Track per-season days on optional assignment so we can
    # apply the 20-day rule (effective 2020+: an option year only counts
    # as "used" if the player accumulates ≥20 days on optional assignment
    # in that calendar season). Walk transactions chronologically,
    # marking the start of each optional-assignment window when the
    # player is optioned + currently on the 40-man, and closing the
    # window at the next recall / selection / activation.
    option_start_by_year: dict[int, date | None] = {}
    days_optioned_by_year: dict[int, int] = {}
    today_cap = today  # close any still-open windows at today

    def _close_option_window(year: int, end_d: date):
        start_d = option_start_by_year.get(year)
        if start_d is None:
            return
        days = max(0, (end_d - start_d).days)
        days_optioned_by_year[year] = days_optioned_by_year.get(year, 0) + days
        option_start_by_year[year] = None

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
        try:
            tx_d = date.fromisoformat(date_iso[:10])
            tx_yr = tx_d.year
        except (ValueError, TypeError):
            tx_d = None
            tx_yr = None
        # 40-man add (typeCode "SE" or any row with "selected the contract").
        if type_code == "SE" or "selected the contract" in desc_low \
                or "purchased the contract" in desc_low:
            # A contract selection closes any open optional-assignment
            # window — the player is back on the active MLB roster.
            if tx_yr is not None and tx_d is not None:
                _close_option_window(tx_yr, tx_d)
            on_40_man = True
            if not selection_date:
                selection_date = date_iso
        # 40-man drop — "sent outright" clears once the player passes
        # through waivers off the 40-man roster.
        elif "sent outright" in desc_low or "removed from the 40" in desc_low:
            on_40_man = False
            # An outright clears any open optional window (player no
            # longer occupies a 40-man spot, so the option isn't
            # actively burning).
            if tx_yr is not None and tx_d is not None:
                _close_option_window(tx_yr, tx_d)
        # Recall / activation — closes the optional-assignment window.
        if ("recalled" in desc_low or type_code == "REC"
                or "activated" in desc_low):
            if tx_yr is not None and tx_d is not None:
                _close_option_window(tx_yr, tx_d)
        # Option year — count any optioning event by season, BUT only
        # when the player is actually on the 40-man at the time. A
        # non-40-man prospect can't burn an option — the MLB rule keys
        # off occupying a 40-man spot. Without this gate the MLB Stats
        # API's loose "optioned" descriptions on minor-league assignment
        # rows leaked phantom options onto pre-debut prospects (Edwin
        # Arroyo case — was showing 2 of 3 used despite no MLB debut).
        if (type_code == "OPT" or "optioned" in desc_low) and on_40_man:
            if tx_yr is not None and tx_d is not None:
                options_seasons.add(tx_yr)
                # Start (or restart) the optional-assignment window.
                if option_start_by_year.get(tx_yr) is None:
                    option_start_by_year[tx_yr] = tx_d
    # Close any windows still open against TODAY (player currently on
    # optional assignment).
    for yr, start_d in list(option_start_by_year.items()):
        if start_d is not None:
            _close_option_window(yr, today_cap)
    # v31.13 — Apply the 20-day rule. An option-year only counts as
    # USED when the player accumulated ≥20 days on optional assignment.
    # Sub-20-day "phantom" options (e.g. optioned in spring training,
    # selected back to MLB after a brief MiLB stint) drop out.
    options_seasons = {
        yr for yr in options_seasons
        if days_optioned_by_year.get(yr, 0) >= 20
    }

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
        debut_date_source = "api"
    elif selection_date and has_mlb_activity:
        debut_date = selection_date
        debut_date_source = "selection"
    else:
        debut_date = None
        debut_date_source = None

    # Rookie / prospect status is lost when the player crosses any of:
    #   * 130 career MLB at-bats          (hitters)
    #   * 50  career MLB innings pitched  (pitchers)
    #   * 45 days on the active MLB roster excluding IL + post-Sept-1
    #     (v15 — third official gate from MLB rookie-eligibility rule)
    #   * has burned all minor-league options AND has at least debuted in
    #     MLB — a player with no options left can't be sent down without
    #     clearing waivers, so the team has effectively committed the
    #     roster spot. Kept as a backstop proxy for the 45-day rule when
    #     the transactions log is incomplete.
    options_exhausted = (len(options_seasons) >= DEFAULT_OPTIONS
                         and debut_date is not None)
    # v15 — Active-roster day count from transactions.
    active_roster_days = _count_active_roster_days(transactions or [], today)
    if mlb_ab_total > ROOKIE_AB_THRESHOLD:
        graduation_reason: str | None = "ab_threshold"
    elif mlb_ip_total > ROOKIE_IP_THRESHOLD:
        graduation_reason = "ip_threshold"
    elif active_roster_days > ROOKIE_ACTIVE_DAYS_THRESHOLD and has_mlb_activity:
        graduation_reason = "active_days_threshold"
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

    # v31.13 — Pre-debut gate. Per user product decision, options do
    # NOT count as "used" for prospects who have never appeared in an
    # MLB game, even if they're on the 40-man and have been on
    # optional assignment for 20+ days. The MLB-canonical rule says
    # such a player has burned a year; but for prospect-tracking
    # purposes the user wants the chip to read 3/3 until the prospect
    # actually debuts (the moment the team has truly "committed" the
    # roster spot). Edwin Arroyo case: 40-man add Nov 2025 + optioned
    # March 2026 reads as 3/3 here despite the canonical rule saying
    # 2/3, because he has not yet debuted.
    if debut_date is None:
        options_seasons = set()
    options_used = min(DEFAULT_OPTIONS, len(options_seasons))
    options_remaining = max(0, DEFAULT_OPTIONS - options_used)

    return {
        "mlb_debut_date":         debut_date,
        # DS-12 (docs/efv-v2/DRIVER_SYSTEM_V2.md, bug B7): where the date came
        # from. "selection" is the first contract selection, which for a
        # November Rule 5 protection add is NOT a game date; run_monthly asks
        # /people/{id} for those before storage would roll them forward to a
        # {year}-07-01 placeholder.
        "mlb_debut_date_source":  debut_date_source,
        "on_40_man":              bool(on_40_man),
        "options_used":           options_used,
        "options_used_years":     sorted(options_seasons),
        "options_remaining":      options_remaining,
        "mlb_seasons":            mlb_seasons,
        "career_mlb_ab":          mlb_ab_total,
        "career_mlb_ip":          round(mlb_ip_total, 1),
        "active_roster_days":     int(active_roster_days),    # v15 — third rookie gate
        "rookie_exhausted":       bool(rookie_exhausted),
        "graduation_reason":      graduation_reason,
        "service_phase":          service_phase,
        "injury_history":         derive_injury_history(transactions or []),
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
    consistent across the codebase. Both paths walk the same
    _walk_il_stints, so a stint that fetch_il_status reports closed is
    closed here too (see that function for the close signals).
    """
    return _walk_il_stints(transactions or [])


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

    # The request is SEASON-SCOPED (season={season} above), so more than one split
    # never means more than one season. It means STINTS: StatsAPI returns the
    # season TOTAL first, marked with numTeams and carrying no team block, then one
    # row per club. The old code took splits[-1] with the comment "last in list is
    # usually most recent season slice", which is the LAST STINT for anyone traded.
    #
    # Verified against the live API 2026-07-31, mlbam 672275 (traded mid-season):
    # splits[0] numTeams=2 -> wRC+ 53.2, WAR 0.204; splits[-1] (San Francisco leg)
    # -> wRC+ 14.8, WAR -0.156. For a player who was not traded there is exactly
    # one split and the two readings are identical, which is why this survived.
    # It is not cosmetic: prospx renders this wRC+ as a headline chip.
    agg = next((s for s in splits if s.get("numTeams")), None)
    stat = (agg or splits[0]).get("stat", {})

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
# Career WAR - bulk bWAR pull via pybaseball (Baseball-Reference war_daily)
# ---------------------------------------------------------------------------
# This is the bWAR FRAME feed, not the served series. eWAR epoch (owner
# decision 2026-09-03): the site serves and labels on eWAR v2 (ewar.py), which
# is this same Baseball-Reference run frame with pitching re-priced on FIP
# (centred per season x role) and fielding left at B-Ref's rfield (swap
# weight 0.0, measured). bWAR stays the INPUT: run_monthly calls
# war_source.career_war_bulk (default provider), and the 'bwar' provider
# delegates here verbatim (pinned byte-exact by test_war_source.py). The
# career_war sqlite table keeps the frame beside the served series as
# `seasons_bwar` (storage.upsert_career_war). For position players the two
# series are equal until the SDR defense drop lands.
#
# The MLB Stats API only returns WAR inside the `stats=sabermetrics` endpoint
# and only one season at a time, so a per-player loop would be 2-4k extra
# requests on a cold cache; B-Ref's war_daily tables arrive as two static
# CSVs covering every player-season in one shot.
#
# Returned aggregate per player_key:
#   {"seasons": {"2023": 1.5, "2024": 2.8, ...},
#    "career_war": 4.3,
#    "war_per_yr": 2.15,
#    "war_seasons_count": 2,
#    "source": "bbref",
#    "seasons_pa": {"2023": 512, "2024": 601},       # measured MLB exposure on
#    "seasons_ip": {"2023": 0.0, "2024": 0.0}}       # the SAME stints as the WAR
# `seasons` is sparse - only years the player actually appeared in MLB.
#
# MEASURED EXPOSURE (owner decision 14c, 2026-09-11). `seasons_pa` is the war_daily
# batting frame's PA and `seasons_ip` the pitching frame's IPouts / 3, summed over
# exactly the stints whose WAR `seasons` sums (same player, same year window, WAR
# not blank), one entry per season in `seasons`. A season with no WAR-bearing stint
# on one side is a measured 0 on that side (the frame was read and has none). A side
# whose frame did not load or carries no exposure column is OMITTED, never zeroed:
# omission is "not measured", which storage treats as missing. storage's WAG gate
# reads it where the MLB Stats API career_stats rows measure nothing for the role
# (641 graduates have no such row at all); rows stored before 2026-09-11 get it from
# storage.persist_career_war_exposure, which reads war_daily_exposure below.

_EXPOSURE_COLUMN = {"bat": ("PA", 1.0), "pit": ("IPouts", 1.0 / 3.0)}


def season_exposure_by_id(df, side: str, cohort_ids=None, start_year: int | None = None,
                          end_year: int | None = None) -> dict[int, dict[int, float]] | None:
    """{mlb_ID: {year: exposure}} from one war_daily stint frame: PA on 'bat', innings
    (IPouts / 3) on 'pit', summed over the stints fetch_career_war_bulk sums WAR on
    (cohort, year window, WAR not blank). None when the frame is absent or has no
    exposure column, so a caller can tell "not measured" from "measured zero"."""
    col, scale = _EXPOSURE_COLUMN[side]
    if df is None or getattr(df, "empty", True) or col not in df.columns:
        return None
    sub = df
    if cohort_ids is not None:
        sub = sub[sub["mlb_ID"].isin(cohort_ids)]
    if start_year is not None and end_year is not None:
        sub = sub[sub["year_ID"].between(start_year, end_year)]
    sub = sub[sub["WAR"].notna()]
    out: dict[int, dict[int, float]] = {}
    for mid, yr, val in zip(sub["mlb_ID"].tolist(), sub["year_ID"].tolist(),
                            sub[col].tolist()):
        try:
            mid, yr = int(mid), int(yr)
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v != v:            # a blank exposure cell on a WAR-bearing stint adds 0
            v = 0.0
        yr_map = out.setdefault(mid, {})
        yr_map[yr] = yr_map.get(yr, 0.0) + v * scale
    return out


def _exposure_for_seasons(seasons: dict, by_year: dict[int, float] | None,
                          *, innings: bool) -> dict[str, float] | None:
    """One season-keyed exposure map for an aggregate's `seasons`, or None when the
    side was not measured. PA rounds to whole appearances, innings to 2dp."""
    if by_year is None:
        return None
    out: dict[str, float] = {}
    for yr_s in seasons:
        v = by_year.get(int(yr_s), 0.0)
        out[yr_s] = round(v, 2) if innings else int(round(v))
    return out


_WAR_DAILY_EXPOSURE_MEMO: dict = {}


def _stint_war_by_id(df) -> dict[int, dict[int, float]]:
    """{mlb_ID: {year: WAR}} summed over one frame's WAR-bearing stints (the sum
    fetch_career_war_bulk stores, before its 2dp rounding)."""
    sub = df[df["WAR"].notna()]
    out: dict[int, dict[int, float]] = {}
    for mid, yr, war in zip(sub["mlb_ID"].tolist(), sub["year_ID"].tolist(),
                            sub["WAR"].tolist()):
        try:
            mid, yr, war = int(mid), int(yr), float(war)
        except (TypeError, ValueError):
            continue
        yr_map = out.setdefault(mid, {})
        yr_map[yr] = yr_map.get(yr, 0.0) + war
    return out


def war_daily_exposure(mlbam_ids: Iterable[int]) -> dict[int, dict[int, dict[str, float]]]:
    """{mlb_ID: {year: {"pa": PA, "ip": IP, "war": bWAR}}} for the given ids, read
    OFFLINE from the war_daily last-good cache (.cache/war_daily/{bat,pit}.parquet,
    the raw bWAR frames war_source.stint_frame stores on every fetch), on the same
    stint rule as the career_war aggregate. `war` is that aggregate's season value
    (batting plus pitching, 2dp), so a caller can check that a stored WAR is the
    vintage the exposure comes from. Both sides or nothing: with one side's cache
    absent a season on that side would read as a measured 0, so {} is returned, with
    a warning. A (player, year) with a WAR-bearing stint on either side gets all three
    keys (0 on the side it has none). Memoised per process on the two files' mtimes."""
    import war_source
    paths = {side: war_source._cache_path(side) for side in ("bat", "pit")}
    try:
        stamp = tuple((str(p), p.stat().st_mtime) for p in paths.values())
    except OSError:
        log.warning("war_daily_exposure: no war_daily cache at %s",
                    " / ".join(str(p) for p in paths.values()))
        return {}
    if _WAR_DAILY_EXPOSURE_MEMO.get("stamp") != stamp:
        import pandas as pd
        sides = {}
        for side, p in paths.items():
            col = _EXPOSURE_COLUMN[side][0]
            try:
                df = pd.read_parquet(p, columns=["mlb_ID", "year_ID", "WAR", col])
            except Exception:
                log.warning("war_daily_exposure: unreadable %s cache at %s", side, p,
                            exc_info=True)
                return {}
            got = season_exposure_by_id(df, side)
            if got is None:
                log.warning("war_daily_exposure: the %s cache at %s has no %s column",
                            side, p, col)
                return {}
            sides[side] = got
            sides[side + "_war"] = _stint_war_by_id(df)
        _WAR_DAILY_EXPOSURE_MEMO.clear()
        _WAR_DAILY_EXPOSURE_MEMO.update({"stamp": stamp, "sides": sides})
    s = _WAR_DAILY_EXPOSURE_MEMO["sides"]
    out: dict[int, dict[int, dict[str, float]]] = {}
    for mid in {int(m) for m in mlbam_ids if m}:
        b, p = s["bat"].get(mid) or {}, s["pit"].get(mid) or {}
        bw, pw = s["bat_war"].get(mid) or {}, s["pit_war"].get(mid) or {}
        yrs = set(b) | set(p)
        if yrs:
            out[mid] = {yr: {"pa": int(round(b.get(yr, 0.0))), "ip": round(p.get(yr, 0.0), 2),
                             "war": round(bw.get(yr, 0.0) + pw.get(yr, 0.0), 2)}
                        for yr in sorted(yrs)}
    return out

def fetch_career_war_bulk(
    targets: list[tuple[str, int, bool]],
    start_year: int,
    end_year: int,
) -> dict[str, dict]:
    """Pull career WAR aggregates for the given (player_key, mlbam_id,
    is_pitcher) cohort. Returns one aggregate per player_key that found
    at least one MLB season in the window. Players with no MLB data
    are silently absent from the result (caller treats absence as "no
    MLB career on record").

    Backed by Baseball-Reference's WAR tables via pybaseball.bwar_bat /
    bwar_pitch — two static CSV downloads cached client-side, so the
    cost is ~5MB one-time even for a 944-player cohort. We tried the
    FanGraphs route first; FG's anti-scraping responses 403 on
    pybaseball's legacy endpoint as of 2025. BBRef WAR (rWAR) differs
    slightly in methodology but is the same shape: per-season WAR you
    can sum into a career total.

    Two-way players are handled by summing batting and pitching WAR for
    the same season; multi-team stints by summing all rows for a given
    (mlb_ID, year_ID).

    On any pybaseball/pandas import failure or HTTP error, returns an
    empty dict so the rest of the pipeline keeps running. The caller
    can fall back to the previous run's cached aggregate via
    storage.load_career_war().
    """
    if not targets:
        return {}
    try:
        import pybaseball  # noqa: F401 - availability probe; the fetch itself goes through war_source
    except ImportError:
        log.warning("pybaseball not installed; skipping career WAR fetch")
        return {}

    cohort_ids = {mid for _, mid, _ in targets if mid}
    if not cohort_ids:
        return {}

    # Pull the two BBRef WAR datasets in one shot each. `return_all=True`
    # surfaces the full multi-year frame; we filter by mlb_ID in-memory.
    # `.itertuples()` is roughly an order of magnitude faster than
    # `.iterrows()` for row-by-row pandas iteration. We only read three
    # columns per row, so the tuple-based access is fine.
    def _by_year(df, value_col="WAR"):
        """Return {mlb_ID: {year: war_total}} after summing stints."""
        out: dict[int, dict[int, float]] = {}
        if df is None or df.empty:
            return out
        # Filter to cohort + valid year + valid WAR before iteration.
        sub = df[df["mlb_ID"].isin(cohort_ids)]
        sub = sub[sub["year_ID"].between(start_year, end_year)]
        sub = sub[sub[value_col].notna()]
        for row in sub.itertuples(index=False):
            try:
                mid = int(getattr(row, "mlb_ID"))
                yr  = int(getattr(row, "year_ID"))
                war = float(getattr(row, value_col))
            except (TypeError, ValueError):
                continue
            yr_map = out.setdefault(mid, {})
            yr_map[yr] = yr_map.get(yr, 0.0) + war
        return out

    # bwar_bat + bwar_pitch are independent ~5 MB CSV downloads from
    # baseball-reference.com. Fetching them in parallel cuts the bWAR
    # refresh path roughly in half. The frames come through the war_source
    # facade (provider 'bwar' = the same pybaseball call this used to make
    # inline), so a future provider swap happens in ONE module.
    bat_by_id: dict[int, dict[int, float]] = {}
    pit_by_id: dict[int, dict[int, float]] = {}
    import concurrent.futures as _cf
    import war_source

    def _safe_fetch(side, label):
        try:
            return war_source.stint_frame(side)
        except Exception as e:
            log.warning("%s fetch failed: %s", label, e)
            return None

    with _cf.ThreadPoolExecutor(max_workers=2) as ex:
        f_bat = ex.submit(_safe_fetch, "bat", "bwar_bat")
        f_pit = ex.submit(_safe_fetch, "pit", "bwar_pitch")
        bat_df = f_bat.result()
        pit_df = f_pit.result()
    if bat_df is not None:
        bat_by_id = _by_year(bat_df)
    if pit_df is not None:
        pit_by_id = _by_year(pit_df)

    if not bat_by_id and not pit_by_id:
        return {}

    # Measured exposure on the same stints (see the section note above). None per
    # side = not measured, so that side's key is left off every aggregate.
    bat_exp = season_exposure_by_id(bat_df, "bat", cohort_ids, start_year, end_year)
    pit_exp = season_exposure_by_id(pit_df, "pit", cohort_ids, start_year, end_year)

    result: dict[str, dict] = {}
    for player_key, mid, _is_pitcher in targets:
        bat_yrs = bat_by_id.get(mid, {})
        pit_yrs = pit_by_id.get(mid, {})
        if not bat_yrs and not pit_yrs:
            continue
        seasons: dict[str, float] = {}
        all_years = set(bat_yrs) | set(pit_yrs)
        for yr in sorted(all_years):
            total = bat_yrs.get(yr, 0.0) + pit_yrs.get(yr, 0.0)
            seasons[str(yr)] = round(total, 2)
        career_war = round(sum(seasons.values()), 2)
        n = len(seasons)
        war_per_yr = round(career_war / n, 2) if n else 0.0
        result[player_key] = {
            "seasons": seasons,
            "career_war": career_war,
            "war_per_yr": war_per_yr,
            "war_seasons_count": n,
            "source": "bbref",
        }
        for field, by_id, innings in (("seasons_pa", bat_exp, False),
                                      ("seasons_ip", pit_exp, True)):
            got = _exposure_for_seasons(
                seasons, None if by_id is None else by_id.get(mid, {}), innings=innings)
            if got is not None:
                result[player_key][field] = got
    return result


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
        # v22 — Pass through k_pct / bb_pct on pitchers (was dropped to
        # None, which forced the UI to fall back to K/9 / BB/9 even
        # when the underlying career row had the per-batter rates).
        # The bulk season-stats fetcher writes k_pct/bb_pct/tbf into
        # the career row at fetch time; here we just thread them
        # through. As a fallback, when the row lacks k_pct but carries
        # the raw `so` + `tbf` (or `bf`) counts, derive on the fly so
        # legacy cached rows still surface the better metric.
        _kpct = _safe_float(chosen.get("k_pct"))
        _bbpct = _safe_float(chosen.get("bb_pct"))
        if _kpct is None or _bbpct is None:
            _tbf = chosen.get("tbf") or chosen.get("bf") or chosen.get("battersFaced")
            try:
                _tbf_i = int(_tbf) if _tbf else 0
            except (TypeError, ValueError):
                _tbf_i = 0
            if _tbf_i > 0:
                if _kpct is None:
                    _so = chosen.get("so") or chosen.get("strikeOuts") or chosen.get("k")
                    if _so is not None:
                        try:
                            _kpct = round(100 * int(_so) / _tbf_i, 1)
                        except (TypeError, ValueError, ZeroDivisionError):
                            pass
                if _bbpct is None:
                    _bb = chosen.get("bb") or chosen.get("baseOnBalls") or chosen.get("walks")
                    if _bb is not None:
                        try:
                            _bbpct = round(100 * int(_bb) / _tbf_i, 1)
                        except (TypeError, ValueError, ZeroDivisionError):
                            pass
        # v22 — Per-9 → per-batter approximation when TBF + so/bb counts
        # are both missing (the common case in MiLB-only career rows).
        # Uses the standard ~4.3 batters/inning league average: a 9 K/9
        # pitcher faces ~38.7 batters per 9, so K% ≈ K/9 ÷ 4.3 × 100/100
        # → K% ≈ K/9 × 100/38.7. Small marginal error vs direct K/TBF
        # (rate of opposite-side baserunners) but better than no value
        # at all. Tagged as approximate via the `_pct_approx` flag the
        # frontend can read to render with a small caveat tooltip.
        _kpct_approx = False
        _bbpct_approx = False
        _k9 = _safe_float(chosen.get("k_per_9"))
        _bb9 = _safe_float(chosen.get("bb_per_9"))
        BATTERS_PER_9 = 38.7
        if _kpct is None and _k9 is not None:
            _kpct = round(_k9 * 100 / BATTERS_PER_9, 1)
            _kpct_approx = True
        if _bbpct is None and _bb9 is not None:
            _bbpct = round(_bb9 * 100 / BATTERS_PER_9, 1)
            _bbpct_approx = True
        return StatLine(
            player_key=player_key, mlbam_id=mlbam_id,
            level=level, games=int(chosen.get("games", 0) or 0),
            avg=None, obp=None, slg=None, ops=None, hr=None, sb=None,
            bb_pct=_bbpct, k_pct=_kpct,
            era=str(chosen["era"]) if chosen.get("era") is not None else None,
            fip=None,
            ip=_safe_float(chosen.get("ip")),
            k_per_9=_safe_float(chosen.get("k_per_9")),
            bb_per_9=_safe_float(chosen.get("bb_per_9")),
            whip=_safe_float(chosen.get("whip")),
            hr_per_9=_safe_float(chosen.get("hr_per_9")),
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
        iso=_safe_float(chosen.get("iso")),
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
    # NB: no outer sleep here - the `requests` caching proxy is the single
    # rate limiter and only sleeps on its network path (cache misses).
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


def detect_debuts_from_index(
    career_stats: dict[str, list[dict]],
    active_players: list[tuple[str, str, bool]],
    player_index: "PlayerIndex | None" = None,
    id_cache: dict[str, int | None] | None = None,
    statlines: dict[str, "StatLine"] | dict[str, dict] | None = None,
) -> dict[str, str | None]:
    """
    Identify debuted prospects — players who should move from the active
    pool to the Debuted section.

    v21 rule (definitive): ANY active prospect whose MLB API record
    carries an `mlbDebutDate` is treated as debuted. Period. No AB/IP
    rookie-eligibility math. A player who pitched 1 inning of MLB ball
    is no longer a prospect; the same goes for a hitter with 0 ABs but
    an active-roster cup of coffee.

    Why we ripped out the 130-AB / 50-IP / 45-roster-day rookie
    thresholds: the multi-criterion gate was producing wrong "still
    active" classifications whenever any input was stale — the API
    cache, the career-stats cache, or the statline derivation. Players
    were sitting in the active pool with `mlb_debut_date` set, which
    confused readers. The user explicitly opted for the simpler signal:
    debut date is the source of truth.

    Args:
        career_stats : kept for API back-compat (no longer read in the
                       primary path — debut date alone gates).
        active_players: (player_key, player_name, is_pitcher_hint).
        player_index : `PlayerIndex` for MLB-API debut dates.
        id_cache     : optional MLBAM ID cache.
        statlines    : kept for back-compat (no longer read in the
                       primary path either).

    Returns:
        {player_key: debut_date_iso} for every active prospect whose
        MLB-API record has an mlbDebutDate; players without one are
        omitted from the result (still active).
    """
    if id_cache is None:
        id_cache = _load_id_cache()
    active_keys = {key for key, _, _ in active_players}

    debuts: dict[str, str | None] = {}
    if player_index is not None:
        for key in active_keys:
            mid = id_cache.get(key)
            if mid is None:
                continue
            debut = player_index.get_debut_date(mid)
            if debut:
                debuts[key] = debut
        log.info(
            "debut detection: %d/%d active prospects have an mlbDebutDate",
            len(debuts), len(active_keys),
        )

    # Fallback when no player_index supplied: any prospect with a
    # career MLB row at all (any AB/IP) is a debut signal. v21 — Use
    # the earliest MLB season's Opening Day ({season}-04-01) as the
    # debut-date approximation, NOT today(). Per user: debut date
    # should fall back to the first MLB game date, never to the
    # rebuild timestamp.
    if player_index is None:
        for key in active_keys:
            rows = career_stats.get(key) or []
            mlb_rows = [r for r in rows if r.get("level") == "MLB"]
            if mlb_rows:
                debuts[key] = f"{min(r['season'] for r in mlb_rows)}-04-01"
    return debuts


# Back-compat alias — callers that still import the old name keep
# working. New code should use `detect_debuts_from_index`.
detect_graduations_from_career = detect_debuts_from_index


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
# zero out the IL state. The optional position token may carry a digit
# ("activated 1B Tommy Hopfe"): with letters only, 1B/2B/3B returns never
# cleared and the stint stayed open for a season (2 of 22 stale rows,
# 2026-09-24).
_BARE_ACTIVATE_RE = _re.compile(
    r"\bactivated\s+(?:[A-Z0-9]{1,4}\s+)?[A-Z][A-Za-z]",
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


# Non-SC transactions that END an open IL stint. MiLB returns from the IL
# very often emit no activation row at all: the club simply reassigns the
# player ("assigned to Portland Sea Dogs from Greenville Drive") or lets him
# go. Walking SC rows alone left those stints open for months: on
# 2026-09-24 the served IL carried 436 rows, and 104 of them had a release,
# retirement or reassignment after the placement (all 50 reassignments to a
# non-complex club were followed by games in the MiLB game log). Rehab
# assignments are ASG rows too and are excluded by _REHAB_RE before this
# check.
_IL_EXIT_TYPE_CODES = frozenset({
    "REL",   # released
    "RET",   # retired
    "DFA",   # elected free agency
})


def _il_tx_type(tx: dict) -> str:
    """typeCode for a raw /transactions row or type_code for a normalized one."""
    return str(tx.get("typeCode") or tx.get("type_code") or "").upper()


def _il_tx_from_team(tx: dict) -> object:
    """The from-team id of an assignment, raw or normalized row shape."""
    ft = tx.get("fromTeam")
    if isinstance(ft, dict) and ft.get("id") is not None:
        return ft.get("id")
    return tx.get("from_team_id")


def _il_tx_seq(tx: dict) -> tuple[str, int]:
    """Chronological sort key for one transaction.

    The date is the LATER of `date` and `effectiveDate`. Late-entered MiLB
    placements carry a backdated `date` (the day the player joined the club)
    and the real placement day in `effectiveDate`: Zac Leigh reads date
    2026-06-26, effectiveDate 2026-07-30, and pitched through 07-28.
    Retroactive placements run the other way (effectiveDate is the earlier
    retro date, which the placement text also carries), so max() keeps them
    at their entry date. Ties on a date break on the transaction id, the
    order the transactions were entered, instead of the API list order.
    """
    d = str(tx.get("date") or "")
    e = str(tx.get("effectiveDate") or tx.get("effective_date") or "")
    try:
        tid = int(tx.get("id") or 0)
    except (TypeError, ValueError):
        tid = 0
    return (max(d, e), tid)


def _walk_il_stints(transactions: list[dict]) -> list[dict]:
    """Walk one player's transactions in order and return every IL stint as
    {since, until, type, reason, description, days, active}, oldest first.

    Accepts raw MLB Stats API rows (typeCode, fromTeam, effectiveDate, id)
    and the normalized player_transactions rows (type_code, from_team_id).

    A stint opens on an SC placement and closes on:
      * an SC activation ("activated ... from the 7-day injured list"),
      * a bare SC "<club> activated <pos> <player>" while a stint is open,
      * a later placement (the prior stint is closed at that date),
      * a release, retirement or free-agent election (_IL_EXIT_TYPE_CODES),
      * a non-rehab reassignment between clubs ("assigned to X from Y")
        entered after the last placement or transfer. A same-day
        reassignment counts only when both rows carry ids and the
        reassignment's id is the later one; normalized rows without ids
        need a strictly later date, so a player who joins a club and is
        placed the same day is not cleared by his own arrival.
    Rehab assignments neither open nor close a stint.
    """
    out: list[dict] = []
    open_stint: dict | None = None
    last_il_seq: tuple[str, int] = ("", 0)

    def _close(until: str) -> None:
        nonlocal open_stint
        if open_stint is None:
            return
        open_stint["until"] = until
        open_stint["active"] = False
        try:
            s = date.fromisoformat(open_stint["since"])
            e = date.fromisoformat(until)
            open_stint["days"] = (e - s).days
        except (TypeError, ValueError):
            pass
        out.append(open_stint)
        open_stint = None

    for tx in sorted(transactions or [], key=_il_tx_seq):
        seq = _il_tx_seq(tx)
        date_iso = seq[0]
        desc = (tx.get("description") or "").strip()
        if not desc or not date_iso:
            continue
        if _REHAB_RE.search(desc):
            # Rehab assignments leave the player on IL: neither open
            # nor close a stint.
            continue
        tcode = _il_tx_type(tx)
        if tcode != "SC":
            if open_stint is None:
                continue
            if tcode in _IL_EXIT_TYPE_CODES:
                _close(date_iso)
                continue
            if tcode == "ASG" and _il_tx_from_team(tx) is not None:
                later = seq[0] > last_il_seq[0] or (
                    seq[0] == last_il_seq[0] and seq[1] and last_il_seq[1]
                    and seq[1] > last_il_seq[1])
                if later:
                    _close(date_iso)
            continue
        if _IL_ACTIVATE_RE.search(desc):
            _close(date_iso)
            continue
        m_trans = _IL_TRANSFER_RE.search(desc)
        if m_trans:
            if open_stint is not None:
                open_stint["type"] = m_trans.group(1)
                if not open_stint.get("reason"):
                    open_stint["reason"] = _il_stint_reason(desc)
                open_stint["description"] = desc
                last_il_seq = seq
            continue
        m_place = _IL_PLACE_RE.search(desc)
        if m_place:
            # Close any prior open stint defensively (a missed activation
            # row would otherwise leave an old stint dangling forever).
            _close(date_iso)
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
            last_il_seq = seq
            continue
        # Fallback: bare "<team> activated <player>" while a stint is open.
        # MLB sometimes drops the "from the X-day IL" clause; Painter's
        # 2024-10-11 activation is the canonical example.
        if open_stint is not None and _BARE_ACTIVATE_RE.search(desc):
            _close(date_iso)
    if open_stint is not None:
        out.append(open_stint)
    return out


def _first_game_for_club_after(mlbam_id: int, club_id: object,
                               after_iso: str) -> str | None:
    """First MiLB game date later than `after_iso` that the player logged for
    `club_id`, across the seasons from after_iso's year to today's. None when
    there is none, the club is unknown, or the game log cannot be read (a
    fetch failure keeps the stint open rather than clearing it on no data).
    MLB games are not in the milb_all game log, and an MLB club always
    records its activations."""
    if club_id is None or not after_iso:
        return None
    try:
        first_season = int(after_iso[:4])
    except ValueError:
        return None
    for season in range(first_season, date.today().year + 1):
        for group in ("hitting", "pitching"):
            url = (f"{MLB_STATS_API}/people/{mlbam_id}/stats?stats=gameLog"
                   f"&group={group}&season={season}&leagueListId=milb_all")
            try:
                resp = requests.get(url, timeout=20, ttl=12 * 3600)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as e:
                log.debug("IL game-log fetch failed for %s: %s", mlbam_id, e)
                continue
            dates = sorted(
                str(s.get("date") or "")
                for st in (payload.get("stats") or [])
                for s in (st.get("splits") or [])
                if (s.get("team") or {}).get("id") == club_id
                and str(s.get("date") or "") > after_iso
            )
            if dates:
                return dates[0]
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

    Returns None when the player is not on IL. The stint walk and its close
    signals live in _walk_il_stints; a stint the walk leaves open is also
    closed when the game log shows the player back with the placing club.

    Cache TTL is 12h. IL refresh runs on the DAILY job (and is chained into the
    monthly run), so a 12h TTL means every nightly pass re-pulls the player's
    transactions and catches new placements within a day. (The prior 7-day TTL
    pre-dated the daily job and silently froze the IL section for up to a week —
    e.g. "no new placements since June 11" — even while the job ran.)
    """
    url = f"{MLB_STATS_API}/transactions?playerId={mlbam_id}"
    try:
        resp = requests.get(url, timeout=20, ttl=12 * 3600)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.debug("IL transactions fetch failed for %s: %s", mlbam_id, e)
        return None

    txs = data.get("transactions") or []
    stints = _walk_il_stints(txs)
    cur = stints[-1] if stints else None
    if not cur or not cur.get("active"):
        return None
    # A player who appears in a game for the club whose IL he is on has been
    # activated, whatever the transaction feed says. Rehab games are played
    # for a different affiliate, so they never trip this. Three open stints
    # on 2026-09-24 ended this way with no activation row: Tate Kuehner
    # (Nashville, placed 05-21, pitched for Nashville from 08-16), Christian
    # Becerra (Cedar Rapids, 06-11, from 07-01) and Brady Day (Jersey Shore,
    # 05-02, from 08-18 after a rehab).
    place = None
    for tx in sorted(txs, key=_il_tx_seq):
        if _il_tx_type(tx) == "SC" and _IL_PLACE_RE.search(tx.get("description") or ""):
            place = tx
    if place is not None:
        club = (place.get("toTeam") or {}).get("id")
        back = _first_game_for_club_after(mlbam_id, club, _il_tx_seq(place)[0])
        if back:
            return None
    return {
        "is_on_il":    True,
        "since":       cur.get("since"),
        "type":        cur.get("type"),
        "description": cur.get("description"),
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
    # Sport-id 16 = Rookie ball (US complex by default). Sport-id 17 is
    # primarily the DSL; 21 is also DSL on some seasons. Where the API
    # uses 16 for a DSL team, fetch_team_affiliations callers should
    # override using the league name — same trick the per-player path
    # uses to dodge the lumped-rookie ambiguity.
    16: "CPX",
    17: "DSL",
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
    # Include sport-ids 16 (US rookie/CPX) and 17 (DSL) so foreign-rookie
    # affiliates surface on farm pages with the correct level label
    # rather than being dropped from the affiliation map.
    sport_ids = (1, 11, 12, 13, 14, 16, 17)
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

    # Second pass: every team (MLB + affiliates) → metadata. We also peek
    # at the league name to bump rookie-bucket teams from the default CPX
    # into DSL when their league is the Dominican Summer League — the
    # MLB Stats API still buckets DSL clubs under sport-id 16 in some
    # season responses, so we can't rely on sport_id alone.
    for teams, sid in zip(results, sport_ids):
        default_level = _LEVEL_BY_SPORT_ID.get(sid)
        for t in teams:
            tid = int(t["id"])
            parent_id = t.get("parentOrgId")
            league_name = ((t.get("league") or {}).get("name") or "").lower()
            team_name = (t.get("name") or "")
            if _is_exhibition_team(team_name) or _is_exhibition_team(league_name):
                continue
            level = default_level
            if level == "CPX":
                if "dominican" in league_name:
                    level = "DSL"
                elif "complex" not in league_name:
                    # Point-in-time level: pre-2021-reorg the US rookie circuits
                    # (AZL / GCL, Pioneer, Appalachian) were "Rookie" (Rk), not
                    # the post-reorg "Complex" (CPX). The season-aware league name
                    # carries the era ("Arizona League" 2019 -> "Arizona Complex
                    # League" 2021), so a sport-16 league whose name lacks
                    # "complex" is the pre-reorg Rookie level.
                    level = "Rk"
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
