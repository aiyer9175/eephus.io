# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Baseball Savant catcher blocking and throwing: DISPLAY columns for the Defense board.

WHY THIS EXISTS
    The /mlbstats/ Defense board showed a catcher's framing (FanGraphs, owner
    decision 13) and nothing else a catcher does. ewar.py, positional_fit.py and
    savant_oaa.py all recorded the catcher boards as unanswerable. That was true
    of the one path probed (/leaderboard/catcher-framing ignores its season), not
    of Savant's catcher boards in general. These two resolve by season and stamp
    it on every row (start_year), measured 2026-09-25:
        /leaderboard/catcher-blocking   2024: 98 rows, 2026: 111 rows (n=1)
        /leaderboard/catcher-throwing   2024: 94 rows, 2026: 108 rows (n=1)

DISPLAY ONLY
    Nothing here feeds DEM+, eWAR, Position Fit, the team rollups or the betting
    model. Framing stays FanGraphs' CFraming. Adding blocking or throwing runs to
    DEM+ changes a validated metric and needs a registered attempt; a catcher arm
    in positional_fit is a new model and needs a gate. No club total of these
    columns is built here (see dem_plus.TEAM_ROLLUP_FRAMING for why club catcher
    totals are held).

REFUSALS
    A response missing a pinned field, or whose rows name another season, is
    refused: it never overwrites a good cache and joins nothing.

NETWORK MANNERS
    One request per board and season, >= 1 second apart, cached raw under
    .cache/savant_catcher/. The current season refreshes once a day; a past
    season is final. Every failure is soft. Nothing here raises.

Run:  python savant_catcher.py [season]
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
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache" / "savant_catcher"
SOURCE = "Baseball Savant catcher blocking and catcher throwing leaderboards"
UA = "eephus.io mlbstats display columns (arkndjl@gmail.com)"
LIVE_TTL_S = 24 * 3600
_MIN_INTERVAL = 1.05
_last_request = [0.0]

# n=1 keeps every catcher with a tracked chance; the served sample columns
# (c_blk_pitches, c_sb_att) say how thin each row is.
BOARDS = {
    "blocking": ("https://baseballsavant.mlb.com/leaderboard/catcher-blocking?game_type=Regular"
                 "&n=1&season_end={y}&season_start={y}&split=no&team=&type=Cat&with_score=1&csv=true"),
    "throwing": ("https://baseballsavant.mlb.com/leaderboard/catcher-throwing?game_type=Regular"
                 "&n=1&season_end={y}&season_start={y}&split=no&team=&type=Cat&csv=true"),
}
# served key -> (board, Savant field, decimals, what it counts).
COLUMNS = {
    "c_blk_pitches": ("blocking", "pitches", 0, "pitches received that the blocking model scores"),
    "c_blk_runs": ("blocking", "catcher_blocking_runs", 0, "runs saved by blocking, Savant's own run value"),
    "c_blk_aa": ("blocking", "blocks_above_average", 0, "blocks above average on those pitches"),
    "c_sb_att": ("throwing", "sb_attempts", 0, "stolen-base attempts with him catching"),
    "c_cs_runs": ("throwing", "catcher_stealing_runs", 1, "runs saved on those attempts, Savant's own run value"),
    "c_cs_aa": ("throwing", "caught_stealing_above_average", 1, "caught stealing above the expected count"),
    "c_pop": ("throwing", "pop_time", 2, "average pop time to second base, seconds"),
    "c_exchange": ("throwing", "exchange_time", 2, "average exchange time, seconds"),
    "c_arm": ("throwing", "arm_strength", 1, "average arm strength on throws, mph"),
}


def _fields(board: str) -> tuple:
    return tuple(spec[1] for spec in COLUMNS.values() if spec[0] == board)


def _throttle() -> None:
    wait = _MIN_INTERVAL - (time.monotonic() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.monotonic()


def cache_path(season: int, board: str) -> Path:
    return CACHE_DIR / f"{board}_{int(season)}.csv"


def shape_ok(text: str, season: int, board: str) -> bool:
    """Every pinned field present and every row stamped with the asked season."""
    if not text or not text.strip():
        return False
    rdr = csv.DictReader(io.StringIO(text))
    head = set(rdr.fieldnames or ())
    if "player_id" not in head or "start_year" not in head:
        return False
    if any(f not in head for f in _fields(board)):
        return False
    n = 0
    for r in rdr:
        if str(r.get("start_year") or "").strip() != str(int(season)):
            return False
        n += 1
    return n > 0


def fetch_text(season: int, board: str, *, force: bool = False) -> str:
    path = cache_path(season, board)
    cached = ""
    if path.exists():
        try:
            cached = path.read_text(encoding="utf-8-sig")
        except OSError:
            cached = ""
    fresh = False
    if cached:
        try:
            fresh = (int(season) < _dt.date.today().year
                     or (time.time() - path.stat().st_mtime) < LIVE_TTL_S)
        except OSError:
            fresh = False
    if cached and fresh and not force and shape_ok(cached, season, board):
        return cached
    try:
        _throttle()
        req = urllib.request.Request(BOARDS[board].format(y=int(season)),
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8-sig", errors="replace")
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        print(f"  [warn] savant catcher {board} {season} fetch failed ({exc}); using cache")
        return cached if shape_ok(cached, season, board) else ""
    if not shape_ok(text, season, board):
        print(f"  [warn] savant catcher {board} {season}: response shape changed; refused")
        return cached if shape_ok(cached, season, board) else ""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
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
    out: dict[int, dict] = {}
    if not text:
        return out
    for r in csv.DictReader(io.StringIO(text)):
        try:
            out[int(r["player_id"])] = r
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _fetched_at(season: int, board: str) -> Optional[str]:
    try:
        ts = cache_path(season, board).stat().st_mtime
    except OSError:
        return None
    return _dt.datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def join(rows: list[dict], season: int, *,
         loader: Optional[Callable[[int, str], str]] = None) -> dict:
    """Stamp the catcher columns onto rows whose primary position is C, by mlbam.

    Returns the provenance block the Defense payload serves as savant_catcher."""
    load = loader or fetch_text
    raw = {b: parse(load(int(season), b)) for b in BOARDS}
    catchers = [r for r in rows if r.get("pos") == "C"]
    n_join = {b: 0 for b in BOARDS}
    n_join_q = {b: 0 for b in BOARDS}
    for r in catchers:
        try:
            mid = int(r.get("mlbam"))
        except (TypeError, ValueError):
            continue
        for b in BOARDS:
            src = raw[b].get(mid)
            if not src:
                continue
            hit = False
            for key, (board, field, dec, _what) in COLUMNS.items():
                if board != b:
                    continue
                v = _num(src.get(field))
                if v is None:
                    continue
                r[key] = int(round(v)) if dec == 0 else round(v, dec)
                hit = True
            if hit:
                n_join[b] += 1
                if r.get("qualified"):
                    n_join_q[b] += 1
    return {
        "available": all(raw[b] for b in BOARDS),
        "source": SOURCE,
        "source_urls": {b: u.format(y=int(season)) for b, u in BOARDS.items()},
        "season": int(season),
        "fetched_at": ({b: _fetched_at(int(season), b) for b in BOARDS}
                       if loader is None else None),
        "n_source_rows": {b: len(raw[b]) for b in BOARDS},
        "n_catchers": len(catchers),
        "n_catchers_qualified": sum(1 for r in catchers if r.get("qualified")),
        "n_joined": n_join,
        "n_joined_qualified": n_join_q,
        "columns": {k: {"board": v[0], "field": v[1], "counts": v[3]} for k, v in COLUMNS.items()},
        "scope": "rows whose primary position is C",
        "use": "display only; DEM+, eWAR, Position Fit and the team rollups do not read these columns",
    }


def main(argv: list[str]) -> int:
    season = int(argv[1]) if len(argv) > 1 else _dt.date.today().year
    for b in BOARDS:
        print(f"  {b} {season}: {len(parse(fetch_text(season, b, force=True)))} catchers")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
