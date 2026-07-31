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


# ============================================================================
# E1 (2026-07-30): Deal+ / verdict distribution PER POSITION GROUP, scored
# against the 33/33/33 design the terciles were cut to deliver.
# ============================================================================
# The shipped edges (109 / 223) are corpus terciles cut on the POOLED corpus.
# Pooled terciles only deliver a third each per group if Deal+ has the same
# distribution in every group, and it does not: Deal+ = rational_value/price,
# and a short deal for a sub-1-WAR reliever prices most of its guarantee
# against very little projected value by construction. This block measures the
# per-group realized split so "the board thinks every reliever is an overpay"
# is a number instead of an impression. Run with --groups.
GROUPS = ("SP", "RP", "C", "POS")


def group_table(rows, dp_of, label):
    """Per-group Deal+ quantiles + verdict split under the SHIPPED pooled
    edges, and the per-group terciles that WOULD deliver 33/33/33."""
    from collections import Counter
    buckets = defaultdict(list)
    for r in rows:
        g = r["pos"]
        side = "pit" if g in ("SP", "RP") else "hit"
        for k in (g, side, "ALL"):
            buckets[k].append(dp_of(r))
    print(f"\n{label}")
    print("  %-5s %5s %7s %7s %7s | %6s %6s %6s | %7s %7s"
          % ("grp", "n", "p33", "median", "p67", "over%", "mkt%", "val%",
             "own_p33", "own_p67"))
    out = {}
    for k in ("ALL", "hit", "pit") + GROUPS:
        v = buckets.get(k)
        if not v:
            continue
        c = verdicts(v)
        n = len(v)
        out[k] = {"n": n, "p33": q(v, .33), "median": q(v, .50), "p67": q(v, .67),
                  "overpay_pct": 100 * c["overpay"] / n,
                  "market_pct": 100 * c["market"] / n,
                  "value_pct": 100 * c["value"] / n,
                  "own_p33": q(v, .33), "own_p67": q(v, .67)}
        print("  %-5s %5d %7.0f %7.0f %7.0f | %5.0f%% %5.0f%% %5.0f%% | %7.0f %7.0f"
              % (k, n, out[k]["p33"], out[k]["median"], out[k]["p67"],
                 out[k]["overpay_pct"], out[k]["market_pct"], out[k]["value_pct"],
                 out[k]["own_p33"], out[k]["own_p67"]))
    return out


def served_group_table():
    """The same slice on the LIVE board (data/fa_class.json) - the thing the
    owner actually looks at. Read-only."""
    import json
    import fa_market as fm
    from collections import Counter
    d = json.loads((ROOT / "data" / "fa_class.json").read_text(encoding="utf-8"))
    buckets = defaultdict(list)
    for r in d["members"]:
        if r.get("dealPlus") is None:
            continue
        g = fm._pos_group(r.get("pos"))
        side = "pit" if g in ("SP", "RP") else "hit"
        for k in (g, side, "ALL"):
            buckets[k].append(r)
    print(f"\nSERVED BOARD data/fa_class.json (class {d['class_year']}, "
          f"generated {d['generated_at']})")
    print("  %-5s %5s %7s %7s %7s | %6s %6s %6s | %11s"
          % ("grp", "n", "p33", "median", "p67", "over%", "mkt%", "val%", "meanSurp$M"))
    for k in ("ALL", "hit", "pit") + GROUPS:
        rows = buckets.get(k)
        if not rows:
            continue
        dps = [r["dealPlus"] for r in rows]
        c = Counter(r.get("verdict") for r in rows)
        surp = [r["surplus"] / 1e6 for r in rows if r.get("surplus") is not None]
        n = len(dps)
        print("  %-5s %5d %7.0f %7.0f %7.0f | %5.0f%% %5.0f%% %5.0f%% | %11.2f"
              % (k, n, q(dps, .33), q(dps, .50), q(dps, .67),
                 100 * c["overpay"] / n, 100 * c["market"] / n, 100 * c["value"] / n,
                 (sum(surp) / len(surp)) if surp else 0.0))


if __name__ == "__main__":
    import argparse
    _ap = argparse.ArgumentParser()
    _ap.add_argument("--groups", action="store_true",
                     help="E1 per-pos-group Deal+/verdict distribution slice "
                          "(corpus + served board) and nothing else")
    _args = _ap.parse_args()
    rows = _am_fa.cached("fa_dealplus_rows", build)
    print("n=%d signings, winters %s" % (len(rows), sorted({r['winter'] for r in rows})))

    if _args.groups:
        group_table(rows, lambda r: 100 * r["exp_val"] / max(r["act_guar"], 1),
                    "CORPUS, Deal+ on the ACTUAL price (the tercile-cut basis)")
        group_table(rows, lambda r: 100 * r["exp_val"] / max(r["pred_guar"], 1),
                    "CORPUS, Deal+ on the PREDICTED price (what the board serves)")
        served_group_table()
        raise SystemExit(0)

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
