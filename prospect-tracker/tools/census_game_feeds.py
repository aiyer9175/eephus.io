# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""What .cache/game_feeds actually contains, counted rather than sampled.

WHY THIS EXISTS. Three readings of the same cache disagreed, and every weather,
umpire and lineup lane downstream is scoped by whichever one is true:

  * the earlier census said MLB (sportId 1) appears in 2026 ONLY, 2,108 games;
  * one verifier's 150-file sample said MLB feeds exist in 2023, 2024 and 2025
    too, and that a Home Plate official was named in 150 of 150;
  * another verifier's 60-file sample said there is NO officials key at all.

A sample cannot settle a question about coverage, and two of the three readings
above were produced by looking in different places for the same field. So this
walks EVERY file and reports presence rates per (sportId, season). No network,
no writes outside its own artifact, no model.

THE PATH THAT CAUSED THE FIGHT. `officials` is NOT under gameData. It sits at
`liveData.boxscore.officials`, a list of {official:{id,fullName}, officialType}.
A reader who looks up gameData.officials finds nothing on every file in the
cache and concludes the feed has no umpires; a reader who looks in the boxscore
finds a named Home Plate umpire. Both readings are honest and both were
reported. This tool counts BOTH paths side by side, so the artifact settles it
instead of a fourth sample.

WHAT IT COUNTS, per file:
  gd_weather        gameData.weather is a non-empty dict
  gd_weather_temp   ... and weather.temp is a non-empty string
  gd_officials      gameData.officials exists and is non-empty (the claimed
                    path; expected to be zero everywhere, which is the point)
  bx_officials      liveData.boxscore.officials exists and is non-empty
  bx_hp_named       ... and one entry has officialType == 'Home Plate' with a
                    non-empty official.fullName
  batting_order     BOTH boxscore.teams.home/away.battingOrder have >= 9 ids
  all_plays         liveData.plays.allPlays is a non-empty list

WHAT IT IS NOT. It is not a quality check on the values it finds. A weather
block reading temp '0' and condition 'Unknown' counts as present here, because
the question this answers is scope (which seasons and levels can a lane even be
built on), not fitness. It grades nothing, fits nothing and claims nothing about
whether an umpire effect exists. A file it cannot parse is counted in its own
`unreadable` bucket and never silently folded into a denominator.

DETERMINISM. Files are processed in sorted order; every reported figure is a
count or a ratio of counts, so the worker count changes runtime and nothing
else. Re-running on an unchanged cache reproduces the artifact byte for byte
apart from `generated_at`.

RUN IT:
    python tools/census_game_feeds.py
    python tools/census_game_feeds.py --workers 8
    python tools/census_game_feeds.py --limit 500 --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEED_DIR = ROOT / ".cache" / "game_feeds"
DEFAULT_OUT = ROOT / ".cache" / "game_feeds_census.json"

# The seven presence flags, in report order. Kept as one list so the worker,
# the aggregator and the printed table cannot drift apart.
FLAGS = ("gd_weather", "gd_weather_temp", "gd_officials", "bx_officials",
         "bx_hp_named", "batting_order", "all_plays")

# sportId -> the name MLB's own /api/v1/sports uses. Only a display label: the
# census keys off the integer and prints whatever name the feed itself carried
# when one is present, so an id absent from this map still reports correctly.
SPORT_NAMES = {1: "MLB", 11: "Triple-A", 12: "Double-A", 13: "High-A",
               14: "Single-A", 15: "Rookie Adv", 16: "Rookie",
               17: "Winter", 21: "Independent", 22: "College", 23: "HS"}


def _nonempty_str(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def scan_one(path: str) -> dict:
    """Presence flags for one feed file. Never raises: an unparseable or
    unshaped file comes back with ok=False and is counted separately."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            feed = json.load(fh)
    except Exception as exc:                                 # noqa: BLE001
        return {"ok": False, "why": f"{type(exc).__name__}: {exc}"[:120]}
    if not isinstance(feed, dict) or "gameData" not in feed:
        return {"ok": False, "why": "no gameData key"}

    gd = feed.get("gameData") or {}
    live = feed.get("liveData") or {}
    game = gd.get("game") or {}
    teams = gd.get("teams") or {}

    # sportId off the HOME team's sport block, falling back to the away team.
    # gameData.game carries no sport of its own in this payload.
    sport_id, sport_name = None, None
    for side in ("home", "away"):
        sp = ((teams.get(side) or {}).get("sport") or {})
        if sp.get("id") is not None:
            sport_id = sp.get("id")
            sport_name = sp.get("name")
            break

    season = game.get("season")
    if not _nonempty_str(str(season or "")):
        # An old feed without game.season still carries the official date.
        season = str((gd.get("datetime") or {}).get("officialDate") or "")[:4] or None
    season = str(season) if season is not None else None

    weather = gd.get("weather") or {}
    gd_off = gd.get("officials") or []
    box = live.get("boxscore") or {}
    bx_off = box.get("officials") or []
    hp_named = any(
        isinstance(o, dict)
        and o.get("officialType") == "Home Plate"
        and _nonempty_str(((o.get("official") or {}).get("fullName")))
        for o in bx_off if isinstance(bx_off, list)
    )
    bx_teams = box.get("teams") or {}
    orders = [(bx_teams.get(s) or {}).get("battingOrder") or [] for s in ("home", "away")]
    plays = (live.get("plays") or {}).get("allPlays") or []

    return {
        "ok": True,
        "sport_id": sport_id,
        "sport_name": sport_name,
        "season": season,
        "gd_weather": bool(isinstance(weather, dict) and weather),
        "gd_weather_temp": bool(isinstance(weather, dict)
                                and _nonempty_str(weather.get("temp"))),
        "gd_officials": bool(gd_off),
        "bx_officials": bool(bx_off),
        "bx_hp_named": bool(hp_named),
        "batting_order": bool(all(isinstance(o, list) and len(o) >= 9 for o in orders)),
        "all_plays": bool(isinstance(plays, list) and plays),
    }


def _blank_cell(sport_id, sport_name, season) -> dict:
    cell = {"sport_id": sport_id, "sport_name": sport_name,
            "season": season, "files": 0}
    for f in FLAGS:
        cell[f] = 0
    return cell


def census(feed_dir: Path, *, workers: int = 1, limit: int | None = None,
           progress=None) -> dict:
    """Walk every *.json in `feed_dir` and aggregate presence by
    (sportId, season). Returns the artifact dict."""
    files = sorted(p.name for p in Path(feed_dir).glob("*.json"))
    if limit:
        files = files[:limit]
    paths = [str(Path(feed_dir) / f) for f in files]

    cells: dict[tuple, dict] = {}
    unreadable: list[dict] = []
    n_done = 0

    def absorb(rec, name):
        nonlocal n_done
        n_done += 1
        if not rec.get("ok"):
            unreadable.append({"file": name, "why": rec.get("why", "")})
            return
        key = (rec.get("sport_id"), rec.get("season"))
        cell = cells.get(key)
        if cell is None:
            cell = cells[key] = _blank_cell(rec.get("sport_id"),
                                            rec.get("sport_name"),
                                            rec.get("season"))
        if cell["sport_name"] is None and rec.get("sport_name"):
            cell["sport_name"] = rec["sport_name"]
        cell["files"] += 1
        for f in FLAGS:
            if rec.get(f):
                cell[f] += 1

    if workers and workers > 1:
        # Chunked so the aggregation order matches the sorted file order; the
        # counters are commutative anyway, this just keeps a partial run's
        # progress line honest.
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for name, rec in zip(files, ex.map(scan_one, paths, chunksize=64)):
                absorb(rec, name)
                if progress and n_done % 2000 == 0:
                    progress(n_done, len(paths))
    else:
        for name, p in zip(files, paths):
            absorb(scan_one(p), name)
            if progress and n_done % 2000 == 0:
                progress(n_done, len(paths))

    rows = sorted(cells.values(),
                  key=lambda c: (c["sport_id"] is None, c["sport_id"] or 0,
                                 c["season"] or ""))
    for r in rows:
        if not r.get("sport_name"):
            r["sport_name"] = SPORT_NAMES.get(r["sport_id"], "?")

    totals = _blank_cell(None, "ALL", "ALL")
    for r in rows:
        totals["files"] += r["files"]
        for f in FLAGS:
            totals[f] += r[f]

    by_sport: dict[str, dict] = {}
    by_season: dict[str, dict] = {}
    for r in rows:
        for bucket, key in ((by_sport, str(r["sport_id"])),
                            (by_season, str(r["season"]))):
            cur = bucket.setdefault(key, {"files": 0, **{f: 0 for f in FLAGS}})
            cur["files"] += r["files"]
            for f in FLAGS:
                cur[f] += r[f]

    return {
        "generated_at": datetime.now(timezone.utc).replace(
            microsecond=0).isoformat(),
        "feed_dir": str(feed_dir),
        "n_files_seen": len(paths),
        "n_unreadable": len(unreadable),
        # Named on purpose and capped: a census that swallows its own failures
        # is the shape this tool exists to correct.
        "unreadable": unreadable[:50],
        "flags": list(FLAGS),
        "cells": rows,
        "totals": totals,
        "by_sport_id": by_sport,
        "by_season": by_season,
    }


def _pct(n: int, d: int) -> str:
    return "   -  " if not d else f"{100.0 * n / d:5.1f}%"


def print_table(art: dict, out=sys.stdout) -> None:
    w = out.write
    w(f"\n.cache/game_feeds census: {art['n_files_seen']} files, "
      f"{art['n_unreadable']} unreadable\n")
    w(f"generated_at {art['generated_at']}\n\n")
    head = (f"{'sportId':>7} {'level':<11} {'season':>6} {'files':>6} "
            f"{'weather':>7} {'wx.temp':>7} {'gd.offs':>7} {'bx.offs':>7} "
            f"{'HPnamed':>7} {'batOrder':>8} {'allPlays':>8}\n")
    w(head)
    w("-" * (len(head) - 1) + "\n")
    for r in art["cells"] + [art["totals"]]:
        if r is art["totals"]:
            w("-" * (len(head) - 1) + "\n")
        n = r["files"]
        w(f"{str(r['sport_id'] if r['sport_id'] is not None else '-'):>7} "
          f"{str(r['sport_name'])[:11]:<11} {str(r['season']):>6} {n:>6} "
          f"{_pct(r['gd_weather'], n):>7} {_pct(r['gd_weather_temp'], n):>7} "
          f"{_pct(r['gd_officials'], n):>7} {_pct(r['bx_officials'], n):>7} "
          f"{_pct(r['bx_hp_named'], n):>7} {_pct(r['batting_order'], n):>8} "
          f"{_pct(r['all_plays'], n):>8}\n")
    w("\ngd.offs = gameData.officials (the path two readers looked in)\n")
    w("bx.offs = liveData.boxscore.officials (where the umpires actually are)\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Census of .cache/game_feeds: coverage by sportId and "
                    "season, presence of weather, officials, batting order "
                    "and play-by-play. No network.")
    ap.add_argument("--feed-dir", type=Path, default=FEED_DIR)
    ap.add_argument("--json", type=Path, default=DEFAULT_OUT,
                    help=f"artifact path (default {DEFAULT_OUT})")
    ap.add_argument("--workers", type=int, default=1,
                    help="parallel readers; counts are commutative so this "
                         "changes runtime only")
    ap.add_argument("--limit", type=int, default=None,
                    help="scan the first N files only (a smoke run, not a "
                         "census: the printed rates are then a SAMPLE)")
    args = ap.parse_args(argv)

    if not Path(args.feed_dir).exists():
        print(f"no such directory: {args.feed_dir}", file=sys.stderr)
        return 2

    def progress(done, total):
        print(f"  ... {done}/{total}", file=sys.stderr, flush=True)

    art = census(Path(args.feed_dir), workers=max(1, args.workers),
                 limit=args.limit, progress=progress)
    if args.limit:
        art["sampled_limit"] = int(args.limit)
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(art, indent=1), encoding="utf-8")
    print_table(art)
    print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":                                   # pragma: no cover
    sys.exit(main())
