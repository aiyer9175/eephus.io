# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The six registered methods of docs/dpw-2026-09-25/DPW_PATH_GATE.md section 3,
the gap rule, the median rule, the taper, the side rule and the re-anchoring
rule, on SYNTHETIC series only. No real series is read and no error of any arm
is computed here (G-0)."""

from __future__ import annotations

import math
import statistics

import pytest

import dpw_path as dp
import fa_market as fm

SYN = {2015: 9.1e6, 2016: 9.4e6, 2017: 9.9e6, 2018: 10.2e6, 2019: 10.0e6, 2020: 10.6e6,
       2021: 13.9e6, 2022: 14.2e6, 2023: 14.9e6, 2024: 15.3e6, 2025: 15.9e6, 2026: 16.5e6}


@pytest.fixture(autouse=True)
def _series_destale(monkeypatch):
    monkeypatch.setattr(fm, "DESTALE_MODE", "series")


@pytest.mark.parametrize("origin", range(2018, 2027))
def test_carry_destale_matches_the_served_rule_to_1e12(origin):
    """Parity with fa_market._destale_rate at every development origin (I-5)."""
    sub = {w: v for w, v in SYN.items() if w <= origin}
    want = fm._destale_rate(sub, origin + 1)
    got = dp.g_destale(SYN, origin)
    assert abs(got - want) <= 1e-12 * max(1.0, abs(want))
    a = SYN[origin]
    for h in range(1, 6):
        assert dp.forecast("carry_destale", SYN, origin, h) == pytest.approx(
            a * (1 + want) ** h, rel=1e-12)


@pytest.mark.parametrize("origin", range(2018, 2027))
def test_trend_line_matches_fit_log_trend_to_1e12(origin):
    sub = {w: v for w, v in SYN.items() if w <= origin}
    pred = fm._fit_log_trend(sub, with_cbt=False)
    for h in (1, 3, 5):
        assert dp.forecast("trend_line", SYN, origin, h) == pytest.approx(pred(origin + h), rel=1e-12)


def test_robust_drift_uses_the_median_with_the_even_count_rule():
    # 2018 has 3 differences (odd), 2019 has 4 (even): the mean of the two middle values
    for origin, n_d in ((2018, 3), (2019, 4)):
        d = dp.differences(SYN, origin)
        assert len(d) == n_d
        want = min(0.12, max(0.0, math.exp(statistics.median(d)) - 1.0))
        assert dp.g_robust(SYN, origin) == pytest.approx(want, rel=1e-15)
    d4 = sorted(dp.differences(SYN, 2019))
    assert statistics.median(d4) == pytest.approx((d4[1] + d4[2]) / 2)


def test_the_clip_is_zero_to_twelve_percent():
    falling = {2015 + i: 10e6 * 0.95 ** i for i in range(6)}
    rising = {2015 + i: 10e6 * 1.30 ** i for i in range(6)}
    assert dp.g_robust(falling, 2020) == 0.0
    assert dp.g_robust(rising, 2020) == 0.12
    assert dp.g_destale(falling, 2020) == 0.0
    assert dp.g_destale(rising, 2020) == 0.12


def test_damped_steps_from_challenger_toward_incumbent():
    gi, ga = dp.g_destale(SYN, 2022), dp.g_robust(SYN, 2022)
    a = SYN[2022]
    p = a
    for h in range(1, 6):
        p *= 1 + gi + (ga - gi) * 0.8 ** (h - 1)
        assert dp.forecast("damped", SYN, 2022, h) == pytest.approx(p, rel=1e-14)


def test_the_gap_rule_annualizes_and_enters_a_gap_once():
    gapped = {w: v for w, v in SYN.items() if w != 2019}
    d = dp.differences(gapped, 2021)
    assert len(d) == len(dp.available(gapped, 2021)) - 1
    assert d[3] == pytest.approx(math.log(SYN[2020] / SYN[2018]) / 2)


def test_fewer_than_four_winters_falls_back_to_carry_zero():
    short = {2015: 9e6, 2016: 9.5e6, 2017: 10e6}
    for m in dp.METHODS:
        assert dp.forecast(m, short, 2017, 3, g_ref=0.04) == 10e6


def test_forecasts_are_ex_ante():
    """Poisoning a later winter changes no forecast made at an earlier origin."""
    poisoned = dict(SYN)
    poisoned[2024] = 99e6
    for m in dp.METHODS:
        for h in range(1, 6):
            assert dp.forecast(m, SYN, 2021, h, g_ref=0.0409) == dp.forecast(
                m, poisoned, 2021, h, g_ref=0.0409)


def test_one_planted_step_contaminates_one_difference():
    flat = {2015 + i: 10e6 * 1.03 ** i for i in range(12)}
    stepped = {w: v * (1.3 if w >= 2021 else 1.0) for w, v in flat.items()}
    d0, d1 = dp.differences(flat), dp.differences(stepped)
    changed = [i for i, (a, b) in enumerate(zip(d0, d1)) if abs(a - b) > 1e-12]
    assert len(changed) == 1
    assert dp.g_robust(stepped, 2026) == pytest.approx(dp.g_robust(flat, 2026), rel=1e-12)


def test_carry_const_uses_the_recorded_g_ref():
    assert dp.forecast("carry_const", SYN, 2026, 3, g_ref=0.0409) == pytest.approx(
        SYN[2026] * 1.0409 ** 3)
    with pytest.raises(dp.DpwPathError):
        dp.forecast("carry_const", SYN, 2026, 1)


def test_the_taper_returns_to_the_escalator_path():
    p = dp.build_path(16e6, 2026, method="robust_drift", g_ref=0.0409, g_a=0.03)
    const = dp.build_path(16e6, 2026, g_ref=0.0409)
    for h in range(1, 6):
        assert p[2026 + h] == pytest.approx(16e6 * 1.03 ** h)
    dev5 = 5 * math.log(1.03 / 1.0409)
    for k in range(1, 5):
        s = 2031 + k
        assert math.log(p[s]) - math.log(const[s]) == pytest.approx((1 - k / 5) * dev5, abs=1e-12)
    for s in range(2036, 2046):
        assert p[s] == pytest.approx(const[s], rel=1e-14)
    kinds = dp.path_kinds(2026, "robust_drift")
    assert kinds[2026] == "realized" and kinds[2031] == "forecast" and kinds[2032] == "assumption"
    assert dp.path_kinds(2026, "carry_const")[2027] == "convention"


def test_the_side_rule_in_growth_terms_and_a_restated_anchor():
    """The side is decided on the scoring vintage's growth, so a restatement of
    the anchor winter between the forecast and the scoring cannot decide it."""
    g_a, g_ref = 0.02, 0.0409
    truth_s = {2026: 16.0e6, 2027: 16.0e6 * 1.025}
    r = dp.realized_log_growth(truth_s, 2027)
    assert dp.side_of_target(r, g_a, g_ref) == "A"
    restated = {2026: 17.5e6, 2027: 17.5e6 * 1.025}           # both winters restated
    assert dp.side_of_target(dp.realized_log_growth(restated, 2027), g_a, g_ref) == "A"
    assert dp.realized_log_growth({2027: 1.0}, 2027) is None   # unsided
    r_c = math.log(1.045)
    assert dp.side_of_target(r_c, g_a, g_ref) == "C"


def test_reanchoring_uses_forecast_over_anchor():
    truth = SYN
    rows = dp.forecast_rows(truth, 2024, made_at="2026-10-02", truth_sha256="0" * 64, basis_id=None,
                            g_ref=0.0409, blind_check={"count": 0})
    a_s = 18e6
    for row in rows:
        re = dp.reanchor(a_s, row["forecast_usd"], row["anchor_usd"])
        growth_form = a_s * (1 + row["growth"]) ** row["h"]
        if row["arm"] in ("carry_destale", "carry_zero", "robust_drift", "carry_const"):
            assert re == pytest.approx(growth_form, rel=1e-12)
        elif row["h"] >= 2:
            assert re != pytest.approx(growth_form, rel=1e-9), row["arm"]


def _t(side, regime=False):
    return {"side": side, "regime": regime}


def test_confirmation_veto_and_unsided_targets():
    # confirm_first: the first two sided non-REGIME targets on A's side confirm
    assert dp.blind_status("PASS_DEV", "confirm_first",
                           [_t("A"), _t(None), _t("A", True), _t("A")])["status"] == "CONFIRMED"
    # one miss before confirmation vetoes, REGIME or not
    assert dp.blind_status("PASS_DEV", "confirm_first", [_t("A"), _t("C", True)])["status"] == "VETOED"
    # an unsided target counts toward nothing
    assert dp.blind_status("PASS_DEV", None, [_t(None), _t("A")])["status"] == "PENDING"
    assert dp.blind_status("NULL", "serve_at_dev_pass", [_t("A")])["status"] == "NOT_ARMED"


def test_serve_at_dev_pass_reverts_only_on_two_consecutive_misses():
    """OD-6 serve_at_dev_pass: A serves from PASS_DEV, the single-miss rule does
    not apply, two consecutive sided misses revert it; a REGIME target on A's
    side or an unsided target neither extends nor resets the run."""
    od6 = "serve_at_dev_pass"
    assert dp.blind_status("PASS_DEV", od6, [_t("C")]) == {"status": "PENDING", "reverted": False}
    assert dp.blind_status("PASS_DEV", od6, [_t("C"), _t("A"), _t("C")])["status"] == "PENDING"
    assert dp.blind_status("PASS_DEV", od6, [_t("C"), _t(None), _t("A", True), _t("C")]) == {
        "status": "VETOED", "reverted": True}
    assert dp.blind_status("PASS_DEV", od6, [_t("C", True), _t("C")])["reverted"] is True
    assert dp.blind_status("PASS_DEV", od6, [_t("A"), _t("C"), _t("A")])["status"] == "CONFIRMED"
    # after confirmation under confirm_first, the reversion rule applies too
    assert dp.blind_status("PASS_DEV", "confirm_first",
                           [_t("A"), _t("A"), _t("C"), _t("C")])["reverted"] is True


def test_the_band_is_disclosure_shaped():
    path = dp.build_path(16e6, 2026, g_ref=0.0409)
    b = dp.band(path, 2026, SYN, 0.03, "carry_const")
    assert b["n_d"] == 11 and b["c_m"] == 1.0
    assert b["t_0.90"] == pytest.approx(1.372184, abs=1e-6)       # t_{0.90, 10}
    for s in (2027, 2031, 2040):
        assert b["p10"][s] < path[s] < b["p90"][s]
        assert b["ev_factor_unapplied"][s] > 1.0
    assert b["kind"][2027] == "convention" and b["kind"][2032] == "assumption"
    assert dp.band(path, 2026, SYN, 0.03, "robust_drift")["c_m"] == pytest.approx(math.pi / 2)
    assert dp.t_quantile(0.95, 7) == pytest.approx(1.894579, abs=1e-6)


def test_level_equivalent_sticker_and_term_mix():
    """G_i = sticker x PV_r(schedule) / PV_r(level); a level schedule is its own sticker."""
    level = [(t, 10e6) for t in range(5)]
    assert dp.level_equivalent_sticker(50e6, 5, level, 0.07) == pytest.approx(50e6)
    deferred = [(t, 2e6) for t in range(5)] + [(t, 8e6) for t in range(10, 15)]
    g = dp.level_equivalent_sticker(50e6, 5, deferred, 0.07)
    assert g < 50e6
    assert g == pytest.approx(50e6 * dp.pv(deferred, 0.07) / dp.pv(level, 0.07))
    idx, dropped = dp.term_mix_index([(1, 10e6, 1.0), (3, 30e6, 2.0)])
    assert dropped == ["4+"]
    w1, w2 = 0.2517 / (0.2517 + 0.3177), 0.3177 / (0.2517 + 0.3177)
    assert idx == pytest.approx(w1 * 10e6 + w2 * 15e6)
    assert sum(dp.TERM_MIX_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-12)
