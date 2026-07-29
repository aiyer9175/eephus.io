"""MECHANISM lane part 6: the SCALE defect.

The board grade inverts value_framework's STRUCTURAL FV->WAR curve
(_expected_control_war), but the model's WAR is anchored to the OUTCOME-FIT
consensus line efv_model._fit_ols_fv. Those two FV<->WAR maps are not inverses,
so the served premium (grade - consensus) is a monotone function of the anchor
even for a player the model has no opinion about. This quantifies it and prices
the rank-neutral alternative (invert the SAME OLS line the anchor uses).
Read-only.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import value_framework as vf                                        # noqa: E402
import efv_model as em                                              # noqa: E402
import efv_score as es                                              # noqa: E402
from prospect_path import _predict                                  # noqa: E402

DATA = ROOT / "data"


def main():
    side = "hit"
    ridge, a, b, ols, _k = es._fit_production(side)
    oa, ob = ols["a"], ols["b"]
    print(f"consensus OLS  E[6yr WAR | FV] = {oa:.4f} + {ob:.4f} * FV")
    print(f"output cal     war = {a:.4f} + {b:.4f} * ridge_pred")

    def ols_inv(war):
        return max(20.0, min(80.0, (war - oa) / ob))

    live = json.loads((DATA / "xfv_live_hitter_matrix.json").read_text(encoding="utf-8"))
    xfv = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]

    rows = []
    for r in live:
        x = xfv.get(r["player_key"])
        if not x or x.get("kind") != "active" or x.get("xfv_grade_model_raw") is None:
            continue
        war = x.get("xfv_war_6yr")
        if war is None:
            continue
        cons = float(r["consensus_fv_raw"])
        rows.append({"pk": r["player_key"], "cons": cons, "war": war,
                     "cur": x["xfv_grade_model_raw"], "alt": ols_inv(war)})

    print(f"\nlive scored hitters n={len(rows)}")
    print("cons band      n   CURRENT grade  CURRENT prem | OLS-INVERSE grade  prem")
    for lo, hi in ((30, 35), (35, 38), (38, 41), (41, 44), (44, 47), (47, 50),
                   (50, 55), (55, 70)):
        s = [t for t in rows if lo <= t["cons"] < hi]
        if not s:
            continue
        print(f"[{lo:2d},{hi:2d})  {len(s):5d}   "
              f"{statistics.mean([t['cur'] for t in s]):8.2f}  "
              f"{statistics.mean([t['cur'] - t['cons'] for t in s]):+8.2f}   |  "
              f"{statistics.mean([t['alt'] for t in s]):8.2f}  "
              f"{statistics.mean([t['alt'] - t['cons'] for t in s]):+8.2f}")

    br = next(t for t in rows if t["pk"] == "enrique_bradfield_jr")
    print(f"\nBradfield: war {br['war']:.3f}  cons {br['cons']:.2f}")
    print(f"  CURRENT      raw grade {br['cur']:.2f}  premium {br['cur']-br['cons']:+.2f}")
    print(f"  OLS-INVERSE  grade     {br['alt']:.2f}  premium {br['alt']-br['cons']:+.2f}")

    # ranks under both
    for key in ("cur", "alt"):
        srt = sorted(rows, key=lambda t: -t[key])
        pos = [i for i, t in enumerate(srt, 1) if t["pk"] == "enrique_bradfield_jr"][0]
        print(f"  hitter-only rank on {key}: {pos} of {len(rows)}")

    # is the change rank-preserving?
    import math
    cur = [t["cur"] for t in rows]
    alt = [t["alt"] for t in rows]

    def rk(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for i, j in enumerate(o):
            r[j] = i
        return r
    rc, ra = rk(cur), rk(alt)
    n = len(cur); mc = sum(rc) / n; ma = sum(ra) / n
    cov = sum((x - mc) * (y - ma) for x, y in zip(rc, ra))
    vx = sum((x - mc) ** 2 for x in rc); vy = sum((y - ma) ** 2 for y in ra)
    print(f"\nSpearman(current grade, OLS-inverse grade) = {cov/math.sqrt(vx*vy):.6f}")
    print("  (both are monotone in xfv_war -> the change is EXACTLY rank-neutral; "
          "ties at the FV-20 floor are the only difference)")
    fl = sum(1 for t in rows if t["cur"] <= 20.0001)
    fla = sum(1 for t in rows if t["alt"] <= 20.0001)
    print(f"  rows pinned at FV 20: current {fl} ({fl/n:.3f})  OLS-inverse {fla} ({fla/n:.3f})")

    # served move distribution
    mv = [t["alt"] - t["cur"] for t in rows]
    print(f"  served grade move: mean {statistics.mean(mv):+.2f} "
          f"median {statistics.median(mv):+.2f} min {min(mv):+.2f} max {max(mv):+.2f}")


if __name__ == "__main__":
    main()
