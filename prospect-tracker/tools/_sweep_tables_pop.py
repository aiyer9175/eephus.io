import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
"""ALL-PLAYER MiLB population age-by-level (the 'average player' reference)."""
import statistics as st, json
from collections import defaultdict
import milb_history as mh
LV=["DSL","CPX","A","A+","AA","AAA"]
HAND={"DSL":18.0,"CPX":19.0,"A":20.0,"A+":21.0,"AA":22.5,"AAA":24.0}
MINPA={"hitting":50,"pitching":60}
agg=defaultdict(list)     # (level) -> ages, all players
agg_s=defaultdict(list)   # (level,season)
for season in range(2014,2027):
    for group in ("hitting","pitching"):
        rows = mh.season_splits(None,season,group,fetch=False) if False else None
for season in range(2014,2027):
    for group in ("hitting","pitching"):
        idx = mh.player_index(season, group, fetch=False)
        if not idx: continue
        for mlbam, rs in idx.items():
            for r in rs:
                lv=r.get("level")
                if lv not in LV: continue
                exp = r.get("bf") if group=="pitching" else r.get("pa")
                try: exp=float(exp)
                except (TypeError,ValueError): continue
                if exp < MINPA[group]: continue
                a=r.get("age")
                try: a=float(a)
                except (TypeError,ValueError): continue
                agg[lv].append(a); agg_s[(lv,season)].append(a)
print("== ALL-PLAYER MiLB POPULATION (2014-2026, exposure-qualified level-seasons) ==")
print(f"{'lvl':>4} {'n':>7} {'hand':>5} {'mean':>6} {'med':>6} {'gap':>6}")
for lv in LV:
    v=agg[lv]
    if not v: print(lv,"none"); continue
    print(f"{lv:>4} {len(v):7d} {HAND[lv]:5.1f} {st.mean(v):6.2f} {st.median(v):6.2f} {st.median(v)-HAND[lv]:+6.2f}")
print("\n-- recent only 2022-2026 --")
for lv in LV:
    v=[a for (l,s),va in agg_s.items() if l==lv and s>=2022 for a in va]
    if v: print(f"{lv:>4} n={len(v):6d} med={st.median(v):5.2f} mean={st.mean(v):5.2f} gap={st.median(v)-HAND[lv]:+5.2f}")
