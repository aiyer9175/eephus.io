#!/usr/bin/env python3
"""Build data/leaderboard_gamelogs.json — the per-game box-line slice that
powers date-windowed PROSPX leaderboards ("last N days" / custom range).

Each active prospect with an mlbam_id gets its full-season game log pulled
from the MLB StatsAPI (the same `statcast_metrics._game_logs` feed the
prospect-card gamelog uses, just uncapped). The frontend joins these games
to DATA.players by player_key, filters to the chosen date window, and
re-aggregates the rate line client-side.

Slice contract (compact, newest-first games):

    {
      "generated_at": "<ISO8601>Z",
      "season": 2026,
      "as_of": "YYYY-MM-DD",          # latest game date present; window
                                       # presets ("last 7d") anchor here
      "players": {
        "<player_key>": {
          "is_pitcher": false,
          "games": [
            {"d","lvl","pa","ab","h","2b","3b","hr","bb","so","sb","r","rbi","hbp","sf"},
            ...                         # hitter box line
          ]
        },
        "<player_key>": {
          "is_pitcher": true,
          "games": [
            {"d","lvl","ip","k","er","r","h","bb","hr","bf","hbp"}, ...
          ]
        }
      }
    }

Coverage: only the top `limit` prospects by overall_rank are pulled (the
nightly d5e call in run_monthly passes limit=200 under a 210 s soft budget), so
window boards and Splits reach only those players; limit=0 covers the full
active pool. The slice records `limit` and `n_candidates` so the frontend can
caption what it covers.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import statcast_metrics as sm  # noqa: E402

DATA_DIR = ROOT / "data"
BOOT = DATA_DIR / "timeseries.json"
OUT = DATA_DIR / "leaderboard_gamelogs.json"


def _home_flag(g: dict):
    """1 home / 0 away / None unknown. The StatsAPI game feed (surfaced by
    statcast_metrics._extract_recent_games) carries `is_home`; we keep it as a
    compact int so the frontend can build Home/Away splits over the FULL season
    (previously dropped here, which is why home/away splits were impossible)."""
    v = g.get("is_home")
    return 1 if v is True else 0 if v is False else None


def _hitter_game(g: dict) -> dict:
    return {
        "d": g["date"], "lvl": g.get("level"),
        "pa": g.get("pa"), "ab": g.get("ab"), "h": g.get("h"),
        "2b": g.get("doub"), "3b": g.get("trip"), "hr": g.get("hr"),
        "bb": g.get("bb"), "so": g.get("so"), "sb": g.get("sb"),
        "r": g.get("r"), "rbi": g.get("rbi"), "home": _home_flag(g),
        "hbp": g.get("hbp"), "sf": g.get("sf"),
    }


def _pitcher_game(g: dict) -> dict:
    return {
        "d": g["date"], "lvl": g.get("level"),
        "ip": g.get("ip"), "k": g.get("k"), "er": g.get("er"),
        "r": g.get("r"), "h": g.get("h"), "bb": g.get("bb"),
        "hr": g.get("hr"), "bf": g.get("bf"), "home": _home_flag(g),
        "hbp": g.get("hbp"),
    }


def _pull_one(player: dict, seasons: list[int],
              ttl_seconds: int = 86400) -> tuple[str, dict] | None:
    """Pull + shape one player's full game log across `seasons` (newest first).
    Returns (player_key, slice_entry) or None on no data / error. Multi-season
    pulls let the frontend build By-season splits; single-season callers pass a
    one-element list and behave exactly as before.

    `ttl_seconds` is forwarded to statcast_metrics._game_logs so an in-process
    caller can share the same on-disk feed cache the daily d5d Statcast scan
    just primed (default 86400 = accept a feed pulled within the last day)."""
    key = player.get("player_key")
    mlbam = player.get("mlbam_id")
    if not key or not mlbam:
        return None
    is_p = bool((player.get("statline") or {}).get("is_pitcher")
                or (player.get("position") or "").upper() in {"SP", "RP", "P", "SIRP", "MIRP", "RHP", "LHP"})
    shaped: list[dict] = []
    for season in seasons:
        try:
            logs = sm._game_logs(int(mlbam), season, is_pitcher=is_p,
                                 ttl_seconds=ttl_seconds)
        except Exception as e:  # noqa: BLE001 - network/parse hiccups skip the season
            print(f"  ! {player.get('player_name')} ({mlbam}) {season}: {e}", file=sys.stderr)
            continue
        if not logs:
            continue
        # Uncapped — keep the whole season so any window is computable.
        games = sm._extract_recent_games(logs, is_p, limit=10_000)
        shaped.extend(_pitcher_game(g) if is_p else _hitter_game(g) for g in games)
    if not shaped:
        return None
    # Newest game first, stable across seasons.
    shaped.sort(key=lambda g: g.get("d") or "", reverse=True)
    return key, {"is_pitcher": is_p, "games": shaped}


def build(season: int | None = None,
          seasons: int = 1,
          limit: int = 200,
          workers: int = 8,
          ttl_seconds: int = 86400,
          deadline_s: float | None = None,
          log: logging.Logger | None = None) -> dict:
    """Pull + shape the top-`limit` prospects' full game logs (by overall_rank)
    and write data/leaderboard_gamelogs.json. Returns a summary dict.

    In-process entry point for the pipeline (run_daily d5e). `limit` caps to the
    recognizable top of the board across every level; 0 = full active pool.

    `deadline_s` is a SOFT wall-clock budget (WS-R): once exceeded, no further
    player results are collected and the not-yet-started pulls are cancelled, so
    a cache-miss storm can't blow the nightly time budget. Whatever has been
    pulled is written (partial slice; the frontend staleness notice covers the
    gaps). Reuses the warm statcast_metrics._game_logs on-disk feed cache, so
    when the daily d5d Statcast scan primed the same (mlbam, season) feeds
    moments earlier most pulls are disk-cache hits."""
    lg = log or logging.getLogger("leaderboard_gamelogs")
    season = season or datetime.now().year
    seasons_list = [season - i for i in range(max(1, seasons))]

    boot = json.loads(BOOT.read_text(encoding="utf-8"))
    players = boot.get("players") or []
    # Active prospects with an mlbam_id, ordered by overall rank so the sample
    # is the recognizable top of the board across every level.
    cand = [p for p in players if p.get("mlbam_id")]
    cand.sort(key=lambda p: (p.get("overall_rank") is None, p.get("overall_rank") or 1e9))
    if limit:
        cand = cand[:limit]
    lg.info("leaderboard_gamelogs: pulling %d prospects (seasons %s-%s, %d workers%s)",
            len(cand), seasons_list[-1], seasons_list[0], workers,
            f", <={deadline_s:.0f}s budget" if deadline_s else "")

    out_players: dict[str, dict] = {}
    t0 = time.time()
    deadline = (t0 + deadline_s) if deadline_s else None
    done = 0
    skipped_deadline = 0
    # Not a `with` block: on a budget overrun we break early and shut the pool
    # down with cancel_futures so queued pulls are dropped rather than awaited.
    ex = ThreadPoolExecutor(max_workers=workers)
    futs = {ex.submit(_pull_one, p, seasons_list, ttl_seconds): p for p in cand}
    try:
        for fut in as_completed(futs):
            if deadline and time.time() > deadline:
                skipped_deadline = len(cand) - done
                lg.warning("leaderboard_gamelogs: soft %.0fs budget hit - skipping "
                           "%d remaining players (partial slice is fail-open)",
                           deadline_s, skipped_deadline)
                break
            done += 1
            res = fut.result()
            if res:
                out_players[res[0]] = res[1]
            if done % 50 == 0:
                lg.info("  %d/%d (%d with games, %.0fs)",
                        done, len(cand), len(out_players), time.time() - t0)
    finally:
        # wait=False so the pipeline is never blocked behind in-flight stragglers
        # (<= `workers` of them); cancel_futures drops the not-yet-started pulls.
        ex.shutdown(wait=False, cancel_futures=True)

    # as_of = latest game date across everyone (the window anchor).
    as_of = ""
    for entry in out_players.values():
        for g in entry["games"]:
            if g["d"] and g["d"] > as_of:
                as_of = g["d"]

    # Fail-safe (finding [24]): a ZERO-player pull is a transient upstream
    # failure (StatsAPI outage, or the soft deadline fired before any future
    # completed), NOT a legitimately empty board. Overwriting the served slice
    # with {} would blank every date-windowed leaderboard ("last 7d" / custom)
    # until the next good run - the frontend's only guard is `!players`, which
    # is falsy for a present-but-empty {} and falls through to an empty pool.
    # So when the pull yields nothing, keep the prior good slice instead. Match
    # the season so a NEW-season cold start doesn't preserve last season's
    # games (which would be worse than an empty board).
    if not out_players and OUT.exists():
        prior = None
        try:
            prior = json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prior = None
        if (isinstance(prior, dict) and prior.get("season") == season
                and (prior.get("players") or {})):
            lg.warning("leaderboard_gamelogs: fresh pull yielded 0 players "
                       "(transient upstream failure?) - keeping the prior good "
                       "slice (%d players, as_of=%s) rather than blanking %s",
                       len(prior.get("players") or {}), prior.get("as_of"),
                       OUT.name)
            return {"players": 0, "games": 0,
                    "as_of": prior.get("as_of", ""),
                    "elapsed_s": time.time() - t0,
                    "skipped_deadline": skipped_deadline,
                    "kept_prior": True,
                    "prior_players": len(prior.get("players") or {})}

    slice_obj = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        "season": season,
        "as_of": as_of,
        # Coverage meta (census M02-07): the frontend captions window boards and
        # Splits with it. 0 = the full active pool.
        "limit": int(limit or 0),
        "n_candidates": len(cand),
        "players": out_players,
    }
    OUT.write_text(json.dumps(slice_obj, separators=(",", ":")), encoding="utf-8")
    total_games = sum(len(e["games"]) for e in out_players.values())
    elapsed = time.time() - t0
    lg.info("leaderboard_gamelogs: wrote %s -> %d players, %d games, as_of=%s, "
            "%.0f KB, %.0fs%s",
            OUT.name, len(out_players), total_games, as_of,
            OUT.stat().st_size / 1024, elapsed,
            f" ({skipped_deadline} skipped by budget)" if skipped_deadline else "")
    return {"players": len(out_players), "games": total_games, "as_of": as_of,
            "elapsed_s": elapsed, "skipped_deadline": skipped_deadline}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=datetime.now().year)
    ap.add_argument("--seasons", type=int, default=1,
                    help="How many seasons back (inclusive of --season) to pull, "
                         "so the frontend can build By-season splits. 1 = current "
                         "season only (default, matches the legacy slice).")
    ap.add_argument("--limit", type=int, default=300,
                    help="Cap to the top-N prospects by overall_rank. "
                         "0 = full active pool. Pipeline d5e passes 200.")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--deadline", type=float, default=None,
                    help="Soft wall-clock budget in seconds; on overrun the "
                         "remaining players are skipped and a partial slice is "
                         "written (fail-open).")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    build(season=args.season, seasons=args.seasons, limit=args.limit,
          workers=args.workers, deadline_s=args.deadline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
