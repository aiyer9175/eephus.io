# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the prospect tool-development tracking system.

Covers:
  * `_compute_tool_deltas` — per-prospect, per-tool lifetime delta
    computation (first observation → latest) from a list of consensus
    points.
  * `TOOL_GROUPS` — the canonical tool-key grouping used to derive
    PowerDvM+ (= mean of game_pwr + raw_pwr) and friends.
  * End-to-end sanity check against the on-disk `data/timeseries.json`
    so a future export regression (e.g. accidentally stripping
    `tool_deltas` or `tool_dev`) breaks the suite. Skipped when the
    JSON file isn't present (vanilla CI without data)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from storage import (
    TOOL_GROUPS,
    _BUCKET_TOOL_IMPORTANCE,
    _bucket_weighted_tool_dvm,
    _compute_tool_deltas,
)

_TIMESERIES = Path(__file__).parent / "data" / "timeseries.json"


# ---------------------------------------------------------------------------
# _compute_tool_deltas — per-prospect helper
# ---------------------------------------------------------------------------

class TestComputeToolDeltas:
    def test_lifetime_delta_first_to_last(self):
        # Two snapshots, hit 50 → hit 55, delta = +5.
        out = _compute_tool_deltas([
            {"snapshot_date": "2023-01-01",
             "tools_consensus": {"hit": 50.0}},
            {"snapshot_date": "2024-08-15",
             "tools_consensus": {"hit": 55.0}},
        ])
        assert out["hit"]["delta"] == 5.0
        assert out["hit"]["first"] == 50.0
        assert out["hit"]["last"] == 55.0
        assert out["hit"]["first_date"] == "2023-01-01"
        assert out["hit"]["last_date"] == "2024-08-15"
        assert out["hit"]["n_obs"] == 2

    def test_negative_delta(self):
        out = _compute_tool_deltas([
            {"snapshot_date": "2023-01-01",
             "tools_consensus": {"speed": 60.0}},
            {"snapshot_date": "2024-08-15",
             "tools_consensus": {"speed": 55.0}},
            {"snapshot_date": "2025-02-01",
             "tools_consensus": {"speed": 50.0}},
        ])
        assert out["speed"]["delta"] == -10.0
        assert out["speed"]["n_obs"] == 3

    def test_skips_tools_with_one_observation(self):
        # `raw_pwr` only appears once → not in output (no delta computable).
        out = _compute_tool_deltas([
            {"snapshot_date": "2023-01-01",
             "tools_consensus": {"hit": 50.0, "raw_pwr": 60.0}},
            {"snapshot_date": "2024-08-15",
             "tools_consensus": {"hit": 55.0}},
        ])
        assert "hit" in out
        assert "raw_pwr" not in out

    def test_handles_out_of_order_snapshots(self):
        # Snapshots passed in reverse date order — sort happens internally.
        out = _compute_tool_deltas([
            {"snapshot_date": "2024-08-15",
             "tools_consensus": {"hit": 55.0}},
            {"snapshot_date": "2023-01-01",
             "tools_consensus": {"hit": 50.0}},
        ])
        assert out["hit"]["delta"] == 5.0
        assert out["hit"]["first"] == 50.0
        assert out["hit"]["last"] == 55.0

    def test_returns_empty_when_no_tools(self):
        out = _compute_tool_deltas([
            {"snapshot_date": "2023-01-01", "tools_consensus": {}},
            {"snapshot_date": "2024-08-15", "tools_consensus": None},
        ])
        assert out == {}

    def test_skips_none_values(self):
        # tools_consensus might carry an explicit None for a tool dropped
        # by all sources on that cycle — those shouldn't count as obs.
        out = _compute_tool_deltas([
            {"snapshot_date": "2023-01-01",
             "tools_consensus": {"hit": None}},
            {"snapshot_date": "2024-08-15",
             "tools_consensus": {"hit": 55.0}},
        ])
        assert "hit" not in out  # only 1 valid observation


# ---------------------------------------------------------------------------
# TOOL_GROUPS — canonical groupings used by per-tool DvM+
# ---------------------------------------------------------------------------

class TestToolGroups:
    def test_pwr_group_uses_consolidated_key(self):
        # v14 — PowerDvM+ reads the consolidated `pwr` key, which is
        # synthesized at the consensus layer from game_pwr + raw_pwr.
        # The legacy "power" group key was renamed to "pwr" to match the
        # per-source per-tool consolidation.
        assert TOOL_GROUPS["pwr"] == ["pwr"]

    def test_arm_maps_to_throw_canonical_key(self):
        # Display name "Arm" is fed by the canonical "throw" key.
        assert TOOL_GROUPS["arm"] == ["throw"]

    def test_all_canonical_keys_covered(self):
        # Every TOOL_GROUPS bucket must reference canonical tool keys.
        # v14 — `pwr` is now a canonical synthesized key (from game_pwr +
        # raw_pwr at consensus time), but isn't in HITTER_TOOL_KEYS yet
        # (which still lists the source-published keys). Allow it.
        from scrapers import HITTER_TOOL_KEYS, PITCHER_TOOL_KEYS
        all_canonical = set(HITTER_TOOL_KEYS) | set(PITCHER_TOOL_KEYS) | {"pwr"}
        all_grouped: set[str] = set()
        for keys in TOOL_GROUPS.values():
            all_grouped.update(keys)
        assert all_grouped <= all_canonical


# ---------------------------------------------------------------------------
# _bucket_weighted_tool_dvm — position-importance-weighted ToolDvM+ composite
# ---------------------------------------------------------------------------

class TestBucketWeightedToolDvm:
    def test_none_when_no_data(self):
        assert _bucket_weighted_tool_dvm({}, {}, {}) is None
        assert _bucket_weighted_tool_dvm(None, None, None) is None

    def test_falls_back_to_unweighted_mean_without_buckets(self):
        # No bucket data → legacy unweighted org-wide mean of per_grp.
        per_grp = {"hit": 110, "pwr": 90, "fb": 100}
        assert _bucket_weighted_tool_dvm(per_grp, {}, {}) == 100

    def test_position_importance_weights_dominant_tools(self):
        # A catcher-only org: Field=120, Arm=120 (high importance), but
        # Speed=80 (low importance, weight 0.5). The weighted composite
        # should sit far above the unweighted mean (which would be dragged
        # down by Speed). C weights: field 3, arm 3, hit 2, speed 0.5.
        per_grp = {"field": 120, "arm": 120, "hit": 100, "speed": 80}
        by_bucket = {"C": {"field": 120, "arm": 120, "hit": 100, "speed": 80}}
        counts = {"C": {"field": {"n_prospects": 5}, "arm": {"n_prospects": 5},
                        "hit": {"n_prospects": 5}, "speed": {"n_prospects": 5}}}
        out = _bucket_weighted_tool_dvm(per_grp, by_bucket, counts)
        unweighted = round((120 + 120 + 100 + 80) / 4)  # = 105
        assert out > unweighted  # importance weighting lifts the dominant tools
        # Exact: (3*120 + 3*120 + 2*100 + 0.5*80) / (3+3+2+0.5) = 960/8.5 ≈ 112.9
        assert out == 113

    def test_hybrid_fallback_to_org_wide_for_sparse_cell(self):
        # Bucket cell missing `arm` → falls back to org-wide per_grp value.
        per_grp = {"field": 100, "arm": 130}
        by_bucket = {"C": {"field": 100}}  # arm absent in the bucket cell
        counts = {"C": {"field": {"n_prospects": 4}}}
        out = _bucket_weighted_tool_dvm(per_grp, by_bucket, counts)
        # C weights present: field 3, arm 3, hit 2, bat_ctrl 1, pitch_sel 1,
        # pwr 1, speed 0.5 — only field (100) + arm (130 via fallback) resolve.
        # (3*100 + 3*130) / (3+3) = 690/6 = 115
        assert out == 115

    def test_bucket_blend_leans_toward_populated_bucket(self):
        # Two buckets: SP composite high with many prospects, C low with one.
        # The blend should land closer to SP than a flat bucket average.
        per_grp = {}
        by_bucket = {
            "SP": {"fb": 120, "cmd": 120},
            "C":  {"field": 80, "arm": 80},
        }
        counts = {
            "SP": {"fb": {"n_prospects": 20}, "cmd": {"n_prospects": 20}},
            "C":  {"field": {"n_prospects": 1}, "arm": {"n_prospects": 1}},
        }
        out = _bucket_weighted_tool_dvm(per_grp, by_bucket, counts)
        flat = round((120 + 80) / 2)  # = 100 if buckets weighted equally
        assert out > flat  # SP's larger prospect count pulls the blend up

    def test_matrix_only_references_canonical_tool_groups(self):
        valid = set(TOOL_GROUPS.keys())
        for bucket, weights in _BUCKET_TOOL_IMPORTANCE.items():
            assert set(weights) <= valid, f"{bucket} references unknown tool groups"


# ---------------------------------------------------------------------------
# End-to-end sanity against the exported timeseries.json
# ---------------------------------------------------------------------------

class TestExportedFields:
    def setup_method(self):
        if not _TIMESERIES.exists():
            pytest.skip(f"{_TIMESERIES} not present — skip e2e checks")
        with _TIMESERIES.open(encoding="utf-8") as fp:
            self.d = json.load(fp)

    def test_at_least_one_player_has_tool_deltas(self):
        # Sanity — if NO player has tool_deltas, the export hook is broken.
        count = sum(1 for p in self.d["players"] if p.get("tool_deltas"))
        assert count > 0, "no players carry tool_deltas — export hook broken?"

    def test_tool_delta_shape(self):
        # Find any player with deltas, verify the shape matches.
        p = next(p for p in self.d["players"] if p.get("tool_deltas"))
        for tool, info in p["tool_deltas"].items():
            assert "delta" in info and "first" in info and "last" in info
            assert "first_date" in info and "last_date" in info
            assert "n_obs" in info and info["n_obs"] >= 2
            assert info["delta"] == round(info["last"] - info["first"], 2)

    def test_every_org_has_tool_dev_field(self):
        orgs = (list(self.d["org_summary"].values())
                if isinstance(self.d["org_summary"], dict)
                else self.d["org_summary"])
        for o in orgs:
            assert "tool_dev" in o, f"{o['org']} missing tool_dev"
            assert "per_tool" in o["tool_dev"]
            assert "per_tool_dvm_plus" in o["tool_dev"]
            assert "tools_dvm_plus" in o["tool_dev"]

    def test_tools_dvm_plus_anchored_at_100(self):
        # League mean of the composite should sit very close to 100
        # since each per-tool DvM+ is itself anchored at 100. Allow
        # ±3 wiggle for the per-org-mean-of-means rounding.
        orgs = (list(self.d["org_summary"].values())
                if isinstance(self.d["org_summary"], dict)
                else self.d["org_summary"])
        vals = [o["tool_dev"]["tools_dvm_plus"] for o in orgs
                if o["tool_dev"].get("tools_dvm_plus") is not None]
        assert vals, "no orgs have a composite ToolsDvM+"
        mean = sum(vals) / len(vals)
        assert 97 <= mean <= 103, (
            f"ToolsDvM+ should be anchored at ~100 across the cohort; got {mean:.1f}"
        )

    def test_tools_dvm_plus_rank_uniqueish(self):
        orgs = (list(self.d["org_summary"].values())
                if isinstance(self.d["org_summary"], dict)
                else self.d["org_summary"])
        ranks = [o["tool_dev"].get("tools_dvm_plus_rank") for o in orgs
                 if o["tool_dev"].get("tools_dvm_plus_rank") is not None]
        # Every populated org has a rank; rank 1 exists; ranks fit in
        # the 1..n_orgs range.
        assert ranks, "no populated ranks"
        assert min(ranks) == 1
        assert max(ranks) <= len(orgs)
