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
            {"d","lvl","pa","ab","h","2b","3b","hr","bb","so","sb","r","rbi"},
            ...                         # hitter box line
          ]
        },
        "<player_key>": {
          "is_pitcher": true,
          "games": [
            {"d","lvl","ip","k","er","r","h","bb","hr","bf"}, ...
          ]
        }
      }
    }

POC mode (default): only the top `--limit` prospects by overall_rank are
pulled, so the slice is small and fast to build for UX review. The pipeline
phase drops `--limit` to cover the full active pool.
"""
from __future__ import annotations

import argparse
import json
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


def _hitter_game(g: dict) -> dict:
    return {
        "d": g["date"], "lvl": g.get("level"),
        "pa": g.get("pa"), "ab": g.get("ab"), "h": g.get("h"),
        "2b": g.get("doub"), "3b": g.get("trip"), "hr": g.get("hr"),
        "bb": g.get("bb"), "so": g.get("so"), "sb": g.get("sb"),
        "r": g.get("r"), "rbi": g.get("rbi"),
    }


def _pitcher_game(g: dict) -> dict:
    return {
        "d": g["date"], "lvl": g.get("level"),
        "ip": g.get("ip"), "k": g.get("k"), "er": g.get("er"),
        "r": g.get("r"), "h": g.get("h"), "bb": g.get("bb"),
        "hr": g.get("hr"), "bf": g.get("bf"),
    }


def _pull_one(player: dict, season: int) -> tuple[str, dict] | None:
    """Pull + shape one player's full-season game log. Returns
    (player_key, slice_entry) or None on no data / error."""
    key = player.get("player_key")
    mlbam = player.get("mlbam_id")
    if not key or not mlbam:
        return None
    is_p = bool((player.get("statline") or {}).get("is_pitcher")
                or (player.get("position") or "").upper() in {"SP", "RP", "P", "SIRP", "MIRP", "RHP", "LHP"})
    try:
        logs = sm._game_logs(int(mlbam), season, is_pitcher=is_p)
    except Exception as e:  # noqa: BLE001 - network/parse hiccups skip the player
        print(f"  ! {player.get('player_name')} ({mlbam}): {e}", file=sys.stderr)
        return None
    if not logs:
        return None
    # Uncapped — keep the whole season so any window is computable.
    games = sm._extract_recent_games(logs, is_p, limit=10_000)
    if not games:
        return None
    shaped = [(_pitcher_game(g) if is_p else _hitter_game(g)) for g in games]
    return key, {"is_pitcher": is_p, "games": shaped}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=datetime.now().year)
    ap.add_argument("--limit", type=int, default=300,
                    help="POC: cap to the top-N prospects by overall_rank. "
                         "0 = full active pool (pipeline phase).")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    boot = json.loads(BOOT.read_text(encoding="utf-8"))
    players = boot.get("players") or []
    # Active prospects with an mlbam_id, ordered by overall rank so the POC
    # sample is the recognizable top of the board across every level.
    cand = [p for p in players if p.get("mlbam_id")]
    cand.sort(key=lambda p: (p.get("overall_rank") is None, p.get("overall_rank") or 1e9))
    if args.limit:
        cand = cand[: args.limit]
    print(f"pulling game logs for {len(cand)} prospects (season {args.season}) "
          f"with {args.workers} workers ...")

    out_players: dict[str, dict] = {}
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_pull_one, p, args.season): p for p in cand}
        for fut in as_completed(futs):
            done += 1
            res = fut.result()
            if res:
                out_players[res[0]] = res[1]
            if done % 25 == 0:
                print(f"  {done}/{len(cand)} ({len(out_players)} with games, "
                      f"{time.time() - t0:.0f}s)")

    # as_of = latest game date across everyone (the window anchor).
    as_of = ""
    for entry in out_players.values():
        for g in entry["games"]:
            if g["d"] > as_of:
                as_of = g["d"]

    slice_obj = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        "season": args.season,
        "as_of": as_of,
        "players": out_players,
    }
    OUT.write_text(json.dumps(slice_obj, separators=(",", ":")), encoding="utf-8")
    total_games = sum(len(e["games"]) for e in out_players.values())
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out_players)} players, "
          f"{total_games} games, as_of={as_of}, "
          f"{OUT.stat().st_size / 1024:.0f} KB, {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
