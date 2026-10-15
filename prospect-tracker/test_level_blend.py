# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""B3 multi-level blend (docs/efv-2026-07-30/B3_LEVEL_BLEND_GATE.md).

The blend is DEFAULT OFF and ships only on its pre-registered gate, so the first
and most important thing to pin is that the default path did not move. The rest
pins the one design decision that is easy to get wrong: the reliability shrink is
applied ONCE on the season's TOTAL exposure, not once per level.

Offline: every test builds its own rate blocks. Nothing fetches.
"""
from __future__ import annotations

import efv_dataset as ed


def test_blend_is_default_off():
    """It rebuilds both matrices and moves the board, so it must never arrive by
    accident. Flipping either flag is a deliberate, gated act."""
    assert ed.LEVEL_BLEND_RATES is False
    assert ed.LEVEL_BLEND_ANCHOR_MOST_EXPOSED is False


def test_season_rates_shrink_flag_is_the_only_difference():
    """shrink=False must return the SAME deviations with the reliability weight
    left off, so the blend can re-apply it once on the total."""
    row = {"pa": 300.0, "so": 60.0, "bb": 30.0, "obp": 0.360, "slg": 0.480,
           "avg": 0.280, "ops": 0.840}
    norms = {"k_pct": 0.22, "bb_pct": 0.09, "iso": 0.150, "obp": 0.330, "ops": 0.720}
    shrunk = ed._season_rates(row, norms, "hit", shrink=True)
    raw = ed._season_rates(row, norms, "hit", shrink=False)
    w = 300.0 / (300.0 + ed._K_REL_PA)
    for k in ("k_rel", "bb_rel", "iso_rel", "obp_rel", "ops_rel"):
        assert abs(shrunk[k] - w * raw[k]) < 1e-12, k
    assert shrunk["exposure"] == raw["exposure"] == 300.0


def test_shrink_is_applied_once_on_total_exposure():
    """The design claim. A season split 200 + 150 across two levels, both at the
    same level-relative quality, must land at the SAME rate as one 350-PA season of
    that quality -- not shrunk harder for having been split. Weighting per-level
    shrunk rates would fail this, which is why the blend takes raw deviations."""
    dev = {"k_rel": -0.04, "bb_rel": 0.03, "iso_rel": 0.05, "obp_rel": 0.04,
           "ops_rel": 0.09, "exposure": 0.0, "rates_missing": 0.0}
    per_level = [(200.0, dict(dev)), (150.0, dict(dev))]
    blended = ed._blend_level_rates(per_level, "hit")
    w_total = 350.0 / (350.0 + ed._K_REL_PA)
    for k in ("k_rel", "bb_rel", "iso_rel", "obp_rel", "ops_rel"):
        assert abs(blended[k] - w_total * dev[k]) < 1e-12, k
    assert blended["exposure"] == 350.0


def test_blend_is_exposure_weighted_not_level_weighted():
    """A 378-PA line one rung down must dominate a 51-PA line above it. This is the
    measured defect: 22% of multi-level hitters are currently scored on the smaller
    side of their own season."""
    big = {"ops_rel": 0.20, "k_rel": 0.0, "bb_rel": 0.0, "iso_rel": 0.0, "obp_rel": 0.0}
    small = {"ops_rel": -0.20, "k_rel": 0.0, "bb_rel": 0.0, "iso_rel": 0.0, "obp_rel": 0.0}
    blended = ed._blend_level_rates([(51.0, small), (378.0, big)], "hit")
    # the weighted mean deviation leans to the 378-PA line
    mean_dev = (51.0 * -0.20 + 378.0 * 0.20) / 429.0
    w = 429.0 / (429.0 + ed._K_REL_PA)
    assert abs(blended["ops_rel"] - w * mean_dev) < 1e-12
    assert blended["ops_rel"] > 0, "the larger sample must set the sign"


def test_sub_threshold_levels_still_carry_weight_but_cannot_dominate():
    """A cameo is information, not noise to be gated away -- but it is 5% of a
    season, not 100% of it. This is the Arias shape: 332 PA at AA plus a 19-PA
    cameo above."""
    aa = {"ops_rel": 0.25, "k_rel": 0.0, "bb_rel": 0.0, "iso_rel": 0.0, "obp_rel": 0.0}
    aaa = {"ops_rel": -0.30, "k_rel": 0.0, "bb_rel": 0.0, "iso_rel": 0.0, "obp_rel": 0.0}
    blended = ed._blend_level_rates([(19.0, aaa), (332.0, aa)], "hit")
    assert blended["ops_rel"] > 0.15, "a 19-PA cameo must not erase a 332-PA season"
    single = ed._blend_level_rates([(332.0, aa)], "hit")
    assert blended["ops_rel"] < single["ops_rel"], (
        "but it must count for something, or it is not a blend")


def test_pitcher_side_uses_batters_faced_and_its_own_constant():
    dev = {"k_rel": 0.05, "bb_rel": -0.02, "era_rel": -0.60}
    blended = ed._blend_level_rates([(200.0, dict(dev)), (100.0, dict(dev))], "pit")
    w = 300.0 / (300.0 + ed._K_REL_BF)
    for k in ("k_rel", "bb_rel", "era_rel"):
        assert abs(blended[k] - w * dev[k]) < 1e-12, k
    assert blended["exposure"] == 300.0


def test_degenerate_inputs_do_not_raise():
    assert ed._blend_level_rates([], "hit") == {}
    only = ed._blend_level_rates([(0.0, {"ops_rel": 0.1})], "hit")
    assert only.get("ops_rel") == 0.1      # zero total exposure falls back, no divide


# ---------------------------------------------------------------------------
# the ANCHOR arm's cameo bound (amendment 2026-10-15, owner decision EW3-21)
# ---------------------------------------------------------------------------

def _season_store(monkeypatch, lines):
    """One synthetic 2024 season for player 1 (offline: the norms and the line adjusters
    are stubbed; nothing fetches)."""
    rows = [dict({"mlbam": 1, "season": 2024, "age": 21, "so": 20, "bb": 10, "obp": ".330",
                  "slg": ".420", "avg": ".260", "ops": ".750"}, **ln) for ln in lines]
    monkeypatch.setattr(ed.mh, "player_index",
                        lambda season, group, fetch=True: ({1: rows} if season == 2024 else {}))
    monkeypatch.setattr(ed, "_resolved_norms", lambda season, level, group: {
        "k_pct": 0.22, "bb_pct": 0.09, "iso": 0.150, "obp": 0.330, "ops": 0.720,
        "era": 4.5, "sb600": 20.0})
    monkeypatch.setattr(ed, "_xline", None)
    monkeypatch.setattr(ed, "_parkline", None)


def _level(monkeypatch, lines, side="hit", arm=False):
    _season_store(monkeypatch, lines)
    monkeypatch.setattr(ed, "LEVEL_BLEND_ANCHOR_MOST_EXPOSED", arm)
    f = ed._milb_features(1, 2025, "2003-01-01", side)
    return f["milb_level"], f["level_rank"]


def test_the_cameo_bound_is_twice_the_selection_floor():
    assert ed.LEVEL_ANCHOR_CAMEO_MULT == 2.0


def test_a_cameo_stint_re_keys_only_with_the_arm_on(monkeypatch):
    lines = [{"level": "AAA", "pa": 61}, {"level": "AA", "pa": 400}]
    assert _level(monkeypatch, lines) == ("AAA", 5.0), "the served path is unchanged"
    assert _level(monkeypatch, lines, arm=True) == ("AA", 4.0)
    edge = [{"level": "AAA", "pa": 99}, {"level": "AA", "pa": 400}]
    assert _level(monkeypatch, edge, arm=True)[0] == "AA"


def test_a_stint_at_twice_the_floor_keeps_the_highest_level(monkeypatch):
    lines = [{"level": "AAA", "pa": 100}, {"level": "AA", "pa": 400}]
    assert _level(monkeypatch, lines, arm=True) == ("AAA", 5.0)
    pit = [{"level": "AAA", "bf": 120, "ip": "28.0", "era": "4.00"},
           {"level": "AA", "bf": 400, "ip": "95.0", "era": "3.50"}]
    assert _level(monkeypatch, pit, side="pit", arm=True)[0] == "AAA"
    pit[0]["bf"] = 119
    assert _level(monkeypatch, pit, side="pit", arm=True)[0] == "AA"


def test_a_cameo_that_is_also_the_most_exposed_level_stays(monkeypatch):
    lines = [{"level": "AAA", "pa": 80}, {"level": "AA", "pa": 30}]
    assert _level(monkeypatch, lines, arm=True) == ("AAA", 5.0)
