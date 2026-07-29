"""SCRATCH (read-only) - two checks:
  (A) decompose the measured 'Jensen gap' into mean-shift vs convexity
  (B) REALIZED $ per realized WAR by CONTRACT TERM (term structure of the
      price of a win), from the archive ledger. Writes nothing.
"""
import json
import sys
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from value_framework import tiered_war_value_usd, _config  # noqa: E402
import numpy as np  # noqa: E402

cfg = _config()
R = float(cfg["discount_rate"])
FLAT = float(cfg["dollars_per_war"]["flat"])
cls = json.loads((ROOT / "data" / "fa_class.json").read_text(encoding="utf-8"))
LEVEL = float(cls["dpw_usd"]) / FLAT
x, w = np.polynomial.hermite_e.hermegauss(15)
w = w / w.sum()
Z = 1.2815515655446004


def rational(path):
    return sum(tiered_war_value_usd(v) * LEVEL / ((1 + R) ** t) for t, v in enumerate(path))


print("=== (A) mean-shift vs convexity decomposition ===")
tot_served = tot_meanpath = tot_full = 0.0
for m in cls["members"]:
    p10, p90, mid, yrs = (m.get("warPathP10"), m.get("warPathP90"),
                          m.get("warPath"), m.get("projYears"))
    if not (p10 and p90 and mid and yrs):
        continue
    n = min(yrs, len(mid), len(p10), len(p90))
    s_hi = [(p90[t] - mid[t]) / Z for t in range(n)]
    s_lo = [(mid[t] - p10[t]) / Z for t in range(n)]
    mean_path, full = [0.0] * n, 0.0
    for zi, wi in zip(x, w):
        s = s_hi if zi >= 0 else s_lo
        pz = [max(0.0, mid[t] + s[t] * zi) for t in range(n)]
        full += wi * rational(pz)
        for t in range(n):
            mean_path[t] += wi * pz[t]
    tot_served += rational(mid[:n])
    tot_meanpath += rational(mean_path)
    tot_full += full
print(f"  served    (value of point path)      ${tot_served/1e9:.3f}B")
print(f"  mean-shift (value of E[W] path)      ${tot_meanpath/1e9:.3f}B   "
      f"delta ${(tot_meanpath-tot_served)/1e9:+.3f}B")
print(f"  full      (E[value(W)])              ${tot_full/1e9:.3f}B   "
      f"convexity-only ${(tot_full-tot_meanpath)/1e9:+.3f}B")

print()
print("=== (B) realized $/WAR by contract term (archive ledger) ===")
arch = json.loads((ROOT / "data" / "fa_archive.json").read_text(encoding="utf-8"))
buckets = defaultdict(lambda: {"g": 0.0, "w": 0.0, "n": 0, "neg": 0})
per_deal = defaultdict(list)
for wtr in arch["winters"]:
    for s in wtr["signings"]:
        if s.get("milb") or not s.get("done") or not s.get("years") or not s.get("guar"):
            continue
        war = s.get("warTd")
        if war is None:
            continue
        y = int(s["years"])
        b = "1" if y == 1 else "2" if y == 2 else "3" if y == 3 else "4-5" if y <= 5 else "6+"
        d = buckets[b]
        d["g"] += s["guar"]
        d["w"] += war
        d["n"] += 1
        d["neg"] += 1 if war <= 0 else 0
        if war > 0.25:
            per_deal[b].append(s["guar"] / war)
order = ["1", "2", "3", "4-5", "6+"]
print(f"  {'term':6s} {'n':>5s} {'sumWAR':>8s} {'pooled $/WAR':>13s} {'median deal $/WAR':>18s} {'%<=0 WAR':>9s}")
for b in order:
    d = buckets.get(b)
    if not d or d["w"] <= 0:
        continue
    med = statistics.median(per_deal[b]) if per_deal[b] else float("nan")
    print(f"  {b:6s} {d['n']:5d} {d['w']:8.1f} {d['g']/d['w']/1e6:13.2f} "
          f"{med/1e6:18.2f} {100*d['neg']/d['n']:8.1f}%")

print()
print("=== (B2) same, but on COMPLETED deals only, dollar-weighted share ===")
tot = sum(d["g"] for d in buckets.values())
for b in order:
    d = buckets.get(b)
    if d:
        print(f"  {b:6s} share of $ {100*d['g']/tot:5.1f}%   share of n {100*d['n']/sum(v['n'] for v in buckets.values()):5.1f}%")
