"""Unit tests for overseas_csv.py — the KBO/NPB ingest path."""

from __future__ import annotations

import unittest

from overseas_csv import (
    _parse_overseas_summary_row,
    _to_usd,
    is_overseas_slug,
    overseas_player_key,
)


class SlugParsing(unittest.TestCase):
    def test_recognizes_year_overseas(self):
        self.assertEqual(is_overseas_slug("2026overseas"), 2026)
        self.assertEqual(is_overseas_slug("2024overseas"), 2024)
        self.assertEqual(is_overseas_slug("2024_overseas"), 2024)

    def test_rejects_other_slugs(self):
        self.assertIsNone(is_overseas_slug("2024report"))
        self.assertIsNone(is_overseas_slug("2024draft"))
        self.assertIsNone(is_overseas_slug("bos2026may"))
        self.assertIsNone(is_overseas_slug(""))


class PlayerKey(unittest.TestCase):
    def test_namespaces_by_league(self):
        k1 = overseas_player_key("NPB", "Sho Yamada")
        k2 = overseas_player_key("KBO", "Sho Yamada")
        self.assertNotEqual(k1, k2)
        self.assertTrue(k1.startswith("overseas_npb_"))
        self.assertTrue(k2.startswith("overseas_kbo_"))

    def test_normalizes_name(self):
        k1 = overseas_player_key("NPB", "José García")
        k2 = overseas_player_key("NPB", "Jose Garcia")
        self.assertEqual(k1, k2)

    def test_missing_league_fallback(self):
        k = overseas_player_key(None, "Test Player")
        self.assertTrue(k.startswith("overseas_other_"))


class UsdParsing(unittest.TestCase):
    def test_plain_integer(self):
        self.assertEqual(_to_usd("8500000"), 8500000)

    def test_dollar_formatted(self):
        self.assertEqual(_to_usd("$8,500,000"), 8500000)
        self.assertEqual(_to_usd("$1.5M"), 15)  # naive parser strips commas/$ only

    def test_blank(self):
        self.assertIsNone(_to_usd(""))
        self.assertIsNone(_to_usd(None))


class SummaryRowParsing(unittest.TestCase):
    def test_npb_pitcher_row(self):
        row = {
            "Name": "Shunpeita Yamashita", "Pos": "SP", "Player Type": "NPB",
            "ETA": "2028", "Age": "23.55", "Country": "Japan",
            "Current Team": "Orix Buffaloes", "Proj Team": "",
            "Proj Bonus": "", "Ht": "6' 2\"", "Wt": "215", "B": "R", "T": "R",
            "FV": "55", "Risk": "High", "Report": "An NPB first round pick...",
            "Video": "", "PlayerId": "sa3063816",
        }
        out = _parse_overseas_summary_row(row, 2026)
        self.assertEqual(out["player_name"], "Shunpeita Yamashita")
        self.assertEqual(out["player_key"], "overseas_npb_shunpeita_yamashita")
        self.assertEqual(out["league"], "NPB")
        self.assertEqual(out["country"], "Japan")
        self.assertEqual(out["current_team"], "Orix Buffaloes")
        self.assertIsNone(out["proj_team"])
        self.assertIsNone(out["proj_bonus_usd"])
        self.assertEqual(out["eta_year"], 2028)
        self.assertEqual(out["fv"], 55.0)
        self.assertEqual(out["fg_player_id"], "sa3063816")

    def test_kbo_hitter_row(self):
        row = {
            "Name": "Do Yeong Kim", "Pos": "3B", "Player Type": "KBO",
            "Country": "South Korea", "Current Team": "KIA Tigers",
            "FV": "47.5", "PlayerId": "sa3018059",
        }
        out = _parse_overseas_summary_row(row, 2026)
        self.assertEqual(out["league"], "KBO")
        self.assertEqual(out["player_key"], "overseas_kbo_do_yeong_kim")

    def test_missing_name_returns_none(self):
        self.assertIsNone(_parse_overseas_summary_row({"Name": ""}, 2026))


if __name__ == "__main__":
    unittest.main()
