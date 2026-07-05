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
    engine = vf.surplus_value_mm(fv, is_pit)
    assert table == pytest.approx(engine, abs=0.05), (
        f"{label} {'pit' if is_pit else 'hit'}: table {table} != engine {engine}")


# --------------------------------------------------------------------------
# Default is production; overlay is a no-op for the default set
# --------------------------------------------------------------------------
def test_default_is_prospx_current_and_no_overlay_leak():
    assert vf.active_valuation_set() == "prospx_current"
    cfg = vf._config()
    assert cfg["_valuation_set"] == "prospx_current"
    # Base config untouched by any overlay.
    assert int(cfg["service_time"]["control_years"]) == 6
    assert list(cfg["service_time"]["arb_model"]["fractions_of_fa_value"]) == [0.40, 0.60, 0.80]


# --------------------------------------------------------------------------
# clemens_2026 overlay applies its params, then restores cleanly
# --------------------------------------------------------------------------
def test_clemens_overlay_applies_and_restores():
    base_50 = vf.surplus_value_mm(50.0, False)
    with vf.valuation_set("clemens_2026"):
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
    # restored
    assert vf.active_valuation_set() == "prospx_current"
    assert vf.surplus_value_mm(50.0, False) == pytest.approx(base_50, abs=0.01)
    assert vf._config()["_valuation_set"] == "prospx_current"


def test_engine_params_translation_units():
    ep = vs.engine_params("clemens_2026")
    assert ep["dollars_per_war"]["tiered"]["rates"]["1_to_2"] == pytest.approx(8.76e6, rel=1e-9)
    assert ep["service_time"]["control_years"] == 7
    assert ep["discount_rate"] == 0.07
    # default set params are documentation only, but the translator still works:
    ep0 = vs.engine_params("prospx_current")
    assert ep0["service_time"]["control_years"] == 6
