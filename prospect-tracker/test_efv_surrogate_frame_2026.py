# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The V 2026 rater freeze (task SG_4B; docs/efv-v2/SURROGATE_2026_GATE.md Q5, s2.2, s4,
s8.13): data/efv_surrogate_frame_2026.json is pinned by sha256 and its rows are checked
for timing (no input dated at or after a row's window end, the ETA shadow join and the
protection cutoff included), for the absence of any 2026 season line in a feature, for
the absence of any outcome column, and for the named V2 object with its twin and head
indices beside it. The freeze tool is scanned for FV-level grouping like the frame
modules are, and a re-freeze is refused.

Nothing here reads an outcome, a label or a score against anything.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

import efv_vintage_frame as F

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
import efv_surrogate_freeze_2026 as FZ  # noqa: E402

FREEZE = ROOT / "data" / "efv_surrogate_frame_2026.json"
#: The frozen bytes (git stores them as is: data/efv_surrogate_*.json is -text).
FREEZE_SHA256 = "1c7823316b697dbbf107416379e54711bd1e10dc270a7db6c998ed268b9cf9b8"

_OUTCOME_WORDS = ("w3", "w2", "r3", "l6", "war", "debut", "reached", "outcome", "label",
                  "status", "bust", "never", "career", "contributor", "season_2026")
_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin")


@pytest.fixture(scope="module")
def doc() -> dict:
    return json.loads(FREEZE.read_bytes().decode("utf-8"))


def _rows(doc):
    for side in FZ.SIDES:
        for r in doc["rows"][side]:
            yield side, r


def _keys(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{prefix}{k}"
            yield from _keys(v, f"{prefix}{k}.")
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v, prefix)


def test_frozen_bytes_are_pinned():
    assert FREEZE.exists()
    assert hashlib.sha256(FREEZE.read_bytes()).hexdigest() == FREEZE_SHA256


def test_frozen_by_sg_4b_from_the_snapshot_and_the_bundle(doc):
    assert doc["frozen_by"] == "SG_4B" and doc["frame"] == "lv_2026"
    assert doc["vintage"] == 2026
    assert doc["snapshot"]["manifest_head"] == FZ.SNAPSHOT_HEAD
    assert doc["snapshot"]["path"] == "../_pre_epoch_fwar_2026-10/"
    assert doc["step_z_entry"]["heading"] == FZ.STEP_Z_HEADING
    assert doc["universe"]["is_step_a_snapshot"] is False
    assert {f: v["sha256"] for f, v in doc["universe"]["files"].items()} == FZ.UNIVERSE_SHA256
    for rel, info in doc["snapshot"]["inputs"].items():
        assert len(info["sha256"]) == 64, rel
    assert doc["asserted"]["resolved_through"] == 2025
    assert doc["asserted"]["default_provider"] == "ewar_v2"
    assert doc["label"]["provider"] == "ewar_v2"
    assert doc["label"]["resolved_through"] == 2025
    assert doc["asserted"]["reserved_lv"] == sorted(F.RESERVED_LV)
    assert doc["asserted"]["reserved_vm_pins"] == []
    assert len(doc["head_at_freeze"]) == 40


def test_counts_match_the_rows(doc):
    for side in FZ.SIDES:
        rows = doc["rows"][side]
        assert len(rows) == doc["counts"]["matched"][side]["rows"]
        assert sum(1 for r in rows if r["person_id"] is not None) == \
            doc["counts"]["matched"][side]["person_ids"]
        assert doc["counts"]["retaken"][side]["rows"] >= len(rows)
        assert len({r["player_key"] for r in rows}) == len(rows)
        for r in rows:
            assert r["side"] == side and r["vintage"] == 2026
    assert doc["counts"]["s2_2"] == FZ.S22_COUNTS
    assert doc["counts"]["s2_2_at_draft"] == FZ.S22_COUNTS_AT_DRAFT
    assert doc["gate"]["owner_answers"]["SG4B-Q2"] == "A"
    if doc["recount"] is None:
        for side in FZ.SIDES:
            assert doc["counts"]["retaken"][side] == FZ.S22_COUNTS[side]
    else:
        for side in FZ.SIDES:
            d = doc["recount"]["difference"][side]
            assert abs(d["rows"]) <= FZ.RECOUNT_MAX and abs(d["person_ids"]) <= FZ.RECOUNT_MAX
            assert abs(d["rows"]) <= doc["recount"]["marked"][side]
            assert len(doc["recount"]["excluded_rows"][side]) == doc["recount"]["marked"][side]
            assert all(not r.get("recount_split") for r in doc["rows"][side])


def test_no_input_after_the_window_end(doc):
    for side, r in _rows(doc):
        lo, hi = r["window"]
        assert lo == "2026-01-01" and hi <= "2026-05-01", r["player_key"]
        assert lo <= r["asof_date"] < hi, r["player_key"]
        for d in r["source_dates"]:
            assert d < hi, (r["player_key"], d)
        assert r["real_sources"], r["player_key"]
        assert r["protection"]["cutoff"] == lo
        if r["bmi_asof_date"]:
            assert r["bmi_asof_date"] < hi
        eta = r["eta"]
        if eta is not None:
            assert eta["listing_date"] < hi, (r["player_key"], eta["listing_date"])
    for side in FZ.SIDES:
        n = sum(1 for r in doc["rows"][side] if r["eta"] is not None)
        assert n == doc["eta_shadow"]["joined"][side]
        assert doc["eta_shadow"]["joined"][side] + doc["eta_shadow"]["absent"][side] \
            + doc["eta_shadow"]["listing_at_or_after_window_end"][side] \
            == doc["counts"]["retaken"][side]["rows"]


def test_no_2026_season_line_in_any_feature(doc):
    for side, r in _rows(doc):
        if r["milb_last_season"] is not None:
            assert r["milb_last_season"] <= 2025, r["player_key"]
        if r["milb_block"]:
            assert r["milb_last_season"] is not None
    for side in FZ.SIDES:
        rec = doc["v2_object"]["fold_receipt"][side]
        assert max(rec["train_years"]) <= 2019 and min(rec["train_years"]) >= 2011
        v1 = doc["efv_v1"]["receipt"][side]
        assert max(v1["train_decision_years"]) <= 2025
        late = v1["rows_at_or_after_v"]
        assert v1["matrix_rows"] == v1["n_train"] + v1["n_train_excluded_in_frame"] \
            + late["n"]
        assert len(late["player_keys"]) == late["n"]
        frame_keys = {r["player_key"] for r in doc["rows"][side]}
        # a late matrix row's player may sit on the V 2026 list; that frame row is
        # scored from its own in-window drivers and the matrix row trains nothing
        assert set(late["in_frame"]) == frame_keys & set(late["player_keys"])
        for r in doc["rows"][side]:
            if r["player_key"] in late["in_frame"]:
                assert r["asof_date"] < r["window"][1] and r["efv_v1"] is not None
        assert all(y >= 2026 for y in late["decision_years"])


def test_no_outcome_column(doc):
    for side, r in _rows(doc):
        for k in _keys(r):
            low = k.lower()
            assert not any(w in low for w in _OUTCOME_WORDS), (r["player_key"], k)
    assert doc["rules"]["outcome_columns"].startswith("none")


def test_the_named_v2_object_with_its_twin_and_head_indices(doc):
    v2 = doc["v2_object"]
    assert v2["name"] == FZ.V2_OBJECT_NAME
    for phrase in ("V2 list-vintage fold V = 2026", "eWAR v2 label, RT 2025",
                   "DS-08 draft weights", FZ.ASSEMBLY_BLOB,
                   "fWAR re-derivation is not applied"):
        assert phrase in v2["name"], phrase
    assert v2["assembly_blob"] == FZ.ASSEMBLY_BLOB
    assert doc["code"]["blobs"]["data/efv_v2_assembly.json"] == FZ.ASSEMBLY_BLOB
    assert len(v2["sha256"]) == 64
    assert doc["twin"]["seed"] == 20260931
    for side in FZ.SIDES:
        rec = v2["fold_receipt"][side]
        assert rec["n_train"] > 0 and rec["n_train_excluded_in_frame_players"] >= 0
        assert "skill_head" in rec and "timing_head" in rec
        for r in doc["rows"][side]:
            assert r["v2"] is not None and r["twin"] is not None, r["player_key"]
            for f in ("u_c", "e_skill", "e_time", "order_idx", "efv_grade"):
                assert isinstance(r["v2"][f], float) and isinstance(r["twin"][f], float)
            assert r["twin"]["u_c"] == r["v2"]["u_c"], r["player_key"]
            assert set(r["grades"]) == {"prospx_consensus", "mlb_pipeline", "fangraphs"}
            assert r["grades"]["prospx_consensus"] is not None
    assert sum(v2["fold_receipt"][s]["n_train_excluded_in_frame_players"]
               for s in FZ.SIDES) >= 1


def test_rows_hash_is_self_consistent(doc):
    assert doc["rows_sha256"] == FZ.canonical_sha256(doc["rows"])


def test_re_freeze_is_refused(tmp_path):
    p = tmp_path / "efv_surrogate_frame_2026.json"
    p.write_text("{}", encoding="utf-8")
    with pytest.raises(FZ.FreezeRefused):
        FZ.refuse_if_frozen(p)
    with pytest.raises(FZ.FreezeRefused):
        FZ.write_freeze({}, p)
    assert p.read_text(encoding="utf-8") == "{}"
    FZ.refuse_if_frozen(tmp_path / "absent.json")


def test_the_freeze_is_kept_off_the_webroot():
    lines = (ROOT / "deploy" / "data_exclude.txt").read_text(encoding="utf-8").split("\n")
    assert "efv_surrogate_frame_2026.json" in [ln.strip() for ln in lines]


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


def test_tool_has_no_fv_cell_grouping_and_the_frame_imports_no_label_module():
    tree = ast.parse((ROOT / "tools" / "efv_surrogate_freeze_2026.py").read_text(
        encoding="utf-8"))
    for name in _names(tree):
        assert not any(t in name.lower() for t in _BANNED_TOKENS), name
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)
    frame = ast.parse((ROOT / "efv_vintage_frame.py").read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(frame) if isinstance(n, (ast.Import, ast.ImportFrom))
                for a in n.names} | {n.module for n in ast.walk(frame)
                                     if isinstance(n, ast.ImportFrom) and n.module}
    assert not imported & {"efv_labels", "war_source", "ewar", "stats"}, imported
