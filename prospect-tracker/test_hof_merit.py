# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""H-PRED-3: the merit model lost its gate, and the loss is the deliverable.

/hof/ shipped its predictor section dark, blocked on "no induction probability is
published until a merit model has passed its own gate". That was a promise about
work not yet done. The model now exists, was gated on the bake-off's own frame,
folds and bootstrap, and LOST:

    merit          AUC 0.9557   Brier 0.0427
    hof_monitor    AUC 0.9785   Brier 0.0353
    deficit        0.0228, against a 0.0138 player-clustered detection floor

The section stays dark, but for a measured reason with a number on it instead of
an unbuilt one.

THE MODEL IS NOT BAD, and that distinction is the point of the artifact. It beats
every in-house arm (0.9557 against 0.9492 for career_war, the strongest single
column), and beats hof_standard and JAWS. The gap to hof_monitor is MISSING DATA:
that metric is built from batting titles, MVP shares, All-Star selections and
postseason play, none of which is in our feature set. docs/HOF_BAKEOFF_GATE.md
predicted exactly this before the run.

These tests pin the things that would let the loss be quietly turned into a win:
the feature set staying in-house, the fit staying out of fold, and the page
reading its numbers off the artifact rather than restating them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent
ART = HERE / "data" / "hof_merit_eval.json"


def _art():
    if not ART.exists():
        pytest.skip("data/hof_merit_eval.json not built on this machine")
    return json.loads(ART.read_text(encoding="utf-8"))


def test_no_public_arm_is_a_feature():
    """A public arm as a feature scores the model against its own input."""
    import tools.hof_merit as hm
    import tools.hof_bakeoff as hb
    overlap = set(hm.FEATURES) & set(hb.PUBLIC_ARMS)
    assert not overlap, f"public arms used as features: {overlap}"
    d = _art()
    assert not set(d["features"]) & set(hb.PUBLIC_ARMS)


def test_the_fit_is_out_of_fold():
    """Every scored player must come from a block trained on strictly earlier ones."""
    d = _art()
    fitted = [f for f in d["folds"] if f.get("fitted")]
    assert fitted, "no block was fitted"
    for f in fitted:
        assert f["lo"] > d["burn_in_year"], f
        assert f["n_train"] > 0 and f["n_test"] > 0
    # the chain must be contiguous and forward-only
    los = [f["lo"] for f in d["folds"]]
    assert los == sorted(los)
    assert d["n_scored"] <= sum(f["n_test"] for f in d["folds"])


def test_a_losing_verdict_cannot_claim_a_calibration_win():
    """The gate is ordered on purpose.

    Discrimination non-inferiority comes FIRST. A model that ranks materially
    worse does not get to win the run on a second metric, so a
    NO_SHIP_DISCRIMINATION verdict must not also be reported as shipping.
    """
    d = _art()
    assert d["verdict"] in ("SHIP", "NO_SHIP_DISCRIMINATION", "NO_SHIP_CALIBRATION")
    if not d["non_inferior_on_discrimination"]:
        assert d["verdict"] == "NO_SHIP_DISCRIMINATION"
    if d["verdict"] != "SHIP":
        assert d["delta_auc_vs_best_public"] < 0 or d["delta_brier_vs_best_public"] >= 0


def test_the_predictor_section_stays_dark_while_the_model_loses():
    board = HERE / "data" / "hof_board.json"
    if not board.exists():
        pytest.skip("hof_board.json not built")
    sec = json.loads(board.read_text(encoding="utf-8"))["sections"]["predictor"]
    d = _art()
    if d["verdict"] != "SHIP":
        assert sec["live"] is False, (
            "the predictor section went live on a model that did not pass its gate")
        assert sec.get("verdict") == d["verdict"]


def test_the_page_reads_its_numbers_off_the_artifact():
    """Restating them in copy is how the FA verdict tooltip drifted for six weeks."""
    board = HERE / "data" / "hof_board.json"
    if not board.exists():
        pytest.skip("hof_board.json not built")
    sec = json.loads(board.read_text(encoding="utf-8"))["sections"]["predictor"]
    d = _art()
    if d["verdict"] == "SHIP":
        pytest.skip("model shipped; the dark copy does not apply")
    why = sec.get("why") or ""
    assert f"{d['auc']['merit']:.4f}" in why, "the served AUC is not the artifact's"
    assert str(d["n_scored"]) in why
    assert sec.get("eval_artifact") == "data/hof_merit_eval.json"


def test_the_loss_is_attributed_to_data_not_to_modelling():
    """The model beats every in-house arm. The page has to say so, or the reader
    concludes our features are worse than they are."""
    d = _art()
    if d["verdict"] == "SHIP":
        pytest.skip("model shipped")
    house = {k: v for k, v in d["auc"].items()
             if k not in ("merit", "hof_monitor", "hof_standard",
                          "WAR_career", "WAR_peak7", "JAWS")}
    assert house, "no in-house arms scored"
    assert d["auc"]["merit"] > max(house.values()), (
        "the model no longer beats the best single in-house column; the "
        "what_it_does_beat copy on /hof/ would be false")
