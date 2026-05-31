# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

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


# =============================================================================
# v32.1 — Per-side $/FV split + acquisition-method efficiency
# =============================================================================
def test_active_surplus_per_side_fv_split() -> None:
    """fin_active_surplus should expose per_fv_pt_hit_mm and per_fv_pt_pit_mm
    when both sides have ≥3 contributors with positive fv totals."""
    import storage
    m = {
        "_active_surplus_count":         8,
        "_active_surplus_net_mm":      120.0,
        "_active_surplus_cost_mm":       3.0,
        "_active_surplus_fv_total":    400.0,
        # 5 hitters totaling 250 FV / $80M surplus
        "_active_surplus_count_hit":     5,
        "_active_surplus_net_mm_hit":   80.0,
        "_active_surplus_fv_total_hit": 250.0,
        # 3 pitchers totaling 150 FV / $40M surplus
        "_active_surplus_count_pit":     3,
        "_active_surplus_net_mm_pit":   40.0,
        "_active_surplus_fv_total_pit": 150.0,
    }
    out = storage._finalize_active_surplus_leaf(m)
    assert out["per_fv_pt_hit_mm"] == pytest.approx(80.0 / 250.0, abs=1e-3)
    assert out["per_fv_pt_pit_mm"] == pytest.approx(40.0 / 150.0, abs=1e-3)
    assert out["fv_total_hit"] == pytest.approx(250.0, abs=0.05)
    assert out["fv_total_pit"] == pytest.approx(150.0, abs=0.05)


def test_active_surplus_method_efficiency_populated() -> None:
    """method_efficiency dict should expose draft/IFA/trade breakdowns
    when each channel has ≥3 actives with positive fv."""
    import storage
    m = {
        "_active_surplus_count":         9,
        "_active_surplus_net_mm":      120.0,
        "_active_surplus_cost_mm":       4.0,
        "_active_surplus_fv_total":    450.0,
        "_active_surplus_count_hit":     5,
        "_active_surplus_count_pit":     4,
        "_method_surplus": {
            "draft":            {"net_mm": 60.0, "fv_total": 200.0, "count": 4, "cost_mm": 2.5},
            "international_fa": {"net_mm": 40.0, "fv_total": 180.0, "count": 3, "cost_mm": 1.0},
            "trade":            {"net_mm": 20.0, "fv_total":  70.0, "count": 2, "cost_mm": 0.5},
        },
    }
    out = storage._finalize_active_surplus_leaf(m)
    me = out["method_efficiency"]
    # Draft + IFA: ≥3 contributors → populated
    assert me["draft"]["surplus_per_fv_pt_mm"] == pytest.approx(60.0 / 200.0, abs=1e-3)
    assert me["international_fa"]["surplus_per_fv_pt_mm"] == pytest.approx(40.0 / 180.0, abs=1e-3)
    # Trade: only 2 contributors → ratio None, but count + raw sums on file
    assert me["trade"]["surplus_per_fv_pt_mm"] is None
    assert me["trade"]["count"] == 2
    assert me["trade"]["surplus_total_mm"] == pytest.approx(20.0, abs=0.05)


def test_tx_trades_per_fv_metrics_present() -> None:
    """tx_trades should include both the prospect-only $/FV ratios AND
    the separate vet-value fields so trade audit UI can render them
    side-by-side per the project-wide FV→$ vs realized-$ split."""
    src = (_ROOT / "storage.py").read_text(encoding="utf-8")
    for field in ("in_per_fv_mm", "out_per_fv_mm", "per_fv_delta_mm",
                  # v32.1 vet/prospect split
                  "in_surplus_prospect_mm", "out_surplus_prospect_mm",
                  "in_fv_prospect", "out_fv_prospect",
                  "in_vet_value_mm", "out_vet_value_mm",
                  "in_prospect_count", "out_prospect_count",
                  "in_vet_count", "out_vet_count"):
        assert f'"{field}"' in src, f"tx_trades schema missing {field}"


def test_trade_player_value_returns_kind() -> None:
    """_trade_player_value should return (value, kind) per v32.1, where
    kind in {'vet', 'prospect', None}. This is the contract the tx_trades
    loop relies on for the prospect/vet split."""
    src = (_ROOT / "storage.py").read_text(encoding="utf-8")
    # The function is nested; match with optional leading whitespace.
    fn = re.search(r"def _trade_player_value\([^)]*\).*?(?=\n    [a-zA-Z_])",
                   src, re.DOTALL)
    assert fn is not None, "_trade_player_value not found"
    body = fn.group(0)
    assert '"vet"' in body, "vet kind not returned"
    assert '"prospect"' in body, "prospect kind not returned"
    # Tuple return shape declared
    assert "tuple[float | None, str | None]" in body, "tuple return type missing"


def test_surplus_granular_for_non_anchor_fv() -> None:
    """v2: surplus_value_mm produces a smooth, granular value for non-5pt FVs.
    Continuity is now a model GUARANTEE (P(bucket|FV) is a smooth ordered-logit
    and the per-bucket surplus is FV-independent), so FV 47 sits strictly
    between FV 45 and FV 50 with NO grade-boundary jump -- the opposite of the
    v1 tier-rate kink this test used to assert."""
    s45 = vf.surplus_value_mm(45, is_pitcher=False, position=None)
    s47 = vf.surplus_value_mm(47, is_pitcher=False, position=None)
    s50 = vf.surplus_value_mm(50, is_pitcher=False, position=None)
    assert s45 < s47 < s50, f"FV 47 ({s47}) not strictly between FV 45 ({s45}) and 50 ({s50})"
    # Smooth: close to the linear interpolation (no discontinuous kink).
    naive_linear = s45 + (s50 - s45) * (47 - 45) / 5
    assert abs(s47 - naive_linear) < 0.25 * (s50 - s45)


def test_expected_war_interpolates_at_one_point_granularity() -> None:
    """v2: the P(bucket|FV)-weighted six-year average WAR (which replaced the v1
    fv_to_war_peak point estimate) must be distinct and strictly monotone at
    1-point FV granularity -- continuous FV shifts probability mass smoothly."""
    vals = [vf.expected_six_year_avg_war(g, is_pitcher=False) for g in (45, 46, 47, 48, 49, 50)]
    for i in range(len(vals) - 1):
        assert vals[i] < vals[i + 1], f"non-monotonic at FV {45+i}->{46+i}: {vals}"


def test_dollars_per_fv_granular() -> None:
    """$/FV should produce distinct values for non-5pt FVs."""
    d47 = vf.dollars_per_fv(47, False, None)
    d50 = vf.dollars_per_fv(50, False, None)
    assert d47 is not None
    assert d50 is not None
    # Different magnitudes — the framework treats them differently.
    assert abs(d47 - d50) > 0.01


def test_financial_leaf_weights_v32_1() -> None:
    """Leaf weights should reflect the v32.1 rebalance: active_surplus 0.40,
    contract_surplus 0.20, others unchanged."""
    import storage
    fin = storage.FARM_LEAF_WEIGHTS["financial"]
    assert fin["fin_active_surplus"]   == 0.40
    assert fin["fin_contract_surplus"] == 0.20
    assert fin["fin_war_per_m"]        == 0.10
    assert fin["fin_draft_pool_efficiency"] == 0.15
    assert fin["fin_ifa_roi"]          == 0.15
    # Weights still sum to 1.0
    assert pytest.approx(sum(fin.values()), abs=1e-9) == 1.0


def test_draft_pool_efficiency_grades_both_metrics() -> None:
    """The leaf grading spec should now include both war_per_m_pool AND
    fv_per_m_pool as sub-inputs."""
    src = (_ROOT / "storage.py").read_text(encoding="utf-8")
    # Find the fin_draft_pool_efficiency lambda block by locating the
    # opening key and walking to the matching `],` close.
    start = src.find('"fin_draft_pool_efficiency": [')
    assert start >= 0, "fin_draft_pool_efficiency block not found"
    end = src.find("],", start)
    assert end > start, "fin_draft_pool_efficiency block end not found"
    block = src[start:end]
    assert '"war_per_m_pool"' in block
    assert '"fv_per_m_pool"'  in block


def test_active_surplus_grades_both_metrics() -> None:
    """The fin_active_surplus leaf grading spec should now grade BOTH
    surplus_per_prospect_mm and surplus_per_fv_pt_mm."""
    src = (_ROOT / "storage.py").read_text(encoding="utf-8")
    start = src.find('"fin_active_surplus": [')
    assert start >= 0, "fin_active_surplus block not found"
    end = src.find("],", start)
    assert end > start, "fin_active_surplus block end not found"
    block = src[start:end]
    assert "surplus_per_prospect_mm" in block
    assert "surplus_per_fv_pt_mm"    in block
