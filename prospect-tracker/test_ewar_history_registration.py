# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR history registration pins (docs/ewar/EWAR_HISTORY_GATE.md, task
EWAR_BACKGRADE_HISTORY).

The registration is committed ALONE, before any number of its estimand exists.
Every clause is pinned by the sentence that makes it bind. Prose assertions run
against a whitespace-flattened copy of the document, so re-wrapping a paragraph is
not a test failure. A result pin never lives here.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "ewar" / "EWAR_HISTORY_GATE.md"


def _flat() -> str:
    return re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))


def test_document_names_itself_and_this_test():
    text = _flat()
    assert text.startswith("# eWAR history: every season the data supports, stamped with its parts "
                           "(ewar_history_v1)")
    assert "Task EWAR_BACKGRADE_HISTORY (owner decision EW3-17, 2026-10-15" in text
    assert "committed ALONE, before any number of its estimand is computed" in text
    assert "test_ewar_history_registration.py" in text


def test_scope_admits_nothing_and_moves_nothing_served():
    text = _flat()
    assert "This task admits no part, changes no part, refits nothing and moves no constant." in text
    assert "**Nothing that is served today moves.**" in text
    assert "**Not a label decision.**" in text


def test_seasons_and_where_they_stop():
    text = _flat()
    assert "**2000 to 2026**, every season of the frozen vintage" in text
    assert "`ewar_history.FIRST_SEASON` is `fwar_vintage.FIRST_ACCEPTED_SEASON`" in text
    assert "the vintage is never refetched" in text


def test_parts_are_measured_never_typed():
    text = _flat()
    assert "each part MEASURED on that season's rows, never typed" in text
    for part in ("`batting`", "`wsb`", "`bsr_rest`", "`fielding`", "`framing`", "`positional`",
                 "`league_replacement`", "`pitching`", "`eabs`", "`r2`"):
        assert f"| {part} |" in text
    assert "abs(baseRunning - wSb) above 0.005 runs" in text
    assert "abs(F_i) above 0.05 runs" in text
    assert "`eabs` is never listed as missing before its first season" in text


def test_core_and_full_definitions():
    text = _flat()
    assert "x_i = (baseRunning_i - wSb_i) + F_i" in text
    assert "X_i = x_i - PA_i * (sum_k x_k) / (sum_k PA_k)" in text
    assert "RPW_fg,s = (sum rar) / (sum war) over hitting rows with abs(war) >= 0.5" in text
    assert "core_j = war_j" in text
    assert "full_i = war_i + dh_i realized_i = war_i + dr_i" in text


def test_agreement_is_identities_and_a_descriptive_report():
    text = _flat()
    assert "**Identities (hard: any miss refuses the build and nothing is written).**" in text
    assert "FULL - CORE = B + Fr + eABS within 1e-9 wins" in text
    assert "it decides nothing, carries no threshold and moves nothing" in text
    assert "hitters with 300 or more PA" in text
    assert "pitchers with 50 or more IP" in text
    assert "No band is registered for the gap." in text


def test_served_and_never_served():
    text = _flat()
    assert "**Served: FULL, the headline eWAR, which is the displayed eWAR already.**" in text
    assert "a bWAR value is never printed under the eWAR v2 label" in text
    assert "**Recorded, never displayed: CORE.**" in text
    assert ("CORE is never a column, a sort key, a label, a driver or a model input.") in text
    assert "HoF stays on bWAR" in text


def test_results_empty_at_registration():
    text = _flat()
    assert "## 10. Results" in text


def test_amendment_9_1_terms_enter_only_where_the_stamp_carries_them():
    text = _flat()
    assert ("### 9.1 2026-10-22: a part's term enters x_i only in a season whose stamp carries it "
            "(definition defect, identity 3)") in text
    assert ("`x_i = [baseRunning_i - wSb_i if the season's stamp carries bsr_rest] + [F_i if it carries "
            "framing]`") in text
    assert "the largest abs(F_i) is 0.00027 and 0.00036 runs" in text


def test_amendment_9_2_full_side_sum_within_storage_rounding():
    text = _flat()
    assert ("### 9.2 2026-10-22: FULL's side sum is checked within the artifact's storage rounding "
            "(definition defect, identity 2)") in text
    assert "within 1e-6 + 5e-7 x (rows of the side the artifact lists with a departure on that series) wins" in text
    assert "CORE keeps 1e-6." in text
