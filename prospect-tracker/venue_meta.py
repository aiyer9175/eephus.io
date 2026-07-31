# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Ballpark metadata from the MLB StatsAPI /venues endpoint, cached to disk.

Every game and team the local DB already carries a `venueId`, but nothing
local describes the park itself: where it sits, how high, what the fences
look like, or which way the batter faces. The StatsAPI `/api/v1/venues`
endpoint returns that context for the whole affiliated ladder in six
calls (one per sportId) when hydrated with location + fieldInfo, keyed by
`venueId` which already joins straight onto our teams/games.

Landed fields per venue:
  name          park name
  level         platform level of the sportId it was fetched under (MLB
                venues under sportId 1, AAA under 11, ... CPX under 16);
                when a park hosts more than one level the HIGHEST is kept
  lat / lon     location.defaultCoordinates
  elevation_ft  location.elevation (feet above sea level; sparse below MLB)
  roof / turf   fieldInfo.roofType / turfType
  dims          the outfield dimension keys fieldInfo carries (leftLine,
                left, leftCenter, center, rightCenter, right, rightLine),
                only those actually present
  azimuth       location.azimuthAngle (home-plate-to-center bearing; the
                park-line / handedness feature depends on this)
  capacity      fieldInfo.capacity

Cache: .cache/venue_meta/venues_{sport}.json (gitignored). Landed table:
data/venue_meta.json keyed by venueId. Pure read-only consumer; never
touches the prospect DB. NOT wired into run_monthly / build_site (owner
integration).

Coordinates for use: `venue_for(venue_id)`.
"""

from __future__ import annotations

import json
import logging
import time
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / ".cache" / "venue_meta"
DATA_PATH = Path(__file__).parent / "data" / "venue_meta.json"

BASE = "https://statsapi.mlb.com/api/v1/venues"
_HYDRATE = "location,fieldInfo,timezone"
_UA = {"User-Agent": "Mozilla/5.0"}

# sportId -> platform level label (mirrors milb_history.SPORT_LEVEL, minus
# the retired short-season sportId 15). These six are the verified venue
# sportIds; NPB/KBO/indy parks are out of scope for park factors.
SPORT_LEVEL = {1: "MLB", 11: "AAA", 12: "AA", 13: "A+", 14: "A", 16: "CPX"}
SPORTS = (1, 11, 12, 13, 14, 16)
_LEVEL_RANK = {"CPX": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5, "MLB": 6}

# fieldInfo dimension keys, outfield line-to-line. StatsAPI always carries
# the *Line/*Center variants and sometimes a bare left/right; we keep only
# the ones actually present on each park.
_DIM_KEYS = ("leftLine", "left", "leftCenter", "center",
             "rightCenter", "right", "rightLine")

# Venue metadata is effectively static, so past caches live forever; a file
# older than this TTL refreshes once so new parks and re-measured fences land.
_TTL_SEC = 20 * 3600

# statsapi rate limit: keep to <= 1 request/sec, never parallelize.
_MIN_REQ_GAP = 1.1
_last_req = [0.0]


def _fetch(url: str) -> dict:
    import urllib.request
    gap = _MIN_REQ_GAP - (time.monotonic() - _last_req[0])
    if gap > 0:
        time.sleep(gap)
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    finally:
        _last_req[0] = time.monotonic()


def _sport_venues(sport_id: int, fetch: bool = True) -> list[dict]:
    """Raw venue records for one sportId, cached. Returns [] when uncached
    and fetch=False so offline consumers stay network-free."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"venues_{sport_id}.json"
    cached = None
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            cached = None
        if cached is not None:
            stale = fetch and (time.time() - path.stat().st_mtime) >= _TTL_SEC
            if not stale:
                return cached
    if not fetch:
        return cached or []
    url = f"{BASE}?hydrate={_HYDRATE}&sportId={sport_id}"
    try:
        d = _fetch(url)
    except Exception as e:                                    # noqa: BLE001
        log.warning("venue_meta fetch failed sport=%s: %s", sport_id, e)
        return cached or []                     # transient failure keeps prior cache
    venues = d.get("venues") or []
    if not venues and cached is not None:
        return cached                           # empty refetch keeps prior cache
    path.write_text(json.dumps(venues, separators=(",", ":")), encoding="utf-8")
    log.info("venue_meta cached sport=%s: %d venues", sport_id, len(venues))
    return venues


def _lean(v: dict, level: str) -> dict:
    loc = v.get("location") or {}
    coords = loc.get("defaultCoordinates") or {}
    fi = v.get("fieldInfo") or {}
    dims = {k: fi.get(k) for k in _DIM_KEYS if fi.get(k) is not None}
    return {
        "name": v.get("name"),
        "level": level,
        "lat": coords.get("latitude"),
        "lon": coords.get("longitude"),
        "elevation_ft": loc.get("elevation"),
        "roof": fi.get("roofType"),
        "turf": fi.get("turfType"),
        "dims": dims,
        "azimuth": loc.get("azimuthAngle"),
        "capacity": fi.get("capacity"),
    }


def _fill_nulls(primary: dict, other: dict) -> dict:
    """Same park seen under two sportIds should carry identical geometry,
    but if one record has a field the other lacks (e.g. elevation present
    only under the MLB fetch) fill the gap without changing name/level."""
    for k, v in other.items():
        if k in ("name", "level"):
            continue
        if primary.get(k) in (None, {}, "") and v not in (None, {}, ""):
            primary[k] = v
    return primary


def build(fetch: bool = True, sports=SPORTS) -> dict[int, dict]:
    """Fetch venues across sportIds, merge, and land data/venue_meta.json
    keyed by venueId. A park hosting multiple levels keeps the highest
    level label; non-null geometry is carried across the merge."""
    merged: dict[int, dict] = {}
    for sport in sports:
        level = SPORT_LEVEL.get(sport, "?")
        for v in _sport_venues(sport, fetch=fetch):
            vid = v.get("id")
            if vid is None:
                continue
            vid = int(vid)
            row = _lean(v, level)
            prev = merged.get(vid)
            if prev is None:
                merged[vid] = row
            elif _LEVEL_RANK.get(level, 0) > _LEVEL_RANK.get(prev.get("level"), 0):
                merged[vid] = _fill_nulls(row, prev)      # new level higher -> adopt
            else:
                merged[vid] = _fill_nulls(prev, row)      # keep prev level, fill gaps
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps({str(k): merged[k] for k in sorted(merged)},
                   separators=(",", ":")),
        encoding="utf-8")
    _load.cache_clear()
    log.info("venue_meta landed %d venues -> %s", len(merged), DATA_PATH)
    return merged


@lru_cache(maxsize=1)
def _load() -> dict[int, dict]:
    if DATA_PATH.exists():
        try:
            raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            return {int(k): v for k, v in raw.items()}
        except ValueError:
            pass
    return {}


def venue_for(venue_id) -> dict | None:
    """Landed metadata for one venueId, or None. Reads the on-disk table
    (build() must have run at least once); never fetches."""
    if venue_id is None:
        return None
    try:
        vid = int(venue_id)
    except (TypeError, ValueError):
        return None
    return _load().get(vid)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    table = build()
    n_ll = sum(1 for r in table.values() if r["lat"] is not None)
    n_el = sum(1 for r in table.values() if r["elevation_ft"] is not None)
    print(f"venues={len(table)} with_latlon={n_ll} with_elevation={n_el}")
    ex = next((r for lvl in ("AAA", "AA", "A+", "A", "CPX")
               for r in table.values()
               if r["level"] == lvl and r["elevation_ft"] is not None), None)
    if ex:
        print("MiLB example:", ex["name"], ex["level"],
              f"lat={ex['lat']} lon={ex['lon']} elev_ft={ex['elevation_ft']}")
