# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
efv_side_correction_lab.py - E2b-narrow. Does a per-side monotone recalibration
fix the FV 45 pitcher under-grade OUT OF SAMPLE?

Pre-registered at docs/efv-2026-08-12/PITCHER_BAND_CORRECTION_GATE.md, committed
before this file existed. Read it first: it fixes the folds, the correction
family and a three-clause ship rule, and clause 3 exists to catch the 2026-06-25
tail-regression failure under a new name.

E2a found pitchers at eFV 45 realizing +1.13 [0.19, 2.04] WAR more than hitters
holding the same grade. That was measured IN SAMPLE on the served grade. This
asks the only question that can justify changing a served grade: does a
correction fitted on EARLIER cohorts still help on LATER ones.

A NULL IS THE EXPECTED OUTCOME and is a complete result. The effect is 1 of 4
scored cells and its interval nearly touches zero.

Writes data/xfv_side_correction_eval.json.

Usage:
    python tools/efv_side_correction_lab.py
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
OUT = DATA / "xfv_side_correction_eval.json"

SEED = 20260812
BAND_LO, BAND_HI = 45.0, 50.0      # the cell E2a resolved
TAIL_LO = 55.0                     # clause 3
MIN_TRAIN, MIN_EVAL_SIDE = 150, 60
MAE_TOLERANCE = 0.02


def load_pool() -> list[dict]:
    """Resolved rows carrying predicted WAR, realized WAR, side, grade and the
    YEAR THE SCORED GRADE WAS GIVEN.

    For a graduate that year is his debut year, because run_backgrade anchors
    him at the last snapshot before it. For a bust it is his final snapshot.
    Those are the same quantity ("when was this grade current"), which is what
    lets them share one forward-chaining axis.
    """
    x = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    year_of: dict[str, int] = {}
    for name in ("debuts.json", "inactive.json"):
        try:
            rows = json.loads((DATA / name).read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in (rows if isinstance(rows, list) else []):
            if not isinstance(r, dict):
                continue
            k = r.get("player_key")
            if not k:
                continue
            d = r.get("debut_date")
            if not d:
                pts = r.get("points")
                d = (pts[-1].get("snapshot_date")
                     if isinstance(pts, list) and pts else None)
            if d and str(d)[:4].isdigit():
                year_of.setdefault(k, int(str(d)[:4]))

    pool = []
    for k, v in x.items():
        if v.get("kind") not in ("debuted", "bust") or v.get("side") not in ("H", "P"):
            continue
        rw = 0.0 if v["kind"] == "bust" else v.get("realized_war")
        if rw is None or v.get("xfv_war_6yr") is None or v.get("xfv_grade") is None:
            continue
        y = year_of.get(k)
        if y is None:
            continue
        pool.append({"key": k, "side": v["side"], "year": y,
                     "pred": float(v["xfv_war_6yr"]),
                     "real": float(rw), "grade": float(v["xfv_grade"])})
    return pool


def _isotonic(xs, ys):
    """PAVA. sklearn if present, else a compact pool-adjacent-violators fit.

    Returned as a step function over the fitted knots so the caller never has to
    hold sklearn's object, and so a fold with a degenerate fit degrades to the
    identity rather than raising."""
    pairs = sorted(zip(xs, ys))
    if len(pairs) < 10:
        return lambda v: v
    try:
        from sklearn.isotonic import IsotonicRegression
        ir = IsotonicRegression(out_of_bounds="clip")
        ir.fit([p[0] for p in pairs], [p[1] for p in pairs])
        return lambda v: float(ir.predict([v])[0])
    except Exception:
        blocks = [[y, 1, x] for x, y in pairs]          # [mean, weight, x]
        i = 0
        while i < len(blocks) - 1:
            if blocks[i][0] <= blocks[i + 1][0] + 1e-12:
                i += 1
                continue
            m0, w0, x0 = blocks[i]
            m1, w1, _ = blocks.pop(i + 1)
            blocks[i] = [(m0 * w0 + m1 * w1) / (w0 + w1), w0 + w1, x0]
            if i:
                i -= 1
        knots = [(b[2], b[0]) for b in blocks]

        def f(v):
            lo, hi = 0, len(knots) - 1
            if v <= knots[0][0]:
                return knots[0][1]
            if v >= knots[hi][0]:
                return knots[hi][1]
            while lo < hi - 1:
                mid = (lo + hi) // 2
                if knots[mid][0] <= v:
                    lo = mid
                else:
                    hi = mid
            return knots[lo][1]
        return f


def _band_gap(rows, lo, hi):
    h = [r for r in rows if lo <= r["grade"] < hi and r["side"] == "H"]
    p = [r for r in rows if lo <= r["grade"] < hi and r["side"] == "P"]
    if len(h) < 10 or len(p) < 10:
        return None, len(h), len(p)
    return st.mean(r["resid"] for r in p) - st.mean(r["resid"] for r in h), len(h), len(p)


def run(boot: int) -> dict:
    pool = load_pool()
    years = sorted({r["year"] for r in pool})
    folds, evaluated = [], []
    for y in years:
        train = [r for r in pool if r["year"] <= y]
        ev = [r for r in pool if r["year"] == y + 1]
        if len(train) < MIN_TRAIN:
            continue
        if sum(1 for r in ev if r["side"] == "H") < MIN_EVAL_SIDE or \
           sum(1 for r in ev if r["side"] == "P") < MIN_EVAL_SIDE:
            continue
        maps = {}
        for s in ("H", "P"):
            tr = [r for r in train if r["side"] == s]
            maps[s] = _isotonic([r["pred"] for r in tr], [r["real"] for r in tr])
        for r in ev:
            corr = maps[r["side"]](r["pred"])
            evaluated.append({**r,
                              "pred_corr": corr,
                              # residual = realized minus predicted. The side
                              # gap in E2a is a gap in THIS, and a correction
                              # that works drives both sides' residuals together.
                              "resid": r["real"] - r["pred"],
                              "resid_corr": r["real"] - corr,
                              "fold_train_to": y})
        folds.append({"train_to": y, "n_train": len(train), "n_eval": len(ev)})

    if not evaluated:
        return {"verdict": "NO_SHIP", "reason": "no fold met the registered minimums",
                "folds": folds}

    def mae(rows, key):
        return st.mean(abs(r[key]) for r in rows) if rows else None

    # Clause 1: the band gap.
    for r in evaluated:
        r["_r"] = r["resid"]
    gap_before, nh, np_ = _band_gap(evaluated, BAND_LO, BAND_HI)
    for r in evaluated:
        r["resid"], r["_keep"] = r["resid_corr"], r["_r"]
    gap_after, _, _ = _band_gap(evaluated, BAND_LO, BAND_HI)
    for r in evaluated:
        r["resid"] = r["_keep"]

    rng = random.Random(SEED)
    improved = None
    if gap_before is not None and gap_after is not None:
        diffs = []
        idx = range(len(evaluated))
        for _ in range(boot):
            samp = [evaluated[rng.randrange(len(evaluated))] for _ in idx]
            for r in samp:
                r["resid"] = r["_keep"]
            b, _, _ = _band_gap(samp, BAND_LO, BAND_HI)
            for r in samp:
                r["resid"] = r["resid_corr"]
            a, _, _ = _band_gap(samp, BAND_LO, BAND_HI)
            for r in samp:
                r["resid"] = r["_keep"]
            if b is not None and a is not None:
                diffs.append(abs(b) - abs(a))          # positive = shrank
        diffs.sort()
        if diffs:
            improved = [round(diffs[int(0.025 * (len(diffs) - 1))], 4),
                        round(diffs[int(0.975 * (len(diffs) - 1))], 4)]

    clause1 = bool(gap_before is not None and gap_after is not None
                   and abs(gap_after) < abs(gap_before)
                   and improved and improved[0] > 0)

    # Clause 2: overall per-side MAE.
    per_side, clause2 = {}, True
    for s in ("H", "P"):
        rows = [r for r in evaluated if r["side"] == s]
        b, a = mae(rows, "resid"), mae(rows, "resid_corr")
        per_side[s] = {"n": len(rows), "mae_before": round(b, 4) if b else None,
                       "mae_after": round(a, 4) if a else None,
                       "delta": round(a - b, 4) if (a and b) else None}
        if b is not None and a is not None and a > b + MAE_TOLERANCE:
            clause2 = False

    # Clause 3: the tail, which is where the 2026-06-25 attempt died.
    tail, clause3 = {}, True
    for s in ("H", "P"):
        rows = [r for r in evaluated if r["side"] == s and r["grade"] >= TAIL_LO]
        b, a = mae(rows, "resid"), mae(rows, "resid_corr")
        tail[s] = {"n": len(rows), "mae_before": round(b, 4) if b else None,
                   "mae_after": round(a, 4) if a else None,
                   "delta": round(a - b, 4) if (a and b) else None}
        if b is not None and a is not None and a > b + MAE_TOLERANCE:
            clause3 = False

    ship = clause1 and clause2 and clause3
    return {
        "verdict": "SHIP" if ship else "NO_SHIP",
        "clauses": {"c1_band_gap_shrinks": clause1,
                    "c2_overall_mae_not_worse": clause2,
                    "c3_tail_mae_not_worse": clause3},
        "band": {"lo": BAND_LO, "hi": BAND_HI, "n_hit": nh, "n_pit": np_,
                 "gap_before": round(gap_before, 4) if gap_before is not None else None,
                 "gap_after": round(gap_after, 4) if gap_after is not None else None,
                 "improvement_ci95": improved},
        "per_side_mae": per_side, "tail_mae": tail,
        "folds": folds, "n_evaluated": len(evaluated),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=2000)
    args = ap.parse_args()
    res = run(args.boot)
    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model_id": "xfv_side_correction",
        "pre_registration": "docs/efv-2026-08-12/PITCHER_BAND_CORRECTION_GATE.md",
        "basis": {"seed": SEED, "bootstrap_B": args.boot,
                  "folds": "forward-chained on the year the scored grade was given",
                  "correction": "per-side isotonic (PAVA) of realized WAR on predicted WAR",
                  "mae_tolerance": MAE_TOLERANCE},
        **res,
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")

    print(f"folds: {len(res.get('folds') or [])}, rows evaluated out of sample: "
          f"{res.get('n_evaluated')}")
    b = res.get("band") or {}
    print(f"\nCLAUSE 1  band {b.get('lo')}-{b.get('hi')} gap "
          f"{b.get('gap_before')} -> {b.get('gap_after')} "
          f"(improvement CI {b.get('improvement_ci95')})  "
          f"{'PASS' if res['clauses']['c1_band_gap_shrinks'] else 'FAIL'}")
    print("CLAUSE 2  overall MAE " +
          "  ".join(f"{s}: {v['mae_before']} -> {v['mae_after']}"
                    for s, v in (res.get("per_side_mae") or {}).items()) +
          f"  {'PASS' if res['clauses']['c2_overall_mae_not_worse'] else 'FAIL'}")
    print("CLAUSE 3  tail MAE    " +
          "  ".join(f"{s}: {v['mae_before']} -> {v['mae_after']} (n={v['n']})"
                    for s, v in (res.get("tail_mae") or {}).items()) +
          f"  {'PASS' if res['clauses']['c3_tail_mae_not_worse'] else 'FAIL'}")
    print(f"\nVERDICT: {res['verdict']}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
