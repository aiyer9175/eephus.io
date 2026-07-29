"""ADVERSARIAL VERIFY v1: re-derive claim A2 (eFV-as-displayed beats consensus FV at
ordering realized career WAR) from scratch, then probe it for in-sample leakage.

Nothing is written. persist-free by construction (read-only).
"""
import json, random, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def spearman(xs, ys):
    n = len(xs)
    if n < 3: return None
    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0]*n; i = 0
        while i < n:
            j = i
            while j+1 < n and v[order[j+1]] == v[order[i]]: j += 1
            avg = (i+j)/2 + 1
            for k in range(i, j+1): r[order[k]] = avg
            i = j+1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx = sum(rx)/n; my = sum(ry)/n
    cov = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
    vx = sum((a-mx)**2 for a in rx); vy = sum((b-my)**2 for b in ry)
    if vx == 0 or vy == 0: return None
    return cov/math.sqrt(vx*vy)

by = json.loads((ROOT/"data/xfv.json").read_text(encoding="utf-8"))["by_player"]
fitted = set()
for f in ("data/xfv_scored.json", "data/xfv_scored_pitcher.json"):
    for r in json.loads((ROOT/f).read_text(encoding="utf-8")):
        fitted.add(r["player_key"])

COLS = ["xfv_grade_quantile", "xfv_war_6yr", "xfv_grade_model_raw", "surplus_mm", "consensus_fv"]
rows = []
for pk, v in by.items():
    if v.get("kind") not in ("debuted", "resolved", "graduated"): continue
    if v.get("realized_war") is None: continue
    if any(v.get(c) is None for c in COLS): continue
    rows.append((pk, [float(v[c]) for c in COLS], float(v["realized_war"]),
                 pk in fitted))
print("pool n =", len(rows), " in-sample rows =", sum(1 for r in rows if r[3]),
      " out-of-sample rows =", sum(1 for r in rows if not r[3]))

def rhos(sub):
    y = [r[2] for r in sub]
    return {c: spearman([r[1][i] for r in sub], y) for i, c in enumerate(COLS)}

def report(label, sub, B=4000, seed=11):
    if len(sub) < 60:
        print(f"  {label}: n={len(sub)} BELOW n>=60 reporting bar -> UNAVAILABLE"); return
    rr = rhos(sub)
    print(f"\n[{label}] n={len(sub)}")
    for c in COLS: print(f"    {c:24s} {rr[c]:+.4f}")
    # paired bootstrap of quantile - consensus (resampling the same rows for both)
    rnd = random.Random(seed)
    n = len(sub); iq = COLS.index("xfv_grade_quantile"); ic = COLS.index("consensus_fv")
    diffs = []
    for _ in range(B):
        idx = [rnd.randrange(n) for _ in range(n)]
        s = [sub[i] for i in idx]
        y = [r[2] for r in s]
        a = spearman([r[1][iq] for r in s], y)
        b = spearman([r[1][ic] for r in s], y)
        if a is not None and b is not None: diffs.append(a-b)
    diffs.sort()
    obs = rr["xfv_grade_quantile"] - rr["consensus_fv"]
    m = sum(diffs)/len(diffs)
    sd = (sum((d-m)**2 for d in diffs)/(len(diffs)-1))**0.5
    lo = diffs[int(0.025*len(diffs))]; hi = diffs[int(0.975*len(diffs))]
    pgt = sum(1 for d in diffs if d > 0)/len(diffs)
    print(f"    quantile - consensus: obs {obs:+.4f} sd {sd:.4f} "
          f"CI95 [{lo:+.4f},{hi:+.4f}] P(>0)={pgt:.3f} MDE95(1.96sd)={1.96*sd:.4f}")
    # zero-information control: row-permuted twin of the SAME column
    rnd2 = random.Random(seed+1)
    perm = [r[1][iq] for r in sub]; rnd2.shuffle(perm)
    print(f"    zero-info control (permuted quantile): "
          f"{spearman(perm, [r[2] for r in sub]):+.4f}")
    return obs

full = [r for r in rows]
ins  = [r for r in rows if r[3]]
oos  = [r for r in rows if not r[3]]
o_full = report("FULL POOL (what the lane reported)", full)
o_in   = report("IN-SAMPLE subset (ridge was FIT on these rows' labels)", ins)
o_out  = report("HELD-OUT subset (not in the production fit)", oos)

print("\nLEAK DECOMPOSITION")
print(f"  delta on rows the model was fit on : {o_in:+.4f}" if o_in is not None else "")
print(f"  delta on rows it was NOT fit on    : {o_out:+.4f}" if o_out is not None else "")
