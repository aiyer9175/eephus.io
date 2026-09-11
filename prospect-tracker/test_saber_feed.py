# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""saber_feed: the one loader for FanGraphs' served WAR components."""
from __future__ import annotations

import pytest

import saber_feed as S


def _row(pid, n=1, **stat):
    return {"player": {"id": pid, "fullName": f"p{pid}"}, "numTeams": n, "stat": stat}


def test_a_percentage_string_is_never_a_run_value():
    assert S.run_value("1.000") is None
    assert S.run_value(6.41) == pytest.approx(6.41)
    assert S.run_value(True) is None
    assert S.run_value(float("nan")) is None


def test_a_stint_group_resolves_to_its_unique_season_total():
    rows, amb, multi = S.resolve_groups([_row(1, 1, fielding=1.0), _row(1, 2, fielding=3.0)])
    assert rows[1]["stat"]["fielding"] == 3.0 and not amb and multi == 1


def test_two_season_totals_refuse_the_id():
    rows, amb, _ = S.resolve_groups([_row(1, 2, fielding=1.0), _row(1, 2, fielding=3.0)])
    assert 1 not in rows and amb == [1]


def test_the_framing_residual_is_rar_minus_the_six_components():
    st = {"batting": -16.19, "baseRunning": -2.62, "fielding": 5.49, "positional": 8.83,
          "wLeague": 1.27, "replacement": 13.77, "rar": 31.55}
    assert S.framing_residual(st) == pytest.approx(21.00, abs=0.01)
    st.pop("wLeague")
    assert S.framing_residual(st) is None


def test_the_hitter_board_reads_the_same_url():
    import hitter_export
    assert hitter_export._SABER_URL == S.SABER_URL
