# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/efv_fwar_label_epoch_lab.py on fixtures only (step H's producer).

The lab's first real run is runbook step H; nothing here reads career_war, an arm matrix
or a snapshot. What is pinned: the twin permutes within (season, side); the clause (i)
residual identity; UNAVAILABLE on a missing or omitted arm, never inferred; the snapshot
refusal (absent, and the forbidden names); the reporting path on fixtures that carry
nulls; the relabelling reproduces the build's rule; A2 is applied per fold to the
milb_unavailable rows only; the lab never writes a served path or the database.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import numpy as np
import pytest

import efv_dataset as ed
import efv_model as em

ROOT = Path(__file__).resolve().parent


def _lab():
    spec = importlib.util.spec_from_file_location(
        "_efv_fwar_label_epoch_lab", ROOT / "tools" / "efv_fwar_label_epoch_lab.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # importing the lab runs nothing and leaves every flag at its default
    assert ed.NEVER_RESOLUTION_ARM_R is False and ed.SERVICE_ALIGNED_WINDOW is False
    assert em.NEUTRAL_MILB_IMPUTE is False and ed.LABEL_SEASONS_KEY == "seasons"
    return mod


# ---------------------------------------------------------------------------
# constants the registration fixes
# ---------------------------------------------------------------------------

def test_registered_constants():
    lab = _lab()
    assert lab.SEED == 20260807 and lab.TOST_MARGIN == 0.02
    assert lab.B_PERM_MIN == 2000 and lab.MIN_TIME_SPLITS == 4
    assert lab.BASES == ("ewar_v2", "fwar", "twin")          # no `nopp` under the substitution
    assert lab.INCUMBENT_KEY == "seasons_ewar_v2" and lab.CANDIDATE_KEY == "seasons"
    assert lab.OUT_PATH == ROOT / "data" / "xfv_fwar_label_epoch_eval.json"
    assert lab.BLAST_PATH == ROOT / "data" / "xfv_fwar_label_epoch_blast.json"
    assert lab.SNAP_DIR.name == "_pre_epoch_fwar_2026-10"
    assert lab.FORBIDDEN_SNAPSHOT_NAMES == ("_pre_epoch_2026-09", "_pre_epoch_2026-09-25")


# ---------------------------------------------------------------------------
# the twin: within (season, side)
# ---------------------------------------------------------------------------

def _cw():
    return {
        "a": {"seasons_ewar_v2": {"2015": 1.0, "2016": 2.0}, "seasons": {"2015": 1.5, "2016": 2.5}},
        "b": {"seasons_ewar_v2": {"2015": 0.0, "2016": 1.0}, "seasons": {"2015": -1.0, "2016": 1.0}},
        "c": {"seasons_ewar_v2": {"2015": 3.0}, "seasons": {"2015": 6.0}},
        # no kept incumbent: the fallback reads `seasons` and is counted
        "f": {"seasons": {"2015": 0.4, "2016": 0.6}},
        # the other side, with deltas that would be unmistakable if they crossed
        "p": {"seasons_ewar_v2": {"2015": 0.0, "2016": 0.0}, "seasons": {"2015": 50.0, "2016": 60.0}},
    }


def test_twin_permutes_deltas_within_season_and_side_only():
    lab = _lab()
    cw = _cw()
    side_keys = {"a", "b", "c", "f"}
    seen_different = False
    for seed in range(12):
        twin = lab.twin_series(cw, side_keys, np.random.default_rng(seed))
        assert set(twin) == side_keys                       # the other side is not in the twin
        for y in (2015, 2016):
            orig = sorted(lab._int_seasons(cw[k]["seasons"])[y] - lab.incumbent_series(cw[k])[0][y]
                          for k in side_keys if y in lab._int_seasons(cw[k]["seasons"]))
            got = sorted(twin[k][y] - lab.incumbent_series(cw[k])[0][y]
                         for k in side_keys if y in lab._int_seasons(cw[k]["seasons"]))
            assert got == pytest.approx(orig)              # the season's delta multiset survives
            assert all(abs(twin[k][y]) < 40 for k in side_keys if y in twin[k])   # no 50s crossed
        if any(abs(twin[k][2015] - lab._int_seasons(cw[k]["seasons"])[2015]) > 1e-9
               for k in side_keys):
            seen_different = True
    assert seen_different                                   # it is a permutation, not a copy


def test_build_series_counts_the_incumbent_fallback_and_the_moved_seasons():
    lab = _lab()
    built = lab.build_series(_cw(), {"a", "b", "c", "f"}, np.random.default_rng(1))
    assert built["receipts"]["players"] == 4
    assert built["receipts"]["incumbent_fallback_rows"] == 1           # "f"
    assert built["receipts"]["seasons"] == 7
    assert built["receipts"]["seasons_moved_by_the_basis"] == 4        # a:2, b:1, c:1
    assert built["series"]["ewar_v2"]["f"] == {2015: 0.4, 2016: 0.6}   # the fallback reads seasons
    assert lab.incumbent_series({"seasons_ewar_v2": {}, "seasons": {"2015": 1.0}}) == ({}, 0)


# ---------------------------------------------------------------------------
# clause (i): the residual identity and UNAVAILABLE
# ---------------------------------------------------------------------------

def _q(**kw):
    base = {k: None for k in _lab().Q_KEYS}
    base.update(kw)
    return base


def test_residual_identity_over_the_leave_one_out_effects():
    lab = _lab()
    q = {"Estar": _q(margin_debuted=0.30, rows=100), "E0": _q(margin_debuted=0.20, rows=90),
         "F1": _q(margin_debuted=0.27, rows=100), "F2": _q(margin_debuted=0.29, rows=95),
         "F3": _q(margin_debuted=0.28, rows=100), "F4": _q(margin_debuted=0.31, rows=100),
         "F5": _q(margin_debuted=0.30, rows=100)}
    t = lab.arm_table(q, {"omitted": {}})
    row = t["margin_debuted"]
    eff = {f: row["effects"][f]["effect"] for f in ("F1", "F2", "F3", "F4", "F5")}
    assert eff == pytest.approx({"F1": 0.03, "F2": 0.01, "F3": 0.02, "F4": -0.01, "F5": 0.0})
    assert row["total_move_Estar_minus_E0"] == pytest.approx(0.10)
    assert row["interaction_unattributed"] == pytest.approx(0.10 - sum(eff.values()))
    assert row["summed_over"] == ["F1", "F2", "F3", "F4", "F5"]
    assert "additivity" in row["interaction_note"]
    assert t["rows"]["interaction_unattributed"] == pytest.approx(10 - 5)
    assert t["n_debuted_scored"]["interaction_unattributed"] is None


def test_unavailable_on_an_omitted_or_missing_arm_is_never_inferred():
    lab = _lab()
    q = {"Estar": _q(margin_debuted=0.30), "E0": _q(margin_debuted=0.20),
         "F1": _q(margin_debuted=0.27), "F2": _q(margin_debuted=0.29),
         "F4": _q(margin_debuted=0.31), "F5": None}
    man = {"omitted": {"F3": {"reason": "BUST2 union invariant failed at step F: 4 rows"}}}
    row = lab.arm_table(q, man)["margin_debuted"]
    assert row["effects"]["F3"]["status"] == "UNAVAILABLE" and "effect" not in row["effects"]["F3"]
    assert "4 rows" in row["effects"]["F3"]["reason"] and "never inferred" in row["effects"]["F3"]["note"]
    assert row["effects"]["F5"]["status"] == "UNAVAILABLE" and "effect" not in row["effects"]["F5"]
    assert row["summed_over"] == ["F1", "F2", "F4"]
    assert row["interaction_unattributed"] == pytest.approx(0.10 - (0.03 + 0.01 - 0.01))
    # the candidates' own clauses say UNAVAILABLE too, and the sign rule cannot be read
    assert lab.arm_r_clauses("hit", [], None, np.random.default_rng(0), 5, {})["status"] == "UNAVAILABLE"
    assert lab.a1_clauses("hit", [], None, {})["status"] == "UNAVAILABLE"
    assert lab.a2_clauses("hit", [], None, {})["status"] == "UNAVAILABLE"
    assert lab.sign_agreement(lab.arm_table(q, man))["status"] == "UNAVAILABLE"


def test_sign_agreement_rule():
    lab = _lab()
    t = {"margin_debuted": {"effects": {"F4": {"effect": 0.01}, "F5": {"effect": -0.02}}}}
    s = lab.sign_agreement(t)
    assert s["disagree_in_sign"] is True and s["disposition"].startswith("neither ships")
    t = {"margin_debuted": {"effects": {"F4": {"effect": 0.01}, "F5": {"effect": 0.0}}}}
    assert lab.sign_agreement(t)["disagree_in_sign"] is False


def test_dispositions():
    lab = _lab()
    assert lab.tost_disposition([-0.01, 0.015]).startswith("RULED OUT")
    assert lab.tost_disposition([0.021, 0.05]) == "SWAP GAIN"
    assert lab.tost_disposition([-0.05, -0.021]) == "SWAP LOSS"
    assert lab.tost_disposition([-0.03, 0.01]) == "UNDECIDED" and lab.tost_disposition(None) == "UNDECIDED"
    assert lab.non_inferiority([-0.019, 0.01]) == "NON-INFERIOR"
    assert lab.non_inferiority([-0.05, -0.021]) == "INFERIOR"
    assert lab.non_inferiority([-0.03, 0.01]) == "UNDECIDED"


# ---------------------------------------------------------------------------
# the snapshot refusal
# ---------------------------------------------------------------------------

def test_blast_refuses_an_absent_snapshot_and_the_forbidden_names(monkeypatch, tmp_path):
    lab = _lab()
    monkeypatch.setattr(lab, "SNAP_DIR", tmp_path / "_pre_epoch_fwar_2026-10")
    with pytest.raises(SystemExit, match="no snapshot"):
        lab.blast(write=False)
    for bad in ("_pre_epoch_2026-09", "_pre_epoch_2026-09-25"):
        d = tmp_path / bad
        d.mkdir()
        (d / "xfv.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(lab, "SNAP_DIR", d)
        with pytest.raises(SystemExit, match="never read"):
            lab.blast(write=False)
    # a read that would escape the snapshot directory is refused
    ok = tmp_path / "_pre_epoch_fwar_2026-10"
    ok.mkdir()
    with pytest.raises(SystemExit, match="outside the snapshot"):
        lab._snap_load(ok, "../xfv.json")


def test_the_previous_snapshot_is_named_only_in_the_forbidden_tuple():
    src = inspect.getsource(_lab())
    lines = [ln for ln in src.splitlines() if "_pre_epoch_2026-09" in ln]
    assert len(lines) == 1 and "FORBIDDEN_SNAPSHOT_NAMES" in lines[0]


# ---------------------------------------------------------------------------
# the reporting path on fixtures that contain nulls
# ---------------------------------------------------------------------------

def _rows_with_nulls(side="hit"):
    return [
        {"player_key": "n1", "kind": "debuted", "target_resolved": None, "target_censored": None,
         "censored": None, "weight": None, "cutoff": None, "debut_year": None,
         "consensus_fv_raw": None, "milb": None},
        {"player_key": "n2", "kind": "debuted", "target_resolved": -0.5, "target_censored": -0.5,
         "censored": False, "weight": 1.0, "cutoff": "2017-05-01", "debut_year": 2017,
         "consensus_fv_raw": 45.0, "milb": None, "milb_unavailable": True},
        {"player_key": "n3", "kind": "debuted", "target_resolved": 2.0, "target_censored": 3.0,
         "censored": True, "weight": 0.5, "cutoff": "2022-09-01", "debut_year": 2022,
         "consensus_fv_raw": 50.0, "milb": {"level_rank": 4.0}},
        {"player_key": "b1", "kind": "bust", "target_resolved": 0.0, "target_censored": 0.0,
         "censored": False, "weight": 1.0, "bust_recent": False, "consensus_fv_raw": 40.0,
         "cutoff": None, "milb": None},
        {"player_key": "b2", "kind": "bust", "target_resolved": 0.0, "target_censored": 0.0,
         "censored": False, "weight": 0.5, "bust_recent": True, "consensus_fv_raw": None},
        {"player_key": "x", "kind": None, "target_resolved": None},
    ]


def test_reporting_path_survives_nulls():
    lab = _lab()
    rows = _rows_with_nulls()
    c = lab.row_census(rows)
    assert c["rows"] == 6 and c["debuted_rows"] == 3 and c["busts_in_pool"] == 1
    assert c["resolved_labels_le_0_share"] == 1.0          # n2 only; n1 has no label
    other = [dict(r) for r in rows]
    other[3]["bust_recent"] = True                          # F3 differs in one bust mark
    other[2]["censored"] = False                            # F4 differs in one censoring
    r = lab.arm_r_clauses("hit", rows, other, np.random.default_rng(0), 3, {})
    assert r["1_resolved_to_censored_count"] == 0 and r["1b_censored_to_resolved_count"] == 1
    assert "2_full_pool_bust_share" in r and "3_rank_clause" in r
    a1 = lab.a1_clauses("hit", rows, other, {"window_shifted": 2})
    assert a1["1_censoring_cost"]["resolved_to_censored"] == 1
    assert a1["1_censoring_cost"]["window_shifted_rows"] == 2
    assert "3_level_clause" in a1 or "2_disposition" in a1
    a2 = lab.a2_clauses("hit", rows, other, {})
    assert "level_clause" in a2
    q = lab.arm_quantities("hit", rows, {})
    assert q["rows"] == 6 and q["margin_debuted"] is None    # no fold survives the floors
    assert lab.label_date_for(rows[0]) is None
    assert lab.relabel(rows, {"n2": {2017: 1.0}}, {})[0]["target_resolved"] is None
    assert lab.parity_mismatches(rows, rows) == []


# ---------------------------------------------------------------------------
# relabelling reproduces the build's rule
# ---------------------------------------------------------------------------

def test_relabel_reproduces_the_label_rule_and_the_terminal_override():
    rt0 = ed.RESOLVED_THROUGH
    # 86226bb2 (the fWAR label epoch) moved the module clock from 2025 to 2026.
    assert rt0 == 2026
    lab = _lab()
    seasons = {2019: 0.5, 2020: 1.0, 2021: 1.5, 2022: 2.0, 2023: 2.5, 2024: 3.0, 2025: 3.5}
    plain = {"player_key": "p", "kind": "debuted", "debut_year": 2019, "cutoff": "2019-09-20",
             "target_resolved": 0, "target_censored": 0, "censored": True, "weight": 0.1}
    flags_off = {"efv_dataset.SERVICE_ALIGNED_WINDOW": False, "efv_dataset.RESOLVED_THROUGH": 2025}
    got = lab.relabel([plain], {"p": seasons}, flags_off)[0]
    assert (got["target_resolved"], got["target_censored"], got["censored"], got["weight"],
            got["observed_seasons"]) == ed._label_6yr(seasons, 2019, None)
    assert got["censored"] is False and got["target_resolved"] == 10.5
    # the arm's own window rule: A1 on shifts the September debut to 2020..2025 plus the stub
    flags_a1 = {"efv_dataset.SERVICE_ALIGNED_WINDOW": True, "efv_dataset.RESOLVED_THROUGH": 2025}
    on = lab.relabel([plain], {"p": seasons}, flags_a1)[0]
    assert on["target_resolved"] == 14.0 and ed.SERVICE_ALIGNED_WINDOW is False
    # a re-dated window (debut_year is not the cutoff's year) passes no date, so A1 cannot
    # shift it twice; a placeholder day and a rerouted bust pass none either
    assert lab.label_date_for(dict(plain, debut_year=2020)) is None
    assert lab.label_date_for(dict(plain, debut_date_is_placeholder=True)) is None
    assert lab.label_date_for(dict(plain, rerouted_from_bust=True)) is None
    assert lab.label_date_for(plain) == "2019-09-20"
    # RESOLVED_THROUGH from the flags: at 2026 a 2021 debut resolves, at 2025 it does not
    row21 = dict(plain, debut_year=2021, cutoff="2021-04-01")
    s21 = {y: 1.0 for y in range(2021, 2027)}
    assert lab.relabel([row21], {"p": s21}, {"efv_dataset.RESOLVED_THROUGH": 2026})[0]["censored"] is False
    assert lab.relabel([row21], {"p": s21}, {"efv_dataset.RESOLVED_THROUGH": 2025})[0]["censored"] is True
    assert ed.RESOLVED_THROUGH == rt0     # relabel's flag overrides restore the module clock
    # the terminal override: a censored row with a terminal transaction resolves at its sum
    term = dict(row21, terminal_resolved="2024-03-01")
    t = lab.relabel([term], {"p": s21}, {"efv_dataset.RESOLVED_THROUGH": 2025})[0]
    assert t["censored"] is False and t["weight"] == 1.0 and t["target_censored"] == t["target_resolved"]
    assert lab.parity_mismatches([t], [t]) == [] and lab.parity_mismatches([t], [dict(t, weight=0.5)]) == ["p"]


# ---------------------------------------------------------------------------
# A2 at fit: per fold, the milb_unavailable rows only
# ---------------------------------------------------------------------------

def test_a2_imputes_unavailable_rows_at_the_train_fold_mean_only():
    lab = _lab()
    keys = ["fv", "level_rank"]

    def _p(pk, level, unavailable=False):
        return {"player_key": pk, "feats": {"fv": 45.0, "level_rank": level,
                                            "milb_unavailable": 1.0 if unavailable else 0.0,
                                            "milb_missing": 0.0}}
    prep = [_p("h1", 3.0), _p("h2", 5.0), _p("u1", 0.0, True), _p("t1", 4.0), _p("tu", 0.0, True)]
    X = np.array([[p["feats"][k] for k in keys] for p in prep], dtype=float)
    D = {"keys": keys, "prep": prep, "X": X}
    tr, te = np.array([0, 1, 2]), np.array([3, 4])
    Xtr, Xte = lab.fold_X(D, tr, te, True)
    assert Xtr[:, 1].tolist() == [3.0, 5.0, 4.0]          # u1 at the train has-MiLB mean 4.0
    assert Xte[:, 1].tolist() == [4.0, 4.0]               # tu imputed at the same mean, t1 untouched
    Xtr0, Xte0 = lab.fold_X(D, tr, te, False)
    assert Xtr0.tolist() == X[tr].tolist() and Xte0.tolist() == X[te].tolist()
    assert em.NEUTRAL_MILB_IMPUTE is False


# ---------------------------------------------------------------------------
# what the lab never does
# ---------------------------------------------------------------------------

def test_the_lab_never_writes_a_served_path_the_database_or_a_document():
    lab = _lab()
    src = inspect.getsource(lab)
    writes = [ln for ln in src.splitlines() if ".write_text(" in ln]
    assert len(writes) == 2
    assert any("OUT_PATH.write_text" in ln for ln in writes)
    assert any("BLAST_PATH.write_text" in ln for ln in writes)
    assert "matrix_path(" not in src.replace("manifest_path(", "")
    assert "upsert" not in src and "INSERT" not in src and "UPDATE " not in src
    assert "run_backtest" not in src
    # the database is touched by exactly one read, the career_war select
    assert src.count("storage.connect(") == 1
    assert "select player_key, payload_json from career_war" in src
    assert ".md\").write" not in src and "FWAR_LABEL_EPOCH_GATE.md" in src
    # strata never include an FV cell
    assert "never a consensus-FV cell" in src
