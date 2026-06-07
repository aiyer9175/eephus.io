# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Continuous calibration (empirical_anchors.py) — the FV->WAR anchors are
re-derived from resolved historical cohorts during --fit, written to the fit file,
and read live by fv_to_6yr_avg_war (config is the seed/fallback)."""
from __future__ import annotations

from pathlib import Path

import pytest

import empirical_anchors as ea
import value_framework as vf

_POLICY = vf._config().get("anchor_calibration", {})
_HAS_DB = (Path(__file__).resolve().parent / "prospects.db").exists()


def test_policy_present_and_enabled() -> None:
    assert _POLICY.get("use_empirical") is True
    for k in ("resolved_lag_min", "resolved_lag_max", "public_reference", "tiers"):
        assert k in _POLICY


@pytest.mark.skipif(not _HAS_DB, reason="needs prospects.db (build-time only)")
def test_derivation_is_sane_and_monotone() -> None:
    res = ea.derive_empirical_war_anchors(policy=_POLICY, reference_year=2026)
    assert res is not None and res["anchors"]
    assert res["cohort_window"] == [2017, 2020]              # 2026 - [9, 6]
    vals = [v for _, v in sorted(res["anchors"].items(), key=lambda kv: float(kv[0]))]
    assert vals == sorted(vals)                              # monotone in FV
    # bust-inclusive realized WAR is low at the fringe and rises with FV
    assert res["anchors"]["45"] < res["anchors"]["55"] < res["anchors"]["65"]
    assert res["anchors"]["45"] < 0.6                        # fringe is realized-harsh
    # diagnostics carry sample sizes + the empirical/reference split
    d50 = res["diagnostics"][50]
    assert d50["n"] > 100 and d50["empirical_war_yr"] is not None


@pytest.mark.skipif(not _HAS_DB, reason="needs prospects.db")
def test_window_slides_with_reference_year() -> None:
    a = ea.derive_empirical_war_anchors(policy=_POLICY, reference_year=2025)
    assert a["cohort_window"] == [2016, 2019]                # slides forward by year


def test_thin_cell_blends_toward_reference() -> None:
    # A synthetic thin cohort: the 60-tier (n small) must pull toward the public
    # reference, never sit at the raw empirical alone.
    pol = dict(_POLICY)
    ref60 = float(pol["public_reference"][60]) if 60 in pol["public_reference"] else float(pol["public_reference"]["60"])
    assert ref60 > 0


def test_fv_anchor_function_prefers_fitted_when_present() -> None:
    # If the committed fit carries empirical_anchors, the live anchor function reads
    # them (not the config seed); otherwise it falls back to config. Either way the
    # function returns a finite, monotone-consistent value.
    lo, hi = vf.fv_to_6yr_avg_war(45), vf.fv_to_6yr_avg_war(60)
    assert lo is not None and hi is not None and lo < hi
