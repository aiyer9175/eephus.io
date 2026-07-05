# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Phase 5 -- validation/sensitivity/diff harness: universe load, the pure
rollup helpers, and the residence-time reconciliation arithmetic."""
import pytest

import valuation_sets as vs
import value_framework as vf
from tools import build_valuation_reports as br


def test_universe_loads():
    universe, asof = br.load_universe()
    assert universe and asof
    p = universe[0]
    assert {"player_key", "fv", "is_pitcher", "org"} <= set(p)
    assert all(isinstance(x["fv"], float) for x in universe[:50])


def test_split_5050():
    universe = [
        {"player_key": "a", "fv": 45.0},
        {"player_key": "b", "fv": 50.0},
        {"player_key": "c", "fv": 60.0},
    ]
    per = {"a": 10.0, "b": 20.0, "c": 30.0}
    sub, ge = br._split_5050(universe, per)
    assert sub == 10.0            # only the 45 FV is sub-50
    assert ge == 50.0             # 50 + 60


def test_table_sum_matches_engine():
    universe = [
        {"player_key": "h50", "fv": 50.0, "is_pitcher": False, "org": "X", "position": None, "age": None},
        {"player_key": "p50", "fv": 50.0, "is_pitcher": True, "org": "X", "position": None, "age": None},
    ]
    total, per, per_org = br._sum_table_surplus(universe, "clemens_2026", vs)
    assert per["h50"] == pytest.approx(45.0, abs=0.05)   # clemens 50 hitter
    assert per["p50"] == pytest.approx(33.5, abs=0.05)   # clemens 50 pitcher
    assert total == pytest.approx(78.5, abs=0.1)
    assert per_org["X"] == pytest.approx(78.5, abs=0.1)


def test_residence_reconciliation_arithmetic():
    residence = float(vs.load("clemens_2026")["params"]["residence"]["central_years"])
    assert residence == 2.0
    sub_stock = 12.0
    assert sub_stock / residence == pytest.approx(6.0)


def test_default_set_restored_after_report_pricing():
    # The harness switches sets; ensure nothing leaves the engine off-default
    # (the production default is now clemens_2026).
    br.load_universe()
    assert vf.active_valuation_set() == "clemens_2026"
