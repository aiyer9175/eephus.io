"""Power check: score ONLY the bio-covered test rows. The 34-37% uncovered rows
carry an identical feature value in both arms, so they can only dilute the delta.
Training still uses the full pool (unchanged), so this is an evaluation restriction,
not a pool change."""
import sys, json
import numpy as np
sys.path.insert(0, r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker\tools")
import _arch_bio_gate as G
from prospect_path import _spearman
from efv_model import _feature_spec, blend_lambda


def eval_covered(rows, kind, side, axis="bmi"):
    keys = _feature_spec(side)[0]
    lam = blend_lambda(side)
    B, T = [], []
    for yr in G.FOLDS_EXT:
        tr = [r for r in rows if r["decision_year"] < yr and r["target_censored"] is not None]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        out = G._score_fold(tr, te, keys, kind, lam, side)
        if out is None:
            continue
        b, p, t, fv = out
        for i, r in enumerate(te):
            if r["bio"][axis] is not None:
                B.append(float(b[i])); T.append(float(t[i]))
    if len(B) < 30:
        return None, 0
    return _spearman(B, T), len(B)


for side, axis, kinds in (("hit", "bmi", ("bmi", "linear", "arch_inter", "arch_strat")),
                          ("hit", "frame", ("frame",)),
                          ("pit", "bmi", ("bmi", "linear", "arch_inter", "arch_strat")),
                          ("pit", "frame", ("frame",))):
    rows = G.load(side)
    base, n = eval_covered(rows, "none", side, axis)
    print("== %s covered-only (%s present) n=%d  base rho=%.4f" % (side, axis, n, base))
    years = sorted({r["decision_year"] for r in rows})
    by_year = {y: [r for r in rows if r["decision_year"] == y] for y in years}
    for kind in kinds:
        c, _ = eval_covered(rows, kind, side, axis)
        rng = np.random.default_rng(4242)
        boot = []
        for _ in range(400):
            res = []
            for y in years:
                g = by_year[y]
                idx = rng.integers(0, len(g), len(g))
                res.extend(g[i] for i in idx)
            b0, _n0 = eval_covered(res, "none", side, axis)
            b1, _n1 = eval_covered(res, kind, side, axis)
            if b0 is not None and b1 is not None:
                boot.append(b1 - b0)
        boot = np.array(boot)
        print("   %-11s rho=%.4f  d=%+.4f  CI95[%+.4f,%+.4f]  P(imp)=%.3f"
              % (kind, c, c - base, np.quantile(boot, .025), np.quantile(boot, .975),
                 (boot > 0).mean()))
