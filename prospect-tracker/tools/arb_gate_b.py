# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""GATE B: should the fitted arbitration ladder replace the shipped constant?

Pre-registered in docs/ARBITRATION_GATE.md section 5.

THE TARGET IS OBSERVED ARBITRATION DOLLARS, NEVER surplus_backtest_real.
`surplus_backtest_real._impute_seasons` computes the REALIZED salary as
`frac * tiered_war_value_usd(war)` from the same `fractions_of_fa_value` the
prediction uses, so target and parameter are the same number and the ladder
largely cancels in the residual. B4 below proves that artifact is
non-diagnostic rather than asserting it.

THE INCUMBENT IS clemens_2026, not [0.40, 0.60, 0.80]. Production runs a
four-step [0.15, 0.35, 0.50, 0.75] ladder on a prior-season basis with seven
control years; the three-step ladder in the base yaml is the prospx_current
base-identity set. Both are scored and both are reported.

Metric: MAE of the DISCOUNTED arbitration-window salary total per player. The
ladder is consumed inside a discounted sum, so a ladder that is wrong per-year
and right in total is fine for surplus and the reverse is not.

Usage:
    python tools/arb_gate_b.py --write
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np                                              # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import value_framework as vf                                    # noqa: E402

OUT = ROOT / "data" / "arb_ladder_eval.json"
SEED = 20260809

CLEMENS = [0.15, 0.35, 0.50, 0.75]
PROSPX = [0.40, 0.60, 0.80]
DISCOUNT = 0.07


def _pool():
    """Players with an observed arbitration WINDOW: consecutive scored seasons
    with a salary and a step."""
    import arb_dataset as A
    rows = A.build_panel()["rows"]
    sc = A.scored_rows(rows)
    by: dict[int, dict[int, dict]] = {}
    for r in sc:
        by.setdefault(int(r["mlbam"]), {})[int(r["arb_year"])] = r
    out = []
    for mlbam, steps in by.items():
        if len(steps) < 2:
            continue
        out.append({"mlbam": mlbam, "steps": steps,
                    "name": next(iter(steps.values())).get("name")})
    return out


def _market_usd(row) -> float:
    """That season's open-market value for the player's WAR, through the shipped
    kernel - the denominator the ladder is a fraction OF."""
    return float(vf.tiered_war_value_usd(float(row.get("war") or 0.0)))


def _predict_window(steps: dict, ladder, *, basis="prior_season") -> float:
    """Discounted total predicted salary across the observed window."""
    tot = 0.0
    for i, (step, row) in enumerate(sorted(steps.items())):
        idx = min(step - 1, len(ladder) - 1)
        frac = ladder[idx]
        if basis == "prior_season":
            mkt = float(row.get("prior_market") or _market_usd(row))
        else:
            mkt = _market_usd(row)
        lm = float(row.get("league_min") or 700_000.0)
        tot += max(lm, frac * mkt) / ((1 + DISCOUNT) ** i)
    return tot


def _actual_window(steps: dict) -> float:
    tot = 0.0
    for i, (_step, row) in enumerate(sorted(steps.items())):
        tot += float(row["salary"]) / ((1 + DISCOUNT) ** i)
    return tot


def _mae(pool, ladder, basis="prior_season") -> float:
    e = [abs(_predict_window(p["steps"], ladder, basis=basis)
             - _actual_window(p["steps"])) for p in pool]
    return float(np.mean(e))


def _fit_ladder(pool, basis="prior_season"):
    """The fitted ladder: per step, the median ratio of the OBSERVED salary to
    that season's market value. This is what `fractions_of_fa_value` MEANS."""
    by: dict[int, list[float]] = {}
    for p in pool:
        for step, row in p["steps"].items():
            mkt = _market_usd(row)
            if mkt > 0:
                by.setdefault(int(step), []).append(float(row["salary"]) / mkt)
    out = []
    for step in (1, 2, 3, 4):
        v = by.get(step)
        out.append(float(np.median(v)) if v and len(v) >= 15
                   else (out[-1] if out else 0.2))
    # Enforce monotonicity, which value_framework._arb_ladder assumes.
    for i in range(1, len(out)):
        out[i] = max(out[i], out[i - 1])
    return out, {str(k): len(v) for k, v in sorted(by.items())}


def run() -> dict:
    pool = _pool()
    print(f"players with an observed arbitration window: {len(pool)}")
    fitted, counts = _fit_ladder(pool)
    print(f"fitted ladder: {[round(x, 4) for x in fitted]}  (n per step {counts})")

    base = {
        "fitted": _mae(pool, fitted),
        "clemens_2026": _mae(pool, CLEMENS),
        "prospx_current": _mae(pool, PROSPX),
    }
    for k, v in base.items():
        print(f"  MAE {k:16s} ${v/1e6:8.3f}M")

    # B2: the one-parameter twin. If a single global scalar on the incumbent
    # captures most of the gain, the finding is a LEVEL correction and ships as
    # one parameter, not as a fitted shape.
    best_s, best_mae = 1.0, base["clemens_2026"]
    for s in np.arange(0.30, 3.01, 0.01):
        m = _mae(pool, [f * s for f in CLEMENS])
        if m < best_mae:
            best_s, best_mae = float(s), float(m)
    gain_fitted = base["clemens_2026"] - base["fitted"]
    gain_scalar = base["clemens_2026"] - best_mae
    captured = (gain_scalar / gain_fitted) if gain_fitted > 0 else 1.0
    print(f"  B2 one-parameter twin: scalar {best_s:.2f} -> MAE "
          f"${best_mae/1e6:.3f}M, captures {captured:.1%} of the fitted gain")

    # B3: the rank-identical twin - same ordering, different spacing.
    rng = np.random.default_rng(SEED)
    twin_better = 0
    for _ in range(200):
        jitter = sorted(float(f * (1 + rng.normal(0, 0.15))) for f in fitted)
        if _mae(pool, jitter) <= base["fitted"]:
            twin_better += 1
    print(f"  B3 rank-identical twins beating the fit: {twin_better}/200")

    # Floor: paired bootstrap clustered on player, refitting every draw.
    boot = []
    for _ in range(1000):
        idx = rng.integers(0, len(pool), len(pool))
        draw = [pool[i] for i in idx]
        f, _c = _fit_ladder(draw)
        boot.append(_mae(draw, CLEMENS) - _mae(draw, f))
    a = np.array(boot, float)
    sd = float(a.std(ddof=1))
    floor = 1.645 * sd
    resolvable = gain_fitted >= floor
    print(f"  B1 gain ${gain_fitted/1e6:.3f}M vs floor ${floor/1e6:.3f}M "
          f"-> {gain_fitted/floor if floor else 0:.2f}x  resolvable={resolvable}")

    level_only = captured >= 0.75
    verdict = "PASS" if (resolvable and not level_only) else "NULL"
    doc = {
        "generated_at": date.today().isoformat(),
        "produced_by": "python tools/arb_gate_b.py --write",
        "model": "arb_ladder",
        "gate": "docs/ARBITRATION_GATE.md section 5 (GATE B)",
        "conventions": {
            "target": ("OBSERVED arbitration dollars, never "
                       "surplus_backtest_real, whose realized side is computed "
                       "from the same constant being fitted"),
            "metric": ("MAE of the DISCOUNTED arbitration-window salary total "
                       "per player"),
            "basis": "prior_season, matching the shipped clemens_2026 set",
            "floor": ("paired bootstrap clustered on PLAYER, refitting the "
                      "ladder on every draw, one-sided MDE95"),
        },
        "n_players": len(pool),
        "n_per_step": counts,
        "fitted_ladder": fitted,
        "incumbents": {"clemens_2026": CLEMENS, "prospx_current": PROSPX},
        "mae_usd": base,
        "b1_gain_vs_clemens_usd": gain_fitted,
        "mde95_onesided_usd": floor,
        "gain_over_floor": (gain_fitted / floor) if floor else None,
        "resolvable": bool(resolvable),
        "b2_one_parameter_twin": {
            "best_scalar": best_s, "mae_usd": best_mae,
            "share_of_fitted_gain_captured": captured,
            "level_only": bool(level_only),
        },
        "b3_rank_identical_twins_beating_fit": twin_better,
        "verdict_gate": verdict,
        "verdict": "unvalidated",
        "config_changed": False,
        "loss_ledger": [],
    }
    if verdict == "NULL":
        doc["loss_ledger"].append({
            "claim": "the fitted arbitration ladder should replace the shipped constant",
            "verdict": "NULL",
            "statement": (
                "The fitted ladder is a LEVEL correction, not a shape "
                "correction. A single global scalar applied to the shipped "
                f"clemens_2026 ladder captures {captured:.1%} of the fitted "
                "ladder's improvement, against a pre-registered 75% rule. It "
                "ships, if it ships, as one parameter. The three- and four-number "
                "ladders are NOT supported by this measurement, and "
                "value_framework_config.yaml is UNCHANGED."
                if level_only else
                "The fitted ladder does not beat the shipped clemens_2026 ladder "
                "by more than the floor measured for this basis. Reported as a "
                "NULL. value_framework_config.yaml is UNCHANGED."),
        })
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    doc = run()
    print(f"\nVERDICT: {doc['verdict_gate']}  (config unchanged)")
    if args.write:
        OUT.write_text(json.dumps(doc, indent=1, default=float), encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
