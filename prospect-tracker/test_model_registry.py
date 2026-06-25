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
    enforcement."""
    reg = mr.load()
    referenced = {m["eval_artifact"] for m in reg["models"] if m.get("eval_artifact")}
    on_disk = {f"data/{p.name}" for p in (ROOT / "data").glob("*_eval.json")}
    on_disk |= {f"data/{p.name}" for p in (ROOT / "data").glob("*gate*_eval.json")}
    unregistered = on_disk - referenced
    # gate artifacts referenced under their canonical names still count
    unregistered = {u for u in unregistered
                    if u not in referenced}
    assert not unregistered, (
        f"eval artifacts with NO registry row (register them in "
        f"data/model_registry.json): {sorted(unregistered)}")


def test_freshness_stamps():
    fresh = mr.freshness()
    assert fresh, "no freshness stamps computed"
    for mid, f in fresh.items():
        assert f["artifact_age_days"] >= 0, mid
        assert isinstance(f["stale"], bool), mid


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
