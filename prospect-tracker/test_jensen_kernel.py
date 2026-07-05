# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Phase 2 -- convex pricing kernel: Jensen (transform-first beats price-the-mean),
bucket_step vs smoothed modes, and the divergence surfaced in the snapshot.

Set A: every path is 5 seasons of 1.5 WAR.
Set B: half the paths are 5 seasons of 3.0 WAR, half are all zeros.
Both sets have the SAME expected per-season WAR (1.5), so pricing the MEAN path
values them identically (= Set A). A convex kernel priced per-season-per-path
must value Set B STRICTLY higher. Verified pre-salary/pre-discount and through
the full salary+discount pipeline, in both kernel modes.
"""
import contextlib

import pytest

import value_framework as vf

_SET_A = [[1.5] * 5]                    # one representative path (all identical)
_SET_B = [[3.0] * 5, [0.0] * 5]         # half boom, half bust


@contextlib.contextmanager
def _kernel_mode(mode):
    cfg = vf._config()
    prev = cfg["dollars_per_war"].get("kernel_mode", "smoothed")
    cfg["dollars_per_war"]["kernel_mode"] = mode
    try:
        yield
    finally:
        cfg["dollars_per_war"]["kernel_mode"] = prev


def _presalary(pathset):
    """Mean over paths of the pre-salary, pre-discount market value of a path."""
    return sum(sum(vf.tiered_war_value_usd(w) for w in path)
               for path in pathset) / len(pathset)


def _full_pipeline(pathset):
    """Mean over paths of the full salary-netted, discounted surplus of a path."""
    return sum(vf._service_path_surplus_usd(path, False, 0.0)
               for path in pathset) / len(pathset)


@pytest.mark.parametrize("mode", ["smoothed", "bucket_step"])
def test_jensen_presalary(mode):
    with _kernel_mode(mode):
        a = _presalary(_SET_A)
        b = _presalary(_SET_B)
        assert b > a, f"[{mode}] pre-salary: value(B)={b} must exceed value(A)={a}"
        # Hand-computed from the live tier rates (1.5 and 3.0 sit at/above tier
        # centers, so both modes return WAR*tier-rate there).
        rates = vf._config()["dollars_per_war"]["tiered"]["rates"]
        r_mid, r_hi = float(rates["1_to_2"]), float(rates["2plus"])
        assert a == pytest.approx(5 * 1.5 * r_mid, rel=1e-9)
        assert b == pytest.approx(0.5 * (5 * 3.0 * r_hi), rel=1e-9)


@pytest.mark.parametrize("mode", ["smoothed", "bucket_step"])
def test_jensen_full_pipeline(mode):
    with _kernel_mode(mode):
        a = _full_pipeline(_SET_A)
        b = _full_pipeline(_SET_B)
        assert b > a, f"[{mode}] full pipeline: value(B)={b} must exceed value(A)={a}"
        assert b > 0.0
        # Pricing the MEAN path of Set B (5x 1.5 WAR) is exactly Set A -- the
        # transform-first value must strictly exceed that price-the-mean value.
        price_the_mean_B = vf._service_path_surplus_usd([1.5] * 5, False, 0.0)
        assert b > price_the_mean_B


def test_modes_diverge_at_breakpoint():
    """The two modes must actually differ (else the mode switch is inert). At a
    breakpoint (2.0 WAR) the hard step jumps to the 2plus rate while the smoothstep
    is still ramping."""
    tiered = vf._config()["dollars_per_war"]["tiered"]
    smoothed = vf._tiered_war_value(2.0, "smoothed", tiered)
    step = vf._tiered_war_value(2.0, "bucket_step", tiered)
    assert step > smoothed > 0.0
    # Both agree at/above the top tier center and at zero.
    assert vf._tiered_war_value(3.0, "smoothed", tiered) == pytest.approx(
        vf._tiered_war_value(3.0, "bucket_step", tiered))
    assert vf._tiered_war_value(0.0, "smoothed", tiered) == 0.0


def test_snapshot_carries_kernel_divergence():
    snap = vf.build_snapshot()
    dpw = snap["dollars_per_war"]
    assert dpw["kernel_mode"] == "smoothed"   # production default
    kd = dpw["kernel_divergence"]
    assert kd["sample_war"] == [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    assert len(kd["smoothed_mm"]) == len(kd["bucket_step_mm"]) == 6
    # At 2.0 WAR the step mode prices higher than the smoothed ramp.
    i2 = kd["sample_war"].index(2.0)
    assert kd["bucket_step_mm"][i2] > kd["smoothed_mm"][i2]


def test_default_kernel_mode_is_smoothed_production():
    # The engine default must remain the production smoothed ramp.
    assert str(vf._config()["dollars_per_war"].get("kernel_mode")) == "smoothed"


# --------------------------------------------------------------------------
# D5: mlb_trade_lookup vet surplus -- per-season convex kernel is now the DEFAULT
# (transform-first, Phase-5 diff reviewed); legacy price-the-mean is the opt-out
# (TRADE_LOOKUP_PER_SEASON_KERNEL=0).
# --------------------------------------------------------------------------
def test_trade_lookup_default_is_per_season_kernel():
    import mlb_trade_lookup as mtl
    assert mtl._PER_SEASON_TRADE_KERNEL is True   # per-season kernel is the live board
    # Declining vet: rate 2.0 (career 10 / 5 seasons), age 30, 3 yrs left, $5M AAV.
    # Seasons: 1.6, 1.2, 0.8 (aging -0.4/yr past 29); proj_war 3.6, avg 1.2.
    proj, surplus = mtl._compute_surplus(10.0, 5, 30, 5_000_000, 3)
    assert proj == pytest.approx(3.6, abs=0.01)
    # per-season: each season priced on its OWN WAR through the convex kernel.
    seasons = [1.6, 1.2, 0.8]
    exp = round(sum(vf.tiered_war_value_usd(w) for w in seasons) / 1e6 - 5.0 * 3, 1)
    assert surplus == pytest.approx(exp, abs=0.05)


def test_trade_lookup_per_season_kernel_flag(monkeypatch):
    import mlb_trade_lookup as mtl
    monkeypatch.setattr(mtl, "_PER_SEASON_TRADE_KERNEL", True)
    proj, surplus_on = mtl._compute_surplus(10.0, 5, 30, 5_000_000, 3)
    assert proj == pytest.approx(3.6, abs=0.01)
    seasons = [1.6, 1.2, 0.8]
    exp_on = round(sum(vf.tiered_war_value_usd(w) for w in seasons) / 1e6 - 5.0 * 3, 1)
    assert surplus_on == pytest.approx(exp_on, abs=0.05)
    # The correction actually moves the number: the fringe 0.8-WAR season is priced
    # at the fringe rate rather than blended up to the 1-2 tier.
    _, surplus_off = None, None
    monkeypatch.setattr(mtl, "_PER_SEASON_TRADE_KERNEL", False)
    _, surplus_off = mtl._compute_surplus(10.0, 5, 30, 5_000_000, 3)
    assert surplus_on != surplus_off
