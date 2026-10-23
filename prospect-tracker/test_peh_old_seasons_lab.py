# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PE-H old-seasons read's code against its registration
(docs/ewar-v3/EWAR_PEH_OLD_SEASONS_GATE.md): the registered constants, the controls
(an all-zero delta never reads WIN, a planted delta reads WIN (components) with its
twin failing), the club-code normalization, the fetcher's nightly window, and the
whole reporting path on fixtures with nulls. Nothing here reads a real season."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import fetch_win_prob_old as FO  # noqa: E402
import peh_old_seasons_lab as P  # noqa: E402
import swar_lab as L  # noqa: E402


def test_registered_constants():
    assert P.PREDICTOR_SEASONS == tuple(range(2002, 2015))
    assert P.SEASONS == tuple(range(2002, 2016))
    assert (P.BOOT, P.SEED, P.CLUB_SEED) == (4000, 20261023, 20261023 + 202)
    assert P.K_B1_PEH == 427.0 and P.K_B1_SECONDARY == 662.0
    assert P.PLANT_SHARE == 0.5
    assert (P.MIN_IDENTITY_SHARE, P.MIN_PITCH_COVERAGE, P.MIN_GAME_COVERAGE) == (0.999, 0.99, 0.99)
    assert P.MIN_PREDICTOR_SEASONS == 6
    assert (P.TOL_SCALE, P.TOL_WEIGHT) == (0.0005, 0.002)
    assert P.STANDINGS_KEY == {"ANA": "LAA", "FLA": "MIA", "TBD": "TBR", "MON": "WSN"}
    assert P.RECORD_PATH.relative_to(P.ROOT).as_posix() == "docs/ewar-v3/peh_old_seasons_eval.json"
    assert P.CORPUS_OLD.parts[-2:] == ("peh_old", "corpus")
    assert "pbp_corpus" not in P.CORPUS_OLD.parts


def test_frozen_part_constants_are_the_looks():
    import pitch_economy as pe
    assert (pe.DELTA_TTO, pe.K_CL, pe.K_P) == (0.01847965, 236.41, 110.95)


def test_normalize_team_exposure():
    got = P.normalize_team_exposure({("hit", 2004, 1): {"MON": 300.0, "FLA": 100.0},
                                     ("hit", 2004, 2): {"ANA": 50.0, "TBD": 20.0, "BOS": 5.0}})
    assert got[("hit", 2004, 1)] == {"WSN": 300.0, "MIA": 100.0}
    assert got[("hit", 2004, 2)] == {"LAA": 50.0, "TBR": 20.0, "BOS": 5.0}
    assert P.club_of(got, "hit", 2004, 1) == "WSN"
    assert P.club_of(got, "hit", 2004, 9).startswith("none|")


def test_planted_and_null_tests():
    pairs = [{"mlbam": 1, "y": 2002, "n0": 400.0, "n1": 500.0, "b0": 5.0, "tgt": 10.0, "tests": {}},
             {"mlbam": 2, "y": 2002, "n0": 300.0, "n1": 500.0, "b0": -2.0, "tgt": 0.0, "tests": {}}]
    null = P.with_tests(pairs, lambda p: p["b0"])
    assert [p["tests"]["peh"] for p in null] == [5.0, -2.0]
    pl = P.planted(pairs)
    mean = 10.0 / 1000.0
    assert pl[0]["tests"]["peh"] == pytest.approx(5.0 + 0.5 * 400 * (10.0 / 500 - mean))
    assert pl[1]["tests"]["peh"] == pytest.approx(-2.0 + 0.5 * 300 * (0.0 / 500 - mean))


def test_nightly_window():
    t = dt.datetime(2026, 10, 23, 6, 30, tzinfo=dt.timezone.utc)
    assert FO.seconds_until_open(t) == pytest.approx(4.5 * 3600)
    assert FO.seconds_until_open(dt.datetime(2026, 10, 23, 11, 0, tzinfo=dt.timezone.utc)) == 0.0
    assert FO.seconds_until_open(dt.datetime(2026, 10, 23, 5, 59, tzinfo=dt.timezone.utc)) == 0.0
    slept = []
    pacer = FO.WindowPacer(utcnow=lambda: t, sleep=slept.append, clock=lambda: 0.0)
    pacer.wait()
    assert slept and slept[0] == pytest.approx(4.5 * 3600 + 1.0)
    assert FO.OLD_SEASONS == tuple(range(2002, 2011))
    with pytest.raises(SystemExit):
        FO.parse_seasons("2011")


def test_fetcher_refuses_the_live_and_record_dirs():
    import fetch_win_prob_hist as FH
    for bad in ("win_prob", "pbp_corpus", "pbp_runners"):
        with pytest.raises(RuntimeError):
            FH.check_out_dir(ROOT / ".cache" / bad)
    assert FO.OLD_DIR.name == "win_prob_old"


@pytest.mark.parametrize("plant,expect_win", [(0.0, False), (0.8, True)])
def test_reporting_path_on_fixtures(tmp_path, plant, expect_win):
    rec = P.run_read(tmp_path / "rec.json", boot=120, log=lambda *a: None,
                     inputs=P.fixture_inputs(plant=plant))
    assert (tmp_path / "rec.json").exists()
    assert rec["void"] is False
    assert rec["controls"]["null_passes"] is True and rec["controls"]["planted_passes"] is True
    for c in ("PE-H rate", "PE-H total"):
        assert rec["controls"]["null"][c]["disposition"] not in (L.WIN_COMPONENTS, L.WIN_REGRESSION, L.SMALL_WIN)
        assert rec["controls"]["planted"][c]["disposition"] == L.WIN_COMPONENTS
        assert rec["controls"]["planted"][c]["twin_lo95"] <= 0
    rate = rec["cells"]["PE-H rate"]["disposition"]
    assert (rate == L.WIN_COMPONENTS) is expect_win
    assert rec["cells"]["PE-H rate"]["holm_family"] == ["PE-H rate", "PE-H total"]
    assert set(rec["floors"]) == {"PE-H rate", "PE-H total"}
    assert "club_clustered" in rec and "team_guard" in rec and "secondary" in rec
    assert rec["cited_not_rescored"]["look_2026_10_19"]["pairs"] == 1071
    if not expect_win:
        assert rec["admission"]["passes"] is False


def test_read_runs_once(tmp_path):
    out = tmp_path / "rec.json"
    out.write_text("{}", encoding="utf-8")
    with pytest.raises(P.ReadStop):
        P.run_read(out, boot=50, log=lambda *a: None, inputs=P.fixture_inputs())


def test_failed_control_voids_before_real_cells(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "PLANT_SHARE", 0.0)
    rec = P.run_read(tmp_path / "rec.json", boot=60, log=lambda *a: None, inputs=P.fixture_inputs(plant=0.8))
    assert rec["void"] is True and "cells" not in rec
    assert rec["controls"]["planted_passes"] is False
