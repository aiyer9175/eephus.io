# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The fWAR label epoch's RESULT pin (docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md
part 9, the step Z entry of 2026-10-03).

test_fwar_label_epoch_registration.py pins the criteria and, since that entry,
points here for the result, so that a result pin never sits beside a criterion
pin (the reason test_arb_gate_c2_registration.py gives). This file pins three
things:

  1. The entry exists under a dated step Z heading, carries the LABEL FREEZE
     RECEIPT (the vintage id and the label= term, the per-side coverage, the E7
     receipt with its sha256), the display state under EPOCH-Q4, the FAILED ARM
     F6 and the shipped configuration with every dropped factor named.
  2. The dispositions the entry writes are the ones the committed eval artifact
     carries (clause (d) per side, Arm R's clauses, the A1/A2 sign rule), so the
     prose cannot drift from data/xfv_fwar_label_epoch_eval.json.
  3. Clause (l) holds inside the entry: no sentence claims the basis made a
     model more accurate, better calibrated or closer to the truth.

A later re-measurement goes to part 9 as a NEW dated entry (clause (i) point
7); it does not edit this one, and this pin is extended, not rewritten.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "efv-2026-09-17" / "FWAR_LABEL_EPOCH_GATE.md"
EVAL = ROOT / "data" / "xfv_fwar_label_epoch_eval.json"
VINTAGE_ID = "2026-10-02-0341299c20ec"
E7_RECEIPT = ROOT / "data" / "_labs" / "fwar_epoch_arms" / "e7_receipt.json"
E7_SHA256 = "65e7c8c9c5a897050f46ce1504c4b9ae4da3a671ec9165cfa6d7088ab5146499"
HEADING = "### 2026-10-03: step Z, the fWAR label epoch's results"


def _entry() -> str:
    doc = DOC.read_text(encoding="utf-8").replace("\r\n", "\n")
    body = doc.split("## 9. Results", 1)[1]
    assert HEADING in body, "the step Z entry is missing from part 9"
    entry = body.split(HEADING, 1)[1]
    return entry.split("\n---\n", 1)[0]


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _eval() -> dict:
    return json.loads(EVAL.read_text(encoding="utf-8"))


def test_the_entry_sits_under_a_dated_step_z_heading_in_part_9():
    doc = DOC.read_text(encoding="utf-8")
    above, below = doc.split("## 9. Results", 1)
    assert HEADING not in above
    assert re.search(r"^### \d{4}-\d{2}-\d{2}: step Z", below, re.M)


def test_the_label_freeze_receipt_has_its_three_items():
    flat = _flat(_entry())
    assert "#### The LABEL FREEZE RECEIPT" in _entry()
    assert f"`vintage_id` `{VINTAGE_ID}`" in flat
    assert f"`label=fwar@{VINTAGE_ID}`" in flat
    assert "Share 100.0 percent in every cohort band and every fold on both sides" in flat
    assert "hitters 968 of 968 debuted rows matched (share 1.0000)" in flat
    assert "pitchers 1,116 of 1,116 (share 1.0000)" in flat
    assert E7_SHA256 in flat


def test_the_receipts_match_the_committed_files():
    assert hashlib.sha256(E7_RECEIPT.read_bytes()).hexdigest() == E7_SHA256
    rec = json.loads(E7_RECEIPT.read_text(encoding="utf-8"))
    assert rec["vintage_id"] == VINTAGE_ID
    import fwar_vintage
    import storage
    # The 2026-10-15 plate-appearance amendment (EWAR_P0_VINTAGE_PA, owner answer EW3-19)
    # gave the vintage a new id. The step Z id stays on its WAR-identical lineage, and the
    # fingerprint names the lineage's head, the vintage on disk.
    lineage = fwar_vintage.war_lineage(fwar_vintage.load())
    assert VINTAGE_ID in lineage
    import war_source
    if war_source.EFV_LABEL_PROVIDER == "ewar_headline":
        # eFV's label moved to the headline eWAR (EWAR_HEADLINE_LABEL_GATE.md), whose frozen
        # vintage is built on the lineage's head and names it
        assert f"label=ewar_headline@ewar-headline-{lineage[0]}-" in storage.BOARD_BASIS_FINGERPRINT
    else:
        assert f"label=fwar@{lineage[0]}" in storage.BOARD_BASIS_FINGERPRINT
    cov = _eval()["clause_c_coverage"]
    for side in ("hit", "pit"):
        for band in cov[side]["by_cohort_band"].values():
            assert band["share"] == 1.0 and band["players_no_id"] == 0, side


def test_clause_d_dispositions_are_the_artifacts():
    d = _eval()["clause_d_tost"]
    flat = _flat(_entry())
    assert d["hit"]["disposition"].startswith("RULED OUT")
    assert d["pit"]["disposition"] == "UNDECIDED"
    assert "RULED OUT (equivalent within the registered margin)" in flat
    assert "UNDECIDED: the interval is neither inside nor entirely beyond the 0.02 margin" in flat
    assert f"E_cond CI95 [{d['hit']['E_cond_ci95'][0]}, {d['hit']['E_cond_ci95'][1]}]" in flat
    assert f"E_cond CI95 [{d['pit']['E_cond_ci95'][0]}, {d['pit']['E_cond_ci95'][1]}]" in flat
    assert "Holm changes neither disposition" in flat


def test_the_candidates_and_the_shipped_configuration():
    cand = _eval()["candidate_clauses"]
    flat = _flat(_entry())
    for side in ("hit", "pit"):
        assert cand[side]["F3_arm_r"]["ships_on_its_own_clauses"] is True, side
        assert cand[side]["a1_a2_sign_agreement"]["disagree_in_sign"] is True, side
    assert "Arm R's clauses PASS" in flat
    assert "so NEITHER ships" in flat
    assert "E* as built is not E* as shipped: F4 (A1) and F5 (A2) are dropped" in flat
    assert "The served artifacts at this entry carry F1, F2 and F6 only" in flat
    assert "FAILED ARMS: F6" in flat and "attribution is UNAVAILABLE" in flat
    assert "interaction, unattributed" in flat


def test_the_display_state_under_epoch_q4():
    flat = _flat(_entry())
    assert "The displayed WAR is eWAR v2" in flat
    assert "NOT TAKEN, with the owner's answer EPOCH-Q4" in flat
    assert "EPOCH_FWAR_REFERENCE_COLUMN" in flat
    assert "orchestrator ruling: the gate's placement" in flat
    assert "8,703 of 8,703" in flat


def test_the_carried_abort_reads_the_served_board():
    flat = _flat(_entry())
    assert "membership change top 10 / 25 / 100 / 250 = 0 / 0 / 0 / 1" in flat
    assert "The carried abort (\"abort if top-10 board membership changes\") is NOT tripped" in flat


def test_clause_l_no_accuracy_claim_from_the_basis():
    text = _entry().lower()
    for phrase in ("more accurate", "better calibrated", "closer to the truth",
                   "improves accuracy", "improved accuracy", "accuracy gain from"):
        for m in re.finditer(re.escape(phrase), text):
            window = text[max(0, m.start() - 160):m.end() + 40]
            assert "no " in window or "not" in window or "never" in window, (
                f"part 9's step Z entry carries an accuracy claim: {window!r}")


def test_served_changes_reopen_after_the_entry():
    assert "After this entry, served changes may land again (2026-10-03)." in _flat(_entry())
