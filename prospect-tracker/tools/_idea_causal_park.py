"""SCRATCH: feasibility of the within-player park natural experiment.
How many FA signings actually change parks, with usable before/after seasons?
"""
from __future__ import annotations
import json, sqlite3, sys, pickle, statistics
from collections import defaultdict, Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

corpus = pickle.load(open(ROOT / ".cache" / "fa_corpus.pkl", "rb"))
hist = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
for side in ("hit", "pit"):
    for r in corpus[side]:
        hist[side][r["mlbam"]][r["season"]] = r

db = sqlite3.connect(ROOT / "prospects.db")
mv = Counter(); usable = Counter(); pairs = []
for pk, cy, pj in db.execute("select player_key, class_year, payload_json from fa_signings"):
    p = json.loads(pj); W = int(cy); mid = p.get("mlbam_id")
    ft, tt = p.get("from_team"), p.get("to_team")
    if not mid or not ft or not tt:
        continue
    moved = ft != tt
    mv[moved] += 1
    for side in ("hit", "pit"):
        bys = hist[side].get(int(mid))
        if not bys: continue
        pre, post = bys.get(W - 1), bys.get(W)
        expo = "pa" if side == "hit" else "bf"
        if pre and post and (pre.get(expo) or 0) >= 200 and (post.get(expo) or 0) >= 200:
            usable[(side, moved)] += 1
            pairs.append({"side": side, "moved": moved, "from": ft, "to": tt, "W": W,
                          "mid": mid, "pre": pre, "post": post})
print("moved vs stayed (all signings):", dict(mv))
print("usable before/after pairs:", dict(usable))

# how much park variation does a move actually deliver?
meta = json.load(open(ROOT / "data" / "fa_meta.json"))["park_factors"]
deltas = []
for r in pairs:
    a, b = meta.get(r["from"]), meta.get(r["to"])
    if a and b and r["moved"]:
        deltas.append(b["woba"] - a["woba"])
if deltas:
    deltas.sort()
    print(f"park wOBA-factor delta on moves: n={len(deltas)} sd={statistics.pstdev(deltas):.2f} "
          f"p10={deltas[len(deltas)//10]} p90={deltas[-len(deltas)//10]} "
          f"|d|>=5: {sum(1 for d in deltas if abs(d)>=5)}")

# dimension variation available (venue_meta, MLB only)
vm = json.load(open(ROOT / "data" / "venue_meta.json"))
mlb = [v for v in vm.values() if isinstance(v, dict) and v.get("level") == "MLB"]
print("MLB venues in venue_meta:", len(mlb))
for f in ("elevation_ft", "azimuth", "capacity"):
    vals = [v[f] for v in mlb if v.get(f) is not None]
    print(f"  {f}: n={len(vals)} range {min(vals)}..{max(vals)}")
dimf = [v["dims"] for v in mlb if v.get("dims")]
print("  with dims:", len(dimf))
for k in ("leftLine", "left", "leftCenter", "center", "rightCenter", "right", "rightLine"):
    vals = [d[k] for d in dimf if d.get(k)]
    if vals:
        print(f"    {k}: n={len(vals)} {min(vals)}-{max(vals)} sd={statistics.pstdev(vals):.1f}")
roofs = Counter(v.get("roof") for v in mlb)
print("  roof:", dict(roofs))
