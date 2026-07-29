"""Lane: prospect. (a) re-derive farm_grades + prospect_surplus registered claims.
persist=False everywhere: NOTHING is written to data/."""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import farm_grade_backtest as fgb

t = time.time()
rep = fgb.run(persist=False)
print("farm_grade_backtest re-run in %.1fs" % (time.time() - t))
old = json.loads((ROOT / "data" / "farm_grade_eval.json").read_text(encoding="utf-8"))
print("REGISTERED mean_spearman:", old.get("mean_spearman"))
print("RE-DERIVED mean_spearman:", rep.get("mean_spearman"))
print("REGISTERED verdict:", old.get("verdict"))
print("RE-DERIVED verdict:", rep.get("verdict"))
print("\nper-vintage re-derived:")
for v, blk in rep.get("per_vintage", {}).items():
    o = (old.get("per_vintage") or {}).get(str(v)) or {}
    print(" ", v, "new", blk.get("spearman"), "| old", o.get("spearman"))
