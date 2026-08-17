"""Certification gate framework (docs/CERTIFICATION_STANDARD.md, Parts BA, BY).

No averaged certification: a GateTable deliberately does not expose a
pass-rate number when any critical gate is present, because "29/30 PASS"
is meaningless when the one failure is the critical one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ALLOWED_STATUSES = (
    "PASS",
    "PASS_WITH_FINDINGS",
    "FAIL",
    "BLOCKED",
    "NOT_ATTEMPTED",
    "NOT_IDENTIFIED",
    "NOT_MEASURED",
    "NOT_APPLICABLE",
    "INSUFFICIENT_EVIDENCE",
    "NEEDS_REVIEW",
)

_PASSING_STATUSES = {"PASS", "PASS_WITH_FINDINGS"}


class InvalidGateStatus(ValueError):
    pass


@dataclass
class Gate:
    gate_id: str
    description: str
    status: str
    critical: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_STATUSES:
            raise InvalidGateStatus(
                f"Gate {self.gate_id}: status '{self.status}' not in {ALLOWED_STATUSES}"
            )

    @property
    def passing(self) -> bool:
        return self.status in _PASSING_STATUSES


@dataclass
class GateTable:
    gates: list[Gate] = field(default_factory=list)

    def add(self, gate_id: str, description: str, status: str, critical: bool = False, notes: str = "") -> Gate:
        gate = Gate(gate_id, description, status, critical, notes)
        self.gates.append(gate)
        return gate

    def critical_gates(self) -> list[Gate]:
        return [g for g in self.gates if g.critical]

    def failed_critical_gates(self) -> list[Gate]:
        return [g for g in self.critical_gates() if not g.passing]

    def verdict(self) -> str:
        """CERTIFIED only if every critical gate passes. Never computed from an aggregate pass rate."""
        if self.failed_critical_gates():
            return "NOT_CERTIFIED"
        if any(g.status in ("BLOCKED", "NEEDS_REVIEW") for g in self.gates):
            return "CERTIFIED_WITH_OPEN_ITEMS"
        return "CERTIFIED"

    def to_markdown(self) -> str:
        lines = ["| Gate | Description | Status | Critical | Notes |", "|---|---|---|---|---|"]
        for g in self.gates:
            crit = "**yes**" if g.critical else "no"
            lines.append(f"| {g.gate_id} | {g.description} | {g.status} | {crit} | {g.notes} |")
        return "\n".join(lines)
