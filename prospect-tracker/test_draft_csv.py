"""Unit tests for draft_csv.py — the amateur prospect ingest path."""

from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path

from draft_csv import (
    _parse_draft_summary_row,
    _parse_pick_cell,
    draft_player_key,
    is_draft_slug,
)


class SlugParsing(unittest.TestCase):
    def test_recognizes_year_draft(self):
        self.assertEqual(is_draft_slug("2024draft"), 2024)
        self.assertEqual(is_draft_slug("2026draft"), 2026)
        self.assertEqual(is_draft_slug("2024_draft"), 2024)
        self.assertEqual(is_draft_slug("2024-draft"), 2024)

    def test_rejects_milb_slugs(self):
        self.assertIsNone(is_draft_slug("2024report"))
        self.assertIsNone(is_draft_slug("2024updated"))
        self.assertIsNone(is_draft_slug("2024graduates"))
        self.assertIsNone(is_draft_slug("bos2026may"))
        self.assertIsNone(is_draft_slug(""))


class PickCell(unittest.TestCase):
    def test_parses_overall_team(self):
        self.assertEqual(_parse_pick_cell("7/STL"), (7, "STL"))
        self.assertEqual(_parse_pick_cell("1/CLE"), (1, "CLE"))
        self.assertEqual(_parse_pick_cell("105/NYY"), (105, "NYY"))

    def test_handles_whitespace(self):
        self.assertEqual(_parse_pick_cell(" 7 / STL "), (7, "STL"))

    def test_rejects_garbage(self):
        self.assertEqual(_parse_pick_cell(""), (None, None))
        self.assertEqual(_parse_pick_cell(None), (None, None))
        self.assertEqual(_parse_pick_cell("Unsigned"), (None, None))


class DraftPlayerKey(unittest.TestCase):
    def test_namespaces_by_year(self):
        k1 = draft_player_key(2024, "John Smith")
        k2 = draft_player_key(2025, "John Smith")
        self.assertNotEqual(k1, k2)
        self.assertTrue(k1.startswith("draft_2024_"))
        self.assertTrue(k2.startswith("draft_2025_"))

    def test_normalizes_name(self):
        k1 = draft_player_key(2024, "José Ramírez")
        k2 = draft_player_key(2024, "Jose Ramirez")
        self.assertEqual(k1, k2)


class SummaryRowParsing(unittest.TestCase):
    def test_post_draft_with_pick(self):
        row = {
            "Rank": "7", "Top 100": "", "Pick": "7/STL",
            "Name": "JJ Wetherholt", "Pos": "2B", "Player Type": "ColH",
            "Age": "21.8361111", "Ht": "5' 11\"", "Wt": "180",
            "B": "L", "T": "R", "School": "West Virginia",
            "College Commit": "", "FV": "50", "Risk": "Low",
            "Report": "Wetherholt is a native of Mars, Pennsylvania...",
            "Video": "", "PlayerId": "",
        }
        out = _parse_draft_summary_row(row, 2024)
        self.assertEqual(out["player_name"], "JJ Wetherholt")
        self.assertEqual(out["player_key"], "draft_2024_jj_wetherholt")
        self.assertEqual(out["position"], "2B")
        self.assertEqual(out["school"], "West Virginia")
        self.assertEqual(out["fv"], 50.0)
        self.assertEqual(out["rank"], 7)
        self.assertEqual(out["pick_overall"], 7)
        self.assertEqual(out["pick_team"], "STL")
        self.assertEqual(out["draft_year"], 2024)

    def test_pre_draft_with_trend(self):
        row = {
            "Rank": "1", "Top 100": "", "Trend": "",
            "Name": "Roch Cholowsky", "Pos": "SS", "Player Type": "COLh",
            "Age": "21.27", "Ht": "6' 2\"", "Wt": "202",
            "B": "R", "T": "R", "School": "UCLA",
            "College Commit": "", "FV": "55", "Risk": "Med",
            "Report": "Cholowsky is the odds-on favorite...",
            "Video": "", "PlayerId": "sa3028866",
        }
        out = _parse_draft_summary_row(row, 2026)
        self.assertEqual(out["player_name"], "Roch Cholowsky")
        self.assertEqual(out["player_key"], "draft_2026_roch_cholowsky")
        self.assertIsNone(out["pick_overall"])
        self.assertIsNone(out["pick_team"])
        self.assertEqual(out["fg_player_id"], "sa3028866")

    def test_hs_player_with_commit(self):
        row = {
            "Rank": "8", "Pick": "", "Name": "Jacob Lombard",
            "Pos": "SS", "Player Type": "HSh", "Age": "18.0",
            "School": "Gulliver HS (FL)", "College Commit": "Miami",
            "FV": "45", "Report": "...",
        }
        out = _parse_draft_summary_row(row, 2026)
        self.assertEqual(out["school"], "Gulliver HS (FL)")
        self.assertEqual(out["college_commit"], "Miami")
        self.assertEqual(out["player_type"], "HSh")

    def test_missing_name_returns_none(self):
        out = _parse_draft_summary_row({"Rank": "1", "Name": ""}, 2024)
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
