# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v5 group-driver pins (EFV5_GROUP_DRIVERS, docs/efv-v2/EFV_V5_BACKTEST.md).

1. The flag is off and the served fit checks it before any v5 fit.
2. The menu is derived from the atlas artifact by the documented rule: clean cells of the
   long-label families only, one column per (group, statistic), age at the timing head,
   the names the screening lab registers as wave 5, each named in the document.
3. fit_v5 at base_config() is fit_v2 bit for bit; only menu columns at their own side and
   head may be added; registration never widens the v3 menu.
4. The column: the as-of season steps back over 2020; the group test reads level, age
   band, role and the no-MLB-line condition; in-group values are centered within their
   read year and every other row is 0; reserved frames raise without the gate sha.
5. Gate compliance: no FV-cell grouping in the module, no dash characters, the document
   carries the rule's constants.

Nothing here reads a frame row or an outcome.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

import efv5_group_drivers as G
import efv_v2_model as H
import efv_v3 as V3
import efv_vintage_frame as F

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
import efv_screen_lab as LAB  # noqa: E402
import efv_v3_backtest as T3  # noqa: E402
from test_efv_v3 import WEIGHTS, _orders, _rows  # noqa: E402

SRC = ROOT / "efv5_group_drivers.py"
DOC = ROOT / G.BACKTEST_DOC
MENU_SIZE = 28


def _cell(**kw):
    c = {"metric": "k_pct_pit", "family": "box", "side": "pit", "level": "A",
         "age_band": "all", "group": "all", "label": "reach3", "frame": "clean",
         "incr": 0.05, "ci95": [0.02, 0.08], "q": 0.02, "n": 900, "players": 800,
         "status": "clean"}
    c.update(kw)
    return c


# ---------------------------------------------------------------------------
# 1. the flag
# ---------------------------------------------------------------------------

def test_the_flag_is_off():
    assert G.EFV_V5_ON is False
    src = (ROOT / "efv_v2_serve.py").read_text(encoding="utf-8")
    assert "if V5.EFV_V5_ON:" in src
    assert src.index("if V5.EFV_V5_ON:") < src.index("if V4.EFV_V4_ON:")


# ---------------------------------------------------------------------------
# 2. the menu
# ---------------------------------------------------------------------------

def test_metric_base():
    assert G.metric_base("k_pct_rel_pit") == "k_pct"
    assert G.metric_base("k_pct_pit") == "k_pct"
    assert G.metric_base("age_rel_level_hit") == "age"
    assert G.metric_base("bb_minus_k_rel_hit") == "bb_minus_k"
    assert G.metric_base("pbp_two_strike_contact_hit") == "pbp_two_strike_contact"
    assert G.metric_base("bf_per_g_rel_pit") == "bf_per_g"
    with pytest.raises(ValueError):
        G.metric_base("k_pct")


def test_menu_rule_on_a_synthetic_atlas():
    atlas = {"candidates": [
        _cell(),
        _cell(metric="k_pct_rel_pit", q=0.03, incr=0.06),            # same statistic, larger q
        _cell(metric="age_pit", q=0.05),                             # age: timing head
        _cell(metric="age_rel_level_pit", q=0.05),                   # the same column
        _cell(metric="bb_gb_pit", family="bb"),                      # no long label
        _cell(metric="trk_csw_pit", family="tracking"),              # no long label
        _cell(metric="era_pit", status="spent-overlap", frame="all"),  # spent cohorts
        _cell(metric="hr_pct_pit", q=0.11),                          # q above the rule
        _cell(metric="bb_pct_pit", ci95=[-0.01, 0.05]),              # CI95 spans 0
        _cell(metric="k_pct_pit", group="SP", q=0.04),               # its own group
        _cell(metric="pbp_contact_hit", family="pbp", side="hit", level="A+",
              age_band="young", label="reach5", q=0.08),
    ]}
    menu = G.menu_from_atlas(atlas)
    assert list(menu) == ["g5_pit_A_all_all_k_pct", "g5_pit_A_all_SP_k_pct",
                          "g5_pit_A_all_all_age", "g5_hit_Ap_young_all_pbp_contact"]
    assert menu["g5_pit_A_all_all_k_pct"]["metric"] == "k_pct_pit"
    assert menu["g5_pit_A_all_all_age"]["head"] == "timing"
    assert menu["g5_pit_A_all_all_age"]["metric"] == "age_pit"
    assert all(s["head"] == "skill" for n, s in menu.items() if not n.endswith("_age"))
    assert menu["g5_hit_Ap_young_all_pbp_contact"]["atlas"]["label"] == "reach5"
    with pytest.raises(NotImplementedError):
        G.menu_from_atlas({"candidates": [_cell(side="hit", metric="k_pct_hit", group="SS")]})


def test_the_menu_is_the_documented_28_columns():
    menu = G.menu_columns()
    assert len(menu) == MENU_SIZE
    assert tuple(menu) == LAB.WAVE5_MODULES["efv5_group_drivers"]
    assert LAB.wave5_columns() is menu
    text = DOC.read_text(encoding="utf-8")
    qs = [s["atlas"]["q"] for s in menu.values()]
    assert qs == sorted(qs)
    for name, spec in menu.items():
        assert f"`{name}`" in text, name
        assert spec["family"] in G.LONG_FAMILIES
        assert spec["atlas"]["q"] <= G.CANDIDATE_Q and spec["atlas"]["ci95"][0] > 0
        assert spec["head"] == ("timing" if spec["base"] == "age" else "skill")
        assert spec["key"] == f"{H.V2_SCREEN_PREFIX}{name}"
        assert spec["atlas"]["label"] in ("reach3", "reach5")


def test_registration_never_widens_the_v3_menu():
    before = len(T3.menu(V3.base_config()))
    assert before == 44
    with G.registered():
        assert all(n in V3.W2_COLUMNS for n in G.menu_columns())
        assert len(G.menu_steps(G.base_config())) == MENU_SIZE
    assert not any(n in V3.W2_COLUMNS for n in G.menu_columns())
    assert len(T3.menu(V3.base_config())) == before
    with pytest.raises(KeyError):
        with G.registered(["not_a_column"]):
            pass


# ---------------------------------------------------------------------------
# 3. base parity and the configuration space
# ---------------------------------------------------------------------------

def test_base_config_is_v2_bit_for_bit():
    train = _rows(years=range(2011, 2017), n=150)
    test_rows = _rows(years=[2017], seed=99)
    v2 = H.fit_v2(train, "hit", frame="lv", weights=WEIGHTS, absent_ok=False)
    v5 = G.fit_v5(train, "hit", frame="lv", weights=WEIGHTS, cfg=G.base_config(),
                  absent_ok=False)
    assert v5["model_id"] == G.MODEL_ID and v5["base_model_id"] == H.V2_ASSEMBLED_ID
    assert (v5["skill"] or {}).get("keys") == (v2["skill"] or {}).get("keys")
    assert (v5["timing"] or {}).get("keys") == (v2["timing"] or {}).get("keys")
    assert _orders(H.predict_v2(v2, test_rows)) == _orders(G.predict_v5(v5, test_rows))
    assert G.is_base(G.base_config()) and G.describe(G.base_config()).startswith("V2")


def test_only_menu_columns_may_be_added_at_their_own_head():
    name = "g5_pit_A_all_all_k_minus_bb"
    cfg = G.with_column(G.base_config(), name)
    assert cfg["add"]["pit"]["skill"] == [name] and G.added(cfg) == [name]
    step = next(s for s in G.menu_steps(G.base_config()) if s["column"] == name)
    assert G.apply_step(G.base_config(), step) == cfg
    assert all(s["column"] != name for s in G.menu_steps(cfg))
    age = G.with_column(G.base_config(), "g5_hit_A_all_all_age")
    assert age["add"]["hit"]["timing"] == ["g5_hit_A_all_all_age"]
    for side, head, col in (("hit", "skill", name), ("pit", "timing", name),
                            ("pit", "skill", "w2p_cstr_p"), ("hit", "skill", "g5_hit_A_all_all_age")):
        bad = G.base_config()
        bad["add"][side][head].append(col)
        with pytest.raises(ValueError):
            G.validate_config(bad)
    bad = G.base_config()
    bad["scale"]["hit"]["skill"] = 0.25
    with pytest.raises(ValueError):
        G.validate_config(bad)
    assert (T3.MIN_LV_GAIN, T3.VM_TOLERANCE, T3.MAX_STEPS) == (0.002, -0.002, 6)


def test_the_committed_spec_validates_when_present():
    if not G.SPEC_PATH.exists():
        pytest.skip("the selection has not run")
    spec = G.load_spec()
    cfg = G.spec_config(spec)
    assert spec["model_id"] == G.MODEL_ID and spec["selection_doc"] == G.BACKTEST_DOC
    assert spec["flag"].startswith("efv5_group_drivers.EFV_V5_ON")
    assert G.describe(cfg) == spec["description"]
    assert len(spec["steps"]) <= T3.MAX_STEPS
    assert set(spec["columns"]) == set(G.added(cfg))


# ---------------------------------------------------------------------------
# 4. the column
# ---------------------------------------------------------------------------

def test_read_season_steps_back_over_2020():
    assert G.read_season(2018, "2018-02-01") == 2017
    assert G.read_season(2021, "2021-03-01") == 2019
    assert G.read_season(2022, "2022-02-01") == 2021


class _Lines(G.Lines):
    """A Lines with hand-set tables (no cache read)."""

    def __init__(self, side="pit"):
        self.side = side
        self.metrics = ["k_pct_pit"]
        self.vals = {(1, 2017, "A"): {"k_pct_pit": 0.30}, (2, 2017, "A"): {"k_pct_pit": 0.20},
                     (3, 2017, "A"): {"k_pct_pit": None}, (4, 2017, "A"): {"k_pct_pit": 0.25},
                     (5, 2017, "A+"): {"k_pct_pit": 0.40}}
        self.band = {(1, 2017, "A"): "young", (2, 2017, "A"): "old",
                     (3, 2017, "A"): "young", (4, 2017, "A"): "young"}
        self.role = {(1, 2017, "A"): "SP", (2, 2017, "A"): "RP", (3, 2017, "A"): "SP",
                     (4, 2017, "A"): "SP"}
        self.norm = {(2017, "A", "k_pct_pit"): (0.25, 0.05)}
        self.mlb = {4: {2016}, 1: {2019}}


def test_member_reads_level_band_role_and_the_mlb_condition():
    ln = _Lines()
    spec = {"level": "A", "band": "young", "group": "SP", "metric": "k_pct_pit"}
    assert ln.member(1, 2017, spec) == (True, pytest.approx(1.0))   # MLB 2019 is after S
    assert ln.member(2, 2017, spec) == (False, None)                 # old, RP
    assert ln.member(3, 2017, spec) == (True, None)                  # in group, no value
    assert ln.member(4, 2017, spec) == (False, None)                 # MLB line before S
    assert ln.member(5, 2017, spec) == (False, None)                 # another level
    assert ln.member(None, 2017, spec) == (False, None)
    assert ln.member(2, 2017, dict(spec, band="all", group="all")) == (True, pytest.approx(-1.0))


def test_centered_is_the_metric_times_the_group_indicator():
    reads = {(2017, "a"): {"c": (True, 1.0)}, (2017, "b"): {"c": (True, 3.0)},
             (2017, "x"): {"c": (False, None)}, (2017, "m"): {"c": (True, None)},
             (2018, "d"): {"c": (True, 10.0)}, (2018, "y"): {"c": (False, None)}}
    vals, cnt = G.centered(reads, ["c"])
    assert vals["c"] == {(2017, "a"): -1.0, (2017, "b"): 1.0, (2017, "x"): 0.0,
                         (2017, "m"): 0.0, (2018, "d"): 0.0, (2018, "y"): 0.0}
    assert cnt["c"] == {2017: 3, 2018: 1}


def test_reserved_frames_raise_without_the_gate_sha(monkeypatch):
    monkeypatch.setitem(G._LINES, "pit", _Lines())
    names = ["g5_pit_A_all_all_k_pct"]
    for V in sorted(F.RESERVED_LV):
        with pytest.raises(F.ReservedFrameError):
            G.lv_columns("pit", {V: []}, names)
    rows = [{"player_key": "p1", "decision_year": F.R_VM_FIRST_DEBUT_YEAR}]
    with pytest.raises(F.ReservedFrameError):
        G.vm_columns("pit", rows, {}, names, gate_sha="not-a-sha")
    vals, _cnt = G.vm_columns("pit", rows, {}, names)
    assert vals[names[0]] == {}


# ---------------------------------------------------------------------------
# 5. gate compliance and copy
# ---------------------------------------------------------------------------

_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED = ("groupby", "tier", "bucket", "by_fv", "fv_band", "fv_bin", "stratum")


def test_no_fv_cell_grouping():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else
                node.attr if isinstance(node, ast.Attribute) else
                node.name if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else None)
        if name:
            assert not any(t in name.lower() for t in _BANNED), name
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)


@pytest.mark.parametrize("path", [SRC, DOC, Path(__file__)])
def test_no_dash_characters(path):
    t = path.read_text(encoding="utf-8")
    assert chr(0x2014) not in t and chr(0x2013) not in t


def test_the_document_carries_the_rule():
    t = DOC.read_text(encoding="utf-8")
    for s in ("+0.0020", "-0.0020", "6 steps", "28 columns", "efv5_group_spent.json", "R-LV",
              "R-VM", "E_refit", "B 200", "position-group", "PROSPECT_ANCHOR_GATE",
              "EFV_V5_ON = False", "spent frame, read after the 10-08 confirmation",
              "EW2-10", "EW3-1", "e7931ce4e13110eebb53555bff455ff13ca7c502"):
        assert s in t, s
