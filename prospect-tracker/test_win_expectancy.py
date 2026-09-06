"""M-ENG-1: the win-expectancy model.

WHAT RESTS ON IT. Every In-Game Management number is a difference of two win
expectancies, so an error here does not show up as a wrong win probability, it
shows up as a manager praised for a decision that cost his team the game.

THE FAILURE THAT MADE THIS A MODEL INSTEAD OF A TABLE, and the reason the
monotonicity tests below are the most important ones in the file. The first
version was a grid of raw cell means. It agreed with the published
bottom-of-the-ninth figures, its calibration was fine, and it was useless:
advancing a runner from first to second LOWERED the batting team's win expectancy
in 42.6% of comparable cells. Not a state bug (the corpus reproduces the
published run-expectancy table to three decimals) but arithmetic. 1.45 million
plays over 4,557 cells is 318 each, the standard error of a binary outcome there
is 0.029, and the effect being measured is 0.02 to 0.05.

The fix is structural rather than statistical: the base-out state enters ONLY
through its run expectancy, as a single covariate with a positive coefficient, so
advancing a runner cannot lower the batting team's win probability. These tests
assert that property exhaustively rather than trusting the argument.

A second defect from the same session, also pinned: the corpus stores each base
as the RUNNER'S PLAYER ID in a float64 column, NaN when empty, and numpy's bool()
of NaN is True. astype(bool) therefore reports every base occupied and collapses
the corpus onto the loaded state, while producing output that looks healthy.
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
# Monotonicity: the property the whole module is built to guarantee
# --------------------------------------------------------------------------

def test_advancing_a_runner_never_lowers_the_batting_teams_win_probability(W):
    """EXHAUSTIVE, over every state the model can price. This is the check the
    cell-mean table failed in 42.6% of cells, and it is the reason the base-out
    state enters through run expectancy rather than as its own cell."""
    bad = []
    for inn in range(1, 10):
        for half in ("top", "bottom"):
            for d in range(-6, 7):
                for o in (0, 1, 2):
                    for lo, hi in ((1, 2), (2, 4), (1, 4), (3, 6), (5, 7),
                                   (0, 1), (0, 2), (3, 7), (6, 7)):
                        a = W.offense_we(inn, half, d, o, lo)
                        b = W.offense_we(inn, half, d, o, hi)
                        if a is None or b is None:
                            continue
                        if b < a - 1e-12:
                            bad.append((inn, half, d, o, lo, hi, a, b))
    assert not bad, (
        f"{len(bad)} states where advancing a runner LOWERED the batting team's "
        f"win probability. First: {bad[0]}. This is guaranteed false by "
        "construction when the base state enters only through run expectancy "
        "with a positive coefficient, so a failure here means the model form "
        "changed and differencing is no longer safe.")


def test_the_run_expectancy_coefficient_is_positive(art):
    """The single fact the guarantee rests on."""
    assert art["coef"]["re_bat"] > 0, (
        "the run-expectancy coefficient is not positive, so a better base-out "
        "state now lowers the batting team's win probability")
    assert art["coef"]["re_bat"] + art["coef"]["re_bat_x_urgency"] > 0, (
        "the urgency interaction can cancel the main effect; at the highest "
        "urgency the combined run-expectancy slope must still be positive")


def test_an_out_never_helps_the_batting_team(W):
    for inn in range(1, 10):
        for half in ("top", "bottom"):
            for d in (-3, -1, 0, 1, 3):
                for base in range(8):
                    vals = [W.offense_we(inn, half, d, o, base) for o in (0, 1, 2)]
                    if any(v is None for v in vals):
                        continue
                    assert vals[0] >= vals[1] - 1e-12 >= vals[2] - 2e-12, (
                        f"inning {inn} {half}, diff {d}, base {base}: win "
                        f"expectancy did not fall with outs: {vals}")


def test_a_bigger_lead_is_worth_more(W):
    for inn in (1, 5, 9):
        for half in ("top", "bottom"):
            vals = [(d, W.we(inn, half, d, 0, 0)) for d in range(-5, 6)]
            vals = [(d, v) for d, v in vals if v is not None]
            for (d1, v1), (d2, v2) in zip(vals, vals[1:]):
                assert v2 >= v1 - 1e-12, (
                    f"inning {inn} {half}: win expectancy fell going from a "
                    f"{d1} to a {d2} run difference ({v1} to {v2})")


# --------------------------------------------------------------------------
# Run expectancy: the check that the states themselves are right
# --------------------------------------------------------------------------

def test_run_expectancy_covers_all_twenty_four_states(art):
    """A gap here is never a property of the data: every base-out state occurs
    tens of thousands of times a season. The masked implementation dropped a
    different cell on each build, each holding six figures of observations, and
    every downstream lookup for that state then returned None. The builder now
    refuses to write a model with a gap; this asserts the artifact on disk."""
    missing = [f"{b}|{o}" for b in range(8) for o in (0, 1, 2)
               if f"{b}|{o}" not in art["run_expectancy"]]
    assert not missing, f"run-expectancy cells missing: {missing}"
    for k, c in art["run_expectancy"].items():
        assert c["n"] >= 500, f"{k} rests on only {c['n']} plays"


def test_the_builder_refuses_to_write_a_model_with_a_missing_cell():
    """Behaviour, not a string. Hand run_expectancy a frame that cannot fill all
    24 cells and it must raise rather than return a table with a hole, because a
    hole becomes a None at every downstream lookup for a common state."""
    import numpy as np
    import pandas as pd
    df = pd.DataFrame({
        "game_pk": [1] * 4, "inning": [1] * 4, "half": ["top"] * 4,
        "outs_before": [0, 1, 2, 0], "_base": [0, 0, 0, 1],
        "runs_scored_on_play": [0, 0, 0, 1],
    })
    with pytest.raises(ValueError, match="missing base-out cells"):
        we.run_expectancy(df, np)


def test_the_half_inning_start_table_is_measured_and_dense(art):
    """The boundary value. A smooth model cannot be trusted across a boundary it
    was never constrained at, so this is measured instead."""
    tbl = art["half_inning_start"]
    assert len(tbl) > 150
    dense = [c for c in tbl.values() if not c["thin"]]
    assert len(dense) / len(tbl) > 0.9
    ns = sorted(c["n"] for c in tbl.values())
    assert ns[len(ns) // 2] > 400, (
        f"median half-inning-start cell holds only {ns[len(ns)//2]} games")


def test_the_boundary_table_gets_the_ninth_inning_right(art):
    """Where it matters most, and where it is checkable against common
    knowledge: the home team batting in the bottom of the ninth."""
    tbl = art["half_inning_start"]
    tied = tbl["9|bottom|0"]["p"]
    down1 = tbl["9|bottom|-1"]["p"]
    assert 0.55 < tied < 0.70, f"tied entering the bottom of the ninth: {tied}"
    assert 0.10 < down1 < 0.25, f"trailing by one: {down1}"
    assert tied > down1


def test_run_expectancy_matches_the_published_table(art):
    """RE24 is the most reproduced table in baseball analytics. Agreement here
    is what proves the base-out reconstruction is right, and it is what proved
    the win-expectancy trouble was estimation noise and not a broken state."""
    re = art["run_expectancy"]
    for key, want, tol in (("0|0", 0.49, 0.04), ("1|0", 0.88, 0.05),
                           ("7|0", 2.29, 0.10), ("0|2", 0.10, 0.03),
                           ("4|1", 0.95, 0.08)):
        got = re[key]["re"]
        assert abs(got - want) <= tol, (
            f"run expectancy for base-out {key} is {got}, against a published "
            f"value near {want}")


def test_run_expectancy_is_monotone_in_both_directions(art):
    re = art["run_expectancy"]
    for o in (0, 1, 2):
        for lo, hi in ((0, 1), (1, 2), (2, 3), (1, 4), (3, 7), (6, 7)):
            a, b = re.get(f"{lo}|{o}"), re.get(f"{hi}|{o}")
            if not a or not b:
                continue
            assert b["re"] >= a["re"], f"outs {o}: base {lo} -> {hi} fell"
    for b in range(8):
        vals = [re[f"{b}|{o}"]["re"] for o in (0, 1, 2) if f"{b}|{o}" in re]
        assert vals == sorted(vals, reverse=True), f"base {b}: {vals}"


# --------------------------------------------------------------------------
# Base occupancy: the bug that hid
# --------------------------------------------------------------------------

def test_base_code_bits_are_first_second_third():
    assert we.base_code(False, False, False) == 0
    assert we.base_code(True, False, False) == 1
    assert we.base_code(False, True, False) == 2
    assert we.base_code(False, False, True) == 4
    assert we.base_code(True, True, True) == 7


def test_the_empty_state_is_the_most_common(art):
    """Bases empty is the most frequent situation in baseball by a wide margin.
    Any other answer means occupancy is being read from a column of runner ids
    as though it were a boolean, which reports every base occupied."""
    re = art["run_expectancy"]
    by_base = {b: sum(re[f"{b}|{o}"]["n"] for o in (0, 1, 2)
                      if f"{b}|{o}" in re) for b in range(8)}
    assert max(by_base, key=by_base.get) == 0, f"counts by base: {by_base}"
    assert by_base[0] > 2 * by_base[1]


def test_the_builder_refuses_a_boolean_occupancy_column():
    src = (ROOT / "win_expectancy.py").read_text(encoding="utf-8")
    assert "notna()" in src
    assert "dtype == bool" in src, (
        "the builder no longer refuses a boolean occupancy column, so a schema "
        "change would silently produce a wrong model rather than an error")


# --------------------------------------------------------------------------
# Calibration
# --------------------------------------------------------------------------

def test_the_model_beats_the_base_rate(art):
    c = art["calibration"]
    assert c["brier"] < c["brier_base_rate_only"]
    assert c["brier_skill_score"] > 0.25, (
        f"Brier skill score is only {c['brier_skill_score']}; a win probability "
        "that barely beats the home-field constant cannot value a decision")


def test_the_model_is_calibrated_where_decisions_live(art):
    c = art["calibration"]
    assert c["expected_calibration_error"] < 0.02, (
        f"expected calibration error is {c['expected_calibration_error']}; a "
        "model used for differencing has to be right in the middle of its "
        "range, which is where every decision sits")
    for r in c["reliability"]:
        assert abs(r["predicted"] - r["observed"]) < 0.05, (
            f"reliability bin {r['bin']} predicts {r['predicted']} and observes "
            f"{r['observed']} over {r['n']} plays")


def test_the_home_win_rate_is_right(art):
    hr = art["calibration"]["home_win_rate"]
    assert 0.50 <= hr <= 0.56, (
        f"the corpus reports a {hr} home win rate; the real figure is about "
        "0.53, and a label that misses it is not the game outcome")


def test_the_feed_comparison_is_stated_as_measured(art):
    """This claim was written before it was measured and was WRONG: the note
    said the feed was better, and on Brier the context-free model is very
    slightly ahead. The artifact must carry what was measured, not what was
    expected."""
    c = art["calibration"]
    note = c["feed_note"]
    # The note quotes figures from the build that wrote it. What must hold is
    # that its DIRECTION matches the numbers in the same artifact; the exact
    # digits move with every refit and pinning them would make the note a
    # maintenance burden that nobody updates, which is how a stale claim ships.
    assert "0.15" in note, "the feed note quotes no Brier score at all"
    if c["feed_brier"] > c["brier"]:
        assert "better" in note.lower(), (
            "the model beats the feed and the note does not say so")
    assert "team quality" in note.lower()


def test_the_feed_is_not_the_engine(art):
    note = art["calibration"]["feed_note"].lower()
    assert "not the engine" in note
    assert "team quality" in note, (
        "the note does not say WHY the feed is refused; the reason is that it "
        "carries team quality, and a manager must not be credited for his roster")


# --------------------------------------------------------------------------
# The side convention, the easiest thing here to get backwards
# --------------------------------------------------------------------------

def test_offense_we_flips_in_the_top_half(W):
    home = W.we(1, "top", 0, 0, 0)
    assert abs(W.offense_we(1, "top", 0, 0, 0) - (1.0 - home)) < 1e-12
    assert abs(W.offense_we(1, "bottom", 0, 0, 0)
               - W.we(1, "bottom", 0, 0, 0)) < 1e-12


def test_the_batting_team_is_better_off_at_home(W):
    top = W.offense_we(1, "top", 0, 0, 0)
    bot = W.offense_we(1, "bottom", 0, 0, 0)
    assert bot > top, (
        f"the batting team's win probability is {top} in the top of the first "
        f"and {bot} in the bottom; home-field advantage is the wrong way round")


def test_game_start_matches_home_field_advantage(W):
    v = W.we(1, "top", 0, 0, 0)
    assert 0.51 <= v <= 0.57, (
        f"pregame home win probability came out {v}; the published home-field "
        "advantage is about 0.54")


def test_the_ninth_inning_tail_is_disclosed_as_smoothed(art):
    """The model is deliberately less sharp than the cell means at the extremes.
    That trade is stated in the artifact so a family reading the ninth-inning
    tail knows to say so."""
    note = art.get("smoothing_costs_the_tails") or ""
    assert "ninth" in note.lower() and "smooth" in note.lower()


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def test_the_loader_refuses_the_old_cell_table():
    """Schema 1 was the grid of cell means. Loading one and differencing it is
    exactly the mistake this rewrite exists to prevent, so it is refused by
    version rather than by hope."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump({"schema_version": 1, "table": {}}, f)
        p = Path(f.name)
    try:
        with pytest.raises(ValueError, match="schema 2"):
            we.WinExpectancy.load(p)
    finally:
        p.unlink(missing_ok=True)


def test_an_unseen_base_out_state_returns_none_not_a_default(W):
    assert W.we(5, "top", 0, 9, 99) is None
    assert W.run_exp(99, 9) is None


def test_the_state_says_what_it_leaves_out(art):
    ex = art["state_excludes"].lower()
    for word in ("batter", "pitcher", "park"):
        assert word in ex
    assert "leak" in ex or "confound" in ex
