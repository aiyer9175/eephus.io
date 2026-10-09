# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v4 rater-panel pins (efv_rater_panel.py, efv_w2_raters.py; EFV4_RATER_PANEL, EW2-10).

1. The identity pass reads no outcome: an AST scan of efv_rater_panel.py (the
   test_efv_identity pattern) and its import list.
2. Parsing: numbered lists in every separator the pages use, reader comments that repeat
   a rank, ordered HTML lists, publication day and the [V-01-01, V-05-01) window.
3. Identity on fixture boards: exact name, club, side, last name plus initial, a listed
   name variant, ties left unresolved.
4. Reserved list years are not built until the committed registration names them.
5. The column: list floor, as-of reads, the panel mean, the within-group residual, the
   reserved guard on lv vintages.
6. The runtime registration leaves efv_v3 as it was; the arms are registered in the
   screening lab; no FV-level grouping and no em or en dash in the new sources; the
   progress rows are development rows with a screening block.

Fixture rows and pages throughout; nothing here builds a real frame or reads a real list.
"""
from __future__ import annotations

import ast
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_rater_panel as RP  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import efv_w2_raters as W  # noqa: E402

PANEL_SRC = ROOT / "efv_rater_panel.py"
W_SRC = ROOT / "efv_w2_raters.py"
FETCH_SRC = ROOT / "tools" / "efv4_rater_fetch.py"

# ---------------------------------------------------------------------------
# 1. the identity pass reads no outcome
# ---------------------------------------------------------------------------

_FORBIDDEN = re.compile(
    r"debut|career|(^|_)war($|_)|mlb_first|reached|(^|_)label|(^|_)w3|(^|_)r3|"
    r"mlbam_id|birth|all_sports|player_index|sport1|first_mlb|outcome")
#: interval_label is the board snapshot's list name (for example "MLB Pipeline 2014
#: Angels Top 30"), read for the club; it names a list, not an outcome label.
_ALLOWED_TOKENS = {"interval_label"}
_ALLOWED_IMPORTS = {"__future__", "html", "json", "re", "sqlite3", "subprocess",
                    "unicodedata", "datetime", "pathlib"}


def _docstring_ids(tree) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _tokens(tree):
    docs = _docstring_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id, node.lineno
        elif isinstance(node, ast.Attribute):
            yield node.attr, node.lineno
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            yield node.name, node.lineno
        elif isinstance(node, ast.arg):
            yield node.arg, node.lineno
        elif isinstance(node, ast.keyword) and node.arg:
            yield node.arg, node.lineno
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docs:
            yield node.value, node.lineno


def test_identity_source_reads_no_outcome_column():
    tree = ast.parse(PANEL_SRC.read_text(encoding="utf-8"))
    for tok, line in _tokens(tree):
        low = tok.lower()
        for allowed in _ALLOWED_TOKENS:
            low = low.replace(allowed, "")
        assert not _FORBIDDEN.search(low), (tok, line)
        assert tok != "MLB", line


def test_identity_source_imports_only_its_own_stack():
    tree = ast.parse(PANEL_SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] in _ALLOWED_IMPORTS, a.name
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] in _ALLOWED_IMPORTS, node.module


def test_identity_reads_board_sources_only():
    assert RP.ID_SOURCES == ("mlb_pipeline", "fangraphs")
    assert RP.RESERVED_YEARS == F.RESERVED_LV


# ---------------------------------------------------------------------------
# 2. parsing
# ---------------------------------------------------------------------------

_NUMBERED_PAGE = """
<script type="application/ld+json">{"datePublished":"2013-02-25T10:00:00+00:00"}</script>
<p>100. <a href="x">Austin Romine</a> | Catcher | New York AL<br />
99. <strong>Luis Heredia</strong> | RHP | Pittsburgh<br />
3. Dylan Bundy, RHP, Baltimore (2013 LVL: AA/MLB, ETA: 2013): A talent<br />
2. Andrew Heaney. LHP, Miami<br />
1. Fernando Tatis, Jr., SS, San Diego Padres</p>
<div class="comments"><p>3. Somebody Else, OF, Rays (they missed)</p></div>
"""

_OL_PAGE = """
<p>intro</p>
<ol><li>Not, a, list item that matches nothing useful at all ok</li></ol>
<ol>
<li><span class="playerdef"><a href="c">Ronald Acuna</a></span>, OF, <span><a>Atlanta Braves</a></span></li>
<li><a href="c"><span>Vladimir Guerrero</span> Jr.</a>, 3B, <span>Toronto Blue Jays</span></li>
<li>Gleyber Torres, SS, New York Yankees</li>
</ol>
"""


def test_numbered_lists_parse_every_separator_and_ignore_repeats():
    got = RP.parse_numbered(_NUMBERED_PAGE)
    by = {e["rank"]: e for e in got}
    assert sorted(by) == [1, 2, 3, 99, 100]
    assert by[100]["name"] == "Austin Romine" and by[100]["pos"] == "Catcher"
    assert by[99]["team"] == "Pittsburgh"
    assert by[3]["name"] == "Dylan Bundy" and by[3]["team"] == "Baltimore"
    assert by[2]["name"] == "Andrew Heaney" and by[2]["pos"] == "LHP"
    assert by[1]["name"] == "Fernando Tatis" and by[1]["pos"] == "SS"
    assert RP.published(_NUMBERED_PAGE) == "2013-02-25"


def test_ordered_lists_take_the_longest_matching_list():
    got = RP.parse_ol(_OL_PAGE)
    assert [e["rank"] for e in got] == [1, 2, 3]
    assert got[0]["name"] == "Ronald Acuna" and got[0]["team"] == "Atlanta Braves"
    assert got[1]["name"].startswith("Vladimir Guerrero") and got[1]["pos"] == "3B"


def test_window_is_preseason_only():
    assert RP.in_window("2016-04-01", 2016)
    assert RP.in_window("2011-01-01", 2011)
    assert not RP.in_window("2016-05-01", 2016)
    assert not RP.in_window("2015-12-31", 2016)
    assert not RP.in_window(None, 2016)


def test_club_codes():
    assert RP.club_code("New York AL") == "NYY"
    assert RP.club_code("Chicago NL") == "CHC"
    assert RP.club_code("Los Angeles Angels") == "LAA"
    assert RP.club_code("Florida") == "MIA"
    assert RP.club_code("Oakland A\u2019s") == "OAK"
    assert RP.club_code("Guardians") == RP.club_code("Indians") == "CLE"
    assert RP.club_code("Nowhere") is None


# ---------------------------------------------------------------------------
# 3. identity on fixture boards
# ---------------------------------------------------------------------------

def _index():
    rows = [
        ("jose_a", "Jose Alpha", "SS", "MLB Pipeline 2014 Twins Top 30", "mlb_pipeline"),
        ("luis_g1", "Luis Garcia", "SS", "MLB Pipeline 2014 Nationals Top 30", "mlb_pipeline"),
        ("luis_g2", "Luis Garcia", "RHP", "MLB Pipeline 2014 Phillies Top 30", "mlb_pipeline"),
        ("luis_g3", "Luis Garcia", "OF", "MLB Pipeline 2014 Phillies Top 30", "mlb_pipeline"),
        ("jon_gray", "Jon Gray", "RHP", "MLB Pipeline 2014 Rockies Top 30", "mlb_pipeline"),
        ("adalberto_mondesi", "Adalberto Mondesi", "SS", "MLB Pipeline 2014 Royals Top 30",
         "mlb_pipeline"),
        ("twin_a", "Sam Twin", "C", "MLB Pipeline 2014 Mets Top 30", "mlb_pipeline"),
        ("twin_b", "Sam Twin", "C", "MLB Pipeline 2014 Mets Top 30", "mlb_pipeline"),
    ]
    return RP.BoardIndex.from_rows(2014, rows)


def test_identity_steps():
    idx = _index()
    assert idx.resolve("Jose Alpha", "SS", "Twins")[:2] == ("jose_a", "name")
    assert idx.resolve("Jos\u00e9 Alpha Jr.", "SS", "Twins")[0] == "jose_a"
    assert idx.resolve("Luis Garcia", "SS", "Washington Nationals")[:2] == ("luis_g1",
                                                                         "name_club")
    assert idx.resolve("Luis Garcia", "RHP", "Phillies")[:2] == ("luis_g2", "name_side")
    assert idx.resolve("Jonathan Gray", "RHP", "Colorado Rockies")[:2] == (
        "jon_gray", "last_name_initial_club")
    assert idx.resolve("Jonathan Gray", "RHP", "Cubs")[0] is None
    assert idx.resolve("Jonathan Gray", "C", "Rockies")[0] is None    # side disagrees
    assert idx.resolve("Raul Mondesi", "SS", "Kansas City Royals")[:2] == (
        "adalberto_mondesi", "alias")
    assert idx.resolve("Sam Twin", "C", "Mets")[:2] == (None, "ambiguous")
    assert idx.resolve("Nobody Here", "C", "Mets")[:2] == (None, "no_candidate")


def _fixture_db(path: Path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE snapshots (id INTEGER, source TEXT, snapshot_date TEXT, "
                "interval_label TEXT, player_key TEXT, player_name TEXT, position TEXT, "
                "org TEXT, rank INTEGER, fv REAL, status TEXT, inserted_at TEXT, "
                "tools_json TEXT, fv_plus INTEGER)")
    rows = [
        ("mlb_pipeline", "2013-01-22", "MLB Pipeline 2013 Twins Top 30", "jose_a", "Jose Alpha",
         "SS"),
        ("mlb_pipeline", "2020-01-22", "MLB Pipeline 2020 Twins Top 30", "kid_b", "Kid Beta",
         "SS"),
        ("auto_detect", "2013-04-01", "Auto-detected", "other_c", "Other Gamma", "SS"),
    ]
    for i, (src, d, lab, pk, nm, pos) in enumerate(rows):
        con.execute("INSERT INTO snapshots (id, source, snapshot_date, interval_label, "
                    "player_key, player_name, position) VALUES (?,?,?,?,?,?,?)",
                    (i, src, d, lab, pk, nm, pos))
    con.commit()
    con.close()


def test_build_panel_skips_reserved_years_until_named(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    page13 = ('{"datePublished":"2013-02-25T00:00:00"}<p>1. Jose Alpha, SS, Twins<br />'
              '2. Other Gamma, SS, Rays</p>')
    page20 = ('{"datePublished":"2020-01-27T00:00:00"}<ol><li>Kid Beta, SS, Minnesota Twins'
              '</li></ol>')
    (raw / "bp_2013.html").write_text(page13, encoding="utf-8")
    (raw / "bp_2020.html").write_text(page20, encoding="utf-8")
    db = tmp_path / "p.db"
    _fixture_db(db)
    monkeypatch.setattr(RP, "LISTS", {"bp_2013": ("bp", 2013, "numbered"),
                                      "bp_2020": ("bp", 2020, "ol")})
    monkeypatch.setattr(RP, "MANIFEST", tmp_path / "none.json")
    doc = RP.build_panel(raw_dir=raw, db_path=db, allow_reserved=False)
    assert list(doc["lists"]) == ["bp_2013"]
    assert doc["skipped_lists"][0]["list"] == "bp_2020"
    ent = doc["lists"]["bp_2013"]["entries"]
    assert ent[0]["player_key"] == "jose_a"
    assert ent[1]["player_key"] is None            # auto_detect is never an identity source
    doc2 = RP.build_panel(raw_dir=raw, db_path=db, allow_reserved=True)
    assert doc2["lists"]["bp_2020"]["entries"][0]["player_key"] == "kid_b"


def test_build_panel_drops_a_list_published_outside_the_window(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "bp_2013.html").write_text('{"datePublished":"2013-07-02T00:00:00"}'
                                      '<p>1. Jose Alpha, SS, Twins</p>', encoding="utf-8")
    db = tmp_path / "p.db"
    _fixture_db(db)
    monkeypatch.setattr(RP, "LISTS", {"bp_2013": ("bp", 2013, "numbered")})
    monkeypatch.setattr(RP, "MANIFEST", tmp_path / "none.json")
    doc = RP.build_panel(raw_dir=raw, db_path=db, allow_reserved=False)
    assert doc["lists"] == {}
    assert "outside" in doc["skipped_lists"][0]["reason"]


def test_registration_marker_is_in_the_registration_doc():
    text = (ROOT / RP.REGISTRATION_DOC).read_text(encoding="utf-8")
    assert RP.RESERVED_MARKER in text
    assert "Registration status: REGISTERED" in text


# ---------------------------------------------------------------------------
# 5. the column
# ---------------------------------------------------------------------------

def test_list_floor_is_one_step_below_the_last_rank():
    assert W.list_floor(101) == 45.0
    assert W.list_floor(100) == 45.0
    assert W.list_floor(142) == 40.0
    assert W.list_floor(30) == 50.0


def _panel():
    doc = {"lists": {
        "bp_2015": {"rater": "bp", "year": 2015, "published": "2015-02-09", "last_rank": 101,
                    "entries": [{"rank": 1, "player_key": "a"}, {"rank": 50, "player_key": "b"},
                                {"rank": 80, "player_key": None}]},
        "fg_2015": {"rater": "fg", "year": 2015, "published": "2015-02-17", "last_rank": 142,
                    "entries": [{"rank": 120, "player_key": "b"}]},
        "bp_2020": {"rater": "bp", "year": 2020, "published": "2020-01-27", "last_rank": 101,
                    "entries": [{"rank": 3, "player_key": "z"}]}}}
    return doc


def test_panel_value_reads_as_of_and_averages_raters():
    p = W.Panel.from_doc(_panel())
    assert ("bp", 2020) not in p.lists                       # reserved list year withheld
    assert p.value("a", "2015-02-10") == (70.0, 1, 1)         # fg not yet published
    v, n, nl = p.value("a", "2015-03-01")
    assert (v, n, nl) == ((70.0 + 40.0) / 2, 2, 1)            # fg floor 40 (142 list)
    assert p.value("b", "2015-03-01") == ((50.0 + 45.0) / 2, 2, 2)
    assert p.value("c", "2015-03-01") == ((45.0 + 40.0) / 2, 2, 0)
    assert p.value("a", "2015-01-15") == (None, 0, 0)         # nothing published yet
    assert p.value("a", "2016-03-01") == (None, 0, 0)         # a list counts in its own year
    assert p.value("a", None) == (None, 0, 0)
    assert ("bp", 2020) in W.Panel.from_doc(_panel(), allow_reserved=True).lists


def test_resid_is_the_panel_percentile_minus_the_consensus_percentile():
    p = W.Panel.from_doc(_panel())
    items = [(("x", k), k, "2015-03-01", fv, "g") for k, fv in
             (("a", 55.0), ("b", 50.0), ("c", 60.0), ("d", 45.0))]
    items.append((("x", "e"), "e", "2015-01-02", 50.0, "g"))  # no list yet: None
    vals, info = W.resid_column(items, p)
    assert vals[("x", "e")] is None and info[("x", "e")]["panel_fv"] is None
    pv = [info[("x", k)]["panel_fv"] for k in "abcd"]
    up = H.within_pct(pv, [0] * 4)
    uc = H.within_pct([55.0, 50.0, 60.0, 45.0], [0] * 4)
    for i, k in enumerate("abcd"):
        assert vals[("x", k)] == pytest.approx(up[i] - uc[i])


def test_lv_values_trip_on_a_reserved_vintage():
    p = W.Panel.from_doc(_panel())
    rows = [{"player_key": "a", "asof_date": "2020-03-01", "grades": {}}]
    with pytest.raises(F.ReservedFrameError):
        W.lv_values("hit", {2020: (rows, [{}])}, {2020: {(2020, "a", "test")}}, p)


def test_lv_values_group_by_vintage_and_fill_slots():
    import source_backtest as SB
    p = W.Panel.from_doc(_panel())
    rows = [{"player_key": k, "asof_date": "2015-03-01", "grades": {SB.CONSENSUS_KEY: fv}}
            for k, fv in (("a", 55.0), ("b", 50.0), ("c", 45.0))]
    slots = {2015: {(2015, "a", "train"), (2015, "a", "test"), (2015, "c", "test")}}
    vals, info = W.lv_values("hit", {2015: (rows, [{}, {}, {}])}, slots, p)
    assert set(vals) == slots[2015]
    assert vals[(2015, "a", "train")] == vals[(2015, "a", "test")]
    assert info[(2015, "c", "test")]["n_listed"] == 0


def test_twin_permutes_within_year_and_kind():
    vals = {(2015, f"p{i}", "train"): float(i) for i in range(30)}
    vals.update({(2016, f"p{i}", "test"): float(100 + i) for i in range(30)})
    t = W.permuted(vals, 7)
    assert sorted(v for s, v in t.items() if s[0] == 2015) == list(map(float, range(30)))
    assert sorted(v for s, v in t.items() if s[0] == 2016) == [100.0 + i for i in range(30)]
    assert t != vals


# ---------------------------------------------------------------------------
# 6. registration, lab, source hygiene, ledger rows
# ---------------------------------------------------------------------------

def test_runtime_registration_leaves_efv_v3_unchanged():
    import efv_v3 as V3
    before = dict(V3.W2_COLUMNS)
    with W.register_runtime():
        assert V3.W2_COLUMNS["w2r_panel_hit"]["key"] == W.column_key("hit")
        cfg = W.arm_config(W.ARMS[-1])
        assert cfg["add"]["hit"]["skill"] == ["w2r_panel_hit"]
        assert cfg["add"]["pit"]["skill"] == ["w2r_panel_pit"]
    assert V3.W2_COLUMNS == before
    assert "w2r_" not in (ROOT / "efv_v3.py").read_text(encoding="utf-8")
    assert W.column_key("pit").startswith(H.V2_SCREEN_PREFIX)


def test_arms_are_registered_in_the_screening_lab():
    import efv_screen_lab as LAB
    assert LAB.WAVE2_DEV[W.MODULE] == tuple(a["name"] for a in W.ARMS)
    assert len(LAB.CANDIDATES) == 7


_BANNED = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv", "fv_band",
           "fv_bin", "by_consensus", "per_fv", "per_consensus")


@pytest.mark.parametrize("src", [PANEL_SRC, W_SRC])
def test_no_fv_grouping_in_the_sources(src):
    tree = ast.parse(src.read_text(encoding="utf-8"))
    fv_group = re.compile(r"(by|per|group)_?(fv|consensus|grade)")
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.arg):
            name = node.arg
        if name:
            low = name.lower()
            assert not any(b in low for b in _BANNED), (name, node.lineno)
            assert not fv_group.search(low), (name, node.lineno)


@pytest.mark.parametrize("src", [PANEL_SRC, W_SRC, FETCH_SRC,
                                 ROOT / "docs" / "efv-v2" / "EFV4_RATER_PANEL.md",
                                 Path(__file__)])
def test_no_em_or_en_dash(src):
    text = src.read_text(encoding="utf-8")
    assert chr(0x2014) not in text and chr(0x2013) not in text


def test_fetcher_writes_only_its_own_cache_and_keeps_the_window():
    import datetime as dt
    import efv4_rater_fetch as FX
    assert FX.CACHE.name == "efv4_raters" and FX.CACHE.parent.name == ".cache"
    assert not FX._fetch_window_open(dt.datetime(2026, 10, 9, 6, 0, tzinfo=dt.timezone.utc))
    assert not FX._fetch_window_open(dt.datetime(2026, 10, 9, 10, 59, tzinfo=dt.timezone.utc))
    assert FX._fetch_window_open(dt.datetime(2026, 10, 9, 11, 0, tzinfo=dt.timezone.utc))
    assert FX._fetch_window_open(dt.datetime(2026, 10, 9, 5, 59, tzinfo=dt.timezone.utc))
    assert {s["rater"] for s in FX.SKIPPED} >= {"ba", "espn"}


def _leg(d):
    return {"delta": d, "ci95": [d - 0.01, d + 0.01], "mde95": 0.01, "reading": "inside",
            "estimator": "E_cond", "status": "ok", "n": 100}


def _frame_blk():
    legs = {"spearman": _leg(0.001), "pooled": _leg(0.0), "auc": _leg(0.0)}
    r = {"spearman": 0.2, "auc": 0.6, "n": 100, "within": 0.2, "pooled": 0.2}
    return {"frame_version": "lv1_v2", "n": 100, "n_by_side": {"hit": 100},
            "raters": {"efv_v2_candidate": r, "efv_v2_base": r, "prospx_consensus": r},
            "deltas": {"candidate_vs_efv_v2_base": legs, "candidate_vs_prospx_consensus": legs,
                       "efv_v2_base_vs_prospx_consensus": legs},
            "statistic": "within", "secondary": {}, "admitted_folds": 1, "n_folds": 3,
            "twin": {"within": 0.0}}


def test_progress_rows_are_development_rows_with_a_screening_block(tmp_path):
    import efv_progress as P
    doc = {"generated_at": "2026-10-09T03:00:00Z", "label": {"id": "x"}, "code": {},
           "dev": {"arms": [{"name": "w2r_panel_hit", "sides": ["hit"], "head": "skill",
                             "kind": "column", "model_id": "efv_w2_raters:v4:w2r_panel_hit",
                             "frames": {"lv_dev": _frame_blk(), "vm_dev": _frame_blk()}}]}}
    docs = W.arm_docs(doc)
    assert len(docs) == 1 and docs[0]["role"] == "development"
    assert docs[0]["screening"]["development_only"] is True
    rows = P.build_dev_rows(docs[0], sources=[], date="2026-10-09", trigger="efv_change",
                            now_iso="2026-10-09T03:00:00Z", frames=W.DEV_FRAMES,
                            raters=P.SCREEN_RATERS, deltas=P.SCREEN_DELTAS,
                            statistic_fields=True)
    assert rows and all(r["role"] == "development" for r in rows)
    assert {r["frame"] for r in rows} <= set(W.DEV_FRAMES)


def test_spent_frames_never_reach_the_ledger():
    doc = {"dev": {"arms": []}, "spent": {"arms": [{"name": "w2r_panel_hit"}]}}
    assert W.arm_docs(doc) == []
    assert set(W.SPENT_FRAMES).isdisjoint(W.DEV_FRAMES)
    assert W.SPENT_LABEL == "spent frame, read after the 10-08 confirmation"


def test_lab_reads_reserved_only_on_the_gate():
    with pytest.raises(F.ReservedFrameError):
        W.build_spent_inputs(W.Panel({}), "0" * 40)
    _ = np
