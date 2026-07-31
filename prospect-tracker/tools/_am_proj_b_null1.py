"""AM-PROJ (b) null band for A1: 10 zero-information twins that drop the same
NUMBER of curve cells at random ages instead of by pair count."""
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

t0 = time.time()
acc = L.score(corpus, by_player, war_actual, L.BASES, ["base", "A1", "A3"],
              np.random.default_rng(7))
p_base = L.pooled(acc["base"])
d_a1 = p_base - L.pooled(acc["A1"])
d_a3 = p_base - L.pooled(acc["A3"])
print(f"base {p_base:.5f} | A1 {d_a1:+.5f} | A3 {d_a3:+.5f}  ({time.time()-t0:.0f}s)")

perm = []
for i in range(NPERM):
    r = np.random.default_rng(5000 + i)
    a = L.score(corpus, by_player, war_actual, L.BASES, ["C1"], r)
    perm.append(p_base - L.pooled(a["C1"]))
    print(f"  C1 perm {i}: {perm[-1]:+.5f}  ({time.time()-t0:.0f}s)")

p = np.asarray(perm)
out = {"base_mae": p_base, "a1_delta": d_a1, "a3_delta": d_a3, "perm": perm,
       "perm_mean": float(p.mean()), "perm_sd": float(p.std(ddof=1)),
       "perm_p05": float(np.percentile(p, 5)),
       "perm_p95": float(np.percentile(p, 95)),
       "a1_beats_perm_frac": float((d_a1 > p).mean())}
print(json.dumps({k: v for k, v in out.items() if k != "perm"}, indent=1))
json.dump(out, open(ROOT / "tools" / "_am_proj_out_aging_null1.json", "w"), indent=1)
