# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The skill look's precedence and admission rule, pinned on fixtures
(docs/ebr-2026-09-30/EBR_GATE.md parts 9.5 and 9.6; orchestrator ruling X1 of
the former skill plan). Every cell takes the first disposition that holds in
the order WIN, SMALL WIN, LOSS, EQUIVALENT, UNRESOLVED, so exactly one
applies; a part enters only under part 9.6 and part 1's recorded answers.
Nothing here reads real data or relates any delta to a next-season quantity.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import swar  # noqa: E402
import swar_lab as L  # noqa: E402


def cell(part=L.PART_FIELDING, holm=True, gap=None, lo95=None, hi95=None, lo90=None, hi90=None,
         b1_lo95=0.01, twin_lo95=-0.01, transport=True, v1_sign_agrees=True):
    return {"part": part, "holm_reject": holm, "gap": gap, "lo95": lo95, "hi95": hi95,
            "lo90": lo90, "hi90": hi90, "b1_lo95": b1_lo95, "twin_lo95": twin_lo95,
            "transport": transport, "v1_sign_agrees": v1_sign_agrees}


def _only_one(c) -> str:
    d = L.disposition(c)
    assert sum(1 for x in L.DISPOSITIONS if x == d) == 1, d
    return d


# --------------------------------------------------------------------------
# the precedence (part 9.5)
# --------------------------------------------------------------------------

def test_a_holm_rejected_small_gap_is_small_win_and_counts_as_equivalent():
    c = cell(gap=0.008, lo95=0.002, hi95=0.014, lo90=0.003, hi90=0.013)
    assert _only_one(c) == L.SMALL_WIN
    assert L.counts_as(L.SMALL_WIN) == L.EQUIVALENT


def test_a_holm_rejected_gap_at_the_margin_with_lo95_above_zero_is_win():
    c = cell(gap=0.025, lo95=0.004, hi95=0.046, lo90=0.008, hi90=0.042)
    assert _only_one(c) == L.WIN_COMPONENTS


def test_the_same_win_with_the_b1_clause_failing_is_win_regression_only():
    c = cell(gap=0.025, lo95=0.004, hi95=0.046, lo90=0.008, hi90=0.042, b1_lo95=-0.003)
    assert _only_one(c) == L.WIN_REGRESSION
    c = cell(gap=0.025, lo95=0.004, hi95=0.046, b1_lo95=None)
    assert _only_one(c) == L.WIN_REGRESSION


def test_a_twin_that_reproduces_the_gain_or_a_failed_transport_is_regression_only():
    assert _only_one(cell(gap=0.03, lo95=0.01, hi95=0.05, twin_lo95=0.001)) == L.WIN_REGRESSION
    assert _only_one(cell(gap=0.03, lo95=0.01, hi95=0.05, twin_lo95=None)) == L.WIN_REGRESSION
    p = dict(part=L.PART_PITCHING, gap=0.03, lo95=0.01, hi95=0.05)
    assert _only_one(cell(transport=True, **p)) == L.WIN_COMPONENTS
    assert _only_one(cell(transport=False, **p)) == L.WIN_REGRESSION
    # transport binds the pitching part only
    assert _only_one(cell(transport=False, gap=0.03, lo95=0.01, hi95=0.05)) == L.WIN_COMPONENTS


def test_the_position_parts_win_components_needs_no_b1_clause():
    c = cell(part=L.PART_POSITION, gap=0.025, lo95=0.004, hi95=0.046, b1_lo95=None)
    assert _only_one(c) == L.WIN_COMPONENTS
    c = cell(part=L.PART_POSITION, gap=0.025, lo95=0.004, hi95=0.046, b1_lo95=-0.02)
    assert _only_one(c) == L.WIN_COMPONENTS


def test_an_interval_below_zero_is_loss_never_equivalent():
    c = cell(holm=False, gap=-0.010, lo95=-0.015, hi95=-0.005, lo90=-0.014, hi90=-0.006)
    assert _only_one(c) == L.LOSS


def test_a_90_percent_interval_inside_the_margin_without_holm_is_equivalent():
    c = cell(holm=False, gap=0.001, lo95=-0.016, hi95=0.019, lo90=-0.012, hi90=0.015)
    assert _only_one(c) == L.EQUIVALENT


def test_a_90_percent_interval_that_is_neither_is_unresolved():
    c = cell(holm=False, gap=-0.01, lo95=-0.035, hi95=0.014, lo90=-0.03, hi90=0.01)
    assert _only_one(c) == L.UNRESOLVED


def test_holm_without_lo95_above_zero_is_not_a_win():
    c = cell(holm=True, gap=0.03, lo95=-0.001, hi95=0.06, lo90=0.002, hi90=0.055)
    assert _only_one(c) == L.UNRESOLVED


def test_v1_disagreeing_in_sign_blocks_a_positive_disposition():
    c = cell(gap=0.025, lo95=0.004, hi95=0.046, lo90=0.008, hi90=0.042, v1_sign_agrees=False)
    assert _only_one(c) == L.UNRESOLVED
    c = cell(gap=0.008, lo95=0.002, hi95=0.014, lo90=0.003, hi90=0.013, v1_sign_agrees=False)
    assert _only_one(c) == L.EQUIVALENT


def test_a_null_cell_is_unresolved_and_every_fixture_has_exactly_one_disposition():
    assert _only_one(cell(holm=None)) == L.UNRESOLVED
    grid = [cell(part=p, holm=h, gap=g, lo95=g - w, hi95=g + w, lo90=g - 0.8 * w, hi90=g + 0.8 * w,
                 b1_lo95=b, twin_lo95=t, transport=tr)
            for p in L.PARTS for h in (True, False, None) for g in (-0.04, -0.01, 0.0, 0.01, 0.02, 0.05)
            for w in (0.005, 0.02, 0.04) for b in (None, -0.01, 0.01) for t in (None, -0.01, 0.01)
            for tr in (None, True, False)]
    for c in grid:
        _only_one(c)


# --------------------------------------------------------------------------
# the HR-arm clause and transport (part 9.5)
# --------------------------------------------------------------------------

def test_the_hr_arm_keeps_the_shrink_only_when_both_blocks_are_positive():
    assert L.hr_arm_clause(0.004, 0.011)["variant"] == swar.HR_SHRUNK
    for early, late in ((-0.002, 0.011), (0.004, -0.001), (0.0, 0.01), (None, 0.01)):
        out = L.hr_arm_clause(early, late)
        assert out["variant"] == swar.HR_FWAR and out["holds"] is False
        assert "R2e.2" in out["note"]


def test_transport_needs_both_blocks_positive():
    assert L.transport_holds(0.01, 0.02)
    assert not L.transport_holds(-0.01, 0.02)
    assert not L.transport_holds(0.01, None)


def test_holm_is_a_step_down_within_one_family():
    assert L.holm({"a": 0.01, "b": 0.03}) == {"a": True, "b": True}
    assert L.holm({"a": 0.03, "b": 0.03}) == {"a": False, "b": False}
    assert L.holm({"a": 0.001, "b": 0.015, "c": 0.02, "d": 0.5}) == {"a": True, "b": True, "c": True, "d": False}
    assert L.holm({"a": 0.001, "b": 0.02, "c": 0.02, "d": 0.5}) == {"a": True, "b": False, "c": False, "d": False}
    assert L.holm({"a": 0.001, "b": None}) == {"a": True, "b": False}


# --------------------------------------------------------------------------
# admission (part 9.6)
# --------------------------------------------------------------------------

A = {"EWV3-Q1": "a", "EWV3-Q2": "a", "void": False}
B = {"EWV3-Q1": "b", "EWV3-Q2": "a", "void": False}


def test_the_recorded_answers_are_part_1s():
    assert L.ANSWERS == {"EWV3-Q1": "a", "EWV3-Q2": "a"}


def test_a_rate_win_components_with_a_cumulative_loss_is_not_admitted():
    for part, (r, c) in L.RATE_CUM.items():
        assert not L.admit(part, {r: L.WIN_COMPONENTS, c: L.LOSS}, A)["admitted"]
        assert L.admit(part, {r: L.WIN_COMPONENTS, c: L.UNRESOLVED}, A)["admitted"]
        assert L.admit(part, {r: L.WIN_COMPONENTS, c: L.EQUIVALENT}, A)["admitted"]


def test_win_regression_only_is_admitted_under_q1_b_and_not_under_q1_a():
    cells = {"H-rate": L.WIN_REGRESSION, "H-cum": L.EQUIVALENT}
    assert not L.admit(L.PART_FIELDING, cells, A)["admitted"]
    assert L.admit(L.PART_FIELDING, cells, B)["admitted"]


def test_small_win_equivalent_loss_and_unresolved_rate_cells_never_admit():
    for d in (L.SMALL_WIN, L.EQUIVALENT, L.LOSS, L.UNRESOLVED):
        for ans in (A, B):
            assert not L.admit(L.PART_PITCHING, {"P-rate": d, "P-cum": L.WIN_COMPONENTS}, ans)["admitted"]


BOTH = {"HEM+ H-rate": L.WIN_COMPONENTS, "HEM+ H-cum": L.EQUIVALENT,
        "xHEM+ H-rate": L.WIN_COMPONENTS, "xHEM+ H-cum": L.UNRESOLVED}


def test_both_batting_arms_qualifying_ask_for_the_contrast_first():
    out = L.admit(L.PART_BATTING, BOTH, A)
    assert out["needs_contrast"] and not out["admitted"]


def test_the_contrast_at_lo95_plus_0_004_admits_xhem_and_at_minus_0_001_admits_hem():
    out = L.admit(L.PART_BATTING, dict(BOTH, contrast={"lo95": 0.004}), A)
    assert out["admitted"] and out["arm"] == "xHEM+"
    out = L.admit(L.PART_BATTING, dict(BOTH, contrast={"lo95": -0.001}), A)
    assert out["admitted"] and out["arm"] == "HEM+"
    out = L.admit(L.PART_BATTING, dict(BOTH, contrast={"lo95": None}), A)
    assert out["admitted"] and out["arm"] == "HEM+"


def test_one_qualifying_batting_arm_enters_alone_without_a_contrast():
    cells = dict(BOTH, **{"xHEM+ H-cum": L.LOSS})
    out = L.admit(L.PART_BATTING, cells, A)
    assert out["admitted"] and out["arm"] == "HEM+" and not out["needs_contrast"]
    cells = dict(BOTH, **{"HEM+ H-rate": L.WIN_REGRESSION})
    out = L.admit(L.PART_BATTING, cells, A)
    assert out["admitted"] and out["arm"] == "xHEM+"


def test_q2_b_and_c_pick_as_registered():
    cells = {"HEM+ H-rate": {"disposition": L.WIN_COMPONENTS, "gap": 0.031},
             "HEM+ H-cum": {"disposition": L.EQUIVALENT, "gap": 0.0},
             "xHEM+ H-rate": {"disposition": L.WIN_COMPONENTS, "gap": 0.027},
             "xHEM+ H-cum": {"disposition": L.EQUIVALENT, "gap": 0.0}}
    assert L.admit(L.PART_BATTING, cells, {"EWV3-Q1": "a", "EWV3-Q2": "b"})["arm"] == "HEM+"
    assert L.admit(L.PART_BATTING, cells, {"EWV3-Q1": "a", "EWV3-Q2": "c"})["arm"] == "xHEM+"


def test_a_void_run_admits_nothing():
    good = {"H-rate": L.WIN_COMPONENTS, "H-cum": L.WIN_COMPONENTS}
    for part in (L.PART_POSITION, L.PART_FIELDING):
        assert not L.admit(part, good, dict(A, void=True))["admitted"]
    assert not L.admit(L.PART_PITCHING, {"P-rate": L.WIN_COMPONENTS, "P-cum": L.EQUIVALENT},
                       dict(A, void=True))["admitted"]
    assert not L.admit(L.PART_BATTING, dict(BOTH, contrast={"lo95": 0.01}), dict(A, void=True))["admitted"]


def test_the_licensed_sentences_follow_part_9_6():
    s = L.licensed_sentence(L.PART_FIELDING, L.SMALL_WIN, 0.008, 0.002, 0.014, 1255)
    assert s.startswith("ranked the next season's fWAR about as well as fWAR itself did")
    assert "1,255 pairs" in s and "hitters with 200 or more PA" in s
    assert L.licensed_sentence(L.PART_FIELDING, L.UNRESOLVED) is None
    s = L.licensed_sentence(L.PART_POSITION, L.WIN_COMPONENTS)
    assert "uniformly shrunk" not in s
    s = L.licensed_sentence(L.PART_PITCHING, L.WIN_COMPONENTS)
    assert "uniformly shrunk" in s and "pitchers with 50 or more IP" in s
    for d in L.DISPOSITIONS:
        t = L.licensed_sentence(L.PART_BATTING, d) or ""
        for banned in ("more accurate", "better than FanGraphs", "true talent", "regress"):
            assert banned not in t


# --------------------------------------------------------------------------
# B1 and the registered parameters
# --------------------------------------------------------------------------

def test_the_registered_parameters():
    assert (L.SEED, L.BOOT, L.MARGIN, L.MDE_Z) == (20261008, 2000, 0.02, 1.645)
    assert L.PREDICTOR_SEASONS == (2021, 2022, 2023, 2024)
    assert L.TRANSPORT_EARLY_SEASONS == (2016, 2017, 2018) == L.B1_FIT_SEASONS
    assert L.HOLDOUT_SEASONS == (2025,)
    assert (L.MIN_PA, L.MIN_IP) == (200.0, 50.0)
    fams = {p: list(L.PART_CELLS[p]["cells"]) for p in L.PARTS}
    assert fams == {"position": ["H-rate", "H-cum"],
                    "batting": ["HEM+ H-rate", "HEM+ H-cum", "xHEM+ H-rate", "xHEM+ H-cum"],
                    "pitching": ["P-rate", "P-cum", "S2b P-rate", "S2b P-cum"],
                    "fielding": ["H-rate", "H-cum"]}
    assert L.PITCHING_ARMS == {"S2": ("P-rate", "P-cum"), "S2b": ("S2b P-rate", "S2b P-cum")}
    assert L.PITCHING_ARM_RULE == "a"


# --------------------------------------------------------------------------
# the pitching basis (EBR_GATE.md part 11.3.5): two arms, one Holm family
# --------------------------------------------------------------------------

BOTH_P = {"P-rate": L.WIN_COMPONENTS, "P-cum": L.EQUIVALENT,
          "S2b P-rate": L.WIN_COMPONENTS, "S2b P-cum": L.UNRESOLVED}


def test_one_qualifying_pitching_arm_enters_alone():
    out = L.admit(L.PART_PITCHING, dict(BOTH_P, **{"S2b P-cum": L.LOSS}), A)
    assert out["admitted"] and out["arm"] == "S2" and not out["needs_contrast"]
    out = L.admit(L.PART_PITCHING, dict(BOTH_P, **{"P-rate": L.WIN_REGRESSION}), A)
    assert out["admitted"] and out["arm"] == "S2b"
    # S2's cells alone (no S2b cell scored) behave as before part 11.3
    out = L.admit(L.PART_PITCHING, {"P-rate": L.WIN_COMPONENTS, "P-cum": L.EQUIVALENT}, A)
    assert out["admitted"] and out["arm"] == "S2"


def test_both_pitching_arms_need_the_contrast_and_s2b_enters_only_above_zero():
    out = L.admit(L.PART_PITCHING, BOTH_P, A)
    assert out["needs_contrast"] and not out["admitted"]
    out = L.admit(L.PART_PITCHING, dict(BOTH_P, contrast={"lo95": 0.003}), A)
    assert out["admitted"] and out["arm"] == "S2b"
    for lo in (0.0, -0.004, None):
        out = L.admit(L.PART_PITCHING, dict(BOTH_P, contrast={"lo95": lo}), A)
        assert out["admitted"] and out["arm"] == "S2"
    assert not L.admit(L.PART_PITCHING, dict(BOTH_P, contrast={"lo95": 0.01}), dict(A, void=True))["admitted"]


def test_the_s2b_cells_take_the_pitching_parts_b1_and_transport_clauses():
    win = cell(part=L.PART_PITCHING, gap=0.03, lo95=0.01, hi95=0.05, lo90=0.012, hi90=0.045,
               b1_lo95=0.004, twin_lo95=-0.01, transport=False)
    assert L.disposition(win) == L.WIN_REGRESSION
    assert L.disposition(dict(win, transport=True)) == L.WIN_COMPONENTS
    s = L._sentence(L.PART_PITCHING, {"P-rate": {"disposition": L.LOSS},
                                      "S2b P-rate": {"disposition": L.WIN_COMPONENTS, "gap": 0.03,
                                                     "lo95": 0.01, "hi95": 0.05, "n_pairs": 700}},
                    {"arm": "S2b"}, "look")
    assert s.startswith("ranked the next season's fWAR better than fWAR itself did") and "700 pairs" in s


def test_b1_constants_are_frozen_with_their_fit_log():
    assert L.B1_K == {"hit": 662.0, "pit": 244.0}
    assert L.B1_FIT_LOG["hit"]["k"] == L.B1_K["hit"] and L.B1_FIT_LOG["pit"]["k"] == L.B1_K["pit"]
    assert L.B1_FIT_LOG["fit_seasons"] == [2016, 2017, 2018]
    for side in ("hit", "pit"):
        f = L.B1_FIT_LOG[side]
        assert f["k"] == round(f["hm"] * (1 - f["r"]) / f["r"])


def test_the_b1_fit_reads_fwar_and_exposure_only_and_reproduces_the_rule():
    payload = L.FixtureLabInputs().preview()
    exp = L.exposure_rows(payload)
    for blk in exp.values():
        for side_rows in blk.values():
            for v in side_rows.values():
                assert len(v) == 2   # (n, fWAR): no part, delta or test value
    f = L.fit_b1(exp, L.HIT)
    assert f["k"] == round(f["hm"] * (1 - f["r"]) / f["r"])
    assert L.b1_rate(3.0, 600.0, 0.004, 662.0) == pytest.approx((3.0 + 0.004 * 662.0) / 1262.0)


# --------------------------------------------------------------------------
# the dry run and the write rule
# --------------------------------------------------------------------------

def test_the_dry_run_writes_only_under_its_temp_dir_and_every_cell_has_one_disposition(tmp_path):
    before = set(p for p in (ROOT / "data").glob("swar*"))
    out = L.dry_run(log=lambda *a: None, boot=60, tmp_dir=tmp_path)
    rec = json.loads(Path(out["record"]).read_text(encoding="ascii"))
    assert rec["status"] == "SCORED" and rec["holdout"]["status"] == "SCORED"
    for part, fam in rec["look"]["cells"].items():
        for c, r in fam.items():
            assert r["disposition"] in L.DISPOSITIONS
    assert set(p for p in (ROOT / "data").glob("swar*")) == before
    assert Path(out["record"]).resolve().parent == tmp_path.resolve()


def test_the_lab_refuses_a_record_under_data():
    with pytest.raises(L.LabStop):
        L.write_record({"x": 1}, ROOT / "data" / "swar_eval.json")
