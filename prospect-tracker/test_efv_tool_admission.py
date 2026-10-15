# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""TL_16_EFV_TOOL_DEV_ADMISSION pins (Part 9 PLAN section 9.4.5; LANE_C.md section 2.7,
route (a)).

1. Guards: no run without the R-LV record and the committed gate sha; the vm folds stop
   below the R-VM cohorts; pwr_comp is not a candidate under look P's C0.
2. The columns: tool_hit_w is the weight-averaged per-source hit grade; BA2's weights per
   fold read board years at most V - 3 and leave the fold's frame out; a vm row takes the
   sidecar row of the latest list vintage whose window closed before its as-of date.
3. The rule per fold on fixtures: the V frame's players never train fold V.
4. The committed artifact, the arm ledger rows and the pre-declaration document.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

import efv_v2_model as H
import efv_vintage_frame as F

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))

import efv_tool_admission as A  # noqa: E402

ART = ROOT / "data" / "_labs" / "efv_tool_admission.json"
LEDGER = ROOT / "data" / "xfv_arm_ledger.json"
DOC = ROOT / "docs" / "efv-v2" / "NEXT_REGISTRATION_TOOL_CANDIDATES.md"
_BANNED_TOKENS = ("by_fv", "fv_band", "fv_bin", "fv_cell", "stratum", "strata")


# ---------------------------------------------------------------------------
# 1. guards
# ---------------------------------------------------------------------------

def test_guards_refuse_without_the_rlv_record(monkeypatch):
    monkeypatch.setattr(A, "rlv_record", lambda: False)
    with pytest.raises(F.ReservedFrameError):
        A.guards("e7931ce4e13110eebb53555bff455ff13ca7c502")


def test_guards_refuse_without_the_gate_sha():
    with pytest.raises(F.ReservedFrameError):
        A.guards(None)


def test_folds_and_vintages():
    assert A.LV_FOLDS == (2017, 2018, 2019, 2020, 2021)
    assert A.VM_FOLDS == (2020, 2021, 2022, 2023, 2024)
    assert max(A.VM_FOLDS) < F.R_VM_FIRST_DEBUT_YEAR
    assert set(A.LV_VINTAGES) == set(F.DEV_VINTAGES) | set(F.RESERVED_LV)
    assert all(k.startswith(H.V2_SCREEN_PREFIX) for k in A.KEYS.values())


def test_pwr_comp_is_not_a_candidate_under_c0():
    assert A.pwr_comp_status()["candidate"] is False


# ---------------------------------------------------------------------------
# 2. the columns
# ---------------------------------------------------------------------------

def test_weighted_hit():
    assert A.weighted_hit({}, {"fangraphs": 1.0}) is None
    assert A.weighted_hit({"fangraphs": 50.0, "mlb_pipeline": 60.0},
                          {"fangraphs": 1.0, "mlb_pipeline": 1.0}) == 55.0
    v = A.weighted_hit({"fangraphs": 50.0, "mlb_pipeline": 60.0},
                       {"fangraphs": 0.5, "mlb_pipeline": 1.5})
    assert v == pytest.approx(57.5)
    assert A.weighted_hit({"mlb_pipeline": 45.0}, {"fangraphs": 0.6,
                                                   "mlb_pipeline": 1.4}) == 45.0


def test_hit_weights_fold_reads_lagged_board_years_outside_the_frame():
    hw = A.HitWeights.__new__(A.HitWeights)
    import ba_tool_grade_lab as BA
    hw.BA = BA
    hw.lag = BA.MIN_LAG_YEARS
    seen = {}

    def fake(by_year, sources, max_base):
        seen["years"] = sorted(by_year)
        seen["players"] = {r["player"] for rs in by_year.values() for r in rs}
        seen["max_base"] = max_base
        return {s: 1.0 for s in sources}, 0, {}

    hw.BA = type("BA", (), {"derive_weights": staticmethod(fake)})
    hw.by_year = {2016: [{"player": "a"}, {"player": "b"}], 2017: [{"player": "c"}],
                  2018: [{"player": "d"}]}
    out = hw.fold(2020, {"b"})
    assert seen["max_base"] == 2017 and seen["years"] == [2016, 2017]
    assert seen["players"] == {"a", "c"}
    assert out["flat"] is True and out["max_board_year"] == 2017


def test_vm_join_takes_the_latest_closed_window():
    feats = {(2018, "p"): {"tip": 0.1, "hit": {}}, (2019, "p"): {"tip": 0.2, "hit": {}},
             (2021, "p"): {"tip": 0.3, "hit": {}}}
    rows = [{"player_key": "p", "decision_year": 2020}]
    got = A.vm_join(rows, {"p": "2020-07-01"}, feats)
    assert got["p"][0] == 2019
    got = A.vm_join(rows, {"p": "2019-04-30"}, feats)
    assert got["p"][0] == 2018
    assert A.vm_join(rows, {"p": None}, feats) == {}


# ---------------------------------------------------------------------------
# 3. the rule per fold
# ---------------------------------------------------------------------------

def _rows():
    import random
    rnd = random.Random(7)
    rows, feats = [], {}
    for V in range(2011, 2022):
        for i in range(80):
            pk = f"p{V}_{i}"
            c = rnd.random()
            x = rnd.gauss(0, 1)
            rows.append({"player_key": pk, "decision_year": V, "fv": 40 + 20 * c,
                         "target": c + 0.5 * x + 0.1 * rnd.gauss(0, 1), "reached": 1.0,
                         "v2": {"has_block": True, "acq_known": False,
                                "tool_hit": 50.0}})
            feats[(V, pk)] = {"tip": x, "hit": {"mlb_pipeline": 50 + 5 * x}}
    return rows, feats


def test_fold_never_trains_on_its_frame():
    rows, feats = _rows()
    frame_keys = {V: {r["player_key"] for r in rows if r["decision_year"] == V}
                  for V in A.LV_FOLDS}
    # a player of the 2019 frame also listed at 2018 must leave fold 2019's training
    rows.append(dict(rows[0], player_key="p2019_0", decision_year=2018,
                     v2=dict(rows[0]["v2"])))
    feats[(2018, "p2019_0")] = {"tip": 0.0, "hit": {}}
    A._GATE[0] = None
    out = A.lv_folds(rows, frame_keys, feats, None, folds=(2017, 2018, 2019))
    assert out["2019"]["tip_iso_resid"]["n_train"] == 8 * 80
    assert out["2019"]["tip_iso_resid"]["admitted"] is True
    assert out["2019"]["tool_hit_w"]["admitted"] is True
    assert out["2017"]["tip_iso_resid"]["training_vintages"] == list(range(2011, 2017))
    assert out["2019"]["hit_weights"]["flat"] is True


# ---------------------------------------------------------------------------
# 4. the committed artifact, the ledger and the document
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def art():
    if not ART.exists():
        pytest.skip("admission artifact not built")
    return json.loads(ART.read_text(encoding="utf-8"))


def test_artifact_shape(art):
    assert art["role"].startswith("development") and art["adjudicates"] == "nothing"
    assert art["label"]["provider"] == "fwar"
    assert F.gate_sha_committed(art["guards"]["gate_sha"])
    assert set(art["arms"]) == {"TL:hit.skill.tip_iso_resid", "TL:hit.skill.tool_hit_w"}
    assert art["not_run"]["TL:hit.skill.pwr_comp"]["verdict"] == "NOT RUN"
    for a in art["arms"].values():
        assert a["role"] == "development"
        assert a["n_folds"] == len(A.LV_FOLDS) + len(A.VM_FOLDS)
        assert set(a["per_vintage_signs"]) == set(a["by_fold"])
        for k, f in a["by_fold"].items():
            assert all(int(y) < int(k.split(":")[1]) for y in f["per_vintage_signs"])
            assert all(int(y) < F.R_VM_FIRST_DEBUT_YEAR for y in f["training_vintages"])
        assert a["admitted"] == (a["n_admitted_folds"] == a["n_folds"])
    w = art["arms"]["TL:hit.skill.tool_hit_w"]["hit_weights_by_fold"]
    for k, f in w.items():
        assert f["max_board_year"] == int(k.split(":")[1]) - 3
    text = json.dumps(art)
    assert not any(t in text for t in _BANNED_TOKENS)
    assert '"w3":' not in text


def test_ledger_carries_the_arms_with_signs(art):
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = [r for r in led["arms"] if str(r.get("arm", "")).startswith("TL:")]
    assert {r["arm"] for r in rows} == set(art["arms"])
    for r in rows:
        assert r["per_vintage_signs"] == art["arms"][r["arm"]]["per_vintage_signs"]
        assert r.get("role") == "development"


def test_pre_declaration_document(art):
    text = " ".join(DOC.read_text(encoding="utf-8").split())
    assert "39 arms, zero survivors" in text
    assert "iso_rel 0 of 11 folds" in text
    assert "+0.000 to +0.003" in text
    for tag, a in art["arms"].items():
        assert tag in text and a["verdict"] in text
    assert "—" not in text and "–" not in text
    assert not re.search(r"\b(fv_cell|stratum)\b", text)


def test_no_emdash_in_the_tool():
    src = (ROOT / "tools" / "efv_tool_admission.py").read_text(encoding="utf-8")
    assert "—" not in src and "–" not in src
