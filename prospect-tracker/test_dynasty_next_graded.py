# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Dynasty lens "Next to be graded" (Part 8 wiring W04, 2026-10-07).

Owner ask 4 (2026-09-30) wires provisional grades v2 into /fantasy/: a Dynasty
lens of the prospects no label source has graded, ordered by the chance of a
first grade, reading the SAME field the PROSPX section "Not yet graded by any
source" reads (provisional_v2 p_any_w12). Pinned here:

  1. the exporter's order equals the PROSPX section order, by running prospx's
     own comparators (boardCmp, provSectionCmp, fvCmpDesc, _dedupeProvPool,
     _buildProvPlayers) in V8 over the same inputs, on a fixture and on the
     served build when the sidecar and the files it read are from one build;
  2. no grade of any kind rides on a lens row (no expected FV, no eFV, no
     production grade), and the lens copy prints no forecast word;
  3. the lens renders its own rows with figures read from the payload's claim
     block, and the board never fetches the sidecar.
The claims-freshness pin (every printed figure equals the provisional track
record's) lives in test_claims_freshness.py.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

import fantasy_export as fe

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"
DYNASTY_JS = ROOT / "assets" / "dynasty.js"
DATA = ROOT / "data"
SIDECAR = DATA / "fantasy_next_graded.json"


# ---------------------------------------------------------------------------
# fixture: a board, the ungraded file, the eFV file, the chance model, a track
# ---------------------------------------------------------------------------
def _ts():
    def row(pk, mid, graded, **kw):
        r = {"player_key": pk, "player_name": pk.replace("_", " ").title(), "mlbam_id": mid,
             "org": "BOS", "position": "SS", "status": "active", "source_graded": graded,
             "fv_close": 35.0}
        r.update(kw)
        return r
    return {"generated_at": "2026-10-07T00:00:00Z",
            "prov_section": {"on": True, "title": "Not yet graded by any source"},
            "players": [
                row("graded_a", 1, True),
                row("anchor_hi", 11, False),
                row("anchor_tie_a", 12, False),
                row("anchor_tie_b", 13, False),
                row("anchor_nomodel", 14, False),
                row("anchor_debuted", 15, False, status="debuted", debut_date="2026-09-01"),
                row("twin_key", 16, False),
            ]}


def _ung():
    def e(mid, g, **kw):
        r = {"mlbam_id": mid, "player_name": "Prov %d" % mid, "org": "SEA", "position": "RHP",
             "xfv_grade": g}
        r.update(kw)
        return r
    return {"meta": {"generated_at": "2026-10-07"}, "by_player": {
        "prov_a": e(21, 30.0),
        "prov_b": e(22, 28.0),
        "prov_c": e(23, 26.0),
        # the twin of a board row: prospx drops it for the board row
        "twin_key": e(16, 44.0),
    }}


def _xfv():
    return {"meta": {"generated_at": "2026-10-07"}, "by_player": {
        "graded_a": {"xfv_grade": 55.0, "board_sort_key": 3.0},
        "anchor_hi": {"xfv_grade": 33.0, "board_sort_key": 0.5},
        # same chance, same grade: board_sort_key decides
        "anchor_tie_a": {"xfv_grade": 31.0, "board_sort_key": -0.2},
        "anchor_tie_b": {"xfv_grade": 31.0, "board_sort_key": 0.1},
        "anchor_nomodel": {"xfv_grade": 47.0, "board_sort_key": 1.0},
        "twin_key": {"xfv_grade": 29.0, "board_sort_key": 0.0},
    }}


def _v2():
    def r(mid, p12, **kw):
        out = {"mlbam": mid, "level": "A", "age": 19.0, "p_any_w6": p12 / 2, "p_any_w12": p12,
               "fv_first_fg": 41.2, "fv_first_mlbp": 40.1}
        out.update(kw)
        return out
    return {"generated_at": "2026-10-07T00:00:00+00:00", "model_id": "provisional_v2",
            "anchor": {"W6_end": "2027-04-15", "W12_end": "2027-10-15"},
            "label_sources": ["fangraphs", "mlb_pipeline", "mlb_pipeline_international"],
            "rows": [r(11, 0.80), r(12, 0.50), r(13, 0.50), r(21, 0.50), r(22, 0.65),
                     r(23, 0.10), r(16, 0.30), r(15, 0.99), r(1, 0.99)]}


def _track():
    return {"generated_at": "2026-10-02T00:00:00+00:00",
            "latest": {"a": "spent|1", "b": "pro|W6", "c": "pro|W12"},
            "by_player": {"source_names": {"fangraphs": "FanGraphs", "mlb_pipeline": "MLB Pipeline",
                                           "mlb_pipeline_international": "MLB Pipeline"}},
            "rows": [
                {"run_id": "spent|0", "leg": "served_backdated", "verdict_readable": True,
                 "as_of": "2026-10-01", "frozen_at": "2026-06-23", "scored_through": "2026-09-24",
                 "result": {"ANY": {"n": 1, "graded_in_window": 1, "selection": {}, "level": {}}}},
                {"run_id": "spent|1", "leg": "served_backdated", "verdict_readable": True,
                 "as_of": "2026-10-02", "frozen_at": "2026-06-23", "scored_through": "2026-09-24",
                 "result": {"ANY": {"n": 5631, "graded_in_window": 97,
                                    "selection": {"grade": {"auc": 0.8262},
                                                  "null_level_rank": {"auc": 0.6151}},
                                    "level": {"grade": {"spearman": 0.017, "mae": 6.21,
                                                        "mae_null_const": 4.54, "null_const": 35.0}}}}},
                {"run_id": "pro|W12", "leg": "prospective", "frozen_at": "2026-09-25",
                 "window_end": "2027-10-15", "scored_through": "2026-10-02", "verdict_readable": False,
                 "result": {"n_rows": 6066, "ANY": {"graded_in_window": 0}}},
                {"run_id": "pro|W6", "leg": "prospective", "frozen_at": "2026-09-25",
                 "window_end": "2027-04-15", "scored_through": "2026-10-02", "verdict_readable": False,
                 "result": {"n_rows": 6066, "ANY": {"graded_in_window": 0}}},
            ]}


def _build(n=None):
    return fe._next_graded(_ts(), v2=_v2(), ung=_ung(), xfv=_xfv(), track=_track(), n=n)


# ---------------------------------------------------------------------------
# 1. the exporter
# ---------------------------------------------------------------------------
def test_membership_and_order_follow_the_prospx_section():
    out = _build()
    keys = [r["key"] for r in out["rows"]]
    # graded rows, the graduate and the board row's provisional twin never list;
    # the model-uncovered row sits in the section but is not served
    assert keys == ["anchor_hi", "prov_b", "anchor_tie_b", "anchor_tie_a", "prov_a", "twin_key", "prov_c"]
    assert [r["n"] for r in out["rows"]] == list(range(1, 8))
    sec = out["section"]
    assert (sec["n_section"], sec["n_model"], sec["n_served"], sec["cut"]) == (8, 7, 7, "cap")
    # the twin row is the BOARD row (its board org), not the provisional entry
    twin = [r for r in out["rows"] if r["key"] == "twin_key"][0]
    assert twin["org"] == "BOS"


def test_the_list_stops_before_a_tie_the_shared_terms_cannot_order():
    ts, x = _ts(), _xfv()
    x["by_player"]["anchor_tie_b"]["board_sort_key"] = -0.2   # now an exact three-term tie
    out = fe._next_graded(ts, v2=_v2(), ung=_ung(), xfv=x, track=_track())
    assert [r["key"] for r in out["rows"]] == ["anchor_hi", "prov_b"]
    assert out["section"]["cut"] == "tie"
    assert [r["key"] for r in _build(n=3)["rows"]] == ["anchor_hi", "prov_b", "anchor_tie_b"]


def test_no_grade_rides_on_a_lens_row():
    """The model has no skill on the LEVEL of the first grade, so the lens shows
    the chance of a grade and never an expected FV (nor eFV or the production
    grade)."""
    out = _build()
    for r in out["rows"]:
        assert set(r) == set(fe.NEXT_GRADED_ROW_KEYS), r
    blob = json.dumps(out["rows"])
    for bad in ("fv_first", "xfv", "efv", "\"fv", "grade", "surplus", "p_bust"):
        assert bad not in blob, bad
    assert "p6" not in fe.NEXT_GRADED_ROW_KEYS


def test_the_claim_block_copies_the_latest_rows():
    c = _build()["claim"]
    assert c["retro"]["run_id"] == "spent|1"
    assert (c["retro"]["auc"], c["retro"]["auc_null_level"], c["retro"]["n"], c["retro"]["graded"]) == (
        0.8262, 0.6151, 5631, 97)
    assert (c["retro"]["spearman"], c["retro"]["mae"], c["retro"]["mae_null"], c["retro"]["null_const"]) == (
        0.017, 6.21, 4.54, 35.0)
    f = c["forward"]
    assert (f["run_id"], f["frozen_at"], f["n_rows"], f["window_end"], f["graded"]) == (
        "pro|W6", "2026-09-25", 6066, "2027-04-15", 0)
    out = _build()
    assert out["label_sources"] == ["FanGraphs", "MLB Pipeline"]
    assert out["windows"] == {"W6": "2027-04-15", "W12": "2027-10-15"}


def test_section_off_or_missing_inputs_build_nothing():
    ts = _ts()
    ts["prov_section"]["on"] = False
    assert fe._next_graded(ts, v2=_v2(), ung=_ung(), xfv=_xfv(), track=_track())["rows"] == []
    assert fe._next_graded(None, v2=_v2()) is None


def test_the_write_lands_on_the_redirected_path():
    """conftest redirects NEXT_GRADED_PATH, so this writes the mirror, never the
    served file."""
    fe._export_next_graded(_build(), log=None)
    doc = json.loads(Path(fe.NEXT_GRADED_PATH).read_text(encoding="utf-8"))
    assert doc["rows"][0]["key"] == "anchor_hi"


# ---------------------------------------------------------------------------
# 2. parity with prospx in V8
# ---------------------------------------------------------------------------
_FUNCS = ("provSectionInfo", "provSectionOn", "inProvSection", "provV2Of", "_provNum",
          "provSectionCmp", "efvBoardValue", "efvRankValue", "efvBoardSortKey", "getEfv",
          "fvCmpDesc", "boardCmp", "_dedupeProvPool", "_buildProvPlayers")


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


@pytest.fixture(scope="module")
def prospx_js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    src = PROSPX.read_text(encoding="utf-8")
    m = re.search(r"^const _NO_SORT_KEY = ([^;]+);", src, re.M)
    assert m, "_NO_SORT_KEY not found in prospx"
    assert float(eval(m.group(1))) == fe._NO_BOARD_SORT_KEY  # noqa: S307 - a numeric literal
    ctx = mr.MiniRacer()
    # The later terms of the fvCmpDesc chain (tiebreaker score, name) only order
    # rows the exporter refuses to serve, so a constant stands in for the score.
    ctx.eval("var DATA = null; var _EFV = null; var _EFV_UNG = null; var _PROV_V2 = null;"
             " var _PROV_PLAYERS = null, _PROV_BY_KEY = null;"
             " function provPlayers() { if (_PROV_PLAYERS === null) _buildProvPlayers(); return _PROV_PLAYERS || []; }"
             " function tiebreakerScore() { return 0; }"
             " const _NO_SORT_KEY = %s;" % m.group(1))
    for name in _FUNCS:
        ctx.eval(_function_source(src, name))
    return ctx


def _prospx_section_keys(ctx, ts, ung, xfv, v2) -> list[str]:
    by = {}
    for r in v2.get("rows") or []:
        if r.get("mlbam") is not None:
            by[fe._js_id(r["mlbam"])] = {"p_any_w12": r.get("p_any_w12")}
    ctx.eval("DATA = %s; _EFV = %s; _EFV_UNG = %s; _PROV_V2 = {by: %s};"
             " _PROV_PLAYERS = null; _PROV_BY_KEY = null;" % (
                 json.dumps(ts), json.dumps((xfv or {}).get("by_player") or {}),
                 json.dumps(ung), json.dumps(by)))
    # buildEfvRankMap's own three lines
    return json.loads(ctx.eval(
        "(function () { var pool = _dedupeProvPool(DATA.players.filter(p => p && p.player_key), provPlayers());"
        " pool.sort(boardCmp); return JSON.stringify(pool.filter(p => inProvSection(p)).map(p => p.player_key)); })()"))


def test_fixture_order_equals_the_prospx_section_order(prospx_js):
    sec = _prospx_section_keys(prospx_js, _ts(), _ung(), _xfv(), _v2())
    out = _build()
    assert len(sec) == out["section"]["n_section"]
    assert [r["key"] for r in out["rows"]] == sec[:out["section"]["n_served"]]
    # the uncovered row is last in prospx too
    assert sec[-1] == "anchor_nomodel"


def _slim_inputs():
    ts = json.loads((DATA / "timeseries.json").read_text(encoding="utf-8"))
    ung = json.loads((DATA / "xfv_ungraded.json").read_text(encoding="utf-8"))
    xfv = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    v2 = json.loads((DATA / "provisional_v2.json").read_text(encoding="utf-8"))
    keep_p = ("player_key", "player_name", "mlbam_id", "status", "debut_date", "source_graded",
              "_is_provisional", "fv_close", "fv_close_plus", "org", "position")
    keep_x = ("xfv_grade", "board_sort_key", "player_name", "name", "mlbam_id", "org", "position")
    stamps = {"timeseries": ts.get("generated_at"), "provisional_v2": v2.get("generated_at"),
              "xfv_ungraded": (ung.get("meta") or {}).get("generated_at"),
              "xfv": (xfv.get("meta") or {}).get("generated_at")}
    ts_s = {"generated_at": ts.get("generated_at"), "prov_section": ts.get("prov_section"),
            "players": [{k: p.get(k) for k in keep_p if k in p} for p in ts.get("players") or []
                        if isinstance(p, dict)]}
    ung_s = {"meta": ung.get("meta"), "by_player": {
        k: {kk: e.get(kk) for kk in keep_x if kk in e}
        for k, e in (ung.get("by_player") or {}).items() if isinstance(e, dict)}}
    xfv_s = {"meta": xfv.get("meta"), "by_player": {
        k: {kk: e.get(kk) for kk in ("xfv_grade", "board_sort_key") if kk in e}
        for k, e in (xfv.get("by_player") or {}).items() if isinstance(e, dict)}}
    return ts_s, ung_s, xfv_s, v2, stamps


def test_served_lens_equals_the_served_prospx_section_order(prospx_js):
    """The same build: the served sidecar's rows are the first rows of the
    section prospx prints from the files the sidecar says it read."""
    need = [SIDECAR] + [DATA / n for n in ("timeseries.json", "xfv_ungraded.json", "xfv.json",
                                           "provisional_v2.json")]
    if not all(p.exists() for p in need):
        pytest.skip("the served build is not in this tree")
    side = json.loads(SIDECAR.read_text(encoding="utf-8"))
    ts, ung, xfv, v2, stamps = _slim_inputs()
    inputs = side.get("inputs") or {}
    if any(inputs.get(k) != v for k, v in stamps.items()):
        pytest.skip("the sidecar was built from another build's files: %s vs %s" % (inputs, stamps))
    sec = _prospx_section_keys(prospx_js, ts, ung, xfv, v2)
    rows = side["rows"]
    assert rows and len(sec) == side["section"]["n_section"]
    assert [r["key"] for r in rows] == sec[:len(rows)]
    assert [r["n"] for r in rows] == list(range(1, len(rows) + 1))
    for r in rows:
        assert set(r) == set(fe.NEXT_GRADED_ROW_KEYS), r


# ---------------------------------------------------------------------------
# 3. the client
# ---------------------------------------------------------------------------
def _dyn_ctx(next_payload):
    from test_fantasy_split import APP_PRELUDE, MiniRacer
    payload = {"season": 2026, "n_players": 0, "scoring_catalog": [], "players": [],
               "sections": {"dynasty": [
                   {"mlbam": 101, "name": "First Kid", "org": "BOS", "pos": "SS", "eta": 2027,
                    "efv": 62.4, "star": 31, "bust": 12, "surplus": 88.0, "band": [15.0, 190.0],
                    "score": 9.1, "rank": 1, "tier": "Elite"}], "callup_watch": []}}
    route = ("var NEXTP = %s; var __urls = [];\n"
             "var fetch = function (u) { __urls.push(String(u));"
             " var P = String(u).indexOf('fantasy_next_graded') >= 0 ? NEXTP : PAYLOAD;"
             " return FT({ ok: true, json: function () { return FT(P); } }); };\n"
             "window.fetch = fetch;\n") % json.dumps(next_payload)
    c = MiniRacer()
    c.eval(APP_PRELUDE % json.dumps(payload) + route)
    c.eval(DYNASTY_JS.read_text(encoding="utf-8"))
    return c


def _names(html):
    return re.findall(r'<a class="dyn-name-link" href="/prospx/#player=([^"]+)"', html)


def _next_payload():
    out = _build()
    out["generated_at"] = "2026-10-07T00:00:00Z"
    return out


def test_the_lens_renders_its_own_rows_in_the_served_order():
    c = _dyn_ctx(_next_payload())
    html = c.eval('__go("#section=dynasty&lens=next")')
    names = _names(html)
    assert names[:7] == ["anchor_hi", "prov_b", "anchor_tie_b", "anchor_tie_a", "prov_a", "twin_key", "prov_c"]
    assert "First Kid" not in html
    bar = c.eval("__html['dynasty-scoring']")
    assert 'data-dynlens="next"' in bar and "Next to be graded" in bar
    # the chance, nearest whole percent, under a label read from the window end
    assert ">80%<" in html and "By Oct 2027" in html
    # sorting by name re-sorts the same rows and keeps their places
    by_name = c.eval('__go("#section=dynasty&lens=next&sort=name.a")')
    assert _names(by_name)[0] == "anchor_hi"
    # Back to the board: a hash without a lens is the board
    board = c.eval('__go("#section=dynasty")')
    assert "First Kid" in board and "/prospx/#player=" not in board


def test_the_lens_copy_prints_the_claim_block_figures():
    c = _dyn_ctx(_next_payload())
    html = c.eval('__go("#section=dynasty&lens=next")')
    for s in ("AUC 0.826", "against 0.615 for ordering by level", "97 first grades among 5,631 players",
              "no skill on the grade itself", "Spearman 0.017", "a miss of 6.21 FV on average against 4.54",
              "for a flat 35", "A freeze of 6,066 players taken Sep 25, 2026",
              "its first window closes Apr 15, 2027", "0 of them had drawn a first grade through Oct 2, 2026",
              "The production grade PROSPX served on Jun 23, 2026", "by Sep 24, 2026",
              "from FanGraphs or MLB Pipeline by Oct 15, 2027", "the first 7 of the 8 rows",
              "Not yet graded by any source", "1 row of the section sits outside the model's coverage"):
        assert s in html, s
    # the claim block moves the copy: a different artifact, different words
    p = _next_payload()
    p["claim"]["retro"]["auc"] = 0.7
    p["claim"]["retro"]["mae"] = 3.0
    html2 = _dyn_ctx(p).eval('__go("#section=dynasty&lens=next")')
    assert "AUC 0.700" in html2 and "no skill on the grade itself" not in html2


def test_no_forecast_word_and_no_grade_on_the_lens():
    c = _dyn_ctx(_next_payload())
    html = c.eval('__go("#section=dynasty&lens=next")') + c.eval("__html['dynasty-scoring']")
    low = html.lower()
    for w in ("sleeper", "breakout", " due ", "will "):
        assert w not in low, w
    assert "eFV" not in html and "fv-badge" not in html and "Expected first grade" not in html
    src = DYNASTY_JS.read_text(encoding="utf-8")
    assert "sleeper" not in src.lower()


def test_the_board_never_fetches_the_lens_sidecar():
    c = _dyn_ctx(_next_payload())
    c.eval('__go("#section=dynasty")')
    c.eval('__go("#section=dynasty&lens=contend")')
    c.eval('__go("#section=keeper")')
    assert not [u for u in json.loads(c.eval("JSON.stringify(__urls)")) if "next_graded" in u]
    c.eval('__go("#section=dynasty&lens=next")')
    assert [u for u in json.loads(c.eval("JSON.stringify(__urls)")) if "next_graded" in u]


def test_an_empty_or_missing_sidecar_says_so():
    html = _dyn_ctx({"rows": []}).eval('__go("#section=dynasty&lens=next")')
    assert "Nothing is broken" in html


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
