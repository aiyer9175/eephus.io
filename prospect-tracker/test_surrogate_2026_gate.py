# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SG_0 and SG_7 pins (efv2026 PLAN.md s5 and item N5): the surrogate gate
docs/efv-v2/SURROGATE_2026_GATE.md, a DRAFT at its first commit and REGISTERED by SG_7.

1. The file carries exactly one status line; gate_doc_registered reads it as REGISTERED
   exactly when that line says so, and the commit that first added it (a DRAFT) opens
   neither the surrogate guard nor the R-LV guard.
2. The header keeps the draft-time OQ1 line and records efv2026 OQ1 to OQ6 (option A to
   all six, DECISIONS_FOR_OWNER.md 2026-10-01), which gate_header_records reads.
3. The REGISTERED commit carries this file alone, is the sha the look runner finds, and
   its header answers OQ2 = A, so the lv2026_surrogate purpose stays closed.
4. No item marked PENDING is left below the header, and section 12 (results) is empty
   until the S3 look writes data/efv_surrogate_gate.json, then carries its output (SG_8).
5. No em-dash, and no FV-cell stratum (the test_efv_v2_gate.py pattern).

Nothing here reads a frame row, an outcome, a score or a label.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

import efv_surrogate_guard as G
import efv_vintage_frame as F

ROOT = Path(__file__).parent
DOC = ROOT / G.SURROGATE_GATE_DOC
DRAFT_LINE = F.GATE_STATUS_PREFIX + " DRAFT"
#: The owner answers recorded on 2026-10-01 (efv2026 OQ1 to OQ6), option A to all six.
REGISTERED_ANSWERS = {f"OQ{i}": "A" for i in range(1, 7)}


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


def test_registered_exactly_when_the_status_line_says_so():
    t = _text()
    is_registered = _status_lines(t) == [F.GATE_STATUS_REGISTERED]
    assert F.gate_doc_registered(t) is is_registered
    # the predicate itself, on this file's own text with the line swapped either way
    as_draft = t.replace(F.GATE_STATUS_REGISTERED, DRAFT_LINE)
    assert F.gate_doc_registered(as_draft) is False
    assert F.gate_doc_registered(as_draft.replace(DRAFT_LINE, F.GATE_STATUS_REGISTERED)) is True


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


def test_the_header_records_oq1_to_oq6():
    t = _text()
    assert "Owner answer at draft commit (efv2026 OQ1): A (own gate; every section " \
           "below applies)." in t
    for key, letter in REGISTERED_ANSWERS.items():
        assert G.header_answer(t, key) == letter, key
    assert G.header_answer(t, "OQ7") is None
    answers = [ln for ln in t.splitlines() if ln.startswith("Owner answer")]
    assert len(answers) == 1 + len(REGISTERED_ANSWERS), answers
    head = t.split("\n---\n", 1)[0]
    assert all(ln in head for ln in answers)


def _registered_commit() -> str | None:
    r = _git("log", "--format=%H", "--", G.SURROGATE_GATE_DOC)
    for sha in r.stdout.split():
        if G.gate_sha_committed_for(sha, G.SURROGATE_GATE_DOC):
            return sha
    return None


def test_the_registered_commit_is_alone_and_reads_its_answers():
    if _status_lines(_text()) != [F.GATE_STATUS_REGISTERED]:
        pytest.skip("the surrogate gate is not REGISTERED in this tree")
    sha = _registered_commit()
    assert sha is not None, "no commit carries the gate marked REGISTERED"
    changed = _git("show", "--name-only", "--format=", sha).stdout.split()
    assert len(changed) == 1 and changed[0].endswith(G.SURROGATE_GATE_DOC), changed
    for key, letter in REGISTERED_ANSWERS.items():
        assert G.gate_header_records(sha, key) == letter, key
    # OQ2 = A: the one surrogate read of lv_2026 never opens, whatever records exist
    with pytest.raises(F.ReservedFrameError):
        G.guard_surrogate_read(2026, gate_sha=sha, look_records=["rvm_look_1"],
                               purpose="lv2026_surrogate")
    for V in sorted(F.RESERVED_LV):
        with pytest.raises(F.ReservedFrameError):
            G.guard_surrogate_read(V, gate_sha=sha, purpose="transfer")


def test_no_pending_item_below_the_header():
    t = _text()
    if _status_lines(t) != [F.GATE_STATUS_REGISTERED]:
        pytest.skip("PENDING items are filled at the REGISTERED commit")
    body = t.split("\n---\n", 1)[1]
    assert "PENDING" not in body, [ln for ln in body.splitlines() if "PENDING" in ln]


EMPTY_12 = "(Empty. Filled only by the look runner after the status line reads REGISTERED.)"


def _transfer_read() -> dict | None:
    p = ROOT / "data" / "efv_surrogate_gate.json"
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    blk = doc.get("transfer") if isinstance(doc, dict) else None
    return blk if isinstance(blk, dict) and blk else None


def test_section_12_is_empty_until_the_look_and_then_carries_it():
    """Section 12 stays empty until the S3 look writes its key; from then it carries the
    runner's verbatim output (every clause verdict line, the gate sha) (SG_8)."""
    t = _text()
    head = "## 12. Results"
    assert t.count(head) == 1
    body = t.split(head, 1)[1].strip()
    read = _transfer_read()
    if read is None:
        assert body == EMPTY_12, body[:200]
        return
    assert EMPTY_12 not in body and "OWNER-WAIVED EARLY READ" in body
    for clause, verdict in read["verdicts"].items():
        assert f"\n{clause}: {verdict}\n" in body.replace("\r\n", "\n"), clause
    assert read["receipt"]["gate_sha"] in body


def test_no_dash_characters():
    t = _text()
    assert "\u2014" not in t and "\u2013" not in t


def test_the_draft_names_no_fv_cell_stratum():
    t = _text().lower()
    assert not re.search(r"\bfv ?(35|40|45|50|55|60|65)\+? (cell|band|bucket|tier)", t)
    assert not re.search(r"\b(by|per|within) (consensus[- ])?fv (cell|band|bucket|tier)", t)
    assert not re.search(r"\b45 ?/ ?50 ?/ ?55\b", t)
