# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eTools amendment 4 (etools_stale.py): the carried-forward board, the stale eTool built on
fresh fits, the HOLDS rule and its comparators, and the served stale records. Fixtures only;
no real row is scored here."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import etools as E
import etools_stale as S

ROOT = Path(__file__).resolve().parent


# --- the carried-forward board ------------------------------------------------
def _snaps():
    return {
        ("fangraphs", "a"): [("2016-02-10", {"hit": 50.0}, "SS"), ("2017-08-01", {"hit": 55.0}, "SS")],
        ("mlb_pipeline", "a"): [("2016-01-22", {"hit": 45.0}, "SS")],
        ("fangraphs", "b"): [("2021-02-10", {"hit": 60.0}, "2B")],
        ("fangraphs", "c"): [("2018-02-10", {"hit": 40.0, "speed": 50.0}, "CF")],
    }


def test_latest_before_takes_the_latest_grade_per_tool_and_marks_reserved_years():
    lst = _snaps()[("fangraphs", "a")]
    assert S.latest_before(lst, "2019-01-01") == {"hit": (55.0, "2017-08-01")}
    assert S.latest_before(lst, "2017-01-01") == {"hit": (50.0, "2016-02-10")}
    assert S.latest_before(_snaps()[("fangraphs", "b")], "2023-01-01", skip_years=(2020, 2021)) == \
        {"hit": (None, "2021-02-10")}


def test_stale_board_skips_fresh_tools_and_drops_reserved_list_grades():
    fresh = {(2019, "fangraphs", "c"): {"tools": {"hit": 45.0}}}
    out, counts = S.stale_board(fresh, (2019, 2023), snaps=_snaps())
    # a: both outlets carried forward into 2019; the mean happens in tool_frames
    assert out[(2019, "fangraphs", "a")]["tools"] == {"hit": 55.0}
    assert out[(2019, "mlb_pipeline", "a")]["dates"] == {"hit": "2016-01-22"}
    # c: hit is fresh in 2019 (never carried), speed is stale
    assert out[(2019, "fangraphs", "c")]["tools"] == {"speed": 50.0}
    # b: the only grade is a 2021 list: dropped in 2023, never substituted
    assert (2023, "fangraphs", "b") not in out
    assert counts["tools_dropped_reserved_list_year"] == 1


def test_stale_board_live_reads_any_list_year_before_live_from():
    out, _ = S.stale_board({}, (0,), live=True, snaps=_snaps())
    assert out[(0, "fangraphs", "b")]["tools"] == {"hit": 60.0}


def test_grade_dates_take_the_latest_outlet_date_and_age_at_may_first():
    board = {(2019, "fangraphs", "a"): {"dates": {"hit": "2017-08-01"}},
             (2019, "mlb_pipeline", "a"): {"dates": {"hit": "2016-01-22"}}}
    rows = [{"year": 2019, "player_key": "a"}]
    S.attach_grade_dates(rows, board)
    assert rows[0]["grade_date"] == {"hit": "2017-08-01"}
    assert rows[0]["grade_age_days"]["hit"] == 638
    rows = [{"year": 0, "player_key": "a"}]
    S.attach_grade_dates(rows, {(0, "fangraphs", "a"): {"dates": {"hit": "2024-08-01"}}}, asof_live="2026-10-19")
    assert rows[0]["grade_age_days"]["hit"] == 809


def test_side_conflicts_drop_the_other_side():
    fresh = [{"year": 2019, "pid": 1, "side": "pit"}]
    stale = [{"year": 2019, "pid": 1, "side": "hit"}, {"year": 2019, "pid": 2, "side": "hit"}]
    assert [r["pid"] for r in S.side_conflicts(stale, fresh)] == [2]


# --- the stale eTool ------------------------------------------------------------
def test_stale_oof_on_copies_of_fresh_rows_is_the_served_out_of_fold_eTool():
    """Stale rows that are exact copies of each year's fresh rows get the same training
    exclusion and the same fresh re-centring as etool_oof_detail, so the same eTool."""
    ff, _sf, _ages = S.fixture(n_players=500)
    det = E.etool_oof_detail(ff, ["k_rw"])
    out = S.stale_oof(ff, ff, ["k_rw"])
    ok = np.isfinite(det["pred_rc"])
    assert ok.sum() > 100
    assert np.allclose(out["pred_rc"][ok], det["pred_rc"][ok])
    assert np.allclose(out["pred_unc"][ok], det["pred"][ok])


def test_stale_rows_are_centred_on_the_fresh_rows_not_on_themselves():
    ff, sf, _ = S.fixture(n_players=500)
    shifted = E.ToolFrame("hit", [])
    shifted.__dict__.update(sf.__dict__)
    shifted.cands = {"k_rw": sf.cands["k_rw"] - 3.0}             # every stale player far below
    out = S.stale_oof(ff, shifted, ["k_rw"])
    base = S.stale_oof(ff, sf, ["k_rw"])
    m = np.isfinite(out["pred_rc"]) & np.isfinite(sf.cands["k_rw"])
    # the stale shift is kept (a self-centring would erase it)
    assert np.nanmean(out["pred_rc"][m] - base["pred_rc"][m]) < -0.5


def _fixture_read(n_players=1400, Bn=200):
    ff, sf, ages = S.fixture(n_players=n_players)
    return S.tool_read(ff, sf, ages, ["k_rw"], Bn=Bn)


def test_tool_read_recovers_a_planted_gain_and_the_comparators_behave():
    rec = _fixture_read()
    assert rec["second_label"] == "mlb"
    assert rec["zero_comparator"] == {"mlb": 0.0, "um": 0.0}
    assert rec["S12"]["holds"] and rec["planted"]["holds"]
    assert not rec["null"]["holds"]
    assert rec["verdict"] == "HOLDS"


def test_second_label_falls_back_to_l_any_then_to_not_computable():
    ff, sf, ages = S.fixture(n_players=800)
    old = ages >= S.STALE_DAYS
    labels = {"mlb": np.full(sf.n, np.nan), "um": sf.y["um"], "any": sf.y["um"] + 0.1}
    assert S.second_label(sf, old, labels) == "any"
    assert S.second_label(sf, old, {"mlb": labels["mlb"], "um": sf.y["um"]}) is None
    assert S.second_label(sf, old, {"mlb": sf.y["mlb"], "um": np.full(sf.n, np.nan)}) is None


@pytest.mark.parametrize("rec,want", [
    ({"second_label": None, "null": {"holds": True}, "S12": {"holds": True}, "planted": {"holds": True}},
     "NOT COMPUTABLE"),
    ({"second_label": "mlb", "null": {"holds": True}, "S12": {"holds": True}, "planted": {"holds": True}}, "VOID"),
    ({"second_label": "mlb", "null": {"holds": False}, "S12": {"holds": True}, "planted": {"holds": False}},
     "HOLDS"),
    ({"second_label": "any", "null": {"holds": False}, "S12": {"holds": False}, "planted": {"holds": False}},
     "DOES NOT HOLD; UNDERPOWERED"),
    ({"second_label": "any", "null": {"holds": False}, "S12": {"holds": False}, "planted": {"holds": True}},
     "DOES NOT HOLD"),
])
def test_verdict_order(rec, want):
    assert S.verdict(rec) == want


def test_holds_needs_um_and_the_second_label():
    pos = {"computable": True, "lb95": 0.01}
    neg = {"computable": True, "lb95": -0.01}
    for um, sec, want in ((pos, pos, True), (pos, neg, False), (neg, pos, False)):
        out = {"um": um, "mlb": sec}
        assert bool(E._lb_pos(out["um"]) and E._lb_pos(out["mlb"])) is want


# --- guards ---------------------------------------------------------------------------
def test_run_refuses_without_a_registered_sha(monkeypatch, tmp_path):
    monkeypatch.setattr(S, "READS_PATH", tmp_path / "r.json")
    with pytest.raises(S.StaleGuard):
        S.run("0000000")


def test_run_refuses_when_spent(monkeypatch, tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"spent": True, "spent_at": "x"}), encoding="utf-8")
    monkeypatch.setattr(S, "READS_PATH", p)
    with pytest.raises(S.StaleGuard, match="spent"):
        S.run("dff62ea9")


def test_served_tools_reads_only_a_clean_spent_read(monkeypatch, tmp_path):
    p = tmp_path / "r.json"
    monkeypatch.setattr(S, "READS_PATH", p)
    assert S.served_tools() == set()
    p.write_text(json.dumps({"spent": True, "serve": {"hit": True, "fb": False}}), encoding="utf-8")
    assert S.served_tools() == {"hit"}
    p.write_text(json.dumps({"spent": True, "error": "x", "serve": {"hit": True}}), encoding="utf-8")
    assert S.served_tools() == set()


# --- serving ---------------------------------------------------------------------------
def _live_rows():
    return [{"player_key": "old_hitter", "pid": 9, "name": "Old Hitter", "side": "hit",
             "per_source": {"fangraphs": {"hit": 70.0}}, "cands": {"k_rw": 0.5, "babip_rw": None},
             "grade_date": {"hit": "2024-08-01"}, "grade_age_days": {"hit": 809}},
            {"player_key": "fresh_one", "pid": 7, "name": "Fresh", "side": "hit",
             "per_source": {"fangraphs": {"hit": 40.0}}, "cands": {"k_rw": 0.1, "babip_rw": 0.2},
             "grade_date": {"hit": "2025-02-01"}, "grade_age_days": {"hit": 625}}]


def _fits():
    return {"hit": {"admitted": ["k_rw", "babip_rw"], "lines": [(0.0, 0.0, True), (0.0, 0.0, True)],
                    "c": [10.0, 4.0], "delta": np.array([0.1, 0.0]), "sigma": 5.0}}


def test_extend_preview_adds_stale_records_and_never_touches_a_fresh_tool():
    players = {"fresh_one": {"name": "Fresh", "mlbam": 7, "side": "hit",
                             "tools": {"eHIT": {"etool": 41.0, "basis": "etool"}}}}
    info = S.extend_preview(players, _fits(), rows=_live_rows(), tools={"hit"}, log=lambda *_a: None)
    assert players["fresh_one"]["tools"]["eHIT"] == {"etool": 41.0, "basis": "etool"}
    rec = players["old_hitter"]["tools"]["eHIT"]
    # 70 + 10 x (0.5 - 0.1); babip missing contributes nothing
    assert rec["etool"] == 74.0 and rec["etool_display"] == 74
    assert rec["grade_date"] == "2024-08-01" and rec["grade_age_months"] == 26.6
    assert rec["stale"] and rec["construction"] == "recentred" and rec["consensus"] == 70.0
    assert [d["key"] for d in rec["drivers"]] == ["k_rw"]
    assert info["records"] == 1 and info["players_added"] == 1


def test_extend_preview_serves_nothing_for_a_tool_that_does_not_hold():
    players = {}
    info = S.extend_preview(players, _fits(), rows=_live_rows(), tools=set(), log=lambda *_a: None)
    assert players == {} and info["records"] == 0


def test_served_doc_carries_the_grade_date_only_for_stale_records():
    doc = {"keys": {t: E.TOOLS[t]["key"] for t in E.TOOLS}, "tools": {},
           "stale_graded": {"tools": ["hit"]},
           "players": {"old_hitter": {"mlbam": 9, "side": "hit", "tools": {"eHIT": {
               "etool": 74.0, "etool_display": 74, "consensus": 70.0, "band80": [67.6, 80.0], "drivers": [],
               "basis": "etool", "grade_date": "2024-08-01", "grade_age_months": 26.6}}},
               "fresh_one": {"mlbam": 7, "side": "hit", "tools": {"eHIT": {
                   "etool": 41.0, "etool_display": 41, "consensus": 40.0, "band80": [], "drivers": [],
                   "basis": "etool"}}}}}
    out = E.served_doc(doc)
    assert out["players"]["old_hitter"]["tools"]["hit"]["grade_date"] == "2024-08-01"
    assert "grade_date" not in out["players"]["fresh_one"]["tools"]["hit"]
    assert out["stale_tools"] == ["hit"]


def test_card_tooltip_names_the_scouting_grade_date():
    body = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert "scouting grade from ${_ETOOL_MONTHS[" in body
    i = body.index("function toolGradeTip(")
    assert "_eToolGradeDate(r)" in body[i:i + 3000]
    j = body.index("function eToolsBlockHTML(")
    assert "_eToolGradeDate(r)" in body[j:j + 2000]


def test_month_label():
    assert S.month_label("2024-08-01") == "Aug 2024"
