# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Confirm DvM+ math is now WAR-tail-weighted.

The user's intent: a 70→75 FV lift counts much more than a 40→45 FV lift.
With the FV_EXPECTED_WAR curve (70=25, 75=32.5, 45=1.5, 50=3), the
ratio of WAR-deltas should be roughly (32.5−25) / (3−1.5) = 5x. The
previous raw-FV-delta math would have given 1x (both are +5 grade pts).
"""

from __future__ import annotations

import unittest

from storage import _fv_to_expected_war


class TailWeight(unittest.TestCase):
    def test_high_end_jump_dominates_low_end(self):
        # 70→75 in WAR units
        hi = _fv_to_expected_war(75) - _fv_to_expected_war(70)
        # 45→50 in WAR units
        lo = _fv_to_expected_war(50) - _fv_to_expected_war(45)
        ratio = hi / lo
        # Expect the high-end jump to weigh >3x the low-end jump.
        self.assertGreater(ratio, 3.0,
                           f"expected high-end FV jump to dominate; ratio={ratio:.1f}")

    def test_70_to_80_dominates_40_to_50(self):
        # User's exact callout: 70->80 vs 40->50
        hi = _fv_to_expected_war(80) - _fv_to_expected_war(70)
        lo = _fv_to_expected_war(50) - _fv_to_expected_war(40)
        ratio = hi / lo
        # 80→60WAR, 70→25WAR → 35 WAR for top jump.
        # 50→3WAR, 40→0.5WAR → 2.5 WAR for low jump.
        # Ratio: 35/2.5 = 14x.
        self.assertGreater(ratio, 10.0,
                           f"expected 70→80 to dominate 40→50 by ≥10x; got {ratio:.1f}")

    def test_curve_monotonic(self):
        # Sanity: WAR-equivalent strictly increases with FV.
        vals = [_fv_to_expected_war(fv) for fv in range(30, 81, 5)]
        for a, b in zip(vals, vals[1:]):
            self.assertGreaterEqual(b, a, "FV_EXPECTED_WAR curve must be monotonic")


if __name__ == "__main__":
    unittest.main()
