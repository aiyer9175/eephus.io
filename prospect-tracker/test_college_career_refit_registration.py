# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The career-label refit of the college translation stays registered, not scored.

Owner answer M20-3 (census M03-13): docs/COLLEGE_CAREER_REFIT_GATE.md names the
label, the minimum sample, the frame, the metric against the production fit,
the pass rule and one look on 2026-11-09. Before that date nothing may score it:
no eval artifact, no look directory, and the registry row says so.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).parent
GATE = ROOT / "docs" / "COLLEGE_CAREER_REFIT_GATE.md"
LOOK = dt.date(2026, 11, 9)


def _row() -> dict:
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    return next(m for m in reg["models"] if m["model_id"] == "college_translation_career_refit")


def test_registry_row_is_registered_not_scored():
    r = _row()
    assert r["registration_status"] == "registered, not scored"
    assert r["verdict"] == "provisional"
    assert r["eval_artifact"] is None
    assert "2026-11-09" in r["champion"]


def test_gate_names_every_preregistered_part():
    text = GATE.read_text(encoding="utf-8")
    for part in ("## 2. The label", "100 AB", "20 IP", "## 3. The frame", "promoted_key",
                 "## 4. Models compared", "## 5. Metric and pass rule", "seed 20261109",
                 "between 0.75 and 0.85", "**2026-11-09**", "## 7. Earlier measurements"):
        assert part in text, part


def test_nothing_is_scored_before_the_look():
    if dt.date.today() >= LOOK:
        return
    assert not (ROOT / "docs" / "college-career-refit-2026-11-09").exists()
    assert not any((ROOT / "data").glob("college_career_refit*"))
