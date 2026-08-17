"""Reproduction gate (docs/CERTIFICATION_STANDARD.md, Part AX)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReproductionResult:
    expected: float
    observed: float
    absolute_difference: float
    relative_difference: float
    tolerance: float
    status: str  # PASS | FAIL | BLOCKED

    def to_report(self) -> str:
        return (
            f"EXPECTED: {self.expected}\n"
            f"OBSERVED: {self.observed}\n"
            f"ABSOLUTE DIFFERENCE: {self.absolute_difference}\n"
            f"RELATIVE DIFFERENCE: {self.relative_difference}\n"
            f"TOLERANCE: {self.tolerance}\n"
            f"STATUS: {self.status}"
        )


def reproduce(expected: float, observed: float | None, tolerance: float) -> ReproductionResult:
    """observed=None means the value could not be recomputed at all -> BLOCKED, not FAIL."""
    if observed is None:
        return ReproductionResult(expected, float("nan"), float("nan"), float("nan"), tolerance, "BLOCKED")

    abs_diff = abs(observed - expected)
    rel_diff = abs_diff / abs(expected) if expected != 0 else float("inf")
    status = "PASS" if abs_diff <= tolerance else "FAIL"
    return ReproductionResult(expected, observed, abs_diff, rel_diff, tolerance, status)
