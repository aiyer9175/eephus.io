# Scratch lab (audit-mode, lane=plusmetrics).
# C1 follow-up: the hitter Luck column (luck_gap = xHEM+ - HEM+) is scale-broken
# because HEM+ divides a SHRUNK wOBA by a shrunk-pool anchor while xHEM+ divides
# an UNSHRUNK xwOBA by a raw-pool anchor. Two candidate repairs; measure the
# forward COST of each before recommending one.
#
#   FIX-A  shrink xwOBA with the same EB recipe (toward the pool, by Savant PA)
#          before the ratio, so both legs are on one ruler.
#   FIX-B  redefine hitter Luck as (actual wOBA - xwOBA), i.e. exactly what the
#          starter/reliever boards already publish. Costs nothing forward
#          (it is not a predictor), and removes the family inconsistency.
#
# Requirement for FIX-A: shrinking xwOBA must not DEGRADE the validated
# forward signal (X-H3 rho 0.4543). EB shrink by PA is NOT rank-preserving
# across players with different PA, so this has to be measured, not assumed.
from __future__ import annotations
import os, sys, json, math
from pathlib import Path
import numpy as np
from scipy import stats

ROOT = Path(os.environ.get("EEPHUS_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import mlb_player_export as mpe
import plus_lab_harness as plh
import hem_plus as HP

SEASONS = [2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
MIN_PA = 200.0
RNG = np.random.default_rng(20260725)


def load(y):
    out = {}
    for r in mpe._savant("expected", y, "batter"):
        try:
            out[int(r["player_id"])] = (float(r["woba"]), float(r["est_woba"]), float(r["pa"]))
        except (TypeError, ValueError, KeyError):
            continue
    return out


data = {y: load(y) for y in SEASONS}
rows = []
for y in SEASONS:
    cur, nxt = data.get(y), data.get(y + 1)
    if not cur or not nxt:
        continue
    for mid, (w, x, pa) in cur.items():
        nn = nxt.get(mid)
        if nn and pa >= MIN_PA and nn[2] >= MIN_PA and plh.season_complete(y + 1):
            rows.append({"mid": mid, "y": y, "woba": w, "xwoba": x, "pa": pa, "tgt": nn[0]})
print(f"X-H3 pair set reproduced: n={len(rows)}")

tgt = np.array([r["tgt"] for r in rows])
xw = np.array([r["xwoba"] for r in rows])
wb = np.array([r["woba"] for r in rows])
pa = np.array([r["pa"] for r in rows])
ys = np.array([r["y"] for r in rows])

# pool anchor per predictor season (PA-weighted), same as _join_xhem_plus
anchor = {}
for y in sorted(set(ys)):
    m = ys == y
    anchor[y] = float(np.average(xw[m], weights=pa[m]))
anc = np.array([anchor[y] for y in ys])

print("\n--- FIX-A: EB-shrunk xwOBA (toward the season pool, by Savant PA) ---")
print(f"{'K (PA)':>8}{'fwd rho':>10}{'delta vs raw':>14}{'sd(xHEM+)/sd(HEM+) proxy':>28}")
base = stats.spearmanr(xw, tgt).statistic
print(f"{'raw':>8}{base:>10.4f}{0.0:>14.4f}")
best = None
for K in [50, 100, 150, 200, 300, 500]:
    xs = (pa * xw + K * anc) / (pa + K)
    r = stats.spearmanr(xs, tgt).statistic
    # spread compression the shrink buys, per season
    comp = np.mean([np.std(xs[ys == y]) / np.std(xw[ys == y]) for y in sorted(set(ys))])
    print(f"{K:>8}{r:>10.4f}{r - base:>14.4f}{comp:>28.4f}")

# paired bootstrap on the K that best matches HEM+'s own spread compression
K = 200
xs = (pa * xw + K * anc) / (pa + K)
B = 2000
g = []
for b in range(B):
    i = RNG.integers(0, len(rows), len(rows))
    g.append(stats.spearmanr(xs[i], tgt[i]).statistic - stats.spearmanr(xw[i], tgt[i]).statistic)
g = np.array(g)
print(f"\npaired bootstrap (B={B}) shrunk-xwOBA minus raw-xwOBA forward rho:")
print(f"  obs {stats.spearmanr(xs,tgt).statistic - base:+.4f}  mean {g.mean():+.4f}"
      f"  lo95 {np.percentile(g,2.5):+.4f}  hi95 {np.percentile(g,97.5):+.4f}"
      f"  P(worse)={float((g<0).mean()):.3f}")

# zero-information control: permute the shrink weight across rows
pa_perm = pa[RNG.permutation(len(pa))]
xs_ctrl = (pa_perm * xw + K * anc) / (pa_perm + K)
print(f"  zero-info control (PA column row-permuted): rho "
      f"{stats.spearmanr(xs_ctrl,tgt).statistic:.4f}  "
      f"delta {stats.spearmanr(xs_ctrl,tgt).statistic - base:+.4f}")

print("\n--- FIX-B: Luck = actual wOBA - xwOBA (the pitcher-board definition) ---")
lk = wb - xw
print(f"  n={len(lk)}  mean {lk.mean():+.4f}  sd {lk.std(ddof=1):.4f}  median {np.median(lk):+.4f}")
print(f"  rho(Luck, xwOBA) = {stats.spearmanr(lk,xw).statistic:+.4f}"
      f"   rho(Luck, wOBA) = {stats.spearmanr(lk,wb).statistic:+.4f}")
print("  (a well-formed residual is near-balanced between the two legs; the shipped")
print("   luck_gap reads +0.816 vs xHEM+ and +0.315 vs HEM+ -- see _am_plusmetrics_coh C1)")
# does Luck-as-residual actually forecast the bounce-back it claims?
d_next = tgt - wb
print(f"  rho(Luck_Y, wOBA_Y+1 - wOBA_Y) = {stats.spearmanr(lk, d_next).statistic:+.4f}"
      f"   (positive = 'unlucky hitters bounce back', the claim on the site)")
