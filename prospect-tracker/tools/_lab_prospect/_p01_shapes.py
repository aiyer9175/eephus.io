"""Lane: prospect. Shape probe of the served payloads."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data"

def load(n):
    return json.loads((D / n).read_text(encoding="utf-8"))

x = load("xfv.json")
print("xfv meta:", json.dumps(x["meta"], indent=1)[:1500])
bp = x["by_player"]
print("xfv by_player n =", len(bp))
k0 = next(iter(bp))
print("sample key", k0, json.dumps(bp[k0], indent=1)[:2000])

tv = load("trade_values.json")
print("\ntrade_values keys:", list(tv.keys())[:12] if isinstance(tv, dict) else len(tv))
if isinstance(tv, dict):
    for k, v in tv.items():
        print("  ", k, type(v), (len(v) if hasattr(v, "__len__") else ""))

mp = load("mlb_projections.json")
print("\nmlb_projections keys:", list(mp.keys()))
