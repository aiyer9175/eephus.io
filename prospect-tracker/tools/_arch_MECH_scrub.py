# SCRATCH: LEAK-SCRUB. `no_track` (= no MiLB block) is 94-96% identical to
# "no resolved mlbam_id", and in the 2020+ folds an unresolved-id row debuts
# 1.3-1.9% of the time vs 59-72% for track rows. So ANY arm that can sense
# missingness is handed a near-deterministic proxy for the debut/no-debut AUC
# label. This script re-runs every arm on a pool restricted to modern decision
# years (where the 2014 StatsAPI cache floor no longer forces missingness) and
# reports AUC on the track-record population only.
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
MINY = int(sys.argv[2]) if len(sys.argv) > 2 else 2017
FOLDS = (2020, 2021, 2022, 2023, 2024)

keys, _ = E._feature_spec(SIDE)
axes = M.ARCH_AXES[SIDE]
data = [d for d in M.load(SIDE, "production") if d["decision_year"] >= MINY]
D = M.arrays(data, keys, axes)
lam = E.blend_lambda(SIDE)
MILB_KEYS = {"level_rank", "n_milb_seasons", "ops_rel", "obp_rel", "k_rel",
             "peak_k_rel", "age_rel_level", "age", "bb_rel", "era_rel", "x_era_k"}
CTX = {"milb_cols": [i for i, k in enumerate(keys) if k in MILB_KEYS],
       "comp_axes": D["A"], "knn_k": 20, "k": 6, "seed": 11,
       "thin_cut": None, "omega": None}
MET = ("rho", "block_rho", "t45", "auc", "mae", "brier")
INV = ("mae", "brier")

print(f"{SIDE} pool>={MINY}: n={len(data)} track={int(D['tr'].sum())} "
      f"({100*D['tr'].mean():.1f}%) folds={FOLDS} lam={lam}")

b = M.run_arm("BASE", D, FOLDS, lam, rng=np.random.default_rng(5), ctx=dict(CTX))
base, bt = M.score_arm(b), M.score_arm(b, True)
print(f"BASE  full n={base['n']} rho={base['rho']:.4f} blk={base['block_rho']:.4f} "
      f"t45={base['t45']:.4f} auc={base['auc']:.4f} mae={base['mae']:.4f}")
print(f"BASE  track-only n={bt['n']} rho={bt['rho']:.4f} auc={bt['auc']:.4f} "
      f"mae={bt['mae']:.4f}")
print(f"\n{'arm':<16}" + " ".join(f"{m:>9}" for m in MET)
      + "  ||  TRACK-ONLY " + " ".join(f"{m:>9}" for m in MET))
for arm in ("E1_STD_TR", "E1_CTRL", "E2_NOTRACK", "E2_CTRL", "E2X_INTERACT",
            "E3_TR_ONLY", "E3_CTRL", "M1_ARCH", "M1_CTRL", "M1B_DIST", "M1B_CTRL",
            "M2_COMP", "M2_CTRL", "M3_CONDCAL", "M3_CTRL", "M4_SHRINK", "M4_CTRL"):
    r = M.run_arm(arm, D, FOLDS, lam, rng=np.random.default_rng(5), ctx=dict(CTX))
    s, st = M.score_arm(r), M.score_arm(r, True)
    if s is None:
        print(f"{arm:<16} -- none --"); continue
    def f(a, bb, m):
        if a is None or a[m] != a[m] or bb[m] != bb[m]:
            return "     nan "
        d = (bb[m] - a[m]) if m in INV else (a[m] - bb[m])
        return f"{d:+9.4f}"
    print(f"{arm:<16}" + " ".join(f(s, base, m) for m in MET) + "  ||             "
          + " ".join(f(st, bt, m) for m in MET))
