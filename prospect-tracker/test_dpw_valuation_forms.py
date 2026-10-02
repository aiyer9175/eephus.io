# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""I7, the rate per valuation-set form, on a SYNTHETIC series (DESIGN_v2 2).

Under a net form (clemens_2026, whose literal form string is net_7_flat) the
nominal rate is the stored owner R and the escalator g_ref, so the net rate is
0.07 at the default R. Under rate_minus_growth (prospx_current) the nominal
rate is the set's own 0.09 and the escalator is STILL g_ref, never the set's
legacy growth, so the net rate is 1.09 / 1.0409 - 1, not the set's own 0.0381.
"""

from __future__ import annotations

import pytest

import dpw_testkit as kit
import valuation_sets as vs
import value_framework as vf


def test_both_committed_set_files_have_a_form():
    assert vs.discount_form("clemens_2026") == "net_flat"
    assert vs.discount_form_literal("clemens_2026") == "net_7_flat"
    assert vs.discount_form("prospx_current") == "rate_minus_growth"


def test_clemens_2026_reads_the_recorded_owner_rate(tmp_path):
    with vf.valuation_set("clemens_2026"):
        with kit.unified(tmp_path):
            assert vf.nominal_rate() == 0.113763
            assert vf.g_ref() == 0.0409
            assert vf.net_rate() == pytest.approx(0.07, abs=1e-12)
        with kit.unified(tmp_path, R=0.10):
            assert vf.nominal_rate() == 0.10
            assert vf.net_rate() == pytest.approx(1.10 / 1.0409 - 1.0, rel=1e-12)


def test_prospx_current_keeps_its_nominal_rate_and_reads_g_ref(tmp_path):
    with vf.valuation_set("prospx_current"):
        cfg = vf._config()
        assert float(cfg["discount_rate"]) == 0.09
        assert float(cfg["dollars_per_war_inflation"]) == 0.05
        with kit.unified(tmp_path):
            assert vf.nominal_rate() == 0.09
            assert vf.g_ref() == 0.0409
            assert vf.net_rate() == pytest.approx(1.09 / 1.0409 - 1.0, rel=1e-12)
            assert vf.net_rate() == pytest.approx(0.0472, abs=1e-4)
            assert abs(vf.net_rate() - (1.09 / 1.05 - 1.0)) > 0.008


def test_the_resolved_config_is_not_changed_by_the_form_helper():
    before = dict(vf._config())
    vs.discount_form("clemens_2026")
    vs.discount_form("prospx_current")
    assert dict(vf._config()) == before
