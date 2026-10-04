# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the MC-5 pricing read (tools/efv_v2_pricing_calibration.py, EFV3_C05;
docs/efv-v2/MODEL_CLASS_SCREEN.md "MC-5, pricing calibration by position and age").
Synthetic rows for every fit; the served artifact and ledger rows are read, never written.

1. order_idx (and u_c, the heads and the eFV grade) bit-identical with and without the
   pricing term.
2. The position read is dated inside the frame window (before the row's window_end on
   lv, on or before the read on vm); the record's undated position is never read; the
   pitcher role reads only MiLB seasons that had ended by the read.
3. The family dummies and age are continuous columns on the line, never a table by
   grade; no strata other than position family and age band; no FV-cell key.
4. The reserved guards raise (R-LV list vintages, R-VM 2025+ years, a non-frozen label).
5. The conftest restore list carries data/efv_progress.json and the new artifact, and
   the writer's OUT_PATH is redirected.
6. The served artifact's schema and the ledger rows copied from it.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

import efv_progress as P
import efv_v2_candidates as C
import efv_v2_model as H
import efv_vintage_frame as F

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
import efv_v2_pricing_calibration as T  # noqa: E402

SRC = ROOT / "tools" / "efv_v2_pricing_calibration.py"
ART = ROOT / "data" / "efv_v2_pricing_calibration_eval.json"
SERVED = ROOT / "data" / "efv_progress.json"
WEIGHTS = {"hit": {"w_skill": 0.5, "w_time": 0.2}, "pit": {"w_skill": 0.5, "w_time": 0.2}}
_FV_CELL = re.compile(r"(?:^|[^0-9])(?:35|40|45|50|55|60|65|70)(?:\+|plus)?(?:$|[^0-9])"
                      r"|tier|fv_cell|fv_bucket", re.IGNORECASE)


# ---------------------------------------------------------------------------
# synthetic rows (the shape efv_v2_model.fit_v2 consumes)
# ---------------------------------------------------------------------------

def _rows(side="hit", years=range(2011, 2017), n=120, seed=5):
    rng = np.random.default_rng(seed)
    out, i = [], 0
    for yr in years:
        for _ in range(n):
            fv = float(rng.normal(45, 5))
            th = float(rng.normal(50, 8))
            kr = float(rng.normal(0, 0.05))
            drv = 0.08 * (th - 50) if side == "hit" else 20.0 * kr
            t = 0.1 * (fv - 45) + drv + float(rng.normal(0, 1))
            feats = {"milb_unavailable": 0.0, "milb_missing": 0.0, "obp_rel": 0.0,
                     "k_rel": kr, "peak_k_rel": kr, "level_rank": float(rng.integers(0, 6)),
                     "age_rel_level": float(rng.normal(0, 1)), "tool_hit": th,
                     "tool_speed": 48.0, "is_college": 0.0, "is_ifa": 0.0,
                     "pick_missing": 1.0}
            extra = {"bmi": 25.0, "pl_rev": None, "on_40man": 0.0, "nov_add": 0.0}
            out.append({"player_key": f"{side}{i}", "decision_year": yr, "fv": fv,
                        "target": t, "reached": float(t > 0.5), "weight": 1.0,
                        "feats": feats, "extra": extra, "v2": H.v2_row(feats, extra),
                        "frame": "lv", "ids_outcome_blind": True})
            i += 1
    return out


@pytest.fixture(scope="module")
def train():
    return _rows()


@pytest.fixture(scope="module")
def test_rows():
    return _rows(years=(2017,), n=200, seed=9)


# ---------------------------------------------------------------------------
# 1. order_idx bit-identical
# ---------------------------------------------------------------------------

def test_order_idx_bit_identical_with_and_without_the_term(train, test_rows):
    rng = np.random.default_rng(1)
    fams = [str(rng.choice(["corner", "middle", "other"])) for _ in train]
    ages = [None if k % 7 == 0 else float(rng.normal(21, 2)) for k in range(len(train))]
    model = H.fit_v2(train, "hit", frame="lv", weights=WEIGHTS, absent_ok=False)
    pr = C.fit_mc5_pricing(train, fams, ages, side="hit")
    ft = [str(rng.choice(["corner", "middle", "other"])) for _ in test_rows]
    at = [float(rng.normal(21, 2)) for _ in test_rows]
    without = H.predict_v2(model, test_rows)
    with_term = C.predict_mc5(C.attach_mc5(model, pr), test_rows, ft, at)
    a = np.array([o["order_idx"] for o in without], dtype=np.float64)
    b = np.array([o["order_idx"] for o in with_term], dtype=np.float64)
    assert a.tobytes() == b.tobytes()
    for key in ("u_c", "e_skill", "e_time", "efv_grade"):
        assert [o[key] for o in with_term] == [o[key] for o in without], key
    assert T._order_identical(without, with_term)
    assert any(o["efv_war"] != o["efv_war_v2"] for o in with_term)
    # the tool's base price is predict_v2's own, untouched
    assert [o["efv_war_v2"] for o in with_term] == [o["efv_war"] for o in without]


# ---------------------------------------------------------------------------
# 2. the dated reads
# ---------------------------------------------------------------------------

LISTINGS = {"p1": [("2016-12-01", "mlb_pipeline", "C"),
                   ("2017-03-01", "fangraphs", "CF"),
                   ("2017-03-01", "mlb_pipeline", "SS/2B"),
                   ("2017-06-01", "mlb_pipeline", "1B"),
                   ("2018-03-01", "mlb_pipeline", "LF")]}


class _Roles(T.MilbRoles):
    def __init__(self, idx):
        super().__init__()
        self._idx = idx


def test_position_read_is_dated_inside_the_frame_window():
    row = {"player_key": "p1", "side": "hit", "window": ["2017-01-01", "2017-05-01"],
           "asof_date": "2017-04-15", "birth_date": "1997-04-15", "mlbam_id": None,
           "position": "LF"}
    cv = T.lv_covariates(row, LISTINGS, _Roles({}))
    lst = cv["listing"]
    assert row["window"][0] <= lst["date"] < row["window"][1]
    # same-day tie goes to the earlier source in LISTING_SOURCES; first token read
    assert lst == {"position": "SS/2B", "date": "2017-03-01", "source": "mlb_pipeline"}
    assert cv["family"] == "middle" and cv["family_how"] == "listing"
    # the record's own (undated) position, LF, is never what is read
    assert cv["family"] != C.position_family("LF", "hit")
    assert cv["age"] == pytest.approx(20.0, abs=0.01)
    # a window that closes before any in-range listing reads nothing, never a later one
    early = dict(row, window=["2017-01-01", "2017-02-01"], asof_date="2017-01-20")
    assert T.lv_covariates(early, LISTINGS, _Roles({}))["listing"] is None
    # vm: on or before the read date, inside the lookback
    raw = {"player_key": "p1", "mlbam_id": None, "birth_date": "1997-04-15"}
    vm = T.vm_covariates("hit", raw, "2017-05-31", LISTINGS, _Roles({}))
    assert vm["listing"]["date"] <= "2017-05-31" and vm["listing"]["position"] == "SS/2B"
    assert T.vm_covariates("hit", raw, "2017-06-01", LISTINGS, _Roles({}))["listing"][
        "position"] == "1B"
    assert T.vm_covariates("hit", raw, None, LISTINGS, _Roles({}))["family"] is None


def test_pitcher_role_reads_only_seasons_ended_by_the_read():
    idx = {2016: {7: [{"level": "AA", "g": 30, "gs": 2}, {"level": "MLB", "g": 5, "gs": 5}]},
           2017: {7: [{"level": "AAA", "g": 20, "gs": 20}]}}
    roles = _Roles(idx)
    r = roles.role(7, "2017-03-01")
    assert r == {"family": "rp", "season": 2016, "g": 30, "gs": 2}
    assert roles.role(7, "2017-10-15")["family"] == "sp"     # 2017 had ended by then
    assert roles.role(7, "2017-09-30")["season"] == 2016     # not yet
    assert roles.role(None, "2017-03-01") is None
    row = {"player_key": "p9", "side": "pit", "window": ["2017-01-01", "2017-05-01"],
           "asof_date": "2017-03-01", "birth_date": None, "mlbam_id": 7}
    cv = T.lv_covariates(row, {"p9": [("2017-02-01", "fangraphs", "SP")]}, roles)
    assert cv["family"] == "rp" and cv["family_how"] == "milb_gs_share" and cv["age"] is None
    cv2 = T.lv_covariates(dict(row, mlbam_id=None),
                          {"p9": [("2017-02-01", "fangraphs", "SIRP")]}, roles)
    assert cv2["family"] == "rp" and cv2["family_how"] == "listing"


# ---------------------------------------------------------------------------
# 3. continuous columns on the line; strata
# ---------------------------------------------------------------------------

def test_dummies_are_continuous_columns_on_the_line_never_a_table_by_grade(train):
    rng = np.random.default_rng(2)
    fams = [str(rng.choice(["corner", "middle", "other"])) for _ in train]
    ages = [float(rng.normal(21, 2)) for _ in train]
    pr = C.fit_mc5_pricing(train, fams, ages, side="hit")
    assert pr["columns"] == ["intercept", "fv", "family:middle", "family:other",
                             "age_at_read"]
    grid = np.linspace(30.0, 70.0, 41)
    for fam in ("corner", "middle", "other"):
        w = C.mc5_war(pr, grid, [fam] * grid.size, [21.0] * grid.size)
        assert np.allclose(np.diff(w), pr["b"] * np.diff(grid))
    # the tool groups by family and age band only: no grade enters a grouping key
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert not re.search(r"fv_cell|fv_bucket|\btier\b", node.value), node.value
    src = SRC.read_text(encoding="utf-8")
    for bad in ("round(r[\"fv\"]", "efv_grade\"])]", "groupby"):
        assert bad not in src


# ---------------------------------------------------------------------------
# 4. the reserved guards
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("folds", [[2020], [2019, 2021], [2022]])
def test_lv_guard_raises_on_a_reserved_vintage(folds):
    with pytest.raises(F.ReservedFrameError):
        T.guard_lv_folds(folds)


@pytest.mark.parametrize("years", [[2025], [2023, 2026]])
def test_vm_guard_raises_on_r_vm(years):
    with pytest.raises(F.ReservedFrameError):
        T.guard_vm_years(years)


def test_guards_pass_development_years_and_training_guard_raises(train):
    assert T.guard_lv_folds([2017, 2018, 2019]) == [2017, 2018, 2019]
    assert T.guard_vm_years(range(2017, 2025)) == list(range(2017, 2025))
    bad = [dict(train[0], decision_year=2025)]
    with pytest.raises(F.ReservedFrameError):
        C.guard_training_rows(bad, "vm")
    with pytest.raises(F.ReservedFrameError):
        C.guard_training_rows([dict(train[0], decision_year=2020)], "lv")
    with pytest.raises(F.ReservedFrameError):
        C.fit_mc5_pricing(bad * 20, [None] * 20, [None] * 20, side="hit")


def test_run_refuses_a_label_other_than_the_frozen_one(monkeypatch):
    monkeypatch.setattr(T.L, "provider", lambda: "ewar_v2")
    with pytest.raises(RuntimeError, match="frozen"):
        T.run()


# ---------------------------------------------------------------------------
# 5. conftest
# ---------------------------------------------------------------------------

def test_conftest_restore_list_carries_the_ledger_and_the_artifact():
    import conftest
    assert "data/efv_progress.json" in conftest._SIDECAR_GLOBS
    assert "data/efv_v2_pricing_calibration_eval.json" in conftest._SIDECAR_GLOBS
    assert ("tools.efv_v2_pricing_calibration", "OUT_PATH",
            "data/efv_v2_pricing_calibration_eval.json") in conftest._SIDECAR_WRITE_TARGETS


# ---------------------------------------------------------------------------
# 6. the served artifact and the ledger rows
# ---------------------------------------------------------------------------

def _art():
    if not ART.exists():
        pytest.skip("data/efv_v2_pricing_calibration_eval.json not built")
    return json.loads(ART.read_text(encoding="utf-8"))


def _keys(o, out):
    if isinstance(o, dict):
        for k, v in o.items():
            out.append(str(k))
            _keys(v, out)
    elif isinstance(o, list):
        for v in o:
            _keys(v, out)
    return out


def test_artifact_schema_and_frames():
    doc = _art()
    for k in ("generated_at", "label", "code", "frames", "model_id", "note"):
        assert doc.get(k), k
    assert doc["model_id"] == T.MODEL_ID and doc["role"] == "development"
    assert doc["metric"] == "mae" and doc["adjudicates"] is False
    assert doc["exploratory"] is False and doc["label"]["provider"] == T.FROZEN_PROVIDER
    assert doc["code"]["commit"] and doc["note"] == T.NOTE
    g = doc["reserved_guard"]
    assert max(g["lv_vintages_read"]) < min(F.RESERVED_LV)
    assert max(g["vm_years_read"]) < F.R_VM_FIRST_DEBUT_YEAR
    assert set(doc["frames"]) == set(T.FRAMES)
    for fid, f in doc["frames"].items():
        for k in ("n", "mae_base", "mae_position_age", "delta", "ci95", "per_family"):
            assert f.get(k) is not None, (fid, k)
        assert f["delta"] == pytest.approx(f["mae_position_age"] - f["mae_base"], abs=2e-4)
        assert f["ci95"][0] <= f["ci95"][1]
        assert sum(c["n"] for c in f["per_family"].values()) == f["n"]
        assert sum(c["n"] for c in f["per_age_band"].values()) == f["n"]
        for name, c in f["per_family"].items():
            side, fam = name.split(":")
            assert fam in C.MC5_FAMILIES[side] + ("unknown",)
            assert {"n", "mean_resid_base", "mean_resid_new"} <= set(c)
        for name in f["per_age_band"]:
            assert name.split(":")[1] in ("<=18", "19-20", "21-22", "23-24", ">=25",
                                          "unknown")
        assert all(p["order_idx_bit_identical"] for p in f["per_fold"])
    bad = [k for k in _keys(doc, []) if _FV_CELL.search(k)]
    assert not bad, bad
    text = ART.read_text(encoding="utf-8")
    assert "—" not in text and "–" not in text


def test_ledger_rows_copy_the_artifact():
    doc = _art()
    rows = P.build_pricing_rows(doc, sources=[], date="2026-10-03", trigger="efv_change",
                                now_iso="2026-10-03T00:00:00Z")
    assert [r["frame"] for r in rows] == list(P.PRICING_FRAMES)
    for r in rows:
        f = doc["frames"][r["frame"]]
        assert r["model_id"] == "efv_v2_pricing_pos_age" and r["role"] == "development"
        assert r["metric"] == "mae" and r["raters"] == {} and r["deltas"] == {}
        assert r["note"] == "pricing calibration, MAE diagnostic, no rank claim; order_idx unchanged"
        for k in P.PRICING_FIELDS:
            assert r["pricing"][k] == f.get(k), k
        assert r["content_hash"] == P.content_hash(r)
    assert P.build_pricing_rows(dict(doc, exploratory=True), sources=[], date="2026-10-03",
                                trigger="efv_change", now_iso="x") == []
    if SERVED.exists():
        served = json.loads(SERVED.read_text(encoding="utf-8"))
        mine = [r for r in served["rows"] if r.get("model_id") == T.MODEL_ID]
        for r in mine:
            assert r["role"] == "development" and r["metric"] == "mae"
            assert r["raters"] == {} and r["deltas"] == {}
            assert r["content_hash"] == P.content_hash(r)
            if r["sources"] and r["sources"][0].get("generated_at") == doc["generated_at"]:
                f = doc["frames"][r["frame"]]
                assert all(r["pricing"][k] == f.get(k) for k in P.PRICING_FIELDS)


def test_mae_delta_is_seeded_and_paired():
    keys = [f"k{i // 2}" for i in range(200)]
    rng = np.random.default_rng(4)
    eb = rng.normal(0, 1, 200)
    en = eb * 0.9
    a = T.mae_delta(keys, eb, en, B=200)
    b = T.mae_delta(keys, eb, en, B=200)
    assert a == b and a["n_clusters"] == 100
    assert a["delta"] < 0 and a["ci95"][1] < 0
