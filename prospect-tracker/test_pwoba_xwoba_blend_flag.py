# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The pWOBA xwOBA blend flag (EEPHUS_PWOBA_XWOBA_BLEND): the 2026-10-14
re-gate PASS's production diff. The owner flipped it on (NOV15-PWOBA-FLIP =
(a), 2026-10-14), so it defaults ON and the variable is an off switch. Off,
nothing is read and the column is the unblended engine projection."""
from __future__ import annotations

import pytest

import hitter_export as he


@pytest.fixture(autouse=True)
def _flag_unset(monkeypatch):
    monkeypatch.delenv(he.PWOBA_XWOBA_BLEND_ENV, raising=False)


def test_the_flag_defaults_on_and_only_an_explicit_off_value_turns_it_off(monkeypatch):
    assert he.pwoba_xwoba_blend_on() is True
    for v in ("1", "on", "", "true", "YES"):
        monkeypatch.setenv(he.PWOBA_XWOBA_BLEND_ENV, v)
        assert he.pwoba_xwoba_blend_on() is True, v
    for v in ("0", "off", "false", "No"):
        monkeypatch.setenv(he.PWOBA_XWOBA_BLEND_ENV, v)
        assert he.pwoba_xwoba_blend_on() is False, v


def test_the_blend_is_the_frozen_arm_and_a_missing_leg_leaves_w_alone():
    assert he.PWOBA_XWOBA_BLEND_B == 0.2
    assert he.blend_pwoba_xwoba(0.300, 0.350) == pytest.approx(0.8 * 0.300 + 0.2 * 0.350)
    assert he.blend_pwoba_xwoba(0.300, None) == 0.300


def test_the_xwoba_map_keeps_the_labs_pa_floor(monkeypatch):
    import mlb_player_export as mpe
    rows = [{"player_id": "1", "est_woba": "0.360", "pa": "250"},
            {"player_id": "2", "est_woba": "0.800", "pa": "1"},
            {"player_id": "3", "est_woba": "0.330", "pa": "100"},
            {"player_id": "x", "est_woba": "0.330", "pa": "100"}]
    monkeypatch.setattr(mpe, "_savant", lambda kind, year, side="batter": rows)
    m = he._pwoba_xwoba_map(2026)
    assert m == {1: pytest.approx(0.360), 3: pytest.approx(0.330)}


def test_off_the_map_is_never_read(monkeypatch):
    import mlb_player_export as mpe

    def _boom(*a, **k):
        raise AssertionError("the Savant leaderboard must not be read while the flag is off")

    monkeypatch.setattr(mpe, "_savant", _boom)
    monkeypatch.setenv(he.PWOBA_XWOBA_BLEND_ENV, "0")
    assert he.pwoba_xwoba_blend_on() is False
    # the exporter's guard: the map is built only when the flag is on
    xw = he._pwoba_xwoba_map(2026) if he.pwoba_xwoba_blend_on() else {}
    assert xw == {}
