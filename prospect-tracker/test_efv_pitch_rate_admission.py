# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Q10_11 pins for the pitch-rate admission diagnostic (tools/efv_pitch_rate_admission.py;
owner ask 19, the eFV half; pitch_metrics.md s7 step (c), checklist PM-13).

Why this may run at all: the eFV feature frontier is closed (plan Part 2.2; the
2026-08-14 frontier closure), and for pitchers DS-Q2 keeps pitcher eFV in consensus order
until pitch-quality or K-rate data passes the sign-stability admission rule; these arms
are reopened only by a new data field (MiLB pitch counts, never before a model input)
plus the owner's ask 19 of 2026-09-30, and pbf_rel goes beyond DS-Q2 on that authority
alone. The artifact states each arm's correlation with the closed bb_rel arm.

1. The rule is efv_v2_model.admission_for_key inside each fold: a planted column is
   admitted in every fold, a column whose sign flips between training vintages is
   refused with the rule's own reason, and the fold's training rows are the rows at
   vintages below V with every V-frame player left out.
2. A row without a value imputes at the observed training mean and carries no flag; a
   vintage with fewer than 60 observed rows gives no t.
3. The guards: a reserved list vintage or a 2025 year raises before any read.
4. The tool fits no order index, reads no delta, groups nothing by consensus-FV level,
   names no reserved vintage as a literal, and carries no em-dash.
5. The committed artifact (when built): lv_dev folds 2017 to 2019 only, the frozen fWAR
   label, two PM19 arms with uppercase verdicts and per-fold signs, nothing adjudicated;
   the arm ledger counts both arms under their own lane.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

import efv_v2_model as H
import efv_vintage_frame as F

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))

import efv_pitch_rate_admission as A  # noqa: E402
import test_efv_screen_lab as T  # noqa: E402

TOOL = ROOT / "tools" / "efv_pitch_rate_admission.py"
ARTIFACT = ROOT / "data" / "_labs" / "efv_pitch_rate_admission.json"
LEDGER = ROOT / "data" / "xfv_arm_ledger.json"
YEARS = range(2013, 2020)
EM, EN = chr(0x2014), chr(0x2013)  # the dashes the house copy rule bans
_BANNED_TOKENS = ("groupby", "tier", "bucket", "stratum", "strata", "by_fv", "fv_band",
                  "fv_bin", "fit_v2", "predict_v2", "order_idx", "paired_delta")


def _values(rows, drop_every: int = 0) -> dict:
    out = {(r["decision_year"], r["player_key"]): r["x"] for r in rows}
    if drop_every:
        for i, k in enumerate(list(out)):
            if i % drop_every == 0:
                out.pop(k)
    return out


@pytest.fixture(scope="module")
def rows():
    return {"hit": T._rows("hit", years=YEARS, n=90, seed=11),
            "pit": T._rows("pit", years=YEARS, n=90, seed=12)}


# ---------------------------------------------------------------------------
# 1. the rule inside each fold
# ---------------------------------------------------------------------------

def test_planted_column_is_admitted_in_every_fold(rows):
    out = A.run_on_rows({s: list(r) for s, r in rows.items()},
                        {s: _values(r) for s, r in rows.items()})
    assert set(out["arms"]) == {"PM19:hit.skill.ppa_rel", "PM19:pit.skill.pbf_rel"}
    for arm in out["arms"].values():
        assert arm["verdict"] == "ADMITTED" and arm["admitted_folds"] == ["2017", "2018", "2019"]
        assert arm["head"] == "skill" and arm["target"] == "u_y" and arm["rows"] == "has_block"
        assert arm["sign_predicted"] is None and arm["delta"] is None
        for V, f in arm["by_fold"].items():
            assert f["training_vintages"] == [y for y in YEARS if y < int(V)]
            assert set(f["per_vintage_signs"].values()) == {1}
            assert f["mean_abs_t"] >= H.ADMIT_MIN_MEAN_ABS_T


def test_a_sign_flip_between_training_vintages_is_refused(rows):
    hit = list(rows["hit"])
    vals = _values(hit)
    # the planted column with its sign reversed on the even vintages
    flipped = {(V, pk): (-v if V % 2 == 0 else v) for (V, pk), v in vals.items()}
    out = A.run_on_rows({"hit": hit}, {"hit": flipped})
    arm = out["arms"]["PM19:hit.skill.ppa_rel"]
    assert arm["verdict"] == "REFUSED" and arm["admitted_folds"] == []
    for f in arm["by_fold"].values():
        assert f["reason"] == "sign flipped between training vintages"
        assert len(set(f["per_vintage_signs"].values())) == 2


def test_fold_training_excludes_the_frame_players(rows):
    hit = rows["hit"]
    frame_keys = {r["player_key"] for r in hit if r["decision_year"] == 2018}
    tr = A.fold_train(hit, 2018, frame_keys)
    assert tr and all(int(r["decision_year"]) < 2018 for r in tr)
    assert not any(r["player_key"] in frame_keys for r in tr)
    # the rule as the tool applies it IS efv_v2_model.admission_for_key
    key = A.KEYS["hit"]
    A.attach(hit, key, _values(hit))
    chk = H.admission_for_key(tr, key, target="u_y", has_block_only=True)
    out = A.run_on_rows({"hit": list(hit)}, {"hit": _values(hit)})
    f = out["arms"]["PM19:hit.skill.ppa_rel"]["by_fold"]["2018"]
    assert f["t_by_vintage"] == chk["t_by_vintage"]
    assert f["per_vintage_signs"] == chk["per_vintage_signs"]


# ---------------------------------------------------------------------------
# 2. missingness
# ---------------------------------------------------------------------------

def test_absent_values_impute_at_the_observed_mean_without_a_flag(rows):
    hit = list(rows["hit"])
    vals = _values(hit, drop_every=5)
    out = A.run_on_rows({"hit": hit}, {"hit": vals})
    key = A.KEYS["hit"]
    assert out["counts"]["hit"]["observed"] == len(vals) < len(hit)
    means = H.has_block_means(hit)
    obs = [r["v2"][key] for r in hit if r["v2"][key] is not None]
    assert means[key] == pytest.approx(sum(obs) / len(obs))
    assert not any(k.endswith("_absent") or k.endswith("_missing")
                   for k in (key,) if k != H.V2_ABSENCE_KEY)
    assert out["arms"]["PM19:hit.skill.ppa_rel"]["verdict"] == "ADMITTED"


def test_a_vintage_with_fewer_than_sixty_observed_rows_gives_no_t(rows):
    hit = list(rows["hit"])
    vals = _values(hit)
    # strip 2015 down to 30 observed rows: it must give no t in every later fold
    kept = 0
    for (V, pk) in list(vals):
        if V == 2015:
            kept += 1
            if kept > 30:
                vals.pop((V, pk))
    out = A.run_on_rows({"hit": hit}, {"hit": vals})
    for V, f in out["arms"]["PM19:hit.skill.ppa_rel"]["by_fold"].items():
        assert 2015 in f["vintages_without_t"]
        assert "2015" not in f["t_by_vintage"]
        assert f["by_vintage"]["2015"]["observed"] == 30


# ---------------------------------------------------------------------------
# 3. the guards
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("V", sorted(F.RESERVED_LV))
def test_a_reserved_fold_raises_before_any_read(rows, V):
    with pytest.raises(F.ReservedFrameError):
        A.guards(folds=(2017, 2018, V))
    with pytest.raises(F.ReservedFrameError):
        A.run_on_rows({"hit": list(rows["hit"])}, {"hit": {}}, folds=(2017, V))


def test_a_reserved_year_on_a_training_row_raises(rows):
    hit = list(rows["hit"])
    bad = dict(hit[0], decision_year=F.R_VM_FIRST_DEBUT_YEAR, player_key="late")
    with pytest.raises(Exception):
        A.run_on_rows({"hit": hit + [bad]}, {"hit": {}})
    with pytest.raises(F.ReservedFrameError):
        A.sidecar_values({"rows": {"hit": {str(min(F.RESERVED_LV)): {"p": [0.1, 100, [2019]]}}}},
                         "hit")


# ---------------------------------------------------------------------------
# 4. what the tool never does
# ---------------------------------------------------------------------------

def test_tool_fits_nothing_groups_nothing_and_names_no_reserved_vintage():
    text = TOOL.read_text(encoding="utf-8")
    assert EM not in text and EN not in text
    tree = ast.parse(text)
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            names.add(n.id)
        elif isinstance(n, ast.Attribute):
            names.add(n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool):
            assert n.value not in F.RESERVED_LV, f"reserved vintage literal {n.value}"
            assert n.value < F.R_VM_FIRST_DEBUT_YEAR or n.value > 2100
    code_names = {n.lower() for n in names}
    for tok in _BANNED_TOKENS:
        assert tok not in code_names, tok
    assert "admission_for_key" in names


def test_test_file_and_artifact_carry_no_dash():
    assert EM not in Path(__file__).read_text(encoding="utf-8")
    if ARTIFACT.exists():
        t = ARTIFACT.read_text(encoding="utf-8")
        assert EM not in t and EN not in t


# ---------------------------------------------------------------------------
# 5. the committed artifact and the ledger
# ---------------------------------------------------------------------------

def test_committed_artifact_is_lv_dev_on_the_frozen_label_and_adjudicates_nothing():
    if not ARTIFACT.exists():
        pytest.skip("admission artifact not built")
    doc = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert doc["frame"] == "lv_dev" and doc["folds"] == [2017, 2018, 2019]
    assert doc["adjudicates"] == "nothing"
    assert doc["label"]["provider"] == "fwar" and doc["label"]["label_id"].startswith("fwar@")
    assert doc["guards"]["reserved_vm_pins"] == [] and doc["guards"]["gate_registered"]
    assert not doc["guards"]["order_index_fitted"] and not doc["guards"]["delta_read"]
    assert "frontier is closed" in doc["why_this_may_run"] and "DS-Q2" in doc["why_this_may_run"]
    assert doc["n_arms"] == 2 == len(doc["arms"])
    for tag, arm in doc["arms"].items():
        assert tag.startswith("PM19:") and arm["verdict"] in ("ADMITTED", "REFUSED")
        assert arm["verdict"] == ("ADMITTED" if arm["n_admitted_folds"] == 3 else "REFUSED")
        assert set(arm["by_fold"]) == {"2017", "2018", "2019"}
        for V, f in arm["by_fold"].items():
            assert max(f["training_vintages"]) < int(V)
            assert not set(f["training_vintages"]) & F.RESERVED_LV
            assert set(f["per_vintage_signs"]) == set(f["t_by_vintage"])
        assert arm["closed_arm_comparison"]["closed_arm"] == "D-1:bb_rel:hit"
        assert arm["closed_arm_comparison"]["spearman_vs_bb_rel"] is not None
    both = all(a["admitted"] for a in doc["arms"].values())
    assert doc["admitted_all_folds_both_sides"] is both
    assert doc["pre_declaration"].startswith("owed" if both else "not owed")
    # nothing is cut by a grade level
    assert not re.search(r'"(fv|grade)_?(level|tier|cell|band)"', ARTIFACT.read_text(encoding="utf-8"))


def test_the_arm_ledger_counts_both_arms_under_their_own_lane():
    if not (LEDGER.exists() and ARTIFACT.exists()):
        pytest.skip("ledger or artifact not built")
    import efv_arm_ledger as AL
    assert any(name.endswith("efv_pitch_rate_admission.json") for name, _k, _l in AL.SOURCES)
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    doc = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    mine = [a for a in led["arms"] if a["arm"].startswith("PM19:")]
    assert len(mine) == doc["n_arms"] == 2
    assert {a["verdict"] for a in mine} == {doc["arms"][a["arm"]]["verdict"] for a in mine}
    assert all(a["cleared_own_floor"] is None for a in mine)
    assert all(a["per_vintage_signs"] == doc["arms"][a["arm"]]["per_vintage_signs"] for a in mine)
    assert not any(p["probe"].startswith("PM19:") and p["lane"] == mine[0]["lane"]
                   for p in led["probes"])
