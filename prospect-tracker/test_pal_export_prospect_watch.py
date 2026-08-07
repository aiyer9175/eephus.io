# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for the pal_export RULE BLOCKS - the bounds data/pal.json stamps
into itself so the /pal/ copy can never state a threshold the export is not
applying. Two of them live here: prospect_watch_rule and tier_rule.

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


def test_severity_cuts_are_quarters_of_the_swing_band_and_never_below_the_floor():
    """Severity is the band read in quarters, not a fitted scale: full / three
    quarters / half of pal_conversion.SHAPE_SWING_BAND. The bottom band is
    clamped to the listing floor, because a band advertising a cut BELOW the
    threshold that decides what gets listed would describe rows that are not on
    the page."""
    import pal_conversion as pc
    band = pc.SHAPE_SWING_BAND
    cuts = pal_export.prospect_watch_severity_cuts()
    assert [c["key"] for c in cuts] == ["severe", "marked", "modest"]
    assert [c["min_margin"] for c in cuts] == [band, band * 0.75, band * 0.5]
    # biggest first, so the first band a margin clears is the right one
    mins = [c["min_margin"] for c in cuts]
    assert mins == sorted(mins, reverse=True)
    # a floor above the structural half-band must win, or the band would name
    # rows the staging has already dropped
    raised = pal_export.prospect_watch_severity_cuts(margin_min=12.0)
    assert raised[-1]["min_margin"] == 12.0


def test_prospect_watch_rule_publishes_severity_counts_that_add_up():
    pool = [_THIN_SP, _DEEP_RP]
    staged = pal_export.build_prospect_watch(pool)
    rule = pal_export.prospect_watch_rule(pal_export.build_prospect_watch_all(pool), staged)
    assert rule["swing_band"] == 20.0
    cuts = rule["severity_cuts"]
    # Deep RP is 40 points past its boundary (severe), Thin SP is 13 (modest).
    by_key = {c["key"]: c["n"] for c in cuts}
    assert by_key == {"severe": 1, "marked": 0, "modest": 1}
    assert sum(by_key.values()) == rule["n_shown"]


def test_prospect_watch_tolerates_missing_player_key():
    # a mismatch prospect with no player_key is still kept (chip degrades to a
    # name+org join client-side), not dropped or crashing the export.
    no_key = dict(_THIN_SP)
    no_key.pop("player_key")
    watch = pal_export.build_prospect_watch([no_key])
    assert len(watch) == 1
    assert watch[0]["player_key"] is None
    assert watch[0]["name"] == "Thin SP"


# ---------------------------------------------------------------------------
# tier_rule: the candidate TIER cuts, per direction, stamped into the payload.
#
# The bug this replaces: one shared set of cuts (70/55/42) for two scores that
# are not on the same scale. sp_rp_fit multiplies relief upside by a
# conversion-need factor, so its pool tops out near 60 and the advertised
# "Bullpen Upside (70+)" tier had ZERO members in every build while three
# quarters of the board sat in the bottom tier.
# ---------------------------------------------------------------------------

def _rows(*fits, successful=False):
    return [{"fit": f, "successful": successful} for f in fits]


def test_tier_cuts_differ_by_direction_and_are_absolute():
    assert pal_export.TIER_CUTS["rp2sp"] == (70.0, 55.0, 42.0)
    assert pal_export.TIER_CUTS["sp2rp"] == (55.0, 45.0, 35.0)
    for cuts in pal_export.TIER_CUTS.values():
        assert list(cuts) == sorted(cuts, reverse=True)


def test_sp2rp_top_tier_is_reachable_on_its_own_scale():
    """The whole point of the per-direction cuts. A tier system whose top tier
    cannot be reached is decoration, so this pins the cut BELOW the compressed
    scale's ceiling rather than pinning any particular membership count."""
    rule = pal_export.tier_rule(_rows(62.8, 55.1, 48.0, 38.0, 4.1), "sp2rp")
    assert rule["tiers"][0]["min_fit"] < rule["fit_max"]
    assert [t["n"] for t in rule["tiers"]] == [2, 1, 1, 1]
    assert sum(t["n"] for t in rule["tiers"]) == rule["n_rows"]
    # the bands must PARTITION: a row belongs to exactly one tier, so a value
    # sitting on a cut goes up, never into both
    edge = pal_export.tier_rule(_rows(55.0, 45.0, 35.0), "sp2rp")
    assert [t["n"] for t in edge["tiers"]] == [1, 1, 1, 0]


def test_tier_rule_reports_the_live_scale_so_the_legend_can_state_it():
    rule = pal_export.tier_rule(_rows(4.1, 33.2, 62.8), "sp2rp")
    assert (rule["fit_min"], rule["fit_median"], rule["fit_max"]) == (4.1, 33.2, 62.8)


def test_only_rp2sp_carries_the_premium_top_tier_variant():
    """A reliever who is already succeeding AND profiles as a starter is the
    value-additive case. SP->RP has no such split, and inventing one would
    imply a ranking that direction's backtest does not support."""
    hot = pal_export.tier_rule(_rows(90.0, 80.0, successful=True), "rp2sp")
    assert hot["tiers"][0]["premium_label"] == "Prime Starter Convert"
    assert hot["tiers"][0]["n_premium"] == 2
    cold = pal_export.tier_rule(_rows(90.0, 80.0), "rp2sp")
    assert cold["tiers"][0]["n_premium"] == 0
    assert "premium_label" not in pal_export.tier_rule(_rows(60.0), "sp2rp")["tiers"][0]


def test_tier_names_stay_screen_language_on_the_unvalidated_direction():
    """RP->SP's backtest is SIGN-WRONG (rho -0.17 at n=35, a closed no-ship), so
    its tier names describe a profile and must never imply a predictive rank.
    This is a copy invariant, not a modelling one, and it is easy to break by
    reaching for punchier labels."""
    labels = " ".join(pal_export.TIER_LABELS["rp2sp"]
                      + (pal_export.TIER_PREMIUM["rp2sp"][0],)).lower()
    for banned in ("best", "top", "elite", "likely", "will ", "projected", "rank"):
        assert banned not in labels, banned


def test_tier_rule_survives_an_empty_direction():
    rule = pal_export.tier_rule([], "sp2rp")
    assert rule["n_rows"] == 0 and rule["fit_max"] is None
    assert all(t["n"] == 0 for t in rule["tiers"])
