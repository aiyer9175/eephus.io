# Scratch lab (audit-mode, lane=plusmetrics).
# Does the SHIPPED hitter Luck column (luck_gap = xHEM+ - HEM+) rank bounce-back
# worse than the units-honest residual (xwOBA - actual wOBA)?
# Forward-chained over the X-H3 pair seasons, paired bootstrap + permutation null.
from __future__ import annotations
import os, sys
from pathlib import Path
import numpy as np
from scipy import stats

ROOT = Path(os.environ.get("EEPHUS_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import mlb_player_export as mpe
import plus_lab_harness as plh
import hem_plus as HP
import hitter_export as he

SEASONS = [2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
MIN_PA = 200.0
XPA = 100.0                      # the shipped _XHEM_MIN_PA gate
RNG = np.random.default_rng(20260725)


def savant(y):
    out = {}
    for r in mpe._savant("expected", y, "batter"):
        try:
            out[int(r["player_id"])] = (float(r["woba"]), float(r["est_woba"]), float(r["pa"]))
        except (TypeError, ValueError, KeyError):
            continue
    return out


def hem_core(y):
    rows = he.load_season_hitting(y)
    if not rows:
        return {}
    hs = he.build_hitters(rows)
    pool_input = [h for h in hs if HP._woba_denom(h) > 0]
    for h in pool_input:
        HP.derive_rates(h)
    pool = HP.build_pool(pool_input)
    out = {}
    for h in pool_input:
        HP.hem_plus(h, pool)
        if h.hem_plus_raw is not None and h.mlbam is not None:
            out[int(h.mlbam)] = h.hem_plus_raw
    return out


sav = {y: savant(y) for y in SEASONS}
hem = {y: hem_core(y) for y in SEASONS}

rows = []
for y in SEASONS:
    cur, nxt = sav.get(y), sav.get(y + 1)
    hc = hem.get(y) or {}
    if not cur or not nxt or not hc:
        continue
    # reproduce the SHIPPED xHEM+ anchor: PA-weighted mean xwOBA over Savant PA>=100
    elig = {m: v for m, v in cur.items() if v[2] >= XPA and v[1] > 0}
    dtot = sum(v[2] for v in elig.values())
    anchor = sum(v[1] * v[2] for v in elig.values()) / dtot
    for mid, (w, x, p) in cur.items():
        nn = nxt.get(mid)
        if not (nn and p >= MIN_PA and nn[2] >= MIN_PA and plh.season_complete(y + 1)):
            continue
        hp = hc.get(mid)
        if hp is None:
            continue
        xhem = 100.0 + HP.HEM_SPREAD_GAIN * (100.0 * x / anchor - 100.0)
        rows.append({"y": y, "mid": mid, "woba": w, "xwoba": x,
                     "hem": hp, "xhem": xhem,
                     "luck_shipped": xhem - hp,          # the served column, unrounded
                     "luck_fixb": x - w,                 # xwOBA - actual, wOBA units
                     "dnext": nn[0] - w})                # bounce-back the column claims

print(f"pairs with a HEM core joined: n={len(rows)}")
ls = np.array([r["luck_shipped"] for r in rows])
lb = np.array([r["luck_fixb"] for r in rows])
dn = np.array([r["dnext"] for r in rows])
ys = np.array([r["y"] for r in rows])
xh = np.array([r["xhem"] for r in rows]); hh = np.array([r["hem"] for r in rows])

print(f"\nshipped luck_gap : mean {ls.mean():+7.3f}  sd {ls.std(ddof=1):6.3f}"
      f"  rho w/ xHEM+ {stats.spearmanr(ls,xh).statistic:+.4f}"
      f"  rho w/ HEM+ {stats.spearmanr(ls,hh).statistic:+.4f}")
print(f"FIX-B  (xwOBA-wOBA): mean {lb.mean():+7.4f} sd {lb.std(ddof=1):6.4f}"
      f"  rho w/ xwOBA {stats.spearmanr(lb,np.array([r['xwoba'] for r in rows])).statistic:+.4f}"
      f"  rho w/ wOBA {stats.spearmanr(lb,np.array([r['woba'] for r in rows])).statistic:+.4f}")

print("\n--- ranking the bounce-back it advertises: rho(Luck_Y, wOBA_Y+1 - wOBA_Y) ---")
r_s = stats.spearmanr(ls, dn).statistic
r_b = stats.spearmanr(lb, dn).statistic
print(f"  shipped luck_gap : {r_s:+.4f}")
print(f"  FIX-B residual   : {r_b:+.4f}")
print("\n  per predictor season (>=4 independent time splits):")
per_s, per_b = [], []
for y in sorted(set(ys)):
    m = ys == y
    if m.sum() < 60:
        continue
    a = stats.spearmanr(ls[m], dn[m]).statistic
    b = stats.spearmanr(lb[m], dn[m]).statistic
    per_s.append(a); per_b.append(b)
    print(f"    {y}  n={m.sum():4d}   shipped {a:+.4f}   fix-B {b:+.4f}   gap {b-a:+.4f}")
print(f"    MEAN over {len(per_s)} splits: shipped {np.mean(per_s):+.4f}"
      f"  fix-B {np.mean(per_b):+.4f}  gap {np.mean(per_b)-np.mean(per_s):+.4f}")

B = 2000
g = []
for _ in range(B):
    i = RNG.integers(0, len(rows), len(rows))
    g.append(stats.spearmanr(lb[i], dn[i]).statistic - stats.spearmanr(ls[i], dn[i]).statistic)
g = np.array(g)
print(f"\n  paired bootstrap B={B}: gap mean {g.mean():+.4f}"
      f"  lo95 {np.percentile(g,2.5):+.4f}  hi95 {np.percentile(g,97.5):+.4f}"
      f"  P(fix-B better)={float((g>0).mean()):.3f}")

P = 2000
null = []
for _ in range(P):
    perm = RNG.permutation(len(rows))
    null.append(stats.spearmanr(lb[perm], dn).statistic)
null = np.abs(np.array(null))
print(f"  permutation null band |rho|: p50 {np.percentile(null,50):.4f}"
      f"  p95 {np.percentile(null,95):.4f}  p99 {np.percentile(null,99):.4f}"
      f"   -> MDE95 = {np.percentile(null,95):.4f}")
