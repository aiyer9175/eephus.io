# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Repair 5 of the 2026-09-11 plan: the starting nine and the claims around it.

Three things are pinned here, and none of them is a number relating anything to
an outcome or a price:

  * `fantasy_schedule.fetch_lineups`'s docstring no longer says the completed
    feed's `battingOrder` ARRAY verified the posted card. On game 824804, the
    game it cites, that array differs from the nine who started on BOTH sides
    (three home slots and one away, read off this box's cached feed on
    2026-09-17) while the posted card matches the starters exactly, in order,
    on both sides. The claim was true about the card and false about the array,
    and the correction has to keep the half that is true;
  * the reader the corrected docstring sends people to,
    `betting_lineup_job.starting_nine`, is where the docstring says it is. Its
    own contract (the N00 codes, the substitute the array keeps) is pinned in
    test_betting_lineup_job.py, and that file also holds the line that nothing
    else in the tree imports the job while 5j phase 1 is dark, so the pointer
    is checked by READING the source rather than importing it. A docstring
    aiming at a function that moved is how the array gets read as a starting
    nine again;
  * the eval artifact discloses WHICH starter the backtest priced, and that
    disclosure is PUBLISHED but NOT RENDERED. data/betting_model_eval.json
    ships (deploy/data_exclude.txt keeps the eval artifacts in the rsync set on
    purpose, and assets/betting.js fetches it as AUX_URL.evald), so the block
    reaches a reader wherever it is written; what placement decides is whether
    /betting/ renders it, because `betting_export.BACKTEST_KEYS` copies the
    vintage block to the page verbatim. The block sits at the top of the
    artifact, and the pin below is against the SOURCE so it holds on a checkout
    with no artifact on disk. Whether the validation tab SHOULD carry this
    qualifier beside the vintage Brier and the skill t is a live decision for
    the copy step; these tests do not settle it, they only keep the step that
    added the block from changing the page as a side effect.

Offline: synthetic rows, the module docstrings, one source file read as text,
the source of `backtest` itself, and the artifact already on disk. Nothing here
writes a file.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import betting_export as be
import betting_model as bm
import fantasy_schedule as fsched


# ===========================================================================
# 1. the docstring that pointed at the wrong object
# ===========================================================================
DOC = fsched.fetch_lineups.__doc__ or ""


def test_the_docstring_no_longer_claims_the_feed_array_verified_the_card():
    """The old sentence said the array order and the batting order agree
    exactly. They do not agree on the game it cites, so the sentence cannot
    survive in any form a reader could act on."""
    assert "the array order and the batting order agree exactly" not in DOC
    assert "ARRAY" in DOC and "CURRENT occupant" in DOC


def test_the_docstring_keeps_the_half_of_the_claim_that_is_true():
    """The posted card IS the nine that started, in order, on game 824804. That
    is what makes a bare index safe to publish, and the correction must not
    throw it out with the wrong half."""
    assert "824804" in DOC
    assert "safe to publish" in DOC


def test_the_docstring_names_the_rule_and_the_reader():
    """A correction that says what is wrong and not what is right sends the
    next reader back to the array."""
    assert "ends in `00`" in DOC
    assert "starting_nine" in DOC


def test_the_docstring_says_the_reader_may_be_read_and_not_imported():
    """5j phase 1 is dark. A pointer that reads as an invitation to import is a
    pointer at a guard, and the next reader would trip
    test_betting_lineup_job.py::test_no_module_in_the_tree_imports_the_job."""
    assert "do not import it" in DOC


def test_the_reader_the_docstring_names_is_where_it_says_it_is():
    """ON THE SOURCE, NOT BY IMPORTING IT, for the reason above. The reader's
    own contract is pinned over in test_betting_lineup_job.py; what would break
    here is a rename that left the docstring aiming at an object that had
    moved, which is how the array gets read as a starting nine again. The match
    is deliberately loose about the signature so that a type annotation can
    change without failing another module's test file."""
    src = (ROOT / "tools" / "betting_lineup_job.py").read_text(encoding="utf-8")
    assert "def starting_nine(" in src
    assert 'endswith("00")' in src
    assert "tools/betting_lineup_job.starting_nine" in DOC


# ===========================================================================
# 2. the disclosure: which starter the backtest priced
# ===========================================================================
ROWS = [{"home_sp": 11, "away_sp": 22},
        {"home_sp": 33, "away_sp": None},
        {"home_sp": None, "away_sp": None}]


def test_the_disclosure_counts_the_rows_the_artifact_was_built_from():
    b = bm._starter_basis(ROWS)
    assert b["counts"] == {"n_games": 3, "both_sides_named": 1,
                           "one_side_named": 1, "neither_side_named": 1}
    assert bm._starter_basis([])["counts"]["n_games"] == 0


def test_the_disclosure_names_the_field_and_says_the_board_reads_another():
    """The whole point of the block: the graded pricer holds a starter the
    served board does not always have."""
    b = bm._starter_basis(ROWS)
    assert b["source"] == "final feed probablePitchers"
    assert "home_sp" in b["field"]
    assert "not this field" in b["served_board_reads"]
    assert "not an outcome leak" in b["note"]


def test_the_disclosure_names_BOTH_doors_the_field_comes_through():
    """The field has two writers, not one: the one-time feed walk reads
    gameData.probablePitchers and the routine top-up reads the schedule's
    teams[side].probablePitcher, overwriting the row on every refresh. They are
    different objects, so a block that named one door would be asserting an
    identity it does not have. What is true is that they AGREE on this archive,
    and that is carried as a dated measurement."""
    d = bm._starter_basis(ROWS)["doors"]
    assert "gameData.probablePitchers" in d["feed_walk"]
    assert "probablePitcher" in d["top_up"] and "overwrites" in d["top_up"]
    ag = d["agreement"]
    assert ag["sides_compared"] == 4576 and ag["differ"] == 0
    assert ag["sides_compared"] == 2 * ag["n_games"]
    assert ag["measured_on"] == "2026-09-17"
    assert "completed_games.json" in ag["source"] and "game_feeds" in ag["source"]


def test_the_disclosure_dates_and_attributes_the_agreement_rate():
    """4,385 of 4,392 is R4's count over the archive as it stood, not a number
    this artifact recomputes. An undated count in an artifact is a number
    nobody can check later."""
    eq = bm._starter_basis(ROWS)["equals_first_pitcher_used"]
    assert eq["sides_compared"] == 4392 and eq["equal"] == 4385
    assert eq["equal"] + eq["differ"] == eq["sides_compared"]
    assert (eq["sides_compared"] + eq["sides_without_a_probable"]
            == eq["sides_total"])
    assert eq["measured_on"] == "2026-09-11"
    assert "R4 count A" in eq["source"]


def test_the_frozen_rate_says_it_is_frozen_and_what_retires_it():
    """THE RECORD MOVES WITH THE CONSTANT, the rule dfs_export's
    _PA_PER_START_BASIS is written under. This rate rides in an artifact that
    is rebuilt every night beside `counts`, which grows every night, and the
    two have different denominators: 4,394 sides over R4's 2,197 cached feeds
    against however many rows this run read. A reader who takes the two as one
    sample is the failure this pins against, and the block has to say when it
    stops being the answer."""
    eq = bm._starter_basis(ROWS)["equals_first_pitcher_used"]
    assert "frozen" in eq["denominator_note"]
    assert "counts" in eq["denominator_note"]
    assert "betting_lineup_job" in eq["retires_when"]
    # FROZEN means frozen: the block is the same whatever rows the run read,
    # so nothing can quietly start deriving it from this run's sample
    assert eq == bm._starter_basis([])["equals_first_pitcher_used"]


def test_the_prose_and_the_numbers_are_the_same_numbers():
    """A number that moves in the dict while the docstring that explains it
    stands still is the audited-record failure dfs_export names. Every count
    the block carries is quoted in the docstring, so they move together."""
    doc = bm._starter_basis.__doc__ or ""
    b = bm._starter_basis(ROWS)
    eq, ag = b["equals_first_pitcher_used"], b["doors"]["agreement"]
    for n in (eq["equal"], eq["sides_compared"], eq["sides_total"],
              ag["sides_compared"], ag["n_games"]):
        assert "{:,}".format(n) in doc, n
    assert eq["measured_on"] in doc and ag["measured_on"] in doc


def test_the_served_sentence_the_disclosure_named_has_been_repaired():
    """The served vintage blurb USED TO say the listed probable comes out of
    the vintage snapshot. The snapshot supplies his SEM+ ratings; his IDENTITY
    comes from the completed-game row, which is what this block documents.
    That sentence was named as owed on 2026-09-17 and repaired on 2026-09-18.

    WHAT THIS PINS NOW. The block still names the repair through
    `copy_repair_owed` (that string lives in `betting_model`, which this step
    does not own, so it is stale by one day and is handed to that lane), and
    the SERVED sentence it named is now true: it credits the snapshot with the
    ratings, credits the completed-game row with the identity, and says in as
    many words that the difference is one of information rather than an outcome
    leak, so a reader cannot take it for a leak.

    MUTATION: put "the listed probable and the park index all come out of that
    snapshot" back into `MODE_MEANING["vintage"]`. This fails."""
    owed = bm._starter_basis(ROWS)["copy_repair_owed"]
    assert "MODE_MEANING" in owed
    assert "SEM+" in owed and "completed-game row" in owed
    blurb = be.MODE_MEANING["vintage"]
    # the false half is gone
    assert "the listed probable and the park index" not in blurb
    # the true halves are both there, and neither may stand without the other
    assert "SEM+ ratings" in blurb
    assert "completed-game row" in blurb
    assert "nightly build" in blurb
    assert "information and not an outcome leak" in blurb


def test_the_disclosure_is_pure_and_touches_nothing_it_is_handed():
    """It reads two keys off rows it is given and returns a dict. A block that
    could reach a coefficient would be a feature and would need a gate."""
    rows = [{"home_sp": 11, "away_sp": 22, "home_runs": 4, "away_runs": 3}]
    before = json.dumps(rows, sort_keys=True)
    bm._starter_basis(rows)
    assert json.dumps(rows, sort_keys=True) == before


# ===========================================================================
# 3. published, and not rendered: where the block sits
# ===========================================================================
def test_the_disclosure_is_not_a_served_key():
    assert "starter_basis" not in be.BACKTEST_KEYS
    # ... and this is WHY it cannot live in the vintage block: that one is
    # copied to /betting/ verbatim.
    assert "vintage" in be.BACKTEST_KEYS


def test_the_placement_is_pinned_against_the_source_not_against_a_file_on_disk():
    """THE GUARD THAT HAS TO HOLD ON A FRESH CHECKOUT. The artifact test below
    can only speak about an artifact that exists; this one reads the code, so
    moving the block into the vintage block fails here whether or not a
    backtest has ever run on this box. Both writers in `backtest` (the no-data
    branch and the graded one) assign at the top level, and neither grader puts
    it anywhere."""
    bt = inspect.getsource(bm.backtest)
    assert bt.count('result["starter_basis"] = _starter_basis(games)') == 2
    for fn in (bm._grade_vintage, bm._empty_vintage_block):
        assert "starter_basis" not in inspect.getsource(fn), fn.__name__


def test_adding_the_disclosure_changes_no_served_byte():
    """The two projections /betting/ is built from, before and after. The
    artifact itself is published either way; what this pins is that the step
    which added the block did not change the PAGE."""
    art = ROOT / "data" / "betting_model_eval.json"
    evald = (json.loads(art.read_text(encoding="utf-8"))
             if art.exists() else {"vintage": {"mode": "vintage", "n_graded": 0}})
    evald.pop("starter_basis", None)

    def served(d):
        return json.dumps(
            {"backtest": {k: d.get(k) for k in be.BACKTEST_KEYS if k in d},
             "validation": be.validation_state(d)}, sort_keys=True)

    before = served(evald)
    after = served(dict(evald, starter_basis=bm._starter_basis(ROWS)))
    assert before == after
    assert "starter_basis" not in after


def test_an_artifact_that_carries_the_disclosure_carries_it_at_the_top():
    """A SKIP FOR AN ARTIFACT THAT CANNOT SPEAK, A FAILURE FOR ONE THAT SAYS
    THE WRONG THING. No artifact on disk, or one written before this change,
    is a state this test has nothing to say about (X6 bars a test from writing
    one). An artifact carrying the block UNDER `vintage` is the regression the
    placement exists to prevent, so it is asserted before either skip."""
    art = ROOT / "data" / "betting_model_eval.json"
    if not art.exists():
        pytest.skip("no eval artifact in this checkout; the source pin above "
                    "covers the placement")
    d = json.loads(art.read_text(encoding="utf-8"))
    assert "starter_basis" not in json.dumps(d.get("vintage") or {})
    if "starter_basis" not in d:
        pytest.skip("eval artifact predates the starter disclosure; re-run --backtest")
    b = d["starter_basis"]
    assert b["source"] == "final feed probablePitchers"
    assert b["counts"]["n_games"] == d.get("n_games")
