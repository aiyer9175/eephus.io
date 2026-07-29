# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Where does the Bradfield over-grade actually come from?

The comp cohort (Triple-A, age >= 23.5, below the level median) realized a mean first-6yr
WAR of 0.49 with a 78.3% bust rate, n=69. Bradfield is served 51 FV with p_bust 0.239.
Every STRUCTURAL fix for that gap measured as a null in the structure lane. So the gap is
not a missing feature. This asks the next question: is eFV's error CONDITIONAL on the
population, in a way the pooled gate metric cannot see?

The hypothesis worth testing, and it comes straight from the calibration lane: eFV trains
and gates on a pool that is largely rows with NO MiLB track record, while the served board
contains only rows WITH one. If the model's bias differs sharply between those two
populations, then every gate number in the repo has been computed mostly on players the
board never displays, and a large served-population bias can sit underneath a clean pooled
metric without ever showing up.

Read-only. Uses the already-scored artifact rather than refitting.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"


def main() -> int:
    mat = {r["player_key"]: r for r in
           json.loads((DATA / "xfv_hitter_matrix.json").read_text(encoding="utf-8"))}
    scored = json.loads((DATA / "xfv_scored.json").read_text(encoding="utf-8"))
    if isinstance(scored, dict):
        scored = scored.get("rows") or scored.get("players") or []
    print(f"matrix {len(mat)}   scored {len(scored)}")
    if scored:
        print("scored keys:", sorted(scored[0].keys())[:24])

    gk = next((k for k in ("xfv_grade", "grade", "xfv", "pred_grade")
               if scored and k in scored[0]), None)
    yk = next((k for k in ("target_resolved", "realized_war_6yr", "y", "target")
               if scored and k in scored[0]), None)
    print(f"using grade key {gk!r}, outcome key {yk!r}")
    if not gk:
        print("NO GRADE KEY -- cannot proceed")
        return 1

    rows = []
    for s in scored:
        pk = s.get("player_key")
        m = mat.get(pk)
        if not m:
            continue
        y = m.get("target_resolved")
        if not isinstance(y, (int, float)):
            continue
        mb = m.get("milb") if isinstance(m.get("milb"), dict) else {}
        has_milb = bool(mb) and not mb.get("rates_missing") and mb.get("age") is not None
        rows.append({
            "key": pk, "g": float(s[gk]), "y": float(y), "has_milb": has_milb,
            "lvl": mb.get("milb_level"), "age": mb.get("age"), "ops": mb.get("ops_rel"),
        })
    print(f"joined with a resolved outcome: {len(rows)}")

    import value_framework as vf

    def implied_war(g):
        return 6 * vf.fv_to_6yr_avg_war(g)

    def block(name, sel):
        if len(sel) < 10:
            print(f"\n{name}: n={len(sel)} TOO THIN")
            return
        pred = [implied_war(x["g"]) for x in sel]
        act = [x["y"] for x in sel]
        bias = st.mean(pred) - st.mean(act)
        print(f"\n{name}: n={len(sel)}")
        print(f"  mean served grade {st.mean(x['g'] for x in sel):5.2f}")
        print(f"  WAR the grade PROMISES {st.mean(pred):6.2f}   "
              f"WAR actually realized {st.mean(act):6.2f}   "
              f"OVER-PROMISE {bias:+6.2f}")

    block("ALL scored+resolved", rows)
    block("HAS a MiLB track record (the served population)",
          [x for x in rows if x["has_milb"]])
    block("NO MiLB track record (trains + gates, never served)",
          [x for x in rows if not x["has_milb"]])
    aaa = [x for x in rows if x["has_milb"] and x["lvl"] == "AAA"]
    block("Triple-A (served)", aaa)
    block("Triple-A, age >= 23.5 (served)",
          [x for x in aaa if (x["age"] or 0) >= 23.5])
    block("THE BRADFIELD PROFILE: AAA, age >= 23.5, ops_rel < 0",
          [x for x in aaa if (x["age"] or 0) >= 23.5 and (x["ops"] or 0) < 0])
    block("CONTRAST: AAA, age <= 22, ops_rel > 0",
          [x for x in aaa if (x["age"] or 99) <= 22 and (x["ops"] or 0) > 0])

    n_has = sum(1 for x in rows if x["has_milb"])
    print(f"\nPOPULATION SPLIT of the gated pool: {n_has} with a track record, "
          f"{len(rows) - n_has} without ({100*(len(rows)-n_has)/max(1,len(rows)):.1f}% "
          f"of what every gate number is computed on is never shown on the board)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
