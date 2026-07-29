# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""T1.1 - the calibration instrument is validated as an INSTRUMENT.

Three synthetic generators with known answers, and the instrument must
return the right diagnosis for each. No ship decision attaches to any of
this; a broken thermometer is worse than no thermometer, so the thermometer
is checked before anything is measured with it.

Measured 2026-07-25 (n=4000, seed 11, DEFAULT_TAUS 0.05..0.95):
  calibrated  chi2   7.91  p 0.544  lean -0.0057  hump +0.0145  cov 0.79975
  inflated    chi2 824.15  p 0.000  lean -0.0047  hump +0.1988  cov 0.94675
  biased      chi2 297.96  p 0.000  lean +0.0791  hump -0.0070  cov 0.79225
"""

from __future__ import annotations

import math
import statistics

import pytest

import fa_calibration as fc


# --------------------------------------------------------------- primitives --

def test_z_matches_known_normal_quantiles():
    for p, want in ((0.5, 0.0), (0.9, 1.2815516), (0.975, 1.959964),
                    (0.1, -1.2815516), (0.01, -2.3263479)):
        assert fc._z(p) == pytest.approx(want, abs=1e-6)


def test_pinball_is_minimized_at_the_true_quantile():
    """The property that makes the CRPS built from it proper."""
    import random
    rng = random.Random(3)
    draws = [rng.gauss(0.0, 1.0) for _ in range(20000)]
    tau = 0.75
    truth = fc._z(tau)
    at = statistics.mean(fc.pinball(y, truth, tau) for y in draws)
    for off in (-0.4, -0.15, 0.15, 0.4):
        assert statistics.mean(fc.pinball(y, truth + off, tau) for y in draws) > at


def test_crps_grid_converges_to_the_closed_form():
    """2 x mean pinball on an m-point interior grid runs high by the
    m/(m+1) strip the rectangle rule drops. Rescaling recovers the
    closed-form Gaussian CRPS."""
    import random
    rng = random.Random(5)
    m = 99
    taus = [i / (m + 1) for i in range(1, m + 1)]
    errs = []
    for _ in range(400):
        mu = rng.uniform(-2, 2)
        y = rng.gauss(mu, 1.3)
        q = {t: mu + 1.3 * fc._z(t) for t in taus}
        grid = fc.crps_from_quantiles(y, q) * m / (m + 1)
        errs.append(grid - fc.crps_normal(y, mu, 1.3))
    assert abs(statistics.mean(errs)) < 0.01


def test_crps_is_proper_wider_bands_do_not_win():
    """A forecast cannot buy a better CRPS by widening. This is the reason
    coverage alone is not a scoring rule."""
    rows = fc.synthetic_rows("calibrated", n=3000, seed=7)
    good = statistics.mean(fc.crps_from_quantiles(r["y"], r["q"]) for r in rows)
    for infl in (1.5, 2.0, 3.0):
        wide = statistics.mean(
            fc.crps_from_quantiles(
                r["y"], {t: r["mu"] + infl * (v - r["mu"]) for t, v in r["q"].items()})
            for r in rows)
        assert wide > good
    narrow = statistics.mean(
        fc.crps_from_quantiles(
            r["y"], {t: r["mu"] + 0.5 * (v - r["mu"]) for t, v in r["q"].items()})
        for r in rows)
    assert narrow > good


def test_pit_value_interpolates_and_extrapolates_monotonically():
    q = {t: fc._z(t) for t in fc.DEFAULT_TAUS}
    assert fc.pit_value(0.0, q) == pytest.approx(0.5, abs=0.01)
    assert fc.pit_value(fc._z(0.25), q) == pytest.approx(0.25, abs=0.01)
    seq = [fc.pit_value(y, q) for y in (-6, -3, -1, 0, 1, 3, 6)]
    assert seq == sorted(seq)
    assert 0.0 < seq[0] and seq[-1] < 1.0     # the clamp keeps PIT interior


def test_sigma_from_band_round_trips():
    s = fc.sigma_from_band(-1.2815516, 1.2815516, 0.10, 0.90)
    assert s == pytest.approx(1.0, abs=1e-6)


# -------------------------------------------------- the three known answers --

@pytest.fixture(scope="module")
def reports():
    return fc.validate_instrument(n=4000, seed=11)


def test_generator_1_calibrated_gives_a_flat_pit(reports):
    r = reports["calibrated"]
    assert r["diagnosis"] == "calibrated"
    assert r["pit"]["p_uniform"] > 0.05
    assert abs(r["pit"]["lean"]) < 0.02
    assert abs(r["pit"]["hump"]) < 0.02
    # every histogram bin within 4 binomial se of flat
    for f in r["pit"]["freq"]:
        assert abs(f - 0.1) < 4 * r["pit"]["bin_se"]
    # coverage and the reliability diagram both land on the diagonal
    assert r["coverage"]["coverage"] == pytest.approx(0.80, abs=0.02)
    assert r["reliability_summary"]["mean_abs_gap"] < 0.015


def test_generator_2_inflated_intervals_give_a_humped_pit(reports):
    r = reports["inflated"]
    assert r["diagnosis"] == "over_wide"
    assert r["pit"]["p_uniform"] < 1e-6
    assert r["pit"]["hump"] > 0.10          # mass bunched in the middle
    assert abs(r["pit"]["lean"]) < 0.02     # but NOT shifted
    assert r["coverage"]["coverage"] > 0.90  # nominal 0.80
    # and the proper score punishes it even though coverage looks "safe"
    assert r["crps"] > reports["calibrated"]["crps"]


def test_generator_3_bias_gives_a_leaning_pit(reports):
    r = reports["biased"]
    assert r["diagnosis"] == "biased_low"
    assert r["pit"]["p_uniform"] < 1e-6
    assert r["pit"]["lean"] > 0.05          # realizations sit high in the band
    assert abs(r["pit"]["hump"]) < 0.02     # width is fine, location is not
    # the headline coverage is nearly UNMOVED, which is the whole point
    assert abs(r["coverage"]["coverage"] - 0.80) < 0.02
    assert r["crps"] > reports["calibrated"]["crps"]
    assert r["bias_median"] < -0.2          # median forecast below the truth


def test_the_three_diagnoses_are_distinct(reports):
    assert len({reports[k]["diagnosis"] for k in reports}) == 3


def test_over_narrow_is_also_detected():
    """The fourth corner: bands too tight give a U, not a hump."""
    rows = fc.synthetic_rows("inflated", n=4000, seed=13, inflate=0.6)
    rep = fc.calibration_report(rows)
    assert rep["diagnosis"] == "over_narrow"
    assert rep["pit"]["hump"] < -0.05
    assert rep["coverage"]["coverage"] < 0.70


# ------------------------------------------------- conditional-coverage test --

def test_conditional_coverage_finds_a_defect_the_marginal_hides():
    """The Gate-1 situation, built on purpose: half the panel is over-wide
    and half is over-narrow, so the MARGINAL coverage lands on nominal while
    both halves are wrong. The conditional table must see it."""
    lo = fc.synthetic_rows("inflated", n=3000, seed=21, inflate=1.6)
    hi = fc.synthetic_rows("inflated", n=3000, seed=22, inflate=0.715)
    for r in lo:
        r["grp"] = "wide"
    for r in hi:
        r["grp"] = "tight"
    rows = lo + hi
    marg = fc.coverage(rows)
    assert abs(marg["coverage"] - 0.80) < 0.02          # looks perfect
    cond = fc.conditional_coverage(rows, "grp")
    by = {c["bin"]: c for c in cond}
    assert by["wide"]["coverage"] > 0.90
    assert by["tight"]["coverage"] < 0.70
    assert abs(by["wide"]["z"]) > 5 and abs(by["tight"]["z"]) > 5


def test_conditional_coverage_bins_numeric_covariates_by_equal_count():
    rows = fc.synthetic_rows("calibrated", n=2000, seed=31)
    cond = fc.conditional_coverage(rows, lambda r: r["mu"], n_bins=10)
    assert len(cond) == 10
    assert {c["n"] for c in cond} == {200}
    assert all(c["lo"] <= c["hi"] for c in cond)


def test_quantile_crossing_is_isotonized_and_counted():
    q = {0.1: 2.0, 0.5: 1.0, 0.9: 3.0}
    assert fc.n_crossings(q) == 1
    assert fc._sorted_grid(q) == [(0.1, 2.0), (0.5, 2.0), (0.9, 3.0)]
    assert math.isfinite(fc.crps_from_quantiles(1.5, q))


def test_report_is_empty_safe():
    assert fc.calibration_report([]) == {"n": 0}
    assert fc.pit_histogram([]) == {"n": 0}
    assert fc.coverage([]) == {"n": 0}
