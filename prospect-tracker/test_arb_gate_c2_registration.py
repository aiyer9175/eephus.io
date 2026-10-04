# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""GATE C2 REGISTRATION pins (docs/ARBITRATION_GATE.md section 11).

The registration is the whole point of a pre-registered gate, and this one
carries an unusual load: the owner ordered the control-window salary path
SERVED on 2026-09-16, before any clause had been scored, so section 11 scores
a served model rather than a candidate and a failing clause moves a served
number back rather than withholding a ship.

That only means something if the criteria cannot be edited once a result is
visible. This file is that ratchet. It pins the clause set, the two clauses
whose wording carries the teeth (C9's UNDERPOWERED rule and C2's kill rule),
the pre-registered response table, the must-not-move list, and the registry
row that points at all of it.

It does NOT pin any RESULT. Results land in the gate_c2 block of
data/arbitration_eval.json and are pinned by test_arb_path_gate.py, which is
a separate file on purpose: a result pin that lives beside a criterion pin
invites editing the criterion to match the result.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent
DOC = ROOT / "docs" / "ARBITRATION_GATE.md"


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _row() -> dict:
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    hits = [m for m in reg["models"] if m["model_id"] == "control_window_salary_path"]
    assert hits, "registry row control_window_salary_path is missing"
    return hits[0]


def test_section_11_exists_with_every_clause():
    doc = _doc()
    assert "## 11. GATE C2 - the control-window salary path (pre-registered 2026-09-16)" in doc
    for clause in ("C1'", "C2'", "C3'", "C4'", "C5'", "C6'", "C7'a", "C7'b", "C8'", "C9'"):
        assert f"| {clause} |" in doc, f"clause {clause} dropped out of the registration"


def test_the_registration_says_the_model_is_already_served():
    """The honesty clause. A gate written after the ship must say so, in the
    document, or a later reader will take the verdict for a bar that was
    cleared first."""
    doc = _doc()
    assert "**This gate scores a SERVED model, not a candidate.**" in doc
    assert "BEFORE any acceptance" in doc
    assert "ordered the path served in full" in doc
    assert "It is NOT true that these numbers cleared a bar before they reached a" in doc


def test_a_failure_has_a_mechanical_consequence():
    """A gate whose failure changes nothing is a note. The consequence is the
    flag, and 11e fixes per clause how far it moves."""
    doc = _doc()
    assert "MOVE THE SERVED NUMBER BACK" in doc
    assert "### 11e. The response to a failure, fixed in advance" in doc
    assert 'SALARY_PATH_MODE = "off"' in doc
    for clause in ("C2'", "C4'", "C6'", "C8'", "C9' FAIL", "C9' UNDERPOWERED (n < 25)"):
        assert f"| {clause} |" in doc, f"no pre-registered response for {clause}"


def test_c9_underpowered_verdict_is_registered_before_n_is_known():
    """C9' is the only external check on the control HORIZON and its n is
    small by construction, so the underpowered reading is registered now
    rather than argued once n is on the table. Underpowered is not a pass."""
    doc = _doc()
    assert "**n < 25**" in doc and "**UNDERPOWERED**" in doc
    assert "It is NOT read as a pass" in doc


def test_c2_is_the_clause_that_can_kill_the_change():
    doc = _doc()
    assert "**This is the owner's own check and it can kill the change**" in doc


def test_the_must_not_move_list_is_registered():
    """Registered here so the commit that moves the flag has a list to assert
    against, rather than a memory of one."""
    doc = _doc()
    assert "### 11f. Served numbers that must NOT move" in doc
    for phrase in ("published `tot`", "signed through 2028", "277 veterans",
                   "every prospect row", "Contract Surplus", "OrgSur+",
                   "every eFV number"):
        assert phrase in doc, f"must-not-move list lost: {phrase}"


def test_the_registry_row_points_at_the_registration():
    row = _row()
    assert row["verdict"] == "provisional"
    assert row["eval_artifact"] == "data/arbitration_eval.json"
    # The reader field names the gate; the docs/ path left the registry's
    # reader fields in COPY_11 (2026-10-04) and the gate doc itself is
    # asserted by the tests above.
    assert "Gate C2" in row["metric"]
    assert "gate_c2" in row["notes"] or "GATE C2" in row["notes"]
    assert "BEFORE ANY CLAUSE HAS BEEN SCORED" in row["notes"]
    assert "SALARY_PATH_MODE" in row["notes"]


def test_the_award_row_records_that_its_scope_widened():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    aw = [m for m in reg["models"] if m["model_id"] == "arb_award"][0]
    assert "2026-09-16 SCOPE EXTENSION" in aw["notes"]
    assert "control_window_salary_path" in aw["notes"]


def test_the_gate_does_not_claim_an_accuracy_win_it_did_not_measure():
    """Coverage change, not an accuracy change: the standing reading of this
    program, and the one a reader of a $9B move will reach for first."""
    doc = _doc()
    assert "61.3% of the added money is" in doc
    assert "that the award model became more accurate. It is unchanged." in doc
    assert "realized control-window surplus label set" in doc
