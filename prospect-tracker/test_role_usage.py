# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for role_usage (rule D usage-based pitcher role correction).

Covers the rule itself (starter_by_usage), the label override
(usage_position_override) with the cache read mocked so the tests never
depend on .cache/milb_stats contents, and the cache aggregation helper
(current_season_pitching) against a mocked milb_history.player_index.
"""

import unittest
from unittest import mock

import role_usage
from role_usage import (
    current_season_pitching,
    starter_by_usage,
    usage_position_override,
)


class TestStarterByUsage(unittest.TestCase):
    def test_clemmey_shape_flips(self):
        # Alex Clemmey 2026: 19 G / 19 GS / 87 IP. GS-share 1.00,
        # IP/G 4.58 - the canonical stretched starter. Must flip.
        self.assertTrue(starter_by_usage(19, 19, 87.0))

    def test_opener_stays(self):
        # Alex Cook 2026: 28 G / 5 GS / 32 IP. IP/G 1.13 - the opener
        # shape. GS-share 0.18 and IP/G both fail. Must not flip.
        self.assertFalse(starter_by_usage(28, 5, 32.0))

    def test_sub_20_ip_cameo_stays(self):
        # 4 G / 4 GS / 18 IP: starter-shaped rates but under the 20 IP
        # floor - an early-season cameo. Must not flip.
        self.assertFalse(starter_by_usage(4, 4, 18.0))

    def test_boundary_line_flips(self):
        # Exactly at every threshold: GS-share 0.50, IP/G 3.0, IP 60.
        # Thresholds are inclusive.
        self.assertTrue(starter_by_usage(20, 10, 60.0))

    def test_high_gs_share_low_ip_per_g_stays(self):
        # Piggyback/tandem shape: majority GS but short outings.
        # 20 G / 12 GS / 40 IP -> IP/G 2.0 fails the 3.0 floor.
        self.assertFalse(starter_by_usage(20, 12, 40.0))

    def test_missing_data_stays(self):
        self.assertFalse(starter_by_usage(None, None, None))
        self.assertFalse(starter_by_usage(None, 5, 40.0))
        self.assertFalse(starter_by_usage(10, None, 40.0))
        self.assertFalse(starter_by_usage(10, 5, None))
        self.assertFalse(starter_by_usage("", "", ""))

    def test_zero_games_stays(self):
        self.assertFalse(starter_by_usage(0, 0, 0))
        self.assertFalse(starter_by_usage(0, 0, 25.0))


class TestUsagePositionOverride(unittest.TestCase):
    def test_clemmey_shape_mirp_flips_to_sp(self):
        with mock.patch.object(
            role_usage, "current_season_pitching",
            return_value={"g": 19, "gs": 19, "ip": 87.0},
        ):
            self.assertEqual(usage_position_override("MIRP", 700001, 2026), "SP")
            self.assertEqual(usage_position_override("SIRP", 700001, 2026), "SP")
            # Compound relief label and lowercase both qualify.
            self.assertEqual(usage_position_override("MIRP/SIRP", 700001, 2026), "SP")
            self.assertEqual(usage_position_override("mirp", 700001, 2026), "SP")

    def test_opener_stays_unchanged(self):
        with mock.patch.object(
            role_usage, "current_season_pitching",
            return_value={"g": 28, "gs": 5, "ip": 32.0},
        ):
            self.assertEqual(usage_position_override("MIRP", 700002, 2026), "MIRP")
            self.assertEqual(usage_position_override("SIRP", 700002, 2026), "SIRP")

    def test_non_role_label_passes_through_without_cache_read(self):
        # A label usage may never adjudicate must return unchanged and never
        # even read the cache. NARROWED 2026-07-30: "SP" and "RHP" used to be
        # in this list, and stopped being when USAGE_ROLE_BOTH_DIRECTIONS
        # shipped ON - usage now rules on them in both directions, so they DO
        # read the cache. What survives is the real invariant: a hitter label,
        # and a compound carrying a non-role token, are never touched and never
        # cost a cache read. The retired one-direction contract for SP/RHP is
        # pinned explicitly in test_position_role_phase5.
        with mock.patch.object(
            role_usage, "current_season_pitching",
            side_effect=AssertionError("cache read for a non-role label"),
        ):
            self.assertEqual(usage_position_override("SS", 700003, 2026), "SS")
            # Mixed compound with a non-relief token stays untouched.
            self.assertEqual(usage_position_override("SP/MIRP", 700003, 2026), "SP/MIRP")
            # And the retired behaviour is still reachable byte-for-byte.
            self.assertEqual(
                usage_position_override("SP", 700003, 2026,
                                        both_directions=False), "SP")
            self.assertEqual(
                usage_position_override("RHP", 700003, 2026,
                                        both_directions=False), "RHP")

    def test_missing_usage_data_stays(self):
        with mock.patch.object(
            role_usage, "current_season_pitching", return_value=None,
        ):
            self.assertEqual(usage_position_override("MIRP", 700004, 2026), "MIRP")

    def test_missing_identity_stays(self):
        # No mlbam or no position: unchanged, no cache read.
        with mock.patch.object(
            role_usage, "current_season_pitching",
            side_effect=AssertionError("cache read without an mlbam"),
        ):
            self.assertEqual(usage_position_override("MIRP", None, 2026), "MIRP")
            self.assertIsNone(usage_position_override(None, 700005, 2026))
            self.assertEqual(usage_position_override("", 700005, 2026), "")


class TestCurrentSeasonPitching(unittest.TestCase):
    def _index(self):
        # One player split across A+ and AA plus an MLB cup of coffee;
        # ip strings use baseball thirds notation ('.1' = 1/3).
        return {
            700100: [
                {"mlbam": 700100, "level": "A+", "g": 10, "gs": 10, "ip": "40.2"},
                {"mlbam": 700100, "level": "AA", "g": 9, "gs": 9, "ip": "40.2"},
                {"mlbam": 700100, "level": "MLB", "g": 3, "gs": 3, "ip": "15.0"},
            ],
        }

    def test_sums_milb_levels_excludes_mlb_and_parses_thirds(self):
        with mock.patch("milb_history.player_index",
                        return_value=self._index()):
            line = current_season_pitching(700100, 2026)
        self.assertIsNotNone(line)
        self.assertEqual(line["g"], 19)
        self.assertEqual(line["gs"], 19)
        # 40.2 + 40.2 in thirds notation = 122 + 122 outs = 81.33 IP
        # (NOT 80.4); the MLB 15.0 must not be included.
        self.assertAlmostEqual(line["ip"], 81.33, places=2)

    def test_unknown_player_returns_none(self):
        with mock.patch("milb_history.player_index",
                        return_value=self._index()):
            self.assertIsNone(current_season_pitching(999999, 2026))

    def test_bad_mlbam_returns_none(self):
        self.assertIsNone(current_season_pitching(None, 2026))
        self.assertIsNone(current_season_pitching("not-an-id", 2026))

    def test_cache_error_returns_none(self):
        with mock.patch("milb_history.player_index",
                        side_effect=OSError("cache unreadable")):
            self.assertIsNone(current_season_pitching(700100, 2026))


if __name__ == "__main__":
    unittest.main()
