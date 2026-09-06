"""H-PRED-1: the Hall of Fame labels, and the censoring rule that governs them.

THE FAILURE MODE THIS FILE EXISTS FOR. A censored player scored zero is a label
that says "the voters decided no" about somebody the voters have not finished
deciding on. It biases every recent cohort toward zero, it does it hardest to the
best active candidates, and it is completely silent: the model trains, the AUC
looks fine, and the thing it learned is that being recent means being bad.

TWO LABELS, TWO CLOCKS. The writers' ballot closes, by election, by falling under
five percent, or by running out of years. The era and veterans committees never
formally close, and they have elected players fifty years after retirement, so on
a strict reading no non-inductee is ever a resolved zero for the any-route label
and the negative class is empty. The committee horizon is the stated assumption
that closes it, and the sensitivity table is what it costs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import hof_data as H          # noqa: E402

PANEL = ROOT / "data" / "hof_ballots.json"


@pytest.fixture(scope="module")
def b():
    if not PANEL.exists():
        pytest.skip("the ballot panel has not been built")
    return H.ballots()


def _panel(rows, inducted=None):
    """A hand-built panel, so the rules are tested rather than the data."""
    by_pid: dict = {}
    for r in rows:
        by_pid.setdefault(r["player_id"], []).append(r)
    return {"by_pid": by_pid, "inducted": inducted or {}, "doc": {}}


def _row(pid, year, num, pct, elected=False, dropped=False, route="BBWAA"):
    return {"player_id": pid, "election_year": year, "ballot_number": num,
            "vote_pct": pct, "elected": elected, "dropped_off": dropped,
            "route": route}


# --------------------------------------------------------------------------
# The censoring invariant
# --------------------------------------------------------------------------

def test_a_player_still_on_the_ballot_is_censored_not_zero():
    p = _panel([_row("x01", 2024, 1, 0.30), _row("x01", 2025, 2, 0.40)])
    got = H.label_bbwaa("x01", as_of_year=2026, ballots_=p)
    assert got is H.CENSORED, (
        f"a candidate in his second year at 40% was labelled {got}; his window "
        "is open and a zero there teaches the model that recent means bad")


def test_a_player_who_never_appeared_is_censored_not_zero():
    """Absence from the ballot is the SCREENING COMMITTEE's decision, not the
    writers'. This panel cannot tell one from the other, and treating absence as
    rejection would silently label thousands of marginal players as
    considered-and-refused."""
    assert H.label_bbwaa("nobody", as_of_year=2026, ballots_=_panel([])) is H.CENSORED


def test_an_elected_player_is_one():
    p = _panel([_row("x01", 2025, 1, 0.997, elected=True)])
    assert H.label_bbwaa("x01", as_of_year=2026, ballots_=p) == 1


def test_falling_under_five_percent_closes_the_window():
    p = _panel([_row("x01", 2020, 1, 0.03, dropped=True)])
    assert H.label_bbwaa("x01", as_of_year=2026, ballots_=p) == 0


def test_exhausting_the_ballot_closes_the_window():
    rows = [_row("x01", 2015 + i, i + 1, 0.30) for i in range(10)]
    p = _panel(rows)
    assert H.label_bbwaa("x01", as_of_year=2026, ballots_=p) == 0


def test_vanishing_from_the_ballot_closes_the_window():
    """THE RULE THAT ACTUALLY DECIDES, and the one the first implementation got
    wrong. A candidate appears every year until he is resolved, so a player
    whose last appearance predates the panel's most recent election has left the
    ballot. Counting appearances against a fifteen-year window instead left
    Barry Bonds censored, when he is the most-discussed resolved non-inductee in
    the game: the 2014 rule change shortened the window for players already on
    the ballot too."""
    rows = [_row("x01", 2013 + i, i + 1, 0.30) for i in range(10)]   # 2013-2022
    rows += [_row("other", 2026, 1, 0.10)]                            # panel runs to 2026
    p = _panel(rows)
    assert H.label_bbwaa("x01", as_of_year=2026, ballots_=p) == 0, (
        "a candidate who stopped appearing four elections ago is still censored")


def test_a_player_on_the_most_recent_ballot_is_still_open():
    rows = [_row("x01", 2024, 1, 0.30), _row("x01", 2025, 2, 0.35),
            _row("x01", 2026, 3, 0.40)]
    p = _panel(rows)
    assert H.label_bbwaa("x01", as_of_year=2026, ballots_=p) is H.CENSORED


def test_the_label_is_as_of_a_year_and_does_not_see_the_future():
    """Point-in-time, or a forward-chained model is reading its own answer."""
    p = _panel([_row("x01", 2025, 1, 0.997, elected=True)])
    assert H.label_bbwaa("x01", as_of_year=2024, ballots_=p) is H.CENSORED
    assert H.label_bbwaa("x01", as_of_year=2025, ballots_=p) == 1


# --------------------------------------------------------------------------
# The any-route label and its horizon
# --------------------------------------------------------------------------

def test_a_committee_induction_counts_for_the_any_route_label():
    p = _panel([_row("x01", 2000, 1, 0.20, dropped=True)],
               inducted={"x01": {"player_id": "x01", "election_year": 2022,
                                 "route": "VETERANS"}})
    assert H.label_any("x01", as_of_year=2026, ballots_=p) == 1
    # and the writers still said no
    assert H.label_bbwaa("x01", as_of_year=2026, ballots_=p) == 0


def test_an_open_committee_window_is_censored_not_zero():
    """Owner decision 12, requirement (a): the censoring rule is stated PER
    ROUTE, and a player whose committee window is still open is censored."""
    p = _panel([_row("x01", 2020, 1, 0.03, dropped=True)])
    assert H.label_any("x01", as_of_year=2026, ballots_=p) is H.CENSORED, (
        "a player whose writers' window closed six years ago was already "
        "written off by the committees, which have elected players fifty years "
        "after retirement")


def test_the_horizon_eventually_closes_the_any_route_label():
    p = _panel([_row("x01", 1980, 1, 0.03, dropped=True)])
    assert H.label_any("x01", as_of_year=2026, ballots_=p) == 0


def test_the_horizon_is_a_parameter_and_moves_the_label():
    p = _panel([_row("x01", 2000, 1, 0.03, dropped=True)])
    assert H.label_any("x01", as_of_year=2026, ballots_=p,
                       horizon_years=20) == 0
    assert H.label_any("x01", as_of_year=2026, ballots_=p,
                       horizon_years=40) is H.CENSORED


def test_the_horizon_is_labelled_an_assumption_where_it_is_defined():
    src = (ROOT / "hof_data.py").read_text(encoding="utf-8")
    i = src.index("COMMITTEE_HORIZON_YEARS")
    head = src[max(0, i - 1500):i]
    assert "assumption" in head.lower(), (
        "the committee horizon is the one arbitrary constant in the label and "
        "it is not marked as an assumption; a reader will take it for a fact")
    assert "arbitrary" in head.lower()


# --------------------------------------------------------------------------
# Against the real panel
# --------------------------------------------------------------------------

def test_the_real_panel_labels_known_hall_of_famers(b):
    for pid in ("ruthba01", "mayswi01", "johnswa01"):
        assert H.label_any(pid, as_of_year=2026, ballots_=b) == 1, (
            f"{pid} is not labelled a Hall of Famer by the any-route label")


def test_the_real_panel_labels_a_known_non_inductee(b):
    """Barry Bonds is the most-discussed non-inductee in the game: he exhausted
    the writers' ballot in 2022 without election."""
    assert H.label_bbwaa("bondsba01", as_of_year=2026, ballots_=b) == 0
    # And the committees have NOT acted, so the any-route label is censored
    # rather than zero: Bonds remains eligible for era-committee consideration.
    assert H.label_any("bondsba01", as_of_year=2026, ballots_=b) != 1


def test_the_frame_never_carries_a_censored_zero(b):
    """The invariant, run over the real universe rather than a fixture."""
    fr = H.label_frame(offline=True, as_of_year=2026, ballots_=b)
    for col, cen in (("label_bbwaa", "censored_bbwaa"),
                     ("label_any", "censored_any")):
        bad = fr[fr[cen] & fr[col].notna()]
        assert len(bad) == 0, (
            f"{len(bad)} rows are marked censored on {col} and carry a value")


def test_the_frame_has_both_classes(b):
    fr = H.label_frame(offline=True, as_of_year=2026, ballots_=b)
    for col in ("label_bbwaa", "label_any"):
        pos = int((fr[col] == 1).sum())
        neg = int((fr[col] == 0).sum())
        assert pos > 20 and neg > 20, (
            f"{col} has {pos} positives and {neg} negatives; a label with an "
            "empty class cannot train anything")


def test_the_sensitivity_table_shows_what_the_horizon_costs(b):
    s = H.label_sensitivity(offline=True, as_of_year=2026)
    assert set(s["by_horizon"]) >= {"15", "25", "40"}
    # A longer horizon can only censor more and resolve fewer.
    order = sorted(int(k) for k in s["by_horizon"])
    prev = None
    for h in order:
        cell = s["by_horizon"][str(h)]
        if prev is not None:
            assert cell["censored"] >= prev["censored"], (
                f"horizon {h} censors fewer players than a shorter one")
            assert cell["negative"] <= prev["negative"]
        prev = cell
    assert "assumption" in s["what_the_horizon_is"].lower()
