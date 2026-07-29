"""Lane: prospect. (b) coherence: star odds vs the eFV outcome distribution, and
the farm rollup vs its members. Concrete named test players."""
import json, statistics, sys
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "data"
L = lambda n: json.loads((D / n).read_text(encoding="utf-8"))

xfv = L("xfv.json")["by_player"]
slv = L("star_label_view.json")
print("star_label_view type:", type(slv), list(slv.keys())[:8] if isinstance(slv, dict) else len(slv))
if isinstance(slv, dict):
    for k, v in slv.items():
        print("  ", k, type(v), len(v) if hasattr(v, "__len__") else v)
        if isinstance(v, dict):
            k0 = next(iter(v))
            print("     sample", k0, json.dumps(v[k0])[:400])
            break
        if isinstance(v, list) and v:
            print("     sample", json.dumps(v[0])[:400])
            break
