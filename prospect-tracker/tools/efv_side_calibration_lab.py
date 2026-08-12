# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
efv_side_calibration_lab.py - E2a. Is eFV systemically undervaluing pitchers?

Pre-registered at docs/efv-2026-08-12/SIDE_CALIBRATION_GATE.md, committed
BEFORE this file existed. Read it first: it fixes the estimands, the frame and
the decision rule, and it is what stops this from being a number hunt.

THE ONE RULE THAT SHAPES EVERYTHING (owner, binding): source bias is measured
against REALIZED OUTCOMES, never against another source's grade. "eFV puts 8
pitchers in its top 100 and the consensus puts 27" is not evidence about either
of them. Only what those players produced adjudicates.

Frame: the resolved pool, kind in (debuted, bust), busts entered at realized
6-year WAR of 0. Busts are IN because dropping them is survivor bias and the
bust counts differ by side.

Writes data/xfv_side_calibration_eval.json.

Usage:
    python tools/efv_side_calibration_lab.py
    python tools/efv_side_calibration_lab.py --boot 2000
"""

from __future__ import annotations

import argparse
import json
import random
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "xfv_side_calibration_eval.json"

SEED = 20260812
BANDS = (60, 55, 50, 45, 40, 35, 30)
MIN_CELL = 30          # registered: below this a cell is reported, not scored


def band_of(g):
    if g is None:
        return None
    for lo in BANDS:
        if g >= lo:
            return lo
    return BANDS[-1]


def load_pool() -> list[dict]:
    doc = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    out = []
    for key, v in (doc.get("by_player") or {}).items():
        kind, side = v.get("kind"), v.get("side")
        if kind not in ("debuted", "bust") or side not in ("H", "P"):
            continue
        # A bust never reached MLB, so its realized 6-year WAR is 0. Recording
        # it as missing and dropping it would keep only survivors, and the
        # survivor rate is exactly what differs between the two sides.
        rw = 0.0 if kind == "bust" else v.get("realized_war")
        if rw is None:
            continue
        out.append({
            "key": key, "side": side, "kind": kind,
            "realized_war": float(rw),
            "efv": v.get("xfv_grade"),
            "consensus": v.get("consensus_fv"),
            "pred_war": v.get("xfv_war_6yr"),
        })
    return out


def _boot_diff(a: list[float], b: list[float], B: int, rng: random.Random):
    """95% interval for mean(a) - mean(b) by independent resampling.

    The two side samples are disjoint players, so this is an unpaired
    difference; resampling each side within itself is the honest analogue of
    the paired bootstrap used elsewhere in this repo."""
    if len(a) < 2 or len(b) < 2:
        return None, None
    diffs = []
    for _ in range(B):
        ra = [a[rng.randrange(len(a))] for _ in range(len(a))]
        rb = [b[rng.randrange(len(b))] for _ in range(len(b))]
        diffs.append(st.mean(ra) - st.mean(rb))
    diffs.sort()
    lo = diffs[int(0.025 * (len(diffs) - 1))]
    hi = diffs[int(0.975 * (len(diffs) - 1))]
    return round(lo, 4), round(hi, 4)


def by_band(pool, grade_key: str, B: int) -> dict:
    """M1: mean realized WAR by side within each band of `grade_key`."""
    rng = random.Random(SEED)
    cells, scored_gaps = {}, []
    for b in BANDS:
        h = [r["realized_war"] for r in pool
             if r["side"] == "H" and band_of(r.get(grade_key)) == b]
        p = [r["realized_war"] for r in pool
             if r["side"] == "P" and band_of(r.get(grade_key)) == b]
        scorable = len(h) >= MIN_CELL and len(p) >= MIN_CELL
        gap = (st.mean(p) - st.mean(h)) if (h and p) else None
        lo, hi = _boot_diff(p, h, B, rng) if scorable else (None, None)
        resolvable = bool(scorable and lo is not None and (lo > 0 or hi < 0))
        cells[str(b)] = {
            "n_hit": len(h), "n_pit": len(p),
            "mean_war_hit": round(st.mean(h), 3) if h else None,
            "mean_war_pit": round(st.mean(p), 3) if p else None,
            "gap_pit_minus_hit": round(gap, 3) if gap is not None else None,
            "ci95": [lo, hi] if lo is not None else None,
            "scored": scorable,
            "resolvable": resolvable,
            "verdict": ("not scored, cell under the registered floor" if not scorable
                        else "pitchers realize more" if resolvable and gap > 0
                        else "pitchers realize less" if resolvable and gap < 0
                        else "not resolvable at this power"),
        }
        if scorable:
            scored_gaps.append((b, gap, lo, hi))
    return {"cells": cells, "n_scored_cells": len(scored_gaps),
            "n_resolvable": sum(1 for b in cells.values() if b["resolvable"])}


def per_side_forecast(pool) -> dict:
    """M2: is the model's own WAR forecast biased, per side?"""
    out = {}
    for side in ("H", "P"):
        rows = [r for r in pool if r["side"] == side and r.get("pred_war") is not None]
        if len(rows) < 30:
            out[side] = {"n": len(rows), "note": "too few rows"}
            continue
        pred = [r["pred_war"] for r in rows]
        real = [r["realized_war"] for r in rows]
        mp, mr = st.mean(pred), st.mean(real)
        vp = sum((x - mp) ** 2 for x in pred)
        cov = sum((pred[i] - mp) * (real[i] - mr) for i in range(len(rows)))
        slope = cov / vp if vp else None
        out[side] = {
            "n": len(rows),
            "mean_predicted_war": round(mp, 3),
            "mean_realized_war": round(mr, 3),
            "bias_pred_minus_real": round(mp - mr, 3),
            "slope_real_on_pred": round(slope, 4) if slope is not None else None,
            "reading": ("a slope under 1 means the forecast is too spread out, "
                        "over 1 means too compressed; bias is its level error"),
        }
    return out


def share_conventions(pool, top_n: int = 100) -> dict:
    """M3: pitcher share of the top N under three conventions. Descriptive."""
    served = [r for r in pool if r.get("efv") is not None]
    served.sort(key=lambda r: -r["efv"])
    as_served = sum(1 for r in served[:top_n] if r["side"] == "P")

    # Within-side percentile parity: rank inside each side, then interleave by
    # percentile. This is the industry convention, and it is a pure relabelling.
    out = {}
    for label, key in (("efv", "efv"), ("consensus", "consensus")):
        rows = [r for r in pool if r.get(key) is not None]
        by_side = {}
        for s in ("H", "P"):
            side_rows = sorted([r for r in rows if r["side"] == s],
                               key=lambda r: -r[key])
            n = len(side_rows)
            for i, r in enumerate(side_rows):
                by_side[r["key"]] = (n - i) / n if n else 0.0
        ranked = sorted(rows, key=lambda r: -by_side.get(r["key"], 0.0))
        out[label] = {
            "top_n": top_n,
            "pitchers_as_ranked": sum(1 for r in sorted(rows, key=lambda r: -r[key])[:top_n]
                                      if r["side"] == "P"),
            "pitchers_under_percentile_parity": sum(1 for r in ranked[:top_n]
                                                    if r["side"] == "P"),
        }
    return {"resolved_pool_top_n": top_n, "efv_as_served": as_served, "by_grade": out,
            "note": ("this is the RESOLVED pool, not the live board. It shows what "
                     "each convention does to the mix, not what the board shows today")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=2000)
    args = ap.parse_args()

    pool = load_pool()
    n_h = sum(1 for r in pool if r["side"] == "H")
    n_p = len(pool) - n_h
    print(f"resolved pool: {len(pool)} rows ({n_h} hit / {n_p} pit), "
          f"busts entered at realized WAR 0")

    efv_bands = by_band(pool, "efv", args.boot)
    cons_bands = by_band(pool, "consensus", args.boot)
    forecast = per_side_forecast(pool)
    shares = share_conventions(pool)

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model_id": "xfv_side_calibration",
        "pre_registration": "docs/efv-2026-08-12/SIDE_CALIBRATION_GATE.md",
        "basis": {
            "frame": "resolved pool: kind in (debuted, bust), busts at realized 6yr WAR 0",
            "n": len(pool), "n_hit": n_h, "n_pit": n_p,
            "bootstrap_B": args.boot, "seed": SEED,
            "min_cell": MIN_CELL,
            "reference": ("realized 6-year WAR. No claim here is made by comparing "
                          "one source's grade to another's"),
            "caveat": ("the served eFV grade is retrospective on this pool, so this "
                       "measures the SHIPPED grade map against outcomes, not an "
                       "out-of-sample forecast"),
        },
        "m1_realized_war_by_band": {"efv": efv_bands, "consensus": cons_bands},
        "m2_per_side_forecast": forecast,
        "m3_share_conventions": shares,
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")

    print("\nM1  realized 6yr WAR by band, pitchers minus hitters")
    for label, blk in (("served eFV", efv_bands), ("consensus FV", cons_bands)):
        print(f"\n  --- {label} ---")
        for b in BANDS:
            c = blk["cells"][str(b)]
            g = c["gap_pit_minus_hit"]
            ci = c["ci95"]
            print(f"   {b:>3}: H n={c['n_hit']:>4} {str(c['mean_war_hit']):>7} | "
                  f"P n={c['n_pit']:>4} {str(c['mean_war_pit']):>7} | "
                  f"gap {('%+.2f' % g) if g is not None else '   -  '} "
                  f"{('[%.2f, %.2f]' % (ci[0], ci[1])) if ci else ''}  {c['verdict']}")

    print("\nM2  per-side WAR forecast")
    for s in ("H", "P"):
        f = forecast[s]
        if "bias_pred_minus_real" in f:
            print(f"   {s}: n={f['n']:>4} pred {f['mean_predicted_war']:>5} vs real "
                  f"{f['mean_realized_war']:>5}  bias {f['bias_pred_minus_real']:+.3f}  "
                  f"slope {f['slope_real_on_pred']}")

    print("\nM3  pitcher share of the resolved top 100")
    print(f"   as served (eFV):                      {shares['efv_as_served']}")
    for k, v in shares["by_grade"].items():
        print(f"   {k:<10} ranked / percentile parity:  "
              f"{v['pitchers_as_ranked']} / {v['pitchers_under_percentile_parity']}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
