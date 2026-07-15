# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""E-STALE serve-time anchor decay - schedule math + wiring pins.

The Nathan Hickey class (2026-07-14): active players whose consensus anchor is
frozen at a long-past list appearance were scored as if the anchor were fresh.
The decay lives in efv_dataset (schedule constants pinned to the ledger in
test_phase4b_evals), feeds efv_model._vec's fv feature and the scorer's
consensus blend leg, and NEVER touches the displayed consensus."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import efv_dataset as ed
from efv_model import _vec

TODAY = date(2026, 7, 14)


def _disc(asof, fv):
    return ed._stale_anchor_discount(asof, fv, today=TODAY)


def test_fresh_anchor_no_decay():
    assert _disc("2026-01-22", 45.0) == 0.0          # ~6 months: inside cadence
    assert _disc("2025-02-01", 40.0) == 0.0          # ~17.4 months: still inside


def test_ramp_and_terminal():
    # ~24 months -> half ramp; ~36 months -> full terminal
    half = _disc("2024-07-14", 40.0)
    assert 4.0 < half < 6.0
    assert _disc("2023-07-01", 40.0) == ed.STALE_ANCHOR_TERMINAL[40]
    # the Hickey case: 2024-01-22 anchor, FV45 -> near-terminal
    h = _disc("2024-01-22", 45.0)
    assert 9.0 <= h <= ed.STALE_ANCHOR_TERMINAL[45]


def test_ungrounded_bands_never_decay():
    """Only bands with held-out ground truth (35-45) decay; a stale FV 50+ or
    sub-35 anchor is left alone rather than extrapolated."""
    assert _disc("2023-01-01", 50.0) == 0.0
    assert _disc("2023-01-01", 55.0) == 0.0
    assert _disc("2023-01-01", 30.0) == 0.0


def test_missing_inputs_are_safe():
    assert _disc(None, 45.0) == 0.0
    assert _disc("2024-01-22", None) == 0.0
    assert _disc("garbage", 45.0) == 0.0


def test_vec_prefers_effective_anchor():
    row = {"player_key": "x", "kind": "active", "consensus_fv_raw": 45.0,
           "fv_effective": 35.5, "milb": {"age": 26.0}}
    assert _vec(row, "hit")["fv"] == 35.5
    # training rows (no fv_effective) fall through to raw
    row2 = {"player_key": "y", "kind": "debuted", "consensus_fv_raw": 45.0,
            "milb": {"age": 22.0}}
    assert _vec(row2, "hit")["fv"] == 45.0


def test_display_consensus_untouched_in_live_rows():
    """build_live_matrix must decay fv_effective ONLY - consensus_fv_raw is
    what every display surface joins on."""
    src = (Path(__file__).parent / "efv_dataset.py").read_text(encoding="utf-8")
    assert 'row["fv_effective"] = round(row["consensus_fv_raw"] - _disc, 2)' in src
    scorer = (Path(__file__).parent / "efv_score.py").read_text(encoding="utf-8")
    # the blend's consensus leg prices the decayed anchor...
    assert "_cons_anchor = float(_fv_eff) if _fv_eff is not None else cons_fv" in scorer
    # ...while the exported consensus_fv field stays the raw consensus
    assert '"consensus_fv": round(cons_fv, 1)' in scorer
