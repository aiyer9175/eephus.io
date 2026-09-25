# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EV-04 pins (docs/efv-v2/PROGRAM.md s2.2, s2.4, s3.4): the list-vintage frame and its
labels.

1. No input on a frame row is dated outside its V preseason window, and the MiLB read
   stops at V - 1.
2. W3 is 0 whenever the player did not debut within 3 seasons of V, and a nonzero W3
   always means he did (the debut flag, not the value, separates a 0.0 debut).
3. The reserved guard raises for list vintages 2020 and 2021 without the committed gate
   sha, on the frame, on the labels and on a bare score request; the R-VM pin holds.
4. Neither module groups or strata rows by consensus-FV level (PROSPECT_ANCHOR_GATE).

Real-data tests read development vintages only. Nothing here computes a grade-vs-outcome
statistic of any kind.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

import efv_labels as L
import efv_vintage_frame as F

ROOT = Path(__file__).parent
DATA = ROOT / "data"
_HAVE_DATA = all((DATA / f).exists() for f in ("debuts.json", "inactive.json",
                                                "timeseries.json"))


def _pt(date, per_source, cons=45.0):
    return {"snapshot_date": date, "consensus_fv_raw": cons,
            "sources_contributing": sorted(per_source),
            "per_source": {s: {"fv_published": v, "snapshot_date": date}
                           for s, v in per_source.items()}}


def _rec(key="synthetic_player", debut=None, points=(), position="SS", mlbam=None,
         birth="1995-03-01"):
    return {"player_key": key, "debut_date": debut, "position": position,
            "mlbam_id": mlbam, "birth_date": birth, "points": list(points),
            "statline": {}}


# ---------------------------------------------------------------------------
# 1. timing
# ---------------------------------------------------------------------------

def test_synthetic_row_reads_only_the_window_and_stops_at_debut():
    V = 2016
    rec = _rec(debut="2016-04-10", points=[
        _pt("2015-08-01", {"mlb_pipeline": 50.0}),          # before the window
        _pt("2016-02-01", {"fangraphs": 45.0}),              # in the window
        _pt("2016-04-20", {"mlb_pipeline": 60.0}, cons=60),  # in window, after debut
        _pt("2016-07-01", {"fangraphs": 70.0}, cons=70),     # midseason
    ])
    row = F.frame_row(rec, "hit", V, milb=False)
    assert row is not None
    assert row["window"] == ["2016-01-01", "2016-04-10"]
    assert row["point_dates"] == ["2016-02-01"]
    assert row["grades"] == {"fangraphs": 45.0, "prospx_consensus": 45.0}
    for d in F.row_input_dates(row):
        assert row["window"][0] <= d < row["window"][1]


def test_synthetic_membership_rules():
    V = 2016
    real = _pt("2016-02-01", {"fangraphs": 45.0})
    # debuted before the window opened: not a prospect at V
    assert F.frame_row(_rec(debut="2015-09-01", points=[real]), "hit", V, milb=False) is None
    # a constant-anchor source is not a real grader read
    anchor = _pt("2016-02-01", {"performance_ingest": 35.0})
    assert F.frame_row(_rec(points=[anchor]), "hit", V, milb=False) is None
    # no read inside the window
    assert F.frame_row(_rec(points=[_pt("2016-06-01", {"fangraphs": 45.0})]),
                       "hit", V, milb=False) is None
    # a grade carried forward from last year's board is not a read in V
    carried = _pt("2016-02-01", {"fangraphs": 45.0})
    carried["per_source"]["fangraphs"]["snapshot_date"] = "2015-02-01"
    assert F.frame_row(_rec(points=[carried]), "hit", V, milb=False) is None
    # side routing: a pitcher is not a hitter row
    assert F.frame_row(_rec(points=[real], position="RHP"), "hit", V, milb=False) is None
    assert F.frame_row(_rec(points=[real], position="RHP"), "pit", V, milb=False) is not None


@pytest.mark.skipif(not _HAVE_DATA, reason="served data files absent")
@pytest.mark.parametrize("side,V", [("hit", 2016), ("pit", 2018)])
def test_real_frame_has_no_input_after_the_window(side, V):
    rows = F.build_frame(side, V)
    assert rows, f"empty development frame {side} {V}"
    lo = f"{V}-01-01"
    for r in rows:
        assert r["vintage"] == V and r["window"][0] == lo
        assert r["window"][1] <= f"{V}-05-01"
        for d in F.row_input_dates(r):
            assert lo <= d < r["window"][1], (r["player_key"], d)
        for d in r["source_dates"]:
            assert d < r["window"][1], (r["player_key"], d)
        assert r["real_sources"], r["player_key"]
        if r.get("milb"):
            assert r["milb"]["milb_season"] <= V - 1, r["player_key"]
            assert r["milb_last_season"] <= V - 1
        assert r["il_cutoff"] == lo
        if not r["acq_known_at_v"]:
            assert r["pick_overall"] is None and r["bonus_usd"] is None
        else:
            assert r["acq_year"] < V
        if r.get("debut_date"):
            assert r["debut_date"][:10] >= lo


# ---------------------------------------------------------------------------
# 2. W3
# ---------------------------------------------------------------------------

def test_window_war_zero_iff_no_debut_in_window():
    V = 2015
    seasons = {2016: 1.5, 2017: 2.0, 2018: -0.5, 2019: 4.0}
    assert L.window_war(seasons, None, V, 3) == (0.0, False)
    assert L.window_war(seasons, V + 4, V, 3) == (0.0, False)
    assert L.window_war(seasons, V - 1, V, 3) == (0.0, False)
    assert L.window_war(seasons, 2016, V, 3) == (3.0, True)
    assert L.window_war(seasons, 2016, V, 2) == (3.5, True)
    # a debuted player whose window sums to exactly zero keeps the flag
    assert L.window_war({2017: 0.5, 2018: -0.5}, 2017, V, 3) == (0.0, True)


def test_labels_for_synthetic_records():
    V = 2015
    never = _rec(key="never_reached", birth="1985-01-01",
                 points=[_pt("2015-02-01", {"fangraphs": 40.0})])
    lab = L.labels_for(never, V, None)
    assert lab["reached"] == "never" and lab["w3"] == 0.0 and lab["w3_debut"] is False
    assert lab["r3"] == 0.0 and lab["l6"] == 0.0
    deb = _rec(key="reached_2017", debut="2017-05-01")
    lab = L.labels_for(deb, V, {2017: 1.0, 2018: 2.0, 2019: 3.0, 2020: 9.0})
    assert lab["reached"] == "reached" and lab["debut_year"] == 2017
    assert lab["w3"] == 6.0 and lab["w3_debut"] is True
    assert lab["w2"] == 3.0 and lab["r3"] == 1.0
    late = _rec(key="reached_2019", debut="2019-05-01")
    lab = L.labels_for(late, V, {2019: 5.0})
    assert lab["w3"] == 0.0 and lab["w3_debut"] is False and lab["r3"] == 0.0
    # guard a: a WAR season before the published debut is never labelled
    vet = _rec(key="veteran", debut="2018-05-01")
    lab = L.labels_for(vet, V, {2016: 1.0, 2018: 1.0})
    assert lab["status"] == "identity_conflict" and lab["w3"] is None


@pytest.mark.skipif(not _HAVE_DATA, reason="served data files absent")
def test_real_w3_zero_iff_no_debut_in_window():
    V = 2014
    universe = F.load_universe()
    war = L.war_seasons_table()
    n_debut = 0
    for side in F.SIDES:
        rows = F.build_frame(side, V, universe=universe, milb=False, sidecars=False)
        for lab in L.labels_for_frame(rows, universe=universe, war=war):
            if lab["w3"] is None:
                assert lab["status"] in ("identity_conflict", "reserved_vm")
                continue
            in_window = (lab["reached"] == "reached" and lab["debut_year"] is not None
                         and V <= lab["debut_year"] <= V + L.W_DEBUT_WINDOW)
            assert lab["w3_debut"] is in_window, lab
            if not in_window:
                assert lab["w3"] == 0.0, lab
            if lab["w3"] != 0.0:
                assert lab["w3_debut"] is True, lab
            n_debut += in_window
    assert n_debut > 0


# ---------------------------------------------------------------------------
# 3. reserved guard
# ---------------------------------------------------------------------------

def _head_sha():
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def test_reserved_constants():
    assert F.RESERVED_LV == frozenset({2020, 2021})
    assert F.R_VM_FIRST_DEBUT_YEAR == 2025
    assert not set(F.DEV_VINTAGES) & set(F.RESERVED_LV)
    assert max(F.DEV_VINTAGES) < min(F.RESERVED_LV)


@pytest.mark.parametrize("V", sorted(F.RESERVED_LV))
def test_reserved_guard_raises(V):
    head = _head_sha()
    for sha in (None, "", "0" * 40, "deadbeef", head):
        with pytest.raises(F.ReservedFrameError):
            F.guard_score_request(V, gate_sha=sha)
        with pytest.raises(F.ReservedFrameError):
            F.build_frame("hit", V, gate_sha=sha, universe={})
        with pytest.raises(F.ReservedFrameError):
            L.labels_for(_rec(), V, None, gate_sha=sha)
    with pytest.raises(F.ReservedFrameError):
        F.frame_counts((V,), universe={})


def test_head_is_not_a_gate_sha_until_the_gate_commits():
    # The registration does not exist yet (PROGRAM.md s4); HEAD cannot open R-LV.
    if (ROOT / F.GATE_DOC).exists():
        pytest.skip("gate document present; the sha check is exercised above")
    assert F.gate_sha_committed(_head_sha()) is False


def test_dev_vintages_pass_the_guard():
    for V in F.DEV_VINTAGES:
        F.guard_score_request(V)
    assert F.build_frame("hit", 2015, universe={}) == []


def test_reserved_vm_pins_hold():
    assert F.reserved_vm_pins() == []


# ---------------------------------------------------------------------------
# 4. no FV-cell grouping anywhere in either module
# ---------------------------------------------------------------------------

_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin")


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
        elif isinstance(node, ast.alias):
            yield node.name


@pytest.mark.parametrize("mod", ["efv_vintage_frame.py", "efv_labels.py"])
def test_no_fv_cell_grouping(mod):
    tree = ast.parse((ROOT / mod).read_text(encoding="utf-8"))
    for name in _names(tree):
        low = name.lower()
        assert not any(t in low for t in _BANNED_TOKENS), (mod, name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (mod, node.value, node.lineno)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            low = node.value.lower()
            assert not any(t in low for t in _BANNED_TOKENS), (mod, node.value)


def test_labels_read_no_grade_and_frame_reads_no_war():
    lab = ast.parse((ROOT / "efv_labels.py").read_text(encoding="utf-8"))
    fv_word = re.compile(r"(^|_)(fv|grades?)(_|$)")
    for name in _names(lab):
        assert not fv_word.search(name.lower()), name
    for node in ast.walk(lab):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            assert not fv_word.search(node.value.lower()), node.value
    frame = ast.parse((ROOT / "efv_vintage_frame.py").read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(frame) if isinstance(n, (ast.Import, ast.ImportFrom))
                for a in n.names} | {n.module for n in ast.walk(frame)
                                     if isinstance(n, ast.ImportFrom) and n.module}
    assert not imported & {"efv_labels", "war_source", "ewar", "stats"}, imported
