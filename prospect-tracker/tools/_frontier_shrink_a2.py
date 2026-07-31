# SCRATCH: (a2) the NULL BAND for an alpha-selector change. The shipped selector's
# holdout permutation seed (20260707) is an arbitrary, zero-information choice: any
# other seed is an equally valid selector carrying no extra information. The spread of
# block_rho deltas across seeds is therefore the correct pairing-preserving null band
# against which any "better alpha selection" claim must be judged.
# Run: python tools/_frontier_shrink_a2.py [K]
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _frontier_shrink as fs
from _frontier_shrink import BASE_KEYS, OUT, load_pool, score_records, blend, block_rho

GLOBAL = {"kind": "global"}


def main(K=24):
    t0 = time.time()
    pool = load_pool()
    recs, au = score_records(pool, BASE_KEYS, {"mode": "shipped"})
    base = block_rho(recs, blend(recs, GLOBAL))
    print(f"n={len(recs)}  shipped block_rho={base:.5f}  "
          f"alpha_path={[a for _s,_y,a in au]}", flush=True)

    orig = fs.SHIPPED_SEED
    deltas, paths = [], []
    for i in range(K):
        fs.SHIPPED_SEED = orig + 7919 * (i + 1)      # a different arbitrary holdout draw
        r, a = score_records(pool, BASE_KEYS, {"mode": "shipped"})
        d = block_rho(r, blend(r, GLOBAL)) - base
        deltas.append(d)
        paths.append([x for _s, _y, x in a])
    fs.SHIPPED_SEED = orig

    v = np.array(deltas)
    print(f"\n== NULL BAND: {K} zero-information alpha-selector seeds, real refits ==")
    print(f"  mean {v.mean():+.5f}  sd {v.std(ddof=1):.5f}  min {v.min():+.5f} "
          f"max {v.max():+.5f}  max|d| {np.abs(v).max():.5f}  p95|d| "
          f"{np.percentile(np.abs(v), 95):.5f}")
    print(f"  distinct alpha paths: {len(set(map(tuple, paths)))}/{K}")
    print("  sorted deltas:", np.sort(v).round(5).tolist())

    (OUT / "_scratch_shrink_a2.json").write_text(json.dumps(
        {"K": K, "n": len(recs), "base_block_rho": round(base, 5),
         "deltas": [round(float(x), 5) for x in v],
         "sd": round(float(v.std(ddof=1)), 5),
         "max_abs": round(float(np.abs(v).max()), 5),
         "p95_abs": round(float(np.percentile(np.abs(v), 95)), 5),
         "distinct_paths": len(set(map(tuple, paths)))}, indent=1), encoding="utf-8")
    print("\nwrote", OUT / "_scratch_shrink_a2.json", f"[{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main(K=int(sys.argv[1]) if len(sys.argv) > 1 else 24)
