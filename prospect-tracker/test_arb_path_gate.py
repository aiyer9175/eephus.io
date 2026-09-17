# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""GATE C2 RESULT pins (data/arbitration_eval.json, block `gate_c2`).

Separate from test_arb_gate_c2_registration.py on purpose: that file pins the
CRITERIA, this one pins the RESULTS, and a result pin living beside a criterion
pin invites editing the criterion to match the result.

What this file will not let slip:
  * a clause that was never scored cannot read as a pass. NOT_SCORED and
    UNDERPOWERED are their own verdicts and each has to carry its blocking
    reason in the artifact;
  * every clause carries its criterion VERBATIM beside its number, so the
    receipt is readable without the gate doc open;
  * every clause carries its pre-registered response (section 11e), because a
    gate whose failure has no mechanical consequence is a note.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent

CLAUSES = ("c1_window_mae", "c2_realized_2026_awards", "c3_swartz_gap",
           "c4_reordering_is_the_coverage", "c5_monotone_paths",
           "c6_prospect_clamps", "c7a_floor_never_lowers",
           "c7b_backward_beats_forward", "c8_closure_chain",
           "c9_horizon_vs_service_time", "c10_salary_leg_star_tail")

VERDICTS = ("PASS", "FAIL", "NOT_SCORED", "UNDERPOWERED")


def _block():
    p = ROOT / "data" / "arbitration_eval.json"
    if not p.exists():
        pytest.skip("data/arbitration_eval.json not built")
    g = json.loads(p.read_text("utf-8")).get("gate_c2")
    if not g:
        pytest.skip("gate_c2 not scored yet (tools/arb_path_gate.py --write)")
    return g


def test_every_registered_clause_is_present_with_a_verdict():
    g = _block()
    for c in CLAUSES:
        assert c in g, f"clause {c} is missing from the receipt"
        assert g[c]["verdict"] in VERDICTS, (c, g[c]["verdict"])


def test_every_clause_publishes_its_criterion_and_its_response():
    """A number without its criterion beside it is not a receipt, and a
    criterion without a consequence is not a gate."""
    g = _block()
    for c in CLAUSES:
        assert g[c].get("criterion"), f"{c} has no criterion in the artifact"
        assert g[c].get("response_if_failed"), f"{c} has no pre-registered response"


def test_an_unscored_clause_says_why_and_never_reads_as_a_pass():
    g = _block()
    for c in CLAUSES:
        v = g[c]["verdict"]
        if v == "NOT_SCORED":
            assert g[c].get("blocking_reason") or g[c].get("n_scored") == 0, c
        if v == "UNDERPOWERED":
            assert g[c].get("n") is not None and g[c]["n"] < 25
            assert "not a pass" in json.dumps(g[c]).lower()


def test_the_receipt_says_the_model_was_already_served():
    g = _block()
    assert "SERVED MODEL, NOT A CANDIDATE" in g.get("order_of_events", "")
    assert g.get("served_mode") in ("off", "ladder", "closure", "full")


def test_c7a_publishes_the_criterion_conflict_instead_of_editing_it():
    """The registered C7'a wording asks for no negative surplus on a cuttable
    season. R1 - backward induction, shipped by the same spec - deliberately
    keeps one when a later season pays for it. The conflict is published with
    its count; the criterion is not rewritten."""
    g = _block()
    c = g["c7a_floor_never_lowers"]
    assert c.get("criterion_conflict_published_not_edited")
    assert c.get("negative_surplus_on_a_kept_cuttable_season") is not None


def test_c9_publishes_n_because_its_power_is_the_whole_question():
    g = _block()
    assert g["c9_horizon_vs_service_time"].get("n") is not None


def test_c8_says_what_it_does_not_test():
    g = _block()
    assert "HORIZON" in g["c8_closure_chain"].get("what_this_does_not_test", "")
    assert g["c8_closure_chain"].get("n_pool") is not None


def test_the_successor_question_is_named_in_the_artifact():
    """No clause scores surplus accuracy out of sample. Naming it here is how
    the hole stops being rediscovered as a finding."""
    g = _block()
    assert "realized control-window surplus label set" in g.get("successor_question", "")


def test_the_non_degrade_argument_is_recorded_not_re_derived():
    g = _block()
    nd = g.get("non_degrade") or {}
    assert nd.get("producer") == "surplus_backtest_real.py"
    assert "never reads" in nd.get("argument", "")


def test_the_salary_leg_star_tail_clause_is_scored_and_published():
    """C10' is the clause that says the thing the whole change leans on is
    biased, and in which direction. It fails today by design: the repair is
    upstream in arb_export and moves /arbitration/'s published ladder, so it
    carries its own gate. A future silent deletion of this clause would remove
    the only place the bias is written down, so the pin is on its PRESENCE and
    on its numbers, not on a passing verdict."""
    blk = _block()
    c10 = blk.get("c10_salary_leg_star_tail")
    assert c10, "C10' is not in the served gate block"
    assert c10["verdict"] in ("PASS", "FAIL")
    for k in ("served_max_usd", "realized_p90_usd", "rung_compression_x",
              "root_cause", "direction_on_the_served_number"):
        assert c10.get(k) is not None, k
    assert "war3" in c10["root_cause"] and "career_war" in c10["root_cause"]
    if c10["verdict"] == "FAIL":
        assert c10["served_max_usd"] < c10["realized_p90_usd"]
        # and the failure is registered as NOT moving the served number
        assert "NOT a revert" in c10["response_if_failed"]


def test_no_failing_clause_silently_moves_the_served_number():
    """A block verdict of FAIL is not an instruction. Each clause carries its
    own registered response, and the block has to say out loud which of the
    failing ones move the mode - otherwise a reader has to re-read ten response
    strings to find out whether the board he is looking at is the one the gate
    scored."""
    blk = _block()
    assert "failing_clauses" in blk
    moving = blk.get("failing_clauses_that_move_the_served_number")
    assert moving is not None
    for k in moving:
        assert blk[k]["verdict"] == "FAIL"
