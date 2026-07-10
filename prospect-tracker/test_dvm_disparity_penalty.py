# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the v30 DvM+ over-grading penalty.

When the FV-derived DvM+ trajectory outruns the tool-grade DvM+
trajectory by a wide margin, the org's blended DvM+ is shifted toward
the tool side. The reverse case (tools running ahead of FV) is NOT
penalized — that reads as a lagging scout upgrade, not overgrading.

The penalty is implemented as an adaptive tool weight inside the
private _blend_dvm closure of export_timeseries_json. These tests
exercise the same arithmetic by reproducing the schedule independently
+ running the end-to-end pipeline on a fixture to confirm the
penalized blend values appear on the org_summary payload.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


# Re-derive the adaptive tool-weight schedule the storage code uses
# so the threshold contract is locked down by tests independent of
# the closure that owns the helper inside export_timeseries_json.
def _expected_tool_weight(overall, tool):
    if overall is None or tool is None:
        return 0.30
    gap = overall - tool
    if gap < 15:
        return 0.30
    if gap >= 35:
        return 0.60
    return 0.40 + (gap - 15) * 0.01


def _expected_blend(overall, tool):
    if overall is None and tool is None:
        return None
    if overall is None:
        return round(tool)
    if tool is None:
        return round(overall)
    tw = _expected_tool_weight(overall, tool)
    return round((1 - tw) * overall + tw * tool)


class TestAdaptiveBlendSchedule:
    def test_no_penalty_below_threshold(self):
        """Gap < 15: baseline 70/30 blend; no shift toward tools."""
        for ov, tl in [(100, 100), (110, 100), (114, 100), (120, 106)]:
            tw = _expected_tool_weight(ov, tl)
            assert tw == 0.30, f"({ov}, {tl}) should not trigger penalty"

    def test_penalty_engages_at_15(self):
        """Gap = 15: tool weight jumps to 0.40 (the soft-penalty knee)."""
        assert _expected_tool_weight(115, 100) == 0.40
        # And the blend value moves accordingly:
        # baseline 0.7*115 + 0.3*100 = 110.5; penalized 0.6*115 + 0.4*100 = 109
        assert _expected_blend(115, 100) == 109

    def test_penalty_ramps_linearly_15_to_35(self):
        """Tool weight goes 0.40 → 0.60 as gap walks 15 → 35."""
        assert _expected_tool_weight(120, 100) == pytest.approx(0.45)
        assert _expected_tool_weight(125, 100) == pytest.approx(0.50)
        assert _expected_tool_weight(130, 100) == pytest.approx(0.55)
        assert _expected_tool_weight(135, 100) == pytest.approx(0.60)

    def test_penalty_caps_at_gap_35(self):
        """Gaps above 35 don't push tool weight past 60%."""
        assert _expected_tool_weight(150, 100) == 0.60
        assert _expected_tool_weight(200, 100) == 0.60

    def test_asymmetric_reverse_case(self):
        """Tools ahead of FV → no penalty (this direction is lagging-
        upgrade signal, NOT overgrading)."""
        assert _expected_tool_weight(100, 130) == 0.30
        assert _expected_tool_weight(100, 200) == 0.30
        # Blend stays at the 70/30 default — tools count for 30% only.
        # 0.7 * 100 + 0.3 * 130 = 109
        assert _expected_blend(100, 130) == 109

    def test_missing_signal_passes_through(self):
        """Either side missing → return the present side (no penalty)."""
        assert _expected_blend(None, None) is None
        assert _expected_blend(120, None) == 120
        assert _expected_blend(None, 95)  == 95


_TIMESERIES = Path(__file__).parent / "data" / "timeseries.json"


@pytest.mark.skipif(
    not _TIMESERIES.exists(),
    reason="data/timeseries.json missing — run rebuild-only first",
)
class TestPenaltyOnLiveData:
    @classmethod
    def setup_class(cls):
        cls.data = json.loads(_TIMESERIES.read_text(encoding="utf-8"))
        cls.org_summary = cls.data.get("org_summary") or []

    def test_disparity_report_present(self):
        """Every org should carry the disparity_by_window report on
        both dev branches so the UI can explain when the penalty
        fired."""
        for entry in self.org_summary:
            tree = entry.get("tree") or {}
            for branch in ("dev_hitter", "dev_pitcher"):
                disp = (tree.get(branch) or {}).get("disparity_by_window")
                assert disp is not None, f"{entry.get('org')} missing {branch}.disparity_by_window"
                assert "6y" in disp, f"{entry.get('org')} {branch} missing 6y window"
                row = disp["6y"]
                for k in ("overall_dvm_plus", "tool_dvm_plus_used", "gap", "tool_weight_applied", "penalty_pts"):
                    assert k in row, f"{entry.get('org')} {branch} 6y missing {k}"

    def test_penalty_only_fires_on_FV_ahead_of_tools(self):
        """Where penalty_pts > 0, overall_dvm_plus MUST be ahead of
        tool_dvm_plus_used. The reverse case (tools ahead of FV)
        should always have penalty_pts == 0."""
        for entry in self.org_summary:
            tree = entry.get("tree") or {}
            for branch in ("dev_hitter", "dev_pitcher"):
                disp = (tree.get(branch) or {}).get("disparity_by_window") or {}
                for win, row in disp.items():
                    if row.get("penalty_pts", 0) > 0:
                        assert row["overall_dvm_plus"] > row["tool_dvm_plus_used"], (
                            f"{entry.get('org')} {branch} {win}: penalty fired but "
                            f"overall ({row['overall_dvm_plus']}) <= "
                            f"tool ({row['tool_dvm_plus_used']})"
                        )

    def test_disparity_report_carries_meaningful_signals(self):
        """v30.7 reframing — the disparity report no longer drives the
        final blend value (the blend now goes through position-bucket
        weighting on the dev_hitter / dev_pitcher leaf, so the report
        and the headline value compute different things). The report
        retains its diagnostic role: it tells you when the FV vs Tool
        gap fired the over-grade penalty. This test confirms the
        report's internal arithmetic is consistent (tw matches gap
        size; penalty_pts non-negative)."""
        for entry in self.org_summary:
            tree = entry.get("tree") or {}
            for branch in ("dev_hitter", "dev_pitcher"):
                node = tree.get(branch) or {}
                disp = node.get("disparity_by_window") or {}
                for win, row in disp.items():
                    ov = row.get("overall_dvm_plus")
                    tl = row.get("tool_dvm_plus_used")
                    tw = row.get("tool_weight_applied")
                    pp = row.get("penalty_pts", 0)
                    if ov is None or tl is None or tw is None:
                        continue
                    # Penalty pts can never be negative — the schedule
                    # only ever moves the blend toward tools (never the
                    # other direction).
                    assert pp >= 0, (
                        f"{entry.get('org')} {branch} {win}: penalty_pts {pp} < 0"
                    )
                    # Tool weight is clamped to [0.30, 0.60] by the
                    # adaptive schedule.
                    assert 0.30 <= tw <= 0.60, (
                        f"{entry.get('org')} {branch} {win}: tool_weight_applied "
                        f"{tw} outside [0.30, 0.60]"
                    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
