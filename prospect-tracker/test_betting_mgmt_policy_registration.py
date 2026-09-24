# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The 5l club-policy registration exists BEFORE any code, and says what it says.

Docs only. docs/diamond-betting.md section 5l and docs/BETTING_DUGOUT_GATE.md register
two dated club-policy columns (`mg_pen_per_game_l30`, `mg_hook_pitches_l30`) as one Holm
family with a first look no earlier than 2027-07-01. Nothing here computes a number:
the tests pin the documents' text (the dates, the family, the criteria), pin the two
documents to one contaminated-screen wording (review defect H1), and assert that no
non-test module reads the candidates before the "Builder landed" amendment exists.

5c rule 1: a candidate measured before its section exists is disqualified, whatever it
measured. A lab written before the builder is exactly the early look, so the scan below
covers every non-test .py at the root and under tools/, the
test_betting_sidecar_isolation._discovered_modules idiom. The registration and fence
test files carry the column literals by design and are skipped by name.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
GATE_DOC = ROOT / "docs" / "diamond-betting.md"
LONG_FORM = ROOT / "docs" / "BETTING_DUGOUT_GATE.md"
PLAN = ROOT / "docs" / "master-plan-2026-09-11-war-epoch-drivers-betting.md"

COLUMN_PREFIXES = ("mg_pen_", "mg_hook_")
RULE_1_SENTENCE = "before any value of the column has been related to any game outcome"
FIT_WINDOW_SENTENCE = ("The 305 games of the 2026 fit window (2026-07-06 to 2026-07-31) "
                       "stay ungraded in every mode of every artifact this gate writes")
SCREEN_PRESENT = ("only on a member that passed", "after the 2027 look")
SCREEN_ABSENT = ("2026 read", "end-of-season 2026", "against 2026 outcomes")
EM_DASH, EN_DASH = chr(0x2014), chr(0x2013)     # spelled so this file carries neither


def _norm(text: str) -> str:
    """The documents are hard-wrapped at about 85 columns, so a sentence pinned here
    is matched with every run of whitespace collapsed to one space."""
    return re.sub(r"\s+", " ", text)


def _doc() -> str:
    assert GATE_DOC.exists(), "docs/diamond-betting.md is missing"
    return GATE_DOC.read_text(encoding="utf-8")


def _section_5l(doc: str | None = None) -> str:
    doc = _doc() if doc is None else doc
    m = re.search(r"^## 5l\..*$", doc, flags=re.M)
    assert m, "docs/diamond-betting.md has no '## 5l.' heading: the registration is missing"
    start = m.start()
    nxt = re.search(r"^## (?!5l\.)", doc[m.end():], flags=re.M)
    return doc[start:] if nxt is None else doc[start:m.end() + nxt.start()]


def _long_form() -> str:
    assert LONG_FORM.exists(), "docs/BETTING_DUGOUT_GATE.md is missing"
    return LONG_FORM.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# the section, the long form, the calendar
# ---------------------------------------------------------------------------
def test_the_5l_section_exists_with_the_rule_1_sentence():
    sec = _section_5l()
    head = sec.splitlines()[0]
    assert "pre-registered" in head, head
    assert re.search(r"pre-registered 20\d\d-\d\d-\d\d", head), (
        "the 5l heading must carry its pre-registration date")
    assert RULE_1_SENTENCE in _norm(sec)
    assert "mg_pen_per_game_l30" in sec and "mg_hook_pitches_l30" in sec


def test_the_long_form_document_exists_and_names_the_look():
    lf = _norm(_long_form())
    for needle in ("2027-07-01", "Holm", "m = 2", "SERVE_MGMT_POLICY",
                   FIT_WINDOW_SENTENCE, "MODEL_VERSION", "2027-08-01", "0.0024",
                   "600", "300"):
        assert needle in lf, f"docs/BETTING_DUGOUT_GATE.md lacks {needle!r}"
    assert "whatever the effect size" in lf.lower()


def test_the_5l_section_names_the_same_dates_family_and_criteria():
    """The two documents carry one set of thresholds; 5l is the registration of
    record and the long form may not drift from it."""
    sec = _norm(_section_5l())
    for needle in ("2027-07-01", "2027-08-01", "Holm", "m = 2", "SERVE_MGMT_POLICY",
                   "MODEL_VERSION", FIT_WINDOW_SENTENCE, "0.0024", "t >= 1.645", "VIF",
                   "200", "0.025"):
        assert needle in sec, f"5l lacks {needle!r}"
    assert "whatever the effect size" in sec.lower()
    # A "### Builder landed" HEADING must carry a date; the prose that promises the
    # amendment is not the amendment.
    for m in re.finditer(r"^### Builder landed(.*)$", _section_5l(), flags=re.M):
        assert re.match(r" 20\d\d-\d\d-\d\d", m.group(1)), m.group(0)


def test_the_plan_calendar_carries_the_row():
    assert PLAN.exists()
    p = PLAN.read_text(encoding="utf-8")
    i = p.index("### 5.1")
    j = p.index("### 5.2", i)
    table = p[i:j]
    rows = [ln for ln in table.splitlines() if "5l" in ln and "2027-07-01" in ln]
    assert rows, "the plan's 5.1 calendar has no row for the 5l look on 2027-07-01"
    assert any("m = 2" in r for r in rows), rows


# ---------------------------------------------------------------------------
# no code, no column, no look
# ---------------------------------------------------------------------------
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


def test_no_column_exists_before_its_builder_is_dated():
    """If the column exists in the vintage schema the section must say when the
    builder landed; if it does not, no non-test module may name the columns (a lab
    written before the builder is exactly the early look 5c rule 1 forbids)."""
    lv = (ROOT / "leaderboard_vintages.py").read_text(encoding="utf-8")
    sec = _section_5l()
    if "mg_pen_per_game_l30" in lv:
        assert re.search(r"### Builder landed 20\d\d-\d\d-\d\d", sec), (
            "the column is in leaderboard_vintages.py but 5l has no dated "
            "'### Builder landed' amendment (plan stop item X9)")
        return
    offenders = []
    for p in _non_test_modules():
        src = p.read_text(encoding="utf-8", errors="replace")
        if any(pref in src for pref in COLUMN_PREFIXES):
            offenders.append(p.relative_to(ROOT).as_posix())
    assert not offenders, (
        "these non-test modules name a 5l column before its builder landed; a number "
        "computed on it is the early look that voids the member: " + ", ".join(offenders))


def test_no_notebook_or_lab_names_the_candidates_either():
    """The same scan over notebooks and the docs lab folders, so a scratch read does
    not hide behind a file type the module scan skips."""
    hits = []
    for pat in ("*.ipynb", "tools/*.ipynb", "docs/**/*.py", "docs/**/*.ipynb"):
        for p in ROOT.glob(pat):
            src = p.read_text(encoding="utf-8", errors="replace")
            if any(pref in src for pref in COLUMN_PREFIXES):
                hits.append(p.relative_to(ROOT).as_posix())
    assert not hits, hits


def test_the_contaminated_screen_waits_for_the_look():
    """Review defect H1: the screen runs once, after the 2027 look, only on a member
    that passed, and no 2026 form of it exists."""
    sec = _norm(_section_5l())
    lf = _norm(_long_form())
    for text, name in ((sec, "5l"), (lf, "BETTING_DUGOUT_GATE.md")):
        low = text.lower()
        for needle in SCREEN_PRESENT:
            assert needle in low, f"{name} lacks {needle!r}"
        for bad in SCREEN_ABSENT:
            assert bad not in low, f"{name} carries {bad!r}, a 2026 form of the screen"


def test_the_two_documents_carry_one_contaminated_screen_wording():
    """The paragraph is verbatim in both, so an amendment to one cannot loosen the
    other."""
    def para(text: str) -> str:
        m = re.search(r"\*\*Contaminated screen \(5c rule 4's first serve leg.*?(?=\n\n)",
                      text, flags=re.S)
        assert m, "the contaminated-screen paragraph is missing"
        return re.sub(r"\s+", " ", m.group(0)).strip()
    assert para(_section_5l()) == para(_long_form())


def test_the_flag_is_absent_or_false():
    bm = pytest.importorskip("betting_model")
    assert getattr(bm, "SERVE_MGMT_POLICY", False) is False
    # Registration only: no dark tuple for the family exists yet either.
    assert not any(c.startswith("mg_") for c in getattr(bm, "DARK_TEAM_COLUMNS", ()))


def test_no_dashes_in_either_document():
    for p in (LONG_FORM,):
        t = p.read_text(encoding="utf-8")
        assert EM_DASH not in t and EN_DASH not in t, p.name
    sec = _section_5l()
    assert EM_DASH not in sec and EN_DASH not in sec, "5l carries an em or en dash"
