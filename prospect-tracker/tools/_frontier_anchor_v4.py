# SCRATCH: anchor v4 -- PRODUCTION-CONFIG anchor eval.
#   TRAIN on the full pool minus recent busts (production sample weights), TEST on
#   debuted rows.  Unified WLS anchor (per-source slope/intercept + coverage-pattern
#   intercepts, shrunk), paired refit bootstrap, pattern-permutation placebo null,
#   shuffled-target null, per-block cross-split.
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from scipy.stats import rankdata
import _frontier_anchor as A

OUT = Path(__file__).resolve().parent / "_frontier_out"
OUT.mkdir(exist_ok=True)
PATTERNS = ("both", "fg_only", "mp_only", "none")
ORG = tuple(range(2020, 2025))


def pattern_of(fg, mp):
    f = np.isfinite(fg); m = np.isfinite(mp)
    out = np.empty(len(f), dtype=object)
    out[f & m] = "both"; out[f & ~m] = "fg_only"
    out[~f & m] = "mp_only"; out[~f & ~m] = "none"
    return out


def load(side):
    """Returns (pool_arrays, debut_mask). Pool = production train pool
    (full pool minus recent busts); debut_mask flags the rows eligible as TEST rows."""
    rows = A.load_rows(side, "full_pool_km")
    a = A.to_arrays(rows)
    a["deb"] = np.array([r["row"]["kind"] == "debuted" for r in rows])
    a["pat"] = pattern_of(a["fg"], a["mp"])
    return a


# ------------------------------------------------------------------ anchors
def _wls(X, y, w, ridge=0.0):
    W = w[:, None]
    Ac = X.T @ (W * X) + ridge * np.eye(X.shape[1])
    return np.linalg.solve(Ac, X.T @ (w * y))


def build_designs(a, idx, kind):
    """Design matrix rows for the unified anchor specs."""
    cons, fg, mp, pat = a["cons"][idx], a["fg"][idx], a["mp"][idx], a["pat"][idx]
    n = len(idx)
    cols = [np.ones(n)]
    names = ["const"]
    if kind in ("cons_cov", "cons_only"):
        cols.append(cons); names.append("cons")
    if kind in ("src", "src_cov"):
        # per-source slope + per-source presence intercept (bias AND scale per outlet)
        for k, arr in (("fg", fg), ("mp", mp)):
            pres = np.isfinite(arr).astype(float)
            v = np.where(np.isfinite(arr), arr, 0.0)
            cols.append(pres); names.append(f"has_{k}")
            cols.append(v); names.append(f"fv_{k}")
        cols.append(np.where(np.isfinite(fg) | np.isfinite(mp), 0.0, 1.0)); names.append("no_src")
        cols.append(np.where(np.isfinite(fg) | np.isfinite(mp), 0.0, cons)); names.append("no_src_cons")
    if kind in ("cons_cov", "src_cov"):
        for p in ("fg_only", "mp_only", "none"):
            cols.append((pat == p).astype(float)); names.append(f"pat_{p}")
    return np.column_stack(cols), names


def fit_anchor(a, tri, kind, y_override=None, ridge=1.0):
    y = a["y"][tri] if y_override is None else y_override
    X, names = build_designs(a, tri, kind)
    # standardize-free ridge on everything but the constant
    R = np.eye(X.shape[1]) * ridge
    R[0, 0] = 0.0
    W = a["w"][tri][:, None]
    beta = np.linalg.solve(X.T @ (W * X) + R, X.T @ (a["w"][tri] * y))
    return {"beta": beta, "names": names, "kind": kind}


def apply_anchor(a, idx, M):
    X, _ = build_designs(a, idx, M["kind"])
    return X @ M["beta"]


# ------------------------------------------------------------------ eval
def _r01(v):
    return (rankdata(v) - 0.5) / len(v)


def evaluate(sides, kinds, origins=ORG, y_shuffle_rng=None, perm_pat_rng=None,
             ret_blocks=False):
    preds = {k: [] for k in kinds}
    tgt, blocks = [], []
    for s, a in sides.items():
        if perm_pat_rng is not None:
            a = dict(a)
            a["pat"] = perm_pat_rng.permutation(a["pat"])
        for Y in origins:
            tri = np.flatnonzero(a["dy"] < Y)
            tei = np.flatnonzero((a["dy"] == Y) & a["deb"])
            if len(tei) < 15 or len(tri) < 60:
                continue
            yov = None
            if y_shuffle_rng is not None:
                yov = a["y"][tri][y_shuffle_rng.permutation(len(tri))]
            for k in kinds:
                if k == "shipped":
                    v = a["cons"][tei]
                else:
                    M = fit_anchor(a, tri, k, y_override=yov)
                    v = apply_anchor(a, tei, M)
                preds[k].append(_r01(v))
            tgt.append(_r01(a["y"][tei]))
            blocks.append((s, Y, len(tei)))
    if not tgt:
        return None
    P = {k: np.concatenate(v) for k, v in preds.items()}
    T = np.concatenate(tgt)
    out = {k: A.spear(P[k], T) for k in kinds}
    return (out, blocks, P, T) if ret_blocks else out


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
    return out


KINDS = ["shipped", "cons_only", "cons_cov", "src", "src_cov"]


def main():
    t0 = time.time()
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    BN = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    sides = {s: load(s) for s in ("hit", "pit")}
    res = {}
    for s, a in sides.items():
        print(f"{s}: pool n={len(a['y'])} (debuted {int(a['deb'].sum())}) "
              f"patterns " + " ".join(f"{p}={int((a['pat']==p).sum())}" for p in PATTERNS))

    pt, blocks, P, T = evaluate(sides, KINDS, ret_blocks=True)
    print(f"\n=== POINT: PRODUCTION CONFIG (train=full pool minus recent busts, "
          f"test=debuted, origins 2020-2024, n={len(T)}) ===")
    for k in KINDS:
        print(f"  {k:11s} rho {pt[k]:.4f}  delta {pt[k]-pt['shipped']:+.4f}")
    res["point"] = {k: float(pt[k]) for k in KINDS}
    res["blocks"] = [[b[0], int(b[1]), int(b[2])] for b in blocks]

    # coefficients of the winning specs (train<2024, for the record)
    print("\n=== FITTED COEFFICIENTS (train<2024) ===")
    for s in ("hit", "pit"):
        a = sides[s]
        tri = np.flatnonzero(a["dy"] < 2024)
        for k in ("cons_cov", "src_cov"):
            M = fit_anchor(a, tri, k)
            print(f"  {s}/{k}: " + " ".join(f"{n}={b:+.4f}" for n, b in zip(M["names"], M["beta"])))
            res.setdefault("coefs", {})[f"{s}_{k}"] = dict(
                zip(M["names"], [float(v) for v in M["beta"]]))

    # ---- per-block cross-split (each side x origin separately, 2014-2024)
    print("\n=== PER-BLOCK DELTAS (side x origin 2014-2024) ===")
    perblk = {}
    for s in ("hit", "pit"):
        for Y in range(2014, 2025):
            r = evaluate({s: sides[s]}, KINDS, origins=(Y,))
            if r is None:
                continue
            perblk[f"{s}{Y}"] = {k: float(r[k]) for k in KINDS}
    res["per_block"] = perblk
    for k in KINDS:
        if k == "shipped":
            continue
        d = np.array([v[k] - v["shipped"] for v in perblk.values()])
        d = d[np.isfinite(d)]
        se = d.std(ddof=1) / np.sqrt(len(d))
        print(f"  {k:11s} mean {d.mean():+.4f} se {se:.4f} t {d.mean()/se:+.2f} "
              f"signs {int((d>0).sum())}+/{int((d<0).sum())}-  nblk={len(d)}")
        res.setdefault("per_block_summary", {})[k] = {
            "mean": float(d.mean()), "se": float(se),
            "pos": int((d > 0).sum()), "neg": int((d < 0).sum())}

    # ---- paired refit bootstrap
    print(f"\n=== PAIRED REFIT BOOTSTRAP (resample pool within (side,dy), refit), B={B} ===")
    st = strata(sides)
    rng = np.random.default_rng(A.SEED)
    draws = {k: [] for k in KINDS}
    for _ in range(B):
        sb = resample(sides, st, rng)
        r = evaluate(sb, KINDS)
        if r is None:
            continue
        for k in KINDS:
            draws[k].append(r[k])
    D = {k: np.array(v) for k, v in draws.items()}
    for k in KINDS:
        if k == "shipped":
            continue
        d = D[k] - D["shipped"]
        d = d[np.isfinite(d)]
        e = {"point": float(pt[k] - pt["shipped"]), "mean": float(d.mean()),
             "sd": float(d.std(ddof=1)), "lo": float(np.percentile(d, 2.5)),
             "hi": float(np.percentile(d, 97.5)), "p_gt0": float((d > 0).mean()),
             "mde95": float(1.645 * d.std(ddof=1)), "B": int(len(d))}
        res.setdefault("bootstrap", {})[k] = e
        print(f"  {k:11s} point {e['point']:+.4f} mean {e['mean']:+.4f} sd {e['sd']:.4f} "
              f"CI95 [{e['lo']:+.4f},{e['hi']:+.4f}] P(>0) {e['p_gt0']:.3f} MDE95 {e['mde95']:.4f}")

    # ---- null A: permute the coverage pattern labels (pairing-preserving placebo)
    print(f"\n=== NULL A: coverage-pattern labels PERMUTED (zero-info twin), B={BN} ===")
    rngA = np.random.default_rng(A.SEED + 5)
    nb = {k: [] for k in ("cons_cov", "src_cov")}
    for _ in range(BN):
        r = evaluate(sides, ["shipped", "cons_cov", "src_cov"], perm_pat_rng=rngA)
        for k in nb:
            nb[k].append(r[k] - r["shipped"])
    for k, v in nb.items():
        v = np.array(v); real = pt[k] - pt["shipped"]
        print(f"  {k:11s} null mean {v.mean():+.5f} sd {v.std(ddof=1):.5f} p95 "
              f"{np.percentile(v,95):+.5f} max|d| {np.abs(v).max():.5f} | real {real:+.4f} "
              f"p(null>=real) {(v>=real).mean():.4f}")
        res.setdefault("null_pattern_perm", {})[k] = {
            "mean": float(v.mean()), "sd": float(v.std(ddof=1)),
            "p95": float(np.percentile(v, 95)), "max_abs": float(np.abs(v).max()),
            "real": float(real), "p_ge_real": float((v >= real).mean())}

    # ---- null B: shuffled train target (all fitted structure becomes noise)
    print(f"\n=== NULL B: train target SHUFFLED, B={BN} ===")
    rngB = np.random.default_rng(A.SEED + 6)
    nb2 = {k: [] for k in KINDS if k != "shipped"}
    for _ in range(BN):
        r = evaluate(sides, KINDS, y_shuffle_rng=rngB)
        for k in nb2:
            nb2[k].append(r[k] - r["shipped"])
    for k, v in nb2.items():
        v = np.array(v); real = pt[k] - pt["shipped"]
        print(f"  {k:11s} null mean {v.mean():+.5f} sd {v.std(ddof=1):.5f} p95 "
              f"{np.percentile(v,95):+.5f} | real {real:+.4f} p(null>=real) {(v>=real).mean():.4f}")
        res.setdefault("null_target_shuffle", {})[k] = {
            "mean": float(v.mean()), "sd": float(v.std(ddof=1)),
            "p95": float(np.percentile(v, 95)), "real": float(real),
            "p_ge_real": float((v >= real).mean())}

    json.dump(res, open(OUT / "_anchor_v4.json", "w"), indent=1, default=float)
    print("\nelapsed", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
