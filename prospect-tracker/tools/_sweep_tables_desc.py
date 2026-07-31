"""Lane TABLES scratch lab: descriptive re-derivation of _TYPICAL_LEVEL_AGE."""
import json, statistics as st
from collections import defaultdict
from pathlib import Path
D = Path(__file__).parent.parent / "data"
LV = ["DSL","CPX","A","A+","AA","AAA"]
HAND = {"DSL":18.0,"CPX":19.0,"A":20.0,"A+":21.0,"AA":22.5,"AAA":24.0}

def load(p): return json.loads((D/p).read_text(encoding="utf-8"))

def boot_med(vals, B=2000, seed=7):
    import random
    rnd = random.Random(seed); n=len(vals); out=[]
    for _ in range(B):
        s=[vals[rnd.randrange(n)] for _ in range(n)]
        out.append(st.median(s))
    out.sort()
    return out[int(.025*B)], out[int(.975*B)]

rows = []
for f,side in (("xfv_hitter_matrix.json","hit"),("xfv_pitcher_matrix.json","pit")):
    for r in load(f):
        m = r.get("milb") or {}
        if m.get("milb_level") and m.get("age") is not None and not m.get("age_missing"):
            rows.append((side, r["kind"], m["milb_level"], float(m["age"]), int(m["milb_season"]),
                         r.get("target_censored"), r.get("weight"), r.get("player_key"),
                         r.get("consensus_fv_raw")))

print("== TRAINING PROSPECT POPULATION (final pre-decision MiLB season, one row/player) ==")
print(f"{'lvl':>4} {'n':>5} {'hand':>5} {'mean':>6} {'med':>6} {'CI95 med':>16} {'p25':>5} {'p75':>5} {'gap':>6}")
for lv in LV:
    v = sorted(x[3] for x in rows if x[2]==lv)
    if len(v)<10: print(lv, len(v), "sparse"); continue
    med=st.median(v); lo,hi=boot_med(v)
    print(f"{lv:>4} {len(v):5d} {HAND[lv]:5.1f} {st.mean(v):6.2f} {med:6.2f} "
          f"[{lo:5.2f},{hi:5.2f}] {v[int(.25*len(v))]:5.1f} {v[int(.75*len(v))]:5.1f} {med-HAND[lv]:+6.2f}")

for side in ("hit","pit"):
    print(f"\n-- side={side} --")
    for lv in LV:
        v = sorted(x[3] for x in rows if x[2]==lv and x[0]==side)
        if len(v)<10: continue
        print(f"{lv:>4} n={len(v):5d} med={st.median(v):5.2f} hand={HAND[lv]:5.1f} gap={st.median(v)-HAND[lv]:+5.2f}")

print("\n-- by kind (debuted vs bust) --")
for kind in ("debuted","bust"):
    print(f"  {kind}:", {lv: (len([x for x in rows if x[2]==lv and x[1]==kind]),
                              round(st.median([x[3] for x in rows if x[2]==lv and x[1]==kind]),2))
                         for lv in LV if len([x for x in rows if x[2]==lv and x[1]==kind])>=10})

print("\n-- era drift: median age by level x season bucket --")
for lv in LV:
    line=[]
    for lo,hi in ((2014,2017),(2018,2021),(2022,2025)):
        v=[x[3] for x in rows if x[2]==lv and lo<=x[4]<=hi]
        line.append(f"{lo}-{hi}:{(round(st.median(v),2) if len(v)>=10 else '  na')}(n={len(v)})")
    print(f"{lv:>4} " + "  ".join(line))

print("\n== LIVE (served) BOARD POPULATION ==")
lrows=[]
for f,side in (("xfv_live_hitter_matrix.json","hit"),("xfv_live_pitcher_matrix.json","pit")):
    for r in load(f):
        m=r.get("milb") or {}
        if m.get("milb_level") and m.get("age") is not None and not m.get("age_missing"):
            lrows.append((side,m["milb_level"],float(m["age"]),int(m["milb_season"]),r["player_key"]))
print(f"{'lvl':>4} {'n':>5} {'hand':>5} {'med':>6} {'CI95':>16} {'gap':>6}")
for lv in LV:
    v=sorted(x[2] for x in lrows if x[1]==lv)
    if len(v)<10: continue
    lo,hi=boot_med(v)
    print(f"{lv:>4} {len(v):5d} {HAND[lv]:5.1f} {st.median(v):6.2f} [{lo:5.2f},{hi:5.2f}] {st.median(v)-HAND[lv]:+6.2f}")
