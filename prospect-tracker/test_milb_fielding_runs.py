# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Fixture tests for the in-house MiLB fielding runs tool (tools/milb_fielding_runs.py,
docs/sdr-2026-08-18/MILB_FIELDING_RUNS_GATE.md). Offline; no fetch and no real row. The
dry run's fixture carries None values (unlocated balls in play, taken pitches without
location, MLB targets and grades missing) so every refusal path runs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import milb_fielding_runs as M  # noqa: E402


def _payload():
    """A two-play StatsAPI-shaped allPlays list: a ground-ball out 6-3 and a single to CF,
    with a defensive switch and taken pitches with and without location."""
    return [
        {"result": {"eventType": "field_out"}, "about": {"atBatIndex": 0, "inning": 1,
                                                         "isTopInning": True},
         "count": {"outs": 1}, "matchup": {"batSide": {"code": "R"}},
         "playEvents": [
             {"isPitch": True, "index": 0, "details": {"call": {"code": "C"}},
              "count": {"balls": 0, "strikes": 1},
              "pitchData": {"strikeZoneTop": 3.4, "strikeZoneBottom": 1.6,
                            "coordinates": {"pX": 0.31, "pZ": 2.2}}},
             {"type": "action", "index": 1, "details": {"eventType": "defensive_switch"},
              "player": {"id": 77}, "position": {"code": "8"}},
             {"isPitch": True, "index": 2, "details": {"call": {"code": "X"}},
              "count": {"balls": 0, "strikes": 1},
              "hitData": {"trajectory": "ground_ball", "hardness": "medium", "location": "6",
                          "coordinates": {"coordX": 110.0, "coordY": 150.0}}}],
         "runners": [{"movement": {"originBase": None, "start": None, "end": None,
                                   "isOut": True},
                      "details": {"playIndex": 2, "eventType": "field_out",
                                  "runner": {"id": 5}},
                      "credits": [{"player": {"id": 66}, "position": {"code": "6"},
                                   "credit": "f_assist"},
                                  {"player": {"id": 33}, "position": {"code": "3"},
                                   "credit": "f_putout"}]}]},
        {"result": {"eventType": "single"}, "about": {"atBatIndex": 1, "inning": 1,
                                                      "isTopInning": True},
         "count": {"outs": 1}, "matchup": {"batSide": {"code": "L"}},
         "playEvents": [
             {"isPitch": True, "index": 0, "details": {"call": {"code": "B"}},
              "count": {"balls": 1, "strikes": 0}, "pitchData": {}},
             {"isPitch": True, "index": 1, "details": {"call": {"code": "D"}},
              "count": {"balls": 1, "strikes": 0},
              "hitData": {"trajectory": "line_drive", "coordinates": {"coordX": 125.0,
                                                                     "coordY": 80.0}}}],
         "runners": [{"movement": {"originBase": None, "start": None, "end": "1B",
                                   "isOut": False},
                      "details": {"playIndex": 1, "eventType": "single", "runner": {"id": 6}},
                      "credits": [{"player": {"id": 88}, "position": {"code": "8"},
                                   "credit": "f_fielded_ball"}]}]},
    ]


def test_reduce_plays_keeps_credits_subs_and_located_pitches():
    r = M.reduce_plays(_payload())
    assert [p[3] for p in r["plays"]] == ["field_out", "single"]
    assert r["plays"][0][7:12] == ["ground_ball", "medium", "6", 110.0, 150.0]
    assert r["plays"][0][12] == 2                     # last pitch index
    assert r["credits"][0] == [0, 2, "field_out", 66, "6", "f_assist"]
    assert r["subs"] == [[0, 1, 77, "8", "defensive_switch"]]
    assert r["taken"][0] == [0, "C", 0, 0, 0.31, 2.2, 3.4, 1.6]
    assert r["taken"][1][4] is None                   # a taken pitch without location


def test_holder_is_last_at_or_before_else_first_after():
    plays_top = {0: 1, 1: 1, 5: 1}
    credits = [[1, 2, "x", 10, "6", "f_assist"], [5, 0, "x", 11, "6", "f_putout"]]
    tl = M._timelines(plays_top, credits, [])
    assert M._holder(tl, 1, "6", (0, 0)) == 10       # before any entry: the first after
    assert M._holder(tl, 1, "6", (3, 0)) == 10
    assert M._holder(tl, 1, "6", (5, 9)) == 11
    assert M._holder(tl, 1, "7", (5, 9)) == 0        # nobody known at the position


def test_parse_game_one_ball_in_play_each():
    rec = M.game_record({"gamePk": 1, "home": 100, "away": 200}, 11, 2023, _payload(), "t")
    T = M.Tables()
    M.parse_game(rec, 0, T)
    F = M.to_frames(T)
    b = F["bip"]
    assert len(b) == 2
    assert b.out.tolist() == [1, 0]
    assert b.init.tolist() == [6, 8]
    assert b.team.tolist() == [100, 100]              # top half: the home team defends
    assert b.h6.tolist() == [66, 66] and b.h8.tolist() == [77, 88]
    cen = T.census[(11, 2023)]
    assert cen["taken"] == 2 and cen["taken_located"] == 1
    assert len(F["taken"]) == 0                       # no catcher is known in this game


def test_range_runs_sum_to_out_minus_expectation():
    rec = M.fixture_records(games_per_cell=6)
    T = M.Tables()
    for i, r in enumerate(rec):
        M.parse_game(r, i, T)
    b = M.to_frames(T)["bip"]
    p, w, d = M.fit_cells(b)
    runs, chances = M.range_runs(b, p, w, d)
    loc = b.located.to_numpy() == 1
    np.testing.assert_allclose(runs[loc, 1:].sum(1), ((b.out.to_numpy() - p) * d)[loc],
                               atol=1e-9)
    ws = w[loc, 1:].sum(1)
    assert (ws >= 0).all() and (ws <= 1.0 + 1e-9).all()
    # a hit's fielder is never credited with an out
    hit = loc & (b.out.to_numpy() == 0)
    assert (runs[hit, 1:] <= 1e-12).all()


def test_level_norms_centre_each_cell():
    rec = M.fixture_records(games_per_cell=6)
    T = M.Tables()
    for i, r in enumerate(rec):
        M.parse_game(r, i, T)
    gr = M.level_norms(M.game_rows(M.to_frames(T)))
    tot = gr.groupby(["sport", "season", "pos"])[list(M.COMPONENTS)].sum()
    assert np.abs(tot.to_numpy()).max() < 1e-8


def test_statistics_helpers():
    assert M.spearman([1, 2, 3, 4], [1, 2, 3, 5]) == 1.0
    assert M.spearman([1, 1, 1], [1, 2, 3]) is None
    assert M.spearman([1, None, 3], [1, 2, 3]) is None
    h = M.holm({"T1": 0.01, "T2": 0.04, "T3": None})
    assert h["T1"]["rejects"] and h["T2"]["rejects"] and not h["T3"]["rejects"]
    h = M.holm({"T1": 0.03, "T2": 0.04})
    assert not h["T1"]["rejects"] and not h["T2"]["rejects"]
    rng = np.random.default_rng(1)
    g = rng.normal(size=400)
    x = g + rng.normal(size=400)
    y = g + rng.normal(size=400)
    assert abs(M.partial_rank(x, y, g)) < 0.15
    assert M.partial_rank(x, x + 0.01 * rng.normal(size=400), g) > 0.9


def test_reserved_debut_cohorts_excluded():
    from efv_vintage_frame import R_VM_FIRST_DEBUT_YEAR
    assert max(M.DEBUT_YEARS) < R_VM_FIRST_DEBUT_YEAR


def test_dry_run_reports_every_estimand(tmp_path):
    out = tmp_path / "dry.json"
    art = M.dry_run(out, b=20, log=lambda *a: None)
    assert out.exists()
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["dry_run"] is True and d["gate"] == M.GATE_DOC
    for k in ("a", "b", "c"):
        assert d["verdicts"][k] in {"PASS", "FAIL", "UNDERPOWERED", "VOID"}
    assert "null_N_a" in d["a_persistence"] and "planted_P_a" in d["a_persistence"]
    assert "null_N_b" in d["b_mlb"] and "planted_P_b" in d["b_mlb"]
    assert "null_N_c" in d["c_incremental"] and "planted_P_c" in d["c_incremental"]
    assert art["serves"] == (d["verdicts"]["b"] == "PASS")


def test_read_refuses_without_sha_and_when_spent(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "EVAL_OUT", tmp_path / "eval.json")
    a = type("A", (), {"dry_run": False, "gate_sha": None})()
    assert M.cmd_read(a) == 3
    (tmp_path / "eval.json").write_text(json.dumps({"dry_run": False}), encoding="utf-8")
    a.gate_sha = "abc"
    assert M.cmd_read(a) == 3


def test_no_grade_level_grouping_in_source():
    src = (ROOT / "tools" / "milb_fielding_runs.py").read_text(encoding="utf-8")
    for bad in ("groupby(\"fv", "groupby('fv", "fv_bucket", "fv_level", "by_fv"):
        assert bad not in src
    assert pd.__version__


# --- the served sidecar (gate part 6) -------------------------------------------------

def _fixture_build():
    import tempfile
    from collections import defaultdict
    tmp = Path(tempfile.mkdtemp(prefix="mfr_t_"))
    recs = M.fixture_records(games_per_cell=30)
    sched = defaultdict(list)
    for r in recs:
        M._atomic_write_gz(M.game_path(r["sportId"], r["season"], r["gamePk"], tmp), r)
        sched[(r["sportId"], r["season"])].append({"gamePk": r["gamePk"]})
    return M.build(tmp, write=False, sports=(11, 12), seasons=(2021, 2022, 2023),
                   schedule_fn=lambda s, y: sched.get((s, y), []), log=lambda *a: None)


def _eval_fixture(verdict="PASS"):
    cell = {"point": 0.2559, "n": 203, "lb95": 0.1073}
    return {"dry_run": False, "verdicts": {"a": "PASS", "b": verdict, "c": "UNDERPOWERED"},
            "b_mlb": {"primary": {"T1": cell, "T2": {"point": 0.198, "n": 164, "lb95": 0.033}}}}


def test_sidecar_payload_shape_and_pre_debut_window():
    import milb_fielding_runs_export as X
    res = _fixture_build()
    st = res["st"]
    meta = {"k": res["k"], "levels": {k: v for k, v in res["levels"].items() if k != "_F"}}
    pids = sorted(st.pid.unique().tolist())
    keys = {f"p{i}": p for i, p in enumerate(pids)}
    debut = {pids[0]: 2022}
    pay = X.build_payload(st, meta, _eval_fixture(), keys, debut, generated_at="2026-10-16T00:00:00Z")
    assert pay["eval_artifact"] == "data/milb_fielding_runs_eval.json"
    assert "0.26" in pay["claim"] and "203" in pay["claim"] and "0.20" in pay["claim"]
    assert pay["n_players"] == len(pay["by_mlbam"]) > 0
    for mid, rec in pay["by_mlbam"].items():
        assert str(mid) in pay["key_to_mlbam"].values()
        for x in rec["positions"]:
            assert x["inn"] >= M.INN_FLOOR - 0.5
            assert x["band"] == X.band_of(x["rel"])
            assert x["pos"] in M.POS_NAME.values()
            assert x["mfr"] == round(x["mfr"], 1)
    first = pay["by_mlbam"].get(str(pids[0]))
    if first:                                     # only the 2021 season counts before 2022
        assert first.get("pre_debut_only") is True
        assert all(x["seasons"] == [2021, 2021] for x in first["positions"])


def test_sidecar_writes_nothing_without_a_pass(tmp_path, monkeypatch):
    import milb_fielding_runs_export as X
    ev = tmp_path / "eval.json"
    ev.write_text(json.dumps(_eval_fixture("FAIL")), encoding="utf-8")
    out = tmp_path / "out.json"
    assert X.run(eval_path=ev, out_path=out, tables=tmp_path) is None and not out.exists()
    monkeypatch.setattr(X, "MILB_FIELDING_RUNS_SERVE", False)
    assert X.run(eval_path=ev, out_path=out, tables=tmp_path) is None and not out.exists()


def test_prospx_card_reads_the_sidecar_and_sits_in_signals():
    src = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert "function milbFieldingCard(p)" in src
    assert 'fetch("/data/milb_fielding_runs.json"' in src
    assert "defHomeHtml, milbFieldingHtml" in src and "].filter(Boolean)" in src
    blk = src[src.index("function milbFieldingCard(p)"):src.index("// ===== eTools: the shown grade")]
    assert "\u2014" not in blk and "\u2013" not in blk


# --- the eFV driver read (gate part 11) ------------------------------------------------

def test_driver_row_metric_and_bh():
    import milb_fielding_runs_driver as D
    st = pd.DataFrame({"pid": [1, 1, 2], "season": [2021, 2021, 2021], "sport": [13, 13, 13],
                       "pos": [6, 4, 6], "inn": [300.0, 100.0, 40.0], "runs": [3.0, 1.0, 2.0]})
    k = {p: {"k": 400.0} for p in M.POS_RATED}
    rm = D.row_metric(st, k)
    assert set(rm) == {(1, 2021, 13)}                 # 40 innings is under the floor
    assert abs(rm[(1, 2021, 13)] - 1000.0 * 4.0 / 800.0) < 1e-9
    assert D._bh([0.01, None, 0.04]) == [0.02, None, 0.04]


def test_driver_dry_run_scores_real_null_and_planted():
    import milb_fielding_runs_driver as D
    T, A = D.fixture_table()
    res = D.score(T, A, log=lambda *a: None)
    fams = {c["family"] for c in res["cells"]}
    assert fams == {"fielding", "null", "planted"}
    assert res["verdict"] in {"VOID", "CANDIDATES", "NO CANDIDATE", "UNDERPOWERED"}
    assert all(c["powered"] in (True, False) for c in res["cells"] if c["family"] == "fielding")
