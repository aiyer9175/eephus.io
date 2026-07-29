"""Diagnostic: does any biometric axis correlate with the SHIPPED model's
out-of-fold residual? This is independent of ridge shrinkage, so it separates
"the feature has no information" from "the ridge shrank it away"."""
import sys, json
import numpy as np
sys.path.insert(0, r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker\tools")
import _arch_bio_gate as G
from prospect_path import _spearman
from efv_model import _feature_spec, blend_lambda

for side in ("hit", "pit"):
    rows = G.load(side)
    keys = _feature_spec(side)[0]
    lam = blend_lambda(side)
    recs = []
    for yr in G.FOLDS_EXT:
        tr = [r for r in rows if r["decision_year"] < yr and r["target_censored"] is not None]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        out = G._score_fold(tr, te, keys, "none", lam, side)
        if out is None:
            continue
        b, p, t, fv = out
        for i, r in enumerate(te):
            recs.append((r, float(b[i]), float(t[i])))
    # rank-residual: rank(truth) - rank(model score), so + = model UNDER-rated him
    sc = np.array([x[1] for x in recs]); tr_ = np.array([x[2] for x in recs])
    rs = sc.argsort().argsort().astype(float) / len(sc)
    rt = tr_.argsort().argsort().astype(float) / len(tr_)
    resid = rt - rs
    print("== %s  n=%d" % (side, len(recs)))
    for axis in ("bmi", "h", "w", "frame", "athl", "levers"):
        v = [(i, r[0]["bio"][axis]) for i, r in enumerate(recs) if r[0]["bio"][axis] is not None]
        if len(v) < 60:
            print("   %-7s n=%-4d  (too thin)" % (axis, len(v)))
            continue
        idx = [i for i, _ in v]; val = [x for _, x in v]
        rho = _spearman(val, list(resid[idx]))
        # 95% band for rho at this n under independence
        band = 1.96 / np.sqrt(len(v) - 1)
        print("   %-7s n=%-4d  rho(axis, rank-residual) = %+.4f   indep 95%% band +/-%.4f  %s"
              % (axis, len(v), rho, band, "signal" if abs(rho) > band else "no signal"))
