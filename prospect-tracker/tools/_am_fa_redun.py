# AUDIT LANE `fa`. (c) REDUNDANCY: what does each stage consume, and do two
# regressors carry the same information under different names?
"""Correlation / VIF audit of the FA stack's regression inputs.

The concrete suspicion the mandate raises is that fa_market (price),
fa_rational_value (value) and fa_projection (WAR) all ultimately regress on
the same war path. fa_market's guarantee stage in particular takes BOTH the
raw war path (w1, w1*years, prime_war) AND log_rational, which is a
deterministic convex-and-discounted function OF that same war path -- so the
same signal enters the design matrix twice, once raw and once transformed.
"""
from __future__ import annotations

import math
import pickle
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import _am_fa  # noqa: E402

GUAR_NAMES = ["const", "years", "w1", "w1*years", "age", "qo", "supply",
              "log_dpw", "log_comps_guar", "log_rational", "prime_war"]


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = math.sqrt(sum((x - ma) ** 2 for x in a))
    vb = math.sqrt(sum((x - mb) ** 2 for x in b))
    if va == 0 or vb == 0:
        return float("nan")
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb)


def vif(cols, j):
    """R^2 of column j on all the others -> 1/(1-R2)."""
    import numpy as np
    others = [c for i, c in enumerate(cols) if i != j and statistics.pstdev(c) > 0]
    if not others:
        return float("nan")
    X = np.column_stack([np.ones(len(cols[j]))] + [np.asarray(c) for c in others])
    y = np.asarray(cols[j])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    if ss_tot == 0:
        return float("nan")
    r2 = 1 - ss_res / ss_tot
    return 1 / max(1e-9, 1 - r2)


if __name__ == "__main__":
    import fa_market as fm
    with open(_am_fa.SCRATCH / "fa_enriched_signings_B.pkl", "rb") as fh:
        pool = pickle.load(fh)
    W = 2026
    train = [s for s in pool if s["class_year"] < W]
    dpw_series = fm.dollars_per_war_by_winter(train)
    model = fm.MarketModel(train, dpw_series)
    rows = model.train_pool

    names = list(GUAR_NAMES)
    if fm.X_FEATURES.get("rate_line"):
        nx = len(fm._x_rate_feats(rows[0]))
        names += ["rate_line_%d" % i for i in range(nx)]

    X = []
    for s in rows:
        dpw = fm.winter_dpw(dpw_series, s["class_year"])
        X.append(fm._features_guar(
            s, float(s["years"]), dpw, model._supply_z(s),
            model._comps_stats(s)[1],
            model._log_rational(s, float(s["years"]), dpw),
            model._prime_war(s)))
    cols = [[r[i] for r in X] for i in range(len(X[0]))]
    names = names[:len(cols)]
    print("GUARANTEE STAGE design matrix, train fold < %d, n=%d, p=%d"
          % (W, len(rows), len(cols)))

    print("\npairwise |r| >= 0.70 among guarantee regressors:")
    flagged = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            if statistics.pstdev(cols[i]) == 0 or statistics.pstdev(cols[j]) == 0:
                continue
            r = corr(cols[i], cols[j])
            if abs(r) >= 0.70:
                flagged.append((abs(r), names[i], names[j], r))
    for a, ni, nj, r in sorted(flagged, reverse=True):
        print("   %-18s %-18s r = %+0.4f" % (ni, nj, r))
    if not flagged:
        print("   none")

    print("\nVIF (variance inflation) per regressor:")
    for j, nm in enumerate(names):
        if statistics.pstdev(cols[j]) == 0:
            print("   %-18s constant" % nm)
            continue
        print("   %-18s %10.1f" % (nm, vif(cols, j)))

    # How much of log_rational is explained by the raw war-path features?
    import numpy as np
    idx = {n: i for i, n in enumerate(names)}
    lr = np.asarray(cols[idx["log_rational"]])
    raw = np.column_stack([np.ones(len(lr))] + [
        np.asarray(cols[idx[n]]) for n in ("w1", "years", "w1*years", "prime_war", "log_dpw")])
    b, *_ = np.linalg.lstsq(raw, lr, rcond=None)
    res = lr - raw @ b
    r2 = 1 - float((res ** 2).sum()) / float(((lr - lr.mean()) ** 2).sum())
    print("\nlog_rational regressed on the RAW war-path features it is built from:")
    print("   R^2 = %.4f   (log_rational carries %.1f%% unique variance)"
          % (r2, 100 * (1 - r2)))

    print("\nCROSS-MODEL: correlation of the signals the stack's models emit")
    import numpy as np2
    lab = {}
    lab["war_y1 (fa_projection)"] = [s["_war_path"]["war_y1"] for s in rows]
    lab["disc_war (fa_war_paths)"] = [fm.disc_war(s["_war_path"], int(s["years"])) for s in rows]
    lab["log_rational (fa_rational_value)"] = cols[idx["log_rational"]]
    lab["log_comps_guar (comps anchor)"] = cols[idx["log_comps_guar"]]
    lab["log_actual_guar (target)"] = [math.log(fm._npv_of(s)) for s in rows]
    ks = list(lab)
    print("   %-36s %s" % ("", "  ".join("%7d" % i for i in range(len(ks)))))
    for i, k in enumerate(ks):
        print("   %-36s %s" % ("%d %s" % (i, k),
                               "  ".join("%+7.3f" % corr(lab[k], lab[k2]) for k2 in ks)))
