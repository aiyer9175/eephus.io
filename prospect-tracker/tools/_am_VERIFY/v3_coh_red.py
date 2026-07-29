"""ADVERSARIAL VERIFY v3: coherence C1/C2 and redundancy R1/R2 on the SERVED payloads,
plus the suppressor probe the redundancy section owes (is the 'risk' column a
conditional signal or a deterministic restatement?). Read-only."""
import json, math, random
from pathlib import Path
from collections import Counter, defaultdict
ROOT = Path(__file__).resolve().parents[2]

def spearman(xs, ys):
    n = len(xs)
    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i]); r = [0.0]*n; i = 0
        while i < n:
            j = i
            while j+1 < n and v[order[j+1]] == v[order[i]]: j += 1
            avg = (i+j)/2+1
            for k in range(i, j+1): r[order[k]] = avg
            i = j+1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx = sum(rx)/n; my = sum(ry)/n
    cov = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
    vx = sum((a-mx)**2 for a in rx); vy = sum((b-my)**2 for b in ry)
    if vx == 0 or vy == 0: return float("nan")
    return cov/math.sqrt(vx*vy)

tv = json.loads((ROOT/"data/trade_values.json").read_text(encoding="utf-8"))
pl = tv["players"]
xfv = json.loads((ROOT/"data/xfv.json").read_text(encoding="utf-8"))["by_player"]
print("trade_values generated_at", tv.get("generated_at"), "n", len(pl))

# ---------------- C1: default-sort vs displayed letter -----------------------
def tb_grade_bucket(mm):
    # rank-equivalent proxy: the letter is a monotone step function of mm, so any
    # displayed-order violation is exactly a trade_value_mm order violation.
    return mm
rows = [p for p in pl if p.get("xfv_grade") is not None and p.get("trade_value_mm") is not None]
rows.sort(key=lambda p: (-float(p["xfv_grade"]),
                         -(float(p["xfv_war_6yr"]) if p.get("xfv_war_6yr") is not None else -1e9)))
inv = 0; examples = []
for a, b in zip(rows, rows[1:]):
    if float(b["trade_value_mm"]) > float(a["trade_value_mm"]):
        inv += 1
        if len(examples) < 6 and float(b["trade_value_mm"]) - float(a["trade_value_mm"]) > 80:
            examples.append((a["player_name"], a["trade_value_mm"], b["player_name"], b["trade_value_mm"]))
print(f"\nC1 default-sort (xfv_grade desc, efvTie) adjacent pairs where DISPLAYED $ increases: "
      f"{inv} / {len(rows)-1} = {100*inv/(len(rows)-1):.1f}%")
for e in examples: print("   ", f"{e[0]} ${e[1]}M  ABOVE  {e[2]} ${e[3]}M")
# and what the proposed fix does
rows2 = sorted(rows, key=lambda p: -float(p["trade_value_mm"]))
inv2 = sum(1 for a, b in zip(rows2, rows2[1:]) if float(b["trade_value_mm"]) > float(a["trade_value_mm"]))
print(f"   after PATCH 2 (sort by trade_value_mm): {inv2} inversions")
# what PATCH 1 ALONE does (sort by quantile grade, still display $ letter)
r3 = [p for p in rows if xfv.get(p["player_key"], {}).get("xfv_grade_quantile") is not None]
r3.sort(key=lambda p: -float(xfv[p["player_key"]]["xfv_grade_quantile"]))
inv3 = sum(1 for a, b in zip(r3, r3[1:]) if float(b["trade_value_mm"]) > float(a["trade_value_mm"]))
print(f"   PATCH 1 ALONE (sort by xfv_grade_quantile, letter still from $): "
      f"{inv3} / {len(r3)-1} = {100*inv3/(len(r3)-1):.1f}%  <- does NOT fix C1")

# ---------------- C2: two grades for the same player -------------------------
pairs = [(p["player_key"], float(p["xfv_grade"]), float(xfv[p["player_key"]]["xfv_grade_quantile"]))
         for p in pl if p.get("xfv_grade") is not None
         and xfv.get(p["player_key"], {}).get("xfv_grade_quantile") is not None]
d = [abs(b-c) for _, b, c in pairs]
print(f"\nC2 board xfv_grade vs prospx xfv_grade_quantile: n={len(pairs)} "
      f"rho={spearman([b for _,b,_ in pairs],[c for _,_,c in pairs]):.4f} "
      f"mean|diff|={sum(d)/len(d):.2f}  >=5pts: {sum(1 for x in d if x>=5)}")
worst = sorted(pairs, key=lambda t: -abs(t[1]-t[2]))[:4]
for k, b, c in worst: print(f"    {k}: board {b}  prospx {c}")
# whole-xfv version (all 9287)
allp = [(v["xfv_grade"], v["xfv_grade_quantile"]) for v in xfv.values()
        if v.get("xfv_grade") is not None and v.get("xfv_grade_quantile") is not None]
print(f"    whole xfv.json n={len(allp)} rho={spearman([a for a,_ in allp],[b for _,b in allp]):.4f} "
      f"mean|diff|={sum(abs(a-b) for a,b in allp)/len(allp):.2f}")

# ---------------- R1/R2: redundancy on the ACTIVE board ----------------------
act = [p for p in pl if p.get("status") == "active"]
print(f"\nR1 actives n={len(act)}")
def col(name, src="tv"):
    out = []
    for p in act:
        v = p.get(name) if src == "tv" else (xfv.get(p["player_key"], {}) or {}).get(name)
        out.append(None if v is None else float(v))
    return out
S = col("posterior_surplus_mm")
have = [i for i, v in enumerate(S) if v is not None]
def sub(c): return [c[i] for i in have]
cols = {"surplus_mm": sub(S), "trade_value_mm": sub(col("trade_value_mm")),
        "downside_mm": sub(col("downside_mm")), "risk_mm": sub(col("risk_mm")),
        "sortino": sub(col("sortino"))}
xd = [(xfv.get(act[i]["player_key"], {}) or {}).get("dist") or {} for i in have]
cols["dist_mean_mm"] = [ (v.get("mean_mm") if v.get("mean_mm") is not None else float("nan")) for v in xd ]
ok = [i for i in range(len(have)) if all(c[i] is not None and not (isinstance(c[i], float) and math.isnan(c[i])) for c in cols.values())]
cols = {k: [v[i] for i in ok] for k, v in cols.items()}
n = len(ok); print("  complete rows", n)
base = cols["surplus_mm"]
for k, v in cols.items():
    if k == "surplus_mm": continue
    print(f"    rho({k:14s}, surplus_mm) = {spearman(v, base):+.4f}   distinct={len(set(v))}")
eq = sum(1 for a, b in zip(cols["trade_value_mm"], base) if a == b)
print(f"    trade_value_mm EXACTLY == surplus_mm on {eq}/{n}")
eqm = sum(1 for a, b in zip(cols["dist_mean_mm"], base) if abs(a-b) < 1e-9)
print(f"    dist_mean_mm  EXACTLY == surplus_mm on {eqm}/{n}")
# non-floored honest cut
nf = [i for i in range(n) if base[i] > 0]
print(f"  NON-FLOORED actives n={len(nf)}")
for k, v in cols.items():
    if k == "surplus_mm": continue
    print(f"    rho({k:14s}, surplus_mm) = {spearman([v[i] for i in nf],[base[i] for i in nf]):+.4f}"
          f"   distinct={len(set(v[i] for i in nf))}")

# ---------------- SUPPRESSOR PROBE (item d) ---------------------------------
# Is the risk column a DETERMINISTIC function of (displayed eFV grade, role)?
# If sortino is constant inside every (grade, role) cell, it carries no
# conditional information at all - it cannot be a suppressor, it is a relabel.
grade = [ (xfv.get(act[have[i]]["player_key"], {}) or {}).get("xfv_grade") for i in ok ]
posn  = [ act[have[i]].get("position") for i in ok ]
cell = defaultdict(list)
for g, ps, s in zip(grade, posn, cols["sortino"]):
    if g is None: continue
    cell[(round(float(g), 1), str(ps))].append(s)
multi = {k: v for k, v in cell.items() if len(v) > 1}
const = sum(1 for v in multi.values() if len(set(v)) == 1)
print(f"\nSUPPRESSOR PROBE: (xfv_grade, position) cells with >1 player: {len(multi)}; "
      f"cells where sortino is CONSTANT: {const} ({100*const/max(1,len(multi)):.1f}%)")
cell2 = defaultdict(list)
for g, ps, s in zip(grade, posn, cols["downside_mm"]):
    if g is None: continue
    cell2[(round(float(g), 1), str(ps))].append(s)
m2 = {k: v for k, v in cell2.items() if len(v) > 1}
c2 = sum(1 for v in m2.values() if len(set(v)) == 1)
print(f"                  downside_mm CONSTANT in {c2}/{len(m2)} cells "
      f"({100*c2/max(1,len(m2)):.1f}%)")
# re-ranking power: how many adjacent surplus-order pairs does a sortino sort flip?
idx = sorted(range(n), key=lambda i: -base[i])
srt = sorted(range(n), key=lambda i: -cols["sortino"][i])
pos_in = {v: j for j, v in enumerate(idx)}
flips = sum(1 for a, b in zip(srt, srt[1:]) if pos_in[a] > pos_in[b])
print(f"                  sorting by sortino flips {flips}/{n-1} adjacent surplus-order pairs; "
      f"sortino takes {len(set(cols['sortino']))} distinct values over {n} players")
