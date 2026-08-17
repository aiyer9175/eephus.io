from __future__ import annotations

import pytest

from eephus_research.certification.gates import Gate, GateTable, InvalidGateStatus


def test_gate_rejects_invalid_status():
    with pytest.raises(InvalidGateStatus):
        Gate("G01", "test gate", "MAYBE")


def test_gate_table_verdict_certified_when_all_pass():
    table = GateTable()
    table.add("G01", "a", "PASS", critical=True)
    table.add("G02", "b", "PASS")
    assert table.verdict() == "CERTIFIED"


def test_gate_table_verdict_not_certified_on_failed_critical_gate():
    table = GateTable()
    table.add("G01", "a", "PASS")
    table.add("G02", "leakage check", "FAIL", critical=True)
    assert table.verdict() == "NOT_CERTIFIED"


def test_no_averaged_certification_many_passes_do_not_rescue_one_critical_failure():
    table = GateTable()
    for i in range(29):
        table.add(f"G{i:02d}", "minor", "PASS")
    table.add("G29", "critical leakage gate", "FAIL", critical=True)
    assert table.verdict() == "NOT_CERTIFIED"
    assert len(table.failed_critical_gates()) == 1


def test_certified_with_open_items_on_blocked_noncritical_gate():
    table = GateTable()
    table.add("G01", "a", "PASS", critical=True)
    table.add("G02", "b", "BLOCKED")
    assert table.verdict() == "CERTIFIED_WITH_OPEN_ITEMS"


def test_to_markdown_contains_all_gates():
    table = GateTable()
    table.add("G01", "a", "PASS")
    table.add("G02", "b", "FAIL", critical=True)
    md = table.to_markdown()
    assert "G01" in md and "G02" in md and "**yes**" in md
