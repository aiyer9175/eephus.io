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

The fourth is the census. Every identity above holds INSIDE the population, and
all of them passed while the population was missing 40.56% of its caught
stealings (audit F02-01). So one block compares the population with the corpus
it was read from, and holds priced plus excluded equal to the corpus count.
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


@pytest.fixture(scope="module")
def priced():
    """The live attempt frame, computed once for every test that needs it."""
    if not (M.CORPUS / "events").is_dir() or not (M.CORPUS / "plays").is_dir():
        pytest.skip(".cache/pbp_corpus is not on this machine")
    if not (ROOT / "data" / "win_expectancy.json").exists():
        pytest.skip("the win-expectancy model has not been built")
    return M.attempts()


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
    """EVERY counter, not two of them. Until 2026-09-11 this asserted only
    prior_state_change and origin_base_empty, so the counter that was short by
    2,455 (two_outs_crosses_the_boundary) was never even required to exist."""
    ex = art["excluded"]
    for k in ("prior_state_change", "origin_base_empty",
              "no_play_row_to_price_from", "two_outs_crosses_the_boundary",
              "unpriceable_state"):
        assert k in ex, f"the exclusion counter {k!r} is not published"
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
# The census (audit F02-01, F02-02)
#
# A steal that ENDS a plate appearance is not a playEvent. It is the play's
# own result, so the corpus writes it to the plays table and never to the
# events table. This module read the events table alone and lost 40.56% of
# every caught stealing, 2,455 of them two-out attempts the exclusion row said
# it counted. Every test above passed throughout, because each one checked an
# identity INSIDE the population and nothing compared the population with the
# corpus it came from.
# --------------------------------------------------------------------------

class _FlatModel:
    """A stand-in win model: monotone in bases and outs, never undefined. The
    census tests are about which attempts are counted, not what they are worth,
    so nothing here should depend on a fitted model being on disk."""

    def offense_we(self, inning, half, score_diff, outs, base):
        return 0.5 + 0.02 * bin(int(base)).count("1") - 0.1 * int(outs)

    def half_inning_start(self, inning, half, lead):
        return 0.5


def _tiny_corpus(root: Path, season: str = "2099") -> Path:
    """Five plate appearances, each a case the census has to get right.

      ab 0  a mid-PA steal of second, an event row. Priced.
      ab 1  a caught stealing that ends the PA with two out: ONLY a play
            result. Must reach the two-out exclusion, not vanish.
      ab 2  a caught stealing written BOTH as an event row and as the play
            result, same type. One attempt, priced once.
      ab 3  a steal of second (event row, two out) and then a caught stealing
            at third that ends the PA (play result, different type). Two real
            attempts; keying on the plate appearance alone would drop one.
            The play-result one follows a state change, so it is counted as
            prior_state_change.
      ab 4  a steal of third that ends the PA with one out: ONLY a play
            result, and priceable. The shape of the two real attempts
            (games 716359 and 824664) the repair added to the priced pool.
    """
    import pandas as pd

    (root / "events" / season).mkdir(parents=True)
    (root / "plays" / season).mkdir(parents=True)
    ev = pd.DataFrame({
        "game_pk": [1, 1, 1],
        "at_bat_index": [0, 2, 3],
        "index": [0, 0, 0],
        "event_type": ["stolen_base_2b", "caught_stealing_2b", "stolen_base_2b"],
    })
    nan = float("nan")
    pl = pd.DataFrame({
        "game_pk": [1, 1, 1, 1, 1],
        "at_bat_index": [0, 1, 2, 3, 4],
        "inning": [3, 3, 4, 4, 5],
        "half": ["top", "top", "bottom", "bottom", "top"],
        "event_type": ["single", "caught_stealing_2b", "caught_stealing_2b",
                       "caught_stealing_3b", "stolen_base_3b"],
        "outs_before": [0, 2, 1, 2, 1],
        "on_first": [100.0, 101.0, 102.0, 103.0, nan],
        "on_second": [nan, nan, nan, nan, 104.0],
        "on_third": [nan, nan, nan, nan, nan],
        "home_score": [0, 0, 0, 0, 0],
        "away_score": [0, 0, 0, 0, 0],
        "runs_scored_on_play": [0, 0, 0, 0, 0],
    })
    ev.to_parquet(root / "events" / season / "events.parquet", index=False)
    pl.to_parquet(root / "plays" / season / "plays.parquet", index=False)
    return root


def test_a_plate_appearance_ending_steal_is_counted(tmp_path):
    """The regression test for F02-01, on a corpus small enough to read."""
    corpus = _tiny_corpus(tmp_path / "pbp_corpus")
    df = M.attempts(corpus=corpus, seasons=["2099"], we=_FlatModel())
    art = M.summarize(df)
    ex = art["excluded"]
    c = art["attempt_census"]
    assert c["from_the_events_table"] == 3
    assert c["from_the_play_result_only"] == 3, (
        "a steal that exists only as the play's own result was not read")
    assert c["play_result_already_an_event_row"] == 1, (
        "a play result that is also an event row of the same type must be "
        "counted once")
    assert ex["two_outs_crosses_the_boundary"] == 2, (
        f"two two-out attempts, one of them only a play result; counted {ex}")
    assert ex["prior_state_change"] == 1, (
        "the caught stealing at third that follows a steal of second in the "
        "same plate appearance is a second attempt; keying on the plate "
        "appearance alone drops it")
    assert art["n_attempts_priced"] == 3
    got = sorted(zip(df["at_bat_index"].astype(int), df["event_type"]))
    assert got == [(0, "stolen_base_2b"), (2, "caught_stealing_2b"),
                   (4, "stolen_base_3b")]
    assert c["total"] == 6 and c["priced_plus_excluded"] == 6
    assert c["reconciles"] is True


def test_the_attempt_census_reconciles_with_the_corpus(priced):
    """THE LAW, over the live corpus: every steal attempt the corpus holds is
    either priced or counted in an exclusion, exactly once.

    The corpus side is counted here, independently of management.py: steal
    event types from the events table, plus steal event types on the play
    result that are not already an event row of the same type in the same
    plate appearance. event_type stays in the key; see _tiny_corpus ab 3.
    """
    import pandas as pd

    key = ["game_pk", "at_bat_index", "event_type"]
    seasons = sorted(p.name for p in (M.CORPUS / "events").iterdir() if p.is_dir())
    n_ev = n_po = 0
    for s in seasons:
        efs = sorted((M.CORPUS / "events" / s).glob("*.parquet"))
        pfs = sorted((M.CORPUS / "plays" / s).glob("*.parquet"))
        if not efs or not pfs:
            continue
        ev = pd.concat([pd.read_parquet(f, columns=key) for f in efs])
        pl = pd.concat([pd.read_parquet(f, columns=key) for f in pfs])
        evs = ev[ev["event_type"].isin(M.STEAL_EVENTS)]
        pls = pl[pl["event_type"].isin(M.STEAL_EVENTS)]
        seen = set(map(tuple, evs[key].to_numpy().tolist()))
        n_ev += len(evs)
        n_po += sum(1 for t in map(tuple, pls[key].to_numpy().tolist())
                    if t not in seen)
    ex = priced.attrs["excluded"]
    c = priced.attrs["attempt_census"]
    accounted = int(len(priced)) + sum(v for k, v in ex.items()
                                       if k != "unpriceable_state")
    assert c["from_the_events_table"] == n_ev
    assert c["from_the_play_result_only"] == n_po
    assert accounted == n_ev + n_po, (
        f"priced plus excluded is {accounted:,} and the corpus holds "
        f"{n_ev + n_po:,} steal attempts ({n_ev:,} event rows + {n_po:,} that "
        "exist only as a play result). An attempt that is neither priced nor "
        "counted is the defect this test was written against.")


def test_the_published_census_closes(art):
    """The same law over the ARTIFACT, which is what the page renders."""
    c = art.get("attempt_census")
    assert c, ("data/management_running.json carries no attempt_census; "
               "rebuild it with python management.py")
    assert c["total"] == c["from_the_events_table"] + c["from_the_play_result_only"]
    assert art["n_attempts_priced"] + sum(art["excluded"].values()) == c["total"]
    assert c["priced_plus_excluded"] == c["total"] and c["reconciles"] is True
    assert c["from_the_play_result_only"] > 0, (
        "no attempt was read off a play result. On any real corpus the "
        "plate-appearance-ending caught stealings are there, so the plays "
        "table is not being read.")


# --------------------------------------------------------------------------
# The decision, not the outcome
# --------------------------------------------------------------------------

def test_the_decision_is_priced_at_the_league_rate_not_the_runners(art):
    note = art["league_average_is_deliberate"].lower()
    assert "roster fact" in note and "not a manager's decision" in note


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
    75.03%, summed decision value -0.19 wins.

    RE-MEASURED 2026-09-10 on the repaired win model (audit F07-02, which removed
    a post-play score from the fit and every query). Same 11,977 attempts: success
    75.00% against a break-even of 75.29%, summed decision value -2.60 wins. The
    FINDING is unchanged, and that is worth stating plainly: managers still run
    the stolen base at the point of indifference, and the gap is still inside a
    third of a percentage point. What moved is the price, not the verdict.
    """
    v = art["by_target"]["2B"]
    assert v["n"] > 10000
    gap = v["success_rate"] - v["swing_weighted_breakeven_p"]
    assert abs(gap) < 0.02, (
        f"the league's stolen-base success rate now sits {gap:+.4f} from its "
        "swing-weighted break-even, against -0.0029 on 2026-09-10. That is a "
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
        "figure is about 45% (it read 40% until the 2026-09-11 census repair "
        "added the plate-appearance-ending caught stealings), and a large move "
        "means the exclusion is selecting something other than what it claims")


def test_no_attempt_is_priced_so_that_being_caught_helps(art, priced):
    """The property the two-out exclusion buys, and the reason it is worth 45%
    of the sample."""
    src = (ROOT / "management.py").read_text(encoding="utf-8")
    assert "two_outs_crosses_the_boundary" in src
    df = priced
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
