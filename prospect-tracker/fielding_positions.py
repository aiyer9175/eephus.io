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


# Defensive spectrum, hardest first. Used ONLY as the last tie-break in
# observed_position: when two positions are level on games AND on starts,
# the harder one is the meaningful assignment (industry convention, and the
# one the scarcity model prices). Stating the order makes the resolver
# deterministic; the shipped versa sort breaks its ties on dict-insertion
# order, which is whatever the StatsAPI happened to return.
_SPECTRUM = ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "OF", "IF", "P"]
_SPECTRUM_RANK = {pos: i for i, pos in enumerate(_SPECTRUM)}


def observed_position_detail(by_pos: dict[str, dict],
                             min_games: int = VERSA_MIN_GAMES,
                             min_starts: int = VERSA_MIN_STARTS) -> dict | None:
    """Most-played NON-DH position from a game-data `by_pos` map, with detail.

    The owner ask ("hitter position should be based on what position they've
    played the most in the minors") answered from the fielding census rather
    than from a scouting projection. Returns
    ``{"pos", "g", "gs", "share", "tie", "qualified"}`` where `share` is the
    position's fraction of the player's non-DH fielding games, `tie` flags that
    the top position was decided by a tie-break rather than won outright on
    games, and `qualified` records that the top position cleared the exposure
    floor.

    Rules, all pre-registered in docs/efv-2026-07-30/POSITION_ROLE_GATE.md:

    * DH / PH / PR are never eligible (`_NON_FIELD`, same set versa uses). A
      player whose largest bucket is DH resolves to his largest FIELDING
      bucket; a player with nothing but DH/PH/PR resolves to None.
    * Exposure floor: the winner must clear `>= min_games` games OR
      `>= min_starts` starts - the SAME thresholds versa already qualifies on,
      so no new tunable enters the system. Below that this returns None rather
      than naming a position off three cameo games.
    * Ties break deterministically on (games, starts, defensive spectrum,
      name), never on dict order.

    Returns None for an empty / all-DH / below-floor map. Never raises on
    malformed counts (non-numeric entries read as 0).
    """
    if not by_pos:
        return None

    def _n(v) -> int:
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0

    cands = [(pos, _n(v.get("g")), _n(v.get("gs")))
             for pos, v in by_pos.items()
             if pos and pos not in _NON_FIELD]
    cands = [c for c in cands if c[1] > 0 or c[2] > 0]
    if not cands:
        return None
    total_g = sum(c[1] for c in cands)
    cands.sort(key=lambda c: (-c[1], -c[2],
                              _SPECTRUM_RANK.get(c[0], len(_SPECTRUM)), c[0]))
    pos, g, gs = cands[0]
    tie = len(cands) > 1 and cands[1][1] == g
    qualified = g >= min_games or gs >= min_starts
    if not qualified:
        return None
    return {"pos": pos, "g": g, "gs": gs,
            "share": round(g / total_g, 4) if total_g else 0.0,
            "tie": bool(tie), "qualified": True}


def observed_position(by_pos: dict[str, dict],
                      min_games: int = VERSA_MIN_GAMES,
                      min_starts: int = VERSA_MIN_STARTS) -> str | None:
    """Most-played non-DH position, or None. Thin wrapper on
    observed_position_detail - see that docstring for every rule."""
    d = observed_position_detail(by_pos, min_games, min_starts)
    return d["pos"] if d else None


def load_observed_positions(path: str | Path = "data/positions_played.json",
                            min_games: int = VERSA_MIN_GAMES,
                            min_starts: int = VERSA_MIN_STARTS) -> dict[str, str]:
    """{player_key: observed_position} over the whole sidecar.

    Players whose census is empty, all-DH, or below the exposure floor are
    OMITTED (not mapped to None), so a caller's `.get(key)` returns None for
    "no observation" whichever way the player got there. Missing or malformed
    file yields an empty map: this must never be able to break an export.
    """
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for pk, rec in (doc.get("players") or {}).items():
        pos = observed_position((rec or {}).get("by_pos") or {},
                                min_games, min_starts)
        if pos:
            out[pk] = pos
    return out


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
