# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The registered identity repairs run as a receipt-guarded daily step (B4ID-2, PVA-2).

Owner answers of 2026-10-01: the deploy box keeps its own prospects.db, so the
repairs tools/repair_identity_split_2026_09_30.py applied locally must reach the
box through its own nightly, never by hand. The fWAR label epoch's step A
(EPOCH_RUN, 2026-10-03) wired `run_step()` into run_monthly.run_daily as step
d00, BEFORE every capture and exporter. This file pins the wiring by source
(the step name, the function, its position) so a later edit of run_daily cannot
drop it silently; test_identity_repairs.py pins run_step's own behaviour
(receipt skip, one backup, refusal without a receipt).
"""

from __future__ import annotations

import inspect
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _run_daily_source() -> str:
    import run_monthly
    return inspect.getsource(run_monthly.run_daily)


def test_the_daily_chain_runs_the_identity_repair_step_first():
    src = _run_daily_source()
    assert "d00. Registered identity repairs" in src
    assert "repair_identity_split_2026_09_30 as _idr" in src
    assert "_idr.run_step()" in src
    # before the first capture and therefore before every exporter
    assert src.index("d00. Registered identity repairs") < src.index("d0. TJStats Live capture")
    # the night's closing rebuild (the last call in run_daily) comes after it; rindex
    # skips the docstring's mention of the same name
    assert src.index("d00. Registered identity repairs") < src.rindex("rebuild_only(")


def test_the_step_never_aborts_the_night_and_records_a_heartbeat():
    src = _run_daily_source()
    block = src[src.index("d00. Registered identity repairs"):src.index("d0. TJStats Live capture")]
    assert "except Exception" in block, "a crashed repair must not end the night"
    assert '_idr_hb.record("identity_repairs"' in block


def test_run_step_reads_the_registered_list_and_the_receipt_file():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "repair_tool", HERE / "tools" / "repair_identity_split_2026_09_30.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    src = inspect.getsource(tool.run_step)
    assert "identity_repairs.REPAIRS" in src
    assert "receipted_ids(" in src
    assert tool.RECEIPTS.name == "receipts.jsonl"
    assert tool.RECEIPTS.parent.name == "identity_repairs"
