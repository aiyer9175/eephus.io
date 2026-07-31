"""Lane: prospect. (a)+(b) Re-derive the trade_machine_surplus slice-A claims AND
derive the MDE for the statistic the board's ordering decision was made on.

The board sorts its default Grade column by xfv_grade (RAW model grade) because
data/trade_machine_eval.json records rho 0.3433 for that orderer vs 0.3289 for the
displayed surplus. Delta = 0.0144. No floor was ever derived for THAT statistic.
Here we derive it: paired bootstrap over the resolved pool, a row-permuted
zero-information twin of each column, a permutation null band, and >= 4 time
splits (debut-year cohorts from data/debuts.json).
"""
import json, math, random, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "data"
from source_backtest import _spearman, _auc     # canonical helpers

L = lambda n: json.loads((D / n).read_text(encoding="utf-8"))
xfv = L("xfv.json")["by_player"]
RESOLVED = {"debuted", "resolved", "graduated"}

# debut year for time splits
deb = {}
for r in L("debuts.json"):
    k, dd = r.get("player_key"), r.get("debut_date")
    if k and dd:
        deb[k] = int(dd[:4])

rows = []
for k, x in xfv.items():
    if x.get("kind") not in RESOLVED:
        continue
    if x.get("realized_war") is None:
        continue
    if x.get("surplus_mm") is None or x.get("xfv_grade_model_raw") is None \
       or x.get("xfv_grade_quantile") is None or x.get("consensus_fv") is None:
        continue
    rows.append(dict(k=k, side=x.get("side"), y=float(x["realized_war"]),
                     sur=float(x["surplus_mm"]),
                     raw=float(x["xfv_grade_model_raw"]),
                     qnt=float(x["xfv_grade_quantile"]),
                     cons=float(x["consensus_fv"]),
                     war6=float(x.get("xfv_war_6yr") or 0.0),
                     yr=deb.get(k)))
print("resolved pool n =", len(rows), " with debut year:", sum(1 for r in rows if r["yr"]))

y = np.array([r["y"] for r in rows])
COLS = {c: np.array([r[c] for r in rows]) for c in ("sur", "raw", "qnt", "cons", "war6")}

def rho(a, b):
    return _spearman(list(a), list(b))

print("\n--- (a) REPRODUCTION of data/trade_machine_eval.json slice_a ---")
reg = L("trade_machine_eval.json")["slice_a"]
print(f"  registered  n={reg['n']}  surplus rho={reg['pooled']['spearman']}  "
      f"consensus rho={reg['baseline_consensus_fv']['spearman']}  "
      f"xfv_grade rho={reg['xfv_grade_orderer']['spearman']}  AUC={reg['pooled']['auc_useful_asset']}")
auc = _auc([1 if v >= 6.0 else 0 for v in y], list(COLS["sur"]))
print(f"  re-derived  n={len(rows)}  surplus rho={rho(COLS['sur'],y):.4f}  "
      f"consensus rho={rho(COLS['cons'],y):.4f}  xfv_grade rho={rho(COLS['raw'],y):.4f}  AUC={auc:.4f}")
print(f"  ALSO the DISPLAYED quantile grade rho={rho(COLS['qnt'],y):.4f}   war6 rho={rho(COLS['war6'],y):.4f}")

# ---------------------------------------------------------------- MDE / floor
B = 4000
rng = np.random.default_rng(20260725)
n = len(rows)
def boot_delta(a, b, B=B):
    """paired bootstrap of rho(a,y) - rho(b,y)."""
    out = np.empty(B)
    for i in range(B):
        idx = rng.integers(0, n, n)
        yy = y[idx]
        out[i] = rho(a[idx], yy) - rho(b[idx], yy)
    return out

print("\n--- MDE95 for a PAIRED rho-difference on this pool (the floor the board decision needed) ---")
d_null = boot_delta(COLS["sur"], COLS["sur"], 1200)   # same column vs itself = 0 by construction
# the real floor: bootstrap sd of a rho-difference between two DISTINCT columns of
# comparable strength. Use the sd of the observed contrast as the scale.
d_rq = boot_delta(COLS["raw"], COLS["qnt"])
d_rs = boot_delta(COLS["sur"], COLS["sur"])
d_gs = boot_delta(COLS["raw"], COLS["sur"])
def rep(name, d, obs):
    lo, hi = np.percentile(d, [2.5, 97.5])
    print(f"  {name:34s} obs={obs:+.4f}  boot mean={d.mean():+.4f}  sd={d.std():.4f}  "
          f"CI95=[{lo:+.4f},{hi:+.4f}]  P(>0)={float((d>0).mean()):.3f}  MDE95(1.96sd)={1.96*d.std():.4f}")
rep("raw_grade - surplus", d_gs, rho(COLS['raw'],y)-rho(COLS['sur'],y))
rep("raw_grade - quantile_grade", d_rq, rho(COLS['raw'],y)-rho(COLS['qnt'],y))

# zero-information control: row-permuted twin of the SAME column
print("\n--- zero-information control (row-permuted twin of the same column) ---")
for cname in ("raw", "qnt", "sur"):
    perm = COLS[cname].copy(); rng.shuffle(perm)
    print(f"  {cname:5s} rho={rho(COLS[cname],y):+.4f}   permuted twin rho={rho(perm,y):+.4f}")

# permutation null band for the raw-vs-surplus delta
print("\n--- permutation null band for delta rho(raw) - rho(surplus) ---")
nulls = np.empty(2000)
for i in range(2000):
    p = rng.permutation(n)
    nulls[i] = rho(COLS["raw"][p], y) - rho(COLS["sur"], y)
# proper null: break the raw-grade link only, keep surplus intact -> distribution of
# the delta when raw carries no information
lo, hi = np.percentile(nulls, [2.5, 97.5])
print(f"  raw permuted: delta null mean={nulls.mean():+.4f} CI95=[{lo:+.4f},{hi:+.4f}]")
# symmetric null: permute BOTH, so the delta has mean 0
nulls2 = np.empty(2000)
for i in range(2000):
    nulls2[i] = rho(COLS["raw"][rng.permutation(n)], y) - rho(COLS["sur"][rng.permutation(n)], y)
lo2, hi2 = np.percentile(nulls2, [2.5, 97.5])
print(f"  both permuted: delta null mean={nulls2.mean():+.4f} CI95=[{lo2:+.4f},{hi2:+.4f}]  "
      f"=> band half-width {max(abs(lo2),abs(hi2)):.4f}")

# ---------------------------------------------------------------- time splits
print("\n--- >= 4 independent time splits (debut-year cohorts) ---")
yrs = sorted({r["yr"] for r in rows if r["yr"]})
buckets = {}
for r in rows:
    if r["yr"] is None:
        continue
    buckets.setdefault(r["yr"], []).append(r)
big = [(v, rr) for v, rr in sorted(buckets.items()) if len(rr) >= 60]
print(f"  cohorts with n>=60: {[(v,len(rr)) for v,rr in big]}")
deltas_gs, deltas_rq = [], []
for v, rr in big:
    yy = np.array([r["y"] for r in rr])
    a = np.array([r["raw"] for r in rr]); b = np.array([r["sur"] for r in rr])
    c = np.array([r["qnt"] for r in rr]); cs = np.array([r["cons"] for r in rr])
    dgs = rho(a, yy) - rho(b, yy); drq = rho(a, yy) - rho(c, yy)
    deltas_gs.append(dgs); deltas_rq.append(drq)
    print(f"   {v}  n={len(rr):4d}  raw={rho(a,yy):+.4f} sur={rho(b,yy):+.4f} qnt={rho(c,yy):+.4f} "
          f"cons={rho(cs,yy):+.4f} | raw-sur={dgs:+.4f}  raw-qnt={drq:+.4f}")
print(f"  cross-split mean raw-surplus  = {np.mean(deltas_gs):+.4f}  ({sum(1 for d in deltas_gs if d>0)}/{len(deltas_gs)} positive)")
print(f"  cross-split mean raw-quantile = {np.mean(deltas_rq):+.4f}  ({sum(1 for d in deltas_rq if d>0)}/{len(deltas_rq)} positive)")
