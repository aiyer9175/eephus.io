# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Statcast (tracked parks) hitter sidecar - the batter analog of
stuff_plus_aaa.json. The file keeps its historical name; the card it feeds
reads "Statcast (tracked parks)" (owner answer M25AAA-2, 2026-10-01).

  DATA     the Savant minors batter aggregates (the statcast-search minors
           player CSV, request arkmetric_forward_eval.SAVANT; coverage begins
           2023), read per season from one of TWO caches:
             .cache/savant_minors_live/batter_<season>.csv  the current
                 season, refreshed by refresh() (run_monthly step 6b2a);
                 read by THIS CARD ONLY.
             .cache/savant_minors/batter_<season>.csv  the model cache that
                 arkmetric_forward_eval.savant_rows maintains; used for every
                 season the live cache does not hold.
  PARKS    the Savant minors search covers every Hawk-Eye tracked park, not
           AAA alone: every AAA park (International and Pacific Coast
           Leagues) and the Single-A Florida State League. Measured on the
           2026-10-01 bake: 1,631 of 1,640 rows' Savant PA equal the PA of
           the player's AAA plus Florida State League season lines exactly,
           7 differ by 1 PA, 2 cover part of an FSL line, and no row
           has a Savant line without one of those two. A+ and AA parks do not
           appear. So a hitter with no AAA line (154 of the 720 2026 rows,
           for example Dax Kilby) carries his FSL line here.
  ROWS     each mlbam with >= 100 PA in a season; the LATEST qualified
           season wins (seasons walked ascending, later overwrites). Every
           row is kept (owner answer M25AAA-2: keep and relabel, no AAA-only
           filter).
  FIELDS   xwoba / woba / xslg / slg, ev (launch_speed), hardhit_percent,
           barrels_per_bbe_percent, whiff (swing_miss_percent), bat_speed
           (null - the minors aggregate export does not carry it yet),
           luck_gap = round(xwoba - woba, 3) (positive = under-performed
           the contact quality), pa, season, levels.
  LEVELS   levels = the level(s) the season's Statcast line came from,
           highest first: the player's MiLB season lines that season
           (milb_history cache, offline) with PA > 0 in a tracked league,
           AAA in any league and A in the Florida State League only. Savant's
           aggregate carries no level or league column, so the season lines
           are the only source. [] when the cache holds no such line (none on
           the 2026-10-01 bake). A label, never an input to any number.

WHY TWO CACHES (owner answer M25-3, 2026-09-25, held until fWAR epoch step M).
The model cache's batter_2026.csv is not a card-only input. Three served model
paths read it: the S-XLINE measurement layer that adjusts AAA 2026 lines before
eFV scores them (efv_statcast_line._gap_index), the Savant-minors SC+ re-source
in storage.py, whose statcast_plus feeds the eFV live tilt (efv_score), and the
eFV v2 modern-signal snapshot (tools/snapshot_modern_signals.py). Projections
are not retrained before 2026-10-05 and the eFV inputs move at the fWAR label
epoch's step M, so a refetch into that cache would move served eFV grades
outside the epoch. The refreshed season therefore lands in the live cache, and
only this sidecar reads it. Promoting it into the model cache is a step M
decision, not something this module does. arkmetric_forward_eval.run scores
SEASONS 2023-2025 only, so its forward eval never reads a 2026 file.

Sidecar: data/statcast_aaa_hitters.json {"generated_at", "note", "source",
"source_fetched": {season: fetch date}, "source_through": {season: last
regular-season game date the CSV covers}, "by_mlbam": {mlbam: {...}}}.
Consumer: the PROSPX hitter-card "Statcast (tracked parks)" pill row
(aaaStatcastPanel), which prints each row's level(s) beside the season, the
data-through date and the source.

MONTHLY PHASE (refresh): gated to the AAA regular season (StatsAPI /seasons,
sportId 11) plus ONE final pull after it ends, so the card's last 2026 read
covers the whole AAA regular season. The gate reads the AAA calendar only;
the Florida State League rows ride the same request. One request per run,
cached, never more often than REFRESH_TTL_S. A failed or malformed fetch keeps the last good file and
returns ok=False for the ingest-health ledger; nothing here raises.

Run: python statcast_aaa_hitters.py            (bake the sidecar from the caches)
     python statcast_aaa_hitters.py --refresh  (gated fetch, then bake)
"""

from __future__ import annotations

import csv
import io
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "statcast_aaa_hitters.json"
LIVE_DIR = ROOT / ".cache" / "savant_minors_live"

SEASONS = (2023, 2024, 2025, 2026)   # Savant minors coverage begins 2023
MIN_PA = 100

NOTE = ("Savant minors Statcast (tracked parks: every AAA park and the "
        "Single-A Florida State League) batter aggregates 2023+, latest "
        ">=100 PA season per player; levels = the tracked level(s) of the "
        "player's season lines that season; luck_gap = round(xwoba - woba, 3), "
        "positive = under-performed the contact quality")
SOURCE = ("Baseball Savant statcast search, minors (tracked parks: every AAA "
          "park and the Single-A Florida State League), regular season, "
          "batters with 100+ PA")

# The tracked leagues by level (see PARKS in the module docstring). None =
# every league at that level. Level labels and league names are the
# milb_history cache's own.
TRACKED_LEAGUES = {"AAA": None, "A": frozenset({"FSL", "Florida State League"})}

AAA_SPORT_ID = 11
SEASONS_API = "https://statsapi.mlb.com/api/v1/seasons/{season}?sportId={sport}"
CALENDAR_TTL_S = 7 * 86400
# The phase runs on the monthly pass (the 1st); a manual full rerun inside the
# same month does not refetch.
REFRESH_TTL_S = 20 * 86400
# A refetch that comes back with fewer than this share of the last good file's
# rows is refused: the season's 100+ PA pool only grows.
MIN_KEEP_RATIO = 0.8
REQUIRED_COLS = ("player_id", "pa", "xwoba", "woba", "launch_speed",
                 "hardhit_percent", "swing_miss_percent")
_MIN_INTERVAL = 1.05
_last_request = [0.0]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _r(v, nd: int):
    return None if v is None else round(v, nd)


def _row(r: dict, season: int) -> dict:
    xwoba = _r(_f(r.get("xwoba")), 3)
    woba = _r(_f(r.get("woba")), 3)
    return {
        "xwoba": xwoba,
        "woba": woba,
        "xslg": _r(_f(r.get("xslg")), 3),
        "slg": _r(_f(r.get("slg")), 3),
        "ev": _r(_f(r.get("launch_speed")), 1),
        "hardhit_percent": _r(_f(r.get("hardhit_percent")), 1),
        "barrels_per_bbe_percent": _r(_f(r.get("barrels_per_bbe_percent")), 1),
        "whiff": _r(_f(r.get("swing_miss_percent")), 1),
        "bat_speed": _r(_f(r.get("bat_speed")), 1),
        "luck_gap": (round(xwoba - woba, 3)
                     if xwoba is not None and woba is not None else None),
        "pa": int(_f(r.get("pa")) or 0),
        "season": season,
    }


# --------------------------------------------------------------------------
# Reading the caches
# --------------------------------------------------------------------------
def live_path(season: int) -> Path:
    return LIVE_DIR / f"batter_{int(season)}.csv"


def live_meta_path(season: int) -> Path:
    return LIVE_DIR / f"batter_{int(season)}.meta.json"


def read_live_meta(season: int) -> dict:
    try:
        return json.loads(live_meta_path(season).read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def _csv_rows(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    return list(csv.DictReader(io.StringIO(text)))


def season_rows(season: int) -> tuple[list[dict], str]:
    """(rows, which cache) for one season: the live refresh when it exists,
    else the model cache (offline, fetch=False)."""
    lp = live_path(season)
    if lp.exists():
        rows = _csv_rows(lp)
        if rows:
            return rows, "live"
    import arkmetric_forward_eval as af
    return af.savant_rows(season, "batter", fetch=False), "model"


def tracked_lines(mlbam: int, season: int) -> list[dict]:
    """The player's MiLB season lines (milb_history cache, offline) in a
    tracked league that season, PA > 0."""
    import milb_history as mh
    out = []
    for r in mh.player_index(int(season), "hitting", fetch=False).get(int(mlbam), []):
        lv = r.get("level")
        if lv not in TRACKED_LEAGUES or not (_f(r.get("pa")) or 0) > 0:
            continue
        leagues = TRACKED_LEAGUES[lv]
        if leagues is not None and (r.get("league") or "").strip() not in leagues:
            continue
        out.append(r)
    return out


def tracked_levels(mlbam: int, season: int) -> list[str]:
    """The level(s) a season's Statcast line came from, highest first (see
    LEVELS in the module docstring)."""
    import milb_history as mh
    lvls = {r["level"] for r in tracked_lines(mlbam, season)}
    return sorted(lvls, key=lambda lv: -mh._LEVEL_RANK.get(lv, -1))


def build(seasons=SEASONS) -> dict:
    """Payload from the cached CSVs only (never fetches)."""
    import arkmetric_forward_eval as af
    by_mlbam: dict[str, dict] = {}
    used: dict[str, str] = {}
    for season in seasons:                       # ascending: latest wins
        n = 0
        rows, which = season_rows(season)
        if rows:
            used[str(season)] = which
        for r in rows:
            mid = _f(r.get("player_id"))
            pa = _f(r.get("pa"))
            if mid is None or pa is None or pa < MIN_PA:
                continue
            row = _row(r, season)
            row["levels"] = tracked_levels(int(mid), season)
            by_mlbam[str(int(mid))] = row
            n += 1
        log.info("aaa statcast hitters %d: %d qualified rows (%s cache)",
                 season, n, which)
    fetched = source_fetched(seasons, af.CACHE_DIR)
    through: dict[str, str] = {}
    for s, which in used.items():
        if which != "live":
            continue
        meta = read_live_meta(int(s))
        if meta.get("fetched"):
            fetched[s] = meta["fetched"]
        if meta.get("through"):
            through[s] = meta["through"]
    return {"generated_at": date.today().isoformat(),
            "note": NOTE,
            "source": SOURCE,
            "source_fetched": fetched,
            "source_through": through,
            "by_mlbam": by_mlbam}


def source_fetched(seasons, cache_dir: Path) -> dict[str, str]:
    """{season: UTC date the cached Savant CSV was fetched}.

    generated_at is the BAKE date and says nothing about the data: on
    2026-09-24 the sidecar read generated_at 2026-07-23 while its 2026 rows
    came from a CSV fetched on 2026-06-22, so the card printed "AAA 2026"
    over roughly half a season. The cache lives only on the machine that
    bakes (.cache/ is gitignored) and savant_rows writes it on fetch, so the
    file's modification time is its fetch time. A season fetched during that
    same year is a partial season, and the card prints the date. A season
    read from the live cache takes its fetch date from the meta file instead
    (see build)."""
    out: dict[str, str] = {}
    for season in seasons:
        p = cache_dir / f"batter_{season}.csv"
        if p.exists():
            out[str(season)] = datetime.fromtimestamp(
                p.stat().st_mtime, tz=timezone.utc).date().isoformat()
    return out


def bake(persist: bool = True) -> dict:
    payload = build()
    if persist and payload["by_mlbam"]:
        OUT_PATH.write_text(json.dumps(payload, separators=(",", ":")),
                            encoding="utf-8")
        log.info("wrote %s (%d hitters)", OUT_PATH, len(payload["by_mlbam"]))
    return payload


# --------------------------------------------------------------------------
# The monthly refresh
# --------------------------------------------------------------------------
def _throttle() -> None:
    wait = _MIN_INTERVAL - (time.monotonic() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.monotonic()


def _http_get(url: str, timeout: int = 120) -> bytes:
    import urllib.request
    _throttle()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def aaa_calendar(season: int, *, fetch: bool = True, getter=None) -> dict | None:
    """{"start", "end"} of the AAA regular season (StatsAPI /seasons,
    sportId 11), cached a week; a failed fetch falls back to the copy on
    disk at any age. None when the calendar is unknown."""
    path = LIVE_DIR / f"aaa_season_{int(season)}.json"
    data = None
    fresh = path.exists() and (time.time() - path.stat().st_mtime) < CALENDAR_TTL_S
    if fetch and not fresh:
        try:
            raw = (getter or _http_get)(SEASONS_API.format(season=int(season),
                                                           sport=AAA_SPORT_ID), 30)
            data = json.loads(raw)
            LIVE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(path)
        except Exception as e:                            # noqa: BLE001
            log.warning("aaa calendar fetch failed for %s: %s", season, e)
            data = None
    if data is None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    for s in (data or {}).get("seasons") or []:
        if str((s or {}).get("seasonId")) == str(int(season)):
            start, end = s.get("regularSeasonStartDate"), s.get("regularSeasonEndDate")
            if start and end:
                return {"start": str(start), "end": str(end)}
    return None


def _eastern_date(ts: datetime) -> date:
    """The calendar date in US Eastern, where Savant's nightly update runs."""
    try:
        from zoneinfo import ZoneInfo
        return ts.astimezone(ZoneInfo("America/New_York")).date()
    except Exception:                                     # noqa: BLE001
        return (ts - timedelta(hours=4)).date()


def data_through(fetched_at: datetime, cal: dict | None) -> str | None:
    """Last regular-season game date a CSV fetched at `fetched_at` covers:
    the day before the fetch (Eastern), capped at the regular season's end.
    None when the fetch predates the season's first game day."""
    d = _eastern_date(fetched_at) - timedelta(days=1)
    if cal:
        end = date.fromisoformat(cal["end"])
        start = date.fromisoformat(cal["start"])
        if d > end:
            d = end
        if d < start:
            return None
    return d.isoformat()


def phase_decision(today: date, cal: dict | None, meta: dict,
                   now_ts: float | None = None) -> tuple[bool, str]:
    """(fetch?, reason). In season: fetch when the live copy is older than
    REFRESH_TTL_S. After the season: fetch once more unless the live copy
    already covers the last regular-season day. Before it: never."""
    now_ts = time.time() if now_ts is None else now_ts
    if cal is None:
        # Calendar unknown: fall back to the months AAA plays (April to
        # September) and fetch on the TTL inside them.
        if not 4 <= today.month <= 9:
            return False, "calendar unknown and outside April to September"
        start, end = date(today.year, 4, 1), date(today.year, 9, 30)
    else:
        start, end = date.fromisoformat(cal["start"]), date.fromisoformat(cal["end"])
    if today < start:
        return False, f"preseason (AAA regular season opens {start.isoformat()})"
    if today <= end:
        age = now_ts - float(meta.get("fetched_ts") or 0)
        if meta and age < REFRESH_TTL_S:
            return False, f"live copy is {age / 86400:.0f} days old (TTL {REFRESH_TTL_S // 86400})"
        return True, "in season"
    if (meta.get("through") or "") >= end.isoformat():
        return False, f"final pull done (games through {meta.get('through')})"
    return True, f"final post-season pull (regular season ended {end.isoformat()})"


def shape_ok(text: str, prev_rows: int = 0) -> tuple[bool, str]:
    """A refetch replaces the last good file only when it is a CSV with the
    columns the card reads, has rows, and has not shrunk below
    MIN_KEEP_RATIO of the last good copy."""
    if not text or not text.strip():
        return False, "empty response"
    if text.lstrip().startswith("<"):
        return False, "HTML, not a CSV"
    rdr = csv.DictReader(io.StringIO(text))
    head = {h.strip().strip('"') for h in (rdr.fieldnames or ())}
    missing = [c for c in REQUIRED_COLS if c not in head]
    if missing:
        return False, "missing columns " + ", ".join(missing)
    n = sum(1 for r in rdr if _f(r.get("player_id")) is not None)
    if n == 0:
        return False, "no rows"
    if prev_rows and n < MIN_KEEP_RATIO * prev_rows:
        return False, f"{n} rows against {prev_rows} in the last good file"
    return True, f"{n} rows"


def fetch_live(season: int, cal: dict | None, *, getter=None,
               now: datetime | None = None) -> dict:
    """One Savant request for `season`, validated, then swapped in atomically.
    Never raises: a failure keeps the last good file and says why."""
    import arkmetric_forward_eval as af
    url = af.SAVANT.format(type="batter", year=int(season))
    path = live_path(season)
    # The last good copy is the live file, or, before the first refresh, the
    # model cache's copy of the same season (the shrink guard compares to it).
    prev = (_csv_rows(path) if path.exists()
            else af.savant_rows(int(season), "batter", fetch=False))
    prev_n = sum(1 for r in prev if _f(r.get("player_id")) is not None)
    try:
        raw = (getter or _http_get)(url, 120)
        text = raw.decode("utf-8-sig", errors="replace")
    except Exception as e:                                # noqa: BLE001
        return {"ok": False, "message": f"fetch failed: {e}"[:200],
                "rows": prev_n, "kept": path.exists()}
    ok, why = shape_ok(text, prev_n)
    if not ok:
        return {"ok": False, "message": f"refused: {why}", "rows": prev_n,
                "kept": path.exists()}
    now = now or datetime.now(timezone.utc)
    rows = sum(1 for r in csv.DictReader(io.StringIO(text))
               if _f(r.get("player_id")) is not None)
    meta = {"season": int(season), "source": SOURCE, "url": url,
            "fetched": now.date().isoformat(),
            "fetched_at": now.replace(microsecond=0).isoformat(),
            "fetched_ts": now.timestamp(),
            "through": data_through(now, cal), "rows": rows}
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    mtmp = live_meta_path(season).with_suffix(".json.tmp")
    mtmp.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    mtmp.replace(live_meta_path(season))
    return {"ok": True, "message": f"fetched {rows} rows, games through "
                                   f"{meta['through']}", "rows": rows,
            "through": meta["through"], "kept": False}


def refresh(today: date | None = None, *, getter=None, persist: bool = True,
            force: bool = False) -> dict:
    """The monthly phase: gated fetch of the current season into the live
    cache, then a rebake. Returns {ok, fetched, message, n_hitters}; ok is
    False only when a fetch was due and failed (the last good file stands
    and the sidecar is still rebaked from it)."""
    today = today or date.today()
    season = today.year
    out = {"ok": True, "fetched": False, "season": season}
    try:
        cal = aaa_calendar(season, getter=getter)
        meta = read_live_meta(season)
        due, reason = phase_decision(today, cal, meta)
        if force and not due:
            due, reason = True, f"forced ({reason})"
        out["message"] = reason
        if due:
            res = fetch_live(season, cal, getter=getter)
            out["ok"], out["fetched"] = res["ok"], res["ok"]
            out["message"] = f"{reason}: {res['message']}"
        payload = bake(persist=persist)
        out["n_hitters"] = len(payload["by_mlbam"])
    except Exception as e:                                # noqa: BLE001
        out.update(ok=False, message=f"crashed: {e}"[:200])
        log.exception("aaa statcast refresh crashed")
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--refresh" in sys.argv:
        res = refresh(persist="--dry-run" not in sys.argv,
                      force="--force" in sys.argv)
        print("refresh:", res)
    else:
        out = bake(persist="--dry-run" not in sys.argv)
        print("hitters:", len(out["by_mlbam"]))
