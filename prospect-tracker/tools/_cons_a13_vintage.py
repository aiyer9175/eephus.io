# A13 -- investigation 4 support: is the stored MLB Pipeline history genuinely
# POINT-IN-TIME, or hindsight-backfilled? Checked against the independent
# point-in-time boards in data/pipeline_vintages.json.
from __future__ import annotations

import collections
import json

import numpy as np

from _cons_data import DATA

vin = json.loads((DATA / "pipeline_vintages.json").read_text(encoding="utf-8"))["vintages"]
uni = json.loads((DATA / "timeseries.json").read_text(encoding="utf-8"))["players"]
uni += json.loads((DATA / "debuts.json").read_text(encoding="utf-8"))

# stored Pipeline top-100 membership per year, from the exported snapshot history
stored = collections.defaultdict(set)
graded = collections.defaultdict(dict)
for p in uni:
    mid = p.get("mlbam_id")
    for pt in (p.get("points") or []):
        ps = (pt.get("per_source") or {}).get("mlb_pipeline")
        if not ps:
            continue
        sd = str(ps.get("snapshot_date") or pt.get("snapshot_date") or "")
        if len(sd) < 4:
            continue
        yr = int(sd[:4])
        lbl = str(ps.get("interval_label") or "")
        rk = ps.get("rank")
        if mid and rk and "Top 100" in lbl:
            stored[yr].add(int(mid))
        if mid and ps.get("fv_published") is not None:
            graded[yr][int(mid)] = float(ps["fv_published"])

print("=== A13a. stored Pipeline Top-100 membership vs the point-in-time vintage board ===")
print(f"{'year':>6} {'vintage':>8} {'stored':>7} {'overlap':>8} {'recall':>7}")
for y in sorted(vin):
    yi = int(y)
    v = {int(r["mlbam"]) for r in vin[y] if r.get("mlbam")}
    s = stored.get(yi, set())
    if not s:
        print(f"{yi:>6} {len(v):>8} {0:>7} {0:>8}   no stored Top-100 rows")
        continue
    ov = len(v & s)
    print(f"{yi:>6} {len(v):>8} {len(s):>7} {ov:>8} {ov/max(len(v),1):>7.1%}")

print("\n=== A13b. vintage 20-80 Overall grades available per year "
      "(the FV-drift check the vintages could support) ===")
tot = 0
for y in sorted(vin):
    g = [r for r in vin[y] if r.get("grades") or r.get("overall") or r.get("fv")]
    n = sum(1 for r in vin[y] if any(k in r for k in ("overall", "fv", "grades")))
    tot += n
    print(f"  {y}: rows {len(vin[y])}  with a grade field {n}")
print(f"  TOTAL graded vintage rows across all years: {tot}")
print("  keys present on a sample row:", sorted(vin[sorted(vin)[0]][0].keys()))
