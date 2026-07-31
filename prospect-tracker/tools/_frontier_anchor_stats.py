# SCRATCH: Level-1 anchor statistics -- paired refit bootstrap + null bands + cross-split.
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import _frontier_anchor as A

OUT = Path(__file__).resolve().parent / "_frontier_out"
OUT.mkdir(exist_ok=True)
ORIGINS = tuple(range(2020, 2025))
B_BOOT = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
B_NULL = int(sys.argv[2]) if len(sys.argv) > 2 else 500

KINDS = ["shipped", "affine_twin", "plain_mean", "shift_only", "scale_only",
         "zmap", "qmap", "warcal", "warcal_prec", "rho_vote"]


# --- extra anchor variants (decomposition of zmap) -------------------------
_orig_apply = A.apply_anchor


def apply2(kind, P, te, weights=None):
    cons, fg, mp = te["cons"], te["fg"], te["mp"]
    n = len(cons)
    if kind == "shift_only":          # remove per-source LEVEL bias only
        zs = []
        for k, arr in (("fg", fg), ("mp", mp)):
            mo = P[f"mom_{k}"]
            zs.append(arr - mo[0] if mo else np.full(n, np.nan))
        cm = P["cons_mom"]
        return A._combine(cons - cm[0] if cm else cons, zs, [1.0, 1.0])
    if kind == "scale_only":          # remove per-source SPREAD difference only
        zs = []
        for k, arr in (("fg", fg), ("mp", mp)):
            mo = P[f"mom_{k}"]
            zs.append(arr / mo[1] if mo else np.full(n, np.nan))
        cm = P["cons_mom"]
        return A._combine(cons / cm[1] if cm else cons, zs, [1.0, 1.0])
    return _orig_apply(kind, P, te, weights=weights)


A.apply_anchor = apply2


# --- helpers ---------------------------------------------------------------
def sides_arrays():
    return {s: A.to_arrays(A.load_rows(s, "debuted_km")) for s in ("hit", "pit")}


def strata(sides):
    """index lists per (side, decision_year) over the WHOLE pool."""
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
        out[s] = {k: (v[ii] if isinstance(v, np.ndarray) else v) for k, v in a.items()
                  if isinstance(v, np.ndarray)}
        out[s]["n"] = len(ii)
    return out


def run(sides, kinds, **kw):
    r = A.fwd_anchor(kinds, sides, ORIGINS, **kw)
    if r is None:
        return None
    preds, tgt, _blk = r
    return {k: A.spear(preds[k], tgt) for k in kinds}


def main():
    t0 = time.time()
    sides = sides_arrays()
    st = strata(sides)
    res = {}

    # ---------------- point estimates
    pt = run(sides, KINDS)
    print("=== POINT (pooled block-percentile Spearman vs realized WAR, n=1001) ===")
    for k in KINDS:
        print(f"  {k:13s} rho {pt[k]:.4f}  delta {pt[k]-pt['shipped']:+.4f}")
    res["point"] = pt

    # what the fitted per-source corrections actually are (full pool, for the record)
    allrows = {s: sides[s] for s in sides}
    for s in ("hit", "pit"):
        a = sides[s]
        tr = {k: v for k, v in a.items() if isinstance(v, np.ndarray)}
        P = A.fit_anchor(tr)
        print(f"  [{s}] FG mom {P['mom_fg']} MP mom {P['mom_mp']} | "
              f"FG ols {tuple(round(v,4) for v in P['ols_fg'])} "
              f"MP ols {tuple(round(v,4) for v in P['ols_mp'])} | "
              f"rho_fg {P['rho_fg']:.4f} rho_mp {P['rho_mp']:.4f}")
        res.setdefault("fitted", {})[s] = {
            "mom_fg": P["mom_fg"], "mom_mp": P["mom_mp"],
            "ols_fg": P["ols_fg"], "ols_mp": P["ols_mp"],
            "rho_fg": P["rho_fg"], "rho_mp": P["rho_mp"],
            "prec_w_fg": 1.0 / P["ols_fg"][2], "prec_w_mp": 1.0 / P["ols_mp"][2]}

    # ---------------- paired refit bootstrap
    print(f"\n=== PAIRED BOOTSTRAP (resample WHOLE pool within (side,dy), refit), B={B_BOOT} ===")
    rng = np.random.default_rng(A.SEED)
    draws = {k: [] for k in KINDS}
    for b in range(B_BOOT):
        sb = resample(sides, st, rng)
        r = run(sb, KINDS)
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
        boot[k] = {
            "point": pt[k] - pt["shipped"], "mean": float(d.mean()), "sd": float(d.std(ddof=1)),
            "lo": float(np.percentile(d, 2.5)), "hi": float(np.percentile(d, 97.5)),
            "p_gt0": float((d > 0).mean()), "B": int(len(d)),
            "mde95": float(1.645 * d.std(ddof=1)),
        }
        print(f"  {k:13s} point {boot[k]['point']:+.4f}  boot mean {boot[k]['mean']:+.4f} "
              f"sd {boot[k]['sd']:.4f} CI95 [{boot[k]['lo']:+.4f},{boot[k]['hi']:+.4f}] "
              f"P(>0)={boot[k]['p_gt0']:.3f} MDE95 {boot[k]['mde95']:.4f}")
    res["bootstrap"] = boot
    # arm-level sd for reference
    res["arm_sd"] = {k: float(D[k].std(ddof=1)) for k in KINDS}
    print("  arm-level sd (unpaired, for reference): " +
          " ".join(f"{k}={D[k].std(ddof=1):.4f}" for k in ("shipped", "zmap", "warcal")))

    json.dump(res, open(OUT / "_anchor_stats.json", "w"), indent=1, default=float)
    print("\nelapsed", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
