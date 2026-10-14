# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""tools/starter_workload_lab.py, the stage-1 lab of the section "Starter workload: expected
outs and pitches per start" (docs/diamond-betting.md), on fixtures only.

Nothing here reads a corpus row. The tests pin what the section registered: a start's own
outs and pitches never enter its inputs; the burn-in grids and the run constants are the
section's; the lab refuses any 2026 season or date, an early run, a look day and a second
run; the arithmetic of A0, the candidate, D1, D2 and C1 on a hand row; the 2025 corpus
parity read on a fixture (85.0 pitches per start); and the reporting path end to end on a
fixture with nulls (a probable with no prior start, an opener, no 2024 season). Every
artifact goes to tmp_path; data/ is never written.
"""
from __future__ import annotations

import ast
import copy
import datetime as dt
import importlib.util
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent
LAB_PATH = ROOT / "tools" / "starter_workload_lab.py"
GATE_DOC = ROOT / "docs" / "diamond-betting.md"
STEP_Z_TEXT = "## 9. Results\n\n### 2026-10-03: step Z, the fWAR label epoch's results\n"


def _load():
    spec = importlib.util.spec_from_file_location("starter_workload_lab", LAB_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lab = _load()


def _pre_run_doc_bytes() -> bytes:
    """docs/diamond-betting.md as it stood before the one run: the section's stage-1
    result block (the heading through the paragraphs above the rule that closes the
    section) taken out, in the file's own line endings. The doc-copy tests append a
    fixture result to this text, never to the recorded one."""
    raw = GATE_DOC.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")
    sec = lab.section_text(text)
    start = text.index(sec)
    m = re.search(r"^### Stage 1 result\b.*?(?=\n---\n)", sec, flags=re.M | re.S)
    if m is not None:
        a, b = start + m.start(), start + m.end()
        text = text[:a].rstrip("\n") + "\n\n" + text[b:].lstrip("\n")
    if crlf:
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


@pytest.fixture(scope="module")
def synth():
    return lab.synthetic_tables()


def _source(synth, **kw):
    tables, dates, weights = synth
    return lab.FixtureSource(tables, dates, weights, **kw)


@pytest.fixture(scope="module")
def dry_art(tmp_path_factory, synth):
    out = tmp_path_factory.mktemp("swl") / "starter_workload_eval.json"
    art = lab.run_stage1(_source(synth), out, mode="dry_run_fixture", parity=None,
                         log=lambda *_a: None)
    return art, out


# ---------------------------------------------------------------------------
# The registered constants
# ---------------------------------------------------------------------------
def test_the_burn_in_grids_and_run_constants_are_the_sections():
    assert lab.GRID_KB == (2, 4, 8, 16, 32)
    assert lab.GRID_KO == (15, 30, 60, 120, 240)
    assert lab.GRID_KL == (100, 300, 1000, 3000)
    assert lab.GRID_KC == lab.GRID_KB
    assert (lab.WINDOW_DAYS, lab.LINEUP_DAYS, lab.OUTS_CAP) == (365, 30, 27)
    assert lab.A0_CLIP_IP == (2.0, 7.5) and lab.A0_FALLBACK_IP == 5.2
    assert lab.OPENER_OUTS == 6.0 and lab.FLOOR_SHARE == 0.01
    assert (lab.BOOT_B, lab.BOOT_SEED, lab.LB_PERCENTILE) == (2000, 20260930, 5.0)
    assert lab.HOLM_ALPHAS == (0.025, 0.05)
    assert lab.SEASONS == (2018, 2019, 2021, 2022, 2023, 2024, 2025)
    assert lab.BURN_IN_HISTORY == (2018,) and lab.BURN_IN_SCORED == (2019,)
    assert lab.FLOOR_SEASONS == (2021, 2022, 2023) and lab.SCORED_SEASONS == (2024, 2025)
    assert lab.EARLIEST_RUN == dt.date(2026, 10, 11)
    assert lab.PARITY_2025 == {"starts": 4860, "pitches_per_start": 85.0}
    assert lab.VERDICTS == ("PASS", "FAIL", "PASS-BELOW-FLOOR")
    assert lab.ARTIFACT == ROOT / "data" / "starter_workload_eval.json"


def test_the_constants_match_the_section_text():
    sec = re.sub(r"\s+", " ", lab.section_text())
    for needle in ("k_b in {2, 4, 8, 16, 32}", "k_o in {15, 30, 60, 120, 240}",
                   "k_l in {100, 300, 1000, 3000}", "B 2000, seed 20260930",
                   "5th percentile", "2.0, 7.5", "15.6 outs", "under 6 outs per start",
                   "1 percent of A0's outs MAE", "0.025", "2026-10-11",
                   "85.0 pitches per start"):
        assert needle in sec, needle


def test_the_burn_in_reads_2019_only_and_is_frozen_before_later_seasons(synth, tmp_path):
    """The priors are chosen on the 2019 starts before any later season is read: re-drawing
    every season from 2021 on leaves the burn-in block byte-identical."""
    with pytest.raises(lab.LabRefused):
        lab.select_priors({"season": np.array([2019, 2021]), "label_outs": np.ones(2)})
    a1 = lab.run_stage1(_source(synth), tmp_path / "a.json", mode="t", parity=None,
                        log=lambda *_a: None)
    other = lab.synthetic_tables(late_seed=99)
    a2 = lab.run_stage1(_source(other), tmp_path / "b.json", mode="t", parity=None,
                        log=lambda *_a: None)
    b1, b2 = a1["stage1"]["burn_in"], a2["stage1"]["burn_in"]
    for k in ("priors", "grid", "grid_c1", "anchors", "in_sample_2019", "scored"):
        assert b1[k] == b2[k], k
    assert a1["stage1"]["floor"] != a2["stage1"]["floor"]
    assert len(b1["grid"]) == 5 * 5 * 4 and len(b1["grid_c1"]) == 5


def test_a_tie_goes_to_the_smallest_priors_in_the_order_listed():
    n = 6
    A = {"season": np.full(n, 2019), "label_outs": np.arange(n, dtype=float),
         "n": np.zeros(n), "w_pitches": np.zeros(n), "w_outs": np.zeros(n),
         "opp_pitches": np.zeros(n), "opp_pa": np.zeros(n),
         "L_pgs": np.full(n, 85.0), "L_ppo": np.full(n, 5.5), "L_ppa": np.full(n, 3.9),
         "L_opg": np.full(n, 15.5)}
    pri, grid, grid_c = lab.select_priors(A)
    assert pri == {"k_b": 2, "k_o": 15, "k_l": 100, "k_c": 2}
    assert len({t["mae_outs"] for t in grid}) == 1


def test_the_floor_is_on_disk_before_any_2024_or_2025_row_is_read(synth, tmp_path):
    out = tmp_path / "e.json"
    seen = []

    def hook(season):
        seen.append(season)
        if season >= 2024:
            st = json.loads(out.read_text(encoding="utf-8"))["stage1"]
            assert st["status"] == "floor_fixed"
            assert st["floor"]["floor"] is not None
            assert st["burn_in"]["priors"]

    lab.run_stage1(_source(synth, on_tables=hook), out, mode="t", parity=None,
                   log=lambda *_a: None)
    assert seen == [2018, 2019, 2021, 2022, 2023, 2025]


# ---------------------------------------------------------------------------
# A start's own outs and pitches never enter its inputs
# ---------------------------------------------------------------------------
INPUT_KEYS = ("n", "w_pitches", "w_outs", "opp_pitches", "opp_pa", "std_outs_all",
              "std_gs", "std_start_outs", "std_start_pitches")


def _walk_rows(games_by_season):
    w = lab.Walk()
    rows = {}
    for s in sorted(games_by_season):
        for r in w.feed(games_by_season[s], {"L_pgs": 1, "L_ppo": 1, "L_ppa": 1,
                                             "L_opg": 1}, score=True):
            rows[(r["game_pk"], r["half"])] = r
    return rows


def test_a_starts_own_pitches_and_same_day_games_never_enter_its_inputs(synth):
    src = _source(synth)
    games = {s: lab.load_season(src, s)[0] for s in (2018, 2019)}
    base = _walk_rows(games)
    # the date with the most games in 2019, after the club history has built up
    g19 = games[2019]
    day = g19[len(g19) // 2]["ord"]
    on_day = [g["game_pk"] for g in g19 if g["ord"] == day]
    assert len(on_day) >= 2
    mutated = copy.deepcopy(games)
    for g in mutated[2019]:
        if g["ord"] == day:
            for h in ("top", "bottom"):
                for line in g["lines"][h].values():
                    line["pitches"] += 40
                    line["outs"] += 5
                g["batting"][h]["pitches"] += 77
                g["batting"][h]["pa"] += 9
    after = _walk_rows(mutated)
    for pk in on_day:
        for h in ("top", "bottom"):
            a, b = base[(pk, h)], after[(pk, h)]
            assert {k: a[k] for k in INPUT_KEYS} == {k: b[k] for k in INPUT_KEYS}
            assert b["label_pitches"] == a["label_pitches"] + 40
            assert b["label_outs"] == a["label_outs"] + 5
    # a later start of the same pitcher does see the change
    later = [k for k, r in after.items() if r["date"] > g19[len(g19) // 2]["date"]
             and r["season"] == 2019]
    assert any(after[k]["w_pitches"] != base[k]["w_pitches"] for k in later)


def test_the_walk_refuses_history_out_of_date_order(synth):
    src = _source(synth)
    g19 = lab.load_season(src, 2019)[0]
    g18 = lab.load_season(src, 2018)[0]
    w = lab.Walk()
    w.feed(g19, None, score=False)
    with pytest.raises(lab.LabRefused):
        w.feed(g18, None, score=False)


# ---------------------------------------------------------------------------
# Refusals: 2026, an early date, a look day, no step Z, a second run, data/
# ---------------------------------------------------------------------------
def test_any_2026_season_or_date_is_refused(synth):
    src = _source(synth)
    for s in (2026, 2027):
        with pytest.raises(lab.LabRefused):
            lab.load_season(src, s)
    with pytest.raises(lab.LabRefused):
        src.check_seasons((2025, 2026))
    with pytest.raises(lab.LabRefused):
        lab.CorpusSource().tables(2026)
    tables, dates, weights = synth
    bad = dict(dates)
    first_2025 = int(tables[2025][0]["game_pk"].iloc[0])
    bad[first_2025] = "2026-03-27"
    with pytest.raises(lab.LabRefused):
        lab.load_season(lab.FixtureSource(tables, bad, weights), 2025)
    plays, pitches = tables[2025]
    p26 = plays.copy()
    p26.loc[p26.index[:3], "season"] = 2026
    with pytest.raises(lab.LabRefused):
        lab.games_from_tables(p26, pitches, dates, {}, 2025)


def test_the_clock_refuses_an_early_date_a_look_day_and_the_epoch_gap():
    with pytest.raises(lab.LabRefused):
        lab.check_clock(dt.date(2026, 10, 10), STEP_Z_TEXT)
    with pytest.raises(lab.LabRefused):
        lab.check_clock(dt.date(2026, 10, 8), STEP_Z_TEXT)
    for d in ("2026-10-21", "2026-10-23", "2026-11-20", "2026-12-01"):
        with pytest.raises(lab.LabRefused):
            lab.check_clock(dt.date.fromisoformat(d), STEP_Z_TEXT)
    with pytest.raises(lab.LabRefused):
        lab.check_clock(dt.date(2026, 10, 12), "## 9. Results\n\nnothing yet\n")
    got = lab.check_clock(dt.date(2026, 10, 11), STEP_Z_TEXT)
    assert got == {"today": "2026-10-11", "earliest_run": "2026-10-11",
                   "step_z_entry": "2026-10-03"}


def test_the_repo_epoch_gate_carries_its_step_z_entry():
    assert lab.step_z_entry() is not None


def test_a_second_run_is_refused_by_the_artifact_or_the_section(tmp_path, dry_art):
    art, out = dry_art
    doc = _pre_run_doc_bytes().decode("utf-8")
    lab.check_one_run(tmp_path / "absent.json", doc)          # the pre-run state passes
    with pytest.raises(lab.LabRefused, match="stage-1 block"):
        lab.check_one_run(out, doc)
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({"stage1": {"status": "burn_in_frozen"}}), encoding="utf-8")
    with pytest.raises(lab.LabRefused):
        lab.check_one_run(partial, doc)
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(lab.LabRefused):
        lab.check_one_run(broken, doc)
    # the section's result heading alone also refuses
    copy_doc = tmp_path / "diamond-betting.md"
    copy_doc.write_bytes(_pre_run_doc_bytes())
    lab.append_result(copy_doc, art)
    text = copy_doc.read_text(encoding="utf-8")
    with pytest.raises(lab.LabRefused, match="Stage 1 result"):
        lab.check_one_run(tmp_path / "absent.json", text)
    with pytest.raises(lab.LabRefused):
        lab.append_result(copy_doc, art)


def test_the_result_heading_lands_inside_the_section_with_the_files_endings(tmp_path,
                                                                           dry_art):
    art, _out = dry_art
    copy_doc = tmp_path / "diamond-betting.md"
    raw = _pre_run_doc_bytes()
    copy_doc.write_bytes(raw)
    lab.append_result(copy_doc, art)
    new = copy_doc.read_bytes()
    assert (b"\r\n" in raw) == (b"\r\n" in new)
    if b"\r\n" in raw:
        assert new.count(b"\n") == new.count(b"\r\n")
    sec = lab.section_text(new.decode("utf-8"))
    head = lab.result_heading(art)
    assert re.fullmatch(r"### Stage 1 result \(run \d{4}-\d\d-\d\d, once\): FAIL", head)
    assert head in sec
    assert "No number has been computed on this candidate." in sec
    old_len = len(raw.decode("utf-8").replace("\r\n", "\n"))
    assert len(new.decode("utf-8").replace("\r\n", "\n")) > old_len
    assert "\n## 6. The backtest" in new.decode("utf-8").replace("\r\n", "\n")


def test_the_pre_run_doc_carries_no_stage_1_heading():
    sec = lab.section_text(_pre_run_doc_bytes().decode("utf-8"))
    assert not lab.STAGE1_HEADING_RE.search(sec)
    assert "No number has been computed on this candidate." in sec


def test_the_recorded_run_refuses_a_second_and_agrees_with_its_section_and_row():
    """Once the one run is recorded, the repo itself refuses another, and the artifact,
    the section's heading and the registry row say the same thing."""
    if not lab.ARTIFACT.exists():
        pytest.skip("stage 1 has not run")
    art = json.loads(lab.ARTIFACT.read_text(encoding="utf-8"))
    st = art["stage1"]
    assert st["status"] == "complete" and st["verdict"] in lab.VERDICTS
    with pytest.raises(lab.LabRefused):
        lab.check_one_run(lab.ARTIFACT)
    sec = lab.section_text()
    heads = lab.STAGE1_HEADING_RE.findall(sec)
    assert len(heads) == 1
    assert lab.result_heading(art) in sec
    assert lab.result_text(art) in sec.replace("\r\n", "\n")
    assert st["parity_2025"]["ok"] is True
    assert set(st["corpus_seasons"]) == {str(s) for s in lab.SEASONS}
    import model_registry as mr
    row = {m["model_id"]: m for m in mr.load()["models"]}[lab.REGISTRY_ROW]
    assert row["eval_artifact"] == "data/starter_workload_eval.json"
    assert row["verdict"] == ("provisional" if st["verdict"] == "PASS" else "deprecated")


def test_a_dry_run_never_writes_under_data(tmp_path):
    with pytest.raises(lab.LabRefused):
        lab.check_out_path(ROOT / "data" / "starter_workload_eval.json")
    with pytest.raises(lab.LabRefused):
        lab.check_out_path(ROOT / "data" / "sub" / "x.json")
    assert lab.check_out_path(tmp_path / "x.json") == (tmp_path / "x.json").resolve()
    assert lab.main(["--dry-run", "--out", str(ROOT / "data" / "x.json")]) == 2
    assert not (ROOT / "data" / "x.json").exists()


def test_a_refusal_inside_the_run_is_recorded_and_blocks_a_rerun(synth, tmp_path):
    tables, dates, weights = synth
    bad = dict(dates)
    bad[int(tables[2022][0]["game_pk"].iloc[0])] = "2026-04-01"
    out = tmp_path / "r.json"
    with pytest.raises(lab.LabRefused):
        lab.run_stage1(lab.FixtureSource(tables, bad, weights), out, mode="t",
                       parity=None, log=lambda *_a: None)
    st = json.loads(out.read_text(encoding="utf-8"))["stage1"]
    assert st["status"] == "refused" and "2026" in st["refusal"]
    with pytest.raises(lab.LabRefused):
        lab.check_one_run(out, GATE_DOC.read_text(encoding="utf-8"))


def test_a_crash_after_the_first_write_is_recorded(synth, tmp_path, monkeypatch):
    out = tmp_path / "c.json"

    def boom(_A):
        raise ZeroDivisionError("fixture crash")

    monkeypatch.setattr(lab, "select_priors", boom)
    with pytest.raises(ZeroDivisionError):
        lab.run_stage1(_source(synth), out, mode="t", parity=None, log=lambda *_a: None)
    st = json.loads(out.read_text(encoding="utf-8"))["stage1"]
    assert st["status"] == "crashed" and "fixture crash" in st["crash"]["error"]
    assert "never rerun" in st["protocol"]


# ---------------------------------------------------------------------------
# Fixture arithmetic: A0, D1, the candidate, D2, C1, the pitches comparator
# ---------------------------------------------------------------------------
def test_a0_and_d1_arithmetic():
    # 70 outs over all appearances, 4 starts: 70 / 3 / 4 = 5.8333 IP, 17.5 outs
    assert lab.a0_outs([70], [4])[0] == pytest.approx(17.5)
    assert lab.a0_outs([100], [4])[0] == pytest.approx(22.5)      # 8.33 IP clips to 7.5
    assert lab.a0_outs([12], [4])[0] == pytest.approx(6.0)        # 1.0 IP clips to 2.0
    assert lab.a0_outs([9], [0])[0] == pytest.approx(15.6)        # no start: 5.2 x 3
    assert lab.d1_outs([60], [4])[0] == pytest.approx(15.0)       # starts only: 5.0 IP
    assert lab.season_mean_pitches([340], [4], [81.0])[0] == pytest.approx(85.0)
    assert lab.season_mean_pitches([0], [0], [81.0])[0] == pytest.approx(81.0)


def test_the_candidate_d2_and_c1_arithmetic():
    # n 4 starts, 360 pitches, 60 outs; the opposing club 2,100 pitches over 500 PA;
    # L_pgs 85, L_ppo 5.5, L_ppa 3.9, L_opg 15.5; k_b 4, k_o 30, k_l 300, k_c 4
    b = lab.budget([360], [4], [85.0], 4)[0]
    assert b == pytest.approx(87.5)                    # (360 + 340) / 8
    p = lab.ppo([360], [60], [5.5], 30)[0]
    assert p == pytest.approx(525 / 90)                # (360 + 165) / 90 = 5.8333
    r = lab.lineup_ratio([2100], [500], [3.9], 300)[0]
    assert r == pytest.approx(4.0875 / 3.9)            # (2100 + 1170) / 800 / 3.9
    assert lab.xouts(b, p, r) == pytest.approx(14.3119, abs=1e-4)
    assert lab.xouts(b, p, 1.0) == pytest.approx(15.0)  # D2
    assert lab.c1_outs([60], [4], [15.5], 4)[0] == pytest.approx(15.25)  # (60 + 62) / 8
    assert lab.xouts([400.0], [5.0], [1.0]) == pytest.approx(27.0)       # the cap
    # a probable with no prior start and an idle opposing club: the anchors alone
    assert lab.xouts(lab.budget([0], [0], [85.0], 4), lab.ppo([0], [0], [5.5], 30),
                     lab.lineup_ratio([0], [0], [3.9], 300))[0] == pytest.approx(85 / 5.5)
    A = {"w_pitches": np.array([360.0]), "n": np.array([4.0]), "w_outs": np.array([60.0]),
         "opp_pitches": np.array([2100.0]), "opp_pa": np.array([500.0]),
         "std_outs_all": np.array([70.0]), "std_gs": np.array([4.0]),
         "std_start_outs": np.array([60.0]), "std_start_pitches": np.array([340.0]),
         "L_pgs": np.array([85.0]), "L_ppo": np.array([5.5]), "L_ppa": np.array([3.9]),
         "L_opg": np.array([15.5])}
    P = lab.predictions(A, {"k_b": 4, "k_o": 30, "k_l": 300, "k_c": 4})
    assert P["a0"][0] == pytest.approx(17.5) and P["d1"][0] == pytest.approx(15.0)
    assert P["candidate"][0] == pytest.approx(14.3119, abs=1e-4)
    assert P["d2"][0] == pytest.approx(15.0) and P["c1"][0] == pytest.approx(15.25)
    assert P["budget"][0] == pytest.approx(87.5)
    assert P["season_mean"][0] == pytest.approx(85.0)


def test_the_bootstrap_p_value_holm_and_the_verdict_rules():
    assert lab.one_sided_p(np.array([0.1, -0.2, 0.0, 0.3])) == pytest.approx(3 / 5)
    assert lab.one_sided_p(None) is None
    assert lab.holm_two(0.01, 0.04) == {"T1": True, "T2": True}
    assert lab.holm_two(0.03, 0.04) == {"T1": False, "T2": False}
    assert lab.holm_two(0.06, 0.02) == {"T1": False, "T2": True}
    assert lab.holm_two(None, 0.001) == {"T1": False, "T2": False}
    d = lab.decide(0.01, 0.1, 0.2, 0.15, 0.05, 15.0, 16.0)
    assert d["verdict"] == "PASS"
    assert lab.decide(0.01, 0.1, 0.2, 0.04, 0.05, 15.0, 16.0)["verdict"] == "PASS-BELOW-FLOOR"
    assert lab.decide(-0.01, 0.1, 0.2, 0.15, 0.05, 15.0, 16.0)["verdict"] == "FAIL"
    assert lab.decide(0.01, None, 0.2, 0.15, 0.05, 15.0, 16.0)["verdict"] == "FAIL"
    assert lab.decide(0.01, 0.1, -0.2, 0.15, 0.05, 15.0, 16.0)["verdict"] == "FAIL"
    assert lab.decide(0.01, 0.1, 0.2, 0.15, 0.05, 16.5, 16.0)["verdict"] == "FAIL"
    w = lab.wording(False, False)
    assert w["credit"] == "starts-only length over a 365-day window"
    assert w["lineup"] == "nothing credits the opposing lineup's P/PA"
    assert lab.wording(True, True)["credit"] == "pitch rates"


def test_the_bootstrap_resamples_games_with_the_same_draws_for_every_contrast():
    pk = np.array([1, 1, 2, 2, 3, 3])
    err = {"candidate": np.array([1.0, 1.0, 2.0, 2.0, 3.0, 3.0])}
    err["a0"] = err["candidate"] + 1.0
    err["d2"] = err["candidate"] + 1.0
    err["c1"] = err["candidate"] - 0.5
    b = lab.clustered_bootstrap(pk, err, B=50, seed=lab.BOOT_SEED)
    assert b["games"] == 3
    assert np.allclose(b["reps"]["a0"], 1.0) and np.allclose(b["reps"]["d2"], 1.0)
    assert np.allclose(b["reps"]["c1"], -0.5)
    b2 = lab.clustered_bootstrap(pk, err, B=50, seed=lab.BOOT_SEED)
    assert all(np.array_equal(b["reps"][k], b2["reps"][k]) for k in b["reps"])
    assert lab.clustered_bootstrap(np.array([]), {})["reps"] is None


# ---------------------------------------------------------------------------
# Corpus parity on a 2025 fixture: 85.0 pitches per start
# ---------------------------------------------------------------------------
def _parity_tables(n_games=10):
    plays, pitches, dates, weights = [], [], {}, []
    for c, club in enumerate(("BOS", "NYY")):
        for j in range(9):
            weights.append({"mlb_ID": float(10 + 100 * c + j), "year_ID": 2025,
                            "team_ID": club, "PA": 400})
    for g in range(n_games):
        pk = 800000 + g
        dates[pk] = (dt.date(2025, 4, 1) + dt.timedelta(days=g)).isoformat()
        abi = 0
        for half, bat_c, sp, rp, per_pa in (("top", 1, 501, 601, 16 + (g % 2) * 2),
                                            ("bottom", 0, 502, 602, 18 - (g % 2) * 2)):
            # five starter PAs (per_pa pitches each: 80 or 90 per start, 85.0 mean),
            # then one reliever PA of 4 pitches
            for i, pid in enumerate([sp] * 5 + [rp]):
                n_p = per_pa if pid == sp else 4
                plays.append({"game_pk": pk, "season": 2025, "half": half,
                              "at_bat_index": abi, "batter_id": 10 + 100 * bat_c + i,
                              "pitcher_id": pid, "event_type": "field_out",
                              "outs_before": i % 3, "outs_after": i % 3 + 1})
                pitches += [{"game_pk": pk, "season": 2025, "at_bat_index": abi,
                             "is_pitch": True}] * n_p
                pitches.append({"game_pk": pk, "season": 2025, "at_bat_index": abi,
                                "is_pitch": False})       # a non-pitch event row
                abi += 1
            # a play with no event type and no pitch: no plate appearance, no out
            plays.append({"game_pk": pk, "season": 2025, "half": half, "at_bat_index": abi,
                          "batter_id": 10 + 100 * bat_c, "pitcher_id": rp,
                          "event_type": None, "outs_before": 0, "outs_after": 0})
            abi += 1
    return {2025: (pd.DataFrame(plays), pd.DataFrame(pitches))}, dates, pd.DataFrame(weights)


def test_corpus_parity_on_a_2025_fixture_reads_85_pitches_per_start():
    tables, dates, weights = _parity_tables()
    games, counts = lab.load_season(lab.FixtureSource(tables, dates, weights), 2025)
    assert counts["games"] == 10 and counts["clubs"]["resolved"] == 10
    read = lab.parity_read(games)
    assert read["starts"] == 20 and read["pitches_per_start"] == 85.0
    assert lab.check_parity(read, {"starts": 20, "pitches_per_start": 85.0})
    assert not lab.check_parity(read, lab.PARITY_2025)
    g = games[0]
    assert g["home"] == "BOS" and g["away"] == "NYY"
    assert g["starters"] == {"top": 501, "bottom": 502}
    assert g["lines"]["top"][501] == {"outs": 5, "pitches": 80}
    assert g["lines"]["top"][601] == {"outs": 1, "pitches": 4}
    assert g["batting"]["top"] == {"pitches": 84, "pa": 6}


def test_a_failed_parity_stops_before_any_scored_start(synth, tmp_path):
    out = tmp_path / "p.json"
    with pytest.raises(lab.LabRefused, match="parity"):
        lab.run_stage1(_source(synth), out, mode="t", parity=lab.PARITY_2025,
                       log=lambda *_a: None)
    st = json.loads(out.read_text(encoding="utf-8"))["stage1"]
    assert st["status"] == "stopped_parity" and st["parity_2025"]["ok"] is False
    assert "results" not in st and "verdict" not in st


# ---------------------------------------------------------------------------
# The reporting path end to end on the fixture with nulls
# ---------------------------------------------------------------------------
def test_the_reporting_path_runs_end_to_end_with_nulls(dry_art):
    art, out = dry_art
    on_disk = json.loads(out.read_text(encoding="utf-8"),
                         parse_constant=lambda c: pytest.fail(f"non-finite {c}"))
    assert on_disk == json.loads(json.dumps(art))
    st = art["stage1"]
    assert st["status"] == "complete" and st["verdict"] in lab.VERDICTS
    res = st["results"]
    # no 2024 season: its figures are null and criterion 2 is not met
    assert res["by_season"]["2024"] is None
    assert st["criteria"]["improvement_2024"] is None
    assert st["criteria"]["2_positive_in_2024_and_2025"] is False
    assert st["verdict"] == "FAIL"
    assert res["counts"]["per_season"]["2024"] == {"absent": True}
    # a probable with no prior start, and an opener
    assert res["counts"]["starts_n0_by_season"]["2025"] > 0
    assert res["openers_pooled_2024_2025"]["n"] > 0
    assert res["counts"]["starts_2021_window_reaches_absent_2020"] > 0
    for arm in lab.ARMS_OUTS:
        blk = res["pooled_2024_2025"]["outs"][arm]
        assert set(blk) == {"n", "mae", "rmse", "bias"}
    assert set(res["pooled_2024_2025"]["pitches"]) == set(lab.ARMS_PITCHES)
    assert st["floor"]["floor"] == pytest.approx(0.01 * st["floor"]["a0_outs_mae"], abs=1e-6)
    at = st["attribution"]
    assert 0 < at["T1_p"] <= 1 and 0 < at["T2_p"] <= 1
    assert at["wording"] == lab.wording(at["holm"]["T1"], at["holm"]["T2"])
    assert st["criteria"]["bootstrap"] == {"games": 48, "B": 2000, "seed": 20260930}
    text = lab.result_text(art)
    assert "none (no scored start)" in text
    assert chr(0x2014) not in text and chr(0x2013) not in text


def test_the_dry_run_cli_writes_its_own_path(tmp_path, capsys):
    out = tmp_path / "dry.json"
    assert lab.main(["--dry-run", "--out", str(out), "--tee",
                     str(tmp_path / "tee.log")]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["mode"] == "dry_run_fixture"
    assert "Stage 1 result" in (tmp_path / "tee.log").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# What the lab never reads, and the registry row
# ---------------------------------------------------------------------------
def test_the_lab_names_no_dark_column_and_imports_no_management_or_betting_module():
    src = LAB_PATH.read_text(encoding="utf-8")
    for needle in ("sp_tto3_bf", "sp_rest_days", "sp_n365", "sp_budget", "sp_ppo",
                   "sp_xouts", "bat_ppa_l30", "betting_model_eval", "game_feeds",
                   "leaderboard_vintages", "odds/", "odds_", "SERVE_"):
        assert needle not in src, needle
    assert not re.search(r"(?<![A-Za-z])mg_", src)
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert not {m for m in mods if m.startswith(("mgmt", "management", "betting"))}, mods
    assert {m for m in mods if not m.startswith("_")} <= {
        "argparse", "datetime", "json", "math", "os", "re", "sys", "traceback",
        "collections", "pathlib", "numpy", "pandas", "pyarrow", "trades", "mlbstats_games",
        "__future__"}, mods
    assert chr(0x2014) not in src and chr(0x2013) not in src


def test_the_registry_row_lands_unvalidated_with_no_artifact():
    import model_registry as mr
    rows = {m["model_id"]: m for m in mr.load()["models"]}
    row = rows[lab.REGISTRY_ROW]
    if not lab.ARTIFACT.exists():
        assert row["verdict"] == "unvalidated"
        assert row["eval_artifact"] is None
    assert lab.SECTION_TITLE in row["notes"]
    assert "tools/starter_workload_lab.py" in row["notes"]
