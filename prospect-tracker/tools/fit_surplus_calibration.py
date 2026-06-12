# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Fit + ship the prospect-surplus calibration correction (Phase 4, WS-6).

Phase 0 measured the raw model overshooting ~2x at the margin (slope 0.51
full / 0.55 resolved, bias -6M/player). The leave-one-year-out CV in
data/surplus_backtest_real.json shows the isotonic correction fixing it
held-out (bias -0.01, slope 0.93, PIT coverage 0.67 -> 0.79). This tool
re-runs the real backtest, takes the FULL-SAMPLE isotonic fit, downsamples
it to ~25 quantile breakpoints (interpolation preserves the shape; nobody
needs 2,900 knots in a yaml file), and prints the calibration block to
paste into value_framework_config.yaml. The block is committed WITH the
regenerated artifact — config decision + eval, the standing-rule pattern.

The backtest always fits/score against RAW predictions (no circularity:
backtest.py reads expected_surplus_usd, not apply_calibration output).

Run: python tools/fit_surplus_calibration.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest import fit_isotonic_correction, run_backtest          # noqa: E402
from surplus_backtest_real import build_cohorts, _resolved_only     # noqa: E402
import value_framework as vf                                        # noqa: E402

N_BREAKPOINTS = 25


def _downsample(xs: list[float], ys: list[float], k: int) -> tuple[list, list]:
    if len(xs) <= k:
        return xs, ys
    idx = [round(i * (len(xs) - 1) / (k - 1)) for i in range(k)]
    idx = sorted(set(idx))
    return [xs[i] for i in idx], [ys[i] for i in idx]


def main() -> None:
    records, accounting = build_cohorts()
    cfg = vf._config()
    # v3 (2026-06-12, owner: levels read low across the board): the
    # realized TARGETS are priced at the STANDING flat $/WAR rather than
    # each season's historical rate. Historical pricing ($6.7-12.1M/WAR
    # for the cohort seasons) deflated every target by the era's cheaper
    # dollars, so the calibration was "correcting" the model for dollar
    # inflation on top of WAR optimism. Constant today-pricing makes the
    # calibration a pure WAR-layer correction and the shipped surplus
    # mean "expected realized value at current replacement cost". The
    # committed backtest artifact keeps historical pricing (that slice
    # answers a different question: what DID the cohort return).
    flat_mm = vf.dollars_per_war_flat()
    dpw_by_year = {y: {"overall": flat_mm} for y in range(2014, 2035)}
    # Fit on the RESOLVED pool (censored-active excluded) — the cleanest
    # target population; the full-pool CV in the artifact corroborates.
    resolved = _resolved_only(records)
    rep = run_backtest(resolved, discount_rate=float(cfg["discount_rate"]),
                       dpw_by_year=dpw_by_year, correction_method="isotonic_binned")
    corr = rep.get("fitted_correction_full_sample") or {}
    xs = [float(v) for v in corr.get("x_mm", [])]
    ys = [float(v) for v in corr.get("y_mm", [])]
    if len(xs) < 2:
        # fall back to fitting directly from the per-player frame
        pairs = sorted((r["predicted_mm"], r["realized_mm"])
                       for r in rep["players"])
        fit = fit_isotonic_correction([p for p, _ in pairs],
                                      [a for _, a in pairs])
        xs, ys = fit["x_mm"], fit["y_mm"]
    xs, ys = _downsample(xs, ys, N_BREAKPOINTS)
    block = {
        "enabled": True,
        "version": f"isotonic-real-v3-todaypriced-{date.today().isoformat()}",
        "method": "isotonic",
        "linear": {"slope": 1.0, "intercept_mm": 0.0},
        "isotonic": {"x_mm": [round(x, 2) for x in xs],
                     "y_mm": [round(y, 2) for y in ys]},
        "fit_provenance": (
            "REAL-data fit v3 BINNED + TODAY-PRICED targets (realized WAR valued at the standing flat $/WAR; the calibration corrects the WAR layer only) (count-weighted PAVA on equal-count bin means - "
            "per-player PAVA let exact-zero busts force a degenerate $0 bottom block; "
            "surplus_backtest_real resolved pool, 2017-2019 "
            "listings, n=%d): raw slope %.2f / bias %+.1fM corrected to "
            "held-out slope %.2f / bias %+.2fM under leave-one-year-out CV "
            "(see data/surplus_backtest_real.json cross_validated_correction). "
            "Breakpoints downsampled to %d knots." % (
                rep["n_players"],
                rep["raw_calibration"]["slope"], rep["raw_errors"]["bias"],
                rep["cross_validated_correction"]["held_out_calibration"]["slope"],
                rep["cross_validated_correction"]["held_out_bias"],
                len(xs))),
    }
    print(json.dumps(block, indent=1))
    out = ROOT / "data" / "surplus_calibration_fit.json"
    out.write_text(json.dumps(block, indent=1), encoding="utf-8")
    print(f"\nwrote {out} — paste the block into value_framework_config.yaml "
          f"calibration: and re-emit snapshots")


if __name__ == "__main__":
    main()
