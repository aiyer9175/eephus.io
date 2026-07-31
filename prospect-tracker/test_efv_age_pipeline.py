# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Phase C age pipeline (2026-07-30): decimal ages and continuous ramps.

Pins, in order:
  C1  the model reads the DECIMAL season-midpoint age, with a data-conflict guard;
  C3  the age / reliever ramps are continuous, and the ONSET DIAL defaults to the
      retired hard gate exactly (so the shipping commit is output-neutral);
  C3  the two arms whose gate came back NULL / OWED are implemented but DEFAULT OFF,
      and OFF is byte-identical to the shipped behaviour.

Gate record: docs/efv-2026-07-30/EFV_LANE_GATES.md, data/xfv_agepipe_eval.json.
Pure-data, no network, no writes.
"""
from __future__ import annotations

import pytest

import age_level
import efv_dataset as ed
import efv_score as es
import eta


# --------------------------------------------------------------------------
# C1 - decimal season-midpoint age
# --------------------------------------------------------------------------
def test_decimal_age_is_preferred_over_the_integer_feed_age():
    # A 1999-07-08 birth date is 23.98 at the 2023 season midpoint; the StatsAPI
    # baseball age floors that to 23 and the model used to read the 23.
    assert ed._resolve_season_age(23.0, "1999-07-08", 2023) == pytest.approx(24.0)
    # The floor loss depends on BIRTH MONTH, which is the bias C1 removes: two players
    # the feed calls the same age are nearly a full year apart in truth.
    july = ed._resolve_season_age(21.0, "2001-07-16", 2023)
    june = ed._resolve_season_age(21.0, "2002-06-16", 2023)
    assert july > june
    assert july - june > 0.9


def test_decimal_age_falls_back_to_the_feed_age():
    assert ed._resolve_season_age(21.0, None, 2023) == pytest.approx(21.0)
    assert ed._resolve_season_age(21.0, "not-a-date", 2023) == pytest.approx(21.0)
    assert ed._resolve_season_age(None, None, 2023) is None
    # no feed age at all -> the decimal stands on its own
    assert ed._resolve_season_age(None, "2003-03-01", 2023) == pytest.approx(20.3)


def test_age_conflict_guard_rejects_a_mis_bound_birth_date():
    """The two ages are floor-related, so they cannot differ by a year or more. A
    larger gap is a birth_date attached to the wrong player (measured: a luis_gonzalez
    carrying 2005-07-15 against a StatsAPI age of 23 in 2019, a 9.0 yr gap). eFV must
    keep the feed's own age rather than start trusting the bad birth date."""
    assert ed._resolve_season_age(23.0, "2005-07-15", 2019) == pytest.approx(23.0)
    assert ed.AGE_CONFLICT_MAX_YR == pytest.approx(1.05)
    # inside the guard the decimal still wins (the 1dp rounding can reach exactly 1.0)
    assert ed._resolve_season_age(21.0, "2000-07-16", 2022) == pytest.approx(22.0)


# --------------------------------------------------------------------------
# C3-AGE - the onset is a dial, and its default reproduces the retired hard gate
# --------------------------------------------------------------------------
def _retired_age_gate(age):
    if age is None or float(age) <= 25.0:
        return 1.0
    return round(max(0.75, 1.0 - 0.10 * (float(age) - 25.0)), 3)


def test_age_ramp_mechanism_reproduces_the_retired_hard_gate_at_onset_25():
    """The ramp MECHANISM must be a faithful generalisation of the retired hard gate:
    evaluated AT the incumbent onset it reproduces it exactly, to 1e-12, at every age.

    This is the check that matters and it outlives any particular dial setting. It was
    originally written as an output-neutrality pin on the default, which conflated two
    different claims: 'the mechanism is faithful' and 'the owner has not moved the dial
    yet'. The owner moved the dial on 2026-07-30 (see the next test), so the two claims
    are now separated."""
    assert es._AGE_PENALTY_PER_YR == pytest.approx(0.10)
    assert es._AGE_PENALTY_FLOOR == pytest.approx(0.75)
    a = 14.0
    while a <= 40.0001:
        assert es._age_ramp(a, onset=25.0) == pytest.approx(_retired_age_gate(a),
                                                            abs=1e-12), f"age {a}"
        a += 0.05
    assert es._age_factor({"age_now": None}) == 1.0
    assert es._age_factor({}) == 1.0


def test_age_onset_is_the_owner_decided_value():
    """OWNER DECISION 2026-07-30 (master plan D2): onset 23.0.

    Chosen from a measured table (22.0 / 23.0 / 24.0 / 25.0) to move a 24.7-year-old
    repeating AAA on a .664 OPS out of the top 100, which the retired hard gate at
    exactly 25.0 taxed at nothing. 22.0 was rejected because it costs two pitchers out
    of the top 100 (366 of the 489 rows pinned at the age_rel_level cap are pitchers,
    so an early onset taxes the side the rest of the program is trying not to
    under-rate). If this value changes again it is a POLICY change and wants a
    measured table and an owner decision, not a quiet edit."""
    assert es._AGE_PENALTY_ONSET == pytest.approx(23.0)
    # The decision's whole purpose: a 24.7-year-old now pays, and pays the ramp rather
    # than a cliff.
    assert es._age_factor({"age_now": 22.9}) == pytest.approx(1.0)
    assert es._age_factor({"age_now": 24.7}) == pytest.approx(0.83, abs=1e-9)
    assert es._age_factor({"age_now": 25.5}) == pytest.approx(0.75, abs=1e-9)


def test_age_ramp_is_continuous_monotone_and_floored():
    prev, a = 1.0, 14.0
    while a <= 45.0001:
        v = es._age_ramp(a)
        assert es._AGE_PENALTY_FLOOR - 1e-9 <= v <= 1.0
        assert v <= prev + 1e-9, f"ramp rose at {a}"
        prev = v
        a += 0.05
    # no step anywhere: a 0.05 yr age change can never move the factor by more than
    # slope * 0.05 (plus the 3dp rounding), which is what "continuous" has to mean here
    a = 14.0
    while a <= 45.0001:
        step = abs(es._age_ramp(a) - es._age_ramp(a + 0.05))
        assert step <= es._AGE_PENALTY_PER_YR * 0.05 + 1e-3, f"step at {a}: {step}"
        a += 0.05
    # the dial actually moves the ramp, and only the onset moves
    assert es._age_ramp(24.0, onset=23.0) == pytest.approx(0.90)
    assert es._age_ramp(24.0, onset=25.0) == pytest.approx(1.00)


# --------------------------------------------------------------------------
# C3-ROLE - the 20-point reliever staircase becomes the same ramp
# --------------------------------------------------------------------------
def _rp(age):
    return es._role_factor({"age_now": age, "position": "SIRP"}, 2.0)


def test_role_ramp_removes_the_twenty_point_step_at_age_25():
    # the retired staircase dropped 1.0 -> 0.80 across a hundredth of a year
    assert abs(_rp(24.99) - _rp(25.01)) < 0.01
    prev, a = 1.0, 20.0
    while a <= 32.0001:
        v = _rp(a)
        assert es._ROLE_PENALTY_FLOOR - 1e-9 <= v <= 1.0
        assert v <= prev + 1e-9, f"role ramp rose at {a}"
        assert abs(v - _rp(a + 0.05)) <= es._AGE_PENALTY_PER_YR * 0.05 + 1e-3
        prev = v
        a += 0.05


def test_role_ramp_passes_through_the_retired_tier_midpoints():
    """The offset is DERIVED, not tuned: it is the one that keeps each retired tier's
    central tendency where the owner directive put it."""
    assert es._ROLE_RAMP_OFFSET_YR == pytest.approx(-1.5)
    assert _rp(25.5) == pytest.approx(0.80, abs=1e-9)
    assert _rp(26.5) == pytest.approx(0.70, abs=1e-9)
    assert _rp(27.5) == pytest.approx(0.70, abs=1e-9)      # floored


def test_role_ramp_keeps_its_designation_and_enthusiasm_gates():
    assert es._role_factor({"age_now": 30.0, "position": "SS"}, 5.0) == 1.0
    assert es._role_factor({"age_now": 30.0, "position": "P"}, 5.0) == 1.0   # generic P excluded
    assert es._role_factor({"age_now": 30.0, "position": "RP"}, 1.4) == 1.0  # model not enthusiastic
    assert es._role_factor({"age_now": None, "position": "RP"}, 5.0) == 1.0


# --------------------------------------------------------------------------
# C3-CLIP - NULL gate: implemented, DEFAULT OFF, and OFF is the shipped clip
# --------------------------------------------------------------------------
def test_age_rel_soft_saturation_is_off_by_default():
    assert ed.AGE_REL_SOFT is False, "the C3 clip arm gated NULL; it must ship OFF"
    assert ed.AGE_REL_CAP == pytest.approx(3.5)
    for x in (-9.0, -3.5, -3.4999, -1.0, 0.0, 0.5, 3.4999, 3.5, 9.0):
        assert ed._age_rel_bound(x) == pytest.approx(max(-3.5, min(3.5, x)), abs=1e-12)


def test_age_rel_soft_saturation_when_enabled_keeps_the_range_and_the_order():
    ed.AGE_REL_SOFT = True
    try:
        vals = [ed._age_rel_bound(x / 10.0) for x in range(-200, 201)]
        assert all(-ed.AGE_REL_CAP < v < ed.AGE_REL_CAP for v in vals)
        assert all(b >= a - 1e-12 for a, b in zip(vals, vals[1:]))     # monotone
        assert ed._age_rel_bound(0.0) == pytest.approx(0.0)            # odd, fixed at 0
        assert ed._age_rel_bound(-1.0) == pytest.approx(-ed._age_rel_bound(1.0))
        # near zero it is the identity to first order, so small age gaps are untouched
        assert ed._age_rel_bound(0.1) == pytest.approx(0.1, abs=2e-3)
        # and it never pins: the 489 rows that shared exactly +3.5 now spread
        assert ed._age_rel_bound(4.0) < ed._age_rel_bound(6.0) < ed.AGE_REL_CAP
    finally:
        ed.AGE_REL_SOFT = False


# --------------------------------------------------------------------------
# C3-ETA - gate OWED: implemented, DEFAULT OFF, and OFF is the shipped staircase
# --------------------------------------------------------------------------
def _retired_eta_staircase(diff):
    if diff <= -4.0:
        return -1.50
    if diff <= -3.0:
        return -1.15
    if diff <= -2.0:
        return -0.80
    if diff <= -1.0:
        return -0.40
    if diff >= 4.0:
        return +1.25
    if diff >= 3.0:
        return +1.00
    if diff >= 2.0:
        return +0.70
    if diff >= 1.0:
        return +0.35
    return 0.0


def test_eta_age_adj_default_is_the_retired_staircase_exactly():
    assert eta.AGE_ADJ_CONTINUOUS is False, \
        "the ETA arm's KM/censoring gate is OWED; it must ship OFF"
    d = -6.0
    while d <= 6.0001:
        assert eta.age_adj_for_diff(d) == pytest.approx(_retired_eta_staircase(d),
                                                        abs=1e-12), f"diff {d}"
        d += 0.01


def test_eta_age_adj_continuous_preserves_every_staircase_knot():
    eta.AGE_ADJ_CONTINUOUS = True
    try:
        for k in (-4.0, -3.0, -2.0, -1.0, 1.0, 2.0, 3.0, 4.0):
            assert eta.age_adj_for_diff(k) == pytest.approx(_retired_eta_staircase(k),
                                                            abs=1e-9), f"knot {k}"
        # the defect: 0.40 yr of ETA across a hundredth of a year of age
        assert abs(_retired_eta_staircase(-0.99) - _retired_eta_staircase(-1.00)) == \
            pytest.approx(0.40, abs=1e-9)
        assert abs(eta.age_adj_for_diff(-0.99) - eta.age_adj_for_diff(-1.00)) < 0.01
        prev, d = -2.0, -6.0
        while d <= 6.0001:
            v = eta.age_adj_for_diff(d)
            assert v >= prev - 1e-9, f"eta age_adj fell at {d}"
            prev = v
            d += 0.01
        # clamped outside the knot range
        assert eta.age_adj_for_diff(-99.0) == pytest.approx(-1.50)
        assert eta.age_adj_for_diff(+99.0) == pytest.approx(+1.25)
    finally:
        eta.AGE_ADJ_CONTINUOUS = False


# --------------------------------------------------------------------------
# C3-TBS - age_level tiers deliberately UNCHANGED (premise refuted, see the gate doc)
# --------------------------------------------------------------------------
def test_age_level_tier_agrees_with_the_diff_printed_beside_it():
    """The tier is a DISPLAY LABEL and must agree with the 1dp diff shown next to it.
    Deriving it from the unrounded value would put '-2.0 / young for level' on 155 of
    4,254 live cards. The scoring consumers all read the (already continuous) diff."""
    r = age_level.score_age_vs_level(19.96, "A+", {"A+": 22.0})
    assert r.diff == pytest.approx(-2.0)
    assert r.tier == "very-young", "tier must follow the displayed diff, not the raw value"
    # the documented tier vocabulary -- storage's org rollup tests for "very-old", which
    # this module never emits (recorded in the gate doc as a storage-side bug)
    vocab = {age_level.score_age_vs_level(a, "AA", {"AA": 23.0}).tier
             for a in (20.0, 22.0, 23.0, 24.0, 26.0)}
    assert vocab == {"very-young", "young", "neutral", "old", "too-old"}
    assert "very-old" not in vocab


# --------------------------------------------------------------------------
# C2 - the norm swap gated NULL, so the static table must still be the shipped one
# --------------------------------------------------------------------------
def test_c2_norm_swap_did_not_ship():
    """C2 measured NULL and NEGATIVE on the pitcher side (rho -0.0019, block -0.0051,
    SCORED_YEARS -0.0075). The gate standard does not license shipping that, so the
    static prior stands and the measured empirical table is a DISPLAY reference only."""
    assert ed._TYPICAL_LEVEL_AGE == {"DSL": 18.0, "CPX": 19.0, "A": 20.0,
                                     "A+": 21.0, "AA": 22.5, "AAA": 24.0}
