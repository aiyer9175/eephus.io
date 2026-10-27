"""A-CLAIM-3: the exposure-matched label, and the hypothesis it kills.

WHAT THIS LANE MEASURES. The same head-to-head, scored against first-six-season eWAR
(`efv_dataset._label_6yr`) instead of career WAR to date. Career WAR rewards being older,
and being older is a property of the base year rather than of the grade.

THE FOUR MISTAKES THESE TESTS EXIST FOR:

  1. QUOTING THE PLAN'S BOUNDARY. The registration says the clean cut is "debuts through
     2021". RESOLVED_THROUGH is 2025 and the window is six seasons, so it is 2020. The
     artifact must derive the boundary from the shipped constants, not restate a number.
  2. SCORING TWO CUTS ON DIFFERENT POPULATIONS AND COMPARING THEM. The exposure test only
     means anything if the career-WAR control runs on the SAME rows.
  3. CALLING THE HYPOTHESIS REFUTED WITHOUT CHECKING THE LABEL WORKED. If the six-season
     label had not actually flattened the outcome spread, "no shrinkage" would say nothing
     at all.
  4. CORRECTING THE CENSORING BIAS. It is a property of the label the eFV model is fitted
     to. Correcting it would score the raters against a label the model never saw.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

ART = ROOT / "data" / "source_backtest.json"
DOC = ROOT / "docs" / "efv-2026-09-06" / "EXPOSURE_MATCHED_LABEL.md"
SCALE_DOC = ROOT / "docs" / "efv-2026-09-06" / "RATER_SCALE_VIEW.md"
RATERS = ("fangraphs", "mlb_pipeline", "prospx_consensus", "xfv")


@pytest.fixture(scope="module")
def exp():
    if not ART.exists():
        pytest.skip("data/source_backtest.json has not been built")
    e = (json.loads(ART.read_text(encoding="utf-8"))
         .get("accuracy", {}).get("claim_instruments", {})
         .get("exposure_matched_label"))
    if not e:
        pytest.skip("the exposure-matched frame is not in the artifact")
    return e


# --------------------------------------------------------------------------
# The label and its boundary
# --------------------------------------------------------------------------

def test_the_resolved_boundary_is_derived_from_the_shipped_constants(exp):
    """The registration says 2021 and the shipped constants say 2020. A lane that
    hard-coded the plan's number would be wrong today and would stay wrong when
    RESOLVED_THROUGH moves."""
    import efv_dataset as ed
    r = exp["receipt"]
    assert r["resolved_through"] == ed.RESOLVED_THROUGH
    assert r["target_seasons"] == ed.TARGET_SEASONS
    assert r["last_fully_resolved_debut_year"] == (
        ed.RESOLVED_THROUGH - ed.TARGET_SEASONS + 1)


def test_the_receipt_accounts_for_every_row_read(exp):
    r = exp["receipt"]
    total = (r["kept"] + r["no_debut_year"] + r["no_seasons"]
             + r["outside_debut_years"] + r["raised"])
    assert total == r["considered"], (
        f"the receipt loses {r['considered'] - total} rows between reading and "
        "keeping; every drop must be named")
    assert r["n_fully_resolved"] + r["n_censored"] == r["kept"]


def test_the_label_function_is_the_shipped_one_not_a_reimplementation():
    src = (ROOT / "source_backtest.py").read_text(encoding="utf-8")
    assert "_ed._label_6yr(" in src, (
        "the six-season label must come from efv_dataset, which is what the eFV "
        "model trains on; a local copy would drift from it silently")


def test_a_missing_efv_dataset_degrades_rather_than_failing_the_backtest():
    """An optional receipt must never be the reason the whole backtest cannot
    run."""
    src = (ROOT / "source_backtest.py").read_text(encoding="utf-8")
    i = src.index("def _six_year_label_map")
    body = src[i:i + 1600]
    assert "import efv_dataset as _ed" in body and "except Exception" in body


# --------------------------------------------------------------------------
# The two cuts
# --------------------------------------------------------------------------

def test_the_fully_resolved_cut_is_actually_fully_resolved(exp):
    c = exp["cuts"]["fully_resolved"]
    assert c["n_censored"] == 0
    assert c["mean_exposure_weight"] == 1.0
    assert c["min_exposure_weight"] == 1.0
    import efv_dataset as ed
    assert max(c["debut_years"]) <= ed.RESOLVED_THROUGH - ed.TARGET_SEASONS + 1


def test_the_censored_cut_carries_its_weights_and_they_are_below_one(exp):
    c = exp["cuts"]["censored_full"]
    assert c["n_censored"] > 0
    assert c["min_exposure_weight"] < 1.0
    assert c["mean_exposure_weight"] < 1.0


def test_both_cuts_score_every_comparator_with_a_floor(exp):
    for tag in ("fully_resolved", "censored_full"):
        cells = exp["cuts"][tag]["cells"]
        assert set(cells) >= {"fangraphs", "mlb_pipeline", "prospx_consensus"}
        for comp, cell in cells.items():
            assert (cell["floor_E_cond_in_run"] or {}).get("mde95") is not None
            assert cell["comparator"] == comp


def test_the_registered_expectation_holds_on_both_cuts(exp):
    """C1 and C2: eFV against the consensus and against MLB Pipeline stay
    unresolved. A nominal flip is not quotable and a real one has to be confirmed
    before this test is edited."""
    import efv_v2_serve
    crossed = []
    for tag in ("fully_resolved", "censored_full"):
        for comp in ("prospx_consensus", "mlb_pipeline"):
            cell = exp["cuts"][tag]["cells"][comp]
            if abs(cell["point_delta"]) > cell["floor_E_cond_in_run"]["mde95"]:
                crossed.append(f"{tag} vs {comp} {cell['point_delta']:+.5f} against "
                               f"{cell['floor_E_cond_in_run']['mde95']}")
    # DS-02 (2026-09-25): the registration was made on eFV v1. On the served eFV V2 a
    # crossing is an unconfirmed reading on a spent frame (no page prints this block)
    # and stays visible here as an expected failure until the owner rules on it.
    if crossed and efv_v2_serve.enabled():
        pytest.xfail("eFV V2 crosses the floor on the exposure-matched label, "
                     "unconfirmed and unclaimed: " + "; ".join(crossed))
    for tag in ("fully_resolved", "censored_full"):
        for comp in ("prospx_consensus", "mlb_pipeline"):
            cell = exp["cuts"][tag]["cells"][comp]
            d = abs(cell["point_delta"])
            m = cell["floor_E_cond_in_run"]["mde95"]
            assert d <= m, (
                f"{tag} vs {comp} now CLEARS its floor ({d:.5f} against {m}) on "
                "the exposure-matched label. That contradicts the registration "
                "and would change a published claim; confirm it first.")


def test_the_censoring_bias_is_stated_and_not_corrected_for(exp):
    n = exp["censoring_bias_direction"]
    assert n.get("source", "").endswith("xfv_label_censoring_eval.json")
    assert n.get("by_n_obs_and_side"), "the per-cell bias table did not travel"
    assert "direction" in n
    src = (ROOT / "source_backtest.py").read_text(encoding="utf-8")
    i = src.index("def _censoring_bias_note")
    assert "STATED, NOT CORRECTED FOR" in src[i:i + 900]


def test_the_frame_declares_that_it_moves_nothing(exp):
    assert exp["changes_no_published_number"] is True


# --------------------------------------------------------------------------
# The refutation
# --------------------------------------------------------------------------

def test_the_hypothesis_test_ran_on_the_same_rows_with_only_the_label_changed(exp):
    """Mistake 2. Two passes on different populations would compare a label
    change against a population change and attribute the whole thing to the
    label."""
    h = exp["exposure_hypothesis_test"]
    a, b = h["on_career_war_same_rows"], h["on_exposure_matched_label"]
    assert a["n"] == b["n"]
    assert a["n_players"] == b["n_players"]
    assert a["blocks_kept"] == b["blocks_kept"]
    assert set(a["blocks"]) == set(b["blocks"])
    for bk in a["blocks"]:
        assert a["blocks"][bk]["n"] == b["blocks"][bk]["n"]


def test_the_exposure_matched_label_actually_flattened_the_outcome(exp):
    """Mistake 3, and it is the test that makes the refutation mean anything. If
    the label had not compressed the between-block outcome spread, "no
    shrinkage" would be a statement about a label that did nothing."""
    h = exp["exposure_hypothesis_test"]
    career = [v["mean_war"] for k, v in sorted(h["on_career_war_same_rows"]["blocks"].items())]
    six = [v["mean_war"] for k, v in sorted(h["on_exposure_matched_label"]["blocks"].items())]
    assert st.pstdev(six) < st.pstdev(career), (
        f"the six-season label did not reduce the between-block outcome spread "
        f"(sd {st.pstdev(six):.3f} against {st.pstdev(career):.3f}), so it did "
        "not do the exposure matching this lane's refutation rests on")
    assert (max(six) - min(six)) < (max(career) - min(career))


#: The raters A-CLAIM-13 measured a resolvable block effect in, the effect the exposure
#: explanation was offered for. eFV carried none ("and none in eFV"), so its row is read
#: but is not part of the refutation (the dated note in EXPOSURE_MATCHED_LABEL.md,
#: 2026-10-26).
REFUTED_FOR = ("fangraphs", "mlb_pipeline", "prospx_consensus")


def test_the_block_effect_does_not_shrink_under_exposure_matching(exp):
    """THE REFUTATION. If this ever reverses, A-CLAIM-13's exposure explanation
    comes back and both docs are wrong."""
    sh = exp["exposure_hypothesis_test"]["shrinkage"]
    assert set(sh) >= set(RATERS)
    for r, v in sh.items():
        if r not in REFUTED_FOR:
            continue
        assert abs(v["six_season_delta"]) >= abs(v["career_war_delta"]) - 1e-9, (
            f"{r}: the block effect SHRANK under exposure matching "
            f"({v['career_war_delta']} to {v['six_season_delta']}), which "
            "supports the exposure explanation the docs now call refuted")


def test_the_hypothesis_test_states_its_own_power_caveat(exp):
    h = exp["exposure_hypothesis_test"]
    assert "SMALLER" in h["caveat"] and "same population" in h["caveat"].lower()


# --------------------------------------------------------------------------
# The record
# --------------------------------------------------------------------------

def test_the_doc_corrects_the_plans_boundary():
    assert DOC.exists()
    txt = DOC.read_text(encoding="utf-8")
    assert "debuts through 2020" in txt and "2021" in txt


def test_the_doc_records_the_receipt_not_a_claim():
    txt = DOC.read_text(encoding="utf-8")
    assert "receipt, not a claim" in txt, (
        "FanGraphs clears on the resolved cut and sits at exactly 1.00x its "
        "floor on the censored one; the doc must say that is a margin nobody "
        "should quote")


def test_the_scale_view_doc_was_corrected_rather_than_left_standing():
    txt = SCALE_DOC.read_text(encoding="utf-8")
    assert "falsified the same day" in txt, (
        "RATER_SCALE_VIEW.md still presents exposure as the live explanation; a "
        "hypothesis that was tested and lost is corrected in place, not left for "
        "a reader to discover")
