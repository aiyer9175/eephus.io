"""Prospect Greeks math guard. Extracts computeGreeks + _svAt from
prospx/index.html and exercises them against a synthetic value framework:
Delta (surplus from a one-grade upgrade) is positive on a rising curve, Theta
(ETA decay) is negative and equals the discount haircut, Vega scales with grade
dispersion, and a missing grade yields null. Skips without py_mini_racer.
"""
import re
import json
import warnings

import pytest

warnings.filterwarnings("ignore")
mr = pytest.importorskip("py_mini_racer")


def _ctx():
    src = open("prospx/index.html", encoding="utf-8").read()
    fns = ""
    for name in ("_svAt", "computeGreeks"):
        m = re.search(r"function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S)
        assert m, f"{name} not found"
        fns += m.group(0)
    c = mr.MiniRacer()
    curve = [round(0.08 * (1.09 ** (i * 0.5)), 4) for i in range(121)]  # rising, fv 20..80
    vf = {"sv_curve": {"fv_min": 20.0, "fv_max": 80.0, "step": 0.5,
                       "hitter": curve, "pitcher": curve}, "discount_rate": 0.09}
    c.eval("var window = {VALUE_FRAMEWORK: %s};" % json.dumps(vf))
    c.eval(fns)
    return c


def _greeks(ctx, fv, is_pit, dist):
    out = ctx.eval("JSON.stringify(computeGreeks(%s, %s, %s))"
                   % (json.dumps(fv), "true" if is_pit else "false", json.dumps(dist)))
    return json.loads(out) if out else None


DIST = {"mean_mm": 52.0, "fv_dispersion": 2.5, "p10_mm": 20, "p90_mm": 90}


def test_null_grade_yields_none():
    ctx = _ctx()
    assert _greeks(ctx, None, False, DIST) is None


def test_delta_positive_and_theta_is_decay():
    ctx = _ctx()
    g = _greeks(ctx, 55, False, DIST)
    assert g["delta"] > 0                                  # a grade up adds surplus
    assert g["theta"] < 0                                  # decay is negative
    assert abs(g["theta"] - (-(52.0 * 0.09 / 1.09))) < 0.01  # = mean * dr/(1+dr)
    assert g["iv"] == 2.5


def test_vega_scales_with_dispersion():
    ctx = _ctx()
    lo = _greeks(ctx, 55, False, {**DIST, "fv_dispersion": 1.0})
    hi = _greeks(ctx, 55, False, {**DIST, "fv_dispersion": 4.0})
    assert hi["vega"] > lo["vega"]                         # more disagreement = more vega


def test_higher_grade_has_larger_delta_on_convex_curve():
    ctx = _ctx()
    g50 = _greeks(ctx, 50, False, DIST)
    g65 = _greeks(ctx, 65, False, DIST)
    assert g65["delta"] > g50["delta"]                    # convex surplus curve
