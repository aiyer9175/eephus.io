"""SCRATCH: is the FA pool selected on a PLATFORM-YEAR SPIKE (career year)?
If yes, the Marcel 5/4/3 weighting over-weights the selected realization for
exactly the players the FA module prices, and the optimal shrink differs by pool.
"""
import json, sqlite3, statistics, sys, pickle, math
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
corpus = pickle.load(open(ROOT / ".cache" / "fa_corpus.pkl", "rb"))
hist = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
for side in ("hit", "pit"):
    for r in corpus[side]:
        hist[side][r["mlbam"]][r["season"]] = r
db = sqlite3.connect(ROOT / "prospects.db")
ent = defaultdict(set); guar = {}
for pk, cy, pj in db.execute("select player_key, class_year, payload_json from fa_signings"):
    p = json.loads(pj)
    if p.get("mlbam_id"):
        ent[int(cy)].add(int(p["mlbam_id"])); guar[(int(cy), int(p["mlbam_id"]))] = p.get("guarantee_usd") or 0

EXPO = {"hit": "pa", "pit": "bf"}; MIN = {"hit": 250, "pit": 150}
rows = []
for W in range(2015, 2026):
    for side in ("hit", "pit"):
        for mid, bys in hist[side].items():
            p1, p2, p3 = bys.get(W-1), bys.get(W-2), bys.get(W-3)
            if not p1 or not p2 or not p3: continue
            if (p1.get(EXPO[side]) or 0) < MIN[side] or (p2.get(EXPO[side]) or 0) < MIN[side]:
                continue
            age = p1.get("age")
            if age is None or not (27 <= age <= 40): continue
            # per-600PA / per-700BF WAR rate to remove PT
            def rate(r):
                e = r.get(EXPO[side]) or 0
                return (r.get("war") or 0.0) / e * (600 if side == "hit" else 700)
            spike = rate(p1) - (rate(p2) + rate(p3)) / 2
            rows.append({"W": W, "side": side, "D": 1 if mid in ent.get(W, ()) else 0,
                         "spike": spike, "base": (rate(p2)+rate(p3))/2, "rate1": rate(p1),
                         "guar": guar.get((W, mid), 0), "age": age})
def rep(sel, lab):
    a = [r for r in sel if r["D"]==1]; b = [r for r in sel if r["D"]==0]
    if len(a) < 20: print(f"{lab}: n too small"); return
    sa = [r["spike"] for r in a]; sb = [r["spike"] for r in b]
    se = math.sqrt(statistics.pvariance(sa)/len(sa)+statistics.pvariance(sb)/len(sb))
    print(f"{lab:34s} nD1={len(a):5d} nD0={len(b):5d}  platform spike (WAR/600) "
          f"{statistics.mean(sa):+.3f} vs {statistics.mean(sb):+.3f}  diff {statistics.mean(sa)-statistics.mean(sb):+.3f} "
          f"(t {(statistics.mean(sa)-statistics.mean(sb))/se:+.2f})")
rep(rows, "all")
for s in ("hit","pit"): rep([r for r in rows if r["side"]==s], f"side={s}")
rep([r for r in rows if r["D"]==0 or r["guar"] >= 20e6], "D1 restricted to $20M+ deals")
rep([r for r in rows if r["D"]==0 or (0 < r["guar"] < 20e6)], "D1 restricted to sub-$20M deals")
