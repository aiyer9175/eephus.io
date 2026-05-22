"""Tests for the MLB-equivalent translation overlay on overseas stats."""

from __future__ import annotations

import unittest

from overseas_export import (
    LEAGUE_CONTEXT,
    _mlb_translate,
    build_overseas_export,
)


class TranslationFactors(unittest.TestCase):
    def test_all_supported_leagues_have_factors(self):
        for league in ("NPB", "KBO", "CPBL"):
            ctx = LEAGUE_CONTEXT[league]
            self.assertIn("hitter_wrc_factor", ctx)
            self.assertIn("pitcher_era_factor", ctx)
            # Factors must be within a sane range (no typos that would
            # silently turn a wRC+ 130 into 13 or 1300).
            self.assertGreater(ctx["hitter_wrc_factor"], 0.5)
            self.assertLess(ctx["hitter_wrc_factor"], 1.0)
            self.assertGreater(ctx["pitcher_era_factor"], 1.0)
            self.assertLess(ctx["pitcher_era_factor"], 2.5)

    def test_translation_direction(self):
        """Sanity: MLBe hitter wRC+ should be LOWER than league (haircut),
        MLBe pitcher ERA should be HIGHER than league (haircut)."""
        ctx = LEAGUE_CONTEXT["NPB"]
        # Hitter: 145 wRC+ → 145 * 0.87 = 126
        hit = _mlb_translate({"wrc_plus": 145}, ctx, is_pitcher=False)
        self.assertEqual(hit["wrc_plus_mlbe"], 126)
        # Pitcher: 1.61 ERA → 1.61 * 1.25 = 2.01
        pit = _mlb_translate({"era": 1.61}, ctx, is_pitcher=True)
        self.assertEqual(pit["era_mlbe"], 2.01)

    def test_kbo_factors(self):
        ctx = LEAGUE_CONTEXT["KBO"]
        # 168 wRC+ * 0.81 = 136
        hit = _mlb_translate({"wrc_plus": 168}, ctx, is_pitcher=False)
        self.assertEqual(hit["wrc_plus_mlbe"], 136)

    def test_missing_inputs_safe(self):
        """No payload field → no MLBe field added, no crash."""
        ctx = LEAGUE_CONTEXT["NPB"]
        out = _mlb_translate({}, ctx, is_pitcher=False)
        self.assertNotIn("wrc_plus_mlbe", out)
        out = _mlb_translate({"wrc_plus": None}, ctx, is_pitcher=False)
        self.assertNotIn("wrc_plus_mlbe", out)

    def test_empty_context_safe(self):
        """Unknown-league context (e.g., a brand-new league code) →
        no _mlbe annotations, no exception."""
        out = _mlb_translate({"era": 3.50, "wrc_plus": 110}, {}, is_pitcher=True)
        self.assertEqual(out["era"], 3.50)
        self.assertNotIn("era_mlbe", out)


class ExportIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.export = build_overseas_export()

    def test_npb_pitchers_have_era_mlbe(self):
        npb = next(b for b in self.export["leagues"] if b["league"] == "NPB")
        had_one = False
        for p in npb["prospects"]:
            for s in p["stats"]:
                if s.get("league") != "NPB":
                    continue
                era = (s.get("payload") or {}).get("era")
                if era is None:
                    continue
                era_mlbe = (s.get("payload") or {}).get("era_mlbe")
                self.assertIsNotNone(era_mlbe,
                                     f"{p['player_name']} {s['season']} missing era_mlbe")
                # Only assert magnitude when the raw is non-zero (a 0.00
                # ERA in a 2-IP cup of coffee multiplies to 0.00 MLBe).
                if era > 0:
                    self.assertGreater(era_mlbe, era,
                                       "MLBe ERA should be higher than league raw")
                had_one = True
        self.assertTrue(had_one, "expected at least one NPB pitcher with era + era_mlbe")

    def test_country_code_populated(self):
        for league in self.export["leagues"]:
            for p in league["prospects"]:
                if p["country"] in ("Japan", "South Korea", "Taiwan", "Cuba"):
                    self.assertIsNotNone(p["country_code"],
                                         f"{p['player_name']} ({p['country']}) missing country_code")
                    self.assertIsNotNone(p["country_flag_svg"])


if __name__ == "__main__":
    unittest.main()
