# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The pluggable WAR facade (the D0 spec from
docs/master-plan-2026-08-03-eight-asks.md, built 2026-08-04d lane B1).

One module wraps every WAR read the sites make today, behind a provider id:

  * per-season WAR by mlbam/player_key -- the career_war sqlite table,
    written by stats.fetch_career_war_bulk (career_war_bulk / career_war_table)
  * the stint frame -- Baseball-Reference war_daily rows via pybaseball
    (stint_frame), one row per player-stint-season
  * the run-value decomposition -- WAR_def / runs_position / runs_bat etc.,
    columns that ride the stint frame (run_value_frame)
  * the name index -- normalized name -> {mlb_ID: {years, war}}
    (name_index, delegating to fa_ident.war_daily_index)
  * the per-season side split -- {mlbam: {season: {"bat": w, "pit": w}}}
    (side_war_by_season, delegating to mlb_player_export._war_daily)

PROVIDER CONTRACT. 'bwar' is the default and the only servable provider; it
is a pure delegation layer over the existing stats.py / fa_ident.py /
mlb_player_export.py functions, so routing through this module is a no-op
refactor (pinned byte-exact by test_war_source.py). 'ewar_v2' and
'ewar_merged' are DECLARED so call sites can name them today, but they raise
DataUnavailable loudly until their inputs exist; nothing silently falls back.

The per-(player, season) call shape a future provider must satisfy is
ewar.ewar_for (ewar.py) -- read it before wiring a new provider; do not
reimplement its artifact read here.

KNOWN TRAP (do not "just flip the default"): bWAR is pinned beyond the ten
call sites this facade absorbed -- the empirical FV curve, FV_EXPECTED_WAR
and the survivor anchors, the draft slot curve, war_rate_plus frozen
vintages, and copy gates literally asserting "bWAR" in user-facing prose.
A provider swap is the coordinated Stage-2 runbook
(docs/master-plan-2026-08-03-eight-asks.md D3, an OWNER CHECKPOINT) or
nothing; a partial re-anchor desyncs fingerprinted artifacts.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class DataUnavailable(RuntimeError):
    """A declared WAR provider whose input data does not exist yet.

    Deliberately loud: callers must never catch this to fall back silently
    to 'bwar' -- the caller that wants bwar asks for bwar."""


#: Every provider id this facade recognises. Declared != servable.
PROVIDERS: tuple[str, ...] = ("bwar", "ewar_v2", "ewar_merged")

#: The one servable provider. bWAR is the ONE WAR source site-wide.
DEFAULT_PROVIDER: str = "bwar"

_SIDES = ("bat", "pit")

# Why each non-servable provider refuses, naming the missing input. Kept as
# module data so test_war_source.py can pin the wording without duplicating it.
_UNAVAILABLE: dict[str, str] = {
    "ewar_v2": (
        "WAR provider 'ewar_v2' is declared but not servable: data/ewar.json "
        "(ewar.py) is a gated EVAL artifact on the bWAR frame, not an "
        "approved serving series. Missing input: the Stage-2 coordinated "
        "re-anchor runbook (docs/master-plan-2026-08-03-eight-asks.md D3, an "
        "owner checkpoint) covering the bWAR-pinned artifacts (empirical FV "
        "curve, FV_EXPECTED_WAR, draft slot curve, war_rate_plus vintages, "
        "copy gates)."
    ),
    "ewar_merged": (
        "WAR provider 'ewar_merged' is declared but not servable: the merged "
        "series is Will's pitcher eWAR plus SDR-bearing fielding on the "
        "ewar.py frame, and the pitcher eWAR parquet handoff "
        "(milb-projections/manifests/BENCHMARK_MANIFEST.yaml, "
        "mlb_pitcher_ewar_champion) has not been delivered; no hitter eWAR "
        "exists anywhere. Missing input: the private export bundle (a queued "
        "owner action)."
    ),
}


def _require(provider: str) -> None:
    """Validate a provider id. ValueError on an unknown id; DataUnavailable
    (with the missing input named) on a declared-but-absent one."""
    if provider not in PROVIDERS:
        raise ValueError(
            f"unknown WAR provider {provider!r}; known providers: {PROVIDERS}")
    if provider != "bwar":
        raise DataUnavailable(_UNAVAILABLE[provider])


# ---------------------------------------------------------------------------
# per-season WAR by player (the career_war funnel)
# ---------------------------------------------------------------------------

def career_war_bulk(targets: list[tuple[str, int, bool]],
                    start_year: int, end_year: int,
                    *, provider: str = DEFAULT_PROVIDER) -> dict[str, dict]:
    """Per-player {seasons, career_war, war_per_yr, war_seasons_count, source}
    aggregates for a (player_key, mlbam_id, is_pitcher) cohort.

    Provider 'bwar' delegates verbatim to stats.fetch_career_war_bulk (the
    sole writer feed of the career_war sqlite table)."""
    _require(provider)
    import stats
    return stats.fetch_career_war_bulk(targets, start_year, end_year)


def career_war_table(*, provider: str = DEFAULT_PROVIDER) -> dict[str, dict]:
    """The persisted per-player aggregate the sites read today:
    {player_key: aggregate} from the career_war sqlite table
    (storage.load_career_war). {} when the table is absent."""
    _require(provider)
    import storage
    return storage.load_career_war()


def side_war_by_season(*, provider: str = DEFAULT_PROVIDER
                       ) -> dict[int, dict[int, dict[str, float]]]:
    """{mlbam: {season: {"bat": WAR, "pit": WAR}}} with batting and pitching
    kept on SEPARATE keys (two-way players; position-player pitching cameos).
    Provider 'bwar' delegates to mlb_player_export._war_daily."""
    _require(provider)
    import mlb_player_export
    return mlb_player_export._war_daily()


# ---------------------------------------------------------------------------
# the stint frame + run-value decomposition
# ---------------------------------------------------------------------------

def stint_frame(side: str, *, provider: str = DEFAULT_PROVIDER):
    """The raw war_daily stint frame: one row per player-stint-season, with
    mlb_ID / year_ID / WAR / name_common / age / team_ID / exposure columns.
    ``side`` is 'bat' or 'pit'.

    Provider 'bwar' is pybaseball.bwar_bat / bwar_pitch with return_all=True
    (two static Baseball-Reference CSV downloads, cached by pybaseball) --
    exactly the call every migrated site used to make inline. Exceptions
    (network, ImportError) propagate; per-site try/except policy stays where
    it always lived, at the call sites."""
    _require(provider)
    if side not in _SIDES:
        raise ValueError(f"unknown stint-frame side {side!r}; use one of {_SIDES}")
    import pybaseball as pyb
    fn = pyb.bwar_bat if side == "bat" else pyb.bwar_pitch
    return fn(return_all=True)


def run_value_frame(side: str = "bat", *, provider: str = DEFAULT_PROVIDER):
    """The run-value decomposition read: the stint frame selected for its
    component columns (WAR_def, runs_position, runs_bat, runs_br, runs_dp,
    PA, pitcher, ...). Defaults to the batting frame, which carries the
    fielding/positional decomposition tools/build_def_history.py consumes."""
    return stint_frame(side, provider=provider)


# ---------------------------------------------------------------------------
# the name index
# ---------------------------------------------------------------------------

def name_index(*, provider: str = DEFAULT_PROVIDER) -> dict[str, dict[int, dict]]:
    """{normalized_name: {mlb_ID: {"years": set[int], "war": {year: WAR}}}}
    across both war_daily sides -- the veteran identity index. Provider
    'bwar' delegates to fa_ident.war_daily_index (lru-cached there; use
    fa_ident.resolve for windowed disambiguation, never guess here)."""
    _require(provider)
    import fa_ident
    return fa_ident.war_daily_index()
