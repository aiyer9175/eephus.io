# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Schema + sanity tests for data/mock_draft_eval.json (mock draft score).

The artifact is produced by tools/mock_draft_scorer.py against the gate at
docs/draft-2026-08-19/MOCK_DRAFT_SCORE_GATE.md. These tests pin the contract:
pre-draft provenance, both baselines present, internally consistent deltas,
and clause verdicts recorded. They do NOT re-run the lab.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

ARTIFACT = Path(__file__).parent / "data" / "mock_draft_eval.json"

# Frozen provenance: the last pre-draft archive of the mock's output.
MOCK_COMMIT = "725143899a5a80d4ffc0f590012c54e5aa7bee20"
# The 2026 draft started mid-July; results ingested 2026-07-15 (689c10d0).
DRAFT_START = datetime(2026, 7, 12)


@pytest.fixture(scope="module")
def art() -> dict:
    with ARTIFACT.open(encoding="utf-8") as f:
        return json.load(f)


def test_artifact_exists_and_parses(art):
    assert isinstance(art, dict)


def test_top_level_schema(art):
    for key in ("generated_at", "draft_year", "provenance", "n_actual_pool",
                "mock", "baseline_consensus", "baseline_random_analytic",
                "mock_minus_consensus", "clauses"):
        assert key in art, key
    assert art["draft_year"] == 2026
    # 613 picks landed in the 2026 draft; the pool is unique player keys.
    assert 550 <= art["n_actual_pool"] <= 620


def test_generated_at_parses(art):
    datetime.strptime(art["generated_at"], "%Y-%m-%dT%H:%M:%SZ")


def test_provenance_is_predraft(art):
    prov = art["provenance"]
    assert prov["mock_commit"] == MOCK_COMMIT
    commit_dt = datetime.fromisoformat(prov["mock_commit_date"])
    assert commit_dt.replace(tzinfo=None) < DRAFT_START, (
        "mock provenance must predate draft day; a post-draft mock is leaky")
    assert "draft_results" in prov["results_source"]
    assert "MOCK_DRAFT_SCORE_GATE" in prov["gate_doc"]


def _check_score_block(block: dict, *, n_predicted: int):
    assert block["n_predicted"] == n_predicted
    assert 0 < block["n_matched"] <= n_predicted
    assert (block["n_matched_by_key"] + block["n_matched_by_name"]
            == block["n_matched"])
    assert (len(block["unmatched_names"])
            == n_predicted - block["n_matched"])
    assert 0.0 <= block["top10_exact"] <= 1.0
    assert 0.0 <= block["top30_exact"] <= 1.0
    assert block["mae_pick"] > 0
    assert -1.0 <= block["spearman_rho"] <= 1.0
    assert 0.0 <= block["spearman_p"] <= 1.0


def test_mock_block(art):
    _check_score_block(art["mock"], n_predicted=75)
    # Gate clause C1: validity floor.
    assert art["mock"]["n_matched"] >= 50


def test_consensus_baseline_block(art):
    _check_score_block(art["baseline_consensus"], n_predicted=75)


def test_random_baseline_is_analytic(art):
    b2 = art["baseline_random_analytic"]
    assert b2["top10_exact"] == pytest.approx(1.0 / 75)
    assert b2["top30_exact"] == pytest.approx(1.0 / 75)
    assert b2["spearman_rho"] == 0.0
    assert b2["mae_pick"] > art["mock"]["mae_pick"], (
        "random MAE floor must sit above the scored mock or C2 is suspect")


def test_deltas_consistent(art):
    mock, b1 = art["mock"], art["baseline_consensus"]
    d = art["mock_minus_consensus"]
    assert d["top10_exact"] == pytest.approx(
        mock["top10_exact"] - b1["top10_exact"])
    assert d["top30_exact"] == pytest.approx(
        mock["top30_exact"] - b1["top30_exact"])
    assert d["mae_pick"] == pytest.approx(mock["mae_pick"] - b1["mae_pick"])
    assert d["spearman_rho"] == pytest.approx(
        mock["spearman_rho"] - b1["spearman_rho"])


def test_clause_verdicts_recorded(art):
    clauses = art["clauses"]
    assert clauses["C1_validity"] == "PASS", (
        "artifact must only exist when C1 passed")
    assert clauses["C2_skill_vs_random"] in {"PASS", "FAIL"}
    assert clauses["C3_tendency_vs_board"] in {"BEAT", "TIED", "LOST"}


def test_c2_verdict_matches_numbers(art):
    mock = art["mock"]
    b2 = art["baseline_random_analytic"]
    expect = (mock["spearman_rho"] > 0 and mock["spearman_p"] < 0.05
              and mock["top30_exact"] > b2["top30_exact"])
    got = art["clauses"]["C2_skill_vs_random"] == "PASS"
    assert got == expect
