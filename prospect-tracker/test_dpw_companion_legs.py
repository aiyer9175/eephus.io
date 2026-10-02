# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""I5, the companion salary legs, on SYNTHETIC inputs (DESIGN_v2 section 2,
rows 2 and 28; OD-4).

Tabled minimum seasons read the CBA table, season B keeps what salary_path
serves, and untabled seasons after s_T follow the OD-4 mode (the served path's
ratio, each index's own trend, or flat nominal). The prospect engine's
arbitration on the prior_season basis is the minimum or the arbitration
fraction of the PRIOR season's WAR priced at the market of season s_t. The
/arbitration/ inputs never move, and the 0.05 fallbacks raise in unified mode.
"""

from __future__ import annotations

import pytest

import dpw_companion
import dpw_path as dp
import dpw_testkit as kit
import fa_class
import fa_market as fm
import salary_path as sp
import value_framework as vf

B = 2027


@pytest.fixture
def deflator(monkeypatch):
    series = {y: 1.022 ** (y - 2015) for y in range(2015, 2027)}
    monkeypatch.setattr(sp, "arb_deflator_series", lambda: series)
    return series


@pytest.mark.parametrize("mode", ["neutral_follow_path", "own_trends", "flat_nominal"])
def test_the_writer_reads_the_table_then_the_mode(deflator, mode):
    path = dp.build_path(16.46e6, B - 1, g_ref=0.0409)
    blk = dpw_companion.salary_index_block(B, path, mode, dp.WRITTEN_THROUGH)
    table = {int(k): float(v) for k, v in sp.league_min_table().items()}
    lmin = {int(k): v for k, v in blk["league_min_by_season"].items()}
    arb = {int(k): v for k, v in blk["arb_index_scale_by_season"].items()}
    s_t = blk["s_T"]
    assert s_t == max(B, max(table))
    for s, v in table.items():
        assert lmin[s] == v                                   # never override a tabled number
    assert lmin[B] == float(sp.league_min_usd(B))             # season B as salary_path serves it
    for k in (1, 4, 9):
        s = s_t + k
        if mode == "neutral_follow_path":
            assert lmin[s] == pytest.approx(lmin[s_t] * path[s] / path[s_t], rel=1e-12)
            assert arb[s] == pytest.approx(path[s] / path[blk["s_T_arb"]], rel=1e-12)
        elif mode == "own_trends":
            assert lmin[s] == pytest.approx(lmin[s_t] * (1 + blk["league_min_growth"]) ** k, rel=1e-12)
            assert arb[s] == pytest.approx((1 + blk["arb_growth"]) ** (s - blk["s_T_arb"]), rel=1e-12)
            assert blk["arb_growth"] == pytest.approx(0.022, rel=1e-9)
        else:
            assert lmin[s] == lmin[s_t] and arb[s] == 1.0


@pytest.mark.parametrize("mode", ["neutral_follow_path", "own_trends", "flat_nominal"])
def test_the_accessors_follow_the_recorded_mode(tmp_path, mode):
    with kit.unified(tmp_path, companion_mode=mode):
        si = vf._require_block()["salary_index"]
        s_t = int(si["s_T"])
        for s in range(2023, s_t + 1):
            assert vf.league_min_for(s) == float(si["league_min_by_season"][str(s)])
        s = s_t + 3
        if mode == "neutral_follow_path":
            assert vf.league_min_for(s) == pytest.approx(
                vf.league_min_for(s_t) * vf.price_level(s) / vf.price_level(s_t), rel=1e-9)
        elif mode == "own_trends":
            assert vf.league_min_for(s) == pytest.approx(vf.league_min_for(s_t) * 1.054 ** 3, rel=1e-9)
        else:
            assert vf.league_min_for(s) == vf.league_min_for(s_t)
        # past the written range the mode carries on
        assert vf.league_min_for(2050) > 0


def test_the_prior_season_arbitration_rule(tmp_path, monkeypatch):
    st = vf._config()["service_time"]
    monkeypatch.setitem(st, "arb_basis", "prior_season")
    wars = [0.5, 1.0, 1.5, 4.0, 2.0, 3.0]
    with kit.unified(tmp_path):
        seasons = [2028.0 + t for t in range(len(wars))]
        sal = vf._service_path_salaries_unified(wars, seasons, False)
        pre_arb, fracs = vf._arb_ladder(st, False)
        for t, s in enumerate(seasons):
            lm = vf.league_min_for(s, legacy=float(st["league_min_usd"]))
            if t < pre_arb:
                assert sal[t] == lm
            else:
                frac = fracs[min(t - pre_arb, len(fracs) - 1)]
                assert sal[t] == pytest.approx(max(lm, frac * vf.season_value_usd(wars[t - 1], s)),
                                               rel=1e-12)


def test_the_arbitration_inputs_never_move(tmp_path):
    off = (dict(sp.league_min_table()), [sp.league_min_usd(s) for s in range(2020, 2040)])
    with kit.unified(tmp_path, companion_mode="own_trends"):
        on = (dict(sp.league_min_table()), [sp.league_min_usd(s) for s in range(2020, 2040)])
    assert on == off


def test_the_005_fallbacks_raise_in_unified_mode(tmp_path, monkeypatch):
    cfg = vf._config()
    monkeypatch.delitem(cfg, "dollars_per_war_inflation")
    assert fm._dpw_inflation() == 0.05                         # OFF: the legacy fallback fires
    with kit.unified(tmp_path):
        with pytest.raises(vf.DpwPathError):
            fm._dpw_inflation()
        with pytest.raises(vf.DpwPathError):
            fa_class.dollars_per_war_for_season(2020)
        assert fa_class.dollars_per_war_for_season(2030) == pytest.approx(vf.price_level(2030))
    import inspect
    import proj_export
    assert "raise vf.DpwPathError" in inspect.getsource(proj_export._build_payload_body)
