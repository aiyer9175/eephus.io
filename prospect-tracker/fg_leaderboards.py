# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""FanGraphs leaderboard inputs for the fWAR replica, one season at a time.

WHY THIS EXISTS (owner decisions 13 and 14a, 2026-09-11). The pitcher half of the
W1.1 replica (tools/fwar_replica_eval.py) could not clear its gate from disk
because two of FanGraphs' own inputs were not on disk: infield fly balls per
pitcher-season (the IFFB term of ifFIP) and FanGraphs' FIP park factor per
team-season. The owner approved pulling both from FanGraphs, and approved
FanGraphs CFraming as the catcher framing source (decision 13). This module is
the fetcher and the cache. It reads three things and nothing else:

  pitching      the major-league pitching leaderboard (stats=pit): IFFB, the
                CFraming earned on each pitcher's pitches (FanGraphs charges it
                back to him; fwar_frame convention 9), Start-IP, and the
                published FIP, IP, G, GS and WAR the replica is scored beside
  fielding      the major-league fielding leaderboard (stats=fld): CFraming on
                every catcher row
  park_factors  the Guts park-factor table (type=pf): the FIP column per club

NOT A SERVED INPUT. Nothing on the site reads this module in the patch that
added it. The one reader is the replica eval, and test_fg_leaderboards.py fails
if any other tracked module imports it. Promoting a column from here into a
served number is a separate, measured change.

THE TRANSPORT RULE, measured 2026-09-09 and again 2026-09-11. The FanGraphs
JSON endpoints answer a plain client with the library's default User-Agent. A
spoofed browser User-Agent is what draws the Cloudflare challenge (HTTP 403,
"Just a moment..."), so this module never sets one. Requests are throttled to at
most one per MIN_INTERVAL_S across the process.

  leaderboards  https://www.fangraphs.com/api/leaders/major-league/data
  park factors  https://www.fangraphs.com/api/tools/guts/data?type=pf&teamid=0
                (the JSON the /tools/guts page is rendered from; the old
                guts.aspx URL redirects to that HTML page)

SEASON-STAMPED, REFUSE ON SHAPE CHANGE. Every cached file is one (kind, season)
and records the season, the URL, the fetch time, the sha256 of the raw body and
whether the season was complete when it was fetched. A response is validated
BEFORE it is written: a missing column, a row from the wrong season, a page
that does not hold the whole season (totalCount above the rows returned), an
unmapped club name, or a value outside its physical range raises ShapeChanged
and leaves the previous cache untouched. A silent shape change is how a
column goes to zero without anyone noticing, so the refusal is the point.

CACHE POLICY. A season that was complete when fetched is never refetched
unless force=True. The live season's files are refetched after LIVE_TTL_S.
Readers (iffb, catcher_framing, fip_park_factors) read the cache ONLY and never
touch the network; they raise NotCached when a season is absent, so an offline
eval can say what it lacks instead of fetching behind the caller's back.

Usage:
    python fg_leaderboards.py --seasons 2011 2026            # fetch what is missing
    python fg_leaderboards.py --seasons 2025 --kinds pitching --force
    python fg_leaderboards.py --cache-dir PATH --keep-raw ...
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional

ROOT = Path(__file__).resolve().parent
CACHE_DIR = Path(os.environ.get("FG_CACHE_DIR") or (ROOT / ".cache" / "fangraphs"))

LEADERS_URL = "https://www.fangraphs.com/api/leaders/major-league/data"
GUTS_URL = "https://www.fangraphs.com/api/tools/guts/data"

#: Seconds between two requests to FanGraphs, process-wide.
MIN_INTERVAL_S = 1.0
#: How long a live-season file is trusted before a refetch.
LIVE_TTL_S = 20 * 3600
#: First season this module will fetch: the replica window starts in 2011.
FIRST_SEASON = 2002
SCHEMA = 1

KINDS = ("pitching", "fielding", "park_factors")


class ShapeChanged(RuntimeError):
    """A FanGraphs response no longer has the shape this module was written
    against. The cache is left as it was."""


class NotCached(LookupError):
    """The cache has no file for this (kind, season). Readers never fetch."""


# --------------------------------------------------------------------------
# Schemas: the columns each kind keeps, and the ones that must be present
# --------------------------------------------------------------------------

#: Kept per pitching row. Every one is required on every row (value may be null
#: only where NULLABLE says so).
PITCHING_COLUMNS = ("xMLBAMID", "playerid", "Season", "TeamName", "teamid",
                    "IP", "G", "GS", "TBF", "IFFB", "FB", "HR", "BB", "IBB", "HBP",
                    "SO", "FIP", "FIP-", "ERA", "WAR", "RAR", "Start-IP",
                    "Relief-IP", "gmLI", "CFraming")
PITCHING_NULLABLE = frozenset({"Start-IP", "Relief-IP", "gmLI", "FIP-", "ERA",
                               "FIP", "RAR", "WAR", "FB", "teamid", "TBF", "CFraming"})

FIELDING_COLUMNS = ("xMLBAMID", "playerid", "Season", "Pos", "TeamName", "teamid",
                    "Inn", "CFraming")
FIELDING_NULLABLE = frozenset({"CFraming", "teamid", "Inn"})

PARK_COLUMNS = ("Season", "Team", "Basic (5yr)", "1yr", "3yr", "HR", "SO", "BB",
                "IFFB", "FIP")
PARK_NULLABLE = frozenset()

#: FanGraphs club name (Guts table) -> StatsAPI team id. FanGraphs names clubs by
#: nickname and follows renames; both names of a renamed club map to one id.
FG_CLUB_TO_TEAM_ID: Mapping[str, int] = {
    "Angels": 108, "Astros": 117, "Athletics": 133, "Blue Jays": 141,
    "Braves": 144, "Brewers": 158, "Cardinals": 138, "Cubs": 112,
    "Diamondbacks": 109, "D-backs": 109, "Dodgers": 119, "Giants": 137,
    "Guardians": 114, "Indians": 114, "Cleveland": 114, "Mariners": 136,
    "Marlins": 146, "Mets": 121, "Nationals": 120, "Orioles": 110, "Padres": 135,
    "Phillies": 143, "Pirates": 134, "Rangers": 140, "Rays": 139,
    "Red Sox": 111, "Reds": 113, "Rockies": 115, "Royals": 118,
    "Tigers": 116, "Twins": 142, "White Sox": 145, "Yankees": 147,
}

#: Physical ranges. A value outside one is a unit or column change, not a park.
PF_RANGE = (75.0, 130.0)
IFFB_LEAGUE_PER_IP = (0.04, 0.25)
#: Row-count bands per season (MLB 2002-2026 is 600-1,000 pitchers, 1,500-2,500
#: player-position fielding rows). 2020's short season sits inside both.
PITCHING_ROWS = (400, 2500)
FIELDING_ROWS = (800, 4000)
CATCHER_ROWS = (40, 300)


def _num(v) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def fg_ip(x) -> float:
    """FanGraphs innings (195.1 = 195 and one out) as true innings."""
    f = _num(x) or 0.0
    whole = int(f)
    return whole + round((f - whole) * 10) / 3.0


# --------------------------------------------------------------------------
# Validation: raise ShapeChanged, never repair
# --------------------------------------------------------------------------

def _rows_of(blob, kind: str) -> list:
    """The row list of a response. Leaderboards answer {"data": [...],
    "totalCount": n}; the Guts endpoint answers a bare list."""
    if kind == "park_factors":
        if not isinstance(blob, list):
            raise ShapeChanged(f"{kind}: expected a JSON list, got {type(blob).__name__}")
        return blob
    if not isinstance(blob, dict) or not isinstance(blob.get("data"), list):
        raise ShapeChanged(f"{kind}: expected an object with a 'data' list")
    rows = blob["data"]
    total = blob.get("totalCount")
    if not isinstance(total, int):
        raise ShapeChanged(f"{kind}: 'totalCount' missing or not an integer")
    if total != len(rows):
        raise ShapeChanged(f"{kind}: page holds {len(rows)} of totalCount {total}; "
                           f"the season did not fit one page")
    return rows


def _check_columns(rows: list, cols, nullable, kind: str, season: int) -> None:
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            raise ShapeChanged(f"{kind} {season}: row {i} is not an object")
        miss = [c for c in cols if c not in r]
        if miss:
            raise ShapeChanged(f"{kind} {season}: row {i} lacks {miss}")
        nulls = [c for c in cols if c not in nullable and r.get(c) is None]
        if nulls:
            raise ShapeChanged(f"{kind} {season}: row {i} has null {nulls}")
        if int(_num(r.get("Season")) or -1) != int(season):
            raise ShapeChanged(f"{kind} {season}: row {i} is season {r.get('Season')!r}")


def validate_pitching(blob, season: int) -> list[dict]:
    rows = _rows_of(blob, "pitching")
    if not (PITCHING_ROWS[0] <= len(rows) <= PITCHING_ROWS[1]):
        raise ShapeChanged(f"pitching {season}: {len(rows)} rows outside {PITCHING_ROWS}")
    _check_columns(rows, PITCHING_COLUMNS, PITCHING_NULLABLE, "pitching", season)
    ids = [r["xMLBAMID"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ShapeChanged(f"pitching {season}: an MLBAM id appears twice (split rows?)")
    tot_ip = tot_iffb = 0.0
    for r in rows:
        ip, iffb = fg_ip(r["IP"]), _num(r["IFFB"])
        tbf = _num(r.get("TBF")) or 0.0
        # an infield fly is one batter's plate appearance: never more of them
        # than batters faced (or outs recorded, where TBF is absent)
        if iffb is None or iffb < 0 or iffb > max(tbf, 3.0 * ip):
            raise ShapeChanged(f"pitching {season}: IFFB {r['IFFB']!r} on {ip:.1f} IP, "
                               f"{tbf:.0f} TBF (mlbam {r['xMLBAMID']}) is outside its range")
        tot_ip += ip
        tot_iffb += iffb
    if not any(_num(r.get("CFraming")) for r in rows):
        raise ShapeChanged(f"pitching {season}: CFraming is null or zero on every pitcher")
    # the league rate is about a tenth of an infield fly per inning; a rate
    # outside this band is a unit or column change
    if tot_ip <= 0 or not (IFFB_LEAGUE_PER_IP[0] <= tot_iffb / tot_ip <= IFFB_LEAGUE_PER_IP[1]):
        raise ShapeChanged(f"pitching {season}: league IFFB per IP "
                           f"{(tot_iffb / tot_ip) if tot_ip else float('nan'):.4f} "
                           f"outside {IFFB_LEAGUE_PER_IP}")
    return [{c: r[c] for c in PITCHING_COLUMNS} for r in rows]


def validate_fielding(blob, season: int) -> list[dict]:
    rows = _rows_of(blob, "fielding")
    if not (FIELDING_ROWS[0] <= len(rows) <= FIELDING_ROWS[1]):
        raise ShapeChanged(f"fielding {season}: {len(rows)} rows outside {FIELDING_ROWS}")
    _check_columns(rows, FIELDING_COLUMNS, FIELDING_NULLABLE, "fielding", season)
    catchers = [r for r in rows if r.get("Pos") == "C"]
    if not (CATCHER_ROWS[0] <= len(catchers) <= CATCHER_ROWS[1]):
        raise ShapeChanged(f"fielding {season}: {len(catchers)} catcher rows outside {CATCHER_ROWS}")
    if not any(_num(r.get("CFraming")) for r in catchers):
        raise ShapeChanged(f"fielding {season}: CFraming is null or zero on every catcher")
    return [{c: r[c] for c in FIELDING_COLUMNS} for r in rows]


def validate_park_factors(blob, season: int) -> list[dict]:
    rows = _rows_of(blob, "park_factors")
    if len(rows) != 30:
        raise ShapeChanged(f"park_factors {season}: {len(rows)} clubs, expected 30")
    _check_columns(rows, PARK_COLUMNS, PARK_NULLABLE, "park_factors", season)
    seen = set()
    for r in rows:
        tid = FG_CLUB_TO_TEAM_ID.get(str(r["Team"]).strip())
        if tid is None:
            raise ShapeChanged(f"park_factors {season}: unmapped club {r['Team']!r}")
        if tid in seen:
            raise ShapeChanged(f"park_factors {season}: club {r['Team']!r} maps to a team twice")
        seen.add(tid)
        for c in ("Basic (5yr)", "FIP"):
            v = _num(r[c])
            if v is None or not (PF_RANGE[0] <= v <= PF_RANGE[1]):
                raise ShapeChanged(f"park_factors {season}: {r['Team']} {c} = {r[c]!r} "
                                   f"outside {PF_RANGE}")
    return [dict({c: r[c] for c in PARK_COLUMNS},
                 team_id=FG_CLUB_TO_TEAM_ID[str(r["Team"]).strip()]) for r in rows]


VALIDATORS: Mapping[str, Callable] = {
    "pitching": validate_pitching,
    "fielding": validate_fielding,
    "park_factors": validate_park_factors,
}


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------

def request_for(kind: str, season: int) -> tuple[str, dict]:
    """(url, params) for one (kind, season). One call returns the whole season."""
    season = int(season)
    if kind == "park_factors":
        return GUTS_URL, {"type": "pf", "teamid": 0, "season": season}
    stats = {"pitching": "pit", "fielding": "fld"}[kind]
    return LEADERS_URL, {
        "age": "", "pos": "all", "stats": stats, "lg": "all", "qual": 0,
        "season": season, "season1": season, "startdate": "", "enddate": "",
        "month": 0, "hand": "", "team": 0, "pageitems": 5000, "pagenum": 1,
        "ind": 0, "rost": 0, "players": "", "type": 8, "postseason": "",
        "sortdir": "default", "sortstat": "WAR" if kind == "pitching" else "Defense",
    }


_LOCK = threading.Lock()
_LAST_REQUEST = [0.0]


def _throttle() -> None:
    with _LOCK:
        wait = MIN_INTERVAL_S - (time.monotonic() - _LAST_REQUEST[0])
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST[0] = time.monotonic()


def _http_get(url: str, params: dict, timeout: float = 90.0) -> tuple[int, bytes, str]:
    """(status, body, final url). The library's default User-Agent on purpose:
    a spoofed browser User-Agent is what draws FanGraphs' Cloudflare challenge."""
    import requests                      # noqa: PLC0415 - network only when fetching
    _throttle()
    r = requests.get(url, params=params, timeout=timeout)
    return r.status_code, r.content, r.url


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------

def _dir(cache_dir: Optional[Path]) -> Path:
    return Path(cache_dir) if cache_dir is not None else CACHE_DIR


def cache_path(kind: str, season: int, cache_dir: Optional[Path] = None) -> Path:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; use one of {KINDS}")
    return _dir(cache_dir) / f"{kind}_{int(season)}.json"


def season_complete(season: int, today: Optional[date] = None) -> bool:
    """A season is complete from November 1 of its year: the regular season and
    the postseason are over, and FanGraphs' end-of-season numbers have settled."""
    today = today or date.today()
    return (int(season), 11, 1) <= (today.year, today.month, today.day)


def is_fresh(doc: dict, now: Optional[float] = None) -> bool:
    """A complete season's file never expires; a live one expires after LIVE_TTL_S."""
    if doc.get("complete"):
        return True
    try:
        t = datetime.fromisoformat(doc["fetched_at"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return False
    return ((now if now is not None else time.time()) - t) < LIVE_TTL_S


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def fetch(kind: str, season: int, *, force: bool = False,
          cache_dir: Optional[Path] = None, keep_raw: bool = False,
          today: Optional[date] = None,
          http_get: Callable[..., tuple] = None) -> dict:
    """Return the cached document for (kind, season), fetching it when it is
    missing, when a live-season copy has expired, or when force=True.

    The response is validated before anything is written; ShapeChanged leaves
    the previous file in place. `http_get` is the test seam."""
    season = int(season)
    if season < FIRST_SEASON:
        raise ValueError(f"season {season} precedes FIRST_SEASON {FIRST_SEASON}")
    path = cache_path(kind, season, cache_dir)
    if path.exists() and not force:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("schema") == SCHEMA and is_fresh(doc):
            return doc
    url, params = request_for(kind, season)
    status, body, final = (http_get or _http_get)(url, params)
    if status != 200:
        raise RuntimeError(f"fangraphs {kind} {season}: HTTP {status} from {final}")
    try:
        blob = json.loads(body)
    except ValueError as exc:
        head = body[:80].decode("utf-8", "replace") if isinstance(body, bytes) else str(body)[:80]
        raise ShapeChanged(f"{kind} {season}: body is not JSON ({head!r})") from exc
    rows = VALIDATORS[kind](blob, season)
    raw = body if isinstance(body, bytes) else str(body).encode("utf-8")
    doc = {
        "schema": SCHEMA, "kind": kind, "season": season,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "complete": season_complete(season, today),
        "url": final, "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_bytes": len(raw), "n_rows": len(rows),
        "columns": list(PARK_COLUMNS) + ["team_id"] if kind == "park_factors"
        else list(PITCHING_COLUMNS if kind == "pitching" else FIELDING_COLUMNS),
        "rows": rows,
    }
    if keep_raw:
        _write_atomic(path.with_name(f"{kind}_{season}.raw.json"), raw.decode("utf-8"))
    _write_atomic(path, json.dumps(doc, separators=(",", ":")) + "\n")
    return doc


def load(kind: str, season: int, cache_dir: Optional[Path] = None) -> dict:
    """The cached document, never the network. NotCached when absent."""
    path = cache_path(kind, season, cache_dir)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise NotCached(f"no cached FanGraphs {kind} for {season} at {path}") from None
    if doc.get("schema") != SCHEMA or doc.get("season") != int(season) or doc.get("kind") != kind:
        raise ShapeChanged(f"cached {kind} {season} at {path} is not schema {SCHEMA}")
    return doc


# --------------------------------------------------------------------------
# Readers (cache only)
# --------------------------------------------------------------------------

def pitcher_iffb(season: int, cache_dir: Optional[Path] = None) -> dict[int, float]:
    """{mlbam: IFFB} season totals (one row per pitcher on the leaderboard)."""
    return {int(r["xMLBAMID"]): float(_num(r["IFFB"]) or 0.0)
            for r in load("pitching", season, cache_dir)["rows"]}


def pitcher_rows(season: int, cache_dir: Optional[Path] = None) -> dict[int, dict]:
    """{mlbam: row} of the pitching leaderboard (published FIP, IP, Start-IP, WAR)."""
    return {int(r["xMLBAMID"]): r for r in load("pitching", season, cache_dir)["rows"]}


def pitcher_framing(season: int, cache_dir: Optional[Path] = None) -> dict[int, float]:
    """{mlbam: CFraming runs earned on the pitcher's own pitches} from the
    PITCHING leaderboard. FanGraphs charges these back to the pitcher (the
    catcher is credited them inside Fielding); fwar_frame convention 9."""
    return {int(r["xMLBAMID"]): float(_num(r.get("CFraming")) or 0.0)
            for r in load("pitching", season, cache_dir)["rows"]}


def catcher_framing(season: int, cache_dir: Optional[Path] = None) -> dict[int, float]:
    """{mlbam: CFraming runs} summed over a player's catcher rows."""
    out: dict[int, float] = {}
    for r in load("fielding", season, cache_dir)["rows"]:
        if r.get("Pos") != "C":
            continue
        v = _num(r.get("CFraming"))
        if v is None:
            continue
        mid = int(r["xMLBAMID"])
        out[mid] = out.get(mid, 0.0) + v
    return out


def fip_park_factors(season: int, cache_dir: Optional[Path] = None) -> dict[int, float]:
    """{StatsAPI team id: FIP park factor as a decimal} (FanGraphs 99.2 -> 0.992)."""
    return {int(r["team_id"]): float(r["FIP"]) / 100.0
            for r in load("park_factors", season, cache_dir)["rows"]}


def basic_park_factors(season: int, cache_dir: Optional[Path] = None) -> dict[int, float]:
    """{StatsAPI team id: the Basic (5yr) runs park factor as a decimal}."""
    return {int(r["team_id"]): float(r["Basic (5yr)"]) / 100.0
            for r in load("park_factors", season, cache_dir)["rows"]}


def coverage(seasons, cache_dir: Optional[Path] = None) -> dict:
    """{kind: {season: {fetched_at, complete, n_rows} | None}} for a report."""
    out: dict = {}
    for kind in KINDS:
        out[kind] = {}
        for s in seasons:
            try:
                d = load(kind, s, cache_dir)
                out[kind][str(s)] = {"fetched_at": d["fetched_at"], "complete": d["complete"],
                                     "n_rows": d["n_rows"], "raw_sha256": d["raw_sha256"]}
            except (NotCached, ShapeChanged):
                out[kind][str(s)] = None
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", nargs=2, type=int, required=True, metavar=("FIRST", "LAST"))
    ap.add_argument("--kinds", nargs="*", default=list(KINDS), choices=KINDS)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--cache-dir")
    ap.add_argument("--keep-raw", action="store_true", help="also write the raw response body")
    args = ap.parse_args(argv)
    cd = Path(args.cache_dir) if args.cache_dir else None
    bad = 0
    for s in range(args.seasons[0], args.seasons[1] + 1):
        for kind in args.kinds:
            try:
                d = fetch(kind, s, force=args.force, cache_dir=cd, keep_raw=args.keep_raw)
                print(f"{kind:13s} {s}  rows {d['n_rows']:5d}  complete {d['complete']}  "
                      f"fetched {d['fetched_at']}")
            except (ShapeChanged, RuntimeError) as exc:
                bad += 1
                print(f"{kind:13s} {s}  REFUSED: {exc}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
