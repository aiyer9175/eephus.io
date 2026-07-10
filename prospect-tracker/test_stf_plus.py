# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the peripheral STF+ calculation in storage.py.

These exercise `_compute_peripheral_stf_plus` with synthetic statlines
and hand-built level-norms blocks. No network or DB access needed.

Run: python -m pytest test_stf_plus.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from storage import _compute_peripheral_stf_plus


# Synthetic AA-ish level norms. Means hand-picked so the math is checkable.
AA_PERF_NORMS = {
    "avg_pitcher_k_pct":  22.0,
    "avg_pitcher_bb_pct": 9.0,
    "avg_hr_per_9":       1.0,
}


def _statline(**kw):
    base = {"is_pitcher": True, "ip": 50, "level": "AA"}
    base.update(kw)
    return base


class TestSamplGate:
    def test_below_ip_and_bf_gate_returns_none(self):
        sl = _statline(ip=10, batters_faced=20, k_pct=30, bb_pct=7, hr_per_9=0.8)
        assert _compute_peripheral_stf_plus(sl, AA_PERF_NORMS) is None

    def test_meets_ip_gate_only(self):
        sl = _statline(ip=20, batters_faced=0, k_pct=30, bb_pct=7, hr_per_9=0.8)
        assert _compute_peripheral_stf_plus(sl, AA_PERF_NORMS) is not None

    def test_meets_bf_gate_only(self):
        sl = _statline(ip=0, batters_faced=30, k_pct=30, bb_pct=7, hr_per_9=0.8)
        assert _compute_peripheral_stf_plus(sl, AA_PERF_NORMS) is not None


class TestNullInputs:
    def test_no_norms_returns_none(self):
        sl = _statline(k_pct=30, bb_pct=7, hr_per_9=0.8)
        assert _compute_peripheral_stf_plus(sl, None) is None

    def test_not_pitcher_returns_none(self):
        sl = _statline(k_pct=30, bb_pct=7, hr_per_9=0.8)
        sl["is_pitcher"] = False
        assert _compute_peripheral_stf_plus(sl, AA_PERF_NORMS) is None

    def test_all_peripherals_missing_returns_none(self):
        sl = _statline()
        assert _compute_peripheral_stf_plus(sl, AA_PERF_NORMS) is None


class TestComputeValues:
    def test_at_mean_anchors_at_100(self):
        # K% = μ, BB% = μ, HR/9 = μ → z_k = z_bb = z_hr = 0 → STF+ = 100.
        sl = _statline(k_pct=22.0, bb_pct=9.0, hr_per_9=1.0)
        assert _compute_peripheral_stf_plus(sl, AA_PERF_NORMS) == 100

    def test_better_k_raises_stf(self):
        # K% one stdev above mean (σ = 0.15·22 = 3.3) -> z_k = 1.0
        # STF+ = 100 + 10·(0.55·1.0 + 0 + 0) / sum(weights w/ data only)
        # All three weights present (zero z still counted) so
        # composite = 0.55/1.0 = 0.55, STF+ = 100 + 5.5 → 106.
        sl = _statline(k_pct=22.0 + 3.3, bb_pct=9.0, hr_per_9=1.0)
        out = _compute_peripheral_stf_plus(sl, AA_PERF_NORMS)
        assert out == 106  # 100 + round(10·0.55) - tolerate ±1

    def test_higher_bb_lowers_stf(self):
        # BB% one stdev above mean (σ = 0.15·9 = 1.35) → z_bb = -1.0 after invert
        # STF+ = 100 + 10·(0.30·-1.0) = 100 - 3.0 = 97.
        sl = _statline(k_pct=22.0, bb_pct=9.0 + 1.35, hr_per_9=1.0)
        out = _compute_peripheral_stf_plus(sl, AA_PERF_NORMS)
        assert out == 97

    def test_higher_hr9_lowers_stf(self):
        # HR/9 one stdev above mean (σ = 0.15·1.0 = 0.15) → z_hr = -1.0 after invert
        # STF+ = 100 + 10·(0.15·-1.0) = 100 - 1.5 → 98 or 99 (round).
        sl = _statline(k_pct=22.0, bb_pct=9.0, hr_per_9=1.0 + 0.15)
        out = _compute_peripheral_stf_plus(sl, AA_PERF_NORMS)
        assert out in {98, 99}

    def test_partial_data_skips_missing_component(self):
        # Only K% is set — composite uses K% weight alone, weight_sum
        # normalizes so the result lands at 100 + 10·(1.0) = 110.
        sl = _statline(k_pct=22.0 + 3.3)
        out = _compute_peripheral_stf_plus(sl, AA_PERF_NORMS)
        # weight_sum = 0.55, parts = [(0.55, 1.0)], composite = 1.0
        # → 100 + 10 = 110
        assert out == 110

    def test_zero_mean_norm_returns_none(self):
        # If a level somehow ships avg_pitcher_k_pct = 0, the function
        # must defend (no div-by-zero). All three norms zero → all three
        # z-scores fail to compute → no parts → None.
        sl = _statline(k_pct=30, bb_pct=7, hr_per_9=0.8)
        norms = {"avg_pitcher_k_pct": 0, "avg_pitcher_bb_pct": 0, "avg_hr_per_9": 0}
        assert _compute_peripheral_stf_plus(sl, norms) is None
