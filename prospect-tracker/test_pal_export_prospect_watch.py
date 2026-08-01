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


def test_prospect_watch_sorted_by_fv_desc_and_capped():
    watch = pal_export.build_prospect_watch([_DEEP_RP, _THIN_SP])
    fvs = [w.get("fv") or 0 for w in watch]
    assert fvs == sorted(fvs, reverse=True)      # Thin SP (50) before Deep RP (45)
    assert len(pal_export.build_prospect_watch([_DEEP_RP, _THIN_SP], cap=1)) == 1


def test_prospect_watch_tolerates_missing_player_key():
    # a mismatch prospect with no player_key is still kept (chip degrades to a
    # name+org join client-side), not dropped or crashing the export.
    no_key = dict(_THIN_SP)
    no_key.pop("player_key")
    watch = pal_export.build_prospect_watch([no_key])
    assert len(watch) == 1
    assert watch[0]["player_key"] is None
    assert watch[0]["name"] == "Thin SP"
