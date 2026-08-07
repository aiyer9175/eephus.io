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
        assert f["age_source"] in ("artifact", "mtime"), mid


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
    "data/fa_gate2_eval.json",
    "data/proj_def_feature_eval.json",
    "data/proj_horizon_eval.json",
    "data/prospect_def_value_eval.json",
    "data/surplus_sensitivity.json",
    "data/total_band_eval.json",
    "data/trade_machine_eval.json",
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
