# SCRATCH: (1) ridge alpha-holdout SEED sensitivity of every ablation delta,
#          (2) per-(side,origin) sign stability, (3) wider-origin-window robustness read.
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import _frontier_ablate as FA
from _frontier_ablate import load_side, score_side, block_rho, rho, OUT
from _frontier_ablate_arms import arms_for

D = {s: load_side(s) for s in ("hit", "pit")}
ARMS = {s: {n: np.array([D[s]["idx"][k] for k in ks]) for n, ks in arms_for(s).items()}
        for s in ("hit", "pit")}


def deltas(origins, seed):
    FA.RIDGE_SEED[0] = seed
    rec = {s: {n: score_side(D[s], c, origins=origins) for n, c in ARMS[s].items()}
           for s in ("hit", "pit")}
    out = {}
    for s in ("hit", "pit"):
        base = rec[s]["base"]
        bs = block_rho([(s,) + base])
        out[s] = {n: bs - block_rho([(s,) + r]) for n, r in rec[s].items() if r is not None}
    return out, rec


# ---- (1) seed sensitivity ------------------------------------------------
SEEDS = [20260707, 11, 202, 3033, 40404, 555555, 7, 88, 909, 12345]
acc = {s: {} for s in ("hit", "pit")}
for sd in SEEDS:
    d, _ = deltas(FA.ORIGINS, sd)
    for s in ("hit", "pit"):
        for n, v in d[s].items():
            acc[s].setdefault(n, []).append(v)
FA.RIDGE_SEED[0] = 20260707

# ---- (2) per-(side,origin) sign stability at the shipped seed -------------
_, rec = deltas(FA.ORIGINS, 20260707)
perblock = {s: {} for s in ("hit", "pit")}
for s in ("hit", "pit"):
    bb, bp, bt = rec[s]["base"]
    for n, r in rec[s].items():
        if r is None:
            continue
        ab, ap, at = r
        row = []
        for yr in np.unique(bb):
            m = bb == yr
            row.append(rho(bp[m], bt[m]) - rho(ap[m], at[m]))
        perblock[s][n] = row

# ---- (3) wider origin windows -------------------------------------------
wide = {}
for w, org in (("2020_24", (2020, 2021, 2022, 2023, 2024)),
               ("2018_24", tuple(range(2018, 2025))),
               ("2016_24", tuple(range(2016, 2025)))):
    d, _ = deltas(org, 20260707)
    wide[w] = d

json.dump({"seed_sens": {s: {n: v for n, v in acc[s].items()} for s in ("hit", "pit")},
           "perblock": perblock, "wide": wide, "seeds": SEEDS},
          open(OUT / "_ablate_stab.json", "w"))
print("done")
