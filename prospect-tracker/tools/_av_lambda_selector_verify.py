"""ADVERSARIAL VERIFY of the crossmodel lane's N2 (pitcher blend-lambda pinning).

The lane measured the flatness of the POOLED-RHO curve and compared it to a
pooled-rho lambda-shift floor. But efv_model.rank_calibration -- the selector that
actually sets the live pit lambda -- maximises a COMPOSITE
(pooled rho + within-tier weighted-mean rho + t45), not pooled rho. This harness
bootstraps the SHIPPED objective.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import efv_model as em  # noqa: E402
from efv_dataset import matrix_path  # noqa: E402

LO, HI = 0.50, 0.70
CAND = [round(LO + (HI - LO) * i / 20, 3) for i in range(21)]


def folds_for(side):
    """Exactly rank_calibration's fold construction: debuted-only, forward-chained."""
    keys, _m = em._feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    data = em._prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)
    out = []
    for yr in em.SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = em._fit_ols_fv(tr)
        ridge = em._fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        for r in te:
            out.append((max(0.0, em._pred_ols(ols, r["fv"])),
                        em._predict(ridge, r["feats"]), r["target"], r["fv"]))
    return out


def metrics(folds, lam):
    scored = [((1 - lam) * c + lam * m, t, fv) for c, m, t, fv in folds]
    rho = em._spearman([s for s, _, _ in scored], [t for _, t, _ in scored]) or 0.0
    byt = {}
    for s, t, fv in scored:
        byt.setdefault(round(fv / 5) * 5, []).append((s, t))
    wsum = wn = 0.0
    t45 = 0.0
    for tk, grp in byt.items():
        if len(grp) < 15:
            continue
        r = em._spearman([a for a, _ in grp], [b for _, b in grp])
        if r is None:
            continue
        wsum += r * len(grp)
        wn += len(grp)
        if tk == 45:
            t45 = r
    return rho, (wsum / wn if wn else 0.0), t45


def main():
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    rng = random.Random(99)
    out = {}
    for side in ("pit", "hit"):
        folds = folds_for(side)
        n = len(folds)
        pt = {L: metrics(folds, L) for L in CAND}
        comp = {L: sum(pt[L]) for L in CAND}
        argmax = max(CAND, key=lambda L: comp[L])
        spread_comp = max(comp.values()) - min(comp.values())
        spread_rho = max(pt[L][0] for L in CAND) - min(pt[L][0] for L in CAND)
        spread_t45 = max(pt[L][2] for L in CAND) - min(pt[L][2] for L in CAND)
        print(f"=== {side}  n_folds={n}")
        print(f"  point argmax {argmax}  composite spread {spread_comp:.5f}  "
              f"pooled-rho spread {spread_rho:.5f}  t45 spread {spread_t45:.5f}")

        # NULL BAND: permute the target within each fold-year block, re-select.
        # If the selector is picking noise, the permuted argmax distribution and the
        # permuted composite spread should look like the real one.
        perm_spreads = []
        perm_args = []
        for _ in range(100):
            tg = [f[2] for f in folds]
            rng.shuffle(tg)
            pf = [(c, m, tg[i], fv) for i, (c, m, _t, fv) in enumerate(folds)]
            pm = {L: sum(metrics(pf, L)) for L in CAND}
            perm_spreads.append(max(pm.values()) - min(pm.values()))
            perm_args.append(max(CAND, key=lambda L: pm[L]))
        perm_spreads.sort()
        p95 = perm_spreads[int(0.95 * len(perm_spreads))]
        print(f"  PERMUTATION NULL composite spread: median {perm_spreads[len(perm_spreads)//2]:.5f}"
              f"  p95 {p95:.5f}   -> observed {spread_comp:.5f} "
              f"{'ABOVE' if spread_comp > p95 else 'INSIDE'} the null band")

        # bootstrap the selector
        args = []
        cost = {L: [] for L in (0.50, 0.54, 0.59, 0.70)}
        for _ in range(B):
            idx = [rng.randrange(n) for _ in range(n)]
            bf = [folds[i] for i in idx]
            bm = {L: sum(metrics(bf, L)) for L in CAND}
            a = max(CAND, key=lambda L: bm[L])
            args.append(a)
            best = bm[a]
            for L in cost:
                cost[L].append(bm[L] - best)
        args.sort()
        lo95, hi95 = args[int(0.025 * B)], args[min(B - 1, int(0.975 * B))]
        from collections import Counter
        cc = Counter(args)
        print(f"  bootstrap argmax CI95 [{lo95}, {hi95}]  mass@0.50 {cc[0.5]/B:.3f} "
              f"mass@0.70 {cc[0.7]/B:.3f}")
        for L in sorted(cost):
            v = sorted(cost[L])
            print(f"    composite cost of pinning at {L}: mean {sum(v)/len(v):+.5f} "
                  f"p05 {v[int(0.05*len(v))]:+.5f}")
        out[side] = {"n_folds": n, "point_argmax": argmax,
                     "composite_spread": round(spread_comp, 5),
                     "pooled_rho_spread": round(spread_rho, 5),
                     "t45_spread": round(spread_t45, 5),
                     "perm_null_p95_spread": round(p95, 5),
                     "boot_argmax_ci95": [lo95, hi95],
                     "boot_argmax_hist": {str(k): v / B for k, v in sorted(cc.items())},
                     "pin_cost_composite": {str(L): round(sum(cost[L]) / B, 5) for L in sorted(cost)},
                     "curve_composite": {str(L): round(comp[L], 5) for L in CAND}}
    (ROOT / "data" / "_av_lambda_selector_verify.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    print("wrote data/_av_lambda_selector_verify.json")


if __name__ == "__main__":
    main()
