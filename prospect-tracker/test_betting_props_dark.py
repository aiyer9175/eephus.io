"""Dark grading for the HR and strikeout prop sub-models.

WHAT IT DISCHARGES. Owner decision 8 permits extending the prop market set only after
"the HR and strikeout sub-models have GRADED DARK against base rates". This is that
grade, and a dark grade is the only kind available: zero prop odds have ever been
captured, so owner decision 6's accuracy leg, which is defined against the market, is
unreachable for every prop market.

THE THREE DEFECTS THESE TESTS EXIST FOR, all of which produce plausible output:

  1. A LEAK. If a date's rows are folded into the accumulators before they are priced,
     a batter's home run helps predict itself. The result looks like a strong model.
  2. A SLIDING BURN-IN. If the cut is `int(n * 0.30)` rather than a frozen date, the
     completed-games cache grows and the constants are refitted on a different window
     every run, which is a constant chosen by looking at results.
  3. AN ARM THAT SILENTLY BECOMES ITS OWN BASELINE. The park arm was handed the inner
     park_factors mapping while its helper looked for the outer document, so every org
     defaulted to neutral and the arm came out BYTE-IDENTICAL to the arm it extends. It
     reported a perfect null and looked like a finding.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import betting_props_dark as B          # noqa: E402

ART = ROOT / "data" / "betting_props_dark_eval.json"


@pytest.fixture(scope="module")
def art():
    if not ART.exists():
        pytest.skip("the dark grade has not been run")
    return json.loads(ART.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# The leak defence
# --------------------------------------------------------------------------

def test_a_row_is_priced_before_its_own_date_is_folded_in():
    """THE LEAK TEST. Two batters, two dates. The first date must be priced from
    an empty accumulator, which means no league rate and no arms at all; the
    second must see only the first."""
    rows = [
        {"game_pk": 1, "date": "2026-04-01", "player_id": 7, "pa": 4, "hr": 4,
         "org": "AAA", "opp": "BBB", "home_org": "AAA"},
        {"game_pk": 2, "date": "2026-04-02", "player_id": 7, "pa": 4, "hr": 0,
         "org": "AAA", "opp": "BBB", "home_org": "AAA"},
    ]
    seen = []

    def price(state, r):
        seen.append((r["date"], state["lg_num"], state["lg_den"]))
        return {}

    B._walk_forward(rows, price, trials_key="pa", event_key="hr")
    assert seen[0] == ("2026-04-01", 0, 0), (
        "the first date was priced against a non-empty accumulator, so an "
        "outcome was folded in before it was predicted")
    assert seen[1] == ("2026-04-02", 4, 4), (
        f"the second date saw {seen[1]}, not the first date's 4 HR in 4 PA")


def test_every_row_on_one_date_sees_the_same_state():
    """Two games on the same day must not leak into each other either: the
    earlier game_pk is not earlier information."""
    rows = [
        {"game_pk": 1, "date": "2026-04-01", "player_id": 1, "pa": 4, "hr": 2,
         "org": "A", "opp": "B", "home_org": "A"},
        {"game_pk": 2, "date": "2026-04-01", "player_id": 2, "pa": 4, "hr": 0,
         "org": "C", "opp": "D", "home_org": "C"},
    ]
    states = []
    B._walk_forward(rows, lambda st, r: states.append((st["lg_num"], st["lg_den"])) or {},
                    trials_key="pa", event_key="hr")
    assert states[0] == states[1] == (0, 0)


# --------------------------------------------------------------------------
# The frozen burn-in
# --------------------------------------------------------------------------

def test_the_burn_in_cut_is_a_frozen_date_not_a_fraction():
    src = (ROOT / "betting_props_dark.py").read_text(encoding="utf-8")
    assert 'BURN_IN_CUT_DATE = "2026-05-12"' in src
    assert "int(n * 0.30)" not in src and "int(len(" not in src.split(
        "BURN_IN_CUT_DATE")[0][-200:]


def test_the_artifact_records_the_cut_it_used(art):
    assert art["burn_in_cut_date"] == B.BURN_IN_CUT_DATE


def test_no_eval_row_predates_the_cut(art):
    """Rows before the cut train the constants and must never be graded."""
    for mkt in ("home_runs", "strikeouts"):
        b = art.get(mkt) or {}
        if b:
            assert b["n_burn_in"] > 0 and b["n_eval"] > 0


# --------------------------------------------------------------------------
# Probability helpers
# --------------------------------------------------------------------------

def test_p_at_least_one_is_the_binomial_complement():
    assert B.p_at_least_one(0.0, 5) == 0.0
    assert B.p_at_least_one(1.0, 5) == 1.0
    assert abs(B.p_at_least_one(0.1, 1) - 0.1) < 1e-12
    assert abs(B.p_at_least_one(0.1, 2) - (1 - 0.9 ** 2)) < 1e-12


def test_the_binomial_tail_respects_its_support_cap():
    """The whole structural argument for the binomial: a starter cannot strike
    out more batters than he faces."""
    assert B.p_over_binom(0.25, 3, 5.5) == 0.0
    assert 0.0 < B.p_over_binom(0.25, 30, 5.5) < 1.0


def test_poisson_puts_mass_above_the_cap_and_the_binomial_does_not():
    """Stated in the shipped reason string, so it is checked rather than
    asserted: at six trials Poisson still prices a 6-plus outcome above zero."""
    assert B.p_over_poisson(0.25 * 6, 5.5) > 0.0
    assert B.p_over_binom(0.25, 6, 5.5) >= 0.0


def test_nb2_reduces_to_poisson_at_zero_dispersion():
    for line in (2.5, 5.5):
        assert abs(B.p_over_nb2(5.0, 0.0, line) - B.p_over_poisson(5.0, line)) < 1e-9


def test_nb2_has_a_fatter_tail_than_poisson():
    assert B.p_over_nb2(5.0, 0.3, 8.5) > B.p_over_poisson(5.0, 8.5)


# --------------------------------------------------------------------------
# The park arm, which silently became its own baseline
# --------------------------------------------------------------------------

def test_the_park_helper_takes_the_park_factors_mapping():
    """It was handed the inner mapping while looking for the outer document, so
    every org defaulted to neutral and the park arm was byte-identical to the
    arm it extends."""
    pf = {"LAD": {"hr": 125}, "KCR": {"hr": 88}}
    assert B._park_hr_index("LAD", pf) == 1.25
    assert B._park_hr_index("KCR", pf) == 0.88


def test_an_absent_org_prices_neutral_rather_than_dropping_or_inverting():
    """ATH is absent from data/fa_meta.json and owns real home games. A KeyError
    would drop them and a zero would invert them."""
    assert B._park_hr_index("ATH", {"LAD": {"hr": 125}}) == 1.0
    assert B._park_hr_index("ANY", {}) == 1.0
    assert B._park_hr_index("BAD", {"BAD": {"hr": "not a number"}}) == 1.0


def test_the_park_arm_is_not_identical_to_the_arm_it_extends(art):
    hr = art.get("home_runs") or {}
    arms = hr.get("arms") or {}
    if "A3_eb_park" not in arms or "A2_eb" not in arms:
        pytest.skip("park arm not present")
    assert arms["A3_eb_park"]["brier"] != arms["A2_eb"]["brier"], (
        "the park arm scores byte-identically to the arm it extends, which "
        "means the park multiplier is not being applied and its null is an "
        "artifact rather than a finding")


def test_the_park_is_scored_against_what_it_extends(art):
    """An arm can clear the league bar purely on the component it inherits, so
    a park arm scored only against the league constant says nothing about the
    park."""
    hr = art.get("home_runs") or {}
    assert "structure_leg" in hr
    leg = hr["structure_leg"].get("A3_eb_park") or {}
    assert "paired_delta_vs_A2_eb" in leg


# --------------------------------------------------------------------------
# The estimator
# --------------------------------------------------------------------------

def test_the_bootstrap_resamples_games_not_rows(art):
    b = art["bootstrap"]
    assert b["resampling_unit"] == "game_pk"
    assert "park" in b["why"] and "umpire" in b["why"]


def test_a_clears_flag_agrees_with_its_own_interval(art):
    for mkt in ("home_runs", "strikeouts"):
        blk = art.get(mkt) or {}
        for group in ("arms", "structure_leg", "pmf_line_leg"):
            for name, v in (blk.get(group) or {}).items():
                ci = v.get("ci95")
                if ci is None or "clears" not in v:
                    continue
                assert v["clears"] is (ci[1] < 0), (
                    f"{mkt}/{group}/{name}: clears={v['clears']} with CI {ci}")


def test_a_non_clearing_arm_says_which_kind_of_failure_it_is(art):
    """"Inside the noise" and "measurably worse" are different results and a
    verdict that blurs them lets a wrong-signed arm read as unproven."""
    for mkt in ("home_runs", "strikeouts"):
        blk = art.get(mkt) or {}
        for group in ("arms", "structure_leg", "pmf_line_leg"):
            for name, v in (blk.get(group) or {}).items():
                ci, verdict = v.get("ci95"), v.get("verdict")
                if ci is None or v.get("clears"):
                    continue
                if ci[0] > 0:
                    assert "WRONG side" in verdict, f"{mkt}/{name}: {verdict}"
                else:
                    assert "contains zero" in verdict, f"{mkt}/{name}: {verdict}"


# --------------------------------------------------------------------------
# The findings, pinned
# --------------------------------------------------------------------------

def test_the_unshrunk_home_run_rate_is_worse_than_knowing_nothing(art):
    """The result most likely to be assumed away. A batter with a dozen plate
    appearances and one homer reads as a 200-homer pace."""
    a = (art["home_runs"]["arms"] or {}).get("A1_unshrunk") or {}
    assert a["paired_delta_vs_A0_league"] > 0
    assert a["ci95"][0] > 0, (
        "the unshrunk rate is no longer measurably worse than the league "
        "constant; that is a real change and the shrinkage argument needs "
        "re-reading")


def test_the_shrunk_home_run_rate_clears_but_is_tiny(art):
    """It clears, and headlining it would be dishonest: it recovers well under
    two percent of the baseline Brier."""
    hr = art["home_runs"]
    a = hr["arms"]["A2_eb"]
    base = hr["arms"]["A0_league"]["brier"]
    assert a["clears"] is True
    assert abs(a["paired_delta_vs_A0_league"]) / base < 0.02


def test_the_park_index_buys_nothing_on_top_of_the_batter_rate(art):
    leg = art["home_runs"]["structure_leg"]["A3_eb_park"]
    assert leg["clears"] is False
    assert leg["ci95"][0] < 0 < leg["ci95"][1], (
        f"the park structure leg is no longer a clean null: {leg['ci95']}")


def test_the_strikeout_champion_clears_by_a_real_margin(art):
    kk = art["strikeouts"]
    a = kk["arms"]["B2_eb"]
    base = kk["arms"]["B0_league"]["brier"]
    assert a["clears"] is True
    assert abs(a["paired_delta_vs_B0_league"]) / base > 0.05, (
        "the strikeout champion's edge has fallen below five percent of its "
        "baseline; it was about ten percent, and it is the only prop result "
        "with any size to it")


def test_the_served_distribution_wins_the_line_leg(art):
    """The shipped choice is the binomial. If Poisson or NB2 ever beat it here,
    the served distribution is wrong and this is where that surfaces."""
    leg = art["strikeouts"]["pmf_line_leg"]
    for alt in ("B2_poisson", "B2_nb2"):
        assert leg[alt]["paired_delta_vs_B2_binom"] > 0, (
            f"{alt} now prices the 5.5 line better than the served binomial")


def test_the_pmf_leg_says_it_is_only_the_line_leg(art):
    note = art["strikeouts"]["pmf_leg_note"].lower()
    assert "not a verdict on which" in note or "different question" in note


def test_the_shipped_reason_no_longer_argues_backwards_from_dispersion():
    """The reason string used to cite Poisson over-dispersion as grounds to
    reject it. Measured, the real count over-disperses against the binomial by
    1.400x and against Poisson by only 1.095x, so that argument pointed the
    wrong way. The CHOICE survives on the line leg; the reason had to change."""
    import betting_export
    r = betting_export.PROPS_DISTRIBUTIONS["Strikeouts"]["reason"]
    assert "1.400" in r and "1.095" in r, (
        "the strikeout reason no longer carries the measured dispersion ratios")
    assert "does NOT fit the shape better" in r
    assert "over-disperses (variance lam" not in r


# --------------------------------------------------------------------------
# What it may not be read as
# --------------------------------------------------------------------------

def test_the_artifact_refuses_to_be_read_as_a_market_grade(art):
    n = art["what_this_is_not"].lower()
    assert "not a grade against a market" in n
    assert "no slot" in n and "unreachable" in n


def test_coverage_names_its_shortfall(art):
    c = art["coverage"]
    assert "skipped" in c
    assert c["batter_games"] >= 40000, (
        f"only {c['batter_games']} batter-games; the population is smaller than "
        "the floor this grade was measured on")
    assert c["starter_games"] >= 3000


def test_the_burn_in_sweep_publishes_its_own_flatness(art):
    s = art["home_runs"]["burn_in_sweep"]
    assert s["chosen"] is not None
    assert len(s["grid"]) >= 3
    assert "flat" in s["flatness_note"].lower(), (
        "the sweep does not disclose its flatness, so a reader cannot tell "
        "whether the fitted constant is doing any work")
