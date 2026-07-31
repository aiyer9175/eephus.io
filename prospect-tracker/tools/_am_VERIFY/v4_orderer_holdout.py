"""ADVERSARIAL VERIFY v4: re-run the lane's orderer contrasts (C3/N1/N2) on the
HELD-OUT subset (rows the production ridge was NOT fit on), which is the only
place the contrast is not measured on its own training labels. Read-only."""
import json, math, random
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def spearman(xs, ys):
    n = len(xs)
    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i]); r = [0.0]*n; i = 0
        while i < n:
            j = i
            while j+1 < n and v[order[j+1]] == v[order[i]]: j += 1
            avg = (i+j)/2+1
            for k in range(i, j+1): r[order[k]] = avg
            i = j+1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx = sum(rx)/n; my = sum(ry)/n
    cov = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
    vx = sum((a-mx)**2 for a in rx); vy = sum((b-my)**2 for b in ry)
    return cov/math.sqrt(vx*vy) if vx and vy else float("nan")

by = json.loads((ROOT/"data/xfv.json").read_text(encoding="utf-8"))["by_player"]
fitted = set()
for f in ("data/xfv_scored.json", "data/xfv_scored_pitcher.json"):
    for r in json.loads((ROOT/f).read_text(encoding="utf-8")): fitted.add(r["player_key"])

COLS = ["xfv_grade_quantile", "xfv_grade_model_raw", "surplus_mm", "consensus_fv", "xfv_war_6yr"]
rows = []
for pk, v in by.items():
    if v.get("kind") not in ("debuted", "resolved", "graduated"): continue
    if v.get("realized_war") is None: continue
    if any(v.get(c) is None for c in COLS): continue
    rows.append(([float(v[c]) for c in COLS], float(v["realized_war"]), pk in fitted))

def contrast(sub, a, b, B=4000, seed=3, label=""):
    ia, ib = COLS.index(a), COLS.index(b)
    y = [r[1] for r in sub]
    obs = spearman([r[0][ia] for r in sub], y) - spearman([r[0][ib] for r in sub], y)
    rnd = random.Random(seed); n = len(sub); out = []
    for _ in range(B):
        idx = [rnd.randrange(n) for _ in range(n)]
        s = [sub[i] for i in idx]; yy = [r[1] for r in s]
        out.append(spearman([r[0][ia] for r in s], yy) - spearman([r[0][ib] for r in s], yy))
    out.sort(); m = sum(out)/len(out)
    sd = (sum((d-m)**2 for d in out)/(len(out)-1))**0.5
    print(f"  {label}{a} - {b}: obs {obs:+.4f} sd {sd:.4f} "
          f"CI95 [{out[int(.025*B)]:+.4f},{out[int(.975*B)]:+.4f}] "
          f"P(>0)={sum(1 for d in out if d>0)/B:.3f} MDE95={1.96*sd:.4f}")

ins = [r for r in rows if r[2]]; oos = [r for r in rows if not r[2]]
for name, sub in (("IN-SAMPLE  n=%d " % len(ins), ins), ("HELD-OUT   n=%d " % len(oos), oos)):
    print(f"\n[{name.strip()}]")
    for a, b in (("xfv_grade_model_raw", "surplus_mm"),
                 ("xfv_grade_quantile", "xfv_grade_model_raw"),
                 ("xfv_grade_quantile", "surplus_mm"),
                 ("xfv_grade_quantile", "consensus_fv")):
        contrast(sub, a, b, label="  ")
