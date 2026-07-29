# (a) Is the restored pool genuinely RESOLVED failure, or not-yet-resolved prospects
#     misread as 0-WAR? (the bust_recent question eFV already answers for itself)
# (b) What would the shipped weight estimator / ship gate do on the repaired universe?
from __future__ import annotations

import collections
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))
import source_backtest as sb   # noqa: E402


def load(name):
    d = json.loads((DATA / name).read_text(encoding="utf-8"))
    return d["players"] if isinstance(d, dict) else d


TS, DEB, INA = load("timeseries.json"), load("debuts.json"), load("inactive.json")
YEARS = (2017, 2018, 2019, 2020, 2021, 2022, 2023)

graded = []
for p in INA:
    yrs = [y for y in YEARS
           if (g := sb._rater_grades_for_year(p, y)) and all(s in g for s in sb.SCORED_SOURCES)]
    if yrs:
        pts = [q["snapshot_date"] for q in (p.get("points") or []) if q.get("snapshot_date")]
        graded.append({"key": p["player_key"], "years": yrs,
                       "last_list": max(pts)[:4] if pts else None,
                       "age": p.get("age")})

print("restored (inactive + graded on a scored preseason common set):", len(graded))
print("last list-appearance year:",
      dict(sorted(collections.Counter(g["last_list"] for g in graded).items())))
ages = [g["age"] for g in graded if g["age"] is not None]
ages.sort()
print(f"age now: n={len(ages)} p10={ages[int(.1*len(ages))]:.1f} "
      f"median={ages[len(ages)//2]:.1f} p90={ages[int(.9*len(ages))]:.1f}")
print("share last-listed 2024+ (the eFV 'bust_recent' class):",
      round(sum(1 for g in graded if (g["last_list"] or "0") >= "2024") / len(graded), 3))
print("share age >= 26 now:", round(sum(1 for a in ages if a >= 26) / len(ages), 3))

print("\n=== (b) shipped weight estimator on each universe (live vintage: base <= %d) ==="
      % (date.today().year - sb.MIN_LAG_YEARS))
for lab, uni in (("SHIPPED", TS + DEB), ("REPAIRED", TS + DEB + INA)):
    w = sb.derive_source_weights(uni, date.today().year - sb.MIN_LAG_YEARS)
    print(f"  {lab:>9}: {w}")

print("\n=== (b2) the equal-vs-weighted A/B, both universes ===")


def ab(universe):
    resolved = sb._resolved_years(universe, date.today().year)
    rows_by_year = {}
    for p in universe:
        o = sb._outcome(p)
        for y in resolved:
            g = sb._rater_grades_for_year(p, y)
            if g and all(s in g for s in sb.SCORED_SOURCES):
                rows_by_year.setdefault(y, []).append({"grades": g, "outcome": o})
    pooled = {"eq": [], "wt": [], "war": [], "con": []}
    for Y in sorted(rows_by_year):
        w = sb.derive_source_weights(universe, Y - sb.MIN_LAG_YEARS)
        if all(abs(v - 1.0) < 1e-9 for v in w.values()):
            continue
        ws = sum(w[s] for s in sb.SCORED_SOURCES)
        for r in rows_by_year[Y]:
            g = r["grades"]
            pooled["eq"].append(sum(g[s] for s in sb.SCORED_SOURCES) / 2.0)
            pooled["wt"].append(sum(w[s] * g[s] for s in sb.SCORED_SOURCES) / ws)
            pooled["war"].append(r["outcome"]["war"])
            pooled["con"].append(r["outcome"]["contributor"])
    if not pooled["war"]:
        return None
    return {
        "n": len(pooled["war"]),
        "d_rho": (sb._spearman(pooled["wt"], pooled["war"])
                  - sb._spearman(pooled["eq"], pooled["war"])),
        "d_auc": (sb._auc(pooled["wt"], pooled["con"])
                  - sb._auc(pooled["eq"], pooled["con"])),
    }


for lab, uni in (("SHIPPED", TS + DEB), ("REPAIRED", TS + DEB + INA)):
    r = ab(uni)
    if r is None:
        print(f"  {lab:>9}: no differentiable years")
        continue
    print(f"  {lab:>9}: n={r['n']} d_rho={r['d_rho']:+.5f} (gate needs >= +0.0068)  "
          f"d_auc={r['d_auc']:+.5f} (gate needs >= +0.0052)  "
          f"-> ship={r['d_rho'] >= 0.0068 and r['d_auc'] >= 0.0052}")
