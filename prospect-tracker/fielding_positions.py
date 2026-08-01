# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Game-data positional versatility ("versa").

Until now `versa` was a FanGraphs scout-reported multi-position string. This module
derives versa from ACTUAL GAME DATA: the MLB StatsAPI fielding group gives career
games + starts at each position. A prospect qualifies at a position once he has
>= VERSA_MIN_GAMES games OR >= VERSA_MIN_STARTS starts there (fantasy-standard; the
OR-starts clause lets a regular qualify mid-season while filtering one-off defensive
cameos). DH / PH / PR are excluded (not defensive positions).

Output: data/positions_played.json
    {"min_games": 10, "min_starts": 5, "generated_at": "...",
     "players": {player_key: {"by_pos": {POS: {"g": int, "gs": int}}, "versa": [POS, ...]}}}

The frontend loads this sidecar and surfaces the game-data versa (preferring it over
the FG-reported string). Built for ALL prospects (position players; pitchers skipped).
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from datetime import date
from pathlib import Path

VERSA_MIN_GAMES = 10   # games at a position to qualify (owner: "~10 games, calibrate")
VERSA_MIN_STARTS = 5   # OR starts — lets a regular qualify before 10 games accrue

# Not defensive positions — never count toward versatility.
_NON_FIELD = {"DH", "PH", "PR"}
_MLB_API = "https://statsapi.mlb.com/api/v1"

log = logging.getLogger(__name__)


def fetch_player_fielding(mlbam_id: int, timeout: float = 15.0) -> dict[str, dict]:
    """Career games + starts at each position for one player, MiLB+MLB.

    Returns {POS: {"g": games, "gs": gamesStarted}}. Empty on no fielding data."""
    url = (f"{_MLB_API}/people/{mlbam_id}/stats"
           f"?stats=career&group=fielding&leagueListId=mlb_milb")
    with urllib.request.urlopen(url, timeout=timeout) as r:
        doc = json.load(r)
    splits = (doc.get("stats") or [{}])[0].get("splits") or []
    by_pos: dict[str, dict] = {}
    for s in splits:
        pos = ((s.get("position") or {}).get("abbreviation") or "").strip()
        if not pos:
            continue
        st = s.get("stat") or {}
        slot = by_pos.setdefault(pos, {"g": 0, "gs": 0})
        slot["g"] += int(st.get("games") or 0)
        slot["gs"] += int(st.get("gamesStarted") or 0)
    return by_pos


def versa_positions(by_pos: dict[str, dict],
                    min_games: int = VERSA_MIN_GAMES,
                    min_starts: int = VERSA_MIN_STARTS) -> list[str]:
    """Positions the prospect QUALIFIES at (>= min_games games OR >= min_starts
    starts), most-played first. DH / PH / PR excluded."""
    qual = [(pos, v) for pos, v in by_pos.items()
            if pos not in _NON_FIELD
            and ((v.get("g") or 0) >= min_games or (v.get("gs") or 0) >= min_starts)]
    qual.sort(key=lambda kv: -(kv[1].get("g") or 0))
    return [pos for pos, _ in qual]


def build_positions_played(players: list[dict],
                           out_path: str | Path = "data/positions_played.json",
                           throttle: float = 0.05,
                           log_: logging.Logger | None = None) -> dict:
    """Fetch fielding-by-position for every POSITION-PLAYER prospect with an mlbam_id
    and write the versa sidecar. Pitchers are skipped (no versa). Per-player errors
    are swallowed so one bad id can't sink the batch."""
    lg = log_ or log
    out: dict[str, dict] = {}
    n = err = skipped = 0
    for p in players:
        mid = p.get("mlbam_id")
        pk = p.get("player_key")
        if not mid or not pk:
            skipped += 1
            continue
        if (p.get("statline") or {}).get("is_pitcher"):
            skipped += 1
            continue
        try:
            by_pos = fetch_player_fielding(mid)
        except Exception:
            err += 1
            continue
        if not by_pos:
            continue
        out[pk] = {"by_pos": by_pos, "versa": versa_positions(by_pos)}
        n += 1
        if throttle:
            time.sleep(throttle)
    payload = {
        "generated_at": date.today().isoformat(),
        "min_games": VERSA_MIN_GAMES,
        "min_starts": VERSA_MIN_STARTS,
        "players": out,
    }
    Path(out_path).write_text(json.dumps(payload, separators=(",", ":")),
                              encoding="utf-8")
    lg.info("positions_played: wrote %d players (%d errors, %d skipped) -> %s",
            n, err, skipped, out_path)
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ts = json.loads(Path("data/timeseries.json").read_text(encoding="utf-8"))
    players = [p for p in (ts.get("players") or [])
               if not p.get("debut_date")]
    build_positions_played(players)
