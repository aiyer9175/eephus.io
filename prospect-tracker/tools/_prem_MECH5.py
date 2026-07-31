"""MECHANISM lane part 5: the single consistent decomposition path from the
stratum's served mean premium (-6.06) to Bradfield's (+6.09), plus the FV-20
floor / Jensen accounting and the zero-fill standardization audit.
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

DATA = ROOT / "data"
NONFV = ("tool_speed", "tool_hit", "is_college", "peak_k_rel", "age_rel_level",
         "n_milb_seasons", "age", "is_ifa", "ops_rel", "k_rel", "obp_rel",
         "milb_missing", "level_rank")


def main():
    side = "hit"
    ridge, a, b, ols, _k = es._fit_production(side)
    mu = dict(zip(ridge["keys"], ridge["mu"]))
    sd = dict(zip(ridge["keys"], ridge["sd"]))
    w = dict(zip(ridge["keys"], ridge["w"]))
    keys = list(ridge["keys"])

    matrix = json.loads((DATA / "xfv_hitter_matrix.json").read_text(encoding="utf-8"))
    scored = {s["player_key"]: s for s in
              json.loads((DATA / "xfv_scored.json").read_text(encoding="utf-8"))}
    live = json.loads((DATA / "xfv_live_hitter_matrix.json").read_text(encoding="utf-8"))
    br = next(x for x in live if x["player_key"] == "enrique_bradfield_jr")
    bf = em._vec(br, side)

    strat = []
    for r in matrix:
        if r.get("is_pitcher"):
            continue
        m = r.get("milb") or {}
        if m.get("milb_level") != "AAA" or m.get("age") is None or float(m["age"]) < 23.5:
            continue
        if m.get("ops_rel") is None or float(m["ops_rel"]) >= 0:
            continue
        if r["player_key"] in scored:
            strat.append(r)
    sf = {k: statistics.mean([em._vec(r, side).get(k, 0.0) for r in strat]) for k in keys}
    scons = statistics.mean([float(r["consensus_fv_raw"]) for r in strat])

    gr = [scored[r["player_key"]]["xfv_grade"] for r in strat]
    floored = sum(1 for g in gr if g <= 20.0001)
    print(f"stratum n={len(strat)}  served mean grade {statistics.mean(gr):.4f}  "
          f"median {statistics.median(gr):.2f}  min {min(gr):.1f} max {max(gr):.1f}")
    print(f"  rows pinned to the FV-20 floor: {floored} ({floored/len(strat):.3f})")
    print(f"  served mean premium {statistics.mean([scored[r['player_key']]['xfv_minus_consensus'] for r in strat]):.4f}")

    def pred(vals):
        return ridge["b"] + sum(w[k] * ((vals[k] - mu[k]) / (sd[k] or 1.0)) for k in keys)

    def grade(vals, gm_age):
        return vf.realized_implied_fv(max(-2.0, a + b * pred(vals)), False,
                                      age=gm_age, position="CF", exposure_seasons=6)

    S = {k: sf[k] for k in keys}
    B = {k: bf.get(k, 0.0) for k in keys}

    print("\n=== ONE CONSISTENT PATH: stratum served premium -> Bradfield served premium ===")
    steps = []
    cur_prem = statistics.mean([scored[r['player_key']]['xfv_minus_consensus'] for r in strat])
    steps.append(("stratum served mean premium (mean of 66 individual grades)", cur_prem, 0.0))

    # 1. collapse the mean-of-grades to the grade-of-mean-features (Jensen / FV-20 floor)
    g1 = grade(S, 31.936)
    p1 = g1 - scons
    steps.append(("-> single representative row at the stratum mean feature vector "
                  "(removes the FV-20 floor / concavity heterogeneity)", p1, p1 - cur_prem))

    # 2. age placement: stratum gm_age 31.936 -> Bradfield 31.100
    g2 = grade(S, 31.1)
    p2 = g2 - scons
    steps.append(("-> Bradfield's grade-map age placement (31.94 -> 31.10)", p2, p2 - p1))

    # 3. consensus anchor 38.734 -> 45.640 (moves BOTH the fv feature and the subtrahend)
    S3 = dict(S); S3["fv"] = B["fv"]
    g3 = grade(S3, 31.1)
    p3 = g3 - float(br["consensus_fv_raw"])
    steps.append(("-> his consensus anchor 38.73 -> 45.64 (fv feature AND the subtracted "
                  "consensus)", p3, p3 - p2))

    # 4. each non-fv feature, in descending |effect|
    cur = dict(S3); gcur = g3; pcur = p3
    order = sorted(NONFV, key=lambda k: -abs(w[k] * ((B[k] - S[k]) / (sd[k] or 1.0))))
    for k in order:
        cur[k] = B[k]
        gn = grade(cur, 31.1)
        pn = gn - float(br["consensus_fv_raw"])
        if abs(pn - pcur) >= 0.005:
            steps.append((f"-> feature {k}: {S[k]:.3f} -> {B[k]:.3f}", pn, pn - pcur))
        pcur = pn

    # 5. live Statcast tilt
    war_b = max(-2.0, a + b * pred(B))
    war_t = es._apply_war_tilt(war_b, 0.988)
    g5 = vf.realized_implied_fv(war_t, False, age=31.1, position="CF", exposure_seasons=6)
    p5 = g5 - float(br["consensus_fv_raw"])
    steps.append(("-> live Statcast+ tilt (0.988, live path only)", p5, p5 - pcur))

    for lbl, prem, d in steps:
        print(f"  {prem:+7.3f}  ({d:+6.3f})  {lbl}")
    print(f"\n  served raw-model premium (data/xfv.json xfv_grade_realized 51.7 - 45.6) = +6.1")
    print(f"  reconstruction = {steps[-1][1]:+.3f}")
    print(f"  TOTAL SWING accounted = {steps[-1][1] - steps[0][1]:+.3f} FV")

    # grouped
    jensen = steps[1][2]
    agep = steps[2][2]
    anchor = steps[3][2]
    feat = sum(d for _l, _p, d in steps[4:-1])
    tilt = steps[-1][2]
    print(f"\n  GROUPED: Jensen/FV-20 floor {jensen:+.2f} | age placement {agep:+.2f} | "
          f"consensus anchor {anchor:+.2f} | non-fv features {feat:+.2f} | live tilt {tilt:+.2f}")

    # ---- zero-fill standardization audit -----------------------------------
    pool = [r for r in matrix if not r.get("is_pitcher")
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    data = em._prep(pool, "target_censored", side)
    bk = {r["player_key"]: r for r in pool}
    z_lr = sum(1 for d in data if d["feats"].get("level_rank", 0.0) == 0.0)
    z_nomilb = sum(1 for d in data if not bk[d["player_key"]].get("milb"))
    print(f"\nZERO-FILL AUDIT: fit rows with level_rank == 0.0: {z_lr}/{len(data)} "
          f"({z_lr/len(data):.3f}); rows with NO milb block at all: {z_nomilb} "
          f"({z_nomilb/len(data):.3f})")
    print("  -> level_rank/n_milb_seasons/ops_rel are hard 0.0 for those rows "
          "(efv_model._vec g() default), i.e. MISSING encoded as the DSL value.")
    print(f"  level_rank z for an AAA row: full-pool {(5.0-mu['level_rank'])/sd['level_rank']:+.3f} "
          f"vs track-record-pool +1.090")
    # how many LIVE scored rows are AAA
    ls = json.loads((DATA / "xfv_scored_live.json").read_text(encoding="utf-8"))
    lk = {r["player_key"]: r for r in live}
    lev = {}
    for s in ls:
        m = (lk.get(s["player_key"]) or {}).get("milb") or {}
        lev[m.get("milb_level")] = lev.get(m.get("milb_level"), 0) + 1
    print(f"  LIVE scored hitter pool by level: {dict(sorted(lev.items(), key=lambda kv: -kv[1]))}")


if __name__ == "__main__":
    main()
