# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""savant_days - one Savant bat-tracking file per game date (League Trends plan
5.1 and 3.4, owner answer TR-Q3 (a) of 2026-10-01).

WHAT IT FETCHES. One ``statcast_search`` request per regular-season game date,
built from ``swing_plus_ingest.SEARCH`` (the full parameter skeleton, because a
sparse one falls back to defaults silently) with the game-date bounds set to
that one date and the batter filter removed, so the file holds every hitter's
pitches of the day. Only these columns are kept: game_date, game_pk, batter,
at_bat_number, pitch_number, description, bat_speed, swing_length,
attack_angle. A row whose game_date is not the requested date is refused (left
out and counted), so a file never carries another day's swings.

WHERE IT WRITES. ``.cache/league_trends/savant_days/<date>.csv`` and a
``manifest.json`` beside it (per season: dates, tracked swings, hitters, the
latest date). It never writes ``.cache/swing_pitches/``, the Swing+ cache,
which stays Swing+'s alone.

FAIL-SOFT. A timeout or a network error leaves the date's cached file (if
any) as it was and moves on; nothing half-written lands (atomic replace). Two
answers stop a run instead, because continuing would be wrong rather than
merely slow: HTTP 403 (Savant refusing the client) and a changed column set
(a kept column missing from the response header). Either raises
``SavantStop``; the files already written are kept. Each run files one
``record_ingest`` row (source ``savant_days``) when a pipeline is live.

WHICH DATES. The regular-season game dates of a season on the US Eastern
calendar, from the cached win-probability payloads
(``mlbstats_games.season_game_dates``). A completed season's file is never
refetched; in the live season a date is fetched once its file is absent. A
response with no row of the date writes nothing, so the date is tried again on
the next run.

Nothing here is a model, a rate or a forecast; the files are raw Savant rows.

Run:
    python savant_days.py --backfill 2024,2025,2026      (the one-time backfill)
    python savant_days.py                                (the live season's new dates)
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

import swing_plus_ingest as SPI

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / ".cache" / "league_trends" / "savant_days"
SWING_CACHE = SPI.CACHE_DIR                  # .cache/swing_pitches, never written here
SOURCE = "savant_days"
THROTTLE_S = SPI.THROTTLE_S                  # 1.5 s, Swing+'s own courtesy
TIMEOUT_S = 180
FIRST_SEASON = SPI.FIRST_TRACKING_SEASON     # 2024

KEEP_COLS = ("game_date", "game_pk", "batter", "at_bat_number", "pitch_number",
             "description", "bat_speed", "swing_length", "attack_angle")

_DATE_BOUNDS_EMPTY = "&game_date_gt=&game_date_lt="
_BATTER_FILTER = "&batters_lookup%5B%5D={mlbam}"


def _day_search() -> str:
    """swing_plus_ingest.SEARCH with date bounds and no batter filter."""
    s = SPI.SEARCH
    if _DATE_BOUNDS_EMPTY not in s or _BATTER_FILTER not in s:
        raise RuntimeError("swing_plus_ingest.SEARCH changed shape; savant_days cannot "
                           "derive its day query from it")
    s = s.replace(_DATE_BOUNDS_EMPTY, "&game_date_gt={day}&game_date_lt={day}")
    return s.replace(_BATTER_FILTER, "")


DAY_SEARCH = _day_search()


class SavantStop(RuntimeError):
    """A 403 or a changed column set: the run stops, files already written stay."""


def day_url(day: str) -> str:
    return DAY_SEARCH.format(season=int(day[:4]), day=day)


def day_path(day: str, out_dir: Optional[Path] = None) -> Path:
    return Path(out_dir or OUT_DIR) / f"{day}.csv"


def _guard_out(out_dir: Path) -> None:
    o = Path(out_dir).resolve()
    s = Path(SWING_CACHE).resolve()
    if o == s or s in o.parents:
        raise SystemExit(f"refused: {o} is the Swing+ cache; savant_days writes "
                         ".cache/league_trends/savant_days")


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return r.read()


_last = 0.0


def _throttle(throttle_s: float) -> None:
    global _last
    dt = time.time() - _last
    if dt < throttle_s:
        time.sleep(throttle_s - dt)
    _last = time.time()


def parse_day(raw: bytes, day: str) -> tuple[list, int]:
    """(kept rows for ``day`` as lists in KEEP_COLS order, rows of another date
    refused). Raises SavantStop when a kept column is missing from the header."""
    text = raw.decode("utf-8-sig", errors="replace")
    if not text.strip():
        return [], 0
    rd = csv.reader(io.StringIO(text))
    try:
        header = next(rd)
    except StopIteration:
        return [], 0
    header = [h.strip().strip('"') for h in header]
    missing = [c for c in KEEP_COLS if c not in header]
    if missing:
        raise SavantStop(f"Savant column set changed for {day}: missing {missing}")
    pos = [header.index(c) for c in KEEP_COLS]
    gd = header.index("game_date")
    rows: list = []
    refused = 0
    for rec in rd:
        if not rec or len(rec) <= max(pos):
            continue
        if rec[gd] != day:
            refused += 1
            continue
        rows.append([rec[i] for i in pos])
    return rows, refused


def _write_csv_atomic(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(KEEP_COLS)
        w.writerows(rows)
    os.replace(tmp, path)


def fetch_day(day: str, *, out_dir: Optional[Path] = None,
              getter: Callable[[str], bytes] = _http_get,
              throttle_s: float = THROTTLE_S) -> dict:
    """Fetch one date and write its file. Returns {"day", "status", "rows",
    "swings", "refused", "error"}; status is written, empty or failed (the
    cached file, if any, untouched). Raises SavantStop on 403 or a changed
    column set."""
    od = Path(out_dir or OUT_DIR)
    _guard_out(od)
    _throttle(throttle_s)
    try:
        raw = getter(day_url(day))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise SavantStop(f"Savant answered 403 for {day}") from e
        return {"day": day, "status": "failed", "rows": 0, "swings": 0, "refused": 0,
                "error": f"HTTP {e.code}"}
    except Exception as e:                    # noqa: BLE001 - fail-soft by design
        return {"day": day, "status": "failed", "rows": 0, "swings": 0, "refused": 0,
                "error": f"{type(e).__name__}: {e}"[:200]}
    rows, refused = parse_day(raw, day)
    if not rows:
        return {"day": day, "status": "empty", "rows": 0, "swings": 0,
                "refused": refused, "error": None}
    _write_csv_atomic(day_path(day, od), rows)
    swings = sum(1 for r in rows if r[KEEP_COLS.index("bat_speed")] not in ("", None))
    return {"day": day, "status": "written", "rows": len(rows), "swings": swings,
            "refused": refused, "error": None}


def season_dates(season: int) -> list:
    """The season's regular-season game dates (US Eastern) from the payloads."""
    import mlbstats_games as G
    return G.season_game_dates(int(season))


def live_season() -> int:
    return date.today().year


def season_counts(season: int, out_dir: Optional[Path] = None) -> dict:
    """{dates, rows, swings, hitters, max_game_date} over a season's day files:
    swings are rows with a bat_speed; hitters are batters with one or more."""
    od = Path(out_dir or OUT_DIR)
    dates, rows, swings, hitters, last = 0, 0, 0, set(), None
    ib, iv = KEEP_COLS.index("batter"), KEEP_COLS.index("bat_speed")
    for p in sorted(od.glob(f"{int(season)}-*.csv")):
        dates += 1
        last = p.stem
        with open(p, encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh)
            next(rd, None)
            for rec in rd:
                rows += 1
                if len(rec) > iv and rec[iv] != "":
                    swings += 1
                    hitters.add(rec[ib])
    return {"dates": dates, "rows": rows, "swings": swings, "hitters": len(hitters),
            "max_game_date": last}


def write_manifest(seasons: Iterable[int], out_dir: Optional[Path] = None) -> dict:
    od = Path(out_dir or OUT_DIR)
    path = od / "manifest.json"
    try:
        man = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        man = {"seasons": {}}
    man.setdefault("seasons", {})
    for s in seasons:
        man["seasons"][str(int(s))] = season_counts(s, od)
    man["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    man["source"] = "baseballsavant statcast_search, one request per game date"
    man["columns"] = list(KEEP_COLS)
    od.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(man, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
    return man


def record_ingest(ok: bool, n_rows: int, message: str) -> None:
    """File one ingest-health row through the live pipeline module when one is
    running (run_monthly's _record_ingest); a standalone run prints instead.
    Never raises."""
    try:
        mod = sys.modules.get("run_monthly")
        if mod is None or not hasattr(mod, "_record_ingest"):
            main = sys.modules.get("__main__")
            mod = main if (main is not None and hasattr(main, "_record_ingest")) else None
        if mod is not None:
            mod._record_ingest(SOURCE, ok=ok, n_rows=n_rows, message=message)
    except Exception:                         # noqa: BLE001 - reporting never breaks a run
        log.debug("could not record ingest health for %s", SOURCE, exc_info=True)


def run(seasons: Iterable[int], *, out_dir: Optional[Path] = None,
        dates_for: Callable[[int], list] = season_dates,
        getter: Callable[[str], bytes] = _http_get,
        throttle_s: float = THROTTLE_S, echo: Callable = print) -> dict:
    """Fetch every date of the given seasons that has no file yet (a completed
    season's file is never refetched). Stops on SavantStop, keeping what
    landed. Returns {"results", "stopped", "manifest"}."""
    od = Path(out_dir or OUT_DIR)
    _guard_out(od)
    results: list = []
    stopped = None
    seasons = sorted(int(s) for s in seasons)
    try:
        for s in seasons:
            days = [d for d in dates_for(s) if not day_path(d, od).exists()]
            echo(f"savant_days: {s}: {len(days)} dates to fetch")
            for d in days:
                r = fetch_day(d, out_dir=od, getter=getter, throttle_s=throttle_s)
                results.append(r)
                echo(f"  {d} {r['status']} rows {r['rows']} swings {r['swings']}"
                     f" refused {r['refused']}" + (f" error {r['error']}" if r["error"] else ""))
    except SavantStop as e:
        stopped = str(e)
        echo(f"savant_days: STOPPED: {stopped}")
    man = write_manifest(seasons, od)
    written = sum(1 for r in results if r["status"] == "written")
    failed = [r["day"] for r in results if r["status"] == "failed"]
    rows = sum(r["rows"] for r in results)
    msg = (f"{written} dates written, {len(failed)} failed, "
           f"{sum(1 for r in results if r['status'] == 'empty')} empty"
           + (f"; stopped: {stopped}" if stopped else ""))
    record_ingest(ok=stopped is None and not failed, n_rows=rows, message=msg)
    echo(f"savant_days: {msg}")
    return {"results": results, "stopped": stopped, "manifest": man}


def main(argv=None) -> int:                 # pragma: no cover - the CLI
    ap = argparse.ArgumentParser(description="Savant bat-tracking day files.")
    ap.add_argument("--backfill", default="", help="comma list of seasons, e.g. 2024,2025,2026")
    a = ap.parse_args(argv)
    seasons = [int(x) for x in a.backfill.split(",") if x.strip()] or [live_season()]
    if any(s < FIRST_SEASON for s in seasons):
        ap.error(f"bat tracking begins in {FIRST_SEASON}")
    res = run(seasons)
    for s, c in sorted((res["manifest"].get("seasons") or {}).items()):
        print(f"{s}: {c['dates']} dates, {c['swings']:,} tracked swings, "
              f"{c['hitters']:,} hitters, through {c['max_game_date']}")
    return 2 if res["stopped"] else 0


if __name__ == "__main__":                  # pragma: no cover
    raise SystemExit(main())
