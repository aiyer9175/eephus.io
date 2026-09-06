"""M-ENG-1: the win-expectancy table.

WHAT RESTS ON IT. Every In-Game Management number is a difference of two win
expectancies, so an error here does not show up as a wrong win probability, it
shows up as a manager being praised for a decision that cost his team the game.
The table is therefore checked three ways: internal shape, agreement with the
published literature, and agreement with the MLB feed's own live number.

THE BUG THAT MADE THIS FILE LONGER THAN IT LOOKS. The corpus stores each base as
the RUNNER'S PLAYER ID in a float64 column, NaN when empty. numpy's bool() of NaN
is True, so the first build read every base as occupied, collapsed 1.45 million
plays onto the bases-loaded state, and produced a 576-cell table that looked
perfectly healthy. Nothing about the output said it was wrong. The occupancy tests
below exist so that failure mode is loud next time.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import win_expectancy as we          # noqa: E402

ART = ROOT / "data" / "win_expectancy.json"


@pytest.fixture(scope="module")
def W():
    if not ART.exists():
        pytest.skip("data/win_expectancy.json has not been built")
    return we.WinExpectancy.load()


@pytest.fixture(scope="module")
def art():
    if not ART.exists():
        pytest.skip("data/win_expectancy.json has not been built")
    return json.loads(ART.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Base occupancy: the bug that hid
# --------------------------------------------------------------------------

def test_base_code_bits_are_first_second_third():
    assert we.base_code(False, False, False) == 0
    assert we.base_code(True, False, False) == 1
    assert we.base_code(False, True, False) == 2
    assert we.base_code(False, False, True) == 4
    assert we.base_code(True, True, True) == 7


def test_the_table_is_not_all_one_base_state(art):
    """The exact shape of the NaN bug. A table whose base states are all 7 is
    what `astype(bool)` on a runner-id column produces, and it is invisible from
    any summary statistic."""
    states = {int(k.split("|")[4]) for k in art["table"]}
    assert len(states) == 8, (
        f"the table covers only base states {sorted(states)}. All eight must "
        "appear; a single state means base occupancy is being read from a "
        "column of runner ids as though it were a boolean.")


def test_the_empty_state_is_the_most_common(art):
    """Bases empty is the most frequent situation in baseball by a wide margin.
    If some other state carries the most observations, occupancy is inverted or
    misread."""
    by_state = {}
    for k, c in art["table"].items():
        b = int(k.split("|")[4])
        by_state[b] = by_state.get(b, 0) + (c.get("own_n") or c["n"])
    assert max(by_state, key=by_state.get) == 0, (
        f"the most-observed base state is {max(by_state, key=by_state.get)}, "
        "not empty")


def test_the_builder_refuses_a_boolean_occupancy_column():
    src = (ROOT / "win_expectancy.py").read_text(encoding="utf-8")
    assert "notna()" in src
    assert "dtype == bool" in src, (
        "the builder no longer refuses a boolean occupancy column, so a schema "
        "change would silently produce a wrong table rather than an error")


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------

def test_every_value_is_a_probability(art):
    for k, c in art["table"].items():
        assert 0.0 <= c["we"] <= 1.0, f"{k} -> {c['we']}"


def test_thin_cells_are_backed_off_and_say_so(art):
    for k, c in art["table"].items():
        if c.get("backed_off"):
            assert c.get("backed_off_to")
            assert c.get("own_n", 0) < art["min_cell_n"]
        elif not c.get("thin"):
            assert c["n"] >= art["min_cell_n"], (
                f"{k} is served on {c['n']} observations without being marked "
                "backed off or thin")


def test_an_unseen_state_returns_none_not_a_default(W):
    """A decision priced off a made-up 0.5 is worse than one that reports it
    could not be priced."""
    assert W.we(9, "bottom", 5, 0, 0) is None or isinstance(
        W.we(9, "bottom", 5, 0, 0), float)
    assert W.we(99, "sideways", 0, 9, 99) is None


# --------------------------------------------------------------------------
# Agreement with the published literature
# --------------------------------------------------------------------------

def test_game_start_matches_home_field_advantage(W):
    """Top of the first, tied, nobody on, nobody out IS the pregame home win
    probability. The published figure is about 0.54."""
    v = W.we(1, "top", 0, 0, 0)
    assert v is not None
    assert 0.51 <= v <= 0.57, (
        f"pregame home win probability came out {v}; the published home-field "
        "advantage is about 0.54, and a table that disagrees at the start of "
        "the game disagrees everywhere")


def test_bottom_of_the_ninth_tied_matches_the_published_table(W):
    """Tango's win-expectancy tables give roughly 0.63, 0.57 and 0.52 for the
    bottom of the ninth, tied, bases empty, by outs. This is the single most
    quoted cell in the literature and the cheapest external check available."""
    vals = [W.we(9, "bottom", 0, o, 0) for o in (0, 1, 2)]
    assert all(v is not None for v in vals)
    for got, want in zip(vals, (0.63, 0.57, 0.52)):
        assert abs(got - want) <= 0.03, (
            f"bottom-9th tied cells came out {vals}; the published values are "
            "about 0.63, 0.57, 0.52")


def test_win_expectancy_falls_as_outs_accumulate(W):
    """For the team batting, an out is always bad. Checked in the bottom half,
    where the batting team is the home team the table is stated for."""
    for base in (0, 1, 2, 4):
        vals = [W.we(7, "bottom", 0, o, base) for o in (0, 1, 2)]
        if any(v is None for v in vals):
            continue
        assert vals[0] >= vals[1] >= vals[2] - 1e-9, (
            f"base state {base}: win expectancy did not fall with outs: {vals}")


def test_a_bigger_lead_is_worth_more(W):
    """Monotone in score difference, in the home team's favour, by definition."""
    vals = [(d, W.we(7, "top", d, 0, 0)) for d in (-3, -2, -1, 0, 1, 2, 3)]
    vals = [(d, v) for d, v in vals if v is not None]
    for (d1, v1), (d2, v2) in zip(vals, vals[1:]):
        assert v2 >= v1 - 1e-9, (
            f"win expectancy fell going from a {d1} to a {d2} run difference "
            f"({v1} to {v2})")


def test_runners_help_the_team_that_is_batting(W):
    """In the bottom half the home team bats, so putting a runner on must not
    lower the home team's win probability."""
    empty = W.we(7, "bottom", 0, 0, 0)
    for base in (1, 2, 4, 3, 6, 7):
        v = W.we(7, "bottom", 0, 0, base)
        if v is None or empty is None:
            continue
        assert v >= empty - 1e-9, (
            f"a runner on {we.BASE_LABELS[base]} lowered the batting team's win "
            f"probability ({empty} to {v})")


# --------------------------------------------------------------------------
# The side convention, which is the easiest thing in the module to get backwards
# --------------------------------------------------------------------------

def test_offense_we_flips_in_the_top_half(W):
    """The table is stated for the HOME team throughout. A decision family must
    call offense_we, because a manager's decision is good or bad for HIS team,
    and a sign error here inverts every verdict the module publishes."""
    home = W.we(1, "top", 0, 0, 0)
    assert abs(W.offense_we(1, "top", 0, 0, 0) - (1.0 - home)) < 1e-9
    assert abs(W.offense_we(1, "bottom", 0, 0, 0)
               - W.we(1, "bottom", 0, 0, 0)) < 1e-9


def test_the_batting_team_is_better_off_at_home(W):
    """Home-field advantage, read through offense_we: batting in the bottom of
    the first is worth more than batting in the top of it."""
    top = W.offense_we(1, "top", 0, 0, 0)
    bot = W.offense_we(1, "bottom", 0, 0, 0)
    assert bot > top, (
        f"the batting team's win probability is {top} in the top of the first "
        f"and {bot} in the bottom; home-field advantage is the wrong way round")


# --------------------------------------------------------------------------
# Agreement with the feed
# --------------------------------------------------------------------------

def test_the_feed_check_is_on_a_probability_scale(art):
    """The feed publishes PERCENT, 0.1 to 99.9. Comparing it to a 0/1 outcome
    without dividing reports a mean absolute error near 50, which is what the
    first run of the builder printed and what this test now prevents."""
    fa = art["feed_agreement"]
    mae = fa["mean_abs_error_of_feed_wp_vs_outcome"]
    assert mae is not None
    assert 0.0 <= mae <= 0.5, (
        f"the feed check reports a mean absolute error of {mae}; anything "
        "outside [0, 0.5] means it is comparing a percentage to a probability")
    assert mae < 0.45, (
        f"the feed's own win probability is barely better than a coin ({mae}); "
        "either the join is wrong or the outcome label is")


def test_the_feed_is_a_check_and_not_the_engine(art):
    note = art["feed_agreement"]["what_it_is"].lower()
    assert "check" in note and "never as the engine" in note


def test_the_state_says_what_it_leaves_out(art):
    ex = art["state_excludes"].lower()
    for word in ("batter", "pitcher", "park"):
        assert word in ex
    assert "leak" in ex or "confound" in ex, (
        "the artifact does not say WHY the state is deliberately thin; the "
        "reason is that any of those columns would let a manager's roster into "
        "his grade, and a future editor who does not know that will add one")
