# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR site-wide calibration's build (docs/ewar-2026-10-22/EWAR_SITEWIDE_CALIBRATION.md
parts 3 and 4): WAG's observed leg on the headline eWAR, and the Awards deserved read on
eWAR realized with its measurement band. Synthetic rows only; nothing is fetched."""

from __future__ import annotations

import math

import pytest

import awards_core as A
import storage


# --------------------------------------------------------------------------- #
# part 3: WAG on the headline eWAR
# --------------------------------------------------------------------------- #
ROW = {"source": "fwar", "career_war": 6.77, "seasons": {"2025": 2.5, "2026": 4.27},
       "fwar_coverage": {"mlbam": 1, "fallback_pre_years": [], "fallback_post_years": []}}


def _fake_v3(dep):
    def f(row, provider):
        assert provider == "ewar_v3"   # named literally, never DISPLAY_PROVIDER
        seasons = dict(row["seasons"])
        seasons["2026"] = round(seasons["2026"] + dep, 2)
        return dict(row, seasons=seasons, source="ewar_v3",
                    career_war=round(sum(seasons.values()), 2))
    return f


def test_wag_reads_the_stored_row_while_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(storage, "WAG_EWAR_HEADLINE", False)
    assert storage._wag_observed_war(ROW) == (6.77, "fwar")


def test_wag_on_the_headline_adds_the_season_departures(monkeypatch):
    import war_source
    monkeypatch.setattr(storage, "WAG_EWAR_HEADLINE", True)
    monkeypatch.setattr(war_source, "row_on_provider", _fake_v3(-0.31))
    obs, basis = storage._wag_observed_war(ROW)
    assert basis == "ewar_v3" and obs == pytest.approx(6.46)


def test_wag_on_the_headline_keeps_the_stored_total_with_no_departure(monkeypatch):
    import war_source
    monkeypatch.setattr(storage, "WAG_EWAR_HEADLINE", True)
    monkeypatch.setattr(war_source, "row_on_provider", _fake_v3(0.0))
    obs, basis = storage._wag_observed_war(dict(ROW, career_war=6.771))
    assert obs == 6.771 and basis == "ewar_v3"


def test_wag_falls_back_to_the_stored_row_when_the_provider_does_not_re_express(monkeypatch):
    import war_source
    monkeypatch.setattr(storage, "WAG_EWAR_HEADLINE", True)
    monkeypatch.setattr(war_source, "row_on_provider", lambda row, provider: dict(row))
    assert storage._wag_observed_war(ROW) == (6.77, "fwar")


# --------------------------------------------------------------------------- #
# part 4: the Awards deserved read
# --------------------------------------------------------------------------- #
def test_the_band_constant_halves_the_systems_disagreement_per_unit_of_exposure():
    stints = {"bat": [{"year_ID": 2019, "mlb_ID": 1, "PA": 300, "WAR_bwar": 1.0},
                      {"year_ID": 2019, "mlb_ID": 1, "PA": 100, "WAR_bwar": 0.5},
                      {"year_ID": 2021, "mlb_ID": 2, "PA": 600, "WAR_bwar": 3.0},
                      {"year_ID": 2020, "mlb_ID": 3, "PA": 200, "WAR_bwar": 9.0}],
              "pit": [{"year_ID": 2022, "mlb_ID": 4, "IPouts": 600, "WAR_bwar": 2.0}]}
    fwar = {"bat": {(1, 2019): 2.5, (2, 2021): 2.0, (3, 2020): 0.0}, "pit": {(4, 2022): 4.0}}
    k = A.band_constants(stints, fwar)
    # bat: d = 1.0 on 400 PA, d = -1.0 on 600 PA; 2020 is outside the frame
    assert k["bat"]["n"] == 2 and k["bat"]["k"] == pytest.approx(2.0 / (2 * 1000))
    # pit: d = 2.0 on 200 IP
    assert k["pit"]["k"] == pytest.approx(4.0 / (2 * 200)) and k["pit"]["unit"] == "IP"
    assert 2020 not in k["seasons"] and k["z"] == A.DESERVED_Z
    assert not A.band_ok(k)   # fewer than BAND_MIN_N player-seasons


def test_sigma_reads_pitching_only_for_the_cy_young():
    k = {"bat": {"k": 0.001}, "pit": {"k": 0.004}}
    assert A.band_sigma(k, "CY", 600, 200) == pytest.approx(math.sqrt(0.8))
    assert A.band_sigma(k, "MVP", 600, 200) == pytest.approx(math.sqrt(0.6 + 0.8))


def _rows():
    return [{"mlbam": 1, "name": "A", "league": "AL", "bat": 6.0, "pit": 0.0, "bat_real": 6.0,
             "pit_real": 0.0, "pa": 650, "ip": 0.0, "clubs": ["NYY"], "war_provider": "ewar_v3"},
            {"mlbam": 2, "name": "B", "league": "AL", "bat": 0.0, "pit": 5.0, "pit_real": 6.4,
             "pa": 0, "ip": 200.0, "clubs": ["BOS"], "war_provider": "ewar_v3"},
            {"mlbam": 3, "name": "C", "league": "AL", "bat": 3.0, "pit": 0.0, "bat_real": 3.0,
             "pa": 600, "ip": 0.0, "clubs": ["TOR"], "war_provider": "ewar_v3"}]


def test_realized_rows_swap_each_side_and_keep_the_headline():
    rows = A.realized_rows(_rows())
    b = next(r for r in rows if r["mlbam"] == 2)
    assert b["pit"] == 6.4 and b["headline"] == 5.0 and "pit_real" not in b
    assert A.realized_rows([{"mlbam": 9, "bat": 1.0, "pit": 0.0}]) is None


def test_deserved_block_verdict_band_and_writers():
    rows = A.realized_rows(_rows())
    ballot = A.mvp_ballot(rows, "AL", 2025, n=A.DESERVED_N)
    k = {"bat": {"k": 0.0005}, "pit": {"k": 0.0038}}
    blk = A.deserved_block("MVP", ballot, rows, k, writers_id=1)
    first = blk["top"][0]
    assert first["mlbam"] == 2 and first["score"] == 6.4 and first["ewar_display"] == 5.0
    # 6.4 vs 6.0: inside 1.645 * sqrt(0.76 + 0.325); 6.4 vs 3.0: outside
    assert blk["verdict"] == "too_close" and blk["within_band_of_first"] == [1]
    assert blk["writers"] == {"id": 1, "standing": "within_band"}
    assert "Too close to call on eWAR realized" in blk["sentence"]
    tight = {"bat": {"k": 1e-6}, "pit": {"k": 1e-6}}
    clear = A.deserved_block("MVP", ballot, rows, tight, writers_id=3)
    assert clear["verdict"] == "clear" and clear["writers"]["standing"] == "outside_band"
    assert "—" not in clear["sentence"] and "–" not in clear["sentence"]


def test_the_deserved_flag_and_its_constants():
    assert isinstance(A.AWARDS_DESERVED_LIVE, bool)
    assert A.DESERVED_N == 5 and A.DESERVED_Z == 1.645
    assert A.DESERVED_AWARDS == ("MVP", "CY", "ROY")
    assert A.BAND_SEASONS == (2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
