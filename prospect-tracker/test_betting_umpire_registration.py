# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The umpire registration exists BEFORE the capture, and says what it says.

docs/diamond-betting.md carries the section "The home-plate umpire: a dark pregame
assignment capture" and docs/BETTING_UMPIRE_GATE.md its long form. Nothing here
computes a number. The tests pin the section by its TITLE, never by its letter
(letters go by commit order), pin the two documents to each other on every
threshold, pin the capture's row fields to the registered list, and assert that:

- the section was committed before the capture job, by git date;
- no non-test module names a candidate column before a dated "### Builder landed"
  amendment exists in the section (5c rule 1: a lab that names them early is the
  early look);
- no serving flag is True;
- 5d-F's ban is reopened beneath it, never over it.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

DOC = ROOT / "docs" / "diamond-betting.md"
GATE = ROOT / "docs" / "BETTING_UMPIRE_GATE.md"
JOB = ROOT / "tools" / "betting_umpire_job.py"

TITLE = "The home-plate umpire: a dark pregame assignment capture"
COLUMNS = ("ump_cs_rate_prior", "ump_rpg_prior")
FLAG = "SERVE_UMPIRE"
EM_DASH, EN_DASH = chr(0x2014), chr(0x2013)

#: Every threshold the section and the gate document must both carry.
SHARED = (
    "2027-06-01", "2027-08-01", "Looking early DISQUALIFIES", "umpire_capture/1",
    "k_c = 3000", "k_r = 150", "600", "300", "m = 2", "0.025", "28 days",
    "0.114 x sd_d", "1 percent of the incumbent's fit-window mean absolute error",
    "hydrate=officials", "5 minutes", "SERVE_UMPIRE", "ump_cs_rate_prior",
    "ump_rpg_prior", "2018, 2019", "2026", "data/_labs/umpire_prior/umpire_prior_2027.json",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _section() -> str:
    doc = DOC.read_text(encoding="utf-8")
    hits = list(re.finditer(r"^## [^\n]*" + re.escape(TITLE) + r"[^\n]*$", doc, flags=re.M))
    assert len(hits) == 1, f"expected one section titled {TITLE!r}, got {len(hits)}"
    m = hits[0]
    nxt = re.search(r"^## ", doc[m.end():], flags=re.M)
    return doc[m.start():] if nxt is None else doc[m.start():m.end() + nxt.start()]


def _builder_landed(sec: str) -> bool:
    return re.search(r"^### Builder landed 20\d\d-\d\d-\d\d", sec, flags=re.M) is not None


def _non_test_modules() -> list[Path]:
    out = []
    for base in (ROOT, ROOT / "tools"):
        for p in sorted(base.glob("*.py")):
            if p.name.startswith("test_") or p.name == "conftest.py":
                continue
            out.append(p)
    return out


def _first_commit_date(needle: str, path: Path) -> str | None:
    if shutil.which("git") is None:
        return None
    try:
        out = subprocess.run(
            ["git", "log", "--reverse", "--format=%cI", "-S", needle, "--",
             path.relative_to(ROOT).as_posix()],
            cwd=ROOT, capture_output=True, text=True, timeout=120, check=True).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return lines[0] if lines else None


def test_the_section_and_the_gate_document_exist_and_carry_the_same_thresholds():
    sec, gate = _norm(_section()), _norm(GATE.read_text(encoding="utf-8"))
    for needle in SHARED:
        assert needle in sec, f"the section lacks {needle!r}"
        assert needle in gate, f"the gate document lacks {needle!r}"


def test_the_section_names_the_family_the_twin_and_the_sign():
    sec = _norm(_section())
    for needle in ("Holm family UMP", "ASSIGNMENT twin", "seeds 0 to 199",
                   "Criterion 4, the sign", "NEGATIVE", "POSITIVE",
                   "contaminated", "No number has been computed on this candidate."):
        assert needle in sec, needle


def test_the_capture_time_rule_is_written_before_any_capture():
    sec = _norm(_section())
    assert "strictly earlier than T_price(g)" in sec
    assert "the open odds snapshot" in sec
    assert "One pre-look correction is allowed" in sec


def test_the_registered_row_fields_are_the_job_fields():
    import betting_umpire_job as job
    sec = _section()
    para = sec[sec.index("**The capture (step 2"):sec.index("**The candidate columns")]
    named = re.findall(r"`([a-z_]+)`", para)
    fields = list(dict.fromkeys(n for n in named if n in job.ROW_FIELDS))
    assert fields == list(job.ROW_FIELDS), (fields, job.ROW_FIELDS)
    assert job.CAPTURE_SCHEMA == "umpire_capture/1"
    gate = GATE.read_text(encoding="utf-8")
    block = gate[gate.index("Fields, the schema"):gate.index("**Bracketing publication.**")]
    assert list(dict.fromkeys(n for n in re.findall(r"`([a-z_]+)`", block)
                              if n in job.ROW_FIELDS)) == list(job.ROW_FIELDS)


def test_no_module_names_a_candidate_column_before_the_builder_lands():
    if _builder_landed(_section()):
        pytest.skip("the builder has landed; its own tests take over")
    hits = [p.name for p in _non_test_modules()
            if any(c in p.read_text(encoding="utf-8", errors="replace") for c in COLUMNS)]
    assert hits == [], f"named before the builder amendment: {hits}"


def test_no_serving_flag_is_true():
    for p in _non_test_modules():
        src = p.read_text(encoding="utf-8", errors="replace")
        assert not re.search(r"^\s*" + FLAG + r"\s*(?::[^=]*)?=\s*True\b", src, flags=re.M), p.name


def test_the_section_predates_the_capture_job():
    sec_date = _first_commit_date(TITLE.split(":")[0], DOC)
    job_date = _first_commit_date("CAPTURE_SCHEMA", JOB) if JOB.exists() else None
    if sec_date is None or job_date is None:
        pytest.skip("git cannot date one of the two yet")
    assert sec_date <= job_date, (sec_date, job_date)


def test_5d_f_is_reopened_beneath_it_never_over_it():
    doc = DOC.read_text(encoding="utf-8")
    f = doc.index("### 5d-F. The home plate umpire is NOT SERVABLE")
    nxt = doc.index("### Correction (2026-09-07, same day)", f)
    block = doc[f:nxt]
    assert "**Do not add an umpire column to the vintage store until a source publishes the" \
        in block, "5d-F's own text must stand as written"
    assert "**Reopened (2026-10-08, owner answer 2026-09-25 batch 5).**" in block
    assert block.index("**Do not add an umpire column") < block.index("**Reopened")


def test_both_documents_are_plain_ascii_without_a_dash():
    for text in (_section(), GATE.read_text(encoding="utf-8")):
        assert EM_DASH not in text and EN_DASH not in text
        assert all(ord(c) < 128 for c in text)
