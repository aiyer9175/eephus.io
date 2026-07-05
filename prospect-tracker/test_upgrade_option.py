# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Phase 7 (Tier 2) -- upgrade-option layer: transition estimation, the absorbing
Markov valuation, and the OPT% acceptance (45 FV a high-option call, 60 FV not)."""
import json
from pathlib import Path

import numpy as np
import pytest

import upgrade_option as uo

_DATA = Path(uo.__file__).resolve().parent / "data"


def test_data_sufficient():
    assert uo.data_sufficient() is True


@pytest.mark.parametrize("is_pit", [False, True])
def test_transition_matrix_is_row_stochastic(is_pit):
    P = uo.transition_matrix(is_pit)
    assert P.shape == (len(uo.GRADES), len(uo.GRADES) + 2)
    assert np.allclose(P.sum(axis=1), 1.0)
    assert (P >= 0).all()


def test_snap_tier():
    assert uo._snap_tier(47.5) == 50 or uo._snap_tier(47.5) == 45  # nearest 5
    assert uo._snap_tier(32) == 35   # clamped low
    assert uo._snap_tier(99) == 70   # clamped high
    assert uo._snap_tier(60) == 60


def test_valuation_structure_and_identity():
    v = uo.option_valuation(False)
    assert v["role"] == "hitter" and v["set_id"] == "clemens_2026"
    for g, r in v["grades"].items():
        # option = total - intrinsic (definition)
        assert r["option_musd"] == pytest.approx(r["total_musd"] - r["intrinsic_musd"], abs=0.02)
        assert 0 <= r["p_graduate_annual"] <= 1
        assert r["n_obs"] >= 0


def test_acceptance_45_is_high_option_60_is_not():
    h = uo.option_valuation(False)["grades"]
    # 45 FV hitter: mostly option value (upside-driven)
    assert h[45]["opt_pct"] > 0.50
    # 60 FV hitter: OPT% well below the 45 FV (little upside, downgrade risk)
    assert h[60]["opt_pct"] < h[45]["opt_pct"]
    # Option value monotonically less optionful as grade rises across the thick tiers.
    assert h[35]["opt_pct"] > h[40]["opt_pct"] > h[45]["opt_pct"]


def test_config_prior_mode_runs():
    v = uo.option_valuation(False, mode="config_prior")
    assert v["mode"] == "config_prior"
    assert v["grades"][45]["opt_pct"] > 0.0   # the labelled 20% upgrade prior gives upside


def test_eval_artifact_present_and_gate_passes():
    doc = json.loads((_DATA / "upgrade_option_eval.json").read_text(encoding="utf-8"))
    assert doc["experiment"] == "upgrade-option-layer"
    assert doc["gate"]["pass"] is True
    assert set(doc["roles"]) == {"hitter", "pitcher"}
