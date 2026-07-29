"""Lane: prospect. (e) LEAK PROBE on the Pipeline vintage ETA + the star-odds test.

LEAK PROBE: a back-revised archive would show (a) the same player's published eta
never changing across vintages and (b) that eta equal to his realized debut year.
A genuine point-in-time board shows the eta MOVING as the player advances.

STAR ODDS: does the point-in-time Pipeline RANK (1-100, full coverage) predict
'2+ control seasons of >=4 WAR' better than the served predictor (the published
FanGraphs tier odds keyed on consensus FV)?
"""
import json, statistics, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "data"
import storage
from source_backtest import _spearman, _auc

pv = json.loads((D / "pipeline_vintages.json").read_text(encoding="utf-8"))["vintages"]
by_player = defaultdict(dict)
for y, recs in pv.items():
    for r in recs:
        if r.get("mlbam"):
            by_player[int(r["mlbam"])][int(y)] = r

print("=" * 74)
print("LEAK PROBE on the point-in-time ETA")
print("=" * 74)
multi = {m: v for m, v in by_player.items() if len(v) >= 2}
moved = same = 0
for m, v in multi.items():
    es = [int(str(r["eta"])[:4]) for y, r in sorted(v.items()) if r.get("eta")]
    if len(es) < 2:
        continue
    if len(set(es)) > 1:
        moved += 1
    else:
        same += 1
print(f"  players on >=2 vintages: {len(multi)}   published eta CHANGES across vintages: {moved}"
      f"   never changes: {same}")
print("  (a back-revised archive would show ~0 changes)")
ex = [(m, {y: str(r.get('eta')) for y, r in sorted(v.items())})
      for m, v in list(multi.items())[:6]]
for m, e in ex:
    print("   mlbam", m, e)

print("\n" + "=" * 74)
print("STAR ODDS: Pipeline point-in-time RANK vs the served FV-tier predictor")
print("=" * 74)
# realized star = 2+ seasons of >=4 bWAR in debut..debut+6
with storage.connect() as con:
    cw, ident = {}, {}
    for r in con.execute("SELECT player_key, payload_json FROM career_war"):
        try:
            s = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
        except ValueError:
            continue
        cw[r["player_key"]] = {int(y): float(w) for y, w in s.items()}
debuts = json.loads((D / "debuts.json").read_text(encoding="utf-8"))
by_mlbam = {}
for d in debuts:
    if d.get("mlbam_id") and d.get("player_key") and d.get("debut_date"):
        by_mlbam[int(d["mlbam_id"])] = (d["player_key"], int(d["debut_date"][:4]))

xfv = json.loads((D / "xfv.json").read_text(encoding="utf-8"))["by_player"]
LAST_RESOLVED = 2025
rows = []
for m, v in by_player.items():
    hit = by_mlbam.get(m)
    if not hit:
        continue
    pk, dy = hit
    if dy + 6 > LAST_RESOLVED:          # window must be fully observed
        continue
    seasons = cw.get(pk) or {}
    star = sum(1 for y, w in seasons.items() if dy <= y <= dy + 6 and w >= 4.0) >= 2
    vy = min(v)                          # EARLIEST vintage listing (most pre-debut)
    if vy >= dy:                         # must be strictly pre-debut
        cand = [y for y in v if y < dy]
        if not cand:
            continue
        vy = min(cand)
    rec = v[vy]
    xe = xfv.get(pk) or {}
    rows.append(dict(pk=pk, m=m, vy=vy, rank=int(rec["rank"]), star=star,
                     cons=xe.get("consensus_fv"), efv=xe.get("xfv_grade_quantile"),
                     dy=dy))
print("resolved, strictly-pre-debut Pipeline entries:", len(rows),
      " star rate:", round(float(np.mean([r["star"] for r in rows])), 4))
if len(rows) < 60:
    print("INSUFFICIENT n - UNAVAILABLE")
    sys.exit(0)
lab = [r["star"] for r in rows]
negrank = [-r["rank"] for r in rows]      # better rank = higher score
print(f"  AUC(pipeline rank)        = {_auc(negrank, lab):.4f}   n={len(rows)}")
for col in ("cons", "efv"):
    sub = [(r[col], r["star"]) for r in rows if r.get(col) is not None]
    if len(sub) >= 60:
        print(f"  AUC({col:4s})                = {_auc([a for a,_ in sub],[b for _,b in sub]):.4f}   n={len(sub)}")
# joint: rank on top of consensus FV
sub = [r for r in rows if r.get("cons") is not None]
print("\n  paired bootstrap of AUC(rank) - AUC(consensus_fv) on the joint rows (n=%d)" % len(sub))
rng = np.random.default_rng(20260725)
nn = len(sub)
d = np.empty(3000)
for i in range(3000):
    ix = rng.integers(0, nn, nn)
    s = [sub[j] for j in ix]
    l = [x["star"] for x in s]
    if len(set(l)) < 2:
        d[i] = 0.0; continue
    d[i] = (_auc([-x["rank"] for x in s], l) - _auc([x["cons"] for x in s], l))
lo, hi = np.percentile(d, [2.5, 97.5])
obs = _auc([-x["rank"] for x in sub], [x["star"] for x in sub]) - \
      _auc([x["cons"] for x in sub], [x["star"] for x in sub])
print(f"  obs={obs:+.4f} mean={d.mean():+.4f} sd={d.std():.4f} CI95=[{lo:+.4f},{hi:+.4f}] "
      f"P(>0)={float((d>0).mean()):.3f} MDE95={1.96*d.std():.4f}")
print("\n  ZERO-INFO CONTROL: permuted rank column")
pr = [-x["rank"] for x in sub]; rng.shuffle(pr)
print(f"   permuted AUC={_auc(pr,[x['star'] for x in sub]):.4f}")
print("\n  PER-VINTAGE (time splits)")
for vy in sorted({r["vy"] for r in rows}):
    s = [r for r in rows if r["vy"] == vy]
    l = [r["star"] for r in s]
    if len(s) < 25 or len(set(l)) < 2:
        continue
    sc = [r for r in s if r.get("cons") is not None]
    a1 = _auc([-r["rank"] for r in s], l)
    a2 = (_auc([r["cons"] for r in sc], [r["star"] for r in sc])
          if len(sc) >= 25 and len(set(r["star"] for r in sc)) > 1 else None)
    print(f"   {vy} n={len(s):4d} stars={sum(l):3d}  AUC(rank)={a1:.4f}  "
          f"AUC(cons)={a2 if a2 is None else round(a2,4)}")
