# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The runner-aware steal split (W11 stage 2): registered, then read once, NULL.

Owner answer W-OQ3 (b): docs/management-2026-10/STEAL_RUNNER_SPLIT_GATE.md names
the candidate, the frame (fit 2018-2023, tune 2024, one score on 2025), the
statistic (paired log loss and Brier against the league-average-runner incumbent,
a game bootstrap of 2000 draws), the pass rule and one look on 2026-10-20. These
pins hold the registration as TEXT; prose is compared whitespace-flattened, so a
re-wrapped paragraph passes and an edited criterion fails.

The one read ran on 2026-10-14 as an OWNER-WAIVED EARLY READ (EW3-5) and was a
NULL on pass condition 4. The pins below hold the record: the eval artifact, the
look directory with its teed log and frozen fit, the registry row moved to
deprecated with the failed condition named, and section 11 of the gate carrying it.
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


def test_registry_row_records_the_one_read():
    r = _row()
    assert r["registration_status"].startswith("read once")
    assert r["eval_artifact"] == "data/steal_runner_split_eval.json"
    art = json.loads(EVAL.read_text(encoding="utf-8"))
    # gate section 5: a NULL moves the row to deprecated, a PASS makes it eligible
    assert r["verdict"] == ("deprecated" if art["verdict"] == "NULL" else "provisional")
    assert "condition 4" in r["notes"] and "READ 2026-10-14 (W11_3)" in r["notes"]


def test_the_read_is_on_record_once():
    assert EVAL.exists() and LOOK_DIR.exists()
    for name in ("look_stdout_stderr.log", "frozen_fit.json", "look_record.json"):
        assert (LOOK_DIR / name).exists(), name
    art = json.loads(EVAL.read_text(encoding="utf-8"))
    assert art["verdict"] == "NULL"
    assert art["failed_conditions"] == ["4_dLL_runner_lower_bound_above_0"]
    assert art["served"] is False and art["dv_unchanged"] is True
    assert art["read"]["run_date"] == "2026-10-14"
    # read before the registered date: recorded as the owner's waiver
    assert dt.date.fromisoformat(art["read"]["run_date"]) < LOOK
    assert "OWNER-WAIVED EARLY READ" in art["read"]["kind"]
    rec = json.loads((LOOK_DIR / "look_record.json").read_text(encoding="utf-8"))
    assert rec["conditions"] == art["conditions"]
    log = (LOOK_DIR / "look_stdout_stderr.log").read_text(encoding="utf-8")
    assert "VERDICT NULL" in log and "EXIT 0" in log
    # the fit was frozen before the score frame was read
    assert log.index("frozen: candidate lambda") < log.index("reading the score frame now")
    text = _flat(GATE.read_text(encoding="utf-8"))
    assert "**Read once, 2026-10-14: NULL.**" in text
    assert "## Note 2026-10-14: an owner-waived early read" in text
