# SCRATCH: PERMUTATION TEST per shipped feature and per feature block.
# H0: the column carries no information. Replace it with a fresh row-permutation of ITSELF
# (identical marginal, zero information, dimensionality unchanged), refit, recompute
# block-rho. p = P(rho_perm >= rho_real) over J draws.
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from _frontier_ablate import load_side, score_side, block_rho, OUT, SEED
from _frontier_ablate_arms import GROUPS

J = 300
D = {s: load_side(s) for s in ("hit", "pit")}
rng = np.random.default_rng(SEED + 4242)
out = {}
for s in ("hit", "pit"):
    D_ = D[s]
    keys = list(D_["keys"])
    nk = len(keys)
    cols = np.arange(nk)
    real = block_rho([(s,) + score_side(D_, cols)])
    n = len(D_["y"])
    tests = {k: [k] for k in keys}
    tests.update({"BLOCK:" + g: fs for g, fs in GROUPS[s].items()})
    out[s] = {"real": real, "J": J, "tests": {}}
    for name, fs in tests.items():
        ix = [keys.index(f) for f in fs]
        vals = []
        X0 = D_["X"]
        for _ in range(J):
            X2 = X0.copy()
            for j in ix:
                X2[:, j] = X0[rng.permutation(n), j]
            D2 = dict(D_); D2["X"] = X2
            vals.append(block_rho([(s,) + score_side(D2, cols)]))
        v = np.array(vals)
        p = float((v >= real).mean())
        out[s]["tests"][name] = {"effect": real - float(v.mean()), "perm_mean": float(v.mean()),
                                 "perm_sd": float(v.std(ddof=1)), "p": p, "k": len(fs)}
        print("%s %-22s effect %+.4f  perm sd %.4f  p=%.3f" %
              (s, name, real - v.mean(), v.std(ddof=1), p), flush=True)
json.dump(out, open(OUT / "_ablate_perm.json", "w"), indent=1)
