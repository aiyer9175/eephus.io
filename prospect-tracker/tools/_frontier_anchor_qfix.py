# SCRATCH: the CONCRETE repair candidate -- grade_normalization.quantile_map uses an
# upper-edge tie convention on a discrete 5-point FV lattice, which makes the MLB-Pipeline
# -> FanGraphs map a near identity.  This rebuilds the consensus with a MID-RANK
# (mid-distribution) quantile map fitted forward-chained on TRAIN paired rows, and runs it
# through the recommended eFV evaluator with the full control set.
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import _frontier_anchor_level2 as L

OUT = Path(__file__).resolve().parent / "_frontier_out"
SEED = 20260724


def _midrank_map(src_vals, ref_vals, upper_edge=False):
    """Return f(v) mapping a source grade onto the reference scale.
    mid-rank: q(v) = (P(src<v) + P(src<=v)) / 2   [upper_edge=True reproduces the
    shipped np.interp behaviour, q(v) = P(src<=v), which is what makes the map inert]."""
    s = np.sort(np.asarray(src_vals, float))
    r = np.sort(np.asarray(ref_vals, float))
    n, m = len(s), len(r)
    if n < 25 or m < 25:
        return None

    def f(v):
        v = np.asarray(v, float)
        lo = np.searchsorted(s, v, "left") / n
        hi = np.searchsorted(s, v, "right") / n
        q = hi if upper_edge else (lo + hi) / 2.0
        idx = np.clip((q * m).astype(int), 0, m - 1)
        return r[idx]
    return f


def anchor_qfix(kind, a, tri, tei, pat_override=None, ridge_pen=1.0):
    fv, fg, mp = a["fv"], a["fg"], a["mp"]
    if kind == "shipped":
        return fv[tri], fv[tei]
    upper = kind.endswith("_upper")
    both = np.isfinite(fg[tri]) & np.isfinite(mp[tri])
    f = _midrank_map(mp[tri][both], fg[tri][both], upper_edge=upper) if both.sum() >= 25 else None

    def build(idx):
        F, M = fg[idx], mp[idx]
        Mn = f(np.where(np.isfinite(M), M, 45.0)) if f is not None else M
        Mn = np.where(np.isfinite(M), Mn, np.nan)
        num = np.zeros(len(idx)); den = np.zeros(len(idx))
        for arr in (F, Mn):
            ok = np.isfinite(arr)
            num[ok] += arr[ok]; den[ok] += 1
        return np.where(den > 0, num / np.where(den > 0, den, 1), fv[idx])
    return build(tri), build(tei)


def main():
    t0 = time.time()
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    BN = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    sides = {s: L.load(s) for s in ("hit", "pit")}
    res = {}

    # ---- 1. what the two tie conventions actually do to the Pipeline scale
    print("=== TIE-CONVENTION DIAGNOSTIC (train<2024 paired rows) ===")
    for s in ("hit", "pit"):
        a = sides[s]
        tri = np.flatnonzero(a["dy"] < 2024)
        both = np.isfinite(a["fg"][tri]) & np.isfinite(a["mp"][tri])
        MP, FG = a["mp"][tri][both], a["fg"][tri][both]
        for name, up in (("shipped upper-edge", True), ("mid-rank", False)):
            f = _midrank_map(MP, FG, upper_edge=up)
            mapped = f(MP)
            grid = np.array([35., 40., 45., 50., 55., 60.])
            print(f"  {s} {name:18s}: grid " +
                  " ".join(f"{int(g)}->{f(np.array([g]))[0]:.0f}" for g in grid) +
                  f" | residual paired gap after map {np.mean(mapped - FG):+.3f} "
                  f"(raw {np.mean(MP - FG):+.3f}) n={len(MP)}")
            res.setdefault("tie_diag", {})[f"{s}_{name}"] = {
                "residual_gap": float(np.mean(mapped - FG)),
                "raw_gap": float(np.mean(MP - FG)),
                "grid": {int(g): float(f(np.array([g]))[0]) for g in grid}}

    # ---- 2. downstream
    save = L.anchor
    L.anchor = anchor_qfix
    KIND = ["shipped", "qfix", "qfix_upper"]
    try:
        pt = L.evaluate(sides, KIND)
        print(f"\n=== LEVEL 2 (recommended evaluator, n={pt['n']}) ===")
        for k in KIND:
            print(f"  {k:11s} blend {pt[k+'.blend']:.4f} (d {pt[k+'.blend']-pt['shipped.blend']:+.4f}) "
                  f"cons {pt[k+'.cons']:.4f} (d {pt[k+'.cons']-pt['shipped.cons']:+.4f}) "
                  f"ridge {pt[k+'.ridge']:.4f} (d {pt[k+'.ridge']-pt['shipped.ridge']:+.4f})")
        res["point"] = {k: float(v) for k, v in pt.items()}
        for s in ("hit", "pit"):
            r = L.evaluate({s: sides[s]}, KIND)
            print(f"  {s} only n={r['n']}: " + " | ".join(
                f"{k} d {r[k+'.blend']-r['shipped.blend']:+.4f}" for k in KIND if k != "shipped"))
            res[f"point_{s}"] = {k: float(v) for k, v in r.items()}

        print(f"\n=== PAIRED REFIT BOOTSTRAP B={B} ===")
        st = L.strata(sides)
        rng = np.random.default_rng(SEED)
        draws = [L.evaluate(L.resample(sides, st, rng), KIND) for _ in range(B)]
        draws = [d for d in draws if d is not None]
        for k in KIND:
            if k == "shipped":
                continue
            for leg in ("blend", "cons", "ridge"):
                d = np.array([x[f"{k}.{leg}"] - x[f"shipped.{leg}"] for x in draws])
                d = d[np.isfinite(d)]
                e = {"point": float(pt[f"{k}.{leg}"] - pt["shipped." + leg]),
                     "mean": float(d.mean()), "sd": float(d.std(ddof=1)),
                     "lo": float(np.percentile(d, 2.5)), "hi": float(np.percentile(d, 97.5)),
                     "p_gt0": float((d > 0).mean()), "mde95": float(1.645 * d.std(ddof=1)),
                     "mde80pow": float(2.49 * d.std(ddof=1)), "B": int(len(d))}
                res.setdefault("boot", {})[f"{k}.{leg}"] = e
                print(f"  {k:11s} {leg:6s} point {e['point']:+.4f} mean {e['mean']:+.4f} "
                      f"sd {e['sd']:.4f} CI95 [{e['lo']:+.4f},{e['hi']:+.4f}] P(>0) {e['p_gt0']:.3f} "
                      f"MDE95 {e['mde95']:.4f} MDE(80%pow) {e['mde80pow']:.4f}")

        print(f"\n=== NULL: source labels permuted (which outlet graded whom), B={BN} ===")
        rngN = np.random.default_rng(SEED + 3)
        nb = {k: [] for k in KIND if k != "shipped"}
        for _ in range(BN):
            sp = {}
            for s, a in sides.items():
                b = dict(a)
                # permute the (fg, mp) PAIR assignment across rows: identical marginal
                # grade distributions and identical coverage-pattern counts, zero
                # information about which player each outlet actually graded.
                p = rngN.permutation(len(a["fv"]))
                b["fg"] = a["fg"][p]; b["mp"] = a["mp"][p]
                sp[s] = b
            r = L.evaluate(sp, KIND)
            for k in nb:
                nb[k].append(r[f"{k}.blend"] - r["shipped.blend"])
        for k, v in nb.items():
            v = np.array(v); real = pt[f"{k}.blend"] - pt["shipped.blend"]
            print(f"  {k:11s} null mean {v.mean():+.5f} sd {v.std(ddof=1):.5f} "
                  f"p95 {np.percentile(v,95):+.5f} max {v.max():+.5f} | REAL {real:+.4f} "
                  f"p(null>=real) {(v>=real).mean():.4f}")
            res.setdefault("null_srcperm", {})[k] = {
                "mean": float(v.mean()), "sd": float(v.std(ddof=1)),
                "p95": float(np.percentile(v, 95)), "max": float(v.max()),
                "real": float(real), "p_ge_real": float((v >= real).mean()), "B": int(len(v))}

        print("\n=== CROSS-SPLIT (side x origin 2014-2024) ===")
        pb = {}
        for s in ("hit", "pit"):
            for Y in range(2014, 2025):
                r = L.evaluate({s: sides[s]}, KIND, origins=(Y,))
                if r:
                    pb[f"{s}{Y}"] = {k: float(r[f"{k}.blend"]) for k in KIND}
        res["per_block"] = pb
        for k in KIND:
            if k == "shipped":
                continue
            d = np.array([v[k] - v["shipped"] for v in pb.values()])
            se = d.std(ddof=1) / np.sqrt(len(d))
            print(f"  {k:11s} mean {d.mean():+.4f} se {se:.4f} t {d.mean()/se:+.2f} "
                  f"signs {int((d>0).sum())}+/{int((d<0).sum())}- nblk={len(d)}")
            res.setdefault("per_block_summary", {})[k] = {
                "mean": float(d.mean()), "se": float(se), "t": float(d.mean() / se),
                "pos": int((d > 0).sum()), "neg": int((d < 0).sum())}
    finally:
        L.anchor = save
    json.dump(res, open(OUT / "_anchor_qfix.json", "w"), indent=1, default=float)
    print("\nelapsed", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
