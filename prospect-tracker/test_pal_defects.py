# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Alchemy Lab: four things the page was saying that were not so.

1. Brooks Raley throws a changeup 10% of the time and the board told him to add a
   changeup. 22 of 236 pitch_add rows recommended a pitch already in the arsenal,
   every one from the same branch: the earlier branches all fire on a family HOLE,
   so what they name is necessarily absent, while the deep-arsenal platoon branch
   picked from the weak hand alone and never looked at the arsenal.

2. The card's eFV branch was dead. assets/pal.js reads `p.fvE != null ?
   Math.round(p.fvE) : fCeil(p.fv)` and fvE was null on 202 of 202 rows, because
   build_prospect_watch_all did not copy the field the loader had already
   resolved. Only the fallback ever ran.

3. "SWING" meant two things. 691 of 1,875 pool pitchers carry a position of RHP,
   LHP or P, which states handedness and NO role, and they were filed as SWING
   beside genuine swingmen. Excluding them from a mismatch list is correct (there
   is no stated role for the shape to disagree with); calling the exclusion a role
   was not, and the copy said "1,875 scanned" without it.

4. A reverse split hid an extreme one. The platoon read was a ternary on
   `reverse`, and 22 of 146 listed rows carry BOTH flags, so they showed the
   strength the note describes and hid the blocker it describes in the same
   sentence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import pal_conversion as pc

HERE = Path(__file__).parent
PAYLOAD = HERE / "data" / "pal.json"

# Statcast code -> the display name recommend_pitch uses.
PITCH_NAME = {"SL": "Slider", "ST": "Sweeper", "CU": "Curveball", "KC": "Knuckle-curve",
              "CH": "Changeup", "FS": "Splitter", "FC": "Cutter", "SI": "Sinker",
              "FF": "Four-seam", "FA": "Four-seam"}


def _payload():
    if not PAYLOAD.exists():
        pytest.skip("data/pal.json not built on this machine")
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


def test_no_arm_is_told_to_add_a_pitch_he_already_throws():
    rows = _payload().get("pitch_add") or []
    bad = []
    for r in rows:
        add = (r.get("rec") or {}).get("add")
        have = {PITCH_NAME.get(a.get("pitch"), a.get("pitch"))
                for a in (r.get("arsenal") or [])
                if (a.get("usage") or 0) >= pc.PITCH_ADD_MIN_USAGE}
        if add and add in have:
            bad.append((r.get("name"), add, sorted(have)))
    assert not bad, (
        f"{len(bad)} row(s) recommend a pitch already thrown at "
        f"{pc.PITCH_ADD_MIN_USAGE:.0%} usage or more: {bad[:5]}"
    )


def test_the_deep_arsenal_branch_consults_the_arsenal():
    """Unit-level, so this holds with no payload on disk."""
    arm = pc.PalArm(
        mlbam=1, name="already throws it", p_throws="L",
        arsenal=[{"pitch": "FF", "usage": 0.40}, {"pitch": "SL", "usage": 0.25},
                 {"pitch": "CH", "usage": 0.20}, {"pitch": "FS", "usage": 0.15}],
        ops_vl=0.600, ops_vr=0.800,      # weak vs RHB, split 0.200 -> big_split
    )
    assert pc.recommend_pitch(arm) is None, (
        "an arm that already throws both offspeed candidates still gets an add "
        "recommendation, which is the defect this branch had"
    )
    # and one who throws neither gets the incumbent recommendation, unchanged
    arm2 = pc.PalArm(
        mlbam=2, name="has a hole", p_throws="L",
        arsenal=[{"pitch": "FF", "usage": 0.45}, {"pitch": "SL", "usage": 0.30},
                 {"pitch": "CU", "usage": 0.25}],
        ops_vl=0.600, ops_vr=0.800,
    )
    rec = pc.recommend_pitch(arm2)
    assert rec is not None and rec["add"] == "Changeup", rec


def test_the_watch_carries_the_efv_grade_the_card_reads():
    d = _payload()
    rows = (d.get("prospect_watch") or []) + (d.get("prospect_watch_all") or [])
    if not rows:
        pytest.skip("no prospect-watch rows on this build")
    n = sum(1 for r in rows if r.get("fvE") is not None)
    assert n, (
        "no watch row carries fvE, so assets/pal.js always falls back to the "
        "consensus close and its eFV branch is dead"
    )
    js = (HERE / "assets" / "pal.js").read_text(encoding="utf-8")
    assert "p.fvE" in js, "the card no longer reads fvE at all"


def test_no_role_stated_is_not_the_same_as_swingman():
    assert pc.prospect_role_fit({"fb": 60, "cmd": 50}, "RHP")["role"] == "UNSTATED"
    assert pc.prospect_role_fit({"fb": 60, "cmd": 50}, "LHP")["role"] == "UNSTATED"
    assert pc.prospect_role_fit({"fb": 60, "cmd": 50}, "P")["role"] == "UNSTATED"
    assert pc.prospect_role_fit({"fb": 60, "cmd": 50}, None)["role"] == "UNSTATED"
    # the roles that DO carry information are unmoved
    assert pc.prospect_role_fit({"fb": 60, "cmd": 50}, "SP")["role"] == "SP"
    assert pc.prospect_role_fit({"fb": 60, "cmd": 50}, "SIRP")["role"] == "RP"
    assert pc.prospect_role_fit({"fb": 60, "cmd": 50}, "MIRP")["role"] == "RP"
    assert pc.prospect_role_fit({"fb": 60, "cmd": 50}, "CL")["role"] == "RP"


def test_an_unstated_role_still_cannot_be_a_mismatch():
    """The EXCLUSION was always right and must not change. Only its name did."""
    thin = {"fb": 60, "sl": 55, "cmd": 40}          # profiles as a reliever
    assert pc.prospect_role_fit(thin, "SP")["mismatch"] is True
    assert pc.prospect_role_fit(thin, "RHP")["mismatch"] is False
    assert pc.prospect_role_fit(thin, "RHP")["mismatch_margin"] is None


def test_the_page_discloses_who_it_could_not_screen():
    d = _payload()
    rule = d.get("prospect_watch_rule") or {}
    if rule.get("n_pool") is None:
        pytest.skip("payload predates the coverage block")
    assert rule.get("n_role_unstated") is not None
    assert rule["n_role_unstated"] <= rule["n_pool"]
    js = (HERE / "assets" / "pal.js").read_text(encoding="utf-8")
    assert "n_role_unstated" in js, (
        f"{rule['n_role_unstated']} of {rule['n_pool']} pool pitchers cannot reach "
        f"this list and the page does not say so"
    )


def test_a_row_that_is_both_reverse_and_extreme_shows_both():
    js = (HERE / "assets" / "pal.js").read_text(encoding="utf-8")
    assert "r.reverse && r.extreme" in js, (
        "the platoon read is a bare ternary on `reverse` again, so a row carrying "
        "both flags shows only the favourable one"
    )
    rows = _payload().get("reverse_platoon") or []
    both = [r for r in rows
            if r.get("reverse") and r.get("extreme")
            and (r.get("min_tbf") is None or r["min_tbf"] >= 100)]
    if not both:
        pytest.skip("no dual-flag rows on this build")
    assert len(both) > 0


def test_no_served_watch_row_prints_the_efv_floor_as_a_level():
    """M07-02 (2026-09-24). A watch row whose eFV grade is the outcome map's floor
    (data/xfv.json xfv_grade_is_floor) must carry fvE_is_floor, or the card prints
    the bottom of the scale as a resolved grade. 12 of 140 rows on the 2026-09-23
    build, 6 of 60 on the staged list."""
    d = _payload()
    xp = HERE / "data" / "xfv.json"
    if not xp.exists():
        pytest.skip("data/xfv.json not built on this machine")
    by = json.loads(xp.read_text(encoding="utf-8")).get("by_player") or {}
    rows = (d.get("prospect_watch") or []) + (d.get("prospect_watch_all") or [])
    if not rows:
        pytest.skip("no prospect-watch rows on this build")
    bad = [r.get("name") for r in rows
           if r.get("fvE") is not None
           and (by.get(r.get("player_key")) or {}).get("xfv_grade_is_floor") is True
           and r.get("fvE_is_floor") is not True]
    assert not bad, f"floor eFV served without the floor flag: {bad[:6]}"
