"""REVIEW LAB: reweight the odds lane's reliability gain from the FIT-FRAME p-distribution
to the SERVED board p-distribution. Tests external validity of the claimed win."""
import json, math

BINS = [
 ("0.00-0.09", 64, 0.0356, 0.2656, 0.00, 0.09),
 ("0.09-0.22", 65, 0.1445, 0.5077, 0.09, 0.22),
 ("0.22-0.38", 64, 0.3065, 0.6094, 0.22, 0.38),
 ("0.38-0.50", 65, 0.4411, 0.7077, 0.38, 0.50),
 ("0.50-0.74", 64, 0.6261, 0.7969, 0.50, 0.74),
 ("0.75-0.95", 65, 0.8677, 0.8615, 0.74, 0.955),
 ("0.96-0.98", 64, 0.9818, 0.8438, 0.955, 0.982),
 ("0.98-0.99", 65, 0.9867, 0.8615, 0.982, 1.01),
]
A, B = 0.7204, 0.3671   # global Platt from the eval artifact

def logit(p):
    p = min(max(p, 1e-9), 1-1e-9); return math.log(p/(1-p))
def inv(z): return 1.0/(1.0+math.exp(-z))
def recal(p): return inv(A + B*logit(p))

x = json.load(open('data/xfv.json'))['by_player']
ps = [r['p_bust'] for r in x.values() if r.get('p_bust') is not None]
N = len(ps)

print("bin           n_fit  w_fit  w_board   p_inc   p_recal   obs   redBrier_inc  redBrier_rec   gain")
rows = []
tot_fit = sum(b[1] for b in BINS)
for name, n, pinc, obs, lo, hi in BINS:
    nb = sum(1 for p in ps if lo <= p < hi)
    w_fit = n/tot_fit
    w_bd  = nb/N
    pr = recal(pinc)
    r_i = (pinc-obs)**2
    r_r = (pr-obs)**2
    rows.append((name, w_fit, w_bd, pinc, pr, obs, r_i, r_r, r_i-r_r, nb))
    print(f"{name:12s} {n:5d} {w_fit:6.3f} {w_bd:7.3f}  {pinc:6.4f}  {pr:6.4f}  {obs:5.3f}   "
          f"{r_i:10.5f}   {r_r:10.5f}  {r_i-r_r:+8.5f}")

g_fit = sum(r[1]*r[8] for r in rows)
g_bd  = sum(r[2]*r[8] for r in rows)
w_bd_tot = sum(r[2] for r in rows)
g_bd_n = sum(r[2]*r[8] for r in rows)/w_bd_tot if w_bd_tot else float('nan')
print()
print(f"FIT-FRAME weighted reducible-Brier gain   : {g_fit:+.5f}")
print(f"BOARD-weighted   reducible-Brier gain     : {g_bd_n:+.5f}   (board mass covered {w_bd_tot:.3f})")
print(f"ratio board/fit                            : {g_bd_n/g_fit:.3f}")
print()
print("BOARD MASS BY BIN (share of %d rows with p_bust):" % N)
for r in rows:
    print(f"  {r[0]:12s} board n={r[9]:5d}  share {r[2]:.4f}   fit share {r[1]:.4f}")
print()
top = sum(1 for p in ps if p >= 0.955)
print(f"board share p>=0.955: {top/N:.4f} ({top})   fit-frame share: {129/tot_fit:.4f} (129)")
print(f"EVIDENCE BASE for the DOWNWARD move applied to {top} board rows = {129} test rows")
