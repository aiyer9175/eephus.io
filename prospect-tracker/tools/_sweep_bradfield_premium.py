# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Does eFV's PREMIUM OVER SCOUTS pay off on the Bradfield profile?

Bradfield is served eFV 51 against a consensus of 45.6, a +6.1 premium. His historical
comps (Triple-A, old for level, below the level median) were graded ~33 by this same
model -- because their CONSENSUS was 35-43, not 45.6. So eFV is not inventing his grade
from nothing; it is anchoring on a scouting grade and then adding to it.

The sharp question is therefore not "is 51 too high" in the abstract. It is: on players
with this profile, is eFV's disagreement with scouts INFORMATIVE or is it noise pointed
the wrong way? If the premium is positively correlated with realized WAR, the model is
adding value and the complaint is about scouts. If the premium is flat or negative on this
cohort, eFV is systematically overrating a profile that does not pay off, and that is a
real, targeted defect rather than a global calibration wobble.

Measured with a paired bootstrap over players, plus the same statistic on the whole pool
as the reference. Read-only.
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
random.seed(20260725)


def _spearman(a, b):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    ra, rb = rank(a), rank(b)
    n = len(a)
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((x - mb) ** 2 for x in rb) ** 0.5
    return num / (da * db) if da and db else 0.0


def main() -> int:
    mat = {r["player_key"]: r for r in
           json.loads((DATA / "xfv_hitter_matrix.json").read_text(encoding="utf-8"))}
    scored = json.loads((DATA / "xfv_scored.json").read_text(encoding="utf-8"))

    rows = []
    for s in scored:
        m = mat.get(s.get("player_key"))
        if not m:
            continue
        y = s.get("realized_war_6yr")
        c = s.get("consensus_fv")
        g = s.get("xfv_grade")
        if not all(isinstance(v, (int, float)) for v in (y, c, g)):
            continue
        mb = m.get("milb") if isinstance(m.get("milb"), dict) else {}
        rows.append({"key": s["player_key"], "y": float(y), "c": float(c), "g": float(g),
                     "prem": float(g) - float(c), "lvl": mb.get("milb_level"),
                     "age": mb.get("age"), "ops": mb.get("ops_rel"),
                     "spd": m.get("tool_speed")})

    def block(name, sel, B=2000):
        if len(sel) < 20:
            print(f"\n{name}: n={len(sel)} TOO THIN")
            return
        prem = [x["prem"] for x in sel]
        y = [x["y"] for x in sel]
        rho_g = _spearman([x["g"] for x in sel], y)
        rho_c = _spearman([x["c"] for x in sel], y)
        rho_p = _spearman(prem, y)
        # paired bootstrap over players on the premium's own correlation with outcome
        draws = []
        n = len(sel)
        for _ in range(B):
            idx = [random.randrange(n) for _ in range(n)]
            draws.append(_spearman([prem[i] for i in idx], [y[i] for i in idx]))
        draws.sort()
        lo, hi = draws[int(0.025 * B)], draws[int(0.975 * B)]
        print(f"\n{name}: n={n}")
        print(f"  mean premium (eFV - consensus): {st.mean(prem):+5.2f} FV   "
              f"mean realized WAR {st.mean(y):5.2f}")
        print(f"  rank corr with realized WAR:  eFV {rho_g:+.4f}   "
              f"consensus {rho_c:+.4f}   eFV minus consensus = {rho_g - rho_c:+.4f}")
        print(f"  rank corr of the PREMIUM ITSELF with realized WAR: {rho_p:+.4f}  "
              f"CI95 [{lo:+.4f}, {hi:+.4f}]  "
              f"{'INFORMATIVE' if lo > 0 else ('MISLEADING' if hi < 0 else 'NULL')}")

    block("ALL scored (reference)", rows)
    has = [x for x in rows if x["lvl"]]
    block("has a MiLB level (served-comparable)", has)
    aaa = [x for x in has if x["lvl"] == "AAA"]
    block("Triple-A", aaa)
    old = [x for x in aaa if (x["age"] or 0) >= 23.5]
    block("Triple-A, age >= 23.5", old)
    brad = [x for x in old if (x["ops"] or 0) < 0]
    block("THE BRADFIELD PROFILE: AAA, age >= 23.5, ops_rel < 0", brad)
    block("speed-first: tool_speed >= 65, ops_rel < 0, any level",
          [x for x in has if (x["spd"] or 0) >= 65 and (x["ops"] or 0) < 0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
