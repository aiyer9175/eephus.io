# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for scrapers._clean_report_prose."""

from __future__ import annotations

import unittest

from scrapers import _clean_report_prose


class CleanerCases(unittest.TestCase):
    def test_strips_nav_prefix_with_double_arrow(self):
        raw = ("• Top 100 starry prospects • Reliever depth chart for "
               "every MLB team Fantasy baseball home page >> "
               "I liked Hernandez's two-way athleticism that manifested "
               "in his delivery and fastball velo.")
        out = _clean_report_prose(raw)
        self.assertTrue(out.startswith("I liked Hernandez"),
                        f"unexpected leading text: {out[:80]!r}")

    def test_strips_draft_guide_prefix(self):
        raw = ("The fantasy baseball Draft Guide today is here! >> "
               "The theory goes that being a supinator works.")
        out = _clean_report_prose(raw)
        self.assertTrue(out.startswith("The theory goes"))

    def test_strips_leading_scouting_report_header(self):
        out = _clean_report_prose("Scouting Report: Cholowsky has hands.")
        self.assertEqual(out, "Cholowsky has hands.")

    def test_strips_trailing_video_link_tail(self):
        out = _clean_report_prose(
            "Cholowsky has hands and pitches well too. >> Watch the highlights")
        self.assertEqual(out, "Cholowsky has hands and pitches well too.")

    def test_passes_through_normal_prose(self):
        out = _clean_report_prose("Normal writeup with no cruft.")
        self.assertEqual(out, "Normal writeup with no cruft.")

    def test_too_short_returns_none(self):
        self.assertIsNone(_clean_report_prose("ok"))

    def test_empty_returns_none(self):
        self.assertIsNone(_clean_report_prose(""))
        self.assertIsNone(_clean_report_prose(None))

    def test_idempotent(self):
        cleaned = _clean_report_prose("Scouting Report: Some writeup here.")
        re_cleaned = _clean_report_prose(cleaned)
        self.assertEqual(cleaned, re_cleaned)

    def test_collapses_nbsp(self):
        out = _clean_report_prose("Hands   and feet.")
        self.assertIn("Hands and feet.", out)


if __name__ == "__main__":
    unittest.main()
