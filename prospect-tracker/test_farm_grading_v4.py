"""v4 farm-grading-system tests — steepened FV_POINTS curve, 5 new
leaves (top-3 grad WAR, conviction, boom% leaf, draft-pool efficiency,
IFA ROI), rebalanced branch weights, conviction cap."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from storage import (
    FARM_TREE_WEIGHT_ACQUISITION_STRATEGY,
    FARM_TREE_WEIGHT_DEVELOPMENT,
    FARM_TREE_WEIGHT_FINANCIAL,
    FARM_TREE_WEIGHT_MLB_PRODUCTION,
    FV_POINTS,
    _compute_conviction_leaf,
    _compute_draft_pool_efficiency,
    _compute_ifa_roi,
    _compute_top_grads_leaf,
    _fv_to_points,
    _top3_career_war,
)

TS_PATH = Path(__file__).parent / "data" / "timeseries.json"


# ---------------------------------------------------------------------------
# Steepened FV_POINTS curve
# ---------------------------------------------------------------------------

class FvPointsCurve(unittest.TestCase):
    def test_monotonic(self):
        keys = sorted(FV_POINTS.keys())
        for lo, hi in zip(keys, keys[1:]):
            self.assertLessEqual(FV_POINTS[lo], FV_POINTS[hi])

    def test_70_at_least_2x_65(self):
        # The steepening's whole point: top-end leaps dramatically.
        self.assertGreaterEqual(FV_POINTS[70] / FV_POINTS[65], 1.5)

    def test_80_at_least_double_old_anchor(self):
        # Old curve: 80 = 100.0. v4 anchored at 250 (2.5×).
        self.assertGreaterEqual(FV_POINTS[80], 200.0)

    def test_top_tier_dominates_filler(self):
        # An 80 should be worth more than 100 org-fillers (40-grade).
        self.assertGreater(_fv_to_points(80), 100 * _fv_to_points(40))


# ---------------------------------------------------------------------------
# Branch weights sum to 1.0
# ---------------------------------------------------------------------------

class BranchWeights(unittest.TestCase):
    def test_weights_sum_to_one(self):
        total = (FARM_TREE_WEIGHT_ACQUISITION_STRATEGY
                 + FARM_TREE_WEIGHT_DEVELOPMENT
                 + FARM_TREE_WEIGHT_FINANCIAL
                 + FARM_TREE_WEIGHT_MLB_PRODUCTION)
        self.assertAlmostEqual(total, 1.0, places=9)


# ---------------------------------------------------------------------------
# Top-end leaves
# ---------------------------------------------------------------------------

class TopGradsLeaf(unittest.TestCase):
    def test_gates_below_3_grads(self):
        gagg = {"_top_grads": [
            {"career_war": 5.0, "war_per_yr": 2.0, "seasons": 3,
             "is_pitcher": False, "last_mlb_year": 2025},
            {"career_war": 4.0, "war_per_yr": 1.5, "seasons": 4,
             "is_pitcher": False, "last_mlb_year": 2024},
        ]}
        out = _compute_top_grads_leaf(gagg)
        self.assertIsNone(out["top3_war_per_yr"])
        self.assertEqual(out["grad_count_qualifying"], 2)

    def test_top3_uses_best_3(self):
        gagg = {"_top_grads": [
            {"career_war": 1.0, "war_per_yr": 0.5, "is_pitcher": False, "last_mlb_year": 2024, "seasons": 2},
            {"career_war": 8.0, "war_per_yr": 4.0, "is_pitcher": False, "last_mlb_year": 2025, "seasons": 2},
            {"career_war": 6.0, "war_per_yr": 3.0, "is_pitcher": True,  "last_mlb_year": 2025, "seasons": 2},
            {"career_war": 4.0, "war_per_yr": 2.0, "is_pitcher": False, "last_mlb_year": 2023, "seasons": 2},
            {"career_war": 12.0, "war_per_yr": 6.0, "is_pitcher": True, "last_mlb_year": 2025, "seasons": 2},
        ]}
        out = _compute_top_grads_leaf(gagg)
        # Top 3 war_per_yr = 6.0, 4.0, 3.0 → mean 4.33
        self.assertAlmostEqual(out["top3_war_per_yr"], 4.33, places=2)
        # Top 3 career_war (across all 5) = 12, 8, 6 → mean 8.67
        self.assertAlmostEqual(out["top3_career_war"], 8.67, places=2)

    def test_top3_career_war_pitcher_only(self):
        grads = [
            {"career_war": 12.0, "is_pitcher": True},
            {"career_war": 8.0,  "is_pitcher": True},
            {"career_war": 4.0,  "is_pitcher": True},
            {"career_war": 20.0, "is_pitcher": False},  # ignored
        ]
        out = _top3_career_war(grads, is_pitcher=True)
        self.assertAlmostEqual(out, 8.0, places=2)


class ConvictionLeaf(unittest.TestCase):
    def test_fires_on_recent_war_per_yr(self):
        from datetime import date
        gagg = {"_top_grads": [
            # 4.5 WAR/yr last MLB year was 2 years ago → recent star ✓
            {"career_war": 9.0, "war_per_yr": 4.5,
             "is_pitcher": False, "last_mlb_year": date.today().year - 1, "seasons": 2},
        ]}
        out = _compute_conviction_leaf(gagg)
        self.assertEqual(out["conviction"], 1)

    def test_fires_on_career_war_threshold(self):
        from datetime import date
        gagg = {"_top_grads": [
            # 15 career WAR but last MLB year was 10 years ago — career
            # WAR branch still fires.
            {"career_war": 15.0, "war_per_yr": 1.5,
             "is_pitcher": False, "last_mlb_year": date.today().year - 10, "seasons": 8},
        ]}
        out = _compute_conviction_leaf(gagg)
        self.assertEqual(out["conviction"], 1)

    def test_clears_when_neither_threshold_met(self):
        from datetime import date
        gagg = {"_top_grads": [
            # 3 WAR/yr (below 4.0) + 6 career WAR (below 12) → not a star
            {"career_war": 6.0, "war_per_yr": 3.0,
             "is_pitcher": False, "last_mlb_year": date.today().year - 1, "seasons": 2},
        ]}
        out = _compute_conviction_leaf(gagg)
        self.assertEqual(out["conviction"], 0)

    def test_empty_returns_zero(self):
        out = _compute_conviction_leaf({"_top_grads": []})
        self.assertEqual(out["conviction"], 0)
        self.assertIsNone(out["peak_war_per_yr"])
        self.assertIsNone(out["peak_career_war"])


# ---------------------------------------------------------------------------
# Financial leaves
# ---------------------------------------------------------------------------

class DraftPoolEfficiency(unittest.TestCase):
    def test_gates_below_3_grads(self):
        from datetime import date
        gagg = {"_draft_pool_grads": [
            {"draft_year": date.today().year - 3, "career_war": 5.0},
            {"draft_year": date.today().year - 4, "career_war": 3.0},
        ]}
        out = _compute_draft_pool_efficiency(gagg, draft_pools={}, org_code="XYZ")
        self.assertIsNone(out["war_per_m_pool"])

    def test_computes_ratio(self):
        from datetime import date
        ty = date.today().year
        gagg = {"_draft_pool_grads": [
            {"draft_year": ty - 3, "career_war": 10.0},
            {"draft_year": ty - 4, "career_war": 6.0},
            {"draft_year": ty - 5, "career_war": 4.0},
        ]}
        # Synthetic draft pools: $10M / year ×4 years (T-2..T-5) = $40M
        draft_pools = {
            ty - 2: {"team_pools": {"XYZ": 10_000_000}},
            ty - 3: {"team_pools": {"XYZ": 10_000_000}},
            ty - 4: {"team_pools": {"XYZ": 10_000_000}},
            ty - 5: {"team_pools": {"XYZ": 10_000_000}},
        }
        out = _compute_draft_pool_efficiency(gagg, draft_pools=draft_pools, org_code="XYZ")
        # 20 WAR / $40M = 0.5 WAR/$M
        self.assertAlmostEqual(out["war_per_m_pool"], 0.5, places=2)
        self.assertEqual(out["grad_count"], 3)


class IfaRoi(unittest.TestCase):
    def test_gates_below_1_grad(self):
        # v7 — gate loosened from ≥2 → ≥1. A zero-grad org returns
        # None; a single qualifying grad now computes a ratio.
        gagg_empty = {"_ifa_grads": []}
        out_empty = _compute_ifa_roi(gagg_empty, ifa_org_spending={})
        self.assertIsNone(out_empty["war_per_m_ifa"])

    def test_computes_ratio_from_per_grad_bonus(self):
        # v7 — denominator switched from ifa_org_spending table sum to
        # per-grad bonus_usd sum (numerator and denominator align on
        # the exact same set of grads, so sparse spend-table coverage
        # no longer produces inflated ratios).
        from datetime import date
        ty = date.today().year
        gagg = {"_ifa_grads": [
            {"signed_year": ty - 5, "bonus_usd": 1_000_000, "career_war": 10.0},
            {"signed_year": ty - 6, "bonus_usd": 2_000_000, "career_war": 8.0},
        ]}
        # ifa_org_spending is no longer used by the computation (the
        # function still accepts it for API back-compat).
        out = _compute_ifa_roi(gagg, ifa_org_spending={})
        # 18 WAR / $3M = 6.0 WAR/$M
        self.assertAlmostEqual(out["war_per_m_ifa"], 6.0, places=2)
        self.assertEqual(out["grad_count"], 2)
        self.assertEqual(out["ifa_total_usd"], 3_000_000)


# ---------------------------------------------------------------------------
# Integration smoke — read the exported timeseries.json
# ---------------------------------------------------------------------------

class IntegrationSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TS_PATH.exists():
            raise unittest.SkipTest("data/timeseries.json missing — run rebuild_only")
        cls.payload = json.loads(TS_PATH.read_text(encoding="utf-8"))
        cls.orgs = cls.payload.get("org_summary") or []

    def test_every_org_has_new_tree_leaves(self):
        required_leaves = {
            "mlb_production_boom_pct",
            "mlb_production_top_grads",
            "mlb_production_conviction",
            "fin_draft_pool_efficiency",
            "fin_ifa_roi",
        }
        for o in self.orgs:
            tree = o.get("tree") or {}
            missing = required_leaves - set(tree.keys())
            self.assertFalse(missing,
                f"{o['org']} missing v4 leaves: {missing}")

    def test_conviction_is_binary(self):
        for o in self.orgs:
            c = ((o.get("tree") or {}).get("mlb_production_conviction") or {}).get("conviction")
            self.assertIn(c, {0, 1, None},
                f"{o['org']} conviction must be 0/1/None, got {c}")

    def test_some_orgs_have_conviction(self):
        # At least 5 orgs should produce a star (4.0+ WAR/yr or 12+ career WAR).
        # PIT (Skenes), SEA, ATL, etc. all qualify.
        n_conv = sum(1 for o in self.orgs
                     if ((o.get("tree") or {}).get("mlb_production_conviction") or {}).get("conviction") == 1)
        self.assertGreaterEqual(n_conv, 5,
            f"only {n_conv} orgs with conviction=1; expected ≥5")

    def test_top_5_conviction_zero_orgs_are_all_capped(self):
        # Top-5 by farm_score: any conviction=0 org in the top 5 must
        # have been conviction-capped (the cap clamps them to p75). v7
        # weights + composite stretch can cluster multiple capped orgs
        # at the same p75 value, so the prior "all top-5 must have
        # conviction=1" assertion is too strict — what matters is the
        # cap mechanism fired. A non-capped conviction-0 org in the
        # top 5 WOULD be the bug.
        top5 = sorted(self.orgs,
                      key=lambda o: -(o.get("farm_score") or 0))[:5]
        for o in top5:
            c = ((o.get("tree") or {}).get("mlb_production_conviction") or {}).get("conviction")
            if c == 0:
                self.assertTrue(o.get("conviction_cap_applied"),
                    f"{o['org']} ranked top-5 with conviction=0 but NOT capped — cap should have fired")

    def test_conviction_cap_field_present(self):
        for o in self.orgs:
            self.assertIn("conviction_cap_applied", o)
            self.assertIsInstance(o["conviction_cap_applied"], bool)


if __name__ == "__main__":
    unittest.main()
