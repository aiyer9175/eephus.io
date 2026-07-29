# SCRATCH: dimensionality-matched ZERO-INFORMATION null band. For each group size k,
# draw k fresh N(0,1) columns, append to the shipped set, refit, and record the block-rho
# movement. This is the correct reference for a "drop k real columns" ablation delta.
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from _frontier_ablate import load_side, score_side, block_rho, OUT, SEED, ORIGINS

DRAWS = 200
KS = (1, 2, 3, 4, 7, 8, 13)
D = {s: load_side(s) for s in ("hit", "pit")}
out = {}
rng = np.random.default_rng(SEED + 99)
for s in ("hit", "pit"):
    D_ = D[s]
    nk = len(D_["keys"])
    base = block_rho([(s,) + score_side(D_, np.arange(nk))])
    n = len(D_["y"])
    out[s] = {"base": base}
    for k in KS:
        vals = []
        for _ in range(DRAWS):
            Z = rng.standard_normal((n, k))
            D2 = dict(D_)
            D2["X"] = np.column_stack([D_["X"], Z])
            cols = np.concatenate([np.arange(nk), np.arange(k) + D_["X"].shape[1]])
            r = score_side(D2, cols)
            vals.append(base - block_rho([(s,) + r]))
        vals = np.array(vals)
        out[s]["k%d" % k] = {"mean": float(vals.mean()), "sd": float(vals.std(ddof=1)),
                             "p95_abs": float(np.percentile(np.abs(vals), 95)),
                             "max_abs": float(np.abs(vals).max())}
        print(s, "k=%d" % k, "mean %+.4f sd %.4f p95|%.4f| max|%.4f|"
              % (vals.mean(), vals.std(ddof=1), np.percentile(np.abs(vals), 95),
                 np.abs(vals).max()), flush=True)
json.dump(out, open(OUT / "_ablate_null.json", "w"), indent=1)
