# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Result pins for the GATE A platform-season re-run
(docs/ARBITRATION_GATE.md section 13, scored 2026-10-08).

The registration pins live in test_arb_gate_a_platform_registration.py. This
file checks that the artifact carries the re-run where every consumer reads
it (the top-level GATE A fields), that the 2026-08-09 record survives as a
labelled hindcast with its own numbers, that the same-day award-frame twin is
present and adjudicates nothing, and that each verdict follows from its own
numbers under the section 4 rule.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def _ev() -> dict:
    p = ROOT / "data" / "arbitration_eval.json"
    if not p.exists():
        pytest.skip("no eval artifact")
    return json.loads(p.read_text(encoding="utf-8"))


def test_the_top_level_block_is_the_platform_frame():
    ev = _ev()
    assert ev["frame"] == "platform"
    assert "--frame platform" in ev["produced_by"]
    assert ev["seed"] == 20260808 and ev["B"] == 1200
    assert set(ev["results"]) == {"arb1", "arb2plus"}


def test_the_award_frame_record_is_a_labelled_hindcast():
    ev = _ev()
    hc = ev["hindcast_2026_08_09_award_frame"]
    assert hc["generated_at"] == "2026-08-09"
    assert hc["label"].startswith("HINDCAST.")
    assert "adjudicates nothing" in hc["label"]
    # the 2026-08-09 numbers, moved verbatim
    assert round(hc["results"]["arb1"]["gain_over_floor"], 3) == 3.287
    assert hc["results"]["arb2plus"]["verdict"] == "NULL"
    assert hc["a6_swartz"]["n"] == 261


def test_the_same_day_twin_is_present_and_adjudicates_nothing():
    ev = _ev()
    tw = ev["award_frame_same_day_twin"]
    assert tw["frame"] == "award"
    assert "adjudicates nothing" in tw["role"]
    assert tw["pool"] == ev["pool"], "the twin must score the same day's pool"


@pytest.mark.parametrize("name", ["arb1", "arb2plus"])
def test_each_verdict_follows_from_its_own_numbers(name):
    r = _ev()["results"][name]
    resolvable = abs(r["mdape_gain"]) >= r["mde95_onesided"]
    beats = r["mdape_gain"] > r["a3_control"]["permuted_p95"]
    leak = r["a5_deflator_leak_twin"]["leak_smaller_than_margin"]
    assert r["verdict"] == ("PASS" if (resolvable and beats and leak) else "NULL")


def test_the_artifact_verdict_follows_the_steps():
    ev = _ev()
    ship = any(r["verdict"] == "PASS" for r in ev["results"].values())
    assert ev["verdict"] == ("provisional" if ship else "unvalidated")


def test_downstream_blocks_survive_the_rewrite():
    """arb_gate_a.py used to overwrite the whole file; the GATE C record must
    survive a GATE A write."""
    ev = _ev()
    assert ev["gate_c_verification"]["scored_at"] == "2026-08-19"
