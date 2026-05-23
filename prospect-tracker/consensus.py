"""
Consensus engine — v5 (forward-filled, Bayesian-shrunk).

Anchored to the FanGraphs scouting primer:
  https://blogs.fangraphs.com/the-new-fangraphs-scouting-primer/

Design (v5)
-----------
Every source that publishes an explicit 20-80 FV grade contributes EQUALLY
to the consensus. There is no per-source weighting. This includes:

  * FanGraphs            (Eric Longenhagen + team)
  * ESPN                 (McDaniel)
  * Just Baseball
  * TJStats
  * MLB Pipeline         ("Overall" grade in each prospect bio)
  * MLB Pipeline Intl.   (International prospects ranking)

Two sources are still rank-only (no public FV):
  * Baseball America
  * The Athletic

These contribute via rank → implied-FV mapping ONLY when a player has no
explicit FV grades from any source; once at least one source has graded
the player, the FV mean wins and the ranks are used only for the
informational avg_rank field.

Forward-fill (v5)
-----------------
Real-world sources publish on different dates. To prevent a player whose
two grades arrive on different days from showing only the most recent
single source, each ConsensusPoint at date D uses the *latest known
snapshot from every source* up to D. New snapshots overwrite stale ones
from the same source; sources that have never graded the player simply
don't contribute.

Bayesian shrinkage (v5)
-----------------------
Low-information FVs get pulled toward the prospect-pool mean, with the
prior fading to zero as coverage approaches the maximum number of
FV-publishing sources:

    k_eff       = k * max(0, (N_full - n) / N_full)
    adjusted_fv = (n / (n + k_eff)) * raw_fv
                + (k_eff / (n + k_eff)) * mean_fv

  n      — number of sources contributing to raw_fv (explicit-FV count, or
           rank-only count when only rank-implied FVs are available)
  k      — tuning constant (default 2)
  N_full — source-count at which a player is "fully covered" and gets
           zero shrinkage (default 5: FG, ESPN, JB, TJ, MLB Pipeline)
  mean_fv— global mean of every player's latest pre-shrinkage raw FV

Weight on the raw value by n (with k=2, N_full=5):
   n=1 → 38%   n=2 → 63%   n=3 → 79%   n=4 → 91%   n=5 → 100% (no pull)

So an IFA-only Pipeline grade gets pulled hard, a 2-source prospect like
Asigen sees a moderate correction, and a five-source consensus like
Jesús Made keeps essentially its raw FV.

Per (player, date) we compute:

  a. avg_fv                       — simple mean of explicit FV grades
                                     from sources that published one
  b. avg_rank                     — simple mean of ordinal ranks
  c. rank_implied_fv              — mean of rank-converted FVs
  d. consensus_fv_pre_shrinkage   — avg_fv if any explicit FV present,
                                     otherwise rank_implied_fv
  e. consensus_fv_raw             — pre_shrinkage value pulled toward
                                     mean_fv per the Bayesian formula
  f. consensus_fv                 — rounded post-shrinkage value on the
                                     20-80 scale

Candlestick fields (fv_high / fv_low / fv_open / fv_close) ride on the
PlayerTimeseries object so the front-end can render a candle without
re-aggregating per-snapshot data.

Stock movement is "delta since the most recent prior update," not
"delta from first observation." A graduated player or a player with
only one update reads as "flat."
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field, replace as _dc_replace
from datetime import date

from scrapers import Snapshot


# Bayesian-shrinkage defaults. k controls how fast the prior fades as more
# sources contribute; N_FULL is the source-count at which a player is
# considered "fully covered" and shrinkage decays to zero. N_FULL is
# intentionally < the number of FV-grading outlets (5) so a top prospect
# graded by 4 of the 5 majors still escapes the prior — shrinkage exists
# to discipline thinly-covered players (e.g. 2026 IFAs with only one
# source), not to penalize well-known names just because one outlet has
# only ranked, not FV-graded, them. See `_shrinkage_n` for how the count
# itself is determined.
# Lowered from 2.0 → 1.5 in 2026-05 to ease the 40-tier clustering. With
# k=2.0 a 1-source prospect got 38% weight on the raw FV; the prior
# (population mean ≈ 40) dominated and most weakly-covered prospects
# collapsed onto a 40 tier regardless of what the source actually said.
# At k=1.5 a 1-source FV gets ~45% raw weight; 2-source ~70% — moves
# the marginal cases off 40 without affecting well-covered prospects.
DEFAULT_SHRINKAGE_K = 1.5
DEFAULT_N_FULL = 4
FALLBACK_PRIOR_FV = 45.0

# Single-source uncertainty pull-down — applied inside
# compute_consensus_point when exactly one source published an explicit
# FV. Bayesian shrinkage toward FV 35 with k=0.5:
#   adjusted = weight · raw + (1 − weight) · PRIOR, weight = 1 / (1 + K) = 2/3
# Higher raws get pulled harder (a 65 → 55, a 50 → 45). The prior sits
# at FV 35 deliberately: it's the "barely-a-prospect" floor — pulling
# toward it expresses "without corroboration we're not confident this
# is actually a real prospect-grade player". Multi-source consensus is
# completely untouched (weight = 1.0 in that branch).
SINGLE_SOURCE_PRIOR = 35.0
SINGLE_SOURCE_K = 0.5

# Source aliases — outlets that publish multiple separate lists but
# count as one editorial voice. MLB Pipeline splits its yearly coverage
# into the Top 100 (`mlb_pipeline`) and the International Top 50
# (`mlb_pipeline_international`); a 16-year-old who appears on both
# lists would otherwise show up as "2 sources" and dodge the single-
# source pull-down. Keys = source string emitted by the scraper, values
# = the canonical source name we collapse to for consensus + per_source.
SOURCE_ALIASES = {
    "mlb_pipeline_international": "mlb_pipeline",
}


def _dedupe_source_aliases(day_snaps: list[Snapshot]) -> list[Snapshot]:
    """Collapse multi-list outlets (e.g. MLB Pipeline Top 100 + Pipeline
    International) into a single canonical source per outlet.

    When the player appears on BOTH lists, we keep the canonical one
    (Pipeline Top 100) and drop the alias (Pipeline International) so
    the aggregator doesn't count them twice. When the player only
    appears on the alias list, we relabel it to the canonical source
    name so per_source / avg_fv_n / sources_contributing reflect "one
    Pipeline grade" rather than "one Pipeline International grade".
    """
    if not day_snaps or not SOURCE_ALIASES:
        return day_snaps
    canonical_present = {s.source for s in day_snaps}
    out: list[Snapshot] = []
    for s in day_snaps:
        target = SOURCE_ALIASES.get(s.source)
        if target is None:
            out.append(s)
            continue
        if target in canonical_present:
            # Canonical outlet's row exists — drop the alias entirely.
            continue
        # Canonical outlet missing — keep the alias but relabel it so
        # downstream code treats it as the canonical source.
        out.append(_dc_replace(s, source=target))
    return out


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

    # Post-shrinkage consensus. Until apply_shrinkage runs these mirror
    # consensus_fv_pre_shrinkage.
    consensus_fv: float
    consensus_fv_label: str
    consensus_fv_raw: float

    # Pre-shrinkage raw value (avg_fv or rank_implied_fv fallback). Surfaced
    # so the front-end can show "raw vs. adjusted" when useful.
    consensus_fv_pre_shrinkage: float

    # n / (n+k) — the weight Bayesian shrinkage placed on the player's
    # observations vs. the population mean. 1.0 means no shrinkage applied
    # (e.g. shrinkage skipped); lower values mean the prior pulled harder.
    shrinkage_weight: float

    sources_contributing: list[str]
    per_source: dict

    # Disagreement fields — computed only from explicit FV grades. Surface
    # how much sources agree on this player. None when fewer than two
    # sources published an explicit FV (a single number has no spread).
    # fv_min / fv_max are snapped to whole 20-80 grades so the UI can
    # render them next to the integer consensus_fv without mixed precision.
    fv_min: float | None = None
    fv_max: float | None = None
    fv_spread: float | None = None      # = fv_max - fv_min, on the raw scale
    fv_stddev: float | None = None      # population stddev of explicit FVs

    # Per-tool consensus, keyed by canonical tool name (hit, game_pwr,
    # raw_pwr, speed, field, throw, fb, sl, cb, ch, cmd). Each tool's
    # consensus is the unweighted mean across the sources that published
    # that tool on this date. Tools absent from every contributing source
    # are simply omitted from the dict — None never appears as a value.
    # Empty dict = no source published any tool grade on this date.
    tools_consensus: dict = field(default_factory=dict)
    # Per-tool spread (max - min) across publishing sources, for the UI
    # disagreement read. Only populated when ≥2 sources graded the tool.
    tools_spread: dict = field(default_factory=dict)


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

    # Total (source, snapshot_date) pairs across the player's history where
    # an explicit FV was published. Drives the single-instance shrinkage
    # trigger and the frontend "1" mark on the FV badge.
    fv_total_instances: int = 0

    # Set when status == "graduated"; date of the first source's grad signal.
    graduation_date: str | None = None


# ---------------------------------------------------------------------------
# Core compute — one (player, date) bucket
# ---------------------------------------------------------------------------

def compute_consensus_point(
    day_snaps: list[Snapshot],
    *,
    event_date: str | None = None,
    event_label: str | None = None,
    single_source_k: float = SINGLE_SOURCE_K,
    total_fv_instances: int | None = None,
) -> ConsensusPoint | None:
    """
    Aggregate one player's snapshots into a ConsensusPoint.

    `day_snaps` may come from a single calendar date OR — as it does after
    forward-fill in build_timeseries — be the latest snapshot from each
    source as of some event date. The aggregation is the same either way:
    one equal vote per source.

    Sources that publish only a rank contribute to avg_rank (and to a
    rank-implied FV fallback that is only used when zero sources published
    an explicit FV).

    Single-instance shrinkage: when `total_fv_instances` is provided
    (build_timeseries passes the player-level count of explicit-FV
    snapshots across history), the FV-35 pull only fires when the player
    has accumulated 1 instance ever — a FanGraphs-only prospect re-graded
    over 5 snapshots is well-observed and escapes the pull. When the
    kwarg is omitted (legacy callers + per-point unit tests), falls back
    to the older per-point trigger (`len(explicit_fvs) == 1`).
    """

    # Collapse multi-list outlets (Pipeline Top 100 + Pipeline
    # International, etc.) into one canonical source per outlet before
    # any aggregation logic runs — see _dedupe_source_aliases.
    day_snaps = _dedupe_source_aliases(day_snaps)

    explicit_fvs: list[float] = []
    ranks: list[int] = []
    rank_implied_fvs: list[float] = []

    per_source: dict[str, dict] = {}
    contributing_sources: set[str] = set()

    # Per-tool aggregation across sources. tools_by_key[key] is a list
    # of (source, grade) pairs; we never average values across multiple
    # snapshots from the same source — compute_consensus_point already
    # receives at most one row per source (forward-fill picks the
    # latest), so duplicates are impossible at this layer.
    tools_by_key: dict[str, list[float]] = {}

    for s in day_snaps:
        per_source[s.source] = {
            "rank": s.rank,
            "fv_published": s.fv,
            "interval_label": s.interval_label,
            "status": s.status,
            "snapshot_date": s.snapshot_date,
            "tools": dict(s.tools) if s.tools else None,
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
        if s.tools:
            for k, v in s.tools.items():
                # `_extras` is a sibling metadata dict, not a tool grade —
                # passes through per_source.tools._extras via the dict
                # copy at line 343, must not enter numeric aggregation.
                if k == "_extras":
                    continue
                tools_by_key.setdefault(k, []).append(v)
                contributing_sources.add(s.source)

    if not explicit_fvs and not rank_implied_fvs:
        return None

    avg_fv = sum(explicit_fvs) / len(explicit_fvs) if explicit_fvs else None
    avg_rank = sum(ranks) / len(ranks) if ranks else None
    rank_implied_fv = (
        sum(rank_implied_fvs) / len(rank_implied_fvs)
        if rank_implied_fvs else None
    )

    # Disagreement only meaningful with ≥2 explicit FV grades. fv_min /
    # fv_max get snapped to whole grades for display consistency with
    # consensus_fv; fv_spread/fv_stddev stay raw so a "2.5-grade spread"
    # doesn't get hidden by rounding.
    if len(explicit_fvs) >= 2:
        raw_min, raw_max = min(explicit_fvs), max(explicit_fvs)
        fv_min_snapped, _ = snap_to_grade(raw_min)
        fv_max_snapped, _ = snap_to_grade(raw_max)
        fv_min = fv_min_snapped
        fv_max = fv_max_snapped
        fv_spread = round(raw_max - raw_min, 2)
        fv_stddev = round(statistics.pstdev(explicit_fvs), 2)
    else:
        fv_min = fv_max = fv_spread = fv_stddev = None

    # Consensus = unweighted mean of explicit FVs. Fall back to the
    # rank-implied mean ONLY when no source published an FV grade —
    # otherwise a player ranked only by Baseball America / The Athletic
    # would have no consensus FV at all.
    pre_shrinkage = avg_fv if avg_fv is not None else rank_implied_fv
    assert pre_shrinkage is not None

    # Single-instance uncertainty pull. When the player has accumulated
    # only ONE explicit-FV instance across their entire history (1
    # snapshot, 1 source, ever — typically a brand-new 2026 IFA appearing
    # only on Pipeline's Top 50), shrink the consensus toward FV 35 using
    # a Bayesian prior with k=0.5. This pulls a 65 → 55, a 50 → 45, etc.
    # Higher grades get pulled harder, which matches the principle that
    # the variance on a high-end singleton is wider than on a corroborated
    # grade. A player re-graded over multiple snapshots — even by a
    # single source — escapes the pull because the source has confirmed
    # the grade over time. Multi-source consensus also stays untouched.
    # The pre-shrinkage value is preserved on the point for transparency.
    #
    # Legacy callers (per-point unit tests) that omit total_fv_instances
    # fall back to the older per-point trigger so synthetic fixtures
    # keep working without plumbing a player-level count.
    if total_fv_instances is not None:
        should_shrink = total_fv_instances <= 1 and explicit_fvs and single_source_k > 0
    else:
        should_shrink = len(explicit_fvs) == 1 and single_source_k > 0
    if should_shrink:
        shrinkage_weight_val = 1.0 / (1.0 + single_source_k)  # = 2/3 at K=0.5
        consensus_fv_raw_value = (
            shrinkage_weight_val * pre_shrinkage
            + (1.0 - shrinkage_weight_val) * SINGLE_SOURCE_PRIOR
        )
    else:
        shrinkage_weight_val = 1.0
        consensus_fv_raw_value = pre_shrinkage
    consensus_fv, consensus_label = snap_to_grade(consensus_fv_raw_value)

    # Default snapshot_date / interval_label come from the latest snapshot
    # in `day_snaps` (forward-fill yields a heterogeneous mix); callers
    # forward-filling across event dates pass explicit overrides.
    if event_date is None or event_label is None:
        latest_snap = max(day_snaps, key=lambda s: s.snapshot_date)
        event_date = event_date or latest_snap.snapshot_date
        event_label = event_label or latest_snap.interval_label

    # Per-tool consensus = unweighted mean across publishing sources.
    # Round to 0.5 grade — matches the precision of FanGraphs' published
    # tool grids and keeps the UI from showing 57.33-style noise.
    tools_consensus: dict[str, float] = {}
    tools_spread: dict[str, float] = {}
    for k, grades in tools_by_key.items():
        if not grades:
            continue
        mean = sum(grades) / len(grades)
        tools_consensus[k] = round(mean * 2) / 2
        if len(grades) >= 2:
            tools_spread[k] = round(max(grades) - min(grades), 2)

    return ConsensusPoint(
        snapshot_date=event_date,
        interval_label=event_label,
        avg_fv=round(avg_fv, 2) if avg_fv is not None else None,
        avg_fv_n=len(explicit_fvs),
        avg_rank=round(avg_rank, 1) if avg_rank is not None else None,
        rank_implied_fv=rank_implied_fv,
        avg_rank_n=len(ranks),
        consensus_fv=consensus_fv,
        consensus_fv_label=consensus_label,
        consensus_fv_raw=round(consensus_fv_raw_value, 2),
        consensus_fv_pre_shrinkage=round(pre_shrinkage, 2),
        shrinkage_weight=shrinkage_weight_val,
        sources_contributing=sorted(contributing_sources),
        per_source=per_source,
        fv_min=fv_min,
        fv_max=fv_max,
        fv_spread=fv_spread,
        fv_stddev=fv_stddev,
        tools_consensus=tools_consensus,
        tools_spread=tools_spread,
    )


# ---------------------------------------------------------------------------
# Bayesian shrinkage
# ---------------------------------------------------------------------------

def _shrinkage_n(point: ConsensusPoint) -> int:
    """Total number of sources providing *any* signal on this player.

    Uses the union of (a) sources that published an explicit FV and (b)
    sources that ranked the player without an FV. Both kinds of signal
    are real coverage — if Baseball America or Just Baseball ranks a
    prospect #4 without grading them, that's still strong evidence we
    "know who this player is" and the prior shouldn't pull as hard.

    This is more generous than the old rule (`avg_fv_n` only, falling
    back to `avg_rank_n` only when zero explicit FVs exist), which under-
    counted prospects like Jesús Made: graded by 4 outlets and ranked by
    a 5th, but `n` came in at 4 and the prior nudged him down a tier.
    """
    return len(point.sources_contributing)


def apply_shrinkage(
    point: ConsensusPoint,
    mean_fv: float,
    k: float = DEFAULT_SHRINKAGE_K,
    n_full: int = DEFAULT_N_FULL,
) -> None:
    """Mutate `point` in place to fold Bayesian shrinkage into consensus_fv.

        k_eff    = k * max(0, (n_full - n) / n_full)
        adjusted = (n / (n + k_eff)) * raw + (k_eff / (n + k_eff)) * mean_fv

    When n >= n_full, k_eff = 0 and the raw value passes through unchanged.
    Pre-shrinkage fields stay readable via consensus_fv_pre_shrinkage.
    """
    n = _shrinkage_n(point)
    raw = point.consensus_fv_pre_shrinkage
    # Snap the pre-shrinkage value first so the no-pull branches below are
    # idempotent: re-running apply_shrinkage on an already-shrunk point
    # (e.g. when tuning the formula and re-patching exported JSON) doesn't
    # leave stale post-shrinkage values in consensus_fv when the new
    # parameters say "no pull at all".
    raw_snapped, raw_label = snap_to_grade(raw)
    point.consensus_fv = raw_snapped
    point.consensus_fv_label = raw_label
    point.consensus_fv_raw = round(raw, 2)
    if n <= 0 or k <= 0 or n_full <= 0:
        # Nothing to shrink toward, or shrinkage disabled. Leave defaults.
        point.shrinkage_weight = 1.0
        return
    k_eff = k * max(0.0, (n_full - n) / n_full)
    if k_eff == 0.0:
        # Full coverage — no prior pull.
        point.shrinkage_weight = 1.0
        return
    weight = n / (n + k_eff)
    adjusted = weight * raw + (1.0 - weight) * mean_fv
    point.consensus_fv_raw = round(adjusted, 2)
    snapped, label = snap_to_grade(adjusted)
    point.consensus_fv = snapped
    point.consensus_fv_label = label
    point.shrinkage_weight = round(weight, 4)


def compute_prior_mean_fv(
    timeseries: list["PlayerTimeseries"],
    fallback: float = FALLBACK_PRIOR_FV,
) -> float:
    """Mean of each player's latest pre-shrinkage consensus FV.

    Each player contributes one data point (their most recent point's
    pre-shrinkage value), so a single source that grades a hundred
    prospects can't dominate the prior.
    """
    vals: list[float] = []
    for p in timeseries:
        if not p.points:
            continue
        v = p.points[-1].consensus_fv_pre_shrinkage
        if v is not None:
            vals.append(v)
    return sum(vals) / len(vals) if vals else fallback


# ---------------------------------------------------------------------------
# Time-series & candlestick assembly
# ---------------------------------------------------------------------------

def _latest_meta(snaps: list[Snapshot]) -> tuple[str, str | None, str | None]:
    snaps_sorted = sorted(snaps, key=lambda s: s.snapshot_date, reverse=True)
    # FanGraphs forward-projects positions — they publish where a
    # prospect is *expected* to land long-term (incl. SP / SIRP / MIRP
    # role designations), not just the current MiLB roster slot. Prefer
    # FG when present; fall back to latest-non-null from any source
    # otherwise. The team-org and player-name resolution stay on the
    # latest-non-null heuristic (no source has a meaningful claim to be
    # more authoritative on org/name).
    fg_pos = next((s.position for s in snaps_sorted
                   if s.source == "fangraphs" and s.position), None)
    any_pos = next((s.position for s in snaps_sorted if s.position), None)
    return (
        snaps_sorted[0].player_name,
        fg_pos or any_pos,
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
    *,
    shrinkage_k: float = DEFAULT_SHRINKAGE_K,
    shrinkage_n_full: int = DEFAULT_N_FULL,
    prior_mean_fv: float | None = None,
    single_source_k: float = SINGLE_SOURCE_K,
) -> list[PlayerTimeseries]:
    """Build per-player FV time-series with forward-filled sources and
    Bayesian shrinkage applied to every point.

    Forward-fill: at each event date, the consensus aggregates the latest
    snapshot from every source that has ever graded the player up to that
    date. This is what fixes the Asigen case — FG snaps on 5/17 + Pipeline
    Intl snaps on 5/19 produce a 5/19 point that averages BOTH grades, not
    just the most recent single source.

    Shrinkage: after the raw points are built, the population prior mean
    is computed from each player's latest pre-shrinkage value and applied
    uniformly across every point. Pass `prior_mean_fv` to override the
    auto-computed prior (e.g. for unit tests).
    """
    by_player: dict[str, list[Snapshot]] = defaultdict(list)
    for s in snapshots:
        by_player[s.player_key].append(s)

    result: list[PlayerTimeseries] = []
    for player_key, player_snaps in by_player.items():
        name, pos, org = _latest_meta(player_snaps)

        by_date: dict[str, list[Snapshot]] = defaultdict(list)
        for s in player_snaps:
            by_date[s.snapshot_date].append(s)

        # Single-instance shrinkage trigger: count how many published-FV
        # observations the player has accumulated across their entire
        # history (deduped per (source, snapshot_date)). With ≥2 instances
        # the player is considered well-observed and the FV-35 pull does
        # NOT fire at any of their points — even single-source players
        # who have been re-graded over time escape the pull. Brand-new
        # prospects with exactly one published grade still get pulled,
        # which is the intended uncertainty signal.
        seen_fv_keys: set[tuple[str, str]] = set()
        for s in player_snaps:
            if s.fv is not None:
                seen_fv_keys.add((s.source, s.snapshot_date))
        total_fv_instances = len(seen_fv_keys)

        # Walk event dates chronologically, forward-filling per source.
        # `latest_by_source` holds the most recent Snapshot seen from each
        # source up to (and including) the current event date.
        points: list[ConsensusPoint] = []
        latest_by_source: dict[str, Snapshot] = {}
        for snap_date in sorted(by_date):
            for s in by_date[snap_date]:
                prev = latest_by_source.get(s.source)
                # Multiple snapshots from the same source on the same date
                # (rare): keep the one with the most information — prefer
                # an explicit FV over a rank-only update from the same day.
                if (
                    prev is None
                    or s.snapshot_date > prev.snapshot_date
                    or (prev.fv is None and s.fv is not None)
                ):
                    latest_by_source[s.source] = s

            event_label = by_date[snap_date][-1].interval_label
            pt = compute_consensus_point(
                list(latest_by_source.values()),
                event_date=snap_date,
                event_label=event_label,
                single_source_k=single_source_k,
                total_fv_instances=total_fv_instances,
            )
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

        # Candle fields are populated after shrinkage is applied below.
        result.append(PlayerTimeseries(
            player_key=player_key, player_name=name,
            position=pos, org=org,
            points=points, status=status,
            graduation_date=graduation_date,
            fv_high=0.0, fv_high_label="—", fv_high_date="",
            fv_low=0.0,  fv_low_label="—",  fv_low_date="",
            fv_open=0.0, fv_close=0.0,
            fv_total_instances=total_fv_instances,
        ))

    # v7 — collapse duplicate (player_name) entries. FanGraphs CSV
    # ingest synthesizes `__noid`-suffixed player_keys whenever two
    # players collide on the FG id field; the result here ends up with
    # two PlayerTimeseries rows for the same person (e.g. Travis
    # Sykora, Chase DeLauter, Bryce Rainer). Merge them by preferring
    # the canonical (no-suffix) key and pooling points + graduation
    # state. Future: a `_SAME_NAME_NOT_DUPES` allowlist can carve out
    # legit same-name pairs if any surface.
    by_name: dict[str, PlayerTimeseries] = {}
    for p in result:
        canon = by_name.get(p.player_name)
        if canon is None:
            by_name[p.player_name] = p
            continue
        # Prefer the entry whose key does NOT end with __noid.
        if not canon.player_key.endswith("__noid"):
            keep, drop = canon, p
        else:
            keep, drop = p, canon
        # Merge points — dedupe by (snapshot_date, interval_label) so
        # the same source-snap doesn't get double-counted.
        seen: set[tuple[str, str]] = set()
        merged: list = []
        for pt in (keep.points + drop.points):
            key = (pt.snapshot_date, getattr(pt, "interval_label", ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(pt)
        merged.sort(key=lambda pt: pt.snapshot_date)
        keep.points = merged
        # Pull through the more authoritative status / graduation_date.
        if keep.status != "graduated" and drop.status == "graduated":
            keep.status = drop.status
            keep.graduation_date = drop.graduation_date
        # Pool the per-snapshot FV-instance count so the "n instances"
        # badge reflects the full publication history.
        keep.fv_total_instances = (
            (keep.fv_total_instances or 0) + (drop.fv_total_instances or 0)
        )
        # Position / org — prefer the canonical entry's value but fill
        # in from the duplicate if canon is missing.
        if not keep.position and drop.position:
            keep.position = drop.position
        if not keep.org and drop.org:
            keep.org = drop.org
        by_name[p.player_name] = keep
    result = list(by_name.values())

    # Population-prior Bayesian shrinkage was removed (2026-05): the
    # pull-toward-prior was compressing single-source prospects (90% of
    # actives) into a giant 40-FV cluster. compute_consensus_point now
    # produces the final consensus_fv values directly — multi-source
    # consensus = arithmetic mean (no shrinkage), single-source = the
    # targeted FV-35 pull (see SINGLE_SOURCE_PRIOR / SINGLE_SOURCE_K).
    # The legacy apply_shrinkage / compute_prior_mean_fv functions stay
    # defined for back-compat callers but are no longer wired in.
    for p in result:
        for attr, val in _candle_fields(p.points).items():
            setattr(p, attr, val)

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
