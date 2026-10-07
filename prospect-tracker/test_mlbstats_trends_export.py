# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""mlbstats_trends_export: every player-season index for the /mlbstats/ drawer.

Pins the file mlbstats_trends.json: the lab panel, live board and history
order of the sources; plus stats rounded to the nearest whole number; the
refusal when a lab panel and a history payload disagree on a shared (player,
season) index; the thinner-file guard; and the dark flag (the preview directory
under .cache/league_teams/preview/, never data/). Fixtures live under tmp_path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import mlbstats_trends_export as T
from tools import mlbstats_window_lab as lab

LIVE = 2026


def _w(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _boards(d: Path) -> None:
    _w(d / "hitter_leaderboards.json", {"season": LIVE, "as_of": "2026-10-03", "hitters": [
        {"mlbam": 1, "hem_plus": 142, "pa": 482}, {"mlbam": 2, "hem_plus": 88, "pa": 210}]})
    _w(d / "starter_leaderboards.json", {"season": LIVE, "as_of": "2026-10-03", "starters": [
        {"mlbam": 10, "sem_plus": 144, "ip": 158.7}]})
    _w(d / "bullpen_leaderboards.json", {"season": LIVE, "as_of": "2026-10-03", "relievers": [
        {"mlbam": 11, "rem_plus": 121, "ip": 61.3}]})
    _w(d / "defense_leaderboards.json", {"season": LIVE, "as_of": "2026-10-03", "fielders": [
        {"mlbam": 1, "dem_plus": 92, "inn": 572.0, "pos": "LF"}]})
    _w(d / "leverage_leaderboards.json", {"season": LIVE, "as_of": "2026-10-02", "batters": [
        {"mlbam": 1, "wpa": 1.699, "pa": 483}], "starters": []})


def _history(d: Path) -> None:
    def blk(season, key, rows):
        return {"history": {str(season): {"season": season, key: rows}}}
    hh = {"history": {
        "2021": {"hitters": [{"mlbam": 1, "hem_plus": 160, "pa": 654}]},
        "2022": {"hitters": [{"mlbam": 1, "hem_plus": 143, "pa": 664}]}}}
    _w(d / "hitter_history.json", hh)
    _w(d / "starter_history.json", blk(2022, "starters", [{"mlbam": 10, "sem_plus": 120, "ip": 117.7}]))
    _w(d / "bullpen_history.json", blk(2022, "relievers", [{"mlbam": 11, "rem_plus": 90, "ip": 50.0}]))
    _w(d / "defense_history.json", {"history": {
        "2016": {"fielders": [{"mlbam": 1, "dem_plus": 97, "inn": 987.0, "pos": "LF"}]},
        "2022": {"fielders": [{"mlbam": 1, "dem_plus": 77, "inn": 1298.3, "pos": "RF"}]}}})
    _w(d / "leverage_history.json", blk(2022, "batters", [{"mlbam": 1, "wpa": 1.193, "pa": 666}]))


def _panel(lab_dir: Path, season: int = 2022, hem: float = 143.0) -> None:
    _w(lab_dir / f"panel_{season}_v{lab.SCHEMA}.json", {
        "schema": lab.SCHEMA, "season": season,
        "hit": {"1": {"hem": hem, "pa": 664}, "3": {"hem": 99.5, "pa": 120}},
        "pit": {"10": {"outs": 353, "sem": 120.0}, "11": {"outs": 150, "rem": 90.0},
                "12": {"outs": 90, "sem": 101.0, "rem": 104.0}},
        "dfn": {"1": {"dem": 77.0, "inn": 1298.3, "pos": "RF"}},
        "lev_bat": {"1": {"wpa": 1.193, "pa": 666}},
        "lev_sp": {}})


@pytest.fixture()
def fx(tmp_path):
    data, labd = tmp_path / "data", tmp_path / "lab"
    _boards(data)
    _history(data)
    _panel(labd)
    return {"data_dir": data, "lab_dir": labd, "out": tmp_path / "out" / T.OUT_NAME}


def test_the_sources_follow_the_lab_board_history_order(fx):
    doc = T.build(data_dir=fx["data_dir"], lab_dir=fx["lab_dir"], log=lambda *a: None)
    assert doc["seasons"] == list(range(2016, LIVE + 1))
    assert doc["fields"]["h"] == ["season", "hem", "pa"]
    assert doc["fields"]["p"] == ["season", "plus", "ip", "board"]
    p1 = doc["players"]["1"]
    assert p1["h"] == [[2021, 160, 654], [2022, 143, 664], [LIVE, 142, 482]]
    assert p1["d"] == [[2016, 97, 987.0, "LF"], [2022, 77, 1298.3, "RF"], [LIVE, 92, 572.0, "LF"]]
    assert p1["l"] == [[2022, 1.193, 666], [LIVE, 1.699, 483]]
    assert doc["players"]["10"]["p"] == [[2022, 120, 117.7, "sp"], [LIVE, 144, 158.7, "sp"]]
    # a swingman carries one row per pool he was scored in
    assert doc["players"]["12"]["p"] == [[2022, 104, 30.0, "rp"], [2022, 101, 30.0, "sp"]]
    assert doc["sources"]["h"]["2021"] == "qualified history rows only"
    assert doc["sources"]["h"]["2022"].startswith("window lab panel")
    assert doc["sources"]["h"][str(LIVE)].startswith("live hitter_leaderboards")
    assert doc["sources"]["p"][str(LIVE)] == {"sp": "live starter_leaderboards, its scored pool",
                                             "rp": "live bullpen_leaderboards, its scored pool"}
    assert doc["check"]["disagree"] == 0 and doc["check"]["shared"] == 5
    assert doc["as_of"] == "2026-10-03" and doc["live_season"] == LIVE


def test_plus_stats_round_to_the_nearest_whole_number(fx):
    doc = T.build(data_dir=fx["data_dir"], lab_dir=fx["lab_dir"], log=lambda *a: None)
    assert doc["players"]["3"]["h"] == [[2022, 100, 120]]       # 99.5 rounds up
    assert T._nearest(99.49) == 99 and T._nearest(100.5) == 101


def test_a_lab_and_history_disagreement_refuses_and_keeps_the_last_good_file(fx):
    good = T.export(out=fx["out"], data_dir=fx["data_dir"], lab_dir=fx["lab_dir"], log=lambda *a: None)
    assert good["written"] and fx["out"].exists()
    before = fx["out"].read_bytes()
    _panel(fx["lab_dir"], hem=150.0)                             # history says 143
    with pytest.raises(T.Refused, match="disagreements"):
        T.build(data_dir=fx["data_dir"], lab_dir=fx["lab_dir"], log=lambda *a: None)
    s = T.export(out=fx["out"], data_dir=fx["data_dir"], lab_dir=fx["lab_dir"], log=lambda *a: None)
    assert s["written"] is False and "disagreements" in s["refused"]
    assert fx["out"].read_bytes() == before


def test_a_thinner_file_is_not_written(fx):
    T.export(out=fx["out"], data_dir=fx["data_dir"], lab_dir=fx["lab_dir"], log=lambda *a: None)
    before = fx["out"].read_bytes()
    (fx["lab_dir"] / f"panel_2022_v{lab.SCHEMA}.json").unlink()
    s = T.export(out=fx["out"], data_dir=fx["data_dir"], lab_dir=fx["lab_dir"], log=lambda *a: None)
    assert s["refused"] == "thinner than the last good file"
    assert fx["out"].read_bytes() == before


def test_the_flag_is_dark_and_writes_only_the_preview_directory():
    assert T.MLBSTATS_DRAWER_LIVE is False
    assert T.out_dir() == T.PREVIEW_DIR
    assert T.PREVIEW_DIR.relative_to(T.ROOT / ".cache") == Path("league_teams") / "preview"
    assert T.DATA_DIR not in T.PREVIEW_DIR.parents
    assert not (T.DATA_DIR / T.OUT_NAME).exists(), "mlbstats_trends.json shipped before the flip"


def test_the_served_lab_panels_agree_with_the_history_payloads():
    """The refusal's premise on this tree's own files: every player-season that a
    memoised lab panel and a history payload share carries one index."""
    if not any(T.LAB_DIR.glob(f"panel_*_v{lab.SCHEMA}.json")):
        pytest.skip("no memoised window lab panel on this machine")
    doc = T.build(log=lambda *a: None)
    assert doc["check"]["disagree"] == 0
    assert doc["check"]["shared"] > 1000
    assert doc["counts"]["players"] > 2000
