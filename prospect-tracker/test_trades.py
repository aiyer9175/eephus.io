# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
Tests for trade detection.

Covers:
- Org-change inference from snapshots (the always-on signal)
- Org alias normalization
- Reconciliation of API + inferred trades (the dedup logic)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from scrapers import Snapshot
from trades import (
    canonical_org, infer_trades_from_snapshots, reconcile_trades,
    detect_trades, Trade,
)


def _snap(source, name, date_, org, rank=None, fv=None, status="active",
          label="upd"):
    return Snapshot(
        source=source, snapshot_date=date_, interval_label=label,
        player_key=name.lower().replace(" ", "_"), player_name=name,
        position="SS", org=org, rank=rank, fv=fv, status=status,
    )


# ---------------------------------------------------------------------------
# Org normalization
# ---------------------------------------------------------------------------

class TestCanonicalOrg:
    def test_passthrough_for_codes(self):
        assert canonical_org("PIT") == "PIT"
        assert canonical_org("NYM") == "NYM"

    def test_full_name_to_code(self):
        assert canonical_org("Pirates") == "PIT"
        assert canonical_org("Pittsburgh") == "PIT"

    def test_case_insensitive(self):
        assert canonical_org("pirates") == "PIT"
        assert canonical_org("PIRATES") == "PIT"

    def test_none_passes_through(self):
        assert canonical_org(None) is None
        assert canonical_org("") is None

    def test_unknown_passthrough(self):
        # Unknown strings are returned as-is so we don't lose information
        assert canonical_org("Some Indy Team") == "Some Indy Team"


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

class TestInferTrades:
    def test_no_change_no_trade(self):
        snaps = [
            _snap("fangraphs",         "X", "2025-02-15", "PIT"),
            _snap("baseball_america",  "X", "2025-08-15", "PIT"),
            _snap("fangraphs",         "X", "2026-02-16", "PIT"),
        ]
        assert infer_trades_from_snapshots(snaps) == []

    def test_single_trade_detected(self):
        snaps = [
            _snap("fangraphs", "Walcott", "2026-02-16", "TEX"),
            _snap("tjstats",   "Walcott", "2026-05-13", "NYM"),
        ]
        trades = infer_trades_from_snapshots(snaps)
        assert len(trades) == 1
        t = trades[0]
        assert t.from_org == "TEX"
        assert t.to_org == "NYM"
        assert t.source == "inferred"
        assert t.date_range_start == "2026-02-16"
        assert t.date_range_end == "2026-05-13"
        assert t.trade_date == "2026-05-13"  # latest possible

    def test_org_aliases_normalized(self):
        """A source saying 'Rangers' and another saying 'TEX' is NOT a trade."""
        snaps = [
            _snap("fangraphs",       "X", "2026-02-16", "TEX"),
            _snap("mlb_pipeline",    "X", "2026-03-01", "Rangers"),
            _snap("baseball_america","X", "2026-05-13", "Texas"),
        ]
        assert infer_trades_from_snapshots(snaps) == []

    def test_same_day_majority_vote(self):
        """If 2 sources same day disagree on org, take the majority."""
        snaps = [
            # Day 1: 2 sources say PIT, 1 says BAL (stale) — majority PIT
            _snap("fangraphs",       "X", "2026-02-16", "PIT"),
            _snap("baseball_america","X", "2026-02-16", "PIT"),
            _snap("mlb_pipeline",    "X", "2026-02-16", "BAL"),
            # Day 2: all say BAL — trade!
            _snap("fangraphs",       "X", "2026-05-13", "BAL"),
            _snap("tjstats",         "X", "2026-05-13", "BAL"),
        ]
        trades = infer_trades_from_snapshots(snaps)
        assert len(trades) == 1
        assert trades[0].from_org == "PIT"
        assert trades[0].to_org == "BAL"

    def test_multiple_trades_sequential(self):
        snaps = [
            _snap("fangraphs", "Journeyman", "2025-02-15", "PIT"),
            _snap("fangraphs", "Journeyman", "2025-08-15", "BAL"),
            _snap("fangraphs", "Journeyman", "2026-02-16", "NYM"),
        ]
        trades = infer_trades_from_snapshots(snaps)
        assert len(trades) == 2
        assert (trades[0].from_org, trades[0].to_org) == ("PIT", "BAL")
        assert (trades[1].from_org, trades[1].to_org) == ("BAL", "NYM")


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

class TestReconcileTrades:
    def _api_trade(self, key, dt, from_org, to_org):
        return Trade(player_key=key, trade_date=dt, from_org=from_org,
                     to_org=to_org, source="mlb_api",
                     description="Test trade", date_range_start=None,
                     date_range_end=None)

    def _inferred_trade(self, key, start, end, from_org, to_org):
        return Trade(player_key=key, trade_date=end, from_org=from_org,
                     to_org=to_org, source="inferred",
                     description=None,
                     date_range_start=start, date_range_end=end)

    def test_api_only(self):
        api = [self._api_trade("walcott", "2026-07-31", "TEX", "NYM")]
        out = reconcile_trades(api, [])
        assert len(out) == 1
        assert out[0].source == "mlb_api"

    def test_inferred_only(self):
        inf = [self._inferred_trade("walcott", "2026-03-04", "2026-05-13",
                                     "TEX", "NYM")]
        out = reconcile_trades([], inf)
        assert len(out) == 1
        assert out[0].source == "inferred"

    def test_api_supersedes_inferred(self):
        """API trade within the inferred window -> drop the inferred."""
        api = [self._api_trade("walcott", "2026-04-15", "TEX", "NYM")]
        inf = [self._inferred_trade("walcott", "2026-03-04", "2026-05-13",
                                     "TEX", "NYM")]
        out = reconcile_trades(api, inf)
        assert len(out) == 1
        assert out[0].source == "mlb_api"
        assert out[0].trade_date == "2026-04-15"  # exact API date wins

    def test_api_outside_window_keeps_both(self):
        """If the inferred window doesn't cover the API date, both remain."""
        api = [self._api_trade("journeyman", "2026-08-15", "BAL", "NYM")]
        inf = [self._inferred_trade("journeyman", "2025-02-15", "2025-08-15",
                                     "PIT", "BAL")]
        out = reconcile_trades(api, inf)
        assert len(out) == 2  # Different trades — both kept

    def test_different_orgs_kept_separately(self):
        """Same player, two different trades — keep both."""
        api = [self._api_trade("journeyman", "2026-07-31", "BAL", "NYM")]
        inf = [self._inferred_trade("journeyman", "2025-02-15", "2025-08-15",
                                     "PIT", "BAL")]
        out = reconcile_trades(api, inf)
        assert len(out) == 2


# ---------------------------------------------------------------------------
# End-to-end without API
# ---------------------------------------------------------------------------

class TestDetectTrades:
    def test_offline_uses_inference_only(self):
        snaps = [
            _snap("fangraphs", "X", "2026-02-16", "TEX"),
            _snap("tjstats",   "X", "2026-05-13", "NYM"),
        ]
        trades = detect_trades(snaps, tracked_players=None, skip_api=True)
        assert len(trades) == 1
        assert trades[0].source == "inferred"

    def test_empty_snapshots_no_trades(self):
        assert detect_trades([], tracked_players=None, skip_api=True) == []


def test_the_tier_claim_matches_the_eval_it_cites():
    """"Grade wins within every tier" sat in the code, the registry and the
    Grade column tooltip for months, and the eval it cites contradicts it.

    Measured in slice_a.by_tier: elite 0.2328 against 0.1490, high 0.2485
    against 0.1507, mid 0.2536 against 0.0820, and low 0.0683 against 0.0816,
    where GRADE LOSES. Low holds 1,301 of the 2,333 scored rows, more than the
    other three tiers combined, so the claim was wrong about the majority of the
    board it existed to justify.

    This reads the ARTIFACT rather than the prose, so it stays correct if the
    eval is ever re-run: if grade does come to win everywhere, this passes and
    the copy can be changed back deliberately rather than by drift.
    """
    import json
    import pytest
    root = Path(__file__).resolve().parent
    p = root / "data" / "trade_machine_eval.json"
    if not p.exists():
        pytest.skip("trade_machine_eval.json not built")
    by_tier = ((json.loads(p.read_text(encoding="utf-8")).get("slice_a") or {})
               .get("by_tier") or {})
    if not by_tier:
        pytest.skip("no by_tier block")
    losing = [t for t, v in by_tier.items()
              if v.get("xfv_grade_spearman") is not None
              and v.get("spearman") is not None
              and v["xfv_grade_spearman"] < v["spearman"]]
    src = (root / "assets" / "trademachine.js").read_text(encoding="utf-8")
    reg = (root / "data" / "model_registry.json").read_text(encoding="utf-8")
    if losing:
        for where, text in (("trademachine.js", src), ("model_registry.json", reg)):
            assert "wins within every tier" not in text, (
                f"{where} claims grade wins in every tier while the eval has it "
                f"losing in {losing}")
            assert "wins inside every tier" not in text, where


def test_the_tier_the_claim_was_wrong_about_is_the_biggest_one():
    """Recorded because it is what makes the correction material rather than
    pedantic: the tier where the claim fails holds more rows than the rest of
    the board put together."""
    import json
    import pytest
    root = Path(__file__).resolve().parent
    p = root / "data" / "trade_machine_eval.json"
    if not p.exists():
        pytest.skip("trade_machine_eval.json not built")
    by_tier = ((json.loads(p.read_text(encoding="utf-8")).get("slice_a") or {})
               .get("by_tier") or {})
    if not by_tier:
        pytest.skip("no by_tier block")
    biggest = max(by_tier, key=lambda t: by_tier[t].get("n") or 0)
    others = sum(v.get("n") or 0 for t, v in by_tier.items() if t != biggest)
    assert (by_tier[biggest].get("n") or 0) > others, (
        "the largest tier no longer outweighs the rest, so the materiality "
        "argument in the correction needs re-reading")
