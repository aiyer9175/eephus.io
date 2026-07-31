# SCRATCH driver for tools/_arch_MECH.py -- point estimates for every arm.
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                     # noqa: E402
import _arch_MECH as M                    # noqa: E402

SIDE = sys.argv[1] if len(sys.argv) > 1 else "hit"
K = int(sys.argv[2]) if len(sys.argv) > 2 else 6

keys, _mono = E._feature_spec(SIDE)
axes = M.ARCH_AXES[SIDE]
data = M.load(SIDE, "production")
D = M.arrays(data, keys, axes)
lam = E.blend_lambda(SIDE)

# milb-block columns inside the production key set (for the E2X interaction arm)
MILB_KEYS = {"level_rank", "n_milb_seasons", "ops_rel", "obp_rel", "k_rel",
             "peak_k_rel", "age_rel_level", "age", "bb_rel", "era_rel", "x_era_k"}
milb_cols = [i for i, k in enumerate(keys) if k in MILB_KEYS]

ctx = {"k": K, "milb_cols": milb_cols, "comp_axes": D["A"], "knn_k": 20,
       "seed": 11, "thin_cut": None, "omega": None}

print(f"side={SIDE} n={len(data)} track={int(D['tr'].sum())} "
      f"({100*D['tr'].mean():.1f}%) lam={lam} k={K} keys={len(keys)}", flush=True)

ARMS = ["BASE",
        "E1_STD_TR", "E1_CTRL", "E2_NOTRACK", "E2_CTRL", "E2X_INTERACT",
        "E3_TR_ONLY", "E3_CTRL",
        "M1_ARCH", "M1_CTRL", "M1B_DIST", "M1B_CTRL",
        "M2_COMP", "M2_CTRL",
        "M3_CONDCAL", "M3_CTRL",
        "M4_SHRINK", "M4_CTRL"]

for foldset, tag in ((M.FOLDS, "6fold"), (M.SHIPPED_FOLDS, "4fold")):
    print(f"\n===== {tag} folds {foldset} =====")
    base_p = base_t = None
    rows = []
    for arm in ARMS:
        rng = np.random.default_rng(2026)
        t0 = time.time()
        res = M.run_arm(arm, D, foldset, lam, rng=rng, ctx=dict(ctx))
        s_all = M.score_arm(res, tr_only=False)
        s_tr = M.score_arm(res, tr_only=True)
        if arm == "BASE":
            base_p, base_t = s_all, s_tr
        def d(a, b, k):
            if a is None or b is None or a.get(k) is None:
                return float("nan")
            return a[k] - b[k]
        rows.append((arm, s_all, s_tr, time.time() - t0))
    hdr = (f"{'arm':<14}{'n':>5}  {'rho':>8}{'drho':>9} {'blk':>8}{'dblk':>9} "
           f"{'t45':>8}{'dt45':>9} {'auc':>8}{'dauc':>9} || TRACK-ONLY "
           f"{'rho':>8}{'drho':>9} {'t45':>8}{'dt45':>9} {'auc':>8}{'dauc':>9}")
    print(hdr)
    for arm, s, st, el in rows:
        if s is None:
            print(f"{arm:<14} -- no result --"); continue
        def f(v):
            return "  nan  " if v != v else f"{v:+.4f}"
        def g(v):
            return "  nan " if v != v else f"{v:.4f}"
        dr = {k: (s[k] - base_p[k]) for k in ("rho", "block_rho", "t45", "auc")}
        if st is not None and base_t is not None:
            dt = {k: (st[k] - base_t[k]) for k in ("rho", "block_rho", "t45", "auc")}
        else:
            dt = {k: float("nan") for k in ("rho", "block_rho", "t45", "auc")}
        print(f"{arm:<14}{s['n']:>5}  {g(s['rho'])}{f(dr['rho'])} "
              f"{g(s['block_rho'])}{f(dr['block_rho'])} "
              f"{g(s['t45'])}{f(dr['t45'])} {g(s['auc'])}{f(dr['auc'])} || "
              f"{st['n'] if st else 0:>5} {g(st['rho']) if st else ''}{f(dt['rho'])} "
              f"{g(st['t45']) if st else ''}{f(dt['t45'])} "
              f"{g(st['auc']) if st else ''}{f(dt['auc'])}  [{el:.1f}s]")
