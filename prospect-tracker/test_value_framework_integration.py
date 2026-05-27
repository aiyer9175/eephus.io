"""Integration tests for the FV/WAR/$ conversion framework.

Checks that:
  * data/value_framework.json + .js stay in sync with what value_framework.py
    would emit RIGHT NOW (the snapshot is committed; this test fails if
    someone edits the constants but forgets to re-emit).
  * Backend consumers (storage.py, mlb_trade_lookup.py) route through
    value_framework's exports (not local hardcoded duplicates).
  * The new $/FV downstream surfaces -- surplus_per_fv_pt_mm,
    fv_per_m_pool -- are correctly populated when the underlying
    accumulators carry data.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import value_framework as vf

_ROOT = Path(__file__).resolve().parent
_DATA = _ROOT / "data"


# =============================================================================
# Snapshot file freshness
# =============================================================================
def test_value_framework_json_matches_current_module() -> None:
    """If someone edits constants in value_framework.py but forgets to
    re-emit snapshots, this test fails. Recovery:
        python value_framework.py --emit-snapshots
    """
    json_path = _DATA / "value_framework.json"
    assert json_path.exists(), "data/value_framework.json missing"
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    fresh = vf.build_snapshot()
    assert on_disk == fresh, (
        "Snapshot drift -- re-run `python value_framework.py --emit-snapshots`"
    )


def test_value_framework_js_mirrors_json() -> None:
    """JS sidecar should round-trip to the same payload as the JSON."""
    json_path = _DATA / "value_framework.json"
    js_path   = _DATA / "value_framework.js"
    assert js_path.exists(), "data/value_framework.js missing"
    on_disk_json = json.loads(json_path.read_text(encoding="utf-8"))
    js = js_path.read_text(encoding="utf-8")
    assert "window.VALUE_FRAMEWORK = " in js
    body = js.split("window.VALUE_FRAMEWORK = ", 1)[1].rstrip().rstrip(";")
    assert json.loads(body) == on_disk_json


# =============================================================================
# Backend rewiring
# =============================================================================
def test_storage_imports_from_value_framework() -> None:
    """storage.py should route surplus calcs through value_framework
    rather than its old hardcoded _SURPLUS_VALUE_MM_HITTER table."""
    src = (_ROOT / "storage.py").read_text(encoding="utf-8")
    assert "from value_framework import" in src, \
        "storage.py no longer imports from value_framework"
    # The old local table constants must be gone.
    assert "_SURPLUS_VALUE_MM_HITTER" not in src, \
        "Old _SURPLUS_VALUE_MM_HITTER table still in storage.py"
    assert "_SURPLUS_VALUE_MM_PITCHER" not in src, \
        "Old _SURPLUS_VALUE_MM_PITCHER table still in storage.py"


def test_mlb_trade_lookup_routes_through_value_framework() -> None:
    """mlb_trade_lookup._compute_surplus should call value_framework.dollars_per_war
    instead of the old flat $8M constant."""
    src = (_ROOT / "mlb_trade_lookup.py").read_text(encoding="utf-8")
    assert "from value_framework import dollars_per_war" in src
    # Old hardcoded $8M should be gone in the function body (the docstring
    # still mentions $8M historically, that's fine).
    fn_body = re.search(r"def _compute_surplus.*?(?=\n\ndef |\Z)",
                        src, re.DOTALL)
    assert fn_body is not None, "_compute_surplus function not found"
    body = fn_body.group(0)
    assert "_WAR_DOLLAR_MM = 8.0" not in body, \
        "Old hardcoded $8M still in _compute_surplus"


def test_index_html_includes_value_framework_script() -> None:
    """index.html must load data/value_framework.js so the
    window.VALUE_FRAMEWORK global is defined before downstream JS runs."""
    src = (_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'src="data/value_framework.js"' in src, \
        "index.html missing <script src=data/value_framework.js>"


def test_index_html_drops_hardcoded_surplus_tables() -> None:
    """The duplicated SURPLUS_VALUE_MM / SURPLUS_POSITION_MULT literal
    tables in index.html should be gone -- replaced by reads from
    window.VALUE_FRAMEWORK."""
    src = (_ROOT / "index.html").read_text(encoding="utf-8")
    # The old hardcoded surplus table was literally "{ 80: 200, 75: 130 ..."
    # If that's gone, the de-duplication landed cleanly.
    assert "{ 80: 200, 75: 130" not in src, \
        "Old SURPLUS_VALUE_MM hitter table still in index.html"
    assert "{ 80: 100, 75: 80" not in src, \
        "Old SURPLUS_VALUE_MM pitcher table still in index.html"


# =============================================================================
# New $/FV surfaces populated correctly
# =============================================================================
def test_surplus_per_fv_pt_uses_value_framework_table() -> None:
    """The org-tree active_surplus leaf's surplus_per_fv_pt_mm should
    derive cleanly: total_surplus / total_fv_pts."""
    # Build a synthetic org-agg dict and run the leaf finalizer.
    import storage
    # Two prospects: FV 55 hitter SS, FV 50 pitcher SP
    m = {
        "_active_surplus_count":       6,    # gate: >= 5
        "_active_surplus_net_mm":     90.0,
        "_active_surplus_cost_mm":     2.0,
        "_active_surplus_fv_total":  315.0,  # 6 prospects, ~52.5 avg FV
        "_active_surplus_net_mm_hit":  60.0,
        "_active_surplus_count_hit":   4,
        "_active_surplus_net_mm_pit":  30.0,
        "_active_surplus_count_pit":   2,
    }
    out = storage._finalize_active_surplus_leaf(m)
    assert out["surplus_per_fv_pt_mm"] == pytest.approx(90.0 / 315.0, abs=1e-3)
    assert out["fv_total"] == pytest.approx(315.0, abs=0.05)
    # Per-prospect math should still hold.
    assert out["surplus_per_prospect_mm"] == pytest.approx(90.0 / 6.0, abs=1e-2)


def test_surplus_per_fv_pt_none_below_gate() -> None:
    """Below 5-prospect gate, the metric should be None."""
    import storage
    m = {
        "_active_surplus_count":       3,
        "_active_surplus_net_mm":     30.0,
        "_active_surplus_fv_total":  120.0,
    }
    out = storage._finalize_active_surplus_leaf(m)
    assert out["surplus_per_fv_pt_mm"] is None


def test_draft_pool_efficiency_returns_both_metrics() -> None:
    """fv_per_m_pool should populate alongside war_per_m_pool."""
    import storage
    gagg = {
        "_draft_pool_grads": [
            {"draft_year": 2020, "career_war":  5.0},
            {"draft_year": 2021, "career_war":  3.0},
            {"draft_year": 2022, "career_war":  1.5},
        ],
        "_draft_pool_active_fv_total": 280.0,
    }
    # Use draft years that fall in T-5..T-2. Need realistic pool sizes.
    from datetime import date
    yr = date.today().year
    pools = {
        yr - 5: {"team_pools": {"FAKE": 8_000_000}},
        yr - 4: {"team_pools": {"FAKE": 8_500_000}},
        yr - 3: {"team_pools": {"FAKE": 9_000_000}},
        yr - 2: {"team_pools": {"FAKE": 9_500_000}},
    }
    # Re-write grad draft years into the relevant window.
    gagg["_draft_pool_grads"] = [
        {"draft_year": yr - 5, "career_war":  5.0},
        {"draft_year": yr - 4, "career_war":  3.0},
        {"draft_year": yr - 3, "career_war":  1.5},
    ]
    out = storage._compute_draft_pool_efficiency(gagg, pools, "FAKE")
    assert out["war_per_m_pool"] is not None
    assert out["fv_per_m_pool"]  is not None
    assert out["fv_total_active"] == pytest.approx(280.0, abs=0.05)
    # fv_per_m sanity: 280 / 35.0  ≈ 8.0
    assert out["fv_per_m_pool"] == pytest.approx(280.0 / 35.0, abs=0.05)


def test_draft_pool_efficiency_war_none_but_fv_populated() -> None:
    """When grads are sparse (no realized WAR yet) but actives carry
    FV pts, war_per_m_pool should be None while fv_per_m_pool fires --
    the whole point of the fast-cycle companion."""
    import storage
    gagg = {
        "_draft_pool_grads":           [],   # no grads yet
        "_draft_pool_active_fv_total": 200.0,
    }
    from datetime import date
    yr = date.today().year
    pools = {
        yr - 5: {"team_pools": {"FAKE": 10_000_000}},
        yr - 4: {"team_pools": {"FAKE": 10_000_000}},
        yr - 3: {"team_pools": {"FAKE": 10_000_000}},
        yr - 2: {"team_pools": {"FAKE": 10_000_000}},
    }
    out = storage._compute_draft_pool_efficiency(gagg, pools, "FAKE")
    assert out["war_per_m_pool"] is None
    assert out["fv_per_m_pool"]  is not None
    assert out["fv_per_m_pool"]  == pytest.approx(200.0 / 40.0, abs=0.01)


# =============================================================================
# End-to-end sanity: a recognizable prospect grade should produce a
# defensible $-equivalent.
# =============================================================================
def test_top_prospect_surplus_in_expected_range() -> None:
    """An FV 60 hitter SS should produce $80-150M in 6yr surplus per
    the current calibration. If this drifts wildly, something changed
    that warrants review."""
    s = vf.surplus_value_mm(60, is_pitcher=False, position="SS")
    assert s is not None
    assert 80.0 <= s <= 200.0, f"FV 60 SS surplus {s} out of expected range"


def test_fringe_prospect_surplus_at_floor() -> None:
    """An FV 40 hitter should be near the $0.3M floor (or just above)."""
    s = vf.surplus_value_mm(40, is_pitcher=False, position="OF")
    assert s is not None
    assert 0.3 <= s <= 5.0


def test_mlb_vet_career_war_value() -> None:
    """A 30-WAR career vet should value around $300M+ at the overall
    rolling $/WAR rate (~$11.74M)."""
    v = vf.career_war_value_mm(30.0)
    assert v is not None
    assert 300.0 <= v <= 400.0
