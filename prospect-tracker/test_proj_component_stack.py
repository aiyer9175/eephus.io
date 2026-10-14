# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""W2, the component stack twin (tools/proj_component_stack.py, task
PJ_9_STACK_ARM_DARK, docs/PROJ_COMPONENTS_GATE.md section 6).

Three invariants: the stack schema is the serving schema plus the named
columns in order, so a serving feature never moves; the twin is never on the
served path (a source scan of every served module and a monkeypatched loader
that would raise if anything called it); and the veto block lands in
data/proj_horizon_eval.json by read-modify-write without touching another
key. Every score here runs on fixtures; no real row is read."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import proj_ml                                # noqa: E402
import proj_component_stack as S              # noqa: E402

SERVED_MODULES = ("fa_market.py", "fa_projection.py", "proj_export.py", "fa_export.py",
                  "build_site.py", "tools/export_trade_values.py", "proj_eval.py",
                  "fa_class.py", "run_monthly.py")


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def test_stack_schema_extends_serving_schema_in_order():
    for side in ("hit", "pit"):
        serving = proj_ml.feature_names(side)
        names = S.stack_feature_names(side)
        assert names[:len(serving)] == serving, "the serving columns keep their positions"
        assert names[len(serving):] == S.STACK_EXTRA[side]
        assert len(set(names)) == len(names), "no duplicate column"
    assert S.STACK_EXTRA["hit"] == ["bsr_rate_proj", "fld_rate_proj", "pos_rate_proj",
                                    "sprint_l1", "sprint_missing"]
    assert S.STACK_EXTRA["pit"] == ["gmli_proj", "ra9_gap_proj"]
    # the star-slice flag the predict path gates on sits where proj_ml put it
    assert S.stack_feature_names("hit")[proj_ml._STAR_FLAG_IDX] == "star_l1"
    assert S.schema_tag() != proj_ml._SCHEMA_TAG, "the twin's caches never collide with proj_ml's"


def test_stack_columns_from_a_line_and_nan_when_not_projected():
    line = {"pa": 600.0, "bsr600": 1.5, "fld": -3.0, "pos": 6.0}
    hit = S.hitter_stack(line, {"sprint_speed_l1": 28.1})
    assert hit == [1.5, -3.0, 6.0, 28.1, 0.0]
    hit = S.hitter_stack(None, {"sprint_speed_l1": None})
    assert all(math.isnan(v) for v in hit[:4]) and hit[4] == 1.0
    hit = S.hitter_stack({"pa": 0.0, "bsr600": None, "fld": 1.0, "pos": 1.0}, {})
    assert all(math.isnan(v) for v in hit[:4]) and hit[4] == 1.0
    assert S.pitcher_stack({"gmli": 1.2, "ra9gap_100ip": -0.4}, {}) == [1.2, -0.4]
    pit = S.pitcher_stack({"gmli": None, "ra9gap_100ip": 0.1}, {})
    assert math.isnan(pit[0]) and pit[1] == 0.1
    assert all(math.isnan(v) for v in S.pitcher_stack(None, {}))


# --------------------------------------------------------------------------
# Never served
# --------------------------------------------------------------------------

def test_served_path_never_names_the_twin():
    pat = re.compile(r"proj_component_stack|proj_lgbm_components|load_twin")
    for rel in SERVED_MODULES:
        p = ROOT / rel
        if not p.exists():
            continue
        assert not pat.search(p.read_text(encoding="utf-8", errors="replace")), \
            f"{rel} names the twin"
    assert S.BUNDLE_DIR != proj_ml.MODEL_DIR
    assert "proj_lgbm_components" not in str(proj_ml.MODEL_DIR)


def test_monkeypatched_twin_loader_is_never_called_by_the_served_path(monkeypatch):
    """fa_market's ML dispatch loads the live bundle through proj_ml.load()
    with no path; the twin's loader is replaced by one that raises, and the
    live loader records what it was asked for."""
    import fa_market as fm

    def boom(*a, **k):
        raise AssertionError("the served path called the twin loader")
    monkeypatch.setattr(S, "load_twin", boom)
    asked = []

    def fake_load(path=None):
        asked.append(path)
        return None                      # no bundle: champion fallback
    monkeypatch.setattr(proj_ml, "load", fake_load)
    monkeypatch.setattr(fm.fa_class, "get_config",
                        lambda: {"projection": {"ml": {"enabled": True}}})
    assert fm._ml_active() is False
    assert asked and all(p is None for p in asked), "the live loader is asked for the live bundle only"
    # the twin's own loader returns None without a bundle on disk
    monkeypatch.undo()
    assert S.load_twin(Path("C:/no/such/dir")) is None


# --------------------------------------------------------------------------
# The veto block
# --------------------------------------------------------------------------

def test_score_pairs_drops_nulls_and_is_seeded():
    pairs = S.fixture_pairs()
    a = S.score_pairs(pairs, B=50)
    b = S.score_pairs(pairs, B=50)
    assert a == b, "the same seed gives the same draws"
    assert a["n_rows"] == 40 and a["n_players"] == 40, "None and NaN pairs are not scored"
    # hand check of the point statistic
    rows = [p for p in pairs if all(p[k] is not None and math.isfinite(p[k])
                                    for k in ("twin", "incumbent", "actual"))]
    delta = sum(abs(p["twin"] - p["actual"]) - abs(p["incumbent"] - p["actual"]) for p in rows) / len(rows)
    assert a["delta"] == round(delta, 4)
    assert a["ub95"] == round(a["delta"] + S.Z_ONE_SIDED_95 * a["sd"], 4)
    assert a["sd"] > 0 and a["mde95"] > 0
    assert S.score_pairs([], B=10)["n_rows"] == 0


def test_veto_verdict_at_the_bar():
    assert S.veto_verdict({"ub95": 0.0065})["vetoed"] is True
    assert S.veto_verdict({"ub95": 0.0064})["vetoed"] is False
    assert S.veto_verdict({"ub95": -0.2})["vetoed"] is False
    v = S.veto_verdict({"ub95": None})
    assert v["vetoed"] is False and "NOT COMPUTABLE" in v["verdict"]
    for ub in (0.5, -0.5, None):
        assert "PASS" not in S.veto_verdict({"ub95": ub})["verdict"], "a veto read never passes"


def test_write_veto_block_keeps_every_other_key_and_line_endings(tmp_path):
    art = tmp_path / "proj_horizon_eval.json"
    doc = {"model": "marcel_decay_v2", "bases": [2015], "generated_at": "2026-01-01T00:00:00Z",
           "challenger_blocks": {"holdout_2022_2024": {"keep": True}, "dev": {"n": 3}},
           "rowmatch_champion_vs_challenger": {"h": 1}, "unrelated_key": "keep me"}
    art.write_bytes(json.dumps(doc, indent=1).replace("\n", "\r\n").encode("utf-8"))
    block = S.veto_block(S.fixture_pairs(), B=20)
    S.write_veto_block(block, art)
    raw = art.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    out = json.loads(raw.decode("utf-8"))
    for k, v in doc.items():
        if k != "challenger_blocks":
            assert out[k] == v, f"{k} moved"
    cb = out["challenger_blocks"]
    assert cb["holdout_2022_2024"] == {"keep": True} and cb["dev"] == {"n": 3}
    assert cb[S.VETO_KEY]["label"] == "READ"
    assert cb[S.VETO_KEY]["never_cited_for_a_pass"] is True
    assert set(cb) == {"holdout_2022_2024", "dev", S.VETO_KEY}
    # idempotent: writing again changes nothing but the block
    S.write_veto_block(block, art)
    assert json.loads(art.read_text(encoding="utf-8")) == out
    # an LF artifact stays LF
    lf = tmp_path / "lf.json"
    lf.write_bytes(json.dumps({"a": 1}, indent=1).encode())
    S.write_veto_block(block, lf)
    assert b"\r\n" not in lf.read_bytes()
    assert json.loads(lf.read_text())["a"] == 1


def test_accountability_block_reads_no_new_key():
    src = (ROOT / "proj_export.py").read_text(encoding="utf-8", errors="replace")
    assert S.VETO_KEY not in src
    assert "component_stack" not in src


def test_dry_run_writes_under_out_only(tmp_path):
    out = tmp_path / "dry"
    block = S.dry_run(out)
    assert block["dry_run"] is True and block["label"] == "READ"
    assert (out / "dry_run.txt").exists() and (out / "proj_horizon_eval.dryrun.json").exists()
    text = S.format_block(block)
    assert "n/a" in text, "the star slice is empty on the fixtures and prints n/a"
    assert "pooled" in text
    assert S.main(["--dry-run", "--out", str(tmp_path / "cli")]) == 0
    assert (tmp_path / "cli" / "dry_run.txt").exists()


def test_final_refuses_without_a_read_and_when_vetoed(monkeypatch, tmp_path):
    art = tmp_path / "proj_horizon_eval.json"
    monkeypatch.setattr(S, "ARTIFACT", art)
    monkeypatch.setattr(S, "train_twin", lambda *a, **k: pytest.fail("trained without a read"))
    assert S.main(["--final"]) == 2
    art.write_text(json.dumps({"challenger_blocks": {S.VETO_KEY: {"vetoed": True}}}), encoding="utf-8")
    assert S.main(["--final"]) == 3
    assert S.recorded_veto(art)["vetoed"] is True
    assert S.recorded_veto(tmp_path / "missing.json") is None


def test_veto_read_runs_once(monkeypatch, tmp_path):
    art = tmp_path / "proj_horizon_eval.json"
    art.write_text(json.dumps({"challenger_blocks": {S.VETO_KEY: {"vetoed": False}}}), encoding="utf-8")
    monkeypatch.setattr(S, "ARTIFACT", art)
    monkeypatch.setattr(S, "run_veto_read", lambda *a, **k: pytest.fail("reran a recorded read"))
    assert S.main(["--veto-read"]) == 2


def test_registered_constants():
    assert S.VETO_BASES == (2022, 2023, 2024, 2025)
    assert S.VETO_SEED == 20261119 and S.VETO_B == 1000 and S.VETO_VIF == 1.8
    assert S.VETO_BAR == 0.0065
    assert S.FROZEN_PARAMS_SHA256 == "da2d5114fe2c05a1cceed883a625ddb63060e45c8fc848c385860694b02cf9b6"
