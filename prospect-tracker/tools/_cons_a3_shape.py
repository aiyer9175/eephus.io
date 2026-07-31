# A3 -- is the FG<->Pipeline gap a pure SHIFT, or level-dependent (needs a slope)?
from __future__ import annotations

import collections

import numpy as np

from _cons_data import cluster_bootstrap, ci, load_matrix_rows

rows = load_matrix_rows()
pair = [r for r in rows if r["fg"] is not None and r["mp"] is not None]
fg = np.array([r["fg"] for r in pair], float)
mp = np.array([r["mp"] for r in pair], float)
keys = np.array([r["player_key"] for r in pair])

print("=== A3a. gap (MP - FG) by FanGraphs grade bin ===")
print(f"{'FG bin':>8} {'n':>5} {'meanMP':>8} {'gap':>8} {'se':>6}")
bins = [(20, 37.5), (37.5, 42.5), (42.5, 47.5), (47.5, 52.5), (52.5, 80)]
for lo, hi in bins:
    m = (fg >= lo) & (fg < hi)
    if m.sum() < 20:
        continue
    g = mp[m] - fg[m]
    print(f"{lo:>4}-{hi:<3} {m.sum():>5} {mp[m].mean():>8.2f} {g.mean():>+8.3f} "
          f"{g.std(ddof=1)/np.sqrt(m.sum()):>6.3f}")

print("\n=== A3b. regression MP = a + b*FG (Deming-free OLS both ways) ===")
X = np.column_stack([np.ones_like(fg), fg])
b_fwd = np.linalg.lstsq(X, mp, rcond=None)[0]
X2 = np.column_stack([np.ones_like(mp), mp])
b_rev = np.linalg.lstsq(X2, fg, rcond=None)[0]
print(f"  MP ~ FG : slope {b_fwd[1]:.4f} intercept {b_fwd[0]:+.3f}")
print(f"  FG ~ MP : slope {b_rev[1]:.4f} intercept {b_rev[0]:+.3f}")
print(f"  sd(FG)={fg.std(ddof=1):.3f}  sd(MP)={mp.std(ddof=1):.3f}  "
      f"ratio={mp.std(ddof=1)/fg.std(ddof=1):.4f}   corr={np.corrcoef(fg,mp)[0,1]:.4f}")
# error-in-variables consistent scale map: match sds (reduced major axis)
rma = mp.std(ddof=1) / fg.std(ddof=1)
print(f"  reduced-major-axis map: MP = {mp.mean()-rma*fg.mean():+.3f} + {rma:.4f}*FG")
print(f"  -> FG-scale(MP) = (MP - ({mp.mean()-rma*fg.mean():+.3f})) / {rma:.4f}")

# Is the pure shift enough? compare residual sd of shift-only vs rma map
shift = mp.mean() - fg.mean()
r_shift = (mp - shift) - fg
r_rma = (mp - (mp.mean() - rma * fg.mean())) / rma - fg
print(f"\n  residual sd, shift-only map : {r_shift.std(ddof=1):.4f}")
print(f"  residual sd, RMA (scale) map: {r_rma.std(ddof=1):.4f}")


def slope_dev(i):
    x, y = fg[i], mp[i]
    Xi = np.column_stack([np.ones_like(x), x])
    return float(np.linalg.lstsq(Xi, y, rcond=None)[0][1]) - 1.0


bs = cluster_bootstrap(keys, slope_dev, B=2000)
lo, hi = ci(bs)
print(f"\n  OLS slope(MP~FG) - 1 = {slope_dev(np.arange(len(pair))):+.4f}  "
      f"CI95 [{lo:+.4f}, {hi:+.4f}]  -> "
      f"{'slope differs from 1 (not a pure shift)' if (lo>0 or hi<0) else 'consistent with a pure shift'}")
