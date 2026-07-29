# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""(1) Permutation null BAND for the conditional-lambda arms: the identical estimator
run on stratum labels permuted across players (same marginal sizes, zero information),
many seeds, on the FIXED pool. Gives a p-value for the real arms' point estimates.

(2) The direction check the lane's premise depends on: inside Bradfield's own stratum,
is the CONSENSUS leg (lam=0) actually better than the MODEL leg (lam=1)? If consensus is
worse there, shrinking toward it cannot help no matter how the strata are chosen.
"""
from __future__ import annotations
import sys, json, random, statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tools"))

import _prem_shrink_lab as L

SIDE = "hit"
NSEED = 250
LAM_G = L.blend_lambda(SIDE)
M = ["rho_pooled", "rho_served", "t45", "auc_pooled", "auc_served"]

base = L.summarize(*L.run_arm(SIDE, "global", LAM_G)[:2])
real = {}
for name, mode, param in (("HIER:k=25", "hier", 25), ("HIER:k=50", "hier", 50),
                          ("GATE:dip=0.5", "gate", 0.50), ("GATE:dip=1.0", "gate", 1.00)):
    s = L.summarize(*L.run_arm(SIDE, mode, param)[:2])
    real[name] = {m: s[m] - base[m] for m in M}

null = {m: [] for m in M}
for sd in range(1000, 1000 + NSEED):
    s = L.summarize(*L.run_arm(SIDE, "rand", 0.50, rand_seed=sd)[:2])
    for m in M:
        if s[m] is not None:
            null[m].append(s[m] - base[m])

print(f"PERMUTATION NULL BAND  (stratum labels permuted across players, "
      f"{NSEED} seeds, same marginal sizes)\n")
print(f"{'metric':12s} {'null mean':>10s} {'null p5':>9s} {'null p95':>9s} | "
      + " | ".join(f"{k:>13s}" for k in real))
out = {"n_seeds": NSEED, "null": {}, "real": real, "p_values": {}}
for m in M:
    d = sorted(null[m])
    lo, hi = d[int(0.05 * len(d))], d[int(0.95 * len(d))]
    out["null"][m] = {"mean": round(st.mean(d), 5), "p5": round(lo, 5), "p95": round(hi, 5),
                      "n": len(d)}
    cells = []
    for k in real:
        v = real[k][m]
        p = sum(1 for x in d if x >= v) / len(d)
        out["p_values"].setdefault(k, {})[m] = {"delta": round(v, 5), "p_one_sided": round(p, 4)}
        cells.append(f"{v:+.4f}(p={p:.2f})")
    print(f"{m:12s} {st.mean(d):+10.5f} {lo:+9.5f} {hi:+9.5f} | " + " | ".join(f"{c:>13s}" for c in cells))

# ---- (2) which leg is better INSIDE Bradfield's stratum ----
print("\n\nDIRECTION CHECK -- inside the stratum, is consensus better than the model?\n")
pooled0, _, _ = L.run_arm(SIDE, "global", 0.0)     # pure consensus leg
pooled1, _, _ = L.run_arm(SIDE, "global", 1.0)     # pure model leg
by = {x["player_key"] if "player_key" in x else i: x for i, x in enumerate(pooled0)}
cuts = {
    "ALL OOS test rows": lambda x: True,
    "served (has MiLB record)": lambda x: x["served"],
    "HIGH/OLD/BELOW (Bradfield's ex-ante stratum)": lambda x: x["strat"] == "HIGH/OLD/BELOW",
    "AAA & age>=23.5 & ops_rel<0 (lead's profile)": lambda x: x["is_target"],
}
rnd = random.Random(4242)
res2 = {}
for name, f in cuts.items():
    a = [x for x in pooled0 if f(x)]
    b = [x for x in pooled1 if f(x)]
    if len(a) < 15:
        print(f"{name}: n={len(a)} TOO THIN")
        continue
    rc = L._spearman([x["b"] for x in a], [x["y"] for x in a])
    rm = L._spearman([x["b"] for x in b], [x["y"] for x in b])
    n = len(a)
    draws = []
    for _ in range(3000):
        idx = [rnd.randrange(n) for _ in range(n)]
        ca = L._spearman([a[i]["b"] for i in idx], [a[i]["y"] for i in idx])
        cb = L._spearman([b[i]["b"] for i in idx], [b[i]["y"] for i in idx])
        if ca is not None and cb is not None:
            draws.append(cb - ca)
    draws.sort()
    lo, hi = draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws))]
    v = "MODEL BETTER" if lo > 0 else ("CONSENSUS BETTER" if hi < 0 else "NULL")
    print(f"{name}\n   n={n:4d}  consensus-leg rho={rc:+.4f}   model-leg rho={rm:+.4f}   "
          f"model-minus-consensus={rm-rc:+.4f}  CI95 [{lo:+.4f},{hi:+.4f}]  {v}")
    res2[name] = {"n": n, "rho_consensus_leg": round(rc, 4), "rho_model_leg": round(rm, 4),
                  "model_minus_consensus": round(rm - rc, 4),
                  "ci95": [round(lo, 4), round(hi, 4)], "verdict": v}

out["direction_check"] = res2
Path("tools/_prem_shrink_null_out.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("\nwrote tools/_prem_shrink_null_out.json")
