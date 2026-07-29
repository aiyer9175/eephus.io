"""Lane TABLES: empirical re-derivation of _TYPICAL_LEVEL_AGE with CIs + the
affine-in-level_rank identification decomposition."""
import sys, pathlib, json, random, statistics as st
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import numpy as np
from efv_dataset import matrix_path, live_matrix_path

LV=["DSL","CPX","A","A+","AA","AAA"]; RK={l:i for i,l in enumerate(LV)}
HAND={"DSL":18.0,"CPX":19.0,"A":20.0,"A+":21.0,"AA":22.5,"AAA":24.0}

def rows_from(paths):
    out=[]
    for p in paths:
        for r in json.loads(p.read_text(encoding="utf-8")):
            m=r.get("milb") or {}
            if m.get("milb_level") in RK and m.get("age") is not None and not m.get("age_missing"):
                out.append((m["milb_level"], float(m["age"]), r.get("weight",1.0),
                            r.get("target_censored"), r.get("kind"), r.get("player_key"),
                            int(m.get("milb_season") or 0)))
    return out

def boot_mean(v,B=4000,seed=11):
    rnd=random.Random(seed); n=len(v)
    s=sorted(sum(v[rnd.randrange(n)] for _ in range(n))/n for _ in range(B))
    return s[int(.025*B)], s[int(.975*B)]

def table(rows, name):
    print(f"\n=== {name} ===")
    print(f"{'lvl':>4} {'n':>6} {'hand':>6} {'mean':>6} {'CI95':>16} {'med':>5} {'gap(mean-hand)':>15}")
    out={}
    for lv in LV:
        v=[a for l,a,*_ in rows if l==lv]
        if len(v)<25: print(f"{lv:>4} {len(v):6d}  (sparse, skipped)"); continue
        m=st.mean(v); lo,hi=boot_mean(v)
        out[lv]=round(m,2)
        print(f"{lv:>4} {len(v):6d} {HAND[lv]:6.1f} {m:6.2f} [{lo:5.2f},{hi:5.2f}] {st.median(v):5.1f} {m-HAND[lv]:+15.2f}")
    return out

def affine_decomp(tbl, label):
    """Split a level-age table into (affine in level_rank) + residual curvature.
    Only the residual can change a model that already carries a FREE level_rank
    coefficient alongside a FREE age_rel_level coefficient."""
    ks=[l for l in LV if l in tbl]
    x=np.array([RK[l] for l in ks],float); y=np.array([tbl[l] for l in ks],float)
    A=np.vstack([np.ones_like(x),x]).T
    coef,*_=np.linalg.lstsq(A,y,rcond=None)
    fit=A@coef; res=y-fit
    r2=1-((res**2).sum()/((y-y.mean())**2).sum())
    print(f"  {label:22s} affine fit age = {coef[0]:.3f} + {coef[1]:.3f}*rank  R2={r2:.4f}  "
          f"residual(curvature) = {dict(zip(ks,[round(v,3) for v in res]))}")
    return dict(zip(ks,res))

tr = rows_from([matrix_path("hit"),matrix_path("pit")])
tr_h = rows_from([matrix_path("hit")]); tr_p = rows_from([matrix_path("pit")])
lv_ = rows_from([live_matrix_path("hit"),live_matrix_path("pit")])

T_TRAIN = table(tr, "TRAINING prospect pool (both sides, final pre-decision MiLB season)")
T_TRH   = table(tr_h,"TRAINING hitters")
T_TRP   = table(tr_p,"TRAINING pitchers")
T_LIVE  = table(lv_, "LIVE board pool (the population the table is APPLIED to)")

# live restricted to CURRENT-season reads (non-stale)
lv_cur=[r for r in lv_ if r[6]>=2025]
T_LIVEC= table(lv_cur,"LIVE board, 2025-2026 reads only")

print("\n=== IDENTIFICATION: affine-in-level_rank decomposition ===")
print("  (hitter model carries BOTH age_rel_level and level_rank as free ridge features,")
print("   so any component of the table that is affine in level_rank is exactly")
print("   reparametrised away; only the residual curvature can move predictions.)")
r_hand=affine_decomp(HAND,"HAND (shipped)")
r_tr  =affine_decomp(T_TRAIN,"EMP training prospects")
r_live=affine_decomp(T_LIVE,"EMP live board")
r_livc=affine_decomp(T_LIVEC,"EMP live 2025-26")
print("\n  curvature DELTA vs hand (this is the only part a level_rank-bearing model sees):")
for nm,rr in (("emp_train",r_tr),("emp_live",r_live),("emp_live_cur",r_livc)):
    print(f"   {nm:14s}", {k: round(rr[k]-r_hand[k],3) for k in r_hand if k in rr})

json.dump({"train":T_TRAIN,"train_hit":T_TRH,"train_pit":T_TRP,
           "live":T_LIVE,"live_current":T_LIVEC},
          open(pathlib.Path(__file__).parent/"_sweep_tables_derived.json","w"),indent=1)
