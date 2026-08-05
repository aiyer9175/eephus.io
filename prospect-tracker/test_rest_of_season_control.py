# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Rest-of-season control pricing (owner ask, 2026-08-03) + the de-aged talent
basis (owner decision, 2026-08-05).

Until now `surNpv` summed only FIRST_SEASON onward, so a contract whose last
season is the one in progress produced no surplus anywhere on the platform and
every deadline rental read "not tradeable". A club still controls that player
for the balance of the season, and that is a real, tradeable asset.

This supersedes the reading recorded in docs/efv-2026-07-31/TRADE_BOARD_COVERAGE.md
("a pending free agent is not a trade asset"). A.J. Minter is the canonical
case: NYM, contract through 2026, $7,588,208 for the year. At ~32% of the
season left and a 0.23-WAR full-season projection he is worth about -$1.7M -
a slightly negative rental, because he is owed more than his remaining
production is worth. NEGATIVE IS A RESULT, NOT A BUG: the board has carried
negative-surplus rows since the v6 EV frame removed the $0 floor, and "we can
price him and he is worth less than his salary" is a different and far more
useful statement than "he has no trade value".

The leg applies to EVERY vet with a current-season salary, not only expiring
ones. Pricing Minter's remainder while ignoring Judge's would invent exactly
the class of inconsistency this codebase keeps paying to remove.

THE TALENT BASIS (2026-08-05). What the remainder is priced ON is a separate
question from how it is prorated, and the two must not be confused when reading
these tests. `war[0]` is the FIRST_SEASON projection, one aging year PAST the
season being sold, so the shipped basis de-ages it one year with the exact
inverse of the platform's own decay operator (proj_export.ROS_TALENT_BASIS,
`deaged_year1`). The proration assertions below are basis-agnostic and stay
exactly as strong as they were; the basis gets its own section at the end.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import bayes_trade_value as btv
import proj_export as pe
import value_framework as vf

DATA = Path(__file__).parent / "data"

# ---------------------------------------------------------------------------
# Hand-arithmetic anchors (2026-08-04d)
# ---------------------------------------------------------------------------
# The pricing tests below use LITERAL dollar figures worked out by hand, not a
# second call to the code under test. They only stay hand-checkable while the
# valuation config still carries the numbers they were derived from, so the
# first test asserts those numbers and every later literal cites its derivation.
#
# Above the top tier CENTER (breakpoint2 + 0.5 = 2.5 WAR) the convex smoothstep
# kernel is exactly linear at the 2plus rate (value_framework.py:_tiered_war_value
# -- the ramp has reached its final rate), so for w >= 2.5:
#       V(w) = w * RATE_2PLUS * (dpw / FLAT)
# which is the only regime where a literal can be written down without
# re-implementing the smoothstep. Every literal below sits in it.
FLAT = 11_740_000.0          # dollars_per_war.flat
RATE_2PLUS = 13_630_000.0    # dollars_per_war.tiered.rates["2plus"]
BREAKPOINTS = [1.0, 2.0]
LINEAR_FROM = 2.5            # breakpoints[1] + 0.5


def test_the_config_this_files_hand_arithmetic_is_derived_from():
    """Fails loudly if the anchors move, instead of letting every literal below
    fail one by one with no explanation."""
    cfg = vf._config()["dollars_per_war"]
    assert float(cfg["flat"]) == FLAT
    assert float(cfg["tiered"]["rates"]["2plus"]) == RATE_2PLUS
    assert [float(b) for b in cfg["tiered"]["breakpoints"]] == BREAKPOINTS
    assert str(cfg.get("kernel_mode", "smoothed")) == "smoothed"


# --------------------------------------------------------------------------
# The value accessor: surTotal wins, surNpv is the compatibility fallback
# --------------------------------------------------------------------------

def test_proj_value_prefers_sur_total():
    assert btv._proj_value_usd({"surTotal": 5, "surNpv": 9}) == 5


def test_proj_value_falls_back_to_sur_npv_on_a_stale_artifact():
    """A mlb_projections.json written before this change must still price.

    Without the fallback, one export cycle with a stale artifact would unprice
    the entire veteran board rather than degrade quietly.
    """
    assert btv._proj_value_usd({"surNpv": 9}) == 9


def test_proj_value_is_none_when_nothing_is_priced():
    assert btv._proj_value_usd({}) is None
    assert btv._proj_value_usd({"surTotal": None, "surNpv": None}) is None


def test_proj_value_keeps_a_negative_price():
    """A negative surplus is a price, not a missing value. If this coerced to
    None, every below-market rental would silently fall back to `unpriced`."""
    assert btv._proj_value_usd({"surTotal": -1_700_000}) == -1_700_000


# --------------------------------------------------------------------------
# The arithmetic
# --------------------------------------------------------------------------

def test_the_season_kernel_is_linear_at_the_top_rate():
    """The one regime where a hand literal is possible, asserted before it is
    used: at dpw == FLAT the scale factor is exactly 1, so a 4.00-WAR season is
    4 x $13.63M = $54,520,000 with nothing else in the arithmetic."""
    assert pe._season_value_usd(4.0, 0, FLAT) == pytest.approx(54_520_000.0)
    # ... and the level scales linearly in the $/WAR level: at 1.5x FLAT the
    # same season is 1.5 x $54.52M = $81,780,000.
    assert pe._season_value_usd(4.0, 0, 1.5 * FLAT) == pytest.approx(81_780_000.0)


def test_rest_of_season_surplus_is_the_whole_season_surplus_prorated_once():
    """surRos = f * (V(war[0]) - salary), all hand-computed.

    w = 4.00 WAR, dpw = FLAT (scale 1), so V(w) = 4 x $13,630,000 = $54,520,000.
    Salary $40,000,000 -> full-season surplus $14,520,000.
    A quarter of the season left -> 0.25 x $14,520,000 = $3,630,000.
    """
    assert pe._ros_surplus_usd(4.0, 40_000_000.0, 0.25, FLAT) == pytest.approx(
        3_630_000.0)
    # A rental owed more than his remaining production is worth prices NEGATIVE,
    # and that is a price: V(3.0) = 3 x $13.63M = $40,890,000, salary $60M,
    # full-season -$19,110,000, at 30% left -> -$5,733,000.
    assert pe._ros_surplus_usd(3.0, 60_000_000.0, 0.30, FLAT) == pytest.approx(
        -5_733_000.0)


def test_production_and_salary_prorate_on_the_SAME_factor():
    """The defect this replaced: the production leg priced V(f*w) - the shrunken
    remainder re-classified by the CONVEX tier kernel at a smaller player's
    per-win rate - while the salary leg prorated linearly. Two legs, two bases.

    Pinned three ways, all with hand numbers at dpw == FLAT:
      1. the leg is exactly LINEAR in f (halve the season left, halve the price);
      2. it equals f x (full-season surplus) computed independently;
      3. it is NOT the old V(f*w) - f*salary form wherever the two differ.
    """
    w, sal = 4.0, 40_000_000.0
    full = 54_520_000.0 - sal                     # = $14,520,000, by hand
    for f, expect in ((1.0, 14_520_000.0), (0.5, 7_260_000.0),
                      (0.25, 3_630_000.0), (0.1, 1_452_000.0)):
        got = pe._ros_surplus_usd(w, sal, f, FLAT)
        assert got == pytest.approx(expect)       # (1) and (2)
        assert got == pytest.approx(f * full)
    # (3) the old form, at f = 0.25: V(1.0) is priced off the LOW tier, nowhere
    # near a quarter of V(4.0). It must not be what ships.
    old_form = pe._season_value_usd(w * 0.25, 0, FLAT) - sal * 0.25
    assert old_form < 0.0 < pe._ros_surplus_usd(w, sal, 0.25, FLAT), (
        "the rest-of-season leg is pricing the PRORATED war through the convex "
        "kernel again (V(f*w)); it must prorate the full-season surplus")


def test_rest_of_season_is_undiscounted_and_unescalated():
    """t=0 matters: surNpv's own discount origin is FIRST_SEASON, so pricing the
    in-progress season at t=-1 would have inflated the remainder by (1 + r).

    The leg is the t=0 point of the kernel: a salary-free full season at 4.00 WAR
    is exactly the $54,520,000 the linear-regime literal above gives. The $/WAR
    escalator is read from config rather than pinned, because production
    currently configures it to 0.0 (data/value_framework.json) - a literal here
    would pin a live no-op instead of the mechanism.
    """
    infl = float(vf._config().get("dollars_per_war_inflation", 0.0))
    assert pe._ros_surplus_usd(4.0, 0.0, 1.0, FLAT) == pytest.approx(54_520_000.0)
    assert pe._season_value_usd(4.0, 0, FLAT) == pytest.approx(54_520_000.0)
    assert pe._season_value_usd(4.0, 1, FLAT) == pytest.approx(
        54_520_000.0 * (1.0 + infl))
    # No discount factor anywhere in the leg: $3,630,000, not $3,630,000/(1+r).
    r = float(vf._config()["discount_rate"])
    assert r > 0.0
    assert pe._ros_surplus_usd(4.0, 40_000_000.0, 0.25, FLAT) == pytest.approx(
        3_630_000.0)
    assert abs(pe._ros_surplus_usd(4.0, 40_000_000.0, 0.25, FLAT)
               - 3_630_000.0 / (1.0 + r)) > 100_000.0


# --------------------------------------------------------------------------
# The TALENT BASIS (owner decision, 2026-08-05)
# --------------------------------------------------------------------------
# `deaged_year1` runs the platform's own aging operator BACKWARDS one year. The
# operator itself is pure arithmetic on four numbers - the year-1 WAR, the
# projected exposure, and the two fitted curve deltas at the player's age - so
# it is pinned here with hand literals and STUBBED curve deltas. Stubbing is the
# point: the fitted curves are data that will move, while the algebra must not.
#
#   per-600-PA rate  = war1 / expo * 600
#   de-aged rate     = rate - curve_delta(war_rate, age)      [SUBTRACT: the
#   de-aged exposure = expo - curve_delta(pt, age)             forward step adds]
#   de-aged WAR      = de-aged rate * de-aged exposure / 600

_STUB_D_RATE = -0.40      # war_rate delta at age 34: aging COSTS 0.40 per 600 PA
_STUB_D_PT = -60.0        # pt delta at age 34: aging COSTS 60 PA


def _stub_engine(monkeypatch, war1=3.0, expo=600.0, side_role="OF"):
    """Replace the Marcel engine and the fitted curves with constants, so the
    de-aging ARITHMETIC is the only thing under test."""
    monkeypatch.setattr(pe.fp, "project_player",
                        lambda *a, **k: {"pt_proj": expo, "role": side_role})
    monkeypatch.setattr(pe.fp, "war_from_projection", lambda *a, **k: war1)
    monkeypatch.setattr(pe.fp, "profile_role", lambda *a, **k: side_role)
    monkeypatch.setattr(pe.fp, "curve_delta",
                        lambda curves, side, role, comp, age:
                        _STUB_D_RATE if comp == "war_rate" else _STUB_D_PT)


def _hist(pa=600, ip=0, age=33, season=2026):
    """One history row. age 33 in the 2026 season is age 34 in the FIRST_SEASON
    (2027) projection, which is the age the operator inverts at - the same
    +1-per-season offset proj_export applies when it builds the projection."""
    return [{"season": season, "age": age, "pa": pa, "ip": ip}]


def test_de_aging_is_the_forward_step_subtracted_with_hand_arithmetic(monkeypatch):
    """3.00 WAR in 600 PA at age 34, de-aged one year, all by hand.

    rate = 3.00 / 600 x 600 = 3.00 WAR per 600 PA
    de-aged rate = 3.00 - (-0.40) = 3.40
    de-aged PA   = 600 - (-60)   = 660
    de-aged WAR  = 3.40 x 660 / 600 = 3.74
    ratio        = 3.74 / 3.00 = 1.2466666...
    """
    _stub_engine(monkeypatch)
    got = pe.deaged_year1({"hit": _hist()}, 2027, {}, {}, {}, None)
    assert got is not None
    assert got["war1_champ"] == pytest.approx(3.0)
    assert got["war1_deaged"] == pytest.approx(3.74)
    assert got["ratio"] == pytest.approx(3.74 / 3.0)
    assert got["sides"][0]["side"] == "hit"


def test_rate_only_de_aging_holds_the_playing_time_projection(monkeypatch):
    """The less aggressive half: 3.40 x 600 / 600 = 3.40, ratio 3.40/3.00."""
    _stub_engine(monkeypatch)
    got = pe.deaged_year1({"hit": _hist()}, 2027, {}, {}, {}, None, rate_only=True)
    assert got["war1_deaged"] == pytest.approx(3.40)
    assert got["ratio"] == pytest.approx(3.40 / 3.0)


def test_de_aging_is_the_exact_inverse_of_the_shipped_decay_operator(monkeypatch):
    """The claim the whole basis rests on, asserted against the FORWARD operator
    itself rather than a restatement of it.

    fa_market._decay_path is the only WAR aging operator in the tree. Walk the
    de-aged (rate, exposure) FORWARD one year through it and the original
    projection must come back exactly: de-age then decay is the identity.
    """
    import fa_market as fm
    _stub_engine(monkeypatch)
    back = pe.deaged_year1({"hit": _hist()}, 2027, {}, {}, {}, None)
    expo_back = 600.0 - _STUB_D_PT                       # 660 PA, by hand
    fwd = fm._decay_path(back["war1_deaged"], expo_back, "hit", "OF", 33, {})
    assert fwd[0] == pytest.approx(3.74)                 # the de-aged year
    assert fwd[1] == pytest.approx(3.0)                  # ... decays back to war1


def test_de_aging_respects_the_per_side_universe_gate(monkeypatch):
    """The Miguel Rojas trap, pinned. A position player with a handful of mop-up
    innings has a 'pit' history row, but the SERVED row is hit-only - the pitcher
    pt delta added back to a ~4 BF projection produced a 5.2x de-aging in an
    early draft of the probe. Only sides that cleared the row's own exposure
    floor may be de-aged.
    """
    _stub_engine(monkeypatch)
    got = pe.deaged_year1({"hit": _hist(pa=600), "pit": _hist(pa=0, ip=10)},
                          2027, {}, {}, {}, None)
    assert [s["side"] for s in got["sides"]] == ["hit"], (
        "a side below the universe floor was de-aged; the served row does not "
        "contain it")
    # ... and a player who clears NO floor is unresolved, not de-aged at 1.0.
    assert pe.deaged_year1({"hit": _hist(pa=pe.MIN_PA - 1),
                            "pit": _hist(pa=0, ip=pe.MIN_IP - 1)},
                           2027, {}, {}, {}, None) is None


@pytest.mark.parametrize("war1", [0.05, 0.0, -0.17])
def test_a_near_zero_champion_year_one_is_unresolved_not_a_ratio(monkeypatch, war1):
    """0/0 has no answer, and a NEGATIVE denominator would flip the sign of the
    priced talent. 134 of the 954 rest-of-season rows on the 2026-08-05 artifact
    land here - all of them for this reason, none for a missing side."""
    _stub_engine(monkeypatch, war1=war1)
    assert pe.deaged_year1({"hit": _hist()}, 2027, {}, {}, {}, None) is None


def test_unresolved_rows_fall_back_to_the_first_season_basis_and_say_so():
    """The policy, at the switch. An unresolved row must be PRICED (it still has
    months of control to sell) on the undecayed projection, and must publish a
    basis tag that says the de-aging did not happen. A silent 1.0 multiplier
    would be numerically identical and epistemically a lie."""
    war, tag = pe.ros_talent_basis(2.0, lambda: None)
    assert war == 2.0
    assert tag == "first_season_unresolved"
    assert tag != pe.ROS_TALENT_BASIS, (
        "the fallback must be distinguishable from a row that really was de-aged")


def test_the_switch_actually_switches(monkeypatch):
    """ROS_TALENT_BASIS is the revert, so the revert is what is pinned."""
    deage = lambda: {"ratio": 1.25}                       # noqa: E731
    monkeypatch.setattr(pe, "ROS_TALENT_BASIS", "de_aged")
    assert pe.ros_talent_basis(2.0, deage) == (2.5, "de_aged")
    monkeypatch.setattr(pe, "ROS_TALENT_BASIS", "first_season")
    assert pe.ros_talent_basis(2.0, deage) == (2.0, "first_season")


def test_the_first_season_basis_does_not_even_compute_the_de_aging(monkeypatch):
    """The revert must be one line and must cost nothing: under "first_season"
    the operator is never called, so a broken corpus cannot break a reverted
    export."""
    monkeypatch.setattr(pe, "ROS_TALENT_BASIS", "first_season")

    def _boom():
        raise AssertionError("de-aging ran under the first_season basis")

    assert pe.ros_talent_basis(2.0, _boom) == (2.0, "first_season")


def test_a_typo_in_the_basis_constant_is_loud(monkeypatch):
    """A misspelled basis must not silently degrade to the old pricing - that is
    a re-price of every rental on the board with nothing in the payload saying
    so."""
    monkeypatch.setattr(pe, "ROS_TALENT_BASIS", "de-aged")
    with pytest.raises(ValueError):
        pe.ros_talent_basis(2.0, lambda: {"ratio": 1.25})


def test_the_shipped_basis_is_the_owner_decision():
    """Reverting is legitimate and is one line; doing it by accident is not.
    This fails on an unintended flip and points at the record."""
    assert pe.ROS_TALENT_BASIS == "de_aged", (
        "the rest-of-season talent basis was reverted to the FIRST_SEASON "
        "projection. That is a one-line revert by design - if it was "
        "deliberate, update this test and "
        "docs/ros-talent-basis-2026-08-05/DECISION.md together")
    assert set(pe.ROS_TALENT_BASES) == {"de_aged", "first_season"}


def test_published_ros_war_describes_the_priced_talent():
    """rosWar and surRos must describe the SAME talent, or the board shows a WAR
    that did not produce the dollars beside it.

    Checked on the served artifact: recover the basis talent from rosWar/rosFrac
    and re-price the leg. Rows whose rosBasis says the de-aging was not applied
    must additionally sit on war[0] itself.
    """
    d = _vets()
    dpw = float(d.get("dpw_usd") or 0.0)
    if not dpw:
        pytest.skip("artifact carries no dpw_usd")
    rows = [v for v in (d.get("vets") or [])
            if v.get("rosBasis") and v.get("rosWar") is not None]
    if not rows:
        pytest.skip("served artifact predates the rest-of-season talent basis "
                    "(2026-08-05); regenerate mlb_projections.json")
    bad_tag, bad_fallback = [], []
    for v in rows:
        if v["rosBasis"] not in ("de_aged", "first_season",
                                 "first_season_unresolved"):
            bad_tag.append((v.get("key"), v["rosBasis"]))
        if v["rosBasis"].startswith("first_season"):
            w0 = (v.get("war") or [None])[0]
            if w0 is None:
                continue
            # rosWar publishes to 0.01 and rosFrac to 0.001, so the recomputed
            # product carries both roundings and nothing else.
            tol_war = 0.006 + abs(float(w0)) * 0.0006
            if abs(float(v["rosWar"]) - float(w0) * float(v["rosFrac"])) > tol_war:
                bad_fallback.append((v.get("key"), v["rosWar"], w0))
    assert not bad_tag[:10], f"unknown rosBasis values: {bad_tag[:10]}"
    assert not bad_fallback[:10], (
        "rows tagged as NOT de-aged do not sit on war[0] * rosFrac: "
        f"{bad_fallback[:10]}")


def test_a_negative_talent_row_cannot_pay_the_club_for_production():
    """WAR <= 0 prices at $0 production (the kernel's floor), so the remainder is
    exactly the prorated salary owed - not a bonus for being bad."""
    assert pe._ros_surplus_usd(-0.5, 10_000_000.0, 0.4, FLAT) == pytest.approx(
        -4_000_000.0)


def test_a_finished_season_adds_nothing():
    """season_fraction() returns 1.0 both when the season is over and when the
    league PA substrate is missing. Either way the remaining share is 0.0 and
    the leg must contribute exactly nothing rather than a full extra season."""
    ros_frac = max(0.0, min(1.0, 1.0 - 1.0))
    assert ros_frac == 0.0
    assert pe._ros_surplus_usd(4.0, 40_000_000.0, ros_frac, FLAT) == 0.0


@pytest.mark.parametrize("elapsed,expected", [(0.0, 1.0), (0.682, 0.318), (1.0, 0.0), (1.4, 0.0)])
def test_remaining_share_is_clamped(elapsed, expected):
    assert max(0.0, min(1.0, 1.0 - elapsed)) == pytest.approx(expected)


def test_the_trade_board_band_prorates_the_rest_of_season_fan_the_same_way():
    """bayes_trade_value's band is the second copy of this convention and it has
    to bracket the number it is drawn around. If the priced leg prorates a FULL
    season and the band prices V(quantile * f), the two edges are billed at a
    different per-win rate than the midpoint and the band stops being the
    projection's own fan.

    Hand arithmetic at dpw == FLAT, all three points in the linear regime:
      V(3.00) = $40,890,000 ... V(4.00) = $54,520,000 ... V(5.00) = $68,150,000
    a quarter-season left -> each half-width is 0.25 x $13,630,000 = $3,407,500,
    so a $3.63M row bands to 3.63 - 3.4075 = $0.2M and 3.63 + 3.4075 = $7.0M.
    """
    v = {"surTotal": 3_630_000, "war": [4.0], "warP10": [3.0], "warP90": [5.0],
         "sur": [], "rosFrac": 0.25, "rosWar": 1.0}
    assert btv._projection_band_mm(v, FLAT, 0.07) == (0.2, 7.0)
    # The old form priced the SHRUNKEN quantiles, whose half-widths are
    # V(1.00) - V(0.75) = $2,427,734 low and V(1.25) - V(1.00) = $2,735,391 high
    # (both below $3M, and ASYMMETRIC purely from where the convex ramp lands).
    # Either of those is the mirror having drifted back.
    lo, hi = btv._projection_band_mm(v, FLAT, 0.07)
    assert (3.63 - lo) > 3.0 and (hi - 3.63) > 3.0


# --------------------------------------------------------------------------
# Served-artifact invariants (skip when the artifacts are not built here)
# --------------------------------------------------------------------------

def _vets():
    p = DATA / "mlb_projections.json"
    if not p.exists():
        pytest.skip("mlb_projections.json not built on this machine")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        pytest.skip(f"unreadable artifact: {exc}")


def test_sur_total_is_the_sum_of_its_two_legs():
    d = _vets()
    bad = []
    for v in (d.get("vets") or []):
        if v.get("surTotal") is None:
            continue
        legs = (v.get("surRos") or 0.0) * 1e6 + (v.get("surNpv") or 0)
        # surRos ships rounded to 0.1M, so allow that plus integer truncation.
        if abs(float(v["surTotal"]) - legs) > 60_000:
            bad.append((v.get("key"), v.get("surTotal"), v.get("surRos"), v.get("surNpv")))
    assert not bad[:10], f"surTotal is not surRos + surNpv: {bad[:10]}"


def test_served_ros_leg_prorates_the_full_season_surplus():
    """The A2a convention, checked on the artifact actually being served.

    A single-season (expiring) contract's `aav` IS its current-season salary, so
    for those rows the leg can be recomputed from published fields alone. Only
    rows where the two conventions differ by more than the publication rounding
    are decisive, which is why the discriminating subset is selected on the gap
    itself: measured 2026-08-05, 28 of the expiring rows clear a $500K gap, and
    all 28 answer the question unambiguously.

    BASIS-AGNOSTIC (2026-08-05). The talent `w` is recovered from the row's own
    `rosWar / rosFrac`, not from `war[0]`, so this test asks ONLY the proration
    question and keeps asking it under any talent basis. Pinning `war[0]` here
    would have turned a basis change into a false proration failure - and,
    worse, a later revert to the first_season basis would have made it pass for
    the wrong reason. `test_published_ros_war_describes_the_priced_talent` is
    what pins rosWar to the basis; the two together are strictly stronger than
    the single war[0] form they replace.

    THE TOLERANCE IS DERIVED, NOT LOOSENED BY TASTE. Recovering `w` from a field
    published to 0.01 WAR costs at most 0.005/f of talent, which at the top-tier
    rate is 0.005 x RATE_2PLUS x (dpw/FLAT) of leg dollars once the f cancels -
    about $104K at the 2026-08-05 $/WAR level - on top of the $60K already
    allowed for surRos's own 0.1M publication rounding. The decisive gap is set
    to 500K, comfortably more than twice that, so no row can satisfy both
    conventions at once and the discrimination the test was written for is
    intact (observed worst residual: $123,852, well inside).
    """
    d = _vets()
    dpw = float(d.get("dpw_usd") or 0.0)
    if not dpw:
        pytest.skip("artifact carries no dpw_usd")
    first = int(d.get("first_season") or pe.FIRST_SEASON)
    # Slack on top of the rosWar rounding band: surRos itself publishes in
    # millions to 1dp, so the served figure carries up to $50K of its own
    # rounding. Kept small and separate from the band so the two sources of
    # imprecision stay legible.
    PUBLISH_EPS = 60_000.0
    decisive = 500_000.0
    assert decisive > 4 * PUBLISH_EPS, "the two conventions must not both be matchable"
    new_form, old_form, checked = [], [], 0
    for v in (d.get("vets") or []):
        f, aav = v.get("rosFrac"), v.get("aav")
        war = v.get("war") or []
        if (not f or aav is None or not war or war[0] is None
                or v.get("thru") != first - 1 or v.get("surRos") is None):
            continue
        f, sal = float(f), float(aav)
        got = float(v["surRos"]) * 1e6
        # rosWar is published rounded to 2dp, so the talent it describes is only
        # known to +/- 0.005. BRACKET rather than estimate: price both ends of
        # that interval and accept anything inside. A flat-rate tolerance is
        # wrong here because the tier kernel is CONVEX, so its local slope in a
        # transition zone can run well above the headline 2plus rate (measured:
        # about $34M per WAR near w = 2.23, against a $20.9M headline), which
        # made an honest row look like it matched neither convention.
        if v.get("rosWar") is not None:
            lo_w = (float(v["rosWar"]) - 0.005) / f
            hi_w = (float(v["rosWar"]) + 0.005) / f
        else:
            lo_w = hi_w = float(war[0])
        w = (lo_w + hi_w) / 2.0

        def _band(fn):
            a, b = fn(lo_w), fn(hi_w)
            return (min(a, b) - PUBLISH_EPS, max(a, b) + PUBLISH_EPS)

        new_lo, new_hi = _band(lambda x: f * (pe._season_value_usd(x, 0, dpw) - sal))
        old_lo, old_hi = _band(lambda x: pe._season_value_usd(x * f, 0, dpw) - sal * f)
        new = f * (pe._season_value_usd(w, 0, dpw) - sal)
        old = pe._season_value_usd(w * f, 0, dpw) - sal * f
        if abs(new - old) <= decisive:
            continue                       # not decisive at the published precision
        checked += 1
        if new_lo <= got <= new_hi:
            new_form.append(v.get("key"))
        elif old_lo <= got <= old_hi:
            old_form.append(v.get("key"))
    if checked < 5:
        pytest.skip("too few decisive expiring rows in this artifact")
    if len(old_form) > len(new_form):
        pytest.skip("served artifact predates the f*(V(w)-salary) rest-of-season "
                    "convention (2026-08-04d); regenerate mlb_projections.json")
    assert not old_form[:10], (
        "rest-of-season rows are still priced V(f*w) - f*salary, which runs the "
        "PRORATED war back through the convex tier kernel and bills a smaller "
        f"player's per-win rate: {old_form[:10]}")
    assert len(new_form) == checked, (
        f"{checked - len(new_form)} of {checked} decisive rows match NEITHER "
        "rest-of-season convention")


def test_ros_leg_requires_a_current_season_salary():
    """No 2026 salary on file means no rest-of-season price. The alternative -
    assuming one - is the pre-arb modelling decision that stays registered and
    unbuilt, not something to smuggle in beside a rental."""
    d = _vets()
    for v in (d.get("vets") or []):
        if v.get("surRos") is not None:
            assert v.get("rosFrac") is not None, v.get("key")
            assert 0.0 < float(v["rosFrac"]) <= 1.0, v.get("key")


def test_expiring_contracts_are_no_longer_unpriced_when_a_salary_exists():
    """The owner ask, as an invariant on the served board.

    A vet whose deal ends this season but who carries a current-season salary
    must be PRICED (he has months of control left to trade), not published as
    "not tradeable".
    """
    tv = DATA / "trade_values.json"
    d = _vets()
    if not tv.exists():
        pytest.skip("trade_values.json not built on this machine")
    try:
        board = json.loads(tv.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        pytest.skip(f"unreadable artifact: {exc}")
    priced_keys = {v["key"] for v in (d.get("vets") or [])
                   if v.get("key") and v.get("surTotal") is not None}
    leaked = [r["key"] for r in (board.get("unpriced") or [])
              if r.get("key") in priced_keys]
    assert not leaked[:10], (
        "vets carrying a priced rest-of-season surplus are still published as "
        f"unpriceable: {leaked[:10]}")


def _synthetic_proj(tmp_path, vets):
    (tmp_path / "mlb_projections.json").write_text(
        json.dumps({"first_season": pe.FIRST_SEASON, "vets": vets}), encoding="utf-8")
    return tmp_path


def test_expiring_vet_with_a_priced_remainder_is_not_called_unpriceable(tmp_path):
    """The owner ask at the classifier, independent of any built artifact.

    Two vets whose deals end before the horizon opens. One carries a
    rest-of-season price, one does not. Only the second is unpriceable, and its
    reason is still one of the two documented ones.
    """
    d = _synthetic_proj(tmp_path, [
        {"key": "rental_priced", "name": "Rental Priced", "thru": pe.FIRST_SEASON - 1,
         "surTotal": -1_700_000, "surRos": -1.7, "warTotal": 0.6},
        {"key": "rental_nosalary", "name": "Rental NoSalary", "thru": pe.FIRST_SEASON - 1,
         "warTotal": 0.4},
    ])
    rows = btv._unpriced_vets(d)
    keys = {r["key"] for r in rows}
    assert "rental_priced" not in keys, (
        "a rental carrying a priced remainder is still published as not tradeable")
    assert "rental_nosalary" in keys
    assert {r["reason"] for r in rows} <= {"expiring", "no_contract"}


def test_coverage_reconciles_its_two_denominators(tmp_path):
    """D4: the census counted every unpriceable vet while the published ledger
    excluded those already priced by another basis, so one artifact shipped 581
    and 240 for the same idea with nothing saying why. They must now add up."""
    d = _synthetic_proj(tmp_path, [
        {"key": "priced", "surTotal": 5_000_000, "warTotal": 3.0},
        {"key": "on_board_elsewhere", "warTotal": 2.0},          # eFV-priced
        {"key": "truly_unpriced", "thru": pe.FIRST_SEASON - 1, "warTotal": 1.0},
    ])
    records = [
        {"player_key": "priced", "trade_value_mm": 5.0},
        {"player_key": "on_board_elsewhere", "trade_value_mm": 12.0},
    ]
    cov = btv._projection_coverage(records, d)
    assert cov["available"] is True
    for k in ("unpriceable", "unpriceable_priced_elsewhere", "unpriceable_published"):
        assert k in cov, f"coverage block missing {k}"
    assert cov["unpriceable"] == 2                      # both non-surTotal rows
    assert cov["unpriceable_priced_elsewhere"] == 1     # valued by the eFV path
    assert cov["unpriceable_published"] == 1            # what the ledger ships
    assert cov["unpriceable"] == (cov["unpriceable_priced_elsewhere"]
                                  + cov["unpriceable_published"])
    assert cov["unpriceable_published"] == (cov["unpriceable_expiring"]
                                            + cov["unpriceable_no_contract"])


def test_served_coverage_block_reconciles_after_a_regen():
    """The same invariant on the artifact actually being served. Skips until the
    board is regenerated on this machine, because the shipped file predates the
    rest-of-season leg and cannot carry its keys."""
    tv = DATA / "trade_values.json"
    if not tv.exists():
        pytest.skip("trade_values.json not built on this machine")
    try:
        cov = (json.loads(tv.read_text(encoding="utf-8")) or {}).get("coverage") or {}
    except (OSError, ValueError) as exc:
        pytest.skip(f"unreadable artifact: {exc}")
    if "unpriceable_published" not in cov:
        pytest.skip("served artifact predates rest-of-season pricing; regenerate")
    assert cov["unpriceable"] == (cov["unpriceable_priced_elsewhere"]
                                  + cov["unpriceable_published"])
    assert cov["unpriceable_published"] == (cov["unpriceable_expiring"]
                                            + cov["unpriceable_no_contract"])
