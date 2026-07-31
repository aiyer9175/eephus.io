# SCRATCH LAB (lane: scale-audit) part (d). Read-only.
# empirical_anchors._cohort is the SAME defect class as surplus_backtest_real:
# it pools RAW snapshot FV (plain mean over the window, not even the per-source
# median) and bins to a 5-point tier. Production grades on the NORMALIZED
# consensus. Quantify the tier migration, because those tiers ARE the x-axis of
# fv_to_6yr_avg_war -- the curve expected_surplus_usd is built on.
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))
os.chdir(_HERE)

import storage                     # noqa: E402
import grade_normalization as gn   # noqa: E402
import consensus as cons           # noqa: E402
import value_framework as vf       # noqa: E402

REF_YEAR = 2026
Y0, Y1 = REF_YEAR - 9, REF_YEAR - 6      # policy resolved_lag_max/min defaults
remap = gn.build_remapper(aliases=cons.SOURCE_ALIASES)

fvs_raw, fvs_new, pos = defaultdict(list), defaultdict(list), defaultdict(list)
with storage.connect() as con:
    for r in con.execute(
        "SELECT player_key, source, snapshot_date, fv, position FROM snapshots "
        "WHERE snapshot_date BETWEEN ? AND ? AND fv IS NOT NULL",
            (f"{Y0}-01-01", f"{Y1}-12-31")):
        k = r["player_key"]
        fvs_raw[k].append(float(r["fv"]))
        fvs_new[k].append(float(remap(float(r["fv"]), r["source"], r["position"],
                                      int(str(r["snapshot_date"])[:4]))))
        pos[k].append((r["position"] or "").upper())

print(f"empirical_anchors cohort window {Y0}-{Y1}: {len(fvs_raw)} players, "
      f"{sum(len(v) for v in fvs_raw.values())} snapshots")


def tier(x):
    return int(round(x / 5) * 5)


raw_m = {k: float(np.mean(v)) for k, v in fvs_raw.items()}
new_m = {k: float(np.mean(v)) for k, v in fvs_new.items()}
d = np.array([new_m[k] - raw_m[k] for k in raw_m])
print(f"pooled entry FV shift: mean {d.mean():+.4f}  median {np.median(d):+.4f}  "
      f"sd {d.std(ddof=1):.4f}  p05 {np.percentile(d,5):+.3f}  p95 {np.percentile(d,95):+.3f}")

moved = sum(1 for k in raw_m if tier(raw_m[k]) != tier(new_m[k]))
print(f"players whose 5-point ANCHOR TIER changes: {moved} / {len(raw_m)} "
      f"({100*moved/len(raw_m):.1f}%)")
mig = defaultdict(int)
for k in raw_m:
    a, b = tier(raw_m[k]), tier(new_m[k])
    if a != b:
        mig[(a, b)] += 1
for (a, b), n in sorted(mig.items(), key=lambda x: -x[1])[:12]:
    print(f"    tier {a} -> {b}: {n}")

print("\nTIER OCCUPANCY (the anchor fit's per-tier n, which sets the thin-cell blend weight):")
print(f"  {'tier':>6} {'n RAW':>8} {'n NORM':>8} {'change':>9}")
for t in (35, 40, 45, 50, 55, 60, 65, 70):
    nr = sum(1 for k in raw_m if tier(raw_m[k]) == t)
    nn = sum(1 for k in new_m if tier(new_m[k]) == t)
    if nr or nn:
        print(f"  {t:>6} {nr:>8} {nn:>8} {nn-nr:>+9}")

print("\nWhat the shipped anchors currently say (fv_to_6yr_avg_war), and what a "
      "-2.1 FV x-axis shift implies:")
for t in (40, 45, 50, 55, 60, 65):
    a = vf.fv_to_6yr_avg_war(t)
    a_sh = vf.fv_to_6yr_avg_war(t - 2.135)
    if a and a_sh:
        print(f"  FV {t}: anchor {a:.4f} WAR/yr;  same cohort re-labelled at its "
              f"normalized grade would read at FV {t-2.135:.1f} -> {a_sh:.4f} "
              f"({100*(a_sh/a-1):+.1f}%)")
