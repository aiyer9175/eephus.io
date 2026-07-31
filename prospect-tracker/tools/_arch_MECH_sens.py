# SCRATCH: archetype-mechanism SENSITIVITY sweep -- k, seed, arch_mode, knn_k.
# Every candidate is printed BESIDE its zero-information twin. The decision
# quantity is CANDIDATE MINUS CONTROL, never the candidate alone.
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                     # noqa: E402
import _arch_MECH as M                    # noqa: E402

SIDE = sys.argv[1] if len(sys.argv) > 1 else "hit"
keys, _ = E._feature_spec(SIDE)
axes = M.ARCH_AXES[SIDE]
data = M.load(SIDE, "production")
D = M.arrays(data, keys, axes)
lam = E.blend_lambda(SIDE)
MILB_KEYS = {"level_rank", "n_milb_seasons", "ops_rel", "obp_rel", "k_rel",
             "peak_k_rel", "age_rel_level", "age", "bb_rel", "era_rel", "x_era_k"}
milb_cols = [i for i, k in enumerate(keys) if k in MILB_KEYS]
BASECTX = {"milb_cols": milb_cols, "comp_axes": D["A"], "knn_k": 20, "k": 6,
           "seed": 11, "thin_cut": None, "omega": None}
MET = ("rho", "block_rho", "t45", "auc", "mae", "brier")


def run(arm, ctx, folds, seed=2026):
    return M.run_arm(arm, D, folds, lam, rng=np.random.default_rng(seed), ctx=dict(ctx))


def sc(res, tr_only=False):
    return M.score_arm(res, tr_only=tr_only)


def line(name, s, base, st, bt):
    def f(v, b, inv=False):
        if s is None or v != v or b != b:
            return "   nan  "
        d = (b - v) if inv else (v - b)
        return f"{d:+.4f}"
    return (f"{name:<26}"
            + " ".join(f(s[k], base[k], inv=k in ("mae", "brier")) for k in MET)
            + "  ||  "
            + " ".join(f(st[k], bt[k], inv=k in ("mae", "brier")) if st and bt else "   nan  "
                       for k in MET))


for folds, ftag in ((M.FOLDS, "6fold"), (M.SHIPPED_FOLDS, "4fold")):
    b = run("BASE", BASECTX, folds)
    base, bt = sc(b), sc(b, True)
    print(f"\n########## {SIDE} {ftag}  BASE rho={base['rho']:.4f} blk={base['block_rho']:.4f} "
          f"t45={base['t45']:.4f} auc={base['auc']:.4f} mae={base['mae']:.4f} "
          f"brier={base['brier']:.4f} n={base['n']} | track-only n={bt['n']} "
          f"rho={bt['rho']:.4f} auc={bt['auc']:.4f}")
    print(f"{'DELTA vs BASE (higher=better)':<26}" + " ".join(f"{m:>8}" for m in MET)
          + "  ||  TRACK-ONLY " + " ".join(f"{m:>8}" for m in MET))
    for k in (4, 6, 8, 10):
        for seed in (11, 23):
            ctx = dict(BASECTX, k=k, seed=seed)
            for cand, ctrl in (("M1_ARCH", "M1_CTRL"), ("M3_CONDCAL", "M3_CTRL"),
                               ("M4_SHRINK", "M4_CTRL")):
                rc, rk = run(cand, ctx, folds), run(ctrl, ctx, folds)
                sca, scc = sc(rc), sc(rk)
                sta, stc = sc(rc, True), sc(rk, True)
                print(line(f"{cand} k={k} s={seed}", sca, base, sta, bt))
                print(line(f"  ctrl {ctrl}", scc, base, stc, bt))
                # candidate minus control on the same metrics
                if sca and scc:
                    dd = " ".join(f"{(scc[m]-sca[m]) if m in ('mae','brier') else (sca[m]-scc[m]):+.4f}"
                                  for m in MET)
                    ddt = (" ".join(f"{(stc[m]-sta[m]) if m in ('mae','brier') else (sta[m]-stc[m]):+.4f}"
                                    for m in MET) if sta and stc else "")
                    print(f"{'  CAND-MINUS-CTRL':<26}{dd}  ||  {ddt}")
    # semantic archetypes
    ctx = dict(BASECTX, arch_mode="semantic")
    for cand, ctrl in (("M1_ARCH", "M1_CTRL"), ("M3_CONDCAL", "M3_CTRL"),
                       ("M4_SHRINK", "M4_CTRL")):
        rc, rk = run(cand, ctx, folds), run(ctrl, ctx, folds)
        sca, scc, sta, stc = sc(rc), sc(rk), sc(rc, True), sc(rk, True)
        print(line(f"SEM {cand}", sca, base, sta, bt))
        print(line(f"  ctrl SEM {ctrl}", scc, base, stc, bt))
    # comp-blend kNN sweep
    for kk in (10, 20, 40, 80):
        ctx = dict(BASECTX, knn_k=kk)
        rc, rk = run("M2_COMP", ctx, folds), run("M2_CTRL", ctx, folds)
        sca, scc, sta, stc = sc(rc), sc(rk), sc(rc, True), sc(rk, True)
        print(line(f"M2_COMP knn={kk}", sca, base, sta, bt))
        print(line(f"  ctrl M2_CTRL knn={kk}", scc, base, stc, bt))
    # item-E arms
    for arm in ("E1_STD_TR", "E1_CTRL", "E2_NOTRACK", "E2_CTRL", "E2X_INTERACT",
                "E3_TR_ONLY", "E3_CTRL"):
        r = run(arm, BASECTX, folds)
        print(line(arm, sc(r), base, sc(r, True), bt))
