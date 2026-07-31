# SCRATCH LAB (lane: blastradius) -- Step 3: is FanGraphs the RIGHT reference, and
# does the surplus calibration's INPUT scale still match production's?
#
# surplus_backtest_real._load_inputs prices resolved listings on the RAW median FV
# across sources straight from the snapshots table -- NO grade normalization. The
# shipped calibration (config/valuation_sets/prospx_current.yaml,
# linearmap-v5-todaypriced-2026-07-24) was fit on that pool. Production prices on
# the NORMALIZED consensus. This measures how far apart those two scales now sit.
import json
import os
import statistics
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))
os.chdir(_HERE)
OUT = _HERE / "data" / "_gn_lab"

modes = json.loads((OUT / "consensus_modes.json").read_text(encoding="utf-8"))
new, old = modes["new"], modes["old"]

import storage  # noqa: E402

# RAW median FV per player at their latest snapshot date -- the backtest's definition,
# restricted to the same date the lab used as "latest".
raw_med = {}
with storage.connect() as con:
    rows = con.execute(
        "SELECT player_key, source, snapshot_date, fv FROM snapshots WHERE fv IS NOT NULL"
    ).fetchall()
per = {}
for r in rows:
    k = r["player_key"]
    if k not in new:
        continue
    if r["snapshot_date"] != new[k][0]:
        continue
    per.setdefault(k, []).append(float(r["fv"]))
for k, v in per.items():
    raw_med[k] = statistics.median(v)

live = json.loads((_HERE / "data" / "xfv_scored_live.json").read_text(encoding="utf-8")) \
    + json.loads((_HERE / "data" / "xfv_scored_live_pitcher.json").read_text(encoding="utf-8"))
keys = [r["player_key"] for r in live
        if r["player_key"] in raw_med and r["player_key"] in new
        and new[r["player_key"]][1] is not None]
print(f"live pool with a same-date raw median: n={len(keys)}")

rm = np.array([raw_med[k] for k in keys])
on = np.array([old[k][1] for k in keys])
nn = np.array([new[k][1] for k in keys])

print("\nSCALE COMPARISON on the live pool (FV points):")
print(f"  RAW median across sources (the CALIBRATION-FIT scale): mean {rm.mean():.3f}")
print(f"  OLD normalized consensus  (what was live pre-repair) : mean {on.mean():.3f}"
      f"   vs raw {on.mean()-rm.mean():+.3f}")
print(f"  NEW normalized consensus  (what ships now)           : mean {nn.mean():.3f}"
      f"   vs raw {nn.mean()-rm.mean():+.3f}")

for lo, hi, lbl in ((55, 99, "top band (raw med >= 55)"),
                    (50, 55, "50-54.9"), (45, 50, "45-49.9"), (0, 45, "below 45")):
    m = (rm >= lo) & (rm < hi)
    if m.sum() < 5:
        continue
    print(f"    {lbl:24s} n={int(m.sum()):5d}  raw {rm[m].mean():6.2f}  "
          f"old {on[m].mean():6.2f} ({on[m].mean()-rm[m].mean():+.2f})  "
          f"new {nn[m].mean():6.2f} ({nn[m].mean()-rm[m].mean():+.2f})")

print("\nSHAPE of the eFV display TARGET distribution (sorted consensus FV):")
for q in (0.5, 0.75, 0.9, 0.95, 0.99, 1.0):
    print(f"  q={q:<5} old {np.quantile(on,q):6.2f}   new {np.quantile(nn,q):6.2f}   "
          f"delta {np.quantile(nn,q)-np.quantile(on,q):+.2f}")
print(f"  sd: old {on.std():.3f} -> new {nn.std():.3f} "
      f"({100*(nn.std()/on.std()-1):+.1f}% dispersion)")

# --- fangraphs-vs-outlet reference audit: how much of the board does FG actually see? ---
print("\nREFERENCE AUDIT -- is FanGraphs merely the longest-history source?")
import grade_normalization as gn  # noqa: E402
lat = gn._all_latest()
cov = {}
for (role, yr), players in lat.items():
    if yr != 2026:
        continue
    for pk, d in players.items():
        for s in d:
            cov[s] = cov.get(s, 0) + 1
tot = len({pk for (role, yr), pl in lat.items() if yr == 2026 for pk in pl})
print(f"  2026 cycle: {tot} graded players")
for s, c in sorted(cov.items(), key=lambda x: -x[1]):
    print(f"    {s:32s} {c:6d}  ({100*c/tot:5.1f}% of the cycle)")
print("  years covered per source (any role):")
srcs = set()
for pl in lat.values():
    for d in pl.values():
        srcs.update(d)
for s in sorted(srcs):
    yrs = sorted({yr for (role, yr), pl in lat.items()
                  for d in pl.values() if s in d})
    if yrs:
        print(f"    {s:32s} {min(yrs)}-{max(yrs)}  ({len(yrs)} cycles)")
