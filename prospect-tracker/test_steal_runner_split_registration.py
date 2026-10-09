# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The runner-aware steal split (W11 stage 2) stays registered, not read.

Owner answer W-OQ3 (b): docs/management-2026-10/STEAL_RUNNER_SPLIT_GATE.md names
the candidate, the frame (fit 2018-2023, tune 2024, one score on 2025), the
statistic (paired log loss and Brier against the league-average-runner incumbent,
a game bootstrap of 2000 draws), the pass rule and one look on 2026-10-20. These
pins hold the registration as TEXT; prose is compared whitespace-flattened, so a
re-wrapped paragraph passes and an edited criterion fails. Before the look date
nothing may score it: no eval artifact, no look directory, and the registry row
says so.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
GATE = ROOT / "docs" / "management-2026-10" / "STEAL_RUNNER_SPLIT_GATE.md"
LOOK = dt.date(2026, 10, 20)
EVAL = ROOT / "data" / "steal_runner_split_eval.json"
LOOK_DIR = ROOT / "docs" / "management-2026-10" / "look-steal-runner-split"


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _row() -> dict:
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    return next(m for m in reg["models"] if m["model_id"] == "steal_runner_split")


def test_gate_exists_and_names_frame_statistic_and_look():
    assert GATE.exists()
    text = _flat(GATE.read_text(encoding="utf-8"))
    for part in (
        # the frame
        "## 3. The frame", "management.attempts()", "Fit: 2018, 2019, 2021, 2022, 2023",
        "Tuning: 2024", "Score: 2025, once", "`mgmt_decisions.detect_steals`",
        "`mgmt_steal_context.catcher_of`",
        # the statistic
        "## 4. The statistic", "log loss", "Brier", "B = 2000", "seed 20261020",
        "one-sided 95% lower bound",
        # the pass rule, the look, the bans
        "## 5. The pass rule and what a null means", "the split stays dark",
        "**Date: 2026-10-20**", "**never rerun**", "## 7. The bans",
        "**DV is untouched**", "**never prices a steal in the Diamond**",
        "## 10. Read to write this",
    ):
        assert _flat(part) in text, part


def test_registry_row_is_registered_not_read():
    r = _row()
    assert r["registration_status"] == "registered, not read"
    assert r["verdict"] == "unvalidated"
    assert r["eval_artifact"] is None
    assert "2026-10-20" in r["summary"]


def test_nothing_is_scored_before_the_look():
    if dt.date.today() >= LOOK:
        return
    assert not EVAL.exists()
    assert not LOOK_DIR.exists()
