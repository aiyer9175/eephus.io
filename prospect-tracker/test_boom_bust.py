"""Unit tests for the BOOM / BUST graduate classifier.

Thresholds (locked with user):
  Boom ≥ +5 WAR
  Bust ≤ −2 WAR
  Floor: 800 PA OR 200 IP OR ≥ 2 MLB seasons
"""

from __future__ import annotations

import unittest

from storage import _compute_boom_bust


class BoomBustThresholds(unittest.TestCase):
    def _payload(self, *, career_war=None, seasons=0, pa=0, ip=0.0, fv=55):
        return {
            "career_war":   {"career_war": career_war, "war_seasons_count": seasons},
            "fv_close_raw": fv,
            "fv_close":     fv,
            "career_stats": [{"pa": pa, "ip": ip}],
        }

    def test_clear_boom(self):
        # FV 55 → 6 expected WAR; 15 - 6 = +9 WAG → BOOM
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=15.0, seasons=4, pa=2400)), "boom")

    def test_clear_bust(self):
        # FV 55 → 6 expected WAR; 0 - 6 = -6 WAG → BUST
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=0.0, seasons=3, pa=1500)), "bust")

    def test_settled_middle(self):
        # FV 55 → 6 expected WAR; 4 - 6 = -2 WAG... exactly at -2.0
        # threshold → BUST (≤ −2 includes equality).
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=4.0, seasons=3, pa=1500)), "bust")
        # 5 - 6 = -1 WAG → SETTLED
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=5.0, seasons=3, pa=1500)), "settled")

    def test_boom_boundary_at_plus_5(self):
        # FV 50 → 3 expected; 8 - 3 = +5 WAG exactly → BOOM (≥ +5 includes equality).
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=8.0, seasons=2, pa=1200, fv=50)), "boom")

    def test_sample_floor_excludes_short_samples(self):
        # WAG would qualify as BOOM but sample below floor → UNSETTLED.
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=10.0, seasons=0, pa=100)), "unsettled")

    def test_sample_floor_satisfied_by_seasons_alone(self):
        # 2 MLB seasons trumps PA floor → eligible for labeling.
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=15.0, seasons=2, pa=400)), "boom")

    def test_sample_floor_satisfied_by_ip_alone(self):
        # 200+ IP trumps PA + season floors → eligible. Use FV 45
        # (expected 1.5 WAR) so 8 - 1.5 = +6.5 WAG clears the +5 boom bar.
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=8.0, seasons=1, pa=0, ip=250, fv=45)), "boom")

    def test_no_career_war_returns_unsettled(self):
        self.assertEqual(_compute_boom_bust(self._payload(
            career_war=None, seasons=3, pa=1500)), "unsettled")

    def test_no_fv_close_returns_unsettled(self):
        p = self._payload(career_war=10.0, seasons=3, pa=1500)
        p["fv_close_raw"] = None
        p["fv_close"] = None
        self.assertEqual(_compute_boom_bust(p), "unsettled")


if __name__ == "__main__":
    unittest.main()
