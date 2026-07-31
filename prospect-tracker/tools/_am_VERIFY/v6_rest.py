"""ADVERSARIAL VERIFY v6: remaining served-payload checks. Read-only.
 (1) characterize the held-out subset used in v1/v4
 (2) pipeline_vintages `eta` point-in-time leak probe (L1) - independent re-run
 (3) C5 summed LightGBM quantile points on /projections/ vets
 (4) C4 p_bust disagreement prospx vs projections
"""
import json, statistics
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
J = lambda p: json.loads((ROOT/p).read_text(encoding="utf-8"))

print("=" * 70)
print("(1) HELD-OUT SUBSET CHARACTER")
by = J("data/xfv.json")["by_player"]
fitted = set()
for f in ("data/xfv_scored.json", "data/xfv_scored_pitcher.json"):
    for r in J(f): fitted.add(r["player_key"])
pool = {k: v for k, v in by.items()
        if v.get("kind") in ("debuted", "resolved", "graduated") and v.get("realized_war") is not None}
ins = {k: v for k, v in pool.items() if k in fitted}
oos = {k: v for k, v in pool.items() if k not in fitted}
print("  in-sample", len(ins), "held-out", len(oos))
print("  side in-sample", dict(Counter(v["side"] for v in ins.values())),
      " held-out", dict(Counter(v["side"] for v in oos.values())))
for lab, s in (("in-sample", ins), ("held-out", oos)):
    print(f"  {lab:10s} realized_war mean {statistics.mean(v['realized_war'] for v in s.values()):.2f} "
          f"median {statistics.median(v['realized_war'] for v in s.values()):.2f} | "
          f"consensus_fv mean {statistics.mean(v['consensus_fv'] for v in s.values()):.2f} | "
          f"xfv_grade_quantile mean {statistics.mean(v['xfv_grade_quantile'] for v in s.values()):.2f}")
bg = ROOT/"data/xfv_backgrade.json"
if bg.exists():
    bgk = {r["player_key"] for r in json.loads(bg.read_text(encoding='utf-8')).get("scored", [])}
    print(f"  scored by run_backgrade (one shared production fit): in-sample "
          f"{len(set(ins)&bgk)}/{len(ins)}, held-out {len(set(oos)&bgk)}/{len(oos)}")

print("=" * 70)
print("(2) PIPELINE VINTAGE `eta` POINT-IN-TIME PROBE")
pv = J("data/pipeline_vintages.json")
vin = pv["vintages"]
eta_by = defaultdict(dict)      # mlbam -> {year: eta}
rank_by = defaultdict(dict)
for y, rows in vin.items():
    for r in (rows if isinstance(rows, list) else rows.get("players", [])):
        mk = r.get("mlbam") or r.get("mlbam_id")
        if mk is None: continue
        if r.get("eta") is not None: eta_by[mk][int(y)] = r["eta"]
        if r.get("rank") is not None: rank_by[mk][int(y)] = r["rank"]
multi = {k: v for k, v in eta_by.items() if len(v) >= 2}
same = sum(1 for v in multi.values() if len(set(v.values())) == 1)
print(f"  players on >=2 boards with an eta: {len(multi)}; IDENTICAL eta on every board: {same} "
      f"({100*same/max(1,len(multi)):.1f}%)")
mv = [k for k, v in multi.items() if len(set(v.values())) > 1]
print(f"  players whose eta EVER moves: {len(mv)}")
rmulti = {k: v for k, v in rank_by.items() if len(v) >= 2}
rsame = sum(1 for v in rmulti.values() if len(set(v.values())) == 1)
print(f"  CONTROL - rank on >=2 boards: {len(rmulti)}; identical rank every board: {rsame} "
      f"({100*rsame/max(1,len(rmulti)):.1f}%)  -> rank DOES move, eta does not")
ex = list(multi.items())[:3]
for k, v in ex: print(f"    mlbam {k}: {dict(sorted(v.items()))}")

print("=" * 70)
print("(3) C5 SUMMED QUANTILE POINTS ON /projections/")
pp = ROOT/"data/projections.json"
if not pp.exists():
    cands = sorted(ROOT.glob("data/proj*.json"))
    print("  data/projections.json missing; candidates:", [c.name for c in cands][:10])
else:
    P = json.loads(pp.read_text(encoding="utf-8"))
    rows = P.get("players") if isinstance(P, dict) else P
    vet = pros = vmatch = pmatch = 0
    for p in rows:
        arr = p.get("warP10"); tot = p.get("warTotalP10")
        if arr is None or tot is None: continue
        is_pros = (p.get("kind") == "prospect") or (p.get("is_prospect") is True) or (p.get("type") == "prospect")
        m = abs(round(sum(arr), 1) - float(tot)) < 1e-9
        if is_pros: pros += 1; pmatch += m
        else: vet += 1; vmatch += m
    print(f"  VET rows: {vmatch}/{vet} have warTotalP10 == sum(per-year P10 array)")
    print(f"  PROSPECT rows: {pmatch}/{pros} match a naive sum")

print("=" * 70)
print("(4) C4 P(BUST) prospx vs /projections/")
if pp.exists():
    P = json.loads(pp.read_text(encoding="utf-8"))
    rows = P.get("players") if isinstance(P, dict) else P
    n = big = 0; ex = []
    for p in rows:
        pk = p.get("player_key"); pb = p.get("pBust") if "pBust" in p else p.get("p_bust")
        if pk is None or pb is None: continue
        xb = (by.get(pk) or {}).get("p_bust")
        if xb is None: continue
        n += 1
        if abs(float(pb) - float(xb)) > 0.01:
            big += 1
            if len(ex) < 4: ex.append((pk, round(float(xb), 3), round(float(pb), 3)))
    print(f"  joined {n}; differ by >0.01: {big}")
    for e in ex: print(f"    {e[0]}: prospx {e[1]}  /projections/ {e[2]}")
