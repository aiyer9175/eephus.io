# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR v3 valuation input gate stays registered and unread.

Owner answer SWAR-Q4 (c), 2026-10-01: docs/ewar-v3/EWAR_V3_VALUATION_GATE.md registers one
look comparing eWAR v3 with the fWAR label as the WAR input of the FA module and the Trade
Machine. This pins that the gate exists, names the look date, both consumers' statistics, the
Holm rule and the null comparator, and that its registry row is registered and not read.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
GATE = HERE / "docs" / "ewar-v3" / "EWAR_V3_VALUATION_GATE.md"
REG = HERE / "data" / "model_registry.json"


def test_gate_names_the_look_the_statistics_and_the_pass_rule():
    assert GATE.exists()
    g = re.sub(r"\s+", " ", GATE.read_text(encoding="utf-8"))
    assert "**The one look is on 2027-11-03**" in g
    assert "**Incumbent F: the corpus WAR on `fwar`, the frozen fWAR vintage.**" in g
    assert "**Incumbent T: the corpus WAR on `fwar` through `surTotal` for modeled MLB rows.**" in g
    assert "**F: FA Hard Gate 2**" in g and "**guarantee MAE in $M NPV**" in g
    assert "**rank Spearman of `trade_value_mm` against realized WAR**" in g
    assert "**Holm across the two consumers**, m = 2, family alpha 0.05" in g
    assert "**Null comparator.**" in g
    assert "at least **30** scored units" in g
    assert "## 8. Crash protocol" in g and "## 11. Read to write this" in g
    assert "\u2014" not in g and "\u2013" not in g


def test_registry_row_is_registered_not_read():
    rows = {m["model_id"]: m for m in json.loads(REG.read_text(encoding="utf-8"))["models"]}
    row = rows["ewar_v3_valuation_input"]
    assert row["verdict"] == "unvalidated"
    assert row["registration_status"] == "registered, not read"
    assert row["eval_artifact"] is None
    assert "docs/ewar-v3/EWAR_V3_VALUATION_GATE.md" in row["notes"]
