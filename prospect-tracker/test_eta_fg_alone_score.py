# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FanGraphs-alone ETA score (docs/eta-2026-09-25/ETA_FG_ALONE_SCORE.md):
the arms, the verdict words, the instrument check, the debut-years-only rule,
the one-run refusal and the carried-forward block name. Synthetic rows only:
no database, network or artifact write."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def _lab():
    spec = importlib.util.spec_from_file_location(
        "eta_fg_alone_score", ROOT / "tools" / "eta_fg_alone_score.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


L = _lab()


def _row(i, *, ch40, fg, actual=None, outcome="debuted", vintage=2024, on40=False):
    r = {"player_key": f"p{i}", "vintage": vintage, "level": None, "ch40": ch40,
         "fg": fg, "fg_date": "2024-02-01" if fg is not None else None, "on40": on40,
         "outcome": outcome, "debut_date": None}
    if outcome == "debuted":
        r["actual"] = actual
        r["debut_date"] = f"{actual}-06-01"
    return r


def test_arm_f_is_fangraphs_floored_at_the_list_year():
    assert L.arm_f({"vintage": 2024, "fg": 2027}) == 2027
    assert L.arm_f({"vintage": 2024, "fg": 2023}) == 2024


def test_verdict_words_follow_the_ci():
    assert L._ci_verdict({"ci_dMAE": [0.01, 0.2]}) == "F_BEATS_B"
    assert L._ci_verdict({"ci_dMAE": [-0.3, -0.02]}) == "B_BEATS_F"
    assert L._ci_verdict({"ci_dMAE": [-0.1, 0.1]}) == "TIES"


def test_fangraphs_exact_beats_a_blend_that_is_off():
    """FanGraphs names the debut year exactly; CH40 sits three years late, so
    the blend sits one to two years late: F must BEAT B and the check must pass."""
    rows = [_row(i, ch40=2024 + i % 3 + 3, fg=2024 + i % 3, actual=2024 + i % 3)
            for i in range(90)]
    out = L.score_rows(rows, lambda s: None)
    assert out["instrument"]["verdict"] == "PASS"
    assert out["verdict"] == "F_BEATS_B"
    assert out["scores"]["F"]["mae"] == 0.0


def test_censored_rows_are_counted_but_never_scored():
    """Debut years only: a censored or washed-out row carries no `actual` and
    the scorer must never ask for one."""
    rows = [_row(i, ch40=2026, fg=2025, actual=2025 + i % 2) for i in range(40)]
    rows += [_row(100 + i, ch40=2026, fg=2026, outcome="censored_active") for i in range(30)]
    rows += [_row(200 + i, ch40=2026, fg=2026, outcome="washed_out") for i in range(5)]
    out = L.score_rows(rows, lambda s: None)
    assert out["n"] == {"rows": 75, "debuted": 40, "censored_active": 30,
                        "fg_debuted_c5_clean": 40}
    assert out["scores"]["F"]["n"] == 40


def test_a_fangraphs_year_dated_after_the_debut_is_not_scored():
    rows = [_row(i, ch40=2026, fg=2025, actual=2025) for i in range(20)]
    late = _row(99, ch40=2026, fg=2025, actual=2024)
    late["fg_date"] = "2024-08-01"
    late["debut_date"] = "2024-06-01"
    out = L.score_rows(rows + [late], lambda s: None)
    assert out["n"]["fg_debuted_c5_clean"] == 20


def test_reproduction_names_every_difference():
    rows = [_row(i, ch40=2026, fg=2025, actual=2025) for i in range(20)]
    stored = {"rows": 20, "debuted": 20, "censored_active": 0, "fg_debuted_c5_clean": 19,
              "CH40_mae": 1.0, "B_mae": 9.9}
    out = L.score_rows(rows, lambda s: None, stored=stored)
    assert out["reproduction"]["identical"] is False
    assert out["reproduction"]["differs_on"] == ["B_mae", "fg_debuted_c5_clean"]


def test_the_planted_worse_arm_is_worse_on_every_row():
    r = {"player_key": "p", "vintage": 2024, "ch40": 2026, "fg": 2026, "on40": False,
         "c5_ok": True, "actual": 2026}
    b = L.arm_b(r)
    assert abs(L.planted_worse(r) - r["actual"]) == abs(b - r["actual"]) + 1


def test_one_run_only():
    ok, _ = L.run_allowed({})
    assert ok
    ok, why = L.run_allowed({L.BLOCK: {"run": "2026-10-22"}})
    assert not ok and "--reprint" in why


def test_the_block_is_carried_forward_by_the_eta_backtest():
    import eta_backtest as eb
    assert L.BLOCK.startswith(eb.GATE_BLOCK_PREFIXES)


def test_the_stored_block_matches_the_registration_when_present():
    art = json.loads((ROOT / "data" / "eta_eval.json").read_text(encoding="utf-8"))
    blk = art.get(L.BLOCK)
    if not blk:
        pytest.skip("the registered run has not happened")
    assert blk["registration"] == L.REG_DOC
    assert blk["verdict"] in ("F_BEATS_B", "B_BEATS_F", "TIES", "VOID")
    assert blk["instrument"]["verdict"] in ("PASS", "FAIL")
    assert (blk["verdict"] == "VOID") == (blk["instrument"]["verdict"] == "FAIL")
    assert blk["scores"]["F"]["n"] == blk["n"]["fg_debuted_c5_clean"]
