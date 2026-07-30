# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE-PROV-MAP: should efv_ungraded._grade be re-pointed onto vf.outcome_implied_fv?

MEASUREMENT ONLY. Imports production code read-only, edits nothing, writes exactly one
artifact (data/provisional_grade_map_eval.json). Never imported by the site or an exporter.

Pre-registration (on disk and committed BEFORE this file was written):
docs/efv-2026-07-30/PROVISIONAL_GRADE_MAP_GATE.md.

Candidates (gate doc 1.5):
    V0  re-point, cap constants left as FV numbers      (the literal reading of the brief)
    V1  re-point, cap translated into WAR space         (exact algebra, gate doc 1.3)
    KEEP  the incumbent bespoke linear map

Every counterfactual grade is computed from the SERVED row's own stored `xfv_war_6yr`, so
both sides of every delta use one WAR value and the delta is a pure map effect.

Run:  python -m tools.provisional_grade_map_lab      (from the repo root)
"""
from __future__ import annotations

import json
import math
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

import value_framework as vf                                    # noqa: E402
import efv_ungraded as eu                                       # noqa: E402
import storage as st                                            # noqa: E402
from efv_dataset import TARGET_SEASONS                          # noqa: E402


# ===========================================================================
# the three maps
# ===========================================================================
def g_keep(war: float, side: str) -> float:
    """The incumbent: efv_ungraded._grade, called directly so this is not a re-implementation."""
    return eu._grade(war, side)


def g_v0(war: float, side: str) -> float:
    """V0: outcome_implied_fv, then the SAME soft ceiling with the SAME FV constants."""
    m = eu._GRADE_MAP[side]
    g = vf.outcome_implied_fv(war, exposure_seasons=TARGET_SEASONS)
    if g is None:
        return None
    g = max(m["FLOOR"], g)
    if not eu.UNCAPPED_GRADE:
        knee, ceil, soft = m["KNEE"], m["CEIL"], m["SOFT"]
        if g > knee:
            g = knee + (ceil - knee) * (1.0 - math.exp(-(g - knee) / soft))
    return round(g, 1)


def _war_cap_constants(side: str) -> dict:
    """The soft cap's constants expressed in WAR, by the exact algebra of gate doc 1.3.
    Because the incumbent map is affine (g = BASE + SLOPE*w), compressing w toward CEIL_W
    and then reading BASE + SLOPE*w' reproduces the incumbent grade IDENTICALLY."""
    m = eu._GRADE_MAP[side]
    return {"KNEE_W": (m["KNEE"] - m["BASE"]) / m["SLOPE"],
            "CEIL_W": (m["CEIL"] - m["BASE"]) / m["SLOPE"],
            "SOFT_W": m["SOFT"] / m["SLOPE"],
            "SUBFLOOR_W": (eu._SUBFLOOR_GRADE - m["BASE"]) / m["SLOPE"]}


def cap_war(war: float, side: str) -> float:
    c = _war_cap_constants(side)
    if eu.UNCAPPED_GRADE or war <= c["KNEE_W"]:
        return war
    return c["KNEE_W"] + (c["CEIL_W"] - c["KNEE_W"]) * (
        1.0 - math.exp(-(war - c["KNEE_W"]) / c["SOFT_W"]))


def g_v1(war: float, side: str) -> float:
    """V1: the soft ceiling applied in WAR space, then outcome_implied_fv."""
    g = vf.outcome_implied_fv(cap_war(war, side), exposure_seasons=TARGET_SEASONS)
    return None if g is None else round(max(20.0, g), 1)


def _verify_v1_algebra() -> dict:
    """The claim in gate doc 1.3: capping in WAR space and reading BASE + SLOPE*w' reproduces
    the incumbent grade exactly. Verified numerically before anything is measured with it."""
    worst = 0.0
    for side in ("hit", "pit"):
        m = eu._GRADE_MAP[side]
        w = -2.0
        while w <= 12.0:
            lhs = eu._grade(w, side)
            rhs = round(max(m["FLOOR"], m["BASE"] + m["SLOPE"] * cap_war(w, side)), 1)
            worst = max(worst, abs(lhs - rhs))
            w = round(w + 0.01, 2)
    return {"max_abs_fv_difference": round(worst, 6),
            "claim": "cap-in-WAR then affine == incumbent _grade"}


# ===========================================================================
# the served pool
# ===========================================================================
def load_pool() -> list[dict]:
    d = json.loads((DATA / "xfv_ungraded.json").read_text(encoding="utf-8"))
    out = []
    for pk, e in d["by_player"].items():
        w = e.get("xfv_war_6yr")
        if w is None:
            continue
        side = "pit" if e.get("side") == "P" else "hit"
        out.append({"player_key": pk, "side": side, "war": float(w),
                    "org": e.get("org"), "level": e.get("level"),
                    "served_grade": e.get("xfv_grade"),
                    "served_surplus": e.get("surplus_mm"),
                    "served_p_bust": e.get("p_bust")})
    return out


def _apply(rows: list[dict]) -> None:
    """Attach every candidate's grade, with each branch's own cameo sub-floor cap.

    The cameo cap is part of the map, not a separate step: V0 keeps it as the FV constant
    30.0 (the FV reading); V1 caps the WAR at the equivalent (the WAR reading). Which rows
    it applies to is fixed by the SERVED artifact -- a row is a cameo iff production floored
    it -- so the branch cannot change the population it binds on, only the value it writes."""
    for r in rows:
        side, w = r["side"], r["war"]
        base_keep = g_keep(w, side)
        r["cameo"] = (r["served_grade"] is not None
                      and base_keep > eu._SUBFLOOR_GRADE
                      and abs(r["served_grade"] - eu._SUBFLOOR_GRADE) < 1e-9)
        r["KEEP"] = min(base_keep, eu._SUBFLOOR_GRADE) if r["cameo"] else base_keep
        v0 = g_v0(w, side)
        r["V0"] = min(v0, eu._SUBFLOOR_GRADE) if r["cameo"] else v0
        c = _war_cap_constants(side)
        w1 = min(w, c["SUBFLOOR_W"]) if r["cameo"] else w
        r["V1"] = g_v1(w1, side)
        # cap census
        r["knee_bind_KEEP"] = (not eu.UNCAPPED_GRADE) and w > c["KNEE_W"]
        gv0 = vf.outcome_implied_fv(w, exposure_seasons=TARGET_SEASONS)
        r["knee_bind_V0"] = (not eu.UNCAPPED_GRADE) and gv0 is not None and gv0 > eu._GRADE_MAP[side]["KNEE"]
        r["knee_bind_V1"] = r["knee_bind_KEEP"]


# ===========================================================================
# reporting helpers
# ===========================================================================
def dist(vals: list[float]) -> dict:
    v = sorted(x for x in vals if x is not None)
    if not v:
        return {}
    def q(p):
        return v[min(len(v) - 1, int(p * (len(v) - 1)))]
    return {"n": len(v), "min": v[0], "median": round(statistics.median(v), 1),
            "p75": q(0.75), "p90": q(0.90), "p99": q(0.99), "max": v[-1],
            "mean": round(sum(v) / len(v), 2),
            "share_le_30": round(sum(1 for x in v if x <= 30) / len(v), 4),
            "n_ge_35": sum(1 for x in v if x >= 35),
            "n_ge_40": sum(1 for x in v if x >= 40),
            "n_ge_45": sum(1 for x in v if x >= 45),
            "n_at_floor_20": sum(1 for x in v if x <= 20.0)}


def move_report(rows: list[dict], arm: str) -> dict:
    out = {}
    for sd in ("hit", "pit", "all"):
        sub = [r for r in rows if sd == "all" or r["side"] == sd]
        if not sub:
            continue
        d = [r[arm] - r["KEEP"] for r in sub]
        moved = [x for x in d if abs(x) >= 0.05]
        out[sd] = {
            "n": len(sub), "n_moved": len(moved),
            "share_moved": round(len(moved) / len(sub), 4),
            "n_up": sum(1 for x in d if x > 0.05), "n_down": sum(1 for x in d if x < -0.05),
            "mean_d": round(sum(d) / len(d), 3),
            "mean_abs_d": round(sum(abs(x) for x in d) / len(d), 3),
            "max_abs_d": round(max(abs(x) for x in d), 2),
        }
    # FV45 crossings
    up45 = sum(1 for r in rows if r["KEEP"] < 45 <= r[arm])
    dn45 = sum(1 for r in rows if r[arm] < 45 <= r["KEEP"])
    out["fv45_line"] = {"cross_up": up45, "cross_down": dn45,
                        "n_ge_45_before": sum(1 for r in rows if r["KEEP"] >= 45),
                        "n_ge_45_after": sum(1 for r in rows if r[arm] >= 45)}
    # within-side order preservation (STOP condition 6)
    viol = 0
    for sd in ("hit", "pit"):
        sub = sorted((r for r in rows if r["side"] == sd), key=lambda r: r["war"])
        for a, b in zip(sub, sub[1:]):
            if b[arm] < a[arm] - 1e-9 and b["war"] > a["war"] + 1e-9:
                viol += 1
    out["within_side_order_violations"] = viol
    return out


def farm_report(rows: list[dict], arm: str) -> dict:
    """Farm depth/top-end pool effect. The graded side of the pool is data/xfv.json's active
    rows joined to an org through data/rosters_by_org.json, which is how the served pool is
    assembled (storage._load_ungraded_by_org supplies the provisional side directly)."""
    try:
        xfv = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]
        rost = json.loads((DATA / "rosters_by_org.json").read_text(encoding="utf-8"))
    except OSError:
        return {"available": False}
    org_of = {}
    for org, levels in rost.items():
        for lvl, players in (levels or {}).items():
            if lvl == "MLB" or not isinstance(players, list):
                continue
            for p in players:
                pk = p.get("player_key")
                if pk:
                    org_of[pk] = org
    graded = {}
    for pk, e in xfv.items():
        if e.get("kind") != "active" or e.get("xfv_grade") is None:
            continue
        org = org_of.get(pk)
        if org:
            graded.setdefault(org, []).append({"xfv_grade": float(e["xfv_grade"])})
    prov = {}
    for r in rows:
        if r["org"]:
            prov.setdefault(r["org"], []).append(r)

    per_org, tot_before, tot_after, in25_b, in25_a = {}, 0.0, 0.0, 0, 0
    for org in sorted(set(graded) | set(prov)):
        g = graded.get(org, [])
        pr = prov.get(org, [])
        def score(field):
            pool = g + [{"xfv_grade": r[field], "provisional": True} for r in pr]
            top = st._top_end_points(pool)
            dep = st._depth_points(pool)
            rk = sorted(pool, key=lambda p: (st._eff_grade(p) or 0), reverse=True)[:st.FARM_DEPTH_END]
            return top, dep, sum(1 for p in rk if p.get("provisional"))
        tb, db, cb = score("KEEP")
        ta, da, ca = score(arm)
        per_org[org] = {"n_graded": len(g), "n_prov": len(pr),
                        "top_end_before": tb, "top_end_after": ta,
                        "depth_before": db, "depth_after": da,
                        "prov_in_top25_before": cb, "prov_in_top25_after": ca}
        tot_before += tb + db
        tot_after += ta + da
        in25_b += cb
        in25_a += ca
    changed = sum(1 for v in per_org.values()
                  if abs(v["top_end_after"] - v["top_end_before"]) > 0.005
                  or abs(v["depth_after"] - v["depth_before"]) > 0.005)
    return {"available": True, "n_orgs": len(per_org), "orgs_with_points_change": changed,
            "league_total_points_before": round(tot_before, 2),
            "league_total_points_after": round(tot_after, 2),
            "provisional_in_top25_before": in25_b, "provisional_in_top25_after": in25_a,
            "per_org": per_org}


def joint_board_report(rows: list[dict], arm: str) -> dict:
    """The client-side joint ordering (prospx buildEfvRankMap): graded ACTIVE rows and
    provisional rows sorted together on the single field `xfv_grade`."""
    try:
        xfv = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    except OSError:
        return {"available": False}
    graded = [(pk, float(e["xfv_grade"])) for pk, e in xfv.items()
              if e.get("kind") == "active" and e.get("xfv_grade") is not None]

    def ranks(field):
        pool = [(pk, g, 0) for pk, g in graded] + [(r["player_key"], r[field], 1) for r in rows]
        pool.sort(key=lambda t: (-t[1], t[2], t[0]))
        return {t[0]: i + 1 for i, t in enumerate(pool)}, len(pool)

    rb, n = ranks("KEEP")
    ra, _ = ranks(arm)
    gmv = [abs(ra[pk] - rb[pk]) for pk, _g in graded]
    pmv = [abs(ra[r["player_key"]] - rb[r["player_key"]]) for r in rows]
    def summ(v):
        v = sorted(v)
        return {"n": len(v), "n_moved": sum(1 for x in v if x),
                "median_abs": v[len(v) // 2] if v else 0,
                "p95_abs": v[int(0.95 * (len(v) - 1))] if v else 0, "max_abs": v[-1] if v else 0}
    top = lambda m, k: {t for t, rk in m.items() if rk <= k}
    return {"available": True, "pool_size": n, "n_graded_active": len(graded),
            "graded_rows": summ(gmv), "provisional_rows": summ(pmv),
            "membership": {f"top_{k}": {"held": len(top(rb, k) & top(ra, k)),
                                        "in": len(top(ra, k) - top(rb, k)),
                                        "out": len(top(rb, k) - top(ra, k))}
                           for k in (10, 25, 50, 100, 300)},
            "provisional_in_top": {f"top_{k}": [sum(1 for r in rows if rb[r["player_key"]] <= k),
                                                sum(1 for r in rows if ra[r["player_key"]] <= k)]
                                   for k in (100, 300, 500, 1000)}}


def thin_pbust_report(rows: list[dict], arm: str) -> dict:
    """STOP condition 3. The thin-sample head measured this population's realized bust rate as
    a function of THIS map's grade. What does a candidate do to the grade of the cohort that
    evidence was measured on (provisional grade >= 35), and to the graded-population curve's
    reading of them?"""
    coh = [r for r in rows if r["KEEP"] >= 35.0]
    out = {"n_cohort_grade_ge_35": len(coh)}
    for sd in ("hit", "pit"):
        sub = [r for r in coh if r["side"] == sd]
        if not sub:
            continue
        is_pit = sd == "pit"
        def curve_pbust(field):
            v = []
            for r in sub:
                pb = vf.p_bucket_given_fv(r[field], is_pit)
                if pb:
                    v.append(float(pb[0]))
            return round(sum(v) / len(v), 4) if v else None
        out[sd] = {
            "n": len(sub),
            "mean_grade_before": round(sum(r["KEEP"] for r in sub) / len(sub), 2),
            "mean_grade_after": round(sum(r[arm] for r in sub) / len(sub), 2),
            "graded_curve_p_bust_before": curve_pbust("KEEP"),
            "graded_curve_p_bust_after": curve_pbust(arm),
            "thin_head_p_bust_before": round(sum(
                eu.thin_sample_p_bust(r["KEEP"], sd, r["level"]) or 0 for r in sub) / len(sub), 4),
            "thin_head_p_bust_if_reargued": round(sum(
                eu.thin_sample_p_bust(r[arm], sd, r["level"]) or 0 for r in sub) / len(sub), 4),
            "measured_empirical_bust_rate": 0.881 if sd == "hit" else 0.940,
            "g1_defect_empirical_minus_served": 0.169 if sd == "hit" else 0.130,
        }
    return out


# ===========================================================================
# main
# ===========================================================================
def main() -> dict:
    t0 = time.time()
    print("LANE-PROV-MAP: re-point efv_ungraded._grade onto the board's map?")
    print("  pre-registration: docs/efv-2026-07-30/PROVISIONAL_GRADE_MAP_GATE.md")

    algebra = _verify_v1_algebra()
    print(f"  V1 algebra check: max |dFV| = {algebra['max_abs_fv_difference']}")

    rows = load_pool()
    _apply(rows)
    print(f"  pool: {len(rows)} provisional rows "
          f"({sum(1 for r in rows if r['side']=='hit')} hit / "
          f"{sum(1 for r in rows if r['side']=='pit')} pit), "
          f"{sum(1 for r in rows if r['cameo'])} cameo-capped")

    # reconstruction fidelity of the incumbent map against the served artifact
    diffs = [abs(r["KEEP"] - r["served_grade"]) for r in rows if r["served_grade"] is not None]
    recon = {"n": len(diffs), "n_exact": sum(1 for d in diffs if d < 1e-9),
             "max_abs_fv": round(max(diffs), 3) if diffs else None,
             "mean_abs_fv": round(sum(diffs) / len(diffs), 5) if diffs else None,
             "note": "xfv_war_6yr is stored at 2dp, so a 1dp grade can disagree by up to 0.1 FV"}
    print(f"  reconstruction vs served: {recon['n_exact']}/{recon['n']} exact, "
          f"max {recon['max_abs_fv']} FV")

    cap = {"war_constants": {s: {k: round(v, 4) for k, v in _war_cap_constants(s).items()}
                             for s in ("hit", "pit")},
           "fv_constants": eu._GRADE_MAP,
           "binds_at_predicted_war": {}}
    for s in ("hit", "pit"):
        m = eu._GRADE_MAP[s]
        c = _war_cap_constants(s)
        def inv(fv):
            cc = vf._outcome_curve()
            ks, vs = cc["knots"], cc["value"]
            for (k0, v0), (k1, v1) in zip(zip(ks, vs), zip(ks[1:], vs[1:])):
                if k0 <= fv <= k1:
                    return round(v0 + (v1 - v0) * ((fv - k0) / (k1 - k0)), 4)
            return None
        cap["binds_at_predicted_war"][s] = {
            "KNEE": {"fv": m["KNEE"], "incumbent_map": round(c["KNEE_W"], 4),
                     "outcome_map": inv(m["KNEE"])},
            "CEIL": {"fv": m["CEIL"], "incumbent_map": round(c["CEIL_W"], 4),
                     "outcome_map": inv(m["CEIL"])},
            "SUBFLOOR": {"fv": eu._SUBFLOOR_GRADE, "incumbent_map": round(c["SUBFLOOR_W"], 4),
                         "outcome_map": inv(eu._SUBFLOOR_GRADE)},
        }
    for arm in ("KEEP", "V0", "V1"):
        cap.setdefault("rows_above_knee", {})[arm] = {
            s: sum(1 for r in rows if r["side"] == s and r[f"knee_bind_{arm}"])
            for s in ("hit", "pit")}

    out = {
        "line": "LANE-PROV-MAP 2026-07-30: the provisional grade map, measured.",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "lab": "tools/provisional_grade_map_lab.py",
        "pre_registration": "docs/efv-2026-07-30/PROVISIONAL_GRADE_MAP_GATE.md",
        "registry_row": "xfv_provisional_grade_map",
        "changes_served_output": False,
        "v1_algebra_check": algebra,
        "reconstruction_check": recon,
        "cap_interaction": cap,
        "distribution": {a: dist([r[a] for r in rows]) for a in ("KEEP", "V0", "V1")},
        "distribution_by_side": {
            s: {a: dist([r[a] for r in rows if r["side"] == s]) for a in ("KEEP", "V0", "V1")}
            for s in ("hit", "pit")},
        "blast_radius": {a: move_report(rows, a) for a in ("V0", "V1")},
        "farm_pool": {a: farm_report(rows, a) for a in ("V0", "V1")},
        "joint_board": {a: joint_board_report(rows, a) for a in ("V0", "V1")},
        "thin_pbust_direction": {a: thin_pbust_report(rows, a) for a in ("V0", "V1")},
        "orphans": {},
        "runtime_s": None,
    }

    # the seven recently-routed orphans, at the WAR values ORPHAN_ROUTING.md 3 replayed
    for pk, sd, w in (("easton_shelton", "hit", 3.505), ("braylon_whitaker", "hit", 2.161),
                      ("jacob_friend", "hit", 2.144), ("michael_martinez", "hit", 2.099),
                      ("jake_cunningham", "hit", 1.715), ("mason_guerra", "hit", -0.200),
                      ("jose_meza", "hit", -1.464)):
        out["orphans"][pk] = {
            "predicted_war": w, "KEEP": g_keep(w, sd), "V0": g_v0(w, sd), "V1": g_v1(w, sd),
            "flagship_grade_it_replaced": {"easton_shelton": 40.8, "braylon_whitaker": 35.0,
                                           "jacob_friend": 43.5, "michael_martinez": 40.6,
                                           "jake_cunningham": 41.2, "mason_guerra": 37.5,
                                           "jose_meza": 21.6}[pk],
            "flagship_map_at_this_war": round(
                vf.outcome_implied_fv(w, exposure_seasons=TARGET_SEASONS), 1),
        }

    out["runtime_s"] = round(time.time() - t0, 1)
    (DATA / "provisional_grade_map_eval.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    print(f"  wrote data/provisional_grade_map_eval.json ({out['runtime_s']}s)")
    return out


if __name__ == "__main__":
    main()
