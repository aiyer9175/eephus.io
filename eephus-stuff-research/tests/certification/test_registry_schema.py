"""Every real registry entry this program shipped must actually satisfy its own schema.

This is not a synthetic fixture test -- it validates the live files in
registry/, so if a future edit breaks one, this fails immediately.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from eephus_research.validation.registry_schema import validate_registry_file

_REGISTRY = Path(__file__).resolve().parents[2] / "registry"


@pytest.mark.parametrize(
    "path",
    sorted((_REGISTRY / "decisions").glob("D-*.yaml")),
    ids=lambda p: p.name,
)
def test_decision_entries_satisfy_schema(path):
    validate_registry_file(path, "decision.schema.json")


@pytest.mark.parametrize(
    "path",
    sorted((_REGISTRY / "claims").glob("C-*.yaml")),
    ids=lambda p: p.name,
)
def test_claim_entries_satisfy_schema(path):
    validate_registry_file(path, "claim.schema.json")


def test_at_least_one_decision_and_one_claim_exist():
    assert list((_REGISTRY / "decisions").glob("D-*.yaml"))
    assert list((_REGISTRY / "claims").glob("C-*.yaml"))
