"""Lane TABLES: full EFV_GATE_STANDARD run for a _TYPICAL_LEVEL_AGE swap.
Paired bootstrap (train+test resampled, refit per draw) + zero-information
control + permutation null band + >=4 independent time splits. READ-ONLY."""
import sys, pathlib, json, random, statistics as st, time
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np
import efv_model as em
import _sweep_tables_harness as H
from prospect_path import _fit_ridge, _predict, _spearman

D=json.load(open(pathlib.Path(__file__).parent/"_sweep_tables_derived.json"))
CANDS={"EMP_TRAIN":D["train"],"EMP_LIVE":D["live"]}
ALL_FOLDS=tuple(range(2017,2025))

def prep(side, tbl, permute_seed=None):
    rows = H.apply_table(H.load(side), tbl, permute_seed=permute_seed)
    return em._prep([r for r in rows if bool(r.get("is_pitcher"))==(side=="pit")
                     and not (r.get("kind")=="bust" and r.get("bust_recent"))],
                    "target_censored", side)

def metrics(data, keys, lam, years, idx=None):
    if idx is not None:
        data=[data[i] for i in idx]
    folds=H.fwd_folds(data, years, keys, lam)
    if not folds: return None
    pr,_=H.pooled_rho(folds); br,_=H.block_rho(folds)
    sc=[a for yr in folds for a,_,_,_,_ in folds[yr]]
    lb=[b>=3.0 for yr in folds for _,b,_,_,_ in folds[yr]]
    t,_=H.t45(folds)
    return {"pooled":pr,"block":br,"auc":H.auc(sc,lb),"t45":t,
            "per_fold":{yr:_spearman([a for a,_,_,_,_ in rec],[b for _,b,_,_,_ in rec])
                        for yr,rec in folds.items() if len(rec)>=15}}

def run(side, B=800, seed=7):
    keys,_m=em._feature_spec(side); lam=em.blend_lambda(side)
    base=prep(side,H.HAND)
    n=len(base)
    print(f"\n########## side={side}  n_pool={n}  lambda={lam}  folds={ALL_FOLDS} ##########")
    m0=metrics(base,keys,lam,em.SCORED_YEARS)
    print(f" HAND (SCORED_YEARS {em.SCORED_YEARS}): pooled={m0['pooled']:.4f} block={m0['block']:.4f} auc={m0['auc']:.4f} t45={m0['t45']:.4f}")
    m0a=metrics(base,keys,lam,ALL_FOLDS)
    print(f" HAND (all folds {ALL_FOLDS[0]}-{ALL_FOLDS[-1]}): pooled={m0a['pooled']:.4f} block={m0a['block']:.4f} auc={m0a['auc']:.4f}")
    out={}
    cand_sets={}
    for nm,tbl in CANDS.items(): cand_sets[nm]=prep(side,tbl)
    # zero-information control: same column, row-permuted (identical marginal)
    cand_sets["ZEROINFO_perm_agerel"]=prep(side,H.HAND,permute_seed=1234)
    for nm,dat in cand_sets.items():
        m1=metrics(dat,keys,lam,em.SCORED_YEARS); m1a=metrics(dat,keys,lam,ALL_FOLDS)
        d_pool=m1["pooled"]-m0["pooled"]; d_block=m1["block"]-m0["block"]
        d_auc=m1["auc"]-m0["auc"]; d_t45=m1["t45"]-m0["t45"]
        # per-fold deltas across ALL folds = independent time splits
        pf=[m1a["per_fold"][y]-m0a["per_fold"][y] for y in m0a["per_fold"] if y in m1a["per_fold"]]
        # paired bootstrap: resample the WHOLE pool, refit both arms per draw
        rnd=random.Random(seed); dp=[];db=[];da=[]
        t0=time.time()
        for _ in range(B):
            idx=[rnd.randrange(n) for _ in range(n)]
            a=metrics(base,keys,lam,em.SCORED_YEARS,idx); b=metrics(dat,keys,lam,em.SCORED_YEARS,idx)
            if a and b:
                dp.append(b["pooled"]-a["pooled"]); db.append(b["block"]-a["block"]); da.append(b["auc"]-a["auc"])
        def ci(v):
            v=sorted(v); return (round(v[int(.025*len(v))],4), round(v[int(.975*len(v))],4))
        print(f"\n -- {nm} --")
        print(f"    d_pooled  {d_pool:+.4f}  bootCI95 {ci(dp)}  P(>0)={sum(1 for x in dp if x>0)/len(dp):.3f}   [MDE95 {'0.017' if side=='hit' else '0.016'}]")
        print(f"    d_block   {d_block:+.4f}  bootCI95 {ci(db)}   [MDE95 0.0149]")
        print(f"    d_auc     {d_auc:+.4f}  bootCI95 {ci(da)}")
        print(f"    d_t45     {d_t45:+.4f}   [MDE95 {'0.055' if side=='hit' else '0.10'}]")
        print(f"    time splits (n={len(pf)} folds {ALL_FOLDS[0]}-{ALL_FOLDS[-1]}): mean {st.mean(pf):+.4f} "
              f"median {st.median(pf):+.4f} n_positive {sum(1 for x in pf if x>0)}/{len(pf)} "
              f"values {[round(x,4) for x in pf]}")
        print(f"    (bootstrap {B} draws in {time.time()-t0:.0f}s)")
        out[nm]={"d_pooled":d_pool,"ci":ci(dp),"d_block":d_block,"folds":pf}
    return out

if __name__=="__main__":
    B=int(sys.argv[1]) if len(sys.argv)>1 else 400
    for s in ("hit","pit"): run(s,B=B)
