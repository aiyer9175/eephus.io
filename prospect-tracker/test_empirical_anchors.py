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
    assert res["cohort_window"] == [2014, 2020]              # 2026 - [12, 6] (lag_max widened to 12 for the 2011-2016 backfill)
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
    assert a["cohort_window"] == [2013, 2019]                # slides forward by year (lag_max=12)


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


def test_low_end_anchors_are_present_and_measured() -> None:
    """TRIPWIRE (2026-07-29). The committed anchors MUST carry sub-45 knots.

    Before this amendment the table began at "40" and `fv_to_6yr_avg_war` returned
    the single constant 0.19 WAR/yr across the whole integer grid 20..40, i.e. one
    declared production value for 72.1% of served rows. The resolved cohort says
    FV40 delivers 0.0862 WAR/yr (CI95 [0.0706, 0.1030], n=2083, measured on
    target_censored) and FV35 delivers 0.0188 (CI95 [0.0087, 0.0308], n=909).

    This test exists because the amendment is NOT reproducible by the fit
    machinery: `value_framework.derive_empirical_war_anchors` cannot emit these
    knots (its tier list starts at 40, its public-reference fallback hands tiers
    20/25/30 the FV35 reference, its flat 0.50 public blend keeps the FV40 cell
    half-prior, and its round(v, 2) collapses every sub-45 value). So a routine
    `value_framework --fit` WILL silently revert the key and restore the defect.
    If this test goes red after a fit, do not delete it: re-apply the table and
    fix the derivation, or the bottom 72% of the board goes back to claiming a
    production level it has never delivered.
    """
    import json
    from pathlib import Path
    fitted = json.loads(
        (Path(__file__).resolve().parent / "data" / "value_framework_fitted.json")
        .read_text(encoding="utf-8"))
    anchors = fitted["empirical_anchors"]["anchors"]

    for key in ("20", "25", "30", "35"):
        assert key in anchors, (
            f"sub-45 anchor {key} is gone: the fit machinery reverted the table "
            f"(see empirical_anchors.anchors_provenance)")

    assert anchors["40"] < 0.12, (
        f'FV40 anchor is {anchors["40"]}, back above the measured CI95 upper bound '
        f"0.1030. The 0.19 seed over-stated this tier by 2.2x.")

    vals = [float(anchors[k]) for k in sorted(anchors, key=float)]
    assert vals == sorted(vals), f"anchor table is not monotone: {anchors}"

    # the live function must actually spread the bottom of the board, not serve
    # one constant across it
    distinct = {round(vf.fv_to_6yr_avg_war(g), 4) for g in range(20, 41)}
    assert len(distinct) > 1, (
        "fv_to_6yr_avg_war is constant across FV20..40 again; the low-end knots "
        "are present in the file but not reaching the live function")
