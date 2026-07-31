# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Requirement (d), sharpened. A conditional lambda does two things at once:
it moves the AVERAGE lambda, and it varies lambda BY STRATUM. Comparing it to the
shipped lam=0.70 confounds the two. The right control is the GLOBAL lambda set to the
conditional arm's own MEAN applied lambda: any remaining difference is what stratum
information buys over simply turning the one existing knob.

Paired bootstrap (train+test resampled, full refit per draw), conditional arm vs its
mean-matched global twin, on the same resample.
"""
from __future__ import annotations
import sys, json, random, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tools"))

import _prem_shrink_lab as L

SIDE = "hit"
B = int(sys.argv[1]) if len(sys.argv) > 1 else 400
M = ["rho_pooled", "rho_served", "t45", "rho_target", "auc_pooled", "auc_served"]
ARMS = [("HIER:k=25", "hier", 25), ("HIER:k=50", "hier", 50),
        ("GATE:dip=0.5", "gate", 0.50), ("GATE:dip=1.0", "gate", 1.00)]

# point pass: mean applied lambda per arm
mean_lam = {}
print("POINT ESTIMATES -- conditional arm vs mean-lambda-matched global twin\n")
print(f"{'arm':14s} {'mean lam':>8s} | {'rho':>8s} {'t45':>8s} {'auc':>8s} "
      f"| matched global -> {'rho':>8s} {'t45':>8s} {'auc':>8s} | {'d_rho':>8s} {'d_t45':>8s} {'d_auc':>8s}")
point = {}
for name, mode, param in ARMS:
    pooled, auc_rows, _ = L.run_arm(SIDE, mode, param)
    s = L.summarize(pooled, auc_rows)
    ml = sum(x["lam"] for x in pooled) / len(pooled)
    mean_lam[name] = ml
    g = L.summarize(*L.run_arm(SIDE, "global", ml)[:2])
    point[name] = {"mean_lam": round(ml, 4),
                   "arm": {m: (round(s[m], 5) if s[m] is not None else None) for m in M},
                   "matched_global": {m: (round(g[m], 5) if g[m] is not None else None) for m in M},
                   "delta_vs_matched": {m: (round(s[m] - g[m], 5)
                                            if (s[m] is not None and g[m] is not None) else None)
                                        for m in M}}
    print(f"{name:14s} {ml:8.4f} | {s['rho_pooled']:8.4f} {s['t45']:8.4f} {s['auc_pooled']:8.4f} "
          f"| {'':17s} {g['rho_pooled']:8.4f} {g['t45']:8.4f} {g['auc_pooled']:8.4f} "
          f"| {s['rho_pooled']-g['rho_pooled']:+8.4f} {s['t45']-g['t45']:+8.4f} "
          f"{s['auc_pooled']-g['auc_pooled']:+8.4f}")

# paired bootstrap of the same contrast
print(f"\n\nPAIRED BOOTSTRAP, arm minus mean-matched global (B={B}, refit per draw)\n")
rnd = random.Random(20260725)
pool = L.data_for(SIDE)
n = len(pool)
draws = {a[0]: {m: [] for m in M} for a in ARMS}
t0 = time.time()
for b in range(B):
    idx = [rnd.randrange(n) for _ in range(n)]
    rows = [pool[i] for i in idx]
    try:
        for name, mode, param in ARMS:
            p, ar, _ = L.run_arm(SIDE, mode, param, rows=rows)
            s = L.summarize(p, ar)
            ml = sum(x["lam"] for x in p) / max(1, len(p))
            g = L.summarize(*L.run_arm(SIDE, "global", ml, rows=rows)[:2])
            for m in M:
                if s.get(m) is not None and g.get(m) is not None:
                    draws[name][m].append(s[m] - g[m])
    except Exception:
        continue
    if (b + 1) % 50 == 0:
        print(f"  draw {b+1}/{B} ({time.time()-t0:.0f}s)", flush=True)

print(f"\n{'arm':14s} {'metric':12s} {'mean':>9s} {'CI95_lo':>9s} {'CI95_hi':>9s}  verdict")
out = {"B": B, "point": point, "bootstrap": {}}
for name, _, _ in ARMS:
    out["bootstrap"][name] = {}
    for m in M:
        d = sorted(draws[name][m])
        if len(d) < 30:
            continue
        mean = sum(d) / len(d)
        lo, hi = d[int(0.025 * len(d))], d[min(len(d) - 1, int(0.975 * len(d)))]
        v = "POSITIVE" if lo > 0 else ("NEGATIVE" if hi < 0 else "NULL")
        out["bootstrap"][name][m] = {"mean": round(mean, 5),
                                     "ci95": [round(lo, 5), round(hi, 5)], "verdict": v}
        print(f"{name:14s} {m:12s} {mean:+9.5f} {lo:+9.5f} {hi:+9.5f}  {v}")
    print()

Path("tools/_prem_shrink_matched_out.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("wrote tools/_prem_shrink_matched_out.json")
