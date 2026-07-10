# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for player_images.py — URL builders."""

from __future__ import annotations

import unittest

from player_images import (
    college_logo_url,
    country_flag_svg_url,
    player_headshot_url,
)


class Headshot(unittest.TestCase):
    def test_mlbam_preferred(self):
        url = player_headshot_url({"mlbam_id": 683953, "fg_player_id": "sa3063816"})
        self.assertIn("img.mlbstatic.com", url)
        self.assertIn("683953", url)

    def test_fg_tier_retired(self):
        # The FanGraphs photo tier was removed 2026-06-09: FG serves
        # Cross-Origin-Resource-Policy headers, so browsers hard-block every
        # cross-origin <img> load — the URLs could never render. An fg-only
        # player resolves to None (silhouette), never a doomed FG request.
        self.assertIsNone(player_headshot_url({"fg_player_id": "sa3063816"}))

    def test_no_ids_returns_none(self):
        self.assertIsNone(player_headshot_url({}))
        self.assertIsNone(player_headshot_url(None))

    def test_mlbam_coerce_failure_falls_through(self):
        # Bad MLBAM id → None (silhouette); no FG fallback exists anymore.
        self.assertIsNone(player_headshot_url({"mlbam_id": "not-an-int", "fg_player_id": "sa1"}))


class CollegeLogo(unittest.TestCase):
    def test_known_d1(self):
        self.assertIn("espncdn", college_logo_url("UCLA"))
        self.assertIn("espncdn", college_logo_url("Wake Forest"))
        self.assertIn("espncdn", college_logo_url("West Virginia"))
        self.assertIn("espncdn", college_logo_url("LSU"))

    def test_hs_returns_none(self):
        self.assertIsNone(college_logo_url("Fort Worth Christian HS (TX)"))
        self.assertIsNone(college_logo_url("Some Random High School"))

    def test_alias_resolved(self):
        # Ole Miss alias
        self.assertIn("espncdn", college_logo_url("Mississippi"))

    def test_unknown_returns_none(self):
        self.assertIsNone(college_logo_url("Tiny D-3 University"))
        self.assertIsNone(college_logo_url(""))
        self.assertIsNone(college_logo_url(None))


class CountryFlag(unittest.TestCase):
    def test_valid_codes(self):
        self.assertEqual(country_flag_svg_url("jp"), "https://flagcdn.com/jp.svg")
        self.assertEqual(country_flag_svg_url("KR"), "https://flagcdn.com/kr.svg")

    def test_invalid_returns_none(self):
        self.assertIsNone(country_flag_svg_url(None))
        self.assertIsNone(country_flag_svg_url(""))
        self.assertIsNone(country_flag_svg_url("jpn"))  # not 2 letters
        self.assertIsNone(country_flag_svg_url("12"))


if __name__ == "__main__":
    unittest.main()
