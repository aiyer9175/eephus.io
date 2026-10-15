# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for efv_2026_holdout.py (docs/efv-v2/EFV_2026_HOLDOUT.md, owner EW3-13).

Everything here runs on FIXTURES except the artifact pins at the end, which read the one
committed read (data/efv_2026_holdout.json) and never recompute it. Pinned: the registered
constants, the latest-per-source board read, the training-label truncation, the paired
statistic and its two resamplers, the verdict rule, the one-read guard, and no grouping
by consensus-FV level.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import efv_2026_holdout as X
import efv_dataset as D

ROOT = Path(__file__).parent


def test_the_registered_constants():
    assert X.CUTOFF == "2026-03-25" and X.WINDOW_END == "2026-03-26"
    assert X.LIST_WINDOW == ("2026-01-01", "2026-03-26")
    assert X.DEBUT_WINDOW == ("2025-01-01", "2026-03-26")
    assert X.DEBUT_CLASSES == (2025, 2026) and X.SEASON == 2026
    assert X.TRAIN_RESOLVED_THROUGH == 2025
    assert X.B == 4000 and X.SEED == 20261021 and X.MIN_GROUP_ROWS == 20
    assert X.CLUSTERINGS == ("player", "club")
    assert X.GATE_SHA == "e7931ce4e13110eebb53555bff455ff13ca7c502"
    assert X.LABEL_VINTAGE_ID == "2026-10-02-0341299c20ec"
    assert X.SERVED == "efv_v5_combined"
    assert X.PASS_LEG == "war2026|spearman|pooled|efv_v5_combined-consensus"
    assert (ROOT / X.DOC).exists()


def _pt(d, cons, **src):
    return {"snapshot_date": d, "consensus_fv_raw": cons,
            "per_source": {k: {"fv_published": v} for k, v in src.items()}}


def test_latest_point_per_source_on_or_before_the_cutoff():
    pts = [_pt("2026-01-10", 45.0, fangraphs=50, mlb_pipeline=45),
           _pt("2026-02-20", 46.0, mlb_pipeline=50),
           _pt("2026-02-20", 46.5, mlb_pipeline=55),
           _pt("2026-03-25", 47.0, fangraphs=45),
           _pt("2026-03-26", 60.0, fangraphs=70, mlb_pipeline=70)]
    g = X.source_grades(pts, *X.LIST_WINDOW)
    assert g["fangraphs"] == 45.0               # the latest FG point, not the max
    assert g["mlb_pipeline"] == 55.0            # two points on the latest date: the larger
    assert g["prospx_consensus"] == 47.0        # the latest in-window point
    assert X.source_grades(pts[:1], "2026-02-01", "2026-03-26") == {}


def test_club_reads_the_as_of_point():
    assert X.club_of({"org": "sfg"}) == "SFG"
    assert X.club_of({}) == X.UNKNOWN_CLUB and X.club_of(None) == X.UNKNOWN_CLUB


def test_relabel_stops_the_labels_at_2025():
    rows = [{"player_key": "a", "kind": "debuted", "debut_year": 2024},
            {"player_key": "b", "kind": "debuted", "debut_year": 2025, "target_resolved": 9.0},
            {"player_key": "c", "kind": "bust", "bust_recent": False, "weight": 1.0,
             "terminal_resolved": "2026-06-01"},
            {"player_key": "d", "kind": "debuted", "debut_year": 2023}]
    cw = {"a": {2024: 1.0, 2025: 2.0, 2026: 30.0}, "d": {2023: 1.0, 2024: 1.0, 2025: 1.0}}
    term = {"d": "2026-03-30"}
    out, acct = X.relabel(rows, cw, term, rt=2025, term_cap=X.CUTOFF)
    a, b, c, d = out
    assert a["target_resolved"] == 3.0 and a["observed_seasons"] == 2 and a["censored"]
    assert a["target_censored"] == pytest.approx(3.0 + 4 * 1.5)
    assert b == rows[1]                          # a 2025 debut is left as it was
    assert c["bust_recent"] is True and c["weight"] == 0.5 and "terminal_resolved" not in c
    assert d["censored"] and "terminal_resolved" not in d   # retired after the cutoff
    assert acct["terminal_after_cap"] == 1 and acct["bust_recent_restored"] == 1
    assert D.RESOLVED_THROUGH == 2026            # the patch never leaks


def test_relabel_at_the_matrix_horizon_reproduces_label_6yr():
    cw = {"a": {2022: 1.0, 2023: 0.5, 2024: 2.0, 2025: 1.0, 2026: 0.25}}
    t = D._label_6yr(cw["a"], 2022, None)
    row = {"player_key": "a", "kind": "debuted", "debut_year": 2022,
           "target_resolved": t[0], "target_censored": t[1], "censored": t[2],
           "weight": t[3], "observed_seasons": t[4]}
    out, acct = X.relabel([row], cw, {}, rt=int(D.RESOLVED_THROUGH), term_cap="9999-12-31")
    assert out[0] == row and acct["changed"] == 0


def test_matrix_paths_restores(tmp_path):
    orig = D.matrix_path
    with X.matrix_paths({"hit": tmp_path / "h.json", "pit": tmp_path / "p.json"}):
        assert D.matrix_path("pit") == tmp_path / "p.json"
    assert D.matrix_path is orig


def test_the_verdict_rule():
    leg = lambda pl, pu, cl, cu: {"player": {"lb95": pl, "ub95": pu},   # noqa: E731
                                  "club": {"lb95": cl, "ub95": cu}}
    assert X.verdict(leg(0.01, 0.05, 0.001, 0.06)) == "beats"
    assert X.verdict(leg(0.01, 0.05, -0.001, 0.06)) == "ties"
    assert X.verdict(leg(-0.05, -0.01, -0.06, -0.001)) == "trails"
    assert X.verdict(leg(-0.05, -0.01, -0.06, 0.001)) == "ties"
    assert X.verdict({"player": {"status": "not derived"}}) == "ties"


def _fixture_rows(n=400, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        side = "hit" if i % 2 else "pit"
        talent = rng.normal()
        war = max(0.0, talent + rng.normal(scale=0.7)) if rng.random() < 0.3 else 0.0
        cons = talent + rng.normal(scale=2.5)
        rows.append({"player_key": f"p{i}", "side": side, "group": f"{side}|2026",
                     "club": f"C{i % 12}",
                     "scores": {"prospx_consensus": cons, "efv_v5_combined": talent,
                                "efv_v2": cons, "efv_v1": cons + 0.01,
                                "mlb_pipeline": cons if i % 3 else None,
                                "fangraphs": cons},
                     "labels": {"war2026": war, "r2026": int(war > 0),
                                "rate": war if war > 0 else None}})
    return rows


def test_run_legs_on_a_fixture():
    rows = _fixture_rows()
    legs = X.legs_for("list")
    out = X.run_legs(rows, legs, B_=200, seed=1, log=lambda *a, **k: None)
    tie = out["war2026|spearman|pooled|efv_v2-consensus"]
    assert tie["delta"] == 0.0 and tie["player"]["lb95"] == 0.0
    win = out[X.PASS_LEG]
    assert win["delta"] > 0 and win["player"]["lb95"] > 0 and win["club"]["lb95"] > 0
    assert X.verdict(win) == "beats"
    src = out["war2026|spearman|pooled|mlb_pipeline-consensus"]
    assert src["n"] < tie["n"] and src["set"] == "mlb_pipeline graded"
    assert set(out["war2026|spearman|hit|efv_v2-consensus"]["groups"]) == {"hit|2026"}
    again = X.run_legs(rows, legs[:3], B_=200, seed=1, log=lambda *a, **k: None)
    assert again[legs[0]["name"]]["player"] == out[legs[0]["name"]]["player"]


def test_debut_legs_scope_by_class():
    names = {lg["name"] for lg in X.legs_for("debut")}
    assert "war2026|spearman|2025|efv_v5_combined-consensus" in names
    assert not any(n.startswith("r2026") for n in names)
    rows = _fixture_rows()
    for i, r in enumerate(rows):
        r["group"] = f"{r['side']}|{2025 + i % 2}"
    keep = X.kept_groups(np.asarray([r["group"] for r in rows]), np.ones(len(rows), bool),
                         "2025")
    assert keep and all(g.endswith("2025") for g in keep)


def test_one_read_guard(tmp_path):
    p = tmp_path / "efv_2026_holdout.json"
    X.guard_one_read(p)
    p.write_text("{}")
    with pytest.raises(X.AlreadyRead):
        X.guard_one_read(p)


def test_the_module_groups_nothing_by_consensus_fv_level():
    src = (ROOT / "efv_2026_holdout.py").read_text(encoding="utf-8")
    for bad in ("fv_cell", "fv_bucket", "by_fv", "fv_level", "fv_bin", "fv_stratum"):
        assert bad not in src, bad
    assert "run_backtest" not in src
