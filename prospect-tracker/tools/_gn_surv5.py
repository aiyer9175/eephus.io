# What the survivorship hole actually costs on the PUBLISHED surface:
# source_backtest cohort tier tables (debut_rate / mean_war / contributor_rate),
# shipped universe vs the same tables with the dropped never-debut pool restored.
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
    d = json.loads((DATA / name).read_text(encoding="utf-8"))
    return d["players"] if isinstance(d, dict) else d


TS, DEB, INA = load("timeseries.json"), load("debuts.json"), load("inactive.json")
YEARS = [2017, 2018, 2019, 2020, 2021, 2022, 2023]


def rows_by_rater(universe):
    raters = list(sb.SCORED_SOURCES) + [sb.CONSENSUS_KEY]
    out = {r: [] for r in raters}
    for p in universe:
        o = sb._outcome(p)
        for y in YEARS:
            g = sb._rater_grades_for_year(p, y)
            for r, fv in (g or {}).items():
                if r in out:
                    out[r].append({"fv": fv, "outcome": o})
    return out


def show(universe, label):
    print(f"\n===== {label} =====")
    rbr = rows_by_rater(universe)
    res = {}
    for r, rows in rbr.items():
        tiers = sb._tier_table(rows)
        nd = sum(1 for x in rows if x["outcome"]["debuted"])
        print(f"\n{r}  n={len(rows)}  debuted={nd} ({nd/len(rows):.3f})")
        for t in tiers:
            print(f"   {t['tier']:>4}  n={t['n']:<5} debut={t['debut_rate']:.3f} "
                  f"meanWAR={t['mean_war']:<6} contrib={t['contributor_rate']:.3f} "
                  f"star={t['star_rate']:.3f}")
        res[r] = {"n": len(rows), "n_debuted": nd, "tiers": tiers}
    return res


if __name__ == "__main__":
    a = show(TS + DEB, "SHIPPED universe (what data/source_backtest.json publishes)")
    b = show(TS + DEB + INA, "REPAIRED universe (+ inactive.json never-debut pool)")
    json.dump({"shipped": a, "repaired": b},
              (OUT / "surv_tiers.json").open("w", encoding="utf-8"), indent=1)
