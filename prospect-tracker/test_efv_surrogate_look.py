# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""tools/efv_surrogate_look.py on fixtures (SURROGATE_2026_GATE.md Q7). No test reads a
frame, an outcome or a label, and no test runs a look."""
from __future__ import annotations

import json

import numpy as np
import pytest

import efv_surrogate_guard as G
from tools import efv_surrogate_look as K


@pytest.fixture()
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / G.ETA_EVAL_NAME).write_text(
        json.dumps({G.ETA_LOOK_BLOCK: {"decision": {"verdict": "fixture"}}}),
        encoding="utf-8")
    monkeypatch.setattr(G, "DATA_DIR", data)
    monkeypatch.setattr(G, "ROOT", tmp_path)
    monkeypatch.setattr(K, "DATA_DIR", data)
    monkeypatch.setattr(K, "CACHE_DIR", tmp_path / ".cache" / G.OWN_CACHE_DIR)
    monkeypatch.setattr(K, "t5_assert_static", lambda ctx: ["fixture"])
    return data


def _registered(monkeypatch, sha="a" * 40):
    monkeypatch.setattr(K, "registered_sha", lambda: sha)


def _look1(data):
    p = data / G.LOOK_1_RECORD_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"item": G.LOOK_1_RECORD_ITEM, "role": "reserved",
                             "one_read": True, "generated_at": "2026-10-08T21:38:56Z",
                             "gate": {"guards": {"r_vm_cohort_read": [2025]}}}),
                 encoding="utf-8")


# ---------------------------------------------------------------------------
# refusals
# ---------------------------------------------------------------------------

def test_refuses_without_a_registered_commit(env, monkeypatch):
    monkeypatch.setattr(K, "registered_sha", lambda: None)
    with pytest.raises(K.LookRefused, match="REGISTERED"):
        K.preflight(data_dir=env, check_busy=False)


def test_registered_sha_is_none_or_a_full_sha():
    sha = K.registered_sha()
    assert sha is None or len(sha) == 40


def test_refuses_a_spent_look_by_artifact(env, monkeypatch):
    _registered(monkeypatch)
    (env / K.ARTIFACT).write_text(json.dumps({K.READ_KEY: {"verdicts": {}}}),
                                  encoding="utf-8")
    with pytest.raises(K.LookRefused, match="no second look"):
        K.preflight(data_dir=env, check_busy=False)


def test_refuses_a_spent_look_by_marker(env, monkeypatch):
    _registered(monkeypatch)
    K.CACHE_DIR.mkdir(parents=True)
    (K.CACHE_DIR / G.LOOK_MARKER).write_text("{}", encoding="utf-8")
    with pytest.raises(K.LookRefused, match="began scoring"):
        K.preflight(data_dir=env, check_busy=False)


def test_refuses_beside_another_gates_look(env, monkeypatch, tmp_path):
    _registered(monkeypatch)
    _look1(env)
    other = tmp_path / ".cache" / "dvm_difficulty"
    other.mkdir(parents=True)
    (other / G.LOOK_MARKER).write_text("{}", encoding="utf-8")
    with pytest.raises(K.LookRefused, match="dvm_difficulty"):
        K.preflight(data_dir=env, check_busy=False)


@pytest.mark.parametrize("day", ["2026-10-23", "2026-11-06", "2026-11-13",
                                 "2026-11-20", "2026-12-01"])
def test_no_calendar_day_is_refused(env, monkeypatch, day):
    _registered(monkeypatch)
    _look1(env)
    ctx = K.preflight(data_dir=env, today=day, check_busy=False)
    assert ctx["today"] == day and G.LOOK_1 in ctx["look_records"]


def test_refuses_while_busy(env, monkeypatch):
    _registered(monkeypatch)
    _look1(env)
    monkeypatch.setattr(K, "busy_processes", lambda: ["123: python run_monthly.py"])
    with pytest.raises(K.LookRefused, match="run_monthly"):
        K.preflight(data_dir=env)


def test_refuses_without_the_eta_record(env, monkeypatch):
    _registered(monkeypatch)
    _look1(env)
    (env / G.ETA_EVAL_NAME).unlink()
    with pytest.raises(G.ReservedFrameError, match="ETA"):
        K.preflight(data_dir=env, check_busy=False)


def test_refuses_without_look_1(env, monkeypatch):
    _registered(monkeypatch)
    with pytest.raises(K.LookRefused, match="look 1"):
        K.preflight(data_dir=env, check_busy=False)


# ---------------------------------------------------------------------------
# the one-look crash protocol
# ---------------------------------------------------------------------------

def _drv_ok(ctx):
    rows = [{"decision_year": v, "v2": {d: float(i % 3) for d in
                                        K.T2_MILB_DRIVERS + K.T2_OTHER_DRIVERS}}
            for v in K.G_S_VINTAGES for i in range(5)]
    return {"v2rows": {"hit": rows, "pit": rows}}


def test_a_constant_driver_stops_before_any_outcome(env, monkeypatch, tmp_path):
    _registered(monkeypatch)
    _look1(env)

    def drv(ctx):
        d = _drv_ok(ctx)
        d["v2rows"]["hit"] = [dict(r, v2=dict(r["v2"], milb_absent=1.0))
                              for r in d["v2rows"]["hit"]]
        return d
    called = []
    rc = K.run_look(tmp_path / "task", data_dir=env, B=5, check_busy=False,
                    _assemble_drivers=drv,
                    _assemble_outcomes=lambda c, d: called.append(1))
    assert rc == 3 and not called
    assert not (K.CACHE_DIR / G.LOOK_MARKER).exists()
    assert "hit:milb_absent" in (tmp_path / "task" / "OWNER_QUESTION.md").read_text(
        encoding="utf-8")


def test_a_crash_after_scoring_began_spends_the_look(env, monkeypatch, tmp_path):
    _registered(monkeypatch)
    _look1(env)

    def boom(ctx, drv):
        raise ValueError("fixture crash")
    with pytest.raises(ValueError):
        K.run_look(tmp_path / "task", data_dir=env, B=5, check_busy=False,
                   _assemble_drivers=_drv_ok, _assemble_outcomes=boom)
    assert (K.CACHE_DIR / G.LOOK_MARKER).exists()
    assert "crashed" in (tmp_path / "task" / "OWNER_QUESTION.md").read_text(
        encoding="utf-8")
    assert (tmp_path / "task" / "look_stdout.txt").exists()
    assert K.run_look(tmp_path / "task2", data_dir=env, B=5, check_busy=False,
                      _assemble_drivers=_drv_ok, _assemble_outcomes=boom) == 2


def test_a_moved_pin_voids_the_run(env, monkeypatch, tmp_path):
    _registered(monkeypatch)
    _look1(env)
    pins = iter([{"files": {"a": "1"}}, {"files": {"a": "2"}}])
    monkeypatch.setattr(K, "input_pins", lambda d=None: next(pins))
    with pytest.raises(RuntimeError, match="moved"):
        K.run_look(tmp_path / "task", data_dir=env, B=5, check_busy=False,
                   _assemble_drivers=_drv_ok,
                   _assemble_outcomes=lambda c, d: K.fixture_data(n=60))
    assert not (env / K.ARTIFACT).exists()


def test_a_clean_run_writes_the_read_and_prints_sds_first(env, monkeypatch, tmp_path):
    _registered(monkeypatch)
    _look1(env)
    monkeypatch.setattr(K, "input_pins", lambda d=None: {"files": {}})
    rc = K.run_look(tmp_path / "task", data_dir=env, B=20, check_busy=False,
                    _assemble_drivers=_drv_ok,
                    _assemble_outcomes=lambda c, d: K.fixture_data(n=80))
    assert rc == 0
    doc = json.loads((env / K.ARTIFACT).read_text(encoding="utf-8"))
    assert "OWNER-WAIVED EARLY READ" in doc[K.READ_KEY]["receipt"]["note"]
    text = (tmp_path / "task" / "look_stdout.txt").read_text(encoding="utf-8")
    assert text.index("BOOTSTRAP SDs") < text.index("POINTS")
    assert K.run_look(tmp_path / "t3", data_dir=env, B=5, check_busy=False) == 2


# ---------------------------------------------------------------------------
# statistics and reporting
# ---------------------------------------------------------------------------

def test_fnum_handles_none_nan_and_inf():
    assert K.fnum(None) == "NA" and K.fnum(float("nan")) == "NA"
    assert K.fnum(float("inf")) == "NA" and K.fnum("x") == "NA"
    assert K.fnum(0.5) == "+0.5000" and K.fnum(-0.25) == "-0.2500"


def test_the_dry_run_reports_fixtures_with_nulls(tmp_path):
    block = K.run_dry(tmp_path, B=20)
    text = (tmp_path / "dry_run.txt").read_text(encoding="utf-8")
    assert text.index("BOOTSTRAP SDs") < text.index("POINTS")
    json.loads((tmp_path / "dry_run.json").read_text(encoding="utf-8"))
    assert set(block["verdicts"]) == {"T1", "T2", "T3", "T4"}


def test_report_lines_with_all_null_cells():
    block = {"cells": {"x": {"point": None, "sd_player": float("nan"), "lo95": None}},
             "verdicts": {}}
    lines = K.report_lines(block)
    assert any("sd_player NA" in ln for ln in lines)
    assert any(ln.startswith("T1: NA") for ln in lines)


def test_score_transfer_on_empty_input():
    block = K.score_transfer({}, B=5)
    assert block["verdicts"]["T1"].startswith("UNDECIDED")
    assert block["verdicts"]["T3"].startswith("STOP")
    assert block["verdicts"]["T2"] == "NA" and block["verdicts"]["T4"] == "NA"


def test_spearman_and_within():
    x = np.arange(30.0)
    assert K.spearman(x, x) == pytest.approx(1.0)
    assert K.spearman(x, -x) == pytest.approx(-1.0)
    assert K.spearman([1, 2], [1, 2]) is None
    assert K.spearman(np.ones(10), x[:10]) is None
    g = np.repeat([0, 1], 15)
    assert K.within_spearman(x, x, g, min_rows=10) == pytest.approx(1.0)
    assert K.within_spearman(x, x, g, min_rows=20) is None


def test_partial_spearman_removes_the_shared_driver():
    rng = np.random.default_rng(1)
    z = rng.normal(size=500)
    x = z + rng.normal(scale=0.1, size=500)
    y = z + rng.normal(scale=0.1, size=500)
    assert abs(K.partial_spearman(x, y, z)) < 0.2


def test_slope_given_recovers_a_slope():
    rng = np.random.default_rng(2)
    u, d = rng.normal(size=400), rng.normal(size=400)
    y = 1 + 0.5 * u + 2.0 * d
    assert K.slope_given(y, u, d) == pytest.approx(2.0)
    assert K.slope_given(y, u, np.ones(400)) is None


def test_fisher_z_and_the_t3_band():
    d, lo, hi = K.fisher_z_diff_ci(0.40, 4000, 0.41, 4000)
    assert lo < d < hi and K.t3_verdict(lo, hi) == "PASS"
    d, lo, hi = K.fisher_z_diff_ci(0.40, 200, 0.10, 200)
    assert K.t3_verdict(lo, hi) == "STOP"
    assert K.fisher_z_diff_ci(None, 10, 0.1, 10) == (None, None, None)


def test_t1_t2_t4_rules():
    assert K.t1_verdict({"hit": 0.55, "pit": 0.51}) == "PASS"
    assert K.t1_verdict({"hit": 0.55, "pit": 0.49}) == "FAIL"
    assert K.t1_verdict({"hit": 0.55, "pit": None}).startswith("UNDECIDED")
    assert K.t2_driver_verdict(0.01, True, True, 1.0)
    assert not K.t2_driver_verdict(0.01, True, False, 1.0)
    assert not K.t2_driver_verdict(0.01, True, True, 2.5)
    assert not K.t2_driver_verdict(-0.01, True, True, 1.0)
    assert K.t4_verdict(-0.006, 0.01, None)["harm"]
    assert K.t4_verdict(0.0, -0.001, None)["harm"]
    v = K.t4_verdict(0.0, 0.02, 0.01)
    assert not v["harm"] and v["beats_twin"]


def test_cells_are_seeded_and_club_clustered():
    x = np.arange(100.0)

    def stat(i):
        return float(x[i].mean())
    clubs = np.repeat(np.arange(10), 10)
    a = K.cluster_bootstrap(stat, 100, clubs, B=50)
    b = K.cluster_bootstrap(stat, 100, clubs, B=50)
    assert np.array_equal(a, b) and a.size == 50
    c = K.cell(stat, 100, list(range(100)), clubs, B=50)
    assert c["sd_club"] > c["sd_player"]
    assert c["mde95"] == pytest.approx(K.Z95_ONE * c["sd_player"])


def test_the_variance_check_reads_drivers_only():
    rows = [{"decision_year": v, "v2": {d: float(i) for d in
                                        K.T2_MILB_DRIVERS + K.T2_OTHER_DRIVERS}}
            for v in K.G_S_VINTAGES for i in range(3)]
    assert K.driver_variance_check({"hit": rows}) == []
    for r in rows:
        if r["decision_year"] <= 2013:
            r["v2"]["on_40man"] = 0.0
    assert K.driver_variance_check({"hit": rows}) == ["hit:on_40man:2011-2013"]


def test_no_fv_cell_grouping_and_no_banned_call():
    src = (K.ROOT / "tools" / "efv_surrogate_look.py").read_text(encoding="utf-8")
    for banned in ("fv_bucket", "fv_cell", "by_fv", "guard_score_request(",
                   "source_backtest", "run_backtest", "—"):
        assert banned not in src


# ---------------------------------------------------------------------------
# the 2026-10-15 amendments (SG_8, before the look)
# ---------------------------------------------------------------------------

def test_a_t5_failure_stops_before_any_outcome(env, monkeypatch, tmp_path):
    _registered(monkeypatch)
    _look1(env)

    def bad(ctx):
        raise K.T5Error("fixture T5")
    called = []
    rc = K.run_look(tmp_path / "task", data_dir=env, B=5, check_busy=False,
                    _assemble_drivers=_drv_ok,
                    _assemble_outcomes=lambda c, d: called.append(1), _t5_assert=bad)
    assert rc == 4 and not called
    assert not (K.CACHE_DIR / G.LOOK_MARKER).exists()
    assert "T5" in (tmp_path / "task" / "OWNER_QUESTION.md").read_text(encoding="utf-8")


def test_t1_exits_print_before_the_sds_and_tolerate_none(tmp_path):
    K.run_dry(tmp_path, B=10)
    text = (tmp_path / "dry_run.txt").read_text(encoding="utf-8")
    assert text.index("T1 EXITS") < text.index("BOOTSTRAP SDs") < text.index("POINTS")
    assert text.index("POINTS") < text.index("DESCRIPTIVE")
    assert "other NA" in text and "g_skill" in text and "bypass share" in text


def test_t2_milb_drivers_read_the_2015_2019_partial():
    block = K.score_transfer(K.fixture_data(n=180), B=10)
    for side in K.SIDES:
        lo_all = block["cells"][f"T2a|{side}|partial"]["lo95"]
        lo_milb = block["cells"][f"T2a|{side}|partial_V2015_2019"]["lo95"]
        drv = block["t2"][side]["drivers"]
        for d in K.T2_MILB_DRIVERS:
            assert all(c["partial_lo95"] == lo_milb for c in drv[d].values())
            assert set(drv[d]) == {"pooled", "2015-2016", "2017-2019"}
        for d in K.T2_OTHER_DRIVERS:
            assert all(c["partial_lo95"] == lo_all for c in drv[d].values())
        assert block["t2"][side]["n_milb"] < block["t2"][side]["n"]
    assert K.T2_MILB_YEARS == (2015, 2016, 2017, 2018, 2019)


def test_t4_is_one_within_cell_per_side():
    block = K.score_transfer(K.fixture_data(n=120), B=10)
    t4 = [k for k in block["cells"] if k.startswith("T4|")]
    assert sorted(t4) == sorted(f"T4|{s}|{a}" for s in K.SIDES
                                for a in ("aug_minus_inc", "real_minus_twin"))
    assert set(block["t4"]) == set(K.SIDES)
    assert block["t4"]["hit"]["vintages"] == list(K.T4_EVAL_VINTAGES)


def test_exit_reasons():
    assert K._exit_reason({"status": "reserved_vm"}) == "reserved_vm"
    assert K._exit_reason({"status": "identity_conflict"}) == "identity_conflict"
    assert K._exit_reason({"status": "not_reached", "reached": "censored_never"}) ==         "censored_never"
    assert K._exit_reason({"status": "ok", "reached": "reached"}) == "other"


def test_t5_outcomes_refuses_an_l6_for_a_2025_debutant():
    built = {2016: [{"player_key": "a", "s5_status": "ACTIVE"}]}
    K.t5_assert_outcomes("hit", built, {2016: {"a": {"debut_year": 2025, "l6": None}}})
    with pytest.raises(K.T5Error, match="2025"):
        K.t5_assert_outcomes("hit", built, {2016: {"a": {"debut_year": 2025, "l6": 1.0}}})
    with pytest.raises(K.T5Error, match="status"):
        K.t5_assert_outcomes("hit", {2016: [{"player_key": "a", "s5_status": "X"}]}, {})


def test_t5_static_holds_on_this_tree():
    import subprocess
    r = subprocess.run(["git", "-C", str(K.ROOT), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not G.eta_look_recorded():
        pytest.skip("no git tree or no ETA record here")
    done = K.t5_assert_static({})
    assert any("s11 blob" in ln for ln in done) and any("AP+" in ln for ln in done)
