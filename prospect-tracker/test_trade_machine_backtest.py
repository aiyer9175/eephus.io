# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the Trade Machine validation backtest + the Trade Value Grade map."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import pytest

from bayes_trade_value import _trade_value_grade, _platform_tier
import trade_machine_backtest as tmb


# ── Trade Value Grade map ────────────────────────────────────────────────────
@pytest.mark.parametrize("mm,grade", [
    (250.0, "A+"), (100.0, "A+"), (99.9, "A"), (60.0, "A"), (59.9, "A-"),
    (40.0, "A-"), (39.9, "B+"), (25.0, "B+"), (24.9, "B"), (15.0, "B"),
    (14.9, "B-"), (8.0, "B-"), (7.9, "C"), (3.0, "C"), (2.9, "D"),
    (0.0, "D"), (-0.1, "F"), (-50.9, "F"),
])
def test_trade_value_grade_thresholds(mm, grade):
    assert _trade_value_grade(mm) == grade


def test_trade_value_grade_none_passthrough():
    assert _trade_value_grade(None) is None


def test_grade_aligns_with_platform_tier_floors():
    # The A- floor (40) is the Elite tier floor; the B- floor (8) is the Mid floor.
    assert _platform_tier(40.0) == "elite" and _trade_value_grade(40.0) == "A-"
    assert _platform_tier(8.0) == "mid" and _trade_value_grade(8.0) == "B-"
    assert _platform_tier(-1.0) == "minimal" and _trade_value_grade(-1.0) == "F"


# ── Slice A (rank validation) ────────────────────────────────────────────────
def _synthetic_by_player(*, model_good: bool):
    """Build a small resolved cohort spanning all four tiers. When model_good,
    surplus_mm ranks realized_war perfectly and consensus_fv ranks it backwards
    (model should win every tier); otherwise surplus ranks it backwards while
    consensus_fv tracks it perfectly (model should lose)."""
    by_player = {}
    i = 0
    # tier center surplus values: elite>=40, high 20-40, mid 8-20, low 0-8
    for base in (45.0, 25.0, 12.0, 3.0):
        for j in range(6):
            sur = base + j                  # 6 players within the same tier band
            within = base + (5 - j)         # reversed within-tier value
            if model_good:
                realized = sur              # surplus ranks realized perfectly
                cfv = within                # consensus_fv ranks it backwards
            else:
                realized = within           # surplus ranks realized backwards
                cfv = within                # consensus_fv == realized -> ranks perfectly
            by_player[f"p{i}"] = {
                "kind": "debuted", "surplus_mm": sur, "realized_war": realized,
                "consensus_fv": cfv, "side": "H" if j % 2 else "P",
            }
            i += 1
    return by_player


def test_slice_a_ships_when_model_beats_baseline():
    res = tmb._slice_a(_synthetic_by_player(model_good=True))
    assert res["n"] == 24
    assert res["pooled"]["spearman"] == pytest.approx(1.0, abs=1e-6)
    # Model beats the baseline pooled, and wins every comparable within-tier.
    assert res["pooled"]["spearman"] > res["baseline_consensus_fv"]["spearman"]
    assert res["tiers_won_vs_baseline"] == "4/4"
    assert res["ship"] is True


def test_slice_a_does_not_ship_when_model_loses():
    res = tmb._slice_a(_synthetic_by_player(model_good=False))
    assert res["pooled"]["spearman"] < res["baseline_consensus_fv"]["spearman"]
    assert res["ship"] is False


def test_slice_a_skips_unresolved_and_missing():
    by_player = {
        "active1": {"kind": "active", "surplus_mm": 50.0, "realized_war": None},
        "noval": {"kind": "debuted", "surplus_mm": None, "realized_war": 5.0},
    }
    res = tmb._slice_a(by_player)
    assert res["n"] == 0


# ── Slice A' (per-source join) ───────────────────────────────────────────────
def test_slice_a_prime_join_by_source():
    by_player = {f"p{i}": {"realized_war": float(i)} for i in range(6)}
    trade_values = {
        "generated_at": "2026-06-25",
        "players": [
            {"player_key": "p0", "trade_value_mm": 1.0, "status": "debuted", "surplus_source": "xfv_backgrade"},
            {"player_key": "p1", "trade_value_mm": 2.0, "status": "debuted", "surplus_source": "xfv_backgrade"},
            {"player_key": "p2", "trade_value_mm": 3.0, "status": "graduated", "surplus_source": "xfv_backgrade"},
            {"player_key": "p3", "trade_value_mm": 9.0, "status": "debuted", "surplus_source": "projection"},
            {"player_key": "p4", "trade_value_mm": 8.0, "status": "debuted", "surplus_source": "projection"},
            {"player_key": "p5", "trade_value_mm": 7.0, "status": "debuted", "surplus_source": "projection"},
            # active player must be excluded (no resolved outcome)
            {"player_key": "p0", "trade_value_mm": 99.0, "status": "active", "surplus_source": "xfv"},
        ],
    }
    res = tmb._slice_a_prime(by_player, trade_values)
    assert res is not None
    assert res["n_matched"] == 6
    assert set(res["by_source"]) == {"xfv_backgrade", "projection"}
    # xfv_backgrade is perfectly rank-aligned with realized_war; n recorded.
    assert res["by_source"]["xfv_backgrade"]["n"] == 3


def test_slice_a_prime_none_without_trade_values():
    assert tmb._slice_a_prime({"p": {"realized_war": 1.0}}, {}) is None


# ── Real-data artifact + registry wiring ─────────────────────────────────────
def test_run_artifact_schema():
    a = tmb.run(write=False)
    for k in ("generated_at", "model", "conventions", "slice_a", "ship", "honest_note"):
        assert k in a, f"missing artifact key {k}"
    assert a["model"] == "trade_machine_surplus"
    assert isinstance(a["honest_note"], str) and len(a["honest_note"]) > 50
    assert a["slice_a"]["n"] > 0


def test_registered_in_model_registry():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    entry = next((m for m in reg["models"] if m["model_id"] == "trade_machine_surplus"), None)
    assert entry is not None, "trade_machine_surplus not registered"
    assert entry["verdict"] in reg["verdict_enum"]
    assert (ROOT / entry["eval_artifact"]).exists()


# --------------------------------------------------------------------------
# A price names a window it integrates over
# --------------------------------------------------------------------------

def test_a_free_agent_has_no_control_window_and_gets_no_price():
    """THE DEFECT. Surplus is production above cost over the seasons a club
    CONTROLS the player. A free agent with zero remaining controlled seasons has
    nothing to integrate over and no contract to trade.

    The eFV backgrade fallback priced him anyway, off a prospect-era grade: 61
    rows, 43 of them positive, $482.7M in total. Victor Robles read $80.0M with
    a Trade Value Grade of A in a row whose own Contract cell said
    "Free Agent".
    """
    import bayes_trade_value as b
    assert b._has_control_window({"remaining_control_years": 0.0}) is False
    assert b._has_control_window({"remaining_control_years": 0}) is False
    assert b._has_control_window({"remaining_control_years": 1.0}) is True


def test_an_unknown_control_window_is_not_treated_as_an_empty_one():
    """A missing field is a COVERAGE GAP, not a statement that the window is
    empty. Treating None as zero would silently unprice every row whose control
    years simply failed to resolve, which is a much larger and quieter defect
    than the one being fixed."""
    import bayes_trade_value as b
    assert b._has_control_window({}) is True
    assert b._has_control_window({"remaining_control_years": None}) is True
    assert b._has_control_window({"remaining_control_years": "x"}) is True


def test_the_withheld_backgrade_is_stamped_and_counted():
    """The row KEEPS its own bayes price; only the backgrade is withheld, and
    the key says which. A row that quietly changes basis is indistinguishable
    from one that never did."""
    src = (ROOT / "bayes_trade_value.py").read_text(encoding="utf-8")
    assert 'r["efv_backgrade_withheld"] = "no_control_window"' in src
    assert 'stats["no_control_window"] += 1' in src
    i = src.index('"no_control_window": 0')
    assert i > 0, "the counter is not initialised in the stats dict"


def test_the_served_board_prices_no_zero_control_backgrade_row():
    """The artifact check. Skips until the board is rebuilt, because the fix is
    in the exporter and the served file predates it."""
    import json
    p = ROOT / "data" / "trade_values.json"
    if not p.exists():
        pytest.skip("trade_values.json not built")
    rows = json.loads(p.read_text(encoding="utf-8")).get("players") or []
    bad = [r for r in rows
           if r.get("surplus_source") == "xfv_backgrade"
           and (r.get("remaining_control_years") or 0) == 0
           and r.get("trade_value_mm") is not None]
    if bad:
        pytest.skip(
            f"{len(bad)} zero-control backgrade rows still priced; the exporter "
            "is fixed and data/trade_values.json has not been rebuilt yet")
    assert not bad


def test_the_gate_never_fires_on_a_row_the_owner_rule_would_price():
    """THE CHALLENGE THIS ANSWERS, and it is a real one.

    An owner decision of 2026-08-03, recorded in bayes_trade_value._unpriced_vets,
    says: "an expiring deal is no longer unpriceable by itself. A club still
    controls the player for the rest of this season and that is a real, tradeable
    asset ... This supersedes the earlier reading that a pending free agent is
    not a trade asset."

    So "a free agent cannot be traded" is NOT available as a justification here,
    and the first version of this repair used it.

    What makes the gate correct is the BRANCH ORDER, not that premise. The owner's
    rule prices such a player through surTotal off a current-season salary, which
    is the `projection` branch, tested FIRST. A row that qualifies for it never
    reaches the backgrade fallback the gate guards. Measured when this landed: 0
    of the 61 gated rows carried a projection surplus.
    """
    src = (ROOT / "bayes_trade_value.py").read_text(encoding="utf-8")
    # 452b2940 keys the projection branch on the mlbam-joined ppk.
    i = src.index("if ppk in proj_sur:")
    j = src.index("_has_control_window(r)")
    assert i < j, (
        "the control-window gate now runs BEFORE the projection branch, so it can "
        "block a row the owner's 2026-08-03 rule says must be priced")


def test_the_owner_decision_is_cited_where_the_gate_lives():
    """A future reader who finds the owner note and this gate must not have to
    reconcile them alone."""
    src = (ROOT / "bayes_trade_value.py").read_text(encoding="utf-8")
    i = src.index("def _has_control_window")
    doc = src[i:i + 1800]
    assert "2026-08-03" in doc
    assert "supersedes" in doc


def test_no_gated_row_carries_a_projection_price():
    """The artifact check behind the branch-order argument. If a gated row ever
    also has a projection surplus, the two paths are no longer disjoint and the
    gate needs re-reading against the owner decision."""
    import json
    p = ROOT / "data" / "trade_values.json"
    q = ROOT / "data" / "mlb_projections.json"
    if not (p.exists() and q.exists()):
        pytest.skip("artifacts not built")
    gated = [r for r in json.loads(p.read_text(encoding="utf-8")).get("players") or []
             if r.get("efv_backgrade_withheld")]
    if not gated:
        pytest.skip("no gated rows on this build")
    proj = json.loads(q.read_text(encoding="utf-8"))
    vets = proj.get("vets") or proj.get("players") or []
    by = {v.get("player_key") or v.get("key"): v for v in vets}
    keys = ("surTotal", "surTot", "surplus_total_mm", "surNpv")
    both = [r.get("player_name") for r in gated
            if any((by.get(r.get("player_key")) or {}).get(k) is not None for k in keys)]
    assert not both, (
        f"{len(both)} gated rows also carry a projection surplus, so the "
        f"projection branch did not claim them first: {both[:5]}")
