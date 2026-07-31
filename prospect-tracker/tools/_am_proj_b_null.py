"""AM-PROJ (b) null band: 10 independent zero-information twins of A2.

Each C2 draw applies the SAME monotone-tail edit magnitudes at a random
permutation of the same curve's ages. The spread of these is the permutation
null band the A2 effect must clear.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import fa_projection as fp  # noqa: E402
import _am_proj_b_aging as L  # noqa: E402

corpus = fp.build_corpus()
by_player, war_actual = L.index_corpus(corpus)
NPERM = int(sys.argv[1]) if len(sys.argv) > 1 else 10

rng = np.random.default_rng(90210)
t0 = time.time()
acc = L.score(corpus, by_player, war_actual, L.BASES, ["base", "A2"], rng)
p_base = L.pooled(acc["base"])
d_a2 = p_base - L.pooled(acc["A2"])
print(f"base MAE {p_base:.5f} | A2 delta {d_a2:+.5f}  ({time.time()-t0:.0f}s)")

perm = []
for i in range(NPERM):
    r = np.random.default_rng(1000 + i)
    a = L.score(corpus, by_player, war_actual, L.BASES, ["C2"], r)
    perm.append(p_base - L.pooled(a["C2"]))
    print(f"  perm {i}: {perm[-1]:+.5f}  ({time.time()-t0:.0f}s)")

p = np.asarray(perm)
out = {"base_mae": p_base, "a2_delta": d_a2, "perm": perm,
       "perm_mean": float(p.mean()), "perm_sd": float(p.std(ddof=1)),
       "perm_p95": float(np.percentile(p, 95)),
       "perm_p05": float(np.percentile(p, 5)),
       "a2_beats_perm_frac": float((d_a2 > p).mean())}
print(json.dumps({k: v for k, v in out.items() if k != "perm"}, indent=1))
json.dump(out, open(ROOT / "tools" / "_am_proj_out_aging_null.json", "w"), indent=1)
