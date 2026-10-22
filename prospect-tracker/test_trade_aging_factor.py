"""TRADE_AGING_PREPEAK_FIX (AG_3_TM_PREPEAK_FIX, plan Part 9 section 9.3).

bayes_trade_value._aging_factor's v2 tent returned min(1.10, 1.0 + 0.025 *
(peak - age_at)) before the peak, so a 23-year-old hitter (peak 27) read 1.075,
1.05, 1.025, 1.0, then 0.93. With the flag on the factor is the ratio of
value_framework._aging_multiplier at age_at to the same multiplier at age_now,
so it rises to the peak and falls after it. With the flag off the old values
are pinned by a golden over the same grid.
"""
from __future__ import annotations

import hashlib

import pytest

import bayes_trade_value as btv
import value_framework as vf

ROLES = (("hitter", False, "SS"), ("pitcher", True, "RHP"), ("catcher", False, "C"))
AGES = range(19, 43)
OFFSETS = range(1, 8)

# sha256 of the flag-off factors (repr, newline-joined) over ROLES x AGES x
# OFFSETS, recorded from the pre-change code on 2026-10-21.
GOLDEN_OFF_SHA256 = "5b394ba7bf69d6e9156b3d972a3853f1ea2a3455264fe5f10e5ad535ce4d2fa9"
GOLDEN_OFF_SPOTS = {
    "SS|23|1": 1.075,
    "SS|23|4": 1.0,
    "SS|23|5": 0.9299999999999999,
    "SS|30|3": 0.58,
    "SS|40|7": 0.25,
    "RHP|23|1": 1.025,
    "RHP|23|4": 0.86,
    "RHP|23|5": 0.79,
    "RHP|30|3": 0.43999999999999995,
    "RHP|40|7": 0.25,
    "C|23|1": 1.025,
    "C|23|4": 0.8200000000000001,
    "C|23|5": 0.73,
    "C|30|3": 0.28,
    "C|40|7": 0.2
}


def _grid(position_isp=ROLES):
    for _, isp, pos in position_isp:
        for a in AGES:
            for k in OFFSETS:
                yield isp, pos, float(a), k


def test_flag_defaults_off():
    assert btv.TRADE_AGING_PREPEAK_FIX is False


def test_flag_off_matches_the_old_values(monkeypatch):
    monkeypatch.setattr(btv, "TRADE_AGING_PREPEAK_FIX", False)
    vals = [repr(btv._aging_factor(a, k, isp, pos)) for isp, pos, a, k in _grid()]
    assert len(vals) == 3 * 24 * 7
    assert hashlib.sha256("\n".join(vals).encode()).hexdigest() == GOLDEN_OFF_SHA256
    for key, want in GOLDEN_OFF_SPOTS.items():
        pos, a, k = key.split("|")
        isp = pos == "RHP"
        assert btv._aging_factor(float(a), int(k), isp, pos) == want, key
    # the defect itself, as recorded: a 23-year-old hitter falls toward his peak
    seq = [btv._aging_factor(23.0, k, False, "SS") for k in range(1, 6)]
    assert seq == pytest.approx([1.075, 1.05, 1.025, 1.0, 0.93])


@pytest.mark.parametrize("role,isp,pos", ROLES)
def test_flag_on_rises_before_peak_and_falls_after(monkeypatch, role, isp, pos):
    monkeypatch.setattr(btv, "TRADE_AGING_PREPEAK_FIX", True)
    cfg = btv._cfg()["aging_curve"]
    peak = float(cfg["catcher_peak_age" if pos == "C" else
                     ("pitcher_peak_age" if isp else "hitter_peak_age")])
    for a in AGES:
        a = float(a)
        prev = 1.0  # offset 0 is the player's own level
        for k in OFFSETS:
            f = btv._aging_factor(a, k, isp, pos)
            assert f > 0
            if a + k <= peak:
                assert f >= prev - 1e-12, (role, a, k, f, prev)
            else:
                assert f <= prev + 1e-12, (role, a, k, f, prev)
            prev = f


@pytest.mark.parametrize("role,isp,pos", ROLES)
def test_flag_on_is_the_value_framework_ratio(monkeypatch, role, isp, pos):
    monkeypatch.setattr(btv, "TRADE_AGING_PREPEAK_FIX", True)
    cfg = btv._cfg()["aging_curve"]
    if pos == "C":
        peak, dec, flo = cfg["catcher_peak_age"], cfg["catcher_decline_per_yr"], cfg["catcher_min_multiplier"]
    elif isp:
        peak, dec, flo = cfg["pitcher_peak_age"], cfg["pitcher_decline_per_yr"], cfg["min_multiplier"]
    else:
        peak, dec, flo = cfg["hitter_peak_age"], cfg["hitter_decline_per_yr"], cfg["min_multiplier"]
    tent = {"climb_per_year_before_peak": vf._config()["aging"]["climb_per_year_before_peak"],
            "decline_per_year_after_peak": dec, "min_multiplier": flo}
    for a in AGES:
        for k in OFFSETS:
            want = (vf._aging_multiplier(a + k, float(peak), tent)
                    / vf._aging_multiplier(float(a), float(peak), tent))
            assert btv._aging_factor(float(a), k, isp, pos) == pytest.approx(want, abs=1e-12)


def test_flag_on_twenty_three_year_old_hitter_climbs(monkeypatch):
    monkeypatch.setattr(btv, "TRADE_AGING_PREPEAK_FIX", True)
    seq = [btv._aging_factor(23.0, k, False, "SS") for k in range(1, 6)]
    # climb 0.04 a year to 1.0 at 27 from 0.84 at 23, then 0.07 a year down
    assert seq == pytest.approx([0.88 / 0.84, 0.92 / 0.84, 0.96 / 0.84, 1.0 / 0.84, 0.93 / 0.84])
    assert btv._aging_factor(None, 3, False, "SS") == 1.0
