# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the eFV tracking-era head (efv5_tracking_head.py, EFV5_TRACKING_HEAD;
docs/efv-v2/EFV_TRACKING_HEAD_GATE.md).

1. The registration: the document exists, carries its status line and the constants the
   producer declares (N, the cohorts, the penalty grid, the candidates).
2. Labels and rows: reach3 and rate3 by the registered rule; a MLB line at or before S is
   no row; the spent flag follows the window; the higher tracked level wins a season.
3. The model: a penalty of infinity zeroes the metric columns; the fit recovers a planted
   signal; selection ties go to the larger penalty; the held-out design uses the training
   moments and imputes an absent metric at z = 0.
4. The ship rule: four strict inequalities; unreadable or a consensus-only head never ships.
5. Bans: the switch is off; no served module imports the producer; no grouping by
   consensus-FV level; no backtest, no fetch, no em-dash.
6. The artifact, when present: development only, nothing served, the verdict equals the
   rule applied to its own numbers, every held-out number labelled spent, no em-dash.
No test touches the network or the database.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import efv5_tracking_head as T  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

SRC = ROOT / "efv5_tracking_head.py"
TEST_SRC = Path(__file__)
GATE = ROOT / "docs" / "efv-v2" / "EFV_TRACKING_HEAD_GATE.md"


def _rows(n=300, seed=7, side="pit"):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        fv = float(rng.choice([40, 45, 50, 55, 60]))
        lv = "AAA" if rng.uniform() < 0.5 else "A"
        m = {k: float(rng.normal()) for k in T.metrics_of(side)}
        if side == "pit" and rng.uniform() < 0.3:
            m["arm_angle"] = None
        z = 0.08 * (fv - 50) + 1.2 * m[T.CORE[side][0]] + (0.5 if lv == "AAA" else 0.0)
        reach = float(rng.uniform() < 1.0 / (1.0 + math.exp(-z)))
        rate = (0.5 + 0.5 * m[T.CORE[side][1]] + rng.normal() * 0.5) if reach else 0.0
        rows.append({"pid": i, "season": 2021 if i % 2 else 2022, "level": lv,
                     "player_key": str(i), "fv": fv, "group": "SP", "m": m,
                     "reach3": reach, "rate3": rate, "spent": False, "role": "train"})
    return rows


# ---------------------------------------------------------------------------
# the registration
# ---------------------------------------------------------------------------

def test_registration_exists_and_declares_the_producer_constants():
    text = GATE.read_text(encoding="utf-8")
    assert "Registration status: REGISTERED" in text
    assert "N = 3" in text and T.N_SEASONS == 3
    assert "2021" in text and "2022" in text and "2023" in text
    assert T.TRAIN_COHORTS == (2021, 2022) and T.HOLDOUT_COHORT == 2023
    assert "{1, 3, 10, 30, 100, 300, infinity}" in text
    assert T.LAMBDAS == (1.0, 3.0, 10.0, 30.0, 100.0, 300.0, math.inf)
    for k in T.CORE["pit"] + T.IMPUTED["pit"] + T.CORE["hit"]:
        assert f"`{k}`" in text, k
    assert "0.5 * u(V2 order_idx) + 0.5 * u(order_head)" in text and T.BLEND_W == 0.5
    assert chr(0x2014) not in text


# ---------------------------------------------------------------------------
# labels and rows
# ---------------------------------------------------------------------------

def test_labels_by_the_registered_rule():
    mlb = {1: {2023, 2024, 2027}, 2: {2020, 2023}, 3: {2025}, 4: set()}
    war = {(1, 2023): 1.0, (1, 2024): 3.0, (1, 2027): 9.0}
    assert T.labels3(1, 2021, mlb, war) == {"reach3": 1.0, "rate3": 2.0}     # 2027 outside
    assert T.labels3(2, 2021, mlb, war) is None                              # MLB at or before S
    assert T.labels3(3, 2021, mlb, war) == {"reach3": 0.0, "rate3": 0.0}     # debut after S+3
    assert T.labels3(3, 2022, mlb, war) == {"reach3": 1.0, "rate3": 0.0}
    assert T.labels3(4, 2023, mlb, war) == {"reach3": 0.0, "rate3": 0.0}


def test_spent_follows_the_window():
    assert not T.spent(2021)
    assert T.spent(2022) and T.spent(2023)
    assert F.R_VM_FIRST_DEBUT_YEAR == 2025


def test_pick_rows_takes_the_higher_level_and_needs_every_core_metric():
    full = {f"trk_{k}_pit": 1.0 for k in T.CORE["pit"]}
    trk = {(1, 2022, "A"): dict(full, trk_astuff_plus_pit=5.0),
           (1, 2022, "AAA"): dict(full, trk_astuff_plus_pit=9.0),
           (2, 2022, "A"): {"trk_astuff_plus_pit": 1.0},
           (3, 2024, "A"): dict(full),
           (4, 2021, "AA"): dict(full)}
    out = T.pick_rows(trk, "pit")
    assert set(out) == {(1, 2022)}
    assert out[(1, 2022)][0] == "AAA" and out[(1, 2022)][1]["astuff_plus"] == 9.0
    assert out[(1, 2022)][1]["arm_angle"] is None


# ---------------------------------------------------------------------------
# the model
# ---------------------------------------------------------------------------

def test_infinite_penalty_switches_the_metrics_off():
    rows = _rows()
    mom = T.moments(rows, "pit")
    X = T.design(rows, "pit", mom)
    y = np.array([r["reach3"] for r in rows])
    w = T.fit_logistic(X, y, math.inf)
    assert np.all(w[T.N_FIXED:] == 0.0) and w[2] > 0          # consensus still carries
    ww = T.fit_ridge(X[y > 0], np.array([r["rate3"] for r in rows])[y > 0], math.inf)
    assert np.all(ww[T.N_FIXED:] == 0.0)


def test_fit_recovers_a_planted_signal_and_reports_it():
    rows = _rows(n=500)
    sel = T.select_penalties(rows, "pit", log=lambda s: None)
    fit = T.fit_final(rows, "pit", sel["_lam_r"], sel["_lam_w"])
    cols = fit["columns"]
    assert cols[:3] == ["intercept", "aaa", "consensus_fv"]
    j = cols.index(T.CORE["pit"][0])
    assert fit["w_reach"][j] > 0.5 and abs(fit["w_reach"][j]) == max(abs(v) for v in fit["w_reach"][3:])
    k = cols.index(T.CORE["pit"][1])
    assert abs(fit["w_rate"][k]) == max(abs(v) for v in fit["w_rate"][3:])
    rep = T.weight_report(rows, "pit", fit, sel["_lam_r"], sel["_lam_w"])
    carried = {(r["head"], r["metric"]) for r in rep if r["carries_weight"]}
    assert ("reach", T.CORE["pit"][0]) in carried and ("rate", T.CORE["pit"][1]) in carried


def test_selection_ties_go_to_the_larger_penalty():
    assert T._argmax_last([0.6, 0.7, 0.7, 0.65, 0.5, 0.5, 0.4]) == 10.0
    assert T._argmax_last([0.5] * 7) == math.inf
    assert T._argmax_last([None, 0.5, None, 0.5, None, None, None]) == 30.0


def test_held_out_design_uses_training_moments_and_imputes_at_zero():
    rows = _rows(n=120)
    mom = T.moments(rows, "pit")
    held = [{"pid": 9999, "season": 2023, "level": "A", "player_key": "x", "fv": mom["fv"][0],
             "group": None, "m": {k: mom[k][0] for k in T.CORE["pit"]} | {"arm_angle": None},
             "reach3": 0.0, "rate3": 0.0, "spent": True, "role": "holdout"}]
    X = T.design(held, "pit", mom)
    assert X.shape == (1, 3 + len(T.metrics_of("pit")))
    assert X[0, 0] == 1.0 and X[0, 1] == 0.0
    assert np.allclose(X[0, 2:], 0.0)


# ---------------------------------------------------------------------------
# the ship rule
# ---------------------------------------------------------------------------

def _held(head, cons, v2):
    return {"scores": {"head": {"auc_reach3": head[0], "rho_rate3": head[1]},
                       "consensus": {"auc_reach3": cons[0], "rho_rate3": cons[1]},
                       "v2": {"auc_reach3": v2[0], "rho_rate3": v2[1]}}}


def test_ship_rule_is_four_strict_inequalities():
    sel = {"lambda_R": 3.0, "lambda_W": "inf"}
    assert T.ship_verdict(_held((0.7, 0.3), (0.65, 0.25), (0.66, 0.28)), sel, readable_ok=True)["ships"]
    assert not T.ship_verdict(_held((0.7, 0.3), (0.7, 0.25), (0.66, 0.28)), sel, readable_ok=True)["ships"]
    assert not T.ship_verdict(_held((0.7, 0.3), (0.65, 0.25), (0.66, 0.31)), sel, readable_ok=True)["ships"]
    v = T.ship_verdict(_held((0.7, 0.3), (0.65, 0.25), (0.66, 0.28)), sel, readable_ok=False, why_unreadable="x")
    assert not v["ships"] and "unreadable" in v["reason"]
    v = T.ship_verdict(_held((0.9, 0.9), (0.1, 0.1), (0.1, 0.1)), {"lambda_R": "inf", "lambda_W": "inf"}, readable_ok=True)
    assert not v["ships"] and "infinity" in v["reason"]


def test_readable_thresholds():
    rows = [{"reach3": 1.0 if i < 12 else 0.0} for i in range(60)]
    assert T.readable(rows) == (True, None)
    assert not T.readable(rows[:49])[0]
    assert not T.readable([{"reach3": 1.0} for _ in range(60)])[0]
    assert not T.readable([{"reach3": 0.0} for _ in range(60)])[0]


# ---------------------------------------------------------------------------
# bans
# ---------------------------------------------------------------------------

def test_switch_is_off_and_the_served_hook_is_guarded():
    """The switch is off; no served module imports the producer at module level, and the
    one served hook (efv_v2_serve._tracking_head) returns before any read while it is off."""
    assert T.EFV_TRACKING_HEAD_ON is False
    for name in ("efv_export.py", "efv_score.py", "efv_v2_model.py", "efv_v2_serve.py",
                 "build_site.py", "source_backtest.py", "storage.py", "run_monthly.py"):
        p = ROOT / name
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                assert not line.startswith(("import efv5_tracking_head", "from efv5_tracking_head")), (name, line)
    import efv_v2_serve as S
    rows = [{"player_key": "a", "decision_year": 2026, "fv": 50.0, "mlbam_id": 1}]
    preds = [{"player_key": "a", "order_idx": 0.5, "efv_grade": 50.0, "efv_war": 1.0}]
    assert S._tracking_head("pit", rows, preds, {}) == [[]]
    assert preds == [{"player_key": "a", "order_idx": 0.5, "efv_grade": 50.0, "efv_war": 1.0}]


def test_source_bans():
    src = SRC.read_text(encoding="utf-8")
    assert chr(0x2014) not in src and chr(0x2014) not in TEST_SRC.read_text(encoding="utf-8")
    assert not re.compile(r"(by|per|group)_?(fv|consensus|grade)").search(src)
    assert not re.search(r"fv_cell|fv_tier|fv_bucket", src)
    for banned in ("import backtest", "run_backtest", "import efv_export", "import proj_export",
                   "train_proj_models", "import efv_score", "import storage", "urlopen",
                   "requests."):
        assert banned not in src, banned
    assert set(T.CONSENSUS_VINTAGES).isdisjoint(F.RESERVED_LV)
    assert T.CONSENSUS_VINTAGES == (2022, 2023, 2024)


# ---------------------------------------------------------------------------
# the artifact, when present
# ---------------------------------------------------------------------------

def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


@pytest.fixture(scope="module")
def artifact():
    if not T.OUT_PATH.exists():
        pytest.skip("no artifact")
    return json.loads(T.OUT_PATH.read_text(encoding="utf-8"))


def test_artifact_is_development_only(artifact):
    assert artifact["role"] == "development" and artifact["served"] is False
    assert artifact["flag"] == {"EFV_TRACKING_HEAD_ON": False}
    assert artifact["status"] == "complete"
    assert artifact["declared"]["train_cohorts"] == [2021, 2022]
    assert artifact["declared"]["holdout_cohort"] == 2023
    assert artifact["registration"]["doc"] == "docs/efv-v2/EFV_TRACKING_HEAD_GATE.md"


def test_artifact_names_no_fv_cell_and_no_emdash(artifact):
    for s in _strings(artifact):
        assert chr(0x2014) not in s
        assert not re.search(r"\bFV (45|50|55|60|65)\b", s), s


def test_artifact_verdict_equals_the_rule_on_its_own_numbers(artifact):
    for side in ("hit", "pit"):
        held = artifact["holdout"][side]
        v = artifact["verdict"][side]
        ok = held.get("readable", False)
        expect = T.ship_verdict(held if ok else None, artifact["selection"][side],
                                readable_ok=ok, why_unreadable=held.get("unreadable_reason"))
        assert v["ships"] == expect["ships"], side
        if ok:
            assert held["spent"] is True and held["seasons"] == [2023]
            assert held["n"] >= T.MIN_ROWS
    assert artifact["ships_any_side"] == any(artifact["verdict"][s]["ships"] for s in ("hit", "pit"))


def test_artifact_selection_is_on_the_grid_and_training_only(artifact):
    grid = {1.0, 3.0, 10.0, 30.0, 100.0, 300.0, "inf"}
    for side in ("hit", "pit"):
        sel = artifact["selection"][side]
        assert sel["lambda_R"] in grid and sel["lambda_W"] in grid
        assert len(sel["curve_R"]) == 7 and len(sel["curve_W"]) == 7
        dev = artifact["development"][side]
        assert set(dev["seasons"]) <= {2021, 2022}
        for c in artifact["frame"][side]:
            assert c["role"] == ("holdout" if c["season"] == 2023 else "train")
            assert c["spent"] == (c["season"] >= 2022)


# ---------------------------------------------------------------------------
# the served path, dark
# ---------------------------------------------------------------------------

def _fake_fit(side="pit"):
    cols = ["intercept", "aaa", "consensus_fv"] + list(T.metrics_of(side))
    return {"columns": cols, "moments": {k: [0.0, 1.0] for k in ["fv"] + list(T.metrics_of(side))},
            "w_reach": [0.0, 0.5, 1.0] + [1.0] + [0.0] * (len(cols) - 4),
            "w_rate": [1.0, 0.0, 0.5] + [0.0] * (len(cols) - 3)}


def _live(n=12):
    rng = np.random.default_rng(3)
    rows, preds = [], []
    for i in range(n):
        rows.append({"player_key": f"p{i}", "decision_year": 2026, "fv": float(40 + 5 * (i % 5)),
                     "mlbam_id": 1000 + i})
        preds.append({"player_key": f"p{i}", "order_idx": float(rng.uniform()),
                      "efv_grade": 0.0, "efv_war": 0.0})
    return rows, preds


def test_blend_keeps_the_subset_multiset_and_orders_by_the_blend():
    o = np.array([0.1, 0.5, 0.9, 0.3])
    h = np.array([5.0, 1.0, 2.0, 9.0])
    new = T.blend_orders(o, h, w=0.5)
    assert sorted(new.tolist()) == sorted(o.tolist())
    u = 0.5 * T._pct(h) + 0.5 * T._pct(o)
    assert np.argsort(new).tolist() == np.lexsort((h, o, u)).tolist()   # ties on u: V2's order
    assert new.tolist() == [0.1, 0.3, 0.9, 0.5]                          # no value averaged away
    assert np.allclose(T.blend_orders(o, h, w=0.0), o)                 # no head weight: unchanged
    assert np.argsort(T.blend_orders(o, h, w=1.0)).tolist() == np.argsort(h).tolist()


def test_apply_to_live_is_a_no_op_while_dark():
    rows, preds = _live()
    before = json.dumps(preds, sort_keys=True)
    assert T.EFV_TRACKING_HEAD_ON is False
    n = T.apply_to_live("pit", rows, preds, {"war_map": None},
                        fits={"pit": _fake_fit()}, tracking={1000: ("AAA", {k: 1.0 for k in T.metrics_of("pit")})})
    assert n == 0 and json.dumps(preds, sort_keys=True) == before


def test_apply_to_live_when_on_reorders_only_tracked_rows_and_keeps_the_grade_multiset(monkeypatch):
    import efv_v2_model as H
    monkeypatch.setattr(T, "EFV_TRACKING_HEAD_ON", True)
    rows, preds = _live()
    groups = [2026] * len(rows)
    fv = np.array([r["fv"] for r in rows])
    base = H.output_map(np.array([p["order_idx"] for p in preds]), groups, fv)
    for p, g in zip(preds, base):
        p["efv_grade"] = float(g)
    before = {p["player_key"]: p["order_idx"] for p in preds}
    tracking = {1000 + i: ("AAA" if i % 2 else "A", {k: float(i) for k in T.metrics_of("pit")})
                for i in range(0, 12, 2)}                      # six tracked rows
    n = T.apply_to_live("pit", rows, preds, {"war_map": None}, fits={"pit": _fake_fit()},
                        tracking=tracking)
    assert n == 6
    moved = [p for p in preds if p.get("tracking_head")]
    assert len(moved) == 6 and all(p["tracking_head"]["note"] == T.SURFACE_NOTE for p in moved)
    tracked_keys = {f"p{i}" for i in range(0, 12, 2)}
    assert sorted(before[k] for k in tracked_keys) == sorted(p["order_idx"] for p in moved)
    for p in preds:
        if p["player_key"] not in tracked_keys:
            assert p["order_idx"] == before[p["player_key"]]
    assert sorted(p["efv_grade"] for p in preds) == sorted(base.tolist())
    chips = [T.head_chip(p, 0.5) for p in preds]
    for p, c in zip(preds, chips):
        if c:
            assert c[0]["driver"] == T.CHIP_DRIVER and c[0]["unit"] == "percentile points"
            assert c[0]["mag"] == round(abs(p["tracking_head"]["shift_pct"]), 2)
    # a side that does not ship is untouched
    rows2, preds2 = _live()
    assert T.apply_to_live("hit", rows2, preds2, {"war_map": None}, fits={"pit": _fake_fit()},
                           tracking=tracking) == 0


def test_shipped_sides_reads_only_a_complete_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "OUT_PATH", tmp_path / "none.json")
    assert T.shipped_sides() == {}
    doc = {"status": "selection written", "verdict": {"pit": {"ships": True}}, "fit": {"pit": {}}}
    assert T.shipped_sides(doc) == {}
    doc["status"] = "complete"
    assert list(T.shipped_sides(doc)) == ["pit"]
