# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Phase 5 model<->table reconciliation DIAGNOSTIC: the per-role WAR-anchor
multiplier is REPORTED, never FORCED onto the live board. These tests pin that
contract so a future edit that bakes a scale into the shipped set (which would
silently rescale the production board toward the ~2x published table) fails loudly.
"""
import copy

import pytest

import valuation_sets as vs
import value_framework as vf


def test_war_anchor_scale_default_identity():
    # The production default (clemens_2026) carries NO war_anchor_scale, so the
    # lever is identity and the live board is NOT rescaled to the published table.
    assert vf.active_valuation_set() == "clemens_2026"
    assert vf._war_anchor_scale_for("hitter") == 1.0
    assert vf._war_anchor_scale_for("pitcher") == 1.0
    assert "war_anchor_scale" not in vf._config()


def test_shipped_sets_carry_no_reconciliation_scale():
    # Neither shipped set may hard-code a war-anchor / calibration scale: the
    # reconciliation is diagnostic-only. If one is ever added the board would jump
    # to ~table scale, so this guard must fail first.
    for sid in ("prospx_current", "clemens_2026"):
        params = vs.load(sid).get("params") or {}
        assert "calibration" not in params, f"{sid} must not ship a calibration/anchor scale"
        assert "war_anchor_scale" not in params


def test_surplus_50_hitter_stays_model_scale_not_table():
    # Production surplus for a 50 FV hitter is the MODEL value, NOT the published table
    # $45M. The reconciliation does not move it.
    # Literal restamped 2026-07-29: 18.5 -> 29.6. That is the third pre-v5 literal in this
    # cluster (the others were 28.2 and a v3-era 17.7, both now 32.8); the v5 surplus
    # calibration moved the model scale and these assertions were never restamped with it.
    # The test's PURPOSE is intact and verified: the model value 29.6 is still distinct from
    # the prospx_current TABLE value 32.8, which is the thing this test exists to pin.
    # NOTE the headroom: the < 30.0 guard below now clears by only 0.4, so the next upward
    # move in the model scale will trip it. That is deliberate. It is the tripwire for "the
    # board jumped to table scale", and it should be re-examined rather than widened.
    assert vf.surplus_value_mm(50.0, False) == pytest.approx(29.6, abs=0.6)
    assert vf.surplus_value_mm(50.0, False) < 30.0


def test_fit_reported_not_forced():
    # The best-fit anchor multiplier LOWERS the mean deviations but leaves a
    # non-zero residual (a single scalar cannot zero a two-functional tier curve);
    # a per-tier snap would drive these to ~0. This is the anti-snap pin.
    fit = vf.fit_tier_reconciliation("clemens_2026")
    for role in ("hitter", "pitcher"):
        d = fit["roles"][role]
        assert d["k"] > 1.0  # model runs below the published tiers, so k lifts it
        # star-odds residual improves but stays clearly above zero (not snapped)
        assert d["post"]["star_mean_abs_dev"] < d["pre"]["star_mean_abs_dev"]
        assert d["post"]["star_mean_abs_dev"] > 0.01
        # surplus residual likewise stays materially non-zero
        assert d["post"]["surplus_mean_pct_dev"] > 0.05


def test_fit_restores_production_pricing():
    # Running the diagnostic must not leave the engine rescaled.
    before = vf.surplus_value_mm(50.0, False)
    vf.fit_tier_reconciliation("clemens_2026")
    assert vf.surplus_value_mm(50.0, False) == pytest.approx(before, abs=0.01)
    assert "war_anchor_scale" not in vf._config()
    assert vf.active_valuation_set() == "clemens_2026"


def test_war_anchor_scale_lever_moves_both_surplus_and_star():
    # When the lever IS set (as the diagnostic does transiently), it raises BOTH
    # surplus and star odds -- confirming it is the single shared upstream anchor.
    base_surplus = vf.surplus_value_mm(55.0, False)
    base_star = vf.star_odds(55.0, False)
    cfg = vf._config()
    try:
        cfg["war_anchor_scale"] = {"hitter": 1.5}
        vf._reset_derived_caches()
        assert vf.surplus_value_mm(55.0, False) > base_surplus
        assert vf.star_odds(55.0, False) > base_star
    finally:
        cfg.pop("war_anchor_scale", None)
        vf._reset_derived_caches()
    # reverted
    assert vf.surplus_value_mm(55.0, False) == pytest.approx(base_surplus, abs=0.01)


def test_cache_cleared_on_set_switch():
    # _fv_war_scale is cached but reads the active set's config; set_valuation_set
    # must clear it (guards the _reset_caches edit). Price under clemens, switch to
    # the base-identity set, and the value must revert to the legacy scale.
    clemens_50 = vf.surplus_value_mm(50.0, False)
    with vf.valuation_set("prospx_current"):
        # Re-stamped 2026-07-29: 17.7 -> 32.8. The 17.7 was a v3-era literal that was
        # never restamped through v4 or v5, so this assertion had been pinning a price
        # two calibration versions stale. It asserts the base-identity FV50 price, which
        # is the same fact the prospx_current tier re-capture carries.
        assert vf.surplus_value_mm(50.0, False) == pytest.approx(32.8, abs=0.1)
    assert vf.surplus_value_mm(50.0, False) == pytest.approx(clemens_50, abs=0.01)


def test_surplus_tier_calibration_structure():
    rep = vf.surplus_tier_calibration("clemens_2026")
    assert set(rep["roles"]) == {"hitter", "pitcher"}
    for role in ("hitter", "pitcher"):
        d = rep["roles"][role]
        assert "max_abs_pct_dev" in d and "mean_abs_pct_dev" in d and d["tiers"]
        for row in d["tiers"]:
            assert {"tier", "fv", "published", "model", "abs_dev", "pct_dev"} <= set(row)
