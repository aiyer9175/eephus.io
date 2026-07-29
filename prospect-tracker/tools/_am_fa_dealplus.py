# AUDIT LANE `fa`. (d) COHERENCE: is Deal+ a ratio of two comparable quantities?
"""Deal+ = 100 x rational_value / price. Both halves must be the same KIND
of number and must be priced off the same $/WAR curve. This checks both.

WHAT THE CODE DOES (fa_export.py:396-401, live board):
    guar     = pred["proj_guarantee_usd"]          <- MEDIAN of the price
    rational = fm.expected_rational_value_usd(...) <- MEAN of the value (T1.4)
    deal_plus = 100 * rational / guar

The numerator was deliberately converted from a value-of-the-mean to a
mean-of-the-value on 2026-07-25. The denominator is an exponentiated
log-space OLS fit, i.e. a conditional MEDIAN, and its residuals are
near-log-normal with sigma ~0.92 (measured: skew +0.035, kurtosis 2.896),
so its conditional MEAN is materially larger than the number used.

This lab measures the size of the resulting mismatch and what it does to the
shipped verdict terciles (109 / 223).
"""
from __future__ import annotations

import math
import pickle
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import _am_fa            # noqa: E402
import _am_fa_gate2 as g2  # noqa: E402

MAX_TERM = 10


def build():
    import fa_market as fm
    with open(_am_fa.SCRATCH / "fa_enriched_signings_B.pkl", "rb") as fh:
        pool = pickle.load(fh)
    winters = sorted({s["class_year"] for s in pool})
    rows = []
    for W in winters:
        train = [s for s in pool if s["class_year"] < W]
        test = [s for s in pool if s["class_year"] == W]
        if len(train) < 100 or not test:
            continue
        dpw_series = fm.dollars_per_war_by_winter(train)
        model = fm.MarketModel(train, dpw_series)
        model.supply_by_year[W] = fm._supply(test, W)
        dpw = fm.winter_dpw(dpw_series, W)
        infl = fm._destale_rate(dpw_series, W)
        for s in test:
            path = s.get("_war_path") or {}
            if not path.get("war_by_year"):
                continue
            pred = model.predict(s)
            yrs = min(int(pred["proj_years"]), MAX_TERM)
            act_guar = fm._npv_of(s)
            pred_guar = pred["proj_guarantee_usd"]
            try:
                exp_val = fm.expected_rational_value_usd(path, yrs, W, dpw, infl=infl)
            except Exception:                       # noqa: BLE001
                continue
            mean_val = fm.rational_value_usd(path["war_by_year"][:yrs], W, dpw, infl=infl)
            rows.append({
                "winter": W, "name": s.get("player_name"),
                "pos": fm._pos_group(s.get("position")),
                "act_guar": act_guar, "pred_guar": pred_guar,
                "exp_val": exp_val, "mean_val": mean_val, "years": yrs,
            })
    return rows


def q(vals, p):
    v = sorted(vals)
    return v[min(len(v) - 1, int(p * len(v)))]


def verdicts(dps, lo=109, hi=223):
    o = sum(1 for d in dps if d < lo)
    va = sum(1 for d in dps if d >= hi)
    return {"overpay": o, "market": len(dps) - o - va, "value": va}


if __name__ == "__main__":
    rows = _am_fa.cached("fa_dealplus_rows", build)
    print("n=%d signings, winters %s" % (len(rows), sorted({r['winter'] for r in rows})))

    variants = {
        "A  mean-value / ACTUAL price  (the tercile-cut basis)":
            lambda r: 100 * r["exp_val"] / max(r["act_guar"], 1),
        "B  mean-value / PREDICTED price (WHAT THE LIVE BOARD SERVES)":
            lambda r: 100 * r["exp_val"] / max(r["pred_guar"], 1),
        "C  point-value / ACTUAL price (pre-T1.4 basis)":
            lambda r: 100 * r["mean_val"] / max(r["act_guar"], 1),
        "D  point-value / PREDICTED price (pre-T1.4 live)":
            lambda r: 100 * r["mean_val"] / max(r["pred_guar"], 1),
    }
    print("\n%-58s %7s %7s %7s %8s" % ("basis", "p33", "median", "p67", "mean"))
    dp = {}
    for k, fn in variants.items():
        v = [fn(r) for r in rows]
        dp[k] = v
        print("%-58s %7.1f %7.1f %7.1f %8.1f"
              % (k, q(v, .33), q(v, .50), q(v, .67), sum(v) / len(v)))

    print("\nverdict counts under the SHIPPED edges (overpay <109, value >=223):")
    for k, v in dp.items():
        c = verdicts(v)
        print("  %-58s overpay %4d / market %4d / value %4d"
              % (k, c["overpay"], c["market"], c["value"]))

    a = dp["A  mean-value / ACTUAL price  (the tercile-cut basis)"]
    b = dp["B  mean-value / PREDICTED price (WHAT THE LIVE BOARD SERVES)"]
    ratio = [x / y for x, y in zip(b, a) if y > 0]
    print("\nDeal+ on PREDICTED price / Deal+ on ACTUAL price:")
    print("  mean %.3f  median %.3f  -> the live board's Deal+ runs %.0f%% high"
          % (sum(ratio) / len(ratio), statistics.median(ratio),
             100 * (statistics.median(ratio) - 1)))
    print("  i.e. actual/predicted price ratio, median %.3f"
          % statistics.median([r["act_guar"] / max(r["pred_guar"], 1) for r in rows]))

    # the T1.4 numerator move on its own
    m = [r["exp_val"] / max(r["mean_val"], 1) for r in rows if r["mean_val"] > 0]
    print("\nT1.4 numerator inflation (expected / point rational value):")
    print("  mean %.3f  median %.3f" % (sum(m) / len(m), statistics.median(m)))
