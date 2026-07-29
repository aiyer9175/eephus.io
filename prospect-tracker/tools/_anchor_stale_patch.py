import json,sys
from pathlib import Path
from datetime import date
HERE=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(HERE))
from efv_dataset import _stale_anchor_discount
TD=date.fromisoformat(sys.argv[1])
n=0
for f in ["xfv_live_hitter_matrix.json","xfv_live_pitcher_matrix.json"]:
    p=HERE/"data"/f
    rows=json.loads(p.read_text(encoding="utf-8"))
    for r in rows:
        d=_stale_anchor_discount(r.get("asof_date"), r.get("consensus_fv_raw"), today=TD)
        if d>0:
            r["anchor_stale_discount"]=round(d,2)
            r["fv_effective"]=round(float(r["consensus_fv_raw"])-d,2)
            n+=1
    p.write_text(json.dumps(rows),encoding="utf-8")
print("decayed rows",n)
