# SCRATCH: paired cohort-stratified REFIT bootstrap for the ablation audit.
# Resamples players with replacement WITHIN (side, decision_year) over the WHOLE pool
# (train AND test), refits every arm on the same replicate, stores each arm's block-rho.
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from _frontier_ablate import load_side, score_side, block_rho, OUT, SEED
from _frontier_ablate_arms import arms_for

B = int(sys.argv[1]) if len(sys.argv) > 1 else 500
D = {s: load_side(s) for s in ("hit", "pit")}
ARMS = {}
for s in ("hit", "pit"):
    A = arms_for(s)
    ARMS[s] = {n: np.array([D[s]["idx"][k] for k in ks]) for n, ks in A.items()}

STRATA = {}
for s in ("hit", "pit"):
    dy = D[s]["dy"]
    STRATA[s] = [np.flatnonzero(dy == v) for v in np.unique(dy)]


def one(sel):
    """sel: {side: index array}. Returns {side: {arm: (rho_side, records)}}"""
    rec = {}
    for s in ("hit", "pit"):
        rec[s] = {}
        for n, cols in ARMS[s].items():
            r = score_side(D[s], cols, sel=sel[s])
            rec[s][n] = r
    out = {}
    for s in ("hit", "pit"):
        o = "pit" if s == "hit" else "hit"
        bo = rec[o]["base"]
        out[s] = {}
        for n, r in rec[s].items():
            if r is None:
                out[s][n] = (float("nan"), float("nan"))
                continue
            out[s][n] = (block_rho([(s,) + r]),
                         block_rho([(s,) + r, (o,) + bo]) if bo is not None else float("nan"))
    return out


rng = np.random.default_rng(SEED)
store = {s: {n: [] for n in ARMS[s]} for s in ("hit", "pit")}
t0 = time.time()
# replicate 0 = the point estimate (full sample)
for b in range(B + 1):
    if b == 0:
        sel = {s: np.arange(len(D[s]["y"])) for s in ("hit", "pit")}
    else:
        sel = {s: np.concatenate([rng.choice(ix, size=len(ix), replace=True)
                                  for ix in STRATA[s]]) for s in ("hit", "pit")}
    r = one(sel)
    for s in ("hit", "pit"):
        for n, v in r[s].items():
            store[s][n].append(v)
    if b % 50 == 0:
        print(b, round(time.time() - t0, 1), "s", flush=True)

json.dump({s: {n: v for n, v in store[s].items()} for s in ("hit", "pit")},
          open(OUT / "_ablate_boot.json", "w"))
print("done", B, round(time.time() - t0, 1), "s")
