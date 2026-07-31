# scratch lab: intlalias -- functional form (offset vs slope) + Option A/B agreement.
import sys, sqlite3, collections
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import grade_normalization as gn
con = sqlite3.connect(str(HERE / "prospects.db")); cur = con.cursor()

def cboot(vals, keys, fn, B=4000, seed=3):
    cl = collections.defaultdict(list)
    for v, k in zip(vals, keys): cl[k].append(v)
    ks = list(cl); rng = np.random.default_rng(seed)
    pt = fn(vals)
    dr = []
    for _ in range(B):
        idx = rng.integers(0, len(ks), len(ks))
        s = [x for i in idx for x in cl[ks[i]]]
        v = fn(s)
        if v is not None and np.isfinite(v): dr.append(v)
    return pt, float(np.percentile(dr, 2.5)), float(np.percentile(dr, 97.5))

# --- same-outlet pairs: intl vs main pipeline ---
q = """SELECT a.player_key, substr(a.snapshot_date,1,4), a.fv, b.fv, a.snapshot_date, b.snapshot_date
       FROM snapshots a JOIN snapshots b ON a.player_key=b.player_key
        AND substr(a.snapshot_date,1,4)=substr(b.snapshot_date,1,4)
       WHERE a.source='mlb_pipeline_international' AND b.source='mlb_pipeline'
         AND a.fv IS NOT NULL AND b.fv IS NOT NULL"""
best = {}
for pk, y, af, bf, ad, bd in cur.execute(q):
    k = (pk, y)
    if k not in best or (ad, bd) > best[k][2]: best[k] = (af, bf, (ad, bd))
P = [(pk, y, af, bf) for (pk, y), (af, bf, _) in best.items()]
X = np.array([p[3] for p in P]); Y = np.array([p[2] for p in P]); K = [p[0] for p in P]
print(f"intl vs main_pipeline, same player/cycle  n={len(P)}")
print(f"  pearson r = {np.corrcoef(X, Y)[0,1]:.4f}   spearman-ish (ties heavy)")
from scipy import stats as st
print(f"  spearman  = {st.spearmanr(X, Y).statistic:.4f}")
sl = lambda v: float(np.polyfit([x[1] for x in v], [x[0] for x in v], 1)[0])
vals = list(zip(Y, X))
pt, lo, hi = cboot(vals, K, sl)
print(f"  OLS slope (intl ~ main) = {pt:.3f} CI95 [{lo:.3f}, {hi:.3f}]   (1.000 => pure offset)")
res = Y - (X + 7.279)
print(f"  residual sd after a pure -7.279 shift = {np.std(res):.3f} FV")

# --- intl vs fangraphs ---
q2 = """SELECT a.player_key, substr(a.snapshot_date,1,4), a.fv, b.fv, a.snapshot_date, b.snapshot_date
        FROM snapshots a JOIN snapshots b ON a.player_key=b.player_key
         AND substr(a.snapshot_date,1,4)=substr(b.snapshot_date,1,4)
        WHERE a.source='mlb_pipeline_international' AND b.source='fangraphs'
          AND a.fv IS NOT NULL AND b.fv IS NOT NULL"""
best2 = {}
for pk, y, af, bf, ad, bd in cur.execute(q2):
    k = (pk, y)
    if k not in best2 or (ad, bd) > best2[k][2]: best2[k] = (af, bf, (ad, bd))
P2 = [(pk, y, af, bf) for (pk, y), (af, bf, _) in best2.items()]
X2 = np.array([p[3] for p in P2]); Y2 = np.array([p[2] for p in P2]); K2 = [p[0] for p in P2]
print(f"\nintl vs fangraphs, same player/cycle  n={len(P2)}")
print(f"  pearson r = {np.corrcoef(X2, Y2)[0,1]:.4f}  spearman = {st.spearmanr(X2, Y2).statistic:.4f}")
pt2, lo2, hi2 = cboot(list(zip(Y2, X2)), K2, sl)
print(f"  OLS slope (intl ~ fg) = {pt2:.3f} CI95 [{lo2:.3f}, {hi2:.3f}]")

# control: main_pipeline vs fangraphs on the SAME players
q3 = """SELECT a.player_key, substr(a.snapshot_date,1,4), a.fv, b.fv
        FROM snapshots a JOIN snapshots b ON a.player_key=b.player_key
         AND substr(a.snapshot_date,1,4)=substr(b.snapshot_date,1,4)
        WHERE a.source='mlb_pipeline' AND b.source='fangraphs'
          AND a.fv IS NOT NULL AND b.fv IS NOT NULL
          AND substr(a.snapshot_date,1,4) >= '2021'"""
d3 = {}
for pk, y, af, bf in cur.execute(q3):
    d3[(pk, y)] = (af, bf)
X3 = np.array([v[1] for v in d3.values()]); Y3 = np.array([v[0] for v in d3.values()])
print(f"\nCONTROL main_pipeline vs fangraphs (2021+) n={len(d3)}: "
      f"pearson r={np.corrcoef(X3,Y3)[0,1]:.4f} spearman={st.spearmanr(X3,Y3).statistic:.4f} "
      f"slope={np.polyfit(X3,Y3,1)[0]:.3f}")

# --- Option A (intl cell vs FG) vs Option B (within-outlet shift then main cell) ---
print("\n--- Option A (reachable intl cell) vs Option B (-7.279 then main cell) ---")
for yr in (2022, 2023, 2024, 2025, 2026):
    s, r, _p = gn._paired_dists("mlb_pipeline_international", "hitter", yr)
    sm, rm, _pm = gn._paired_dists("mlb_pipeline", "hitter", yr)
    if len(s) == 0: continue
    oa = float(np.mean(s) - np.mean(r)); om = float(np.mean(sm) - np.mean(rm))
    print(f"  {yr}: A={-oa:+.3f}  B={-(7.279+om):+.3f}  |A-B|={abs(oa-(7.279+om)):.3f}")
con.close()
