# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for the v14 BOOM / BUST graduate classifier.

v14 thresholds (post-redesign):
  Boom ≥ +2.5 full-season-equivalent WAR above FV-implied WAR/yr
  Bust ≤ −1.5 below
  WAG sample floor: career PA ≥ 150 (hitters) OR career IP ≥ 50 (pitchers)
  BOOM/BUST also requires: ≥2 MLB seasons OR ≥800 career PA OR ≥200 career IP

The v14 WAG = (career_war / career_pa) × full_season_pa_target − fv_implied_war_per_yr.
This projects the player's rate to a qualifier-equivalent full season, which
fixes the cycle-13 bug where mid-career grads with elite rates (Caminero, etc.)
read as negative WAG simply because they hadn't accumulated yet.

Frontend boomBustPillHTML in index.html must mirror these thresholds.
"""

from __future__ import annotations

import unittest

from storage import _compute_boom_bust, _grad_wag


class V14WAGFormula(unittest.TestCase):
    def _payload(self, *, career_war=None, seasons=0, pa=0, ip=0.0,
                 fv=55, position="SS"):
        return {
            "career_war": {
                "career_war":        career_war,
                "war_seasons_count": seasons,
            },
            "fv_close_raw": fv,
            "fv_close":     fv,
            "position":     position,
            "career_stats": [{"level": "MLB", "pa": pa, "ip": ip}],
        }

    def test_caminero_shape_positive_wag(self):
        # Junior Caminero: 4.6 WAR over ~510 PA at FV 55.
        # full_season_war = 4.6 × (612 / 510) ≈ 5.52
        # expected at FV 55 = 2.5
        # WAG ≈ +3.0 (positive, BOOM-tier)
        wag = _grad_wag(self._payload(
            career_war=4.6, seasons=1, pa=510, fv=55))
        self.assertIsNotNone(wag)
        self.assertGreater(wag, 2.0)

    def test_hitter_under_pa_floor_returns_none(self):
        # 100 PA < 150 floor → WAG = None
        wag = _grad_wag(self._payload(
            career_war=2.0, seasons=0, pa=100, fv=55))
        self.assertIsNone(wag)

    def test_pitcher_under_ip_floor_returns_none(self):
        # 30 IP < 50 floor → WAG = None
        wag = _grad_wag(self._payload(
            career_war=1.0, seasons=0, ip=30, fv=55, position="RHP"))
        self.assertIsNone(wag)


class V14BoomBustThresholds(unittest.TestCase):
    def _payload(self, *, career_war=None, seasons=0, pa=0, ip=0.0,
                 fv=55, position="SS"):
        return {
            "career_war": {
                "career_war":        career_war,
                "war_seasons_count": seasons,
            },
            "fv_close_raw": fv,
            "fv_close":     fv,
            "position":     position,
            "career_stats": [{"level": "MLB", "pa": pa, "ip": ip}],
        }

    def test_clear_boom(self):
        # FV 55, expect 2.5. 20 WAR over 2400 PA = (20/2400)*612 = 5.1
        # full-season → +2.6 WAG → BOOM.
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=20.0, seasons=4, pa=2400, fv=55)), "boom")

    def test_clear_bust(self):
        # FV 55, expect 2.5. 1.0 WAR / 1500 PA = (1/1500)*612 = 0.408
        # full-season → -2.1 WAG → BUST
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=1.0, seasons=3, pa=1500, fv=55)), "bust")

    def test_settled_middle(self):
        # FV 55. 6 WAR / 1500 PA = (6/1500)*612 = 2.448
        # full-season → -0.05 WAG → SETTLED (in [-1.5, +2.5] band).
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=6.0, seasons=3, pa=1500, fv=55)), "settled")

    def test_sample_floor_excludes_short_samples(self):
        # WAG would compute (pa=200 > 150 floor) but BOOM/BUST needs the
        # broader floor (800 PA / 200 IP / 2 seasons). Falls back to unsettled.
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=5.0, seasons=0, pa=200, fv=55)), "unsettled")

    def test_sample_floor_satisfied_by_seasons_alone(self):
        # 2 MLB seasons + qualifying PA for WAG. 8 WAR / 400 PA = 12.24
        # full-season → +9.7 vs FV 55 → BOOM.
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=8.0, seasons=2, pa=400, fv=55)), "boom")

    def test_sample_floor_satisfied_by_ip_alone(self):
        # 200+ IP trumps PA + seasons. 5 WAR / 250 IP at FV 45 (expected 1.0).
        # full_season at mirp 65 IP target = 1.3 → +0.3 → SETTLED
        # (rate doesn't project that high over a full reliever season).
        # Use SP role for stronger projection: at SP 175 IP target,
        # 5/250 * 175 = 3.5 → +2.5 → BOOM.
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=5.0, seasons=1, ip=250, fv=45,
            position="SP")), "boom")

    def test_no_career_war_returns_unsettled(self):
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=None, seasons=3, pa=1500)), "unsettled")

    def test_no_fv_close_returns_unsettled(self):
        p = self._payload(career_war=5.0, seasons=3, pa=1500)
        p["fv_close_raw"] = None
        p["fv_close"] = None
        self.assertEqual(_compute_boom_bust(p), "unsettled")


if __name__ == "__main__":
    unittest.main()
