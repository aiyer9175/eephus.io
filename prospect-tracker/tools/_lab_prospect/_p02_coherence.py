"""Lane: prospect. (b) COHERENCE across the prospect stack.

Cross-joins the SERVED payloads for the same player and reports every place
two surfaces disagree about the same quantity:

  eFV grade      xfv.json by_player[k].xfv_grade_quantile
  eFV surplus    xfv.json by_player[k].surplus_mm
  trade value    trade_values.json players[].value / surplus
  proj surplus   mlb_projections.json prospects[].surNpv (vf.surplus_value_mm)
  star odds      data/star_label_view.json
  farm mass      per-org rollup
"""
import json, math, statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data"
L = lambda n: json.loads((D / n).read_text(encoding="utf-8"))

xfv = L("xfv.json")["by_player"]
tv = L("trade_values.json")
mp = L("mlb_projections.json")

tvp = tv["players"]
print("trade_values sample:", json.dumps(tvp[0], indent=1)[:1400])
print()
pr = mp["prospects"]
print("proj prospect sample:", json.dumps(pr[0], indent=1)[:1400])
print()
print("proj prospects n =", len(pr), " vets n =", len(mp["vets"]))
print("tv keys union:", sorted({k for r in tvp[:500] for k in r}))
print("proj prospect keys union:", sorted({k for r in pr[:500] for k in r}))
