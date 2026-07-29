"""Lane: prospect. (4) NO-REDUNDANCY audit across the served prospect-lane signals.

Spearman matrix over the ACTIVE board population for every number the stack ships
as a distinct concept. Anything |rho| >= 0.95 is the same signal under two names.
"""
import json, sys, statistics
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "data"
L = lambda n: json.loads((D / n).read_text(encoding="utf-8"))
from source_backtest import _spearman
import value_framework as vf

xfv = L("xfv.json")["by_player"]
tv = {r["player_key"]: r for r in L("trade_values.json")["players"]}
ap = L("advancement_pace.json")
dv = L("prospect_def_value.json")

def get_map(obj, want):
    if isinstance(obj, dict):
        for k in ("players", "by_player", "rows"):
            if k in obj:
                return obj[k]
    return obj
apm = get_map(ap, None)
dvm = get_map(dv, None)
print("advancement_pace container:", type(apm), len(apm) if hasattr(apm, "__len__") else "")
if isinstance(apm, list) and apm:
    print("  ap sample keys:", sorted(apm[0].keys())[:20])
elif isinstance(apm, dict):
    k0 = next(iter(apm)); print("  ap sample:", k0, json.dumps(apm[k0])[:300])
print("prospect_def_value container:", type(dvm), len(dvm) if hasattr(dvm, "__len__") else "")
if isinstance(dvm, list) and dvm:
    print("  dv sample keys:", sorted(dvm[0].keys())[:20])
elif isinstance(dvm, dict):
    k0 = next(iter(dvm)); print("  dv sample:", k0, json.dumps(dvm[k0])[:300])

# --- build the signal table over ACTIVE prospects ---------------------------
SIG = {}
keys = [k for k, x in xfv.items() if x.get("kind") == "active"]
def add(name, fn):
    SIG[name] = {k: fn(k) for k in keys}
add("efv_grade_quantile", lambda k: xfv[k].get("xfv_grade_quantile"))
add("efv_grade_raw", lambda k: xfv[k].get("xfv_grade_model_raw"))
add("efv_war_6yr", lambda k: xfv[k].get("xfv_war_6yr"))
add("consensus_fv", lambda k: xfv[k].get("consensus_fv"))
add("surplus_mm", lambda k: xfv[k].get("surplus_mm"))
add("band_p90_mm", lambda k: xfv[k].get("band_p90_mm"))
add("p_bust", lambda k: xfv[k].get("p_bust"))
add("p_star", lambda k: (xfv[k].get("p_bucket") or {}).get("star"))
add("trade_value_mm", lambda k: (tv.get(k) or {}).get("trade_value_mm"))
add("sortino", lambda k: (tv.get(k) or {}).get("sortino"))
add("risk_mm", lambda k: (tv.get(k) or {}).get("risk_mm"))
add("downside_mm", lambda k: (tv.get(k) or {}).get("downside_mm"))
add("crunch_score", lambda k: ((tv.get(k) or {}).get("crunch") or {}).get("score"))
add("published_star_odds", lambda k: (
    vf.published_star_odds(float(xfv[k]["xfv_grade_quantile"]), xfv[k].get("side") == "P")
    if xfv[k].get("xfv_grade_quantile") is not None else None))
add("dist_mean_mm", lambda k: (xfv[k].get("dist") or {}).get("mean_mm"))
add("dist_p50_mm", lambda k: (xfv[k].get("dist") or {}).get("p50_mm"))

names = list(SIG)
print("\nSpearman matrix over active prospects (pairwise complete):")
print("     " + " ".join(f"{n[:11]:>12s}" for n in names))
hi = []
for a in names:
    line = f"{a[:16]:16s}"
    for b in names:
        pair = [(SIG[a][k], SIG[b][k]) for k in keys
                if SIG[a][k] is not None and SIG[b][k] is not None]
        if len(pair) < 50:
            line += f"{'':>12s}"; continue
        r = _spearman([x for x, _ in pair], [y for _, y in pair])
        line += f"{r:12.3f}"
        if a < b and r is not None and abs(r) >= 0.95:
            hi.append((a, b, r, len(pair)))
    print(line)

print("\nNEAR-DUPLICATE PAIRS (|rho| >= 0.95):")
for a, b, r, n in sorted(hi, key=lambda t: -abs(t[2])):
    print(f"   {a:22s} <-> {b:22s} rho={r:+.4f}  n={n}")
if not hi:
    print("   none")
