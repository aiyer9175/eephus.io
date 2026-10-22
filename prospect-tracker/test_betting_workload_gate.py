# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""tools/betting_workload_gate.py, the stage-2 look tool of the section "Starter workload:
expected outs and pitches per start" (docs/diamond-betting.md), on fixtures only.

Nothing here reads a vintage record, a completed game or a price. The tests pin what the
section registered for stage 2: the refusals (before 2027-07-01, without a step Z entry,
without 5l's mgmt_policy_gate block, a second run by the artifact or by the section, a
2026 game, a write to data/betting_model_eval.json), the yields (another look that day,
criterion 4 not yet held) and the NOT READ records; the arithmetic of the paired t, the
N6 Holm step, the power precondition and its 0.0024 floor, the twin bar, the VIF read and
the verdict; the candidate share entering through the served clip; the power block on
disk before any eval-half game is graded; and the reporting path end to end on a fixture
with nulls, through the served grader. Every artifact goes to tmp_path; data/ is never
written.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
TOOL_PATH = ROOT / "tools" / "betting_workload_gate.py"
GATE_DOC = ROOT / "docs" / "diamond-betting.md"
STEP_Z_TEXT = "## 9. Results\n\n### 2026-10-03: step Z, the fWAR label epoch's results\n"
NEIGHBOURS = ("ip_per_gs", "sp_tto3_bf", "mg_hook_pitches_l30")


def _load():
    spec = importlib.util.spec_from_file_location("betting_workload_gate", TOOL_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load()
DOC_TEXT = GATE_DOC.read_text(encoding="utf-8")
JULY1 = dt.date(2027, 7, 1)
AUG1 = dt.date(2027, 8, 1)


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t)


def _art(tmp_path, stage1="PASS", stage2=None) -> Path:
    p = tmp_path / "starter_workload_eval.json"
    art = gate.fixture_artifact(stage1)
    if stage2 is not None:
        art["stage2"] = stage2
    p.write_text(json.dumps(art), encoding="utf-8")
    return p


def _doc_with(heading: str) -> str:
    """The real document with a fixture stage-2 heading appended inside the section."""
    sec = gate.section_text(DOC_TEXT).replace("\r\n", "\n")
    text = DOC_TEXT.replace("\r\n", "\n")
    return text.replace(sec, sec.rstrip("\n").removesuffix("---").rstrip("\n")
                        + "\n\n" + heading + "\n\nfixture\n\n---\n\n")


MGMT = {"where": "fixture", "run_date": "2027-06-30"}


# ---------------------------------------------------------------------------
# 1. the registered constants, in code and in the section
# ---------------------------------------------------------------------------
def test_constants_are_the_sections():
    import betting_model as bm
    assert gate.EARLIEST_LOOK == dt.date(2027, 7, 1)
    assert gate.WAIT_FOR_NEXT_SEASON == dt.date(2027, 8, 1)
    assert gate.FIT_TARGET_GAMES == bm.VINTAGE_FIT_TARGET_GAMES == 300
    assert gate.MIN_EVAL_GAMES == bm.VINTAGE_MIN_GRADED_GAMES == 600
    assert gate.N_TWIN == 200 and gate.T_BAR == 1.645 and gate.VIF_BAR == 5.0
    assert gate.FLOOR_BRIER == 0.0024
    assert gate.N6_MEMBERS == ("F05-07", "F08-01", "G4-02", "G4-10")
    assert gate.SHARE_CLIP == (0.25, 0.85)
    sec = _norm(gate.section_text(DOC_TEXT))
    for needle in ("2027-07-01", "2027-08-01", "0.0024", "0.0125", "m = 4",
                   "(2.241 + 0.842) x sd_d / sqrt(600) = 0.126 x sd_d", "200 draws",
                   "VINTAGE_FIT_TARGET_GAMES (300)", "VINTAGE_MIN_GRADED_GAMES (600)",
                   "clip(xOuts / 27, 0.25, 0.85)", "tools/betting_workload_gate.py",
                   "### Stage 2 result (run DATE, once): VERDICT"):
        assert needle in sec, needle
    assert round(gate.power_precondition(1.0)["multiplier"], 3) == 0.126


def test_the_vif_neighbours_are_read_off_criterion_5():
    assert gate.registered_vif_neighbours(DOC_TEXT) == NEIGHBOURS
    with pytest.raises(gate.LookRefused):
        gate.registered_vif_neighbours(DOC_TEXT.replace("(5) the VIF read against",
                                                        "(5) the read against"))


# ---------------------------------------------------------------------------
# 2. the refusals, the yields and the NOT READ records
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("day", [dt.date(2026, 10, 21), dt.date(2027, 4, 1),
                                 dt.date(2027, 6, 30)])
def test_refuses_before_2027_07_01(day):
    with pytest.raises(gate.LookRefused, match="before the registered earliest look"):
        gate.check_clock(day, STEP_Z_TEXT)


def test_refuses_without_a_step_z_entry():
    with pytest.raises(gate.LookRefused, match="step Z"):
        gate.check_clock(JULY1, "## 9. Results\n\nnothing yet\n", pre_epoch_dir=None)
    clock = gate.check_clock(JULY1, STEP_Z_TEXT)
    assert clock["today"] == "2027-07-01" and clock["step_z_entry"] == "2026-10-03"


@pytest.mark.parametrize("stage2,match", [
    ({"season": 2027, "status": "scoring"}, "never rerun"),
    ({"season": 2027, "status": "stopped"}, "never rerun"),
    ({"season": 2027, "status": "complete", "verdict": "FAIL"}, "final"),
    ({"season": 2027, "status": "complete", "verdict": "PASS"}, "final"),
    ({"season": 2027, "status": "complete", "verdict": "PASS-BELOW-FLOOR"}, "final"),
    ({"season": 2027, "status": "complete", "verdict": "UNDERPOWERED"}, "next season"),
    ({"season": 2027, "status": "complete", "verdict": "NOT READ"}, "next season"),
])
def test_the_one_run_guard_reads_the_artifact(tmp_path, stage2, match):
    p = _art(tmp_path, stage2=stage2)
    with pytest.raises(gate.LookRefused, match=match):
        gate.check_one_run(p, DOC_TEXT, 2027)


def test_a_wait_verdict_of_an_earlier_season_and_a_yield_do_not_refuse(tmp_path):
    gate.check_one_run(_art(tmp_path, stage2={"season": 2027, "status": "complete",
                                              "verdict": "UNDERPOWERED"}), DOC_TEXT, 2028)
    gate.check_one_run(_art(tmp_path, stage2={"season": 2027, "status": "yielding",
                                              "yields": [{"date": "2027-07-01"}]}),
                       DOC_TEXT, 2027)
    gate.check_one_run(tmp_path / "absent.json", DOC_TEXT, 2027)


@pytest.mark.parametrize("heading,season", [
    ("### Stage 2 result (run 2027-07-02, once): FAIL", 2028),
    ("### Stage 2 result (run 2027-07-02, once): PASS-BELOW-FLOOR", 2028),
    ("### Stage 2 result (run 2027-08-01, once): NOT READ", 2027),
])
def test_the_one_run_guard_reads_the_section(tmp_path, heading, season):
    with pytest.raises(gate.LookRefused, match="section records"):
        gate.check_one_run(tmp_path / "absent.json", _doc_with(heading), season)


def test_the_recorded_document_has_no_stage_2_result_yet():
    assert not gate.STAGE2_HEADING_RE.search(gate.section_text(DOC_TEXT))


def test_5l_block_is_found_in_json_or_in_the_section(tmp_path):
    a = tmp_path / "betting_model_eval.json"
    a.write_text(json.dumps({"vintage": {}}), encoding="utf-8")
    assert gate.mgmt_policy_block("no 5l here", json_paths=[a]) is None
    b = tmp_path / "betting_mgmt_policy_eval.json"
    b.write_text(json.dumps({"mgmt_policy_gate": {"run_date": "2027-07-01"}}),
                 encoding="utf-8")
    assert gate.mgmt_policy_block("", json_paths=[a, b]) == {
        "where": "betting_mgmt_policy_eval.json", "run_date": "2027-07-01"}
    doc = ("## 5l. Club policy\n\ntext\n\n### Result (run 2027-07-02, once): FAIL\n\n"
           "## 5m. next\n")
    got = gate.mgmt_policy_block(doc, json_paths=[a])
    assert got and got["run_date"] == "2027-07-02"
    assert gate.mgmt_policy_block(DOC_TEXT, json_paths=[a]) is None


def test_other_looks_on_the_day(tmp_path):
    d = tmp_path / "X_GATE.md"
    d.write_text("The one look is taken on 2027-07-09, once.\nNothing on 2027-07-08.\n",
                 encoding="utf-8")
    assert gate.other_looks_on(dt.date(2027, 7, 8), docs=[d]) == []
    assert gate.other_looks_on(dt.date(2027, 7, 9), docs=[d])
    assert gate.other_looks_on(dt.date(2027, 10, 20), docs=[])
    assert gate.other_looks_on(dt.date(2027, 7, 3), docs=[],
                               mgmt={"run_date": "2027-07-03"})


def _small_source(**kw):
    return gate.synthetic_source(neighbours=NEIGHBOURS, **kw)


def _no_grader(*a, **k):
    raise AssertionError("no outcome may be graded on this path")


def test_refuses_without_5l_block_before_aug1_and_records_not_read_after(tmp_path):
    p = _art(tmp_path)
    with pytest.raises(gate.LookRefused, match="mgmt_policy_gate"):
        gate.run_stage2(_small_source(n_dates=20), p, today=JULY1, mode="test",
                        doc_text=DOC_TEXT, mgmt=None, other_looks=[], grade_fn=_no_grader)
    assert "stage2" not in json.loads(p.read_text(encoding="utf-8"))
    blk = gate.run_stage2(_small_source(n_dates=20), p, today=AUG1, mode="test",
                          doc_text=DOC_TEXT, mgmt=None, other_looks=[], grade_fn=_no_grader)
    assert blk["verdict"] == "NOT READ" and "2028" in blk["reason"]


def test_another_look_that_day_yields_and_records_the_yield(tmp_path):
    p = _art(tmp_path)
    blk = gate.run_stage2(_small_source(n_dates=20), p, today=JULY1, mode="test",
                          doc_text=DOC_TEXT, mgmt=MGMT, other_looks=["5x look"],
                          grade_fn=_no_grader)
    assert blk["status"] == "yielding" and blk["verdict"] is None
    assert blk["yields"] == [{"date": "2027-07-01", "reasons": ["5x look"]}]
    gate.check_one_run(p, DOC_TEXT, 2027)                   # a yield is not a run


def test_criterion_4_unmet_yields_then_waits_for_2028(tmp_path):
    p = _art(tmp_path)
    blk = gate.run_stage2(_small_source(n_dates=60), p, today=JULY1, mode="test",
                          doc_text=DOC_TEXT, mgmt=MGMT, other_looks=[], grade_fn=_no_grader)
    assert blk["status"] == "yielding" and "criterion 4" in blk["yields"][0]["reasons"][0]
    blk = gate.run_stage2(_small_source(n_dates=60), p, today=AUG1, mode="test",
                          doc_text=DOC_TEXT, mgmt=MGMT, other_looks=[], grade_fn=_no_grader)
    assert blk["verdict"] == "NOT READ" and blk["split"]["n_eval_games"] < 600
    with pytest.raises(gate.LookRefused):
        gate.check_one_run(p, DOC_TEXT, 2027)


def test_a_failed_stage_1_is_not_read(tmp_path):
    p = _art(tmp_path, stage1="FAIL")
    blk = gate.run_stage2(_small_source(n_dates=20), p, today=JULY1, mode="test",
                          doc_text=DOC_TEXT, mgmt=MGMT, other_looks=[], grade_fn=_no_grader)
    assert blk["verdict"] == "NOT READ" and "stage 1" in blk["reason"]


def test_a_2026_game_is_refused():
    src = _small_source(n_dates=8)
    src._games.append(dict(src._games[0], game_pk=1, date="2026-07-20", season="2026"))
    with pytest.raises(gate.LookRefused, match="2026 fit window"):
        gate.build_records(src, 2027, NEIGHBOURS)


def test_never_writes_the_nightly_betting_eval(tmp_path):
    with pytest.raises(gate.LookRefused, match="betting_model_eval"):
        gate.write_artifact({}, gate.BETTING_EVAL)
    with pytest.raises(gate.LookRefused, match="betting_model_eval"):
        gate.write_artifact({}, tmp_path / "betting_model_eval.json")


def test_a_dry_run_never_writes_under_data():
    assert gate.main(["--dry-run", "--out", str(ROOT / "data" / "x.json")]) == 2


def test_no_served_module_imports_the_tool():
    hits = []
    for base, pat in ((ROOT, "*.py"), (ROOT / "tools", "*.py"), (ROOT / "assets", "*.js")):
        for p in base.glob(pat):
            if p.name.startswith("test_") or p == TOOL_PATH:
                continue
            if "betting_workload_gate" in p.read_text(encoding="utf-8", errors="replace"):
                hits.append(p.name)
    assert not hits, hits


# ---------------------------------------------------------------------------
# 3. fixture arithmetic
# ---------------------------------------------------------------------------
def test_paired_stats_on_a_hand_row():
    d = [0.01, 0.03, -0.01, 0.05]
    st = gate.paired_stats(d)
    sd = float(np.std(d, ddof=1))
    t = 0.02 / (sd / 2.0)
    assert st["n"] == 4 and st["mean"] == pytest.approx(0.02)
    assert st["sd"] == pytest.approx(sd, abs=1e-8) and st["t"] == pytest.approx(t, abs=1e-6)
    assert st["p_one_sided"] == pytest.approx(0.5 * math.erfc(t / math.sqrt(2)), abs=1e-8)
    assert gate.paired_stats([0.1])["t"] is None
    assert gate.paired_stats([0.0, 0.0, 0.0])["t"] is None


def test_holm_in_n6():
    h = gate.holm_n6(0.0125)
    assert h["pass"] and h["threshold_self"] == 0.0125 and len(h["not_read"]) == 3
    assert not gate.holm_n6(0.013)["pass"]
    assert not gate.holm_n6(None)["pass"]
    h = gate.holm_n6(0.016, {"F05-07": 0.001})
    assert h["pass"] and h["threshold_self"] == pytest.approx(0.05 / 3, abs=1e-6)
    assert not gate.holm_n6(0.016, {"F05-07": 0.02})["pass"]
    assert gate.holm_n6(0.01, {"F05-07": 0.02})["pass"]


def test_the_power_precondition_and_its_floor():
    k = (2.241 + 0.842) / math.sqrt(600)
    lo = gate.power_precondition(0.019)
    hi = gate.power_precondition(0.02)
    assert lo["mde"] == pytest.approx(k * 0.019, abs=1e-8) and lo["status"] == "POWERED"
    assert hi["mde"] == pytest.approx(k * 0.02, abs=1e-8) and hi["status"] == "UNDERPOWERED"
    edge = 0.0024 / k
    assert gate.power_precondition(edge)["status"] == "POWERED"
    assert gate.power_precondition(None)["status"] == "UNDERPOWERED"
    assert lo["basis"] == "in-sample fit-window sd, lenient"


def test_the_twin_bar_is_the_linear_95th_percentile():
    xs = [i / 1000 for i in range(200)]
    assert gate.twin_bar(xs) == pytest.approx(0.18905)
    assert gate.twin_bar([]) is None


def test_vif_and_criterion_5():
    rng = np.random.default_rng(3)
    x = rng.normal(size=500)
    y = 0.6 * x + rng.normal(scale=0.8, size=500)
    r = float(np.corrcoef(x, y)[0, 1])
    assert gate.vif_one(y, x) == pytest.approx(1 / (1 - r * r), rel=1e-9)
    assert gate.vif_one(2 * x + 1, x) == math.inf
    z = rng.normal(size=500)
    assert gate.vif(y, [x, z]) >= gate.vif_one(y, x) - 1e-12
    tab = lambda inn, joint: {"by_neighbour": {"ip_per_gs": {"vif": inn}},  # noqa: E731
                              "joint": {"vif": joint}}
    assert gate.criterion5(tab(4.9, 4.99))
    assert gate.criterion5(tab(5.0, None))
    assert not gate.criterion5(tab(4.9, 5.1))
    assert not gate.criterion5(tab(5.01, 4.0))
    assert not gate.criterion5(tab(None, 1.0))
    assert not gate.criterion5(tab("inf", 1.0))


def test_the_verdict():
    ok = {k: True for k in ("1_paired_brier_t_and_holm", "2_log_loss_not_worse",
                            "3_permuted_twin", "4_games", "5_vif")}
    assert gate.decide(ok, 0.0024) == "PASS"
    assert gate.decide(ok, 0.0023) == "PASS-BELOW-FLOOR"
    for k in ok:
        assert gate.decide(dict(ok, **{k: False}), 0.01) == "FAIL"


def test_the_candidate_share_enters_through_the_served_clip():
    import betting_model as bm
    import betting_usage as bu
    side = {"starter": {"mlbam": 1, "sem_plus": 110.0, "ip_per_gs": 6.0}}
    for x, want in ((15.0, 15.0 / 27), (5.0, 0.25), (27.0, 0.85), (20.0, 20.0 / 27)):
        share, plus, src = bm._starter_share({}, gate._starter_for(side, x))
        assert share == pytest.approx(want) and plus == 110.0 and src == "probable"
    assert side["starter"]["ip_per_gs"] == 6.0                  # the served row is untouched
    assert gate._starter_for(side, None) is side["starter"]
    assert gate.candidate_xouts(90.0, 5.5, 4.0, 3.9) == pytest.approx(
        min(27.0, 90.0 / (5.5 * 4.0 / 3.9)))
    assert gate.candidate_xouts(None, 5.5, 4.0, 3.9) is None
    assert gate.candidate_xouts(90.0, 5.5, 4.0, 3.9) == bu.starter_workload_xouts_candidate(
        90.0, 5.5, 4.0, 3.9)


def test_the_twin_permutes_within_each_date():
    recs, _c = gate.build_records(_small_source(n_dates=12), 2027, NEIGHBOURS)
    base = gate.xouts_of(recs)
    a, b = gate.permuted_xouts(recs, 0), gate.permuted_xouts(recs, 0)
    assert a == b and a != gate.permuted_xouts(recs, 1)
    for d in {r["date"] for r in recs}:
        keys = [(r["game_pk"], s) for r in recs if r["date"] == d for s in ("home", "away")]
        assert sorted(base[k] for k in keys) == sorted(a[k] for k in keys)


def test_records_read_no_outcome_and_count_every_null():
    class Guarded(dict):
        def __getitem__(self, k):
            if k in ("home_runs", "away_runs"):
                raise AssertionError("an outcome was read while building records")
            return super().__getitem__(k)

        def get(self, k, default=None):
            if k in ("home_runs", "away_runs"):
                raise AssertionError("an outcome was read while building records")
            return super().get(k, default)

    src = _small_source(n_dates=40)
    src._games = [Guarded(g) for g in src._games]
    recs, counts = gate.build_records(src, 2027, NEIGHBOURS)
    assert counts["no_vintage"] == 12                     # two nights, six games each
    assert counts["probable_not_listed"] > 0 and counts["xouts_null"] > 0
    assert counts["populated"] == len(recs) == counts["games"] - sum(
        v for k, v in counts.items() if k not in ("games", "populated"))
    nb = [r["sides"][s]["nb"] for r in recs for s in ("home", "away")]
    assert any(v["sp_tto3_bf"] is None for v in nb)
    assert any(v["mg_hook_pitches_l30"] is None for v in nb)
    assert all(v["ip_per_gs"] is not None for v in nb)


# ---------------------------------------------------------------------------
# 4. the order of reads, and the stop protocol (a fast fixture grader)
# ---------------------------------------------------------------------------
def _fake_grader(log, art_path=None, noisy=False):
    def grade(fit_games, eval_games, label, mode, resolve):
        if art_path is not None and len(log) == 2:
            s2 = json.loads(Path(art_path).read_text(encoding="utf-8"))["stage2"]
            assert s2["status"] == "scoring" and "power_precondition" in s2, (
                "the power block must be on disk before the eval half is graded")
        log.append((label, {g["game_pk"] for g in fit_games},
                    {g["game_pk"] for g in eval_games}))
        ps = {}
        for g in eval_games:
            teams, sts, _parks = resolve(g)
            h, a = sts[g["home_sp"]], sts[g["away_sp"]]
            if noisy and "candidate" in label:
                ps[g["game_pk"]] = 0.95 if g["game_pk"] % 2 else 0.05
            else:
                ps[g["game_pk"]] = 1 / (1 + math.exp(-0.03 * (h["ip_per_gs"]
                                                        - a["ip_per_gs"])))
        return {"_per_game_p": ps, "coefficients": {"source": "fake"}}
    return grade


def test_the_power_block_is_written_before_any_eval_half_game(tmp_path):
    p = _art(tmp_path)
    log = []
    blk = gate.run_stage2(_small_source(), p, today=JULY1, mode="test", doc_text=DOC_TEXT,
                          mgmt=MGMT, other_looks=[], n_twin=3,
                          grade_fn=_fake_grader(log, p))
    fit = log[0][1]
    assert log[0][2] == fit and log[1][2] == fit                # power: fit window only
    assert all(not (call[2] & fit) for call in log[2:])          # then the eval half
    assert len(log) == 2 + 2 + 3
    assert blk["status"] == "complete" and blk["verdict"] in gate.VERDICTS_FINAL
    assert len(blk["twin"]["improvements"]) == 3


def test_underpowered_stops_before_the_eval_half(tmp_path):
    p = _art(tmp_path)
    log = []
    blk = gate.run_stage2(_small_source(), p, today=JULY1, mode="test", doc_text=DOC_TEXT,
                          mgmt=MGMT, other_looks=[], n_twin=3,
                          grade_fn=_fake_grader(log, noisy=True))
    assert blk["verdict"] == "UNDERPOWERED" and len(log) == 2
    assert blk["power_precondition"]["mde"] > 0.0024
    gate.check_one_run(p, DOC_TEXT, 2028)
    with pytest.raises(gate.LookRefused):
        gate.check_one_run(p, DOC_TEXT, 2027)


def test_an_exception_after_scoring_began_stops_for_good(tmp_path):
    p = _art(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("fixture crash")

    with pytest.raises(RuntimeError, match="fixture crash"):
        gate.run_stage2(_small_source(), p, today=JULY1, mode="test", doc_text=DOC_TEXT,
                        mgmt=MGMT, other_looks=[], grade_fn=boom)
    s2 = json.loads(p.read_text(encoding="utf-8"))["stage2"]
    assert s2["status"] == "stopped" and "never rerun" in s2["protocol"]
    with pytest.raises(gate.LookRefused, match="never rerun"):
        gate.check_one_run(p, DOC_TEXT, 2027)


# ---------------------------------------------------------------------------
# 5. the reporting path end to end, through the served grader
# ---------------------------------------------------------------------------
def test_the_dry_run_end_to_end_on_the_fixture_with_nulls(tmp_path):
    out, doc = tmp_path / "art.json", tmp_path / "doc.md"
    assert gate.main(["--dry-run", "--out", str(out), "--doc-out", str(doc),
                      "--twin-draws", "2"]) == 0
    art = json.loads(out.read_text(encoding="utf-8"))
    assert art["stage1"]["verdict"] == "PASS"                   # the stage-1 block is kept
    s2 = art["stage2"]
    assert s2["status"] == "complete" and s2["verdict"] in gate.VERDICTS_FINAL
    assert s2["split"]["n_fit_games"] >= 300 and s2["n_eval_paired"] >= 600
    assert s2["criteria"]["4_games"] is True
    for k in ("no_vintage", "probable_not_listed", "xouts_null"):
        assert s2["counts"][k] > 0, k
    assert s2["registered"]["vif_neighbours"] == list(NEIGHBOURS)
    assert set(s2["vif"]["by_neighbour"]) == set(NEIGHBOURS)
    assert s2["fitted"]["served"]["coefficients"]["source"] == "fitted"
    assert s2["fitted"]["candidate"]["coefficients"]["b2"] != (
        s2["fitted"]["served"]["coefficients"]["b2"])
    assert "twin draws 2" in s2["mode"] and len(s2["twin"]["improvements"]) == 2
    assert set(s2["coverage_per_club"]["eval"]) == set(gate.FIXTURE_CLUBS)
    raw = doc.read_bytes()
    assert (b"\r\n" in raw) == (b"\r\n" in GATE_DOC.read_bytes())
    text = raw.decode("utf-8")
    heads = gate.STAGE2_HEADING_RE.findall(gate.section_text(text))
    assert heads == [("2027-07-01", s2["verdict"])]
    with pytest.raises(gate.LookRefused):
        gate.check_one_run(out, text, 2027)
    with pytest.raises(gate.LookRefused):
        gate.append_result(doc, s2)


def test_the_served_arm_prices_exactly_what_the_served_grader_does():
    """The tool hands the grader only the two probables per game; the served grader on
    the night's whole starter table gives the same probabilities."""
    import betting_model as bm
    src = _small_source(n_dates=60)
    recs, _c = gate.build_records(src, 2027, NEIGHBOURS)
    fit, ev = recs[:300], recs[300:]
    mine = gate.grade_arm(gate.served_grader(), fit, ev, None, "served arm")["p"]
    full = bm._backtest_grader({}, {}, {})(
        [r["game"] for r in fit], [r["game"] for r in ev], "full", "vintage",
        lambda g: (src.day(g["date"]).teams, src.day(g["date"]).starters,
                   src.day(g["date"]).parks))["_per_game_p"]
    assert mine and set(mine) == set(full)
    assert all(mine[k] == pytest.approx(full[k], abs=1e-12) for k in mine)
