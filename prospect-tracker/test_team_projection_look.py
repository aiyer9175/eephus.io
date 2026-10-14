"""The team gate's GATE look runner (tools/team_projection_look.py): its dry
run scores fixtures with nulls end to end and writes nothing under data/,
and the look refuses a changed freeze, a spent look and an unpinned hash seed
(docs/TEAM_PROJECTIONS_GATE.md sections 4.1 and 4.3)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


look = _load("team_projection_look")
reg_look = _load("register_team_look")


def test_dry_run_scores_fixtures_with_nulls_and_writes_nothing_under_data(tmp_path):
    eval_path = ROOT / "data" / "team_outlook_eval.json"
    before = eval_path.read_bytes() if eval_path.exists() else None
    assert look.run(tmp_path, dry_run=True, write=True, n_sims=50, B=100) == 0
    after = eval_path.read_bytes() if eval_path.exists() else None
    assert before == after, "the dry run never touches data/"
    block = json.loads((tmp_path / "dry_run_block.json").read_text(encoding="utf-8"))
    assert block["dry_run"] is True and block["season"] == 2025 and block["frame"] == "DEV"
    # BAL has actuals but no frame rows (no samples, no projected runs); BOS has no actual RS;
    # each is named on the side it is missing from, never imputed
    assert "BAL" in block["tm_a"]["missing"]
    assert block["tm_c"]["rs"]["missing"] == ["BAL", "BOS"] and block["tm_c"]["ra"]["missing"] == ["BAL"]
    assert block["tm_a"]["bootstrap"]["n"] == 3 and block["tm_b"]["bootstrap"]["n"] == 3
    assert block["bootstrap"] == {"B": 100, "seed": look.SEED_LOOK}
    for v in (block["verdicts"]["TM-A"], block["verdicts"]["TM-B"], *block["verdicts"]["TM-C"].values()):
        assert v in ("PASS", "FAIL", "NULL")
    entry = (tmp_path / "dry_run_entry.md").read_text(encoding="utf-8")
    assert entry.startswith("### 2026-") and "**Clubs scored nowhere" in entry
    assert "—" not in entry and "–" not in entry
    # the registry note builders read every number from the block and cap the summary
    for row_id, fields in reg_look.plan(block):
        assert fields["marker"].startswith("LOOK ")
        if "summary" in fields:
            assert len(fields["summary"].split()) <= 30, fields["summary"]
        assert "—" not in fields["note"] and "–" not in fields["note"]


def test_verdict_words_follow_the_registered_rule():
    assert look._verdict({"pass": True}) == "PASS"
    assert look._verdict({"pass": False}) == "FAIL"
    assert look._verdict({"pass": None}) == "NULL" and look._verdict(None) == "NULL"


def test_refuses_when_the_frozen_params_do_not_hash_to_the_record(monkeypatch):
    monkeypatch.setattr(look, "recorded_params_sha", lambda *a, **k: "0" * 64)
    with pytest.raises(look.LookRefused, match="changed after freezing"):
        look.check_preconditions(dry_run=True)


def test_refuses_a_second_look(monkeypatch):
    import proj_backtest as pb
    monkeypatch.setattr(pb, "_gate_already_read", lambda *a, **k: True)
    with pytest.raises(look.LookRefused, match="runs once"):
        look.check_preconditions(dry_run=False)


def test_main_refuses_the_look_without_the_pinned_hash_seed(monkeypatch, tmp_path):
    monkeypatch.delenv("PYTHONHASHSEED", raising=False)
    assert look.main(["--out", str(tmp_path)]) == 2
    assert not (tmp_path / "gate_2026_block.json").exists()


def test_the_gate_record_has_exactly_one_freeze_entry():
    import team_projection as TP
    assert look.recorded_params_sha() == TP.params_hash(TP.load_params())
