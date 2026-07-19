# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Proprietary and confidential

"""Phase 11 — predictive-isolation tests. These FAIL if Advancement Pace+ ever
leaks into a production model surface, feature registry, or training matrix."""

import ast
import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

HOME = Path.home()
MODULE = HOME / "advancement_pace"
DATA = MODULE / "data"

TOKENS = ["advancement_pace", "advancement_pace_plus", "advancement_percentile"]

# every production / predictive tree that could consume a feature
PRODUCTION_ROOTS = [
    "career_outcome_plus", "swing_plus", "projection_engine", "eowar", "ewar",
    "ewar_v2", "ewar_v12", "playing_time_model", "identity_plus", "variance_plus",
    "environment_engine", "batter_ecosystem", "pd_integration_audit",
]

REGISTRY_FILES = list((HOME / "infra_hardening" / "manifests").glob("*.yaml"))

# packages this descriptive module must never import from
FORBIDDEN_IMPORT_PREFIXES = ("career_outcome_plus", "swing_plus", "projection_engine",
                             "eowar", "ewar", "playing_time_model")


def _grep(root: Path, token: str):
    if not root.exists():
        return []
    r = subprocess.run(
        ["grep", "-rl", "--include=*.py", "--include=*.yaml", "--include=*.yml",
         "--include=*.json", token, str(root)],
        capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if l]


@pytest.mark.parametrize("token", TOKENS)
def test_no_token_in_production_trees(token):
    hits = []
    for root in PRODUCTION_ROOTS:
        hits += _grep(HOME / root, token)
    assert not hits, f"'{token}' found in production trees: {hits}"


@pytest.mark.parametrize("token", TOKENS)
def test_no_token_in_feature_registries(token):
    assert REGISTRY_FILES, "feature registry manifests not found"
    hits = [str(f) for f in REGISTRY_FILES if token in f.read_text()]
    assert not hits, f"'{token}' found in feature registries: {hits}"


def test_module_imports_nothing_predictive():
    for py in MODULE.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            bad = [n for n in names if n.startswith(FORBIDDEN_IMPORT_PREFIXES)]
            assert not bad, f"{py.name} imports predictive package(s): {bad}"


def test_artifact_metadata_flags():
    pub = pd.read_parquet(DATA / "advancement_pace_public.parquet")
    assert (pub.stat_type == "descriptive").all()
    assert (pub.model_eligible == False).all()  # noqa: E712


def test_no_ambiguous_column_names():
    import contracts
    pub = pd.read_parquet(DATA / "advancement_pace_public.parquet")
    bad = contracts.FORBIDDEN_COLUMN_NAMES & {c.lower() for c in pub.columns}
    assert not bad


def test_provenance_forbids_predictive_consumers():
    man = json.loads((DATA / "provenance_manifest.json").read_text())
    forbidden = " ".join(man["consumers_forbidden"]).lower()
    for name in ["career outcome", "p_reach", "xwar", "xfv", "efv", "ewar",
                 "eowar", "readiness", "opportunity"]:
        assert name in forbidden
