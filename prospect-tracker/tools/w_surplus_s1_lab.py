# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""W-SURPLUS S1 (2026-07-24 cycle): isotonic calibration refresh - CANDIDATE ONLY.

Registration (docs/efv-2026-07-24/GATES.md, W-SURPLUS S1): refit the surplus
calibration on the CURRENT resolved pool with the exact shipped protocol
(fit_surplus_calibration.py: today-priced targets, resolved pool,
isotonic_binned count-weighted PAVA, 25-knot downsample) and judge:

  BAR 1: LOyO held-out slope in [0.90, 1.10]
  BAR 2: LOyO held-out PIT P10-P90 coverage >= the shipped artifact's
         (primary comparator: data/surplus_backtest_real.json
          resolved_only.cross_validated_correction.held_out_pit
          .coverage_p10_p90 = 0.8589; full-pool 0.7941 reported too)

NOTHING is written to production configs or data/. The candidate block +
all eval numbers go to the session scratchpad (path via --out). The shipped
block stays untouched; wave D restamps on PASS.

Tail-knot convention replicated from the shipped block: the last observed
segment is linearly continued to x=140 so elite raws keep ordering instead
of clipping at the top bin.

Run: python tools/w_surplus_s1_lab.py --out <scratchpad>/s1_candidate_calibration.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np                                                   # noqa: E402

from backtest import (apply_correction, predict_listing, pit_value,   # noqa: E402
                      realized_sv_pv, run_backtest)
from surplus_backtest_real import build_cohorts, _resolved_only       # noqa: E402
import storage                                                        # noqa: E402
import value_framework as vf                                          # noqa: E402

N_BREAKPOINTS = 25          # frozen: fit tool's downsample count
TAIL_X = 140.0              # frozen: shipped tail-knot convention
SLOPE_LO, SLOPE_HI = 0.90, 1.10
SHIPPED_PIT_RESOLVED = 0.8588655649843681   # surplus_backtest_real.json resolved_only
SHIPPED_PIT_FULL = 0.7941176470588235       # surplus_backtest_real.json full_pool
CURVE_FVS = (40.0, 45.0, 50.0, 55.0, 60.0)


def _downsample(xs: list[float], ys: list[float], k: int) -> tuple[list, list]:
    if len(xs) <= k:
        return xs, ys
    idx = [round(i * (len(xs) - 1) / (k - 1)) for i in range(k)]
    idx = sorted(set(idx))
    return [xs[i] for i in idx], [ys[i] for i in idx]


def _tail_extend(xs: list[float], ys: list[float]) -> tuple[list, list]:
    """Continue the final observed segment to TAIL_X (shipped convention)."""
    if len(xs) < 2 or xs[-1] >= TAIL_X:
        return xs, ys
    dx = xs[-1] - xs[-2]
    dy = ys[-1] - ys[-2]
    slope = (dy / dx) if dx > 0 else 0.0
    return xs + [TAIL_X], ys + [ys[-1] + slope * (TAIL_X - xs[-1])]


def _name_of(con, key: str) -> str:
    row = con.execute("SELECT player_name FROM players WHERE player_key=?",
                      (key,)).fetchone()
    return (row[0] if row and row[0] else key)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    records, accounting = build_cohorts()
    cfg = vf._config()
    flat_mm = vf.dollars_per_war_flat()
    dpw_by_year = {y: {"overall": flat_mm} for y in range(2014, 2035)}
    resolved = _resolved_only(records)
    rep = run_backtest(resolved, discount_rate=float(cfg["discount_rate"]),
                       dpw_by_year=dpw_by_year, correction_method="isotonic_binned")

    corr = rep.get("fitted_correction_full_sample") or {}
    xs = [float(v) for v in corr.get("x_mm", [])]
    ys = [float(v) for v in corr.get("y_mm", [])]
    xs, ys = _downsample(xs, ys, N_BREAKPOINTS)
    xs, ys = _tail_extend(xs, ys)

    cv = rep["cross_validated_correction"]
    held_slope = float(cv["held_out_calibration"].get("slope", float("nan")))
    held_pit = float(cv["held_out_pit"].get("coverage_p10_p90", float("nan")))

    bar1 = SLOPE_LO <= held_slope <= SLOPE_HI
    bar2_resolved = held_pit >= SHIPPED_PIT_RESOLVED
    bar2_full = held_pit >= SHIPPED_PIT_FULL

    candidate_block = {
        "enabled": True,
        "version": f"isotonic-real-v4-todaypriced-{date.today().isoformat()}-CANDIDATE",
        "method": "isotonic",
        "linear": {"slope": 1.0, "intercept_mm": 0.0},
        "isotonic": {"x_mm": [round(x, 2) for x in xs],
                     "y_mm": [round(y, 2) for y in ys]},
        "fit_provenance": (
            "W-SURPLUS S1 CANDIDATE (2026-07-24 cycle, NOT SHIPPED): same protocol as "
            "isotonic-real-v3-todaypriced (count-weighted PAVA on equal-count bin means, "
            "surplus_backtest_real resolved pool 2017-2019 listings, TODAY-PRICED targets, "
            "n=%d): raw slope %.2f / bias %+.1fM corrected to held-out slope %.2f / "
            "bias %+.2fM under leave-one-year-out CV; held-out PIT P10-P90 coverage %.3f. "
            "%d knots incl. the tail-segment continuation to %g." % (
                rep["n_players"], rep["raw_calibration"]["slope"],
                rep["raw_errors"]["bias"], held_slope, cv["held_out_bias"],
                held_pit, len(xs), TAIL_X)),
    }

    # Curve comparison at the registered FVs, both sides, raw -> shipped vs candidate.
    curve = {}
    for side, is_pit, pos in (("hit", False, None), ("pit", True, "SP")):
        rows = []
        for f in CURVE_FVS:
            usd = vf.expected_surplus_usd(f, is_pit, pos)
            raw_mm = (usd or 0.0) / 1e6
            shipped = vf.apply_calibration(raw_mm, f, is_pit)
            cand = apply_correction(candidate_block["isotonic"] | {"method": "isotonic"},
                                    raw_mm)
            rows.append({"fv": f, "raw_mm": round(raw_mm, 2),
                         "shipped_mm": round(float(shipped), 2),
                         "candidate_mm": round(float(cand), 2),
                         "delta_mm": round(float(cand) - float(shipped), 2)})
        curve[side] = rows

    # Named example players: largest positive/negative candidate-vs-shipped moves
    # among the resolved pool's own raw predictions.
    examples = []
    with storage.connect() as con:
        preds = []
        for r in resolved:
            usd = vf.expected_surplus_usd(
                r.listing.fv, r.listing.is_pitcher, r.listing.position,
                age=r.listing.age_at_listing, eta_years=r.listing.eta_years)
            raw_mm = (usd or 0.0) / 1e6
            shipped = float(vf.apply_calibration(raw_mm, r.listing.fv,
                                                 r.listing.is_pitcher))
            cand = float(apply_correction(
                candidate_block["isotonic"] | {"method": "isotonic"}, raw_mm))
            preds.append((cand - shipped, r.listing.player_id, r.listing.fv,
                          raw_mm, shipped, cand, r.listing.listing_year))
        preds.sort(key=lambda t: t[0])
        for d, key, f, raw_mm, shipped, cand, yr in preds[:3] + preds[-3:]:
            examples.append({"player": _name_of(con, key), "listing_year": yr,
                             "fv": f, "raw_mm": round(raw_mm, 2),
                             "shipped_mm": round(shipped, 2),
                             "candidate_mm": round(cand, 2),
                             "delta_mm": round(d, 2)})

    out = {
        "lane": "W-SURPLUS S1 isotonic refresh (2026-07-24 cycle)",
        "registration": "docs/efv-2026-07-24/GATES.md W-SURPLUS S1",
        "generated_at": date.today().isoformat(),
        "protocol": "fit_surplus_calibration.py protocol, resolved pool, today-priced",
        "accounting": accounting,
        "n_resolved": rep["n_players"],
        "raw_calibration": rep["raw_calibration"],
        "raw_errors": rep["raw_errors"],
        "binned_calibration_slope": rep["binned_calibration"].get("slope"),
        "cross_validated_correction": {
            "held_out_slope": held_slope,
            "held_out_bias": cv["held_out_bias"],
            "held_out_rmse": cv["held_out_rmse"],
            "held_out_pit": cv["held_out_pit"],
            "n_held_out": cv["n_held_out"],
            "years": cv["years"],
        },
        "bars": {
            "loyo_slope_in_0.90_1.10": {"measured": held_slope, "pass": bool(bar1)},
            "pit_ge_shipped_resolved_0.8589": {"measured": held_pit,
                                               "pass": bool(bar2_resolved)},
            "pit_ge_shipped_full_0.7941_reported_only": {"measured": held_pit,
                                                         "pass": bool(bar2_full)},
        },
        "verdict_rule": "PASS requires bar1 AND the primary (resolved) PIT bar",
        "verdict": ("PASS" if (bar1 and bar2_resolved) else "FAIL"),
        "candidate_block": candidate_block,
        "curve_fv_table": curve,
        "example_players": examples,
        "shipped_block_version": (cfg.get("calibration") or {}).get("version"),
    }
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in
                      ("n_resolved", "bars", "verdict", "curve_fv_table")}, indent=1))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
