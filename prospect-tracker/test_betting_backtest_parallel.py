# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The backtest's gate blocks fan out across processes (perf(betting):
parallel backtest gates, 2026-10-03).

WHAT THESE TESTS PROTECT: the pool changes WHEN the blocks run and nothing
about what they compute. So: the worker entry is a top-level picklable
function and a real pool returns what the in-process call returns; the kill
switch and the games floor keep small or test-sized seasons in the parent,
where monkeypatched module state lives; a broken pool falls back to the serial
path with the same answer; the sensitivity grid built from supplied gate runs
is the grid built from its own runs; and the eval artifact keeps the key order
it has always had, with `fit_window_probe` still the last key of `ridge_fit`.

The byte-identical proof on the real season (serial vs pool, HEAD vs patch)
lives in the commit that landed this; it takes twenty minutes and does not
belong in the suite."""
from __future__ import annotations

import concurrent.futures
import json
import pickle

import pytest

import betting_model as bm
import leaderboard_vintages as lv
from test_leaderboard_vintages import ORGS, _daterange, _fake_games, _record, _seed


@pytest.fixture()
def store(tmp_path, monkeypatch):
    d = tmp_path / "leaderboard_vintages"
    d.mkdir()
    monkeypatch.setattr(lv, "VINTAGE_DIR", d)
    lv.reset_cache()
    bm.reset_vintage_cache()
    yield d
    lv.reset_cache()
    bm.reset_vintage_cache()


def _inputs():
    games = _fake_games(_daterange("2026-06-01", 32))
    teams = bm.team_inputs_from_vintage(_record("2026-08-04", bump=5.0))
    starters = bm.starter_inputs_from_vintage(_record("2026-08-04"))
    parks = {o: 1.0 for o in ORGS}
    return games, teams, parks, starters


def test_block_entry_is_a_top_level_picklable_function():
    """A spawn start (Windows) pickles the callable by module and name; a
    closure or a lambda would fail there and only there."""
    assert pickle.loads(pickle.dumps(bm._backtest_block)) is bm._backtest_block
    assert bm._backtest_block.__module__ == "betting_model"


@pytest.mark.parametrize("spec", [("in_sample", None), ("dispersion_q", 0.7)])
def test_a_real_pool_returns_what_the_in_process_call_returns(spec):
    """One worker, one block: the value that comes back across the process
    boundary is the value the parent computes, key order included."""
    games, teams, parks, starters = _inputs()
    args = (games, teams, parks, starters, None, {})
    serial = bm._backtest_block(spec, *args)
    with concurrent.futures.ProcessPoolExecutor(max_workers=1) as pool:
        remote = pool.submit(bm._backtest_block, spec, *args).result(timeout=120)
    assert remote["spec"] == spec and remote["failed"] is None
    assert json.dumps(remote["value"]) == json.dumps(serial["value"])
    assert remote["log"] == serial["log"]


def test_kill_switch_and_games_floor_keep_the_blocks_in_process(monkeypatch):
    monkeypatch.setenv(bm.BACKTEST_SERIAL_ENV, "1")
    assert bm.backtest_runs_parallel(10 ** 6) is False
    monkeypatch.setenv(bm.BACKTEST_SERIAL_ENV, "0")
    assert bm.backtest_runs_parallel(bm.BACKTEST_PARALLEL_MIN_GAMES - 1) is False
    monkeypatch.delenv(bm.BACKTEST_SERIAL_ENV, raising=False)
    assert bm.backtest_runs_parallel(bm.BACKTEST_PARALLEL_MIN_GAMES - 1) is False
    assert bm.backtest_runs_parallel(bm.BACKTEST_PARALLEL_MIN_GAMES) is (
        bm.backtest_workers() > 1)
    assert 1 <= bm.backtest_workers() <= bm.BACKTEST_MAX_WORKERS


def test_a_broken_pool_falls_back_to_the_serial_path(monkeypatch, caplog):
    """The pool is a speedup, never a dependency: when it cannot start the
    blocks run in the parent, the answer is the same and the log says so."""
    games, teams, parks, starters = _inputs()
    monkeypatch.setattr(bm, "backtest_runs_parallel", lambda n: True)

    class _Broken:
        def __init__(self, *a, **k):
            pass

        def submit(self, *a, **k):
            raise RuntimeError("no pool here")

        def shutdown(self, *a, **k):
            pass

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", _Broken)
    specs = [("in_sample", None), ("dispersion_q", 0.6)]
    args = (games, teams, parks, starters, None, {})
    with caplog.at_level("WARNING", logger="betting_model"):
        got = bm._run_backtest_blocks(specs, *args)
    assert list(got) == specs
    for spec in specs:
        assert json.dumps(got[spec]["value"]) == json.dumps(bm._backtest_block(spec, *args)["value"])
    assert any("process pool failed" in r.message for r in caplog.records)


def test_sensitivity_grid_from_supplied_runs_is_the_grid_from_its_own(monkeypatch):
    games, teams, parks, starters = _inputs()
    own = bm.dispersion_gate_sensitivity(games, teams=teams, parks=parks, starters=starters)
    runs = {q: bm.run_dispersion_gate(games, teams=teams, parks=parks, starters=starters,
                                      split_q=q, runline_side=bm.RUNLINE_SIDE_AMENDMENT)
            for q in bm.DISPERSION_SPLIT_QUANTILES}

    def _boom(*a, **k):
        raise AssertionError("a supplied run was recomputed")

    monkeypatch.setattr(bm, "run_dispersion_gate", _boom)
    supplied = bm.dispersion_gate_sensitivity(games, teams=teams, parks=parks,
                                              starters=starters, gate_runs=runs)
    assert json.dumps(supplied) == json.dumps(own)


def test_ridge_gate_from_supplied_pieces_is_the_gate_from_its_own(store, monkeypatch):
    """The ridge gate's three split rows and its served window travel as
    separate blocks; assembled from supplied pieces the gate is the gate.

    The synthetic four-org design does not price under the ridge arm (every
    row reports "arms did not price the same games"), so what this exercises
    is the shared frame, the floors path, the row plumbing and the served
    window; the real-season equality is the proof in the landing commit."""
    games, teams, parks, starters = _inputs()
    monkeypatch.setattr(bm, "VINTAGE_MIN_FIT_GAMES", 8)
    monkeypatch.setattr(bm, "VINTAGE_MIN_EVAL_GAMES", 4)
    monkeypatch.setattr(bm, "VINTAGE_FIT_TARGET_GAMES", 8)
    _seed(store, _daterange("2026-05-25", 40))
    own = bm.ridge_fit_gate(games, teams=teams, parks=parks, starters=starters)
    assert own["n_gradable"] == len(games) and len(own["grid"]) == len(bm.DISPERSION_SPLIT_QUANTILES)
    args = (games, teams, parks, starters, None, {})
    rows = {q: bm._backtest_block(("ridge_q", q), *args)["value"]
            for q in bm.DISPERSION_SPLIT_QUANTILES}
    served = bm._backtest_block(("ridge_served", None), *args)["value"]
    assert all(r is not None for r in rows.values()) and served is not None

    def _boom(*a, **k):
        raise AssertionError("a supplied piece was recomputed")

    monkeypatch.setattr(bm, "_ridge_arm", _boom)
    lines = []
    supplied = bm.ridge_fit_gate(games, teams=teams, parks=parks, starters=starters,
                                 log_fn=lines.append, split_rows=rows, served_window=served)
    assert json.dumps(supplied) == json.dumps(own)
    assert len(lines) == sum(1 for r in own["grid"] if r.get("status") == "ran")


EVAL_KEY_ORDER = [
    "generated_at", "model_version", "season", "validated", "contaminated",
    "contamination", "gates_picks", "min_edge", "n_games", "modes", "headline_mode",
    "vintage_coverage", "in_sample", "run_dispersion", "vintage", "starter_basis",
    "prob_calibration", "benchmarks", "per_market", "ridge_fit", "total_level",
    "min_edge_gate", "status", "note",
]


def test_the_eval_artifact_keeps_its_key_order(store, monkeypatch):
    """The blocks are assembled after they all finish, in the order the serial
    code wrote them. A 32-game season has no forward split (fewer than 200 fit
    games), so `split_date` and `forward` are rightly absent here."""
    games, teams, parks, starters = _inputs()
    monkeypatch.setattr(bm, "completed_games", lambda season=None: list(games))
    monkeypatch.setattr(bm, "team_inputs", lambda: teams)
    monkeypatch.setattr(bm, "starter_inputs", lambda: starters)
    monkeypatch.setattr(bm, "park_index", lambda: parks)
    monkeypatch.setattr(bm, "VINTAGE_MIN_FIT_GAMES", 8)
    monkeypatch.setattr(bm, "VINTAGE_MIN_EVAL_GAMES", 4)
    monkeypatch.setattr(bm, "VINTAGE_FIT_TARGET_GAMES", 8)
    _seed(store, _daterange("2026-05-25", 40))
    assert bm.backtest_runs_parallel(len(games)) is False
    r = bm.backtest(write=False)
    assert list(r.keys()) == EVAL_KEY_ORDER
    assert r["vintage"]["status"] == "graded"
    assert list(r["ridge_fit"].keys())[-1] == "fit_window_probe"
    for k in ("sensitivity", "verdict", "verdict_note", "served", "served_alpha"):
        assert k in r["run_dispersion"]
    assert r["run_dispersion"]["split_q"] == 0.7
    assert "_per_game_p" not in r["vintage"] and "_per_game_p" not in r["in_sample"]
