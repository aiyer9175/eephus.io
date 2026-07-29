# SCRATCH: HONEST leaner-model test. Greedy backward elimination is run on 4 of the 5
# origins and the resulting lean set is scored ONLY on the held-out origin (leave-one-
# origin-out selection). Guards against selecting the lean set on the same folds that
# score it. Also reports the in-sample (all-5-origin) greedy result for contrast.
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import _frontier_ablate as FA
from _frontier_ablate import load_side, score_side, rho, block_rho, OUT, ORIGINS

D = {s: load_side(s) for s in ("hit", "pit")}


def per_origin(D_, keys, origins):
    cols = np.array([D_["idx"][k] for k in keys])
    r = score_side(D_, cols, origins=origins)
    if r is None:
        return {}
    b, p, t = r
    return {int(y): rho(p[b == y], t[b == y]) for y in np.unique(b)}


def greedy(D_, sel_origins, min_keep=1, max_drop=8):
    keys = list(D_["keys"])
    cur = per_origin(D_, keys, sel_origins)
    cur_score = float(np.mean([cur[y] for y in sel_origins if y in cur]))
    dropped = []
    for _ in range(max_drop):
        best = None
        for k in keys:
            if k == "fv" or len(keys) <= min_keep + 1:
                continue
            cand = [x for x in keys if x != k]
            po = per_origin(D_, cand, sel_origins)
            sc = float(np.mean([po[y] for y in sel_origins if y in po]))
            if best is None or sc > best[0]:
                best = (sc, k)
        if best is None or best[0] <= cur_score:
            break
        cur_score, k = best
        keys = [x for x in keys if x != k]
        dropped.append(k)
    return keys, dropped, cur_score


out = {}
for s in ("hit", "pit"):
    D_ = D[s]
    full = per_origin(D_, list(D_["keys"]), ORIGINS)
    loo = []
    for Y in ORIGINS:
        sel = tuple(y for y in ORIGINS if y != Y)
        lean, dropped, sc = greedy(D_, sel)
        held = per_origin(D_, lean, ORIGINS)
        loo.append({"held_out": Y, "dropped": dropped, "lean_n": len(lean),
                    "rho_full_heldout": full[Y], "rho_lean_heldout": held[Y],
                    "delta_heldout": held[Y] - full[Y]})
        print(s, Y, "drop", dropped, "d_heldout %+.4f" % (held[Y] - full[Y]), flush=True)
    ins_lean, ins_drop, _ = greedy(D_, ORIGINS)
    ins = per_origin(D_, ins_lean, ORIGINS)
    out[s] = {"loo": loo, "insample_lean": ins_lean, "insample_dropped": ins_drop,
              "insample_delta_mean": float(np.mean([ins[y] - full[y] for y in ORIGINS])),
              "loo_delta_mean": float(np.mean([x["delta_heldout"] for x in loo])),
              "loo_delta_se": float(np.std([x["delta_heldout"] for x in loo], ddof=1) / np.sqrt(5))}
    print(s, "LOO mean %+.4f se %.4f | in-sample greedy %+.4f drops %s"
          % (out[s]["loo_delta_mean"], out[s]["loo_delta_se"],
             out[s]["insample_delta_mean"], ins_drop), flush=True)

json.dump(out, open(OUT / "_ablate_lean.json", "w"), indent=1)
