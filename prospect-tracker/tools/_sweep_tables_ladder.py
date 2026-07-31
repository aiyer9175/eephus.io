"""Lane TABLES: _LEVEL_RANK equal-spacing re-derivation (positional-ladder precedent)
+ _TOOL_IMPUTE sizing + _GRADE_MAP re-anchor + milb-less row counts."""
import sys, pathlib, json, random, statistics as st
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np
import efv_model as em, efv_ungraded as eu, _sweep_tables_harness as H
from efv_dataset import matrix_path, live_matrix_path
from _sweep_tables_gate import metrics
from prospect_path import _fit_ridge, _predict
LV=["DSL","CPX","A","A+","AA","AAA"]; RK={l:i for i,l in enumerate(LV)}

def rows(side,live=False):
    return json.loads((live_matrix_path(side) if live else matrix_path(side)).read_text(encoding="utf-8"))

print("="*78); print("A. _LEVEL_RANK: empirical outcome ladder, rescaled to the shipped 0..5 span")
LAD={}
for side in ("hit","pit"):
    tr=[r for r in rows(side) if r.get("milb") and r.get("target_censored") is not None
        and not (r.get("kind")=="bust" and r.get("bust_recent"))]
    means={}
    for lv in LV:
        sub=[r for r in tr if r["milb"].get("milb_level")==lv]
        if len(sub)<25: continue
        w=np.array([float(r.get("weight",1.0)) for r in sub]); y=np.array([float(r["target_censored"]) for r in sub])
        # bootstrap CI on the weighted mean
        rnd=np.random.default_rng(5); bs=[]
        for _ in range(3000):
            i=rnd.integers(0,len(sub),len(sub)); bs.append(float(np.average(y[i],weights=w[i])))
        bs.sort(); means[lv]=(float(np.average(y,weights=w)), bs[75], bs[2924], len(sub))
    ks=[l for l in LV if l in means]
    v=np.array([means[l][0] for l in ks])
    lad=(v-v.min())/(v.max()-v.min())*(RK[ks[-1]]-RK[ks[0]])+RK[ks[0]]
    LAD[side]={l:round(float(x),3) for l,x in zip(ks,lad)}
    x=np.array([RK[l] for l in ks],float)
    A=np.vstack([np.ones_like(x),x]).T; c,*_=np.linalg.lstsq(A,v,rcond=None)
    r2=1-(((v-A@c)**2).sum()/((v-v.mean())**2).sum())
    print(f"  {side}: weighted mean 6yr WAR by level  " +
          "  ".join(f"{l}={means[l][0]:.2f}[{means[l][1]:.2f},{means[l][2]:.2f}]n{means[l][3]}" for l in ks))
    print(f"       linear-in-rank fit R2={r2:.4f}; residuals " +
          str({l: round(float(v[i]-(A@c)[i]),3) for i,l in enumerate(ks)}))
    print(f"       EMPIRICAL ladder rescaled onto the shipped span: {LAD[side]}")

print("\n  gate: swap level_rank for the empirical ladder (hitters only -- pitchers have no level_rank feature)")
def apply_ladder(rs, lad):
    out=[]
    for r in rs:
        m=r.get("milb"); r2=dict(r)
        if m and m.get("milb_level") in lad:
            m2=dict(m); m2["level_rank"]=lad[m2["milb_level"]]; r2["milb"]=m2
        out.append(r2)
    return out
side="hit"; keys,_=em._feature_spec(side); lam=em.blend_lambda(side)
def prep_l(lad=None, perm=None):
    rs=rows(side)
    if lad: rs=apply_ladder(rs,lad)
    if perm is not None:
        rnd=random.Random(perm); idx=[i for i,r in enumerate(rs) if r.get("milb")]
        pool=[rs[i]["milb"]["level_rank"] for i in idx]; rnd.shuffle(pool)
        rs=[dict(r) for r in rs]
        for i,v in zip(idx,pool):
            rs[i]["milb"]=dict(rs[i]["milb"]); rs[i]["milb"]["level_rank"]=v
    return em._prep([r for r in rs if not r.get("is_pitcher")
                     and not (r.get("kind")=="bust" and r.get("bust_recent"))],"target_censored",side)
m0=metrics(prep_l(),keys,lam,em.SCORED_YEARS)
m1=metrics(prep_l(LAD["hit"]),keys,lam,em.SCORED_YEARS)
print(f"   HAND  pooled {m0['pooled']:.4f} block {m0['block']:.4f} auc {m0['auc']:.4f} t45 {m0['t45']:.4f}")
print(f"   EMPIR d_pooled {m1['pooled']-m0['pooled']:+.4f}  d_block {m1['block']-m0['block']:+.4f} "
      f"d_auc {m1['auc']-m0['auc']:+.4f}  d_t45 {m1['t45']-m0['t45']:+.4f}")
dp=[]
for s in range(60):
    m=metrics(prep_l(perm=7000+s),keys,lam,em.SCORED_YEARS); dp.append(m["pooled"]-m0["pooled"])
dp.sort(); print(f"   zero-info permutation of level_rank (n=60): d_pooled 95% band "
                 f"({dp[1]:+.4f},{dp[-2]:+.4f}) mean {st.mean(dp):+.4f}")
# paired bootstrap
base=prep_l(); cand=prep_l(LAD["hit"]); n=len(base); rnd=random.Random(7); bb=[]
for _ in range(400):
    idx=[rnd.randrange(n) for _ in range(n)]
    a=metrics(base,keys,lam,em.SCORED_YEARS,idx); b=metrics(cand,keys,lam,em.SCORED_YEARS,idx)
    if a and b: bb.append(b["pooled"]-a["pooled"])
bb.sort(); print(f"   paired bootstrap (B=400, train+test resampled, refit): d_pooled CI95 "
                 f"({bb[int(.025*len(bb))]:+.4f},{bb[int(.975*len(bb))]:+.4f}) P(>0)={sum(1 for x in bb if x>0)/len(bb):.3f}")
# time splits
m0a=metrics(prep_l(),keys,lam,tuple(range(2017,2025))); m1a=metrics(prep_l(LAD["hit"]),keys,lam,tuple(range(2017,2025)))
pf=[m1a["per_fold"][y]-m0a["per_fold"][y] for y in m0a["per_fold"]]
print(f"   time splits n={len(pf)}: mean {st.mean(pf):+.4f} n_pos {sum(1 for x in pf if x>0)}/{len(pf)} {[round(x,4) for x in pf]}")

print("="*78); print("B. _TOOL_IMPUTE sizing (SD units of the TRAINING column, share of LIVE rows imputed)")
for side,tools in (("hit",("tool_hit","tool_speed")),("pit",("tool_fb",))):
    tr=rows(side); li=rows(side,True)
    for t in tools:
        v=[float(r[t]) for r in tr if r.get(t) is not None]
        sd=st.pstdev(v); mu=st.mean(v); cur=em._TOOL_IMPUTE[t]
        share=sum(1 for r in li if r.get(t) is None and r.get("milb"))/sum(1 for r in li if r.get("milb"))
        print(f"  {t:12s} shipped {cur:5.1f}  train mean {mu:6.2f} sd {sd:5.2f} -> spurious tilt "
              f"{(cur-mu)/sd:+.3f} SD applied to {share*100:5.1f}% of live scored rows")

print("="*78); print("C. _GRADE_MAP BASE/SLOPE re-anchored to the PROVISIONAL model's own predicted WAR")
for side in ("hit","pit"):
    ridge,a,b=eu.fit_nofv(side)
    tr=[r for r in rows(side) if r.get("milb") and r.get("target_censored") is not None
        and not (r.get("kind")=="bust" and r.get("bust_recent")) and r.get("consensus_fv_raw") is not None]
    pw=np.array([eu._war(ridge,a,b,em._vec(r,side)) for r in tr])
    fv=np.array([float(r["consensus_fv_raw"]) for r in tr]); w=np.array([float(r.get("weight",1.0)) for r in tr])
    A=np.vstack([np.ones_like(pw),pw]).T; W=np.diag(w); c=np.linalg.solve(A.T@W@A,A.T@W@fv)
    gm=eu._GRADE_MAP[side]
    print(f"  {side}: shipped BASE {gm['BASE']} SLOPE {gm['SLOPE']}  |  measured FV ~ a+b*pred_war : "
          f"a={c[0]:.2f} b={c[1]:.3f} (n={len(tr)}); pred_war range [{pw.min():.2f},{pw.max():.2f}] "
          f"p50 {np.quantile(pw,.5):.2f} p95 {np.quantile(pw,.95):.2f}")
    print(f"       shipped map at pred p50/p95/max: {eu._grade(float(np.quantile(pw,.5)),side)} / "
          f"{eu._grade(float(np.quantile(pw,.95)),side)} / {eu._grade(float(pw.max()),side)}"
          f"   | measured map: {c[0]+c[1]*np.quantile(pw,.5):.1f} / {c[0]+c[1]*np.quantile(pw,.95):.1f} / {c[0]+c[1]*pw.max():.1f}")

print("="*78); print("D. rows with NO milb block (where the 22.5 age impute + milb_missing actually fire)")
for side in ("hit","pit"):
    tr=rows(side); li=rows(side,True)
    print(f"  {side}: TRAIN no-milb {sum(1 for r in tr if not r.get('milb'))}/{len(tr)} "
          f"(of which milb_unavailable {sum(1 for r in tr if not r.get('milb') and r.get('milb_unavailable'))}) | "
          f"LIVE no-milb {sum(1 for r in li if not r.get('milb'))}/{len(li)} (all ABSTAINED by run_live)")
