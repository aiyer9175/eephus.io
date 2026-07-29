# A2 -- coverage composition + the inverse-variance weights done in PREDICTED-WAR space.
from __future__ import annotations

import collections

import numpy as np

from _cons_data import cluster_bootstrap, ci, load_matrix_rows, spearman

rows = load_matrix_rows()


def cov_class(r):
    if r["fg"] is not None and r["mp"] is not None:
        return "both"
    if r["fg"] is not None:
        return "fg_only"
    if r["mp"] is not None:
        return "mp_only"
    return "none"


print("=== A2a. coverage class by decision year (matrix pool) ===")
tab = collections.defaultdict(collections.Counter)
for r in rows:
    tab[r["decision_year"]][cov_class(r)] += 1
print(f"{'year':>6} {'both':>6} {'fg_only':>8} {'mp_only':>8} {'none':>5}")
for y in sorted(tab):
    c = tab[y]
    print(f"{y:>6} {c['both']:>6} {c['fg_only']:>8} {c['mp_only']:>8} {c['none']:>5}")

print("\n=== A2b. mean target / mean consensus by coverage class ===")
print(f"{'class':>8} {'n':>6} {'meanFV':>8} {'meanWAR':>8} {'debut%':>7}")
for cc in ("both", "fg_only", "mp_only", "none"):
    sub = [r for r in rows if cov_class(r) == cc]
    if not sub:
        continue
    print(f"{cc:>8} {len(sub):>6} {np.mean([r['cons'] for r in sub]):>8.2f} "
          f"{np.mean([r['target'] for r in sub]):>8.3f} "
          f"{np.mean([r['kind']=='debuted' for r in sub]):>7.1%}")

# ---------------------------------------------------------------------------
# inverse-variance weights in PREDICTED-WAR space (scale-free, the right form)
# ---------------------------------------------------------------------------
pair = [r for r in rows if cov_class(r) == "both"]
keys = np.array([r["player_key"] for r in pair])
t = np.array([r["target"] for r in pair], float)
w = np.array([r["weight"] for r in pair], float)
fg = np.array([r["fg"] for r in pair], float)
mp = np.array([r["mp"] for r in pair], float)


def wls_resid_var(x, y, ww):
    X = np.column_stack([np.ones_like(x), x])
    beta = np.linalg.lstsq(X * ww[:, None], y * ww, rcond=None)[0]
    resid = y - X @ beta
    return float((ww * resid ** 2).sum() / ww.sum())


def ivw_pred_space(i):
    v1 = wls_resid_var(fg[i], t[i], w[i])
    v2 = wls_resid_var(mp[i], t[i], w[i])
    s1, s2 = 1.0 / v1, 1.0 / v2
    return 2 * s1 / (s1 + s2)


obs = ivw_pred_space(np.arange(len(pair)))
bs = cluster_bootstrap(keys, ivw_pred_space, B=2000)
lo, hi = ci(bs)
print("\n=== A2c. inverse-variance vote weight in PREDICTED-WAR space "
      "(scale-free; the correct form) ===")
print(f"  FanGraphs = {obs:.4f}  CI95 [{lo:.4f}, {hi:.4f}]")
print(f"  Pipeline  = {2-obs:.4f}  CI95 [{2-hi:.4f}, {2-lo:.4f}]")
print(f"  equal-weight (1.0) inside CI? {'YES' if lo <= 1.0 <= hi else 'NO'}")
print(f"  SHIPPED: fangraphs 0.9363 / mlb_pipeline 1.0637 -> "
      f"{'inside' if lo <= 0.9363 <= hi else 'OUTSIDE'} the FG CI")

# residual variance CI for each source separately
for nm, x in (("fangraphs", fg), ("mlb_pipeline", mp)):
    bsv = cluster_bootstrap(keys, lambda i, x=x: wls_resid_var(x[i], t[i], w[i]), B=1500)
    l, h = ci(bsv)
    print(f"  residual var {nm:>13} = {wls_resid_var(x, t, w):.3f}  CI95 [{l:.3f}, {h:.3f}]")
dv = lambda i: wls_resid_var(fg[i], t[i], w[i]) - wls_resid_var(mp[i], t[i], w[i])
bsd = cluster_bootstrap(keys, dv, B=2000)
l, h = ci(bsd)
print(f"  var(FG) - var(MP) = {dv(np.arange(len(pair))):+.4f}  CI95 [{l:+.4f}, {h:+.4f}]  "
      f"-> {'DISTINGUISHABLE' if (l>0 or h<0) else 'NULL (indistinguishable precision)'}")
