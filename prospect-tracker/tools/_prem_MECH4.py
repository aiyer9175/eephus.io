"""MECHANISM lane part 4: (c) imputation audit, (d) live-vs-matrix path audit,
and the standardization-pool asymmetry (train mu/sd set by no-track-record rows).
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


def main():
    side = "hit"
    ridge, a, b, ols, _k = es._fit_production(side)
    mu = dict(zip(ridge["keys"], ridge["mu"]))
    sd = dict(zip(ridge["keys"], ridge["sd"]))
    w = dict(zip(ridge["keys"], ridge["w"]))

    matrix = json.loads((DATA / "xfv_hitter_matrix.json").read_text(encoding="utf-8"))
    scored = {s["player_key"]: s for s in
              json.loads((DATA / "xfv_scored.json").read_text(encoding="utf-8"))}
    live = json.loads((DATA / "xfv_live_hitter_matrix.json").read_text(encoding="utf-8"))
    br = next(x for x in live if x["player_key"] == "enrique_bradfield_jr")

    # ---- the FIT pool exactly as _fit_production builds it -------------------
    pool = [r for r in matrix if not r.get("is_pitcher")
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    data = em._prep(pool, "target_censored", side)
    n = len(data)
    by_key = {r["player_key"]: r for r in pool}
    have_milb = [d for d in data if by_key[d["player_key"]].get("milb")]
    print(f"FIT POOL n={n}  with a MiLB block: {len(have_milb)} "
          f"({len(have_milb)/n:.3f})  without: {n-len(have_milb)} "
          f"({1-len(have_milb)/n:.3f})")

    for k in ("level_rank", "n_milb_seasons", "age", "ops_rel", "tool_speed", "fv"):
        allv = [d["feats"].get(k, 0.0) for d in data]
        tr = [d["feats"].get(k, 0.0) for d in have_milb]
        print(f"  {k:16s} FULL mu={statistics.mean(allv):8.4f} sd={statistics.pstdev(allv):7.4f} "
              f"| TRACK-RECORD-ONLY mu={statistics.mean(tr):8.4f} sd={statistics.pstdev(tr):7.4f}")

    # what Bradfield's contributions would be if mu/sd were the track-record pool
    print("\nBradfield contribution under FULL-pool vs TRACK-RECORD-pool standardization:")
    bf = em._vec(br, side)
    tot_full = tot_tr = 0.0
    for k in ridge["keys"]:
        tr = [d["feats"].get(k, 0.0) for d in have_milb]
        m2, s2 = statistics.mean(tr), statistics.pstdev(tr) or 1.0
        cf = w[k] * ((bf.get(k, 0.0) - mu[k]) / (sd[k] or 1.0))
        ct = w[k] * ((bf.get(k, 0.0) - m2) / s2)
        tot_full += cf; tot_tr += ct
        if abs(cf - ct) > 0.02:
            print(f"  {k:16s} full {cf:+7.4f}  track-only {ct:+7.4f}  delta {ct-cf:+7.4f}")
    print(f"  SUM full {tot_full:+.4f}  track-only {tot_tr:+.4f}  delta {tot_tr-tot_full:+.4f}")
    wf = max(-2.0, a + b * (tot_full + ridge["b"]))
    wt = max(-2.0, a + b * (tot_tr + ridge["b"]))
    gf = vf.realized_implied_fv(wf, False, age=31.1, position="CF", exposure_seasons=6)
    gt = vf.realized_implied_fv(wt, False, age=31.1, position="CF", exposure_seasons=6)
    print(f"  war {wf:.3f} -> {wt:.3f}   grade {gf:.3f} -> {gt:.3f}  "
          f"(NOTE: coefficients not refit; illustration of the z-scale only)")

    # ---- stratum: imputation + age placement audit ---------------------------
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
    print(f"\nSTRATUM n={len(strat)}")
    for fld in ("tool_speed", "tool_hit", "tool_field", "tool_game_pwr"):
        miss = sum(1 for r in strat if r.get(fld) is None)
        obs = [float(r[fld]) for r in strat if r.get(fld) is not None]
        print(f"  {fld:14s} missing {miss}/{len(strat)} "
              f"({miss/len(strat):.3f})  observed mean {statistics.mean(obs):.2f}"
              if obs else f"  {fld}: all missing")
    print(f"  Bradfield: tool_speed={br.get('tool_speed')} tool_hit={br.get('tool_hit')} "
          f"tool_field={br.get('tool_field')} (observed, not imputed)")
    print(f"  Bradfield milb flags: stale={br['milb'].get('stale')} "
          f"rates_missing={br['milb'].get('rates_missing')} "
          f"age_missing={br['milb'].get('age_missing')} "
          f"age_rel_level={br['milb'].get('age_rel_level')} "
          f"anchor_stale_discount={br.get('anchor_stale_discount')}")
    nmiss = sum(1 for r in strat if (r.get('milb') or {}).get('rates_missing'))
    print(f"  stratum rates_missing>0: {nmiss}")
    ar = [float((r.get('milb') or {}).get('age_rel_level') or 0.0) for r in strat]
    print(f"  stratum age_rel_level mean {statistics.mean(ar):.4f}  "
          f"Bradfield {br['milb'].get('age_rel_level')}")

    # grade-map age placement, stratum vs Bradfield
    gm = []
    for r in strat:
        dy = r.get("debut_year") or 2020
        ag = es._age_at(r.get("birth_date"), dy)
        if ag is not None:
            gm.append(es._grade_map_age(ag, 0.0))
    print(f"  stratum gm_age mean {statistics.mean(gm):.3f} (n={len(gm)})  "
          f"Bradfield gm_age 31.100")
    # grade sensitivity to that difference at Bradfield's WAR
    for aa in (statistics.mean(gm), 31.1):
        print(f"    grade(4.858, gm_age={aa:.2f}) = "
              f"{vf.realized_implied_fv(4.858, False, age=aa, position='CF', exposure_seasons=6):.4f}")

    # ---- live-path-only effects on Bradfield --------------------------------
    print("\nLIVE-PATH-ONLY effects on Bradfield (FV points):")
    war_pre = 4.858449347401981
    war_post = 4.800147955233157
    g_pre = vf.realized_implied_fv(war_pre, False, age=31.1, position="CF", exposure_seasons=6)
    g_post = vf.realized_implied_fv(war_post, False, age=31.1, position="CF", exposure_seasons=6)
    print(f"  Statcast+ tilt 0.988: {g_pre:.4f} -> {g_post:.4f}  ({g_post-g_pre:+.4f} FV)")
    import efv_board_scale as bs
    bg = bs.board_value({"side": "H", "xfv_grade_model_raw": g_post, "xfv_grade": g_post})
    print(f"  W-SIDESCALE affine:   {g_post:.4f} -> {bg:.4f}  ({bg-g_post:+.4f} FV)")
    sg = statistics.mean([scored[r['player_key']]['xfv_grade'] for r in strat])
    sbg = bs.board_value({"side": "H", "xfv_grade_model_raw": sg, "xfv_grade": sg})
    print(f"  same affine on the stratum mean grade {sg:.3f} -> {sbg:.3f} ({sbg-sg:+.3f} FV)")
    print(f"  blend leg (lambda 0.70 / consensus OLS) enters the SERVED grade: NO "
          f"(rank_war feeds only the retired quantile display)")


if __name__ == "__main__":
    main()
