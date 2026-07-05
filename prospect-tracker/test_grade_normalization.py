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


# --------------------------------------------------------------------------
# Adoption: the precomputed remapper + the consensus plumbing that applies it
# --------------------------------------------------------------------------
def test_build_remapper_identity_and_fallback():
    remap = gn.build_remapper()
    # reference (FanGraphs) maps to itself
    assert remap(55.0, gn.REFERENCE, "SS", _CYCLE) == pytest.approx(55.0, abs=1e-6)
    # unknown source / bad year -> raw fallback (never drops)
    assert remap(50.0, "no_such_source", "SS", _CYCLE) == 50.0
    assert remap(50.0, "mlb_pipeline", "SS", "xxxx") == 50.0
    assert remap(None, "mlb_pipeline", "SS", _CYCLE) is None
    # matches the quantile_map for a real (source, role, cycle) cell
    got = remap(50.0, "mlb_pipeline", "SS", _CYCLE)
    want = gn.quantile_map(50.0, "mlb_pipeline", "hitter", _CYCLE)
    assert got == pytest.approx(want, abs=1e-6)


def test_consensus_point_applies_grade_norm():
    # The plumbing must remap each source FV before it enters the mean. A mock
    # remapper that pins every grade to 40 must land the consensus at ~40.
    from consensus import compute_consensus_point
    from scrapers import Snapshot
    snaps = [
        Snapshot(player_key="x", player_name="X", source="espn", rank=None, fv=60.0,
                 position="CF", org="NYY", snapshot_date="2026-05-01",
                 interval_label="espn 2026", status="active", tools=None),
        Snapshot(player_key="x", player_name="X", source="just_baseball", rank=None, fv=58.0,
                 position="CF", org="NYY", snapshot_date="2026-05-01",
                 interval_label="jb 2026", status="active", tools=None),
    ]
    raw = compute_consensus_point(snaps)
    pinned = compute_consensus_point(snaps, grade_norm=lambda fv, src, pos, yr: 40.0)
    assert raw.consensus_fv > 50.0                      # raw mean near 59
    assert pinned.consensus_fv == pytest.approx(40.0, abs=1.0)
    # the RAW published grades on per_source are untouched (card shows the source)
    assert pinned.per_source["espn"]["fv_published"] == 60.0


def test_build_timeseries_normalize_runs():
    # normalize=True must not crash and (for a FanGraphs-only player) leaves the
    # identity-mapped consensus unchanged vs normalize=False.
    from consensus import build_timeseries
    from scrapers import Snapshot
    snaps = [
        Snapshot(player_key="fgonly", player_name="FG Only", source="fangraphs", rank=None,
                 fv=55.0, position="SS", org="LAD", snapshot_date="2026-04-01",
                 interval_label="2026report", status="active", tools=None),
    ]
    off = build_timeseries(snaps, normalize=False)
    on = build_timeseries(snaps, normalize=True)
    assert off and on
    assert off[0].fv_close == on[0].fv_close       # FG maps to itself
