# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The fWAR label epoch registration pins (docs/efv-2026-09-17/).

The registration is the plan's E4: it is committed ALONE and BEFORE the
rebuild it governs, so that a bundled rebuild of two factors cannot decide
afterwards what it was measuring. This file is the ratchet on that.

It pins five things:

  1. Clauses (a) to (h) are the predecessor's clauses VERBATIM. The check is
     a byte-identical substring of docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md
     rather than a phrase list, because "verbatim" is the whole point: a
     clause edited to suit the new epoch is a new clause.
  2. The reading imposed on those carried clauses: the substitution, the eight
     notes, and the disposition of the predecessor's parts 5 and 7. A clause
     carried verbatim and then quietly widened by a note is the failure this
     mechanism exists to catch, so the two notes that override a carried
     clause are pinned by the sentence that bounds the override.
  3. The four clauses this epoch adds, (i) to (l), each pinned by every
     sentence that makes it BIND, not by its heading. A heading with its teeth
     removed is a note, and the first draft of this file caught 12 of 12
     dropped sections while missing 7 of 9 dropped teeth.
  4. The decision and its date, the bundle and its reason, the E1 to E8 status
     checklist with the per-step blocking map, the frozen ride list and the
     A to Z runbook.
  5. That NO RESULT is recorded, checked case-insensitively below part 9 and
     by result-shaped patterns above it, because the document's own rule is
     "None may be written anywhere above this line".

It does NOT pin a result, and it cannot: there is none. When part 9 is filled
in, the result pin goes in its own file, for the reason
test_arb_gate_c2_registration.py gives - a result pin that lives beside a
criterion pin invites editing the criterion to match the result. The emptiness
assertion below is replaced at that point by a pointer to that file, and the
replacement is itself a commit somebody has to justify.

Prose assertions run against a whitespace-flattened copy of the document, so
that re-wrapping a paragraph is not a test failure. The verbatim check does
not: it is byte-exact on purpose.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "efv-2026-09-17" / "FWAR_LABEL_EPOCH_GATE.md"
PREDECESSOR = ROOT / "docs" / "efv-2026-09-03" / "EWAR_LABEL_EPOCH_GATE.md"

CLAUSE_START = "### (a) Same-label margins only, floors first, both sides"
CLAUSE_END = "## 4. Coordination obligations"

RESULTS_HEADING = "## 9. Results"


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _row(doc: str, prefix: str, after: str, before: str) -> str:
    """The one table row starting with `prefix`, inside one named region.

    The region bounds matter: part 3 carries two tables that both have an
    `| E2 |` row, and the precondition verdict is the one being pinned.
    """
    region = doc[doc.index(after):doc.index(before)]
    rows = [ln for ln in region.splitlines() if ln.startswith(prefix)]
    assert len(rows) == 1, f"expected exactly one row starting {prefix!r}, got {len(rows)}"
    return rows[0]


def _precondition_row(doc: str, prefix: str) -> str:
    return _row(doc, prefix, "## 3. Preconditions E1 to E8",
                "**The rule this table is for.**")


def _runbook_row(doc: str, prefix: str) -> str:
    return _row(doc, prefix, "## 7. The rebuild:",
                "**The letters name artifacts, not a running order.**")


def _carried_clauses() -> str:
    """The predecessor's clause block, from (a) through the end of (h)."""
    text = PREDECESSOR.read_text(encoding="utf-8")
    start = text.index(CLAUSE_START)
    end = text.index(CLAUSE_END)
    block = text[start:end].rstrip("\n")
    assert "### (h) Stop clauses" in block, "clause span lost its tail"
    return block


def test_the_registration_exists_and_says_it_only_registers():
    flat = _flat(_doc())
    assert "# fWAR label epoch: pre-registration (2026-09-17)" in flat
    assert "STATUS: REGISTERED, RESULTS EMPTY." in flat
    assert "committed ALONE and BEFORE the rebuild it governs" in flat
    assert "the registration registers, it does not rebuild" in flat


def test_the_document_names_the_test_that_pins_it():
    """The house form (ARBITRATION_GATE.md part 11) names its pin, so a reader
    who arrives at the gate can find what enforces it."""
    assert "test_fwar_label_epoch_registration.py" in _doc()


def test_clauses_a_to_h_are_carried_verbatim():
    """Byte-identical, not paraphrased. If the predecessor is ever edited this
    fails loudly, which is the correct outcome: one of the two files would then
    carry a clause the other does not."""
    block = _carried_clauses()
    assert block in _doc(), (
        "clauses (a)-(h) are not a byte-identical copy of "
        "docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md part 3")


def test_every_carried_clause_heading_is_present():
    doc = _doc()
    for heading in (
            "### (a) Same-label margins only, floors first, both sides",
            "### (b) The cross-label matrix",
            "### (c) Coverage clause",
            "### (d) TOST margin on the swap's effect",
            "### (e) Controls",
            "### (f) Blast radius, MEASURED and published",
            "### (g) Copy contract",
            "### (h) Stop clauses"):
        assert heading in doc, f"carried clause dropped out: {heading}"


def test_the_substitution_rule_and_all_eight_notes_are_present():
    flat = _flat(_doc())
    assert "the substitution rule, stated once" in flat
    assert '"bWAR" reads as "eWAR v2"' in flat
    for note in ("Note 1.", "Note 2.", "Note 3.", "Note 4.", "Note 5.",
                 "Note 6.", "Note 7.", "Note 8."):
        assert f"**{note}" in flat, f"substitution note missing: {note}"


def test_the_clause_h_kind_override_is_named_and_bounded():
    """Clause (h) forbids a feature arm and admits only label-definition
    fixes. Part 6 admits two factors it would bar. Carrying the clause verbatim
    and then contradicting it in part 6 is exactly the widening the notes exist
    to prevent, so the override is recorded as an OWNER decision, named to two
    factors, and closed to any third."""
    flat = _flat(_doc())
    assert ("Clause (h)'s KIND restriction is OVERRIDDEN for exactly two named factors, "
            "by owner decision, and for no others") in flat
    assert "`RESOLVED_THROUGH` by O2 of 2026-09-17" in flat
    assert "F-DEF by the owner's answer of 2026-09-11" in flat
    assert "no other factor may use it" in flat
    assert "no feature arm other than F-DEF" in flat
    # and the flat restatement in clause (k) carries the exception with it
    assert ("Clause (h) forbids a feature arm inside this epoch, with the single named "
            "exception note 7 records") in flat
    # part 6's two override rows say so at the point of admission
    doc = _doc()
    assert doc.count("clause (h) kind override, note 7") == 2


def test_clause_g_frame_disclosure_is_not_carried_by_substitution():
    """Clause (g) spells out the eWAR v2 frame. Substituting labels into that
    sentence describes published fWAR falsely: it is not a B-Ref run frame and
    its position players are not identical to the incumbent."""
    flat = _flat(_doc())
    assert "Clause (g)'s MECHANISM carries; its frame-disclosure CONTENT does not" in flat
    assert "produces a FALSE description of published fWAR" in flat
    assert "step X re-resolves them by name and never trusts a line number" in flat


def test_the_predecessor_parts_5_and_7_are_dispositioned_rather_than_dropped():
    """The interpretations and the abort conditions are not clauses, so they are
    not in the verbatim block. Dropping them silently loses the half of the
    registration that says what a result MEANS."""
    doc = _doc()
    flat = _flat(doc)
    assert "### 4.3 The predecessor's parts 5 and 7, each carried, void or replaced" in doc
    assert ("**Part 5, the pre-committed interpretations. CARRIED, with one replacement.**"
            in flat)
    assert "**Part 7, the abort conditions. Two carry, one is void, one is replaced.**" in flat
    assert "VOID: the two conditions on the rescaled league eWAR sum for 2011-2015" in flat
    assert ("abort if the `career_war` rebase leaves any season of any player with NEITHER an "
            "fWAR nor an eWAR v2 value") in flat
    assert "abort if top-10 board membership changes" in flat
    assert "the abort condition it wrote was FALSIFIED by the rebuild it governed" in flat


def test_clause_i_has_all_of_its_teeth():
    """A bundled rebuild with no arms cannot say which factor moved a number,
    so clause (i) is the price of the bundle. Each sentence below is one that
    an execution could quietly drop and still look like it had arms."""
    doc = _doc()
    flat = _flat(doc)

    assert "### (i) The attribution arms" in doc
    assert "`effect_f = Q(E*) - Q(E* minus f)`" in flat
    assert "interaction, unattributed" in flat
    assert "Publishing it is the clause" in flat
    assert "Making it small is not" in flat
    # the arm kinds: a bundle arm has no matrix, so it is not counted as one
    assert "BUNDLE arm, inside step M and downstream of step F" in flat
    assert "It is NOT an eFV matrix and no matrix is built for it" in flat
    for fid in ("| F1 |", "| F2 |", "| F3 |", "| F4 |", "| F5 |", "| F6 |"):
        assert fid in doc, f"clause (i) arm table lost {fid}"
    # k is not frozen while O7 is open, and it is fixed before the first matrix
    assert "**k is NOT frozen at this commit" in flat
    assert ("arm set is FIXED at the moment O7 is answered, and in any case BEFORE the first "
            "matrix is built at step F") in flat
    assert "leave-one-out set and never a factorial" in flat
    # the order of operations, because the candidate's definition is circular
    assert 'cannot be defined as "every candidate that passes its own clauses"' in flat
    assert "as built is not necessarily E" in flat
    assert "part 9 says so in those words and names every factor dropped" in flat
    # a failed arm is UNAVAILABLE, never inferred
    assert "is a FAILED ARM" in flat
    assert ("recorded as UNAVAILABLE. It is never inferred from the total and never estimated "
            "from the other arms") in flat
    # arms share one run, one seed convention, one fold structure
    assert "Arms are built in the same run, on the same seed convention and the same folds" in flat
    assert "An arm rebuilt later on a different frame is not an arm" in flat
    # arms do not re-decide the owner's decision
    assert "No arm is a ship condition for O1 or O2" in flat


def test_clause_j_has_all_of_its_teeth():
    doc = _doc()
    flat = _flat(doc)

    assert "### (j) `star_out`, `lineup_strength` and the dark betting columns" in doc
    assert '"betting has zero WAR readers" is FALSE' in flat
    assert "**Step M does not run before 2026-10-05**" in flat
    # 5c-C's window is quoted, not paraphrased, and the conclusion is derived
    assert ("`lv.as_of(date)` prices it on a vintage dated 2026-09-05 to 2026-10-04" in flat)
    assert '"it is dated before 2026-10-05"' in flat
    assert '"it is `gameType` R"' in flat
    assert "The conclusion is DERIVED from that, not substituted for it" in flat
    # this gate sequences around 5c and never amends it
    assert ("This gate may not move a 5c criterion, threshold, window, split or bucket rule, "
            "and does not") in flat
    # the basis change must be visible to the stamp
    assert ("the commit that carries step D or step E writes the corpus `war_provider` into "
            "the projections bundle") in flat
    assert "A basis change the stamp cannot see is a silent construction change" in flat
    # the skipped close job, recorded where a later reader would look for a price
    assert "The close job on the deploy box is SKIPPED by owner decision of 2026-09-17" in flat
    assert "there will be no close-price captures this season" in flat
    assert "No clause in this gate reads a price" in flat


def test_clause_k_points_at_the_next_registration_without_promising_it():
    doc = _doc()
    flat = _flat(doc)
    assert "### (k) The registration that follows this one" in doc
    assert "LABEL_V3_DRIVER_RETEST_GATE.md" in flat
    assert "committed ALONE with an empty results section" in flat
    assert "No result of Z1 may be recorded in this document" in flat
    assert "zero survivors" in flat
    assert "0 of 48 arms and 0 of 177" in flat
    assert "coherence and a permanent close, not a driver that passes" in flat


def test_clause_l_has_all_of_its_teeth():
    """The last basis epoch measured a null on this exact question. The
    prohibition list and its enforcement are the clause; the heading is not."""
    doc = _doc()
    flat = _flat(doc)

    assert "### (l) Copy may never claim an accuracy gain from a basis change" in doc
    assert "The last basis epoch of this class MEASURED THIS EXACT QUESTION AND FOUND A NULL" in flat
    # the prohibition itself, with the surfaces it names
    assert ("No served string, glossary entry, methodology page, changelog line, model "
            "registry note, article, commit message or release note may say that published "
            "fWAR makes") in flat
    assert "more accurate, better calibrated or closer to the truth" in flat
    assert "The permitted claim is COHERENCE" in flat
    assert "MOVEMENT IS NOT ACCURACY" in flat
    # enforcement, not merely statement
    assert "The clause is enforced, not merely stated" in flat
    assert ("The copy sweep (step X) and `copy_lint --check` run before `build_site` (step T)"
            in flat)
    assert "This clause binds the results section of this document too" in flat


def test_the_star_out_correction_is_carried_instead_of_the_plan_sentence_it_replaces():
    """The committed 5c-C text corrects the plan: star_out's ranking moves at
    steps D and E, not at step M. A gate that sequenced itself off the wrong
    step would ungrade a registered dark column's window and never know."""
    flat = _flat(_doc())
    assert "it does NOT move at step M" in flat
    assert 'read as "steps D and E" for this column' in flat
    assert "bucket 2 (post-retrain)" in flat


def test_clause_a_regen_control_is_voided_rather_than_inherited():
    """Under eWAR the hitter label did not move, so hitters were the control.
    Here hitters are the side that moves most. Inheriting the clause silently
    would hand the epoch a control that cannot work."""
    flat = _flat(_doc())
    assert "Clause (a)'s regen control is VOID on this epoch, and is REPLACED" in flat
    assert "There is no side that stands still" in flat
    assert "zero-information twin, computed PER SIDE" in flat


def test_the_owner_decision_and_its_date_are_recorded():
    doc = _doc()
    flat = _flat(doc)
    assert "## 1. Decision record (owner, 2026-09-17, taken in chat)" in doc
    assert "PUBLISHED fWAR" in flat
    assert "FROZEN PER SEASON" in flat
    assert "**Date.** 2026-09-17." in flat
    assert ("**The WAR label basis is an OWNER BASIS DECISION. "
            "It ships regardless of margin.**") in flat


def test_the_bundle_and_the_reason_for_it_are_recorded():
    flat = _flat(_doc())
    assert "`RESOLVED_THROUGH` advance from 2025 to 2026 ship in ONE rebuild" in flat
    assert "at the close of the 2026 regular season" in flat
    assert "The cost is attribution" in flat
    assert "Clause (i) is the price paid for the bundle, and it is not optional" in flat


def test_every_precondition_row_carries_a_status_read_today():
    doc = _doc()
    flat = _flat(doc)
    assert "## 3. Preconditions E1 to E8, with today's status" in doc
    for n in range(1, 9):
        assert f"| E{n} |" in doc, f"precondition E{n} is missing"
    for verdict in ("**PARTIAL.**", "**NOT MET.**", "**IN HAND at this commit**",
                    "**MET, with receipts.**", "**NOT MET, in five parts.**",
                    "**NOT MET, and the dates have MOVED.**"):
        assert verdict in flat, f"status text missing: {verdict}"
    # the preamble reports the tree it was read against exactly
    assert "73 dirty entries" in flat


def test_the_unmet_preconditions_stay_unmet():
    """Flipping a row's verdict is a one-word edit that nothing else catches.
    E2 (identity) and E3 (the vintage, the loader, the provider, the tool) are
    the two that block the rebase, so their verdicts are pinned at the row."""
    doc = _doc()
    assert "**NOT MET.**" in _precondition_row(doc, "| E2 |")
    assert "**NOT MET, in five parts.**" in _precondition_row(doc, "| E3 |")
    assert "**NOT MET.**" in _precondition_row(doc, "| E6 |")
    assert "**NOT MET.**" in _precondition_row(doc, "| E7 |")


def test_the_preconditions_block_per_step_rather_than_all_at_once():
    """All-or-nothing is not executable: the work that makes a row MET is not a
    part 7 step, and a reader needs to know which step each row stops."""
    doc = _doc()
    flat = _flat(doc)
    assert "| Precondition | Blocks |" in doc
    assert "Building what a precondition asks for is not a part 7 step" in flat
    assert "No step begins while a precondition that blocks it reads NOT MET" in flat
    assert "This gate does not waive a precondition" in flat
    assert "it becomes a disclosure in part 9" in flat
    assert "O7 blocks step F" in flat
    assert "step F, and therefore every margin, every arm and every clause (d) cell" in flat


def test_the_ride_list_is_frozen_and_has_both_halves():
    doc = _doc()
    flat = _flat(doc)
    assert "## 6. What may ride this epoch, and what may not" in doc
    assert "This list is FROZEN at this commit" in flat
    assert "**May ride" in flat and "**May NOT ride.**" in flat
    for factor in ("Basis: published fWAR", "Arm R", "F-DEF"):
        assert factor in flat, f"ride list lost: {factor}"
    for barred in ("W1.3 departure", "blend lambda move", "C-7's grade-seam affine",
                   "BUST2 Arm S"):
        assert barred in flat, f"must-not-ride list lost: {barred}"


def test_a_banned_lane_cannot_be_moved_onto_the_may_ride_side():
    """The two halves of part 6 are one edit apart. A lambda move or a
    correction family appearing in the MAY RIDE table would pass every heading
    check in this file, so the may-ride region is read on its own."""
    doc = _doc()
    start = doc.index("**May ride")
    end = doc.index("**May NOT ride.**")
    may_ride = doc[start:end].lower()
    for banned in ("lambda", "affine", "dispersion", "correction family", "w1.3",
                   "bust2", "measured-rates"):
        assert banned not in may_ride, f"a banned lane is on the may-ride side: {banned}"


def test_the_runbook_order_is_carried_whole():
    doc = _doc()
    steps = ["A", "B", "C", "D + U", "E", "F", "G", "H", "I", "J", "K", "L", "M",
             "N", "O", "P", "Q", "R", "S", "T", "V", "W", "X", "Y", "Z"]
    for step in steps:
        assert f"| {step} |" in doc, f"runbook step {step} is missing"
    assert "**SKIPPED.**" in doc, "step B must retire eWAR v2 rather than rebuild it"


def test_the_runbook_letters_are_declared_not_to_be_a_running_order():
    """Step T sits above step X in the table while step T's own note says
    "after X's copy is in". Read top to bottom the table violates clause (l)
    point 5, so the table says in one line that it is an artifact list."""
    flat = _flat(_doc())
    assert "**The letters name artifacts, not a running order.**" in flat
    assert "The execution order of the last block is X, T, V, W" in flat


def test_step_a_does_not_overwrite_the_previous_epochs_snapshot():
    """WAR_BASIS_RUNBOOK.md hardcodes ../_pre_epoch_2026-09/, which holds the
    2026-09-04 epoch's evidence. Clause (f) and clause (i)'s E0 both read the
    step A snapshot, so a half-overwritten directory would corrupt both."""
    doc = _doc()
    flat = _flat(doc)
    assert "`../_pre_epoch_fwar_2026-10/`" in doc
    assert "NOT the runbook's hardcoded `../_pre_epoch_2026-09/`" in flat
    assert "Step A REFUSES if its own destination already exists" in flat
    assert "with ONE exception, named in step A's row below" in flat


def test_the_step_m_date_is_pinned_in_the_runbook_row_as_well_as_the_clause():
    """Clause (j) point 1 and the step M row have to agree, or the runbook
    quietly wins over the clause when somebody executes the table."""
    doc = _doc()
    assert "**Not before 2026-10-05** (clause (j) point 1)" in _runbook_row(doc, "| M |")
    assert ("Not before the 5c-C window closes (clause (j) point 2)"
            in _runbook_row(doc, "| D + U |"))


def test_the_registry_keys_this_gate_moves_are_named_concretely():
    flat = _flat(_doc())
    assert "`label_basis: fwar` in place of `label_basis: ewar_v2`" in flat
    assert "`fa_war_paths_decay` carries the step M retrain hash" in flat
    assert "a new `fwar` row carries the frozen vintage's id and points at this document" in flat
    assert "`MODEL_REGISTRY.md` is generated, never edited" in flat


def test_the_measured_blast_radius_is_stated_against_the_null_it_follows():
    """The numbers only mean something beside the 0.049 they replace."""
    flat = _flat(_doc())
    for number in ("1.785", "0.049", "0.831", "34.2%", "1.435"):
        assert number in flat, f"blast-radius figure missing: {number}"
    assert "A larger movement is not evidence of a better label" in flat


def test_part_2_is_framed_as_prior_descriptives_and_not_as_this_epochs_result():
    """Part 2 is a table of numbers sitting above part 9. Only the framing
    stops it being read as a result of this epoch, so the framing is pinned."""
    flat = _flat(_doc())
    assert "They were measured on 2026-09-11 with no fit, no gate and no game outcome" in flat
    assert ("They are PRIOR to this epoch and they are not clause (f)'s blast radius" in flat)
    assert "it has not been taken" in flat


def test_the_pitcher_prior_names_the_floors_as_its_reason():
    """A smaller label move does not imply a smaller delta of margins. The
    prior is a null because of the E_cond floors, and the label-sd comparison
    is a descriptive beside it, not its cause."""
    flat = _flat(_doc())
    assert "the reason is the FLOORS, not the size of the label move" in flat
    assert "as a descriptive and NOT as its cause" in flat
    assert "does not mechanically imply a smaller margin delta" in flat


def test_no_result_is_recorded_below_part_9():
    """The registration's whole value. Part 9 is empty, and the emptiness is
    checked structurally and case-insensitively rather than by trusting the
    heading: "ruled out" lowercase is as much a result as "RULED OUT"."""
    doc = _doc()
    assert RESULTS_HEADING in doc
    body = doc.split(RESULTS_HEADING, 1)[1]
    flat = _flat(body)
    assert "**EMPTY AT REGISTRATION.**" in flat
    assert "|" not in body, "part 9 carries a table, so it carries a result"
    for token in ("ruled out", "undecided", "gain", "loss", "pass", "fail",
                  "spearman", "rho", "e_cond", "holm", "bootstrap"):
        assert not re.search(rf"\b{re.escape(token)}\b", body, re.I), \
            f"part 9 records a result: {token!r}"
    for pattern in (r"\d+\.\d+", r"\d+\s*%", r"\bp\s*=", r"\bn\s*="):
        assert not re.search(pattern, body, re.I), \
            f"part 9 carries a result-shaped number: {pattern}"
    assert ("nothing above this line may be edited once anything is written "
            "below it") in flat


def test_no_result_is_recorded_above_part_9_either():
    """The document's rule is "None may be written anywhere above this line".
    A margin, an interval or an arm effect written into part 2 or part 3 would
    pass a below-the-heading check, so the shapes a result would take are
    banned above the heading too. Descriptives carried from the planning lanes
    are prose figures; none of them takes these forms."""
    doc = _doc()
    above = doc.split(RESULTS_HEADING, 1)[0]
    for pattern in (
            r"\[\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*\]",   # a confidence interval
            r"\bp\s*=\s*-?0?\.\d",                       # a p-value
            r"\brho\s*=\s*-?\d",                         # a rho
            r"effect_f\s*=\s*-?\d",                      # an arm effect
            r"\bE0\b[^|\n]{0,40}?=\s*-?\d+\.\d+",        # an arm attached to a number
    ):
        m = re.search(pattern, above, re.I)
        assert m is None, f"a result is recorded above part 9: {m.group(0) if m else ''!r}"
