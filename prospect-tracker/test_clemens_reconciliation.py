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
    #
    # 2026-07-31: the tripwire DID trip, and it was re-examined rather than widened, which
    # is what it was for. The v6 EV calibration
    # (docs/efv-2026-07-30/SURPLUS_EV_OBJECTIVE.md) moved the model scale 29.6 -> 40.5.
    # This is NOT the board jumping to table scale: the table moved too, in the same
    # change, 32.8 -> 43.4, and the model still runs clearly BELOW it. The invariant this
    # test exists to pin is the model/table SEPARATION, so the guard is re-expressed below
    # as that separation instead of an absolute dollar ceiling, which was only ever a
    # proxy for it and one that any re-price would trip.
    assert vf.surplus_value_mm(50.0, False) == pytest.approx(40.5, abs=0.6)
    with vf.valuation_set("prospx_current"):
        table_50 = vf.surplus_value_mm(50.0, False)
    assert vf.surplus_value_mm(50.0, False) < table_50 - 1.0, (
        "the model FV50 price must stay materially below the prospx_current TABLE price; "
        "if these converge the board has been snapped to table scale")


def test_fit_reported_not_forced():
    # The best-fit anchor multiplier LOWERS the mean deviations but leaves a
    # non-zero residual (a single scalar cannot zero a two-functional tier curve);
    # a per-tier snap would drive these to ~0. This is the anti-snap pin.
    fit = vf.fit_tier_reconciliation("clemens_2026")
    for role in ("hitter", "pitcher"):
        d = fit["roles"][role]
        # k FLIPPED SIDES on 2026-07-31 and that is a real finding, not a restamp.
        # It used to be > 1.0 because the model ran BELOW the published tiers and k
        # lifted it. Under the v6 EV calibration the model runs ABOVE them (hitter
        # k=0.90, pitcher k=0.95, both interior to the 0.5-4.0 grid, so the fit
        # converged rather than clamping). That is the expected direction: the
        # published table is a per-player realisation figure while our surplus is now
        # a tier EXPECTATION, and an expectation on a lottery-shaped population sits
        # above the typical realisation. What this test pins is that k is FIT, not
        # forced, so assert it is a real non-trivial fit rather than its direction.
        assert 0.5 < d["k"] < 4.0 and abs(d["k"] - 1.0) > 0.01
        # The joint objective (what the fitter actually minimises) must improve...
        j_pre = d["pre"]["surplus_mean_pct_dev"] + d["pre"]["star_mean_abs_dev"]
        j_post = d["post"]["surplus_mean_pct_dev"] + d["post"]["star_mean_abs_dev"]
        assert j_post < j_pre
        # ...and the star residual stays clearly above zero (not snapped). It no longer
        # improves: one scalar buys surplus accuracy by paying in star odds, which is
        # exactly the "a single scalar cannot zero a two-functional curve" claim in the
        # docstring, now visible in the numbers instead of only asserted in prose.
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
        # Re-stamped 2026-07-31: 32.8 -> 43.4 with the v6 EV calibration
        # (docs/efv-2026-07-30/SURPLUS_EV_OBJECTIVE.md).
        # Re-stamped 2026-08-04: 43.4 -> 47.4 for the R7 dpw re-anchor. Unlike
        # the two moves above this is NOT a calibration change: the
        # FA-signings-implied $/WAR series was regenerated (2026 winter
        # 14.92M -> 17.29M, +15.9%) and prospx_current leaves the FA-implied
        # rescale ON, so its tier grid lifts about 10.5% on win cost alone.
        base_50 = vf.surplus_value_mm(50.0, False)
        assert base_50 == pytest.approx(47.4, abs=0.1)
    # The CACHE-CLEARING fact this test exists for, stated scale-free so a future
    # re-price restamps one literal instead of silently voiding the guard: the two
    # contexts must price differently, and leaving must restore the clemens price.
    assert abs(base_50 - clemens_50) > 1.0
    assert vf.surplus_value_mm(50.0, False) == pytest.approx(clemens_50, abs=0.01)


def test_surplus_tier_calibration_structure():
    rep = vf.surplus_tier_calibration("clemens_2026")
    assert set(rep["roles"]) == {"hitter", "pitcher"}
    for role in ("hitter", "pitcher"):
        d = rep["roles"][role]
        assert "max_abs_pct_dev" in d and "mean_abs_pct_dev" in d and d["tiers"]
        for row in d["tiers"]:
            assert {"tier", "fv", "published", "model", "abs_dev", "pct_dev"} <= set(row)
