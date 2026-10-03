# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV3_B4 pins for the pick family (SP/efv3/EFV3_PLAN.md s4; LANE_B.md F-B7 and the
D1 rule in s3).

1. The builder joins on the outcome-blind id and never on record_mlbam_id (AST: the
   name and the string are absent from the source), reads no WAR, debut, label or
   major league column, and poisoning every outcome field and the record id leaves
   every pick output unchanged.
2. The timing rule: a July pick in year V never joins a V row; it joins the V + 1
   row; a player drafted twice carries the latest pre-V pick; the sidecar pick stands
   in only when the frame marked it known at V; otherwise the row is missing.
3. The column is log1p(pick), None on a missing row, timing head only (D4), a named
   re-test registered in the lab under its own name; seasons_at_level and bonus are
   not in the family.
4. Reserved vintages raise everywhere; the coverage receipt is by (side, vintage)
   and refuses a pick dated at or after V.
5. No FV-cell grouping (PROSPECT_ANCHOR_GATE) in the builder or the probe tool; no
   em-dash; the probe's merge keeps every other key and the file's line ending.
"""
from __future__ import annotations

import ast
import copy
import json
import math
import re
import sys
from pathlib import Path

import pytest

import efv_pick_features as PK
import efv_vintage_frame as F

ROOT = Path(__file__).parent
SRC = ROOT / "efv_pick_features.py"
TOOL = ROOT / "tools" / "efv_pick_balance.py"
sys.path.insert(0, str(ROOT / "tools"))

_ALLOWED_IMPORTS = {"__future__", "json", "math", "pathlib", "efv_vintage_frame"}
_OUTCOME_WORD = re.compile(r"(^|_)(war|fwar|ewar|debut|debuts|reached|w3|r3|l6|label|"
                           r"labels|outcome|statline|bonus|seasons_at_level)(_|$)")
_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin")


def _row(pk, V, mlbam=None, acq_year=None, pick=None, side="hit", fv=50.5):
    lo, hi = F.window_bounds(V, None)
    known = acq_year is not None and int(acq_year) < V
    return {"player_key": pk, "vintage": V, "side": side, "window": [lo, hi],
            "mlbam_id": mlbam, "record_mlbam_id": None, "grades": {"consensus": fv},
            "acq_year": acq_year, "acq_known_at_v": known,
            "pick_overall": pick if known else None, "bonus_usd": None}


def _draft_dir(tmp_path, classes):
    """classes: {year: [(pick, mlbam, name), ...]} written as the on-disk shape."""
    d = tmp_path / "draft_history"
    d.mkdir(parents=True)
    for year, picks in classes.items():
        (d / f"{year}.json").write_text(json.dumps(
            [{"pick": p, "mlbam": m, "name": n} for p, m, n in picks]), encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# 1. the join is on the outcome-blind id; no outcome column
# ---------------------------------------------------------------------------

def _imports(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module.split(".")[0])
    return out


def _names(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            yield node.name
        elif isinstance(node, ast.arg):
            yield node.arg
        elif isinstance(node, ast.alias):
            yield node.name


def test_imports_are_the_allowed_set():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    assert _imports(tree) <= _ALLOWED_IMPORTS, _imports(tree) - _ALLOWED_IMPORTS


def test_join_never_names_the_record_id_or_an_outcome():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for name in _names(tree):
        low = name.lower()
        assert "record_mlbam" not in low, name
        assert not _OUTCOME_WORD.search(low), name
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            low = node.value.lower()
            assert "record_mlbam" not in low, node.value
            if len(node.value) < 40:
                assert not _OUTCOME_WORD.search(low), node.value
    # the one id the join reads is the outcome-blind one
    assert "mlbam_id" in {n for n in _names(tree)} | {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)}


def test_outputs_ignore_the_record_id_and_every_outcome_field(tmp_path):
    picks = PK.load_draft_picks(_draft_dir(tmp_path, {2014: [(7, 111, "A"), (30, 222, "B")]}))
    rows = [_row("a", 2016, mlbam=111), _row("b", 2016, mlbam=None),
            _row("c", 2016, mlbam=333, acq_year=2015, pick=90)]
    clean = PK.attach_pick(rows, picks)
    poisoned = copy.deepcopy(rows)
    for r in poisoned:
        r.update(war=1e9, fwar=float("nan"), w3=7.0, r3=1.0, reached="reached",
                 debut_date="2016-01-02", l6=5.0, record_mlbam_id=222)
    dirty = PK.attach_pick(poisoned, picks)
    keys = [k for k in clean[0] if k.startswith("pick_")]
    assert keys
    for c, d in zip(clean, dirty):
        assert {k: c[k] for k in keys} == {k: d[k] for k in keys}
    # the record id names a drafted player, the outcome-blind id does not: missing
    assert dirty[1]["pick_missing"] == 1.0 and dirty[1]["pick_log1p"] is None
    assert clean[0]["pick_source"] == PK.SOURCE_DRAFT and clean[0]["pick_overall_at_v"] == 7
    assert clean[2]["pick_source"] == PK.SOURCE_SIDECAR and clean[2]["pick_overall_at_v"] == 90


# ---------------------------------------------------------------------------
# 2. the timing rule
# ---------------------------------------------------------------------------

def test_july_pick_in_year_v_never_joins_a_v_row(tmp_path):
    picks = PK.load_draft_picks(_draft_dir(tmp_path, {2016: [(3, 111, "A")]}))
    at_v = PK.pick_for_row(_row("a", 2016, mlbam=111), picks)
    assert at_v["pick_missing"] == 1.0 and at_v["pick_overall_at_v"] is None
    assert at_v["pick_log1p"] is None and at_v["pick_source"] is None
    after = PK.pick_for_row(_row("a", 2017, mlbam=111), picks)
    assert after["pick_overall_at_v"] == 3 and after["pick_draft_year"] == 2016
    assert after["pick_source"] == PK.SOURCE_DRAFT and after["pick_missing"] == 0.0
    # the sidecar's July pick in V is not known at V either (the frame's flag)
    sc = PK.pick_for_row(_row("b", 2016, acq_year=2016, pick=12), picks)
    assert sc["pick_missing"] == 1.0
    # and a sidecar row whose flag disagrees with its year is still refused
    bad = dict(_row("b", 2016, acq_year=2015, pick=12), acq_year=2016)
    assert PK.pick_for_row(bad, picks)["pick_missing"] == 1.0


def test_twice_drafted_player_carries_the_latest_pre_v_pick(tmp_path):
    picks = PK.load_draft_picks(_draft_dir(tmp_path, {
        2012: [(40, 111, "A")], 2015: [(1, 111, "A"), (1, 111, "A dup")], 2018: [(5, 111, "A")]}))
    assert PK.pick_at_vintage(111, 2016, picks) == (1, 2015)
    assert PK.pick_at_vintage(111, 2014, picks) == (40, 2012)
    assert PK.pick_at_vintage(111, 2019, picks) == (5, 2018)
    assert PK.pick_at_vintage(111, 2012, picks) == (None, None)
    assert PK.pick_at_vintage(None, 2016, picks) == (None, None)
    assert PK.pick_at_vintage("x", 2016, picks) == (None, None)
    # a same-year duplicate keeps the lower pick
    picks2 = PK.load_draft_picks(_draft_dir(tmp_path / "b", {2008: [(127, 9, "C"), (3, 9, "C")]}))
    assert picks2[9] == {2008: 3}


def test_draft_history_outranks_the_sidecar_and_agreement_is_recorded(tmp_path):
    picks = PK.load_draft_picks(_draft_dir(tmp_path, {2014: [(7, 111, "A")]}))
    agree = PK.pick_for_row(_row("a", 2016, mlbam=111, acq_year=2014, pick=7), picks)
    assert agree["pick_source"] == PK.SOURCE_DRAFT and agree["pick_sidecar_agrees"] is True
    diff = PK.pick_for_row(_row("a", 2016, mlbam=111, acq_year=2014, pick=8), picks)
    assert diff["pick_overall_at_v"] == 7 and diff["pick_sidecar_agrees"] is False
    alone = PK.pick_for_row(_row("a", 2016, mlbam=111), picks)
    assert alone["pick_sidecar_agrees"] is None
    side = PK.pick_for_row(_row("b", 2016, mlbam=999, acq_year=2015, pick=40), picks)
    assert side["pick_source"] == PK.SOURCE_SIDECAR and side["pick_sidecar_agrees"] is None
    assert side["pick_draft_year"] == 2015


def test_draft_dir_absent_or_malformed_reads_as_no_pick(tmp_path):
    assert PK.load_draft_picks(tmp_path / "nowhere") == {}
    assert PK.draft_years_on_disk(tmp_path / "nowhere") == []
    d = tmp_path / "draft_history"
    d.mkdir()
    (d / "2010.json").write_text("not json", encoding="utf-8")
    (d / "notes.json").write_text("[]", encoding="utf-8")
    (d / "2011.json").write_text(json.dumps([{"pick": None, "mlbam": 5, "name": "x"},
                                             {"pick": 2, "mlbam": None, "name": "y"},
                                             {"pick": "9", "mlbam": "6", "name": "z"}]),
                                 encoding="utf-8")
    assert PK.draft_years_on_disk(d) == [2010, 2011]
    assert PK.load_draft_picks(d) == {6: {2011: 9}}


# ---------------------------------------------------------------------------
# 3. the column and its registration in the lab
# ---------------------------------------------------------------------------

def test_screen_column_is_log1p_pick_and_none_when_missing(tmp_path):
    picks = PK.load_draft_picks(_draft_dir(tmp_path, {2014: [(7, 111, "A"), (1, 222, "B")]}))
    frames = {"hit": {2016: ([_row("a", 2016, mlbam=111), _row("b", 2016, mlbam=None),
                              _row("c", 2016, mlbam=333, acq_year=2015, pick=90)],
                             ["labels the builder never reads"]),
                      2017: ([_row("d", 2017, mlbam=222)], None)},
              "pit": {2016: ([_row("p", 2016, mlbam=222, side="pit")], None)}}
    col = PK.screen_column("hit", frames, picks=picks)
    assert col == {(2016, "a"): math.log1p(7.0), (2016, "b"): None,
                   (2016, "c"): math.log1p(90.0), (2017, "d"): math.log1p(1.0)}
    assert PK.screen_column("pit", frames, picks=picks) == {(2016, "p"): math.log1p(1.0)}
    assert PK.TRANSFORM == "log1p" and PK.HEAD == "timing"
    assert PK.column_name("hit") == "pick_overall_time_hit"
    assert PK.column_name("pit") == "pick_overall_time_pit"
    with pytest.raises(ValueError):
        PK.column_name("both")
    with pytest.raises(ValueError):
        PK.screen_column("both", frames, picks=picks)


def test_lab_registers_the_pair_as_a_timing_head_retest_off_this_module(tmp_path):
    import efv_screen_lab as LAB
    picks_dir = _draft_dir(tmp_path, {2014: [(7, 111, "A")]})
    pick_arms = [c for c in LAB.CANDIDATES if c["name"].startswith("pick_overall")]
    assert [c["name"] for c in pick_arms] == ["pick_overall_time_hit", "pick_overall_time_pit"]
    for c in pick_arms:
        assert c["retest"] is True and c["head"] == "timing" and c["kind"] == "column"
        assert c["column"] == {"source": "module", "module": "efv_pick_features",
                               "attr": "screen_column"}
        assert c["name"] == PK.column_name(c["side"])
        assert "D4" in c["what"] and "EFV3_B4" in c["what"]
    names = [c["name"] for c in LAB.CANDIDATES]
    assert not any("seasons_at_level" in n or "bonus" in n for n in names)
    assert all(c["head"] != "skill" for c in pick_arms)
    # the lab's column source resolves to this module's values
    saved = PK.DRAFT_DIR
    PK.DRAFT_DIR = picks_dir
    try:
        frames = {"hit": {2016: ([_row("a", 2016, mlbam=111), _row("b", 2016)], None)}}
        vals = LAB.column_values(pick_arms[0], frames)
    finally:
        PK.DRAFT_DIR = saved
    assert vals == {(2016, "a"): math.log1p(7.0), (2016, "b"): None}


def test_retest_names_the_closed_arm_in_the_ledger():
    led = ROOT / "data" / "xfv_arm_ledger.json"
    if not led.exists():
        pytest.skip("data/xfv_arm_ledger.json not built")
    arms = json.loads(led.read_text(encoding="utf-8"))["arms"]
    closed = [a for a in arms if a["arm"].startswith(PK.RETEST_OF)]
    assert {a["side"] for a in closed} == {"hit", "pit"}
    assert all(a["cleared_own_floor"] is False for a in closed)
    assert all("pick_overall_time" not in a["arm"] for a in arms)


# ---------------------------------------------------------------------------
# 4. reserved vintages and the receipt
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("V", sorted(F.RESERVED_LV))
def test_reserved_vintages_raise_everywhere(V, tmp_path):
    picks = PK.load_draft_picks(_draft_dir(tmp_path, {2014: [(7, 111, "A")]}))
    with pytest.raises(F.ReservedFrameError):
        PK.pick_for_row(_row("a", V, mlbam=111), picks)
    with pytest.raises(F.ReservedFrameError):
        PK.attach_pick([_row("a", V, mlbam=111)], picks)
    with pytest.raises(F.ReservedFrameError):
        PK.screen_column("hit", {"hit": {V: ([_row("a", V, mlbam=111)], None)}}, picks=picks)


def test_coverage_receipt_counts_by_side_and_vintage_only(tmp_path):
    d = _draft_dir(tmp_path, {2013: [(7, 111, "A")], 2015: [(2, 222, "B")]})
    picks = PK.load_draft_picks(d)
    rows = PK.attach_pick([_row("a", 2016, mlbam=111, acq_year=2013, pick=7),
                           _row("b", 2016, mlbam=222), _row("c", 2016, mlbam=None),
                           _row("d", 2016, mlbam=333, acq_year=2015, pick=50)], picks)
    rec = PK.coverage_receipt({"hit": {2016: rows}}, draft_dir=d)
    blk = rec["by_side_vintage"]["hit:2016"]
    assert blk == {"rows": 4, "id_resolved": 3, "draft_history_pre_v": 2, "sidecar_only": 1,
                   "sidecar_known": 2, "with_pick": 3, "missing": 1,
                   "draft_years": {"2013": 1, "2015": 1}, "max_draft_year": 2015,
                   "median_pick": 7, "sidecar_both": 1, "sidecar_agrees": 1,
                   "sidecar_disagrees": 0}
    assert rec["draft_files"]["years"] == [2013, 2015] and rec["head"] == "timing"
    assert rec["transform"] == "log1p" and rec["indicator"] == "pick_missing"
    assert set(rec["by_side_vintage"]) == {"hit:2016"}
    # a pick dated at or after V can never be in a row; the receipt refuses one
    rows[1]["pick_draft_year"] = 2016
    with pytest.raises(ValueError):
        PK.coverage_receipt({"hit": {2016: rows}}, draft_dir=d)


# ---------------------------------------------------------------------------
# 5. no FV-cell grouping, no em-dash, the committed receipt
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [SRC, TOOL])
def test_no_fv_cell_grouping(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for name in _names(tree):
        low = name.lower()
        assert not any(t in low for t in _BANNED_TOKENS), (path.name, name)
    for node in ast.walk(tree):
        if path == SRC and isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            low = node.value.lower()
            assert not any(t in low for t in _BANNED_TOKENS), (path.name, node.value)


def test_no_em_dash_in_the_family():
    for p in (SRC, TOOL, Path(__file__)):
        txt = p.read_text(encoding="utf-8")
        assert chr(0x2014) not in txt and chr(0x2013) not in txt, p.name


def test_merge_pick_key_keeps_every_other_key_and_the_line_ending(tmp_path):
    import efv_pick_balance as PB
    p = tmp_path / "bal.json"
    base = {"generated_at": "x", "balance": {"hit": {"milb_absent": {"verdict": "BALANCED"}}},
            "text": {"balance": {}}, "probes": {"a": 1}, "n_probes": 1}
    p.write_bytes((json.dumps(base, indent=1) + "\n").replace("\n", "\r\n").encode())
    PB.merge_pick_key(p, {"balance": {"hit": {"pick_missing": {"verdict": "BALANCED"}}}})
    raw = p.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    doc = json.loads(raw)
    assert {k: doc[k] for k in base} == base
    assert doc["pick"]["balance"]["hit"]["pick_missing"]["verdict"] == "BALANCED"
    PB.merge_pick_key(p, doc["pick"])
    assert p.read_bytes() == raw
    assert PB.VINTAGES == tuple(F.DEV_VINTAGES) and PB.BALANCE_KEY == "pick"
    assert not set(PB.VINTAGES) & F.RESERVED_LV
    assert PB.INDICATOR == "pick_missing" and PB.REGISTRATION["head"] == "timing"


def test_committed_receipt_key_is_for_this_builder():
    art = ROOT / "data" / "efv_identity_balance.json"
    if not art.exists():
        pytest.skip("data/efv_identity_balance.json not built")
    doc = json.loads(art.read_text(encoding="utf-8"))
    if "pick" not in doc:
        pytest.skip("the pick key is not built yet")
    blk = doc["pick"]
    assert blk["builder"] == "efv_pick_features.py" and blk["role"] == "development"
    assert blk["head"] == "timing"
    assert not set(blk["guards"]["vintages_read"]) & F.RESERVED_LV
    assert blk["guards"]["reserved_vm_pins"] == []
    for side in F.SIDES:
        v = blk["balance"][side]["pick_missing"]["verdict"]
        assert v in ("BALANCED", "IMBALANCED", "CONSTANT")
        assert blk["offered_columns"][side] == [PK.column_name(side)]
    for key, c in blk["coverage"]["by_side_vintage"].items():
        side, V = key.split(":")
        assert c["max_draft_year"] is None or c["max_draft_year"] < int(V), key
        assert c["with_pick"] + c["missing"] == c["rows"], key
        assert c["draft_history_pre_v"] + c["sidecar_only"] == c["with_pick"], key
    for k in ("spearman", "auc", "delta"):
        assert k not in json.dumps(blk["coverage"])
