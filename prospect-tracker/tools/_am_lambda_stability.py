"""CROSSMODEL LANE: is the pitcher blend-lambda selector stable, or is it an
argmax over a curve flatter than its own registered detection limit?

Registered artifact data/xfv_eval_pitcher.json (2026-07-24) stamps
shipped_lambda 0.59 with "matches_shipped_lambda": true.
Live efv_model.blend_lambda('pit') returns 0.54, with no code change; the
selector is a dynamic argmax (efv_model._BLEND_LAMBDA_RESELECT['pit'] is None),
whereas the hitter side was PINNED to 0.70 explicitly for run-to-run stability.

Fits ridge + consensus OLS ONCE per (draw, fold) and scores every lambda off the
same legs, so the lambda sweep costs one fit, not 21.
"""
from __future__ import annotations

import collections
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_model as em  # noqa: E402

GRID = [round(0.50 + 0.01 * i, 2) for i in range(21)]


def load(side):
    p = ROOT / "data" / ("xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json")
    return json.loads(p.read_text(encoding="utf-8"))


def curve_for(rows, side, grid=GRID, debuted_only=False):
    """One ridge+OLS fit per fold; pooled Spearman for every lambda off those legs."""
    is_pit = side == "pit"
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    if debuted_only:
        pool = [r for r in pool if r.get("kind") == "debuted"]
    keys, _m = em._feature_spec(side)
    data = em._prep(pool, "target_censored", side)
    legs = []          # (cons_pred, model_pred, target)
    for yr in em.SCORED_YEARS:
        train = [r for r in data if r["decision_year"] < yr]
        test = [r for r in data if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        ols = em._fit_ols_fv(train)
        ridge = em._fit_ridge(train, keys)
        if not (ols and ridge):
            continue
        for r in test:
            legs.append((max(0.0, em._pred_ols(ols, r["fv"])),
                         em._predict(ridge, r["feats"]), r["target"]))
    if len(legs) < 40:
        return None, 0
    out = {}
    for lam in grid:
        out[lam] = em._score([((1 - lam) * c + lam * m, t) for c, m, t in legs]).get("spearman")
    return out, len(legs)


def main():
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    side = sys.argv[2] if len(sys.argv) > 2 else "pit"
    deb = len(sys.argv) > 3 and sys.argv[3] == "debuted"
    rng = random.Random(7788)
    rows = load(side)
    n = len(rows)

    pt, npairs = curve_for(rows, side, debuted_only=deb)
    best = max(pt, key=lambda k: pt[k])
    print("side %s  rows %d  scored pairs %d  debuted_only=%s" % (side, n, npairs, deb))
    for lam in GRID:
        print("   lam %.2f  rho %.5f%s" % (lam, pt[lam], "   <-- argmax" if lam == best else ""))
    spread = max(pt.values()) - min(pt.values())
    print("point argmax %.2f   curve spread %.5f" % (best, spread))
    print("registered MDE95 for a pit lambda shift (EFV_GATE_STANDARD 1): 0.005-0.008")

    argmaxes, d_pin = [], collections.defaultdict(list)
    for b in range(B):
        rb = [rows[rng.randrange(n)] for _ in range(n)]
        c, _ = curve_for(rb, side, debuted_only=deb)
        if not c:
            continue
        am = max(c, key=lambda k: c[k])
        argmaxes.append(am)
        for pin in (0.54, 0.59, 0.70):
            d_pin[pin].append(c[pin] - c[am])
        if (b + 1) % 25 == 0:
            print("   ... %d draws" % (b + 1))

    if not argmaxes:
        print("no draws")
        return
    cnt = collections.Counter(argmaxes)
    B2 = len(argmaxes)
    print("\nBOOTSTRAP ARGMAX DISTRIBUTION (B=%d):" % B2)
    for lam, k in sorted(cnt.items()):
        print("   lam %.2f  %4d  (%.1f%%)" % (lam, k, 100.0 * k / B2))
    srt = sorted(argmaxes)
    print("argmax CI95 [%.2f, %.2f]  median %.2f  range [%.2f, %.2f]"
          % (srt[int(0.025 * B2)], srt[min(B2 - 1, int(0.975 * B2))],
             srt[B2 // 2], srt[0], srt[-1]))

    def summ(xs):
        xs = sorted(xs)
        m = len(xs)
        return {"mean": round(sum(xs) / m, 5),
                "p05": round(xs[int(0.05 * m)], 5), "n": m}

    print("\nCOST OF PINNING (rho at pin minus rho at that draw's argmax; <=0 by construction):")
    pin_cost = {}
    for pin in sorted(d_pin):
        pin_cost[str(pin)] = summ(d_pin[pin])
        print("   pin %.2f  %s" % (pin, pin_cost[str(pin)]))

    res = {"side": side, "debuted_only": deb, "point_curve": {str(k): v for k, v in pt.items()},
           "point_argmax": best, "curve_spread": round(spread, 5),
           "bootstrap_argmax_counts": {str(k): v for k, v in sorted(cnt.items())},
           "argmax_ci95": [srt[int(0.025 * B2)], srt[min(B2 - 1, int(0.975 * B2))]],
           "pin_cost": pin_cost, "B": B2,
           "registered_artifact_lambda": 0.59, "live_lambda": em.blend_lambda(side)}
    (ROOT / "data" / ("_am_lambda_stability_%s%s.json" % (side, "_deb" if deb else ""))).write_text(
        json.dumps(res, indent=1), encoding="utf-8")
    print("\nwrote data/_am_lambda_stability_%s%s.json" % (side, "_deb" if deb else ""))


if __name__ == "__main__":
    main()
