"""Part 3: BOTH channels (target multiset + rank_war re-ranking). Read-only."""
import json,sys,os
from pathlib import Path
HERE=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(HERE)); D=HERE/"data"
L=lambda p: json.loads((D/p).read_text(encoding="utf-8"))
R=lambda o: o if isinstance(o,list) else (o.get("players") or o.get("rows"))
hit=R(L("xfv_scored_live.json")); pit=R(L("xfv_scored_live_pitcher.json"))
src={}
for r in R(L("xfv_live_hitter_matrix.json"))+R(L("xfv_live_pitcher_matrix.json")):
    src[r["player_key"]]=(r.get("fv_fangraphs"),r.get("fv_mlb_pipeline"))
GAP=3.616; H=GAP/2
DRW={"hit":0.15*0.406+0.85*0.3334, "pit":0.46*0.226+0.54*0.2096}
def shift(pk):
    e=src.get(pk)
    if not e: return 0.0
    f,m=e
    if f is not None and m is not None: return 0.0
    if f is not None: return +H
    if m is not None: return -H
    return 0.0
def dmap(rows,ck,rk):
    tgt=sorted(r[ck] for r in rows)
    order=sorted(range(len(rows)),key=lambda i:(rows[i][rk],rows[i]["player_key"]))
    m=len(rows); out={}
    for rp,i in enumerate(order):
        pos=(rp/(m-1))*(m-1) if m>1 else 0.0
        lo=int(pos); hi=min(m-1,lo+1); fr=pos-lo
        out[rows[i]["player_key"]]=round(tgt[lo]*(1-fr)+tgt[hi]*fr,1)
    return out
res={}
print(f"d(rank_war)/d(fv): hit {DRW['hit']:.4f} pit {DRW['pit']:.4f} WAR per FV point; shift = +/-{H:.3f} FV")
for side,rows in (("hit",hit),("pit",pit)):
    rr=[r for r in rows if r.get("rank_war") is not None and r.get("consensus_fv") is not None]
    for r in rr:
        s=shift(r["player_key"])
        r["_cons_new"]=round(r["consensus_fv"]+s,1)
        r["_rw_new"]=r["rank_war"]+DRW[side]*s
    base=dmap(rr,"consensus_fv","rank_war"); new=dmap(rr,"_cons_new","_rw_new")
    res[side]=(rr,base,new)
    dd=[abs(new[k]-base[k]) for k in base]
    # within-side rank churn
    ob=sorted(rr,key=lambda r:(-r["rank_war"],r["player_key"])); on=sorted(rr,key=lambda r:(-r["_rw_new"],r["player_key"]))
    pb={r["player_key"]:i for i,r in enumerate(ob)}; pn={r["player_key"]:i for i,r in enumerate(on)}
    mv=[abs(pn[k]-pb[k]) for k in pb]
    print(f"\n[{side}] n={len(rr)}  DISPLAY |d|: mean {sum(dd)/len(dd):.3f} max {max(dd):.2f} "
          f">=1FV {sum(1 for x in dd if x>=1)} ({100*sum(1 for x in dd if x>=1)/len(dd):.1f}%) "
          f">=3FV {sum(1 for x in dd if x>=3)}")
    print(f"      within-side RANK |move|: mean {sum(mv)/len(mv):.1f} slots max {max(mv)}; "
          f"top-50 retained {len(set(k for k,_ in list(pb.items()) if pb[k]<50) & set(k for k in pn if pn[k]<50))}/50")
def joint(which):
    a=[]
    for side in ("hit","pit"):
        rr,b,n=res[side]; m=b if which=="b" else n
        a+= [(m[r["player_key"]], r["player_key"]) for r in rr]
    a.sort(key=lambda t:(-t[0],t[1])); return [t[1] for t in a]
ob,on=joint("b"),joint("n")
for N in (10,25,50,100,300):
    print(f"[joint top-{N}] retained {len(set(ob[:N])&set(on[:N]))}/{N}")
pb={k:i for i,k in enumerate(ob)}; pn={k:i for i,k in enumerate(on)}
mv=[abs(pn[k]-pb[k]) for k in pb]; t50=[abs(pn[k]-pb[k]) for k in ob[:50]]
print(f"joint board |move|: mean {sum(mv)/len(mv):.1f} max {max(mv)}; top-50 incumbents mean {sum(t50)/len(t50):.1f} max {max(t50)}")
import value_framework as vf
from efv_score import _cal_mm
tb=tn=0.0; ds=[]
for side,ip in (("hit",False),("pit",True)):
    rr,b,n=res[side]
    for r in rr:
        try:
            sb=vf.expected_surplus_usd(b[r["player_key"]],ip,r.get("position"),eta_years=1.0)
            sn=vf.expected_surplus_usd(n[r["player_key"]],ip,r.get("position"),eta_years=1.0)
        except Exception: continue
        if sb is None or sn is None: continue
        sb=_cal_mm(sb/1e6,b[r["player_key"]],ip); sn=_cal_mm(sn/1e6,n[r["player_key"]],ip)
        if sb is None or sn is None: continue
        tb+=sb; tn+=sn; ds.append((abs(sn-sb),r["player_key"],sb,sn))
ds.sort(reverse=True); ad=[d[0] for d in ds]
print(f"\nSURPLUS: board ${tb:,.0f}M -> ${tn:,.0f}M ({100*(tn-tb)/tb:+.2f}%); per-player |d$| mean ${sum(ad)/len(ad):.2f}M max ${max(ad):.1f}M; >=$1M {sum(1 for x in ad if x>=1)}; >=$10M {sum(1 for x in ad if x>=10)}")
print("top movers: "+", ".join(f"{k} ${b:.0f}->${n:.0f}M" for _a,k,b,n in ds[:6]))
