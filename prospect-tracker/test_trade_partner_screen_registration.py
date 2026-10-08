# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Trade Machine partner screen's 2027-deadline read stays registered.

Owner answer W-OQ4 (a), 2026-10-01: docs/trademachine-2026-10/TRADE_PARTNER_SCREEN_GATE.md
registers one read after the 2027 deadline from daily frozen screen outputs. This pins
that the gate exists and names the look date, the statistic and the two baselines.
"""
from __future__ import annotations

import re
from pathlib import Path

GATE = Path(__file__).parent / "docs" / "trademachine-2026-10" / "TRADE_PARTNER_SCREEN_GATE.md"


def test_gate_names_the_look_date_the_statistic_and_both_baselines():
    assert GATE.exists()
    g = re.sub(r"\s+", " ", GATE.read_text(encoding="utf-8"))
    assert "**The one look is on 2027-08-05**" in g
    assert "**2027-08-05**, after the 2027 deadline" in g
    assert ("**The share of real acquirers inside the top five of the frozen screen per "
            "traded player**") in g
    assert "### 5.2 Baseline R: random among the 29 clubs" in g
    assert "Binomial(N, 5/29)" in g
    assert "### 5.3 Baseline C: contenders-only" in g
    assert "is **at least 0.25**" in g
