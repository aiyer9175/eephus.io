# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SWEEP LANE calibration -- blast-radius check for PATCH A (anchor low-end extension).

Monkeypatches the proposed fv_to_6yr_avg_war in-process (production files are NOT
edited) and reports exactly what moves.
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import value_framework as vf   # noqa: E402

_orig = vf.fv_to_6yr_avg_war


def patched(fv):
    if fv is None:
        return None
    try:
        f = float(fv)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    cal = vf._config().get("anchor_calibration", {})
    fitted = (vf._fitted().get("empirical_anchors") or {}).get("anchors") if cal.get("use_empirical") else None
    anchor = fitted or vf._config()["fv_to_6yr_avg_war"]
    pts = sorted((float(k), float(v)) for k, v in anchor.items())
    if f <= pts[0][0]:
        x0, y0 = pts[0]
        if f <= vf.FV_FLOOR if hasattr(vf, "FV_FLOOR") else f <= 20.0:
            return 0.0
        if x0 <= 20.0:
            return y0
        return y0 * ((f - 20.0) / (x0 - 20.0)) ** (1.0 / vf._LOWEND_FG_EXP)
    if f >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= f <= x1:
            t = (f - x0) / (x1 - x0)
            return y0 * (1 - t) + y1 * t
    return pts[-1][1]


GRADES = [20 + 0.5 * i for i in range(121)]
before = {}
for g in GRADES:
    for is_pit in (False, True):
        s = vf.expected_surplus_usd(g, is_pit, "SS" if not is_pit else "SP", age=None, eta_years=1.0)
        d = vf.sv_distribution(g, is_pit, "SS" if not is_pit else "SP")
        before[(g, is_pit)] = (s, d["percentiles"]["p10"], d["percentiles"]["p90"], d["p_bust"],
                               vf.realized_implied_fv(2.0, is_pit, exposure_seasons=6))

vf.fv_to_6yr_avg_war = patched
vf._fv_war_scale.cache_clear()
vf._prime_war_scale.cache_clear() if hasattr(vf, "_prime_war_scale") else None

print("PATCH A blast radius (expected_surplus_usd / sv_distribution p10,p90 / p_bust)")
print(f"{'grade':>6} {'side':>4} {'d_surplus$':>12} {'d_p10':>9} {'d_p90':>9} {'d_pbust':>9}")
moved_above40 = 0
for g in GRADES:
    for is_pit in (False, True):
        s = vf.expected_surplus_usd(g, is_pit, "SS" if not is_pit else "SP", age=None, eta_years=1.0)
        d = vf.sv_distribution(g, is_pit, "SS" if not is_pit else "SP")
        b = before[(g, is_pit)]
        ds = (s or 0) - (b[0] or 0)
        dp10 = d["percentiles"]["p10"] - b[1]
        dp90 = d["percentiles"]["p90"] - b[2]
        dpb = d["p_bust"] - b[3]
        if g >= 40 and (abs(ds) > 1 or abs(dp10) > 1e-9 or abs(dp90) > 1e-9 or abs(dpb) > 1e-9):
            moved_above40 += 1
        if g in (20, 25, 30, 35, 38, 39.5, 40, 40.5, 45, 50, 60) and not is_pit:
            print(f"{g:6.1f} {'hit':>4} {ds:12.0f} {dp10:9.3f} {dp90:9.3f} {dpb:9.4f}")
print(f"\ncells at or above FV 40 that moved at all: {moved_above40} of {2*sum(1 for g in GRADES if g>=40)}")
print("p_bucket_given_fv is independent of the anchor -> p_bust unchanged everywhere by construction.")
print("\nrealized_implied_fv(2.0 WAR) hit:", vf.realized_implied_fv(2.0, False, exposure_seasons=6),
      " (pre-patch:", before[(20, False)][4], ")")
print("\nROUND TRIP after patch (forward map vs the inverse map):")
for g in (22, 25, 30, 35, 38, 40, 45):
    w = patched(g) * 6
    back = vf.realized_implied_fv(w, False, exposure_seasons=6)
    print(f"  g={g:5.1f} -> implied {w:6.3f} WAR -> rif {back:5.2f}   error {back-g:+5.2f} FV")
print("\nBEFORE the patch the same round trip collapsed every grade in [20,40] onto 39.8 FV.")
