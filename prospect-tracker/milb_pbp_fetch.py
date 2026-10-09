# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MiLB pitch-by-pitch fetch for eFV v4 (task EFV4_PBP_CENSUS_AND_PILOT_FETCH; owner
2026-10-08, decisions EW2-8 to EW2-12; research s2.1 of the eFV v4 lane).

WHAT IT KEEPS. For every final regular-season MiLB game of a (level, season) cell the
StatsAPI `/api/v1/game/{gamePk}/playByPlay` payload (read with a `fields` filter, so the
transfer is about a sixth of the full feed) is reduced to compact per-pitch rows and
written, gzip-compressed and game_pk keyed, to

    .cache/efv4_pbp/{sportId}/{season}/{gamePk}.json.gz

one file per game, so the fetch is resumable (a cached game is never fetched again).
A game already held by the shared `/feed/live` cache (feed_cache.CACHE_DIR, final
feeds only) is reduced from that file instead of the network; that cache is read,
never written.

ROW SHAPE (columnar, see PA_COLS and PITCH_COLS): one PA row per plate appearance
(atBatIndex, batter id, pitcher id, eventType, inning, top/bottom) and one pitch row
per pitch event (atBatIndex, pitchNumber, call code, the count before the pitch, the
count after it, and on a ball in play the hitData trajectory, hardness, fielder
location and field coordinates). Ids are the play's MLBAM ids; no name is stored and
no name resolver is called.

LEAKAGE GUARD. The fetch reads no WAR, debut or label column and writes under .cache
only. It knows nothing of any frame: which seasons a frame may read is the arm's rule
(seasons ended before V-01-01), applied downstream. milb_pbp_census.py marks the
result-only (level, season) cells so downstream columns are withheld there.

FETCH RULE (EW2-11). Network reads only on FETCH_DATES (local calendar), never while
the UTC clock is inside BLACKOUT_UTC_HOURS, at most MAX_WORKERS (4) concurrent requests,
a descriptive User-Agent, retry with backoff on 429 and 5xx (Retry-After honoured).
Outside the window every network call raises FetchWindowClosed; cache reads still work.

Usage:
    python milb_pbp_fetch.py --plan                   # cells the census marks full
    python milb_pbp_fetch.py --run [--max-minutes N]  # fetch them, level by level,
                                                      # newest season first
    python milb_pbp_fetch.py --run --sport 11 --season 2016
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / ".cache" / "efv4_pbp"
FEED_CACHE_DIR = HERE / ".cache" / "game_feeds"
CENSUS_PATH = HERE / "data" / "_labs" / "efv_w2" / "pbp_census.json"

API = "https://statsapi.mlb.com/api/v1"
USER_AGENT = ("BaseballR-prospect-tracker eFV-v4 MiLB pitch-event research fetch "
              "(one-off, 4 connections max, resumable cache)")

#: StatsAPI sport ids and the level each names in the 2006 to 2025 seasons.
SPORTS: dict[int, str] = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 15: "A-", 16: "ROK"}
#: Fetch order: level by level, top of the ladder first.
LEVEL_ORDER: tuple[int, ...] = (11, 12, 13, 14, 15, 16)
NO_SEASON = frozenset({2020})

MAX_WORKERS = 4
FETCH_DATES = frozenset({date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 10)})
BLACKOUT_UTC_HOURS = range(6, 11)
_REQUEST_SLEEP = 0.05

PBP_FIELDS = ",".join((
    "allPlays", "result", "eventType", "about", "atBatIndex", "inning", "isTopInning",
    "matchup", "batter", "pitcher", "id", "playEvents", "isPitch", "pitchNumber",
    "details", "call", "code", "count", "balls", "strikes", "outs", "hitData",
    "trajectory", "hardness", "location", "coordinates", "coordX", "coordY",
))
SCHEDULE_FIELDS = ",".join((
    "dates", "date", "games", "gamePk", "gameType", "officialDate", "status",
    "abstractGameState", "detailedState", "codedGameState", "teams", "home", "away",
    "team", "id", "league",
))
#: Leagues left out of every pool: the Mexican League carried the AAA classification
#: (sport id 11) through 2020 but is not an affiliated league.
EXCLUDED_LEAGUES: dict[int, str] = {125: "Mexican League (AAA-classified, unaffiliated)"}

PA_COLS = ("ab", "batter", "pitcher", "event", "inning", "top")
PITCH_COLS = ("ab", "n", "code", "b0", "s0", "b1", "s1", "traj", "hard", "loc", "x", "y")
ROW_VERSION = 1


class FetchWindowClosed(RuntimeError):
    """A network read was attempted outside the EW2-11 fetch window."""


def fetch_window_open(now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local_day = now.astimezone().date()
    if local_day not in FETCH_DATES:
        return False, f"local date {local_day} is not a fetch date ({sorted(map(str, FETCH_DATES))})"
    utc_hour = now.astimezone(timezone.utc).hour
    if utc_hour in BLACKOUT_UTC_HOURS:
        return False, f"UTC hour {utc_hour:02d} is inside the 06:00 to 11:00 UTC blackout"
    return True, "open"


def _guard() -> None:
    ok, why = fetch_window_open()
    if not ok:
        raise FetchWindowClosed(why)


_session_lock = threading.Lock()
_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    with _session_lock:
        if _session is None:
            s = requests.Session()
            retry = Retry(total=6, backoff_factor=1.0,
                          status_forcelist=[429, 500, 502, 503, 504],
                          allowed_methods=frozenset({"GET"}),
                          respect_retry_after_header=True)
            ad = HTTPAdapter(max_retries=retry, pool_connections=MAX_WORKERS,
                             pool_maxsize=MAX_WORKERS)
            s.mount("https://", ad)
            s.headers["User-Agent"] = USER_AGENT
            _session = s
        return _session


def _get_json(url: str, params: dict) -> dict:
    _guard()
    time.sleep(_REQUEST_SLEEP)
    r = session().get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


# --------------------------------------------------------------------------- io

def _atomic_write_gz(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(gzip.compress(json.dumps(obj, separators=(",", ":")).encode("utf-8"), 6))
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        if not path.exists():
            raise


def read_gz(path: Path):
    with gzip.open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def game_path(sport: int, season: int, game_pk: int, cache_dir: Path | None = None) -> Path:
    return (cache_dir or CACHE_DIR) / str(int(sport)) / str(int(season)) / f"{int(game_pk)}.json.gz"


# --------------------------------------------------------------------- schedule

def schedule(sport: int, season: int, *, cache_dir: Path | None = None) -> list[dict]:
    """Final regular-season games of one (sport, season): [{gamePk, date}], date
    ascending, one entry per gamePk (a suspended game keeps its completion date).
    Cached under {cache}/schedule/; a past season is final, so the cache is kept."""
    cache_dir = cache_dir or CACHE_DIR
    path = cache_dir / "schedule" / f"{int(sport)}_{int(season)}.v2.json.gz"
    if path.exists():
        return read_gz(path)
    data = _get_json(f"{API}/schedule", {
        "sportId": int(sport), "startDate": f"{int(season)}-02-15",
        "endDate": f"{int(season)}-11-30", "gameType": "R", "hydrate": "team(league)",
        "fields": SCHEDULE_FIELDS})
    games: dict[int, dict] = {}
    for d in data.get("dates") or []:
        for g in d.get("games") or []:
            st = g.get("status") or {}
            final = (st.get("abstractGameState") == "Final"
                     and st.get("detailedState") not in {"Postponed", "Cancelled", "Suspended"}
                     and st.get("codedGameState") not in {"D", "C", "U", "T"})
            if g.get("gameType") != "R" or not final:
                continue
            teams = g.get("teams") or {}
            home = (teams.get("home") or {}).get("team") or {}
            away = (teams.get("away") or {}).get("team") or {}
            league = (home.get("league") or {}).get("id")
            if league in EXCLUDED_LEAGUES or (away.get("league") or {}).get("id") in EXCLUDED_LEAGUES:
                continue
            pk = int(g["gamePk"])
            games[pk] = {"gamePk": pk, "date": g.get("officialDate") or d.get("date"),
                         "league": league, "home": home.get("id"), "away": away.get("id")}
    out = sorted(games.values(), key=lambda r: (r["date"] or "", r["gamePk"]))
    _atomic_write_gz(path, out)
    return out


# ----------------------------------------------------------------------- parse

def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 2)


def reduce_plays(all_plays: list[dict]) -> tuple[list[list], list[list]]:
    """Compact PA and pitch rows from a playByPlay `allPlays` list (see PA_COLS,
    PITCH_COLS). The count before a pitch is the count after the previous event of
    the same PA (any event, so an automatic ball or strike is honoured), 0-0 first."""
    pas: list[list] = []
    pitches: list[list] = []
    for i, play in enumerate(all_plays or []):
        about = play.get("about") or {}
        ab = play.get("atBatIndex", about.get("atBatIndex", i))
        mu = play.get("matchup") or {}
        pas.append([ab, (mu.get("batter") or {}).get("id"), (mu.get("pitcher") or {}).get("id"),
                    (play.get("result") or {}).get("eventType"), about.get("inning"),
                    1 if about.get("isTopInning") else 0])
        b0 = s0 = 0
        for ev in play.get("playEvents") or []:
            cnt = ev.get("count") or {}
            b1 = cnt.get("balls", b0)
            s1 = cnt.get("strikes", s0)
            if ev.get("isPitch"):
                det = ev.get("details") or {}
                code = (det.get("call") or {}).get("code") or det.get("code")
                hd = ev.get("hitData") or {}
                co = hd.get("coordinates") or {}
                pitches.append([ab, ev.get("pitchNumber"), code, b0, s0, b1, s1,
                                hd.get("trajectory"), hd.get("hardness"), hd.get("location"),
                                _num(co.get("coordX")), _num(co.get("coordY"))])
            b0, s0 = b1, s1
    return pas, pitches


def game_record(g: dict, sport: int, season: int, all_plays: list[dict], source: str) -> dict:
    pas, pitches = reduce_plays(all_plays)
    return {"v": ROW_VERSION, "gamePk": int(g["gamePk"]), "date": g.get("date"),
            "sportId": int(sport), "level": SPORTS.get(int(sport)), "season": int(season),
            "league": g.get("league"), "home": g.get("home"), "away": g.get("away"),
            "source": source,
            "pa_cols": list(PA_COLS), "pitch_cols": list(PITCH_COLS),
            "pa": pas, "pitches": pitches}


def _plays_from_feed_cache(game_pk: int) -> list[dict] | None:
    path = FEED_CACHE_DIR / f"{int(game_pk)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    st = ((data.get("gameData") or {}).get("status") or {})
    if st.get("abstractGameState") != "Final" or st.get("detailedState") in {"Suspended", "Postponed"}:
        return None
    plays = ((data.get("liveData") or {}).get("plays") or {}).get("allPlays")
    return plays if plays else None


def fetch_game(sport: int, season: int, g: dict, *,
               cache_dir: Path | None = None) -> tuple[str, int]:
    """Ensure one game's compact rows are cached (`g` is a schedule entry). Returns
    (status, n_pitches) with status in {'cached', 'feed_cache', 'fetched'}."""
    game_pk = int(g["gamePk"])
    path = game_path(sport, season, game_pk, cache_dir)
    if path.exists():
        return "cached", -1
    plays = _plays_from_feed_cache(game_pk)
    source = "feed_cache"
    if plays is None:
        data = _get_json(f"{API}/game/{int(game_pk)}/playByPlay", {"fields": PBP_FIELDS})
        plays = data.get("allPlays") or []
        source = "playByPlay"
    rec = game_record(g, sport, season, plays, source)
    _atomic_write_gz(path, rec)
    return ("feed_cache" if source == "feed_cache" else "fetched"), len(rec["pitches"])


# ------------------------------------------------------------------------ plan

#: Seasons the development frames read (lv_dev list vintages 2011 to 2019 read 2009 to
#: 2018; vm_dev debut years 2017 to 2023 read through 2022; R-LV reads 2019). They are
#: fetched first; the R-VM-only seasons (2023 on) and AAA and AA 2007 to 2008 follow.
DEV_SEASONS = range(2009, 2023)


def plan_cells(census: dict | None = None) -> list[tuple[int, int]]:
    """(sport, season) cells to fetch: the census probe's `fetch` cells, dev seasons
    first, then the rest; inside each tier level by level in LEVEL_ORDER, newest
    season first."""
    if census is None:
        census = json.loads(CENSUS_PATH.read_text(encoding="utf-8"))
    cells = {(int(c["sportId"]), int(c["season"])) for c in census["probe"]["cells"] if c.get("fetch")}
    out = []
    for tier in (True, False):
        for sp in LEVEL_ORDER:
            ys = sorted((y for s, y in cells if s == sp and (y in DEV_SEASONS) == tier), reverse=True)
            out += [(sp, y) for y in ys]
    return out


def fetch_cell(sport: int, season: int, *, deadline: float | None = None,
               log=print, cache_dir: Path | None = None) -> dict:
    games = schedule(sport, season, cache_dir=cache_dir)
    todo = [g for g in games if not game_path(sport, season, g["gamePk"], cache_dir).exists()]
    stat = {"sportId": sport, "level": SPORTS[sport], "season": season,
            "scheduled_final": len(games), "cached_before": len(games) - len(todo),
            "fetched": 0, "feed_cache": 0, "failed": 0, "pitches_new": 0, "stopped": None}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        pending = iter(todo)
        futs = {}

        def _submit():
            g = next(pending, None)
            if g is None:
                return False
            futs[ex.submit(fetch_game, sport, season, g, cache_dir=cache_dir)] = g
            return True

        for _ in range(MAX_WORKERS * 2):
            if not _submit():
                break
        while futs:
            done = next(as_completed(list(futs)))
            g = futs.pop(done)
            try:
                status, n = done.result()
                if status == "fetched":
                    stat["fetched"] += 1
                elif status == "feed_cache":
                    stat["feed_cache"] += 1
                stat["pitches_new"] += max(n, 0)
            except FetchWindowClosed as e:
                stat["stopped"] = str(e)
            except Exception as e:  # noqa: BLE001 - a failed game is retried on the next run
                stat["failed"] += 1
                if stat["failed"] <= 5:
                    log(f"  fail {sport}/{season}/{g['gamePk']}: {type(e).__name__}: {e}")
            if stat["stopped"] or (deadline and time.time() > deadline):
                stat["stopped"] = stat["stopped"] or "deadline"
                continue
            _submit()
    stat["seconds"] = round(time.time() - t0, 1)
    return stat


def cached_count(sport: int, season: int, cache_dir: Path | None = None) -> int:
    d = (cache_dir or CACHE_DIR) / str(sport) / str(season)
    return len(list(d.glob("*.json.gz"))) if d.exists() else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--sport", type=int)
    ap.add_argument("--season", type=int)
    ap.add_argument("--max-minutes", type=float, default=None)
    ap.add_argument("--log", type=Path, default=None)
    a = ap.parse_args(argv)

    logf = open(a.log, "a", encoding="utf-8") if a.log else None

    def log(msg):
        line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        if logf:
            logf.write(line + "\n")
            logf.flush()

    cells = plan_cells()
    if a.sport:
        cells = [c for c in cells if c[0] == a.sport]
    if a.season:
        cells = [c for c in cells if c[1] == a.season]
    if a.plan or not a.run:
        for sp, y in cells:
            log(f"{SPORTS[sp]:>3} {y} cached {cached_count(sp, y)}")
        return 0
    ok, why = fetch_window_open()
    if not ok:
        log(f"fetch window closed: {why}")
        return 2
    deadline = time.time() + a.max_minutes * 60 if a.max_minutes else None
    for sp, y in cells:
        st = fetch_cell(sp, y, deadline=deadline, log=log)
        log(f"{st['level']:>3} {y}: final {st['scheduled_final']} cached_before "
            f"{st['cached_before']} fetched {st['fetched']} from_feed_cache {st['feed_cache']} "
            f"failed {st['failed']} pitches_new {st['pitches_new']} {st['seconds']}s"
            + (f" STOPPED {st['stopped']}" if st["stopped"] else ""))
        if st["stopped"]:
            return 3
    log("plan complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
