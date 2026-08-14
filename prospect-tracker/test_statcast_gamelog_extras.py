# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The gameLog piggyback fields must survive the pass-1 memory trim.

WHY THIS EXISTS (2026-08-03). The pass-1 trim (`_slim_split`) reduces each
cached gameLog split to {game.gamePk, date, _level} so the parent process is not
holding 190K+ full stat blocks across passes 2 and 3 - the fix for the fourth
consecutive OOM kill of the nightly statcast step.

Its safety note traced the PARENT's reads (pass-2 gamePk/date dedup, pass-3
level filter) and the external callers of `_game_logs` (vaa.py, the leaderboard
tool), and was right about both. What it missed is that the trimmed list is
also handed to the pass-3 WORKER as its `logs` argument, where two piggyback
extractors read the full stat line:

    standout_games = _extract_standout_games(logs, ...)   # reads split["stat"]
    recent_games   = _extract_recent_games(logs, ...)     # reads split["stat"]

Both bail when the stat block is missing, so every row came back with two empty
lists - and `upsert_statcast_metrics` replaces the whole payload rather than
merging, so the empties overwrote good stored values on every run. Nothing
raised, because `contact_quality` still populated and the row was non-None.

That silently emptied the Spotlights "Standout performances" widget and the
prospect-detail "Last 15 games" viz, removed a 0.35-weighted recent-form input
from the Bayesian trade value (bayes_trade_value.py:1047), blanked the
`_latest_played_level` derivation in storage, and broke the daily incremental
refresh gate in a self-perpetuating way (the gate reads those same two lists to
learn how fresh a row is, so emptying them makes every affected player look
stale forever and get re-fetched nightly - inflating exactly the workload the
OOM fix existed to shrink).

The fix runs the two extractors in pass 1, off the FULL splits, before trimming.
These tests pin the contract from both ends: the extractors' field dependencies,
and the invariant that whatever the trim keeps must cover whatever they read.
"""

from __future__ import annotations

import inspect
import datetime as _dt
import re

import pytest

import statcast_metrics as sm

# FIXTURE DATE IS DERIVED, NOT HARDCODED (2026-08-14).
#
# It was "2026-07-30", and _extract_standout_games filters on a TRAILING WINDOW:
# `cutoff = date.today() - timedelta(days=window_days)` with window_days=14
# (statcast_metrics.py:267,284). So the fixture sat exactly ON the cutoff on
# 2026-08-13 and fell one day outside it on 2026-08-14, and both parametrisations
# of test_extractors_need_the_untrimmed_split went red at midnight with
# "fixture is not a standout" -- a test asserting its own fixture qualifies, which
# it no longer did.
#
# This is the SAME disease as test_farm_rank_and_letter_are_deterministic, which
# rotted to the day on 2026-08-13 against the INACTIVE_MONTHS cutoff. A fixture
# that must sit inside a rolling window has to be derived from today, or it is a
# time bomb with a known fuse length.
_FIXTURE_DATE = (_dt.date.today() - _dt.timedelta(days=2)).isoformat()


def _hitter_split() -> dict:
    return {
        "game": {"gamePk": 777001, "officialDate": _FIXTURE_DATE},
        "date": _FIXTURE_DATE,
        "_level": "AA",
        "isHome": True,
        "opponent": {"name": "Tulsa Drillers"},
        "stat": {"hits": "4", "atBats": "5", "homeRuns": "2", "rbi": "6",
                 "doubles": "1", "triples": "0", "baseOnBalls": "1",
                 "strikeOuts": "0"},
    }


def _pitcher_split() -> dict:
    s = _hitter_split()
    s["stat"] = {"inningsPitched": "7.0", "strikeOuts": "12", "earnedRuns": "0",
                 "hits": "2", "baseOnBalls": "1"}
    return s


def _slim(split: dict) -> dict:
    """The trim exactly as pass 1 applies it."""
    return {
        "game": {"gamePk": (split.get("game") or {}).get("gamePk")},
        "date": split.get("date"),
        "_level": split.get("_level"),
    }


# --------------------------------------------------------------------------
# The extractors genuinely need fields the trim drops. If these ever pass on
# a slimmed split, the extractors changed and the pass-1 harvest may be
# removable - check before deleting it.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("make,is_pitcher", [(_hitter_split, False),
                                             (_pitcher_split, True)])
def test_extractors_need_the_untrimmed_split(make, is_pitcher):
    full = make()
    assert sm._extract_standout_games([full], is_pitcher, limit=8), "fixture is not a standout"
    assert sm._extract_recent_games([full], is_pitcher, limit=15), "fixture produces no recent row"
    # The trimmed shape carries no stat block, so both must come back empty.
    assert sm._extract_standout_games([_slim(full)], is_pitcher, limit=8) == []
    assert sm._extract_recent_games([_slim(full)], is_pitcher, limit=15) == []


# --------------------------------------------------------------------------
# The structural guard: pass 1 must harvest BEFORE it trims.
# --------------------------------------------------------------------------

def _bulk_source() -> str:
    return inspect.getsource(sm.fetch_statcast_metrics_for_players)


def test_pass_one_harvests_the_extras_before_trimming():
    src = _bulk_source()
    assert "_harvest_extras" in src, (
        "pass 1 no longer harvests the gameLog extras; standout_games and "
        "recent_games will be empty on every row the bulk path writes")
    assert "_extract_standout_games" in src and "_extract_recent_games" in src, (
        "the harvest must call both extractors while the full splits are in hand")


def test_every_trim_site_is_preceded_by_a_harvest():
    """Both pass-1 branches (preloaded logs, and freshly fetched logs) trim.
    Neither may trim a split set that was not harvested first."""
    src = _bulk_source()
    trim_lines = [i for i, ln in enumerate(src.splitlines())
                  if "_slim_split(s) for s in" in ln]
    assert len(trim_lines) == 2, (
        f"expected exactly two trim sites (preloaded + fetch), found {len(trim_lines)}; "
        "a new one must harvest first")
    lines = src.splitlines()
    for i in trim_lines:
        window = "\n".join(lines[max(0, i - 12):i + 1])
        assert "_harvest_extras" in window, (
            f"trim at relative line {i} is not preceded by a harvest:\n{window}")


def test_harvest_is_not_inside_the_worker():
    """The harvest belongs in the parent, where the full split lives. Doing it
    in the worker would mean shipping untrimmed logs to the pool, which is the
    memory cost the trim exists to avoid."""
    worker = inspect.getsource(sm.fetch_statcast_metrics_for_player)
    assert "_harvest_extras" not in worker


def test_trim_keeps_what_the_parent_and_the_level_filter_read():
    """gamePk, date and _level are the three fields the parent's own passes
    read off a trimmed split; losing any of them breaks dedup or the level
    filter rather than a widget."""
    slim = _slim(_hitter_split())
    assert (slim.get("game") or {}).get("gamePk") == 777001
    assert slim.get("date") == _FIXTURE_DATE
    assert slim.get("_level") == "AA"


def test_extras_are_stamped_onto_the_row_after_the_worker_returns():
    src = _bulk_source()
    assert re.search(r"standout_games\s*=|\.standout_games", src), (
        "harvested extras are never applied to the row")
    assert re.search(r"recent_games\s*=|\.recent_games", src)


def test_harvest_failure_cannot_kill_the_run():
    """A widget must never take the pipeline down: the harvest swallows and
    logs. Verified by driving the real helper with a split that explodes on
    attribute access."""
    src = _bulk_source()
    m = re.search(r"def _harvest_extras\(.*?\n(?:.*\n)*?.*?_log\.debug", src)
    assert m, "the harvest has no exception guard"
