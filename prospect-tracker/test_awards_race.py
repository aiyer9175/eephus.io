# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Awards race strip's data (AWARDS_5_RACE; AWARDS_PLAN 4.6 'The race', 6 'Invariants
and tests' row I5).

I5 on test_fixtures/awards/race/trimmed.json.gz (built by its _build_fixture.py from the
play corpus and the boards): for 2026 and for the history boards 2021 to 2025, the last
point of a batter, a starter and a reliever equals the board's season wpa (exact for the
batter and the starter, 0.01 for the reliever). Then, on synthetic plays: places are a
permutation of 1 to 3 every week, a doubleheader day holds two games and each is counted
once, Manager's games over .500 come from each game's final score, the feed's officialDate
wins over the first-play date; the 2027 path: a vintage's first write of a date wins,
the rule_place block (places among the whole pool, null outside the top 3, missing weeks),
the flag's vintage folder, and the exporter copying a tracked race file byte for byte.
Last, the tracked data/_labs/awards/race_<S>.json files themselves. No test touches the
network: an autouse fixture refuses every socket.
"""
from __future__ import annotations

import gzip
import json
import shutil
import socket
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import awards_core as A  # noqa: E402
import awards_export as E  # noqa: E402
import awards_race as R  # noqa: E402

FIX = ROOT / "test_fixtures" / "awards" / "race" / "trimmed.json.gz"
EXPORT_FIX = ROOT / "test_fixtures" / "awards" / "export"
PROV = "ewar_v2"
KEYS = [f"{a}_{lg}" for a in A.AWARDS for lg in A.LEAGUES]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("an awards_race test opened a socket")
    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


@pytest.fixture(scope="module")
def trimmed():
    return json.loads(gzip.decompress(FIX.read_bytes()).decode("utf-8"))


def decode(enc: dict):
    """The fixture's compact plays (its _build_fixture.encode) as corpus columns."""
    pks = [pk for pk, n in enc["game_pk"] for _ in range(n)]
    ids = enc["ids"]
    n = len(pks)
    return R.plays_from_columns({
        "game_pk": pks, "half": ["bottom" if h == "b" else "top" for h in enc["half"]],
        "inning": enc["inning"], "at_bat_index": enc["at_bat_index"],
        "batter_id": [ids[int(c)] for c in enc["batter"]],
        "pitcher_id": [ids[int(c)] for c in enc["pitcher"]],
        "wpa_home": [w / 10.0 for w in enc["wpa_tenths"]],
        "home_score": [0] * n, "away_score": [0] * n})


def _meta(dates: dict) -> dict:
    return {int(pk): {"date": d, "type": "R", "home": None, "away": None, "source": "fixture"}
            for pk, d in dates.items()}


# --- I5: the last point against the boards --------------------------------------------------

@pytest.mark.parametrize("season", [2021, 2022, 2023, 2024, 2025, 2026])
def test_i5_last_point_equals_the_boards_season_wpa(trimmed, season):
    blk = trimmed["seasons"][str(season)]
    folded = R.fold(decode(blk["plays"]))
    meta = _meta(blk["dates"])
    weeks = R.week_ends(m["date"] for m in meta.values())
    board = blk["board"]
    checks = (("MVP", blk["batter"], board["bat"], 0.0),
              ("CY", blk["starter"], board["start"], 0.0),
              ("CY", blk["reliever"], board["relief"], R.RELIEVER_TOL))
    for award, mid, rows, tol in checks:
        fin = [{"id": str(mid), "name": "x", "rule_place": 1},
               {"id": "1", "name": "y", "rule_place": 2},
               {"id": "2", "name": "z", "rule_place": 3}]
        race = R.build_block(award, fin, folded, meta, weeks, season, {"fixture": 1})
        last = race["values"][str(mid)][-1]
        want = rows[str(mid)]
        if tol == 0.0:
            assert last == want, (season, award, mid, last, want)
        else:
            assert abs(last - want) <= tol + 1e-9, (season, award, mid, last, want)


def test_i5_reconcile_player_names_a_part_with_no_board_row(trimmed):
    blk = trimmed["seasons"]["2026"]
    folded = R.fold(decode(blk["plays"]))
    board = {k: {int(m): v for m, v in rows.items()} for k, rows in blk["board"].items()}
    assert R.reconcile_player("MVP", blk["batter"], folded, board)["status"] == "exact"
    assert R.reconcile_player("CY", blk["starter"], folded, board)["status"] == "exact"
    assert R.reconcile_player("CY", blk["reliever"], folded, board)["status"] in ("exact", "within_0.01")
    gone = dict(board, start={})
    assert R.reconcile_player("CY", blk["starter"], folded, gone)["status"] == "part_off_board"
    off = dict(board, bat={blk["batter"]: board["bat"][blk["batter"]] + 0.001})
    assert R.reconcile_player("MVP", blk["batter"], folded, off)["status"] == "miss"


# --- synthetic plays ---------------------------------------------------------------------------

def _plays(rows):
    cols = {c: [] for c in R.PLAY_COLS}
    for r in rows:
        for c in R.PLAY_COLS:
            cols[c].append(r[c])
    return R.plays_from_columns(cols)


def _play(pk, ab, half, inning, batter, pitcher, wpa_home, hs=0, as_=0):
    return {"game_pk": pk, "half": half, "inning": inning, "at_bat_index": ab,
            "batter_id": batter, "pitcher_id": pitcher, "wpa_home": wpa_home,
            "home_score": hs, "away_score": as_}


def test_signs_batter_by_half_and_pitcher_the_negative():
    p = _plays([_play(1, 0, "top", 1, 10, 20, 2.5), _play(1, 1, "bottom", 1, 11, 21, 3.0),
                _play(1, 2, "bottom", 2, 11, 22, -1.2)])
    f = R.fold(p)
    assert f["bat"][10] == {1: -25} and f["bat"][11] == {1: 18}
    assert f["start"][20] == {1: 25} and f["start"][21] == {1: -30}
    assert f["relief"][22] == {1: 12}


def test_a_doubleheader_day_counts_each_game_once():
    p = _plays([_play(1, 0, "bottom", 1, 10, 20, 4.0, 1, 0), _play(1, 1, "top", 9, 30, 20, -1.0, 1, 0),
                _play(2, 0, "bottom", 1, 10, 21, 2.0, 0, 3), _play(2, 1, "top", 9, 31, 21, 0.5, 0, 3),
                _play(3, 0, "bottom", 1, 10, 22, 1.0, 2, 1)])
    f = R.fold(p)
    meta = _meta({1: "2026-05-02", 2: "2026-05-02", 3: "2026-05-05"})
    weeks = R.week_ends(m["date"] for m in meta.values())
    assert weeks == ["2026-05-02", "2026-05-05"]
    assert f["bat"][10] == {1: 40, 2: 20, 3: 10}
    assert R.cumulative(f["bat"][10], meta, weeks) == [60, 70]
    fin = [{"id": "10", "name": "a", "rule_place": 1}, {"id": "30", "name": "b", "rule_place": 2},
           {"id": "31", "name": "c", "rule_place": 3}]
    blk = R.build_block("MVP", fin, f, meta, weeks, 2026, {"fixture": 1})
    assert blk["values"]["10"] == [0.06, 0.07]
    assert blk["weeks"] == weeks and blk["record_starts"] == "2026-05-02" and blk["missing"] == []


def test_places_are_a_permutation_every_week_and_ties_go_to_the_rule_place():
    series = {"a": [0, 5, 5, -1], "b": [0, 7, 5, 3], "c": [1, 1, 5, 3]}
    places = R.places_of(["a", "b", "c"], series)
    assert places == {"a": [2, 2, 1, 3], "b": [3, 1, 2, 1], "c": [1, 3, 3, 2]}
    for k in range(4):
        assert sorted(places[i][k] for i in places) == [1, 2, 3]


def test_manager_orders_clubs_by_games_over_500_from_the_finals():
    p = _plays([_play(1, 0, "bottom", 9, 10, 20, 0.0, 5, 3), _play(2, 0, "bottom", 9, 10, 20, 0.0, 1, 4),
                _play(3, 0, "bottom", 9, 10, 20, 0.0, 2, 1), _play(3, -1, "top", 1, 11, 21, 0.0, 0, 0)])
    f = R.fold(p)
    assert f["final"] == {1: (5, 3), 2: (1, 4), 3: (2, 1)}
    meta = {1: {"date": "2026-04-01", "home": "NYY", "away": "BOS"},
            2: {"date": "2026-04-02", "home": "BOS", "away": "NYY"},
            3: {"date": "2026-04-08", "home": "TBR", "away": "NYY"}}
    weeks = R.week_ends(m["date"] for m in meta.values())
    assert R.club_cumulative("NYY", f["final"], meta, weeks) == ([2, 1], 2, 1)
    assert R.club_cumulative("BOS", f["final"], meta, weeks) == ([-2, -2], 0, 2)


def test_the_feed_officialdate_wins_and_the_first_play_date_is_the_fallback(tmp_path):
    feeds = tmp_path / "feeds"
    feeds.mkdir()
    (feeds / "5.json").write_text(json.dumps({"gameData": {
        "datetime": {"officialDate": "2026-06-01"}, "game": {"type": "R"},
        "teams": {"home": {"id": 147}, "away": {"id": 111}}},
        "liveData": {"linescore": {"teams": {"home": {"runs": 4}, "away": {"runs": 2}}}}}),
        encoding="utf-8")
    dates = tmp_path / "dates.json"
    dates.write_text(json.dumps({"5": "2026-06-02", "6": "2026-06-03"}), encoding="utf-8")
    meta = R.game_meta([5, 6], feeds_dir=feeds, dates_path=dates, abbrev={147: "NYY", 111: "BOS"},
                       team_map={6: {"home": "TBR", "away": "NYY"}})
    assert meta[5]["date"] == "2026-06-01" and meta[5]["source"] == "feed"
    assert (meta[5]["home"], meta[5]["away"], meta[5]["home_runs"]) == ("NYY", "BOS", 4)
    assert meta[6]["date"] == "2026-06-03" and meta[6]["source"] == "first_play_date"
    assert meta[6]["home"] == "TBR"


# --- the 2027 path: vintages and rule_place -------------------------------------------------

def _vint(date, through, top, season=2027):
    return {"schema": 1, "produced_by": "awards_export.py", "season": season, "date": date,
            "through": through, "war_provider": PROV, "generated_at": date + "T08:00:00+00:00",
            "top": top}


def _rows(*ids):
    return [{"id": i, "name": i, "rank": n, "score": 10.0 - n} for n, i in enumerate(ids, start=1)]


def test_the_first_write_of_a_date_wins(tmp_path):
    a = _vint("2027-04-05", "2027-04-04", {"MVP_AL": _rows("1", "2", "3")})
    b = _vint("2027-04-05", "2027-04-05", {"MVP_AL": _rows("9", "8", "7")})
    assert E.write_vintage(tmp_path, a) is True
    raw = (tmp_path / "2027-04-05.json").read_bytes()
    assert E.write_vintage(tmp_path, b) is False
    assert (tmp_path / "2027-04-05.json").read_bytes() == raw
    got = E.load_vintages(tmp_path, 2027, pending=b)
    assert len(got) == 1 and got[0]["top"]["MVP_AL"][0]["id"] == "1"
    c = _vint("2027-04-06", "2027-04-05", {"MVP_AL": _rows("4", "5", "6")})
    assert [v["date"] for v in E.load_vintages(tmp_path, 2027, pending=c)] == ["2027-04-05", "2027-04-06"]
    assert E.load_vintages(tmp_path, 2028) == []


def test_rule_place_places_among_the_pool_with_missing_weeks():
    v = [_vint("2027-03-30", "2027-03-29", {"MVP_AL": _rows("1", "2", "3", "4", "5")}),
         _vint("2027-04-03", "2027-04-02", {"MVP_AL": _rows("4", "1", "2", "3")}),
         _vint("2027-04-04", "2027-04-04", {"MVP_AL": _rows("2", "1", "5", "4", "3")}),
         _vint("2027-04-18", "2027-04-17", {"MVP_AL": _rows("1", "4", "2")})]
    out = E.rule_place_race(v)
    b = out["MVP_AL"]
    assert b["mode"] == "rule_place" and b["registry"] == A.SELECTION_REGISTRY
    assert b["weeks"] == ["2027-04-04", "2027-04-11", "2027-04-17"]
    assert b["missing"] == ["2027-04-11"] and b["record_starts"] == "2027-03-29"
    assert [f["id"] for f in b["finalists"]] == ["1", "4", "2"]
    assert b["places"] == {"1": [2, None, 1], "4": [None, None, 2], "2": [1, None, 3]}
    assert b["values"]["4"] == [6.0, None, 8.0]
    assert not A.verdict_hits(b["metric_label"]) and not A.verdict_hits(b["producer"])


def test_vintages_live_under_the_preview_while_the_flag_is_false(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "AWARDS_LIVE", False)
    assert E.vintage_dir(tmp_path / ".cache", tmp_path / "pv") == tmp_path / "pv" / "awards_vintages"
    assert E.vintage_dir(tmp_path / ".cache") == tmp_path / ".cache" / "awards" / "preview" / "awards_vintages"
    assert E.vintage_dir() == E.PREVIEW / "awards_vintages"
    monkeypatch.setattr(A, "AWARDS_LIVE", True)
    assert E.vintage_dir(tmp_path / ".cache", tmp_path / "pv") == tmp_path / ".cache" / "awards_vintages"
    assert E.vintage_dir() == E.VINTAGES == E.CACHE / "awards_vintages"


def test_the_race_block_from_2027_reads_the_vintages_and_tonights_record(tmp_path):
    E.write_vintage(tmp_path, _vint("2027-04-01", "2027-03-31", {"CY_NL": _rows("7", "8", "9")}))
    inp = types.SimpleNamespace(labs_json=lambda name, required=False: None)
    ctx = types.SimpleNamespace(inp=inp, vintage_dir=tmp_path,
                                pending_vintage=_vint("2027-04-09", "2027-04-08",
                                                      {"CY_NL": _rows("8", "7", "9")}))
    race = E._race(ctx, 2027)
    assert set(race) == set(KEYS)
    assert race["CY_NL"]["places"] == {"8": [2, 1], "7": [1, 2], "9": [3, 3]}
    assert race["MVP_AL"] is None
    assert not (tmp_path / "2027-04-09.json").exists()
    assert E._race(types.SimpleNamespace(inp=inp, vintage_dir=tmp_path, pending_vintage=None), 2026) == \
        {k: None for k in KEYS}


def test_vintage_record_holds_the_top_ten_per_award_and_league():
    full = {("MVP", "AL"): {"top": [{"mlbam": 100 + i, "name": f"p{i}", "rank": i + 1, "score": 9.0 - i}
                                    for i in range(14)]},
            ("MOY", "NL"): {"top": [{"club": "CIN", "rank": 1, "score": 3.0}]}}
    rec = E.vintage_record({"season": 2027, "through": "2027-05-01", "full": full},
                           date="2027-05-02", war_provider=PROV, generated_at="g")
    assert list(rec["top"]) == ["MVP_AL", "MOY_NL"]
    assert len(rec["top"]["MVP_AL"]) == E.VINTAGE_TOP == 10
    assert rec["top"]["MVP_AL"][0] == {"id": "100", "name": "p0", "rank": 1, "score": 9.0}
    assert rec["top"]["MOY_NL"][0]["id"] == "ccin"
    assert (rec["season"], rec["date"], rec["through"], rec["war_provider"]) == (2027, "2027-05-02", "2027-05-01", PROV)


# --- the exporter copies the tracked file --------------------------------------------------

def test_the_exporter_copies_the_race_file_byte_for_byte_and_writes_no_vintage_before_2027(tmp_path, monkeypatch):
    # the fixture tree is on PROV; pin the displayed provider to it (since the eWAR v3
    # flip the live display provider is ewar_v3, EBR_GATE.md 11.10.5)
    monkeypatch.setattr(E, "_display_provider", lambda: PROV)
    for sub in ("data", "cache", "labs", "model"):
        shutil.copytree(EXPORT_FIX / sub, tmp_path / sub)
    stints = json.loads((EXPORT_FIX / "stints.json").read_text(encoding="utf-8"))
    weeks = ["2026-03-29", "2026-04-05"]
    race = {"schema": 1, "season": 2026, "mode": "wpa_order", "reconciliation": None}
    for k in KEYS:
        race[k] = {"mode": "wpa_order", "metric_label": R.METRIC_LABEL, "producer": "fixture",
                   "registry": "leverage_board", "weeks": weeks, "record_starts": "2026-03-26",
                   "missing": [], "finalists": [], "places": {"1": [1, 2]}, "values": {"1": [0.123, 0.456]}}
    race["MOY_NL"] = None
    (tmp_path / "labs" / "race_2026.json").write_bytes(R.dumps(race))
    E.reset_frames()
    E.inject_frames(stints, PROV)
    try:
        res = E.export(out_dir=tmp_path / "out", data_dir=tmp_path / "data", cache_dir=tmp_path / "cache",
                       labs_dir=tmp_path / "labs", preview_dir=tmp_path / "preview",
                       model_dir=tmp_path / "model", log=lambda *_a, **_k: None)
    finally:
        E.reset_frames()
    assert res["ok"], res
    assert res["vintage"] is None
    assert not (tmp_path / "preview" / "awards_vintages").exists()
    assert not (tmp_path / "cache" / "awards_vintages").exists()
    doc = json.loads((Path(res["out_dir"]) / "awards.json").read_text(encoding="utf-8"))
    for k in KEYS:
        assert json.dumps(doc["race"][k], sort_keys=True) == json.dumps(race[k], sort_keys=True), k
    assert doc["seasons"][0]["race"] is True


# --- the tracked files -----------------------------------------------------------------------

@pytest.mark.parametrize("season", R.SEASONS)
def test_the_tracked_race_file(season):
    path = R.LABS / f"race_{season}.json"
    if not path.exists():
        pytest.skip(f"race_{season}.json is not on file")
    raw = path.read_bytes()
    assert len(raw) < 80_000
    doc = json.loads(raw.decode("utf-8"))
    assert doc["season"] == season and doc["mode"] == "wpa_order" and doc["war_provider"]
    assert not A.verdict_hits({k: doc[k] for k in KEYS})
    for k in KEYS:
        b = doc[k]
        assert b["mode"] == "wpa_order"
        assert b["metric_label"] == (R.METRIC_LABEL_CLUB if k.startswith("MOY") else R.METRIC_LABEL)
        assert b["registry"] == (None if k.startswith("MOY") else R.REGISTRY) and b["producer"]
        n = len(b["weeks"])
        assert n >= 20 and b["weeks"] == sorted(b["weeks"]) and b["missing"] == []
        assert b["record_starts"] <= b["weeks"][0]
        ids = [f["id"] for f in b["finalists"]]
        assert [f["rule_place"] for f in b["finalists"]] == [1, 2, 3]
        assert list(b["places"]) == ids and list(b["values"]) == ids
        for i in ids:
            assert len(b["places"][i]) == n and len(b["values"][i]) == n
        for w in range(n):
            assert sorted(b["places"][i][w] for i in ids) == [1, 2, 3], (k, w)
            ranked = sorted(ids, key=lambda i: (-b["values"][i][w], ids.index(i)))
            assert [b["places"][i][w] for i in ranked] == [1, 2, 3], (k, w)
    rec = doc["reconciliation"]
    if season >= R.BOARD_FIRST:
        assert rec["finalists"]["counts"]["miss"] == 0
        for part, c in rec["boards"].items():
            assert c["rows"] > 0 and c["agree"] == c["rows"], (part, c)
    assert rec["clubs"]["agree"] == rec["clubs"]["checked"] == 6
