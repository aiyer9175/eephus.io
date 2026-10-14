# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SG_0 pins (efv2026 PLAN.md s5 and item N5): the surrogate gate draft
docs/efv-v2/SURROGATE_2026_GATE.md.

1. The file carries exactly one status line; while it reads DRAFT,
   efv_vintage_frame.gate_doc_registered reads the file as False, and the commit that
   first added it (a DRAFT) opens neither the surrogate guard nor the R-LV guard.
2. The header records efv2026 OQ1 on its one answer line, and no other answer.
3. Section 12 (results) is empty.
4. No em-dash, and no FV-cell stratum (the test_efv_v2_gate.py pattern).

Nothing here reads a frame row, an outcome, a score or a label.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

import efv_surrogate_guard as G
import efv_vintage_frame as F

ROOT = Path(__file__).parent
DOC = ROOT / G.SURROGATE_GATE_DOC
DRAFT_LINE = F.GATE_STATUS_PREFIX + " DRAFT"


def _text() -> str:
    if not DOC.exists():
        pytest.skip(f"{G.SURROGATE_GATE_DOC} absent")
    return DOC.read_text(encoding="utf-8")


def _status_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines()
            if ln.strip().startswith(F.GATE_STATUS_PREFIX)]


def test_the_draft_line_reads_as_the_guard_expects():
    assert DRAFT_LINE == "Registration status: DRAFT"
    assert F.GATE_STATUS_REGISTERED == "Registration status: REGISTERED"


def test_exactly_one_status_line():
    status = _status_lines(_text())
    assert len(status) == 1, status
    assert status[0] in (DRAFT_LINE, F.GATE_STATUS_REGISTERED), status


def test_a_draft_is_not_registered():
    t = _text()
    if _status_lines(t) == [DRAFT_LINE]:
        assert F.gate_doc_registered(t) is False
    # the predicate itself, on this file's own text with the line swapped
    assert F.gate_doc_registered(t.replace(DRAFT_LINE, F.GATE_STATUS_REGISTERED)) is (
        _status_lines(t) == [DRAFT_LINE])


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                          text=True, encoding="utf-8")


def test_the_first_committed_draft_opens_no_guard():
    r = _git("log", "--diff-filter=A", "--format=%H", "--", G.SURROGATE_GATE_DOC)
    shas = r.stdout.split()
    if r.returncode != 0 or not shas:
        pytest.skip("the surrogate gate draft is not committed yet")
    sha = shas[-1]
    shown = _git("show", f"{sha}:./{G.SURROGATE_GATE_DOC}")
    assert shown.returncode == 0, shown.stderr
    assert _status_lines(shown.stdout) == [DRAFT_LINE]
    assert F.gate_doc_registered(shown.stdout) is False
    assert G.gate_sha_committed_for(sha, G.SURROGATE_GATE_DOC) is False
    assert G.gate_header_records(sha, "OQ1") is None
    for purpose in ("transfer", "lv2026_surrogate", "lv2026_long_run"):
        with pytest.raises(F.ReservedFrameError):
            G.guard_surrogate_read(2019, gate_sha=sha, purpose=purpose)
    for V in sorted(F.RESERVED_LV):
        with pytest.raises(F.ReservedFrameError):
            G.guard_surrogate_read(V, gate_sha=sha, purpose="transfer")


def test_the_header_records_oq1_and_nothing_else():
    t = _text()
    assert G.header_answer(t, "OQ1") == "A"
    assert "Owner answer at draft commit (efv2026 OQ1): A (own gate; every section " \
           "below applies)." in t
    for key in ("OQ2", "OQ3", "OQ4", "OQ5", "OQ6"):
        assert G.header_answer(t, key) is None, key
    answers = [ln for ln in t.splitlines() if ln.startswith("Owner answer")]
    assert len(answers) == 1, answers


def test_section_12_is_empty():
    t = _text()
    head = "## 12. Results"
    assert t.count(head) == 1
    body = t.split(head, 1)[1].strip()
    assert body == ("(Empty. Filled only by the look runner after the status line reads "
                    "REGISTERED.)"), body[:200]


def test_no_dash_characters():
    t = _text()
    assert "\u2014" not in t and "\u2013" not in t


def test_the_draft_names_no_fv_cell_stratum():
    t = _text().lower()
    assert not re.search(r"\bfv ?(35|40|45|50|55|60|65)\+? (cell|band|bucket|tier)", t)
    assert not re.search(r"\b(by|per|within) (consensus[- ])?fv (cell|band|bucket|tier)", t)
    assert not re.search(r"\b45 ?/ ?50 ?/ ?55\b", t)
