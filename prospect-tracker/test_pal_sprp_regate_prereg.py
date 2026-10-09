# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins the SP to RP re-gate pre-registration (owner answer M22-3, 2026-09-25).

The section lives in docs/e3-rp-sp-closure.md. These tests check that it exists,
that it names one look date after the fWAR label epoch's step Z entry and off
the registered look days, that the pal_conversion registry note points to it,
and that no re-gate result exists before the look date. They compute nothing.
"""

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "e3-rp-sp-closure.md"
EPOCH_DOC = ROOT / "docs" / "efv-2026-09-17" / "FWAR_LABEL_EPOCH_GATE.md"
REGISTRY = ROOT / "data" / "model_registry.json"
HEADING = "## 2026-10-08: SP to RP re-gate, pre-registered (owner answer M22-3)"
LOOK_DATE = date(2026, 11, 3)
# Look days other gates hold (orchestrator date rules); the re-gate may not share one.
BLOCKED_LOOK_DAYS = {date(2026, 10, 23), date(2026, 11, 6), date(2026, 11, 13),
                     date(2026, 11, 20), date(2026, 12, 1)}


def _section() -> str:
    text = DOC.read_text(encoding="utf-8")
    assert HEADING in text, "re-gate pre-registration section is missing"
    body = text.split(HEADING, 1)[1]
    nxt = re.search(r"^## ", body, flags=re.M)
    return body[: nxt.start()] if nxt else body


def test_section_exists_and_names_its_look_date():
    sec = _section()
    m = re.search(r"\*\*Look date: (\d{4}-\d{2}-\d{2})\.\*\*", sec)
    assert m, "the section must state its look date as '**Look date: YYYY-MM-DD.**'"
    assert date.fromisoformat(m.group(1)) == LOOK_DATE
    assert LOOK_DATE not in BLOCKED_LOOK_DAYS


def test_look_date_is_after_step_z():
    epoch = EPOCH_DOC.read_text(encoding="utf-8")
    m = re.search(r"^### (\d{4}-\d{2}-\d{2}): step Z", epoch, flags=re.M)
    assert m, "the fWAR epoch's step Z entry is missing"
    assert LOOK_DATE > date.fromisoformat(m.group(1))
    assert "step Z" in _section()


def test_section_fixes_the_frame_and_rule():
    sec = _section()
    for needle in ("unseen 2026", "Minimum n:** 15", "seed 20260714", "lo95 > -0.01",
                   "`era_pre`", "`need_shrunk`", "`neg_war_pre`", "structural screen",
                   "reported\n  sensitivity only", "TR_5_FLIP"):
        assert needle in sec.replace("\r\n", "\n"), needle


def test_registry_note_points_to_section():
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    row = next(m for m in reg["models"] if m["model_id"] == "pal_conversion")
    notes = row["notes"]
    assert "docs/e3-rp-sp-closure.md" in notes
    assert "2026-10-08: SP to RP re-gate, pre-registered (owner answer M22-3)" in notes
    assert "LOOK DATE " + LOOK_DATE.isoformat() in notes
    assert row["verdict"] == "provisional"


def test_no_result_before_the_look():
    if date.today() >= LOOK_DATE:
        return
    hits = sorted(p.name for p in (ROOT / "data").glob("*regate*")
                  if "sprp" in p.name.lower() or "sp_rp" in p.name.lower())
    assert not hits, f"a re-gate artifact exists before the look date: {hits}"
