"""Lane: prospect. (e) LEAK-SCRUBBED re-test of the Pipeline ETA against our champion.

The archive serves ONE frozen eta per player replayed onto every vintage slug
(250/250 multi-board players never move; MAE IMPROVES with forecast horizon).
The only rows where that frozen value cannot be a look-ahead are the ones where
the vintage is the player's ONLY board appearance in the whole archive
(2015-2026) -- there is no later board for the value to have come from.
"""
import json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "data"
import eta_backtest as eb

pv = json.loads((D / "pipeline_vintages.json").read_text(encoding="utf-8"))["vintages"]
byp = defaultdict(dict)
for y, recs in pv.items():
    for r in recs:
        if r.get("mlbam"):
            byp[int(r["mlbam"])][int(y)] = r
pipe = {(int(r["mlbam"]), int(y)): int(str(r["eta"])[:4])
        for y, recs in pv.items() for r in recs
        if r.get("mlbam") and r.get("eta") not in (None, "None", "")}

rows, _ = eb.build_cohort()
listings, cs, bio, debut_year, ident = eb._load_inputs()
mlbam = {k: int(v["mlbam"]) for k, v in ident.items() if v.get("mlbam")}
J = []
for r in rows:
    if r["outcome"] != "debuted" or r["actual"] is None:
        continue
    m = mlbam.get(r["player_key"])
    if m is None or (m, r["vintage"]) not in pipe:
        continue
    boards = sorted(byp[m])
    J.append(dict(vy=r["vintage"], actual=r["actual"], ours=r["pred"],
                  pipe=pipe[(m, r["vintage"])], m=m, nboards=len(boards),
                  only=len(boards) == 1, h=r["actual"] - r["vintage"]))

def mae(sel, key):
    return float(np.mean([abs(j[key] - j["actual"]) for j in sel]))
def w1(sel, key):
    return float(np.mean([abs(j[key] - j["actual"]) <= 1 for j in sel]))

print("all joined rows          n=%4d  ours %.3f  pipeline %.3f  d=%+.3f"
      % (len(J), mae(J, "ours"), mae(J, "pipe"), mae(J, "pipe") - mae(J, "ours")))
clean = [j for j in J if j["only"]]
print("SINGLE-BOARD (leak-free) n=%4d  ours %.3f  pipeline %.3f  d=%+.3f"
      % (len(clean), mae(clean, "ours"), mae(clean, "pipe"),
         mae(clean, "pipe") - mae(clean, "ours")))
print("  within-1y: ours %.3f  pipeline %.3f" % (w1(clean, "ours"), w1(clean, "pipe")))
print("  mean horizon on the clean slice: %.2f yr" % np.mean([j["h"] for j in clean]))
print("  by vintage:", {v: sum(1 for j in clean if j["vy"] == v)
                        for v in sorted({j["vy"] for j in clean})})

if len(clean) >= 60:
    rng = np.random.default_rng(20260725)
    o = np.array([j["ours"] for j in clean], float)
    p = np.array([j["pipe"] for j in clean], float)
    a = np.array([j["actual"] for j in clean], float)
    n = len(clean)
    d = np.empty(4000)
    for i in range(4000):
        ix = rng.integers(0, n, n)
        d[i] = np.mean(np.abs(p[ix] - a[ix])) - np.mean(np.abs(o[ix] - a[ix]))
    lo, hi = np.percentile(d, [2.5, 97.5])
    print("\n  PAIRED BOOTSTRAP dMAE (pipeline - ours), leak-free slice, B=4000")
    print(f"   obs={np.mean(np.abs(p-a))-np.mean(np.abs(o-a)):+.4f} mean={d.mean():+.4f} "
          f"sd={d.std():.4f} CI95=[{lo:+.4f},{hi:+.4f}] P(better)={float((d<0).mean()):.3f} "
          f"MDE95={1.96*d.std():.4f}")
    pp = p.copy(); rng.shuffle(pp)
    print(f"   ZERO-INFO CONTROL permuted pipeline MAE={np.mean(np.abs(pp-a)):.3f}")
    nl = np.array([np.mean(np.abs(p[rng.permutation(n)] - a)) - np.mean(np.abs(o - a))
                   for _ in range(2000)])
    print(f"   PERMUTATION NULL dMAE mean={nl.mean():+.4f} "
          f"CI95=[{np.percentile(nl,2.5):+.4f},{np.percentile(nl,97.5):+.4f}]")
    print("\n  PER-VINTAGE on the leak-free slice")
    for v in sorted({j["vy"] for j in clean}):
        s = [j for j in clean if j["vy"] == v]
        if len(s) < 12:
            print(f"   {v} n={len(s):3d}  (below reporting n)")
            continue
        print(f"   {v} n={len(s):3d} ours={mae(s,'ours'):.3f} pipeline={mae(s,'pipe'):.3f} "
              f"d={mae(s,'pipe')-mae(s,'ours'):+.3f}")
else:
    print("\n  leak-free slice too small to gate (n<60) - UNAVAILABLE")
