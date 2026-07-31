# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Is Enrique Bradfield Jr graded too high? Answer it with OUTCOMES, not intuition.

The structure lane already tested every mechanism the complaint points at and every
one is a measured null: level_rank x age (fitted weight is the OPPOSITE sign, and the
out-of-fold residual says the shipped model if anything OVER-penalises age at Triple-A),
a non-linear age hinge, age x production, tool x production, and re-deriving
_TYPICAL_LEVEL_AGE. Dropping tool_speed HURTS (-0.0068 rho, 5/5 folds).

So the model's structure is not obviously wrong. The remaining question is empirical and
much more direct: what actually HAPPENED to historical prospects who look like Bradfield
does now? A speed-first hitter, old for the level, at Triple-A, hitting below the level
median. If their realized first-6yr WAR implies an FV well under his served grade, the
complaint is right and the fix belongs in calibration. If it does not, the grade is
defensible and the honest answer is that it is calibration, not ranking, that is broken.

Read-only.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"


def _load():
    return json.loads((DATA / "xfv_hitter_matrix.json").read_text(encoding="utf-8"))


def _target(r):
    """Realized first-6yr summed bWAR. Prefer the RESOLVED value; a censored row
    has not finished its 6-year window and would understate the outcome."""
    t = r.get("target_resolved")
    return float(t) if isinstance(t, (int, float)) else None


def main() -> int:
    rows = _load()
    xfv = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    b = xfv["enrique_bradfield_jr"]
    print("BRADFIELD, served:")
    print(f"  xfv_grade {b['xfv_grade']:.2f}  consensus {b['consensus_fv']}  "
          f"eFV-minus-consensus +{b['xfv_minus_consensus']}")
    print(f"  tools {b['tool_xfv']}   p_bust {b['p_bust']}   xfv_war_6yr {b['xfv_war_6yr']}")

    # his own feature line, from the live matrix if present
    me = next((r for r in rows if r.get("player_key") == "enrique_bradfield_jr"), None)
    if me and isinstance(me.get("milb"), dict):
        mb = me["milb"]
        print(f"  milb: level {mb.get('milb_level')} season {mb.get('milb_season')} "
              f"age {mb.get('age')} age_rel_level {mb.get('age_rel_level')} "
              f"ops_rel {mb.get('ops_rel')} k_rel {mb.get('k_rel')} "
              f"n_seasons {mb.get('n_milb_seasons')}")

    # ---- comparable cohort: resolved outcomes only ----
    pool = []
    for r in rows:
        y = _target(r)
        mb = r.get("milb")
        if y is None or not isinstance(mb, dict):
            continue
        lvl = mb.get("milb_level")
        age = mb.get("age")
        ops = mb.get("ops_rel")
        spd = r.get("tool_speed")
        if None in (age, ops) or lvl is None:
            continue
        pool.append({"key": r.get("player_key"), "y": y, "lvl": lvl, "age": float(age),
                     "ops": float(ops), "spd": float(spd) if spd is not None else None,
                     "fv": r.get("consensus_fv_raw")})
    print(f"\nresolved-outcome pool: {len(pool)} hitters")

    def block(name, sel):
        ys = sorted(x["y"] for x in sel)
        if len(ys) < 8:
            print(f"\n{name}: n={len(ys)} TOO THIN to read")
            return
        import value_framework as vf
        mean = st.mean(ys)
        med = st.median(ys)
        bust = sum(1 for v in ys if v < 0.5) / len(ys)
        # invert the config's own declared level meaning: grade -> 6yr WAR
        implied = None
        try:
            lo, hi = 20.0, 70.0
            for _ in range(60):
                mid = (lo + hi) / 2
                if 6 * vf.fv_to_6yr_avg_war(mid) < mean:
                    lo = mid
                else:
                    hi = mid
            implied = (lo + hi) / 2
        except Exception:
            pass
        print(f"\n{name}: n={len(ys)}")
        print(f"  realized first-6yr WAR: mean {mean:5.2f}  median {med:5.2f}  "
              f"p10 {ys[len(ys)//10]:5.2f}  p90 {ys[-max(1,len(ys)//10)]:5.2f}")
        print(f"  bust rate (<0.5 WAR): {bust:.1%}")
        if implied is not None:
            print(f"  FV implied by the mean, via the config's own fv_to_6yr_avg_war: "
                  f"{implied:.1f}")

    AAA = {"AAA"}
    block("ALL resolved hitters", pool)
    block("Triple-A, any age", [x for x in pool if x["lvl"] in AAA])
    block("Triple-A, age >= 23.5", [x for x in pool if x["lvl"] in AAA and x["age"] >= 23.5])
    block("Triple-A, age >= 23.5, ops_rel < 0 (below level median)",
          [x for x in pool if x["lvl"] in AAA and x["age"] >= 23.5 and x["ops"] < 0])
    block("THE BRADFIELD COMP: AAA, age >= 23.5, ops_rel < -0.05, speed >= 65",
          [x for x in pool if x["lvl"] in AAA and x["age"] >= 23.5
           and x["ops"] < -0.05 and (x["spd"] or 0) >= 65])
    block("speed >= 70 anywhere, ops_rel < -0.05",
          [x for x in pool if (x["spd"] or 0) >= 70 and x["ops"] < -0.05])
    block("CONTRAST: AAA, age <= 22, ops_rel > 0",
          [x for x in pool if x["lvl"] in AAA and x["age"] <= 22 and x["ops"] > 0])

    sel = [x for x in pool if x["lvl"] in AAA and x["age"] >= 23.5
           and x["ops"] < -0.05 and (x["spd"] or 0) >= 65]
    if sel:
        print("\n  the comp cohort itself (realized first-6yr WAR):")
        for x in sorted(sel, key=lambda z: -z["y"])[:25]:
            print(f"    {x['key']:30s} age {x['age']:4.1f}  ops_rel {x['ops']:+.3f}  "
                  f"spd {x['spd']}  consensus {x['fv']}  ->  WAR {x['y']:6.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
