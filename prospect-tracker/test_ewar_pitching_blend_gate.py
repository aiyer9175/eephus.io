# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR pitching blend read's registration pins
(docs/ewar-v3/EWAR_PITCHING_BLEND_GATE.md, task EWAR_PITCHING_BLEND, owner EW3-50).

The registration is committed ALONE, before any number of its estimands exists. Every
clause that binds the read is pinned by the sentence that makes it bind. Prose
assertions run against a whitespace-flattened copy of the document, so re-wrapping a
paragraph is not a test failure.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "ewar-v3" / "EWAR_PITCHING_BLEND_GATE.md"


def _flat() -> str:
    return re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))


def test_document_names_itself_and_this_test():
    text = _flat()
    assert text.startswith("# eWAR pitching blend: a reliability-weighted combination of FIP-based "
                           "and runs-allowed-based pitching runs (pre-registration, 2026-10-22)")
    assert "This document is committed ALONE, before any number of its estimands is computed" in text
    assert "`test_ewar_pitching_blend_gate.py`" in text
    assert "## 14. Results" in text


def test_scope_and_not_a_reopened_arm():
    text = _flat()
    assert "**The candidate is a weight, not a new run construction.**" in text
    assert "It is not S2 or S2b" in text
    assert "`data/_labs/ewar_pitching_blend/record.json`" in text


def test_sources_and_blend():
    text = _flat()
    for clause in ("F9_j = lgFIP_s * (100 - fipMinus_j) / 100",
                   "B9_j = 9 * sum over stints of runs_above_avg / (sum over stints of IPouts / 3)",
                   "blend9_j = w_j * F9_j + (1 - w_j) * B9_j",
                   "role_j = SP when gamesStarted / gamesPitched >= 0.5, else RP"):
        assert clause in text, clause


def test_split_half_and_weight():
    text = _flat()
    for clause in ("F_h = -(13 HR_h + 3 (BB_h + HBP_h) - 2 K_h) / IP_h",
                   "B_h = -9 R_h / IP_h",
                   "sigma2_F = sum_j (F_odd - F_even)^2 / sum_j h_j",
                   "sigma_FB = sum_j (F_odd - F_even)(B_odd - B_even) / sum_j h_j",
                   "Sigma_T = Sigma_obs - Sigma_E * mean_j(1 / IP_j)",
                   "beta_j = (Sigma_T + Sigma_E / IP_j)^(-1) * Sigma_T[:, B]",
                   "w_j = beta_F / (beta_F + beta_B), clamped to [0, 1]"):
        assert clause in text, clause
    assert "fitted on the seasons 2016 to Y - 1 (2020 out) only" in text
    assert "every run scored is charged to the scoring runner's owner" in text


def test_test_i():
    text = _flat()
    assert "Y in {2017, 2018, 2021, 2022, 2023, 2024}" in text
    assert "`g(K) = rho(blend9) - rho(K)`, K in {F9, B9}" in text
    assert "**Two bootstraps, B = 4,000 each, seed 20261023,**" in text
    assert "`p(K, k) = 1 - Phi(g(K) / sd_k)`" in text and "`p_i = max over K and k`" in text


def test_test_ii_and_holm():
    text = _flat()
    assert "D_j = d_j - IP_j * (sum_k d_k) / (sum_k IP_k)" in text
    assert "**Margin M = 1.0 run**" in text
    assert "`d - 1.645 sd_k > -M` under all three bootstraps" in text
    assert "`p_ii = max over k of 1 - Phi((d + M) / sd_k)`" in text
    assert ("Holm at family-wise 0.05 over {p_i, p_ii}: the smaller p must be at or below 0.025 and "
            "the larger at or below 0.05") in text


def test_nulls_and_planted():
    text = _flat()
    assert "**No-change null.** F9 (w = 1 everywhere)" in text
    assert "**Identity check.** The blend with every w = 1 gives g(F9) = 0 exactly" in text
    assert "**PLANTED PASS** when the truth world passes in at least 16 of 20 replicates" in text
    assert "the fake world in at most 1 of 20" in text
    assert "within 0.10 of the oracle weight" in text


def test_licence_bans_and_owner_question():
    text = _flat()
    assert "**ADOPT licenses nothing served by itself.**" in text
    assert "`ewar_v3.PITCH_BLEND_LIVE` (default False)" in text
    assert "EWPB-Q1 (a) record only, nothing served (default)" in text
    assert "`docs/PROSPECT_ANCHOR_GATE.md`" in text
    assert "`backtest.run_backtest`" in text
    assert "A second `--read` refuses while the record exists." in text
