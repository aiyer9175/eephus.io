# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the 2026-09-18 re-gates (docs/HEM_RIV_REGATE_GATE.md).

RE-GATE 1 asked what the shipped xHEM+ / fwdHEM+ columns actually do, rather
than what the eval-normalized constructions did. RE-GATE 2 asked RIV+ the one
question it claims to answer, with REM+ as the named baseline.

These tests pin what the gates FOUND, including the two losses, and the
structural rules that made the findings trustworthy: both bootstrap conventions
on every cell, no floor read off a stored constant, and coverage reported
separately from the verdict. A test that only pinned the wins would let the
next refactor quietly restore the claims the gates killed.

Pure file reads; no lab is executed here (the batteries are seeded and their
artifacts are committed)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
GATE_DOC = ROOT / "docs" / "HEM_RIV_REGATE_GATE.md"
R1_PATH = ROOT / "data" / "xhem_served_regate_eval.json"
R2_PATH = ROOT / "data" / "riv_market_regate_eval.json"
RIV_SHIPPED = ROOT / "data" / "riv_plus_eval.json"
REM_LAB = ROOT / "tools" / "rem_plus_lab.py"


def _json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _row(model_id: str) -> dict:
    reg = _json(ROOT / "data" / "model_registry.json")
    for m in reg["models"]:
        if m.get("model_id") == model_id:
            return m
    raise AssertionError(f"registry row missing: {model_id}")


# ---------------------------------------------------------------------------
# the pre-registration itself
# ---------------------------------------------------------------------------

def test_gate_document_exists_and_claims_its_order():
    assert GATE_DOC.is_file(), "the pre-registration is the object under test too"
    text = GATE_DOC.read_text(encoding="utf-8")
    assert "NOTHING IN THIS DOCUMENT WAS COMPUTED" in text
    assert "HONESTY CLAUSE" in text, (
        "the document must state which figures were already READ before it was "
        "written; a pre-registration that hides its priors is not one")


@pytest.mark.parametrize("path", [R1_PATH, R2_PATH])
def test_eval_artifacts_name_their_gate_document(path: Path):
    d = _json(path)
    assert d["gate_document"] == "docs/HEM_RIV_REGATE_GATE.md"
    assert d["pre_registered"].startswith("2026-09-18")


# ---------------------------------------------------------------------------
# RE-GATE 1: the reproduction receipt, then the two findings
# ---------------------------------------------------------------------------

def test_d0_reproduces_the_published_xhem_numbers_exactly():
    """The stop rule: if D0 had not reproduced, the run stopped and the
    reproduction failure was the finding. It did reproduce, to four decimals,
    on both arms and both conventions."""
    rep = _json(R1_PATH)["d0_reproduction_check"]
    for arm in ("A1", "A2"):
        assert rep[arm]["reproduces_published"] is True, arm
        assert rep[arm]["identical_to_harness"] is True, (
            f"{arm}: this lab's bootstrap must be the harness bootstrap, not a "
            f"look-alike")
    assert rep["A1"]["lab_v1"]["lo95"] == 0.0173
    assert rep["A2"]["lab_v1"]["lo95"] == 0.0038
    assert rep["A2"]["lab_v2"]["lo95"] == -0.0069


def test_a1_served_xhem_holds_under_both_conventions():
    arm = _json(R1_PATH)["arms"]["A1_xhem_plus"]
    d4 = arm["ladder"]["D4"]
    assert d4["v1"]["gap_ci"]["lo95"] > 0 and d4["v2"]["gap_ci"]["lo95"] > 0
    assert arm["passes_v1_after_holm"] and arm["passes_v2_after_holm"]
    assert arm["verdict"] == "validated"


def test_a2_served_fwdhem_is_not_separable_and_is_not_refuted():
    """The pre-registered EXPECTED outcome. The served normalizer eats the v1
    edge; the interval straddles zero under both conventions. Not separable is
    not the same as refuted, and the row must not be written as either one."""
    arm = _json(R1_PATH)["arms"]["A2_fwdhem_plus"]
    d4 = arm["ladder"]["D4"]
    assert d4["v1"]["gap_ci"]["lo95"] <= 0, "v1 lower bound must not clear zero"
    assert d4["v2"]["gap_ci"]["lo95"] <= 0, "v2 lower bound must not clear zero"
    assert d4["v1"]["gap_ci"]["hi95"] > 0 and d4["v2"]["gap_ci"]["hi95"] > 0, (
        "hi95 above zero: the claim is unestablished, NOT contradicted")
    assert arm["verdict"] == "provisional"
    assert "EXPECTED TO FAIL" in arm["pre_registered_expectation"]


def test_the_served_normalizer_is_what_moved_the_fwdhem_edge():
    """Localization, measured: the leg normalizers (D0 -> D1) cost the edge,
    not display rounding (D3 -> D4). If a later change flips that, the note
    that blames the normalizer has to change with it."""
    lad = _json(R1_PATH)["arms"]["A2_fwdhem_plus"]["ladder"]
    d0 = lad["D0_original_seed"]["v1"]["gap_ci"]["mean"]
    d1 = lad["D1"]["v1"]["gap_ci"]["mean"]
    d3 = lad["D3"]["v1"]["gap_ci"]["mean"]
    d4 = lad["D4"]["v1"]["gap_ci"]["mean"]
    assert (d0 - d1) > abs(d4 - d3), (
        "the normalizer-pool move must dominate the rounding move")
    assert 0.15 < (d0 - d4) / d0 < 0.75, (
        "the served normalizer costs roughly a third of the v1 edge; a move "
        "outside this band is a different finding and needs a different note")


@pytest.mark.parametrize("arm", ["A1_xhem_plus", "A2_fwdhem_plus"])
def test_every_rung_reports_both_conventions_and_an_in_run_floor(arm: str):
    """The rule this lane exists to enforce: never quote the convention that
    passes while hiding the one that fails, and never read a floor off a
    stored constant."""
    for rung, cells in _json(R1_PATH)["arms"][arm]["ladder"].items():
        for conv in ("v1", "v2"):
            c = cells[conv]
            assert c["gap_ci"] is not None, f"{arm}/{rung}/{conv}"
            assert c["mde95_in_run"] is not None, f"{arm}/{rung}/{conv}"
            assert c["n_boot_draws"] > 0


def test_holm_family_is_two_arms_per_convention():
    m = _json(R1_PATH)["multiplicity"]
    assert m["total_primary_tests_in_the_gate_document"] == 3
    for conv in ("v1", "v2"):
        assert m[conv]["k"] == 2
        keys = {c["key"] for c in m[conv]["cells"]}
        assert keys == {"A1_xhem_plus", "A2_fwdhem_plus"}


def test_coverage_is_reported_separately_from_the_verdict():
    cov = _json(R1_PATH)["coverage"]
    assert cov["pair_set_n_by_predictor_season"]
    assert cov["served_normalizer_pool_by_season"]
    assert cov["board_stamped_never_eligible_by_season"]
    assert "never used to explain a gap" in cov["note"].lower()


# ---------------------------------------------------------------------------
# RE-GATE 2
# ---------------------------------------------------------------------------

def test_riv_market_leg_has_support_and_publishes_its_identity_receipts():
    d = _json(R2_PATH)
    cov = d["coverage"]
    assert cov["n_matched"] >= cov["support_floor"] >= 50, (
        "below the pre-registered floor the comparison is REFUSED, not reported")
    assert cov["matched_by_identity_method"]["canonical_mlbam"] > 0, (
        "the canonical identity path must actually have been used")
    assert len(cov["unmatched_signings"]) == cov["n_unmatched_signings"]
    assert "normalized_name_collisions_in_pool_by_season" in cov, (
        "collisions are published, never assumed away")


def test_riv_is_gated_on_one_target_and_one_scale():
    b1 = _json(R2_PATH)["B1_primary"]
    assert "REM+" in b1["baseline"]
    assert b1["sensitivities"]["log_aav_is_a_rank_no_op"] is True, (
        "the shipped log transform is a rank no-op; if that ever stops being "
        "true the estimand changed and the gate must be rewritten")
    for conv in ("v1", "v2"):
        assert b1[conv]["mde95_in_run"] is not None


def test_riv_claim_is_refuted_but_not_reversed():
    """RIV+ is NOT shown to be worse than REM+. It is shown not to be better,
    and 'better than REM+' was the only claim the row made. Both halves of that
    sentence are pinned, because dropping either one misreads the result."""
    d = _json(R2_PATH)
    b1 = d["B1_primary"]
    trig = b1["decision_rule_trigger"]
    assert trig["refuted_on_resolution_lo95_le_minus_mde95"] is True
    assert trig["refuted_directionally_hi95_lt_0"] is False, (
        "no directional loss: the point estimate still favours RIV+")
    assert b1["v1"]["hi95_lt_0"] is False and b1["v2"]["hi95_lt_0"] is False
    assert d["verdict"]["riv_plus"] == "deprecated"
    assert "NOT shown to be worse" in d["verdict"]["reason"]


def test_the_rule_mis_specification_is_recorded_not_edited_away():
    note = _json(R2_PATH)["B1_primary"]["rule_note_mis_specification_found_in_run"]
    assert "0.315" in note, (
        "the algebra that makes the 'not separable' band unreachable near zero "
        "must stay on the record so the next re-gate fixes it")


def test_repeatability_leg_carries_zero_verdict_weight():
    leg = _json(R2_PATH)["disclosure_repeatability_leg"]
    assert leg["verdict_weight"].startswith("ZERO")
    assert "FORBID" in leg["interpretation_fixed_in_advance"].upper()
    res = leg["results"]["RIV+(Y+1)"]
    assert res["v1"]["gap_ci"]["lo95"] > 0, (
        "REM+ predicts next-year RIV+ better than RIV+ does; that is the "
        "recorded prior and it reproduced")


# ---------------------------------------------------------------------------
# the retirements, which happen regardless of outcome
# ---------------------------------------------------------------------------

def test_the_stored_market_slack_constant_is_gone():
    """Parsed, not grepped: the prose still NAMES the retired 0.02 so the
    history survives, and a text search would trip on that. What must be gone
    is the numeric literal itself."""
    import ast
    src = REM_LAB.read_text(encoding="utf-8")
    literals = [n.value for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.Constant) and isinstance(n.value, float)]
    assert 0.02 not in literals, (
        "the RIV+ market floor was a stored literal; it is an in-run MDE95 now")
    assert "MDE_Z" in src and "_iid_gap_draws" in src


def test_riv_less_stable_is_no_longer_a_pass_condition():
    src = REM_LAB.read_text(encoding="utf-8")
    assert "riv_less_stable and riv_market_ok" not in src, (
        "a check that a number is noisier than its baseline can be passed by "
        "ADDING NOISE, so it cannot gate a ship")
    checks = _json(RIV_SHIPPED)["checks"]
    assert checks["riv_market_alignment_ok"] is False
    assert "zero verdict weight" in checks["note"]


def test_the_shipped_riv_eval_points_at_its_successor_without_editing_numbers():
    d = _json(RIV_SHIPPED)
    assert d["superseded_by"]["artifact"] == "data/riv_market_regate_eval.json"
    # the measured figures other surfaces pin are untouched
    assert d["forward_stability_check"]["riv_plus_y_to_y1_rho"] == 0.2023
    assert d["forward_stability_check"]["rem_plus_y_to_y1_rho"] == 0.3601
    assert d["market_check_aav"]["n_signings_matched"] == 271


# ---------------------------------------------------------------------------
# the registry, which is where a verdict has to actually land
# ---------------------------------------------------------------------------

def test_registry_verdicts_match_what_the_gates_found():
    """What the 2026-09-18 gates found is pinned in their own artifacts. The
    xhem_plus and fwdhem_plus REGISTRY verdicts moved on to the re-baseline of
    2026-10-15 (docs/HEM_XWOBA_REGATE_GATE.md, test_hem_xwoba_regate.py), which
    inherits R1-6 and keeps this read as the prior; riv_plus stays where
    re-gate 2 left it."""
    r1 = _json(R1_PATH)["verdict"]
    assert r1["xhem_plus"] == "validated"
    assert r1["fwdhem_plus"] == "provisional"
    assert _row("riv_plus")["verdict"] == "deprecated"


# The re-baseline artifact (2026-10-15) supersedes the 2026-09-18 read as the
# rows' eval_artifact once it exists; until then the rows point at R1_PATH.
REBASELINE = ROOT / "data" / "hem_xwoba_regate_eval.json"
_HEM_ROW_ARTIFACT = ("data/hem_xwoba_regate_eval.json" if REBASELINE.exists()
                     else "data/xhem_served_regate_eval.json")


def test_registry_rows_point_at_the_regate_artifacts():
    assert _row("xhem_plus")["eval_artifact"] == _HEM_ROW_ARTIFACT
    assert _row("fwdhem_plus")["eval_artifact"] == _HEM_ROW_ARTIFACT
    assert _row("riv_plus")["eval_artifact"] == "data/riv_market_regate_eval.json"
    for model_id in ("xhem_plus", "fwdhem_plus"):
        if REBASELINE.exists():
            assert "data/xhem_served_regate_eval.json" in _row(model_id)["notes"], (
                "the 2026-09-18 read stays cited by path as the prior")


@pytest.mark.parametrize("model_id", ["xhem_plus", "fwdhem_plus"])
def test_the_headline_on_a_served_column_is_the_served_number(model_id: str):
    """The standing consequence of re-gate 1, and it binds the whole +index
    family: the card headline quotes the SERVED construction (ladder D4), and
    the eval-normalized figure may only appear as a labelled reproduction."""
    row = _row(model_id)
    arm = "A1_xhem_plus" if model_id == "xhem_plus" else "A2_fwdhem_plus"
    # the row's OWN artifact: R1_PATH until the re-baseline lands, then that
    d4 = _json(ROOT / row["eval_artifact"])["arms"][arm]["ladder"]["D4"]["v1"]
    head = row["card"]["headline"][0]
    assert head["champion"] == round(d4["rho_primary"], 3)
    assert head["baseline"] == round(d4["rho_baseline"], 3)
    assert "served" in head["label"].lower()
    assert "SERVED" in row["champion"] or "SERVED" in row["metric"]


def test_fwdhem_row_states_the_demotion_and_does_not_claim_the_old_edge():
    notes = _row("fwdhem_plus")["notes"]
    assert "DEMOTED TO PROVISIONAL" in notes
    assert "NOT SEPARABLE" in notes.upper()
    assert re.search(r"reproduction", notes, re.I), (
        "the 0.466 vs 0.454 figure may survive only as a labelled reproduction")


def test_riv_row_drops_the_market_claim_and_keeps_the_frame():
    row = _row("riv_plus")
    notes = row["notes"]
    assert "realized-value record, not a forecast" in row["predicts"].lower() \
        or "REALIZED-VALUE RECORD, NOT A FORECAST" in row["predicts"]
    assert "not shown to be worse" in notes.lower()
    assert "DISPLAY DEBT" in notes, (
        "the column still ships; the debt is recorded because another lane "
        "owns the page")
    # the disclosure figures other surfaces pin are quoted, not invented
    assert "0.2023" in notes and "0.3601" in notes


def test_the_riv_column_and_glossary_forbid_a_forward_reading():
    """Census M06-02. The re-gate's disclosure leg forbids any forward reading
    of the RIV+ column and says the column and glossary copy must say so. The
    column header carried no title at all, and the glossary never said it."""
    gl = _json(ROOT / "data" / "glossary.json")
    entry = [e for e in gl["entries"] if e.get("id") == "riv_plus"][0]
    assert "not a forecast" in entry["methodology"]
    js = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
    col = re.search(r'\{ key: "riv_plus", label: "RIV\+"[^}]*\}', js).group(0)
    assert "title: RIV_TITLE" in col, col
    title = re.search(r"var RIV_TITLE = (.*?);\n", js, re.S).group(1)
    assert "not a forecast" in title


def test_the_fwdhem_copy_follows_the_served_regate():
    """Census M06-04. The xHEM+ Blend header said it beat xwOBA alone and the
    glossary methodology claimed a gap floor above zero, after the re-gate of
    the served column demoted the row to provisional. The copy now says
    provisional and the receipt reads the served cell (A2, rung D4) instead of
    any typed figure."""
    gl = _json(ROOT / "data" / "glossary.json")
    meth = [e for e in gl["entries"] if e.get("id") == "fwdhem_plus"][0]["methodology"]
    assert "Provisional" in meth and "not separable from xwOBA alone" in meth
    assert "0.466" not in meth and "incumbent forward column" not in meth
    js = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
    col = re.search(r'\{ key: "fwdhem_plus", label: "xHEM\+ Blend".*?title: "([^"]*)"', js, re.S)
    assert "Provisional" in col.group(1) and "Beats xwOBA" not in col.group(1)
    gjs = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    spec = gjs[gjs.index("      fwdhem_plus: {"):]
    spec = spec[:spec.index("      pwoba: {")]
    assert '"/data/xhem_served_regate_eval.json"' in spec and "A2_fwdhem_plus" in spec
    assert ".D4" in spec and "d4.v1" in spec and "d4.v2" in spec
    d4 = _json(R1_PATH)["arms"]["A2_fwdhem_plus"]["ladder"]["D4"]
    for conv in ("v1", "v2"):
        assert d4[conv]["gap_ci"]["lo95"] < 0 < d4[conv]["gap_ci"]["hi95"], conv
