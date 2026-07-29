# SCRATCH -- ADVERSARIAL REPLICATION LANE. Read-only w.r.t. shipped code.
# Independent re-implementation of the "recommended evaluator" (does NOT import any
# _frontier_* module) used to answer: are the lanes' NULLs honest, or false negatives
# from a broken/insensitive test?
#
#   train = full pool minus bust_recent, decision_year < Y, KM sample weights
#   test  = debuted rows, decision_year == Y
#   fit   = OLS(WAR~fv) + weighted ridge (seeded alpha holdout) + linear calibration
#   score = (1-lam)*max(0,cons) + lam*max(-2, a + b*ridge)
#   metric= (side x origin) percentile-block-normalized pooled Spearman
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_model as E                                       # noqa: E402  read-only
from prospect_path import _ALPHAS, _RIDGE_HOLDOUT_SEED      # noqa: E402

OUT = ROOT / "tools" / "_frontier_out"
OUT.mkdir(exist_ok=True)

ORIGINS = (2020, 2021, 2022, 2023, 2024)
SEED = 771113
LAM_LIVE = {"hit": 0.85, "pit": 0.54}
LAM_LANE = {"hit": 0.85, "pit": 0.63}     # what 3 sibling lanes pinned


# ------------------------------------------------------------------ data
def load(side, lam_map, seed=SEED):
    fn = "xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json"
    raw = json.loads((ROOT / "data" / fn).read_text(encoding="utf-8"))
    prep = E._prep(raw, "target_censored", side)
    keys = list(E._feature_spec(side)[0])
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], float)
    y = np.array([r["target"] for r in prep], float)
    w = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None)
    fv = np.array([r["fv"] for r in prep], float)
    dy = np.array([r["decision_year"] for r in prep], int)
    deb = np.array([r["kind"] == "debuted" for r in prep])
    keep = np.array([not (r["kind"] == "bust" and o.get("bust_recent"))
                     for r, o in zip(prep, raw)])
    return dict(side=side, X=X, y=y, w=w, fv=fv, dy=dy, deb=deb, keep=keep,
                keys=keys, lam=lam_map[side], n=len(y))


# ------------------------------------------------------------------ primitives
def _rank(v):
    v = np.asarray(v, float)
    o = v.argsort(kind="mergesort")
    r = np.empty(len(v), float)
    r[o] = np.arange(1, len(v) + 1, dtype=float)
    s = v[o]
    i, n = 0, len(s)
    while i < n:
        j = i
        while j + 1 < n and s[j + 1] == s[i]:
            j += 1
        if j > i:
            r[o[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def spear(p, t):
    rp, rt = _rank(p) - 0.0, _rank(t) - 0.0
    rp = rp - rp.mean()
    rt = rt - rt.mean()
    d = math.sqrt(float((rp * rp).sum()) * float((rt * rt).sum()))
    return float((rp * rt).sum() / d) if d > 0 else float("nan")


def ridge(X, y, w, rseed, alphas=None):
    n = len(y)
    if n < 40:
        return None
    k = X.shape[1]
    mu, sd = X.mean(0), X.std(0)
    sd = np.where(sd == 0, 1.0, sd)
    Z = (X - mu) / sd
    alphas = _ALPHAS if alphas is None else alphas

    def wm(ix):
        ww = w[ix]
        return float(np.average(y[ix], weights=ww)) if ww.sum() > 0 else float(y[ix].mean())

    def wr(ix, a, b):
        Zi, wi = Z[ix], w[ix]
        WX = Zi * wi[:, None]
        return np.linalg.solve(WX.T @ Zi + a * np.eye(k), WX.T @ (y[ix] - b))

    order = np.random.default_rng(rseed).permutation(n)
    kk = max(1, n // 5)
    ho, tri = order[:kk], order[kk:]
    b_tr = wm(tri)
    best = None
    for a in alphas:
        pr = Z[ho] @ wr(tri, a, b_tr) + b_tr
        mae = (float(np.average(np.abs(pr - y[ho]), weights=w[ho]))
               if w[ho].sum() > 0 else float(np.abs(pr - y[ho]).mean()))
        if best is None or mae < best[0]:
            best = (mae, a)
    a = best[1]
    b = wm(np.arange(n))
    return (mu, sd, wr(np.arange(n), a, b), b, a)


def rpred(m, X):
    mu, sd, ww, b, _ = m
    return ((X - mu) / sd) @ ww + b


def ols(x, y):
    if len(y) < 8:
        return None
    mx, my = x.mean(), y.mean()
    v = float(((x - mx) ** 2).sum())
    if v <= 0:
        return None
    b = float(((x - mx) * (y - my)).sum()) / v
    return (my - b * mx, b)


def score_side(D, Xuse, sel=None, origins=ORIGINS, lam=None, rseed=None,
               train_frame="full", cal=True, alphas=None, mono=None):
    y, w, fv, dy, deb, keep = D["y"], D["w"], D["fv"], D["dy"], D["deb"], D["keep"]
    if sel is None:
        sel = np.arange(len(y))
    Xs, ys, ws, fvs, dys = Xuse[sel], y[sel], w[sel], fv[sel], dy[sel]
    debs, keeps = deb[sel], keep[sel]
    lam = D["lam"] if lam is None else lam
    rseed = _RIDGE_HOLDOUT_SEED if rseed is None else rseed
    trm = keeps if train_frame == "full" else debs
    B, P, T = [], [], []
    for yr in origins:
        tr = np.flatnonzero(trm & (dys < yr))
        te = np.flatnonzero(debs & (dys == yr))
        if len(te) < 15 or len(tr) < 60:
            continue
        o = ols(fvs[tr], ys[tr])
        rg = ridge(Xs[tr], ys[tr], ws[tr], rseed, alphas)
        if o is None or rg is None:
            continue
        if cal:
            c = ols(rpred(rg, Xs[tr]), ys[tr])
            a0, b0 = (0.0, 1.0) if c is None else (round(c[0], 4), round(c[1], 4))
            mod = np.maximum(-2.0, a0 + b0 * rpred(rg, Xs[te]))
        else:
            mod = rpred(rg, Xs[te])
        cons = np.maximum(0.0, o[0] + o[1] * fvs[te])
        B.append(np.full(len(te), yr))
        P.append((1 - lam) * cons + lam * mod)
        T.append(ys[te])
    if not P:
        return None
    return np.concatenate(B), np.concatenate(P), np.concatenate(T)


def blockrho(parts):
    PP, TT = [], []
    for b, p, t in parts:
        for yr in np.unique(b):
            m = b == yr
            if m.sum() < 8:
                continue
            n = int(m.sum())
            PP.append((_rank(p[m]) - 0.5) / n)
            TT.append((_rank(t[m]) - 0.5) / n)
    return spear(np.concatenate(PP), np.concatenate(TT))


def both(Ds, Xmap, sel=None, **kw):
    parts = []
    for s in ("hit", "pit"):
        r = score_side(Ds[s], Xmap[s], None if sel is None else sel[s], **kw)
        if r:
            parts.append(r)
    return blockrho(parts)


# ------------------------------------------------------------------ injected signal
def inject(D, c, rng):
    """Feature with a KNOWN, generalizable correlation to the target:
       x = c*z(rank(y)) + sqrt(1-c^2)*noise.  c=0 -> pure zero-information control."""
    z = _rank(D["y"])
    z = (z - z.mean()) / z.std()
    e = rng.standard_normal(D["n"])
    e = (e - e.mean()) / e.std()
    return c * z + math.sqrt(max(0.0, 1 - c * c)) * e


# ------------------------------------------------------------------ modes
def mode_base():
    print("=== A. INDEPENDENT BASELINE (my code, never imports a _frontier_* module) ===")
    for name, lm in (("live lam (hit .85/pit .54)", LAM_LIVE),
                     ("lane lam (hit .85/pit .63)", LAM_LANE)):
        Ds = {s: load(s, lm) for s in ("hit", "pit")}
        Xm = {s: Ds[s]["X"] for s in ("hit", "pit")}
        parts, ns = [], {}
        for s in ("hit", "pit"):
            r = score_side(Ds[s], Xm[s])
            parts.append(r)
            ns[s] = len(r[2])
        print(f"  {name}: block_rho={blockrho(parts):.5f}  n_hit={ns['hit']} n_pit={ns['pit']} "
              f"n={ns['hit']+ns['pit']}  | hit-only {blockrho(parts[:1]):.5f} "
              f"pit-only {blockrho(parts[1:]):.5f}")
    # gate-config parity (debuted train, no calibration, 2020-2023)
    print("  -- gate-config parity vs shipped efv_model._run_eval --")
    for s in ("hit", "pit"):
        D = load(s, LAM_LIVE)
        r = score_side(D, D["X"], origins=(2020, 2021, 2022, 2023),
                       train_frame="debuted", cal=False)
        keys, mono = E._feature_spec(s)
        raw = json.loads((ROOT / "data" / ("xfv_pitcher_matrix.json" if s == "pit"
                                           else "xfv_hitter_matrix.json")).read_text("utf-8"))
        data = E._prep([x for x in raw if x["kind"] == "debuted"], "target_censored", s)
        ship = E._run_eval(data, "debuted_km", keys, mono, E.blend_lambda(s))["pooled_oos"]
        print(f"    {s}: mine rho={spear(r[1], r[2]):.4f} n={len(r[2])} | shipped blend "
              f"{ship['blend']['spearman']} n={ship['blend']['n']} | shipped baseline "
              f"{ship['baseline']['spearman']}")


def mode_ctrl():
    """B. Zero-information + rank-identical controls under MY evaluator."""
    print("=== B. CONTROLS ===")
    Ds = {s: load(s, LAM_LIVE) for s in ("hit", "pit")}
    base = both(Ds, {s: Ds[s]["X"] for s in ("hit", "pit")})
    print(f"  baseline block_rho {base:.6f}")
    # rank-identical: monotone affine rescale of the FV column -> must move nothing? (it does
    # move the fit) ; the true rank-identical control is a monotone map of the FINAL score,
    # tested separately below.
    rng = np.random.default_rng(SEED)
    ds = []
    for i in range(30):
        Xm = {}
        for s in ("hit", "pit"):
            nz = rng.standard_normal(Ds[s]["n"])
            Xm[s] = np.column_stack([Ds[s]["X"], nz])
        ds.append(both(Ds, Xm) - base)
    ds = np.array(ds)
    print(f"  ZERO-INFO added column (k=1, 30 draws): mean {ds.mean():+.5f} sd {ds.std(ddof=1):.5f} "
          f"p95|d| {np.percentile(np.abs(ds),95):.5f} max|d| {np.abs(ds).max():.5f}")
    # permuted-twin control: append a row-permuted copy of the fv column
    ds2 = []
    for i in range(30):
        Xm = {}
        for s in ("hit", "pit"):
            p = rng.permutation(Ds[s]["n"])
            Xm[s] = np.column_stack([Ds[s]["X"], Ds[s]["X"][p, 0]])
        ds2.append(both(Ds, Xm) - base)
    ds2 = np.array(ds2)
    print(f"  PERMUTED-TWIN of fv   (k=1, 30 draws): mean {ds2.mean():+.5f} sd {ds2.std(ddof=1):.5f} "
          f"max|d| {np.abs(ds2).max():.5f}")
    json.dump({"base": base, "noise": ds.tolist(), "twin": ds2.tolist()},
              open(OUT / "_advers_ctrl.json", "w"))


def mode_power():
    """C. POSITIVE CONTROL / POWER CURVE: inject a feature of KNOWN signal strength and
    find the smallest true effect this evaluator actually resolves."""
    print("=== C. INJECTED-SIGNAL POWER CURVE (does the test see real effects?) ===")
    Ds = {s: load(s, LAM_LIVE) for s in ("hit", "pit")}
    base = both(Ds, {s: Ds[s]["X"] for s in ("hit", "pit")})
    print(f"  baseline block_rho {base:.6f}")
    rows = []
    for c in (0.0, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50):
        vals = []
        for rep in range(12):
            rng = np.random.default_rng(SEED + 1000 * rep + int(c * 1000))
            Xm = {s: np.column_stack([Ds[s]["X"], inject(Ds[s], c, rng)])
                  for s in ("hit", "pit")}
            vals.append(both(Ds, Xm) - base)
        v = np.array(vals)
        rows.append((c, v.mean(), v.std(ddof=1), v.min(), v.max()))
        print(f"  c={c:.2f}  d_mean {v.mean():+.5f}  sd {v.std(ddof=1):.5f} "
              f"[{v.min():+.5f},{v.max():+.5f}]  (12 reps)")
    json.dump({"base": base, "rows": rows}, open(OUT / "_advers_power.json", "w"))


def mode_boot():
    """D. Paired refit bootstrap on (i) a zero-info arm, (ii) an injected arm sized near
    the claimed MDE, (iii) the drop-fv positive control. Independent sd estimate."""
    B = int(sys.argv[2]) if len(sys.argv) > 2 else 250
    print(f"=== D. PAIRED REFIT BOOTSTRAP (B={B}), resample TRAIN+TEST within (side,year) ===")
    Ds = {s: load(s, LAM_LIVE) for s in ("hit", "pit")}
    rng0 = np.random.default_rng(SEED)
    inj = {s: inject(Ds[s], 0.10, np.random.default_rng(SEED + 5)) for s in ("hit", "pit")}
    nz = {s: np.random.default_rng(SEED + 9).standard_normal(Ds[s]["n"]) for s in ("hit", "pit")}

    def arms(sel):
        Xb = {s: Ds[s]["X"] for s in ("hit", "pit")}
        Xi = {s: np.column_stack([Ds[s]["X"], inj[s]]) for s in ("hit", "pit")}
        Xn = {s: np.column_stack([Ds[s]["X"], nz[s]]) for s in ("hit", "pit")}
        Xd = {s: Ds[s]["X"][:, 1:] for s in ("hit", "pit")}          # drop fv
        b = both(Ds, Xb, sel)
        return dict(base=b, inj=both(Ds, Xi, sel) - b, noise=both(Ds, Xn, sel) - b,
                    dropfv=b - both(Ds, Xd, sel))

    strata = {}
    for s in ("hit", "pit"):
        strata[s] = [np.flatnonzero(Ds[s]["dy"] == u) for u in np.unique(Ds[s]["dy"])]
    pt = arms(None)
    print("  POINT: inj(c=.10) {inj:+.5f}  noise {noise:+.5f}  dropfv {dropfv:+.5f} "
          "(base {base:.5f})".format(**pt))
    acc = {k: [] for k in ("inj", "noise", "dropfv")}
    t0 = time.time()
    for r in range(B):
        sel = {}
        for s in ("hit", "pit"):
            sel[s] = np.concatenate([rng0.choice(ix, len(ix), replace=True)
                                     for ix in strata[s] if len(ix)])
        a = arms(sel)
        for k in acc:
            acc[k].append(a[k])
        if (r + 1) % 50 == 0:
            print(f"   .. {r+1}/{B}  {time.time()-t0:.0f}s")
    res = {}
    for k, v in acc.items():
        v = np.array([x for x in v if np.isfinite(x)])
        res[k] = dict(point=pt[k], mean=float(v.mean()), sd=float(v.std(ddof=1)),
                      lo=float(np.percentile(v, 2.5)), hi=float(np.percentile(v, 97.5)),
                      p_gt0=float((v > 0).mean()), n=len(v))
        print(f"  {k:8s} point {pt[k]:+.5f} mean {v.mean():+.5f} sd {v.std(ddof=1):.5f} "
              f"CI95 [{np.percentile(v,2.5):+.5f},{np.percentile(v,97.5):+.5f}] "
              f"P(>0)={float((v>0).mean()):.3f}  MDE95(2.49sd)={2.49*v.std(ddof=1):.5f}")
    json.dump(res, open(OUT / "_advers_boot.json", "w"), indent=1)


def mode_alpha():
    """E. Independent replication of the shrink lane's alpha-plateau NULL."""
    print("=== E. ALPHA SWEEP (independent replication of the shrink lane) ===")
    Ds = {s: load(s, LAM_LANE) for s in ("hit", "pit")}   # lane pinned pit .63
    Xm = {s: Ds[s]["X"] for s in ("hit", "pit")}
    print("  shipped tuned selector: %.5f" % both(Ds, Xm))
    for a in (0.1, 0.3, 1, 3, 10, 30, 100, 300, 1000, 3000):
        print(f"  fixed alpha {a:<7} block_rho {both(Ds, Xm, alphas=(float(a),)):.5f}")
    print("  -- 24 alpha-holdout seeds (the arbitrary-choice null band) --")
    v = []
    for i in range(24):
        v.append(both(Ds, Xm, rseed=1000 + i))
    v = np.array(v)
    b = both(Ds, Xm)
    print(f"  seed band: mean d {np.mean(v-b):+.5f} sd {v.std(ddof=1):.5f} "
          f"max|d| {np.abs(v-b).max():.5f}")


def mode_splits():
    """F. Independent time splits for the injected positive control + the noise control."""
    print("=== F. PER-ORIGIN SPLITS (injected c=.10 vs zero-info), each origin scored alone ===")
    Ds = {s: load(s, LAM_LIVE) for s in ("hit", "pit")}
    inj = {s: inject(Ds[s], 0.10, np.random.default_rng(SEED + 5)) for s in ("hit", "pit")}
    nz = {s: np.random.default_rng(SEED + 9).standard_normal(Ds[s]["n"]) for s in ("hit", "pit")}
    for yr in (2018, 2019, 2020, 2021, 2022, 2023, 2024):
        out = []
        for s in ("hit", "pit"):
            b = score_side(Ds[s], Ds[s]["X"], origins=(yr,))
            if b is None:
                out.append((s, None))
                continue
            i = score_side(Ds[s], np.column_stack([Ds[s]["X"], inj[s]]), origins=(yr,))
            n = score_side(Ds[s], np.column_stack([Ds[s]["X"], nz[s]]), origins=(yr,))
            d = score_side(Ds[s], Ds[s]["X"][:, 1:], origins=(yr,))
            rb = spear(b[1], b[2])
            out.append((s, len(b[2]), rb, spear(i[1], i[2]) - rb,
                        spear(n[1], n[2]) - rb, rb - spear(d[1], d[2])))
        for o in out:
            if o[1] is None:
                continue
            print(f"  {yr} {o[0]}: n={o[1]:4d} rho={o[2]:+.4f}  d_inj {o[3]:+.4f}  "
                  f"d_noise {o[4]:+.4f}  d_dropfv {o[5]:+.4f}")


def mode_misc():
    """G. Does the METRIC or the bootstrap lose sensitivity?
       G1 block-normalized vs raw pooled Spearman on the same injected arm.
       G2 hit-only drop-fv (the ablate lane's one resolvable claim).
       G3 bootstrap point-shrinkage (train-degradation bias)."""
    print("=== G1. METRIC SENSITIVITY: block-normalized vs raw pooled rho ===")
    Ds = {s: load(s, LAM_LIVE) for s in ("hit", "pit")}
    for c in (0.0, 0.10, 0.20):
        db, dr = [], []
        for rep in range(10):
            rng = np.random.default_rng(SEED + 31 * rep + int(c * 1000))
            Xm = {s: np.column_stack([Ds[s]["X"], inject(Ds[s], c, rng)]) for s in ("hit", "pit")}
            pb = [score_side(Ds[s], Ds[s]["X"]) for s in ("hit", "pit")]
            pi = [score_side(Ds[s], Xm[s]) for s in ("hit", "pit")]
            db.append(blockrho(pi) - blockrho(pb))
            rb = spear(np.concatenate([p[1] for p in pb]), np.concatenate([p[2] for p in pb]))
            ri = spear(np.concatenate([p[1] for p in pi]), np.concatenate([p[2] for p in pi]))
            dr.append(ri - rb)
        print(f"  c={c:.2f}  block_rho d {np.mean(db):+.5f} (sd {np.std(db, ddof=1):.5f}) | "
              f"raw pooled rho d {np.mean(dr):+.5f} (sd {np.std(dr, ddof=1):.5f})")

    print("=== G2. HIT-ONLY DROP-FV (ablate lane's single resolvable feature claim) ===")
    for s in ("hit", "pit"):
        b = score_side(Ds[s], Ds[s]["X"])
        d = score_side(Ds[s], Ds[s]["X"][:, 1:])
        print(f"  {s}: block_rho with fv {blockrho([b]):.5f}  without {blockrho([d]):.5f} "
              f"  drop-delta {blockrho([b]) - blockrho([d]):+.5f}  (n={len(b[2])})")

    print("=== G3. FOUR POINT-NEGATIVE SHIPPED FEATURES (ablate claim) ===")
    for s, feat in (("hit", "ops_rel"), ("hit", "age_rel_level"), ("pit", "age"), ("pit", "bb_rel")):
        ks = Ds[s]["keys"]
        if feat not in ks:
            print(f"  {s}/{feat}: NOT IN SHIPPED SET")
            continue
        j = ks.index(feat)
        cols = [i for i in range(len(ks)) if i != j]
        b = score_side(Ds[s], Ds[s]["X"])
        d = score_side(Ds[s], Ds[s]["X"][:, cols])
        print(f"  {s}/{feat:14s} drop-delta (side-only block_rho) "
              f"{blockrho([b]) - blockrho([d]):+.5f}")


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "base"
    t0 = time.time()
    {"base": mode_base, "ctrl": mode_ctrl, "power": mode_power, "boot": mode_boot,
     "alpha": mode_alpha, "splits": mode_splits, "misc": mode_misc}[m]()
    print("elapsed", round(time.time() - t0, 1), "s")
