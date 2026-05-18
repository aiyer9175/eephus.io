"""
Consensus engine — v3.

Anchored to the FanGraphs scouting primer:
  https://blogs.fangraphs.com/the-new-fangraphs-scouting-primer/

What's new in v3 versus v2
--------------------------
1. Seven sources, four of them publishing explicit 20-80 FV grades
   (FanGraphs, ESPN/McDaniel, Just Baseball, TJStats). The other three
   (BA, MLB Pipeline, The Athletic) are still rank-only.

2. Candlestick fields: every player carries a running fv_high / fv_low
   pair representing the highest and lowest consensus FV they've ever
   posted. This lets the front-end render a candlestick (current FV +
   high/low whiskers).

3. Stock movement is now "delta since the most recent prior update,"
   not "delta from first observation." A graduated player or a player
   with only one update reads as "flat."

4. Output trimmed: per the user's request the rendered fields per point
   are just consensus_fv (with label) and avg_rank. avg_fv and
   rank_implied_fv are still in the timeseries for diagnostics but are
   not surfaced in the default front-end columns.

The compute pipeline per (player, date):

  a. avg_fv             — simple mean of explicit FV grades from any source
                          that published one. Display only.
  b. avg_rank           — simple mean of ordinal ranks across all sources.
  c. rank_implied_fv    — mean of rank-converted FVs (FanGraphs tier mapping).
  d. consensus_fv_raw   — weighted mean across all signals; FV-graders
                          contribute their explicit FV at fv_weight, all
                          sources contribute rank-implied FV at rank_weight,
                          and a source publishing both has its rank halved
                          to avoid double-counting.
  e. consensus_fv       — snapped to nearest valid published 20-80 grade.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from scrapers import Snapshot


# ---------------------------------------------------------------------------
# Published-grade grid (20-80, FanGraphs primer)
# ---------------------------------------------------------------------------
# 75 is never published; 35 and 65 are rare but real.
WHOLE_FV_GRADES = [20, 30, 40, 45, 50, 55, 60, 65, 70, 80]

# "+" tier midpoints
PLUS_GRADES = {
    "40+": 42.5,
    "45+": 47.5,
    "50+": 52.5,
    "55+": 57.5,
    "60+": 62.5,
}


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
# Source weights — quality (per-source) × signal type (FV vs rank)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceWeight:
    name: str
    rank_weight: float
    fv_weight: float


DEFAULT_WEIGHTS: dict[str, SourceWeight] = {
    # FV-grading sources
    "fangraphs":        SourceWeight("fangraphs",        rank_weight=1.0, fv_weight=3.0),
    "espn":             SourceWeight("espn",             rank_weight=1.0, fv_weight=2.5),
    "just_baseball":    SourceWeight("just_baseball",    rank_weight=1.0, fv_weight=2.0),
    "tjstats":          SourceWeight("tjstats",          rank_weight=1.0, fv_weight=2.0),
    # Rank-only sources
    "baseball_america": SourceWeight("baseball_america", rank_weight=1.0, fv_weight=0.0),
    "mlb_pipeline":     SourceWeight("mlb_pipeline",     rank_weight=1.0, fv_weight=0.0),
    "the_athletic":     SourceWeight("the_athletic",     rank_weight=1.0, fv_weight=0.0),
}
# Weight rationale:
#   FanGraphs fv_weight=3.0 — primary anchor; the FV scale is theirs.
#   ESPN fv_weight=2.5      — McDaniel is highly credible; explicit 20-80;
#                              uses tighter "rare 65" tiering similar to FG.
#   Just Baseball fv=2.0    — explicit FV, full "+" tier usage, but smaller
#                              org and less industry sourcing.
#   TJStats fv=2.0          — explicit FV grounded in tjStuff+/Statcast;
#                              independent, less consensus-driven.
#   Rank-only fv=0.0        — they don't publish structured FV.
#
# Ranks all equal at 1.0 because no source's ordinal is a priori more
# reliable than another's. Tune via run_monthly.py --weights overrides.


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

def _weighted_mean(pairs: list[tuple[float, float]]) -> float | None:
    total_w = sum(w for _, w in pairs if w > 0)
    if total_w <= 0:
        return None
    return sum(v * w for v, w in pairs if w > 0) / total_w


def compute_consensus_point(
    day_snaps: list[Snapshot],
    weights: dict[str, SourceWeight] = DEFAULT_WEIGHTS,
) -> ConsensusPoint | None:

    explicit_fvs: list[float] = []
    explicit_contribs: list[tuple[str, float, float]] = []
    sources_with_explicit_fv: set[str] = set()

    ranks: list[int] = []
    rank_implied_fvs: list[float] = []
    rank_contribs: list[tuple[str, float, float]] = []

    per_source: dict[str, dict] = {}
    contributing_sources: set[str] = set()

    for s in day_snaps:
        w = weights.get(s.source)
        if w is None:
            continue
        per_source[s.source] = {
            "rank": s.rank,
            "fv_published": s.fv,
            "interval_label": s.interval_label,
            "status": s.status,
        }
        if s.fv is not None:
            explicit_fvs.append(s.fv)
            sources_with_explicit_fv.add(s.source)
            contributing_sources.add(s.source)
            if w.fv_weight > 0:
                explicit_contribs.append((s.source, s.fv, w.fv_weight))

    for s in day_snaps:
        w = weights.get(s.source)
        if w is None or s.rank is None or w.rank_weight <= 0:
            continue
        implied = implied_fv_from_rank(s.rank)
        if implied is None:
            continue
        ranks.append(s.rank)
        rank_implied_fvs.append(implied)
        contributing_sources.add(s.source)
        rank_w = w.rank_weight
        if s.source in sources_with_explicit_fv:
            rank_w *= 0.5
        rank_contribs.append((s.source, implied, rank_w))

    if not explicit_contribs and not rank_contribs:
        return None

    avg_fv = sum(explicit_fvs) / len(explicit_fvs) if explicit_fvs else None
    avg_rank = sum(ranks) / len(ranks) if ranks else None
    rank_implied_fv = (
        sum(rank_implied_fvs) / len(rank_implied_fvs)
        if rank_implied_fvs else None
    )

    all_contribs = (
        [(fv, w) for _, fv, w in explicit_contribs]
        + [(fv, w) for _, fv, w in rank_contribs]
    )
    consensus_raw = _weighted_mean(all_contribs)
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
    weights: dict[str, SourceWeight] = DEFAULT_WEIGHTS,
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
            pt = compute_consensus_point(by_date[snap_date], weights=weights)
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
