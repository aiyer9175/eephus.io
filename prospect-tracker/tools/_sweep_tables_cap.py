"""Lane TABLES: the age_rel_level +/-3.5 cap, re-measured."""
import sys, pathlib, json, random, statistics as st
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import efv_model as em, _sweep_tables_harness as H
from efv_dataset import matrix_path, live_matrix_path
from prospect_path import _predict, _spearman
LV=["DSL","CPX","A","A+","AA","AAA"]

def apply_cap(rows, cap):
    out=[]
    for r in rows:
        m=r.get("milb"); r2=dict(r)
        if m:
            m2=dict(m); lv,ag=m2.get("milb_level"),m2.get("age")
            if lv in H.HAND and ag is not None:
                m2["age_rel_level"]=max(-cap,min(cap,float(ag)-H.HAND[lv]))
            r2["milb"]=m2
        out.append(r2)
    return out

def prep_cap(side,cap):
    rows=apply_cap(json.loads(matrix_path(side).read_text(encoding="utf-8")),cap)
    return em._prep([r for r in rows if bool(r.get("is_pitcher"))==(side=="pit")
                     and not (r.get("kind")=="bust" and r.get("bust_recent"))],
                    "target_censored",side)

from _sweep_tables_gate import metrics
CAPS=(3.5,4.5,6.0,8.0,99.0)
for side in ("hit","pit"):
    keys,_=em._feature_spec(side); lam=em.blend_lambda(side)
    m0=metrics(prep_cap(side,3.5),keys,lam,em.SCORED_YEARS)
    tr=[ (m.get("milb_level"),m.get("age")) for r in json.loads(matrix_path(side).read_text(encoding="utf-8"))
         for m in [r.get("milb") or {}] if m.get("milb_level") in H.HAND and m.get("age") is not None]
    li=[ (m.get("milb_level"),m.get("age")) for r in json.loads(live_matrix_path(side).read_text(encoding="utf-8"))
         for m in [r.get("milb") or {}] if m.get("milb_level") in H.HAND and m.get("age") is not None]
    print(f"\n===== side={side}  HAND-table pooled={m0['pooled']:.4f} block={m0['block']:.4f} =====")
    for cap in CAPS:
        m=metrics(prep_cap(side,cap),keys,lam,em.SCORED_YEARS)
        ct=sum(1 for l,a in tr if abs(a-H.HAND[l])>cap)/len(tr)
        cl=sum(1 for l,a in li if abs(a-H.HAND[l])>cap)/len(li)
        print(f"  cap +/-{cap:5.1f}: d_pooled {m['pooled']-m0['pooled']:+.4f}  d_block {m['block']-m0['block']:+.4f} "
              f" d_auc {m['auc']-m0['auc']:+.4f}  d_t45 {m['t45']-m0['t45']:+.4f} "
              f"| saturated TRAIN {ct*100:5.2f}%  LIVE {cl*100:5.2f}%")
