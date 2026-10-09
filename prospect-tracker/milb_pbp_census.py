# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Coverage census of MiLB pitch-by-pitch events per (level, season), for eFV v4
(task EFV4_PBP_CENSUS_AND_PILOT_FETCH). Writes data/_labs/efv_w2/pbp_census.json.

TWO PARTS, one artifact.

  probe   Written FIRST, before the full fetch. For every StatsAPI MiLB sport id
          (11 AAA, 12 AA, 13 A+, 14 A, 15 A-, 16 ROK) and every season 2006 to 2025
          but 2020 (no MiLB season), PROBE_N final regular-season games spread evenly
          over the season are read through milb_pbp_fetch (so they land in the same
          cache the fetch fills). Per cell: pitches per PA, call-code shares, the
          hitData and coordinate shares of balls in play, the share of sampled games
          with full pitch-by-pitch (a game is FULL when it records at least
          FULL_GAME_PPA pitches per PA; terminal-pitch-only games record about 1.5),
          and the class: full (every sampled game full), mixed (some), result_only
          (none), no_games. `fetch` is true for a cell in FETCH_SEASONS whose sampled
          games are at least FETCH_MIN_FULL_SHARE full (a cell with one full game in
          six is a stray park, not a season of pitch events).

  cache   Rebuilt from the per-game cache after (or during) the fetch: the same
          statistics over every cached game, plus scheduled final games, cached
          games, and the count and share of FULL games, which is the per-game flag a
          downstream column must honour (a result-only game contributes no value).

LEAKAGE GUARD. Reads only the pitch-event cache and the StatsAPI schedule; no WAR,
debut, label, grade, frame or name. The census is per (level, season) of the whole
league population; nothing is grouped by any player attribute.

Usage:
    python milb_pbp_census.py --probe      # network (fetch window), then writes
    python milb_pbp_census.py --cache      # cache only, any day
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import milb_pbp_fetch as F

OUT_PATH = F.CENSUS_PATH
PROBE_SEASONS: tuple[int, ...] = tuple(y for y in range(2006, 2026) if y not in F.NO_SEASON)
#: seasons the fetch may take: AAA and AA from 2007 (2006 is not asked for), the
#: lower levels wherever the probe finds pitch events, through 2025 (the last season
#: any frame's as-of rule can read: a 2026 debut reads 2025).
FETCH_SEASONS: tuple[int, ...] = tuple(y for y in range(2007, 2026) if y not in F.NO_SEASON)
PROBE_N = 6
FETCH_MIN_FULL_SHARE = 1 / 3
FULL_GAME_PPA = 3.0
IN_PLAY = frozenset({"X", "D", "E"})
CALL_CODES = ("B", "*B", "C", "S", "W", "F", "T", "L", "M", "X", "D", "E", "H",
              "I", "P", "Q", "R", "O", "V")


def _game_stats(rec: dict) -> dict:
    pc = rec["pitch_cols"]
    i_code, i_traj, i_x = pc.index("code"), pc.index("traj"), pc.index("x")
    calls = Counter()
    inplay = traj = coords = 0
    for p in rec["pitches"]:
        code = p[i_code]
        calls[code or "none"] += 1
        if code in IN_PLAY:
            inplay += 1
            traj += p[i_traj] is not None
            coords += p[i_x] is not None
    n_pa = len(rec["pa"])
    n_p = len(rec["pitches"])
    return {"pa": n_pa, "pitches": n_p, "calls": calls, "in_play": inplay,
            "traj": traj, "coords": coords,
            "full": bool(n_pa) and n_p / n_pa >= FULL_GAME_PPA}


def _aggregate(stats: list[dict]) -> dict:
    calls = Counter()
    pa = pitches = inplay = traj = coords = full = 0
    for s in stats:
        calls.update(s["calls"])
        pa += s["pa"]
        pitches += s["pitches"]
        inplay += s["in_play"]
        traj += s["traj"]
        coords += s["coords"]
        full += s["full"]
    n = len(stats)
    return {
        "games_read": n, "games_full": full,
        "full_game_share": round(full / n, 4) if n else None,
        "pa": pa, "pitches": pitches,
        "pitches_per_pa": round(pitches / pa, 3) if pa else None,
        "call_share": {k: round(v / pitches, 4) for k, v in sorted(calls.items())} if pitches else {},
        "in_play": inplay,
        "hitdata_trajectory_share": round(traj / inplay, 4) if inplay else None,
        "coordinates_share": round(coords / inplay, 4) if inplay else None,
    }


def _klass(agg: dict, scheduled: int) -> str:
    if not scheduled or not agg["games_read"]:
        return "no_games"
    if agg["games_full"] == agg["games_read"]:
        return "full"
    if agg["games_full"] == 0:
        return "result_only"
    return "mixed"


def _sample(games: list[dict], n: int) -> list[dict]:
    if len(games) <= n:
        return list(games)
    step = len(games) / n
    return [games[int(step * (k + 0.5))] for k in range(n)]


def probe(log=print) -> list[dict]:
    cells = []
    for sp in F.LEVEL_ORDER:
        for y in PROBE_SEASONS:
            games = F.schedule(sp, y)
            sample = _sample(games, PROBE_N)
            with ThreadPoolExecutor(max_workers=F.MAX_WORKERS) as ex:
                list(ex.map(lambda g: F.fetch_game(sp, y, g), sample))
            stats = [_game_stats(F.read_gz(F.game_path(sp, y, g["gamePk"]))) for g in sample]
            agg = _aggregate(stats)
            klass = _klass(agg, len(games))
            cell = {"sportId": sp, "level": F.SPORTS[sp], "season": y,
                    "scheduled_final": len(games),
                    "sample_gamePks": [g["gamePk"] for g in sample],
                    **agg, "class": klass,
                    "fetch": bool(agg["games_read"]) and y in FETCH_SEASONS
                    and agg["games_full"] / agg["games_read"] >= FETCH_MIN_FULL_SHARE}
            cells.append(cell)
            log(f"{F.SPORTS[sp]:>3} {y}: final {len(games):5d} ppa {agg['pitches_per_pa']} "
                f"full {agg['games_full']}/{agg['games_read']} {klass}")
    return cells


def cache_census(log=print) -> list[dict]:
    cells = []
    for sp in F.LEVEL_ORDER:
        for y in PROBE_SEASONS:
            d = F.CACHE_DIR / str(sp) / str(y)
            files = sorted(d.glob("*.json.gz")) if d.exists() else []
            sched_path = F.CACHE_DIR / "schedule" / f"{sp}_{y}.v2.json.gz"
            scheduled = len(F.read_gz(sched_path)) if sched_path.exists() else None
            if not files:
                continue
            agg = _aggregate([_game_stats(F.read_gz(p)) for p in files])
            cell = {"sportId": sp, "level": F.SPORTS[sp], "season": y,
                    "scheduled_final": scheduled, "games_cached": len(files),
                    "complete": scheduled is not None and len(files) >= scheduled,
                    **agg,
                    "games_result_only": agg["games_read"] - agg["games_full"]}
            cells.append(cell)
            log(f"{F.SPORTS[sp]:>3} {y}: cached {len(files)}/{scheduled} ppa "
                f"{agg['pitches_per_pa']} full {agg['games_full']} pitches {agg['pitches']}")
    return cells


def _load() -> dict:
    if OUT_PATH.exists():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {}


def write(doc: dict) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")


def _meta() -> dict:
    return {
        "task": "EFV4_PBP_CENSUS_AND_PILOT_FETCH",
        "role": "census (coverage only; adjudicates nothing; no frame, label or grade read)",
        "source": "statsapi.mlb.com /api/v1/schedule (gameType R, final) and "
                  "/api/v1/game/{gamePk}/playByPlay",
        "cache": ".cache/efv4_pbp/{sportId}/{season}/{gamePk}.json.gz (not committed)",
        "levels": {str(k): v for k, v in F.SPORTS.items()},
        "full_game_rule": f"pitches per PA >= {FULL_GAME_PPA}",
        "probe_games_per_cell": PROBE_N,
        "fetch_rule": "season in fetch_seasons and at least one third of the probe's "
                      "sampled games full",
        "excluded_leagues": {str(k): v for k, v in F.EXCLUDED_LEAGUES.items()},
        "fetch_seasons": [FETCH_SEASONS[0], FETCH_SEASONS[-1]],
        "no_season": sorted(F.NO_SEASON),
        "downstream_rule": "a (level, season) cell of class result_only, and any game "
                           "with games_full false, contributes no pitch-event value; "
                           "batted-ball hitData is present in result-only games too",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="MiLB pitch-event coverage census")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--cache", action="store_true")
    a = ap.parse_args(argv)
    if not (a.probe or a.cache):
        ap.error("pass --probe and/or --cache")
    doc = _load()
    doc["meta"] = _meta()
    if a.probe:
        ok, why = F.fetch_window_open()
        if not ok:
            print(f"fetch window closed: {why}")
            return 2
        cells = probe()
        doc["probe"] = {"as_of": date.today().isoformat(), "cells": cells,
                        "fetch_cells": [[c["sportId"], c["season"]] for c in cells if c["fetch"]],
                        "result_only_cells": [[c["sportId"], c["season"]] for c in cells
                                              if c["class"] == "result_only"]}
    if a.cache:
        cells = cache_census()
        tot = sum(c["games_cached"] for c in cells)
        doc["cache"] = {"as_of": date.today().isoformat(), "cells": cells,
                        "games_cached": tot,
                        "pitches": sum(c["pitches"] for c in cells),
                        "cells_complete": sum(bool(c["complete"]) for c in cells)}
    write(doc)
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
