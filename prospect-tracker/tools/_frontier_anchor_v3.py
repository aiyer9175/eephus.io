# SCRATCH: anchor v3 -- decompose the shift_only/warcal gain into
#   (1) paired grading-SCALE de-bias  vs  (2) COVERAGE-pattern (who graded whom) offsets,
# with a pairing-preserving placebo null and a paired refit bootstrap.
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import _frontier_anchor as A

OUT = Path(__file__).resolve().parent / "_frontier_out"
OUT.mkdir(exist_ok=True)
_orig_apply = A.apply_anchor
_orig_fit = A.fit_anchor

PATTERNS = ("both", "fg_only", "mp_only", "none")


def pattern_of(te):
    f = np.isfinite(te["fg"])
    m = np.isfinite(te["mp"])
    out = np.empty(len(f), dtype=object)
    out[f & m] = "both"
    out[f & ~m] = "fg_only"
    out[~f & m] = "mp_only"
    out[~f & ~m] = "none"
    return out


def fit3(tr, y_override=None):
    P = _orig_fit(tr, y_override=y_override)
    yv = tr["y"] if y_override is None else y_override
    fg, mp, w, cons = tr["fg"], tr["mp"], tr["w"], tr["cons"]
    both = np.isfinite(fg) & np.isfinite(mp)
    if both.sum() >= 25:
        ww = w[both]
        P["pair_gap"] = float((ww * (mp[both] - fg[both])).sum() / ww.sum())
    else:
        P["pair_gap"] = 0.0
    P["pair_n"] = int(both.sum())

    # ---- COVERAGE OFFSETS: mean WAR residual from the cons-OLS, by pattern,
    # shrunk toward 0 with k pseudo-observations, expressed back in FV units.
    co = P["cons_ols"]
    pat = pattern_of(tr)
    off = {}
    resid_mean = {}
    if co is not None and co[1] > 1e-9:
        pred = co[0] + co[1] * cons
        res = yv - pred
        for p in PATTERNS:
            m = pat == p
            if m.sum() < 20:
                off[p] = 0.0
                resid_mean[p] = 0.0
                continue
            ww = w[m]
            r = float((ww * res[m]).sum() / ww.sum())
            n = float(m.sum())
            k = P.get("_shrink_k", 40.0)
            r_sh = r * n / (n + k)
            resid_mean[p] = r
            off[p] = r_sh / co[1]          # WAR residual -> FV-equivalent points
    else:
        off = {p: 0.0 for p in PATTERNS}
        resid_mean = dict(off)
    P["cov_off"] = off
    P["cov_resid"] = resid_mean
    # scale-only marginal source means (for the marginal shift arm)
    return P


def apply3(kind, P, te, weights=None):
    cons, fg, mp = te["cons"], te["fg"], te["mp"]
    n = len(cons)
    g = P.get("pair_gap", 0.0)
    pat = pattern_of(te)

    if kind == "pair_shift":                    # (1) grading-scale de-bias ONLY
        return A._combine(cons - g / 2.0, [fg, mp - g], [1.0, 1.0])
    if kind == "cov_only":                      # (2) coverage offsets ONLY, on the shipped anchor
        o = P["cov_off"]
        return cons + np.array([o.get(p, 0.0) for p in pat])
    if kind == "pair_shift_cov":                # (1) + (2)
        base = A._combine(cons - g / 2.0, [fg, mp - g], [1.0, 1.0])
        o = P["cov_off"]
        return base + np.array([o.get(p, 0.0) for p in pat])
    if kind == "cov_placebo":                   # zero-information twin of cov_only
        o = P["cov_off"]
        rng = P["_placebo_rng"]
        v = np.array([o.get(p, 0.0) for p in pat])
        return cons + rng.permutation(v)        # same marginal offsets, random rows
    if kind == "shift_only":
        zs = []
        for k, arr in (("fg", fg), ("mp", mp)):
            mo = P[f"mom_{k}"]
            zs.append(arr - mo[0] if mo else np.full(n, np.nan))
        cm = P["cons_mom"]
        return A._combine(cons - cm[0] if cm else cons, zs, [1.0, 1.0])
    return _orig_apply(kind, P, te, weights=weights)


A.fit_anchor = fit3
A.apply_anchor = apply3

KINDS = ["shipped", "pair_shift", "cov_only", "pair_shift_cov", "shift_only",
         "warcal", "cov_placebo"]


def sides_arrays(cut="debuted_km"):
    return {s: A.to_arrays(A.load_rows(s, cut)) for s in ("hit", "pit")}


def run(sides, kinds, origins, rng=None, y_shuffle_rng=None):
    # placebo rng plumbed through fit params
    real_fit = A.fit_anchor

    def fit_with_rng(tr, y_override=None):
        P = real_fit(tr, y_override=y_override)
        P["_placebo_rng"] = rng if rng is not None else np.random.default_rng(0)
        return P
    A.fit_anchor = fit_with_rng
    try:
        r = A.fwd_anchor(kinds, sides, origins, y_shuffle_rng=y_shuffle_rng)
    finally:
        A.fit_anchor = real_fit
    if r is None:
        return None, None
    preds, tgt, blk = r
    return {k: A.spear(preds[k], tgt) for k in kinds}, (tgt, blk)


def strata(sides):
    out = {}
    for s, a in sides.items():
        for y in np.unique(a["dy"]):
            out[(s, int(y))] = np.flatnonzero(a["dy"] == y)
    return out


def resample(sides, st, rng):
    picks = {s: [] for s in sides}
    for (s, _y), idx in st.items():
        picks[s].append(rng.choice(idx, size=len(idx), replace=True))
    out = {}
    for s, a in sides.items():
        ii = np.concatenate(picks[s])
        out[s] = {k: v[ii] for k, v in a.items() if isinstance(v, np.ndarray)}
    return out


def main():
    t0 = time.time()
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    BN = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    ORG = tuple(range(2020, 2025))
    sides = sides_arrays()
    res = {}

    # ---------- descriptive: coverage pattern -> realized outcome
    print("=== COVERAGE PATTERN DESCRIPTIVES (debuted rows, all years) ===")
    for s in ("hit", "pit"):
        a = sides[s]
        pat = pattern_of(a)
        for p in PATTERNS:
            m = pat == p
            if m.sum() == 0:
                continue
            print(f"  {s} {p:8s} n={int(m.sum()):4d}  mean cons_fv {a['cons'][m].mean():5.2f}"
                  f"  mean WAR {a['y'][m].mean():5.2f}  median {np.median(a['y'][m]):5.2f}")
            res.setdefault("desc", {})[f"{s}_{p}"] = {
                "n": int(m.sum()), "fv": float(a["cons"][m].mean()),
                "war": float(a["y"][m].mean())}

    rng0 = np.random.default_rng(A.SEED)
    pt, (tgt, blk) = run(sides, KINDS, ORG, rng=rng0)
    print(f"\n=== POINT (n={len(tgt)}, origins {ORG[0]}-{ORG[-1]}) ===")
    for k in KINDS:
        print(f"  {k:16s} rho {pt[k]:.4f}  delta {pt[k]-pt['shipped']:+.4f}")
    res["point"] = {k: float(pt[k]) for k in KINDS}

    # fitted coverage offsets for the record
    print("\n=== FITTED COVERAGE OFFSETS (FV-equivalent points, train<2024) ===")
    for s in ("hit", "pit"):
        a = sides[s]
        tri = np.flatnonzero(a["dy"] < 2024)
        tr = {k: v[tri] for k, v in a.items() if isinstance(v, np.ndarray)}
        P = fit3(tr)
        print(f"  {s}: offsets " + " ".join(f"{p}={P['cov_off'][p]:+.2f}" for p in PATTERNS)
              + " | WAR resid " + " ".join(f"{p}={P['cov_resid'][p]:+.2f}" for p in PATTERNS)
              + f" | pair_gap {P['pair_gap']:+.2f}")
        res.setdefault("offsets", {})[s] = {"off": P["cov_off"], "resid": P["cov_resid"],
                                            "pair_gap": P["pair_gap"]}

    # ---------- paired refit bootstrap
    print(f"\n=== PAIRED REFIT BOOTSTRAP (resample pool within (side,dy)), B={B} ===")
    st = strata(sides)
    rng = np.random.default_rng(A.SEED + 1)
    draws = {k: [] for k in KINDS}
    for b in range(B):
        sb = resample(sides, st, rng)
        r, _ = run(sb, KINDS, ORG, rng=rng)
        if r is None:
            continue
        for k in KINDS:
            draws[k].append(r[k])
    D = {k: np.array(v) for k, v in draws.items()}
    boot = {}
    for k in KINDS:
        if k == "shipped":
            continue
        d = D[k] - D["shipped"]
        d = d[np.isfinite(d)]
        boot[k] = {"point": float(pt[k] - pt["shipped"]), "mean": float(d.mean()),
                   "sd": float(d.std(ddof=1)), "lo": float(np.percentile(d, 2.5)),
                   "hi": float(np.percentile(d, 97.5)), "p_gt0": float((d > 0).mean()),
                   "mde95": float(1.645 * d.std(ddof=1)), "B": int(len(d))}
        print(f"  {k:16s} point {boot[k]['point']:+.4f} mean {boot[k]['mean']:+.4f} "
              f"sd {boot[k]['sd']:.4f} CI95 [{boot[k]['lo']:+.4f},{boot[k]['hi']:+.4f}] "
              f"P(>0) {boot[k]['p_gt0']:.3f} MDE95 {boot[k]['mde95']:.4f}")
    res["bootstrap"] = boot

    # ---------- null band 1: placebo coverage offsets (same marginals, random rows)
    print(f"\n=== NULL BAND A: cov_placebo (identical offset marginals, permuted rows), B={BN} ===")
    nb = []
    rngn = np.random.default_rng(A.SEED + 2)
    for b in range(BN):
        r, _ = run(sides, ["shipped", "cov_placebo"], ORG, rng=rngn)
        nb.append(r["cov_placebo"] - r["shipped"])
    nb = np.array(nb)
    print(f"  mean {nb.mean():+.5f} sd {nb.std(ddof=1):.5f} p95 {np.percentile(nb,95):+.5f} "
          f"max|d| {np.abs(nb).max():.5f}  -> p(null >= real cov_only) = "
          f"{(nb >= (pt['cov_only']-pt['shipped'])).mean():.4f}")
    res["null_placebo"] = {"mean": float(nb.mean()), "sd": float(nb.std(ddof=1)),
                           "p95": float(np.percentile(nb, 95)), "max_abs": float(np.abs(nb).max()),
                           "p_ge_real": float((nb >= (pt["cov_only"] - pt["shipped"])).mean()),
                           "B": int(len(nb))}

    # ---------- null band 2: offsets estimated from a PERMUTED train target
    print(f"\n=== NULL BAND B: offsets fit on SHUFFLED train WAR (structure kept), B={BN} ===")
    nb2 = {k: [] for k in ("cov_only", "pair_shift_cov", "warcal")}
    rngs = np.random.default_rng(A.SEED + 3)
    for b in range(BN):
        r, _ = run(sides, ["shipped", "cov_only", "pair_shift_cov", "warcal"], ORG,
                   rng=rngs, y_shuffle_rng=rngs)
        for k in nb2:
            nb2[k].append(r[k] - r["shipped"])
    for k, v in nb2.items():
        v = np.array(v)
        real = pt[k] - pt["shipped"]
        print(f"  {k:16s} null mean {v.mean():+.5f} sd {v.std(ddof=1):.5f} "
              f"p95 {np.percentile(v,95):+.5f} max|d| {np.abs(v).max():.5f} | real {real:+.4f} "
              f"-> p(null>=real) {(v>=real).mean():.4f}")
        res.setdefault("null_shuffle", {})[k] = {
            "mean": float(v.mean()), "sd": float(v.std(ddof=1)),
            "p95": float(np.percentile(v, 95)), "max_abs": float(np.abs(v).max()),
            "real": float(real), "p_ge_real": float((v >= real).mean())}

    json.dump(res, open(OUT / "_anchor_v3.json", "w"), indent=1, default=float)
    print("\nelapsed", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
