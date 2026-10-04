# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved

"""
fielding.py — Position resolution from parquet + manual overrides.

The pipeline stores players' positions from scouting sources (their minor
league / prospect position).  When a player graduates to MLB they often
change roles: Soderstrom was a C prospect but now plays LF exclusively,
AJ Ewing was a SS prospect but plays OF in the majors.  Using the wrong
position inflates/deflates trade value via the positional scarcity multiplier
and the defensive floor assumption.

Two data sources:
  milb_fielding.parquet  — games-started by position at AA/AAA level.
                           Best for active prospects (current deployment).
                           Unreliable for graduated players who changed role.
  position_overrides.json — manually curated MLB current-season positions.
                             Used for graduated/debuted players.

Resolution priority:
  1. position_overrides.json  (highest confidence for MLB players)
  2. fielding_innings.json current-season usage primary (by mlbam id)
  3. mlb_player_detail.json   (current MLB player-page / projection position)
  4. milb_fielding.parquet    (good for active prospects)
  5. Player's DB position     (fallback)
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

_log  = logging.getLogger(__name__)
_HERE = Path(__file__).resolve().parent
_VALID_POSITIONS = {
    "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "DH",
    "P", "SP", "RP", "RHP", "LHP", "SIRP", "MIRP", "CL", "TWP",
}


def _valid_position(pos: str | None) -> bool:
    if not pos:
        return False
    parts = [p.strip().upper() for p in str(pos).split("/") if p.strip()]
    return bool(parts) and all(p in _VALID_POSITIONS for p in parts)

# ---------------------------------------------------------------------------
# Parquet loader
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_parquet_positions() -> dict[int, str]:
    """Return {mlbam_id: primary_position} from milb_fielding.parquet.

    Uses PyArrow directly to avoid pandas version dependency issues.
    """
    path = _HERE / "milb_fielding.parquet"
    if not path.exists():
        return {}
    try:
        import pyarrow.parquet as pq
        tbl = pq.read_table(str(path))
        d   = tbl.to_pydict()
        n   = len(d.get("mlbam_id") or [])
        out: dict[int, str] = {}
        for i in range(n):
            mid = d["mlbam_id"][i]
            pos = d["pos"][i]
            if mid is not None and pos:
                out[int(mid)] = str(pos)
        _log.debug("fielding: loaded %d positions from parquet", len(out))
        return out
    except Exception as e:
        _log.warning("fielding: could not load parquet: %s", e)
        return {}


@lru_cache(maxsize=1)
def _load_overrides() -> dict[str, str]:
    """Return {player_key: position} from position_overrides.json."""
    path = _HERE / "data" / "position_overrides.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: v["position"] for k, v in (data.get("players") or {}).items()}
    except Exception as e:
        _log.warning("fielding: could not load overrides: %s", e)
        return {}


@lru_cache(maxsize=1)
def _load_mlb_detail_positions() -> dict[str, str]:
    """Return {player_key: current_position} from mlb_player_detail.json.

    This export is built from MLB-facing player data/projections and is a
    better current-role signal for debuted players than their prospect-source
    position label. It catches cases like a player listed by old scouting
    sources as SS but currently deployed almost exclusively at 2B.
    """
    path = _HERE / "data" / "mlb_player_detail.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        players = data.get("players") or {}
        out: dict[str, str] = {}
        if isinstance(players, dict):
            for key, row in players.items():
                pos = (row or {}).get("pos") or (row or {}).get("position")
                if key and _valid_position(pos):
                    out[str(key)] = str(pos).upper()
        return out
    except Exception as e:
        _log.warning("fielding: could not load MLB detail positions: %s", e)
        return {}


@lru_cache(maxsize=1)
def _load_mlb_fielding_usage() -> dict[int, dict[str, dict]]:
    """Return current-season MLB fielding usage keyed by mlbam id and position.

    Shape:
      {mlbam: {position: {games, games_started, innings}}}

    Read from data/fielding_innings.json, the nightly StatsAPI fielding feed
    (fielding_innings.py), at its latest season. Until 2026-09-25 this read
    data/mlb_fielding_positions.json, a June 22 snapshot keyed by name slug that
    nothing refreshed (155 of 650 non-pitcher veterans absent); the owner chose
    the nightly feed (decision L5, 2026-09-17). Kept as a local sidecar so the
    trade-value export makes no live API calls.
    """
    path = _HERE / "data" / "fielding_innings.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        seasons = data.get("seasons") or {}
        season = str(data.get("last_season") or max(seasons, default=""))
        players = seasons.get(season) or {}
        out: dict[int, dict[str, dict]] = {}
        for mid, by_pos in players.items():
            clean: dict[str, dict] = {}
            for raw_pos, usage in (by_pos or {}).items():
                pos = str(raw_pos).upper()
                if not _valid_position(pos):
                    continue
                clean[pos] = {
                    "games": float((usage or {}).get("g") or 0.0),
                    "games_started": float((usage or {}).get("gs") or 0.0),
                    "innings": float((usage or {}).get("inn") or 0.0),
                }
            if clean:
                try:
                    out[int(mid)] = clean
                except (TypeError, ValueError):
                    continue
        return out
    except Exception as e:
        _log.warning("fielding: could not load MLB fielding usage: %s", e)
        return {}


def _primary_from_usage(usage: dict[str, dict]) -> str | None:
    if not usage:
        return None
    if "P" in usage and "DH" in usage:
        p_innings = float((usage.get("P") or {}).get("innings") or 0.0)
        dh_games = float((usage.get("DH") or {}).get("games") or 0.0)
        if p_innings >= 20.0 and dh_games >= 20.0:
            return "TWP"
    defensive = {
        pos: row for pos, row in usage.items()
        if str(pos).upper() != "DH"
    }
    pool = defensive or usage
    pos, row = max(
        pool.items(),
        key=lambda item: (
            float((item[1] or {}).get("innings") or 0.0),
            float((item[1] or {}).get("games_started") or 0.0),
            float((item[1] or {}).get("games") or 0.0),
        ),
    )
    return str(pos).upper()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_position(player_key: str | None,
                     mlbam_id: int | None,
                     db_position: str | None,
                     is_mlb_player: bool = False) -> tuple[str | None, str]:
    """Return the best available current position for a player.

    Returns (position, source) where source is one of:
      'override'    manual position_overrides.json entry
      'parquet'     milb_fielding.parquet primary GS position
      'db'          original DB / scouting position (fallback)
      'unknown'     no data at all
    """
    # 1. Manual override (highest confidence for MLB players)
    overrides = _load_overrides()
    if player_key and player_key in overrides:
        return overrides[player_key], "override"

    # 2. Direct current-season MLB fielding usage, when populated.
    if is_mlb_player and mlbam_id:
        usage_primary = _primary_from_usage(_load_mlb_fielding_usage().get(int(mlbam_id)) or {})
        if usage_primary:
            return usage_primary, "mlb_fielding"

    # 3. MLB detail export for current MLB role. This is intentionally limited
    #    to debuted/graduated players; active prospects still use MiLB fielding
    #    deployment when available.
    if is_mlb_player and player_key:
        detail_positions = _load_mlb_detail_positions()
        if player_key in detail_positions:
            return detail_positions[player_key], "mlb_detail"

    # 4. Parquet (good for active MiLB prospects; skip for MLB players
    #    because the parquet reflects their minor league position history,
    #    not their current MLB deployment)
    if not is_mlb_player and mlbam_id:
        parquet = _load_parquet_positions()
        if mlbam_id in parquet:
            return parquet[mlbam_id], "parquet"

    # 5. DB position (fallback)
    if db_position:
        return db_position, "db"

    return None, "unknown"


def position_usage(player_key: str | None, mlbam_id: int | None = None) -> dict[str, dict]:
    """Return known current MLB fielding usage for a player, by mlbam id (the
    feed has no name key; a row without an id gets nothing)."""
    if not mlbam_id:
        return {}
    try:
        return dict(_load_mlb_fielding_usage().get(int(mlbam_id)) or {})
    except (TypeError, ValueError):
        return {}
