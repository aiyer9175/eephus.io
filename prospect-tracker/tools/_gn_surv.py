# Survivorship lane (2026-07-25). ANALYSIS ONLY -- writes nothing outside tools/_gn_out/.
# Adjudicates C2 (does the source-accuracy universe drop non-debuts?) and scopes the hole
# (does it reach the eFV TRAINING labels?).
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
OUT = HERE / "_gn_out"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))

import source_backtest as sb   # noqa: E402


def load(name):
    p = DATA / name
    d = json.loads(p.read_text(encoding="utf-8"))
    return d["players"] if isinstance(d, dict) else d


TS = load("timeseries.json")
DEB = load("debuts.json")
INA = load("inactive.json")

SHIPPED = TS + DEB                 # exactly source_backtest._load_universe
REPAIRED = TS + DEB + INA


def cohort_rows(universe, years, require=("fangraphs", "mlb_pipeline")):
    """(year, player) rows on the preseason common set, using source_backtest's own
    window + grade extraction so this is the SAME surface, not a re-implementation."""
    rows = []
    for p in universe:
        out = sb._outcome(p)
        for y in years:
            g = sb._rater_grades_for_year(p, y)
            if not g or not all(r in g for r in require):
                continue
            rows.append({"key": p.get("player_key"), "year": y, "grades": g,
                         "outcome": out})
    return rows


YEARS = (2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024)


def table(rows, label):
    print(f"\n--- {label} ---")
    print(f"{'base':>5} {'n':>6} {'debuted':>8} {'debut_rate':>11}")
    by = {}
    for r in rows:
        by.setdefault(r["year"], []).append(r)
    for y in sorted(by):
        rr = by[y]
        d = sum(1 for r in rr if r["outcome"]["debuted"])
        print(f"{y:>5} {len(rr):>6} {d:>8} {d/len(rr):>11.3f}")
    return by


if __name__ == "__main__":
    print("universe sizes: shipped(ts+deb)=%d repaired(+inactive)=%d" % (len(SHIPPED), len(REPAIRED)))
    a = cohort_rows(SHIPPED, YEARS)
    b = cohort_rows(REPAIRED, YEARS)
    ta = table(a, "SHIPPED universe (source_backtest._load_universe)")
    tb = table(b, "REPAIRED universe (+ inactive.json)")
    print("\n--- delta ---")
    print(f"{'base':>5} {'n_ship':>7} {'n_rep':>7} {'added':>6} {'rate_ship':>10} {'rate_rep':>9}")
    for y in sorted(set(ta) | set(tb)):
        ra, rb = ta.get(y, []), tb.get(y, [])
        da = sum(1 for r in ra if r["outcome"]["debuted"])
        db_ = sum(1 for r in rb if r["outcome"]["debuted"])
        print(f"{y:>5} {len(ra):>7} {len(rb):>7} {len(rb)-len(ra):>6} "
              f"{(da/len(ra) if ra else float('nan')):>10.3f} "
              f"{(db_/len(rb) if rb else float('nan')):>9.3f}")
    json.dump({"shipped": {str(y): [len(v), sum(1 for r in v if r['outcome']['debuted'])]
                           for y, v in ta.items()},
               "repaired": {str(y): [len(v), sum(1 for r in v if r['outcome']['debuted'])]
                            for y, v in tb.items()}},
              (OUT / "surv_cohort.json").open("w", encoding="utf-8"), indent=1)
