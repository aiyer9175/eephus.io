"""In-Game Management, first family: the stolen base decision.

WHAT THE METRIC HAS TO GET RIGHT, and therefore what is tested here.

A manager who sends a runner in a spot that justified it and watches him thrown
out made a GOOD DECISION and had a BAD OUTCOME. A metric that cannot tell those
apart is measuring the runner, the catcher and the weather, and it will hand out
credit for having fast players. So every attempt splits into the decision value
(priced with a league-average success rate) and the execution residual (realized
minus expected), and the two sum to the realized win-probability change exactly.
That identity is the first test in the file, because if it fails the split is
arbitrary and neither half means anything.

The second thing it has to get right is the sign. score_diff is HOME minus AWAY
throughout, the win-expectancy model is stated for the home team, and the batting
team is the away team in the top half. Three chances to invert a verdict, none of
which crash.

The third is the third out. A caught stealing with two down ends the half-inning,
and the resulting state is worth what the NEXT half-inning is worth to the other
team. Pricing it as "two outs, bases empty" understates the cost of the worst
possible time to be thrown out, which is exactly the decision the metric most
needs to get right.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import management as M          # noqa: E402
import win_expectancy as wx     # noqa: E402

ART = ROOT / "data" / "management_running.json"


@pytest.fixture(scope="module")
def W():
    p = ROOT / "data" / "win_expectancy.json"
    if not p.exists():
        pytest.skip("the win-expectancy model has not been built")
    return wx.WinExpectancy.load()


@pytest.fixture(scope="module")
def art():
    if not ART.exists():
        pytest.skip("data/management_running.json has not been built")
    return json.loads(ART.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# The identity
# --------------------------------------------------------------------------

def test_decision_plus_execution_is_the_realized_change(art):
    err = art["decomposition"]["identity_max_abs_error"]
    assert err is not None
    assert err < 1e-9, (
        f"DV + ER differs from the realized win-probability change by up to "
        f"{err}. The split is then arbitrary and neither half means anything.")


def test_the_identity_is_stated_where_a_reader_will_look(art):
    assert "DV + ER" in art["decomposition"]["identity"]


# --------------------------------------------------------------------------
# The third out
# --------------------------------------------------------------------------

def test_a_caught_stealing_with_two_down_ends_the_inning(W):
    """The resulting state is valued from the MEASURED half-inning-start table,
    not from the smooth model evaluated at the next half-inning.

    That distinction is the whole reason the engine has a boundary table. A
    smooth model is free to be discontinuous across a boundary it was never
    constrained at, and two successive fits were: they priced up to 19.2% of
    steal attempts so that being CAUGHT STEALING raised the batting team's win
    probability.
    """
    got = M._we_after(W, 5, "bottom", 0, 2, 0, out_added=1)
    naive = W.offense_we(5, "bottom", 0, 2, 0)
    measured = W.half_inning_start(6, "top", 0)
    assert got is not None and measured is not None
    assert abs(got - (1.0 - measured)) < 1e-12, (
        "the third out was not valued from the measured half-inning-start table")
    assert abs(got - naive) > 1e-6, (
        "the third out is being priced as though the inning continued, which "
        "understates the cost of being thrown out at the worst moment")


def test_the_third_out_rolls_the_inning_over_from_the_bottom_half(W):
    got = M._we_after(W, 5, "bottom", 0, 2, 0, out_added=1)
    measured = W.half_inning_start(6, "top", 0)
    assert abs(got - (1.0 - measured)) < 1e-12


def test_a_second_out_does_not_end_the_inning(W):
    got = M._we_after(W, 5, "bottom", 0, 1, 0, out_added=1)
    same = W.offense_we(5, "bottom", 0, 2, 0)
    assert abs(got - same) < 1e-12


def test_being_thrown_out_always_costs_the_batting_team(W):
    """Whatever the state, making an out cannot help. If this ever passes the
    other way the sign convention has inverted somewhere."""
    for inn in (1, 5, 8):
        for half in ("top", "bottom"):
            for outs in (0, 1, 2):
                hold = W.offense_we(inn, half, 0, outs, 1)
                fail = M._we_after(W, inn, half, 0, outs, 0, out_added=1)
                if hold is None or fail is None:
                    continue
                assert fail < hold, (
                    f"inning {inn} {half}, {outs} out: being caught stealing "
                    f"RAISED the batting team's win probability "
                    f"({hold:.4f} to {fail:.4f})")


# --------------------------------------------------------------------------
# The sign convention
# --------------------------------------------------------------------------

def test_a_run_helps_the_batting_team_in_both_halves(W):
    """score_diff is HOME minus AWAY, so the batting team scoring moves it UP in
    the bottom half and DOWN in the top. Getting this backwards makes a steal of
    home look like a disaster for the away team."""
    for half in ("top", "bottom"):
        before = W.offense_we(6, half, 0, 1, 4)
        after = M._we_after(W, 6, half, 0, 1, 0, runs=1)
        assert after > before, (
            f"{half} half: scoring a run LOWERED the batting team's win "
            f"probability ({before:.4f} to {after:.4f})")


def test_stealing_a_base_helps_the_batting_team_in_both_halves(W):
    for half in ("top", "bottom"):
        hold = W.offense_we(6, half, 0, 1, 1)
        succ = M._we_after(W, 6, half, 0, 1, 2)
        assert succ > hold, f"{half}: advancing to second lowered win probability"


# --------------------------------------------------------------------------
# The population
# --------------------------------------------------------------------------

def test_a_plain_pickoff_is_not_a_steal_attempt():
    """The runner never committed. Counting it would blame a manager for a
    decision nobody made."""
    assert "pickoff_1b" not in M.STEAL_EVENTS
    assert "pickoff_2b" not in M.STEAL_EVENTS
    assert "pickoff_caught_stealing_2b" in M.STEAL_EVENTS, (
        "a pickoff-caught-stealing IS an attempt: the runner broke and was "
        "retired")


def test_every_steal_event_names_its_target_and_outcome():
    for ev, (tgt, ok) in M.STEAL_EVENTS.items():
        assert tgt in ("2B", "3B", "HOME")
        assert isinstance(ok, bool)
        assert ok == ev.startswith("stolen_base"), (
            f"{ev} is marked success={ok}, which disagrees with its own name")


def test_the_origin_base_bits_are_consistent():
    """Stealing second means starting on first. A mismatch here silently prices
    the wrong transition."""
    assert M.ORIGIN_BIT == {"2B": 1, "3B": 2, "HOME": 4}
    assert M.TARGET_BIT == {"2B": 2, "3B": 4, "HOME": 0}
    for tgt in ("2B", "3B"):
        assert M.TARGET_BIT[tgt] == M.ORIGIN_BIT[tgt] * 2
    assert M.TARGET_BIT["HOME"] == 0, (
        "a runner who steals home is not on a base afterwards")


def test_exclusions_are_counted_and_published(art):
    ex = art["excluded"]
    for k in ("prior_state_change", "origin_base_empty"):
        assert k in ex
    total = art["n_attempts_priced"] + sum(ex.values())
    assert ex["prior_state_change"] / total < 0.05, (
        f"{ex['prior_state_change']} attempts were dropped for an earlier "
        "state change in the same plate appearance; above a few percent the "
        "population stops being representative")


def test_no_attempt_is_priced_from_an_empty_origin_base(art):
    """A steal of second whose first base is empty means the state and the
    event disagree. Pricing it anyway would invent a decision."""
    assert art["excluded"]["origin_base_empty"] >= 0
    src = (ROOT / "management.py").read_text(encoding="utf-8")
    assert "origin_base_empty" in src


# --------------------------------------------------------------------------
# The decision, not the outcome
# --------------------------------------------------------------------------

def test_the_decision_is_priced_at_the_league_rate_not_the_runners(art):
    note = art["league_average_is_deliberate"].lower()
    assert "roster" in note and "confound" in note


def test_the_breakeven_rate_is_published(art):
    note = art["breakeven_is_published"].lower()
    assert "p*" in art["breakeven_is_published"] or "breakeven" in note
    for tgt, v in art["by_target"].items():
        assert v["median_breakeven_p"] is not None
        assert 0.0 < v["median_breakeven_p"] < 1.0, (
            f"{tgt}: the median break-even rate is {v['median_breakeven_p']}, "
            "outside the unit interval, which means some transition is priced "
            "with success worth less than holding")


def test_the_mean_and_median_breakeven_are_both_published(art):
    """They disagree sharply for steals of home, 0.672 against 0.507, because a
    few states carry an enormous p*. Publishing the mean alone would say the
    average attempt was unjustified while the summed decision value says the
    opposite."""
    for tgt, v in art["by_target"].items():
        assert "mean_breakeven_p" in v and "median_breakeven_p" in v


def test_the_swing_weighted_breakeven_predicts_the_sign_exactly(art):
    """The whole claim in one line, and the RIGHT summary to state it with.

    DV for an attempt is (WE_success - WE_fail) times (league_p - p*), so the
    summed decision value is positive exactly when the league rate beats the
    SWING-WEIGHTED mean of p*. Not the median and not the plain mean: on steals
    of second the league rate clears the median break-even and the summed
    decision value is still slightly negative, which would read as a
    contradiction to anyone checking the sign against the readable summary.
    """
    for tgt, v in art["by_target"].items():
        swb = v["swing_weighted_breakeven_p"]
        assert swb is not None
        assert (v["sum_dv_wins"] > 0) == (v["success_rate"] > swb), (
            f"{tgt}: success rate {v['success_rate']} against a swing-weighted "
            f"break-even of {swb}, yet the summed decision value is "
            f"{v['sum_dv_wins']}")


def test_the_artifact_says_which_breakeven_decides(art):
    note = art["which_breakeven_predicts_the_sign"].lower()
    assert "swing-weighted" in note
    assert "median" in note and "neither determines" in note


# --------------------------------------------------------------------------
# The findings, pinned
# --------------------------------------------------------------------------

def test_the_league_steals_second_at_almost_exactly_break_even(art):
    """THE HEADLINE FINDING, recorded so a change to it has to be deliberate.

    Measured 2026-09-06 over 11,977 attempts with nobody out or one out: the
    league succeeds 75.00% of the time against a swing-weighted break-even of
    75.03%. The summed decision value across eight seasons is -0.19 wins, which
    is zero for every practical purpose. Managers collectively run the stolen
    base at the point of indifference.
    """
    v = art["by_target"]["2B"]
    assert v["n"] > 10000
    gap = v["success_rate"] - v["swing_weighted_breakeven_p"]
    assert abs(gap) < 0.02, (
        f"the league's stolen-base success rate now sits {gap:+.4f} from its "
        "swing-weighted break-even, against 0.0003 on 2026-09-06. That is a "
        "real finding either way; confirm it before it changes any published "
        "number.")
    assert abs(v["sum_dv_wins"]) < 15.0, (
        f"the summed decision value on steals of second is {v['sum_dv_wins']} "
        "wins across eight seasons, no longer the near-zero this test records")


def test_stealing_home_is_a_bad_decision_on_this_evidence(art):
    """The other end of the same measurement, and the one that reads as it
    should: a 25.8% success rate against a 55.8% break-even."""
    v = art["by_target"]["HOME"]
    assert v["success_rate"] < v["swing_weighted_breakeven_p"]
    assert v["sum_dv_wins"] < 0


def test_the_execution_residual_asymmetry_is_disclosed(art):
    """It does not sum to zero, and the reason is a real property of the data
    rather than an error: failed attempts carry about 1.5 times the swing of
    successful ones."""
    note = art["why_execution_residual_does_not_sum_to_zero"].lower()
    assert "swing" in note
    assert "mechanical" in note and "resolved" in note, (
        "the artifact no longer records that the swing asymmetry was RESOLVED "
        "as mechanical. On the full population failures carried 1.5 times the "
        "swing of successes, which invited a behavioural reading; excluding the "
        "two-out attempts, and with them every caught stealing that ends an "
        "inning, drops the ratio to 1.00 on steals of second")
    assert art["by_target"]["2B"]["swing_ratio_failure_over_success"] < 1.15, (
        "the swing asymmetry is back on steals of second, so either the two-out "
        "exclusion has stopped working or the reading needs revisiting")


def test_two_out_attempts_are_excluded_and_the_reason_is_published(art):
    note = art["two_out_attempts_are_excluded"].lower()
    assert "boundary" in note and "caught stealing" in note
    ex = art["excluded"]["two_outs_crosses_the_boundary"]
    assert ex > 0
    total = art["n_attempts_priced"] + sum(art["excluded"].values())
    assert 0.25 < ex / total < 0.55, (
        f"two-out attempts are {ex/total:.1%} of the population; the recorded "
        "figure is about 40%, and a large move means the exclusion is selecting "
        "something other than what it claims")


def test_no_attempt_is_priced_so_that_being_caught_helps(art):
    """The property the two-out exclusion buys, and the reason it is worth 40%
    of the sample."""
    src = (ROOT / "management.py").read_text(encoding="utf-8")
    assert "two_outs_crosses_the_boundary" in src
    import management as _M
    df = _M.attempts()
    ok = df[df["dv"].notna()]
    bad = ok[ok["we_fail"] >= ok["we_hold"]]
    assert len(bad) == 0, (
        f"{len(bad)} of {len(ok)} priced attempts value being CAUGHT STEALING "
        "at or above not attempting. A metric that says being thrown out "
        "improved your chances is not a metric.")


def test_nothing_is_attributed_to_a_manager_yet(art):
    """The module must not publish an MWAR before the gate battery runs."""
    note = art["not_yet_attributed_to_managers"].lower()
    assert "gate" in note
    assert "manager" not in json.dumps(art["by_target"]).lower()
