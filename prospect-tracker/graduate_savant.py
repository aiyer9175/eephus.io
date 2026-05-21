"""Statcast pitch-by-pitch scraper for graduates, plus the zone-classifier
and swing-rate aggregator that feed the swing-zone heatmap on the
graduate detail page.

The endpoint is Baseball Savant's CSV download URL, parameterized by
batter MLBAM id + season. One CSV per (player, year) covers every pitch
the batter saw that season. We keep only the eight columns needed for
zone classification + swing/no-swing labeling, then compress to a
13-element heat array (3x3 inner zone + 4 chase wedges) that drops
directly into the existing `makeStrikeZoneHeatmap` renderer.

Cache: on-disk under `.cache/savant_pitches_<id>_<year>.csv`.
"""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import date
from pathlib import Path

import requests

from scrapers import CACHE_DIR, HEADERS, RATE_LIMIT_SECONDS

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Plate is 17 in wide ≈ 1.417 ft -> half-width ≈ 0.708 ft. Pitches with
# |plate_x| > this are off the plate horizontally.
ZONE_HALF_WIDTH_FT = 17 / 12 / 2

# Statcast "description" values that count as the batter swinging.
_SWING_DESCRIPTIONS = frozenset({
    "hit_into_play",
    "swinging_strike",
    "swinging_strike_blocked",
    "foul",
    "foul_tip",
    "foul_bunt",
    "missed_bunt",
})

# Endpoint template. Regular-season only (hfGT=R%7C), single player lookup.
_SAVANT_CSV_URL = (
    "https://baseballsavant.mlb.com/statcast_search/csv"
    "?all=true"
    "&hfGT=R%7C"
    "&hfSea={year}%7C"
    "&player_type=batter"
    "&batters_lookup%5B%5D={mlbam_id}"
    "&min_pitches=0&min_results=0"
    "&group_by=name"
    "&sort_col=pitches"
    "&type=details"
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _safe_float(v):
    if v is None or v == "" or v == "null":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _classify_zone(plate_x, plate_z, sz_top, sz_bot):
    """Map a single pitch into a 13-bin zone:
      0-8  = inner 3x3 (catcher view, top-left = 0)
      9    = above the zone (chase)
      10   = below the zone (chase)
      11   = left of the zone (chase)
      12   = right of the zone (chase)
    Returns None for missing coords or invalid bounds.
    """
    if plate_x is None or plate_z is None or sz_top is None or sz_bot is None:
        return None
    if sz_top <= sz_bot:
        return None
    inside_x = abs(plate_x) <= ZONE_HALF_WIDTH_FT
    inside_z = sz_bot <= plate_z <= sz_top
    if inside_x and inside_z:
        third = ZONE_HALF_WIDTH_FT / 3
        col = 0 if plate_x < -third else (2 if plate_x > third else 1)
        zone_h = sz_top - sz_bot
        row = 0 if plate_z > sz_top - zone_h / 3 else (2 if plate_z < sz_bot + zone_h / 3 else 1)
        return row * 3 + col
    if plate_z > sz_top:
        return 9
    if plate_z < sz_bot:
        return 10
    if plate_x < -ZONE_HALF_WIDTH_FT:
        return 11
    if plate_x > ZONE_HALF_WIDTH_FT:
        return 12
    return None


def compute_swing_zone_heat(pitches, min_pitches_per_zone: int = 10):
    """Aggregate a list of pitch dicts into a 13-element swing-rate array.
    Zones with fewer than ``min_pitches_per_zone`` samples emit None so
    the renderer can grey them out instead of reading a single chase
    pitch as 100%.
    """
    swings = [0] * 13
    totals = [0] * 13
    for p in pitches:
        z = _classify_zone(p.get("plate_x"), p.get("plate_z"),
                           p.get("sz_top"), p.get("sz_bot"))
        if z is None:
            continue
        totals[z] += 1
        if p.get("description") in _SWING_DESCRIPTIONS:
            swings[z] += 1
    return [
        round(swings[i] / totals[i], 3) if totals[i] >= min_pitches_per_zone else None
        for i in range(13)
    ]


# ---------------------------------------------------------------------------
# HTTP scrape (cached on disk)
# ---------------------------------------------------------------------------

def scrape_savant_pitches(mlbam_id: int, year: int,
                          force: bool = False) -> list[dict]:
    """Fetch one batter-season worth of pitch-by-pitch data from Savant.

    Returns a list of dicts with the eight columns the heatmap needs.
    Empty list on any fetch / parse failure. Cached on disk per
    (player, year) pair.
    """
    cache_key = f"savant_pitches_{mlbam_id}_{year}"
    cache_path = CACHE_DIR / f"{cache_key}.csv"
    if cache_path.exists() and not force:
        body = cache_path.read_text(encoding="utf-8")
        log.info("cache hit: %s (%d bytes)", cache_key, len(body))
    else:
        url = _SAVANT_CSV_URL.format(year=year, mlbam_id=mlbam_id)
        log.info("fetching savant pitches: %s", url)
        time.sleep(RATE_LIMIT_SECONDS)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
        except requests.RequestException as e:
            log.warning("network error fetching savant for %s/%s: %s",
                        mlbam_id, year, e)
            return []
        if resp.status_code != 200:
            log.warning("savant non-200 for %s/%s: HTTP %d",
                        mlbam_id, year, resp.status_code)
            return []
        body = resp.text
        cache_path.write_text(body, encoding="utf-8")

    if not body or not body.strip():
        return []
    rows = []
    try:
        reader = csv.DictReader(io.StringIO(body))
        for r in reader:
            rows.append({
                "plate_x":     _safe_float(r.get("plate_x")),
                "plate_z":     _safe_float(r.get("plate_z")),
                "sz_top":      _safe_float(r.get("sz_top")),
                "sz_bot":      _safe_float(r.get("sz_bot")),
                "description": r.get("description") or "",
                "pitch_type":  r.get("pitch_type") or "",
                "type":        r.get("type") or "",
                "game_date":   r.get("game_date") or "",
            })
    except Exception:
        log.exception("savant CSV parse failed for %s/%s", mlbam_id, year)
        return []
    return rows


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def build_graduate_swing_zone_heat(graduates, max_seasons: int = 3,
                                   force: bool = False) -> dict:
    """For each graduate with an mlbam_id, walk their MLB seasons in
    ``career_war.seasons`` (most recent ``max_seasons``), scrape and
    aggregate pitches, return ``{player_key: heat_array}``.

    Graduates without an mlbam_id, or with no MLB seasons in the
    requested window, are skipped.
    """
    out: dict = {}
    today = date.today()
    for g in graduates:
        mlbam = g.get("mlbam_id")
        key = g.get("player_key")
        if not mlbam or not key:
            continue
        seasons_map = ((g.get("career_war") or {}).get("seasons") or {})
        try:
            seasons = sorted(
                (int(y) for y in seasons_map
                 if int(y) >= today.year - max_seasons),
                reverse=True,
            )[:max_seasons]
        except (TypeError, ValueError):
            seasons = []
        if not seasons:
            continue
        all_pitches: list[dict] = []
        for yr in seasons:
            all_pitches.extend(scrape_savant_pitches(mlbam, yr, force=force))
        heat = compute_swing_zone_heat(all_pitches)
        if any(v is not None for v in heat):
            out[key] = heat
    log.info("graduate_savant: %d graduates with swing zone heat", len(out))
    return out
