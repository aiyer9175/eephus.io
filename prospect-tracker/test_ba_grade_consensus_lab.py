# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/ba_grade_consensus_lab.py (BA_GRADE_IN_CONSENSUS, docs/efv-v2/BA_GRADE_IN_CONSENSUS.md).

Fixture tests only: the arms, the crosswalks, the normalizer table and its patch, the nulls,
the plants, the reading rule and the frame guard. Two tests read prospects.db outcome-free
(the parity P1 and the 2026 identity of arm A). Nothing is scored against an outcome.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import ba_grade_consensus_lab as X  # noqa: E402
import grade_normalization as G  # noqa: E402
from scrapers import Snapshot  # noqa: E402


def _tj(raw, risk):
    return json.dumps({"_extras": {"ba_raw_grade": raw, "ba_risk": risk}})


def _snap(source, key, date, fv, pos="RHP", raw=None, risk=None):
    tools = {"_extras": {"ba_raw_grade": raw, "ba_risk": risk}} if raw is not None else None
    return Snapshot(source=source, snapshot_date=date, interval_label="L", player_key=key,
                    player_name=key, position=pos, org=None, rank=1, fv=fv, status="active",
                    tools=tools)


# --- arms and crosswalks ---------------------------------------------------------------

def test_penalty_uses_the_published_ladder_from_2026_and_the_crosswalk_before():
    assert X.penalty(2026, "Average") == 10.0
    assert X.penalty(2026, "High") == 15.0
    assert X.penalty(2023, "High", "A") == 10.0
    assert X.penalty(2023, "High", "A2") == 15.0
    assert X.penalty(2025, "Very High", "A") == 15.0
    assert X.penalty(2025, "Very High", "A2") == 17.5
    assert X.penalty(2024, "Extreme", "A") == 20.0
    assert X.penalty(2023, "Unheard", "A") is None
    assert X.penalty(2023, None, "A") is None


def test_arm_values():
    assert X.arm_value("S", 2023, 50.0, 50, "High") == 50.0
    assert X.arm_value("S", 2026, 40.0, 50, "Average") == 40.0
    assert X.arm_value("R", 2026, 40.0, 50, "Average") == 50.0
    assert X.arm_value("A", 2023, 50.0, 50, "High") == 40.0
    assert X.arm_value("A2", 2023, 50.0, 50, "High") == 35.0
    assert X.arm_value("A", 2026, 40.0, 50, "Average") == 40.0
    assert X.arm_value("X", 2023, 50.0, 50, "High") is X.DROP
    # the rank-only list keeps None in every arm but X
    for a in ("S", "R", "A", "A2"):
        assert X.arm_value(a, 2026, None, None, None) is None
    with pytest.raises(ValueError):
        X.arm_value("Q", 2023, 50.0, 50, "High")


def test_transform_overrides_raw_and_penalty_per_unit():
    t = X.Transform("R", raw_over={("a", "2023-02-15"): 60.0})
    assert t("a", "2023-02-15", 45.0, _tj(45, "High")) == 60.0
    assert t("b", "2023-02-15", 45.0, _tj(45, "High")) == 45.0
    t = X.Transform("R", pen_over={("a", "2023-02-15"): 15.0})
    assert t("a", "2023-02-15", 45.0, _tj(45, "High")) == 30.0
    assert t("b", "2023-02-15", 45.0, _tj(45, "High")) == 45.0
    with pytest.raises(ValueError):
        X.Transform("Q")


# --- the normalizer table ----------------------------------------------------------------

ROWS = [
    ("fangraphs", "a", "RHP", "2023-02-15", 45, None),
    ("baseballamerica", "a", "RHP", "2023-02-15", 50, _tj(50, "High")),
    ("fangraphs", "b", "SS", "2023-02-15", 50, None),
    ("baseballamerica", "b", "SS", "2023-02-15", 55, _tj(55, "Medium")),
    ("baseballamerica", "b", "SS", "2026-02-15", 45, _tj(55, "Average")),
    ("fangraphs", "b", "SS", "2026-02-15", 50, None),
]


def test_latest_table_mirrors_the_served_shape_and_changes_only_ba():
    s = X.latest_table(ROWS, X.Transform("S"))
    assert s[("pitcher", 2023)]["a"] == {"fangraphs": 45.0, "baseballamerica": 50.0}
    assert s[("hitter", 2026)]["b"] == {"baseballamerica": 45.0, "fangraphs": 50.0}
    r = X.latest_table(ROWS, X.Transform("R"))
    assert r[("hitter", 2026)]["b"]["baseballamerica"] == 55.0
    a = X.latest_table(ROWS, X.Transform("A"))
    assert a[("pitcher", 2023)]["a"]["baseballamerica"] == 40.0
    assert a[("hitter", 2023)]["b"]["baseballamerica"] == 50.0
    assert a[("hitter", 2026)]["b"]["baseballamerica"] == 45.0
    x = X.latest_table(ROWS, X.Transform("X"))
    assert all(X.BA not in d for t in x.values() for d in t.values())
    assert x[("pitcher", 2023)]["a"] == {"fangraphs": 45.0}


def test_normalizer_patch_is_restored_even_on_error():
    orig = G._all_latest
    with pytest.raises(RuntimeError):
        with X.normalizer({("hitter", 2023): {}}):
            assert G._all_latest() == {("hitter", 2023): {}}
            raise RuntimeError("boom")
    assert G._all_latest is orig


def test_transform_snapshots_touches_only_ba():
    fg = _snap("fangraphs", "a", "2023-02-15", 45)
    ba = _snap("baseballamerica", "a", "2023-02-15", 50, raw=50, risk="High")
    out = X.transform_snapshots([fg, ba], X.Transform("A"))
    assert out[0] is fg and out[1].fv == 40.0 and ba.fv == 50
    assert X.transform_snapshots([fg, ba], X.Transform("X")) == [fg]
    assert X.transform_snapshots([fg, ba], X.Transform("S"))[1] is ba


# --- reading an arm ------------------------------------------------------------------------

@dataclasses.dataclass
class _P:
    snapshot_date: str
    consensus_fv_raw: float
    consensus_fv: float
    per_source: dict


def test_window_value_takes_the_latest_point_inside_the_preseason_window():
    pts = [_P("2022-12-01", 40, 40, {}), _P("2023-02-01", 42, 42, {"fangraphs": {}}),
           _P("2023-02-15", 44, 44, {"fangraphs": {}, X.BA: {}}), _P("2023-06-01", 50, 50, {})]
    assert X.window_value(pts, 2023) == (44.0, True)
    assert X.window_value(pts[:2], 2023) == (42.0, False)
    assert X.window_value(pts, 2024) == (None, False)


# --- nulls and plants --------------------------------------------------------------------

UNITS = [{"unit": (k, "2023-02-15"), "key": k, "raw": float(g), "pen": float(p), "role": r}
         for k, g, p, r in (("a", 40, 10, "pitcher"), ("b", 45, 5, "pitcher"),
                            ("c", 50, 20, "pitcher"), ("d", 55, 0, "hitter"),
                            ("e", 60, 15, "hitter"))]


def test_permutation_keeps_each_roles_multiset():
    out = X.permute_within_role(UNITS, "raw", np.random.default_rng(1))
    pit = sorted(out[u["unit"]] for u in UNITS if u["role"] == "pitcher")
    hit = sorted(out[u["unit"]] for u in UNITS if u["role"] == "hitter")
    assert pit == [40.0, 45.0, 50.0] and hit == [55.0, 60.0]
    again = X.permute_within_role(UNITS, "raw", np.random.default_rng(1))
    assert again == out


def test_planted_grade_follows_the_outcome_and_planted_penalty_opposes_it():
    reached = [{"side": "pit", "key": "a", "war": 3.0}, {"side": "pit", "key": "b", "war": 0.0},
               {"side": "pit", "key": "c", "war": 1.0}]
    g = X.planted(UNITS, reached, "raw", high_first=True)
    assert g[("a", "2023-02-15")] == 50.0 and g[("c", "2023-02-15")] == 45.0
    assert g[("b", "2023-02-15")] == 40.0
    p = X.planted(UNITS, reached, "pen", high_first=False)
    assert p[("b", "2023-02-15")] == 20.0 and p[("a", "2023-02-15")] == 5.0


# --- the reading rule ----------------------------------------------------------------------

def test_p_null_one_and_two_sided():
    null = [-0.02, -0.01, 0.0, 0.01, 0.02]
    assert X.p_null(0.03, null, two_sided=False) == round(1 / 6, 4)
    assert X.p_null(-0.015, null, two_sided=False) == round(2 / 6, 4)
    assert X.p_null(0.015, null, two_sided=True) == round(3 / 6, 4)
    assert X.p_null(None, null, two_sided=True) is None


def test_resolves_needs_ci_null_and_plant():
    d = {"delta": 0.05, "ci95": [0.01, 0.09]}
    assert X.resolves(d, 0.01, True)["reading"] == "RESOLVED positive"
    assert X.resolves(d, 0.2, True)["reading"] == "UNRESOLVED"
    assert X.resolves(d, 0.01, False)["reading"] == "UNRESOLVED"
    assert X.resolves({"delta": 0.05, "ci95": [-0.01, 0.09]}, 0.01, True)["resolves"] is False


def test_plant_passes_against_the_null_quantile():
    null = list(np.linspace(-0.01, 0.01, 101))
    assert X.plant_passes({"delta": 0.05, "ci95": [0.02, 0.08]}, null, 0.95,
                          absolute=False)["passes"]
    assert not X.plant_passes({"delta": 0.005, "ci95": [0.001, 0.01]}, null, 0.95,
                              absolute=False)["passes"]
    assert not X.plant_passes({"delta": 0.05, "ci95": [-0.01, 0.08]}, null, 0.95,
                              absolute=False)["passes"]


def test_recommendation_follows_section_8():
    un = {"resolves": False, "direction": None}
    pos = {"resolves": True, "direction": "positive"}
    neg = {"resolves": True, "direction": "negative"}
    assert X.recommendation(un, un, un)["default"] == "KEEP"
    assert X.recommendation(un, un, pos)["default"] == "KEEP"
    assert X.recommendation(un, un, neg)["default"] == "RAW"
    assert X.recommendation(neg, neg, un)["default"] == "EXCLUDE"
    assert X.recommendation(neg, un, un)["default"] == "KEEP"


# --- frames ----------------------------------------------------------------------------------

def _row(year, key="k", side="pit"):
    return {"key": key, "side": side, "year": year, "group": f"{side}|{year}",
            "grades": {X.CONS_KEY: 45.0}, "outcome": {"war": 1.0, "contributor": False}}


def test_guard_refuses_reserved_rows_and_other_frames():
    X.guard_rows({"lv_dev": [_row(2019)], "vm_dev": [_row(2023)]})
    with pytest.raises(RuntimeError):
        X.guard_rows({"lv_dev": [_row(2020)], "vm_dev": []})
    with pytest.raises(RuntimeError):
        X.guard_rows({"lv_dev": [], "vm_dev": [_row(2025)]})
    with pytest.raises(RuntimeError):
        X.guard_rows({"lv_res": []})


def test_stat_rows_keep_the_frame_consensus_on_list_vintages_and_group_by_frame_side_year():
    scored = {"lv_dev": [_row(2018, "a")], "vm_dev": [_row(2023, "b")]}
    vals = {"S": {("pit", 2023, "b"): 47.0}, "X": {("pit", 2023, "b"): 46.0}}
    rows = X.stat_rows(scored, vals)
    assert rows[0]["v"] == {"S": 45.0, "X": 45.0} and rows[0]["group"] == "lv_dev|pit|2018"
    assert rows[1]["v"] == {"S": 47.0, "X": 46.0} and rows[1]["group"] == "vm_dev|pit|2023"
    assert X.primary(rows) == [rows[1]]


def test_p3_counts_development_players_apart_from_others():
    pre = {"S": {("a", "2019-02-01"): 45.0, ("v", "2011-01-22"): None},
           "X": {("a", "2019-02-01"): 45.0, ("v", "2011-01-22"): 55.0}}
    out = X.p3_check(pre, {"a"})
    assert out["dev_points_moved"] == 0 and out["other_points_moved"] == 1
    out = X.p3_check(pre, {"a", "v"})
    assert out["dev_points_moved"] == 1


def test_no_em_dashes_in_the_lab():
    for p in (ROOT / "tools" / "ba_grade_consensus_lab.py", Path(__file__)):
        txt = p.read_text(encoding="utf-8")
        assert chr(0x2014) not in txt and chr(0x2013) not in txt


# --- the database, outcome-free ---------------------------------------------------------------

@pytest.fixture(scope="module")
def db_rows():
    if not G._DB.exists():
        pytest.skip("prospects.db not present")
    return X.db_rows()


def test_p1_the_rederived_table_equals_the_served_one(db_rows):
    import storage
    assert X.latest_table(db_rows, X.Transform("S"), storage.canonical_player_key) \
        == G._all_latest()


def test_arm_a_equals_the_stored_grade_on_every_2026_row(db_rows):
    t = X.Transform("A")
    n = 0
    for src, pk, _pos, date, fv, tj in db_rows:
        if src != X.BA or not str(date).startswith("2026"):
            continue
        if X.extras_of(tj).get("ba_raw_grade") is None:
            continue
        assert t(pk, str(date), fv, tj) == float(fv)
        n += 1
    assert n > 0
