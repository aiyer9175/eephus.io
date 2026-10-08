# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v3 pins (EFV3_W3_SELECT_CONFIRM, docs/efv-v2/EFV_V3_BACKTEST.md).

1. The flag is off and the served fit does not read a v3 model.
2. fit_v3 at base_config() is fit_v2 bit for bit: the same order on every row, with and
   without the configuration's no-op entries; a weight factor re-weights the fitted
   parts without a refit; a removed driver leaves the candidate list.
3. The committed spec (when present) validates and names the backtest document.
4. The reserved guards: a 2025 year raises through _check_years and guard_vm_request
   without the committed gate sha and passes with one (scratch repository), and the
   R-VM pins stay empty.
5. Gate compliance: no FV-cell grouping in efv_v3.py or the backtest tool; no em-dash
   in either or in the backtest document; the document carries the rule's constants.

Nothing here reads a frame row or an outcome.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import efv_v2_model as H
import efv_v3 as V3
import efv_vintage_frame as F

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
import efv_v3_backtest as T  # noqa: E402

SRC = ROOT / "efv_v3.py"
TOOL = ROOT / "tools" / "efv_v3_backtest.py"
DOC = ROOT / V3.BACKTEST_DOC
WEIGHTS = {"hit": {"w_skill": 0.5, "w_time": 0.2}, "pit": {"w_skill": 0.5, "w_time": 0.2}}


# ---------------------------------------------------------------------------
# synthetic rows (test_efv_v2_candidates' shape)
# ---------------------------------------------------------------------------

def _feats(block=True, **kw):
    f = {"milb_unavailable": 0.0 if block else 1.0, "milb_missing": 0.0,
         "obp_rel": 0.0, "k_rel": 0.0, "peak_k_rel": 0.0, "level_rank": 0.0,
         "age_rel_level": 0.0, "tool_hit": 50.0, "tool_speed": 48.0,
         "is_college": 0.0, "is_ifa": 0.0, "pick_missing": 1.0}
    f.update(kw)
    return f


def _rows(side="hit", years=range(2011, 2020), n=150, seed=11, frame="lv"):
    rng = np.random.default_rng(seed)
    out, i = [], 0
    for yr in years:
        for _ in range(n):
            fv = float(rng.normal(45, 5))
            th = float(rng.normal(50, 8))
            ts = float(rng.normal(48, 6))
            kr = float(rng.normal(0, 0.05))
            drv = 0.08 * (th - 50) if side == "hit" else 20.0 * kr
            t = 0.1 * (fv - 45) + drv + float(rng.normal(0, 1))
            feats = _feats(True, tool_hit=th, tool_speed=ts, k_rel=kr, peak_k_rel=kr,
                           obp_rel=float(rng.normal(0, 0.03)),
                           level_rank=float(rng.integers(0, 6)),
                           age_rel_level=float(rng.normal(0, 1)))
            extra = {"bmi": float(rng.normal(25, 2)), "pl_rev": None,
                     "on_40man": float(rng.random() < 0.2),
                     "nov_add": float(rng.random() < 0.1)}
            g = {"fangraphs": fv + float(rng.normal(0, 3)),
                 "mlb_pipeline": fv + float(rng.normal(0, 2))}
            out.append({"player_key": f"{side}{i}", "decision_year": yr, "fv": fv,
                        "target": t, "reached": float(t > 0.5), "weight": 1.0,
                        "feats": feats, "extra": extra, "v2": H.v2_row(feats, extra),
                        "frame": frame, "ids_outcome_blind": frame == "lv", "grades": g})
            i += 1
    return out


@pytest.fixture(scope="module")
def train():
    return _rows(years=range(2011, 2017), n=150)


@pytest.fixture(scope="module")
def test_rows():
    return _rows(years=[2017], seed=99)


def _orders(pred):
    return [p["order_idx"] for p in pred]


# ---------------------------------------------------------------------------
# 1. the flag
# ---------------------------------------------------------------------------

def test_the_flag_is_off():
    assert V3.EFV_V3_ON is False
    src = (ROOT / "efv_v2_serve.py").read_text(encoding="utf-8")
    assert "if V3.EFV_V3_ON:" in src


# ---------------------------------------------------------------------------
# 2. base parity and the steps
# ---------------------------------------------------------------------------

def test_base_config_is_v2_bit_for_bit(train, test_rows):
    v2 = H.fit_v2(train, "hit", frame="lv", weights=WEIGHTS, absent_ok=False)
    v3 = V3.fit_v3(train, "hit", frame="lv", weights=WEIGHTS, cfg=V3.base_config(),
                   absent_ok=False)
    assert v3["model_id"] == V3.MODEL_ID and v3["base_model_id"] == H.V2_ASSEMBLED_ID
    assert (v3["skill"] or {}).get("keys") == (v2["skill"] or {}).get("keys")
    assert (v3["timing"] or {}).get("keys") == (v2["timing"] or {}).get("keys")
    assert v3["w_skill"] == v2["w_skill"] and v3["w_time"] == v2["w_time"]
    a = _orders(H.predict_v2(v2, test_rows))
    b = _orders(V3.predict_v3(v3, test_rows))
    assert a == b
    assert V3.is_base(V3.base_config()) and V3.describe(V3.base_config()).startswith("V2")


def test_a_weight_factor_reweights_the_parts_without_a_refit(train, test_rows):
    cfg = V3.base_config()
    cfg["scale"]["hit"]["skill"] = 0.25
    cfg["scale"]["hit"]["timing"] = 0.0
    m = V3.fit_v3(train, "hit", frame="lv", weights=WEIGHTS, cfg=cfg, absent_ok=False)
    assert m["w_skill"] == pytest.approx(0.25 * m["w_skill_unscaled"])
    assert m["w_time"] == 0.0
    parts = V3.parts_v3(m, test_rows)
    want = V3.order_index(parts, m["w_skill"], m["w_time"])
    got = np.asarray(_orders(V3.predict_v3(m, test_rows)))
    assert np.allclose(want, got)
    base = V3.fit_v3(train, "hit", frame="lv", weights=WEIGHTS, cfg=V3.base_config(),
                     absent_ok=False)
    parts0 = V3.parts_v3(base, test_rows)
    assert np.allclose(parts0["e_skill"], parts["e_skill"])
    assert np.allclose(parts0["u"], parts["u"])


def test_a_removed_driver_leaves_the_candidate_list(train):
    cfg = V3.base_config()
    cfg["remove"]["hit"]["skill"].append("tool_hit")
    m = V3.fit_v3(train, "hit", frame="lv", weights=WEIGHTS, cfg=cfg, absent_ok=False)
    cands = (m["skill"] or {}).get("candidates") or []
    assert "tool_hit" not in cands and "tool_hit" not in ((m["skill"] or {}).get("keys") or [])
    with pytest.raises(ValueError):
        bad = V3.base_config()
        bad["remove"]["hit"]["skill"].append("not_a_driver")
        V3.validate_config(bad)
    with pytest.raises(ValueError):
        bad = V3.base_config()
        bad["add"]["pit"]["skill"].append("w2m_k_hit")
        V3.validate_config(bad)
    with pytest.raises(ValueError):
        bad = V3.base_config()
        bad["scale"]["hit"]["skill"] = 0.7
        V3.validate_config(bad)


def test_an_anchor_configuration_needs_its_anchor_values(train, test_rows):
    cfg = V3.base_config()
    cfg["anchor"] = "an1_pl"
    with pytest.raises(ValueError):
        V3.fit_v3(train, "hit", frame="lv", weights=WEIGHTS, cfg=cfg, absent_ok=False)
    u = np.linspace(0.0, 1.0, len(train))
    m = V3.fit_v3(train, "hit", frame="lv", weights=WEIGHTS, cfg=cfg, u_train=u,
                  absent_ok=False)
    assert (m["skill"] or {}).get("anchor") is True
    with pytest.raises(ValueError):
        V3.predict_v3(m, test_rows)
    out = V3.predict_v3(m, test_rows, u_rows=np.linspace(0.0, 1.0, len(test_rows)))
    assert len(out) == len(test_rows)


def test_the_menu_is_the_documented_44_steps():
    steps = T.menu(V3.base_config())
    assert len(steps) == 44
    kinds = [s["kind"] for s in steps]
    assert kinds == sorted(kinds, key=["anchor", "scale", "remove", "add"].index)
    cfg = T.apply_step(V3.base_config(), steps[0])
    assert cfg["anchor"] == "an1_rel"
    assert all(s["kind"] != "anchor" for s in T.menu(cfg))
    assert len(T.menu(cfg)) == 41
    assert (T.MIN_LV_GAIN, T.VM_TOLERANCE, T.MAX_STEPS) == (0.002, -0.002, 6)


# ---------------------------------------------------------------------------
# 3. the committed spec
# ---------------------------------------------------------------------------

def test_the_committed_spec_validates_when_present():
    if not V3.SPEC_PATH.exists():
        pytest.skip("data/efv_v3_spec.json not written yet (the selection has not run)")
    spec = V3.load_spec()
    cfg = V3.spec_config(spec)
    assert spec["model_id"] == V3.MODEL_ID and spec["selection_doc"] == V3.BACKTEST_DOC
    assert spec["flag"].startswith("efv_v3.EFV_V3_ON")
    assert V3.describe(cfg) == spec["description"]
    assert len(spec["steps"]) <= T.MAX_STEPS


# ---------------------------------------------------------------------------
# 4. the reserved guards
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_a_reserved_year_opens_on_the_committed_gate_sha_only(tmp_path, monkeypatch):
    with pytest.raises(F.ReservedFrameError):
        H._check_years([2024, F.R_VM_FIRST_DEBUT_YEAR])
    with pytest.raises(F.ReservedFrameError):
        F.guard_vm_request([F.R_VM_FIRST_DEBUT_YEAR])
    F.guard_vm_request([2017, 2023])
    assert H._check_years([2017], gate_sha="not a sha") == [2017]
    with pytest.raises(F.ReservedFrameError):
        H._check_years([F.R_VM_FIRST_DEBUT_YEAR], gate_sha="not a sha")
    repo = tmp_path / "repo"
    (repo / "docs" / "efv-v2").mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    doc = repo / F.GATE_DOC
    doc.write_text("# gate\n\nRegistration status: DRAFT\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "draft")
    draft = _git(repo, "rev-parse", "HEAD")
    doc.write_text(f"# gate\n\n{F.GATE_STATUS_REGISTERED}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "registered")
    final = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(F, "ROOT", repo)
    with pytest.raises(F.ReservedFrameError):
        F.guard_vm_request([F.R_VM_FIRST_DEBUT_YEAR], gate_sha=draft)
    with pytest.raises(F.ReservedFrameError):
        H._check_years([F.R_VM_FIRST_DEBUT_YEAR], gate_sha=draft)
    F.guard_vm_request([F.R_VM_FIRST_DEBUT_YEAR], gate_sha=final)
    assert H._check_years([F.R_VM_FIRST_DEBUT_YEAR], gate_sha=final) == [F.R_VM_FIRST_DEBUT_YEAR]
    assert F.reserved_vm_pins() == []


def test_the_committed_gate_sha_is_memoized_per_root(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "ROOT", tmp_path)
    F._GATE_SHA_MEMO.clear()
    sha = "0" * 40
    assert F.gate_sha_committed(sha) is False
    assert (str(tmp_path), sha) in F._GATE_SHA_MEMO
    F._GATE_SHA_MEMO.clear()


# ---------------------------------------------------------------------------
# 5. gate compliance and copy
# ---------------------------------------------------------------------------

_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED = ("groupby", "tier", "bucket", "by_fv", "fv_band", "fv_bin", "stratum")


@pytest.mark.parametrize("path", [SRC, TOOL])
def test_no_fv_cell_grouping(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else
                node.attr if isinstance(node, ast.Attribute) else
                node.name if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else None)
        if name:
            assert not any(t in name.lower() for t in _BANNED), (path.name, name)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (path.name, node.value, node.lineno)


@pytest.mark.parametrize("path", [SRC, TOOL, DOC])
def test_no_dash_characters(path):
    t = path.read_text(encoding="utf-8")
    assert chr(0x2014) not in t and chr(0x2013) not in t


def test_the_document_carries_the_rule():
    t = DOC.read_text(encoding="utf-8")
    for s in ("+0.0020", "-0.0020", "6 steps", "44 steps", "an1_rel", "an2_pos",
              "lv_res", "vm_pros", "E_refit", "B 200", "position-group",
              "PROSPECT_ANCHOR_GATE", "EFV_V3_ON = False"):
        assert s in t, s
    for name in V3.W2_COLUMNS:
        assert name in t, name


def test_cells_are_position_groups_never_fv():
    assert T.CELLS == (("hit", "C"), ("hit", "IF"), ("hit", "OF"), ("pit", "pit"))
    for k in V3.W2_COLUMNS.values():
        assert k["key"].startswith(H.V2_SCREEN_PREFIX)
    assert json.dumps(V3.base_config())
