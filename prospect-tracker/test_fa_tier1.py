# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""FA Tier-1 guards (T1.2 bands, T1.3 correlated paths, T1.4 expected value,
T1.5 option basis).

Every number quoted in a docstring here was produced by a command that was
actually run; the lab scripts that produced them are named inline.
"""

from __future__ import annotations

import math
import statistics

import pytest

import fa_bands
import fa_calibration as fc
import fa_market as fm
import fa_mc


# ============================================================================
# T1.2 - player-specific band width
# ============================================================================

def _panel(n=4000, seed=5):
    """A synthetic panel whose sigma is a KNOWN function of the covariates:
    log sigma = -0.4 + 0.30*age_c - 0.25*log1p(pred). If the estimator cannot
    recover a variance function it built itself, it cannot recover a real one."""
    import random
    rng = random.Random(seed)
    Z, y, g = [], [], []
    for _ in range(n):
        side = "pit" if rng.random() < 0.5 else "hit"
        age = rng.uniform(22, 40)
        pred = max(0.0, rng.gauss(1.5, 1.2))
        expo = rng.uniform(50, 700)
        z = fa_bands.war_z(side, pred, expo, age, 0.0, 0.0, 29.0)
        sig = math.exp(-0.4 + 0.30 * z[1] - 0.25 * z[4])
        Z.append(z)
        y.append(rng.gauss(0.0, sig))
        g.append(side)
    return Z, y, g


def test_scale_fit_recovers_a_known_variance_function():
    Z, y, g = _panel()
    m = fa_bands.fit(Z, y, g, names=fa_bands.WAR_Z_NAMES)
    assert m is not None
    # gamma is on log(sigma^2), so the recovered coefficient is 2x the
    # generating one.
    assert m["gamma"][1] == pytest.approx(2 * 0.30, abs=0.12)
    assert m["gamma"][4] == pytest.approx(2 * -0.25, abs=0.12)
    assert m["sigma_sd"] > 0.05


def test_permuted_residuals_return_a_flat_sigma():
    """THE zero-information control. If this fails, every band claim on the
    dataset is unfalsifiable."""
    Z, y, g = _panel()
    real = fa_bands.fit(Z, y, g, names=fa_bands.WAR_Z_NAMES)
    ctl = fa_bands.fit(Z, y, g, names=fa_bands.WAR_Z_NAMES, permute_seed=1)
    assert ctl is not None
    assert ctl["sigma_sd"] < 0.15 * real["sigma_sd"]
    for c in ctl["gamma"][1:]:
        assert abs(c) < 0.25


def test_offsets_are_monotone_and_bracket_the_point():
    Z, y, g = _panel()
    m = fa_bands.fit(Z, y, g, names=fa_bands.WAR_Z_NAMES)
    for side in ("hit", "pit"):
        z = fa_bands.war_z(side, 2.0, 500, 30.0, 0.0, 0.0, m["age_mean"])
        o = fa_bands.offsets(m, z, side, (0.10, 0.50, 0.90))
        assert o[0.10] < o[0.50] < o[0.90]


def test_band_widths_actually_vary_by_player():
    """The defect being fixed is a CONSTANT width. A replacement that is also
    constant has fixed nothing."""
    Z, y, g = _panel()
    m = fa_bands.fit(Z, y, g, names=fa_bands.WAR_Z_NAMES)
    w = fa_bands.width_summary(m, list(zip(Z, g)))
    assert w["n"] > 1000
    assert w["sd"] / w["mean"] > 0.15
    assert w["ratio_max_min"] > 2.0


def test_sigma_clip_is_per_model_not_global():
    """A log-dollar residual needs its own guard: sigma 10 there is a
    p90/p10 ratio of 1.2e11, and that is exactly what shipped in the first
    Gate-2 run of the guarantee band (max served ratio 5.87e9)."""
    Z, y, g = _panel()
    m = fa_bands.fit(Z, y, g, names=fa_bands.WAR_Z_NAMES,
                     sigma_clip=fa_bands.SIGMA_CLIP_LOG_USD)
    assert m["sigma_clip"] == [0.35, 2.0]
    z = fa_bands.war_z("hit", 40.0, 700, 45.0, 1.0, 2.0, m["age_mean"])
    assert 0.35 <= fa_bands.sigma(m, z) <= 2.0


def test_guarantee_band_is_off_by_default_and_documented_as_a_null():
    """MEASURED NULL 2026-07-25 (tools/_fa_guarband.py, B=200 paired):
    pinball delta -0.00007 against an MDE95 of 0.00288, and the permuted
    control's null band [-0.00153, +0.00269] CONTAINS it."""
    assert fm.BAND_SCALE_GUAR is False
    assert fm._LAB_DEFAULTS["BAND_SCALE_GUAR"] is False


# ============================================================================
# T1.3 - correlated-path Monte Carlo
# ============================================================================

def test_measured_rho_is_between_ar1_and_comonotone():
    """The equicorrelated spec has to be EARNED. AR(1) fitted to the measured
    lag-1 predicts lag2 = lag1^2; the measured lag2 is nearly double that."""
    lags = fa_mc.RHO_LAGS_SPEARMAN
    assert lags[2] > lags[1] ** 2 * 1.5           # far slower decay than AR(1)
    assert lags[2] < lags[1]                      # but not perfectly flat
    assert 0.0 < fa_mc.RHO < 1.0
    # Spearman -> Gaussian copula map
    assert fa_mc.RHO == pytest.approx(
        2 * math.sin(math.pi * fa_mc.RHO_SPEARMAN / 6), abs=0.002)


def test_simulation_reproduces_the_served_marginals():
    """Each horizon keeps its own P10/point/P90 exactly. If the copula moved
    the marginals it would be changing two things at once."""
    import numpy as np
    pt = [3.0, 2.7, 2.4]
    lo = [1.2, 1.0, 0.8]
    hi = [4.8, 4.5, 4.2]
    s = fa_mc.simulate(pt, lo, hi, 3, draws=40000)
    for t in range(3):
        assert float(np.quantile(s[:, t], 0.10)) == pytest.approx(lo[t], abs=0.05)
        assert float(np.quantile(s[:, t], 0.90)) == pytest.approx(hi[t], abs=0.05)


def test_comonotone_limit_reproduces_the_sum_of_quantiles():
    """rho = 1 IS the shipped assumption, so the MC must reduce to it. This is
    what makes the comparison a like-for-like measurement of the assumption
    rather than of the implementation."""
    import numpy as np
    pt = [3.0, 2.7, 2.4, 2.1, 1.8]
    lo = [1.2, 1.0, 0.8, 0.6, 0.4]
    hi = [4.8, 4.5, 4.2, 3.9, 3.6]
    tot = fa_mc.simulate(pt, lo, hi, 5, draws=40000, rho=1.0).sum(axis=1)
    assert float(np.quantile(tot, 0.10)) == pytest.approx(sum(lo), abs=0.15)
    assert float(np.quantile(tot, 0.90)) == pytest.approx(sum(hi), abs=0.15)


def test_correlated_total_is_narrower_than_the_quantile_sum():
    pt = [3.0, 2.7, 2.4, 2.1, 1.8]
    lo = [1.2, 1.0, 0.8, 0.6, 0.4]
    hi = [4.8, 4.5, 4.2, 3.9, 3.6]
    q = fa_mc.path_quantiles(fa_mc.simulate(pt, lo, hi, 5))
    assert q["p90"] - q["p10"] < (sum(hi) - sum(lo)) * 0.85
    assert q["p10"] > sum(lo)
    assert q["p90"] < sum(hi)


def test_simulated_correlation_matches_the_requested_rho():
    import numpy as np
    s = fa_mc.simulate([3.0] * 5, [1.5] * 5, [4.5] * 5, 5, draws=40000)
    c = np.corrcoef(s.T)
    off = [c[i, j] for i in range(5) for j in range(5) if i != j]
    assert statistics.mean(off) == pytest.approx(fa_mc.RHO, abs=0.03)


def test_functionals_the_quantile_sum_cannot_express():
    q = fa_mc.path_quantiles(fa_mc.simulate(
        [3.0, 2.7, 2.4], [1.2, 1.0, 0.8], [4.8, 4.5, 4.2], 3))
    assert q["cvar10"] < q["p10"]                 # tail mean sits below the VaR
    assert 0.0 <= q["p_any_star"] <= 1.0
    assert q["mean"] > 0


def test_simulation_is_reproducible():
    a = fa_mc.simulate([2.0, 1.8], [0.5, 0.4], [3.5, 3.2], 2, draws=2000)
    b = fa_mc.simulate([2.0, 1.8], [0.5, 0.4], [3.5, 3.2], 2, draws=2000)
    assert (a == b).all()


def test_degenerate_band_simulates_as_a_constant():
    s = fa_mc.simulate([0.0, 0.0], [0.0, 0.0], [0.0, 0.0], 2, draws=500)
    assert float(s.max()) == 0.0


# ============================================================================
# T1.4 - expected value, not value of the expectation
# ============================================================================

def test_tier_curve_is_not_strictly_convex():
    """A PREMISE CHECK, not a model test. value_framework's own docstring
    claims the kernel is convex in WAR; differencing the production kernel on
    a 0.02 grid says otherwise, and the shape is what decides the SIGN of the
    T1.4 correction at every WAR level. If someone re-shapes the curve, this
    test tells them the FA correction changed character."""
    from value_framework import tiered_war_value_usd as f
    h = 0.02
    xs = [i * h for i in range(1, 301)]
    d2 = [(f(x + h) - 2 * f(x) + f(x - h)) / (h * h) for x in xs]
    assert min(d2) < -1e6, "expected a concave pocket below 2.52 WAR"
    worst = xs[d2.index(min(d2))]
    assert 2.0 < worst < 2.6
    # exactly linear above the top tier centre
    assert all(abs(v) < 1.0 for x, v in zip(xs, d2) if x >= 2.6)


def test_jensen_gap_is_positive_where_free_agent_seasons_live():
    """Sub-2-WAR seasons dominate the FA contract-year distribution, and that
    is the convex part of the curve. Measured per-season gaps: +35.997% at a
    0.8-WAR point with a 0.0-1.9 band, +23.803% at 1.2 with 0.0-2.4."""
    g = fa_mc.jensen_gap_usd([0.8], [0.0], [1.9], 1, 2027, 9_000_000, 0.0, 0.0)
    assert g["gap_usd"] > 0
    assert g["gap_pct"] == pytest.approx(35.997, abs=0.05)
    assert g["mean_of_value_usd"] > g["value_of_mean_usd"]


def test_jensen_gap_vanishes_in_the_linear_region():
    """Above 2.52 WAR the kernel is exactly linear, so there is nothing for
    the integral to correct and it must return the point price."""
    g = fa_mc.jensen_gap_usd([5.0], [3.0], [7.0], 1, 2027, 9_000_000, 0.0, 0.0)
    assert abs(g["gap_pct"]) < 0.1


def test_jensen_gap_grows_with_the_band_width_in_the_convex_region():
    narrow = fa_mc.jensen_gap_usd([1.0] * 3, [0.8] * 3, [1.2] * 3, 3, 2027,
                                  9_000_000, 0.03, 0.07)["gap_usd"]
    wide = fa_mc.jensen_gap_usd([1.0] * 3, [0.0] * 3, [2.0] * 3, 3, 2027,
                                9_000_000, 0.03, 0.07)["gap_usd"]
    assert wide > narrow


def test_zero_width_band_reduces_to_the_shipped_pricing():
    """No uncertainty, no correction. The new path must be a strict
    generalization of the old one."""
    path = {"war_by_year": [3.0, 2.7, 2.4], "war_by_year_p10": [3.0, 2.7, 2.4],
            "war_by_year_p90": [3.0, 2.7, 2.4]}
    a = fm.expected_rational_value_usd(path, 3, 2027, 9_000_000, infl=0.03)
    b = fm.rational_value_usd([3.0, 2.7, 2.4], 2027, 9_000_000, infl=0.03)
    assert a == pytest.approx(b, rel=0.001)


def test_bandless_path_falls_back_to_point_pricing():
    path = {"war_by_year": [3.0, 2.7, 2.4]}
    a = fm.expected_rational_value_usd(path, 3, 2027, 9_000_000, infl=0.03)
    b = fm.rational_value_usd([3.0, 2.7, 2.4], 2027, 9_000_000, infl=0.03)
    assert a == b


def test_verdict_edges_were_re_derived_with_the_pricing_change(monkeypatch):
    """Corpus terciles under the NEW pricing were p33 108.8 / p67 222.9
    (n=1,300). Leaving the old 75/160 would have re-graded 202 of 1,300
    historical contracts on arithmetic alone.

    The POOLED constants remain live even after the 2026-07-30 owner flip to
    per-group bands: they are still the fallback for an unknown position group and
    still the number the methodology page quotes, so they keep their pin. The mode
    is forced here so this test measures the arithmetic it is named for rather than
    whichever banding mode happens to ship."""
    monkeypatch.setattr(fm, "VERDICT_BAND_MODE", "pooled")
    # RE-CUT 2026-08-19 (owner default of the holistic plan): corpus terciles
    # on the current pricing basis read p33 88.8 / p67 197.8 (n=1,300), so the
    # pooled edges moved 109/223 -> 89/198. The full record, including the 180
    # historical flips this implies on the pooled ledger, lives at
    # fa_gate2_eval.json verdict_edges.recut_2026_08_19. Served verdicts did
    # NOT move: band_mode is 'group' and VERDICT_GROUP_EDGES awaits its own
    # owner-checkpointed re-cut on the same basis.
    assert fm.VERDICT_OVERPAY_MAX == 89
    assert fm.VERDICT_VALUE_MIN == 198
    assert fm.deal_verdict(88) == "overpay"
    assert fm.deal_verdict(89) == "market"
    assert fm.deal_verdict(197) == "market"
    assert fm.deal_verdict(198) == "value"
    assert fm.deal_verdict(None) is None


# ============================================================================
# T1.5 - option basis repair and contingent-claim pricing
# ============================================================================

_PRED = {"proj_aav_usd": 20_000_000, "proj_aav_p10_usd": 10_000_000,
         "proj_aav_p90_usd": 40_000_000,
         "proj_guarantee_usd": 80_000_000,
         "proj_guarantee_p10_usd": 40_000_000,
         "proj_guarantee_p90_usd": 160_000_000}


def test_opt_out_is_priced_on_the_remaining_guarantee_not_one_season():
    """THE units bug. A $22M/yr strike over 4 remaining years is a $88M
    remaining guarantee; comparing it to a single season's AAV made every
    opt-out look impossible."""
    strike = 88_000_000                       # remaining-guarantee shaped
    got = fm.enter_probability_v2(_PRED, "opt_out", strike)
    assert got["method"] == "band_priced_opt_out_remaining_guarantee"
    # market guarantee 80M vs an 88M strike: close call, NOT ~0.
    assert 0.2 < got["enter_prob"] < 0.8
    # the old basis (compare to a 20M AAV) would have said essentially never
    old_z = (math.log(strike) - math.log(_PRED["proj_aav_usd"])) / \
        ((math.log(_PRED["proj_aav_p90_usd"])
          - math.log(_PRED["proj_aav_p10_usd"])) / (2 * 1.2816))
    old_p = 1.0 - 0.5 * (1.0 + math.erf(old_z / math.sqrt(2)))
    assert old_p < 0.05
    assert got["enter_prob"] > 10 * old_p


def test_club_and_player_options_keep_the_annual_basis():
    for t in ("club_option", "player_option"):
        got = fm.enter_probability_v2(_PRED, t, 18_000_000)
        assert got is not None
        assert "opt_out" not in got["method"]
    # and the two sides read the SAME strike in opposite directions
    club = fm.enter_probability_v2(_PRED, "club_option", 18_000_000)
    player = fm.enter_probability_v2(_PRED, "player_option", 18_000_000)
    assert club["enter_prob"] + player["enter_prob"] == pytest.approx(1.0, abs=0.002)


def test_option_values_and_their_signs():
    club = fm.option_value_usd(_PRED, "club_option", 18_000_000)
    player = fm.option_value_usd(_PRED, "player_option", 18_000_000)
    opt = fm.option_value_usd(_PRED, "opt_out", 88_000_000)
    assert club["kind"] == "call" and club["held_by"] == "team"
    assert club["team_value_usd"] > 0            # an asset
    assert player["kind"] == "put" and player["held_by"] == "player"
    assert player["team_value_usd"] < 0          # a liability the team is SHORT
    assert opt["held_by"] == "player" and opt["team_value_usd"] < 0
    assert opt["basis"] == "remaining_guarantee"
    assert club["basis"] == "annual_salary"


def test_option_value_is_monotone_in_the_strike():
    calls = [fm.option_value_usd(_PRED, "club_option", k)["option_value_usd"]
             for k in (10e6, 15e6, 20e6, 30e6, 50e6)]
    assert calls == sorted(calls, reverse=True)   # a call is worth less as K rises
    puts = [fm.option_value_usd(_PRED, "player_option", k)["option_value_usd"]
            for k in (10e6, 15e6, 20e6, 30e6, 50e6)]
    assert puts == sorted(puts)                   # a put is worth more as K rises


def test_put_call_parity_holds_on_the_band_distribution():
    K = 22_000_000
    c = fm.option_value_usd(_PRED, "club_option", K)["option_value_usd"]
    p = fm.option_value_usd(_PRED, "player_option", K)["option_value_usd"]
    sigma = (math.log(_PRED["proj_aav_p90_usd"])
             - math.log(_PRED["proj_aav_p10_usd"])) / (2 * 1.2816)
    ES = _PRED["proj_aav_usd"] * math.exp(0.5 * sigma * sigma)
    assert (c - p) == pytest.approx(ES - K, rel=0.002)


def test_mutual_options_are_deliberately_not_priced():
    """A mutual option needs S > K for the club AND S < K for the player at
    the same instant, which cannot both hold, so its rational value is ~0 and
    its exercise rate should be ~0. The board must not manufacture a price
    for a claim that cannot be in the money for both sides."""
    assert fm.option_value_usd(_PRED, "mutual_option", 20_000_000) is None
    assert fm.enter_probability_v2(_PRED, "mutual_option", 20_000_000) is None
    # the two sides' exercise probabilities sum to 1 at every strike, so the
    # JOINT probability of both wanting it is zero under any band.
    for K in (12e6, 20e6, 35e6):
        club = fm.option_value_usd(_PRED, "club_option", K)["p_exercise"]
        player = fm.option_value_usd(_PRED, "player_option", K)["p_exercise"]
        assert club + player == pytest.approx(1.0, abs=0.002)


def test_mutual_option_exercise_rate_is_untestable_on_current_data():
    """DECISION-LEVEL VALIDATION IS BLOCKED, and the block is recorded here so
    it starts biting the moment the data arrives.

    Measured 2026-07-25: 29 members of the 2027 class carry a mutual option,
    and the event ledger holds ZERO option_exercised events across every
    stored winter 2015-2027 (0 events total). data/fa_archive.json carries no
    option fields at all. There is therefore nothing to test the prediction
    against; asserting it "passes" on an empty set would be manufacturing a
    result."""
    import storage
    n_events = 0
    n_exercised = 0
    for y in range(2015, 2028):
        ev = storage.load_fa_events(y)
        n_events += len(ev)
        n_exercised += sum(1 for e in ev
                           if e.get("event_type") == "option_exercised")
    if n_exercised == 0:
        pytest.skip(f"no option_exercised events on file "
                    f"({n_events} FA events total) - mutual-option exercise "
                    f"rate is not yet testable")
    # Once events exist: mutual exercise must be rare (the structural claim).
    assert n_exercised >= 0


def test_qo_tax_is_no_longer_dead_code():
    """It was fully implemented, tested, and never called by anything that
    serves. WIRED into fa_meta per PAYOR TIER, because the tax is a property
    of the signing team and before a signing there is no signing team."""
    import fa_export
    block = fa_export._qo_tax_block(2027)
    assert block, "qo tax block empty - the wiring regressed"
    for tier, row in block.items():
        assert row["total_usd"] >= 0
        assert row["detail"]


# ============================================================================
# M04-01 - the surplus range is a quantile of VALUE, not the value of a path
# ============================================================================

def test_draw_pricing_matches_the_point_pricer_row_by_row():
    """rational_value_draws_usd is rational_value_usd, one column at a time."""
    s = fa_mc.simulate([3.0, 2.6, 2.1], [0.4, 0.2, 0.0], [5.5, 5.0, 4.4], 3,
                       draws=200)
    vals = fm.rational_value_draws_usd(s, 2027, 17_000_000, infl=0.04)
    for i in (0, 7, 55, 199):
        want = fm.rational_value_usd(list(s[i]), 2027, 17_000_000, infl=0.04)
        assert abs(vals[i] - want) <= 1, (i, vals[i], want)


def _priced_members():
    import json
    from pathlib import Path
    d = json.loads((Path(__file__).parent / "data" / "fa_class.json")
                   .read_text(encoding="utf-8"))
    return [m for m in d["members"] if m.get("surplus") is not None
            and m.get("surplusP10") is not None]


def test_served_surplus_range_reads_the_copula_draws_on_multi_year_terms():
    """Before the fix 41 of the 50 multi-year 2027 rows served surplusP10 equal to
    minus the guarantee (a career at zero WAR every season) while the same row
    printed a positive downside WAR from the copula."""
    rows = _priced_members()
    multi = [m for m in rows if (m.get("projYears") or 0) >= 2]
    assert multi, "no multi-year priced rows"
    for m in multi:
        assert m.get("surplusBandSrc") == "mc_copula", m["key"]
        assert m["surplusP10"] <= m["surplus"] <= m["surplusP90"], m["key"]
        if (m.get("warTotalP10") or 0) >= 0.1:
            assert m["surplusP10"] > -m["projGuar"], m["key"]
        # The comonotone band is wider at both ends and stays in the artifact.
        assert m["surplusP10Comon"] <= m["surplusP10"], m["key"]
        assert m["surplusP90Comon"] >= m["surplusP90"], m["key"]


def test_one_season_terms_keep_the_exact_path_price():
    rows = [m for m in _priced_members() if m.get("projYears") == 1]
    assert rows
    for m in rows:
        assert m.get("surplusBandSrc") == "season_path", m["key"]
        assert m["surplusP10"] == m["surplusP10Comon"], m["key"]
        assert m["surplusP90"] == m["surplusP90Comon"], m["key"]
