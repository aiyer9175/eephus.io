# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PUBLISHED columns on the Baserunning section (the test_hitter_wrc_plus.py
model): FanGraphs' BsR and wSB through MLB's sabermetrics feed and Baseball
Savant's run values.

  STINT SAFETY. A crafted decomposition in which the LAST row is a stint and
  the season total sits in the middle: only numTeams-marker selection passes,
  and an id with two totals is refused (absent), never guessed.
  FEED FAILURE leaves the columns blank; the join is by MLBAM id only.
  TITLES. The page labels every published column "PUBLISHED, NOT COMPUTED HERE"
  (FanGraphs) or "From Baseball Savant", and every eBR column "OURS".
  NEVER READ. The feed's `ubr` and `wGdp` fields: since 2016 the served BsR is
  wSB plus Statcast's extra-base runs with no double-play part.

Offline by construction.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import baserunning_export as BE
import saber_feed

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")


def _split(pid, bsr, wsb, num_teams=1, team_id=None, extra=None):
    st = {"baseRunning": bsr, "wSb": wsb}
    st.update(extra or {})
    s = {"player": {"id": pid, "fullName": f"P{pid}"}, "stat": st, "numTeams": num_teams}
    if team_id is not None:
        s["team"] = {"id": team_id}
    return s


def test_single_rows_join_and_the_feed_fields_are_read_verbatim(monkeypatch):
    monkeypatch.setattr(saber_feed, "fetch_splits", lambda season, group="hitting": [
        _split(1, 7.3, 2.1, extra={"ubr": 99.0, "wGdp": 99.0}), _split(2, -1.2, -0.4)])
    pub = BE.load_published(2025)
    assert pub["available"] is True and pub["n_feed_players"] == 2 and pub["n_ambiguous"] == 0
    assert pub["values"] == {1: {"bsr": 7.3, "wsb": 2.1}, 2: {"bsr": -1.2, "wsb": -0.4}}
    assert pub["not_read"] == ["ubr", "wGdp"]
    assert "ubr" not in str(pub["values"]) and "wGdp" not in str(pub["values"])


def test_a_traded_player_reads_his_season_total_and_never_a_positional_stint(monkeypatch):
    monkeypatch.setattr(saber_feed, "fetch_splits", lambda season, group="hitting": [
        _split(7, 1.0, 0.5, team_id=147),          # a stint
        _split(7, 4.0, 2.0, num_teams=2),          # THE season total, in the middle
        _split(7, 3.0, 1.5, team_id=111),          # the last row is a stint
        _split(8, 2.0, 1.0)])
    pub = BE.load_published(2025)
    assert pub["values"][7] == {"bsr": 4.0, "wsb": 2.0}
    assert pub["n_multi_team"] == 1


def test_an_ambiguous_decomposition_is_refused_not_guessed(monkeypatch):
    monkeypatch.setattr(saber_feed, "fetch_splits", lambda season, group="hitting": [
        _split(9, 4.0, 2.0, num_teams=2), _split(9, 4.5, 2.2, num_teams=3), _split(10, 1.0, 0.1)])
    pub = BE.load_published(2025)
    assert 9 not in pub["values"] and pub["ambiguous_ids"] == [9] and pub["n_ambiguous"] == 1
    assert pub["values"][10] == {"bsr": 1.0, "wsb": 0.1}


def test_feed_failure_leaves_the_columns_blank(monkeypatch):
    monkeypatch.setattr(saber_feed, "fetch_splits", lambda season, group="hitting": None)
    pub = BE.load_published(2025)
    assert pub["available"] is False and pub["values"] == {}
    rows = BE.build_rows(2025, official={1: {"name": "A", "team_id": 1, "pos": "SS", "pa": 300, "sb": 3, "cs": 1, "gidp": 2}},
                         counts={"runners": {}, "teams": {}, "runner_team": {}}, sub_rows={}, published=pub,
                         savant={"brv": {}, "steal": {}}, sprint={}, tmap={1: "X"}, links={}, debuts={})
    assert rows and all(k not in rows[0] for k in ("bsr", "wsb", "bsr_rest", "brv", "brv_xb", "brv_sb"))


def test_the_join_is_by_mlbam_only():
    pub = {"values": {5: {"bsr": 2.0, "wsb": 1.0}}}
    official = {5: {"name": "Same Name", "team_id": 1, "pos": "SS", "pa": 300, "sb": 0, "cs": 0, "gidp": 0},
                6: {"name": "Same Name", "team_id": 1, "pos": "2B", "pa": 300, "sb": 0, "cs": 0, "gidp": 0}}
    rows = {r["mlbam"]: r for r in BE.build_rows(
        2025, official=official, counts={"runners": {}, "teams": {}, "runner_team": {}}, sub_rows={},
        published=pub, savant={"brv": {6: {"runner_runs_tot": 1.5}}, "steal": {}}, sprint={}, tmap={1: "X"},
        links={}, debuts={})}
    assert rows[5]["bsr"] == 2.0 and "bsr" not in rows[6]
    assert rows[6]["brv"] == 1.5 and "brv" not in rows[5]


def _col_titles() -> dict[str, str]:
    src = JS.replace("\r\n", "\n")
    if "var BR_COLS = [" not in src:
        pytest.skip("the Baserunning board (BR_COLS) is not on the page yet")
    i = src.index("var BR_COLS = [")
    block = src[i:src.index("\n  ];", i)]
    out = {}
    for m in re.finditer(r'\{ key: "([a-z0-9_]+)"(.*?)\n(?=    \{ key:|  \];|$)', block, re.S):
        t = re.search(r'title: "((?:[^"\\]|\\.)*)"', m.group(2))
        out[m.group(1)] = t.group(1) if t else ""
    return out


def test_every_published_column_says_so_on_the_page_and_every_ebr_column_says_ours():
    t = _col_titles()
    for key in ("bsr", "wsb"):
        assert t[key].startswith("PUBLISHED, NOT COMPUTED HERE."), (key, t[key])
    assert "BsR minus wSB" in t["bsr_rest"] and "Arithmetic" in t["bsr_rest"]
    assert "UBR" not in t["bsr_rest"] and "wGDP" not in t["bsr_rest"]
    for key in ("brv", "brv_xb", "brv_sb", "sprint", "bolts", "hp1", "lead_p", "lead_s", "sav_steal_runs"):
        assert "Baseball Savant" in t[key], (key, t[key])
    for key in ("ebr", "ebr_sb", "ebr_xb", "ebr_dp"):
        assert t[key].startswith("OURS."), (key, t[key])
    assert "forecast" in t["ebr"] and "not a forecast" in t["ebr"]


def test_no_forecast_word_on_a_baserunning_column_title():
    for key, title in _col_titles().items():
        low = title.lower().replace("not a forecast", "")
        for w in ("luck", " due ", "regress", "trending", "clutch", "sleeper", "will "):
            assert w not in low, (key, w)
