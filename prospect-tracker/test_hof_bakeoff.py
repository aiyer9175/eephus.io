"""The public benchmark bake-off: the bar every later Hall of Fame model has to clear.

THE ANSWER IS THAT WE LOSE, and the lane ships that. Baseball-Reference's HoF Monitor
separates the Hall better than our WAR shelf does, on every in-house column, by more than
this sample can resolve, surviving a multiplicity correction. A benchmark panel that only
ships on a win is not a benchmark.

THE SIX MISTAKES THESE TESTS EXIST FOR, and the fourth is the subtle one:

  1. READING THE SHELF WITHOUT COLLAPSING IT. The file is one row per ballot APPEARANCE,
     4,278 rows over 1,322 players. Skipping the collapse silently reweights every player
     by how many years he lingered on the ballot.
  2. SELECTING RESOLVED ROWS BY TRUTHINESS. The label is float64 and a censored player is
     NaN. `bool(nan)` is True, so `if label:` admits every censored player as an inductee.
  3. IMPUTING A MISSING PUBLIC COLUMN. numpy sorts NaN LAST, so a positive with a missing
     score would be handed the top rank. A zero is no better: it guarantees a misranking
     for Roberto Clemente.
  4. ASSERTING POOLED POST-PLATT AUC EQUALS POOLED RAW AUC. Platt is monotone WITHIN a
     fold. A pooled vector built from many fold-specific maps is not one monotone map, so
     a CORRECT implementation fails that check and a builder would hunt a leak that is not
     there. The per-fold version is the real guard and it holds exactly.
  5. LETTING A LABEL WITH AN OUTCOME-CORRELATED HOLE CARRY THE HEADLINE. label_any drops
     seventeen rows and every one is a positive.
  6. RUNNING THE BATTERY BEFORE ITS OWN CLAUSES ARE WRITTEN.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import hof_bakeoff as bo                                      # noqa: E402

ART = ROOT / "data" / "hof_bakeoff_eval.json"
GATE = ROOT / "docs" / "HOF_BAKEOFF_GATE.md"


@pytest.fixture(scope="module")
def d():
    if not ART.exists():
        pytest.skip("run python tools/hof_bakeoff.py")
    return json.loads(ART.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bb(d):
    return d["labels"]["bbwaa"]


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------

def test_the_gate_doc_exists_and_is_frozen():
    assert GATE.exists()
    assert bo.frozen_at().startswith("Frozen ")


def test_the_battery_refuses_without_a_frozen_doc(monkeypatch, tmp_path):
    """MISTAKE 6. A battery that can run before its own clauses are written is
    not gated by them."""
    monkeypatch.setattr(bo, "GATE_DOC", tmp_path / "nope.md")
    with pytest.raises(RuntimeError, match="frozen before"):
        bo.frozen_at()


def test_the_doc_admits_the_discrimination_leg_was_not_pre_registered():
    txt = GATE.read_text(encoding="utf-8")
    assert "The discrimination leg is NOT pre-registered" in txt, (
        "a design pass read those AUCs before this doc existed; calling them "
        "pre-registered would be false")
    assert "The calibration leg IS unread" in txt


# --------------------------------------------------------------------------
# The frame
# --------------------------------------------------------------------------

def test_the_unit_is_the_player_and_never_the_ballot_appearance():
    """MISTAKE 1."""
    rows = json.loads(bo.BENCH.read_text(encoding="utf-8"))["rows"]
    coll = bo.collapse_shelf(rows)
    assert len(rows) > 4000 and len(coll) < 1500


def test_the_collapse_refuses_a_shelf_whose_metrics_vary():
    rows = [
        {"player_id": "x", "hof_monitor": 1, "hof_standard": 1, "WAR_career": 1,
         "WAR_peak7": 1, "JAWS": 1},
        {"player_id": "x", "hof_monitor": 2, "hof_standard": 1, "WAR_career": 1,
         "WAR_peak7": 1, "JAWS": 1},
    ]
    with pytest.raises(RuntimeError, match="vary across ballot"):
        bo.collapse_shelf(rows)


def test_a_censored_row_never_enters_the_bakeoff(bb):
    """MISTAKE 2. Checked through the counts rather than by trusting the
    selection code: the scored frame must be strictly smaller than the eligible
    universe and its base rate must be the resolved one."""
    f = bb["frame"]
    assert f["n_scored"] < 3620
    assert 0.05 < f["base_rate"] < 0.5
    src = (ROOT / "tools" / "hof_bakeoff.py").read_text(encoding="utf-8")
    assert "NEVER truthiness" in src
    assert ".notna()" in src


def test_no_public_column_is_ever_imputed():
    """MISTAKE 3."""
    src = (ROOT / "tools" / "hof_bakeoff.py").read_text(encoding="utf-8")
    assert "NEVER imputed" in src
    # The only fill in the module is a route CENSUS label, which is a display
    # string and not a score. A fill on any of the arms would be an invented
    # number for a player who never reached an election page.
    for arm in bo.ALL_ARMS:
        assert f'["{arm}"].fillna' not in src and f"{arm}.fillna" not in src


def test_the_common_support_drop_accounting_sums_and_names_its_rows(d):
    for lab in ("bbwaa", "any"):
        a = d["labels"][lab]["frame"]["drop_accounting"]
        assert a["sums"] is True
        assert a["n_kept"] + a["n_dropped"] == a["n_read"]
        assert a["dropped_positive"] + a["dropped_negative"] == a["n_dropped"]
        if a["n_dropped"]:
            assert a["dropped_names"], "rows were dropped and not named"


def test_an_outcome_correlated_drop_refuses_the_pooled_comparison(d):
    """MISTAKE 5. Seventeen dropped rows and every one a positive. A ninety
    percent positive-share threshold would not fire on 17 of 286, which is
    exactly the case such a threshold would exist for."""
    a = d["labels"]["any"]["frame"]["drop_accounting"]
    assert a["n_dropped"] == 17
    assert a["dropped_positive"] == 17 and a["dropped_negative"] == 0
    assert a["pooled_comparison_refused"] is True
    assert "Roberto Clemente" in a["dropped_names"]


def test_the_primary_label_has_no_shelf_hole_at_all(d):
    a = d["labels"]["bbwaa"]["frame"]["drop_accounting"]
    assert a["n_dropped"] == 0, (
        "the headline label now drops rows, so its comparison needs the same "
        "route-concentration adjudication label_any gets")


def test_bbwaa_is_the_primary_label_and_the_reason_is_recorded(d):
    assert d["primary_label"] == "bbwaa"
    why = d["why_bbwaa_is_primary"]
    assert "OUTCOME-DEPENDENT" in why and "seventeen positives" in why


def test_the_population_caveat_travels_with_every_label(d):
    for lab in d["labels"]:
        note = d["labels"][lab]["frame"]["population_note"]
        assert "NOT the eligible universe" in note
        assert "screening committee" in note


# --------------------------------------------------------------------------
# The arms
# --------------------------------------------------------------------------

def test_the_holm_family_is_the_distinct_metrics_and_not_every_column(d):
    """JAWS/jaws, WAR_career/career_war and WAR_peak7/war7 are the scraped and
    in-house versions of the same three quantities."""
    assert len(bo.DISTINCT_METRICS) == 8
    assert len(bo.ALL_ARMS) == 11
    for lab in d["labels"]:
        fams = d["labels"][lab]["discrimination_full_frame"]["families"]
        for name, fam in fams.items():
            assert fam["family_size_k"] == fam["holm"]["k"]
            assert fam["family_size_k"] <= len(bo.DISTINCT_METRICS)


def test_the_label_derived_arm_is_never_used_as_a_score_or_a_normalizer():
    assert "JAWS_pos" in bo.REJECTED_ARMS
    assert "JAWS_pos" not in bo.ALL_ARMS
    assert "LABEL-DERIVED" in bo.REJECTED_ARMS["JAWS_pos"]
    src = (ROOT / "tools" / "hof_bakeoff.py").read_text(encoding="utf-8")
    body = src.split("REJECTED_ARMS", 1)[1].split("def frozen_at", 1)[1]
    assert "JAWS_pos" not in body, "the rejected arm is referenced after its refusal"


def test_the_hof_marker_is_never_read():
    assert "bref_hof_marker_as_of_scrape" in bo.REJECTED_ARMS
    src = (ROOT / "tools" / "hof_bakeoff.py").read_text(encoding="utf-8")
    body = src.split("def frozen_at", 1)[1]
    assert "bref_hof_marker" not in body


def test_the_absent_public_metrics_are_named_as_absent():
    for k in ("black_ink", "gray_ink", "hall_rating", "wwar", "keltner"):
        assert "DOES NOT EXIST" in bo.REJECTED_ARMS[k]


def test_our_ink_is_never_presented_as_black_ink(d):
    assert "ink" in bo.INHOUSE_ARMS
    assert "Never presented as the public Black Ink" in bo.REJECTED_ARMS["black_ink"]


# --------------------------------------------------------------------------
# The result
# --------------------------------------------------------------------------

def test_the_best_public_rule_beats_every_in_house_column(bb):
    """PREDICTION 1. If this ever inverts it is a real finding and the whole
    gate has to be re-read before it is shown anywhere."""
    fam = bb["discrimination_full_frame"]["families"]["resampled_public_argmax"]
    assert bb["discrimination_full_frame"]["public_argmax"] == "hof_monitor"
    for arm in bo.INHOUSE_ARMS:
        c = fam["cells"][arm]
        fl = c["floor_E_cond_in_run"]
        assert fl["point_delta"] < 0, f"{arm} now beats the best public rule"
        assert abs(fl["point_delta"]) > fl["mde95"], (
            f"{arm} no longer loses above its own floor, so the bar is softer "
            "than the gate recorded")


def test_the_ranking_claim_sits_on_one_family_only(bb):
    fams = bb["discrimination_full_frame"]["families"]
    assert fams["resampled_public_argmax"]["carries_the_ranking_claim"] is True
    assert fams["pre_designated_reference"]["carries_the_ranking_claim"] is False


def test_most_of_the_reference_family_does_not_resolve(bb):
    """PREDICTION 2. JAWS was pre-designated deliberately, not because it was
    expected to win."""
    fam = bb["discrimination_full_frame"]["families"]["pre_designated_reference"]
    unres = sum(1 for c in fam["cells"].values() if "not resolvable" in c["verdict"])
    assert unres >= len(fam["cells"]) // 2


def test_the_tie_decomposition_sums_and_matches_the_auc(bb):
    for arm, c in bb["discrimination_full_frame"]["per_arm"].items():
        assert c["concordant"] + c["discordant"] + c["tied"] == c["n_pairs"]
        assert abs(c["auc"] - c["auc_from_pairs"]) < 1e-6, (
            f"{arm}: the AUC and the pair decomposition disagree")


def test_the_low_cardinality_arm_is_flagged_by_its_tie_share(bb):
    """`ink` has 30 distinct values and the highest tie share on the board. It is
    published so a reader can see that its AUC is carried by fewer distinctions
    than the others."""
    ink = bb["discrimination_full_frame"]["per_arm"]["ink"]
    assert ink["n_distinct"] < 60
    assert ink["tied_pair_share"] > 0.01


def test_every_published_delta_carries_a_floor_naming_its_estimator(d):
    for lab in d["labels"]:
        for fam in d["labels"][lab]["discrimination_full_frame"]["families"].values():
            for arm, c in fam["cells"].items():
                fl = c["floor_E_cond_in_run"]
                assert fl["estimator"] == "E_cond"
                assert fl.get("mde95") is not None
                assert fl["convention"].startswith("MDE95 = 1.645")


# --------------------------------------------------------------------------
# The calibration leg and its guards
# --------------------------------------------------------------------------

def test_platt_leaves_auc_bit_identical_within_each_fold(bb):
    c = bb["calibration"]
    assert c["per_fold_auc_invariance_n_checks"] > 50
    assert c["per_fold_auc_invariance_max_abs"] <= 1e-9, (
        "post-Platt AUC moved INSIDE a fold, which is a monotone map failing to "
        "be monotone; nothing ships on that")


def test_the_pooled_shift_is_published_and_not_asserted_zero(bb):
    """MISTAKE 4, and this is the assertion whose ABSENCE is the point. A
    mixture of fold-specific monotone maps is not one monotone map, so the
    pooled shift is real and is published as a measured quantity."""
    c = bb["calibration"]
    sh = c["pooled_calibrated_minus_raw_auc"]
    assert sh and any(abs(v) > 1e-4 for v in sh.values()), (
        "the pooled shift came back at zero everywhere, which would mean the "
        "folds are not producing distinct maps")
    assert "not one monotone map" in c["why_the_pooled_shift_is_published_not_asserted_zero"]


def test_the_platt_fit_is_penalised_and_not_a_bare_hessian_ridge():
    src = (ROOT / "tools" / "hof_bakeoff.py").read_text(encoding="utf-8")
    i = src.index("def platt_fit")
    body = src[i:i + 2200]
    assert "ridge * w" in body, (
        "the penalty must reach the GRADIENT. A ridge on the Hessian alone makes "
        "it invertible and does not bound the coefficients")
    assert "lam *= 0.5" in body, "no step halving, so a deviance increase runs away"


def test_a_separable_fold_converges_to_finite_coefficients():
    """Perfect separation: the unpenalised maximum likelihood estimate is at
    infinity. The fit must come back finite and its probabilities must stay
    strictly inside the unit interval."""
    scores = list(range(40))
    y = [0] * 20 + [1] * 20
    fit = bo.platt_fit(scores, y)
    assert all(abs(fit[k]) < 1e6 for k in ("a", "b"))
    p = bo.platt_apply(fit, scores)
    assert float(p.min()) > 0.0 and float(p.max()) < 1.0


def test_the_burn_in_requires_both_classes(d):
    for lab in d["labels"]:
        f = d["labels"][lab]["folds"]
        if not f.get("blocks"):
            continue
        first = f["blocks"][0]
        assert first["train_pos"] >= bo.BURN_IN_MIN_PER_CLASS
        assert (first["n_train"] - first["train_pos"]) >= bo.BURN_IN_MIN_PER_CLASS


def test_the_fold_blocks_are_contiguous_and_five_years_wide(d):
    for lab in d["labels"]:
        f = d["labels"][lab]["folds"]
        blocks = f.get("blocks") or []
        for b in blocks:
            assert b["hi"] - b["lo"] == bo.FOLD_WIDTH_YEARS - 1
        for a, b in zip(blocks, blocks[1:]):
            assert b["lo"] == a["hi"] + 1, (
                "the fold blocks are not contiguous. An empty block dropped from "
                "the list makes the published chain jump years and reads as a "
                "broken forward chain")


def test_the_training_horizon_violation_count_is_published(d):
    """Guard 5. Career-final features mean a training row can carry WAR earned
    after its own fold cut. It cannot move the raw AUC leg but it contaminates
    the Platt fits, so it is counted rather than assumed away."""
    for lab in d["labels"]:
        c = d["labels"][lab]["calibration"]
        if c.get("status"):
            continue
        assert "training_rows_with_a_season_at_or_after_their_fold_cut" in c


def test_the_calibration_error_leg_resolves_nothing(bb):
    """PREDICTION 3's surviving half, and the sharpest part of it. After per-fold
    Platt every arm is calibrated by construction on its training distribution,
    and a ten-bin error on a few hundred rows cannot separate what is left."""
    h = bb["calibration"]["holm_by_statistic"]["ece_quantile10"]
    assert not [c for c in h["cells"] if c["reject_holm"]], (
        "a calibration-error cell now clears Holm, which contradicts the "
        "registration and would be a real finding")


def test_the_calibration_deltas_are_marked_conditional(bb):
    for arm, cells in (bb["calibration"].get("deltas") or {}).items():
        for name, c in cells.items():
            assert "CONDITIONAL" in c["estimator_note"], (
                "this lane refits a Platt map per fold, so an E_cond floor does "
                "not carry the refit variance and the verdict has to say so")


def test_the_per_arm_levels_are_flagged_as_a_fold_mixture(bb):
    for arm, lv in bb["calibration"]["levels"].items():
        assert lv["is_a_fold_mixture_not_an_arm_calibration"] is True


# --------------------------------------------------------------------------
# The reproduction check
# --------------------------------------------------------------------------

def test_the_scraped_and_in_house_versions_agree_on_most_players(bb):
    """This extends the fifteen hand-checked reproduction cells to over a
    thousand players. The residual is the Negro Leagues and pre-1901
    population, where the two sources count different seasons."""
    r = bb["discrimination_full_frame"]["reproduction_check"]
    for pair, v in r.items():
        assert v["n"] > 1000
        assert v["n_exact_to_a_tenth"] / v["n"] > 0.85, (
            f"{pair}: the reproduction agrees on only "
            f"{v['n_exact_to_a_tenth']} of {v['n']}")


def test_the_gate_records_which_predictions_held_and_which_failed():
    txt = GATE.read_text(encoding="utf-8")
    assert "PREDICTION 1 HELD" in txt
    assert "HELD ON THE PRIMARY LABEL AND FAILED ON THE SENSITIVITY" in txt, (
        "the calibration prediction failed on label_any and a failed prediction "
        "is written down, not edited")
