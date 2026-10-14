# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The owner-waived season-complete override of plus_lab_harness (owner
2026-10-14, EW3-6): explicit, logged, carried by the artifact, and the Nov 15
default never moves."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import plus_lab_harness as plh  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_override(monkeypatch):
    monkeypatch.delenv(plh.SEASON_COMPLETE_ASOF_ENV, raising=False)
    plh._OVERRIDE_LOGGED.clear()
    yield
    plh._OVERRIDE_LOGGED.clear()


def test_the_default_convention_never_changes():
    assert plh.SEASON_COMPLETE_MONTH_DAY == (11, 15)
    assert plh.season_complete(2026, today=date(2026, 10, 14)) is False
    assert plh.season_complete(2026, today=date(2026, 11, 15)) is True
    assert plh.season_complete_override_meta() is None
    assert plh.convention_meta("a", "b")["season_complete_override"] is None


def test_the_override_binds_only_the_season_it_names_and_is_logged(capsys):
    parsed = plh.set_season_complete_asof("2026:2026-10-01")
    assert parsed == {2026: date(2026, 10, 1)}
    assert plh.season_complete(2026, today=date(2026, 10, 14)) is True
    assert plh.season_complete(2026, today=date(2026, 9, 30)) is False
    # 2027 keeps the convention
    assert plh.season_complete(2027, today=date(2027, 10, 14)) is False
    err = capsys.readouterr().err
    assert "season_complete OVERRIDE: season 2026" in err
    assert "owner-waived early read" in err
    plh.season_complete(2026, today=date(2026, 10, 14))
    assert capsys.readouterr().err == "", "logged once per season, not per call"
    meta = plh.convention_meta("a", "b")["season_complete_override"]
    assert meta["seasons"] == {"2026": "2026-10-01"}
    assert meta["default_month_day"] == [11, 15]


def test_a_malformed_override_raises_rather_than_widening_a_pair_set():
    with pytest.raises(ValueError):
        plh.parse_season_complete_asof("2026:10-01")
    with pytest.raises(ValueError):
        plh.parse_season_complete_asof("twentysix:2026-10-01")
    assert plh.parse_season_complete_asof("") == {}
    assert plh.parse_season_complete_asof(None) == {}


def test_clearing_the_override_restores_the_convention():
    plh.set_season_complete_asof("2026:2026-10-01")
    assert plh.season_complete(2026, today=date(2026, 10, 14)) is True
    plh.set_season_complete_asof(None)
    assert plh.season_complete(2026, today=date(2026, 10, 14)) is False
