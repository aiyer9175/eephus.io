# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Z1c registration pins (docs/efv-2026-10-03/Z1C_PITCHER_STUFF_GATE.md).

Owner decision PROGRAM-Q4-REVISIT (2026-10-03): Z1c, the pitcher-stuff first fold, gets its
own registration with one leg on the 2025 debut cohort inside EV-12's one Holm family, written
before EV-12 commits. A registration carries definitions, rules and dates only, so this file
pins that:

1. The file exists, reads DRAFT, carries every section the decision asks for, and its
   Results section is empty.
2. No decimal, no percent, no interval, no 'p =', no count that could only come from a frame,
   no forecast word, no em or en dash and no copy_lint banned word.
3. The column statement stays true: while no pitcher-stuff arm holds a registered id in the arm
   ledger, the file says the leg is defined on a column that does not exist yet and names the
   producer; the day one appears, this test fails until the file names the id.
4. Every cross-reference resolves to an existing file and heading, and the three documents
   that expect a pointer back carry it in the right place (EFV_V2_GATE.md s2.2, PROGRAM.md Q4,
   the fWAR gate's header history list, never its part 9).

Nothing here reads a frame row or an outcome.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC_REL = "docs/efv-2026-10-03/Z1C_PITCHER_STUFF_GATE.md"
DOC = ROOT / DOC_REL
EFV_V2_GATE = ROOT / "docs" / "efv-v2" / "EFV_V2_GATE.md"
PROGRAM = ROOT / "docs" / "efv-v2" / "PROGRAM.md"
FWAR = ROOT / "docs" / "efv-2026-09-17" / "FWAR_LABEL_EPOCH_GATE.md"
Z1 = ROOT / "docs" / "efv-2026-10-03" / "LABEL_V3_DRIVER_RETEST_GATE.md"
LEDGER = ROOT / "data" / "xfv_arm_ledger.json"
Z1_LIST = ROOT / "docs" / "efv-2026-10-03" / "z1_arm_list.json"

SECTIONS = (
    "## 1. Purpose and lineage",
    "## 2. The frame",
    "## 3. The column the leg reads",
    "## 4. The statistic and its direction",
    "## 5. The leg in EV-12's one Holm family",
    "## 6. The look",
    "## 7. The serving consequence",
    "## 8. What this registration does not do",
    "## 9. Pending items",
    "## Results",
)

# (path the registration cites, a heading that must exist in it)
XREFS = (
    ("docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md", "### (k) The registration that follows this one"),
    ("docs/master-plan-2026-09-11-war-epoch-drivers-betting.md", "### 2.7 Reopen status of every closed item"),
    ("docs/master-plan-2026-08-19-holistic-audit.md", "## 2. DO-NOT-REOPEN checklist"),
    ("docs/efv-v2/PROGRAM.md", "### 2.4 Reserved frames"),
    ("docs/efv-v2/PROGRAM.md", "### 3.5 Sequence"),
    ("docs/efv-v2/PROGRAM.md", "## 4. The registration: `docs/efv-v2/EFV_V2_GATE.md`"),
    ("docs/efv-v2/PROGRAM.md", "## 6. Owner questions"),
    ("docs/efv-v2/EFV_V2_GATE.md", "### 2.2 Reserved frames"),
    ("docs/efv-v2/EFV_V2_GATE.md", "### 3.1 Primary: within (side, vintage)"),
    ("docs/efv-v2/EFV_V2_GATE.md", "### 3.5 Contributor AUC (veto only)"),
    ("docs/efv-v2/EFV_V2_GATE.md", "### 3.6 "),
    ("docs/efv-v2/DRIVER_SYSTEM_V2.md", "### 4.3 Architecture"),
    ("docs/efv-2026-10-03/LABEL_V3_DRIVER_RETEST_GATE.md",
     "## 5. Serving a passer (O9) and the confirmation leg on the reserved 2025 cohort"),
    ("docs/efv-2026-08-13/PITCHER_STUFF_CLOCK.md", "## The bound that removes the 2025 fold"),
)

_FORECAST = re.compile(r"\b(luck\w*|due|regress\w*|trending|will|clutch|sleepers?)\b", re.I)


def _text(p: Path = DOC) -> str:
    return p.read_text(encoding="utf-8")


def _headings(p: Path) -> list[str]:
    return [ln.rstrip() for ln in _text(p).splitlines() if ln.startswith("#")]


# ---------------------------------------------------------------------------
# 1. the draft and its sections
# ---------------------------------------------------------------------------

def test_the_registration_exists_and_reads_draft():
    assert DOC.exists(), DOC_REL
    t = _text()
    status = [ln.strip() for ln in t.splitlines() if ln.strip().startswith("Registration status:")]
    assert status == ["Registration status: DRAFT"]
    assert "becomes REGISTERED" in t.replace("\r\n", "\n").replace("\n", " ")
    assert "test_z1c_registration.py" in t


def test_every_section_is_present_in_order():
    heads = _headings(DOC)
    at = []
    for s in SECTIONS:
        hits = [i for i, h in enumerate(heads) if h.startswith(s)]
        assert len(hits) == 1, s
        at.append(hits[0])
    assert at == sorted(at)
    assert heads[-1] == "## Results"


def test_results_section_is_empty():
    body = _text().split("\n## Results", 1)[1].strip()
    assert body == "(Empty. Nothing is recorded here before the leg's first look.)"


def test_the_leg_carries_the_owner_answer_and_its_shape():
    flat = re.sub(r"\s+", " ", _text())
    for s in ("PROGRAM-Q4-REVISIT", "Q4 = A", "first look after the RT 2026 labels",
              "one leg on the 2025 debut cohort", "clause (k)", "item 8a",
              "adds exactly one to that family's m", "removes the column automatically",
              "Looking early disqualifies the leg", "not before 2026-12-01",
              "None by itself", "One-sided", "Option B"):
        assert s in flat, s
    for k in range(1, 6):
        assert f"(Z1c-{k})" in flat, k


# ---------------------------------------------------------------------------
# 2. definitions, rules and dates only
# ---------------------------------------------------------------------------

def _without_section_refs(t: str) -> str:
    return re.sub(r"\b(?:sections?|s)\s?\d+(?:\.\d+)*", "", t)


def test_no_decimal_percent_interval_or_p_value():
    t = _without_section_refs(_text())
    assert not re.search(r"\d\.\d", t), re.search(r".{0,30}\d\.\d.{0,10}", t).group(0)
    assert not re.search(r"\d\s*%|\bpercent\b", t, re.I)
    assert not re.search(r"\[\s*[+-]?\d", t)
    assert not re.search(r"\binterval\b|\bci\s?9\d", t, re.I)
    assert not re.search(r"\bp\s*[=<>]", t, re.I)
    assert not re.search(r"\b(rho|n|delta)\s*=", t, re.I)


def test_no_count_that_could_come_from_a_frame():
    """Integers are years, dates, rule or clause numbers, or ids. A standalone integer from
    40 to 1999, or above 2030, is the shape a row count or a frame number would take."""
    t = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", _text())
    t = re.sub(r"\b[0-9a-f]{7,64}\b", "", t)
    bad = [m.group(0) for m in re.finditer(r"(?<![\w.-])\d+(?![\w.])", t)
           if 40 <= int(m.group(0)) < 2000 or int(m.group(0)) > 2030]
    assert not bad, bad


def test_no_forecast_word_dash_or_banned_word():
    t = _text()
    assert "—" not in t and "–" not in t
    hits = [ln for ln in t.splitlines() if _FORECAST.search(ln)]
    assert not hits, hits
    sys.path.insert(0, str(ROOT / "tools"))
    from copy_lint import BAN_RE
    banned = [ln for ln in t.splitlines() if BAN_RE.search(ln)]
    assert not banned, banned


def test_nothing_is_cut_by_consensus_fv_cell():
    t = _text().lower()
    assert not re.search(r"\bfv ?(35|40|45|50|55|60|65)\+? (cell|band|bucket|tier)", t)


# ---------------------------------------------------------------------------
# 3. the column statement
# ---------------------------------------------------------------------------

def _ledger_stuff_arms() -> list[str]:
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    return [a.get("arm") or "" for a in led.get("arms", [])
            if re.search(r"stuff", a.get("arm") or "", re.I)]


def test_the_column_statement_matches_the_ledger():
    t = re.sub(r"\s+", " ", _text())
    if LEDGER.exists() and _ledger_stuff_arms():
        ids = _ledger_stuff_arms()
        assert any(i in t for i in ids), (
            "a pitcher-stuff arm now has a registered id in data/xfv_arm_ledger.json; name it "
            f"in section 3 and section 9: {ids}")
        return
    assert "The leg is defined on a column that does not exist yet." in t
    assert "`tools/efv_pitcher_stuff_lab.py`" in t and "`tools/efv_arm_ledger.py`" in t
    assert (ROOT / "tools" / "efv_pitcher_stuff_lab.py").exists()
    assert (ROOT / "tools" / "efv_arm_ledger.py").exists()


def test_z1_sets_the_stuff_lane_aside():
    z1 = json.loads(Z1_LIST.read_text(encoding="utf-8"))
    lanes = [x for x in z1["excluded_lanes"] if x.get("artifact") == "xfv_pitcher_stuff_eval.json"]
    assert len(lanes) == 1 and "Z1c" in lanes[0]["reason"]
    assert "xfv_pitcher_stuff_eval.json" in _text()


# ---------------------------------------------------------------------------
# 4. cross-references
# ---------------------------------------------------------------------------

def test_every_cited_heading_exists():
    t = _text()
    for path, head in XREFS:
        assert path in t or Path(path).name in t, path
        heads = _headings(ROOT / path)
        assert any(h.lstrip("#").strip().startswith(head.lstrip("#").strip()) for h in heads), \
            (path, head)


def test_every_backticked_path_exists():
    t = _text()
    paths = {m for m in re.findall(r"`([\w./-]+\.(?:md|py|json))`", t)
             if "/" in m and "*" not in m}
    paths |= {m for m in re.findall(r"`([\w-]+\.py)`", t)}
    missing = [p for p in sorted(paths)
               if not ((ROOT / p).exists() or (ROOT / "tools" / p).exists())]
    assert not missing, missing


def test_the_documents_point_back_where_expected():
    gate = _text(EFV_V2_GATE)
    s22 = gate.split("### 2.2 ", 1)[1].split("\n#### ", 1)[0]
    assert DOC_REL in s22 and "2026-10-03" in s22 and "clause (c)" in s22
    assert gate.count(DOC_REL) == 1

    prog = _text(PROGRAM)
    q4 = prog.split("**Q4. The prospective reserved cohort", 1)[1].split("\n---", 1)[0]
    assert DOC_REL in q4 and "PROGRAM-Q4-REVISIT" in q4
    assert prog.count(DOC_REL) == 1

    fwar = _text(FWAR)
    header = fwar.split("\n## 0. ", 1)[0]
    bullets = [b for b in re.split(r"\n- ", header) if DOC_REL in b]
    assert len(bullets) == 1 and bullets[0].startswith("History, 2026-10-03")
    assert fwar.count(DOC_REL) == 1
    assert "Z1C_PITCHER_STUFF_GATE" not in fwar.split("## 9. Results", 1)[1]
    k = fwar.split("### (k) The registration that follows this one", 1)[1].split("\n### ", 1)[0]
    assert "Z1C_PITCHER_STUFF_GATE" not in k


def test_z1_is_not_edited_to_carry_the_leg():
    z1 = _text(Z1)
    assert "Z1C_PITCHER_STUFF_GATE" not in z1
    assert "**Z1c is not carried here.**" in z1
