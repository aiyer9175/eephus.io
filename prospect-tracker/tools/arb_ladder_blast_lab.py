# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""GATE 0.1 - the arbitration-ladder blast-radius bound.

RUN THIS BEFORE ANY MODEL IS FIT. It is the cheapest measurement in the
arbitration program and it can close GATE B on economic grounds before a single
row is modelled.

The question is not "does a fitted ladder beat the incumbent". It is the prior
question: **can ANY admissible ladder move the served board enough to matter?**
Set the arbitration fractions to the two extremes of the plausible range and
measure how far the board travels. If the whole admissible range moves it less
than a rounding change, then the ladder is not worth fitting, the gate is closed,
and everything downstream of it is dead work.

This is the shape of `docs/PITCHER_LABEL_LEDGER.md`'s decisive move: deleting the
entire censored pitcher block - the maximum possible perturbation any label
instrument could cause - moved the served board by Spearman 0.9441, and the whole
problem turned out to be worth less than a rounding change.

The bound is reported three ways, because a single mean hides the thing that
matters:
  * LEVEL   - mean and median absolute dollar move
  * SHAPE   - Spearman of the board against itself, and top-50 churn
  * TAIL    - movement restricted to the top decile, where the board is read

Usage:
    python tools/arb_ladder_blast_lab.py            # bound + incumbents
    python tools/arb_ladder_blast_lab.py --write    # + data/arb_blast_bound.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import value_framework as vf                                    # noqa: E402

OUT_PATH = ROOT / "data" / "arb_blast_bound.json"

# The admissible range for an arbitration ladder expressed as a fraction of the
# season's market value. Both ends are deliberately beyond anything a fit could
# plausibly return, because the point is to BOUND the effect, not to guess it.
#
#   LOW  - arbitration pays very little of market. Real arb-1 awards for stars
#          run roughly 0.10-0.20 of season market value.
#   HIGH - arbitration pays nearly market. No real ladder reaches here.
LADDER_LOW = [0.10, 0.20, 0.35, 0.50]
LADDER_HIGH = [0.55, 0.75, 0.90, 0.95]

# The two ladders that actually ship, for reference points inside the bound.
LADDER_CLEMENS = [0.15, 0.35, 0.50, 0.75]      # production default
LADDER_PROSPX = [0.40, 0.60, 0.80]             # base-identity set

# A board-shaped grid: FV x role. The prospect board is ~98% sub-50 FV, so the
# grid is weighted to where the rows actually are rather than spread evenly.
FV_GRID = [(fv, is_pit) for fv in (35, 40, 45, 50, 55, 60, 65, 70)
           for is_pit in (False, True)]


def _price(ladder, fv_grid):
    """{(fv, is_pitcher): surplus_usd} under one arbitration ladder."""
    orig = vf._apply_valuation_overlay

    def patched(cfg):
        cfg = orig(cfg)
        st = cfg.setdefault("service_time", {}).setdefault("arb_model", {})
        st["fractions_of_fa_value"] = list(ladder)
        return cfg

    vf._apply_valuation_overlay = patched
    vf._reset_caches()
    try:
        out = {}
        for fv, is_pit in fv_grid:
            try:
                out[(fv, is_pit)] = float(vf.expected_surplus_usd(fv, is_pit))
            except Exception as exc:                # pragma: no cover
                print(f"  price failed fv={fv} pit={is_pit}: {exc}")
        return out
    finally:
        vf._apply_valuation_overlay = orig
        vf._reset_caches()


def _spearman(a: list[float], b: list[float]) -> float:
    def rank(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        for pos, i in enumerate(order):
            r[i] = float(pos)
        return r
    ra, rb = rank(a), rank(b)
    n = len(ra)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((x - mb) ** 2 for x in rb) ** 0.5
    return num / (da * db) if da and db else float("nan")


def _compare(lo: dict, hi: dict) -> dict:
    keys = sorted(set(lo) & set(hi))
    a = [lo[k] for k in keys]
    b = [hi[k] for k in keys]
    diffs = [abs(x - y) for x, y in zip(a, b)]
    rel = [abs(x - y) / max(abs(x), abs(y), 1.0) for x, y in zip(a, b)]
    srt = sorted(diffs)
    med = srt[len(srt) // 2] if srt else 0.0
    top = sorted(range(len(keys)), key=lambda i: -max(a[i], b[i]))[:max(1, len(keys) // 10)]
    return {
        "n_cells": len(keys),
        "mean_abs_move_usd": round(sum(diffs) / len(diffs), 0) if diffs else 0.0,
        "median_abs_move_usd": round(med, 0),
        "max_abs_move_usd": round(max(diffs), 0) if diffs else 0.0,
        "mean_rel_move": round(sum(rel) / len(rel), 4) if rel else 0.0,
        "spearman_lo_vs_hi": round(_spearman(a, b), 4),
        "top_decile_mean_abs_move_usd": round(
            sum(diffs[i] for i in top) / len(top), 0) if top else 0.0,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    print(f"active valuation set: {vf._ACTIVE_VALUATION_SET}")
    print("pricing the grid under four ladders...")
    priced = {
        "low": _price(LADDER_LOW, FV_GRID),
        "high": _price(LADDER_HIGH, FV_GRID),
        "clemens_2026": _price(LADDER_CLEMENS, FV_GRID),
        "prospx_current": _price(LADDER_PROSPX, FV_GRID),
    }
    bound = _compare(priced["low"], priced["high"])
    incumbents = _compare(priced["clemens_2026"], priced["prospx_current"])

    print()
    print("THE BOUND (extreme low ladder vs extreme high ladder):")
    for k, v in bound.items():
        print(f"  {k:34s} {v}")
    print()
    print("For scale, the two ladders that actually ship:")
    for k, v in incumbents.items():
        print(f"  {k:34s} {v}")
    print()
    print("Per-cell surplus ($M), by FV:")
    print(f"  {'fv':>4} {'role':>4} {'low':>9} {'clemens':>9} {'prospx':>9} {'high':>9}")
    for fv, is_pit in FV_GRID:
        k = (fv, is_pit)
        row = [priced[s].get(k) for s in ("low", "clemens_2026", "prospx_current", "high")]
        if any(v is None for v in row):
            continue
        print(f"  {fv:>4} {'P' if is_pit else 'H':>4} " +
              " ".join(f"{v / 1e6:>9.2f}" for v in row))

    doc = {
        "generated_at": date.today().isoformat(),
        "produced_by": "python tools/arb_ladder_blast_lab.py",
        "purpose": ("GATE 0.1 blast-radius bound. Measures how far ANY admissible "
                    "arbitration ladder can move the served board, BEFORE any model "
                    "is fit. If the whole admissible range moves it less than a "
                    "rounding change, GATE B is closed on economic grounds."),
        "active_valuation_set": vf._ACTIVE_VALUATION_SET,
        "ladders": {"low": LADDER_LOW, "high": LADDER_HIGH,
                    "clemens_2026": LADDER_CLEMENS, "prospx_current": LADDER_PROSPX},
        "bound_low_vs_high": bound,
        "shipping_ladders_compared": incumbents,
        "grid": [{"fv": fv, "is_pitcher": p,
                  "low": priced["low"].get((fv, p)),
                  "clemens_2026": priced["clemens_2026"].get((fv, p)),
                  "prospx_current": priced["prospx_current"].get((fv, p)),
                  "high": priced["high"].get((fv, p))}
                 for fv, p in FV_GRID],
    }
    if args.write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        print(f"\nwrote {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
