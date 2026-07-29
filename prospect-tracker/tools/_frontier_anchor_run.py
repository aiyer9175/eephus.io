# SCRATCH: Level-1 anchor evaluation (anchor vs realized WAR rank), forward-chained.
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import _frontier_anchor as A

ORIGINS = tuple(range(2020, 2025))
KINDS = ["shipped", "affine_twin", "plain_mean", "zmap", "qmap", "warcal", "warcal_prec"]

t0 = time.time()
sides = {s: A.to_arrays(A.load_rows(s, "debuted_km")) for s in ("hit", "pit")}
for s, a in sides.items():
    print(f"{s}: n={a['n']}  origins-in-test="
          f"{sorted(set(int(y) for y in a['dy'] if y in ORIGINS))}")

res = A.fwd_anchor(KINDS, sides, ORIGINS)
preds, tgt, blk = res
print("pooled test n =", len(tgt), " blocks:", len(set(blk.tolist())))
pt = A.score(preds, tgt, KINDS)
print("\n=== POINT ESTIMATES (block-percentile pooled Spearman vs realized WAR) ===")
for k in KINDS:
    print(f"  {k:14s} rho={pt[k]:.4f}   delta_vs_shipped={pt[k]-pt['shipped']:+.4f}")

# per-side / per-origin breakdown
print("\n=== PER SIDE (own origins, own pooling) ===")
for s in ("hit", "pit"):
    r2 = A.fwd_anchor(KINDS, {s: sides[s]}, ORIGINS)
    p2 = A.score(r2[0], r2[1], KINDS)
    print(f"  {s} n={len(r2[1])}: " + " ".join(f"{k}={p2[k]:.4f}" for k in KINDS))

json.dump({"point": {k: pt[k] for k in KINDS}, "n": int(len(tgt))},
          open(Path(__file__).parent / "_frontier_out" / "_anchor_point.json", "w"), indent=1)
print("\nelapsed", round(time.time() - t0, 1), "s")
