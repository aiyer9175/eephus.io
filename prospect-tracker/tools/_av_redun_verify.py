# ADVERSARIAL VERIFY, part 2: served-board arithmetic (C1) + the redundancy /
# suppressor question (brief item d).
from __future__ import annotations
import json, os
import numpy as np
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
load = lambda f: json.load(open(os.path.join(D, f), encoding="utf-8"))
A = lambda rows, k: np.array([np.nan if r.get(k) is None else float(r[k]) for r in rows])
rho = lambda a, b: stats.spearmanr(a, b).statistic

print("=== C1 served-board arithmetic, independently recomputed ===")
h = load("hitter_leaderboards.json")["hitters"]
sub = [r for r in h if r.get("xhem_plus") is not None and r.get("hem_plus") is not None]
xh, hp, lg = A(sub, "xhem_plus"), A(sub, "hem_plus"), A(sub, "luck_gap")
print(f"  n={len(sub)}")
print(f"  identity check: max |luck_gap - (xhem-hem)| = {np.nanmax(np.abs(lg-(xh-hp))):.6f}")
print(f"  HEM+ sd {hp.std(ddof=1):.2f}   xHEM+ sd {xh.std(ddof=1):.2f}   ratio {xh.std(ddof=1)/hp.std(ddof=1):.3f}")
b, a = np.polyfit(hp, xh, 1)
print(f"  OLS xHEM+ = {a:.2f} + {b:.4f}*HEM+")
print(f"  luck_gap mean {lg.mean():+.2f} median {np.median(lg):+.1f}")
print(f"  rho(lg,xHEM+) {rho(lg,xh):+.4f}   rho(lg,HEM+) {rho(lg,hp):+.4f}")
q = np.quantile(hp, [1/3, 2/3])
for lab, m in [("bottom", hp <= q[0]), ("middle", (hp > q[0]) & (hp <= q[1])), ("top", hp > q[1])]:
    print(f"    {lab:<7} HEM+ third mean luck_gap {lg[m].mean():+7.2f}  n={int(m.sum())}")

# does the served board carry the raw legs needed for the fix?
print("\n  served-board leg availability for fix-B:")
for k in ("woba", "xwoba", "hem_plus_raw"):
    v = A(sub, k)
    print(f"    {k:<14} non-null {int((~np.isnan(v)).sum())}/{len(sub)}")
w_, x_ = A(sub, "woba"), A(sub, "xwoba")
mm = ~(np.isnan(w_) | np.isnan(x_))
fb = x_[mm] - w_[mm]
print(f"    fix-B on served board: mean {fb.mean():+.4f} median {np.median(fb):+.4f} sd {fb.std(ddof=1):.4f}")
print(f"    rho(fix-B, served luck_gap) = {rho(fb, lg[mm]):+.4f}")

print("\n=== Class-1 monotone-alias claims, recomputed ===")
for f, key, pairs in [
    ("hitter_leaderboards.json", "hitters", [("hem_plus_raw", "woba"), ("xhem_plus", "xwoba")]),
    ("starter_leaderboards.json", "starters", [("sem_plus_raw", "fip"), ("xsem_plus", "xwoba_against")]),
    ("bullpen_leaderboards.json", "relievers",
     [("rem_plus_raw", "fip"), ("xrem_plus", "xwoba_against"), ("riv_plus_raw", "wpa")]),
]:
    rows = load(f)[key]
    for a_, b_ in pairs:
        x, y = A(rows, a_), A(rows, b_)
        m = ~(np.isnan(x) | np.isnan(y))
        if m.sum() < 5:
            print(f"  {a_:<16} vs {b_:<16} UNAVAILABLE"); continue
        print(f"  {a_:<16} vs {b_:<16} rho={rho(x[m],y[m]):+.6f}  n={int(m.sum())}")

print("\n=== Class-2: fwdHEM+ vs xHEM+ -- MERGE or SUPPRESSOR? ===")
fw = A(sub, "fwdhem_plus")
m = ~(np.isnan(fw) | np.isnan(xh) | np.isnan(hp))
print(f"  n={int(m.sum())}  rho(fwdHEM+, xHEM+) = {rho(fw[m],xh[m]):+.4f}"
      f"   rho(fwdHEM+, HEM+) = {rho(fw[m],hp[m]):+.4f}")
# span argument: fwd is a linear blend of z(xwoba) and z(hem core).
# so span{fwd, xhem} == span{xhem, hem}. Check by OLS reconstruction.
Amat = np.column_stack([xh[m], hp[m], np.ones(int(m.sum()))])
beta, res, *_ = np.linalg.lstsq(Amat, fw[m], rcond=None)
pred = Amat @ beta
print(f"  fwdHEM+ reconstructed from (xHEM+, HEM+): R2 = "
      f"{1 - np.sum((fw[m]-pred)**2)/np.sum((fw[m]-fw[m].mean())**2):.6f}")
print(f"    coefs xHEM+ {beta[0]:+.4f}  HEM+ {beta[1]:+.4f}  const {beta[2]:+.2f}")
print("  => fwdHEM+ is an EXACT linear combination of the two columns already displayed.")
print("     Dropping xHEM+ while keeping fwdHEM+ AND HEM+ preserves the span (no info lost).")
print("     Dropping xHEM+ while keeping ONLY fwdHEM+ would collapse a 2-dim span to 1-dim.")

print("\n=== Class-3: level_plus_pct alias, recomputed on served prospx ===")
try:
    pj = load("prospx_players.json")
    plist = pj if isinstance(pj, list) else pj.get("players", pj.get("rows", []))
except Exception as e:
    plist = []
    print(f"  prospx load failed: {e}")
if plist:
    lp = A(plist, "level_plus_pct"); op = A(plist, "ops_plus_level"); er = A(plist, "era_minus_level")
    m1 = ~(np.isnan(lp) | np.isnan(op))
    m2 = ~(np.isnan(lp) | np.isnan(er))
    if m1.sum() > 5:
        print(f"  level_plus_pct vs ops_plus_level   rho {rho(lp[m1],op[m1]):+.6f} n={int(m1.sum())}"
              f"  max|lp-(op-100)| = {np.nanmax(np.abs(lp[m1]-(op[m1]-100))):.4f}")
    if m2.sum() > 5:
        print(f"  level_plus_pct vs era_minus_level  rho {rho(lp[m2],er[m2]):+.6f} n={int(m2.sum())}"
              f"  max|lp-(100-er)| = {np.nanmax(np.abs(lp[m2]-(100-er[m2]))):.4f}")
