"""Structural self-check: the deliverables Part BX requires actually exist on disk.

Read-only. Does not judge content quality -- just that the required files
are present, which is a precondition several P0-NN gates depend on.
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_FILES = [
    "README.md",
    "CLAUDE.md",
    "pyproject.toml",
    ".gitignore",
    "docs/MACHINE_STATE.md",
    "docs/REPOSITORY_INVENTORY.md",
    "docs/RESEARCH_CONSTITUTION.md",
    "docs/MATHEMATICAL_GOVERNANCE.md",
    "docs/STATISTICAL_GOVERNANCE.md",
    "docs/DATA_GOVERNANCE.md",
    "docs/VALIDATION_STANDARD.md",
    "docs/CERTIFICATION_STANDARD.md",
    "docs/BEGINNER_OPERATIONS.md",
    "schemas/claim.schema.json",
    "schemas/decision.schema.json",
    "schemas/experiment.schema.json",
    "schemas/dataset.schema.json",
    "src/eephus_research/provenance/manifest.py",
    "src/eephus_research/validation/schema.py",
    "src/eephus_research/diagnostics/splits.py",
    "src/eephus_research/diagnostics/leakage.py",
    "src/eephus_research/diagnostics/identity_audit.py",
    "src/eephus_research/certification/gates.py",
]

REQUIRED_DIRS = [
    "registry/claims",
    "registry/decisions",
    "registry/experiments",
    "registry/datasets",
    "registry/models",
    "tests/unit",
    "tests/invariants",
    "tests/regression",
    "tests/integration",
    "tests/statistical",
    "tests/certification",
    "tests/fixtures/good",
    "tests/fixtures/bad",
]


def test_all_required_files_present():
    missing = [f for f in REQUIRED_FILES if not (_ROOT / f).exists()]
    assert not missing, f"Missing required Program 0 deliverables: {missing}"


def test_all_required_directories_present():
    missing = [d for d in REQUIRED_DIRS if not (_ROOT / d).is_dir()]
    assert not missing, f"Missing required Program 0 directories: {missing}"


def test_no_stuff_model_artifact_present():
    """P0-24 (critical): no fitted model artifact should exist anywhere in this workbench."""
    model_extensions = {".pkl", ".joblib", ".onnx", ".h5"}
    found = [
        p for p in _ROOT.rglob("*")
        if p.is_file() and p.suffix in model_extensions and ".venv" not in p.parts
    ]
    assert not found, f"Unexpected model artifact(s) found (P0-24 should be NOT_ATTEMPTED): {found}"
