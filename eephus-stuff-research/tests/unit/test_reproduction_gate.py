from __future__ import annotations

from eephus_research.certification.reproduction_gate import reproduce


def test_reproduce_pass_within_tolerance():
    result = reproduce(expected=1.000, observed=1.0005, tolerance=0.001)
    assert result.status == "PASS"


def test_reproduce_fail_outside_tolerance():
    result = reproduce(expected=1.0, observed=1.5, tolerance=0.001)
    assert result.status == "FAIL"


def test_reproduce_blocked_when_not_recomputable():
    result = reproduce(expected=1.0, observed=None, tolerance=0.001)
    assert result.status == "BLOCKED"


def test_reproduce_report_contains_all_required_fields():
    report = reproduce(expected=1.0, observed=1.0, tolerance=0.001).to_report()
    for field in ["EXPECTED", "OBSERVED", "ABSOLUTE DIFFERENCE", "RELATIVE DIFFERENCE", "TOLERANCE", "STATUS"]:
        assert field in report
