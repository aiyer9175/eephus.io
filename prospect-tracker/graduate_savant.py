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
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import requests

from scrapers import CACHE_DIR, HEADERS, RATE_LIMIT_SECONDS

log = logging.getLogger(__name__)

# Bulk-fetch concurrency. The Savant CSV endpoint accepts MULTIPLE
# `batters_lookup[]=ID` params in a single request; one HTTP round-trip
# returns every pitch every listed batter saw that season. That collapses
# what was ~150 (graduate × year) requests down to ~3 (one per season)
# at the cost of a single ~10-30 MB response per call.
_BULK_BATTERS_PER_REQUEST = 50   # cap so URLs don't blow past Savant's limit
_BULK_MAX_WORKERS = 4            # parallelism across year-level batches
_FETCH_LOCK = threading.Lock()
_BULK_RATE_LIMIT_SECONDS = 0.25  # per-request sleep; small batches go fast


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

def _build_bulk_url(mlbam_ids: list[int], year: int) -> str:
    """Construct a bulk Savant CSV URL with multiple batter IDs."""
    base = (
        "https://baseballsavant.mlb.com/statcast_search/csv"
        "?all=true"
        "&hfGT=R%7C"
        f"&hfSea={year}%7C"
        "&player_type=batter"
    )
    batter_params = "".join(f"&batters_lookup%5B%5D={mid}" for mid in mlbam_ids)
    tail = (
        "&min_pitches=0&min_results=0"
        "&group_by=name"
        "&sort_col=pitches"
        "&type=details"
    )
    return base + batter_params + tail


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

    Thread-safe via `_FETCH_LOCK` around the rate-limit sleep so the
    parallel orchestrator can call this from multiple workers without
    bursting Savant.
    """
    cache_key = f"savant_pitches_{mlbam_id}_{year}"
    cache_path = CACHE_DIR / f"{cache_key}.csv"
    if cache_path.exists() and not force:
        body = cache_path.read_text(encoding="utf-8")
        log.debug("cache hit: %s (%d bytes)", cache_key, len(body))
    else:
        url = _SAVANT_CSV_URL.format(year=year, mlbam_id=mlbam_id)
        log.info("fetching savant pitches: %s", url)
        with _FETCH_LOCK:
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

def _scrape_savant_pitches_bulk(mlbam_ids: list[int], year: int,
                                force: bool = False) -> dict[int, list[dict]]:
    """Fetch one bulk CSV containing every pitch every listed batter saw
    in ``year``. Returns ``{mlbam_id: [pitch_dicts]}``.

    Per-(batter, year) cache files are written so subsequent runs can
    pre-fill from disk and skip any batter whose CSV already lives in
    the cache. The bulk request only goes out for the batters not yet
    cached, so warm runs are essentially instant.

    On any fetch / parse failure for the bulk request, every UNCACHED
    batter for that year gets an empty list — graceful degradation.
    """
    out: dict[int, list[dict]] = {}

    # Pre-fill from per-batter cache files; bulk-fetch only the misses.
    to_fetch: list[int] = []
    for mid in mlbam_ids:
        cache_path = CACHE_DIR / f"savant_pitches_{mid}_{year}.csv"
        if cache_path.exists() and not force:
            body = cache_path.read_text(encoding="utf-8")
            out[mid] = _parse_savant_csv(body)
        else:
            to_fetch.append(mid)

    if not to_fetch:
        return out

    url = _build_bulk_url(to_fetch, year)
    log.info("savant bulk fetch: %d batters · year %d · URL len %d",
             len(to_fetch), year, len(url))
    with _FETCH_LOCK:
        time.sleep(_BULK_RATE_LIMIT_SECONDS)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=180)
    except requests.RequestException as e:
        log.warning("savant bulk fetch network error for year %d: %s", year, e)
        for mid in to_fetch:
            out[mid] = []
        return out
    if resp.status_code != 200:
        log.warning("savant bulk fetch non-200 for year %d: HTTP %d",
                    year, resp.status_code)
        for mid in to_fetch:
            out[mid] = []
        return out

    # Parse the combined CSV once, then split by batter.
    body = resp.text
    rows_by_batter: dict[int, list[str]] = {mid: [] for mid in to_fetch}
    header = ""
    try:
        reader = csv.DictReader(io.StringIO(body))
        header_fields = reader.fieldnames or []
        header = ",".join(header_fields)
        # Find the batter-id column. Savant uses "batter" as the ID col.
        bid_col = "batter"
        if bid_col not in header_fields:
            log.warning("savant bulk: 'batter' column missing in CSV; got %s",
                        header_fields[:8])
            for mid in to_fetch:
                out[mid] = []
            return out
        for r in reader:
            try:
                bid = int(r.get(bid_col) or 0)
            except (TypeError, ValueError):
                continue
            if bid in rows_by_batter:
                # Re-serialize the dict row back to CSV for caching.
                # Keeping the original line text would be cheaper, but
                # DictReader doesn't expose it. Build minimal CSV per
                # cache so the disk cache stays per-batter usable.
                rows_by_batter[bid].append(_row_dict_to_csv_line(r, header_fields))
                # Also accumulate the parsed pitch dict into the output.
                out.setdefault(bid, []).append({
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
        log.exception("savant bulk CSV parse failed for year %d", year)
        for mid in to_fetch:
            out.setdefault(mid, [])
        return out

    # Persist per-batter cache so warm runs hit disk for individual
    # players (and so `scrape_savant_pitches` still works in single-
    # player mode).
    for mid in to_fetch:
        cache_path = CACHE_DIR / f"savant_pitches_{mid}_{year}.csv"
        body_out = header + "\n" + "\n".join(rows_by_batter.get(mid, []))
        try:
            cache_path.write_text(body_out, encoding="utf-8")
        except Exception:
            log.exception("failed to write savant cache for %s/%s", mid, year)
        out.setdefault(mid, [])
    return out


def _row_dict_to_csv_line(r: dict, fields: list[str]) -> str:
    """Re-serialize a DictReader row back to a CSV line for caching.
    Values containing commas or quotes get wrapped + escaped per RFC 4180."""
    parts = []
    for f in fields:
        v = "" if r.get(f) is None else str(r.get(f))
        if "," in v or '"' in v or "\n" in v:
            v = '"' + v.replace('"', '""') + '"'
        parts.append(v)
    return ",".join(parts)


def _parse_savant_csv(body: str) -> list[dict]:
    """Parse the project's per-batter CSV cache into pitch dicts."""
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
        log.exception("savant CSV parse failed")
        return []
    return rows


def build_graduate_swing_zone_heat(graduates, max_seasons: int = 3,
                                   force: bool = False,
                                   max_workers: int = _BULK_MAX_WORKERS,
                                   batters_per_request: int = _BULK_BATTERS_PER_REQUEST) -> dict:
    """For each graduate with an mlbam_id, walk their MLB seasons in
    ``career_war.seasons`` (most recent ``max_seasons``), scrape and
    aggregate pitches, return ``{player_key: heat_array}``.

    Year-batched bulk fetch: groups all (graduate, year) pairs by year,
    issues ONE Savant request per year carrying up to
    ``batters_per_request`` batter IDs. ~50 graduates × 3 seasons
    collapses from 150 sequential HTTP calls to 3 (one per season),
    typically returning in <10s on a cold cache. Per-batter cache files
    are still written so single-player calls (`scrape_savant_pitches`)
    stay fast.

    Graduates without an mlbam_id, or with no MLB seasons in the
    requested window, are skipped.
    """
    today = date.today()
    seasons_by_key: dict[str, list[int]] = {}
    mlbam_by_key: dict[str, int] = {}
    # year -> set of (key, mlbam) tuples
    year_to_pairs: dict[int, list[tuple[str, int]]] = {}

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
        seasons_by_key[key] = seasons
        mlbam_by_key[key] = mlbam
        for yr in seasons:
            year_to_pairs.setdefault(yr, []).append((key, mlbam))

    if not year_to_pairs:
        log.info("graduate_savant: nothing to fetch")
        return {}

    # Build batch jobs: (year, [mlbam_ids]). Splits large years across
    # multiple sub-batches so URL length stays under typical 8KB limits.
    jobs: list[tuple[int, list[int]]] = []
    for yr, pairs in year_to_pairs.items():
        ids = list({mid for _, mid in pairs})  # dedupe
        for i in range(0, len(ids), batters_per_request):
            jobs.append((yr, ids[i:i + batters_per_request]))

    log.info("graduate_savant: %d bulk job(s) across %d worker(s) "
             "(years: %s)", len(jobs), max_workers,
             sorted(year_to_pairs.keys()))
    t_start = time.monotonic()

    # mlbam_id -> [pitches]; accumulated as bulk responses come back.
    pitches_by_mlbam: dict[int, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_job = {
            ex.submit(_scrape_savant_pitches_bulk, ids, yr, force): (yr, ids)
            for yr, ids in jobs
        }
        for fut in as_completed(future_to_job):
            yr, ids = future_to_job[fut]
            try:
                bucket = fut.result()
            except Exception:
                log.exception("savant bulk job failed for year %d", yr)
                continue
            for mid, pitches in bucket.items():
                pitches_by_mlbam.setdefault(mid, []).extend(pitches)

    elapsed = time.monotonic() - t_start
    log.info("graduate_savant: %d bulk job(s) fetched in %.1fs",
             len(jobs), elapsed)

    out: dict = {}
    for key, mid in mlbam_by_key.items():
        pitches = pitches_by_mlbam.get(mid, [])
        if not pitches:
            continue
        heat = compute_swing_zone_heat(pitches)
        if any(v is not None for v in heat):
            out[key] = heat
    log.info("graduate_savant: %d graduates with swing zone heat", len(out))
    return out
