# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The DvM+ difficulty arm, off: storage.DVM_DIFFICULTY_ARM None serves today's DvM+.

DVM-5 of the Part 8 dvm_difficulty lane builds the difficulty-adjusted DvM+ behind
storage.DVM_DIFFICULTY_ARM. While the arm is None (every build until the owner's flip,
DVM-6) every DvM+ field of org_summary must be byte-identical to the FV-trajectory
method. The golden test_fixtures/dvm_flag_identity_golden.json holds those fields (and
farm_dev_spec) from a pre-change export of 2026-10-09; the arm-None path below runs the
same functions the export runs and must leave them byte for byte. An end-to-end export
before and after the change (11,745 files, timeseries.json differing only in
generated_at) is recorded in the build commit.
"""
from __future__ import annotations

import ast
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import storage  # noqa: E402

GOLDEN = ROOT / "test_fixtures" / "dvm_flag_identity_golden.json"


def _golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")


def test_the_arm_ships_off():
    assert storage.DVM_DIFFICULTY_ARM is None
    assert storage.DVM_DIFFICULTY_ARMS == ("value", "difficulty")


def test_arm_none_returns_no_result_and_reads_nothing(monkeypatch, tmp_path):
    for mod in ("dvm_difficulty_serve", "dvm_difficulty_lab"):
        monkeypatch.delitem(sys.modules, mod, raising=False)
    opened = []
    real_open = open

    def spy(path, *a, **k):
        opened.append(str(path))
        return real_open(path, *a, **k)
    monkeypatch.setattr("builtins.open", spy)
    res = storage._dvm_difficulty_result(attribution=None, as_of="2026-10-09",
                                         bucket_of={}, actives=["a", "b"])
    assert res is None
    assert "dvm_difficulty_serve" not in sys.modules and "dvm_difficulty_lab" not in sys.modules
    assert not any("dvm_difficulty" in p for p in opened)


def test_every_dvm_field_of_org_summary_is_byte_identical_with_the_arm_none():
    g = _golden()
    org_summary = copy.deepcopy(g["org_summary"])
    assert len(org_summary) == 30
    res = storage._dvm_difficulty_result(attribution=None, as_of="2026-10-09",
                                         bucket_of={}, actives=[])
    storage._apply_dvm_difficulty_tools(org_summary, res)
    storage._apply_dvm_difficulty_fv(org_summary, res)
    for got, want in zip(org_summary, g["org_summary"]):
        for key in want:
            assert _bytes(got[key]) == _bytes(want[key]), (want["org"], key)
        assert set(got) == set(want), "the arm-None path adds no key (no dev_expectation)"


def test_farm_dev_spec_is_byte_identical_with_the_arm_none():
    g = _golden()
    assert _bytes(storage.farm_dev_spec()) == _bytes(g["farm_dev_spec"])
    assert _bytes(storage.farm_dev_spec(None)) == _bytes(g["farm_dev_spec"])
    assert "dvm_difficulty" not in storage.farm_dev_spec(None)


def _export_source() -> ast.FunctionDef:
    tree = ast.parse((ROOT / "storage.py").read_text(encoding="utf-8"))
    return next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "export_timeseries_json")


def test_the_export_binds_the_result_only_under_the_arm():
    fn = _export_source()
    binds = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "_dvm_diff" for t in n.targets)]
    assert len(binds) == 1, "one binding of the arm's result"
    v = binds[0].value
    assert isinstance(v, ast.IfExp) and isinstance(v.orelse, ast.Constant) and v.orelse.value is None
    assert "DVM_DIFFICULTY_ARM is not None" in ast.unparse(v.test)


def test_every_use_of_the_result_is_inert_on_none():
    fn = _export_source()
    src = ast.unparse(fn)
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id.startswith("_apply_dvm_difficulty")]
    assert {c.func.id for c in calls} == {"_apply_dvm_difficulty_fv", "_apply_dvm_difficulty_tools"}
    assert "_dvm_diff['spec'] if _dvm_diff is not None else None" in src
    assert "if _dvm_diff is not None:" in src, "the player index swap is guarded"
    # the swap is the only other write the result drives
    guarded = [n for n in ast.walk(fn) if isinstance(n, ast.If)
               and ast.unparse(n.test) == "_dvm_diff is not None"]
    assert len(guarded) == 1
    assert ast.unparse(guarded[0].body[0]).startswith("_dollar_dvm_by_key = ")


def test_a_failure_with_the_arm_on_keeps_the_trajectory_dvm(monkeypatch, tmp_path):
    import dvm_difficulty_serve as dds
    monkeypatch.setattr(dds, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dds, "_FIXTURE", None)
    res = storage._dvm_difficulty_result(attribution=None, as_of="2026-10-09",
                                         bucket_of={}, actives=[], arm="value")
    assert res is None, "no frozen table: logged, nothing replaced"


@pytest.mark.parametrize("table", [{}, {"receipt": {"fixture": True}},
                                   {"frame_receipt": {"fixture": True}}])
def test_the_arm_serves_only_the_looks_own_table(table, monkeypatch):
    import dvm_difficulty_serve as dds
    monkeypatch.setattr(dds, "_FIXTURE", None)
    with pytest.raises(dds.ArmError):
        dds.require_look_table(table)
    assert dds.require_look_table({"frame_receipt": {"today": "2027-02-01"}})["today"] == "2027-02-01"
