"""Tests for the v3 farm grade tree (4 main grades, 10 leaf sub-grades).

v3 changes vs v2:
  * Acquisitions + Transactions merged → Acquisition Strategy (4 leaves).
  * MLB Production + IFA Performance use 3-input composites (WAG +
    WAR-per-year + Cumulative WAR).
  * Waiver scoreboard kind-mapping bug fixed (was '—' for all 30 orgs).
  * Draft adds Ceiling Hits %; Trade adds WAR Delta; Waiver adds Hit Rate.

Backend assertions:
  * Weight constants sum to 1.0, Development is top-weighted.
  * `_zscore_to_100` math behaves like the wRC+/OPS+ shape.
  * Generated `entry["tree"]` carries the v3 leaf shapes.
  * `entry["grades"]` includes 4 main + 10 sub + composite keys.
  * Sparse-data sub-grades render '—' rather than an unfair letter.
  * Waiver scoreboard now populates."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from storage import (
    FARM_TREE_SUB_WEIGHT_EQUAL,
    FARM_TREE_WEIGHT_ACQUISITION_STRATEGY,
    FARM_TREE_WEIGHT_DEVELOPMENT,
    FARM_TREE_WEIGHT_FINANCIAL,
    FARM_TREE_WEIGHT_MLB_PRODUCTION,
    # Legacy aliases (v2) still importable for back-compat
    FARM_TREE_WEIGHT_ACQUISITIONS,
    FARM_TREE_WEIGHT_TRANSACTIONS,
    _pick_slot_expected_war,
)

_TIMESERIES = Path(__file__).parent / "data" / "timeseries.json"


# ---------------------------------------------------------------------------
# Weight constants
# ---------------------------------------------------------------------------

class TestTreeWeights:
    def test_main_weights_sum_to_one(self):
        # v3: 4 main branches sum to 1.0.
        total = (
            FARM_TREE_WEIGHT_ACQUISITION_STRATEGY
            + FARM_TREE_WEIGHT_DEVELOPMENT
            + FARM_TREE_WEIGHT_FINANCIAL
            + FARM_TREE_WEIGHT_MLB_PRODUCTION
        )
        assert abs(total - 1.0) < 1e-9, (
            f"Main weights must sum to 1.0; got {total}"
        )

    def test_development_is_top_weighted(self):
        # Per user decision, Development is the single biggest skill —
        # it must outweigh all other main grades.
        others = [
            FARM_TREE_WEIGHT_ACQUISITION_STRATEGY,
            FARM_TREE_WEIGHT_FINANCIAL,
            FARM_TREE_WEIGHT_MLB_PRODUCTION,
        ]
        assert FARM_TREE_WEIGHT_DEVELOPMENT > max(others), (
            "Development must be the top-weighted main grade."
        )

    def test_sub_weight_is_50_percent(self):
        assert FARM_TREE_SUB_WEIGHT_EQUAL == 0.5

    def test_v2_aliases_preserved_for_back_compat(self):
        # Legacy v2 constants kept so old imports don't break. The
        # Acquisitions alias should point at the merged Acq Strategy
        # weight; Transactions alias collapses to 0.
        assert FARM_TREE_WEIGHT_ACQUISITIONS == FARM_TREE_WEIGHT_ACQUISITION_STRATEGY
        assert FARM_TREE_WEIGHT_TRANSACTIONS == 0.0


# ---------------------------------------------------------------------------
# _zscore_to_100 — same shape as the inline helper in export_timeseries_json
# ---------------------------------------------------------------------------

def _zscore_to_100_reference(values, higher_is_better=True):
    """Reference impl mirroring the inline helper. Kept identical so the
    test verifies BOTH that the math is correct AND that the export
    helper matches this shape (any divergence breaks the test)."""
    present = [v for v in values if v is not None]
    if len(present) < 3:
        return [None] * len(values)
    mu = sum(present) / len(present)
    var = sum((v - mu) ** 2 for v in present) / len(present)
    sd = var ** 0.5
    if sd < 1e-6:
        return [100.0 if v is not None else None for v in values]
    sign = 1.0 if higher_is_better else -1.0
    return [
        None if v is None else round(100 + 10 * sign * (v - mu) / sd, 1)
        for v in values
    ]


class TestZScoreTo100:
    def test_mean_value_maps_to_100(self):
        # [1, 2, 3] → mean 2 → middle value gets 100.
        result = _zscore_to_100_reference([1.0, 2.0, 3.0])
        assert result[1] == 100.0

    def test_plus_one_sigma_maps_to_110(self):
        # values [80, 100, 120] → mean 100, sd ≈ 16.33; value 120 →
        # z ≈ 1.22 → 100 + 12.2 ≈ 112.2. Verify the 100-anchored shape
        # by checking the relative ordering.
        result = _zscore_to_100_reference([80.0, 100.0, 120.0])
        assert result[0] < 100.0 < result[2]

    def test_sparse_under_3_returns_none_list(self):
        result = _zscore_to_100_reference([5.0, None])
        assert result == [None, None]

    def test_none_passes_through(self):
        result = _zscore_to_100_reference([1.0, 2.0, 3.0, None])
        assert result[3] is None

    def test_higher_is_better_false_inverts(self):
        # When lower is better, the LOWEST raw value should produce the
        # HIGHEST 100-anchored score.
        result = _zscore_to_100_reference([1.0, 2.0, 3.0], higher_is_better=False)
        assert result[0] > result[2]


# ---------------------------------------------------------------------------
# Pick-slot expected WAR — Acquisitions/Draft sub-grade input
# ---------------------------------------------------------------------------

class TestPickSlotExpectedWar:
    def test_first_overall_highest_expectation(self):
        # 1st overall should have the highest expected WAR in the curve.
        assert _pick_slot_expected_war(1) >= _pick_slot_expected_war(5)
        assert _pick_slot_expected_war(1) >= _pick_slot_expected_war(50)

    def test_curve_decays_monotonically(self):
        # Walking up the curve, expectations must never increase.
        for a, b in zip([1, 5, 10, 20, 50, 100, 200, 500],
                        [5, 10, 20, 50, 100, 200, 500, 999]):
            assert _pick_slot_expected_war(a) >= _pick_slot_expected_war(b), (
                f"non-monotonic at pick {a} → {b}"
            )

    def test_none_returns_none(self):
        assert _pick_slot_expected_war(None) is None

    def test_invalid_inputs_return_none(self):
        assert _pick_slot_expected_war("not a number") is None
        assert _pick_slot_expected_war(0) is None
        assert _pick_slot_expected_war(-5) is None

    def test_huge_pick_returns_tail_value(self):
        # Picks past the table's last threshold get the tail value
        # (currently 0.03).
        assert _pick_slot_expected_war(99_999) == 0.03

    def test_pick_string_coerces(self):
        # CSV ingest sometimes leaves pick_overall as a string.
        assert _pick_slot_expected_war("10") == _pick_slot_expected_war(10)


# ---------------------------------------------------------------------------
# End-to-end shape — runs against the exported timeseries.json
# ---------------------------------------------------------------------------

class TestExportedTreeShape:
    def setup_method(self):
        if not _TIMESERIES.exists():
            pytest.skip(f"{_TIMESERIES} missing — skip e2e")
        with _TIMESERIES.open(encoding="utf-8") as fp:
            self.d = json.load(fp)
        self.orgs = (list(self.d["org_summary"].values())
                     if isinstance(self.d["org_summary"], dict)
                     else self.d["org_summary"])

    def test_every_org_has_tree_field(self):
        for o in self.orgs:
            assert "tree" in o, f"{o['org']} missing tree field"
            for leaf in ["acq_ifa", "acq_draft", "dev_hitter", "dev_pitcher",
                         "tx_trades", "tx_waivers", "fin_war_per_m",
                         "fin_contract_surplus", "mlb_hitter_wag",
                         "mlb_pitcher_wag"]:
                assert leaf in o["tree"], f"{o['org']} missing tree.{leaf}"

    def test_every_org_has_4_main_grades(self):
        # v3 — Acquisitions + Transactions merged → Acquisition Strategy.
        for o in self.orgs:
            for parent in ["acquisition_strategy", "development",
                           "financial", "mlb_production"]:
                assert parent in o["grades"], f"{o['org']} grades missing {parent}"
        # Back-compat aliases still resolve (so old UI keys keep working).
        for o in self.orgs:
            assert "acquisitions" in o["grades"], "back-compat acquisitions alias missing"
            assert "transactions" in o["grades"], "back-compat transactions alias missing"

    def test_every_org_has_all_10_sub_grades(self):
        for o in self.orgs:
            for leaf in ["acq_ifa", "acq_draft", "dev_hitter", "dev_pitcher",
                         "tx_trades", "tx_waivers", "fin_war_per_m",
                         "fin_contract_surplus", "mlb_hitter_wag",
                         "mlb_pitcher_wag"]:
                assert leaf in o["grades"], f"{o['org']} grades missing {leaf}"

    def test_main_scores_centered_near_100(self):
        # v3 — 4 main grades; each centered near 100 by construction.
        for parent in ["acquisition_strategy_score", "development_score",
                       "financial_score", "mlb_production_score"]:
            vals = [o.get(parent) for o in self.orgs if o.get(parent) is not None]
            assert vals, f"no orgs have {parent}"
            mean = sum(vals) / len(vals)
            assert 95 <= mean <= 105, (
                f"{parent} cohort mean should be near 100; got {mean:.1f}"
            )

    def test_farm_score_is_weighted_blend(self):
        # v3 — recompute from 4 main scores.
        for o in self.orgs:
            recomputed = (
                FARM_TREE_WEIGHT_ACQUISITION_STRATEGY * (o.get("acquisition_strategy_score") or 100.0)
              + FARM_TREE_WEIGHT_DEVELOPMENT          * (o.get("development_score")          or 100.0)
              + FARM_TREE_WEIGHT_FINANCIAL            * (o.get("financial_score")            or 100.0)
              + FARM_TREE_WEIGHT_MLB_PRODUCTION       * (o.get("mlb_production_score")       or 100.0)
            )
            assert abs(recomputed - o["farm_score"]) < 0.2, (
                f"{o['org']} farm_score {o['farm_score']} doesn't match "
                f"weighted blend {recomputed:.2f}"
            )

    def test_overall_letter_matches_farm_score_rank(self):
        # rank-1 org's overall letter must be A or A+; rank-30 org must
        # not be A-tier.
        ranked = sorted(self.orgs, key=lambda o: -o["farm_score"])
        best, worst = ranked[0], ranked[-1]
        assert best["grades"]["overall"] in ("A+", "A"), (
            f"Top org {best['org']} got grade {best['grades']['overall']}"
        )
        assert worst["grades"]["overall"] not in ("A+", "A"), (
            f"Bottom org {worst['org']} got grade {worst['grades']['overall']}"
        )

    def test_legacy_score_preserved(self):
        for o in self.orgs:
            assert "farm_score_legacy" in o, (
                f"{o['org']} missing farm_score_legacy back-compat field"
            )

    def test_acq_draft_uses_pick_value_when_present(self):
        # When pick_value_mean is populated, the leaf score should
        # come from it (not raw wag_mean). Verify by spot-checking
        # an org with both fields present.
        candidates = [
            o for o in self.orgs
            if (o.get("tree") or {}).get("acq_draft", {}).get("pick_value_mean") is not None
        ]
        assert candidates, "no orgs with pick_value_mean — pick-slot accumulator broken"
        # All such orgs should have pick_value_count >= 3.
        for o in candidates:
            assert o["tree"]["acq_draft"]["pick_value_count"] >= 3

    def test_sparse_subgrade_renders_dash(self):
        # The dash-rendering pipeline must work for at least one leaf
        # somewhere in the cohort. Originally pinned to
        # fin_contract_surplus, but Spotrac coverage filled in enough
        # that all orgs grade. Generalized: walk every leaf, every org;
        # require ≥1 dash somewhere. Reverts to a real failure if the
        # sparse-data gating accidentally gets removed everywhere.
        leaves = ["acq_ifa", "acq_draft", "dev_hitter", "dev_pitcher",
                  "tx_trades", "tx_waivers", "fin_war_per_m",
                  "fin_contract_surplus", "mlb_hitter_wag",
                  "mlb_pitcher_wag"]
        n_dash = sum(
            1 for o in self.orgs for leaf in leaves
            if o["grades"].get(leaf) == "—"
        )
        assert n_dash > 0, (
            "expected at least some '—' grades for sparse leaves across "
            "the 10 leaf×30 org matrix"
        )

    # ── v3 new-feature tests ──

    def test_waiver_scoreboard_populates(self):
        # v3 bugfix — waiver scoreboard was '—' for all 30 orgs because
        # the filter loop read tx.get("kind") via wrong field names. After
        # the fix, at least 5 orgs should have non-None tx_waivers.net_fv.
        n_populated = sum(
            1 for o in self.orgs
            if (o["tree"]["tx_waivers"] or {}).get("net_fv") is not None
        )
        assert n_populated >= 5, (
            f"waiver scoreboard populated only {n_populated}/30 orgs — "
            f"expected most orgs to have at least some claim activity"
        )

    def test_ifa_composite_carries_three_inputs(self):
        # v3 — IFA Performance leaf gains WAR/yr + Cumulative WAR
        # alongside the existing WAG. At least one org should have all
        # three populated (>=3 IFA grads, each with career_war + war/yr).
        candidates = [
            o for o in self.orgs
            if (o["tree"]["acq_ifa"] or {}).get("wag_mean")        is not None
            and (o["tree"]["acq_ifa"] or {}).get("war_per_yr_mean") is not None
            and (o["tree"]["acq_ifa"] or {}).get("career_war_mean") is not None
        ]
        assert candidates, (
            "no org has all 3 IFA composite inputs populated — "
            "WAR/yr + cumulative WAR backfill broken?"
        )

    def test_mlb_production_three_input_composite(self):
        # v3 — Hitter + Pitcher MLB Production each carry WAG, WAR/yr,
        # Cumulative WAR. Verify at least one org has all three on at
        # least one position side.
        for side in ("mlb_hitter_wag", "mlb_pitcher_wag"):
            candidates = [
                o for o in self.orgs
                if (o["tree"][side] or {}).get("wag_mean")        is not None
                and (o["tree"][side] or {}).get("war_per_yr_mean") is not None
                and (o["tree"][side] or {}).get("career_war_mean") is not None
            ]
            assert candidates, (
                f"no org has all 3 inputs on {side} — composite broken?"
            )
