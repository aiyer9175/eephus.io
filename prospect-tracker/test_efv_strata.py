# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV3_D1 pins for the strata module (SP/efv3/LANE_D.md 3.1, 3.5 and 3.9).

1. The AST ban: efv_strata imports nothing from the repository (no label module,
   no WAR source) and no function reads a key matching
   (war|target|consensus_fv|fv_|grade|rank|tier|bust|reached|debut_year) except
   source_disagreement, which reads exactly grades, fangraphs and mlb_pipeline.
2. DIMENSIONS and BANNED_DIMENSIONS are pinned, with the amendment sentence.
3. Every assigner returns a value from its declared cell list or "unknown".
4. Fixture rows reproduce hand values for age band, level family, archetype and
   disagreement; the vm archetype restatement equals source_backtest._archetype.
5. The cells of each dimension partition a fixture frame.
6. No em-dash and no copy_lint BAN_RE hit in the module's strings; no key the
   ledger's _FV_CELL regex rejects.
"""
from __future__ import annotations

import ast
import math
import re
import sys
from pathlib import Path

import pytest

import efv_strata as S

ROOT = Path(__file__).parent
SRC = ROOT / "efv_strata.py"
sys.path.insert(0, str(ROOT / "tools"))

_BANNED_KEY = re.compile(r"(war|target|consensus_fv|fv_|grade|rank|tier|bust|reached|debut_year)")
_DISAGREEMENT_KEYS = {"grades", "fangraphs", "mlb_pipeline"}
_FV_CELL = re.compile(r"(?:^|[^0-9])(?:35|40|45|50|55|60|65|70)(?:\+|plus)?(?:$|[^0-9])|tier|fv_cell|fv_bucket",
                      re.IGNORECASE)
_NAN = float("nan")


def _tree():
    return ast.parse(SRC.read_text(encoding="utf-8"))


def _imports(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module.split(".")[0])
    return out


def _keys_read(node):
    """Every string constant used as a subscript index or as the first argument of
    a .get(...) call under `node`."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) \
                and isinstance(n.slice.value, str):
            out.append(n.slice.value)
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "get" and n.args \
                and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            out.append(n.args[0].value)
    return out


# ---------------------------------------------------------------------------
# 1. the AST ban
# ---------------------------------------------------------------------------

def test_module_imports_nothing_from_the_repository():
    assert _imports(_tree()) == {"__future__"}


def test_no_function_reads_an_outcome_or_grade_key_except_source_disagreement():
    tree = _tree()
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    names = {f.name for f in funcs}
    assert "source_disagreement" in names
    for f in funcs:
        keys = _keys_read(f)
        if f.name == "source_disagreement":
            assert set(keys) == _DISAGREEMENT_KEYS, keys
            assert sorted(keys) == sorted(_DISAGREEMENT_KEYS), keys   # each read once
        else:
            bad = [k for k in keys if _BANNED_KEY.search(k)]
            assert not bad, (f.name, bad)
    # module level (outside every function) reads no such key either
    top = ast.Module(body=[n for n in tree.body if not isinstance(n, ast.FunctionDef)],
                     type_ignores=[])
    assert not [k for k in _keys_read(top) if _BANNED_KEY.search(k)]


def test_module_opens_no_file_and_builds_no_frame():
    tree = _tree()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            fn = n.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
            assert name not in {"open", "read_text", "load", "loads", "build_frame",
                                "connect", "run_source_backtest"}, name


# ---------------------------------------------------------------------------
# 2. the dimensions, the ban list and the amendment sentence
# ---------------------------------------------------------------------------

def test_dimensions_pinned():
    assert S.DIMENSIONS == ("side", "position_family", "level_at_list", "age_band",
                            "list_year", "archetype", "source_disagreement")
    assert set(S.CELLS) == set(S.DIMENSIONS)
    assert S.CELLS["side"] == ("hit", "pit")
    assert S.CELLS["position_family"] == ("C", "IF", "OF")
    assert S.CELLS["level_at_list"] == ("AAA", "AA", "A+", "A", "CPX", "DSL", "none")
    assert S.CELLS["age_band"] == ("<=18", "19-20", "21-22", "23-24", ">=25", "unknown")
    assert S.CELLS["archetype"] == ("hs_bat", "hs_arm", "college_bat", "college_arm",
                                    "intl_bat", "intl_arm", "unknown_bat", "unknown_arm")
    assert S.CELLS["source_disagreement"] == ("gap_10_plus", "gap_under_10")
    assert "2017" in S.CELLS["list_year"] and "2021" in S.CELLS["list_year"]
    assert S.DIMENSION_SIDE == {"position_family": "hit"}
    assert S.DISCLOSED_DIMENSIONS == ("source_disagreement",)
    assert S.DISAGREEMENT_GAP_FV == 10


def test_banned_dimensions_pinned_with_the_amendment_sentence():
    assert S.BANNED_DIMENSIONS == (
        "consensus FV", "eFV grade", "any rater's FV", "tier", "top-N rank",
        "bonus band expressed through FV", "debuted", "reached", "label status")
    assert S.AMENDMENT_RULE == (
        "An FV-tier dimension may be added only by a dated amendment citing the anchor "
        "look record (docs/PROSPECT_ANCHOR_GATE.md section 18), after the later of "
        "2026-11-20 and 14 days after the fWAR epoch's step Z entry.")
    # no dimension names a banned thing and none is keyed on a grade level
    for d in S.DIMENSIONS:
        assert d not in S.BANNED_DIMENSIONS
        assert not _FV_CELL.search(d), d
        for c in S.CELLS[d]:
            assert not _FV_CELL.search(c), (d, c)


def test_frame_ids_are_the_ledger_frames_and_never_a_tilted_one():
    assert S.FRAME_KIND == {"vm2": "vm", "vm_pros": "vm", "bust_inclusive": "vm",
                            "lv_dev": "lv", "lv_res": "lv"}
    with pytest.raises(ValueError):
        S.assign("predebut", {"year": 2019})
    with pytest.raises(ValueError):
        S.assign("all_vintages", {"year": 2019})


# ---------------------------------------------------------------------------
# 3. every assigner returns a declared cell or unknown
# ---------------------------------------------------------------------------

_GARBAGE = [None, {}, {"side": "x"}, {"position": None}, {"position": "TWP"},
            {"position": "DH/OF", "birth_date": "19xx"}, {"milb": "AAA"},
            {"milb": {"milb_level": "Short-A", "milb_season": 2018}},
            {"milb": {"milb_level": None, "milb_season": None}},
            {"grades": None}, {"grades": {"fangraphs": "45", "mlb_pipeline": None}},
            {"grades": {"fangraphs": _NAN, "mlb_pipeline": 50}},
            {"birth_date": _NAN, "vintage": "2019"}, {"is_college": _NAN, "is_ifa": 1.0},
            {"acq_known_at_v": True, "side": "pit"}, {"year": 1999}, {"vintage": 2099}]


@pytest.mark.parametrize("row", _GARBAGE)
@pytest.mark.parametrize("frame_id", ["vm2", "lv_dev"])
def test_every_assigner_returns_a_declared_cell_or_unknown(frame_id, row):
    out = S.assign(frame_id, row, None)
    assert set(out) <= set(S.DIMENSIONS)
    for d, v in out.items():
        assert S.is_cell(d, v), (d, v)
    assert S.is_cell("side", S.side(row))
    assert S.is_cell("position_family", S.position_family(row))
    assert S.is_cell("level_at_list", S.level_at_list(row, 2019))
    assert S.is_cell("age_band", S.age_band(row, None, 2019))
    assert S.is_cell("archetype", S.archetype(frame_id, row))
    assert S.is_cell("source_disagreement", S.source_disagreement(row))
    assert S.is_cell("list_year", S.list_year((row or {}).get("year")))


# ---------------------------------------------------------------------------
# 4. hand values on fixture rows
# ---------------------------------------------------------------------------

def test_age_band_hand_values():
    assert S.age_band({"birth_date": "2001-03-04"}, None, 2019) == "<=18"
    assert S.age_band({"birth_date": "2000-12-31"}, None, 2019) == "19-20"
    assert S.age_band({}, {"birth_date": "1999-01-01"}, 2019) == "19-20"
    assert S.age_band({"birth_date": "1998-06-15"}, None, 2019) == "21-22"
    assert S.age_band({"birth_date": "1997-01-01"}, None, 2019) == "21-22"
    assert S.age_band({"birth_date": "1996-01-01"}, None, 2019) == "23-24"
    assert S.age_band({"birth_date": "1995-01-01"}, None, 2019) == "23-24"
    assert S.age_band({"birth_date": "1994-01-01"}, None, 2019) == ">=25"
    assert S.age_band({"birth_date": None}, None, 2019) == "unknown"
    assert S.age_band({"birth_date": "1996-01-01"}, None, None) == "unknown"


def test_level_family_hand_values():
    assert S.level_at_list({"milb": {"milb_level": "AA", "milb_season": 2018}}, 2019) == "AA"
    assert S.level_at_list({"milb": {"milb_level": "A+", "milb_season": 2018}}, 2019) == "A+"
    assert S.level_at_list({"milb": {"milb_level": "DSL", "milb_season": 2016}}, 2019) == "DSL"
    assert S.level_at_list({"milb": {"milb_level": "ROK", "milb_season": 2018}}, 2019) == "CPX"
    # a block from the debut season itself is not a fact known at the read (vm rows)
    assert S.level_at_list({"milb": {"milb_level": "AAA", "milb_season": 2019}}, 2019) == "none"
    assert S.level_at_list({"milb": None}, 2019) == "none"
    assert S.level_at_list({}, 2019) == "none"
    assert S.level_at_list({"milb": {"milb_level": "Indy", "milb_season": 2018}}, 2019) == "unknown"


def test_archetype_hand_values_vm_and_lv():
    # vm: the common row carries source_backtest's own archetype
    assert S.archetype("vm2", {"archetype": "hs_bat", "side": "hit"}) == "hs_bat"
    assert S.archetype("vm2", {"archetype": None, "side": "hit"}) == "unknown_bat"
    assert S.archetype("vm2", {"archetype": None, "side": "pit"}) == "unknown_arm"
    # vm: restated from the record when the row carries none
    rec = {"position": "SS", "birth_date": "1998-05-01",
           "acquisition": {"method": "draft", "year": 2016}}
    assert S.archetype("vm2", {"side": "hit"}, rec) == "hs_bat"
    rec = {"position": "RHP", "birth_date": "1996-05-01",
           "acquisition": {"method": "draft", "year": 2017}}
    assert S.archetype("vm2", {"side": "pit"}, rec) == "college_arm"
    rec = {"position": "OF", "acquisition": {"method": "international_fa", "year": 2015}}
    assert S.archetype("vm2", {"side": "hit"}, rec) == "intl_bat"
    assert S.archetype("vm2", {"side": "pit"}, {"position": "LHP"}) == "unknown_arm"
    # lv: the sidecar flags
    assert S.archetype("lv_dev", {"side": "hit", "is_college": 1.0, "acq_known_at_v": True}) == "college_bat"
    assert S.archetype("lv_dev", {"side": "pit", "is_ifa": 1.0, "acq_known_at_v": True}) == "intl_arm"
    assert S.archetype("lv_dev", {"side": "hit", "is_ifa": 0.0, "is_college": 0.0,
                                  "acq_known_at_v": True}) == "hs_bat"
    assert S.archetype("lv_dev", {"side": "pit", "acq_known_at_v": False}) == "unknown_arm"


def test_vm_archetype_restatement_equals_source_backtest():
    import source_backtest as SB
    recs = [
        {"position": "SS", "birth_date": "1998-05-01", "acquisition": {"method": "draft", "year": 2016}},
        {"position": "SS", "birth_date": "1997-05-01", "acquisition": {"method": "draft", "year": 2017}},
        {"position": "RHP", "birth_date": "1996-05-01", "acquisition": {"method": "draft", "year": 2017}},
        {"position": "LHP/OF", "birth_date": "2000-01-01", "acquisition": {"method": "draft", "year": 2018}},
        {"position": "OF", "acquisition": {"method": "international_fa", "year": 2015}},
        {"position": "RP", "acquisition": {"method": "international_fa"}},
        {"position": "TWP", "birth_date": "1998-05-01", "acquisition": {"method": "draft", "year": 2016}},
        {"position": "C", "acquisition": {"method": "draft", "year": 2016}},
        {"position": "C", "birth_date": "1998-05-01", "acquisition": {"method": "draft"}},
        {"position": "1B", "acquisition": {"method": "waiver"}},
        {"position": "", "acquisition": None},
        {},
    ]
    for rec in recs:
        assert S.vm_archetype(rec) == SB._archetype(rec), rec


def test_source_disagreement_hand_values():
    assert S.source_disagreement({"grades": {"fangraphs": 55, "mlb_pipeline": 45}}) == "gap_10_plus"
    assert S.source_disagreement({"grades": {"fangraphs": 40, "mlb_pipeline": 50}}) == "gap_10_plus"
    assert S.source_disagreement({"grades": {"fangraphs": 50, "mlb_pipeline": 45}}) == "gap_under_10"
    assert S.source_disagreement({"grades": {"fangraphs": 50, "mlb_pipeline": 50}}) == "gap_under_10"
    assert S.source_disagreement({"grades": {"fangraphs": 50, "mlb_pipeline": None}}) == "unknown"
    assert S.source_disagreement({"grades": {"fangraphs": None, "mlb_pipeline": 50}}) == "unknown"
    assert S.source_disagreement({"grades": {"fangraphs": 50}}) == "unknown"
    assert S.source_disagreement({"grades": {"fangraphs": _NAN, "mlb_pipeline": 50}}) == "unknown"
    assert S.source_disagreement({}) == "unknown"
    # the function reads the two source keys and never another grade
    assert S.source_disagreement({"grades": {"fangraphs": 50, "mlb_pipeline": 60,
                                             "prospx_consensus": 70, "xfv": 35}}) == "gap_10_plus"


def test_side_and_position_family_hand_values():
    assert S.side({"side": "pit"}) == "pit"
    assert S.side({}, {"position": "RHP"}) == "pit"
    assert S.side({}, {"position": "SS"}) == "hit"
    assert S.side({}, {"position": "TWP"}) == "unknown"
    assert S.side({}, {}) == "unknown"
    assert S.position_family({"position": "C"}) == "C"
    assert S.position_family({"position": "SS/2B"}) == "IF"
    assert S.position_family({}, {"position": "cf"}) == "OF"
    assert S.position_family({"position": "RHP"}) == "unknown"
    assert S.position_family({"position": "RP"}) == "unknown"
    assert S.position_family({}) == "unknown"


def test_assign_row_shape_and_the_hitter_only_dimension():
    hit = {"vintage": 2019, "side": "hit", "position": "SS", "birth_date": "1998-01-01",
           "milb": {"milb_level": "A+", "milb_season": 2018},
           "grades": {"fangraphs": 50, "mlb_pipeline": 40, "prospx_consensus": 45},
           "is_college": 0.0, "is_ifa": 0.0, "acq_known_at_v": True}
    pit = dict(hit, side="pit", position="RHP")
    assert S.assign("lv_dev", hit) == {
        "side": "hit", "position_family": "IF", "level_at_list": "A+", "age_band": "21-22",
        "list_year": "2019", "archetype": "hs_bat", "source_disagreement": "gap_10_plus"}
    out = S.assign("lv_dev", pit)
    assert "position_family" not in out
    assert out["side"] == "pit" and out["archetype"] == "hs_arm"
    assert S.applies("position_family", "hit") and not S.applies("position_family", "pit")
    assert all(S.applies(d, "pit") for d in S.DIMENSIONS if d != "position_family")
    # vm: base year is `year`, the record supplies position and birth date
    vm = {"key": "a", "year": 2021, "side": "hit", "archetype": "intl_bat",
          "grades": {"fangraphs": 50, "mlb_pipeline": 55, "prospx_consensus": 52},
          "milb": {"milb_level": "AA", "milb_season": 2020}}
    rec = {"position": "OF", "birth_date": "1999-07-01"}
    assert S.assign("vm2", vm, rec) == {
        "side": "hit", "position_family": "OF", "level_at_list": "AA", "age_band": "21-22",
        "list_year": "2021", "archetype": "intl_bat", "source_disagreement": "gap_under_10"}
    # the matrix block from the debut season itself reads "none" on vm
    assert S.assign("vm2", dict(vm, milb={"milb_level": "AAA", "milb_season": 2021}), rec)["level_at_list"] == "none"


# ---------------------------------------------------------------------------
# 5. the cells of each dimension partition a fixture frame
# ---------------------------------------------------------------------------

def _fixture_frame():
    rows = []
    levels = ["AAA", "AA", "A+", "A", "CPX", "DSL", None]
    for i in range(60):
        side = "hit" if i % 2 == 0 else "pit"
        pos = ["C", "SS", "OF", "1B", "DH", "UT"][i % 6] if side == "hit" else ["RHP", "LHP", "P"][i % 3]
        row = {"vintage": 2017 + i % 3, "side": side, "position": pos,
               "birth_date": None if i % 7 == 0 else f"{1993 + i % 10}-06-01",
               "milb": None if i % 11 == 0 else {"milb_level": levels[i % 7], "milb_season": 2016 + i % 3},
               "grades": {"fangraphs": None if i % 13 == 0 else 40 + i % 25,
                          "mlb_pipeline": 45 + (i * 3) % 20},
               "is_college": float(i % 4 == 0), "is_ifa": float(i % 4 == 1),
               "acq_known_at_v": i % 5 != 0}
        rows.append(row)
    rows.append({"vintage": 2018, "side": "hit", "position": "TWP"})
    return rows


def test_cells_of_each_dimension_partition_the_frame():
    rows = _fixture_frame()
    counts = S.count_cells("lv_dev", rows)
    assert set(counts) == set(S.DIMENSIONS)
    n_by_side = {}
    for r in rows:
        n_by_side[S.side(r)] = n_by_side.get(S.side(r), 0) + 1
    for d in S.DIMENSIONS:
        want = sum(n for s, n in n_by_side.items() if S.applies(d, s))
        got = sum(c["all"] for c in counts[d].values())
        assert got == want, (d, got, want)
        assert all(S.is_cell(d, cell) for cell in counts[d]), (d, list(counts[d]))
        for cell, c in counts[d].items():
            assert c["all"] >= c["hit"] + c["pit"], (d, cell, c)
    # a row lands in exactly one cell per applicable dimension, and the same cell twice
    for r in rows:
        a, b = S.assign("lv_dev", r), S.assign("lv_dev", r)
        assert a == b
        assert set(a) == {d for d in S.DIMENSIONS if S.applies(d, a["side"])}
    assert counts["side"]["hit"]["all"] + counts["side"]["pit"]["all"] + \
        counts["side"].get("unknown", {"all": 0})["all"] == len(rows)
    assert "unknown" in counts["age_band"] and "none" in counts["level_at_list"]


def test_count_cells_accepts_records_by_key():
    rows = [{"key": "a", "year": 2019, "grades": {"fangraphs": 50, "mlb_pipeline": 50}},
            {"key": "b", "year": 2019, "grades": {"fangraphs": 50, "mlb_pipeline": 65}}]
    recs = {"a": {"position": "SS", "birth_date": "1997-01-01"},
            "b": {"position": "RHP", "birth_date": "1994-01-01"}}
    counts = S.count_cells("vm2", rows, recs)
    assert counts["side"] == {"hit": {"all": 1, "hit": 1, "pit": 0}, "pit": {"all": 1, "hit": 0, "pit": 1}}
    assert counts["position_family"] == {"IF": {"all": 1, "hit": 1, "pit": 0}}
    assert counts["age_band"] == {"21-22": {"all": 1, "hit": 1, "pit": 0}, ">=25": {"all": 1, "hit": 0, "pit": 1}}
    assert counts["source_disagreement"] == {"gap_under_10": {"all": 1, "hit": 1, "pit": 0},
                                             "gap_10_plus": {"all": 1, "hit": 0, "pit": 1}}


# ---------------------------------------------------------------------------
# 6. copy: no em-dash, no banned word, no FV-cell key
# ---------------------------------------------------------------------------

def test_no_emdash_and_no_banned_word_in_the_module():
    from copy_lint import BAN_RE
    text = SRC.read_text(encoding="utf-8")
    assert "—" not in text and "–" not in text
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert not BAN_RE.search(node.value), node.value
            assert "—" not in node.value and "–" not in node.value
    assert not BAN_RE.search(S.AMENDMENT_RULE)
    assert not BAN_RE.search(ast.get_docstring(_tree()) or "")


def test_no_fv_cell_key_in_any_output():
    rows = _fixture_frame()
    for r in rows:
        for d, v in S.assign("lv_dev", r).items():
            assert not _FV_CELL.search(d) and not _FV_CELL.search(v), (d, v)
    for d, cells in S.count_cells("lv_dev", rows).items():
        for cell in cells:
            assert not _FV_CELL.search(cell), (d, cell)
    # the module's own string constants never name a cell by grade level
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 40:
            assert not re.search(r"fv_cell|fv_bucket|by_fv", node.value.lower()), node.value
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}, (node.value, node.lineno)
    assert math.isnan(_NAN)
