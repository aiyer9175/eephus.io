"""Lane B-L3 guards: the opportunity-decomposition closure.

WHAT THESE TESTS ARE FOR. The lane's product is a CLOSURE, and a closure is only worth
anything if its evidence stays where it was put. Three properties are load-bearing:

  1. EVERY FAILED ARM IS A BLOCK IN ONE ARTIFACT. A lane that sprays one data/*_eval.json
     per arm creates artifacts with no registry row, which is a suite failure by the
     standing rule in test_model_registry.test_every_eval_artifact_is_registered - and,
     worse, it lets a future reader find one arm without finding the other three.
  2. THE COSINE BOUND IS PUBLISHED, with its scope note. It is the reason the twenty
     closed objective-lane cells had to fail; without it the ledger reads as twenty
     coincidences.
  3. EVERY DELTA CARRIES A FLOOR AND AN ESTIMATOR LABEL. MDE95 is E_refit, MDE95_COND is
     E_cond, and neither is quotable without its estimator (docs/EFV_GATE_STANDARD.md
     section 1). A delta printed bare is how a null gets read as a result.

These tests read the committed artifact. They do NOT re-run the lab: the lab takes about
40 seconds and reads a gitignored parquet cache, so a test that ran it would be both slow
and red on any box without the cache.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
ART = ROOT / "data" / "xfv_opportunity_eval.json"
LAB = ROOT / "tools" / "efv_opportunity_lab.py"
GATE = ROOT / "docs" / "efv-2026-08-09" / "OPPORTUNITY_DECOMP_GATE.md"

# The four registered arms of OPPORTUNITY_DECOMP_GATE.md section 7. Each may appear with
# a `_cal` scale-calibrated companion; the base name is what must exist.
REGISTERED_ARMS = ("multiplicative_blend", "multiplicative_pure", "hurdle_blend",
                   "auxiliary_gamma_1.0")

POOL_CELLS = ("hit.full_pool_km", "hit.debuted_km",
              "pit.full_pool_km", "pit.debuted_km")


@pytest.fixture(scope="module")
def art():
    assert ART.exists(), f"missing {ART.name}; run `python tools/efv_opportunity_lab.py all`"
    return json.loads(ART.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. one artifact, every arm a block inside it
# ---------------------------------------------------------------------------

def test_every_arm_is_a_block_in_the_one_artifact(art):
    arms = art["exploitation_arms"]["arms"]
    for name in REGISTERED_ARMS:
        assert name in arms, (
            f"arm {name} is not a block in data/xfv_opportunity_eval.json. Every arm of "
            f"this lane lives in ONE artifact; splitting them hides the failures from "
            f"each other.")
        assert arms[name]["cells"], f"arm {name} carries no scored cells"


def test_no_arm_is_written_as_a_standalone_eval_artifact():
    """A new data/*_eval.json with no registry row fails
    test_model_registry.test_every_eval_artifact_is_registered. This lane writes exactly
    ONE eval artifact, and this test is what stops a future edit from adding a second."""
    src = LAB.read_text(encoding="utf-8")
    written = set(re.findall(r"[\w./\\]*?([\w]+_eval\.json)", src))
    assert written <= {"xfv_opportunity_eval.json", "xfv_power_eval.json",
                       "xfv_rank_objective_eval.json"}, (
        f"tools/efv_opportunity_lab.py names eval artifacts beyond its own: {written}. "
        f"xfv_power_eval.json is READ for floors and xfv_rank_objective_eval.json is "
        f"CITED; nothing else may appear.")
    # only one path is ever written
    assert src.count("write_text") == 1, (
        "the lab writes more than one file. Exactly one artifact ships from this lane.")
    assert 'OUT_PATH = DATA / "xfv_opportunity_eval.json"' in src

    per_arm = [f"data/xfv_opportunity_{a}_eval.json" for a in REGISTERED_ARMS]
    for p in per_arm:
        assert not (ROOT / p).exists(), f"{p} exists; arms are BLOCKS, not files"


def test_the_arms_that_the_gate_registers_are_the_arms_that_ran(art):
    """Pre-registration is worth nothing if the run quietly drops an arm."""
    doc = GATE.read_text(encoding="utf-8")
    for token in ("ARM 1, MULTIPLICATIVE", "ARM 2, HURDLE", "ARM 3, AUXILIARY MULTI-TASK"):
        assert token in doc, f"gate doc lost its registration of {token}"
    ran = set(art["verdict"]["arms_run"])
    for name in REGISTERED_ARMS:
        assert name in ran, f"registered arm {name} did not run"


# ---------------------------------------------------------------------------
# 2. the cosine bound is published, with its scope
# ---------------------------------------------------------------------------

def test_cosine_bound_is_published_on_both_sides(art):
    for side in ("hit", "pit"):
        cb = art["decomposition"]["sides"][side]["cosine_bound"]
        c = cb["cosine_war_vs_opportunity"]
        assert c is not None, f"{side}: no cosine published"
        assert 0.0 <= c <= 1.0, f"{side}: cosine {c} outside [0, 1]"
        orth = cb["orthogonal_linear_extent_sqrt_1_minus_cos2"]
        assert orth == pytest.approx((1.0 - c * c) ** 0.5, abs=1e-3), (
            f"{side}: the published orthogonal extent does not match its own cosine. That "
            f"number IS the bound; an inconsistent pair is worse than no bound.")
    assert art["verdict"]["cosine_bound"], "the verdict block does not carry the cosine"
    assert art["verdict"]["cosine_orthogonal_linear_extent"]


def test_cosine_bound_carries_its_scope_note(art):
    """A cosine quoted without its scope is a stronger claim than the measurement
    supports: it bounds REWEIGHTINGS of the existing feature set, not new features and
    not nonlinear models."""
    for side in ("hit", "pit"):
        scope = art["decomposition"]["sides"][side]["cosine_bound"]["SCOPE"]
        assert "REWEIGHTINGS" in scope
        assert "does NOT" in scope and "new feature" in scope
        assert "nonlinear" in scope


# ---------------------------------------------------------------------------
# 3. every delta carries a floor and an estimator label
# ---------------------------------------------------------------------------

def _delta_blocks(art):
    for arm, v in art["exploitation_arms"]["arms"].items():
        for cell, b in v["cells"].items():
            yield f"{arm}.{cell}", b


def test_every_delta_carries_a_floor_and_an_estimator_label(art):
    seen = 0
    for label, b in _delta_blocks(art):
        assert "point_delta" in b, f"{label}: no delta"
        for k in ("mde95", "mde95_cond"):
            assert b.get(k) is not None, f"{label}: delta with no {k} floor"
            assert b[k] > 0, f"{label}: non-positive floor {k}"
        assert "E_refit" in b["mde95_estimator"], f"{label}: MDE95 not labelled E_refit"
        assert "E_cond" in b["mde95_cond_estimator"], f"{label}: MDE95_COND not labelled E_cond"
        assert b["floor_source"].startswith("data/xfv_power_eval.json"), (
            f"{label}: the floor does not cite the B-L1 artifact. This lane derives no "
            f"floor of its own.")
        assert b["margin_over_mde95"] == pytest.approx(
            abs(b["point_delta"]) / b["mde95"], abs=2e-3), f"{label}: margin does not match"
        assert b["margin_over_mde95_cond"] == pytest.approx(
            abs(b["point_delta"]) / b["mde95_cond"], abs=2e-3), f"{label}: cond margin"
        assert b["verdict"] in ("NULL", "RESOLVABLE GAIN", "RESOLVABLE LOSS"), label
        seen += 1
    assert seen >= len(REGISTERED_ARMS) * 4, f"only {seen} delta blocks; expected 4+ per arm"


def test_floors_match_the_published_bl1_artifact(art):
    """The floors are READ from data/xfv_power_eval.json, not retyped. A retyped floor
    drifts the moment B-L1 re-derives."""
    power = json.loads((ROOT / "data" / "xfv_power_eval.json").read_text(encoding="utf-8"))
    cells = power["partb_floors"]["cells"]
    published = art["exploitation_arms"]["floors"]
    for key, f in published.items():
        src = cells[f["source_cell"]]
        assert f["mde95"] == src["MDE95"], f"{key}: MDE95 drifted from B-L1"
        assert f["mde95_cond"] == src["MDE95_COND"], f"{key}: MDE95_COND drifted from B-L1"


def test_one_sided_convention_is_stated(art):
    conv = art["exploitation_arms"]["floor_convention"]
    assert "ONE-SIDED" in conv and "1.645" in conv
    assert "E_refit" in conv and "E_cond" in conv


# ---------------------------------------------------------------------------
# 4. the closure itself
# ---------------------------------------------------------------------------

def test_nothing_ships_and_no_arm_promoted(art):
    assert art["verdict"]["ships"] == "nothing"
    assert art["verdict"]["arms_promoted"] == [], (
        "an arm promoted. This lane is a CLOSURE: re-read OPPORTUNITY_DECOMP_GATE.md "
        "section 8 before acting on that, and do not let this test be the thing that "
        "silently blesses it.")
    for arm, v in art["exploitation_arms"]["arms"].items():
        assert v["verdict"] in ("NO SHIP", "PROMOTED"), arm


def test_harness_liveness_is_asserted_not_assumed(art):
    """Nulls are only informative if the battery can resolve anything at all. The
    multiplicative arm is the lane's own detection control: it resolves as a loss."""
    assert art["verdict"]["arms_with_a_resolvable_loss"], (
        "no cell resolves anywhere in the lane, so every null in it is uninformative")
    assert "RESOLVES" in art["verdict"]["harness_liveness"]


def test_multiplicative_failure_is_diagnosed_not_just_reported(art):
    fm = art["exploitation_arms"]["arms"]["multiplicative_blend"]["failure_mechanism"]
    assert fm["status"].startswith("CLOSED FOR CAUSE")
    assert "negative" in fm["statement"].lower()
    assert "TIE" in fm["unfixable_in_family"]
    for cell in POOL_CELLS:
        m = fm["measured"][cell]
        assert m["n_rate_pred"] > 0
        assert 0.0 <= m["share_rate_pred_negative"] <= 1.0
        assert m["share_rate_pred_negative"] > 0.0, (
            f"{cell}: the stated mechanism is that the rate leg goes negative. If no "
            f"prediction is negative the published mechanism is wrong.")


def test_gamma_zero_is_exact_parity_with_the_shipped_fit(art):
    """gamma=0 IS the shipped fit by construction. A non-zero delta there means the arm's
    model leg is not on the shipped scale, which makes every other gamma uninterpretable.
    This check FAILED on the first implementation and is the reason the mixed target is
    rescaled to the WAR target's mean and sd."""
    sweep = art["exploitation_arms"]["auxiliary_gamma_sweep"]
    for cell, row in sweep.items():
        assert row["gamma0_parity_blend"], f"{cell}: gamma=0 blend is not shipped parity"
        assert row["gamma0_parity_pure"], f"{cell}: gamma=0 pure leg is not shipped parity"
        assert row["deltas_by_gamma_blend"]["0.0"] == 0.0, cell


# ---------------------------------------------------------------------------
# 5. the two pre-registered hazards survive into the artifact
# ---------------------------------------------------------------------------

def test_selection_hazard_is_a_field_not_prose(art):
    """rho(fv, quality) is conditional on selection ON THE DENOMINATOR IT DIVIDES BY. A
    downstream consumer reading the JSON must not be able to miss that."""
    for side in ("hit", "pit"):
        d = art["decomposition"]["sides"][side]["decomposition"]
        h = d["SELECTION_HAZARD"]
        assert h["applies_to"].startswith("quality")
        assert "CONDITIONAL-ON-SELECTION" in h["statement"]
        assert "never_quote" in h and "bias_direction" in h
        assert d["quality_primary"]["rho"] is not None
        assert d["quality_sensitivity"], f"{side}: no declared threshold sensitivity"


def test_deploy_hazard_is_recorded(art):
    """.cache/war_daily/*.parquet is gitignored and rebuilt from pybaseball. The artifact
    must say, in itself, that this can never become a model input as-is."""
    dh = art["identity_join"]["deploy_hazard"]
    assert "GITIGNORED" in dh
    assert "MUST NEVER become a model input" in dh
    assert "git checkout" in dh


def test_censoring_parity_between_numerator_and_target(art):
    cp = art["identity_join"]["censoring_parity"]
    assert "_label_6yr" in cp
    # The artifact must be cut on the label clock it decomposes: a stale artifact at an
    # older RESOLVED_THROUGH carries the wrong censoring rule for the current matrix.
    import efv_dataset as ed
    assert f"RESOLVED_THROUGH={ed.RESOLVED_THROUGH}," in cp, (
        f"the artifact was cut at a different RESOLVED_THROUGH than efv_dataset's "
        f"{ed.RESOLVED_THROUGH}; rerun `python tools/efv_opportunity_lab.py all`")
    # 845 at RESOLVED_THROUGH 2025 (B-L3 and the eWAR label epoch); 968 at 2026 since
    # the fWAR label epoch re-run (POSTEPOCH_4).
    assert str(art["identity_join"]["sides"]["hit"]["n_debuted"]) == "968"


# ---------------------------------------------------------------------------
# 6. the not-a-banned-re-analysis argument, and the boundary it stays behind
# ---------------------------------------------------------------------------

def test_artifact_states_why_this_is_not_a_re_analysis(art):
    s = art["not_a_banned_reanalysis"]
    assert "MONOTONE RELABEL" in s
    assert "xfv_rank_objective_eval.json" in s
    assert "NEW DATA" in s


def test_dispersion_leg_stays_on_the_distribution_side_of_the_boundary(art):
    d = art["dispersion_diagnostic"]
    assert "_realized_bucket" in d["boundary"]
    assert "reports no ECE" in d["boundary"]
    # Scan the KEYS the measurement reports under, not its prose: the boundary's own name
    # ("pooled-bust-ECE") has to appear in the note that cites it, and a substring scan
    # over prose also fires on innocent words such as "recent".
    def _keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from _keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from _keys(v)
    banned = re.compile(r"(^|_)(ece|bucket|buckets|calibration_curve)($|_)", re.I)
    hits = [k for k in _keys(d["sides"]) if banned.search(k)]
    assert not hits, (
        f"the dispersion diagnostic reports {hits}. efv_reliability._realized_bucket's "
        f"docstring closes the bucket-assignment and ECE door; this leg is about the "
        f"DISTRIBUTION.")


def test_dispersion_confound_is_reported_not_worked_around(art):
    """The pre-registered cohort-matched control is INFEASIBLE here: `censored` is a
    near-deterministic function of debut cohort. Saying so is the finding."""
    for side in ("hit", "pit"):
        s = art["dispersion_diagnostic"]["sides"][side]
        c = s["cohort_matched_control"]
        assert c["status"] == "INFEASIBLE ON THIS DESIGN"
        col = c["censoring_cohort_collinearity"]
        assert col["share"] < 0.01, (
            f"{side}: censoring is no longer collinear with cohort ({col['share']}). The "
            f"pre-registered control may now be feasible; re-read section 9.")
        assert s["unrestricted_comparison_is_CONFOUNDED"] is True
        synth = s["synthetic_censoring_IDENTIFIED_LEG"]
        assert synth["identified"], f"{side}: the identified leg did not run"
        assert synth["join_label_agreement"]["share"] > 0.95, (
            f"{side}: the war_daily join reproduces target_resolved on only "
            f"{synth['join_label_agreement']['share']} of rows, so the leg would be "
            f"measuring the join rather than the label fill.")
        assert set(synth["by_observed_seasons"]) == {"2", "3", "4", "5"}
    assert "NOT pre-registered" in art["dispersion_diagnostic"]["instrument_note"]


def test_brief_rule_discrepancy_is_recorded(art):
    """The lane brief's decision rule reads inverted against its own mechanism. Recording
    that is a finding; silently resolving it is not."""
    assert "inverted" in art["dispersion_diagnostic"]["brief_rule_discrepancy"]


# ---------------------------------------------------------------------------
# 7. house rules
# ---------------------------------------------------------------------------

def test_no_em_dash_or_en_dash_in_the_lane_files():
    """Owner rule, lint-gated elsewhere. The dash characters are built from code points
    rather than typed, so this file can guard the rule without breaking it."""
    for p in (LAB, GATE, ART, Path(__file__)):
        txt = p.read_text(encoding="utf-8")
        for cp, name in ((0x2014, "em-dash"), (0x2013, "en-dash")):
            assert chr(cp) not in txt, (
                f"{p.name} contains an {name}; the owner rule is ' - '")


def test_rho_and_delta_round_to_four_places(art):
    """rho / AUC / delta round NEAREST at 4 dp; they are not FV grades and do not ceil."""
    for label, b in _delta_blocks(art):
        for k in ("point_delta", "arm_rho", "incumbent_rho"):
            v = b.get(k)
            if v is None:
                continue
            assert round(float(v), 4) == float(v), f"{label}.{k} = {v} is not 4 dp"
