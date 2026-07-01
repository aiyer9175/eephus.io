# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for pal_conversion.py - the role-conversion model core.

Covers the load-bearing properties: arsenal-depth monotonicity (the structural
signal), the fit scores ranking the archetypes correctly (deep-command reliever
> thin power reliever for RP->SP; thin power starter > deep command starter for
SP->RP), the gate flags, the velocity role-delta sign + shape interaction,
role/conversion detection with the held-the-role label, and the display-only
REM+ projection.
"""
from __future__ import annotations

import pal_conversion as pc
from pal_conversion import PalArm


def _arm(mlbam, pitches, *, bb=0.07, velo=94.0, vl=0.70, vr=0.72, k=0.26,
         ip=60.0, tbf=250.0, role="RP"):
    arsenal = [{"pitch": p, "usage": u, "whiff": w, "est_woba": e, "hard_hit": h}
               for (p, u, w, e, h) in pitches]
    return PalArm(mlbam=mlbam, name=f"A{mlbam}", role=role, ip=ip, tbf=tbf,
                  k_pct=k, bb_pct=bb, arsenal=arsenal, fb_velo=velo, ops_vl=vl, ops_vr=vr)


# archetypes
LUGO = _arm(1, [("FF", 0.24, 0.14, 0.31, 0.35), ("SI", 0.16, 0.10, 0.33, 0.36),
                ("CU", 0.22, 0.18, 0.28, 0.33), ("SL", 0.20, 0.20, 0.30, 0.34),
                ("CH", 0.18, 0.16, 0.32, 0.35)], bb=0.055, velo=93.0, vl=0.69, vr=0.70)
HICKS = _arm(2, [("SI", 0.62, 0.12, 0.35, 0.44), ("SL", 0.34, 0.16, 0.33, 0.42)],
             bb=0.115, velo=100.0, vl=0.60, vr=0.78)
MILLER = _arm(3, [("FF", 0.55, 0.28, 0.27, 0.34), ("SL", 0.42, 0.42, 0.24, 0.30)],
              bb=0.075, velo=100.0, vl=0.55, vr=0.58, role="SP", ip=60, tbf=250)
DEEP_SP = _arm(4, [("FF", 0.30, 0.12, 0.33, 0.36), ("SI", 0.20, 0.09, 0.34, 0.37),
                   ("CH", 0.20, 0.16, 0.31, 0.34), ("SL", 0.18, 0.17, 0.30, 0.33),
                   ("CU", 0.12, 0.14, 0.32, 0.35)], bb=0.050, velo=92.0, role="SP")


def test_arsenal_depth_monotone():
    s = [pc.arsenal_depth_score(n) for n in (1, 2, 3, 4)]
    assert s == sorted(s) and s[0] < s[-1]
    assert s[3] == 100.0


def test_rp_sp_ranks_depth_over_power():
    lugo = pc.rp_sp_fit(LUGO)
    hicks = pc.rp_sp_fit(HICKS)
    assert lugo["fit"] > hicks["fit"] + 15, (lugo["fit"], hicks["fit"])
    assert lugo["n_pitches"] >= 4 and hicks["n_pitches"] == 2
    # Hicks (thin, fastball-heavy, wild) trips the structural gates
    keys = {f["key"] for f in hicks["flags"]}
    assert "needs_third" in keys
    # Lugo profiles as a real starter candidate
    assert lugo["fit"] >= 70


def test_sp_rp_gated_by_conversion_need():
    import copy
    # same elite stuff, different rotation results: a dominant starter has no
    # conversion case, a struggling one does
    dom = copy.deepcopy(MILLER); dom.era = 3.0
    strug = copy.deepcopy(MILLER); strug.era = 5.2
    fd, fs = pc.sp_rp_fit(dom), pc.sp_rp_fit(strug)
    assert fs["fit"] > fd["fit"] + 30, (fd["fit"], fs["fit"])       # need gates it
    assert fd["relief_upside"] == fs["relief_upside"]               # upside identical
    assert any(f["key"] == "succeeding_sp" for f in fd["flags"])
    assert any(f["key"] == "struggling_sp" for f in fs["flags"])


def test_sp_rp_ranks_power_over_depth():
    miller = pc.sp_rp_fit(MILLER)
    deep = pc.sp_rp_fit(DEEP_SP)
    assert miller["fit"] > deep["fit"] + 10, (miller["fit"], deep["fit"])
    assert any(f["key"] == "putaway" for f in miller["flags"])       # late-inning weapon
    assert any(f["key"] == "keep_starting" for f in deep["flags"])   # deep arsenal


def test_velo_delta_sign_and_shape():
    # SP->RP gains velo, RP->SP loses it
    assert pc.velo_delta(MILLER, "RP") > 0
    assert pc.velo_delta(LUGO, "SP") < 0
    # a power/thin arm moves MORE than a deep-arsenal arm
    assert abs(pc.velo_delta(HICKS, "RP")) > abs(pc.velo_delta(LUGO, "RP"))
    # projected relief velo is higher than current for a starter
    assert pc.project_velo(MILLER, "RP") > MILLER.fb_velo


def test_platoon_neutrality_and_flag():
    assert pc.platoon_neutrality_score(0.70, 0.70) == 100.0
    assert pc.platoon_neutrality_score(0.60, 0.85) < 100.0
    # Hicks has a big platoon split -> platoon_risk flag
    keys = {f["key"] for f in pc.rp_sp_fit(HICKS)["flags"]}
    assert "platoon_risk" in keys


def test_role_and_conversion_detection():
    assert pc.role_of(60, 0, 65) == "RP"
    assert pc.role_of(30, 28, 165) == "SP"
    assert pc.role_of(30, 12, 100) == "SWING"   # 40% starts, not a full SP or RP
    rows = {
        7: {
            2022: {"G": 60, "GS": 0, "IP": "65.0", "BF": 250, "SO": 70, "BB": 20, "ER": 25, "name": "Convert Guy", "season": 2022},
            2023: {"G": 30, "GS": 28, "IP": "160.0", "BF": 640, "SO": 150, "BB": 45, "ER": 65, "name": "Convert Guy", "season": 2023},
            2024: {"G": 31, "GS": 30, "IP": "175.0", "BF": 700, "SO": 165, "BB": 48, "ER": 70, "name": "Convert Guy", "season": 2024},
        }
    }
    evs = pc.detect_conversions(rows)
    assert len(evs) == 1
    ev = evs[0]
    assert ev["direction"] == "RP->SP" and ev["year"] == 2023
    assert ev["held"] is True               # stayed a starter in 2024
    assert pc.label_success(ev) is True


def test_pitch_add_recommender():
    # Hicks: fastball + slider, no offspeed, big platoon split -> add a changeup vs RHB
    rec = pc.recommend_pitch(HICKS)
    assert rec and rec["add"] == "Changeup" and rec["target"] == "RHB" and rec["priority"] == "high"
    # a fastball + changeup arm with no breaking ball -> add a slider
    fbonly = _arm(9, [("FF", 0.80, 0.10, 0.34, 0.42), ("CH", 0.20, 0.12, 0.33, 0.40)], bb=0.08)
    rec2 = pc.recommend_pitch(fbonly)
    assert rec2 and rec2["add"] == "Slider"
    # Lugo: deep, flat platoon split -> no recommendation
    assert pc.recommend_pitch(LUGO) is None


def test_reverse_platoon():
    # RHP tougher on his own side (RHB) than on LHB -> a reverse split
    rev = PalArm(mlbam=1, ops_vl=0.60, ops_vr=0.74, p_throws="R")
    r = pc.reverse_platoon(rev)
    assert r["reverse"] is True and r["p_throws"] == "R" and r["weak_hand"] == "RHB"
    # a conventional RHP (better vs RHB) is not reverse
    norm = PalArm(mlbam=2, ops_vl=0.78, ops_vr=0.62, p_throws="R")
    assert pc.reverse_platoon(norm)["reverse"] is False
    # LHP conventional (better vs LHB)
    lhp = PalArm(mlbam=3, ops_vl=0.60, ops_vr=0.75, p_throws="L")
    assert pc.reverse_platoon(lhp)["reverse"] is False
    assert pc.reverse_platoon(PalArm(mlbam=4)) is None   # no hand/platoon data


def test_starter_pedigree_nudge():
    import copy
    base = copy.deepcopy(LUGO); base.was_starter = False
    ped = copy.deepcopy(LUGO); ped.was_starter = True
    pro = copy.deepcopy(LUGO); pro.prospx_role = "SP"
    assert pc.rp_sp_fit(ped)["fit"] > pc.rp_sp_fit(base)["fit"]
    assert any(f["key"] == "started_before" for f in pc.rp_sp_fit(ped)["flags"])
    assert any(f["key"] == "prospect_sp" for f in pc.rp_sp_fit(pro)["flags"])


def test_prospect_role_fit_mismatch():
    thin_sp = pc.prospect_role_fit({"fb": 60, "sl": 55, "cmd": 40}, "SP")
    assert thin_sp["lean"] == "RP" and thin_sp["mismatch"] is True      # SP-labeled, profiles RP
    deep_rp = pc.prospect_role_fit({"fb": 60, "sl": 60, "cb": 55, "ch": 55, "cmd": 60}, "RP")
    assert deep_rp["lean"] == "SP" and deep_rp["mismatch"] is True      # RP-labeled, could start
    aligned = pc.prospect_role_fit({"fb": 60, "sl": 60, "cb": 55, "ch": 55, "cmd": 60}, "SP")
    assert aligned["mismatch"] is False


def test_relief_rem_plus_projection_is_display_number():
    import rem_plus
    pool_arms = [rem_plus.Reliever(key=f"p{i}", gs=0, ip=50, tbf=200, so=40, bb=17,
                                   hbp=2, hr=6, er=23) for i in range(12)]
    for r in pool_arms:
        rem_plus.derive_rates(r)
    pool = rem_plus.build_pool(pool_arms)
    proj = pc.project_relief_rem_plus(MILLER, pool)
    assert proj is None or (60 <= proj <= 200)
