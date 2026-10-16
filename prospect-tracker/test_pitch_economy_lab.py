# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/pitch_economy_lab.py on fixtures (docs/ewar/PITCH_ECONOMY_LAB.md). No corpus
season or real line is read here except RE288's committed 2024 table for the count-lift
walk; the one run is a separate step."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
LAB_PATH = ROOT / "tools" / "pitch_economy_lab.py"


def _load():
    spec = importlib.util.spec_from_file_location("pitch_economy_lab", LAB_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lab = _load()


def test_spearman_and_partial_on_known_structure():
    rng = np.random.default_rng(1)
    z = rng.normal(size=400)
    x = z + 0.01 * rng.normal(size=400)
    y = z + rng.normal(size=400)
    assert lab.spearman(x, y) > 0.5
    assert abs(lab.partial_spearman(x, y, z.reshape(-1, 1))) < 0.15
    assert lab.spearman([1, 2], [2, 1]) is None
    assert lab.spearman([1, 1, 1], [1, 2, 3]) is None


def test_cluster_resample_keeps_whole_clusters():
    ids = ["a", "a", "b", "c", "c", "c"]
    rows, starts, sizes = lab._clusters(ids)
    idx = lab._resample(rows, starts, sizes, np.array([2, 2, 0]))
    assert sorted(idx.tolist()) == [0, 1, 3, 3, 4, 4, 5, 5]


def test_boot_ci_is_seeded_and_brackets_the_point():
    rng = np.random.default_rng(2)
    x = rng.normal(size=300)
    y = 0.5 * x + rng.normal(size=300)
    cols = {"x": x, "y": y}
    ids = list(range(300))
    a = lab.boot_ci(lambda c: lab.spearman(c["x"], c["y"]), cols, ids, b=200)
    b = lab.boot_ci(lambda c: lab.spearman(c["x"], c["y"]), cols, ids, b=200)
    assert a == b
    assert a["lo95"] < a["point"] < a["hi95"] and a["excludes_0"] is True


def test_corr_block_drops_missing_controls_and_reports_them():
    cols = {"x": np.arange(20, dtype=float), "y": np.arange(20, dtype=float) ** 2,
            "z": np.where(np.arange(20) % 5 == 0, np.nan, np.arange(20, dtype=float))}
    res = lab.corr_block(cols, list(range(20)), "x", "y", ("z",), [2016] * 20, b=50)
    assert res["dropped"] == 4 and res["n"] == 16
    assert set(res["by_season"]) == {"2016"}


def test_part_f_trigger_reads_the_three_registered_items():
    blk_in = {"n": 100, "point": 0.1, "lo95": 0.02, "hi95": 0.2, "excludes_0": True}
    blk_out = {"n": 100, "point": 0.05, "lo95": -0.02, "hi95": 0.12, "excludes_0": False}
    a = {"A2": {"woba_y1": blk_out}}
    c = {"by_role": {"starters": {"C2": {"pbf|ra9_y1": blk_out}},
                     "relievers": {"C2": {"pbf|ra9_y1": blk_out}}}}
    assert lab.part_f(a, c)["any"] is False
    c["by_role"]["relievers"]["C2"]["pbf|ra9_y1"] = blk_in
    f = lab.part_f(a, c)
    assert f["any"] is True and f["residual_value_shown"] == {"h": False, "s": False, "r": True}


def test_dry_run_on_the_fixture_with_nulls(tmp_path):
    out = tmp_path / "pe_dry.json"
    res = lab.dry_run(out)
    assert out.exists()
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["mode"] == "dry-run"
    assert res["A"]["pairs"] > 0 and res["A"]["missing_xwoba"] > 0
    assert res["C"]["pairs"] > 0
    assert abs(res["D2"]["zero_sum_total_runs"]) < 1e-6
    assert res["E_split_half_null"] == float("inf")
    assert set(res["F"]["residual_value_shown"]) == {"h", "r", "s"}


def test_dry_run_refuses_a_path_under_data(tmp_path):
    with pytest.raises(lab.LabRefused):
        lab.dry_run(ROOT / "data" / "_labs" / "pe_dry.json")


def test_count_lift_walk_on_one_synthetic_plate_appearance():
    pd = pytest.importorskip("pandas")
    cvd = json.loads((ROOT / "data" / "count_value.json").read_text(encoding="utf-8"))
    blk = cvd["by_season"]["2024"]
    t288, re24 = blk["re288"], blk["re24"]
    pa = pd.DataFrame([{
        "game_pk": 1, "at_bat_index": 0, "half": "top", "batter_id": 11, "is_pa": True,
        "event_type": "field_out", "outs_before": 0, "on_first": None, "on_second": None,
        "on_third": None, "end_on_first": None, "end_on_second": None, "end_on_third": None,
        "end_outs": 1, "runs_scored_on_play": 0,
        "states_json": "[[2,null,null,null,0,null,null,null,1,0]]"}])
    # the runner record's base columns are nullable integers: an empty base is pd.NA,
    # which the first run read as occupied (lab part 10, 2026-10-15 note)
    for c in ("on_first", "on_second", "on_third", "end_on_first", "end_on_second", "end_on_third"):
        pa[c] = pd.array([pd.NA], dtype="Int64")
    plays = pd.DataFrame([{"game_pk": 1, "at_bat_index": 0, "pitcher_id": 99, "outs_before": 0,
                           "outs_after": 1}])
    pit = pd.DataFrame([{"game_pk": 1, "at_bat_index": 0, "pitch_number": i + 1, "call_code": c}
                        for i, c in enumerate(["B", "B", "X"])])
    ev = pd.DataFrame(columns=["game_pk", "at_bat_index", "index", "type", "description"])
    w = lab.walk_corpus_season(2024, {"pa": pa, "plays": plays, "pitches": pit, "events": ev},
                               t288, re24, {})
    (row,) = w["rows"]
    bat, gk, _date, pid, is_sp, cls, npit, cl, rv, pss, half = row
    assert (bat, gk, pid, is_sp, cls, npit, pss, half) == (11, 1, 99, 1, "out_in_play", 3, 1, "top")
    assert cl == pytest.approx(t288["2-0|0|0"] - re24["0|0"])
    assert rv == pytest.approx(re24["0|1"] - re24["0|0"])
    assert w["receipt"]["identity_share"] == 1.0
