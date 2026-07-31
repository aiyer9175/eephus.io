# SCRATCH: LEVEL 2 -- does the coverage-adjusted anchor improve the DOWNSTREAM eFV blend?
# Recommended evaluator (foundation finding efv-evaluator-power-2026-07-24):
#   train = production pool (full pool minus recent busts, sample weights), dy < Y
#   test  = debuted rows, dy == Y ; origins 2020-2024 ; both sides pooled with
#           (side x origin) percentile-block normalization ; lambda PINNED.
# The candidate anchor is fit on the TRAIN fold only and replaces consensus_fv_raw in
# BOTH the OLS consensus leg and the ridge `fv` feature.
from __future__ import annotations
import json, os, sys, time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np
from scipy.stats import rankdata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import efv_model as E                                     # noqa: E402
from prospect_path import _ALPHAS, _RIDGE_HOLDOUT_SEED    # noqa: E402

SEED = 20260724
ORG = tuple(range(2020, 2025))
LAM = {"hit": 0.85, "pit": 0.63}
PATTERNS = ("both", "fg_only", "mp_only", "none")
OUT = HERE / "_frontier_out"
OUT.mkdir(exist_ok=True)


# ---------------------------------------------------------------- data
def load(side):
    fn = "xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json"
    raw = json.loads((ROOT / "data" / fn).read_text("utf-8"))
    pool = [r for r in raw if not (r["kind"] == "bust" and r.get("bust_recent"))]
    data = E._prep(pool, "target_censored", side)
    keys, _mono = E._feature_spec(side)
    bykey = {r["player_key"]: r for r in pool}
    X = np.array([[d["feats"].get(k, 0.0) for k in keys] for d in data], float)
    y = np.array([d["target"] for d in data], float)
    w = np.clip(np.array([float(d.get("weight", 1.0) or 0.0) for d in data]), 1e-3, None)
    fv = np.array([d["fv"] for d in data], float)
    dy = np.array([d["decision_year"] for d in data], int)
    deb = np.array([d["kind"] == "debuted" for d in data])
    fg = np.array([_f(bykey[d["player_key"]].get("fv_fangraphs")) for d in data])
    mp = np.array([_f(bykey[d["player_key"]].get("fv_mlb_pipeline")) for d in data])
    hasf, hasm = np.isfinite(fg), np.isfinite(mp)
    pat = np.empty(len(data), dtype=object)
    pat[hasf & hasm] = "both"; pat[hasf & ~hasm] = "fg_only"
    pat[~hasf & hasm] = "mp_only"; pat[~hasf & ~hasm] = "none"
    ifv = keys.index("fv")
    return {"X": X, "y": y, "w": w, "fv": fv, "dy": dy, "deb": deb, "pat": pat,
            "fg": fg, "mp": mp, "ifv": ifv, "keys": keys, "n": len(data)}


def _f(v):
    return np.nan if v is None else float(v)


# ---------------------------------------------------------------- model prims
def ridge_fit(X, y, w):
    n = len(y)
    if n < 40:
        return None
    k = X.shape[1]
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = sd.copy(); sd[sd == 0] = 1.0
    Xs = (X - mu) / sd

    def _wmean(idx):
        ww = w[idx]
        return float(np.average(y[idx], weights=ww)) if ww.sum() > 0 else float(y[idx].mean())

    def _wridge(idx, alpha, b):
        Xi, wi = Xs[idx], w[idx]
        WX = Xi * wi[:, None]
        return np.linalg.solve(WX.T @ Xi + alpha * np.eye(k), WX.T @ (y[idx] - b))

    order = np.random.default_rng(_RIDGE_HOLDOUT_SEED).permutation(n)
    kk = max(1, n // 5)
    ho, tri = order[:kk], order[kk:]
    b_tr = _wmean(tri)
    best = None
    for alpha in _ALPHAS:
        pred = Xs[ho] @ _wridge(tri, alpha, b_tr) + b_tr
        mae = (float(np.average(np.abs(pred - y[ho]), weights=w[ho]))
               if w[ho].sum() > 0 else float(np.abs(pred - y[ho]).mean()))
        if best is None or mae < best[0]:
            best = (mae, alpha)
    b = _wmean(np.arange(n))
    return (mu, sd, _wridge(np.arange(n), best[1], b), b)


def ridge_pred(m, X):
    mu, sd, w, b = m
    return ((X - mu) / sd) @ w + b


def wols(x, y, w):
    sw = w.sum()
    mx = (w * x).sum() / sw
    my = (w * y).sum() / sw
    var = (w * (x - mx) ** 2).sum()
    if var <= 0:
        return None
    b = (w * (x - mx) * (y - my)).sum() / var
    return (my - b * mx, b)


def spear(a, b):
    ra, rb = rankdata(a), rankdata(b)
    ra = ra - ra.mean(); rb = rb - rb.mean()
    d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d else np.nan


def _r01(v):
    return (rankdata(v) - 0.5) / len(v)


# ---------------------------------------------------------------- anchors
_SPECS = {
    # kind -> (pattern indicators, era-control?, min train decision_year)
    "cov":          (("fg_only", "mp_only", "none"), False, None),
    "cov_nonone":   (("fg_only", "mp_only"),        False, None),
    "cov_era":      (("fg_only", "mp_only"),        True,  None),   # year FE identifies within-year
    "cov_2017":     (("fg_only", "mp_only"),        False, 2017),   # both-sources era only
    "cov_era2017":  (("fg_only", "mp_only"),        True,  2017),
    "cov_fgonly":   (("fg_only",),                  True,  None),
    "cov_mponly":   (("mp_only",),                  True,  None),
}


def anchor(kind, a, tri, tei, pat_override=None, ridge_pen=1.0):
    """Return the anchor value on TRAIN and TEST rows. Params fit on TRAIN only."""
    fv, y, w, dy = a["fv"], a["y"], a["w"], a["dy"]
    pat = a["pat"] if pat_override is None else pat_override
    if kind == "shipped":
        return fv[tri], fv[tei]
    if kind in ("pairgap", "pairgap_half"):
        # TARGET-FREE de-bias: put both outlets on a common FV scale using the
        # within-player (paired) mean gap MLB-Pipeline minus FanGraphs, measured on
        # TRAIN rows both outlets graded.  fg_only -> +gap/2, mp_only -> -gap/2.
        both = np.isfinite(a["fg"][tri]) & np.isfinite(a["mp"][tri])
        if both.sum() >= 25:
            ww = w[tri][both]
            gap = float((ww * (a["mp"][tri][both] - a["fg"][tri][both])).sum() / ww.sum())
        else:
            gap = 0.0
        if kind == "pairgap_half":
            gap *= 0.5
        def adj(idx):
            o = np.zeros(len(idx))
            o[pat[idx] == "fg_only"] = +gap / 2.0
            o[pat[idx] == "mp_only"] = -gap / 2.0
            return fv[idx] + o
        return adj(tri), adj(tei)
    pats, era, ymin = _SPECS[kind]
    fit = tri if ymin is None else tri[dy[tri] >= ymin]
    if len(fit) < 60:
        fit = tri
    years = sorted(set(int(v) for v in dy[fit])) if era else []
    years = years[1:]                                  # drop one for identification

    def build(idx, with_era=True):
        c = [np.ones(len(idx)), fv[idx]] + [(pat[idx] == p).astype(float) for p in pats]
        if era:
            for yy in years:
                c.append((dy[idx] == yy).astype(float) if with_era else np.zeros(len(idx)))
        return np.column_stack(c)

    X = build(fit)
    R = np.eye(X.shape[1]) * ridge_pen
    R[0, 0] = 0.0
    W = w[fit][:, None]
    beta = np.linalg.solve(X.T @ (W * X) + R, X.T @ (w[fit] * y[fit]))
    # era dummies are nuisance controls: zero them out when SCORING so the anchor is
    # a pure fv + coverage-pattern function (year level shifts are absorbed by the
    # per-(side,origin) percentile block normalization anyway).
    return build(tri, with_era=False) @ beta, build(tei, with_era=False) @ beta


# ---------------------------------------------------------------- eval
def evaluate(sides, kinds, origins=ORG, pat_perm_rng=None, ret_parts=False,
             y_shuf_rng=None):
    parts = {k: {"blend": [], "cons": [], "ridge": []} for k in kinds}
    tgt = []
    for s, a in sides.items():
        pat = a["pat"] if pat_perm_rng is None else pat_perm_rng.permutation(a["pat"])
        lam = LAM[s]
        for Y in origins:
            tri = np.flatnonzero(a["dy"] < Y)
            tei = np.flatnonzero((a["dy"] == Y) & a["deb"])
            if len(tei) < 15 or len(tri) < 60:
                continue
            if y_shuf_rng is None:
                a_fit = a
            else:                       # shuffle ONLY the TRAIN-fold target used to FIT
                yy = a["y"].copy()
                yy[tri] = a["y"][tri][y_shuf_rng.permutation(len(tri))]
                a_fit = dict(a); a_fit["y"] = yy
            for k in kinds:
                atr, ate = anchor(k, a_fit, tri, tei, pat_override=pat)
                Xtr = a["X"][tri].copy(); Xte = a["X"][tei].copy()
                Xtr[:, a["ifv"]] = atr; Xte[:, a["ifv"]] = ate
                o = wols(atr, a_fit["y"][tri], a["w"][tri])
                rg = ridge_fit(Xtr, a_fit["y"][tri], a["w"][tri])
                if o is None or rg is None:
                    continue
                c = np.maximum(0.0, o[0] + o[1] * ate)
                r = ridge_pred(rg, Xte)
                parts[k]["cons"].append(_r01(c))
                parts[k]["ridge"].append(_r01(r))
                parts[k]["blend"].append(_r01((1 - lam) * c + lam * r))
            tgt.append(_r01(a["y"][tei]))
    if not tgt:
        return None
    T = np.concatenate(tgt)
    out = {}
    for k in kinds:
        for leg in ("blend", "cons", "ridge"):
            out[f"{k}.{leg}"] = spear(np.concatenate(parts[k][leg]), T)
    out["n"] = len(T)
    return (out, parts, T) if ret_parts else out


def strata(sides):
    return {(s, int(y)): np.flatnonzero(a["dy"] == y)
            for s, a in sides.items() for y in np.unique(a["dy"])}


def resample(sides, st, rng):
    picks = {s: [] for s in sides}
    for (s, _y), idx in st.items():
        picks[s].append(rng.choice(idx, size=len(idx), replace=True))
    out = {}
    for s, a in sides.items():
        ii = np.concatenate(picks[s])
        out[s] = {k: (v[ii] if isinstance(v, np.ndarray) else v) for k, v in a.items()}
        out[s]["ifv"] = a["ifv"]; out[s]["keys"] = a["keys"]
    return out


KINDS = ["shipped", "cov", "cov_nonone"]


def main():
    t0 = time.time()
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 250
    BN = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    sides = {s: load(s) for s in ("hit", "pit")}
    for s, a in sides.items():
        print(f"{s}: pool n={a['n']} debuted {int(a['deb'].sum())} keys={len(a['keys'])} "
              f"lam={LAM[s]}")
    res = {}
    pt = evaluate(sides, KINDS)
    print(f"\n=== LEVEL 2 POINT (block-normalized pooled Spearman, n={pt['n']}) ===")
    for k in KINDS:
        print(f"  {k:11s} blend {pt[k+'.blend']:.4f} (d {pt[k+'.blend']-pt['shipped.blend']:+.4f}) "
              f"| cons {pt[k+'.cons']:.4f} (d {pt[k+'.cons']-pt['shipped.cons']:+.4f}) "
              f"| ridge {pt[k+'.ridge']:.4f} (d {pt[k+'.ridge']-pt['shipped.ridge']:+.4f})")
    res["point"] = {k: float(v) for k, v in pt.items()}

    print(f"\n=== PAIRED REFIT BOOTSTRAP (within (side,dy), full refit), B={B} ===")
    st = strata(sides)
    rng = np.random.default_rng(SEED)
    draws = []
    for i in range(B):
        r = evaluate(resample(sides, st, rng), KINDS)
        if r is not None:
            draws.append(r)
    for k in KINDS:
        if k == "shipped":
            continue
        for leg in ("blend", "cons", "ridge"):
            d = np.array([x[f"{k}.{leg}"] - x[f"shipped.{leg}"] for x in draws])
            d = d[np.isfinite(d)]
            e = {"point": float(pt[f"{k}.{leg}"] - pt[f"shipped.{leg}"]),
                 "mean": float(d.mean()), "sd": float(d.std(ddof=1)),
                 "lo": float(np.percentile(d, 2.5)), "hi": float(np.percentile(d, 97.5)),
                 "p_gt0": float((d > 0).mean()), "mde95": float(1.645 * d.std(ddof=1)),
                 "B": int(len(d))}
            res.setdefault("bootstrap", {})[f"{k}.{leg}"] = e
            print(f"  {k:11s} {leg:6s} point {e['point']:+.4f} mean {e['mean']:+.4f} "
                  f"sd {e['sd']:.4f} CI95 [{e['lo']:+.4f},{e['hi']:+.4f}] "
                  f"P(>0) {e['p_gt0']:.3f} MDE95 {e['mde95']:.4f}")

    print(f"\n=== NULL: coverage-pattern labels PERMUTED (zero-info twin), B={BN} ===")
    rngN = np.random.default_rng(SEED + 9)
    nb = {k: [] for k in KINDS if k != "shipped"}
    for _ in range(BN):
        r = evaluate(sides, KINDS, pat_perm_rng=rngN)
        for k in nb:
            nb[k].append(r[f"{k}.blend"] - r["shipped.blend"])
    for k, v in nb.items():
        v = np.array(v); real = pt[f"{k}.blend"] - pt["shipped.blend"]
        print(f"  {k:11s} null mean {v.mean():+.5f} sd {v.std(ddof=1):.5f} "
              f"p95 {np.percentile(v,95):+.5f} max|d| {np.abs(v).max():.5f} | real {real:+.4f} "
              f"p(null>=real) {(v>=real).mean():.4f}")
        res.setdefault("null_pattern_perm", {})[k] = {
            "mean": float(v.mean()), "sd": float(v.std(ddof=1)),
            "p95": float(np.percentile(v, 95)), "max_abs": float(np.abs(v).max()),
            "real": float(real), "p_ge_real": float((v >= real).mean()), "B": int(len(v))}

    print("\n=== PER-BLOCK (side x origin, 2014-2024) blend deltas ===")
    pb = {}
    for s in ("hit", "pit"):
        for Y in range(2014, 2025):
            r = evaluate({s: sides[s]}, KINDS, origins=(Y,))
            if r is None:
                continue
            pb[f"{s}{Y}"] = {k: float(r[f"{k}.blend"]) for k in KINDS}
    res["per_block"] = pb
    for k in KINDS:
        if k == "shipped":
            continue
        d = np.array([v[k] - v["shipped"] for v in pb.values()])
        d = d[np.isfinite(d)]
        se = d.std(ddof=1) / np.sqrt(len(d))
        print(f"  {k:11s} mean {d.mean():+.4f} se {se:.4f} t {d.mean()/se:+.2f} "
              f"signs {int((d>0).sum())}+/{int((d<0).sum())}- nblk={len(d)}")
        res.setdefault("per_block_summary", {})[k] = {
            "mean": float(d.mean()), "se": float(se), "pos": int((d > 0).sum()),
            "neg": int((d < 0).sum()), "n": int(len(d))}

    json.dump(res, open(OUT / "_anchor_level2.json", "w"), indent=1, default=float)
    print("\nelapsed", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
