# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SWEEP LANE calibration -- the sub-40 anchor hole and candidate repairs.

fv_to_6yr_avg_war is the config's declared level meaning of a grade. The fitted
empirical anchors start at FV 40, so the interpolator CLAMPS every grade in
[20, 40] to one value. realized_implied_fv (the INVERSE map) does not clamp: it
re-spreads FV 20-45 with a concave FanGraphs-shaped curve (_LOWEND_FG_EXP). The
two halves of the same contract therefore disagree over the range that holds
88% of the served board.
"""
from __future__ import annotations
import json, math, statistics, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import empirical_anchors as ea   # noqa: E402
import value_framework as vf     # noqa: E402

FIT = json.loads((ROOT / "data" / "value_framework_fitted.json").read_text(encoding="utf-8"))
SERVED = {float(k): float(v) for k, v in FIT["empirical_anchors"]["anchors"].items()}
SEED = {float(k): float(v) for k, v in vf._config()["fv_to_6yr_avg_war"].items()}
EXP = vf._LOWEND_FG_EXP


def interp(anchor, f):
    pts = sorted(anchor.items())
    if f <= pts[0][0]:
        return pts[0][1]
    if f >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= f <= x1:
            t = (f - x0) / (x1 - x0)
            return y0 * (1 - t) + y1 * t
    return pts[-1][1]


def a2(f):
    """A2: below FV 45 use the EXACT inverse of realized_implied_fv's low-end
    re-spread, anchored on the fitted FV-45 value. g = 20 + 25*(w/w45)^EXP
      =>  w(g) = w45 * ((g-20)/25)^(1/EXP)."""
    w45 = SERVED[45.0]
    if f >= 45:
        return interp(SERVED, f)
    if f <= 20:
        return 0.0
    return w45 * ((f - 20.0) / 25.0) ** (1.0 / EXP)


print("=== the hole ===")
print("served fitted anchors:", SERVED)
print("config seed table    :", SEED)
print("anchor_calibration.tiers:", vf._config()["anchor_calibration"]["tiers"])
print("-> the fit's tier list omits 35, so the FITTED anchors have no knot below 40")
print("   and fv_to_6yr_avg_war clamps every grade in [20, 40] to", SERVED[40.0])
print()
print("%6s %10s %10s %10s %10s %12s" % ("grade", "SERVED", "SEED", "A1(+35kt)", "A2(inverse)",
                                        "rif round-trip"))
a1 = dict(SERVED); a1[35.0] = 0.12          # 0.5*emp(0.040) + 0.5*public_reference(0.20)
for g in (20, 25, 30, 32, 35, 38, 40, 42, 45, 50):
    rt = vf.realized_implied_fv(interp(SERVED, g) * 6, False, exposure_seasons=6)
    print("%6.1f %10.3f %10.3f %10.3f %10.3f %12.1f"
          % (g, interp(SERVED, g), interp(SEED, g), interp(a1, g), a2(g), rt))
print()
print("A2 continuity/anchor check: A2(40)=%.4f vs served 40 anchor %.4f (delta %.4f)"
      % (a2(40), SERVED[40.0], a2(40) - SERVED[40.0]))
print("A2(45)=%.4f vs served %.4f  |  A2 is EXACTLY inverse to realized_implied_fv below 45"
      % (a2(45), SERVED[45.0]))
for g in (25, 30, 35, 40):
    back = vf.realized_implied_fv(a2(g) * 6, False, exposure_seasons=6)
    print("   round trip A2: g=%.0f -> w=%.3f -> rif=%.2f  (error %.2f FV)"
          % (g, a2(g) * 6, back, back - g))

print()
print("=== measured support: the DB cohort empirical_anchors itself uses ===")
co = ea._cohort(ROOT / "prospects.db", 2014, 2020)
by = defaultdict(list)
for r in co.values():
    by[int(round(r["fv"] / 5) * 5)].append(r["realized_war"] / 6.0)
print("%6s %6s %12s %10s %10s %10s %10s" % ("tier", "n", "empirical", "SERVED", "A1", "A2", "public_ref"))
ref = vf._config()["anchor_calibration"]["public_reference"]
rows = []
for t in sorted(by):
    v = by[t]
    boot = [float(np.mean(np.random.RandomState(1000 + t * 7 + i).choice(v, len(v)))) for i in range(400)]
    ci = (round(float(np.percentile(boot, 2.5)), 3), round(float(np.percentile(boot, 97.5)), 3))
    print("%6d %6d %7.3f %s %10.3f %10.3f %10.3f %10s"
          % (t, len(v), statistics.mean(v), ci, interp(SERVED, t), interp(a1, t), a2(t), ref.get(t)))
    rows.append((t, len(v), statistics.mean(v), ci))

print()
print("=== level-calibration error of each candidate on the DB cohort (WAR/yr) ===")
print("weighted mean |anchor(tier) - empirical(tier)|, weights = cell n, tiers <= 60")
for name, fn in (("SERVED", lambda f: interp(SERVED, f)), ("A1 (+35 knot)", lambda f: interp(a1, f)),
                 ("A2 (inverse-consistent)", a2), ("SEED config", lambda f: interp(SEED, f))):
    num = den = 0.0
    for t, n, emp, _ci in rows:
        if t > 60:
            continue
        num += n * abs(fn(t) - emp); den += n
    print("  %-26s weighted MAE = %.4f WAR/yr  (x6 = %.3f WAR over the window)"
          % (name, num / den, 6 * num / den))

print()
print("=== blast radius of the clamp on the SERVED board ===")
d = json.loads((ROOT / "data" / "xfv.json").read_text(encoding="utf-8"))
act = [v for v in d["by_player"].values() if v.get("kind") == "active"]
gq = [v["xfv_grade_quantile"] for v in act if v.get("xfv_grade_quantile") is not None]
gr = [v["xfv_grade_realized"] for v in act if v.get("xfv_grade_realized") is not None]
print("  active rows: %d" % len(act))
for lbl, arr in (("xfv_grade_quantile (headline)", gq), ("xfv_grade_realized (odds basis)", gr)):
    print("   %-32s share <= 40 (clamped by the anchor): %.3f   share <= 45: %.3f"
          % (lbl, sum(1 for x in arr if x <= 40) / len(arr), sum(1 for x in arr if x <= 45) / len(arr)))
print("  farm_grade_backtest.py:165 sums fv_to_6yr_avg_war(fv) per member, so every")
print("  sub-40 farm member is credited the same %.2f WAR of expected first-6yr value." % (SERVED[40.0] * 6))
tot_served = sum(interp(SERVED, g) * 6 for g in gq)
tot_a2 = sum(a2(g) * 6 for g in gq)
print("  board-wide expected first-6yr WAR summed over active rows on the headline grade:")
print("    SERVED anchor %.0f WAR   A2 %.0f WAR   delta %.0f WAR (%.1f%%)"
      % (tot_served, tot_a2, tot_a2 - tot_served, 100 * (tot_a2 - tot_served) / tot_served))
