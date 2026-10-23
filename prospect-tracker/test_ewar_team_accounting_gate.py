# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR team accounting read's registration pins
(docs/ewar-v3/EWAR_TEAM_ACCOUNTING_GATE.md, task EWAR_TEAM_ACCOUNTING, owner EW3-50).

The registration is committed ALONE, before any number of its estimands exists. Every
clause that binds the read is pinned by the sentence that makes it bind. Prose
assertions run against a whitespace-flattened copy of the document, so re-wrapping a
paragraph is not a test failure.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "ewar-v3" / "EWAR_TEAM_ACCOUNTING_GATE.md"


def _flat() -> str:
    return re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))


def test_document_names_itself_and_this_test():
    text = _flat()
    assert text.startswith("# eWAR team accounting: do summed values track club runs and wins "
                           "(pre-registration, 2026-10-22)")
    assert "This document is committed ALONE, before any number of its estimands is computed" in text
    assert "`test_ewar_team_accounting_gate.py`" in text
    assert "## 14. Results" in text


def test_scope_is_realized_and_descriptive():
    text = _flat()
    assert "**A descriptive validity read of eWAR realized, decided once, and nothing served moves on it.**" in text
    assert "It is not a re-score of any predictive cell that failed" in text
    assert "**The headline eWAR is reported, deciding nothing** (part 2)." in text
    assert "`data/_labs/ewar_team_accounting/record.json`" in text


def test_frame_and_allocation():
    text = _flat()
    assert "Primary: seasons 2016 to 2019 and 2021 to 2025, 30 clubs each, 270 club-seasons." in text
    assert "plate appearances on the bat side, IPouts on the pit side" in text
    assert "the read stops if the unallocated absolute value exceeds 1.0 win in any season on any series" in text


def test_estimands_and_runs_per_win():
    text = _flat()
    for clause in ("tau_s = sum_c T_c / sum_c G_c",
                   "W_hat = G_c / 2 + (T_c - tau_s * G_c)",
                   "RD_hat = RPW_c * (T_c - tau_s * G_c)",
                   "RS_hat = r_s * G_c + RPW_c * (Hs_c - eta_s * G_c)",
                   "RA_hat = r_s * G_c - RPW_c * (Ps_c - pi_s * G_c)",
                   "Rsq(X, y) = 1 - sum (y - y_hat)^2 / sum (y - mean(y))^2",
                   "`d(X) = RMSE(X, y) - RMSE(E, y)`",
                   "`W0_hat = (0.5 - 1000 / 4860) * G_c + T_c`"):
        assert clause in text, clause
    assert "`league_constants.league_totals(s)[\"rpw\"]`" in text
    assert "`ewar.runs_per_win` (`by_team`, falling back to the season's value)" in text
    assert "Deciding: wins and run differential on the total sums (T)." in text


def test_bootstraps_nulls_and_planted_check():
    text = _flat()
    assert "**Three bootstraps, B = 4,000 each, seed 20261023,**" in text
    for kind in ("season-clustered:", "club-clustered:", "player-clustered:"):
        assert kind in text
    assert "1,000 permutations from a generator seeded 20261023" in text
    assert "**PLANTED PASS** when the truth candidate reads PASS in at least 16 of 20 replicates" in text
    assert "e1 normal with sd 40 runs" in text and "e2 normal with sd 4 wins" in text


def test_pass_rule():
    text = _flat()
    assert "on both deciding outcomes (wins and run differential), `lo > 0` under all three bootstraps" in text
    assert "on either deciding outcome, `hi < 0` under all three bootstraps" in text
    assert ("when E reads WIN against F and WIN against B, E's d(F) clears the permutation null on both "
            "deciding outcomes, and the planted check read PLANTED PASS") in text
    assert "A read whose planted check failed cannot PASS" in text


def test_licence_bans_and_owner_question():
    text = _flat()
    assert "**A PASS licenses nothing served by itself.**" in text
    assert "EWTA-Q1 (a) record only, nothing served (default)" in text
    assert "that eWAR realized measures talent or skill better" in text
    assert "`docs/PROSPECT_ANCHOR_GATE.md`" in text
    assert "`backtest.run_backtest`" in text
    assert "A second `--read` refuses while the record exists." in text
