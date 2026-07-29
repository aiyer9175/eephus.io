# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
mlbam_ingest.py — MLBAM-ID-anchored prospect discovery.

The existing pipeline only tracks players who appear in scouting publications
(FanGraphs, ESPN, etc.).  Players who are producing in affiliated ball but
haven't been formally ranked — like Franklin Primera, who had a $10k IFA bonus
and no prior pedigree but is now raking — never enter the DB until a source
publishes a grade.

This module implements the user's insight: anchor on MLBAM ID existence
(i.e., the player is registered with MLB and playing affiliated ball) rather
than waiting for a scouting publication.  A month of elite production can
completely change a prospect's outlook, so we want real-time ingestion.

Flow:
  1. For each qualifying MiLB level (A, A+, AA, AAA), fetch current-season
     batting/pitching leaders from the MLB Stats API with a minimum sample.
  2. Resolve each MLBAM ID against the players table (by mlbam_id or name).
  3. For any player who meets the qualifier threshold and is NOT yet in our DB,
     call storage.upsert_unranked_active_player() with:
       - provisional_fv = 35 (below-threshold; strong performance moves it)
       - source_label   = 'performance_ingest' (a SYNTHETIC constant, not a
         grade: grade_normalization._SYNTHETIC_SOURCES passes it through raw
         and never quantile-maps it. NOTE it is NOT excluded from consensus:
         data/source_weights.json is {} so it votes at 1.0 like any outlet,
         and for a player no publication has ever graded it IS the whole
         consensus. See .cache/anchor_probe/PATCH_consensus_synthetic_anchor.md)
  4. Return a count of new entries so the pipeline can log what was added.
  5. refresh_performance_anchors() re-dates the anchors of players discovered
     on an earlier run who still qualify, so the stamp cannot freeze.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

log = logging.getLogger(__name__)

# MLB Stats API sport IDs for affiliated levels
_SPORT_IDS: dict[str, int] = {
    "AAA": 11,
    "AA":  12,
    "A+":  13,
    "A":   14,
    "CPX": 16,   # FCL / ACL / DSL complex leagues
}

# Minimum sample before a player is ingested (avoids cup-of-coffee entries)
_MIN_PA = 40     # hitters
_MIN_IP = 15.0   # pitchers (approx 5 starts or 15 relief appearances)

# Position-group maps for the MLB Stats API
_PITCHER_POSITIONS = {"P", "SP", "RP", "RHP", "LHP"}


def _api_get(url: str, params: dict | None = None, timeout: int = 15) -> dict | None:
    """Simple HTTP GET with retry for the MLB Stats API."""
    import urllib.request, urllib.parse, json as _json
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return _json.loads(r.read())
        except Exception as exc:
            log.warning("mlbam_ingest: API error (attempt %d/3): %s %s", attempt + 1, url, exc)
            time.sleep(1.5 * (attempt + 1))
    return None


def _load_existing_mlbam_ids() -> set[int]:
    """Return the set of mlbam_ids already known to the pipeline.

    MLBAM IDs are stored in player_photos (the canonical mlbam_id↔player_key
    table) rather than in the players table itself.
    """
    from storage import connect
    with connect() as con:
        rows = con.execute(
            "SELECT mlbam_id FROM player_photos WHERE mlbam_id IS NOT NULL"
        ).fetchall()
    return {int(r[0]) for r in rows}


def _existing_player_keys() -> set[str]:
    """Return all player_keys already in the DB."""
    from storage import connect
    with connect() as con:
        rows = con.execute("SELECT player_key FROM players").fetchall()
    return {r[0] for r in rows}


def _canonical_key(name: str) -> str:
    """Convert a player name to the canonical DB key used by the pipeline."""
    try:
        from scrapers import normalize_key
        return normalize_key(name)
    except Exception:
        import re, unicodedata
        s = unicodedata.normalize("NFKD", name)
        s = "".join(c for c in s if not unicodedata.combining(c))
        s = s.lower().strip()
        s = re.sub(r"[^a-z0-9\s]", "", s)
        return re.sub(r"\s+", "_", s)


def _durable_key_to_mlbam() -> dict[str, int]:
    """{player_key: mlbam_id} from player_photos — the durable binding used
    to detect name-slug collisions between distinct MLBAM identities."""
    out: dict[str, int] = {}
    try:
        from storage import load_mlbam_player_keys
        for mid, key in load_mlbam_player_keys().items():
            try:
                out[key] = int(mid)
            except (TypeError, ValueError):
                continue
    except Exception as exc:
        log.debug("mlbam_ingest: durable key map unavailable: %s", exc)
    return out


def _collision_safe_key(key: str, mlbam_id: int,
                        durable_by_key: dict[str, int]) -> str:
    """Return the key this MLBAM identity's rows should live under.

    Two different humans can share a name slug (the 2026 DSL Giants signee
    Jose Valdez, mlbam 838649, collides with the retired Tigers RHP Jose A.
    Valdez — both -> "jose_a_valdez"). Known splits come from
    scrapers._SPLIT_KEYS; beyond those, fork a discriminated key whenever
    the slug is already durably bound (player_photos) to a DIFFERENT mlbam,
    so the newcomer is ingested as his own record instead of being silently
    skipped or merged onto the incumbent."""
    try:
        from scrapers import split_key_for_mlbam
        split = split_key_for_mlbam(key, mlbam_id)
        if split:
            return split
    except Exception:
        pass
    durable = durable_by_key.get(key)
    if durable is not None and int(mlbam_id) != durable:
        forked = f"{key}_{mlbam_id}"
        log.warning(
            "mlbam_ingest: name-slug collision — %r is durably bound to "
            "mlbam %s; ingesting id %s under %r",
            key, durable, mlbam_id, forked,
        )
        return forked
    return key


def _fetch_stat_leaders(sport_id: int, group: str, season: int,
                        min_pa_ip: float) -> list[dict]:
    """Fetch per-player stats from the MLB Stats API for a given sport / group.

    Returns a list of dicts with keys:
      mlbam_id, player_name, position, team_abbr, birth_date, pa_or_ip
    """
    url    = "https://statsapi.mlb.com/api/v1/stats"
    params = {
        "stats":       "season",
        "season":      season,
        "sportId":     sport_id,
        "group":       group,   # "hitting" or "pitching"
        "sortStat":    "plateAppearances" if group == "hitting" else "inningsPitched",
        "order":       "desc",
        "limit":       500,
        "hydrate":     "person(birthDate),currentTeam",
    }
    data = _api_get(url, params)
    if not data:
        return []

    results = []
    for split in (data.get("stats") or []):
        for entry in (split.get("splits") or []):
            # The stats endpoint uses "player" key (not "person")
            person = entry.get("player") or entry.get("person") or {}
            team   = entry.get("team") or {}
            stat   = entry.get("stat") or {}
            pos_obj = entry.get("position") or {}
            pid    = person.get("id")
            name   = person.get("fullName") or ""
            pos    = pos_obj.get("abbreviation") or pos_obj.get("code") or ""
            bdate  = person.get("birthDate") or ""
            # CPX/DSL teams don't have an abbreviation — use full name for org resolution
            abbr   = team.get("abbreviation") or team.get("name") or ""

            if not pid or not name:
                continue

            if group == "hitting":
                sample = float(stat.get("plateAppearances") or 0)
            else:
                ip_str = stat.get("inningsPitched") or "0.0"
                try:
                    ip_parts = str(ip_str).split(".")
                    sample = int(ip_parts[0]) + int(ip_parts[1] if len(ip_parts) > 1 else 0) / 3.0
                except (ValueError, IndexError):
                    sample = float(ip_str or 0)

            if sample < min_pa_ip:
                continue

            results.append({
                "mlbam_id":    int(pid),
                "player_name": name,
                "position":    pos,
                "team_abbr":   abbr,
                "team_id":     team.get("id"),
                "birth_date":  bdate[:10] if bdate else None,
                "sample":      sample,
            })
    return results


# --- affiliate -> parent org, from the API instead of a 3-letter guess -------
# _abbr_to_org's last resort is `clean[:3]`, which turns an affiliate name into
# a fake org code: Erie -> "ERI", Reading -> "REA", Wilmington -> "WIL". Measured
# 2026-07-25: 1,360 of the 2,575 auto-tracked players carried an affiliate string
# in players.org instead of an MLB org. StatsAPI publishes the real mapping
# (`parentOrgName` on every one of the 201 affiliate teams, verified live
# HTTP 200), so resolve by team_id first and keep the keyword table as fallback.
_PARENT_ORG_CACHE: dict[int, str] = {}


def _parent_org_by_team_id(season: int) -> dict[int, str]:
    """{affiliate team_id: canonical MLB org code} for every MiLB affiliate."""
    global _PARENT_ORG_CACHE
    if _PARENT_ORG_CACHE:
        return _PARENT_ORG_CACHE
    sport_ids = ",".join(str(v) for v in _SPORT_IDS.values())
    data = _api_get("https://statsapi.mlb.com/api/v1/teams",
                    {"sportIds": sport_ids, "season": season,
                     "fields": "teams,id,parentOrgName,parentOrgId"})
    if not data:
        return {}
    try:
        from trades import canonical_org
    except ImportError:
        canonical_org = lambda t: t  # noqa: E731
    out: dict[int, str] = {}
    for t in (data.get("teams") or []):
        tid, parent = t.get("id"), t.get("parentOrgName")
        if not tid or not parent:
            continue
        code = canonical_org(parent)
        if code:
            out[int(tid)] = code
    _PARENT_ORG_CACHE = out
    log.info("mlbam_ingest: resolved %d affiliate -> parent org mappings", len(out))
    return out


def _org_for_entry(entry: dict, season: int) -> str:
    """Parent MLB org for one leaders row. API mapping first, keyword fallback."""
    tid = entry.get("team_id")
    if tid:
        org = _parent_org_by_team_id(season).get(int(tid))
        if org:
            return org
    return _abbr_to_org(entry.get("team_abbr") or "")


def _abbr_to_org(abbr: str) -> str:
    """Team abbreviation or affiliate name → eephus 3-letter org code.

    The MLB Stats API returns affiliate team names for CPX/DSL levels
    (e.g. "FCL Red Sox", "DSL Cardinals Red") rather than MLB org codes.
    This function maps both forms to the canonical org code.
    """
    s = abbr.upper().strip()
    # Direct 3-letter remap
    _DIRECT = {
        "WSH": "WSN", "CHW": "CWS", "KCA": "KCR", "SDP": "SDP",
        "SFG": "SFG", "OAK": "ATH",
    }
    if s in _DIRECT:
        return _DIRECT[s]
    # Affiliate name → org (complex leagues return full team name)
    _AFFILIATE = {
        "RED SOX": "BOS", "YANKEES": "NYY", "METS": "NYM", "CUBS": "CHC",
        "CARDINALS": "STL", "BREWERS": "MIL", "REDS": "CIN", "PIRATES": "PIT",
        "PHILLIES": "PHI", "BRAVES": "ATL", "MARLINS": "MIA", "NATIONALS": "WSN",
        "PADRES": "SDP", "GIANTS": "SFG", "DODGERS": "LAD", "ROCKIES": "COL",
        "DIAMONDBACKS": "ARI", "ATHLETICS": "ATH", "ASTROS": "HOU",
        "RANGERS": "TEX", "ANGELS": "LAA", "MARINERS": "SEA", "ATHLETICS": "ATH",
        "TWINS": "MIN", "WHITE SOX": "CWS", "TIGERS": "DET", "GUARDIANS": "CLE",
        "ROYALS": "KCR", "RAYS": "TBR", "BLUE JAYS": "TOR", "ORIOLES": "BAL",
        "BLUE JAYS": "TOR",
    }
    # Strip "FCL ", "ACL ", "DSL " prefix and try keyword match
    clean = s.replace("FCL ", "").replace("ACL ", "").replace("DSL ", "").strip()
    # Try multi-word match first (e.g. "RED SOX", "WHITE SOX", "BLUE JAYS")
    for keyword, org in _AFFILIATE.items():
        if keyword in clean:
            return org
    # Single-word match for simple cases
    for keyword, org in _AFFILIATE.items():
        if clean.startswith(keyword.split()[0]):
            return org
    # Fall back to first 3 letters of the cleaned name
    return clean[:3] if len(clean) >= 3 else abbr[:3].upper()


def _synthetic_only_keys() -> set[str]:
    """player_keys whose ONLY explicit-FV snapshot source is the synthetic
    performance_ingest stamp (i.e. no publication has ever graded them).

    Only these may be re-stamped by the refresh pass. A player who has a real
    anchor must NOT get a freshened synthetic vote: the real source's own
    cadence (and its staleness) is the honest signal there."""
    from storage import connect
    with connect() as con:
        rows = con.execute(
            """SELECT player_key,
                      SUM(CASE WHEN source = 'performance_ingest' THEN 1 ELSE 0 END) AS synth,
                      SUM(CASE WHEN source NOT IN ('performance_ingest', 'draft_signing',
                                                   'auto_detect') THEN 1 ELSE 0 END)  AS real
                 FROM snapshots
                WHERE fv IS NOT NULL
             GROUP BY player_key"""
        ).fetchall()
    return {r[0] for r in rows if r[1] and not r[2]}


def refresh_performance_anchors(season: int | None = None,
                                *,
                                levels: list[str] | None = None,
                                min_pa: int = _MIN_PA,
                                min_ip: float = _MIN_IP,
                                as_of: str | None = None,
                                dry_run: bool = False) -> dict[str, int]:
    """Re-date the performance_ingest anchor of ALREADY-tracked players who
    still qualify this season.

    ROOT CAUSE this closes: `ingest_unranked_active_prospects` skips every
    player already in the DB (`if pid in known_ids or key in known_keys:
    continue`), so `upsert_unranked_active_player` is only ever called on the
    run that FIRST discovers a player. Combined with the old
    `snap_date = f"{season}-01-01"`, an auto-tracked player's anchor date was
    written exactly once and never moved again. Measured 2026-07-25: all
    2,760 performance_ingest rows sat at snapshot_date 2026-01-01, min == max.

    Why the date matters: efv_dataset._stale_anchor_discount decays the model
    anchor of any row whose as-of date is > 18 months old, to a terminal of
    -10 FV at 30 months. A permanently frozen 2026-01-01 stamp therefore drags
    the entire auto-tracked cohort from FV 35 to FV 25 starting 2027-07 and
    fully by 2028-07, describing a "dropped off the lists" event that never
    happened.

    The refresh re-asserts the claim the stamp actually encodes ("this player
    is registered and producing at a qualifying level") only while it is still
    TRUE: a player who stops appearing in the qualifying leaders stops being
    re-stamped and correctly decays. It never creates a player and never
    touches a player who has a real published anchor.
    """
    from storage import upsert_unranked_active_player

    season = season or date.today().year
    levels = levels or list(_SPORT_IDS.keys())
    eligible = _synthetic_only_keys()
    key_by_mlbam = {v: k for k, v in _durable_key_to_mlbam().items()}
    stamp = as_of or date.today().isoformat()

    out = {"qualified": 0, "refreshed": 0, "skipped_real_anchor": 0,
           "skipped_untracked": 0}
    seen: set[str] = set()          # a player promoted mid-season qualifies at
                                    # two levels; count him once
    for level in levels:
        sport_id = _SPORT_IDS.get(level)
        if not sport_id:
            continue
        for group, floor in (("hitting", min_pa), ("pitching", min_ip)):
            for entry in _fetch_stat_leaders(sport_id, group, season, floor):
                out["qualified"] += 1
                key = key_by_mlbam.get(entry["mlbam_id"])
                if not key:
                    out["skipped_untracked"] += 1
                    continue
                if key not in eligible:
                    out["skipped_real_anchor"] += 1
                    continue
                if key in seen:
                    continue
                seen.add(key)
                if not dry_run:
                    upsert_unranked_active_player(
                        player_key   = key,
                        player_name  = entry["player_name"],
                        position     = entry["position"],
                        org          = _org_for_entry(entry, season),
                        birth_date   = entry["birth_date"],
                        mlbam_id     = entry["mlbam_id"],
                        season       = season,
                        provisional_fv = 35.0,
                        source_label = "performance_ingest",
                        as_of        = stamp,
                    )
                out["refreshed"] += 1
    log.info("mlbam_ingest.refresh_performance_anchors(%s): %s", season, out)
    return out


def ingest_unranked_active_prospects(
    season: int | None = None,
    *,
    levels: list[str] | None = None,
    min_pa: int = _MIN_PA,
    min_ip: float = _MIN_IP,
    dry_run: bool = False,
) -> dict[str, int]:
    """Discover and ingest qualifying unranked active prospects via MLBAM ID.

    For each MiLB level, fetches current-season stat leaders and creates
    provisional player records for anyone who:
      - Has a qualifying sample (min_pa PA or min_ip IP)
      - Is NOT already in our players table (by MLBAM ID or name-key)

    Returns a summary dict: {level: new_player_count, ...}
    """
    from storage import upsert_unranked_active_player

    season    = season or date.today().year
    levels    = levels or list(_SPORT_IDS.keys())
    known_ids = _load_existing_mlbam_ids()
    known_keys = _existing_player_keys()
    durable_by_key = _durable_key_to_mlbam()
    summary: dict[str, int] = {}

    for level in levels:
        sport_id = _SPORT_IDS.get(level)
        if not sport_id:
            log.warning("mlbam_ingest: unknown level %s — skipping", level)
            continue

        new_count = 0
        for group, sample_floor in [("hitting", min_pa), ("pitching", min_ip)]:
            leaders = _fetch_stat_leaders(sport_id, group, season, sample_floor)
            log.info("mlbam_ingest [%s %s]: %d qualified players from API",
                     level, group, len(leaders))

            for entry in leaders:
                pid  = entry["mlbam_id"]
                name = entry["player_name"]
                # Slug-collision guard: a NEW mlbam whose name-slug collides
                # with an already-tracked DIFFERENT player gets a
                # discriminated key instead of being skipped (or merged).
                key  = _collision_safe_key(_canonical_key(name), pid,
                                           durable_by_key)

                if pid in known_ids or key in known_keys:
                    continue  # already tracked

                org = _org_for_entry(entry, season)
                pos = entry["position"]
                bdate = entry["birth_date"]

                log.info("mlbam_ingest: NEW prospect [%s] %s (%s %s MLBAMID=%d sample=%.0f)",
                         level, name, pos, org, pid, entry["sample"])

                if not dry_run:
                    created = upsert_unranked_active_player(
                        player_key    = key,
                        player_name   = name,
                        position      = pos,
                        org           = org,
                        birth_date    = bdate,
                        mlbam_id      = pid,
                        season        = season,
                        provisional_fv = 35.0,
                        source_label  = "performance_ingest",
                    )
                    if created:
                        new_count += 1
                        known_ids.add(pid)
                        known_keys.add(key)
                else:
                    new_count += 1

        summary[level] = new_count
        log.info("mlbam_ingest [%s]: %d new prospects ingested", level, new_count)

    return summary


if __name__ == "__main__":
    import argparse, json, sys
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    ap = argparse.ArgumentParser(description="Ingest unranked active prospects via MLBAM ID")
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--levels", nargs="*", default=None)
    ap.add_argument("--min-pa",  type=int,   default=_MIN_PA)
    ap.add_argument("--min-ip",  type=float, default=_MIN_IP)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    result = ingest_unranked_active_prospects(
        season=args.season, levels=args.levels,
        min_pa=args.min_pa, min_ip=args.min_ip, dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))
