# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v4 pins (EFV4_SELECT_SHIP, docs/efv-v2/EFV_V4_BACKTEST.md).

1. The flag is off and the served fit does not read a v4 model.
2. The menu is derived from the registered development artifacts: the 40 documented
   columns, each named in the document at its registered head; registration adds them to
   efv_v3's column table for the life of a block only, so the v3 menu stays 44 steps.
3. fit_v4 at base_config() is fit_v2 bit for bit; a configuration may only ADD a menu
   column at its own side and head (no anchor, factor or removal).
4. The committed spec (when present) validates and names the backtest document.
5. Gate compliance: no FV-cell grouping in efv_v4.py or the backtest tool; no em-dash in
   either or in the document; the document carries the rule's constants.

Nothing here reads a frame row or an outcome.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

import efv_v2_model as H
import efv_v3 as V3
import efv_v4 as V4

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
import efv_v3_backtest as T3  # noqa: E402
import efv_v4_backtest as T  # noqa: E402
from test_efv_v3 import WEIGHTS, _orders, _rows  # noqa: E402

SRC = ROOT / "efv_v4.py"
TOOL = ROOT / "tools" / "efv_v4_backtest.py"
DOC = ROOT / V4.BACKTEST_DOC
MENU_SIZE = 40


@pytest.fixture(scope="module")
def train():
    return _rows(years=range(2011, 2017), n=150)


@pytest.fixture(scope="module")
def test_rows():
    return _rows(years=[2017], seed=99)


# ---------------------------------------------------------------------------
# 1. the flag
# ---------------------------------------------------------------------------

def test_the_flag_is_off():
    assert V4.EFV_V4_ON is False
    src = (ROOT / "efv_v2_serve.py").read_text(encoding="utf-8")
    assert "if V4.EFV_V4_ON:" in src


# ---------------------------------------------------------------------------
# 2. the menu and the registration
# ---------------------------------------------------------------------------

def test_the_menu_is_the_documented_40_columns():
    menu = V4.menu_columns()
    assert len(menu) == MENU_SIZE
    text = DOC.read_text(encoding="utf-8")
    fams = [s["family"] for s in menu.values()]
    assert fams == sorted(fams, key=[f["family"] for f in V4.FAMILIES].index)
    for name, spec in menu.items():
        assert name in text, name
        assert spec["side"] in ("hit", "pit") and spec["head"] in V4.HEADS
        assert spec["key"] == f"{H.V2_SCREEN_PREFIX}{name}"
        adm = spec["admitted"]
        assert any(adm[fid] and int(adm[fid].split("/")[0]) > 0 for fid in ("lv_dev", "vm_dev"))
        if spec["family"] == "report" and spec["side"] == "hit":
            assert spec["head"] == "timing"
    for name in ("w2b_park_obp_hit", "rpt_role_ceiling_hit", "rpt_role_ceiling_pit",
                 "w2p_swstr_p", "w2b_ld_h"):
        assert name not in menu


def test_registration_never_widens_the_v3_menu():
    before = len(T3.menu(V3.base_config()))
    assert before == 44
    with V4.registered():
        assert all(n in V3.W2_COLUMNS for n in V4.menu_columns())
        assert len(T.menu(V4.base_config())) == MENU_SIZE
        with V4.registered(["w2p_cstr_p"]):
            pass
        assert "w2p_cstr_p" in V3.W2_COLUMNS
    assert not any(n in V3.W2_COLUMNS for n in V4.menu_columns())
    assert len(T3.menu(V3.base_config())) == before
    with pytest.raises(KeyError):
        with V4.registered(["not_a_column"]):
            pass


# ---------------------------------------------------------------------------
# 3. base parity and the configuration space
# ---------------------------------------------------------------------------

def test_base_config_is_v2_bit_for_bit(train, test_rows):
    v2 = H.fit_v2(train, "hit", frame="lv", weights=WEIGHTS, absent_ok=False)
    v4 = V4.fit_v4(train, "hit", frame="lv", weights=WEIGHTS, cfg=V4.base_config(),
                   absent_ok=False)
    assert v4["model_id"] == V4.MODEL_ID and v4["base_model_id"] == H.V2_ASSEMBLED_ID
    assert (v4["skill"] or {}).get("keys") == (v2["skill"] or {}).get("keys")
    assert (v4["timing"] or {}).get("keys") == (v2["timing"] or {}).get("keys")
    assert v4["w_skill"] == v2["w_skill"] and v4["w_time"] == v2["w_time"]
    assert _orders(H.predict_v2(v2, test_rows)) == _orders(V4.predict_v4(v4, test_rows))
    assert V4.is_base(V4.base_config()) and V4.describe(V4.base_config()).startswith("V2")


def test_only_menu_columns_may_be_added_at_their_own_head():
    cfg = V4.with_column(V4.base_config(), "w2p_cstr_p")
    assert cfg["add"]["pit"]["skill"] == ["w2p_cstr_p"] and V4.added(cfg) == ["w2p_cstr_p"]
    assert V4.describe(cfg) == "pit skill plus w2p_cstr_p"
    step = next(s for s in T.menu(V4.base_config()) if s["column"] == "w2p_cstr_p")
    assert T.apply_step(V4.base_config(), step) == cfg
    assert all(s["column"] != "w2p_cstr_p" for s in T.menu(cfg))
    with pytest.raises(ValueError):
        bad = V4.base_config()
        bad["add"]["hit"]["skill"].append("w2p_cstr_p")
        V4.validate_config(bad)
    with pytest.raises(ValueError):
        bad = V4.base_config()
        bad["add"]["pit"]["timing"].append("w2p_cstr_p")
        V4.validate_config(bad)
    with pytest.raises(ValueError):
        bad = V4.base_config()
        bad["add"]["pit"]["skill"].append("w2s_cmd_pit")
        V4.validate_config(bad)
    with pytest.raises(ValueError):
        bad = V4.base_config()
        bad["anchor"] = "an1_rel"
        V4.validate_config(bad)
    with pytest.raises(ValueError):
        bad = V4.base_config()
        bad["scale"]["hit"]["skill"] = 0.25
        V4.validate_config(bad)
    with pytest.raises(ValueError):
        bad = V4.base_config()
        bad["remove"]["pit"]["skill"].append("k_rel")
        V4.validate_config(bad)
    assert (T.MIN_LV_GAIN, T.VM_TOLERANCE, T.MAX_STEPS) == (0.002, -0.002, 6)


# ---------------------------------------------------------------------------
# 4. the committed spec
# ---------------------------------------------------------------------------

def test_the_committed_spec_validates_when_present():
    if not V4.SPEC_PATH.exists():
        pytest.skip("data/efv_v4_spec.json not written yet (the selection has not run)")
    spec = V4.load_spec()
    cfg = V4.spec_config(spec)
    assert spec["model_id"] == V4.MODEL_ID and spec["selection_doc"] == V4.BACKTEST_DOC
    assert spec["flag"].startswith("efv_v4.EFV_V4_ON")
    assert V4.describe(cfg) == spec["description"]
    assert len(spec["steps"]) <= T.MAX_STEPS
    assert set(spec["columns"]) == set(V4.added(cfg))
    assert spec["is_v2"] == V4.is_base(cfg)


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
    for s in ("+0.0020", "-0.0020", "6 steps", "40 columns", "efv_v4_spent.json", "R-LV", "R-VM",
              "E_refit", "B 200", "position-group", "PROSPECT_ANCHOR_GATE",
              "EFV_V4_ON = False", "spent frame, read after the 10-08 confirmation",
              "EW2-10", "e7931ce4e13110eebb53555bff455ff13ca7c502"):
        assert s in t, s


def test_cells_are_position_groups_never_fv():
    assert T.CELLS == (("hit", "C"), ("hit", "IF"), ("hit", "OF"), ("pit", "pit"))
    assert T.COMPARISONS[0] == ("v4_vs_efv_v2", T.CAND_KEY, T.V2_KEY)
    assert json.dumps(V4.base_config())
