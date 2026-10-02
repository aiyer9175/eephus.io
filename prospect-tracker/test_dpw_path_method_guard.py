# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The method guard (docs/dpw-2026-09-25/DPW_PATH_GATE.md sections 9, 11, 12, 16).

DPW_PATH_METHOD reads carry_const, or robust_drift only while the registered
SERVE CONDITION holds, read ONLY from the dpw_path_gate block of
data/dpw_forecast_eval.json (verdict, blind status, owner_at_amendment, and
owner_after_look for OD-7 option zero_if_floor while INCUMBENT_BELOW_FLOOR is
true), by option CODE, never from the live data/dpw_path_owner.json. The owner
record itself is append-only and hash-chained.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

import dpw_path as dp

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def _gate_block():
    p = DATA / "dpw_forecast_eval.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8")).get("dpw_path_gate")


def _block(verdict="PASS_DEV", status="PENDING", od6=None, od7=None, ibf=None, oal=None):
    oaa = {"OD-6": None if od6 is None else {"option": od6, "date": "2026-11-01", "row_sha256": "x" * 64},
           "OD-7": None if od7 is None else {"option": od7, "date": "2026-11-01", "row_sha256": "y" * 64},
           "chain_head_sha256": "z" * 64, "row_count": 7}
    b = {"verdict": verdict, "blind_status": status, "owner_at_amendment": oaa}
    if ibf is not None:
        b["flags"] = {"INCUMBENT_BELOW_FLOOR": ibf}
    if oal is not None:
        b["owner_after_look"] = {"OD-7": {"option": oal, "date": "2027-01-01", "row_sha256": "w" * 64},
                                 "chain_head_sha256": "v" * 64, "row_count": 8}
    return b


def test_the_method_defaults_to_carry_const_with_no_environment_override():
    assert dp.DPW_PATH_METHOD == "carry_const"
    src = Path(dp.__file__).read_text(encoding="utf-8")
    assert "os.environ" not in src and "getenv" not in src and "import os" not in src


def test_the_committed_method_is_permitted_by_the_committed_gate_block():
    """THE GUARD: whatever DPW_PATH_METHOD reads must be permitted by the block
    as it stands on disk (absent until the pre-look amendment)."""
    assert dp.method_permitted(dp.DPW_PATH_METHOD, _gate_block())
    assert dp.resolve_method(_gate_block()) == dp.DPW_PATH_METHOD


def test_the_serve_condition_by_od6_code():
    sc = dp.serve_condition
    # (i) the conservative default: confirmation, also with no OD-6 row
    assert sc(_block(status="PENDING")) is False
    assert sc(_block(status="CONFIRMED")) is True
    assert sc(_block(status="PENDING", od6="confirm_first")) is False
    assert sc(_block(status="CONFIRMED", od6="confirm_first")) is True
    # (ii) serve at the development pass, the veto armed (the recorded answer)
    assert sc(_block(status="PENDING", od6="serve_at_dev_pass")) is True
    assert sc(_block(status="VETOED", od6="serve_at_dev_pass")) is False
    # never
    assert sc(_block(status="CONFIRMED", od6="never")) is False
    # no pass, no serve
    for v in ("NULL", "NULL_UNDERPOWERED", "WORSE", "VOID", "NOT_AVAILABLE"):
        assert sc(_block(verdict=v, status="CONFIRMED", od6="serve_at_dev_pass")) is False
    assert sc(None) is False
    assert dp.method_permitted("robust_drift", _block(status="PENDING", od6="serve_at_dev_pass"))
    for m in ("damped", "trend_line", "carry_destale", "carry_zero"):
        assert not dp.method_permitted(m, _block(status="CONFIRMED"))


def test_a_pass_under_serve_at_dev_pass_serves_2027_to_2031_with_the_taper():
    """OD-6 serve_at_dev_pass (recorded 2026-09-30): a PASS_DEV serves
    robust_drift for N+1..N+5 with the taper; two consecutive blind misses
    reverse it (dp.blind_status)."""
    blk = _block(status="PENDING", od6="serve_at_dev_pass")
    method = dp.resolve_method(blk, "robust_drift")
    path = dp.build_path(16e6, 2026, method=method, g_ref=0.0409, g_a=0.02)
    assert [s for s, k in dp.path_kinds(2026, method).items() if k == "forecast"] == list(range(2027, 2032))
    assert path[2036] == pytest.approx(16e6 * 1.0409 ** 10)
    reverted = dp.blind_status("PASS_DEV", "serve_at_dev_pass",
                               [{"side": "C", "regime": False}, {"side": "C", "regime": False}])
    assert reverted == {"status": "VETOED", "reverted": True}
    assert dp.serve_condition({**blk, "blind_status": reverted["status"]}) is False


def test_codes_only_never_an_option_number_or_text():
    for bad in ("2", 2, "Serve at the past-winter pass", "SERVE_AT_DEV_PASS", "option 2"):
        with pytest.raises(dp.DpwPathError):
            dp.serve_condition({"verdict": "PASS_DEV", "blind_status": "PENDING",
                                "owner_at_amendment": {"OD-6": {"option": bad}}})
    with pytest.raises(dp.DpwPathError):
        dp.serve_condition({"verdict": "PASSED", "blind_status": "PENDING"})
    with pytest.raises(dp.DpwPathError):
        dp.serve_condition({"verdict": "PASS_DEV", "blind_status": "MAYBE"})
    for bad in ("1", 1, "keep 4.09 percent"):
        with pytest.raises(dp.DpwPathError):
            dp.validate_owner_row({"id": "OD-7", "option": bad})
    with pytest.raises(dp.DpwPathError):
        dp.validate_owner_row({"id": "OD-9", "option": "x"})
    with pytest.raises(dp.DpwPathError):
        dp.validate_owner_row({"id": "OD-2", "option": "r_other"})          # R missing
    dp.validate_owner_row({"id": "OD-2", "option": "r_other", "R": 0.105})


def test_the_od7_rule_reads_owner_at_amendment_and_owner_after_look_only():
    assert dp.g_ref_rule(None) == "keep_0409"
    assert dp.g_ref_rule(_block()) == "keep_0409"
    assert dp.g_ref_rule(_block(od7="remeasure_served_rule")) == "remeasure_served_rule"
    # option (c) exists only after the look, and only while the flag stands
    assert dp.g_ref_rule(_block(od7="remeasure_served_rule", ibf=True, oal="zero_if_floor")) == "zero_if_floor"
    assert dp.g_ref_rule(_block(od7="remeasure_served_rule", ibf=False, oal="zero_if_floor")) == \
        "remeasure_served_rule"
    with pytest.raises(dp.DpwPathError):
        dp.g_ref_rule(_block(od7="zero_if_floor"))
    assert dp.g_ref_value("keep_0409") == 0.0409
    assert dp.g_ref_value("zero_if_floor") == 0.0
    truth = {2015 + i: 9e6 * 1.03 ** i for i in range(12)}
    assert dp.g_ref_value("remeasure_served_rule", truth, 2026) == pytest.approx(0.03, rel=1e-9)
    # measured once per N, never re-estimated nightly
    prev = {"g_ref_rule": "remeasure_served_rule", "g_ref_measured_at_n": 2026, "g_ref": 0.0311}
    assert dp.g_ref_value("remeasure_served_rule", truth, 2026, previous=prev) == 0.0311


def test_no_code_path_reads_od6_or_od7_from_the_live_owner_file(monkeypatch, tmp_path):
    """The live owner file holds serve_at_dev_pass and remeasure_served_rule
    today; with no gate block the guard still reads the conservative defaults."""
    import fa_market as fm
    owner = json.loads((DATA / "dpw_path_owner.json").read_text(encoding="utf-8"))
    assert dp.last_answer(owner, "OD-6")["option"] == "serve_at_dev_pass"
    assert dp.serve_condition(None) is False and dp.g_ref_rule(None) == "keep_0409"
    for fn in (dp.serve_condition, dp.g_ref_rule, dp.method_permitted, dp.resolve_method,
               fm.build_dpw_path_block):
        src = inspect.getsource(fn)
        assert not re.search(r'(last_answer|owner_record_for_block)\([^)]*"OD-[67]"', src), fn.__name__
    # the writer takes its rule and its method from the gate block alone
    src = inspect.getsource(fm.build_dpw_path_block)
    assert "dp.g_ref_rule(gate)" in src and "dp.resolve_method(gate)" in src
    assert "owner_record_for_block" not in src
    # and no module but the writer resolves a path to the owner file
    readers = []
    for p in list(ROOT.glob("*.py")) + list((ROOT / "tools").glob("*.py")):
        if p.name.startswith("test_") or p.name in ("conftest.py", "dpw_testkit.py"):
            continue
        if re.search(r'/\s*"dpw_path_owner\.json"', p.read_text(encoding="utf-8", errors="replace")):
            readers.append(p.name)
    assert sorted(readers) in (["fa_market.py"], ["dpw_path_gate.py", "fa_market.py"]), readers


def test_the_last_row_for_an_id_binds():
    rows = []
    dp.append_chained(rows, {"id": "OD-1", "date": "2026-09-30", "option": "round_trip"})
    dp.append_chained(rows, {"id": "OD-3", "date": "2026-09-30", "option": "base_2027"})
    dp.append_chained(rows, {"id": "OD-1", "date": "2026-10-10", "option": "sticker"})
    doc = {"schema": dp.OWNER_SCHEMA, "answers": rows}
    assert dp.convention(doc, "level_basis") == "sticker"
    assert dp.convention(doc, "trade_machine") == "align"            # default, unanswered
    rec = dp.owner_record_for_block(doc)
    assert rec["OD-6"] is None and rec["row_count"] == 3
    assert rec["chain_head_sha256"] == dp.sha256_of(rows[-1])


def test_the_owner_record_is_chained_and_holds_the_recorded_codes():
    doc = json.loads((DATA / "dpw_path_owner.json").read_text(encoding="utf-8"))
    rows = dp.validate_owner_doc(doc)
    assert [r["id"] for r in rows] == ["OD-6", "OD-7", "OD-2", "OD-1", "OD-3", "OD-4", "OD-5"]
    assert {r["id"]: r["option"] for r in rows} == {
        "OD-6": "serve_at_dev_pass", "OD-7": "remeasure_served_rule", "OD-2": "r_0113763",
        "OD-1": "round_trip", "OD-3": "base_2027", "OD-4": "own_trends", "OD-5": "align"}
    assert dp.last_answer(doc, "OD-8") is None
    for r in rows:
        assert re.fullmatch(r"_audit_2026-09-09/DECISIONS_FOR_OWNER\.md:\d+", r["source"])
        assert r["date"] == "2026-09-30" and r["answer"] and r["question"]
    # an edited row breaks the chain
    rows[2] = {**rows[2], "option": "r_010"}
    with pytest.raises(dp.DpwPathError):
        dp.verify_chain(rows)
    assert dp.nominal_rate_from_owner(doc) == 0.113763


def test_the_owner_record_does_not_ship():
    excl = (ROOT / "deploy" / "data_exclude.txt").read_text(encoding="utf-8").split()
    assert "dpw_path_owner.json" in excl
