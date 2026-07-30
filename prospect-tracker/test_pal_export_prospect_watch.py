# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for pal_export.build_prospect_watch - the /pal/ prospect
conversion-watch builder.

The load-bearing property for the prospx cross-link (finding [34]): every watch
entry must carry `player_key` so the pitcher-card chip can join the PAL
role-conversion read back onto the prospect board by the canonical key. Also
guards the FV floor, the mismatch gate, the FV-desc ordering, and the cap.
"""
from __future__ import annotations

import pal_export


# thin SP-labeled arsenal + poor command -> profiles RP -> mismatch (kept)
_THIN_SP = {"player_key": "thin-sp-1", "name": "Thin SP", "org": "LAD",
            "position": "SP", "fv": 50, "tools": {"fb": 60, "sl": 55, "cmd": 40}}
# deep + command RP-labeled -> could start -> mismatch (kept)
_DEEP_RP = {"player_key": "deep-rp-1", "name": "Deep RP", "org": "SD",
            "position": "RP", "fv": 45,
            "tools": {"fb": 60, "sl": 60, "cb": 55, "ch": 55, "cmd": 60}}
# deep + command SP-labeled -> aligned -> NOT a mismatch (dropped)
_ALIGNED = {"player_key": "aligned-1", "name": "Deep SP", "org": "NYY",
            "position": "SP", "fv": 55,
            "tools": {"fb": 60, "sl": 60, "cb": 55, "ch": 55, "cmd": 60}}
# mismatch but below the FV floor (dropped)
_LOW_FV = {"player_key": "lowfv-1", "name": "Low FV", "org": "TB",
           "position": "SP", "fv": 35, "tools": {"fb": 60, "sl": 55, "cmd": 40}}


def test_prospect_watch_carries_player_key_join():
    watch = pal_export.build_prospect_watch([_THIN_SP, _ALIGNED, _DEEP_RP, _LOW_FV])
    keys = {w["player_key"] for w in watch}
    assert "thin-sp-1" in keys            # SP that profiles RP
    assert "deep-rp-1" in keys            # RP that could start
    assert "aligned-1" not in keys        # not a mismatch
    assert "lowfv-1" not in keys          # below the FV >= 40 floor
    # every kept entry carries the join key + the role-fit fields prospx renders
    for w in watch:
        assert "player_key" in w and w["player_key"]
        assert w["role"] in ("SP", "RP", "SWING")
        assert w["lean"] in ("SP", "RP", "SWING")
        assert w["mismatch"] is True
        assert w["starter_shape"] is not None


def test_prospect_watch_ranked_by_severity_then_fv_and_capped():
    # 2026-07-30 owner decision: the watch is STAGED, so it ranks by mismatch
    # SEVERITY (shape points past the swing band) and only uses FV as the tiebreak.
    # Deep RP is shape 100 -> 40 points past the SP boundary; Thin SP is shape 27 ->
    # 13 points past the RP boundary. Severity therefore puts Deep RP first even
    # though Thin SP carries the higher FV. This deliberately replaces the old
    # FV-desc pin.
    watch = pal_export.build_prospect_watch([_THIN_SP, _DEEP_RP])
    assert [w["player_key"] for w in watch] == ["deep-rp-1", "thin-sp-1"]
    margins = [w["mismatch_margin"] for w in watch]
    assert margins == sorted(margins, reverse=True)
    assert len(pal_export.build_prospect_watch([_DEEP_RP, _THIN_SP], cap=1)) == 1


def test_prospect_watch_severity_threshold_stages_the_list():
    # A mismatch INSIDE the margin is held off the staged list but kept in the
    # unbounded set, which is what the prospx card chip joins against. This is the
    # "do not silently truncate" property.
    # shape 37.0 -> leans RP, but only 3.0 points past the boundary
    marginal = {"player_key": "marginal-1", "name": "Marginal", "org": "SEA",
                "position": "SP", "fv": 50, "tools": {"fb": 60, "sl": 60, "cmd": 45}}
    rf = __import__("pal_conversion").prospect_role_fit(marginal["tools"], "SP")
    assert rf["mismatch"] is True and 0 < rf["mismatch_margin"] < pal_export.PROSPECT_WATCH_MARGIN_MIN

    pool = [_THIN_SP, _DEEP_RP, marginal]
    staged = pal_export.build_prospect_watch(pool)
    full = pal_export.build_prospect_watch_all(pool)
    assert "marginal-1" not in {w["player_key"] for w in staged}
    assert "marginal-1" in {w["player_key"] for w in full}

    rule = pal_export.prospect_watch_rule(full, staged)
    assert rule["n_mismatches"] == 3
    assert rule["n_qualified"] == 2
    assert rule["n_shown"] == 2
    assert rule["n_below_margin"] == 1
    assert rule["cap_binding"] is False
    # every bound the copy states has to be readable off the payload
    for k in ("fv_min", "margin_min", "cap", "n_mismatches", "n_qualified", "n_shown",
              "n_below_margin", "n_over_cap", "best_margin_below_threshold"):
        assert k in rule


def test_prospect_watch_cap_is_reported_when_it_binds():
    pool = [_THIN_SP, _DEEP_RP]
    staged = pal_export.build_prospect_watch(pool, cap=1)
    rule = pal_export.prospect_watch_rule(pool and pal_export.build_prospect_watch_all(pool),
                                          staged, cap=1)
    assert rule["cap_binding"] is True
    assert rule["n_over_cap"] == 1


def test_prospect_watch_tolerates_missing_player_key():
    # a mismatch prospect with no player_key is still kept (chip degrades to a
    # name+org join client-side), not dropped or crashing the export.
    no_key = dict(_THIN_SP)
    no_key.pop("player_key")
    watch = pal_export.build_prospect_watch([no_key])
    assert len(watch) == 1
    assert watch[0]["player_key"] is None
    assert watch[0]["name"] == "Thin SP"
