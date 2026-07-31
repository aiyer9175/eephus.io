# A1 -- per-outlet BIAS and PRECISION, with CIs. Analysis only.
from __future__ import annotations

import collections
import json

import numpy as np

from _cons_data import (OUT, cluster_bootstrap, ci, fmt, load_matrix_rows,
                        spearman, auc, _rank)

rows = load_matrix_rows()
print(f"matrix rows (target present, cons present): {len(rows)}")
print("  by side:", collections.Counter(r["side"] for r in rows))
print("  by kind:", collections.Counter(r["kind"] for r in rows))
print("  n_sources:", collections.Counter(r["n_sources"] for r in rows))
print("  has fg:", sum(1 for r in rows if r["fg"] is not None),
      " has mp:", sum(1 for r in rows if r["mp"] is not None),
      " has both:", sum(1 for r in rows if r["fg"] is not None and r["mp"] is not None))

# ---------------------------------------------------------------------------
# 1. SCALE BIAS on the PAIRED overlap (same players, same decision point)
# ---------------------------------------------------------------------------
pair = [r for r in rows if r["fg"] is not None and r["mp"] is not None]
d = np.array([r["mp"] - r["fg"] for r in pair], float)
keys = np.array([r["player_key"] for r in pair])
print("\n=== A1a. PAIRED SCALE GAP (MLB Pipeline minus FanGraphs), matrix decision points ===")
print(f"n_pair={len(pair)}  mean gap={d.mean():+.3f} FV  sd={d.std(ddof=1):.3f}  "
      f"se={d.std(ddof=1)/np.sqrt(len(d)):.3f}  median={np.median(d):+.2f}")
bs = cluster_bootstrap(keys, lambda i: d[i].mean(), B=2000)
lo, hi = ci(bs)
print(f"  cluster-bootstrap CI95 [{lo:+.3f}, {hi:+.3f}]")
for side in ("hit", "pit"):
    dd = np.array([r["mp"] - r["fg"] for r in pair if r["side"] == side], float)
    print(f"  {side}: n={len(dd)} mean={dd.mean():+.3f} se={dd.std(ddof=1)/np.sqrt(len(dd)):.3f}")

# by decision year -> DRIFT (investigation 4)
print("\n=== A1b. BIAS DRIFT by decision year ===")
byyr = collections.defaultdict(list)
for r in pair:
    byyr[r["decision_year"]].append(r["mp"] - r["fg"])
print(f"{'year':>6} {'n':>5} {'meanGap':>9} {'se':>6}")
drift_rows = []
for y in sorted(byyr):
    v = np.array(byyr[y], float)
    if len(v) < 12:
        continue
    se = v.std(ddof=1) / np.sqrt(len(v))
    print(f"{y:>6} {len(v):>5} {v.mean():>+9.3f} {se:>6.3f}")
    drift_rows.append((y, len(v), float(v.mean()), float(se)))
# drift test: weighted linear trend of gap on year
if len(drift_rows) >= 4:
    ys = np.array([r[0] for r in drift_rows], float)
    gs = np.array([r[2] for r in drift_rows], float)
    ws = np.array([1.0 / (r[3] ** 2) for r in drift_rows], float)
    W = ws.sum()
    mx, my = (ws * ys).sum() / W, (ws * gs).sum() / W
    b = (ws * (ys - mx) * (gs - my)).sum() / (ws * (ys - mx) ** 2).sum()
    resid = gs - (my + b * (ys - mx))
    se_b = np.sqrt(1.0 / (ws * (ys - mx) ** 2).sum())
    print(f"  weighted trend: {b:+.4f} FV/yr  se={se_b:.4f}  t={b/se_b:+.2f}")

# ---------------------------------------------------------------------------
# 2. PRECISION: WAR ~ a + b*FV per source, on the PAIRED set (fair)
# ---------------------------------------------------------------------------
print("\n=== A1c. PRECISION on the PAIRED set (same players, same target) ===")
t = np.array([r["target"] for r in pair], float)
w = np.array([r["weight"] for r in pair], float)
cols = {"fangraphs": np.array([r["fg"] for r in pair], float),
        "mlb_pipeline": np.array([r["mp"] for r in pair], float),
        "served_consensus": np.array([r["cons"] for r in pair], float),
        "equal_mean": np.array([(r["fg"] + r["mp"]) / 2 for r in pair], float)}


def wls(x, y, ww):
    X = np.column_stack([np.ones_like(x), x])
    W = np.diag(ww)
    beta = np.linalg.lstsq(X * ww[:, None], y * ww, rcond=None)[0]
    pred = X @ beta
    resid = y - pred
    rvar = float((ww * resid ** 2).sum() / ww.sum())
    return float(beta[0]), float(beta[1]), rvar


print(f"{'source':>17} {'n':>5} {'slope':>8} {'intercept':>10} {'residVar':>9} "
      f"{'precision':>10} {'rho':>8} {'rho CI95':>20}")
prec = {}
for name, x in cols.items():
    a, b, rv = wls(x, t, w)
    rho = spearman(x, t)
    bs = cluster_bootstrap(keys, lambda i, x=x: spearman(x[i], t[i]), B=1500)
    lo, hi = ci(bs)
    prec[name] = {"slope": b, "intercept": a, "resid_var": rv, "rho": rho,
                  "rho_ci": [lo, hi]}
    print(f"{name:>17} {len(x):>5} {b:>8.4f} {a:>10.3f} {rv:>9.3f} "
          f"{1/rv:>10.4f} {rho:>8.4f}  [{lo:+.4f},{hi:+.4f}]")

# paired difference in rho, FG vs MP (the head-to-head that source weights rest on)
fg, mp = cols["fangraphs"], cols["mlb_pipeline"]
dstat = lambda i: spearman(fg[i], t[i]) - spearman(mp[i], t[i])
obs = dstat(np.arange(len(pair)))
bs = cluster_bootstrap(keys, dstat, B=2000)
lo, hi = ci(bs)
print(f"\n  rho(FG) - rho(Pipeline) = {obs:+.4f}   CI95 [{lo:+.4f}, {hi:+.4f}]  "
      f"P(FG better) = {np.mean(np.array(bs) > 0):.3f}")

# same on AUC (contributor = 3 WAR)
lab = t >= 3.0
dauc = lambda i: auc(fg[i], lab[i]) - auc(mp[i], lab[i])
obs_a = dauc(np.arange(len(pair)))
bs_a = cluster_bootstrap(keys, dauc, B=2000)
lo_a, hi_a = ci(bs_a)
print(f"  AUC(FG) - AUC(Pipeline) = {obs_a:+.4f}  CI95 [{lo_a:+.4f}, {hi_a:+.4f}]  "
      f"P(FG better) = {np.mean(np.array(bs_a) > 0):.3f}")

# ---------------------------------------------------------------------------
# 3. Residual variance decomposition -> inverse-variance weights (with CI)
# ---------------------------------------------------------------------------
print("\n=== A1d. Implied inverse-variance vote weights (from paired residual var) ===")


def ivw(i):
    a1, b1, v1 = wls(fg[i], t[i], w[i])
    a2, b2, v2 = wls(mp[i], t[i], w[i])
    # weight proportional to (slope^2 / residual variance): signal-to-noise
    s1, s2 = (b1 ** 2) / v1, (b2 ** 2) / v2
    return 2 * s1 / (s1 + s2)          # relative vote weight for FG (1.0 = equal)


obs_w = ivw(np.arange(len(pair)))
bs_w = cluster_bootstrap(keys, ivw, B=2000)
lo_w, hi_w = ci(bs_w)
print(f"  FanGraphs relative vote weight = {obs_w:.4f}  CI95 [{lo_w:.4f}, {hi_w:.4f}]")
print(f"  Pipeline  relative vote weight = {2-obs_w:.4f}  CI95 [{2-hi_w:.4f}, {2-lo_w:.4f}]")
print(f"  SHIPPED weights: fangraphs 0.9363 / mlb_pipeline 1.0637")
print(f"  equal-weight (1.0) inside CI? {'YES' if lo_w <= 1.0 <= hi_w else 'NO'}")

json.dump({"n_pair": len(pair), "gap_mean": float(d.mean()),
           "gap_ci": list(ci(cluster_bootstrap(keys, lambda i: d[i].mean(), B=1000))),
           "precision": prec,
           "drift": drift_rows,
           "ivw_fg": obs_w, "ivw_fg_ci": [lo_w, hi_w]},
          open(OUT / "a1_bias.json", "w"), indent=1)
print("\nwrote", OUT / "a1_bias.json")
