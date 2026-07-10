# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""v6 spotlight overhaul — covers:

  * Tighter age cap (+1.5y hitter / +2.0y pitcher) drops marginal
    AAA journeymen that the +2.0/+3.0 v5 cap let through.
  * Sub-AAA level boost (A/A+ +1.5, AA +1.0, AAA +0.5, MLB 0)
    surfaces lower-level prospects above marginal upper-level ones.
  * Faller FV ≥ 45 hard floor — <45 org-fillers can't surface.
  * Faller FV multiplier — high-FV declines outweigh low-FV ones
    at the same perf delta.
  * Bayesian FV-prior rebound scoring — higher-FV prospects pull
    above lower-FV ones at the same observed bump.
  * RP rebounder gate (SIRP / MIRP must be age < 23 to rebound).
  * `_pitcher_role` helper classifies SP / RP / None correctly.
"""

from __future__ import annotations

import unittest

from spotlights import (
    _AGE_CAP_HITTER,
    _AGE_CAP_PITCHER,
    _LEVEL_TIER_BOOST,
    _exceeds_age_cap,
    _faller_fv_multiplier,
    _fv_rebound_prior,
    _level_score_boost,
    _pitcher_role,
    _player_consensus_fv,
    build_spotlights,
)


# ---------------------------------------------------------------------------
# Constants — pin the v6 thresholds
# ---------------------------------------------------------------------------

class TestV6Constants(unittest.TestCase):
    def test_hitter_age_cap_tightened_to_1_5(self):
        self.assertEqual(_AGE_CAP_HITTER, 1.5)

    def test_pitcher_age_cap_tightened_to_2_0(self):
        self.assertEqual(_AGE_CAP_PITCHER, 2.0)

    def test_level_tier_boost_table(self):
        self.assertEqual(_LEVEL_TIER_BOOST["A"], 1.5)
        self.assertEqual(_LEVEL_TIER_BOOST["A+"], 1.5)
        self.assertEqual(_LEVEL_TIER_BOOST["AA"], 1.0)
        self.assertEqual(_LEVEL_TIER_BOOST["AAA"], 0.5)
        self.assertEqual(_LEVEL_TIER_BOOST["MLB"], 0.0)


# ---------------------------------------------------------------------------
# Age cap — v6 tightened thresholds
# ---------------------------------------------------------------------------

class TestAgeCap(unittest.TestCase):
    def test_24_5_yo_hitter_at_aaa_is_now_capped(self):
        # AAA baseline 24.0, diff +0.5 — was passing under v5 (cap +2.0),
        # still passes under v6 (cap +1.5).
        self.assertFalse(_exceeds_age_cap(24.5, "AAA", is_pitcher=False))

    def test_25_5_yo_hitter_at_aaa_is_capped(self):
        # diff +1.5 — exactly at the new cap, INCLUSIVE → cut.
        self.assertTrue(_exceeds_age_cap(25.5, "AAA", is_pitcher=False))

    def test_26_yo_pitcher_at_aaa_is_capped(self):
        # diff +2.0 — exactly at the new pitcher cap, INCLUSIVE → cut.
        self.assertTrue(_exceeds_age_cap(26.0, "AAA", is_pitcher=True))

    def test_25_yo_pitcher_at_aaa_passes(self):
        # diff +1.0 — under the new pitcher cap of +2.0.
        self.assertFalse(_exceeds_age_cap(25.0, "AAA", is_pitcher=True))

    def test_rookie_level_passes_through(self):
        # DSL / CPX / ROK have no baseline → cap never fires.
        self.assertFalse(_exceeds_age_cap(28.0, "DSL", is_pitcher=False))
        self.assertFalse(_exceeds_age_cap(28.0, "CPX", is_pitcher=True))

    def test_missing_age_passes_through(self):
        self.assertFalse(_exceeds_age_cap(None, "AAA", is_pitcher=False))


# ---------------------------------------------------------------------------
# Level boost helper
# ---------------------------------------------------------------------------

class TestLevelScoreBoost(unittest.TestCase):
    def test_a_and_a_plus_get_top_boost(self):
        self.assertEqual(_level_score_boost("A"), 1.5)
        self.assertEqual(_level_score_boost("A+"), 1.5)

    def test_aa_gets_middle_boost(self):
        self.assertEqual(_level_score_boost("AA"), 1.0)

    def test_aaa_gets_small_boost(self):
        self.assertEqual(_level_score_boost("AAA"), 0.5)

    def test_mlb_gets_zero(self):
        self.assertEqual(_level_score_boost("MLB"), 0.0)

    def test_unknown_level_returns_zero(self):
        self.assertEqual(_level_score_boost("DSL"), 0.0)
        self.assertEqual(_level_score_boost(None), 0.0)


# ---------------------------------------------------------------------------
# Pitcher role classification (Part 1)
# ---------------------------------------------------------------------------

class TestPitcherRole(unittest.TestCase):
    def test_sp_classified_as_sp(self):
        self.assertEqual(_pitcher_role("SP"), "SP")

    def test_sirp_classified_as_rp(self):
        self.assertEqual(_pitcher_role("SIRP"), "RP")

    def test_mirp_classified_as_rp(self):
        self.assertEqual(_pitcher_role("MIRP"), "RP")

    def test_bare_rp_classified_as_rp(self):
        self.assertEqual(_pitcher_role("RP"), "RP")

    def test_rhp_returns_none(self):
        # Role-agnostic — RHP doesn't tell us starter vs reliever.
        self.assertIsNone(_pitcher_role("RHP"))

    def test_lhp_returns_none(self):
        self.assertIsNone(_pitcher_role("LHP"))

    def test_bare_p_returns_none(self):
        self.assertIsNone(_pitcher_role("P"))

    def test_none_input_returns_none(self):
        self.assertIsNone(_pitcher_role(None))
        self.assertIsNone(_pitcher_role(""))

    def test_compound_position_uses_first_token(self):
        # 'SP/RP' → SP (primary listed first).
        self.assertEqual(_pitcher_role("SP/RP"), "SP")
        self.assertEqual(_pitcher_role("SIRP/MIRP"), "RP")


# ---------------------------------------------------------------------------
# Bayesian FV-prior helper
# ---------------------------------------------------------------------------

class TestFvReboundPrior(unittest.TestCase):
    def test_fv_40_is_zero_prior(self):
        self.assertEqual(_fv_rebound_prior(40.0), 0.0)

    def test_fv_45_is_quarter_prior(self):
        # Piecewise linear: 40→0, 50→0.5. FV 45 sits at the midpoint → 0.25.
        self.assertAlmostEqual(_fv_rebound_prior(45.0), 0.25, places=2)

    def test_fv_50_is_neutral_prior(self):
        self.assertAlmostEqual(_fv_rebound_prior(50.0), 0.5, places=2)

    def test_fv_55_is_three_quarters(self):
        self.assertAlmostEqual(_fv_rebound_prior(55.0), 0.75, places=2)

    def test_fv_60_is_full_prior(self):
        self.assertEqual(_fv_rebound_prior(60.0), 1.0)

    def test_fv_70_saturates_at_1(self):
        self.assertEqual(_fv_rebound_prior(70.0), 1.0)

    def test_fv_below_40_is_zero(self):
        self.assertEqual(_fv_rebound_prior(35.0), 0.0)

    def test_none_returns_zero(self):
        self.assertEqual(_fv_rebound_prior(None), 0.0)


# ---------------------------------------------------------------------------
# Faller FV multiplier
# ---------------------------------------------------------------------------

class TestFallerFvMultiplier(unittest.TestCase):
    def test_fv_60_doubles_decline(self):
        self.assertEqual(_faller_fv_multiplier(60.0), 2.0)
        self.assertEqual(_faller_fv_multiplier(65.0), 2.0)

    def test_fv_55_one_and_a_half(self):
        self.assertEqual(_faller_fv_multiplier(55.0), 1.5)

    def test_fv_50_one_and_a_quarter(self):
        self.assertEqual(_faller_fv_multiplier(50.0), 1.25)

    def test_fv_45_baseline(self):
        self.assertEqual(_faller_fv_multiplier(45.0), 1.0)

    def test_below_threshold_still_one(self):
        # Below 45 the floor gate stops the player from reaching the
        # multiplier; but defensively the multiplier returns 1.0.
        self.assertEqual(_faller_fv_multiplier(40.0), 1.0)


# ---------------------------------------------------------------------------
# _player_consensus_fv helper
# ---------------------------------------------------------------------------

class TestPlayerConsensusFv(unittest.TestCase):
    def test_resolves_from_consensus_fv_raw(self):
        p = {"points": [{"consensus_fv_raw": 55.0}]}
        self.assertEqual(_player_consensus_fv(p), 55.0)

    def test_prefers_consensus_fv_over_raw(self):
        p = {"points": [{"consensus_fv": 60.0, "consensus_fv_raw": 55.0}]}
        self.assertEqual(_player_consensus_fv(p), 60.0)

    def test_uses_latest_snapshot(self):
        p = {"points": [
            {"consensus_fv_raw": 40.0},
            {"consensus_fv_raw": 55.0},   # latest
        ]}
        self.assertEqual(_player_consensus_fv(p), 55.0)

    def test_returns_none_for_missing(self):
        self.assertIsNone(_player_consensus_fv({"points": []}))
        self.assertIsNone(_player_consensus_fv({}))


# ---------------------------------------------------------------------------
# End-to-end through build_spotlights — RP rebounder gate + FV floor + Bayes
# ---------------------------------------------------------------------------

def _hitter(*, key, name, fv=45.0, ops=".900", prior_ops=".650",
            age=20.0, level="AA"):
    return {
        "player_key": key,
        "player_name": name,
        "position": "SS",
        "org": "ARI",
        "age": age,
        "overall_rank": 100,
        "fv_low": 40.0,
        "age_vs_level": {"tier": "young", "diff": -1.5},
        "points": [
            {"snapshot_date": "2025-02-01", "consensus_fv_raw": 40.0,
             "consensus_fv_label": "40"},
            {"snapshot_date": "2026-05-01", "consensus_fv_raw": fv,
             "consensus_fv_label": str(int(fv)), "consensus_fv": fv},
        ],
        "statline": {
            "level": level, "season": 2026, "is_pitcher": False,
            "is_prior_season": False, "ops": ops, "ab": 120,
            "bb_pct": 11.0, "k_pct": 17.0,
        },
        "career_stats": [
            {"season": 2026, "level": level, "ab": 120, "ops": ops,
             "is_pitcher": False},
            {"season": 2025, "level": "A+", "ab": 220, "ops": prior_ops,
             "is_pitcher": False},
        ],
        "acquisition": {"method": "draft", "pick_overall": 15,
                        "bonus_usd": 4_000_000},
        "statcast": None,
        "pitch_arsenal": None,
    }


def _hitter_faller(*, key, name, fv=50.0, age=22.0, level="AA"):
    """Configured to be classified as a faller — current OPS .550,
    prior OPS .750 → big drop."""
    return {
        "player_key": key,
        "player_name": name,
        "position": "SS",
        "org": "ARI",
        "age": age,
        "overall_rank": 100,
        "fv_low": 40.0,
        "age_vs_level": {"tier": "neutral", "diff": 0.0},
        "points": [
            {"snapshot_date": "2025-02-01", "consensus_fv_raw": 45.0,
             "consensus_fv_label": "45"},
            {"snapshot_date": "2026-05-01", "consensus_fv_raw": fv,
             "consensus_fv_label": str(int(fv)), "consensus_fv": fv},
        ],
        "statline": {
            "level": level, "season": 2026, "is_pitcher": False,
            "is_prior_season": False, "ops": ".550", "ab": 150,
            "bb_pct": 8.0, "k_pct": 28.0,
        },
        "career_stats": [
            {"season": 2026, "level": level, "ab": 150, "ops": ".550",
             "is_pitcher": False, "k_pct": 28.0},
            {"season": 2025, "level": level, "ab": 220, "ops": ".750",
             "is_pitcher": False, "k_pct": 22.0},
        ],
        "acquisition": {"method": "draft", "pick_overall": 12,
                        "bonus_usd": 5_000_000},
        "statcast": None,
        "pitch_arsenal": None,
    }


class TestFallerFvFloor(unittest.TestCase):
    def test_fv_40_player_cannot_be_faller(self):
        p = _hitter_faller(key="bad_low", name="Bad LowFv", fv=40.0, age=22.0)
        out = build_spotlights([p], [])
        names = [x["player_name"] for x in out["fallers"]]
        self.assertNotIn("Bad LowFv", names)

    def test_fv_45_player_qualifies_as_faller(self):
        p = _hitter_faller(key="real_45", name="Real Faller", fv=45.0, age=22.0)
        out = build_spotlights([p], [])
        names = [x["player_name"] for x in out["fallers"]]
        self.assertIn("Real Faller", names)


class TestFallerFvWeighting(unittest.TestCase):
    def test_fv_60_decline_outranks_fv_45_at_same_perf_delta(self):
        # Two fallers, identical perf delta, only FV differs.
        # Use unique keys + names so they're separately ranked.
        p45 = _hitter_faller(key="f45", name="Faller Forty Five", fv=45.0,
                             age=22.0)
        p60 = _hitter_faller(key="f60", name="Faller Sixty",      fv=60.0,
                             age=22.0)
        out = build_spotlights([p45, p60], [])
        names = [x["player_name"] for x in out["fallers"]]
        # Both should appear, AND the FV-60 faller should rank higher
        # (more-negative score) than FV-45.
        self.assertIn("Faller Forty Five", names)
        self.assertIn("Faller Sixty", names)
        idx_60 = names.index("Faller Sixty")
        idx_45 = names.index("Faller Forty Five")
        self.assertLess(idx_60, idx_45,
                        "FV-60 decline should rank ABOVE FV-45 at same perf")


class TestRebounderBayesian(unittest.TestCase):
    def test_higher_fv_rebound_outranks_lower_fv_at_same_observed_bump(self):
        # Two prospect-comeback narratives, identical perf bump + skills,
        # different FV. The FV-55 one should outscore the FV-45 one via
        # the Bayesian prior weighting.
        low  = _hitter(key="lo_fv", name="Comeback Forty Five",
                       fv=45.0, ops=".900", prior_ops=".650")
        high = _hitter(key="hi_fv", name="Comeback Fifty Five",
                       fv=55.0, ops=".900", prior_ops=".650")
        out = build_spotlights([low, high], [])
        rebs = out["rebounders"]
        names = [x["player_name"] for x in rebs]
        self.assertIn("Comeback Forty Five", names)
        self.assertIn("Comeback Fifty Five", names)
        idx_high = names.index("Comeback Fifty Five")
        idx_low  = names.index("Comeback Forty Five")
        self.assertLess(idx_high, idx_low,
                        "Higher-FV rebound should outrank lower-FV at same bump")


# ---------------------------------------------------------------------------
# RP rebounder gate
# ---------------------------------------------------------------------------

def _pitcher_rebounder(*, key, name, position, age):
    return {
        "player_key": key,
        "player_name": name,
        "position": position,
        "org": "ARI",
        "age": age,
        "overall_rank": 80,
        "fv_low": 40.0,
        "age_vs_level": {"tier": "young", "diff": -0.5},
        "points": [
            {"snapshot_date": "2025-02-01", "consensus_fv_raw": 45.0,
             "consensus_fv_label": "45"},
            {"snapshot_date": "2026-05-01", "consensus_fv_raw": 50.0,
             "consensus_fv_label": "50", "consensus_fv": 50.0},
        ],
        "statline": {
            "level": "AA", "season": 2026, "is_pitcher": True,
            "is_prior_season": False, "era": "2.80", "ip": "40.0",
            "k_pct": 28.0, "bb_pct": 7.0,
        },
        "career_stats": [
            {"season": 2026, "level": "AA", "ip": "40.0", "era": "2.80",
             "is_pitcher": True, "k_pct": 28.0, "bb_pct": 7.0},
            {"season": 2025, "level": "A+", "ip": "55.0", "era": "5.10",
             "is_pitcher": True, "k_pct": 22.0, "bb_pct": 11.0},
        ],
        "acquisition": {"method": "draft", "pick_overall": 60,
                        "bonus_usd": 1_500_000},
        "statcast": None,
        "pitch_arsenal": None,
    }


class TestSharedBucketFilters(unittest.TestCase):
    """v6.1 — the RP age<23 gate + FV >= 45 floor now apply to ALL
    THREE buckets uniformly (was rebound-only / faller-only)."""

    def test_old_sirp_excluded_from_risers(self):
        # 25yo SIRP with dominant current performance — should NOT
        # appear as a riser under v6.1 (RPs gated everywhere, not just
        # in rebound).
        p = _pitcher_rebounder(key="old_sirp_riser", name="Old Sirp Riser",
                               position="SIRP", age=25.0)
        # Pump current ERA way down to force a riser-shape profile
        p["statline"]["era"] = "1.20"
        p["career_stats"][0]["era"] = "1.20"
        out = build_spotlights([p], [])
        riser_names = [x["player_name"] for x in out["risers"]]
        self.assertNotIn("Old Sirp Riser", riser_names)

    def test_low_fv_cannot_be_riser(self):
        # FV 40 hitter with a huge OPS jump — used to surface as a riser
        # (org-fillers were allowed). v6.1 floor of 45 drops them.
        p = _hitter(key="fv_40_riser", name="Forty Fv Riser",
                    fv=40.0, ops=".950", prior_ops=".600")
        out = build_spotlights([p], [])
        names = [x["player_name"] for x in out["risers"]]
        self.assertNotIn("Forty Fv Riser", names)

    def test_low_fv_cannot_be_rebounder(self):
        # FV 40 pedigreed-comeback profile — dropped by the shared
        # FV floor.
        p = _hitter(key="fv_40_reb", name="Forty Fv Reb",
                    fv=40.0, ops=".900", prior_ops=".650")
        out = build_spotlights([p], [])
        names = [x["player_name"] for x in out["rebounders"]]
        self.assertNotIn("Forty Fv Reb", names)


class TestRPRebounderGate(unittest.TestCase):
    def test_24yo_sirp_does_not_rebound(self):
        # SIRP at 24 — exceeds the shared RP cap (< 23). Should NOT
        # appear as a rebounder even with the textbook comeback profile.
        p = _pitcher_rebounder(key="old_sirp", name="Old Sirp",
                               position="SIRP", age=24.0)
        out = build_spotlights([p], [])
        names = [x["player_name"] for x in out["rebounders"]]
        self.assertNotIn("Old Sirp", names)

    def test_22yo_sirp_can_rebound(self):
        # SIRP at 22 — under the RP cap, comeback profile fires.
        p = _pitcher_rebounder(key="young_sirp", name="Young Sirp",
                               position="SIRP", age=22.0)
        out = build_spotlights([p], [])
        names = [x["player_name"] for x in out["rebounders"]]
        self.assertIn("Young Sirp", names)

    def test_24yo_mirp_does_not_rebound(self):
        p = _pitcher_rebounder(key="old_mirp", name="Old Mirp",
                               position="MIRP", age=24.0)
        out = build_spotlights([p], [])
        names = [x["player_name"] for x in out["rebounders"]]
        self.assertNotIn("Old Mirp", names)

    def test_24yo_sp_still_rebounds_under_25_cap(self):
        # SP at 24 — under the SP/hitter cap (< 25). SHOULD appear as
        # rebounder.
        p = _pitcher_rebounder(key="old_sp", name="Old Sp",
                               position="SP", age=24.0)
        out = build_spotlights([p], [])
        names = [x["player_name"] for x in out["rebounders"]]
        self.assertIn("Old Sp", names)


if __name__ == "__main__":
    unittest.main()
