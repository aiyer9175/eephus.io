# SCRATCH LAB (lane: blastradius) -- analysis half.
import json
import os
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))
os.chdir(_HERE)
OUT = _HERE / "data" / "_gn_lab"

modes = json.loads((OUT / "consensus_modes.json").read_text(encoding="utf-8"))
new, old = modes["new"], modes["old"]

ts = json.loads((_HERE / "data" / "timeseries.json").read_text(encoding="utf-8"))
players = ts.get("players") or []
print("timeseries.json generated_at:", ts.get("generated_at"))
print("active players in served export:", len(players))

served = {}
for p in players:
    pts = p.get("points") or []
    if not pts:
        continue
    served[p["player_key"]] = (pts[-1].get("snapshot_date"),
                               pts[-1].get("consensus_fv_raw"),
                               p.get("player_name"), p.get("fv_close"))

# ---- VALIDATION: which simulated mode reproduces what is SERVED today? ----
for label, d in (("new", new), ("old", old)):
    diffs = []
    for k, (dt, fv, *_r) in served.items():
        if k in d and d[k][1] is not None and fv is not None:
            diffs.append(abs(d[k][1] - fv))
    diffs = np.array(diffs)
    print(f"  vs served [{label}]: n={len(diffs)} exact={int((diffs<1e-9).sum())} "
          f"({100*(diffs<1e-9).mean():.2f}%) mean|d|={diffs.mean():.4f} max|d|={diffs.max():.3f}")

# ---- BLAST RADIUS on the active board ----
keys = [k for k in served
        if k in new and k in old and new[k][1] is not None and old[k][1] is not None]
print("\nactive board keys measurable both ways:", len(keys))
o = np.array([old[k][1] for k in keys])
n = np.array([new[k][1] for k in keys])
d = n - o
moved = np.abs(d) > 1e-9
print(f"moved: {int(moved.sum())} of {len(keys)} ({100*moved.mean():.2f}%)")
print(f"  down: {int((d < -1e-9).sum())}   up: {int((d > 1e-9).sum())}")
print(f"  mean delta (all): {d.mean():+.4f}   mean delta (movers): {d[moved].mean():+.4f}")
print(f"  median delta (movers): {np.median(d[moved]):+.4f}  "
      f"p05 {np.percentile(d[moved],5):+.3f}  p95 {np.percentile(d[moved],95):+.3f}")
print(f"  max down {d.min():+.3f}   max up {d.max():+.3f}")

names = {k: served[k][2] for k in keys}
# ---- top of board ----
order_old = sorted(keys, key=lambda k: -old[k][1])
print("\nTOP 15 by OLD consensus (old -> new):")
for k in order_old[:15]:
    print(f"  {names[k]:28s} {old[k][1]:6.2f} -> {new[k][1]:6.2f}   ({new[k][1]-old[k][1]:+.2f})")

for target in ("jesus_made", "leo_de_vries", "franklin_arias", "kade_anderson", "max_clark"):
    cand = [k for k in keys if k == target] or [k for k in keys if target.split("_")[0] in k
                                                and target.split("_")[-1] in k]
    for k in cand[:2]:
        print(f"  CLAIMED {target}: {names[k]} {old[k][1]:.2f} -> {new[k][1]:.2f}")

# ---- rank churn ----
r_old = {k: i for i, k in enumerate(sorted(keys, key=lambda k: (-old[k][1], k)))}
r_new = {k: i for i, k in enumerate(sorted(keys, key=lambda k: (-new[k][1], k)))}
ch = np.array([abs(r_new[k] - r_old[k]) for k in keys])
print(f"\nrank churn: mean|d| {ch.mean():.2f}  median {np.median(ch):.1f}  max {ch.max()}  "
      f">25 spots: {int((ch>25).sum())}  >100: {int((ch>100).sum())}")
top100_old = {k for k in keys if r_old[k] < 100}
top100_new = {k for k in keys if r_new[k] < 100}
print(f"top-100 turnover: out {len(top100_old-top100_new)}  in {len(top100_new-top100_old)}")
print(f"spearman(old,new) = "
      f"{np.corrcoef([r_old[k] for k in keys],[r_new[k] for k in keys])[0,1]:.6f}")

# ---- per-source 2026 offsets, straight from the shipped table ----
import grade_normalization as gn  # noqa: E402
print("\n2026 offsets (mean(src) - mean(ref)) on the PAIRED overlap; served fv is fv - offset:")
for src in ("mlb_pipeline", "mlb_pipeline_international", "tjstats", "espn", "just_baseball"):
    for role in ("hitter", "pitcher"):
        s, r, pooled = gn._paired_dists(src, role, 2026)
        if len(s) == 0:
            print(f"  {src:28s} {role:8s} NO PAIRS")
            continue
        off = float(np.mean(s) - np.mean(r))
        se = float(np.std(np.asarray(s) - np.asarray(r), ddof=1) / np.sqrt(len(s))) \
            if len(s) > 1 else float("nan")
        print(f"  {src:28s} {role:8s} n={len(s):5d} pooled={pooled!s:5s} offset={off:+.3f}"
              f"  (note: sorted-marginal means, SE not paired)")
