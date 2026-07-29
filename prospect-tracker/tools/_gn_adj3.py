# ADJUDICATION LAB 3 -- cheap independent checks on C1 (already-propagated?) and C2/C3
# (disjointness + eFV bust provenance, the decisive null of the survivorship lane).
import json, os, sys
from pathlib import Path
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE)); os.chdir(_HERE)
D = _HERE / "data"


def load(n):
    return json.loads((D / n).read_text(encoding="utf-8"))


ts = load("timeseries.json"); deb = load("debuts.json"); ina = load("inactive.json")


def keys(o):
    if isinstance(o, dict):
        for k in ("players", "rows", "data"):
            if k in o and isinstance(o[k], (list, dict)):
                o = o[k]; break
    if isinstance(o, dict):
        return set(o)
    return {r.get("player_key") for r in o if isinstance(r, dict)}


kt, kd, ki = keys(ts), keys(deb), keys(ina)
print(f"C2 universes: ts {len(kt)}  debuts {len(kd)}  inactive {len(ki)}")
print(f"  ts&ina {len(kt&ki)}  deb&ina {len(kd&ki)}  ts&deb {len(kt&kd)}  "
      f"union {len(kt|kd|ki)}  (shipped universe ts+deb = {len(kt|kd)})")

# ---- C1: is the repair already in the served export? jesus_made check ----
def getrow(o, pk):
    if isinstance(o, dict):
        for k in ("players", "rows", "data"):
            if k in o and isinstance(o[k], (list, dict)):
                o = o[k]; break
    if isinstance(o, dict):
        return o.get(pk)
    return next((r for r in o if r.get("player_key") == pk), None)


print("\nC1 served-export spot check (claim: repair ALREADY propagated):")
for pk in ("jesus_made", "leo_de_vries", "roch_cholowsky"):
    r = getrow(ts, pk)
    if not r:
        print(f"  {pk}: NOT FOUND"); continue
    pts = r.get("points") or r.get("series") or []
    last = pts[-1] if pts else {}
    print(f"  {pk}: consensus_fv_raw={last.get('consensus_fv_raw')} "
          f"consensus_fv={last.get('consensus_fv')} date={last.get('date')}")
if isinstance(ts, dict):
    print(f"  timeseries generated_at: {ts.get('generated_at')}")

# ---- C2/C3 decisive null: eFV bust rows come from inactive.json ----
print("\nC2 eFV scoping (claim: bust rows all from inactive.json, so eFV is clean):")
tot = {"bust": 0, "debuted": 0}
prov = {"inactive": 0, "debuts": 0, "timeseries": 0, "none": 0}
for fn in ("xfv_hitter_matrix.json", "xfv_pitcher_matrix.json"):
    for r in load(fn):
        k = r.get("kind") or ("debuted" if r.get("debut_year") else "?")
        tot[k] = tot.get(k, 0) + 1
        if k == "bust":
            pk = r["player_key"]
            prov["inactive" if pk in ki else "debuts" if pk in kd
                 else "timeseries" if pk in kt else "none"] += 1
print(f"  matrix rows by kind: {tot}")
print(f"  bust-row provenance: {prov}")
