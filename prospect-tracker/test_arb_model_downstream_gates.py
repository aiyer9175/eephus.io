# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /arbitration/ Model tab names the gates of the salary path (2026-09-25).

data/arbitration_eval.json carries gate_c_verification (GATE C, scored
2026-08-19) and is where GATE C2 writes its gate_c2 block. build_site never
read either, so the page that is the accountability surface for the award
model said nothing about the salary path that consumes it, and nothing said
that GATE C2 (registered 2026-09-16) has not been scored while the path
serves in mode "full". These tests read the artifact and the flag, never a
retyped figure.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

HERE = Path(__file__).parent


def _eval():
    p = HERE / "data" / "arbitration_eval.json"
    if not p.exists():
        pytest.skip("data/arbitration_eval.json not built")
    return json.loads(p.read_text(encoding="utf-8"))


def _panel():
    import build_site as B
    return B._arb_model_panel()


def test_an_unscored_gate_c2_is_published_as_not_scored():
    import salary_path
    ev = _eval()
    html = _panel()
    assert "GATE C2" in html
    if not ev.get("gate_c2"):
        m = re.search(r'<span class="arb-vd[^"]*">([^<]+)</span> GATE C2', html)
        assert m and m.group(1) == "NOT SCORED", m and m.group(1)
        assert f"<dd>{salary_path.SALARY_PATH_MODE}</dd>" in html


def test_gate_c_receipt_reads_the_artifact():
    ev = _eval()
    gc = ev.get("gate_c_verification")
    if not gc:
        pytest.skip("no gate_c_verification block")
    html = _panel()
    m = re.search(r'<span class="arb-vd[^"]*">([^<]+)</span> GATE C, the surplus '
                  r'consumer \(scored ([0-9-]+)\)', html)
    assert m, "GATE C receipt missing"
    assert m.group(1) == gc["verdict"] and m.group(2) == gc["scored_at"]
    served = gc["c1_per_player_vs_ladders"]["mae_usd"]["served"]
    assert "$%.2fM" % (served / 1e6) in html
