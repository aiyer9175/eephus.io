"""Unit tests for the BOOM / BUST graduate classifier (RATE-BASED).

Thresholds (locked with user, post-v4):
  Boom ≥ +1.5 WAR/yr above FV-implied rate
  Bust ≤ −0.7 WAR/yr below FV-implied rate
  Floor: 800 PA OR 200 IP OR ≥ 2 MLB seasons

The classifier reads `career_war.war_per_yr` (rate), not cumulative
career WAR. This matches the frontend `gradVsFvProjection` pill so
the label on the graduate card and the label stamped by the backend
agree.
"""

from __future__ import annotations

import unittest

from storage import _compute_boom_bust


class BoomBustThresholds(unittest.TestCase):
    def _payload(self, *, war_per_yr=None, career_war=None, seasons=0,
                 pa=0, ip=0.0, fv=55, position="SS"):
        return {
            "career_war": {
                "war_per_yr":         war_per_yr,
                "career_war":         career_war,
                "war_seasons_count":  seasons,
            },
            "fv_close_raw": fv,
            "fv_close":     fv,
            "position":     position,
            "career_stats": [{"pa": pa, "ip": ip}],
        }

    def test_clear_boom(self):
        # FV 55 hitter → expected 2.5 WAR/yr. 5.0 WAR/yr → +2.5 WAG → BOOM
        self.assertEqual(_compute_boom_bust(self._payload(
            war_per_yr=5.0, seasons=4, pa=2400, fv=55)), "boom")

    def test_clear_bust(self):
        # FV 55 hitter → expected 2.5 WAR/yr. 0.5 WAR/yr → −2.0 → BUST
        self.assertEqual(_compute_boom_bust(self._payload(
            war_per_yr=0.5, seasons=3, pa=1500, fv=55)), "bust")

    def test_settled_middle(self):
        # FV 55 → expected 2.5. 2.0 → −0.5 (above −0.7 bust line) → SETTLED
        self.assertEqual(_compute_boom_bust(self._payload(
            war_per_yr=2.0, seasons=3, pa=1500, fv=55)), "settled")
        # 3.0 → +0.5 (below +1.5 boom line) → SETTLED
        self.assertEqual(_compute_boom_bust(self._payload(
            war_per_yr=3.0, seasons=3, pa=1500, fv=55)), "settled")

    def test_boom_boundary_at_plus_1_5(self):
        # FV 50 → expected 1.6 WAR/yr. 3.1 → +1.5 exactly → BOOM (≥ inclusive)
        self.assertEqual(_compute_boom_bust(self._payload(
            war_per_yr=3.1, seasons=2, pa=1200, fv=50)), "boom")

    def test_bust_boundary_at_minus_0_7(self):
        # FV 55 → expected 2.5. 1.8 → −0.7 exactly → BUST (≤ inclusive)
        self.assertEqual(_compute_boom_bust(self._payload(
            war_per_yr=1.8, seasons=3, pa=1500, fv=55)), "bust")

    def test_sample_floor_excludes_short_samples(self):
        # Rate qualifies as BOOM but sample below floor → UNSETTLED.
        self.assertEqual(_compute_boom_bust(self._payload(
            war_per_yr=5.0, seasons=0, pa=100, fv=55)), "unsettled")

    def test_sample_floor_satisfied_by_seasons_alone(self):
        # 2 MLB seasons trumps PA floor → eligible.
        self.assertEqual(_compute_boom_bust(self._payload(
            war_per_yr=5.0, seasons=2, pa=400, fv=55)), "boom")

    def test_sample_floor_satisfied_by_ip_alone(self):
        # 200+ IP trumps PA + season floors → eligible.
        # FV 45 pitcher → expected 1.0 WAR/yr. 3.0 → +2.0 → BOOM.
        self.assertEqual(_compute_boom_bust(self._payload(
            war_per_yr=3.0, seasons=1, pa=0, ip=250, fv=45,
            position="RHP")), "boom")

    def test_no_war_per_yr_returns_unsettled(self):
        self.assertEqual(_compute_boom_bust(self._payload(
            war_per_yr=None, seasons=3, pa=1500)), "unsettled")

    def test_no_fv_close_returns_unsettled(self):
        p = self._payload(war_per_yr=5.0, seasons=3, pa=1500)
        p["fv_close_raw"] = None
        p["fv_close"] = None
        self.assertEqual(_compute_boom_bust(p), "unsettled")

    def test_mid_career_yamamoto_shape_not_bust(self):
        # Mid-career star with limited cumulative WAR but high rate.
        # 2 yrs / 4 WAR / 2.0 WAR/yr / FV 65 hitter (expected ~4.2 WAR/yr).
        # On the OLD cumulative threshold: 4 - 17 = -13 → BUST (unfair).
        # On the rate threshold: 2.0 - 4.2 = -2.2 → still bust because the
        # rate doesn't beat the FV implied yet. But a 4.5 WAR/yr Skenes
        # at FV 60 (expected 3.5) → +1.0 → settled (no longer auto-bust).
        skenes = self._payload(
            war_per_yr=4.5, seasons=2, ip=300, fv=60, position="RHP")
        # FV 60 pitcher expects 3.5; 4.5 → +1.0 → settled
        self.assertEqual(_compute_boom_bust(skenes), "settled")
        # Bump rate to clearly boom — 5.5 WAR/yr → +2.0 → BOOM
        skenes_boom = self._payload(
            war_per_yr=5.5, seasons=2, ip=300, fv=60, position="RHP")
        self.assertEqual(_compute_boom_bust(skenes_boom), "boom")


if __name__ == "__main__":
    unittest.main()
