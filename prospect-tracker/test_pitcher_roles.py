# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the pitcher role-outcome layer (Prompt J).

Validates the spec's requirements:
  * Pitcher SV is NO LONGER inflated by 200-IP reliever normalization -- a
    reliever's per-bucket WAR is normalized to a full bullpen season and capped
    (a 3.6-WAR/200-IP band -> ~1.2 WAR), so RP < generic < SP at every FV.
  * The SP/RP/bust split reconciles to the pitcher BASE RATES: bust ==
    P(bucket=bust|FV), and the non-bust mass divides SP vs RP by P(reliever|bucket);
    the three sum to 1.
  * High-FV arms are mostly SP (elite stuff sticks in the rotation); low/mid arms
    carry real relief risk.
  * The HITTER path is byte-for-byte unchanged.
  * Continuity (0-sample debuted == prospect) and monotonicity survive for every
    pitcher role tag.
"""

from __future__ import annotations

import pytest

import value_framework as vf

_BK = vf._BUCKETS
_N = vf._N_BUCKETS


# =============================================================================
# Reliever WAR ceiling + IP-normalization (the headline distortion fix)
# =============================================================================
def test_reliever_ip_normalization_3p6_band_to_about_1p2() -> None:
    """The spec's worked number: a 3.6-WAR-per-200-IP band reliever is ~1.2 WAR
    over a full (65-IP) bullpen season."""
    lvl = vf._reliever_level(3.6)
    assert lvl == pytest.approx(3.6 * 65 / 200, abs=1e-9)   # 1.17
    assert 1.1 <= lvl <= 1.25


def test_reliever_ceiling_caps_elite_arms() -> None:
    """No reliever clears the full-season WAR ceiling, however good the band WAR."""
    ceil = float(vf._config()["position"]["reliever_war_ceiling"])
    assert vf._reliever_level(100.0) == pytest.approx(ceil)
    assert vf._reliever_level(6.0) == pytest.approx(ceil)   # 6*65/200=1.95 -> capped 1.5


def test_reliever_level_monotone_below_ceiling() -> None:
    lo, hi = vf._reliever_level(1.0), vf._reliever_level(3.0)
    assert lo < hi <= float(vf._config()["position"]["reliever_war_ceiling"])


def test_reliever_curve_is_pure_capped_relief() -> None:
    """The RP-tagged bucket SVs equal the bullpen-capped pitcher pipeline (every
    non-bust bucket is relief), with no injury haircut by default."""
    eff = vf._effective_bucket_sv(True, "RP", None, 0.0)
    pure_rp = vf._bucket_sv_usd("pitcher", True, None, 0.0)
    for i in range(_N):
        assert eff[i] == pytest.approx(pure_rp[i], rel=1e-9)


# =============================================================================
# RP < generic < SP  (the role-value ordering, at every FV)
# =============================================================================
@pytest.mark.parametrize("fv", [45, 50, 55, 60, 65])
def test_rp_lt_generic_lt_sp(fv) -> None:
    rp = vf.surplus_value_mm(fv, True, "RP", age=21, eta_years=2)
    gen = vf.surplus_value_mm(fv, True, None, age=21, eta_years=2)
    sp = vf.surplus_value_mm(fv, True, "SP", age=21, eta_years=2)
    assert rp < gen < sp, f"FV{fv}: rp={rp} gen={gen} sp={sp}"


@pytest.mark.parametrize("fv", [45, 50, 55, 60, 65])
def test_generic_deflated_vs_pure_sp_pipeline(fv) -> None:
    """The generic pitcher is strictly below the UN-blended pure-SP pipeline
    (the old 200-IP-normalized figure) -- i.e. the inflation is removed."""
    probs = vf.p_bucket_given_fv(fv, True)
    pure_sp = vf._bucket_sv_usd("pitcher", False, None, 0.0)
    pure_sp_mm = sum(p * s for p, s in zip(probs, pure_sp)) / 1e6
    gen = vf.surplus_value_mm(fv, True, None)   # no timing -> matches None,0.0 svs
    assert gen < pure_sp_mm, f"FV{fv}: generic {gen} not below pure-SP {pure_sp_mm:.1f}"


def test_effective_bucket_sv_is_the_role_blend() -> None:
    """The generic effective bucket SV is exactly (1-p_rp)*SP + p_rp*RP per bucket."""
    sp = vf._bucket_sv_usd("pitcher", False, None, 0.0)
    rp = vf._bucket_sv_usd("pitcher", True, None, 0.0)
    p_rp = vf._pitcher_rp_by_bucket(None)
    eff = vf._effective_bucket_sv(True, None, None, 0.0)
    for i in range(_N):
        assert eff[i] == pytest.approx((1 - p_rp[i]) * sp[i] + p_rp[i] * rp[i], rel=1e-9)


# =============================================================================
# SP/RP/bust split reconciles to the pitcher base rates
# =============================================================================
@pytest.mark.parametrize("fv", [40, 45, 50, 55, 60, 65, 70])
def test_role_split_sums_to_one(fv) -> None:
    rs = vf.pitcher_role_split(fv, True, None)
    assert rs["sp"] + rs["rp"] + rs["bust"] == pytest.approx(1.0, abs=1e-3)
    assert all(rs[k] >= 0 for k in ("sp", "rp", "bust"))


@pytest.mark.parametrize("fv", [40, 45, 50, 55, 60, 65, 70])
def test_role_split_bust_matches_bucket_model(fv) -> None:
    """The split's bust mass IS the bucket model's P(bucket=bust|FV)."""
    rs = vf.pitcher_role_split(fv, True, None)
    assert rs["bust"] == pytest.approx(vf.p_bucket_given_fv(fv, True)[0], abs=1e-3)


@pytest.mark.parametrize("fv", [45, 55, 65])
def test_role_split_nonbust_divides_by_p_reliever(fv) -> None:
    """The non-bust mass divides SP/RP exactly by P(reliever|bucket)."""
    probs = vf.p_bucket_given_fv(fv, True)
    p_rp = vf._pitcher_rp_by_bucket(None)
    exp_rp = sum(probs[i] * p_rp[i] for i in range(1, _N))
    exp_sp = sum(probs[i] * (1 - p_rp[i]) for i in range(1, _N))
    rs = vf.pitcher_role_split(fv, True, None)
    assert rs["rp"] == pytest.approx(exp_rp, abs=1e-3)
    assert rs["sp"] == pytest.approx(exp_sp, abs=1e-3)


def test_high_fv_is_mostly_starter() -> None:
    """Elite arms stick in the rotation: SP mass dominates RP mass at high FV,
    and the SP share rises with FV."""
    for fv in (60, 65, 70):
        rs = vf.pitcher_role_split(fv, True, None)
        assert rs["sp"] > rs["rp"]
    sp_share = [vf.pitcher_role_split(fv, True, None)["sp"] for fv in (45, 55, 65)]
    assert sp_share == sorted(sp_share)


def test_role_split_none_for_hitter_and_bad_fv() -> None:
    assert vf.pitcher_role_split(55, False, "SS") is None
    assert vf.pitcher_role_split(None, True, "SP") is None
    assert vf.pitcher_role_split(float("nan"), True, "SP") is None


def test_rp_tag_split_is_all_relief() -> None:
    """An RP-tagged prospect's non-bust mass is entirely relief."""
    rs = vf.pitcher_role_split(55, True, "RP")
    assert rs["sp"] == pytest.approx(0.0, abs=1e-9)
    assert rs["rp"] == pytest.approx(1.0 - rs["bust"], abs=1e-3)


# =============================================================================
# Hitter path is unchanged
# =============================================================================
@pytest.mark.parametrize("pos", ["SS", "CF", "C", "1B", None])
def test_hitter_effective_sv_equals_plain_bucket_sv(pos) -> None:
    eff = vf._effective_bucket_sv(False, pos, None, 0.0)
    plain = vf._bucket_sv_usd("hitter", False, None, 0.0)
    assert tuple(eff) == tuple(plain)


@pytest.mark.parametrize("fv", [42, 45, 50, 55, 60])
def test_hitter_surplus_unchanged_vs_raw_pipeline(fv) -> None:
    """The hitter surplus equals the raw hitter pipeline (above the bridge) -- the
    role layer never touches it."""
    if fv >= 45:
        probs = vf.p_bucket_given_fv(fv, False)
        svs = vf._bucket_sv_usd("hitter", False, None, 0.0, vf._war_scale_for(fv, "hitter"))
        raw_mm = sum(p * s for p, s in zip(probs, svs)) / 1e6
        assert vf.surplus_value_mm(fv, False, "SS") == pytest.approx(round(raw_mm, 1), abs=0.1)


def test_hitter_role_split_is_none() -> None:
    assert vf.pitcher_role_split(55, False, "CF") is None


# =============================================================================
# Monotonicity + continuity survive the role layer
# =============================================================================
@pytest.mark.parametrize("pos", [None, "SP", "RP"])
def test_pitcher_curve_monotone_in_fv(pos) -> None:
    vals = [vf.surplus_value_mm(fv, True, pos, age=21, eta_years=2)
            for fv in range(40, 71, 2)]
    assert vals == sorted(vals), (pos, vals)


@pytest.mark.parametrize("pos", [None, "SP", "RP"])
@pytest.mark.parametrize("fv", [50, 55, 60])
def test_debuted_zero_sample_continuity_all_roles(pos, fv) -> None:
    """At 0 IP the debuted pitcher reduces to the prospect value for EVERY role
    tag (the remaining-bucket path carries the same role mix)."""
    d = vf.debuted_player_value(fv, True, pos, observed_war=0.0, observed_pa=0,
                                observed_ip=0, service_time=0.0, age=23, draws=3000)
    prospect = vf.surplus_value_mm(fv, True, pos, age=23, eta_years=0)
    assert d["trade_value_mm"] == pytest.approx(prospect, abs=0.2)


def test_debuted_reliever_below_starter_same_line() -> None:
    """A debuted reliever's remaining value sits below an identical-line starter
    (role-value ordering carries into the debuted mode)."""
    common = dict(observed_war=1.2, observed_ip=120, service_time=2.0, age=26, draws=3000)
    rp = vf.debuted_player_value(50, True, "RP", **common)["trade_value_mm"]
    sp = vf.debuted_player_value(50, True, "SP", **common)["trade_value_mm"]
    assert rp < sp


# --- Regression guards for the adversarial-review fixes (Prompt J) -----------
@pytest.mark.parametrize("fv", [45, 50, 55, 60])
def test_debuted_reliever_monotone_with_sample(fv) -> None:
    """REGRESSION (review HIGH): a reliever-tagged debuted pitcher confirming
    STRONG play (fixed 3.0 WAR/200-IP rate) over a larger sample must be valued
    NON-DECREASINGLY. The pre-fix double-deflation (legacy 0.50 talent haircut +
    _reliever_level applied again on the graduated rate) produced a value DIP as
    w_grad rose."""
    vals = [vf.debuted_player_value(fv, True, "RP", observed_war=3.0 * ip / 200,
                                    observed_ip=ip, service_time=0.0, age=25, draws=3000)["trade_value_mm"]
            for ip in (5, 10, 20, 40, 65, 100, 250)]
    assert vals == sorted(vals), f"FV{fv}: non-monotone {vals}"


def test_debuted_talent_inference_is_role_agnostic() -> None:
    """REGRESSION (review MEDIUM): the same per-200-IP band rate yields the SAME
    bucket posterior for an RP- and an SP-tagged pitcher -- the talent inference
    runs on the 200-IP band scale for all roles; the role VALUE difference comes
    only from the downstream $ conversion (_reliever_level)."""
    kw = dict(observed_war=2.0 * 400 / 200, observed_ip=400, service_time=0.0, age=25, draws=2000)
    rp = vf.debuted_player_value(55, True, "RP", **kw)
    sp = vf.debuted_player_value(55, True, "SP", **kw)
    for b in vf._BUCKETS:
        assert rp["posterior"][b] == pytest.approx(sp["posterior"][b], abs=1e-9)
    assert rp["trade_value_mm"] < sp["trade_value_mm"]   # value still split by role


def test_apply_position_mult_false_preserves_role_tag() -> None:
    """REGRESSION (review LOW): apply_position_mult=False gates only the
    (default-off) market-scarcity multiplier; it must NOT discard the role tag
    (the pre-fix path nulled position, collapsing RP back to the generic curve)."""
    rp_on = vf.surplus_value_mm(50, True, "RP", apply_position_mult=True)
    rp_off = vf.surplus_value_mm(50, True, "RP", apply_position_mult=False)
    generic = vf.surplus_value_mm(50, True, None)
    assert rp_off == pytest.approx(rp_on, abs=1e-9)   # scarcity off -> no-op
    assert rp_off < generic                            # role tag still honored


def test_reliever_level_guards_bad_input() -> None:
    """REGRESSION (review LOW): a non-finite or negative band WAR floors to 0 (it
    can never slip past min(ceil, .) as the ceiling, nor pass through negative)."""
    assert vf._reliever_level(float("nan")) == 0.0
    assert vf._reliever_level(float("inf")) == 0.0
    assert vf._reliever_level(-1.0) == 0.0
    assert vf._reliever_level(0.0) == 0.0


# =============================================================================
# Optional injury/attrition hazard
# =============================================================================
def test_snapshot_exposes_role_layer() -> None:
    """The snapshot ships the SP curve + the pitcher_roles block (config echo +
    a role-split table) so the frontend can pick the right curve and explain it."""
    snap = vf.build_snapshot()
    assert "sp" in snap["sv_curve"]
    assert "sp" in snap["bucket_surplus_mm"]
    assert len(snap["sv_curve"]["sp"]) == len(snap["sv_curve"]["pitcher"])
    pr = snap["pitcher_roles"]
    assert pr["roles"] == ["sp", "rp", "bust"]
    assert "p_rp_by_bucket" in pr and "split_by_grade" in pr
    # SP curve sits between the generic-pitcher and (implicit) pure-SP curves, and
    # strictly above the capped reliever curve at every sampled FV.
    for sp, gen, rp in zip(snap["sv_curve"]["sp"], snap["sv_curve"]["pitcher"], snap["sv_curve"]["reliever"]):
        assert rp <= gen <= sp + 1e-9


def test_injury_hazard_deflates_nonbust_only() -> None:
    """Turning on the attrition hazard scales the non-bust bucket SVs by (1-haz)
    and leaves bust (already $0) untouched; hitters are unaffected."""
    cfg = vf._config()
    mix = cfg.setdefault("pitcher_role_mix", {})
    saved = mix.get("injury_hazard", 0.0)
    base = vf._effective_bucket_sv(True, None, None, 0.0)
    base_hit = vf._effective_bucket_sv(False, "SS", None, 0.0)
    try:
        mix["injury_hazard"] = 0.10
        haz = vf._effective_bucket_sv(True, None, None, 0.0)
        haz_hit = vf._effective_bucket_sv(False, "SS", None, 0.0)
    finally:
        mix["injury_hazard"] = saved
    assert haz[0] == base[0] == 0.0                     # bust untouched
    for i in range(1, _N):
        assert haz[i] == pytest.approx(base[i] * 0.90, rel=1e-9)
    assert tuple(haz_hit) == tuple(base_hit)            # hitter path immune
