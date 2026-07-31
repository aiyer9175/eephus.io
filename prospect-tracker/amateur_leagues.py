# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Amateur / winter / independent-league season stats from the MLB
StatsAPI, cached to disk. The off-affiliated production the milb_history
ladder never sees, carried on native MLBAM player ids.

milb_history.py covers the affiliated sportIds (1, 11-16). This module
covers the three MLBAM-native NON-affiliated buckets, every line keyed by
the same `player.id` so they join straight onto the prospect pool:

  sportId 22  amateur       college (CBB), Cape Cod (CCBL), Appalachian
                            (APP, summer collegiate), MLB Draft League (MLBDL)
  sportId 17  winter        Arizona Fall League (AFL) + the Caribbean
                            circuits (LIDOM, LMP, LVBP, PWL, CS, ABL)
  sportId 23  independent   incl. the Mexican League (MEX / LMB)

IMPORTANT the qualifier default drops sub-threshold lines; every fetch
passes `playerPool=all` (raises the returned count well above the default
qualified pool). Populated 2018-2026; 2013 and earlier are empty.

NOT INGESTED (documented negative control): sportId 31 (NPB) and 32 (KBO)
are listed by /sports but every stats query returns totalSplits 0. They
are deliberately excluded from SPORTS; do not re-add them expecting data.
test_amateur_venues.py pins this so a future dev does not re-add them.

Cache: .cache/amateur_leagues/{group}_{sport}_{season}.json (gitignored).
Landed table: data/amateur_leagues.json keyed by mlbam -> [season lines].
Pure read-only consumer; never touches the prospect DB. NOT wired into
run_monthly / build_site / milb_history (owner integration).

Lines for one player: `amateur_lines(mlbam)`.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / ".cache" / "amateur_leagues"
DATA_PATH = Path(__file__).parent / "data" / "amateur_leagues.json"

BASE = "https://statsapi.mlb.com/api/v1/stats"
_UA = {"User-Agent": "Mozilla/5.0"}

# sportId -> coarse bucket label. The per-line `league` field carries the
# specific circuit (CBB / CCBL / AFL / MEX / ...); this is the family.
SPORT_LABEL = {22: "amateur", 17: "winter", 23: "independent"}
SPORTS = (22, 17, 23)

# Verified-empty sportIds. Kept here as an explicit exclusion + assertion
# target, NOT a fetch list (see module docstring).
EMPTY_SPORTS = (31, 32)  # 31 = NPB, 32 = KBO

_DEFAULT_START = 2021


def _season_range() -> range:
    return range(_DEFAULT_START, date.today().year + 1)


# Current-season caches refresh past this TTL so in-progress winter/indy
# seasons track; past seasons are final and cached forever.
_SEASON_TTL_SEC = 20 * 3600

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


def _lean_row(s: dict, sport_id: int, season: int, group: str) -> dict:
    st = s.get("stat") or {}
    player = s.get("player") or {}
    league = s.get("league") or {}
    row = {
        "mlbam": player.get("id"),
        "name": player.get("fullName"),
        "season": season,
        "sport": sport_id,
        "sport_label": SPORT_LABEL.get(sport_id, str(sport_id)),
        "league": league.get("name"),
        "league_id": league.get("id"),
        "group": group,
        "age": st.get("age"),
    }
    if group == "hitting":
        row.update({
            "pa": st.get("plateAppearances"), "ab": st.get("atBats"),
            "ops": st.get("ops"), "obp": st.get("obp"),
            "slg": st.get("slg"), "avg": st.get("avg"),
            "so": st.get("strikeOuts"), "bb": st.get("baseOnBalls"),
            "hr": st.get("homeRuns"), "sb": st.get("stolenBases"),
        })
    else:
        row.update({
            "ip": st.get("inningsPitched"), "bf": st.get("battersFaced"),
            "era": st.get("era"), "so": st.get("strikeOuts"),
            "bb": st.get("baseOnBalls"), "g": st.get("gamesPlayed"),
            "gs": st.get("gamesStarted"),
        })
    return row


def season_splits(sport_id: int, season: int, group: str,
                  fetch: bool = True) -> list[dict]:
    """All player season lines for one (sport, season, group), cached,
    playerPool=all. group: 'hitting' | 'pitching'. Returns [] when
    uncached and fetch=False (offline-safe)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{group}_{sport_id}_{season}.json"
    cached = None
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            cached = None
        if cached is not None:
            stale = (fetch and season >= date.today().year
                     and (time.time() - path.stat().st_mtime) >= _SEASON_TTL_SEC)
            if not stale:
                return cached
    if not fetch:
        return cached or []
    splits: list[dict] = []
    offset = 0
    while True:
        url = (f"{BASE}?stats=season&group={group}&season={season}"
               f"&sportIds={sport_id}&playerPool=all&limit=2000&offset={offset}")
        try:
            d = _fetch(url)
        except Exception as e:                                # noqa: BLE001
            log.warning("amateur_leagues fetch failed %s/%s/%s: %s",
                        group, sport_id, season, e)
            return cached if cached is not None else splits
        block = (d.get("stats") or [{}])[0]
        page = block.get("splits") or []
        splits.extend(page)
        total = block.get("totalSplits") or len(splits)
        offset += len(page)
        if not page or offset >= total:
            break
    lean = [_lean_row(s, sport_id, season, group)
            for s in splits if (s.get("player") or {}).get("id")]
    # A genuinely empty season (winter/indy before it starts) is a valid
    # result and IS cached; only a failed refetch of a previously-populated
    # cache falls back to the prior copy.
    if not lean and cached:
        return cached
    path.write_text(json.dumps(lean, separators=(",", ":")), encoding="utf-8")
    log.info("amateur_leagues cached %s sport=%s season=%s: %d rows",
             group, sport_id, season, len(lean))
    return lean


def warm_cache(seasons=None, sports=SPORTS) -> None:
    for season in (seasons if seasons is not None else _season_range()):
        for sport in sports:
            for group in ("hitting", "pitching"):
                season_splits(sport, season, group)


def build(seasons=None, sports=SPORTS, fetch: bool = True) -> dict[int, list[dict]]:
    """Fetch the sport/season/group grid and land data/amateur_leagues.json
    keyed by mlbam -> [season lines], each line carrying its league label."""
    seasons = list(seasons if seasons is not None else _season_range())
    out: dict[int, list[dict]] = {}
    for season in seasons:
        for sport in sports:
            for group in ("hitting", "pitching"):
                rows = season_splits(sport, season, group, fetch=fetch)
                for r in rows:
                    mid = r.get("mlbam")
                    if mid is None:
                        continue
                    out.setdefault(int(mid), []).append(r)
    for mid in out:
        out[mid].sort(key=lambda r: (-(r.get("season") or 0),
                                     r.get("sport") or 0, r.get("group") or ""))
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps({str(k): out[k] for k in sorted(out)},
                   separators=(",", ":")),
        encoding="utf-8")
    _load.cache_clear()
    log.info("amateur_leagues landed %d players -> %s", len(out), DATA_PATH)
    return out


@lru_cache(maxsize=1)
def _load() -> dict[int, list[dict]]:
    if DATA_PATH.exists():
        try:
            raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            return {int(k): v for k, v in raw.items()}
        except ValueError:
            pass
    return {}


def amateur_lines(mlbam) -> list[dict]:
    """Amateur/winter/indy season lines for one MLBAM id (newest first),
    or [] if none. Reads the landed table; never fetches."""
    if mlbam is None:
        return []
    try:
        mid = int(mlbam)
    except (TypeError, ValueError):
        return []
    return _load().get(mid, [])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    table = build()
    print(f"players={len(table)} lines={sum(len(v) for v in table.values())}")
