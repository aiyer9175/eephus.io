"""
Consensus engine — v4 (unweighted).

Anchored to the FanGraphs scouting primer:
  https://blogs.fangraphs.com/the-new-fangraphs-scouting-primer/

Design (v4)
-----------
Every source that publishes an explicit 20-80 FV grade contributes EQUALLY
to the consensus. There is no per-source weighting. This includes:

  * FanGraphs            (Eric Longenhagen + team)
  * ESPN                 (McDaniel)
  * Just Baseball
  * TJStats
  * MLB Pipeline         ("Overall" grade in each prospect bio)

Two sources are still rank-only (no public FV):
  * Baseball America
  * The Athletic

These contribute via rank → implied-FV mapping ONLY when a player has no
explicit FV grades from any source; once at least one source has graded
the player, the FV mean wins and the ranks are used only for the
informational avg_rank field.

Per (player, date) we compute:

  a. avg_fv             — simple mean of explicit FV grades from sources
                          that published one. None if no source did.
  b. avg_rank           — simple mean of ordinal ranks across all sources.
  c. rank_implied_fv    — mean of rank-converted FVs (rank-tier mapping).
  d. consensus_fv_raw   — avg_fv if any source published an FV; otherwise
                          rank_implied_fv. NO source weighting.
  e. consensus_fv       — rounded to the nearest whole number on the 20-80
                          scale. No "+" tiers; an average of 58.75 becomes 59,
                          not "60+".

Candlestick fields (fv_high / fv_low / fv_open / fv_close) ride on the
PlayerTimeseries object so the front-end can render a candle without
re-aggregating per-snapshot data.

Stock movement is "delta since the most recent prior update," not
"delta from first observation." A graduated player or a player with
only one update reads as "flat."
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from scrapers import Snapshot


# ---------------------------------------------------------------------------
# Snap helper — consensus FV is always a whole number on the 20-80 scale.
# ---------------------------------------------------------------------------
# Sources may publish "+" tiers (e.g. "55+" → 57.5 on ingest, see
# scrapers._parse_fv), but once aggregated we round to the nearest whole
# integer. An average of 58.75 becomes 59, not "60+".

def snap_to_grade(raw_fv: float) -> tuple[float, str]:
    """Round a raw averaged FV to the nearest whole number on the 20-80 scale."""
    raw_fv = max(20.0, min(80.0, raw_fv))
    rounded = int(round(raw_fv))
    return float(rounded), str(rounded)


# ---------------------------------------------------------------------------
# Rank -> implied FV
# ---------------------------------------------------------------------------

def implied_fv_from_rank(rank: int | None) -> float | None:
    if rank is None:
        return None
    if rank == 1:
        return 70.0
    if rank <= 15:
        return 60.0
    if rank <= 40:
        return 55.0
    if rank <= 110:
        return 50.0
    if rank <= 200:
        return 45.0
    return 40.0


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ConsensusPoint:
    snapshot_date: str
    interval_label: str

    avg_fv: float | None
    avg_fv_n: int

    avg_rank: float | None
    rank_implied_fv: float | None
    avg_rank_n: int

    consensus_fv: float
    consensus_fv_label: str
    consensus_fv_raw: float

    sources_contributing: list[str]
    per_source: dict


@dataclass
class PlayerTimeseries:
    player_key: str
    player_name: str
    position: str | None
    org: str | None

    points: list[ConsensusPoint]
    status: str

    # Candlestick fields (computed in build_timeseries)
    fv_high: float           # peak consensus_fv across this player's history
    fv_high_label: str
    fv_high_date: str
    fv_low: float            # trough consensus_fv across this player's history
    fv_low_label: str
    fv_low_date: str
    fv_open: float           # consensus_fv at the FIRST observation (candle "open")
    fv_close: float          # consensus_fv at the LATEST observation (candle "close")

    # Set when status == "graduated"; date of the first source's grad signal.
    graduation_date: str | None = None


# ---------------------------------------------------------------------------
# Core compute — one (player, date) bucket
# ---------------------------------------------------------------------------

def compute_consensus_point(day_snaps: list[Snapshot]) -> ConsensusPoint | None:
    """
    Aggregate one player's snapshots for a single date into a ConsensusPoint.

    Unweighted: every source that published an explicit FV grade contributes
    one equal vote to the FV mean. Sources that publish only a rank
    contribute to avg_rank (and to a rank-implied FV fallback that is only
    used when zero sources published an explicit FV).
    """

    explicit_fvs: list[float] = []
    ranks: list[int] = []
    rank_implied_fvs: list[float] = []

    per_source: dict[str, dict] = {}
    contributing_sources: set[str] = set()

    for s in day_snaps:
        per_source[s.source] = {
            "rank": s.rank,
            "fv_published": s.fv,
            "interval_label": s.interval_label,
            "status": s.status,
        }
        if s.fv is not None:
            explicit_fvs.append(s.fv)
            contributing_sources.add(s.source)
        if s.rank is not None:
            implied = implied_fv_from_rank(s.rank)
            if implied is not None:
                ranks.append(s.rank)
                rank_implied_fvs.append(implied)
                contributing_sources.add(s.source)

    if not explicit_fvs and not rank_implied_fvs:
        return None

    avg_fv = sum(explicit_fvs) / len(explicit_fvs) if explicit_fvs else None
    avg_rank = sum(ranks) / len(ranks) if ranks else None
    rank_implied_fv = (
        sum(rank_implied_fvs) / len(rank_implied_fvs)
        if rank_implied_fvs else None
    )

    # Consensus = unweighted mean of explicit FVs. Fall back to the
    # rank-implied mean ONLY when no source published an FV grade —
    # otherwise a player ranked only by Baseball America / The Athletic
    # would have no consensus FV at all.
    consensus_raw = avg_fv if avg_fv is not None else rank_implied_fv
    assert consensus_raw is not None
    consensus_fv, consensus_label = snap_to_grade(consensus_raw)

    return ConsensusPoint(
        snapshot_date=day_snaps[0].snapshot_date,
        interval_label=day_snaps[0].interval_label,
        avg_fv=round(avg_fv, 2) if avg_fv is not None else None,
        avg_fv_n=len(explicit_fvs),
        avg_rank=round(avg_rank, 1) if avg_rank is not None else None,
        rank_implied_fv=rank_implied_fv,
        avg_rank_n=len(ranks),
        consensus_fv=consensus_fv,
        consensus_fv_label=consensus_label,
        consensus_fv_raw=round(consensus_raw, 2),
        sources_contributing=sorted(contributing_sources),
        per_source=per_source,
    )


# ---------------------------------------------------------------------------
# Time-series & candlestick assembly
# ---------------------------------------------------------------------------

def _latest_meta(snaps: list[Snapshot]) -> tuple[str, str | None, str | None]:
    snaps_sorted = sorted(snaps, key=lambda s: s.snapshot_date, reverse=True)
    return (
        snaps_sorted[0].player_name,
        next((s.position for s in snaps_sorted if s.position), None),
        next((s.org for s in snaps_sorted if s.org), None),
    )


def _candle_fields(points: list[ConsensusPoint]) -> dict:
    """Compute high / low / open / close from the consensus_fv sequence."""
    if not points:
        return {
            "fv_high": 0.0, "fv_high_label": "—", "fv_high_date": "",
            "fv_low":  0.0, "fv_low_label":  "—", "fv_low_date":  "",
            "fv_open": 0.0, "fv_close": 0.0,
        }
    high_pt = max(points, key=lambda p: p.consensus_fv)
    low_pt  = min(points, key=lambda p: p.consensus_fv)
    return {
        "fv_high":       high_pt.consensus_fv,
        "fv_high_label": high_pt.consensus_fv_label,
        "fv_high_date":  high_pt.snapshot_date,
        "fv_low":        low_pt.consensus_fv,
        "fv_low_label":  low_pt.consensus_fv_label,
        "fv_low_date":   low_pt.snapshot_date,
        "fv_open":       points[0].consensus_fv,
        "fv_close":      points[-1].consensus_fv,
    }


def build_timeseries(
    snapshots: list[Snapshot],
) -> list[PlayerTimeseries]:
    by_player: dict[str, list[Snapshot]] = defaultdict(list)
    for s in snapshots:
        by_player[s.player_key].append(s)

    result: list[PlayerTimeseries] = []
    for player_key, player_snaps in by_player.items():
        name, pos, org = _latest_meta(player_snaps)

        by_date: dict[str, list[Snapshot]] = defaultdict(list)
        for s in player_snaps:
            by_date[s.snapshot_date].append(s)

        points: list[ConsensusPoint] = []
        for snap_date in sorted(by_date):
            pt = compute_consensus_point(by_date[snap_date])
            if pt is not None:
                points.append(pt)

        # Graduation logic: a player is considered graduated as soon as ANY
        # source (typically FanGraphs' graduates page) marks them so. Once
        # set, the status sticks — we don't "ungraduate" them if a stale
        # rank-only source still has them on a midseason list.
        status = "active"
        graduation_date = None
        for s in sorted(player_snaps, key=lambda x: x.snapshot_date):
            if s.status == "graduated":
                status = "graduated"
                graduation_date = s.snapshot_date
                break  # earliest graduation date wins
        if status != "graduated" and points and by_date:
            latest_day = sorted(by_date)[-1]
            statuses = [s.status for s in by_date[latest_day]]
            if "injured_list" in statuses:
                status = "injured_list"

        candle = _candle_fields(points)

        result.append(PlayerTimeseries(
            player_key=player_key, player_name=name,
            position=pos, org=org,
            points=points, status=status,
            graduation_date=graduation_date,
            **candle,
        ))

    result.sort(
        key=lambda p: (p.points[-1].consensus_fv if p.points else 0),
        reverse=True,
    )
    return result


# ---------------------------------------------------------------------------
# Stock movement — *delta since the most recent prior update*
# ---------------------------------------------------------------------------

def stock_movement(player: PlayerTimeseries) -> dict:
    """
    Returns:
        {
            "direction": "up_strong" | "up" | "flat" | "down" | "down_strong" | "graduated",
            "delta": float,         # consensus_fv_raw delta (latest minus prior)
            "from_label": str,      # consensus_fv_label at the prior update
            "to_label": str,        # consensus_fv_label at the latest update
            "from_date": str,
            "to_date": str,
        }
    """
    if player.status == "graduated":
        return {
            "direction": "graduated",
            "delta": 0.0, "from_label": "—", "to_label": "—",
            "from_date": "", "to_date": "",
        }
    if len(player.points) < 2:
        return {
            "direction": "flat",
            "delta": 0.0, "from_label": "—", "to_label": "—",
            "from_date": "", "to_date": "",
        }
    latest = player.points[-1]
    prior  = player.points[-2]
    delta = latest.consensus_fv_raw - prior.consensus_fv_raw
    if delta >= 4:
        direction = "up_strong"
    elif delta >= 1.5:
        direction = "up"
    elif delta <= -4:
        direction = "down_strong"
    elif delta <= -1.5:
        direction = "down"
    else:
        direction = "flat"
    return {
        "direction": direction,
        "delta": round(delta, 2),
        "from_label": prior.consensus_fv_label,
        "to_label": latest.consensus_fv_label,
        "from_date": prior.snapshot_date,
        "to_date": latest.snapshot_date,
    }
