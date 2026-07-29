"""Lane TABLES: train/serve covariate shift + cap-clipping under candidate tables."""
import sys, pathlib, json, statistics as st
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from efv_dataset import matrix_path, live_matrix_path
LV=["DSL","CPX","A","A+","AA","AAA"]
HAND={"DSL":18.0,"CPX":19.0,"A":20.0,"A+":21.0,"AA":22.5,"AAA":24.0}
D=json.load(open(pathlib.Path(__file__).parent/"_sweep_tables_derived.json"))
CANDS={"HAND":HAND,"EMP_TRAIN":D["train"],"EMP_LIVE":D["live"]}

def rows(p):
    o=[]
    for r in json.loads(p.read_text(encoding="utf-8")):
        m=r.get("milb") or {}
        if m.get("milb_level") in LV and m.get("age") is not None and not m.get("age_missing"):
            o.append((m["milb_level"],float(m["age"]),r.get("player_key")))
    return o

for side in ("hit","pit"):
    tr=rows(matrix_path(side)); li=rows(live_matrix_path(side))
    print(f"\n===== side={side}  train n={len(tr)}  live n={len(li)} =====")
    for nm,tbl in CANDS.items():
        def vals(rs):
            return [max(-3.5,min(3.5,a-tbl[l])) for l,a,_ in rs if l in tbl]
        vt,vl=vals(tr),vals(li)
        mt,sdt=st.mean(vt),st.pstdev(vt)
        z_live=(st.mean(vl)-mt)/(sdt or 1)
        clip_t=sum(1 for v in vt if abs(v)>=3.4999)/len(vt)
        clip_l=sum(1 for v in vl if abs(v)>=3.4999)/len(vl)
        clip_hi=sum(1 for v in vl if v>=3.4999)/len(vl)
        print(f" {nm:10s} train mean {mt:+6.3f} sd {sdt:5.3f} | live mean {st.mean(vl):+6.3f} sd {st.pstdev(vl):5.3f}"
              f" | LIVE MEAN SHIFT in train-z units {z_live:+6.3f}"
              f" | clipped train {clip_t*100:5.2f}%  live {clip_l*100:5.2f}% (upper {clip_hi*100:5.2f}%)")
