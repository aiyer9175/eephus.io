"""Characterize the 558 'held-out' rows: are they a clean holdout or a different
scoring seam? Read-only."""
import json, os, statistics
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
by = json.loads((ROOT/"data/xfv.json").read_text(encoding="utf-8"))["by_player"]
fitted = set()
for f in ("data/xfv_scored.json", "data/xfv_scored_pitcher.json"):
    for r in json.loads((ROOT/f).read_text(encoding="utf-8")): fitted.add(r["player_key"])
pool = {k: v for k, v in by.items()
        if v.get("kind") in ("debuted", "resolved", "graduated") and v.get("realized_war") is not None}
oos = {k: v for k, v in pool.items() if k not in fitted}
ins = {k: v for k, v in pool.items() if k in fitted}
print("held-out n", len(oos), "in-sample n", len(ins))
print("side held-out", Counter(v["side"] for v in oos.values()))
print("side in-sample", Counter(v["side"] for v in ins.values()))
for f in ("data/xfv_hitter_matrix.json", "data/xfv_pitcher_matrix.json"):
    p = ROOT/f
    if not p.exists():
        print(f, "MISSING"); continue
    m = json.loads(p.read_text(encoding="utf-8"))
    km = {r["player_key"]: r for r in m}
    hit = set(oos) & set(km)
    print(f, "rows", len(m), "held-out rows present in matrix:", len(hit))
    print("   kind:", Counter(km[k].get("kind") for k in hit),
          "bust_recent:", Counter(bool(km[k].get("bust_recent")) for k in hit))
    print("   consensus_fv_raw missing:", sum(1 for k in hit if km[k].get("consensus_fv_raw") is None),
          " target_censored missing:", sum(1 for k in hit if km[k].get("target_censored") is None))
print("mean realized_war  in-sample %.2f  held-out %.2f" % (
    statistics.mean(v["realized_war"] for v in ins.values()),
    statistics.mean(v["realized_war"] for v in oos.values())))
print("mean consensus_fv  in-sample %.2f  held-out %.2f" % (
    statistics.mean(v["consensus_fv"] for v in ins.values()),
    statistics.mean(v["consensus_fv"] for v in oos.values())))
