# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Phase 8 (Tier 2) -- cross-source grade normalization: identity, monotonicity,
reproducibility, overlap-based drift, and the normalized consensus diff."""
import json
from pathlib import Path

import pytest

import grade_normalization as gn

_DATA = Path(gn.__file__).resolve().parent / "data"
_CYCLE = 2026


def test_reference_maps_to_itself():
    for v in (35, 40, 45, 50, 55, 60, 65):
        assert gn.quantile_map(v, gn.REFERENCE, "hitter", _CYCLE) == pytest.approx(v, abs=1e-6)


def test_quantile_map_monotone():
    prev = -1e9
    for v in (35, 40, 45, 50, 55, 60):
        m = gn.quantile_map(v, "mlb_pipeline", "hitter", _CYCLE)
        assert m is not None and m >= prev - 1e-9
        prev = m


def test_quantile_map_reproducible():
    a = gn.quantile_map(50, "mlb_pipeline", "hitter", _CYCLE)
    b = gn.quantile_map(50, "mlb_pipeline", "hitter", _CYCLE)
    assert a == b


def test_drift_row_overlap_and_material():
    r = gn.drift_row("mlb_pipeline", "hitter", _CYCLE)
    assert r is not None
    assert {"source", "n", "median_raw", "median_fg_overlap", "median_shift", "material"} <= set(r)
    assert r["n"] > 30                         # real overlap
    # mlb_pipeline grades hotter than FanGraphs on shared players -> negative shift.
    assert r["median_shift"] <= 0.0
    # FanGraphs has zero drift by construction.
    fg = gn.drift_row(gn.REFERENCE, "hitter", _CYCLE)
    assert fg["median_shift"] == 0.0 and fg["material"] is False


def test_normalized_consensus_deterministic_and_diffed():
    nc = gn.normalized_consensus(_CYCLE)
    assert len(nc) > 100
    assert nc == gn.normalized_consensus(_CYCLE)      # reproducible
    for pk, p in list(nc.items())[:20]:
        assert p["diff"] == pytest.approx(p["norm_consensus"] - p["raw_consensus"], abs=0.01)
        assert p["n_sources"] >= 2


def test_eval_artifact_present_and_gate():
    doc = json.loads((_DATA / "grade_normalization_eval.json").read_text(encoding="utf-8"))
    assert doc["experiment"] == "cross-source-grade-normalization"
    assert doc["gate"]["pass"] is True
    assert doc["gate"]["reference_identity"] is True
    assert doc["gate"]["material_drift_sources"]      # at least one flagged
