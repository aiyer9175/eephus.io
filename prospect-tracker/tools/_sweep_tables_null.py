"""Lane TABLES: permutation null band for age_rel_level re-centering + the
outcome profile of c_L per level (the 'derive the table from realized outcomes'
attempt)."""
import sys, pathlib, json, random, statistics as st
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import efv_model as em, _sweep_tables_harness as H
from _sweep_tables_gate import prep, metrics

LV=["DSL","CPX","A","A+","AA","AAA"]

for side in ("hit","pit"):
    keys,_m=em._feature_spec(side); lam=em.blend_lambda(side)
    base=prep(side,H.HAND); m0=metrics(base,keys,lam,em.SCORED_YEARS)
    print(f"\n===== side={side}  HAND pooled={m0['pooled']:.4f} block={m0['block']:.4f} =====")
    # (3) PERMUTATION NULL BAND for d_pooled / d_block: 120 row-permutations of the
    # age_rel_level column (identical marginal, zero information).
    dp=[];db=[]
    for s in range(120):
        d=prep(side,H.HAND,permute_seed=9000+s); m=metrics(d,keys,lam,em.SCORED_YEARS)
        dp.append(m["pooled"]-m0["pooled"]); db.append(m["block"]-m0["block"])
    dp.sort(); db.sort()
    band=lambda v:(round(v[int(.025*len(v))],4),round(v[int(.975*len(v))],4))
    print(f"  permutation null band (n=120 permutations of age_rel_level):")
    print(f"    d_pooled 95% band {band(dp)}  mean {st.mean(dp):+.4f}  |  d_block 95% band {band(db)} mean {st.mean(db):+.4f}")
    print(f"    => DESTROYING the feature entirely moves pooled rho by {st.mean(dp):+.4f}; any")
    print(f"       re-centering of it is bounded well inside this.")
    # outcome PROFILE: shift ONE level's typical age over a grid, everything else HAND
    print(f"  outcome profile of c_L (forward-chained pooled rho; HAND value marked *):")
    for lv in LV:
        line=[]
        for dlt in (-2.0,-1.0,-0.5,0.0,0.5,1.0,2.0):
            t=dict(H.HAND); t[lv]=H.HAND[lv]+dlt
            m=metrics(prep(side,t),keys,lam,em.SCORED_YEARS)
            line.append(f"{H.HAND[lv]+dlt:5.1f}:{m['pooled']-m0['pooled']:+.4f}" + ("*" if dlt==0 else " "))
        print(f"    {lv:>4} " + " ".join(line))
