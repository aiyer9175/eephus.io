# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PV-07 / PV-08: the PROSPX section "Not yet graded by any source" and its receipts.

Owner answers 2026-09-25 (DECISIONS_FOR_OWNER.md, PG-Q1 to PG-Q3; spec
_finalpass_2026-09-24/provisional/PROVISIONAL_V2.md sections 3 and 5):
  PG-Q1  the provisional-only rows leave the shared eFV rank for their own section,
         ordered by the recalibrated chance of a first grade by W12 (provisional_v2
         p_any_w12), and rejoin the rank only on a frozen level win;
  PG-Q2  the board actives no label source has ever graded move to the same section;
         trade values and farm points keep their inputs;
  PG-Q3  the card shows the expected first grade on the FanGraphs scale and the chance
         of a first grade by the next list window, and keeps the map value as a
         secondary "production grade".

Pinned here:
  1. storage: one label-source set (equal to the scorer's), the membership predicate,
     the re-bake that clears section rows' ranks and ranks the rest 1..N, the served
     `prov_section` block, the fingerprint term, and the rejoin guard (the switch may
     not be turned off while no frozen window shows a level win).
  2. prospx (V8): every graded row sorts before every section row, the section orders
     by the W12 chance with uncovered rows last, a section row has no board rank, and
     the receipt text reads the artifact.
  3. the served files, where built: the baked ranks follow the section rule.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

import provisional_track
import storage

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"
DATA = ROOT / "data"


# ---------------------------------------------------------------------------
# 1. storage
# ---------------------------------------------------------------------------

def test_label_sources_are_the_scorers_any_set():
    assert tuple(storage.PROV_SECTION_LABEL_SOURCES) == tuple(provisional_track.SETS["ANY"])


def test_label_opinion_reads_per_source_and_contributors():
    yes = [{"per_source": {"performance_ingest": {}}},
           {"sources_contributing": ["tjstats", "mlb_pipeline"]}]
    assert storage.has_label_source_opinion(yes) is True
    for anchor in ("performance_ingest", "draft_signing", "tjstats"):
        assert storage.has_label_source_opinion(
            [{"per_source": {anchor: {}}, "sources_contributing": [anchor]}]) is False, anchor
    assert storage.has_label_source_opinion([]) is False

    class _Pt:
        per_source = {"espn": {}}
        sources_contributing = []
    assert storage.has_label_source_opinion([_Pt()]) is True


def test_membership_reads_the_flag_then_the_points_then_stays_ranked():
    assert storage.row_in_prov_section({"source_graded": False}) is True
    assert storage.row_in_prov_section({"source_graded": True}) is False
    assert storage.row_in_prov_section(
        {"points": [{"per_source": {"performance_ingest": {}}}]}) is True
    assert storage.row_in_prov_section(
        {"points": [{"per_source": {"fangraphs": {}}}]}) is False
    # a row with neither flag nor points (a synthetic or pre-flag payload) stays ranked
    assert storage.row_in_prov_section({"player_key": "x"}) is False


def _payload():
    def row(pk, org, rank, tail, src):
        return {"player_key": pk, "player_name": pk, "org": org, "status": "active",
                "overall_rank": rank, "org_rank": rank, "org_rank_total": 3,
                "prev_overall_rank": None, "rank_movement": None, "board_key_tail": tail,
                "points": [{"per_source": {src: {}}, "sources_contributing": [src]}]}
    return {"players": [
        row("graded_a", "LAD", 1, [50.0, 0, 0.5, 1.0, "LAD"], "fangraphs"),
        # a routed performance-anchor row the old board ranked between the graded two
        row("routed", "LAD", 2, [35.0, 0, 0.4, 999.0, "LAD"], "performance_ingest"),
        row("graded_b", "LAD", 3, [40.0, 0, 0.3, 5.0, "LAD"], "baseballamerica"),
    ]}


def test_rebake_clears_section_ranks_and_ranks_the_rest(tmp_path, monkeypatch):
    p = tmp_path / "timeseries.json"
    p.write_text(json.dumps(_payload()), encoding="utf-8")
    xfv = {"graded_a": {"xfv_grade": 50.0}, "routed": {"xfv_grade": 45.0},
           "graded_b": {"xfv_grade": 40.0}}
    track = tmp_path / "track.json"
    track.write_text(json.dumps({"latest": {}, "rows": []}), encoding="utf-8")
    monkeypatch.setattr(storage, "prov_section_state",
                        lambda path=None, _f=storage.prov_section_state: _f(track))
    out = storage.rebake_board_ranks(p, xfv_by_key=xfv, rank_history={},
                                     update_metric_snapshots=False)
    assert out["n_active"] == 2 and out["n_section"] == 1
    doc = json.loads(p.read_text(encoding="utf-8"))
    by = {r["player_key"]: r for r in doc["players"]}
    assert (by["graded_a"]["overall_rank"], by["graded_b"]["overall_rank"]) == (1, 2)
    assert by["routed"]["overall_rank"] is None and by["routed"]["org_rank"] is None
    assert by["routed"]["source_graded"] is False and by["graded_b"]["source_graded"] is True
    assert by["graded_b"]["org_rank"] == 2 and by["graded_b"]["org_rank_total"] == 2
    assert by["routed"]["org_rank_total"] == 2
    ps = doc["prov_section"]
    assert ps["on"] is True and ps["n_board_rows"] == 1 and ps["level_win"] is False
    # a second pass on the re-baked file moves nothing
    again = storage.rebake_board_ranks(p, xfv_by_key=xfv, rank_history={}, write=False,
                                       update_metric_snapshots=False)
    assert again["n_moved"] == 0


def _track(tmp_path, rows):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"latest": {f"{r['leg']}|f|{r['window']}": r["run_id"] for r in rows},
                             "rows": rows}), encoding="utf-8")
    return p


def test_section_state_reads_the_track_record(tmp_path):
    open_row = {"run_id": "a", "leg": "prospective", "window": "W6", "window_end": "2027-04-15",
                "verdict_readable": False, "claims": None}
    s = storage.prov_section_state(_track(tmp_path, [open_row]))
    assert s["level_win"] is False and s["next_window_end"] == "2027-04-15"
    assert s["windows_closed"] == []
    win = {"run_id": "b", "leg": "prospective", "window": "W12", "window_end": "2027-10-15",
           "verdict_readable": True,
           "claims": {"level": {"fv_fg_pred": {"claim": True}, "grade": {"claim": False}}}}
    assert storage.prov_section_state(_track(tmp_path, [open_row, win]))["level_win"] is True
    # the incumbent grade winning is not the rule's win, and a spent leg never counts
    lose = dict(win, claims={"level": {"grade": {"claim": True}}})
    spent = dict(win, run_id="c", leg="served_backdated")
    assert storage.prov_section_state(_track(tmp_path, [lose]))["level_win"] is False
    assert storage.prov_section_state(_track(tmp_path, [spent]))["level_win"] is False


def test_the_section_stays_until_a_frozen_level_win():
    """PG-Q1: rows rejoin the shared rank ONLY on a frozen level win. Turning the switch
    off is a reviewed change, and this refuses it while the served track record shows no
    such win."""
    assert storage.PROV_SECTION_ON or storage.prov_section_state()["level_win"], (
        "PROV_SECTION_ON was turned off but data/provisional_track_eval.json shows no closed "
        "prospective window with a level win on the frozen expected first grade")


def test_the_fingerprint_names_the_ranked_pool(monkeypatch):
    fp = storage.board_basis_fingerprint()
    assert fp.endswith("|section=label_graded"), fp
    assert fp == storage.BOARD_BASIS_FINGERPRINT
    monkeypatch.setattr(storage, "PROV_SECTION_ON", False)
    assert storage.board_basis_fingerprint().endswith("|section=all")
    assert storage.BOARD_RANK_BASIS_EPOCH >= "2026-10-02"


# ---------------------------------------------------------------------------
# 2. prospx in V8
# ---------------------------------------------------------------------------

def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


_FUNCS = ("provSectionInfo", "provSectionOn", "inProvSection", "provV2Of", "_provNum",
          "_provDate", "provWindowEnd", "_provPct", "provChance", "provExpectedFirst",
          "provSectionCmp", "efvBoardValue", "efvRankValue", "boardCmp", "provReceipt")


@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    src = _src()
    ctx = mr.MiniRacer()
    ctx.eval("var DATA = {prov_section: {on: true}}; var _PROV_V2 = null; var _PROV_TRACK = null;"
             " function getEfv(p) { return p ? (p._x || null) : null; }"
             " function fvCmpDesc(a, b) { return String(a.player_key).localeCompare(String(b.player_key)); }")
    for name in _FUNCS:
        ctx.eval(_function_source(src, name))
    return ctx


_V2 = """_PROV_V2 = {anchor: {W6_end: "2027-04-15", W12_end: "2027-10-15"}, by: {
  "1": {p_any_w12: 0.40, p_any_w6: 0.20, fv_first_fg: 39.6},
  "2": {p_any_w12: 0.90, p_any_w6: 0.004, fv_first_fg: 41.4},
  "3": {p_any_w12: 0.05, p_any_w6: 0.01, fv_first_fg: 35.2}}};"""

_ROWS = """[
  {player_key: "sec_mid", mlbam_id: 1, _is_provisional: true, _x: {xfv_grade: 44}},
  {player_key: "g_low", mlbam_id: 9, source_graded: true, _x: {xfv_grade: 31}},
  {player_key: "sec_none", mlbam_id: 7, source_graded: false, _x: {xfv_grade: 47}},
  {player_key: "sec_top", mlbam_id: 2, source_graded: false, _x: {xfv_grade: 30}},
  {player_key: "g_high", mlbam_id: 8, _x: {xfv_grade: 55}},
  {player_key: "sec_low", mlbam_id: 3, _is_provisional: true, _x: {xfv_grade: 46}},
  {player_key: "grad", mlbam_id: 6, source_graded: false, status: "debuted", _x: {xfv_grade: 40}}
]"""


def _order(js, on=True):
    js.eval(_V2 + "DATA.prov_section = {on: %s};" % ("true" if on else "false"))
    return json.loads(js.eval("JSON.stringify(%s.sort(boardCmp).map(p => p.player_key))" % _ROWS))


def test_graded_rows_sort_first_and_the_section_orders_by_the_w12_chance(js):
    assert _order(js) == ["g_high", "grad", "g_low",         # graded (and the graduate) by grade
                          "sec_top", "sec_mid", "sec_low",   # section: W12 chance 0.90 > 0.40 > 0.05
                          "sec_none"]                        # outside the model, last
    # off (an older payload with no block): the old interleave by board grade
    assert _order(js, on=False)[:3] == ["g_high", "sec_none", "sec_low"]


def test_card_numbers_read_the_model_and_round_like_ef_v(js):
    js.eval(_V2 + "DATA.prov_section = {on: true};")
    assert js.eval("provExpectedFirst({mlbam_id: 1})") == 40
    assert js.eval("provExpectedFirst({mlbam_id: 2})") == 41
    assert js.eval("provExpectedFirst({mlbam_id: 7})") is None
    assert json.loads(js.eval("JSON.stringify(provChance({mlbam_id: 1}, 'W6'))")) == {
        "p": 0.2, "txt": "20%", "end": "2027-04-15", "endLabel": "Apr 15, 2027"}
    assert js.eval("provChance({mlbam_id: 2}, 'W6').txt") == "<1%"
    assert js.eval("_provDate('2027-10-15')") == "Oct 15, 2027"
    assert js.eval("inProvSection({player_key: 'x', source_graded: true})") is False
    assert js.eval("inProvSection({player_key: 'x', _is_provisional: true, debut_date: '2026-09-01'})") is False


def test_the_receipt_reads_the_artifact_rows(js):
    js.eval("""_PROV_TRACK = {columns: ["grade","first_date","first_source","first_fv","first_label","lead_days","player_key"],
      source_names: {fangraphs: "FanGraphs"},
      freezes: {"FREEZE_provisional_2026-09-25.json": {frozen_at: "2026-09-25",
        windows: {W6: "2027-04-15", W12: "2027-10-15"}, scored_through: "2026-10-02",
        rows: {"ann": [37.2, null, null, null, null, null, null],
               "mlbam_5": [33.0, "2027-02-12", "fangraphs", 40, "40", 140, "bob"]}}}};""")
    ann = json.loads(js.eval("JSON.stringify(provReceipt({player_key: 'ann'}))"))
    assert ann["grade"] == 37.2 and ann["first_date"] is None and ann["open_until"] == "2027-04-15"
    bob = json.loads(js.eval("JSON.stringify(provReceipt({player_key: 'bob', mlbam_id: 5}))"))
    assert (bob["first_date"], bob["source"], bob["label"], bob["lead"]) == (
        "2027-02-12", "FanGraphs", "40", 140)
    assert js.eval("provReceipt({player_key: 'nobody'})") is None


def test_section_rows_never_print_a_board_rank():
    src = _src()
    fn = _function_source(src, "boardRankOf")
    assert "if (inProvSection(p)) return null;" in fn
    fn = _function_source(src, "efvRankNumHTML")
    assert fn.index("if (inProvSection(p)) return provRankCellHTML(p);") < fn.index("getEfvRank")
    fn = _function_source(src, "buildEfvRankMap")
    assert "pool = pool.filter(p => !inProvSection(p));" in fn
    fn = _function_source(src, "buildEfvOrgRankMap")
    assert "filter(p => !inProvSection(p))" in fn


def test_the_card_keeps_the_production_grade_secondary():
    """PG-Q3: expected first grade leads; the map value stays, relabelled."""
    src = _src()
    head = _function_source(src, "provDetailHeaderHTML")
    assert "Expected first grade · FanGraphs scale" in head
    assert head.index("badge + chance + prod") > 0
    assert "production grade" in _function_source(src, "provProductionGrade")
    card = _function_source(src, "efvDetailCard")
    assert "Production grade · provisional map, ranked nowhere" in card
    assert "provReceiptHTML(p)" in card


def test_no_typed_number_in_the_receipt_or_section_copy():
    """Every number on the receipt and the section header comes from an artifact."""
    src = _src()
    for name in ("provReceiptHTML", "provSectionHeadHTML", "provRankCellHTML"):
        code = "\n".join(ln for ln in _function_source(src, name).split("\n")
                         if not ln.lstrip().startswith("//"))
        code = re.sub(r"style=\"[^\"]*\"", "", code)
        stats = re.findall(r"(?<![\w.#-])\d+\.\d+(?![\w.])", code)
        assert not stats, f"{name} types a number: {stats}"
        assert not re.search(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", code), f"{name} types a date"


# ---------------------------------------------------------------------------
# 3. served files
# ---------------------------------------------------------------------------

def test_served_baked_ranks_follow_the_section_rule():
    p = DATA / "timeseries.json"
    if not p.exists():
        pytest.skip("data/timeseries.json not built (gitignored)")
    doc = json.loads(p.read_text(encoding="utf-8"))
    if "prov_section" not in doc:
        pytest.skip("payload predates the section (exported before PV-07 and not re-baked)")
    actives = [r for r in doc.get("players") or [] if r.get("board_key_tail") is not None]
    sec = [r for r in actives if r.get("source_graded") is False]
    ranked = [r for r in actives if r.get("source_graded") is not False]
    assert sec and ranked
    assert all(r.get("overall_rank") is None and r.get("org_rank") is None for r in sec)
    assert sorted(r["overall_rank"] for r in ranked) == list(range(1, len(ranked) + 1))
    assert doc["prov_section"]["n_board_rows"] == len(sec)
    assert doc["prov_section"]["on"] is storage.PROV_SECTION_ON
