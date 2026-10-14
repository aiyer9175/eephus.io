# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""TL_11_STATLINE_BUILD_DARK: the guards of docs/proj-prospect-2026-10/
PROSPECT_STATLINE_GATE.md on prospect_statline.py: the holdout guard (1.6), the
R-VM guard (3.3), the FV-cell source scan (Part 7), the forbidden-artifact scan
(0.2, 0.3, Part 11), no quantile summing into WAR (1.4), the nested penalty and
bands on synthetic rows, and the dry run on fixtures with None values."""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import numpy as np
import pytest

import prospect_statline as PS

ROOT = Path(__file__).resolve().parent
SRC = (ROOT / "prospect_statline.py").read_text(encoding="utf-8")

#: Gate Part 7's scan (test_efv_vintage_frame.test_no_fv_cell_grouping, adapted).
_BANNED_TOKENS = ("by_fv", "fv_band", "fv_bin", "fv_cell", "fv_tier", "fv_bucket", "groupby")
_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
#: Gate 0.2 (b), 0.3 and Part 11: artifacts of the looks P, T and W, the served
#: milb_translation and efv_proxy fits, the tool grade tables, the live saber
#: cache and an eWAR label; none may be read or named by the module.
_FORBIDDEN = ("power_composite_eval", "tool_tables_rederived_eval", "tool_accuracy_eval",
              "tool_grade_tables", "xfv_proxy_eval", "milb_translation.json",
              "statsapi_saber", "ewar_v2", "ewar_merged", "ewar_v3", "bwar")


def _names(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            yield node.name
        elif isinstance(node, ast.arg):
            yield node.arg


# --- the frames ----------------------------------------------------------------

def test_frame_constants_as_registered():
    assert PS.DEV_COHORTS == (2017, 2018, 2019, 2020, 2021)
    assert PS.DEV_TEST_YEARS == (2019, 2020, 2021)
    assert PS.HOLDOUT_COHORTS == (2022, 2023, 2024)
    assert PS.HOLDOUT_FIRST_DEBUT_YEAR == 2022
    assert PS.EXPOSURE_FLOOR == 150.0
    assert PS.BOOT_B == 2000 and PS.BOOT_SEED == 20261210
    assert len(PS.PENALTY_GRID) == 13
    assert PS.PENALTY_GRID[0] == pytest.approx(1e-3) and PS.PENALTY_GRID[-1] == pytest.approx(1e3)
    assert PS.COVERAGE_BAND == (0.75, 0.85)
    assert PS.STRATA == ("side", "debut_age_band", "position_group", "last_level")
    assert PS.HIT_STATS == ("k_pct", "bb_pct", "iso", "avg", "babip", "woba", "xwoba")
    assert PS.PIT_STATS == ("k_pct", "bb_pct", "hr_bf", "babip", "xwoba")


@pytest.mark.parametrize("years", [(2025,), (2017, 2026), (2021, 2022, 2025)])
@pytest.mark.parametrize("mode", ["dev", "look", "preview"])
def test_rvm_raises_in_every_mode(years, mode):
    with pytest.raises(PS.ReservedFrameError):
        PS.guard_years(years, mode=mode)


@pytest.mark.parametrize("years", [(2022,), (2017, 2023), (2021, 2024)])
def test_holdout_raises_outside_the_look(years):
    for mode in ("dev", "preview"):
        with pytest.raises(PS.HoldoutFrameError):
            PS.guard_years(years, mode=mode)
    PS.guard_years(years, mode="look")          # the look alone may name them


def test_guards_run_before_any_read(monkeypatch):
    """A holdout or R-VM year raises before debuts.json, the caches or the
    vintage are opened."""
    def boom(*_a, **_k):
        raise AssertionError("a read happened before the guard")
    monkeypatch.setattr(PS, "season_lines", boom)
    monkeypatch.setattr(PS, "savant_expected", boom)
    monkeypatch.setattr(PS, "realized_line", boom)
    monkeypatch.setattr(PS, "input_hashes", boom)
    with pytest.raises(PS.HoldoutFrameError):
        PS.build_profiles((2017, 2022), mode="dev")
    with pytest.raises(PS.ReservedFrameError):
        PS.build_profiles((2017, 2025), mode="dev")
    with pytest.raises(PS.ReservedFrameError):
        PS.run_frame((2016, 2025), (2025,), mode="look")
    with pytest.raises(PS.HoldoutFrameError):
        PS.run_frame((2017, 2022), (2022,), mode="dev")


def test_dev_read_names_only_the_development_frame():
    src = inspect.getsource(PS.run_dev)
    assert "DEV_COHORTS" in src and "DEV_TEST_YEARS" in src
    assert 'mode="dev"' in src


def test_look_refuses_without_its_preconditions(monkeypatch):
    monkeypatch.setattr("efv_vintage_frame.gate_sha_committed", lambda s: False)
    with pytest.raises(PS.LookRefused):
        PS.run_look(None)
    with pytest.raises(PS.LookRefused):
        PS.run_look("deadbeef")
    monkeypatch.setattr("efv_vintage_frame.gate_sha_committed", lambda s: True)
    monkeypatch.setattr(PS, "freeze_recorded", lambda text=None: False)
    with pytest.raises(PS.LookRefused):
        PS.run_look("deadbeef")
    monkeypatch.setattr(PS, "freeze_recorded", lambda text=None: True)
    monkeypatch.setattr(PS, "look_spent", lambda *a, **k: True)
    with pytest.raises(PS.LookRefused):
        PS.run_look("deadbeef")
    monkeypatch.setattr(PS, "look_spent", lambda *a, **k: False)
    with pytest.raises(PS.LookRefused):
        PS.run_look("deadbeef", dry_run_done=False)


def test_look_spent_reads_part_13_and_the_artifact(tmp_path):
    text = "## Part 13. Results\n\nEMPTY AT REGISTRATION.\n"
    assert not PS.look_spent(eval_path=tmp_path / "none.json", text=text)
    text2 = text + "\n### 2026-12-10 look on holdout H\n"
    assert PS.look_spent(eval_path=tmp_path / "none.json", text=text2)
    p = tmp_path / "spent.json"
    p.write_text("{}", encoding="utf-8")
    assert PS.look_spent(eval_path=p, text=text)


# --- the FV-cell ban (gate Part 7) ----------------------------------------------

def test_no_fv_cell_grouping_in_the_module():
    tree = ast.parse(SRC)
    for name in _names(tree):
        low = name.lower()
        assert not any(t in low for t in _BANNED_TOKENS), name
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 40:
            low = node.value.lower()
            assert not any(t in low for t in _BANNED_TOKENS), node.value
    assert "p_bucket_given_fv" not in SRC
    assert "consensus_fv_raw" in SRC         # INC reads the as-of FV as one continuous number


def test_strata_keys_are_exactly_the_four():
    rows = PS.fixture_rows(60)
    out = PS.strata(rows)
    assert tuple(out) == ("side", "debut_age_band", "position_group", "last_level")
    for key, cells in out.items():
        for v, cell in cells.items():
            assert "n" in cell
            if cell["n"] < PS.MIN_STRATUM_ROWS:
                assert list(cell) == ["n"]


# --- forbidden inputs (gate 0.2, 0.3, Part 11) ---------------------------------

def test_module_names_no_look_table_served_fit_or_live_label():
    for token in _FORBIDDEN:
        assert token not in SRC, token
    tree = ast.parse(SRC)
    imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                for a in n.names} | {n.module for n in ast.walk(tree)
                                     if isinstance(n, ast.ImportFrom) and n.module}
    assert not imported & {"war_source", "ewar", "stats", "backtest"}, imported
    assert "value_framework.py --fit" not in SRC and "run_backtest" not in SRC
    assert "fwar_vintage" in imported


def test_label_is_the_frozen_vintage():
    src = inspect.getsource(PS.build_profiles)
    assert "fwar_vintage.season_totals(fwar_vintage.load())" in src
    totals = {(1, 2019): 1.5, (1, 2020): -0.5, (1, 2022): 9.0}
    assert PS.realized_war(1, 2019, totals) == pytest.approx(1.0)      # 2021 absent counts 0
    assert PS.realized_war(2, 2019, totals) == 0.0


# --- WAR from point predictions only (gate 1.4) ---------------------------------

def _consts():
    return {"season": 2018, "lg_r_pa": 0.1168, "lg_ra9": 4.48, "lg_era": 4.15, "rpw": 9.71,
            "fip_constant": 3.16, "lg_pa": 185139.0, "woba_scale": 1.23, "eng_lg_woba": 0.315,
            "lg_nonp_wrc_pa": 0.1208, "lg_adj_rate": 0.00245, "rep_per_pa": 0.0299,
            "lg_fipr9": 4.48, "mlb_games": 2430.0, "inn_per_pa": 2.13, "pf": 1.0, "warip": 0.0}


def _pt():
    return {"hit:H": {"n": 10, "pooled_exposure": 450.0, "per_season": 150.0, "games_per_season": 40.0},
            "pit:SP": {"n": 10, "pooled_exposure": 390.0, "per_season": 130.0, "games_per_season": 13.0},
            "pit:RP": {"n": 10, "pooled_exposure": 200.0, "per_season": 66.0, "games_per_season": 20.0}}


def test_war_reads_the_point_prediction_never_the_bands():
    pytest.importorskip("fwar_frame")
    prof = {"side": "hit", "position_group": "IF", "field_position": "SS", "arrival_age": 23}
    preds = {"woba": {"p50": 0.320, "p10": 0.250, "p90": 0.400}}
    a = PS.assemble_war(prof, preds, _consts(), _pt())
    preds2 = {"woba": {"p50": 0.320, "p10": -9.0, "p90": 9.0}}
    b = PS.assemble_war(prof, preds2, _consts(), _pt())
    assert a is not None and a["war"] == pytest.approx(b["war"])
    assert a["components"]["bsr"] == 0.0 and a["components"]["fld"] == 0.0
    assert a["pa"] == pytest.approx(450.0)
    pit = {"side": "pit", "position_group": "SP", "field_position": None, "arrival_age": 24}
    pp = {"k_pct": {"p50": 0.24, "p10": 0.1, "p90": 0.4}, "bb_pct": {"p50": 0.08, "p10": 0.0, "p90": 0.2},
          "hr_bf": {"p50": 0.03, "p10": 0.0, "p90": 0.1}}
    c = PS.assemble_war(pit, pp, _consts(), _pt())
    pp2 = {k: {"p50": v["p50"], "p10": -1.0, "p90": 2.0} for k, v in pp.items()}
    d = PS.assemble_war(pit, pp2, _consts(), _pt())
    assert c is not None and c["war"] == pytest.approx(d["war"])
    src = inspect.getsource(PS.assemble_war)
    assert '"p10"' not in src and '"p90"' not in src
    assert "hitter_heads" in src and "pitcher_heads" in src


def test_no_war_band_from_rate_bands():
    for fn in (PS.score_rows, PS.leg_l2, PS.run_frame):
        src = inspect.getsource(fn)
        assert "warP10" not in src and "warP90" not in src and "war_p10" not in src


# --- the stacked ridge and its bands (gate 1.2, 1.3) ---------------------------

def test_ridge_closed_form_and_weighted_intercept():
    X = np.array([[0.0], [1.0], [2.0], [3.0]])
    y = np.array([1.0, 3.0, 5.0, 7.0])
    w = np.ones(4)
    f = PS.ridge_fit(X, y, w, 0.0)
    assert f["b"][0] == pytest.approx(2.0) and f["b0"] == pytest.approx(1.0)
    g = PS.ridge_fit(X, y, w, 1e9)
    assert abs(g["b"][0]) < 1e-6 and g["b0"] == pytest.approx(4.0)
    h = PS.ridge_fit(np.zeros((4, 0)), y, np.array([1.0, 1.0, 1.0, 5.0]), 1.0)
    assert h["b0"] == pytest.approx((1 + 3 + 5 + 35) / 8.0)


def test_design_standardizes_and_flags_missing():
    rows = [{"a": 1.0, "b": None}, {"a": 3.0, "b": 2.0}, {"a": None, "b": 4.0}]
    X, st = PS._design(rows, ["a", "b"], None)
    assert X.shape == (3, 4)
    assert X[0, 1] == 0.0 and X[0, 3] == 1.0            # missing b at the mean, flagged
    assert X[2, 0] == 0.0 and X[2, 2] == 1.0
    X2, _ = PS._design([{"a": 2.0, "b": 3.0}], ["a", "b"], st)
    assert X2[0, 0] == pytest.approx(0.0) and X2[0, 1] == pytest.approx(0.0)


def _synthetic_train(n=120, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        x = rng.normal(0.25, 0.05)
        y = x + rng.normal(0, 0.01)
        rows.append({"side": "hit", "debut_year": 2017 + (i % 3), "player_key": f"p{i}",
                     "_x": x, "outcome": {"k_pct": (y, 300.0 + 10 * (i % 7))}})
    return rows


def test_nested_penalty_is_chosen_inside_the_training_cohorts(monkeypatch):
    rows = _synthetic_train()
    monkeypatch.setattr(PS, "level0_inputs", lambda prof, fits, side, stat: {"translation": prof["_x"]})
    m = PS.fit_stat_model(rows, "hit", "k_pct", {})
    assert m is not None
    assert m["inner_years"] == [2018, 2019]               # the earliest cohort is never an inner test
    assert m["lam"] in PS.PENALTY_GRID
    assert m["lam"] <= 1.0                                 # a strong linear signal takes a small penalty
    assert m["q10"] < 0 < m["q90"]
    p = PS.predict_stat(m, {"_x": 0.30}, {})
    assert abs(p["p50"] - 0.30) < 0.02
    assert p["p10"] == pytest.approx(p["p50"] + m["q10"]) and p["p90"] == pytest.approx(p["p50"] + m["q90"])


def test_penalty_ties_resolve_to_the_larger_penalty(monkeypatch):
    rows = _synthetic_train()
    for r in rows:
        r["outcome"]["k_pct"] = (0.22, 300.0)              # a constant target: every penalty ties
    monkeypatch.setattr(PS, "level0_inputs", lambda prof, fits, side, stat: {"translation": prof["_x"]})
    m = PS.fit_stat_model(rows, "hit", "k_pct", {})
    assert m["lam"] == PS.PENALTY_GRID[-1]


def test_holm_step_down():
    out = PS.holm({"a": 0.001, "b": 0.03, "c": 0.04, "d": None}, alpha=0.05)
    assert out == {"a": True, "b": False, "c": False, "d": False}      # 0.03 > 0.05 / 2, step-down stops
    out2 = PS.holm({"a": 0.001, "b": 0.012, "c": 0.04}, alpha=0.05)
    assert out2 == {"a": True, "b": True, "c": True}


def test_baseline_fallback_prices_a_missing_input_at_b0():
    fits = {"b0": {"k_pct": {"IF": 0.23, "__side__": 0.24}}, "translation": {}, "proxy": None,
            "tip": {}, "aging": None}
    prof = {"position_group": "IF", "k_rel": None, "tools": {}, "arrival_age": 23}
    out = PS.baseline_values(prof, "k_pct", fits, "hit")
    assert out["B0"] == 0.23 and out["B1"] == 0.23 and out["_fallback"] == ["B1"]
    prof2 = {"position_group": "DH", "k_rel": None, "tools": {}, "arrival_age": 23}
    assert PS.baseline_values(prof2, "k_pct", fits, "hit")["B0"] == 0.24


# --- the dry run (gate Part 10 item 2) ---------------------------------------

def test_dry_run_completes_on_fixtures_with_none_values():
    rep = PS.dry_run(B=50)
    assert set(rep["l1"]) == {"hit", "pit"}
    for side in ("hit", "pit"):
        assert tuple(rep["l1"][side]) == PS.STATS[side]
        for e in rep["l1"][side].values():
            assert e["verdict"] in {"PASS", "LOSS", "NULL", "NOT COMPUTABLE"}
    assert rep["l2"]["verdict"] in {"PASS", "INC retains", "NOT COMPUTABLE"}
    assert tuple(rep["strata"]) == PS.STRATA
    assert rep["bootstrap"]["B"] == 50


def test_fixture_rows_carry_none_values():
    rows = PS.fixture_rows(120)
    assert any(v is None for r in rows for v in r["preds"].values())
    assert any(r["war_model"] is None for r in rows)


# --- helpers -----------------------------------------------------------------

def test_position_groups_and_bands():
    assert PS.position_group("C", "hit") == "C"
    assert PS.position_group("SS/2B", "hit") == "IF"
    assert PS.position_group("OF", "hit") == "OF"
    assert PS.position_group("DH", "hit") == "DH"
    assert PS.position_group(None, "hit") == "other"
    assert PS.position_group("RHP", "pit") == "SP"
    assert PS.position_group("SIRP", "pit") == "RP"
    assert PS.field_position("DH") is None and PS.field_position("OF") == "RF"
    assert [PS.age_band(a) for a in (20, 21, 22, 23.9, 24, 25, 26, None)] == [
        "21 or younger", "21 or younger", "22 to 23", "22 to 23", "24 to 25", "24 to 25",
        "26 or older", "unknown"]
    assert PS.level_group("AAA") == "AAA" and PS.level_group("A") == "A+ or below"
    assert PS.level_group(None) == "none"
    assert PS.whole_years("2000-06-15", "2023-06-14") == 22
    assert PS.whole_years("2000-06-15", "2023-06-15") == 23


def test_preview_writes_under_cache_only(tmp_path, monkeypatch):
    monkeypatch.setattr(PS, "preview", lambda keys, corpus=None: {"n_rows": 0, "rows": {}, "role": "preview, dark"})
    p = PS.write_preview(["x"], tmp_path / "cache" / "prospect_statline" / "preview" / "prospect_statline.json")
    assert p.exists()
    assert str(PS.PREVIEW_PATH).replace("\\", "/").endswith(".cache/prospect_statline/preview/prospect_statline.json")
    assert not re.search(r"DATA_DIR\s*/\s*\"prospect_statline", inspect.getsource(PS.write_preview))
