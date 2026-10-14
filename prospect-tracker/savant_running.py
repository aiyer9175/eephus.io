# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Baseball Savant baserunning boards: the published comparators eBR is checked against.

WHY THIS EXISTS
    docs/ebr-2026-09-30/EBR_GATE.md part 4 compares eBR, every build, with
    Savant's runner XB runs, runner total and basestealing run value (bug bands,
    never a gate on validity), and part 5.10 lets the one look read these caches
    and fetch nothing. FanGraphs' served BsR since 2016 is wSB plus Savant's
    runner_runs_XB (r 1.000), so for the non-steal part "agrees with FanGraphs"
    and "agrees with Savant" are one target.

THE BOARDS (one request per board and season, n=1, season_start = season_end)
    baserunning-run-value    runner_runs_tot, runner_runs_XB, runner_runs_SBX,
                             N_runner_moved, N_runner_moved_XB (2016 to 2026; the
                             2015 file is header only)
    basestealing-run-value   runs_stolen_on_running_act, n_init, n_sb, n_cs, n_pk
                             (target_base=All)
    Both stamp start_year on every row, so a response is checked against the
    asked season. Savant's plain baserunning board (the path with no run-value
    suffix) ignores its season and is never read here.

SPRINT SPEED
    The live season's sprint CSV goes through savant_sprint.fetch_raw and
    parse_rows, into the CSV cache that module already owns. data/savant_sprint.json
    (the Alchemy Lab's Rng+ reads it) is never written here: savant_sprint.build
    is not called.

REFUSALS
    A response missing a pinned field, or holding a row stamped with another
    season, is refused: it never overwrites a good cache and is read as empty.

NETWORK MANNERS
    One request per 1.1 s with the house User-Agent, cached raw under
    .cache/savant_running/{brv,steal}_<Y>.csv. A past season is final; the current
    season refreshes once a day. Every failure is soft. Nothing here raises.

DISPLAY AND CHECKS ONLY
    No model reads these boards. eBR does not train on them; the eval compares
    aggregates only and writes no per-player Savant value.

Run:  python savant_running.py [first [last]]     # warm 2016 to the current season
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache" / "savant_running"
SOURCE = "Baseball Savant baserunning run value and basestealing run value leaderboards"
UA = "eephus.io mlbstats display columns (arkndjl@gmail.com)"
FIRST_SEASON = 2016
LIVE_TTL_S = 24 * 3600
MIN_INTERVAL = 1.1
_last_request = [0.0]

BOARDS = {
    "brv": ("https://baseballsavant.mlb.com/leaderboard/baserunning-run-value?game_type=Regular"
            "&n=1&season_start={y}&season_end={y}&split=no&team=&type=Run&with_team_only=1&csv=true"),
    "steal": ("https://baseballsavant.mlb.com/leaderboard/basestealing-run-value?game_type=Regular"
              "&n=1&season_start={y}&season_end={y}&target_base=All&split=no&team=&type=Run"
              "&with_team_only=1&csv=true"),
}

#: Fields a response must carry, per board, or it is refused.
PINNED = {
    "brv": ("player_id", "start_year", "runner_runs_tot", "runner_runs_XB", "runner_runs_SBX",
            "N_runner_moved", "N_runner_moved_XB"),
    "steal": ("player_id", "start_year", "runs_stolen_on_running_act", "n_init", "n_sb",
              "n_cs", "n_pk"),
}


def _throttle() -> None:
    wait = MIN_INTERVAL - (time.monotonic() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.monotonic()


def cache_path(season: int, board: str) -> Path:
    return CACHE_DIR / f"{board}_{int(season)}.csv"


def shape_ok(text: str, season: int, board: str) -> bool:
    """Every pinned field present, at least one row, and every row stamped with
    the asked season (start_year and, where present, end_year)."""
    if not text or not text.strip():
        return False
    rdr = csv.DictReader(io.StringIO(text))
    head = set(rdr.fieldnames or ())
    if any(f not in head for f in PINNED[board]):
        return False
    n = 0
    want = str(int(season))
    for r in rdr:
        if str(r.get("start_year") or "").strip() != want:
            return False
        if "end_year" in head and str(r.get("end_year") or "").strip() not in ("", want):
            return False
        n += 1
    return n > 0


def _read_cache(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError:
        return ""


def fetch_text(season: int, board: str, *, force: bool = False, opener=None) -> str:
    """The board's CSV for one season: the cache when it is good and fresh, else
    one request. A failed or refused response keeps the cache."""
    path = cache_path(season, board)
    cached = _read_cache(path) if path.exists() else ""
    fresh = False
    if cached:
        try:
            fresh = (int(season) < _dt.date.today().year
                     or (time.time() - path.stat().st_mtime) < LIVE_TTL_S)
        except OSError:
            fresh = False
    if cached and fresh and not force and shape_ok(cached, season, board):
        return cached
    good_cache = cached if shape_ok(cached, season, board) else ""
    try:
        _throttle()
        req = urllib.request.Request(BOARDS[board].format(y=int(season)),
                                     headers={"User-Agent": UA})
        with (opener or urllib.request.urlopen)(req, timeout=60) as resp:
            text = resp.read().decode("utf-8-sig", errors="replace")
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        print(f"  [warn] savant running {board} {season} fetch failed ({exc}); using cache")
        return good_cache
    if not shape_ok(text, season, board):
        print(f"  [warn] savant running {board} {season}: response refused (shape or season)")
        return good_cache
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".csv.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass
    return text


def _num(v) -> Optional[float]:
    try:
        s = str(v).strip()
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def parse(text: str) -> dict[int, dict]:
    """{mlbam: {field: float or None}} over the pinned numeric fields of either board."""
    out: dict[int, dict] = {}
    if not text:
        return out
    for r in csv.DictReader(io.StringIO(text)):
        try:
            mid = int(r["player_id"])
        except (KeyError, TypeError, ValueError):
            continue
        out[mid] = {k: _num(v) for k, v in r.items()
                    if k not in ("player_id", "entity_name", "player_name", "team_name",
                                 "key_target_base") and k is not None}
    return out


def cached_text(season: int, board: str) -> str:
    """The cached CSV only (never a request): what the look reads."""
    path = cache_path(season, board)
    text = _read_cache(path) if path.exists() else ""
    return text if shape_ok(text, season, board) else ""


def fetched_at(season: int, board: str) -> Optional[str]:
    try:
        ts = cache_path(season, board).stat().st_mtime
    except OSError:
        return None
    return _dt.datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def load(season: int, *, offline: bool = False) -> dict:
    """{"brv": {mlbam: row}, "steal": {mlbam: row}, "fetched_at": {...}}."""
    get = cached_text if offline else fetch_text
    return {b: parse(get(int(season), b)) for b in BOARDS} | {
        "fetched_at": {b: fetched_at(int(season), b) for b in BOARDS}}


def sprint_rows(season: int, *, force: bool = False) -> list[dict]:
    """The season's sprint-speed rows through savant_sprint's own fetch and parse
    (its CSV cache); data/savant_sprint.json is never written here."""
    import savant_sprint
    return savant_sprint.parse_rows(savant_sprint.fetch_raw(int(season), force=force), int(season))


def main(argv: list[str]) -> int:
    first = int(argv[1]) if len(argv) > 1 else FIRST_SEASON
    last = int(argv[2]) if len(argv) > 2 else _dt.date.today().year
    for y in range(first, last + 1):
        for b in BOARDS:
            print(f"  {b} {y}: {len(parse(fetch_text(y, b)))} runners")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
