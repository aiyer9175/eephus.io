# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The timeseries / debuts export binds contracts and career WAR to the mlbam id.

Spotrac contracts and the career_war table are keyed by name slug, and a slug
can name two people. Until 2026-09-25 storage.export_timeseries_json joined both
by slug, so:

  max_muncy (the ATH infielder, mlbam 691777) served the LAD Max Muncy's
  $10.0M contract (Spotrac 16719) instead of his own $684,044 (Spotrac 73287);
  jose_ramirez (802064, a CPX pitcher born 2004) served the CLE third baseman's
  $20.8M through 2032 and a 2014-2018 pitcher's WAR, which the export also
  back-filled into his roster_status mlb_seasons.

These cases drive the two resolvers the export calls, with two players sharing
a slug in each, plus a served-artifact check that skips when debuts.json is
absent.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import spotrac
import storage

DATA = Path(__file__).parent / "data"


def _row(slug, sid, team, pos, aav):
    return {"player_key": slug, "player_name": slug.replace("_", " ").title(),
            "spotrac_id": sid, "team_slug": spotrac._SPOTRAC_TEAM_SLUGS[team],
            "position": pos, "aav_usd": aav, "salary_usd": aav}


MUNCY_LAD = _row("max_muncy", "16719", "LAD", "1B", 10_000_000)
MUNCY_ATH = _row("max_muncy", "73287", "ATH", "3B", 684_044)
RAMIREZ_CLE = _row("jose_ramirez", "14106", "CLE", "3B", 20_800_000)


class TestSpotracKeepsBothRows(unittest.TestCase):
    def test_default_collapse_is_unchanged(self):
        out = spotrac.build_contracts_by_key([MUNCY_LAD, MUNCY_ATH])
        self.assertEqual(out["max_muncy"]["spotrac_id"], "16719")
        self.assertNotIn("same_slug_rows", out["max_muncy"])

    def test_keep_alts_carries_the_other_player(self):
        out = spotrac.build_contracts_by_key([MUNCY_ATH, MUNCY_LAD], keep_alts=True)
        self.assertEqual(out["max_muncy"]["spotrac_id"], "16719")
        self.assertEqual([r["spotrac_id"] for r in out["max_muncy"]["same_slug_rows"]],
                         ["73287"])
        self.assertNotIn("same_slug_rows", MUNCY_LAD)   # the input row is not mutated


class TestContractsJoinOnTheId(unittest.TestCase):
    def setUp(self):
        self.cbk = spotrac.build_contracts_by_key(
            [MUNCY_LAD, MUNCY_ATH, RAMIREZ_CLE], keep_alts=True)

    def test_two_max_muncys_each_get_their_own_contract(self):
        humans = {"max_muncy": (691777, "ATH", False)}
        rivals = [("max_muncy", 571970, "LAD", False)]
        out, rc = storage.resolve_contracts_to_ids(self.cbk, humans, rivals)
        self.assertEqual(out["max_muncy"]["spotrac_id"], "73287")
        self.assertEqual(out["max_muncy"]["aav_usd"], 684_044)
        self.assertNotIn("same_slug_rows", out["max_muncy"])
        self.assertEqual(rc["moved"], 1)

    def test_alone_on_the_slug_the_own_club_row_still_wins(self):
        # No /projections/ file: the ATH player is the only claimant of both rows
        # and keeps the one on his own club, not the higher AAV.
        out, _ = storage.resolve_contracts_to_ids(
            self.cbk, {"max_muncy": (691777, "ATH", False)}, [])
        self.assertEqual(out["max_muncy"]["spotrac_id"], "73287")

    def test_the_cpx_pitcher_does_not_take_the_third_basemans_deal(self):
        humans = {"jose_ramirez": (802064, "CLE", True)}
        rivals = [("jose_ramirez", 608070, "CLE", False)]
        out, rc = storage.resolve_contracts_to_ids(self.cbk, humans, rivals)
        self.assertIn("jose_ramirez", out)
        self.assertIsNone(out["jose_ramirez"])
        self.assertEqual(rc["dropped"], 1)

    def test_the_same_human_under_a_suffixed_projections_key_is_not_a_rival(self):
        rivals = [("max_muncy", 691777, "ATH", False), ("max_muncy", 571970, "LAD", False)]
        out, _ = storage.resolve_contracts_to_ids(
            self.cbk, {"max_muncy": (691777, "ATH", False)}, rivals)
        self.assertEqual(out["max_muncy"]["spotrac_id"], "73287")

    def test_a_traded_player_keeps_his_full_aav_row(self):
        # One Spotrac id on two clubs' pages: the new club's row is the prorated
        # remainder, and the highest-AAV row stands for him (Zack Littell 2026).
        wsn = _row("zack_littell", "24558", "WSN", "SP", 7_000_000)
        ari = _row("zack_littell", "24558", "ARI", "SP", 54_223)
        cbk = spotrac.build_contracts_by_key([wsn, ari], keep_alts=True)
        out, rc = storage.resolve_contracts_to_ids(
            cbk, {"zack_littell": (641793, "ARI", True)}, [])
        self.assertEqual(out["zack_littell"]["aav_usd"], 7_000_000)
        self.assertEqual(rc["kept"], 1)

    def test_a_row_without_an_id_keeps_the_slug_join(self):
        out, _ = storage.resolve_contracts_to_ids(
            self.cbk, {"max_muncy": (None, "ATH", False)}, [])
        self.assertNotIn("max_muncy", out)

    def test_a_manual_override_is_left_alone(self):
        cbk = {"max_muncy": {**MUNCY_LAD, "source": "manual"}}
        out, _ = storage.resolve_contracts_to_ids(
            cbk, {"max_muncy": (691777, "ATH", False)},
            [("max_muncy", 571970, "LAD", False)])
        self.assertNotIn("max_muncy", out)

    def test_a_row_two_claimants_both_fit_goes_to_nobody(self):
        cbk = {"jose_ramirez": dict(RAMIREZ_CLE)}
        out, _ = storage.resolve_contracts_to_ids(
            cbk, {"jose_ramirez": (802064, "CLE", False)},
            [("jose_ramirez", 608070, "CLE", False)])
        self.assertIsNone(out["jose_ramirez"])


class TestCareerWarJoinsOnTheId(unittest.TestCase):
    # war_daily-shaped: {mlbam: {season: {...}}}. 543699 is the pitcher whose
    # 2014-2018 seasons sat under the jose_ramirez slug.
    BY_ID = {
        543699: {y: {"war": 0.1} for y in (2014, 2015, 2016, 2017, 2018)},
        691777: {2025: {"war": -0.12}, 2026: {"war": -1.11}},
    }

    def _cw(self):
        return {
            "jose_ramirez": {"seasons": {str(y): 0.1 for y in range(2014, 2019)},
                             "seasons_bwar": {str(y): 0.1 for y in range(2014, 2019)},
                             "career_war": 0.5, "war_seasons_count": 5, "war_per_yr": 0.1,
                             "source": "ewar_v2"},
            "max_muncy": {"seasons": {"2023": 3.0, "2025": -0.12, "2026": -1.11},
                          "seasons_pa": {"2023": 600, "2025": 220, "2026": 284},
                          "career_war": 1.77, "war_seasons_count": 3, "war_per_yr": 0.59,
                          "source": "ewar_v2"},
            "no_id_row": {"seasons": {"2010": 1.0}, "career_war": 1.0},
        }

    def test_another_players_seasons_are_dropped(self):
        cw = self._cw()
        ids = {"jose_ramirez": 802064, "max_muncy": 691777}
        out, rc = storage.screen_career_war_to_ids(cw, ids, by_id=self.BY_ID)
        # 802064 never played 2014-2018: the whole row was another player's.
        self.assertNotIn("jose_ramirez", out)
        # 691777 played 2025-2026 only; the 2023 season is someone else's.
        self.assertEqual(out["max_muncy"]["seasons"], {"2025": -0.12, "2026": -1.11})
        self.assertEqual(out["max_muncy"]["seasons_pa"], {"2025": 220, "2026": 284})
        self.assertEqual(out["max_muncy"]["career_war"], -1.23)
        self.assertEqual(out["max_muncy"]["war_seasons_count"], 2)
        # A row with no id keeps the slug join.
        self.assertIn("no_id_row", out)
        self.assertEqual(rc["rows_removed"], 1)
        self.assertEqual(rc["seasons_dropped"], 6)
        # The caller's dict is not mutated.
        self.assertIn("2023", cw["max_muncy"]["seasons"])
        self.assertIn("jose_ramirez", cw)

    def test_the_season_in_progress_is_kept(self):
        cw = {"new_guy": {"seasons": {"2026": 0.4}, "career_war": 0.4}}
        out, _ = storage.screen_career_war_to_ids(cw, {"new_guy": 999}, by_id=self.BY_ID)
        self.assertEqual(out["new_guy"]["seasons"], {"2026": 0.4})

    def test_no_cache_passes_rows_through(self):
        cw = self._cw()
        out, rc = storage.screen_career_war_to_ids(
            cw, {"jose_ramirez": 802064}, by_id={})
        self.assertIs(out, cw)
        self.assertFalse(rc["cache_ok"])


class TestServedDebutsBindToTheId(unittest.TestCase):
    """On the served artifact: no debuted row carries a contract whose Spotrac
    row another human claims on /projections/ under the same plain slug."""

    def test_the_named_collisions_are_split(self):
        p = DATA / "debuts.json"
        if not p.exists():
            self.skipTest("data/debuts.json not built")
        rows = {r["player_key"]: r for r in json.loads(p.read_text(encoding="utf-8"))}
        muncy = rows.get("max_muncy")
        if muncy and muncy.get("mlbam_id") == 691777:
            self.assertNotEqual((muncy.get("current_contract") or {}).get("spotrac_id"),
                                "16719", "the ATH Max Muncy serves the LAD veteran's deal")
        ram = rows.get("jose_ramirez")
        if ram and ram.get("mlbam_id") == 802064:
            self.assertNotEqual((ram.get("current_contract") or {}).get("spotrac_id"),
                                "14106", "the CPX pitcher serves the CLE 3B's deal")
            seasons = (ram.get("career_war") or {}).get("seasons") or {}
            self.assertFalse([y for y in seasons if int(y) < 2020],
                             "the CPX pitcher serves another player's 2014-2018 WAR")
            self.assertFalse([y for y in ((ram.get("roster_status") or {})
                                          .get("mlb_seasons") or []) if int(y) < 2020])


if __name__ == "__main__":
    unittest.main()
