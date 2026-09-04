# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Model-registry guards (model-audit WS-0b) — and the STANDING RULE the
owner set for the audit program: every new model ships with a registry
row and an eval artifact, and this file is what enforces it.

The enforcement teeth: any committed eval/gate artifact in data/ MUST be
referenced by a registry row. Write a new model + its backtest artifact
without registering it, and the suite goes red."""

from __future__ import annotations

import json
from pathlib import Path

import model_registry as mr

ROOT = Path(__file__).parent


def test_registry_parses_and_validates():
    reg = mr.load()
    problems = mr.validate(reg)
    assert problems == [], f"registry problems: {problems}"


def test_verdicts_are_honest():
    """validated rows carry artifacts; unvalidated rows carry none (a row
    with an artifact claiming 'unvalidated' is lying about itself)."""
    reg = mr.load()
    assert set(reg["verdict_enum"]) == set(mr.VERDICTS)
    for m in reg["models"]:
        assert m["verdict"] in mr.VERDICTS, m["model_id"]
        if m["verdict"] == "validated":
            assert m["eval_artifact"], f"{m['model_id']}: validated without artifact"
        if m["verdict"] == "unvalidated":
            assert not m["eval_artifact"], f"{m['model_id']}: has artifact, not unvalidated"


def test_known_models_are_registered():
    """The audit's enumerated surfaces can't silently drop off the ledger."""
    ids = {m["model_id"] for m in mr.load()["models"]}
    for required in ("fa_projection_marcel", "fa_war_paths_decay", "fa_market",
                     "fa_team_fit", "fa_penter", "consensus_fv", "eta",
                     "farm_grades", "draft_slot_curve", "overseas_translation",
                     "statcast_plus", "spotlights_movement", "prospect_surplus",
                     "mlb_projections_prospects", "wag"):
        assert required in ids, f"model dropped from registry: {required}"


def test_every_eval_artifact_is_registered():
    """THE STANDING RULE (owner directive 2026-06-11): every committed
    eval/gate artifact must belong to a registered model. New models
    cannot ship a backtest without a registry row — this test is the
    enforcement.

    Registry-hygiene fix 2026-07-16: the glob is *_eval*.json (the old
    *_eval.json missed suffixed companions like rem_plus_eval_restamp.json),
    and COMPANION artifacts count as registered when their parent row's
    notes cite them by path — a companion (restamp / sensitivity table)
    never carries its own verdict, so it belongs on the parent's ledger,
    not on a row of its own."""
    reg = mr.load()
    referenced = {m["eval_artifact"] for m in reg["models"] if m.get("eval_artifact")}
    # companion artifacts cited on a registered row's notes ledger
    import re
    for m in reg["models"]:
        referenced |= set(re.findall(r"data/[\w.\-]+\.json", m.get("notes") or ""))
    on_disk = {f"data/{p.name}" for p in (ROOT / "data").glob("*_eval*.json")}
    on_disk |= {f"data/{p.name}" for p in (ROOT / "data").glob("*gate*_eval.json")}
    unregistered = on_disk - referenced
    # gate artifacts referenced under their canonical names still count
    unregistered = {u for u in unregistered
                    if u not in referenced}
    assert not unregistered, (
        f"eval artifacts with NO registry row (register them in "
        f"data/model_registry.json, or cite the companion on its parent "
        f"row's notes): {sorted(unregistered)}")


def test_freshness_stamps():
    fresh = mr.freshness()
    assert fresh, "no freshness stamps computed"
    for mid, f in fresh.items():
        assert f["artifact_age_days"] >= 0, mid
        assert isinstance(f["stale"], bool), mid
        assert f["age_source"] in ("artifact", "mtime")


def test_an_mtime_age_is_never_reported_as_evidence():
    """A mtime-sourced age is not evidence about a MEASUREMENT's age.

    The deploy box runs `git checkout -- .` nightly, which rewrites the mtime of
    every tracked file to the moment of checkout. So for an artifact that does
    not date itself, the same registry answers differently depending on which
    machine you ask: roughly zero on the box that serves the site, and something
    real on a dev tree. Nothing in the returned dict distinguished the two
    beyond `age_source`, and `stale` was computed from the unreliable number.

    Today this is a NO-OP by luck: no undated artifact happens to be older than
    STALE_DAYS on this machine. It is pinned because the failure is silent and
    machine-dependent, which is the kind that gets discovered from a wrong
    published number rather than from a red test.
    """
    fresh = mr.freshness()
    for mid, f in fresh.items():
        assert f["age_is_evidence"] is (f["age_source"] == "artifact"), mid
        if not f["age_is_evidence"]:
            assert f["stale"] is False, (
                f"{mid} claims stale={f['stale']} from a {f['age_source']}-sourced "
                "age, which the deploy box rewrites on every checkout")


def test_the_undated_set_is_visible_and_bounded():
    """The undated set is a real backlog, so it is counted rather than assumed
    away. It may shrink; test_no_new_undated_eval_artifact stops it growing."""
    fresh = mr.freshness()
    undated = [m for m, f in fresh.items() if not f["age_is_evidence"]]
    assert len(undated) <= 33, (
        f"{len(undated)} rows now take the mtime path, up from the 33 measured "
        "2026-08-14; a new undated artifact should have been caught by "
        "test_no_new_undated_eval_artifact")


def test_a_provisional_row_without_an_artifact_says_why():
    """`validate()` forbids validated-without-artifact and
    unvalidated-with-artifact, but says nothing about PROVISIONAL without an
    artifact. Seven rows are in that state (2026-08-14).

    ON INSPECTION THAT IS NOT A HYGIENE FAILURE, which is why this test asserts
    a justification rather than demanding an artifact or demoting the rows.
    Every one of the seven falls into a category the verdict enum has no word
    for, and each states it in its own `baseline` / `metric`:

      * DESCRIPTIVE BY DESIGN, no forward claim to gate: leverage_board,
        xrem_plus, xsem_plus ("descriptive; no forward gate by design",
        "realized WPA is an outcome, not a forecast").
      * INHERITS A GATED PARENT, a composition or re-expression rather than a
        new estimator: draft_war_room (composes the validated
        draft_slot_curve), prospect_greeks and surplus_downside_risk
        (re-expressions of the validated prospect_surplus curve),
        xfv_backgrade (inherits the eFV forward-chained OOS gate).

    So the real gap is that the enum cannot express "measured by inheritance",
    and the justification lives only in prose. This test makes the prose
    load-bearing: a NEW provisional row carrying no artifact and no stated
    reason fails here. Demoting these seven to `unvalidated` would be worse,
    not better, because a descriptive board that makes no forward claim is not
    the same thing as a predictive claim with zero measurement.
    """
    unjustified = []
    for m in mr.load()["models"]:
        if m.get("verdict") != "provisional" or m.get("eval_artifact"):
            continue
        prose = f"{m.get('baseline') or ''} {m.get('metric') or ''}".lower()
        justified = ("descriptive" in prose or "inherit" in prose
                     or "composes" in prose or "re-expression" in prose
                     or "gated by" in prose or "separately gated" in prose)
        if not justified:
            unjustified.append(m["model_id"])
    assert not unjustified, (
        "provisional rows carrying no eval artifact and no stated reason: "
        f"{sorted(unjustified)}. Either measure them, or say in `baseline` / "
        "`metric` that the row is descriptive by design or inherits a gated "
        "parent, naming the parent.")


def test_stale_threshold_is_reachable():
    """A threshold far above the oldest artifact is not a freshness check.

    STALE_DAYS was 240 while the oldest artifact in the tree was 53 days, so
    `stale` could not fire for any model and the freshness map reported
    "nothing is stale" as a tautology. Keep the threshold within sight of the
    real artifact ages: it should exceed today's oldest (no false alarm on a
    healthy tree) but stay inside 3x of it, so a genuinely neglected eval
    trips it in a plausible amount of time.

    DO NOT LOWER STALE_DAYS AGAIN LOOKING FOR A FINDING. That was tried on
    2026-08-03 (240 -> 90) and re-opened on 2026-08-07 on the grounds that
    `stale` still fires on nothing. It fires on nothing because nothing IS
    neglected: measured 2026-08-07, the oldest dated artifact in the tree is
    58 days and the median is 15. The first clause below FORBIDS any value
    that would fire today, so "lower it until something trips" is not a move
    this test permits, and a bar tuned to produce an alarm on a healthy tree
    is a false alarm rather than a finding.

    The freshness defect that IS real, and is a defect somebody can fix, is
    the undated artifact: see test_no_new_undated_eval_artifact below and
    docs/decision-2026-08-07-freshness-bar.md. One freshness concept, not
    three: this test guards the bar's VALUE, that one guards the INPUT the
    bar is computed from, and /models/ states the distribution for a reader.
    """
    fresh = mr.freshness()
    oldest = max(f["artifact_age_days"] for f in fresh.values())
    assert mr.STALE_DAYS > oldest, (
        f"STALE_DAYS={mr.STALE_DAYS} is below the oldest artifact ({oldest}d), "
        "so the registry would flag a healthy tree")
    assert mr.STALE_DAYS <= 3 * oldest, (
        f"STALE_DAYS={mr.STALE_DAYS} is more than 3x the oldest artifact "
        f"({oldest}d) and cannot realistically fire; lower it so the freshness "
        "map reports a finding rather than a tautology")


# Every registry eval_artifact that declares NO production date of its own,
# measured 2026-08-07: 28 files behind 33 of the 180 freshness rows. For each
# of these, model_registry.freshness() falls back to the file mtime, and the
# deploy box runs `git checkout -- .` nightly, which rewrites every tracked
# mtime to the moment of checkout. So on the box that serves the site these
# rows report an age of roughly zero no matter how old the measurement really
# is, which is the one place a stale eval would matter.
#
# This is a RATCHET, not an allowlist to grow. A new entry here means a new
# row whose age the registry cannot honestly state. When an artifact learns to
# stamp itself (any of generated_at / run_at / fit_date / as_of / date at the
# top level), delete its line; the test stays green as the set shrinks.
UNDATED_EVAL_ARTIFACTS = frozenset({
    "data/_am_crossmodel_agelevel_eval.json",
    "data/college_translation_eval.json",
    "data/fa_gate1_eval.json",
    # fa_gate2_eval, proj_horizon_eval, total_band_eval, trade_machine_eval:
    # removed 2026-08-19, all four now self-date via their writers.
    "data/proj_def_feature_eval.json",
    "data/prospect_def_value_eval.json",
    "data/surplus_sensitivity.json",
    "data/value_framework_fitted.json",
    "data/xfv_cap_sweep_eval.json",
    "data/xfv_generality_eval.json",
    "data/xfv_gradenorm_basis_eval.json",
    "data/xfv_injury_history_eval.json",
    "data/xfv_lambda_reselect_eval.json",
    "data/xfv_odds_calibration_slope_eval.json",
    "data/xfv_overlay_uncapped_eval.json",
    "data/xfv_peak_war_eval.json",
    "data/xfv_proxy_eval.json",
    "data/xfv_surrogate_eval.json",
    "data/xfv_tbs2_eval.json",
    "data/xfv_tools.json",
    "data/xfv_weight_recal_eval.json",
    "data/xfv_wrc_eval.json",
    # Not JSON, so _artifact_date cannot read a stamp out of it at all.
    "docs/efv-2026-07-30/EFV_LANE_GATES.md",
    "docs/efv-sb-athleticism-2026-08-05/results.json",
    "tools/_comb_out/nested_hit_TRACK_R_cal.json",
})


def _undated_artifacts() -> set:
    """Registry eval_artifact paths that exist but declare no date of their own."""
    out = set()
    for m in mr.load()["models"]:
        art = (m.get("eval_artifact") or "").strip()
        if not art:
            continue
        p = ROOT / art
        if p.exists() and mr._artifact_date(p) is None:
            out.add(art)
    return out


def test_no_new_undated_eval_artifact():
    """THE FRESHNESS FINDING (decided 2026-08-07, docs/decision-2026-08-07-
    freshness-bar.md). An eval artifact that does not date itself cannot be
    aged honestly on the deploy box, so the registry silently substitutes a
    checkout timestamp. Ship a new one and this goes red, naming the file.

    The fix when it fires is to stamp the artifact at the top level, not to
    add it to the set: every generator on this platform already knows when it
    ran, and writing that down costs one key."""
    new = sorted(_undated_artifacts() - UNDATED_EVAL_ARTIFACTS)
    assert not new, (
        "eval artifacts with NO production date of their own: "
        f"{new}. model_registry.freshness() will age these by file mtime, and "
        "the deploy box rewrites every mtime on its nightly `git checkout -- .`, "
        "so the age it reports there is the checkout, not the measurement. Add a "
        "top-level generated_at (or run_at / fit_date / as_of / date) to the "
        "artifact's generator. Extending UNDATED_EVAL_ARTIFACTS is not the fix.")


def test_freshness_prefers_the_artifacts_own_stamp_over_mtime():
    """Age must not be measured by file mtime alone.

    `git checkout` and a fresh clone rewrite every mtime to the checkout
    moment, so an mtime-only freshness map reports the entire registry as
    brand new on the deploy box, which is exactly where a stale eval matters.
    Most eval artifacts carry their own generated_at stamp; that must win.
    """
    fresh = mr.freshness()
    stamped = [m for m, f in fresh.items() if f["age_source"] == "artifact"]
    assert len(stamped) > len(fresh) // 2, (
        f"only {len(stamped)}/{len(fresh)} freshness stamps come from the "
        "artifact's own date; the map has fallen back to mtime, which a "
        "checkout resets")


def test_retired_basis_stamps_are_documented():
    """Retired-basis stamps (2026-08-19). Rows whose eval artifacts were
    generated 2026-07-01..2026-08-05 on the 4-fold SCORED_YEARS (2020-2023)
    chain carry basis "retired-4fold-2020-2023": that chain was retired
    2026-08-06 by owner promotion to the 11-fold chain (recorded in
    data/xfv_scoreboard_eval.json legacy_4fold_footnote) and cannot be
    reproduced, so their numbers are archaeology, not the served basis.

    (a) any basis starting "retired" must be one of the documented retired
    bases, so the retirement is readable off the row itself; a new retired
    basis gets added here together with what retired it.
    (b) the SPECIFIC guard: xfv_dispersion_repair carries the C-7 reverted
    stamp. Its correction passed all three originally pre-registered clauses
    and was STILL reverted to identity on the owner's decision (C-7,
    2026-08-14); accidentally re-applying the retired coefficients is the
    exact failure this pins.
    """
    reg = mr.load()
    documented = {"retired-4fold-2020-2023",
                  "retired-correction-reverted-C7-2026-08-14"}
    for m in reg["models"]:
        basis = m.get("basis")
        if basis and basis.startswith("retired"):
            assert basis in documented, (
                f"{m['model_id']}: undocumented retired basis {basis!r}; add it "
                "to this test's documented set together with what retired it")
    by_id = {m["model_id"]: m for m in reg["models"]}
    dr = by_id["xfv_dispersion_repair"]
    assert dr.get("basis") == "retired-correction-reverted-C7-2026-08-14", (
        "xfv_dispersion_repair must carry the C-7 reverted-basis stamp")
    assert "reverted to identity" in (dr.get("notes") or ""), (
        "xfv_dispersion_repair notes must state the C-7 revert to identity")


def test_provisional_kind_enum_when_present():
    """provisional_kind is OPTIONAL and enum-checked only when present
    (model_registry.PROVISIONAL_KINDS); it never changes a verdict."""
    for m in mr.load()["models"]:
        pk = m.get("provisional_kind")
        if pk is not None:
            assert pk in mr.PROVISIONAL_KINDS, (m["model_id"], pk)


def test_surplus_real_backtest_artifact_shape():
    """WS-0d artifact contract: accounting + both slices with the verdict
    metrics; exclusions counted, never guessed; no calibration applied."""
    p = ROOT / "data" / "surplus_backtest_real.json"
    if not p.exists():
        import pytest
        pytest.skip("surplus_backtest_real.json not generated on this machine")
    d = json.loads(p.read_text(encoding="utf-8"))
    acct = d["accounting"]
    assert acct["scored"] > 1000 and acct["listed"] >= acct["scored"]
    assert acct["censored_active"] >= 0 and acct["excluded_no_war"] >= 0
    assert "NONE" in d["conventions"]["calibration_applied"]
    for s in ("full_pool", "resolved_only"):
        blk = d[s]
        assert blk["n_players"] > 500
        assert "slope" in blk["raw_calibration"]
        assert "coverage_p10_p90" in blk["raw_pit"]
        assert "explained_by_war_bias" in blk["decomposition"]


# --------------------------------------------------------------------------
# Post-audit wave, 2026-09-04 (docs/efv-2026-09-03/ARKMETRIC_DESIGN_AUDIT.md).
# Four rows carried claims their own artifacts do not support. These pin the
# corrections so the ledger cannot silently drift back.
# --------------------------------------------------------------------------


def _by_id() -> dict:
    return {m["model_id"]: m for m in mr.load()["models"]}


def test_the_board_floor_routing_has_a_row():
    """AUDIT F18. The routing shipped 2026-08-07 and moved 2,434 served grades,
    its ship doc named a registry row, and the row did not exist: a served-grade
    change lived outside the ledger. The row is provisional and must stay that
    way until a routed grade is scored against realized WAR, because every gate
    it passed measures scope, fidelity and blast radius, never accuracy."""
    row = _by_id().get("efv_board_floor_routing")
    assert row is not None, (
        "the constant-anchor floor routing serves the majority of graded board "
        "rows and has no registry row; docs/efv-2026-08-07/"
        "BOARD_FLOOR_ROUTING_SHIP.md section 7 names it")
    assert row["eval_artifact"] == "docs/efv-2026-08-07/BOARD_FLOOR_ROUTING_SIM.json"
    assert (ROOT / row["eval_artifact"]).exists()
    assert row["verdict"] == "provisional", (
        "no routed grade has ever been scored against realized WAR; the G1-G6 "
        "gates measure scope and blast radius only")
    notes = row["notes"]
    assert "G6" in notes and "PARTIAL FAIL" in notes, (
        "G6 failed on the routed-at-floor population (tie block cut 21.5 "
        "percent, not the >= 50 percent the gate required) and the row must "
        "say so")
    assert "NOT OUTCOME-VALIDATED" in notes.upper()


def test_the_routing_row_agrees_with_the_flag_that_ships_it():
    """The row describes a LIVE routing. If the flag is ever turned back off,
    the row's champion string becomes a false statement about the board."""
    row = _by_id()["efv_board_floor_routing"]
    src = (ROOT / "efv_score.py").read_text(encoding="utf-8")
    assert "SERVE_PROVISIONAL_FOR_CONSTANT_COHORT = True" in src, (
        "efv_score no longer routes the constant-anchor cohort; the "
        "efv_board_floor_routing row still claims routing is ON")
    assert "SERVE_PROVISIONAL_FOR_CONSTANT_COHORT = True" in row["champion"]


def test_wag_is_not_validated_against_an_artifact_with_no_wag_evidence():
    """AUDIT F27. The row read `validated` on "PIT uniformity + coverage" while
    pointing at data/value_framework_fitted.json, which holds the fitted FV to
    WAR bucket curve and nothing about WAG at all. The artifact is kept as
    provenance for the baseline curve; the verdict is not.

    This test is deliberately conditional on the artifact's CONTENT, so it goes
    green the day a real WAG measurement is written into it (or the row is
    re-pointed at one) and red the moment the verdict is promoted without one.
    """
    row = _by_id()["wag"]
    art = ROOT / (row.get("eval_artifact") or "")
    has_wag_evidence = False
    if art.exists() and art.suffix == ".json":
        has_wag_evidence = "wag" in art.read_text(encoding="utf-8").lower()
    if not has_wag_evidence:
        assert row["verdict"] != "validated", (
            f"wag claims `validated` against {row.get('eval_artifact')!r}, which "
            "contains no WAG evidence; a realized-PIT artifact does not exist "
            "(the only PIT test on record samples outcomes from the model "
            "itself). Measure it, or leave the row provisional.")
        assert "realized-pit artifact does not exist" in row["notes"].lower()


def test_consensus_fv_points_at_the_experiment_its_baseline_names():
    """AUDIT F27 / F46. The row's baseline is "best single input", but its
    eval_artifact was data/consensus_weight_eval.json, which measures
    weighted-vs-equal SOURCE WEIGHTING (ship = False). The blend-vs-inputs
    evidence lives in data/source_backtest.json, and it resolves ONE leg: AUC.
    The Spearman leg is inside the floor the backtest can resolve, so the row
    must not be read as an ordering win."""
    row = _by_id()["consensus_fv"]
    assert row["eval_artifact"] == "data/source_backtest.json"
    doc = json.loads((ROOT / row["eval_artifact"]).read_text(encoding="utf-8"))
    blk = doc["accuracy"]["consensus_vs_inputs"]
    assert blk["auc"]["resolvable"] and blk["auc"]["consensus_wins"], (
        "the AUC leg is the only thing holding this row's validated verdict")
    assert not blk["spearman"]["resolvable"], (
        "the Spearman leg became resolvable; re-read the row's metric string, "
        "which states it is not")
    assert "not resolvable" in row["metric"].lower(), (
        "consensus_fv's metric must say the Spearman leg is unresolved; the "
        "blend buys discrimination, not ordering")


def test_the_injury_history_row_retracts_its_coverage_starved_premise():
    """AUDIT F13. The lane was closed on `il_history` (2 of 845 hitter rows),
    but `player_transactions` is already parsed into `injury_history` for the
    live board and clears the row's own revival trigger of 100 pre-cutoff
    stints several times over. The verdict stays `deprecated` because nothing
    is served, not because the substrate is exhausted, and the row has to say
    which."""
    notes = _by_id()["xfv_injury_history"]["notes"]
    assert "coverage-starved" in notes, "the history is retained, not deleted"
    assert "CLOSURE PREMISE RETRACTED" in notes, (
        "the row still closes the lane as coverage-starved with no retraction; "
        "the revival trigger is met on player_transactions (audit F13)")
    assert "player_transactions" in notes and "injury_history" in notes
    assert "NO LIFT IS CLAIMED" in notes, (
        "the measured prospect-side signal is -0.90 WAR at permutation p 0.044 "
        "and confounded three ways; the row must not read as a lift")


def test_the_flagship_rows_lead_with_current_state_not_a_retired_win():
    """AUDIT F46. Both eFV rows opened with 2026-06 headline wins ("BEATS
    consensus", "lambda is None") against artifacts whose honest_note says
    every out-of-sample cut is a NULL under both estimators and whose lambdas
    have been pinned since 2026-08-04. The old paragraphs are retained as
    HISTORY, so what this pins is that a dated CURRENT STATE block leads and
    names each retired claim."""
    retired = {
        "xfv_hitter": ("0.341 vs 0.295", "every FV tier"),
        "xfv_pitcher": ("BEATING consensus on OOS rank", "['pit'] is None"),
    }
    for mid, claims in retired.items():
        notes = _by_id()[mid]["notes"]
        assert notes.startswith("CURRENT STATE 2026-09-04"), (
            f"{mid} leads with something other than its current state")
        marker = "\n\nHISTORY (2026-06 to 2026-08"
        assert marker in notes, f"{mid}: no HISTORY marker"
        head = notes[:notes.index(marker)]
        assert "honest_note" in head, (
            f"{mid}: the current-state block states no artifact key")
        assert "NULL UNDER BOTH ESTIMATORS" in head.upper(), (
            f"{mid}: the current state must say every cut is a null")
        for c in claims:
            assert c in notes, f"{mid}: history paragraph {c!r} was deleted"
        assert "RETIRED" in head, f"{mid}: nothing is marked retired"


def test_the_lambda_pin_the_flagship_rows_quote_is_the_one_in_the_code():
    """The corrected xfv_pitcher block asserts _BLEND_LAMBDA_RESELECT['pit'] is
    NOT None (it is 0.57). That is a statement about product code, so it is
    checked against the product code: unpin either side and the registry prose
    goes stale silently otherwise."""
    import re
    src = (ROOT / "efv_model.py").read_text(encoding="utf-8")
    line = next(ln for ln in src.splitlines()
                if ln.startswith("_BLEND_LAMBDA_RESELECT"))
    pins = dict(re.findall(r'"(hit|pit)":\s*([0-9.]+|None)', line))
    assert pins == {"hit": "0.70", "pit": "0.57"}, (
        f"the shipped blend-lambda pins are {pins}; the xfv_hitter and "
        "xfv_pitcher CURRENT STATE blocks quote hit 0.70 / pit 0.57 and the "
        "prose is now wrong")
    for mid in ("xfv_hitter", "xfv_pitcher"):
        assert "'hit': 0.70, 'pit': 0.57" in _by_id()[mid]["notes"]
