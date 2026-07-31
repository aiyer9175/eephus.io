# Step 2: does the survivorship hole reach the eFV TRAINING labels?
# Evidence = the SHIPPED matrices, not inference from the code path.
from __future__ import annotations

import collections
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"


def load(name):
    d = json.loads((DATA / name).read_text(encoding="utf-8"))
    return d["players"] if isinstance(d, dict) else d


TSK = {p["player_key"] for p in load("timeseries.json")}
DEBK = {p["player_key"] for p in load("debuts.json")}
INAK = {p["player_key"] for p in load("inactive.json")}

mat = []
for fn in ("xfv_hitter_matrix.json", "xfv_pitcher_matrix.json"):
    for r in json.loads((DATA / fn).read_text(encoding="utf-8")):
        r["_side"] = "hit" if "hitter" in fn else "pit"
        mat.append(r)

print("eFV training matrix rows:", len(mat))
print("kind:", collections.Counter(r["kind"] for r in mat))
mk = {r["player_key"] for r in mat}
print("distinct player_keys:", len(mk))

print("\n--- provenance of the eFV training keys ---")
prov = collections.Counter()
for k in mk:
    tags = []
    if k in DEBK:
        tags.append("debuts")
    if k in INAK:
        tags.append("inactive")
    if k in TSK:
        tags.append("timeseries")
    prov[tuple(tags) or ("none",)] += 1
for t, n in prov.most_common():
    print(f"  {'+'.join(t):>28}: {n}")

print("\n--- bust rows: are they the inactive.json pool? ---")
busts = [r for r in mat if r["kind"] == "bust"]
print("bust rows:", len(busts),
      "| in inactive.json:", sum(1 for r in busts if r["player_key"] in INAK),
      "| in timeseries.json:", sum(1 for r in busts if r["player_key"] in TSK),
      "| in debuts.json:", sum(1 for r in busts if r["player_key"] in DEBK))
print("bust_recent flagged:", sum(1 for r in busts if r.get("bust_recent")))
print("bust target_censored all zero:",
      all((r.get("target_censored") or 0.0) == 0.0 for r in busts))

print("\n--- the C2 hole vs eFV: the players the consensus surface drops ---")
# players graded in a preseason window who are in inactive.json only
import sys
sys.path.insert(0, str(HERE.parent))
import source_backtest as sb   # noqa: E402

INA = load("inactive.json")
YEARS = (2017, 2018, 2019, 2020, 2021, 2022, 2023)
dropped = {}
for p in INA:
    for y in YEARS:
        g = sb._rater_grades_for_year(p, y)
        if g and all(s in g for s in ("fangraphs", "mlb_pipeline")):
            dropped.setdefault(p["player_key"], set()).add(y)
print("inactive players graded on >=1 scored preseason common set:", len(dropped))
print("  of those, present in the eFV training matrices:",
      sum(1 for k in dropped if k in mk))
print("  ABSENT from eFV training:", sum(1 for k in dropped if k not in mk))

miss = [k for k in dropped if k not in mk]
if miss:
    ina_by = {p["player_key"]: p for p in INA}
    print("  sample of absent:", miss[:10])
    reasons = collections.Counter()
    for k in miss[:2000]:
        p = ina_by[k]
        pts = [q for q in (p.get("points") or []) if q.get("snapshot_date")]
        if not pts:
            reasons["no points"] += 1
        elif all(q.get("consensus_fv_raw") is None for q in pts):
            reasons["no consensus_fv_raw"] += 1
        elif p.get("career_war"):
            reasons["has career_war (rerouted/dropped)"] += 1
        else:
            reasons["other (side-unknown / mlb-exposed)"] += 1
    print("  absence reasons:", dict(reasons))
