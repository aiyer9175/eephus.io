# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The starter-workload registration exists BEFORE any code, and says what it says.

Docs only. docs/diamond-betting.md carries the section "Starter workload: expected outs
and pitches per start" (plan candidate N6(d), owner ask 16 of 2026-09-30): a two-stage
gate, a workload read on pre-2026 corpus starts and a moneyline look no earlier than
2027-07-01. Nothing here computes a number. The tests pin the section by its TITLE,
never by its letter (letters go by commit order), pin the column names, never a schema
number, and assert that:

- the section predates any builder by git date;
- no non-test module names a dark column before a dated "### Builder landed" amendment;
- no serving flag exists before a stage-2 result exists;
- the tested contrasts T1, T2 and the comparator C1 are named in the text.

5c rule 1: a candidate measured before its section exists is disqualified, whatever it
measured. A lab written before the builder that names the columns is exactly the early
look, so the scan covers every non-test .py at the root and under tools/, the
test_betting_mgmt_policy_registration idiom.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
GATE_DOC = ROOT / "docs" / "diamond-betting.md"
ARTIFACT = ROOT / "data" / "starter_workload_eval.json"
LAB = ROOT / "tools" / "starter_workload_lab.py"

TITLE = "Starter workload: expected outs and pitches per start"
COLUMNS = ("sp_n365", "sp_budget", "sp_ppo", "sp_xouts", "bat_ppa_l30")
FLAGS = ("SERVE_STARTER_WORKLOAD", "SERVE_WORKLOAD_PROPS")
CLOSING = "No number has been computed on this candidate."
EM_DASH, EN_DASH = chr(0x2014), chr(0x2013)     # spelled so this file carries neither


def _norm(text: str) -> str:
    """The document is hard-wrapped at about 86 columns, so a sentence pinned here is
    matched with every run of whitespace collapsed to one space."""
    return re.sub(r"\s+", " ", text)


def _doc() -> str:
    assert GATE_DOC.exists(), "docs/diamond-betting.md is missing"
    return GATE_DOC.read_text(encoding="utf-8")


def _level2(doc: str, heading_re: str) -> str:
    """The text of the one level-2 section whose heading matches, up to the next
    level-2 heading."""
    hits = list(re.finditer(heading_re, doc, flags=re.M))
    assert len(hits) == 1, f"expected one heading matching {heading_re!r}, got {len(hits)}"
    m = hits[0]
    nxt = re.search(r"^## ", doc[m.end():], flags=re.M)
    return doc[m.start():] if nxt is None else doc[m.start():m.end() + nxt.start()]


def _section(doc: str | None = None) -> str:
    doc = _doc() if doc is None else doc
    return _level2(doc, r"^## [^\n]*" + re.escape(TITLE) + r"[^\n]*$")


def _builder_landed(sec: str) -> bool:
    return re.search(r"^### Builder landed 20\d\d-\d\d-\d\d", sec, flags=re.M) is not None


def _stage2_recorded(sec: str) -> bool:
    if re.search(r"^### Stage 2 result", sec, flags=re.M):
        return True
    if ARTIFACT.exists():
        try:
            return "stage2" in json.loads(ARTIFACT.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return False
    return False


def _non_test_modules() -> list[Path]:
    out = []
    for base in (ROOT, ROOT / "tools"):
        if not base.exists():
            continue
        for p in sorted(base.glob("*.py")):
            if p.name.startswith("test_") or p.name == "conftest.py":
                continue
            out.append(p)
    return out


def _modules_naming(needles) -> list[Path]:
    hits = []
    for p in _non_test_modules():
        src = p.read_text(encoding="utf-8", errors="replace")
        if any(n in src for n in needles):
            hits.append(p)
    return hits


def _first_commit_date(needle: str, path: Path) -> str | None:
    """ISO committer date of the earliest commit whose diff adds or removes `needle`
    in `path` (git log -S), or None when git cannot say."""
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


# ---------------------------------------------------------------------------
# the section and what it names
# ---------------------------------------------------------------------------
def test_the_section_exists_with_its_title_and_date():
    sec = _section()
    head = sec.splitlines()[0]
    assert re.search(r"pre-registered 20\d\d-\d\d-\d\d", head), (
        "the starter-workload heading must carry its pre-registration date")
    assert "N6(d)" in head, head
    assert CLOSING in _norm(sec), "the section must close with its no-number sentence"


def test_the_contrasts_comparators_and_wording_are_named():
    sec = _norm(_section())
    for needle in ("T1", "T2", "C1", "D1", "D2", "A0", "m = 2", "m = 4", "0.0125",
                   "20260930", "B 2000",
                   '"starts-only length over a 365-day window"',
                   "nothing credits the opposing lineup's P/PA"):
        assert needle in sec, f"the section lacks {needle!r}"


def test_the_clocks_and_the_artifact_are_named():
    sec = _norm(_section())
    for needle in ("2026-10-11", "PM-Q3", "2027-07-01", "2027-08-01", "mgmt_policy_gate",
                   "600", "0.0024", "data/starter_workload_eval.json",
                   "starter_workload_xouts",
                   "neither ever writes data/betting_model_eval.json",
                   "NEVER 2026", "sp_tto3_bf", "sp_rest_days"):
        assert needle in sec, f"the section lacks {needle!r}"
    for col in COLUMNS:
        assert f"`{col}`" in sec, f"the section does not name the column {col!r}"


def test_the_two_disclosure_amendments_exist():
    doc = _doc()
    tto = doc[doc.index("### 5d-E. "):doc.index("### 5d-F. ")]
    assert TITLE in _norm(tto) and "changes none of 5d-E's criteria" in _norm(tto)
    l_sec = _norm(_level2(doc, r"^## 5l\. .*$"))
    assert TITLE in l_sec
    assert "only to the starter's own workload" in l_sec
    assert "nothing to a game result, price, edge or ledger row" in l_sec


def test_no_dashes_in_the_section():
    sec = _section()
    assert EM_DASH not in sec and EN_DASH not in sec


# ---------------------------------------------------------------------------
# no code, no column, no flag, no number
# ---------------------------------------------------------------------------
def test_no_column_is_named_before_its_builder_is_dated():
    """Until a dated '### Builder landed' amendment exists, no non-test module may
    name a dark column of this section: a lab or builder written before it is the
    early look 5c rule 1 forbids."""
    if _builder_landed(_section()):
        return
    offenders = [p.relative_to(ROOT).as_posix() for p in _modules_naming(COLUMNS)]
    assert not offenders, (
        "these non-test modules name a starter-workload column before its builder "
        "landed: " + ", ".join(offenders))


def test_no_notebook_or_docs_lab_names_the_columns_either():
    hits = []
    for pat in ("*.ipynb", "tools/*.ipynb", "docs/**/*.py", "docs/**/*.ipynb"):
        for p in ROOT.glob(pat):
            src = p.read_text(encoding="utf-8", errors="replace")
            if any(c in src for c in COLUMNS):
                hits.append(p.relative_to(ROOT).as_posix())
    assert not hits, hits


def test_the_section_predates_any_builder_by_git_date():
    """Every non-test module that names a column first did so in a commit no earlier
    than the commit that added the section."""
    modules = _modules_naming(COLUMNS)
    if not modules:
        return
    sec_date = _first_commit_date(TITLE, GATE_DOC)
    if sec_date is None:
        pytest.skip("git cannot date the section here")
    for p in modules:
        src = p.read_text(encoding="utf-8", errors="replace")
        for col in COLUMNS:
            if col not in src:
                continue
            col_date = _first_commit_date(col, p)
            if col_date is None:
                pytest.fail(f"{p.name} names {col} in an uncommitted change while the "
                            "registration test cannot date it")
            assert col_date >= sec_date, (
                f"{p.name} named {col} at {col_date}, before the section ({sec_date})")


def test_no_serve_flag_exists_before_a_stage_2_result():
    """SERVE_STARTER_WORKLOAD lands only with a stage-2 PASS, and SERVE_WORKLOAD_PROPS
    only after both 5l's look and this section's stage-2 look."""
    if _stage2_recorded(_section()):
        return
    offenders = [p.relative_to(ROOT).as_posix() for p in _modules_naming(FLAGS)]
    assert not offenders, (
        "a starter-workload serving flag exists before any stage-2 result: "
        + ", ".join(offenders))
    bm = pytest.importorskip("betting_model")
    for flag in FLAGS:
        assert not hasattr(bm, flag), flag


def test_no_artifact_exists_without_its_lab():
    """The section's own artifact is written by the stage-1 lab and nothing else; a
    file without the lab is a number computed outside the registered run."""
    if ARTIFACT.exists():
        assert LAB.exists(), (
            "data/starter_workload_eval.json exists but tools/starter_workload_lab.py "
            "does not")
