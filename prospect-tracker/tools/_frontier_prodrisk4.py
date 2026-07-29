"""Part 4: one-time TRANSITION churn of the shrink lane's lambda-for-churn proposal,
and the surplus lane's blend_weight_public=0 proposal. Read-only."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(HERE)); D=HERE/"data"
L=lambda p: json.loads((D/p).read_text(encoding="utf-8"))
R=lambda o: o if isinstance(o,list) else (o.get("players") or o.get("rows"))
OLS={"hit":(-15.957,0.406),"pit":(-8.5206,0.226)}
LIVE={"hit":0.85,"pit":0.54}
def dmap(rows,rk):
    tgt=sorted(r["consensus_fv"] for r in rows)
    order=sorted(range(len(rows)),key=lambda i:(rows[i][rk],rows[i]["player_key"]))
    m=len(rows); out={}
    for rp,i in enumerate(order):
        pos=(rp/(m-1))*(m-1) if m>1 else 0.0
        lo=int(pos);hi=min(m-1,lo+1);fr=pos-lo
        out[rows[i]["player_key"]]=round(tgt[lo]*(1-fr)+tgt[hi]*fr,1)
    return out
print("=== ONE-TIME TRANSITION CHURN of a lambda change (served display grade + board order) ===")
for side,fn in (("hit","xfv_scored_live.json"),("pit","xfv_scored_live_pitcher.json")):
    rr=[r for r in R(L(fn)) if r.get("rank_war") is not None and r.get("consensus_fv") is not None]
    a,b=OLS[side]; lam=LIVE[side]
    for r in rr:
        cons=max(0.0,a+b*r["consensus_fv"])
        r["_cons"]=cons; r["_model"]=(r["rank_war"]-(1-lam)*cons)/lam
    base=dmap(rr,"rank_war")
    ob=sorted(rr,key=lambda r:(-r["rank_war"],r["player_key"])); pb={r["player_key"]:i for i,r in enumerate(ob)}
    for newlam in ([0.70,0.50] if side=="hit" else [0.45,0.37]):
        for r in rr: r["_rw2"]=(1-newlam)*r["_cons"]+newlam*r["_model"]
        new=dmap(rr,"_rw2")
        dd=[abs(new[k]-base[k]) for k in base]
        on=sorted(rr,key=lambda r:(-r["_rw2"],r["player_key"])); pn={r["player_key"]:i for i,r in enumerate(on)}
        mv=[abs(pn[k]-pb[k]) for k in pb]
        t50=len(set(k for k in pb if pb[k]<50)&set(k for k in pn if pn[k]<50))
        print(f"  {side} lam {lam} -> {newlam}: display |d| mean {sum(dd)/len(dd):.3f} FV max {max(dd):.2f} "
              f">=1FV {100*sum(1 for x in dd if x>=1)/len(dd):.1f}% >=3FV {sum(1 for x in dd if x>=3)} | "
              f"rank |move| mean {sum(mv)/len(mv):.1f} max {max(mv)} | top-50 retained {t50}/50")
print("\n=== surplus lane: blend_weight_public 0.5 -> 0.0 (anchor recalibration) ===")
import value_framework as vf
emp={40:0.071,45:0.126,50:0.494,55:0.808,60:1.38}   # empirical WAR/yr from the lane
def inv(target6):
    lo,hi=20.0,80.0
    for _ in range(60):
        mid=(lo+hi)/2
        w=(vf.fv_to_6yr_avg_war(mid) or 0)*6
        if w<target6: lo=mid
        else: hi=mid
    return (lo+hi)/2
for fv,wy in emp.items():
    cur=(vf.fv_to_6yr_avg_war(fv) or 0)*6
    tgt=wy*6
    eq=inv(tgt)
    s_cur=vf.expected_surplus_usd(fv,False,"SS",eta_years=1.0)
    s_new=vf.expected_surplus_usd(eq,False,"SS",eta_years=1.0)
    print(f"  FV{fv}: shipped anchor 6yr WAR {cur:.2f} -> empirical {tgt:.2f} (equivalent grade {eq:.1f}); "
          f"hitter surplus ${s_cur/1e6:.1f}M -> ${s_new/1e6:.1f}M ({100*(s_new-s_cur)/max(s_cur,1):+.0f}%)")
