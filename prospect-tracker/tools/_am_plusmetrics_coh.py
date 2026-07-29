# Scratch lab (audit-mode, lane=plusmetrics). Coherence checks.
from __future__ import annotations
import json, os
import numpy as np
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
load = lambda f: json.load(open(os.path.join(D, f), encoding="utf-8"))
A = lambda rows, k: np.array([np.nan if r.get(k) is None else float(r[k]) for r in rows])


def sect(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


# ---------------- C1: hitter luck_gap scale coherence -----------------------
sect("C1  hitter luck_gap = xHEM+ - HEM+  (docstring: 'ONE ruler')")
h = load("hitter_leaderboards.json")["hitters"]
sub = [r for r in h if r.get("xhem_plus") is not None and r.get("hem_plus") is not None]
xh, hp = A(sub, "xhem_plus"), A(sub, "hem_plus")
lg = A(sub, "luck_gap")
print(f"n={len(sub)}")
print(f"  HEM+   mean {hp.mean():7.2f}  sd {hp.std(ddof=1):6.2f}  IQR {np.percentile(hp,75)-np.percentile(hp,25):.1f}")
print(f"  xHEM+  mean {xh.mean():7.2f}  sd {xh.std(ddof=1):6.2f}  IQR {np.percentile(xh,75)-np.percentile(xh,25):.1f}")
print(f"  sd ratio xHEM+/HEM+ = {xh.std(ddof=1)/hp.std(ddof=1):.3f}   (1.000 == one ruler)")
print(f"  luck_gap mean {lg.mean():+.2f}  sd {lg.std(ddof=1):.2f}  median {np.median(lg):+.1f}")
print(f"  corr(luck_gap, xHEM+) = {stats.spearmanr(lg,xh).statistic:+.4f}")
print(f"  corr(luck_gap, HEM+)  = {stats.spearmanr(lg,hp).statistic:+.4f}")
# what a scale-matched residual would look like: regress xh on hp, take residual
b, a = np.polyfit(hp, xh, 1)
res = xh - (a + b * hp)
print(f"  OLS xHEM+ = {a:.2f} + {b:.4f}*HEM+   (slope 1.000 == one ruler)")
print(f"  scale-matched residual: corr w/ xHEM+ {stats.spearmanr(res,xh).statistic:+.4f}"
      f"  corr w/ HEM+ {stats.spearmanr(res,hp).statistic:+.4f}")
# how many players change SIGN of 'luck' under the scale-matched residual
flip = int(np.sum(np.sign(lg) != np.sign(res)))
print(f"  players whose LUCK SIGN flips under a scale-matched residual: {flip}/{len(sub)}"
      f" ({100.0*flip/len(sub):.1f}%)")
# extreme-HEM bias: mean luck_gap by HEM+ tercile
q = np.quantile(hp, [1/3, 2/3])
for lab, m in [("bottom HEM+ third", hp <= q[0]), ("middle", (hp > q[0]) & (hp <= q[1])),
               ("top HEM+ third", hp > q[1])]:
    print(f"    {lab:<20} mean luck_gap {lg[m].mean():+7.2f}   n={m.sum()}")

# ---------------- C2: exact-monotone (display parent) redundancy ------------
sect("C2  is each '+' an EXACT monotone map of a column shown beside it?")
for f, key, pairs in [
    ("hitter_leaderboards.json", "hitters",
     [("hem_plus_raw", "woba"), ("xhem_plus", "xwoba")]),
    ("starter_leaderboards.json", "starters", [("sem_plus_raw", "fip")]),
    ("bullpen_leaderboards.json", "relievers",
     [("rem_plus_raw", "fip"), ("xrem_plus", "xwoba_against"),
      ("riv_plus_raw", "wpa")]),
]:
    rows = load(f)[key]
    for a_, b_ in pairs:
        x, y = A(rows, a_), A(rows, b_)
        m = ~(np.isnan(x) | np.isnan(y))
        if m.sum() < 5:
            print(f"  {a_:<16} vs {b_:<16} n<5 UNAVAILABLE"); continue
        r = stats.spearmanr(x[m], y[m]).statistic
        print(f"  {a_:<16} vs {b_:<16} rho={r:+.6f}  n={m.sum()}")

# ---------------- C3: scale-family coherence --------------------------------
sect("C3  what scale is each '+' actually on?")
import sys
sys.path.insert(0, ROOT)
import hem_plus as HP, rem_plus as RP
print(f"  HEM+  = 100 + {HP.HEM_SPREAD_GAIN} * (100*wOBA_skill/pool - 100)   RATIO x gain")
print(f"  xHEM+ = 100 + {HP.HEM_SPREAD_GAIN} * (100*xwOBA/pool - 100)        RATIO x gain")
print(f"  REM+  = 100 * poolFIP/FIP                                     RATIO, gain 1.0")
print(f"  SEM+  = 100 * poolFIP/FIP                                     RATIO, gain 1.0")
print(f"  xREM+/xSEM+ = 100 * pool_xwOBA/player_xwOBA                   RATIO, gain 1.0")
print(f"  RIV+  = 100 + {RP.RIV_SCALE} * z                                       Z-SCORE")
print(f"  KRP+  = 100 + 10 * z                                          Z-SCORE")
for f, key, k in [("hitter_leaderboards.json", "hitters", "hem_plus"),
                  ("starter_leaderboards.json", "starters", "sem_plus"),
                  ("bullpen_leaderboards.json", "relievers", "rem_plus"),
                  ("bullpen_leaderboards.json", "relievers", "riv_plus"),
                  ("hitter_leaderboards.json", "hitters", "xhem_plus"),
                  ("starter_leaderboards.json", "starters", "xsem_plus"),
                  ("bullpen_leaderboards.json", "relievers", "xrem_plus")]:
    rows = [r for r in load(f)[key] if r.get("qualified")]
    v = A(rows, k); v = v[~np.isnan(v)]
    if len(v) < 5:
        continue
    print(f"    {k:<12} qualified n={len(v):<4} mean {v.mean():7.2f}  sd {v.std(ddof=1):6.2f}"
          f"  p10 {np.percentile(v,10):6.1f}  p90 {np.percentile(v,90):6.1f}")

# ---------------- C4: does the pool average score exactly 100? --------------
sect("C4  anchor check: does each pool average score 100 as documented?")
for f, key, k, w in [("hitter_leaderboards.json", "hitters", "hem_plus", "pa"),
                     ("starter_leaderboards.json", "starters", "sem_plus", "ip"),
                     ("bullpen_leaderboards.json", "relievers", "rem_plus", "ip")]:
    rows = load(f)[key]
    v, ww = A(rows, k), A(rows, w)
    m = ~(np.isnan(v) | np.isnan(ww))
    print(f"  {k:<10} ALL rows n={m.sum():<4} unweighted mean {v[m].mean():7.2f}"
          f"   {w}-weighted {np.average(v[m], weights=ww[m]):7.2f}")
    rows2 = [r for r in rows if r.get("qualified")]
    v2, w2 = A(rows2, k), A(rows2, w)
    m2 = ~(np.isnan(v2) | np.isnan(w2))
    print(f"  {' ':<10} QUALIFIED n={m2.sum():<4} unweighted mean {v2[m2].mean():7.2f}"
          f"   {w}-weighted {np.average(v2[m2], weights=w2[m2]):7.2f}")
