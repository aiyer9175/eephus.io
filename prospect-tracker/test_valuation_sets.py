# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Phase 1 -- versioned valuation sets: load, checksums, null-rejection, table
mode reproduces production, and the clemens_2026 engine overlay applies (and
restores) without touching the default (production) path."""
import copy

import pytest

import valuation_sets as vs
import value_framework as vf


# --------------------------------------------------------------------------
# Load + checksums
# --------------------------------------------------------------------------
def test_both_sets_load_and_checksums_pass():
    for sid in ("prospx_current", "clemens_2026"):
        data = vs.load(sid)
        assert data["id"] == sid
    # clemens_2026 loading at all means its checksum block passed.
    assert set(vs.available()) >= {"prospx_current", "clemens_2026"}


def test_alias_resolves():
    assert vs.load("edwards_2019")["id"] == "prospx_current"
    with vf.valuation_set("edwards_2019"):
        assert vf.active_valuation_set() == "prospx_current"


def test_clemens_checksum_values_exact():
    assert vs.table_value_musd("clemens_2026", 50.0, False) == pytest.approx(45.0, abs=0.05)
    assert vs.table_value_musd("clemens_2026", 50.0, True) == pytest.approx(33.5, abs=0.05)
    assert vs.table_value_musd("clemens_2026", 45.0, False) == pytest.approx(14.5, abs=0.05)
    assert vs.table_value_musd("clemens_2026", 47.5, False) == pytest.approx(18.5, abs=0.05)
    assert vs.table_value_musd("clemens_2026", 40.0, False) == pytest.approx(5.5, abs=0.05)
    assert 150.0 <= vs.table_value_musd("clemens_2026", 70.0, False) <= 200.0
    assert vs.table_star_odds("clemens_2026", 50.0, False) == pytest.approx(0.135, abs=0.001)
    assert vs.table_star_odds("clemens_2026", 50.0, True) == pytest.approx(0.070, abs=0.001)


# --------------------------------------------------------------------------
# Loader refuses malformed / null sets, and a corrupted checksum tier
# --------------------------------------------------------------------------
def test_loader_rejects_null_required_field():
    good = copy.deepcopy(vs.load("clemens_2026"))
    good["tiers"]["hitter"]["50"]["surplus_musd"] = None
    with pytest.raises(vs.ValuationSetError):
        vs._validate(good, "clemens_2026")


def test_loader_rejects_checksum_drift():
    bad = copy.deepcopy(vs.load("clemens_2026"))
    bad["tiers"]["hitter"]["50"]["surplus_musd"] = 40.0   # was 45.0
    with pytest.raises(vs.ValuationSetError):
        vs._validate_checksums(bad, "clemens_2026")


def test_unknown_set_raises():
    with pytest.raises(vs.ValuationSetError):
        vs.load("no_such_set")


# --------------------------------------------------------------------------
# ACCEPTANCE: prospx_current table mode reproduces current production exactly
# (at the tier grid) -- table_value == the live engine surplus_value_mm.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("label,fv", [
    ("35+", 37.5), ("40", 40.0), ("40+", 42.5), ("45", 45.0), ("45+", 47.5),
    ("50", 50.0), ("55", 55.0), ("60", 60.0), ("65", 65.0), ("70", 70.0),
])
@pytest.mark.parametrize("is_pit", [False, True])
def test_prospx_current_table_mode_matches_production(label, fv, is_pit):
    table = vs.table_value_musd("prospx_current", fv, is_pit)
    # prospx_current is now the BASE-IDENTITY set (no longer the default): its
    # table mode reproduces the LEGACY engine, so price the engine in its context.
    with vf.valuation_set("prospx_current"):
        engine = vf.surplus_value_mm(fv, is_pit)
    assert table == pytest.approx(engine, abs=0.05), (
        f"{label} {'pit' if is_pit else 'hit'}: table {table} != engine {engine}")


# --------------------------------------------------------------------------
# Default is clemens_2026 (MODEL mode); prospx_current is the base-identity no-op
# --------------------------------------------------------------------------
def test_default_is_clemens_2026_and_base_identity_no_op():
    # Production default flipped 2026-07 to clemens_2026 (MODEL mode).
    assert vf.active_valuation_set() == "clemens_2026"
    cfg = vf._config()
    assert cfg["_valuation_set"] == "clemens_2026"
    # clemens params applied on the default path.
    assert int(cfg["service_time"]["control_years"]) == 7
    assert list(cfg["service_time"]["arb_model"]["fractions_of_fa_value"]) == [0.15, 0.35, 0.50, 0.75]
    # The base-identity set (prospx_current) overlay is a no-op: selecting it
    # re-prices to the exact legacy base config.
    with vf.valuation_set("prospx_current"):
        cfg0 = vf._config()
        assert cfg0["_valuation_set"] == "prospx_current"
        assert int(cfg0["service_time"]["control_years"]) == 6
        assert list(cfg0["service_time"]["arb_model"]["fractions_of_fa_value"]) == [0.40, 0.60, 0.80]


# --------------------------------------------------------------------------
# clemens_2026 (the default) applies its params; a context switch restores cleanly
# --------------------------------------------------------------------------
def test_clemens_default_applies_and_context_restores():
    # clemens_2026 is the default, so its overlay params ARE the live config.
    cfg = vf._config()
    assert cfg["_valuation_set"] == "clemens_2026"
    assert int(cfg["service_time"]["control_years"]) == 7
    assert list(cfg["service_time"]["arb_model"]["fractions_of_fa_value"]) == [0.15, 0.35, 0.50, 0.75]
    assert cfg["service_time"]["arb_basis"] == "prior_season"
    assert float(cfg["discount_rate"]) == pytest.approx(0.07)
    assert float(cfg["dollars_per_war_inflation"]) == pytest.approx(0.0)
    # fa_implied disabled -> tier rates stay at the published FG figures.
    assert cfg["dollars_per_war"]["fa_implied"]["enabled"] is False
    assert float(cfg["dollars_per_war"]["tiered"]["rates"]["lt_1"]) == pytest.approx(6.97e6, rel=1e-6)
    assert float(cfg["dollars_per_war"]["tiered"]["rates"]["2plus"]) == pytest.approx(13.63e6, rel=1e-6)
    assert cfg["star_definition"]["min_seasons"] == 2
    assert cfg["star_definition"]["war_threshold"] == 4.0
    base_50 = vf.surplus_value_mm(50.0, False)
    # Entering the base-identity context prices the legacy value; leaving restores
    # the clemens default (params + priced value).
    with vf.valuation_set("prospx_current"):
        assert vf.active_valuation_set() == "prospx_current"
        assert int(vf._config()["service_time"]["control_years"]) == 6
        # Re-stamped 2026-07-24b: LANE B1 linearmap-v5 surplus recalibration (accuracy
        # re-fit superseding the same-day v4) set the base-identity FV50 priced value to
        # 28.2 (v3 17.7 -> v4 31.6 -> v5 28.2). The prospx_current tier grid was re-captured
        # in the same change. Deliberate engine-moved tripwire firing on an intended move.
        # Re-stamped 2026-07-29: 28.2 -> 32.8. This is the SAME v5 ship, not a new price
        # move. The 07-24b re-capture above was never actually run against the engine, so
        # the frozen grid sat about 16% under live for five days and 16 acceptance cases
        # were red. The engine has been serving 32.8 the whole time. Grid history at FV50
        # hitter: v3 17.7 -> v4 31.6 -> v5 28.2(claimed) -> 32.8(measured).
        # Re-stamped 2026-07-31: 32.8 -> 43.4, the isotonic-real-v6-evframe re-fit. This
        # one is an OBJECTIVE change, not an accuracy re-fit: surplus became an
        # expected-value quantity (docs/efv-2026-07-30/SURPLUS_EV_OBJECTIVE.md), so the
        # map targets the conditional MEAN instead of the MAE-optimal median. The median
        # on this population is $0 for two thirds of the board, which is why the old map
        # clamped a $0 bottom; the mean is not zero, so every tier lifts. Held-out bias
        # -0.028 vs +2.521 uncalibrated, slope 1.059 vs 1.239. Deliberate.
        # RESTAMPED 2026-08-04 for the R7 dpw re-anchor, 43.4 -> 47.4. This is a
        # WIN-COST move, not another objective change: the FA-signings-implied
        # $/WAR series was regenerated and the 2026 winter went 14.92M -> 17.29M
        # (+15.9%), trailing-3 mean 14.89M -> 16.61M (+11.6%). prospx_current
        # leaves the FA-implied rescale ON (params.win_cost.disable_fa_implied
        # is false), so its whole tier grid lifts about 10.5% and FV50 hit is
        # the grid point this test happens to pin. ctrl_war did not move: the
        # anchors are unchanged, only what a win costs.
        # RESTAMPED 2026-09-04 for the eWAR LABEL EPOCH, 47.4 -> 48.2. career_war was
        # rebased to eWAR v2 and `value_framework --fit` re-derived the empirical WAR
        # anchors on the new label, so the FV-to-WAR map moved and the whole tier grid
        # moved with it. This is an ANCHOR move, not a win-cost move: FV45 goes 0.31 to
        # 0.32 WAR/yr and FV50 0.67 to 0.68, while FV70 goes 2.52 to 2.49, which is why
        # the top of the grid is the only place that falls (hit FV70 226.7 -> 223.2).
        # The prospx_current tier grid was re-captured INSIDE this set in the same change.
        # ctrl_war DID move at the bottom this time, and for a separate reason recorded in
        # data/value_framework_fitted.json anchors_provenance: the routine --fit reverted
        # the sub-45 knots to a single 0.19 constant across FV20..40, they were re-measured
        # on the eWAR label (FV35 0.0069, FV40 0.0710) and re-applied, so 35+ ctrl_war goes
        # 0.32 -> 0.23 and 40 goes 0.52 -> 0.43.
        assert vf.surplus_value_mm(50.0, False) == pytest.approx(48.2, abs=0.1)
    assert vf.active_valuation_set() == "clemens_2026"
    assert vf.surplus_value_mm(50.0, False) == pytest.approx(base_50, abs=0.01)
    assert vf._config()["_valuation_set"] == "clemens_2026"


def test_engine_params_translation_units():
    ep = vs.engine_params("clemens_2026")
    assert ep["dollars_per_war"]["tiered"]["rates"]["1_to_2"] == pytest.approx(8.76e6, rel=1e-9)
    assert ep["service_time"]["control_years"] == 7
    assert ep["discount_rate"] == 0.07
    # base-identity set params mirror the base config (its overlay is a no-op),
    # but the translator still works:
    ep0 = vs.engine_params("prospx_current")
    assert ep0["service_time"]["control_years"] == 6
