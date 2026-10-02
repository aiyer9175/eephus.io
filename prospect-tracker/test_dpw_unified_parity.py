# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""I1 and I2 in unified mode, on a SYNTHETIC series (DESIGN_v2 section 9).

One WAR path priced three ways gives one present value at R to the base season
B: the value_framework accessors, proj_export's per-season kernel with its
unified discount, and fa_market.rational_value_usd at the class year (I2's
exception: a class c values at its transaction date, so it converts by d(c)).
The Trade Machine's projection band (row 30) and the R5.1 pre-arb pricing
(row 31) discount exactly as proj_export's surNpv does, and the realized leg of
total_value_mm (row 27) prices the consumed seasons' market at P(B)/F with the
engine's own market-linked salary estimates scaled alongside, while a
salary_by_year actual and the league-minimum floor stay nominal.
"""

from __future__ import annotations

import json
import random

import pytest

import dpw_testkit as kit
import fa_market as fm
import proj_export
import value_framework as vf


def _paths(n=40, seed=20260925):
    rng = random.Random(seed)
    return [[rng.uniform(-0.3, 5.5) for _ in range(rng.randint(1, 8))] for _ in range(n)]


@pytest.mark.parametrize("s0", [2026, 2027, 2030])
def test_one_war_path_has_one_present_value(tmp_path, s0):
    with kit.unified(tmp_path):
        b = vf.pricing_base_season()
        R = vf.nominal_rate()
        assert b == proj_export.FIRST_SEASON
        for path in _paths():
            engine = sum(vf.season_value_usd(w, s0 + t) * vf.season_discount(s0 + t)
                         for t, w in enumerate(path))
            if s0 >= b:
                off = s0 - b
                pe = vf.season_discount(b) * sum(
                    proj_export._season_value_usd(w, off + t, 12.0e6) / (1.0 + R) ** (off + t)
                    for t, w in enumerate(path))
                assert pe == pytest.approx(engine, rel=1e-9, abs=1e-3)
            fa = fm.rational_value_usd(path, s0, 12.0e6) * (1.0 + R) ** -(s0 - b)
            # rational_value_usd returns whole dollars
            assert fa == pytest.approx(engine, abs=2.0 * max(1.0, (1.0 + R) ** -(s0 - b)))


def test_the_fa_value_leg_ignores_the_legacy_level_and_escalator(tmp_path):
    with kit.unified(tmp_path):
        a = fm.rational_value_usd([2.0, 2.0, 1.5], 2027, 12.0e6, infl=0.05)
        b = fm.rational_value_usd([2.0, 2.0, 1.5], 2027, 30.0e6, infl=0.0)
        assert a == b


def test_the_trade_machine_band_discounts_like_surnpv(tmp_path):
    import bayes_trade_value as bt
    war = [3.0, 2.8, 2.5, 2.1, 1.8]
    p10 = [1.5, 1.2, 1.0, 0.7, 0.4]
    p90 = [4.4, 4.2, 3.9, 3.4, 3.0]
    v = {"war": war, "warP10": p10, "warP90": p90, "sur": [1.0] * 5, "surNpv": 50_000_000}
    with kit.unified(tmp_path):
        b, R = vf.pricing_base_season(), vf.nominal_rate()
        lo, hi = bt._projection_band_mm(v, 17.0e6, R)
        want_lo = sum((vf.season_value_usd(w, b + t) - vf.season_value_usd(p, b + t))
                      * vf.season_discount(b + t) for t, (w, p) in enumerate(zip(war, p10)))
        want_hi = sum((vf.season_value_usd(h, b + t) - vf.season_value_usd(w, b + t))
                      * vf.season_discount(b + t) for t, (w, h) in enumerate(zip(war, p90)))
        assert lo == pytest.approx(round(50.0 - want_lo / 1e6, 1), abs=0.051)
        assert hi == pytest.approx(round(50.0 + want_hi / 1e6, 1), abs=0.051)
        # the legacy 1.07^t discount on a nominal path value would not reproduce it
        legacy_lo = sum((vf.season_value_usd(w, b + t) - vf.season_value_usd(p, b + t)) / 1.07 ** t
                        for t, (w, p) in enumerate(zip(war, p10)))
        assert abs(legacy_lo - want_lo) > 1e5


def test_the_prearb_veteran_npv_reproduces_the_surnpv_rule(tmp_path, monkeypatch):
    import bayes_trade_value as bt
    dd = tmp_path / "data"
    dd.mkdir()
    war = [1.4, 1.6, 1.7, 1.5, 1.2]
    (dd / "mlb_projections.json").write_text(json.dumps({
        "first_season": 2027, "dpw_usd": 17_143_641, "ros_fraction": 0.0,
        "vets": [{"key": "syn_prearb", "war": war}]}), encoding="utf-8")
    (dd / "debuts.json").write_text(json.dumps({"players": [
        {"player_key": "syn_prearb", "roster_status": {"service_phase": "pre_arb"}}]}),
        encoding="utf-8")
    monkeypatch.setattr(bt, "_PREARB_CACHE", {})
    monkeypatch.setattr(bt, "_SERVICE_PHASE_CACHE", {})
    with kit.unified(tmp_path):
        shadow = bt._prearb_priced(dd)["syn_prearb"]
        b = vf.pricing_base_season()
        priced = [t for t, s in enumerate(shadow.get("sur") or []) if s is not None]
        assert priced, shadow.get("prearb")
        want = sum((vf.season_value_usd(war[t], b + t) - vf.league_min_for(b + t))
                   * vf.season_discount(b + t) for t in priced)
        assert shadow["surNpv"] == int(want)


def test_the_realized_leg_prices_at_the_remaining_legs_level(tmp_path):
    wars = {2022: 2.5, 2023: 3.0, 2024: 3.4, 2025: 3.1, 2026: 2.8, 2027: 2.2, 2028: 2.0}
    actual = {2023: 2_500_000}
    off = vf.realized_consumed_seasons(wars, salary_by_year=actual)
    off_usd = vf._realized_consumed_usd(off)
    st = vf._config()["service_time"]
    pre_arb = int(st["pre_arb_years"])
    control = int(st["control_years"])
    lm_mm = float(st["league_min_usd"]) / 1e6
    with kit.unified(tmp_path, level_n=15.0e6):
        k = vf.price_level(vf.pricing_base_season()) / vf._flat_rate_usd()
        assert abs(k - 1.0) > 0.01
        on = vf.realized_consumed_seasons(wars, salary_by_year=actual)
        for a, b_ in zip(off, on):
            assert a["market_mm"] == b_["market_mm"]           # stored at F; the leg applies k once
        r = float(vf._config()["discount_rate"])
        n = len(on)
        for i, (row_off, row_on) in enumerate(zip(off, on)):
            yr = row_on["year"]
            sur_on = row_on["market_mm"] * k - row_on["salary_mm"]
            sur_off = row_off["market_mm"] - row_off["salary_mm"]
            if yr in actual:
                assert row_on["salary_mm"] == row_off["salary_mm"] == actual[yr] / 1e6
            elif i < pre_arb:
                assert row_on["salary_mm"] == row_off["salary_mm"] == pytest.approx(lm_mm)
            elif i < control:
                if row_off["salary_mm"] > lm_mm and row_on["salary_mm"] > lm_mm:
                    # an estimated arbitration season scales exactly by P(B)/F
                    assert sur_on == pytest.approx(sur_off * k, rel=1e-3, abs=2e-4)
            else:
                # an estimated post-control season is paid about fair market: 0 ON and OFF
                assert sur_off == pytest.approx(0.0, abs=1e-4)
                assert sur_on == pytest.approx(0.0, abs=1e-3)
        total = sum((row["market_mm"] * 1e6 * k - row["salary_mm"] * 1e6) * (1 + r) ** (n - 1 - i)
                    for i, row in enumerate(on))
        assert vf._realized_consumed_usd(on) == pytest.approx(total, rel=1e-12)
    assert off_usd == vf._realized_consumed_usd(off)            # OFF unchanged by the excursion


def test_unified_seasons_raise_when_the_path_is_absent(tmp_path):
    p = kit.write_series(tmp_path / "no_block.json", None)
    with vf.dpw_path_forced(True, series_path=p):
        assert vf.dpw_path_active() is False                    # no block: the legacy branch
        with pytest.raises(vf.DpwPathError):
            vf.price_level(2027)
