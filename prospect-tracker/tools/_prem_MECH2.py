"""MECHANISM lane part 2: the historical stratum (resolved hitters, AAA, age>=23.5,
ops_rel<0) and how its served grade / premium was produced, on BOTH grade scales.
Read-only.
"""
from __future__ import annotations

import json
import sys
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import value_framework as vf                                        # noqa: E402
import efv_model as em                                              # noqa: E402
import efv_score as es                                              # noqa: E402
from prospect_path import _predict                                  # noqa: E402

DATA = ROOT / "data"


def main():
    side, is_pit = "hit", False
    keys, _ = em._feature_spec(side)
    ridge, a, b, ols, _k = es._fit_production(side)
    lam = em.blend_lambda(side)

    matrix = json.loads((DATA / "xfv_hitter_matrix.json").read_text(encoding="utf-8"))
    scored = json.loads((DATA / "xfv_scored.json").read_text(encoding="utf-8"))
    sc_by = {s["player_key"]: s for s in scored}
    mx_by = {r["player_key"]: r for r in matrix}

    strat = []
    for r in matrix:
        if r.get("is_pitcher"):
            continue
        m = r.get("milb") or {}
        if m.get("milb_level") != "AAA":
            continue
        ag = m.get("age")
        if ag is None or float(ag) < 23.5:
            continue
        if m.get("ops_rel") is None or float(m["ops_rel"]) >= 0:
            continue
        s = sc_by.get(r["player_key"])
        if not s:
            continue
        strat.append((r, s))

    print(f"stratum n = {len(strat)}")

    rows = []
    for r, s in strat:
        feats = em._vec(r, side)
        pred = _predict(ridge, feats)
        war = max(-2.0, a + b * pred)
        rows.append({
            "pk": r["player_key"],
            "cons": float(r["consensus_fv_raw"]),
            "grade_raw": s.get("xfv_grade"),
            "grade_disp": s.get("xfv_grade_display"),
            "prem_raw": s.get("xfv_minus_consensus"),
            "prem_disp": s.get("xfv_minus_consensus_display"),
            "war_model": s.get("xfv_war_6yr"),
            "war_refit": war,
            "realized": s.get("realized_war_6yr"),
            "level_rank": (r.get("milb") or {}).get("level_rank"),
            "age": (r.get("milb") or {}).get("age"),
            "n_milb": (r.get("milb") or {}).get("n_milb_seasons"),
            "tool_speed": r.get("tool_speed"),
            "is_college": r.get("is_college"),
            "ops_rel": (r.get("milb") or {}).get("ops_rel"),
            "feats": feats,
        })

    def _mean(k):
        v = [x[k] for x in rows if x.get(k) is not None]
        return statistics.mean(v) if v else None

    for k in ("cons", "grade_raw", "grade_disp", "prem_raw", "prem_disp",
              "war_model", "war_refit", "realized", "level_rank", "age",
              "n_milb", "tool_speed", "is_college", "ops_rel"):
        m = _mean(k)
        print(f"mean {k:12s} = {m:.4f}" if m is not None else f"mean {k:12s} = None")

    # per-feature mean contribution, stratum vs Bradfield
    live = json.loads((DATA / "xfv_live_hitter_matrix.json").read_text(encoding="utf-8"))
    br = next(x for x in live if x["player_key"] == "enrique_bradfield_jr")
    bf = em._vec(br, side)

    print("\nfeature            strat_mean_raw  strat_contrib   brad_raw  brad_contrib   delta")
    tot_s = tot_b = 0.0
    for k, mu, sd, w in zip(ridge["keys"], ridge["mu"], ridge["sd"], ridge["w"]):
        sv = statistics.mean([x["feats"].get(k, 0.0) for x in rows])
        cs = w * ((sv - mu) / (sd or 1.0))
        cb = w * ((bf.get(k, 0.0) - mu) / (sd or 1.0))
        tot_s += cs; tot_b += cb
        print(f"{k:18s} {sv:12.3f} {cs:+13.4f} {bf.get(k,0.0):10.3f} {cb:+13.4f} {cb-cs:+8.4f}")
    print(f"{'SUM(z*w)':18s} {'':12s} {tot_s:+13.4f} {'':10s} {tot_b:+13.4f} {tot_b-tot_s:+8.4f}")
    print(f"pred: strat {tot_s + ridge['b']:.4f}  brad {tot_b + ridge['b']:.4f}")
    ws = max(-2.0, a + b * (tot_s + ridge["b"]))
    wb = max(-2.0, a + b * (tot_b + ridge["b"]))
    print(f"war : strat {ws:.4f}  brad {wb:.4f}")

    # grade of stratum-mean-war at stratum-typical age placement vs brad's
    for lbl, war, gm_age in (("strat@meanwar,debutage24", ws, 24 + 6),
                             ("brad", wb, 24.6 + 0.5 + 6)):
        g = vf.realized_implied_fv(war, is_pit, age=gm_age, position="CF",
                                   exposure_seasons=es.TARGET_SEASONS)
        print(f"{lbl}: war={war:.3f} gm_age={gm_age} grade={g:.3f}")

    # d(grade)/d(war) locally
    for w0 in (1.0, 2.0, 3.0, 4.0, 4.8, 6.0):
        g1 = vf.realized_implied_fv(w0, is_pit, age=31.1, position="CF", exposure_seasons=6)
        g2 = vf.realized_implied_fv(w0 + 0.1, is_pit, age=31.1, position="CF", exposure_seasons=6)
        print(f"war {w0:4.1f} -> grade {g1:6.3f}   d(grade)/d(war) = {(g2-g1)/0.1:6.3f}")

    json.dump(rows, open(DATA / "_prem_mech_strat.json", "w", encoding="utf-8"),
              indent=0, default=str)


if __name__ == "__main__":
    main()
