# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Fit the prospect-surplus calibration correction's KNOTS (Phase 4, WS-6;
repaired for the $/WAR path build, VAL_5, 2026-10-02).

Phase 0 measured the raw model overshooting at the margin; the binned isotonic
map corrects the WAR layer. This tool fits that map through
backtest.fit_calibration_knots, the knots-only entry point: it builds the
predictions and the realized targets and fits the map, and it computes no
by_fv_tier table, no sensitivity table, no PIT, no slope, no bias and no
held-out statistic (it never calls backtest.run_backtest). Its records come
from surplus_backtest_real.build_cohorts, the one sanctioned importer of that
module under docs/dpw-2026-09-25/DPW_PATH_GATE.md section 0a.

Target pricing (--target):
  today_flat  v3: every realized season priced at today's flat $/WAR (the
              calibration corrects the WAR layer only), discounted from the
              listing year at discount_rate
  today_path  unified $/WAR path mode only: listings re-dated to N and every
              realized season priced on the written path (value at its own
              level, the minimum and arbitration by the companion index,
              discounted by season_discount)

The fitted block prints to stdout. It is written only when --out names a path,
so a run never overwrites the tracked fit by accident.

Run: python tools/fit_surplus_calibration.py [--target today_flat] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest import fit_calibration_knots                          # noqa: E402
from surplus_backtest_real import build_cohorts, _resolved_only     # noqa: E402
import value_framework as vf                                        # noqa: E402

N_BREAKPOINTS = 25
VERSION_BY_TARGET = {"today_flat": "isotonic-real-v3-todaypriced",
                     "today_path": "isotonic-real-v4-todaypath"}


def _downsample(xs: list[float], ys: list[float], k: int) -> tuple[list, list]:
    if len(xs) <= k:
        return xs, ys
    idx = [round(i * (len(xs) - 1) / (k - 1)) for i in range(k)]
    idx = sorted(set(idx))
    return [xs[i] for i in idx], [ys[i] for i in idx]


def fit_provenance(n_players: int, n_knots: int, target_pricing: str) -> str:
    """Names ONLY the pool, n, the knot count and the target pricing: the
    knots-only entry computes no slope, bias or held-out figure, so none is quoted."""
    return ("REAL-data knots-only fit, BINNED isotonic (count-weighted PAVA on equal-count bin "
            "means) on the surplus_backtest_real resolved pool, 2017-2019 listings, n=%d; "
            "target pricing %s; breakpoints downsampled to %d knots." % (
                n_players, target_pricing, n_knots))


def build_block(target_pricing: str = "today_flat") -> dict:
    records, _accounting = build_cohorts()
    resolved = _resolved_only(records)
    fit = fit_calibration_knots(resolved, target_pricing=target_pricing)
    corr = fit["fitted_correction"]
    xs = [float(v) for v in corr.get("x_mm", [])]
    ys = [float(v) for v in corr.get("y_mm", [])]
    xs, ys = _downsample(xs, ys, N_BREAKPOINTS)
    level_mm = (vf.price_level(vf.pricing_base_season()) / 1e6 if target_pricing == "today_path"
                else vf.dollars_per_war_flat())
    return {
        "enabled": True,
        "version": f"{VERSION_BY_TARGET[target_pricing]}-{date.today().isoformat()}",
        "method": "isotonic",
        # VAL_1 (2026-09-25): the level the targets and raw predictions were
        # priced at; value_framework applies the map in this unit.
        "fit_dpw_flat_usd": int(round(level_mm * 1e6)),
        "target_pricing": target_pricing,
        "linear": {"slope": 1.0, "intercept_mm": 0.0},
        "isotonic": {"x_mm": [round(x, 2) for x in xs],
                     "y_mm": [round(y, 2) for y in ys]},
        "fit_provenance": fit_provenance(fit["n_players"], len(xs), target_pricing),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=sorted(VERSION_BY_TARGET), default="today_flat")
    ap.add_argument("--out", default=None,
                    help="write the block here (default: print only)")
    args = ap.parse_args(argv)
    block = build_block(args.target)
    print(json.dumps(block, indent=1))
    if args.out:
        out = Path(args.out)
        out.write_text(json.dumps(block, indent=1), encoding="utf-8")
        print(f"\nwrote {out}; paste the block into value_framework_config.yaml "
              f"calibration: and re-emit snapshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
