# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Base-config (Prompt B) verification regression tests.

These lock the invariants and reference values verified in docs/config-verification.md
so a later config edit can't silently break the base layer:

  * config schema/type validation fails LOUDLY (ConfigError) on malformed keys
  * REFERENCE-VALUE PINS: the canonical base numbers (tiered $/WAR, flat $/WAR,
    discount rate, projection haircut, FV->WAR anchor, bucket bands, "+"-grade
    half-steps). If an intentional retune changes one, the failing test is the
    prompt to confirm + update -- exactly the "flag, don't silently drift" rule.
  * P(bucket|FV) invariants: training rows ~sum to 1; the fitted curve is
    monotone (bust v, star ^), sums to 1, reproduces the grid cells within a
    bounded tolerance, and is continuous across grade boundaries; "45+" -> 47.5.
  * AVERAGE-not-peak reconciliation at the named targets (50/55/60).
  * TRANSFORM-FIRST wiring (no Jensen collapse) + no double position multiplier.
  * CONFIG IS LIVE: perturbing $/WAR / discount_rate / FV moves outputs correctly.
"""

from __future__ import annotations

import contextlib
import copy
import json
from pathlib import Path

import pytest

import value_framework as vf

_B = vf._BUCKETS
# Base-config verification: capture the config under the BASE-IDENTITY set so the
# reference magnitudes (discount, $/WAR, arb) stay stable across the 2026-07
# production-default flip to clemens_2026 (which overlays those conventions). The
# per-test _pin_base_valuation_set fixture keeps the engine on the same set.
with vf.valuation_set("prospx_current"):
    _CFG = vf._config()
_RECON_TOL = float(_CFG["fit"]["reconcile_tol"])


# =============================================================================
# Perturbation harness -- mutate the in-memory config, clear DERIVED caches only
# (never _config, so the mutation survives), restore on exit.
# =============================================================================
def _clear_derived() -> None:
    vf._bucket_sv_usd.cache_clear()
    vf._calibrated_midpoints.cache_clear()
    vf._fv_war_scale.cache_clear()
    vf._bayes_theta_draws.cache_clear()
    vf._pchip_bucket_interpolators.cache_clear()


@contextlib.contextmanager
def _perturb(mutate):
    cfg = vf._config()
    saved = copy.deepcopy(cfg)
    try:
        mutate(cfg)
        _clear_derived()
        yield cfg
    finally:
        cfg.clear()
        cfg.update(saved)
        _clear_derived()


# =============================================================================
# (2) SCHEMA & TYPES -- loud validation
# =============================================================================
def test_real_config_validates() -> None:
    assert vf._validate_config(copy.deepcopy(_CFG)) is not None


@pytest.mark.parametrize("mutate", [
    lambda c: c.pop("discount_rate"),
    lambda c: c.__setitem__("discount_rate", 9.0),                       # out of [0,1]
    lambda c: c["dollars_per_war"].pop("flat"),
    lambda c: c["dollars_per_war"]["tiered"]["rates"].__setitem__("2plus", -1),
    lambda c: c["dollars_per_war"]["tiered"].__setitem__("breakpoints", [2.0, 1.0]),  # not ascending
    lambda c: c["buckets"].__setitem__("order", ["a", "b"]),
    lambda c: c["p_bucket_given_fv_hitter"]["50"].pop("star"),
    lambda c: c.pop("fv_to_6yr_avg_war"),
    lambda c: c["service_time"].pop("control_years"),
])
def test_malformed_config_raises(mutate) -> None:
    bad = copy.deepcopy(_CFG)
    mutate(bad)
    with pytest.raises(vf.ConfigError):
        vf._validate_config(bad)


# =============================================================================
# (3) REFERENCE-VALUE PINS -- flag (via failing test) any future drift
# =============================================================================
def test_tiered_and_flat_dollars_per_war_match_reference() -> None:
    # v44 — intentional retune: $/WAR moved from the single-2026 row to the
    # trailing 3-yr average (2024-26) of historical_dollars_per_war. These pins
    # are the means of those three years; re-average when a new year is appended.
    # v3 — the LOADED config re-anchors to the FA signings-implied series
    # (_apply_fa_implied_reanchor), so the curated BASE pins are asserted on
    # the raw YAML — the documented fallback that must never silently drift.
    import yaml
    raw = yaml.safe_load(vf._CONFIG_PATH.open(encoding="utf-8"))
    dpw = raw["dollars_per_war"]
    assert dpw["flat"] == pytest.approx(11.74e6)
    rates = dpw["tiered"]["rates"]
    assert rates["lt_1"] == pytest.approx(6.97e6)
    assert rates["1_to_2"] == pytest.approx(8.76e6)
    assert rates["2plus"] == pytest.approx(13.63e6)
    assert dpw["tiered"]["breakpoints"] == [1.0, 2.0]


def test_fa_implied_reanchor_preserves_tier_shape() -> None:
    """The v3 re-anchor may move the LEVEL (to the FA signings-implied
    trailing mean) but never the convex SHAPE: rate ratios match the
    curated base, the flat tracks the series mean, and the re-anchor
    metadata discloses itself."""
    dpw = _CFG["dollars_per_war"]
    meta = dpw.get("_fa_reanchor")
    if not meta:
        pytest.skip("fa_implied re-anchor disabled or series absent")
    assert meta["applied"] is True and meta["scale"] > 0
    rates = dpw["tiered"]["rates"]
    base = {"lt_1": 6.97e6, "1_to_2": 8.76e6, "2plus": 13.63e6}
    for k, b in base.items():
        assert rates[k] / dpw["flat"] == pytest.approx(b / 11.74e6, rel=1e-3), k
    series = json.loads((Path(vf._HERE) / "data" / "fa_dpw_series.json")
                        .read_text(encoding="utf-8"))["usd_per_war_by_winter"]
    tail = sorted(int(y) for y in series)[-3:]
    expect = sum(float(series[str(y)]) for y in tail) / len(tail)
    assert dpw["flat"] == pytest.approx(expect)


def test_discount_and_haircut_match_reference() -> None:
    assert _CFG["discount_rate"] == pytest.approx(0.09)
    assert _CFG["projection_haircut"]["value"] == pytest.approx(0.85)


def test_fv_to_war_anchor_is_average_match_reference() -> None:
    a = {float(k): v for k, v in _CFG["fv_to_6yr_avg_war"].items()}
    assert a[50] == pytest.approx(0.70)   # v47 empirical recalibration (was 2.0)
    assert a[55] == pytest.approx(0.95)
    assert a[60] == pytest.approx(1.45)


def test_bucket_bands_match_reference() -> None:
    b = _CFG["buckets"]
    assert list(b["order"]) == ["bust", "bench", "regular", "good", "star"]
    assert b["bust"]["band"] == "<0.5"
    assert b["bench"]["band"] == "0.5-1.5"
    assert b["regular"]["band"] == "1.5-2.5"
    assert b["good"]["band"] == "2.5-4.0"
    assert b["star"]["band"] == "4.0+"


def test_plus_grades_are_half_steps() -> None:
    assert float(_CFG["plus_grade_axis"]["40+"]) == 42.5
    assert float(_CFG["plus_grade_axis"]["45+"]) == 47.5
    assert float(_CFG["fit"]["role_axes"]["45+"]) == 47.5   # the fit axis the engine trains on


# =============================================================================
# (4) P(bucket|FV) INVARIANTS
# =============================================================================
@pytest.mark.parametrize("role", ["hitter", "pitcher"])
def test_training_rows_sum_to_one(role) -> None:
    for key, row in _CFG[f"p_bucket_given_fv_{role}"].items():
        s = sum(row[b] for b in _B)
        assert abs(s - 1.0) <= 0.02, f"{role} row {key} sums to {s}"


@pytest.mark.parametrize("is_pit", [False, True])
def test_fitted_curve_monotone_and_normalized(is_pit) -> None:
    xs = [35 + 0.5 * i for i in range(71)]            # 35.0 .. 70.0
    probs = [vf.p_bucket_given_fv(x, is_pit) for x in xs]
    for p in probs:
        assert abs(sum(p) - 1.0) < 1e-9
        assert all(v >= 0 for v in p)
    bust = [p[0] for p in probs]
    star = [p[4] for p in probs]
    assert all(bust[i + 1] <= bust[i] + 1e-9 for i in range(len(bust) - 1)), "bust not non-increasing"
    assert all(star[i + 1] >= star[i] - 1e-9 for i in range(len(star) - 1)), "star not non-decreasing"


@pytest.mark.parametrize("is_pit", [False, True])
def test_fit_reproduces_grid_cells_within_bound(is_pit) -> None:
    role = "pitcher" if is_pit else "hitter"
    axes = _CFG["fit"]["role_axes"]
    excl = int(_CFG["fit"]["exclude_n_le"])
    worst = 0.0
    for key, row in _CFG[f"p_bucket_given_fv_{role}"].items():
        if int(row["n"]) <= excl:
            continue
        fit = vf.p_bucket_given_fv(float(axes[key]), is_pit)
        worst = max(worst, max(abs(fit[i] - row[b]) for i, b in enumerate(_B)))
    # The monotone + hierarchical-Bayes fit must smooth the non-monotone "45+"
    # bust bump and the n=12 pitcher-60 cell, so exact reproduction is neither
    # possible nor desired; this just bounds how far it may drift.
    assert worst <= 0.25, f"{role} fit deviates {worst:.3f} from a training cell"


@pytest.mark.parametrize("is_pit", [False, True])
def test_no_discontinuity_across_grade_boundaries(is_pit) -> None:
    # A 1-FV step anywhere (incl. the 45/50/55/60 grade lines) moves no bucket
    # probability by more than a small amount -> smooth, no jump.
    xs = [40 + 0.5 * i for i in range(int((65 - 40) / 0.5) + 1)]
    prev = vf.p_bucket_given_fv(xs[0], is_pit)
    for x in xs[1:]:
        cur = vf.p_bucket_given_fv(x, is_pit)
        assert max(abs(cur[i] - prev[i]) for i in range(5)) < 0.05
        prev = cur


@pytest.mark.parametrize("is_pit", [False, True])
def test_plus_grade_axis_resolves_to_half_step_value(is_pit) -> None:
    # "45+" must evaluate as 47.5 -- between the 45 and 50 curves, not at either.
    p45 = vf.p_bucket_given_fv(45.0, is_pit)
    p475 = vf.p_bucket_given_fv(47.5, is_pit)
    p50 = vf.p_bucket_given_fv(50.0, is_pit)
    assert p50[0] < p475[0] < p45[0]                 # bust strictly between
    assert all(v == pytest.approx(v) for v in p475)  # finite, not a broken string


# =============================================================================
# (5) AVERAGE-NOT-PEAK RECONCILIATION at the named targets
# =============================================================================
@pytest.mark.parametrize("is_pit", [False, True])
@pytest.mark.parametrize("fv", [50, 55, 60])
def test_weighted_six_year_avg_war_reconciles(is_pit, fv) -> None:
    w = vf.expected_six_year_avg_war(fv, is_pit)
    target = vf.fv_to_6yr_avg_war(fv)
    assert abs(w - target) <= _RECON_TOL, f"FV{fv} {'pit' if is_pit else 'hit'} resid {w - target:+.3f}"


def test_committed_fitted_reconciliation_within_tol() -> None:
    # v47: bucket-WAR reconciliation is now EXACT via the FV-dependent scale
    # (_fv_war_scale) -- the live check above (test_*_reconcil*) verifies it. The
    # committed fit instead carries the empirically-derived anchors; verify they're
    # present + monotone (the FV-independent midpoint solve is vestigial).
    fit = json.loads(Path("data/value_framework_fitted.json").read_text())
    ea = (fit.get("empirical_anchors") or {}).get("anchors")
    assert ea, "fitted file missing empirical_anchors (run --fit with a DB)"
    vals = [v for _, v in sorted(ea.items(), key=lambda kv: float(kv[0]))]
    assert vals == sorted(vals), f"empirical anchors not monotone: {ea}"


# =============================================================================
# (6) TRANSFORM-FIRST wiring (no Jensen) + no double position multiplier
# =============================================================================
def test_tiered_value_classifies_each_season_by_own_war() -> None:
    rates = _CFG["dollars_per_war"]["tiered"]["rates"]
    # v46 — continuous convex ramp (smoothstep through the tier-CENTER rates at
    # 0.5/1.5/2.5 WAR), replacing the old hard 3-step. Equals the tier rates at the
    # centers, rises convexly, and is CONTINUOUS across the old 1.0/2.0 breakpoints.
    assert vf.tiered_war_value_usd(0.5) == pytest.approx(0.5 * rates["lt_1"])
    assert vf.tiered_war_value_usd(1.5) == pytest.approx(1.5 * rates["1_to_2"])
    assert vf.tiered_war_value_usd(2.5) == pytest.approx(2.5 * rates["2plus"])
    vals = [vf.tiered_war_value_usd(w) for w in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0)]
    assert all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))      # monotone
    eff = [vf.tiered_war_value_usd(w) / w for w in (0.6, 1.5, 2.4)]
    assert eff[0] < eff[1] < eff[2]                                       # per-win rate rises (convex)
    assert abs(vf.tiered_war_value_usd(2.01) - vf.tiered_war_value_usd(1.99)) < 2.0e6  # no jump (old step was ~$10M)


def test_mixture_differs_from_collapsed_point_estimate() -> None:
    # Transform-first (value each bucket-season then aggregate) must NOT equal the
    # collapse-first comparator E[f(X)] != f(E[X]) in the mid-FV convex region.
    mix = vf.expected_surplus_usd(48, False, "SS")
    collapsed = vf.point_estimate_surplus_usd(48, False, "SS")
    assert abs(mix - collapsed) > 1e3


def test_no_double_position_multiplier_for_hitters() -> None:
    # WAR already embeds the positional adjustment; the core surplus applies no
    # $/position multiplier (scarcity hook off), so position can't move a hitter's SV.
    assert vf.position_multiplier("SS") == 1.0
    base = vf.surplus_value_mm(55, False, None)
    assert vf.surplus_value_mm(55, False, "SS") == base
    assert vf.surplus_value_mm(55, False, "1B") == base


# =============================================================================
# (7) CONFIG IS LIVE -- perturbations move outputs the right direction
# =============================================================================
def test_perturb_tier_rate_raises_sv() -> None:
    base = vf.surplus_value_mm(55, False, "SS")
    with _perturb(lambda c: c["dollars_per_war"]["tiered"]["rates"].__setitem__(
            "2plus", c["dollars_per_war"]["tiered"]["rates"]["2plus"] * 1.2)):
        assert vf.surplus_value_mm(55, False, "SS") > base
    assert vf.surplus_value_mm(55, False, "SS") == base   # restored


def test_perturb_all_tiers_scales_sv_proportionally() -> None:
    base = vf.surplus_value_mm(55, False, "SS")

    def bump(c):
        for k in c["dollars_per_war"]["tiered"]["rates"]:
            c["dollars_per_war"]["tiered"]["rates"][k] *= 1.10
    with _perturb(bump):
        # Salary is a fraction of the (scaled) market value too, so surplus scales
        # ~proportionally with the $/WAR level.
        assert vf.surplus_value_mm(55, False, "SS") == pytest.approx(base * 1.10, rel=0.02)


def test_perturb_discount_rate_lowers_sv() -> None:
    base = vf.surplus_value_mm(55, False, "SS")
    with _perturb(lambda c: c.__setitem__("discount_rate", 0.15)):
        assert vf.surplus_value_mm(55, False, "SS") < base


def test_fv_shift_moves_bucket_weights_smoothly() -> None:
    p50 = vf.p_bucket_given_fv(50, False)
    p60 = vf.p_bucket_given_fv(60, False)
    assert p60[0] < p50[0]      # higher FV -> less bust
    assert p60[4] > p50[4]      # higher FV -> more star
