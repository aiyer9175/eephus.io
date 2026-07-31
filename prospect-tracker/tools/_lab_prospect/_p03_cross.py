"""Lane: prospect. (b) cross-surface coherence checks C1..C7."""
import json, statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data"
L = lambda n: json.loads((D / n).read_text(encoding="utf-8"))

xfv = L("xfv.json")["by_player"]
tv = L("trade_values.json")["players"]
mp = L("mlb_projections.json")
pr = {r["key"]: r for r in mp["prospects"]}
tvd = {r["player_key"]: r for r in tv}

print("=" * 78)
print("C1  same prospect, three dollar figures")
print("=" * 78)
rows = []
for k, p in pr.items():
    xe = xfv.get(k)
    t = tvd.get(k)
    if not xe or not t:
        continue
    rows.append((k, p.get("name"),
                 p.get("surNpv") / 1e6 if p.get("surNpv") is not None else None,
                 xe.get("surplus_mm"), t.get("trade_value_mm"),
                 t.get("surplus_source"), p.get("fv"), xe.get("xfv_grade_quantile"),
                 t.get("xfv_grade"), p.get("eta")))
print("joined prospects (proj & xfv & tv):", len(rows))
bad = [r for r in rows if r[2] is not None and r[3] is not None
       and abs(r[2] - r[3]) > max(1.0, 0.10 * max(abs(r[2]), abs(r[3])))]
print("proj surNpv vs xfv surplus_mm  |diff|>max(1.0, 10%%):", len(bad), "of", len(rows))
bad.sort(key=lambda r: -abs(r[2] - r[3]))
print(f"{'player':26s} {'projSurNpv$M':>12s} {'eFVsurplus$M':>12s} {'tradeVal$M':>10s} {'src':11s} {'projFV':>6s} {'eFVq':>5s} {'tvGrade':>7s} eta")
for r in bad[:25]:
    print(f"{str(r[1])[:26]:26s} {r[2]:12.1f} {r[3]:12.1f} {(r[4] if r[4] is not None else float('nan')):10.1f} {str(r[5]):11s} {r[6]:6.1f} {r[7]:5.1f} {str(r[8]):>7s} {r[9]}")

print()
print("=" * 78)
print("C2  eFV grade shown on the trade board vs eFV grade shown on prospx")
print("=" * 78)
g = [(k, x.get("xfv_grade_quantile"), tvd[k].get("xfv_grade"))
     for k, x in xfv.items() if k in tvd and tvd[k].get("xfv_grade") is not None
     and x.get("xfv_grade_quantile") is not None]
d = [abs(a - b) for _, a, b in g]
print("n joined:", len(g), "max|diff|:", max(d) if d else None,
      "n diff>0.05:", sum(1 for v in d if v > 0.05))
qq = [(k, a, b) for k, a, b in g if abs(a - b) > 0.05]
for k, a, b in qq[:10]:
    print("  ", k, "prospx eFV", a, "board xfv_grade", b)
# which field does the board carry?
gr = [(k, x.get("xfv_grade"), x.get("xfv_grade_quantile"), x.get("xfv_grade_model_raw"),
       tvd[k].get("xfv_grade")) for k, x in xfv.items() if k in tvd][:5]
for r in gr:
    print("   sample", r)

print()
print("=" * 78)
print("C3  proj prospect fv (fv_source) vs eFV quantile grade")
print("=" * 78)
srcs = defaultdict(int)
mism = []
for k, p in pr.items():
    srcs[p.get("fv_source")] += 1
    xe = xfv.get(k)
    if p.get("fv_source") == "xfv" and xe and xe.get("xfv_grade_quantile") is not None:
        if abs(p["fv"] - xe["xfv_grade_quantile"]) > 0.051:
            mism.append((k, p["fv"], xe["xfv_grade_quantile"], xe.get("xfv_grade"),
                         xe.get("xfv_grade_realized")))
print("fv_source counts:", dict(srcs))
print("fv_source=xfv rows where proj fv != eFV quantile:", len(mism))
for m in mism[:15]:
    print("  ", m)

print()
print("=" * 78)
print("C4  monotonicity: does higher eFV surplus always mean higher trade value?")
print("=" * 78)
pp = [(k, xfv[k]["surplus_mm"], tvd[k]["trade_value_mm"], tvd[k].get("surplus_source"),
       tvd[k].get("status"))
      for k in xfv if k in tvd and xfv[k].get("surplus_mm") is not None
      and tvd[k].get("trade_value_mm") is not None]
print("n:", len(pp))
by_src = defaultdict(list)
for k, s, t, src, st in pp:
    by_src[(src, st)].append((k, s, t))
for key, v in sorted(by_src.items(), key=lambda kv: -len(kv[1])):
    if len(v) < 5:
        continue
    ss = [a for _, a, _ in v]; ts = [b for _, _, b in v]
    try:
        from scipy.stats import spearmanr
        rho = spearmanr(ss, ts).correlation
    except Exception:
        rho = None
    dd = [abs(a - b) for _, a, b in v]
    print(f"  {str(key):40s} n={len(v):5d} rho={rho if rho is None else round(rho,4)} "
          f"medianAbsDiff={statistics.median(dd):.2f} maxAbsDiff={max(dd):.1f}")

print()
print("=" * 78)
print("C5  p_bust three ways")
print("=" * 78)
pb = [(k, xfv[k].get("p_bust"), pr[k].get("pBust") if k in pr else None,
       tvd[k].get("p_bust") if k in tvd else None) for k in xfv]
n1 = [(k, a, b) for k, a, b, c in pb if a is not None and b is not None and abs(a - b) > 0.01]
n2 = [(k, a, c) for k, a, b, c in pb if a is not None and c is not None and abs(a - c) > 0.01]
print("xfv.p_bust vs proj.pBust mismatches >0.01:", len(n1), "of",
      sum(1 for k, a, b, c in pb if a is not None and b is not None))
for r in n1[:10]:
    print("   ", r)
print("xfv.p_bust vs trade_values.p_bust mismatches >0.01:", len(n2), "of",
      sum(1 for k, a, b, c in pb if a is not None and c is not None))
for r in n2[:10]:
    print("   ", r)
