# ADVERSARIAL VERIFY of the plusmetrics lane's "Luck" claim.
# Independent re-derivation. Central suspicion: fix-B luck = xwOBA - wOBA and the
# target dnext = wOBA(Y+1) - wOBA(Y) SHARE the term -wOBA(Y). Mathematical
# coupling. A row-permutation of the predictor destroys the coupling, so the
# lane's permutation null cannot see it.
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
XPA = 100.0
RNG = np.random.default_rng(7717)


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
        rows.append({"y": y, "mid": mid, "w": w, "x": x, "pa": p,
                     "hem": hp, "xhem": xhem,
                     "luck_ship": xhem - hp,
                     "luck_b": x - w,
                     "wnext": nn[0],
                     "dnext": nn[0] - w})

n = len(rows)
print(f"pair set reproduced: n={n}   seasons {sorted(set(r['y'] for r in rows))}")
Y = np.array([r["y"] for r in rows])
W = np.array([r["w"] for r in rows]); X = np.array([r["x"] for r in rows])
LS = np.array([r["luck_ship"] for r in rows]); LB = np.array([r["luck_b"] for r in rows])
DN = np.array([r["dnext"] for r in rows]); WN = np.array([r["wnext"] for r in rows])
HEMv = np.array([r["hem"] for r in rows])

rho = lambda a, b: stats.spearmanr(a, b).statistic

print("\n=== STEP 1: reproduce the lane's headline on ITS target (dnext) ===")
print(f"  shipped luck_gap  rho vs dnext = {rho(LS, DN):+.4f}")
print(f"  fix-B  (x - w)    rho vs dnext = {rho(LB, DN):+.4f}")

print("\n=== STEP 2: THE COUPLING CONTROL the lane did not run ===")
print("  Both predictor and target contain -wOBA(Y). Test degenerate predictors:")
print(f"  MINUS actual wOBA(Y) alone      rho vs dnext = {rho(-W, DN):+.4f}   <- pure regression-to-mean")
print(f"  MINUS shrunk HEM+ core alone    rho vs dnext = {rho(-HEMv, DN):+.4f}")
print(f"  xwOBA(Y) alone (no -w term)     rho vs dnext = {rho(X, DN):+.4f}")

# zero-information twin of the SAME column: permute xwOBA WITHIN season, keep w aligned.
P = 2000
null_b, null_s = [], []
for _ in range(P):
    xp = np.empty_like(X); xhp = np.empty_like(LS)
    for y in np.unique(Y):
        m = Y == y
        idx = RNG.permutation(int(m.sum()))
        xp[m] = X[m][idx]
        xhp[m] = (np.array([r["xhem"] for r in rows])[m])[idx]
    null_b.append(rho(xp - W, DN))
    null_s.append(rho(xhp - HEMv, DN))
null_b = np.array(null_b); null_s = np.array(null_s)
print(f"\n  COUPLING NULL (xwOBA row-permuted within season, wOBA leg kept):")
print(f"    fix-B  pseudo-luck   mean {null_b.mean():+.4f}  p50 {np.percentile(null_b,50):+.4f}"
      f"  p95 {np.percentile(null_b,95):+.4f}  p99 {np.percentile(null_b,99):+.4f}")
print(f"    shipped pseudo-luck  mean {null_s.mean():+.4f}  p50 {np.percentile(null_s,50):+.4f}"
      f"  p95 {np.percentile(null_s,95):+.4f}  p99 {np.percentile(null_s,99):+.4f}")
print(f"    observed fix-B {rho(LB,DN):+.4f}   excess over coupling-null mean ="
      f" {rho(LB,DN)-null_b.mean():+.4f}")
print(f"    observed ship  {rho(LS,DN):+.4f}   excess over coupling-null mean ="
      f" {rho(LS,DN)-null_s.mean():+.4f}")

print("\n=== STEP 3: UNCOUPLED target. Predict wOBA(Y+1) LEVEL, not the delta ===")
print(f"  shipped luck_gap  rho vs wOBA(Y+1) = {rho(LS, WN):+.4f}")
print(f"  fix-B  (x - w)    rho vs wOBA(Y+1) = {rho(LB, WN):+.4f}")
print(f"  wOBA(Y)           rho vs wOBA(Y+1) = {rho(W, WN):+.4f}")
print(f"  xwOBA(Y)          rho vs wOBA(Y+1) = {rho(X, WN):+.4f}")

print("\n=== STEP 4: does 'Luck' add CONDITIONAL info over what is already shown? ===")
print("  Forward-chained OOS: train on seasons < t, test on t. Spearman vs wOBA(Y+1).")


def zs(a):
    s = a.std(ddof=1)
    return (a - a.mean()) / (s if s > 0 else 1.0)


def fit_eval(cols, tr, te):
    A = np.column_stack([zs(c[tr]) for c in cols] + [np.ones(tr.sum())])
    beta, *_ = np.linalg.lstsq(A, WN[tr], rcond=None)
    mu = [c[tr].mean() for c in cols]; sd = [c[tr].std(ddof=1) or 1.0 for c in cols]
    B = np.column_stack([(c[te] - mu[i]) / sd[i] for i, c in enumerate(cols)]
                        + [np.ones(te.sum())])
    return rho(B @ beta, WN[te])


yrs = sorted(set(Y))
folds = [y for y in yrs if (Y < y).sum() >= 150 and (Y == y).sum() >= 60]
models = {
    "M0 wOBA only":            [W],
    "M1 wOBA + xwOBA":         [W, X],
    "M2 wOBA + luck_SHIPPED":  [W, LS],
    "M3 wOBA + luck_FIXB":     [W, LB],
}
res = {k: [] for k in models}
for y in folds:
    tr = Y < y; te = Y == y
    for k, cols in models.items():
        res[k].append(fit_eval(cols, tr, te))
print(f"  folds: {folds}  (train sizes {[int((Y<y).sum()) for y in folds]})")
for k in models:
    print(f"    {k:<24} per-fold {' '.join(f'{v:+.4f}' for v in res[k])}   MEAN {np.mean(res[k]):+.4f}")

print("\n  NOTE: M3 (wOBA + luck_fixB) is a LINEAR REPARAMETRIZATION of M1 (wOBA + xwOBA).")
print("        span{w, x-w} == span{w, x}. Any difference is numerical only.")

print("\n=== STEP 5: paired bootstrap, refit per draw, on the UNCOUPLED target ===")
B = 600
gaps = {"M3-M0 (luck_fixB adds over wOBA)": [], "M2-M0 (luck_shipped adds over wOBA)": [],
        "M3-M2 (fixB vs shipped, both over wOBA)": []}
for _ in range(B):
    per = {k: [] for k in models}
    for y in folds:
        tr_i = np.where(Y < y)[0]; te_i = np.where(Y == y)[0]
        trb = RNG.choice(tr_i, len(tr_i), replace=True)
        teb = RNG.choice(te_i, len(te_i), replace=True)
        trm = np.zeros(n, bool); trm[np.unique(trb)] = True
        # honest resample: build index-based masks via arrays
        for k, cols in models.items():
            A = np.column_stack([zs(c[trb]) for c in cols] + [np.ones(len(trb))])
            beta, *_ = np.linalg.lstsq(A, WN[trb], rcond=None)
            mu = [c[trb].mean() for c in cols]; sd = [c[trb].std(ddof=1) or 1.0 for c in cols]
            Bm = np.column_stack([(c[teb] - mu[i]) / sd[i] for i, c in enumerate(cols)]
                                 + [np.ones(len(teb))])
            per[k].append(rho(Bm @ beta, WN[teb]))
    gaps["M3-M0 (luck_fixB adds over wOBA)"].append(np.mean(per["M3 wOBA + luck_FIXB"]) - np.mean(per["M0 wOBA only"]))
    gaps["M2-M0 (luck_shipped adds over wOBA)"].append(np.mean(per["M2 wOBA + luck_SHIPPED"]) - np.mean(per["M0 wOBA only"]))
    gaps["M3-M2 (fixB vs shipped, both over wOBA)"].append(np.mean(per["M3 wOBA + luck_FIXB"]) - np.mean(per["M2 wOBA + luck_SHIPPED"]))
for k, v in gaps.items():
    v = np.array(v)
    print(f"    {k:<42} obs-mean {v.mean():+.4f}  lo95 {np.percentile(v,2.5):+.4f}"
          f"  hi95 {np.percentile(v,97.5):+.4f}  P(>0)={float((v>0).mean()):.3f}")

print("\n=== STEP 6: is the SHIPPED column a rank-equivalent of fix-B? ===")
print(f"  rho(luck_shipped, luck_fixB) = {rho(LS, LB):+.4f}   (rank agreement of the two columns)")
print(f"  pearson                      = {stats.pearsonr(LS, LB).statistic:+.4f}")
print("\n=== STEP 7: sign/centering claims (correctness, not rank) ===")
print(f"  luck_shipped mean {LS.mean():+.3f}  median {np.median(LS):+.3f}  sd {LS.std(ddof=1):.3f}")
print(f"  luck_fixB    mean {LB.mean():+.4f} median {np.median(LB):+.4f} sd {LB.std(ddof=1):.4f}")
q = np.quantile(HEMv, [1/3, 2/3])
for lab, m in [("bottom HEM+ third", HEMv <= q[0]), ("middle", (HEMv > q[0]) & (HEMv <= q[1])),
               ("top HEM+ third", HEMv > q[1])]:
    print(f"    {lab:<20} mean luck_shipped {LS[m].mean():+7.2f}   mean luck_fixB {LB[m].mean():+.4f}   n={int(m.sum())}")
