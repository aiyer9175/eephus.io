# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PE-H old-seasons read's registration pins
(docs/ewar-v3/EWAR_PEH_OLD_SEASONS_GATE.md, task EWAR_PEH_OLD_SEASONS, owner EW3-50).

The registration is committed ALONE, before any number of its estimands exists. Every
clause that binds the read is pinned by the sentence that makes it bind. Prose
assertions run against a whitespace-flattened copy of the document, so re-wrapping a
paragraph is not a test failure.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "ewar-v3" / "EWAR_PEH_OLD_SEASONS_GATE.md"


def _flat() -> str:
    return re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))


def test_document_names_itself_and_this_test():
    text = _flat()
    assert text.startswith("# PE-H on the old seasons: one registered read of the hitter pitch-economy "
                           "part on 2002 to 2015 (pre-registration, 2026-10-22)")
    assert "This document is committed ALONE, before any number of its estimands is computed" in text
    assert "`test_ewar_peh_old_seasons_gate.py`" in text
    assert "## 11. Results" in text


def test_part_unchanged_and_not_a_reopened_arm():
    text = _flat()
    assert "**The part is not changed.**" in text
    assert "DELTA_TTO 0.01847965, K_CL 236.41, K_P 110.95" in text
    assert "Nothing is refitted on the old seasons." in text
    for arm in ("HEM+ or xHEM+", "S2b", "DEM+", "S3c", "PE-P", "positional ladders v1 to v3",
                "eBR against BsR"):
        assert arm in text, arm
    assert "`docs/ewar-v3/peh_old_seasons_eval.json`" in text


def test_cited_not_rescored():
    text = _flat()
    assert "SMALL WIN, gap +0.01304 (+0.00604 to +0.02029)" in text
    assert "EQUIVALENT, gap +0.00216 (-0.01311 to +0.01624)" in text
    assert "No cell of either read is recomputed here" in text


def test_frame_target_and_weights():
    text = _flat()
    assert "predictor seasons Y = 2002 to 2014, outcome seasons 2003 to 2015" in text
    assert "Hitters with 200 or more PA in both seasons" in text
    assert "tgt_i = wRAA_i(Y+1) + W_i(Y+1)" in text
    assert "test_i = B0_i + d_PEH,i(Y)" in text
    assert ("the vintage solve must reproduce the artifact's 2011 to 2015 scale and league wOBA within "
            "0.0005 and every weight within 0.002, else STOP") in text


def test_inputs_and_season_admission():
    text = _flat()
    assert "`tools/fetch_win_prob_old.py`" in text and "`.cache/peh_old/corpus`" in text
    assert "never `.cache/pbp_corpus`" in text
    assert "RE288_s = RE24_s + lambda_s x the frozen pooled count departure" in text
    assert "must reproduce `data/count_value.json`'s 2019 RE288 and RE24 to the fourth decimal" in text
    assert "at least 0.999 of its walked plate appearances" in text
    assert "Fewer than 6 surviving predictor seasons is a STOP." in text


def test_cells_bootstrap_and_guards():
    text = _flat()
    assert "**Holm family {PE-H rate, PE-H total}, k = 2.**" in text
    assert "B = 4,000, seed 20261023." in text
    assert "with k = 427 PA, the PE-H constant the look froze" in text
    assert "seed 20261023 + 202" in text
    assert "W left out, in the same bootstrap; it must not be LOSS" in text
    assert "club-seasons 2003 to 2015" in text
    assert "B = 4,000 each, seed 20261023, through `swar_targets.team_guard`" in text
    assert "(ANA as LAA, FLA as MIA, TBD as TBR, MON as WSN)" in text


def test_controls_and_admission():
    text = _flat()
    assert "**Null comparator.** The delta set to 0 for every pair" in text
    assert "It must not read WIN or SMALL WIN on either cell." in text
    assert "The delta set to 0.5 x PA_i(Y) x (tgt_i / PA_i(Y+1)" in text
    assert "It must read WIN (components) on both cells, and its twin must fail." in text
    assert "**A failed control stops the read before any real cell is scored**" in text
    assert ("PE-H's read PASSES only when, together: the rate cell is WIN (components); the rate cell's "
            "club-clustered lo95 is above 0; the total cell is not LOSS; the sensitivity guard is not LOSS; "
            "and the team guard is NON-INFERIOR.") in text
    assert "PE-H's admission is an OWNER QUESTION" in text


def test_no_dashes_in_document():
    raw = DOC.read_text(encoding="utf-8")
    assert "—" not in raw and "–" not in raw


def test_result_recorded_once_and_matches_the_record():
    import json
    rec_path = ROOT / "docs" / "ewar-v3" / "peh_old_seasons_eval.json"
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    assert rec["void"] is False and rec["boot"] == 4000 and rec["seed"] == 20261023
    assert rec["controls"]["null_passes"] is True and rec["controls"]["planted_passes"] is True
    assert rec["census"]["pairs"] == 3488
    assert rec["cells"]["PE-H rate"]["disposition"] == "SMALL WIN"
    assert rec["cells"]["PE-H total"]["disposition"] == "SMALL WIN"
    assert rec["team_guard"]["non_inferior"] is True
    assert rec["admission"]["passes"] is False
    text = _flat()
    results = text.split("## 11. Results", 1)[1]
    assert "### 11.1 2026-10-23: the read, run once" in results
    assert "**Admission (part 5): NOT PASS.**" in results
    assert "| PE-H rate | 3,488 | +0.00884 | +0.00499 to +0.01252 |" in results
