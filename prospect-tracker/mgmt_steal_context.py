#!/usr/bin/env python
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Runner speed and catcher pop time beside each priced steal: CONTEXT columns only.

WHAT IT IS (final-pass plan Part 8, 8.F P8.6, W11 stage 1; owner answer W-OQ3 (b),
2026-10-01). Two public numbers, joined to every steal row of the /management/
decision ledger and printed in the steal family view:

  runner   the runner's sprint-speed PERCENTILE for the season of the attempt:
           the share of that season's runners on Baseball Savant's sprint speed
           leaderboard (10 or more competitive runs, the floor savant_sprint.py
           pulls) who are slower than him, runners at his exact speed (himself
           included) counted as half, times 100, rounded to the nearest whole
           number. Read from the leaderboard CSV
           savant_sprint.py caches under .cache/savant_sprint/.
  catcher  the catcher's average pop time to second base that season, from
           Savant's catcher throwing leaderboard (savant_catcher.py, X05-02,
           cached under .cache/savant_catcher/). Which catcher was behind the
           plate is read off the win probability payload the play corpus is
           built from (.cache/win_prob/{game_pk}.json): every playEvent carries
           the fielding team's `defense.catcher`, and the steal's own event (or,
           for a steal that ends the plate appearance, the last event of it)
           names him.

WHAT IT IS NOT. Nothing here touches a decision value. management.py prices DV
with a LEAGUE-AVERAGE runner on purpose (its header, "WHY LEAGUE-AVERAGE AND NOT
THE RUNNER'S OWN RATE"), and the execution residual is realized minus that
expectation. These columns sit beside DV and ER and feed neither; the shards,
management_running.json and management_board.json are not read for any number
and never written. A runner-aware success model (W11 stage 2) needs its own gate
document before any number exists.

A BLANK SAYS WHY. A runner absent from that season's leaderboard (under 10
competitive runs, or a season with no leaderboard on file), an attempt whose
catcher could not be read, and a catcher with no pop time on the throwing board
each print an empty cell with a note; context_for() below is the Python twin of
the page's reader and the tests hold the two together.

NETWORK MANNERS. Completed seasons read the caches only. The open season's
sprint CSV is refetched when the cached copy is more than a day old, and the
throwing board keeps savant_catcher.py's own one-day TTL. A fetch that fails
falls back to the cache; a season that comes back empty keeps the previous
build's block for it (carried, and the payload says so). The catcher map of a
season is cached under .cache/mgmt_steal_context/ and seeded from the previous
build, so a box without the win probability cache keeps the committed map.

    python mgmt_steal_context.py            # every season with shards on disk
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import io
import json
import logging
import sys
import time
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "management_steal_context.json"
SHARD_DIR = ROOT / "data" / "mgmt_decisions"
WIN_PROB = ROOT / ".cache" / "win_prob"
CACHE_DIR = ROOT / ".cache" / "mgmt_steal_context"
#: The open season's sprint leaderboard is refetched once its cached copy is
#: older than this; the throwing board keeps savant_catcher.LIVE_TTL_S.
SPRINT_TTL_S = 24 * 3600

SPRINT_SOURCE = "Baseball Savant sprint speed leaderboard"
SPRINT_FLOOR = 10
POP_SOURCE = "Baseball Savant catcher throwing leaderboard"

USE = ("context only: the decision value (DV) is priced with a league-average runner on "
       "purpose, and the execution residual (ER) is realized minus that expectation; "
       "neither reads these columns")
PCT_DEFINITION = ("the share of that season's runners on the Savant sprint speed "
                  "leaderboard (10 or more competitive runs) who are slower, runners at "
                  "his exact speed (himself included) counted as half, times 100, rounded "
                  "to the nearest whole number")
POP_DEFINITION = ("the catcher's average pop time to second base that season, seconds, "
                  "from the Savant catcher throwing leaderboard; the catcher is the one the "
                  "MLB feed names behind the plate on the steal's own event")

#: Why a context cell is blank. {season} and {floor} are filled by context_for and
#: by the page; the payload carries these templates so the page types no sentence.
NOTES = {
    "no_sprint_board": "no Savant sprint speed leaderboard on file for {season}",
    "runner_not_listed": ("not on the {season} Savant sprint speed leaderboard, which lists "
                          "runners with {floor} or more competitive runs"),
    "no_season": "no catcher context on file for {season}",
    "no_catcher": "the MLB feed names no catcher on this attempt",
    "no_pop": "no pop time for this catcher on the {season} Savant catcher throwing leaderboard",
}

log = logging.getLogger("mgmt_steal_context")


# ----------------------------------------------------------------------------
# pure helpers (the tests drive these on fixtures)
# ----------------------------------------------------------------------------

def percentiles(speeds: dict) -> dict:
    """{mlbam: ft_s} -> {mlbam: percentile 0..100}, rounded to the nearest whole number.

    pct = 100 * (n slower + 0.5 * n at his speed, himself included) / n, the midrank
    share PCT_DEFINITION states. In a field of n distinct speeds the fastest runner
    reads 100 * (n - 0.5) / n and the slowest 50 / n; equal speeds share one value."""
    vals = [float(v) for v in speeds.values() if v is not None]
    n = len(vals)
    if not n:
        return {}
    srt = sorted(vals)
    import bisect
    out = {}
    for k, v in speeds.items():
        if v is None:
            continue
        v = float(v)
        below = bisect.bisect_left(srt, v)
        tied = bisect.bisect_right(srt, v) - below
        share = (below + 0.5 * tied) / n
        out[k] = int(round(100.0 * share + 1e-9))
    return out


def catcher_of(plays: list, ab: int) -> Optional[int]:
    """The catcher the feed names on a priced steal of plate appearance `ab`.

    A priced steal is the FIRST state-changing event of its plate appearance
    (management.attempts excludes any attempt with a prior one), so the first
    steal playEvent of the plate appearance is the attempt; a steal that ends the
    plate appearance is no playEvent, and its catcher is the one on the last
    event of the plate appearance. None when the payload names nobody."""
    import management as M
    play = None
    for p in plays or []:
        idx = p.get("atBatIndex")
        if idx is None:
            idx = (p.get("about") or {}).get("atBatIndex")
        if idx == ab:
            play = p
            break
    if play is None:
        return None
    evs = play.get("playEvents") or []
    for e in evs:
        if (e.get("details") or {}).get("eventType") in M.STEAL_EVENTS:
            cid = ((e.get("defense") or {}).get("catcher") or {}).get("id")
            if cid is not None:
                return int(cid)
            break
    for e in reversed(evs):
        cid = ((e.get("defense") or {}).get("catcher") or {}).get("id")
        if cid is not None:
            return int(cid)
    return None


def _note(key: str, season) -> str:
    return NOTES[key].replace("{season}", str(season)).replace("{floor}", str(SPRINT_FLOOR))


def context_for(row: dict, block: Optional[dict]) -> dict:
    """The two context cells of one steal row, as the page prints them.

    Returns {sp_pct, sp_fts, sp_note, c_id, c_name, pop, pop_note}; a value is
    None exactly when its note is set. The Python twin of stealContext() in
    assets/management.js, which reads the same templates off the payload's notes."""
    season = row.get("season")
    out = {"sp_pct": None, "sp_fts": None, "sp_note": None,
           "c_id": None, "c_name": None, "pop": None, "pop_note": None}
    if not block:
        out["sp_note"] = _note("no_sprint_board", season)
        out["pop_note"] = _note("no_season", season)
        return out
    runners = block.get("runners") or {}
    rid = row.get("in_id")
    rec = runners.get(str(rid)) if rid is not None else None
    if not (block.get("sprint") or {}).get("n_runners"):
        out["sp_note"] = _note("no_sprint_board", season)
    elif rec is None:
        out["sp_note"] = _note("runner_not_listed", season)
    else:
        out["sp_pct"], out["sp_fts"] = rec[0], rec[1]
    cid = (block.get("att") or {}).get(f"{row.get('game_pk')}:{row.get('ab')}")
    if cid is None:
        out["pop_note"] = _note("no_catcher", season)
        return out
    out["c_id"] = cid
    crec = (block.get("catchers") or {}).get(str(cid))
    if crec is not None:
        out["c_name"] = crec[2] if len(crec) > 2 else None
    if crec is None or crec[0] is None:
        out["pop_note"] = _note("no_pop", season)
    else:
        out["pop"] = crec[0]
    return out


# ----------------------------------------------------------------------------
# sources
# ----------------------------------------------------------------------------

def _mtime_iso(p: Path) -> Optional[str]:
    try:
        return _dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return None


def sprint_rows(season: int, *, open_season: int) -> tuple[list, Optional[str]]:
    """(rows, fetched_at) of one season's sprint leaderboard via savant_sprint."""
    import savant_sprint as ss
    path = ss._cache_path(int(season))
    force = False
    if int(season) >= int(open_season):
        try:
            force = (time.time() - path.stat().st_mtime) > SPRINT_TTL_S
        except OSError:
            force = True
    rows = ss.parse_rows(ss.fetch_raw(int(season), force=force), int(season))
    return rows, _mtime_iso(path)


def display_name(raw) -> Optional[str]:
    """Savant's "Last, First" as "First Last"; anything else as given."""
    s = str(raw or "").strip()
    if not s:
        return None
    last, sep, first = s.partition(", ")
    return f"{first} {last}" if sep and first else s


def pop_rows(season: int) -> tuple[dict, Optional[str]]:
    """({mlbam: [pop or None, sb_attempts, name]}, fetched_at) from the throwing board."""
    import savant_catcher as sc
    text = sc.fetch_text(int(season), "throwing")
    out = {}
    for r in csv.DictReader(io.StringIO(text or "")):
        try:
            mid = int(r["player_id"])
        except (KeyError, TypeError, ValueError):
            continue
        pop = sc._num(r.get("pop_time"))
        att = sc._num(r.get("sb_attempts"))
        out[str(mid)] = [round(pop, 2) if pop is not None else None,
                         int(round(att)) if att is not None else None,
                         display_name(r.get("player_name"))]
    return out, _mtime_iso(sc.cache_path(int(season), "throwing"))


def steal_rows_on_disk(shard_dir: Path | None = None) -> dict:
    """{season: [{game_pk, ab, in_id, season}]} for every steal row of every shard."""
    import mgmt_shards
    d = Path(shard_dir or SHARD_DIR)
    out: dict = {}
    for p in sorted(d.glob("*.json")):
        m = mgmt_shards._NAME_RE.match(p.name)
        if not m:
            continue
        try:
            sh = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        blk = (sh.get("families") or {}).get("steal")
        if not blk:
            continue
        keys = blk.get("keys") or []
        ix = {k: i for i, k in enumerate(keys)}
        for arr in blk.get("rows") or []:
            def cell(k):
                i = ix.get(k)
                return arr[i] if i is not None and i < len(arr) else None
            out.setdefault(int(m.group(1)), []).append(
                {"game_pk": cell("game_pk"), "ab": cell("ab"), "in_id": cell("in_id"),
                 "season": int(m.group(1))})
    return out


def _catcher_cache(season: int) -> Path:
    return CACHE_DIR / f"catchers_{int(season)}.json"


def attempt_catchers(season: int, rows: list, *, seed: dict | None = None,
                     win_prob: Path | None = None,
                     loader: Optional[Callable[[int], Optional[list]]] = None) -> dict:
    """{"game_pk:ab": catcher id} for the season's steal rows. Seeded from the
    previous build and the season cache; only keys missing from both are read off
    the win probability payloads, one file per game."""
    wp = Path(win_prob or WIN_PROB)
    got: dict = {}
    for src in (seed or {}, _read_json(_catcher_cache(season)) or {}):
        for k, v in src.items():
            if v is not None:
                got.setdefault(k, int(v))
    want: dict = {}
    for r in rows:
        k = f"{r['game_pk']}:{r['ab']}"
        if k not in got and r.get("game_pk") is not None:
            want.setdefault(int(r["game_pk"]), set()).add(int(r["ab"]))

    def _load(g: int):
        if loader is not None:
            return loader(g)
        try:
            return json.loads((wp / f"{g}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    for g, abs_ in sorted(want.items()):
        plays = _load(g)
        if not plays:
            continue
        for ab in sorted(abs_):
            cid = catcher_of(plays, ab)
            if cid is not None:
                got[f"{g}:{ab}"] = cid
    keys = {f"{r['game_pk']}:{r['ab']}" for r in rows}
    out = {k: got[k] for k in sorted(got) if k in keys}
    if want and loader is None:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _catcher_cache(season).write_text(json.dumps(out, separators=(",", ":")),
                                              encoding="utf-8")
        except OSError:
            pass
    return out


def _read_json(p: Path):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ----------------------------------------------------------------------------
# the build
# ----------------------------------------------------------------------------

def season_block(season: int, rows: list, *, sprint: tuple, pop: tuple, att: dict,
                 prev: dict | None = None) -> dict:
    """One season's block from its steal rows and the two sources. `sprint` is
    (rows, fetched_at) of savant_sprint.parse_rows; `pop` is ({id: [pop, att, name]},
    fetched_at). A source that returned nothing keeps `prev`'s copy (carried)."""
    prev = prev or {}
    s_rows, s_at = sprint
    p_map, p_at = pop
    carried = []
    speeds = {str(r["mlbam"]): r.get("ft_s") for r in s_rows if r.get("ft_s") is not None}
    runner_ids = {str(r["in_id"]) for r in rows if r.get("in_id") is not None}
    if speeds:
        pct = percentiles(speeds)
        runs = {str(r["mlbam"]): r.get("runs") for r in s_rows}
        runners = {k: [pct[k], round(float(speeds[k]), 1), runs.get(k)]
                   for k in sorted(runner_ids) if k in pct}
        sprint_meta = {"n_runners": len(speeds), "fetched_at": s_at,
                       "source_url": f"https://baseballsavant.mlb.com/leaderboard/sprint_speed?year={season}&min={SPRINT_FLOOR}"}
    else:
        runners = dict(prev.get("runners") or {})
        sprint_meta = dict(prev.get("sprint") or {"n_runners": 0, "fetched_at": None})
        if runners:
            carried.append("sprint")
    catcher_ids = {str(v) for v in att.values()}
    if p_map:
        catchers = {k: p_map[k] for k in sorted(catcher_ids) if k in p_map}
        pop_meta = {"n_catchers": len(p_map),
                    "n_with_pop": sum(1 for v in p_map.values() if v[0] is not None),
                    "fetched_at": p_at,
                    "source_url": ("https://baseballsavant.mlb.com/leaderboard/catcher-throwing"
                                   f"?game_type=Regular&n=1&season_start={season}&season_end={season}")}
    else:
        catchers = dict(prev.get("catchers") or {})
        pop_meta = dict(prev.get("pop") or {"n_catchers": 0, "n_with_pop": 0, "fetched_at": None})
        if catchers:
            carried.append("pop")
    blk = {"sprint": sprint_meta, "pop": pop_meta, "runners": runners,
           "catchers": catchers, "att": att}
    cov = {"attempts": len(rows), "runner_pct": 0, "catcher_id": 0, "pop": 0}
    for r in rows:
        c = context_for(r, blk)
        cov["runner_pct"] += c["sp_pct"] is not None
        cov["catcher_id"] += c["c_id"] is not None
        cov["pop"] += c["pop"] is not None
    blk["coverage"] = cov
    if carried:
        blk["carried_from_previous_build"] = carried
    return blk


def build(*, shard_dir: Path | None = None, win_prob: Path | None = None,
          open_season: int | None = None, prev: dict | None = None,
          sprint_fn=None, pop_fn=None, catcher_loader=None) -> dict:
    """The payload. Reads the shards for the steal rows (never writes them)."""
    open_season = int(open_season or _dt.date.today().year)
    prev = prev if prev is not None else (_read_json(OUT) or {})
    prev_seasons = prev.get("seasons") or {}
    by_season = steal_rows_on_disk(shard_dir)
    s_fn = sprint_fn or (lambda y: sprint_rows(y, open_season=open_season))
    p_fn = pop_fn or pop_rows
    seasons = {}
    tot = {"attempts": 0, "runner_pct": 0, "catcher_id": 0, "pop": 0}
    for season in sorted(by_season):
        rows = by_season[season]
        pv = prev_seasons.get(str(season)) or {}
        att = attempt_catchers(season, rows, seed=pv.get("att"), win_prob=win_prob,
                               loader=catcher_loader)
        blk = season_block(season, rows, sprint=s_fn(season), pop=p_fn(season), att=att, prev=pv)
        seasons[str(season)] = blk
        for k in tot:
            tot[k] += blk["coverage"][k]
        log.info("steal context %s: %d attempts, runner pct %d, catcher %d, pop %d",
                 season, *(blk["coverage"][k] for k in ("attempts", "runner_pct", "catcher_id", "pop")))
    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "produced_by": "mgmt_steal_context.py",
        "status": "built" if seasons else "not built: no steal rows in the shards",
        "use": USE,
        "runner": {"source": SPRINT_SOURCE, "definition": PCT_DEFINITION,
                   "floor_competitive_runs": SPRINT_FLOOR,
                   "row": "runners.{mlbam} = [percentile, sprint speed ft/s, competitive runs]"},
        "catcher": {"source": POP_SOURCE, "definition": POP_DEFINITION,
                    "row": "catchers.{mlbam} = [pop time to second, s (null when the board has none), "
                           "stolen-base attempts on the board, name]",
                    "attempt_key": "att.{game_pk}:{ab} = the catcher's mlbam id"},
        "key": "a steal row joins on season, then in_id (runner) and game_pk:ab (catcher)",
        "notes": NOTES,
        "coverage": tot,
        "seasons": seasons,
    }


def write(art: dict, out: Path | None = None) -> Path:
    p = Path(out or OUT)
    p.write_text(json.dumps(art, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return p


def run(*, log_fn=None, out: Path | None = None) -> dict:
    """The nightly step: rebuild and write; a build with no steal rows writes nothing."""
    say = log_fn or log.info
    art = build()
    if art.get("status") != "built":
        say(f"steal context: {art.get('status')}; the previous file stands")
        return {"status": "skipped", "why": art.get("status"), "attempts": 0}
    write(art, out)
    c = art["coverage"]
    why = (f"{c['attempts']:,} steal rows; runner percentile on {c['runner_pct']:,}, "
           f"catcher on {c['catcher_id']:,}, pop time on {c['pop']:,}")
    say(f"steal context: {why}")
    return {"status": "built", "why": why, **c}


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    argparse.ArgumentParser(description=__doc__.split("\n", 1)[0]).parse_args(argv)
    res = run(log_fn=print)
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
