"""Self-audit finding (Part BW, Q5: 'can a public claim be unsupported by an artifact?').

Fixed by tightening schemas/claim.schema.json: a claim asserted
PASS/PASS_WITH_FINDINGS/FAIL must point at least one real ref
(artifact/code/dataset/experiment), not just a prose 'evidence' string.
"""
from __future__ import annotations

import pytest

from eephus_research.validation.registry_schema import validate_registry_entry

_BASE = {
    "claim_id": "C-900",
    "statement": "test claim",
    "claim_type": "EMPIRICAL",
    "evidence": "some prose description of evidence",
    "created_at": "2026-08-16",
    "updated_at": "2026-08-16",
}


def test_pass_claim_without_any_refs_is_rejected():
    entry = {**_BASE, "status": "PASS"}
    with pytest.raises(Exception):
        validate_registry_entry(entry, "claim.schema.json")


def test_pass_claim_with_an_artifact_ref_is_accepted():
    entry = {**_BASE, "status": "PASS", "artifact_refs": ["docs/some_report.md"]}
    validate_registry_entry(entry, "claim.schema.json")  # must not raise


def test_not_measured_claim_without_refs_is_still_accepted():
    """A claim honestly marked NOT_MEASURED doesn't need evidence yet -- that's the point of the status."""
    entry = {**_BASE, "status": "NOT_MEASURED"}
    validate_registry_entry(entry, "claim.schema.json")  # must not raise
