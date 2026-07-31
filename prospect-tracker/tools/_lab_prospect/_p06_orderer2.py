"""Lane: prospect. Candidate C-ORDER: make the Trade Machine Grade column order by
the SAME eFV grade the rest of the site displays (xfv_grade_quantile) instead of the
hidden raw grade. Full gate: paired bootstrap, zero-info control, permutation null,
>=4 time splits, plus within-tier."""
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "data"
from source_backtest import _spearman, _auc
from bayes_trade_value import _platform_tier

L = lambda n: json.loads((D / n).read_text(encoding="utf-8"))
xfv = L("xfv.json")["by_player"]
deb = {}
for r in L("debuts.json"):
    if r.get("player_key") and r.get("debut_date"):
        deb[r["player_key"]] = int(r["debut_date"][:4])

R = {"debuted", "resolved", "graduated"}
rows = [dict(k=k, y=float(x["realized_war"]), sur=float(x["surplus_mm"]),
             raw=float(x["xfv_grade_model_raw"]), qnt=float(x["xfv_grade_quantile"]),
             cons=float(x["consensus_fv"]), yr=deb.get(k),
             tier=_platform_tier(float(x["surplus_mm"])))
        for k, x in xfv.items()
        if x.get("kind") in R and x.get("realized_war") is not None
        and x.get("surplus_mm") is not None and x.get("xfv_grade_model_raw") is not None
        and x.get("xfv_grade_quantile") is not None and x.get("consensus_fv") is not None]
n = len(rows)
y = np.array([r["y"] for r in rows])
C = {c: np.array([r[c] for r in rows]) for c in ("sur", "raw", "qnt", "cons")}
rho = lambda a, b: _spearman(list(a), list(b))
print("pool n =", n)
for c in C:
    print(f"  {c:5s} pooled rho={rho(C[c],y):+.4f}")

rng = np.random.default_rng(20260725)
def boot(a, b, B=4000):
    out = np.empty(B)
    for i in range(B):
        idx = rng.integers(0, n, n); yy = y[idx]
        out[i] = rho(a[idx], yy) - rho(b[idx], yy)
    return out

print("\nPAIRED BOOTSTRAP (B=4000), candidate = quantile grade")
for nm, other in (("quantile - raw", "raw"), ("quantile - surplus", "sur"),
                  ("quantile - consensus", "cons")):
    d = boot(C["qnt"], C[other])
    lo, hi = np.percentile(d, [2.5, 97.5])
    print(f"  {nm:22s} obs={rho(C['qnt'],y)-rho(C[other],y):+.4f} mean={d.mean():+.4f} "
          f"sd={d.std():.4f} CI95=[{lo:+.4f},{hi:+.4f}] P(>0)={float((d>0).mean()):.3f} "
          f"MDE95={1.96*d.std():.4f}")

print("\nZERO-INFORMATION CONTROL (row-permuted twin of the SAME column)")
for c in ("qnt", "raw", "sur"):
    p = C[c].copy(); rng.shuffle(p)
    d = boot(p, C["sur"], 800)
    print(f"  permuted {c:4s} vs surplus: obs={rho(p,y)-rho(C['sur'],y):+.4f} "
          f"CI95=[{np.percentile(d,2.5):+.4f},{np.percentile(d,97.5):+.4f}]")

print("\nPERMUTATION NULL BAND (both columns permuted, B=2000)")
nl = np.array([rho(C['qnt'][rng.permutation(n)], y) - rho(C['raw'][rng.permutation(n)], y)
               for _ in range(2000)])
print(f"  mean={nl.mean():+.4f} CI95=[{np.percentile(nl,2.5):+.4f},{np.percentile(nl,97.5):+.4f}] "
      f"half-width={max(abs(np.percentile(nl,2.5)),abs(np.percentile(nl,97.5))):.4f}")

print("\nTIME SPLITS (debut-year cohorts, n>=60)")
bk = {}
for r in rows:
    if r["yr"]:
        bk.setdefault(r["yr"], []).append(r)
dq_raw, dq_sur = [], []
for v, rr in sorted(bk.items()):
    if len(rr) < 60:
        continue
    yy = np.array([r["y"] for r in rr])
    a = np.array([r["qnt"] for r in rr]); b = np.array([r["raw"] for r in rr])
    c = np.array([r["sur"] for r in rr])
    d1, d2 = rho(a, yy) - rho(b, yy), rho(a, yy) - rho(c, yy)
    dq_raw.append(d1); dq_sur.append(d2)
print(f"  quantile - raw     cross-split mean={np.mean(dq_raw):+.4f} "
      f"({sum(1 for d in dq_raw if d>0)}/{len(dq_raw)} positive)")
print(f"  quantile - surplus cross-split mean={np.mean(dq_sur):+.4f} "
      f"({sum(1 for d in dq_sur if d>0)}/{len(dq_sur)} positive)")

print("\nWITHIN-TIER (the gate the registry says the board FAILED)")
for t in ("elite", "high", "mid", "low"):
    rr = [r for r in rows if r["tier"] == t]
    if len(rr) < 30:
        # fold negative/minimal into low the way the registered tool does
        continue
    yy = np.array([r["y"] for r in rr])
    print(f"  {t:6s} n={len(rr):5d}  sur={rho([r['sur'] for r in rr],yy):+.4f} "
          f"raw={rho([r['raw'] for r in rr],yy):+.4f} "
          f"qnt={rho([r['qnt'] for r in rr],yy):+.4f} "
          f"cons={rho([r['cons'] for r in rr],yy):+.4f}")
tiers = sorted({r["tier"] for r in rows})
print("  tier labels present:", tiers, {t: sum(1 for r in rows if r['tier']==t) for t in tiers})
