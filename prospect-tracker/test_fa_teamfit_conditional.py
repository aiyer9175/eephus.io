# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""TEAMFIT CONDITIONAL gate guards (2026-08-19).

Three contracts: (1) the band helpers are player-conditional pure math,
(2) the artifact's teamfit_conditional_gate block recomputes to its own
verdicts from its own numbers (no invented booleans), (3) the frozen band
factor is one number in three places - code constant, fa_config, artifact -
and the config flag can only read true after a shipped gate. Gate doc:
docs/fa-2026-08-19/TEAMFIT_CONDITIONAL_GATE.md."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import fa_fit_backtest as g3

ROOT = Path(__file__).parent


def _artifact_block():
    p = ROOT / "data" / "fa_gate3_eval.json"
    if not p.exists():
        pytest.skip("gate3 artifact not generated on this machine")
    d = json.loads(p.read_text(encoding="utf-8"))
    blk = d.get("teamfit_conditional_gate")
    if not blk:
        pytest.skip("teamfit_conditional_gate block not in artifact yet")
    return blk


def _cfg_fit():
    return yaml.safe_load(
        (ROOT / "fa_config.yaml").read_text(encoding="utf-8"))["fit"]


# ---------------------------------------------------------------------------
# (1) pure band math
# ---------------------------------------------------------------------------

def test_band_bounds():
    lo, hi = g3._cond_band(10_000_000)
    assert lo == pytest.approx(10_000_000 / g3.TEAMFIT_COND_BAND_FACTOR)
    assert hi == pytest.approx(10_000_000 * g3.TEAMFIT_COND_BAND_FACTOR)
    assert lo < 10_000_000 < hi


def test_cond_terms_are_player_conditional():
    """The registered defect: a mega-deal club's behavior leaked onto cheap
    relievers. Banded terms must give the SAME club different terms for
    different prices - the whole point of the lever."""
    events = [(2025, 300_000_000), (2024, 250_000_000), (2023, 8_000_000)]
    # cheap reliever, $8M: band [3.2M, 20M] catches only the $8M deal
    outlay, n = g3._cond_terms(events, 8_000_000, 2023)
    assert n == 1 and outlay == pytest.approx(8_000_000)
    # mega star, $300M: band [120M, 750M] catches the two mega deals
    outlay, n = g3._cond_terms(events, 300_000_000, 2023)
    assert n == 2 and outlay == pytest.approx(550_000_000)
    # recency window: y_min above an event's year drops its outlay, not its count
    outlay, n = g3._cond_terms(events, 300_000_000, 2025)
    assert n == 2 and outlay == pytest.approx(300_000_000)


def test_cond_terms_empty_history():
    assert g3._cond_terms([], 20_000_000, 2020) == (0.0, 0)


# ---------------------------------------------------------------------------
# (2) artifact block recomputes to its own verdicts
# ---------------------------------------------------------------------------

def test_block_clauses_recompute_from_own_numbers():
    blk = _artifact_block()
    g = blk["thresholds"]
    cand, mde = blk["chain_candidate"], blk["mde95"]
    c1 = (cand["mrr"] >= g["mrr_floor_anchor"] - mde
          and cand["top3"] >= g["top3_floor_anchor"] - mde)
    assert blk["clauses"]["1_accuracy_floor"] == c1
    sv = blk["served"]
    if sv.get("available"):
        cc = sv["candidate_composite"]
        c2 = (cc["max_top1_share"] < g["max_top1_share"]
              and cc["distinct_top1"] >= g["min_distinct_top1"]
              and cc["distinct_top3"] >= g["min_distinct_top3"])
        c3 = sv["lad_behavior_cond_top1_share"] < g["lad_behavior_majority"]
        assert blk["clauses"]["2_concentration"] == c2
        assert blk["clauses"]["3_lad_sanity"] == c3
        assert blk["clauses"]["4_trade_refusal_fired"] == (
            (c2 and not c1) or (c1 and not c2))
        assert blk["shipped"] == (c1 and c2 and c3)
    assert blk["mrr_delta"] == pytest.approx(
        cand["mrr"] - blk["chain_incumbent"]["mrr"], abs=1e-3)


def test_block_thresholds_match_frozen_constants():
    blk = _artifact_block()
    assert blk["thresholds"] == g3.TEAMFIT_COND_GATE
    assert blk["band_factor"] == g3.TEAMFIT_COND_BAND_FACTOR


# ---------------------------------------------------------------------------
# (3) config <-> code <-> artifact sync
# ---------------------------------------------------------------------------

def test_band_factor_synced_to_config():
    fit = _cfg_fit()
    assert fit.get("behavior_cond_band_factor") == g3.TEAMFIT_COND_BAND_FACTOR


def test_config_flag_requires_shipped_gate():
    """fa_config.fit.behavior_conditional may only read true after the gate's
    artifact block says shipped - the flag must never precede the evidence.
    (It ships FALSE until fa_fit.fit_scores wires the band terms behind it.)"""
    fit = _cfg_fit()
    flag = fit.get("behavior_conditional")
    assert isinstance(flag, bool)
    if flag:
        assert _artifact_block()["shipped"] is True
