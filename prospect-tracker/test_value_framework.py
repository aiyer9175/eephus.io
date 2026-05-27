"""Unit tests for value_framework.

Covers:
  * $/WAR tier lookup (boundaries + window averaging)
  * FV -> WAR peak (primer ranges, hitter/pitcher split, interpolation)
  * Success-prob curve (monotonic, bounded)
  * surplus_value_mm (monotonic across FV, hitter > pitcher floor,
    position multiplier applied, snapshot stability)
  * career_war_value_mm (overall rate, None handling)
  * Snapshot emitters round-trip JSON cleanly
  * Backend / frontend parity: the JS snapshot mirrors the JSON
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import value_framework as vf


# =============================================================================
# $/WAR tier dispatch
# =============================================================================
def test_dpw_window_default_is_3yr() -> None:
    assert vf.DEFAULT_WINDOW_YEARS == (2024, 2025, 2026)
    tiers = vf.dollars_per_war_for_window()
    # Sanity: tiers must be ordered fringe < mid < star.
    assert tiers["0-1"] < tiers["1-2"] < tiers["2+"]
    # Spot-check the rolling 3yr average against hand math:
    # 0-1: (8.22+5.96+6.74)/3 = 6.973  -> 6.97
    # 2+:  (14.13+13.91+12.84)/3 = 13.626 -> 13.63
    assert tiers["0-1"] == pytest.approx(6.97, abs=0.01)
    assert tiers["2+"]  == pytest.approx(13.63, abs=0.01)


def test_dpw_boundary_at_1_and_2_war() -> None:
    # Exactly 1.0 WAR moves into the 1-2 tier.
    t = vf.dollars_per_war_for_window()
    assert vf.dollars_per_war(0.99) == t["0-1"]
    assert vf.dollars_per_war(1.00) == t["1-2"]
    assert vf.dollars_per_war(1.99) == t["1-2"]
    assert vf.dollars_per_war(2.00) == t["2+"]


def test_dpw_none_falls_to_fringe_tier() -> None:
    assert vf.dollars_per_war(None) == vf.dollars_per_war_for_window()["0-1"]


def test_dpw_custom_window() -> None:
    # 2020-only window should match the raw 2020 row.
    tiers = vf.dollars_per_war_for_window(window=(2020,))
    assert tiers["overall"] == pytest.approx(10.85, abs=0.01)
    assert tiers["0-1"]     == pytest.approx(10.93, abs=0.01)


def test_dpw_flat_returns_overall() -> None:
    overall = vf.dollars_per_war_for_window()["overall"]
    assert vf.dollars_per_war_flat() == overall


# =============================================================================
# FV -> WAR peak
# =============================================================================
def test_fv_to_war_primer_midpoints_hitter() -> None:
    # Hitter FV 50: primer range 1.6-2.4 -> midpoint 2.0
    assert vf.fv_to_war_peak(50, is_pitcher=False) == 2.0
    # Hitter FV 60: primer range 3.4-4.9 -> midpoint 4.15
    assert vf.fv_to_war_peak(60, is_pitcher=False) == 4.15
    # Hitter FV 70: 5.0-7.0 -> 6.0
    assert vf.fv_to_war_peak(70, is_pitcher=False) == 6.0


def test_fv_to_war_primer_midpoints_pitcher() -> None:
    # Pitcher FV 50: 1.8-2.5 -> 2.15
    assert vf.fv_to_war_peak(50, is_pitcher=True) == 2.15
    # Pitcher FV 60: 3.5-4.9 -> 4.2
    assert vf.fv_to_war_peak(60, is_pitcher=True) == 4.2


def test_fv_to_war_monotonic() -> None:
    """WAR(peak) must increase monotonically with FV for both roles."""
    grades = (40, 45, 50, 55, 60, 65, 70, 75, 80)
    for is_pit in (False, True):
        vals = [vf.fv_to_war_peak(g, is_pit) for g in grades]
        assert vals == sorted(vals), f"non-monotonic for is_pitcher={is_pit}"


def test_fv_to_war_interpolates_half_grades() -> None:
    # FV 52.5 should sit halfway between FV 50 (2.0) and FV 55 (2.9).
    v = vf.fv_to_war_peak(52.5, is_pitcher=False)
    assert v == pytest.approx(2.45, abs=0.01)


def test_fv_to_war_none_handling() -> None:
    assert vf.fv_to_war_peak(None, False) is None
    assert vf.fv_to_war_peak("garbage", False) is None  # type: ignore[arg-type]


# =============================================================================
# Bust probability
# =============================================================================
def test_success_prob_monotonic_and_bounded() -> None:
    grades = (20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80)
    for is_pit in (False, True):
        ps = [vf.success_prob(g, is_pit) for g in grades]
        assert ps == sorted(ps), f"non-monotonic for is_pitcher={is_pit}"
        assert all(0.0 < p <= 1.0 for p in ps)


def test_success_prob_pitchers_lower_than_hitters() -> None:
    """Pitchers should have lower success rates at every grade above
    the noise floor (injury + role-conversion risk)."""
    for g in (40, 45, 50, 55, 60, 65, 70, 75, 80):
        h = vf.success_prob(g, is_pitcher=False)
        p = vf.success_prob(g, is_pitcher=True)
        assert p <= h, f"FV {g}: pitcher {p} > hitter {h}"


# =============================================================================
# surplus_value_mm
# =============================================================================
def test_surplus_monotonic_in_fv() -> None:
    grades = (40, 45, 50, 55, 60, 65, 70, 75, 80)
    for is_pit in (False, True):
        vals = [vf.surplus_value_mm(g, is_pit, None,
                                    apply_position_mult=False)
                for g in grades]
        assert vals == sorted(vals), f"non-monotonic for is_pitcher={is_pit}"


def test_surplus_position_mult_applied() -> None:
    """An FV 50 SS should value above an FV 50 1B (scarcity)."""
    fv50_ss = vf.surplus_value_mm(50, is_pitcher=False, position="SS")
    fv50_1b = vf.surplus_value_mm(50, is_pitcher=False, position="1B")
    assert fv50_ss > fv50_1b


def test_surplus_rp_discount() -> None:
    """A pitcher labeled RP should value below a generic SP at same FV."""
    fv50_sp = vf.surplus_value_mm(50, is_pitcher=True, position="SP")
    fv50_rp = vf.surplus_value_mm(50, is_pitcher=True, position="RP")
    assert fv50_rp < fv50_sp


def test_surplus_floor_at_low_fv() -> None:
    """FV 20-35 should still return a small non-zero floor."""
    for g in (20, 25, 30, 35):
        assert vf.surplus_value_mm(g, False, None) is not None
        assert vf.surplus_value_mm(g, False, None) >= 0.3


def test_surplus_returns_none_for_missing_fv() -> None:
    assert vf.surplus_value_mm(None, False, None) is None


def test_dollars_per_fv_ratio() -> None:
    """$/FV should equal surplus / FV exactly."""
    for fv in (40, 50, 60, 70):
        s = vf.surplus_value_mm(fv, False, None)
        d = vf.dollars_per_fv(fv, False, None)
        assert d == pytest.approx(s / fv, abs=0.01)


# =============================================================================
# career_war_value_mm
# =============================================================================
def test_career_war_uses_overall_rate() -> None:
    overall = vf.dollars_per_war_flat()
    assert vf.career_war_value_mm(10.0) == pytest.approx(10.0 * overall, abs=0.05)
    assert vf.career_war_value_mm(0.0) is None
    assert vf.career_war_value_mm(None) is None
    assert vf.career_war_value_mm(-5.0) is None


# =============================================================================
# Snapshot emitters
# =============================================================================
def test_build_snapshot_has_all_required_keys() -> None:
    snap = vf.build_snapshot()
    required = ("version", "window", "sources", "dollars_per_war",
                "fv_to_war_peak", "bust_prob", "surplus_value_mm",
                "position_multipliers", "ramp_factor", "cost_basis")
    for k in required:
        assert k in snap, f"snapshot missing key {k}"
    # Sub-structure checks
    assert "tiers" in snap["dollars_per_war"]
    assert "hitter" in snap["fv_to_war_peak"]
    assert "pitcher" in snap["fv_to_war_peak"]
    assert snap["sources"]["primer"].startswith("https://")
    assert snap["sources"]["dollars_per_war"].startswith("https://")


def test_emit_snapshots_writes_json_and_js(tmp_path: Path) -> None:
    jp, jsp = vf.emit_snapshots(out_dir=tmp_path)
    assert jp.exists() and jsp.exists()
    snap = json.loads(jp.read_text(encoding="utf-8"))
    assert snap["version"] == vf.FRAMEWORK_VERSION
    # JS file should assign window.VALUE_FRAMEWORK and round-trip the
    # same JSON payload.
    js = jsp.read_text(encoding="utf-8")
    assert "window.VALUE_FRAMEWORK = " in js
    # Extract the JSON body and parse -- must equal the JSON file.
    body = js.split("window.VALUE_FRAMEWORK = ", 1)[1].rstrip().rstrip(";")
    assert json.loads(body) == snap


def test_position_multiplier_lookup() -> None:
    """Sanity-check the curated position table."""
    # The values below are pinned -- changes to them indicate someone
    # changed the table, which should be reviewed (likely an audit
    # finding from calibrate_position_mults.py).
    assert vf.position_multiplier("SS") == 1.18
    assert vf.position_multiplier("RP") == 0.55
    assert vf.position_multiplier("1B") == 0.70
    assert vf.position_multiplier("SP") == 1.00
    assert vf.position_multiplier(None) == 1.0
    assert vf.position_multiplier("UNKNOWN") == 1.0
    # Multi-position resolves to primary
    assert vf.position_multiplier("SS/2B") == 1.18


def test_is_pitcher_position() -> None:
    for p in ("SP", "RP", "RHP", "LHP", "MIRP", "SIRP", "P"):
        assert vf.is_pitcher_position(p) is True
    for p in ("SS", "C", "1B", "OF", "DH", "TWP", None, ""):
        assert vf.is_pitcher_position(p) is False
    assert vf.is_pitcher_position("RHP/SP") is True
    assert vf.is_pitcher_position("SS/2B") is False
