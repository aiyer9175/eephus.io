# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/dpw_path_gate.py, the $/WAR path gate's lab, on SYNTHETIC series only
(docs/dpw-2026-09-25/DPW_PATH_GATE.md; DESIGN_v2 section 9).

Never run here: --real, --prelook or --owner-after-look on real data. The
--prelook and --real paths are exercised on synthetic documents, tmp paths and
scratch git repositories.
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pytest

import dpw_path as dp
import dpw_testkit as kit
from tools import dpw_path_gate as lab

ROOT = Path(__file__).resolve().parent
DOC = (ROOT / "docs" / "dpw-2026-09-25" / "DPW_PATH_GATE.md").read_text(encoding="utf-8")


def _series(step=0.0, at=2017, g=0.05, wig=0.0, pattern=None):
    t, v = {}, 9.0e6
    for i, w in enumerate(range(2015, 2027)):
        if w > 2015:
            gg = pattern[i - 1] if pattern else g
            v *= (1 + gg) * ((1 + step) if w == at else 1.0) * (1 + wig * ((-1) ** w))
        t[w] = v
    return t


PASS_SERIES = _series(step=0.5, at=2017, g=0.05)          # one early level step: the challenger's case
WORSE_SERIES = _series(pattern=[0, 0, 0.15, 0, 0, 0.15, 0, 0, 0.15, 0, 0])
NOISY_SERIES = _series(step=0.3, at=2021, g=0.03, wig=0.01)


# ---------------------------------------------------------------- constants and text

def test_the_registered_constants():
    assert lab.SEED == 20260925 and dp.BAND_SEED == 20260925
    assert (lab.B_BOOT, lab.B_PLANT_BOOT, lab.N_DRAWS) == (2000, 500, 1000)
    assert lab.M == 0.025 and lab.C_DEFAULT == 1.894579 and lab.RHOS == (0.0, 0.8)
    assert lab.SIGMA_FLOOR == 0.01 and lab.MAX_HALVINGS == 6 and lab.BISECT_STEPS == 30
    assert lab.TOL_FRAC == 0.05 and lab.KAPPA_BRACKET == (0.0, 1.0) and lab.KAPPA_BRACKET_NEG == (-3.0, 0.0)
    assert (lab.GSTAR_LO, lab.GSTAR_HI, lab.GSTAR_STEP, lab.GSTAR_TOL) == (-0.20, 0.30, 0.0005, 1e-10)
    assert lab.W_BASE == 1.113763 and lab.ORIGINS == tuple(range(2018, 2026))
    assert lab.JACK_WINTERS == tuple(range(2015, 2027)) and lab.REGIME_TARGETS == {2021, 2022}
    assert lab.S1 == {2018, 2019, 2020} and lab.S2 == {2021, 2022, 2023, 2024, 2025}
    assert [round(x, 4) for x in lab.weights_for([1, 2, 3, 4, 5])] == [0.2452, 0.2202, 0.1977, 0.1775, 0.1594]
    assert lab.SIZE_STATUSES == ("FULL", "PARTIAL", "UNAVAILABLE")
    assert lab.DETECTION_BAR == 0.80 and lab.MIN_UNTIED == 6 and lab.P_BAR == 0.05


def test_each_criterion_prints_byte_identical_to_the_doc():
    for k, text in lab.CRITERIA.items():
        assert text in DOC, k
    assert sorted(lab.CRITERIA) == [f"P{i}" for i in range(1, 9)]
    norm = " ".join(DOC.split())
    assert " ".join(lab.UNCONDITIONAL_SENTENCE.split()) in norm


def test_the_frame_has_30_pairs_and_the_jackknife_deletes_everywhere():
    fr = lab.build_frame(PASS_SERIES)
    assert [r["origin"] for r in fr["origins"]] == list(range(2018, 2026))
    assert sum(len(r["h_list"]) for r in fr["origins"]) == 30
    assert [len(r["h_list"]) for r in fr["origins"]] == [5, 5, 5, 5, 4, 3, 2, 1]
    rep = lab.build_frame(PASS_SERIES, delete=2019)
    assert 2019 not in rep["series"] and 2019 not in [r["origin"] for r in rep["origins"]]
    r2018 = rep["origins"][0]
    assert r2018["origin"] == 2018 and r2018["h_list"] == [2, 3, 4, 5]     # h keeps its value
    assert r2018["w"].sum() == pytest.approx(1.0)
    assert r2018["w"][0] == pytest.approx(lab.W_BASE ** -2 / sum(lab.W_BASE ** -h for h in (2, 3, 4, 5)))
    # the gap rule: the replicate's growth uses the annualized 2018/2020 difference
    assert dp.differences(rep["series"], 2020)[-1] == pytest.approx(
        math.log(PASS_SERIES[2020] / PASS_SERIES[2018]) / 2)
    early = lab.build_frame(PASS_SERIES, delete=2015)
    assert len(dp.available(early["series"], 2018)) == 3                # fewer than 4 winters:
    assert early["origins"][0]["origin"] == 2019                         # origin 2018 drops


def test_non_regime_pairs_drop_2021_and_2022_targets():
    fr = lab.build_frame(PASS_SERIES)
    r = fr["origins"][2]                                                   # origin 2020
    assert r["origin"] == 2020
    assert [r["h_list"][i] for i in r["nr_idx"]] == [3, 4, 5]
    assert r["nr_w"].sum() == pytest.approx(1.0)


def test_ties_and_the_sign_flip_floor():
    D = np.array([[-0.01, -0.02, 0.0, 0.0, -0.03, -0.01, -0.02, -0.005]])
    p = lab.sign_flip_p(D, D.mean(1))
    assert p[0] == pytest.approx(4 / 256)                                  # 2^k / 256 with k = 2 ties


def test_g_star_minimises_the_loss_on_its_grid_and_tolerance():
    fr = lab.build_frame(NOISY_SERIES)
    for rec in fr["origins"]:
        g = lab.g_star(rec)
        S = lambda x: float((rec["w"] * ((1 + x) ** rec["hs"] - rec["r"]) ** 2).sum())  # noqa: E731
        assert -0.20 <= g <= 0.30
        assert S(g) <= S(g + 1e-4) + 1e-15 and S(g) <= S(g - 1e-4) + 1e-15


# ---------------------------------------------------------------- the plant search

def _f(fn, tol=1e-9):
    return lambda k, s: (fn(k, s), tol)


def test_plant_search_brackets_in_zero_one():
    res = lab.plant_search(_f(lambda k, s: (0.5 - k) * 1e-3), 0.02)
    assert res["status"] == "FOUND" and res["how"] == "[0, 1]" and res["halvings"] == 0
    assert abs(res["kappa"] - 0.5) < 1e-6


def test_plant_search_one_sided_clip_case_in_minus_three_zero():
    res = lab.plant_search(_f(lambda k, s: -0.001 - 0.001 * k), 0.02)
    assert res["status"] == "FOUND" and res["how"] == "[-3, 0]"
    assert abs(res["kappa"] + 1.0) < 1e-6


def test_plant_search_halves_sigma_when_noise_dominates():
    res = lab.plant_search(_f(lambda k, s: 100 * s * s - 0.008 * k), 0.02)
    assert res["status"] == "FOUND" and res["halvings"] == 2 and res["how"] == "[0, 1]"
    assert res["sigma"] == pytest.approx(0.005)
    sig = [st["sigma"] for st in res["steps"]]
    assert sig[:2] == [0.02, 0.02] and 0.01 in sig


def test_plant_search_root_moves_into_minus_three_zero_under_halving():
    res = lab.plant_search(_f(lambda k, s: 400 * s * s - 5 * s - 0.005 * k), 0.02)
    assert res["status"] == "FOUND" and res["how"] == "[-3, 0]" and res["halvings"] == 1
    assert res["kappa"] == pytest.approx(-2.0, abs=1e-6)


def test_plant_search_unavailable_after_six_halvings():
    res = lab.plant_search(_f(lambda k, s: 1.0), 0.02)
    assert res["status"] == "UNAVAILABLE" and res["halvings"] == 6
    assert min(st["sigma"] for st in res["steps"]) == pytest.approx(0.02 / 64)
    assert min(st["sigma"] for st in res["steps"]) < lab.SIGMA_FLOOR       # may go below the floor


def test_plant_search_unavailable_when_bisection_ends_above_tol():
    res = lab.plant_search(_f(lambda k, s: 1.0 if k < 0.5 else -1.0), 0.02)
    assert res["status"] == "UNAVAILABLE"
    assert sum(1 for st in res["steps"] if st["note"].startswith("bisect")) == lab.BISECT_STEPS


@pytest.fixture(scope="module")
def small():
    ctx = lab.build_context(NOISY_SERIES)
    lab.attach_g_star(ctx)
    streams = lab.draw_streams(len(ctx["full"]["origins"]), n_draws=40, b_plant=40)
    return ctx, streams


def test_size_status_full_partial_unavailable(small):
    ctx, streams = small
    sg = lab.sigma_g(ctx)

    def fake(statuses):
        it = iter(statuses)

        def search(f, s0):
            st = next(it)
            return ({"status": "FOUND", "kappa": 1.0, "sigma": s0, "halvings": 0, "how": "[0, 1]",
                     "steps": []} if st else {"status": "UNAVAILABLE", "steps": [], "halvings": 6})
        return search
    full = lab.size_run(ctx, streams, sg, search=fake([True, True]))
    assert full["size_status"] == "FULL" and full["unavailable_rho"] == []
    part = lab.size_run(ctx, streams, sg, search=fake([True, False]))
    assert part["size_status"] == "PARTIAL" and part["unavailable_rho"] == [0.8]
    r0 = part["by_rho"]["0.0"]
    want = max(lab.C_DEFAULT, r0["q95_neg_dbar_over_se"]) if r0["size_full"] > 0.05 else lab.C_DEFAULT
    assert part["c"] == pytest.approx(want)
    none = lab.size_run(ctx, streams, sg, search=fake([False, False]))
    assert none["size_status"] == "UNAVAILABLE" and none["c"] == lab.C_DEFAULT


def test_common_random_numbers_by_draw():
    a = lab.draw_streams(8, n_draws=5, b_plant=7)
    b = lab.draw_streams(8, n_draws=3, b_plant=7)
    assert np.array_equal(a["E"][:3], b["E"]) and np.array_equal(a["idx"][:3], b["idx"])
    z0 = lab.persistent_z(a["E"], 0.0)
    assert np.array_equal(z0, a["E"])
    z8 = lab.persistent_z(a["E"], 0.8)
    assert z8[0, 1] == pytest.approx(0.8 * a["E"][0, 0] + 0.6 * a["E"][0, 1])


def test_no_passing_draw_leaves_type_m_null(small):
    ctx, streams = small
    det = lab.detection_run(ctx, streams, lab.sigma_g(ctx), 1e9)
    for rec in det.values():
        assert rec["detection_full"] == 0.0
        assert rec["type_m"] is None and rec["detectable_gain_q"] is None
        assert rec["null_reason"] == lab.NO_PASSING_DRAW
    du = lab.delta_usd(ctx, {h: 1e9 for h in range(1, 6)}, type_m=None)
    assert du["DeltaUSD_over_type_m"] is None and du["DeltaUSD_over_type_m_reason"] == lab.NO_PASSING_DRAW


# ---------------------------------------------------------------- order and verdicts

def test_the_size_run_then_the_flag_then_power_then_the_cells(monkeypatch):
    log = []
    real_growth = lab.growth_of

    def spy(frame, key):
        log.append(("growth", key))
        return real_growth(frame, key)
    monkeypatch.setattr(lab, "growth_of", spy)
    res = lab.run_look(NOISY_SERIES, n_draws=30, b_plant=30, log=log)
    steps = [x for x in log if isinstance(x, str)]
    assert steps == ["size_run", "incumbent_vs_floor", "detection_run", "p2_attainability", "cells",
                     "descriptive"]
    first_a = next(i for i, x in enumerate(log) if x == ("growth", "A"))
    assert first_a > log.index("cells")                                   # no error of A before the cells
    assert res["verdict"] in dp.VERDICTS


def test_the_flag_is_computed_once_with_the_c_the_size_run_left(monkeypatch):
    ctx = lab.build_context(NOISY_SERIES)
    raised = {"by_rho": {}, "size_status": "FULL", "c": 7.5, "unavailable_rho": []}
    monkeypatch.setattr(lab, "size_run", lambda *a, **k: raised)
    p = lab.power_block(ctx, n_draws=20, b_plant=20)
    assert p["c"] == 7.5
    ivf = p["incumbent_vs_floor"]
    assert p["INCUMBENT_BELOW_FLOOR"] == (ivf["Dbar"] - 7.5 * ivf["SE_star"] > 0)
    assert p["MDE95"] == pytest.approx(7.5 * p["detection"]["0.8"]["median_SE"])


def _cell(pass_=False, dbar=-0.001, se=0.002, ties=0, n=8):
    return {"pass": pass_, "Dbar": dbar, "SE": se, "ties": ties, "origins": list(range(2018, 2018 + n)),
            "D": [dbar] * n}


def _power(det=(0.9, 0.85), p2=False, c=1.894579):
    return {"c": c, "P2_UNATTAINABLE": p2, "size_run": {"size_status": "FULL", "unavailable_rho": []},
            "detection": {"0.0": {"detection_full": det[0]}, "0.8": {"detection_full": det[1]}},
            "INCUMBENT_BELOW_FLOOR": False, "incumbent_vs_floor": {"Dbar": 0.0, "SE_star": 1.0}}


def test_verdicts_on_planted_cells():
    assert lab.decide(_cell(pass_=True), _power())["verdict"] == "PASS_DEV"
    assert lab.decide(_cell(dbar=0.02, se=0.005), _power())["verdict"] == "WORSE"
    assert lab.decide(_cell(), _power())["verdict"] == "NULL"
    low = lab.decide(_cell(), _power(det=(0.9, 0.4)))
    assert low["verdict"] == "NULL_UNDERPOWERED" and low["detection_full_min"] == 0.4
    un = lab.decide(_cell(), _power(p2=True))
    assert un["verdict"] == "NULL_UNDERPOWERED" and un["reason"] == lab.PASS_UNATTAINABLE
    assert lab.P2_UNATTAINABLE in un["detail"]
    ties = lab.decide(_cell(ties=3), _power())
    assert ties["reason"] == lab.PASS_UNATTAINABLE and "fewer than 6 untied origins" in ties["detail"]
    assert "smallest attainable sign-flip p above 0.05" in lab.decide(_cell(ties=5), _power())["detail"]
    # a tie goes to the incumbent
    assert lab.decide(_cell(dbar=0.0, se=0.0), _power())["verdict"] in ("NULL", "NULL_UNDERPOWERED")


def test_end_to_end_pass_dev_and_worse_on_synthetic_series():
    p = lab.run_look(PASS_SERIES, n_draws=60, b_plant=60)
    assert p["verdict"] == "PASS_DEV" and p["blind_status"] == "PENDING"
    assert all(v["pass"] for v in p["cells"]["criteria"].values())
    assert all(v["text"] == lab.CRITERIA[k] for k, v in p["cells"]["criteria"].items())
    assert p["descriptive"]["T"][0]["label"] == "SPENT" and p["descriptive"]["B"][0]["label"] == "DESCRIPTIVE"
    assert set(p["flags"]) == {"INCUMBENT_BELOW_FLOOR", "BAND_COVERAGE"}
    w = lab.run_look(WORSE_SERIES, n_draws=60, b_plant=60)
    assert w["verdict"] == "WORSE" and w["blind_status"] == "NOT_ARMED"


def test_p2_attainability_reads_the_oracle_inside_the_look_only():
    ctx = lab.build_context(PASS_SERIES)
    p = lab.power_block(ctx, n_draws=20, b_plant=20)
    assert p["P2_UNATTAINABLE"] == (p["Q_I"] - p["Q_g_star"] < lab.M / 2)
    assert p["Q_g_star"] <= p["Q_I"] + 1e-12


# ---------------------------------------------------------------- DeltaUSD (8a)

def _payloads(dd: Path):
    dd.mkdir(parents=True, exist_ok=True)
    (dd / "mlb_projections.json").write_text(json.dumps({
        "first_season": 2027,
        "vets": [{"key": "both", "war": [3.0, 2.8, 2.5, 2.2, 2.0], "warTail": [1.8, 1.5, 1.2, 1.0]},
                 {"key": "vet2", "war": [1.0, 1.0, 1.0, 1.0, 1.0]}],
        "prospects": [{"key": "pro1", "war": [0.0, 0.5, 1.5, 2.0, 2.5]}]}), encoding="utf-8")
    (dd / "fa_class.json").write_text(json.dumps({
        "class_year": 2027, "members": [{"key": "both", "warPath": [9.0, 9.0]},
                                        {"key": "fa1", "warPath": [2.0, 1.8, 1.6]}]}), encoding="utf-8")


def test_delta_usd_exposure_dedupe_pv_and_the_copy(tmp_path, monkeypatch):
    import value_framework as vf
    dd = tmp_path / "data"
    _payloads(dd)
    copy = kit.write_series(tmp_path / "amendment_copy.json", kit.synthetic_block())
    import functools
    read = []
    real_at = vf._dpw_file_at.__wrapped__

    @functools.lru_cache(maxsize=4)
    def spy(path):
        read.append(path)
        return real_at(path)
    monkeypatch.setattr(vf, "_DPW_SERIES_PATH", tmp_path / "live_never_read.json")
    monkeypatch.setattr(vf, "_dpw_file_at", spy)
    X = lab.exposure_by_horizon(dd, copy)
    assert set(read) == {str(copy)}
    assert X["players_counted"] == 4                                       # "both" counted once
    assert X["series_copy_sha256"] == lab._sha_file(copy)
    assert set(X["payload_sha256"]) == {"mlb_projections.json", "fa_class.json"}
    with vf.dpw_path_forced(True, series_path=copy):
        want1 = sum(vf.season_value_usd(w, 2027) * vf.season_discount(2027) for w in (3.0, 1.0, 0.0, 2.0))
        want9 = vf.season_value_usd(1.0, 2035) * vf.season_discount(2035)
    assert X["X"]["1"] == pytest.approx(want1)
    assert X["X"]["9"] == pytest.approx(want9)
    xs = lab.taper_fold(X["X"])
    assert xs[5] == pytest.approx(X["X"]["5"] + 0.8 * X["X"]["6"] + 0.6 * X["X"]["7"]
                                  + 0.4 * X["X"]["8"] + 0.2 * X["X"]["9"])
    ctx = lab.build_context(PASS_SERIES)
    du = lab.delta_usd(ctx, xs, type_m=1.6)
    heads = [r["diff"] for r in du["per_origin"] if r["origin"] in (2018, 2019, 2020, 2021)]
    assert du["DeltaUSD"] == pytest.approx(np.mean(heads))
    assert du["DeltaUSD_over_type_m"] == pytest.approx(du["DeltaUSD"] / 1.6)


# ---------------------------------------------------------------- integrity, git and the ledger

def test_i6_md5_check(tmp_path):
    p = tmp_path / "fa_dpw_series.json"
    p.write_text("{}", encoding="utf-8")
    start = lab.md5_file(p)
    assert lab.check_md5_unchanged(start, p)["unchanged"] is True
    p.write_text('{"x": 1}', encoding="utf-8")
    with pytest.raises(lab.LabRefused):
        lab.check_md5_unchanged(start, p)


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


@pytest.fixture
def scratch(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "lab@example.invalid")
    _git(repo, "config", "user.name", "lab test")
    _git(repo, "config", "core.autocrlf", "false")
    return repo


def test_i7_blob_check_on_both_files(scratch):
    a, b = scratch / "dpw_path_gate.py", scratch / "dpw_path.py"
    a.write_text("x = 1\n", encoding="utf-8")
    b.write_text("y = 2\n", encoding="utf-8")
    _git(scratch, "add", ".")
    _git(scratch, "commit", "-q", "-m", "lab")
    rec = lab.blob_shas([a, b], cwd=scratch)
    assert all(v["equal"] for v in rec.values()) and len(rec) == 2
    assert rec["dpw_path.py"]["working"] == _git(scratch, "hash-object", str(b))
    lab.check_blobs(rec)
    b.write_text("y = 3\n", encoding="utf-8")
    rec = lab.blob_shas([a, b], cwd=scratch)
    with pytest.raises(lab.LabRefused):
        lab.check_blobs(rec)


def test_the_amendment_lookup_returns_the_amendment_alone(scratch):
    assert not any(ln.startswith(lab.AMENDMENT_HEADING) for ln in DOC.splitlines())
    rel = lab.GATE_DOC_REL
    p = scratch / rel
    p.parent.mkdir(parents=True)
    p.write_bytes(DOC.encode("utf-8"))                                   # LF, as the repository stores it
    _git(scratch, "add", ".")
    _git(scratch, "commit", "-q", "-m", "registration")
    p.write_bytes(DOC.replace("Nothing in this document was scored.",
                              "Nothing in this document was scored. ").encode("utf-8"))
    _git(scratch, "commit", "-qam", "unrelated edit")
    assert lab.amendment_commits(cwd=scratch, doc_rel=rel) == []
    text = p.read_bytes().decode("utf-8")
    text = text.replace("## 18. Results", lab.AMENDMENT_HEADING + "\n\nwhat moved on disk\n\n---\n\n## 18. Results")
    p.write_bytes(text.encode("utf-8"))
    _git(scratch, "commit", "-qam", "amendment")
    amend = _git(scratch, "rev-parse", "HEAD")
    assert lab.amendment_commits(cwd=scratch, doc_rel=rel) == [amend]


def test_real_refuses_without_exactly_one_amendment_or_without_registered(monkeypatch):
    monkeypatch.setattr(lab, "amendment_commits", lambda cwd=None: [])
    with pytest.raises(lab.LabRefused):
        lab.preflight_real()
    monkeypatch.setattr(lab, "amendment_commits", lambda cwd=None: ["a" * 40, "b" * 40])
    with pytest.raises(lab.LabRefused):
        lab.preflight_real()
    monkeypatch.setattr(lab, "amendment_commits", lambda cwd=None: ["a" * 40])
    monkeypatch.setattr(lab, "repo_rel", lambda p: Path(p).name)
    monkeypatch.setattr(lab, "show_at", lambda c, rel, cwd=None: json.dumps(
        {"dpw_path_gate": {"verdict": "NULL"}}))
    with pytest.raises(lab.LabRefused):
        lab.preflight_real()
    monkeypatch.setattr(lab, "show_at", lambda c, rel, cwd=None: json.dumps({}))
    with pytest.raises(lab.LabRefused):
        lab.preflight_real()


def _owner(rows):
    out = []
    for r in rows:
        dp.append_chained(out, {"date": "2026-09-30", "question": "q", "answer": "verbatim text", **r})
    return {"schema": dp.OWNER_SCHEMA, "answers": out}


def test_owner_at_amendment_comes_from_the_amendment_tree_as_codes(scratch):
    p = scratch / "data" / "dpw_path_owner.json"
    p.parent.mkdir(parents=True)
    doc = _owner([{"id": "OD-6", "option": "serve_at_dev_pass"},
                  {"id": "OD-7", "option": "remeasure_served_rule"}])
    p.write_text(json.dumps(doc), encoding="utf-8")
    _git(scratch, "add", ".")
    _git(scratch, "commit", "-q", "-m", "amendment")
    c = _git(scratch, "rev-parse", "HEAD")
    live = _owner([{"id": "OD-6", "option": "serve_at_dev_pass"},
                   {"id": "OD-7", "option": "remeasure_served_rule"}, {"id": "OD-6", "option": "never"}])
    p.write_text(json.dumps(live), encoding="utf-8")                      # changed after the amendment
    rec = lab.owner_record_at(c, cwd=scratch, rel="data/dpw_path_owner.json")
    assert rec["OD-6"]["option"] == "serve_at_dev_pass" and rec["row_count"] == 2
    assert rec["OD-6"]["row_sha256"] == dp.sha256_of(doc["answers"][0])
    assert rec["OD-7"] == {"option": "remeasure_served_rule", "date": "2026-09-30",
                           "row_sha256": dp.sha256_of(doc["answers"][1])}
    assert "verbatim text" not in json.dumps(rec) and "q" not in rec
    assert dp.serve_condition({"verdict": "PASS_DEV", "blind_status": "PENDING",
                               "owner_at_amendment": rec}) is True


def test_owner_after_look_only_while_the_floor_flag_is_raised(tmp_path):
    ev = tmp_path / "eval.json"
    ow = tmp_path / "owner.json"
    ow.write_text(json.dumps(_owner([{"id": "OD-7", "option": "remeasure_served_rule"},
                                     {"id": "OD-7", "option": "zero_if_floor"}])), encoding="utf-8")
    ev.write_text(json.dumps({lab.BLOCK_KEY: {"verdict": "NULL_UNDERPOWERED",
                                              "flags": {"INCUMBENT_BELOW_FLOOR": False}}}), encoding="utf-8")
    with pytest.raises(lab.LabRefused):
        lab.owner_after_look(ev, ow)
    ev.write_text(json.dumps({lab.BLOCK_KEY: {"verdict": "NULL_UNDERPOWERED",
                                              "flags": {"INCUMBENT_BELOW_FLOOR": True}}}), encoding="utf-8")
    blk = lab.owner_after_look(ev, ow)
    assert blk["owner_after_look"]["OD-7"]["option"] == "zero_if_floor"
    assert blk["owner_after_look"]["row_count"] == 2
    assert dp.g_ref_rule(blk) == "zero_if_floor"
    ow.write_text(json.dumps(_owner([{"id": "OD-7", "option": "keep_0409"}])), encoding="utf-8")
    with pytest.raises(lab.LabRefused):
        lab.owner_after_look(ev, ow)


def test_the_ledger_chain_and_its_head(tmp_path):
    led = tmp_path / "ledger.json"
    h1 = lab.append_ledger([{"kind": "forecast", "i": 1}, {"kind": "forecast", "i": 2}], led)
    h2 = lab.append_ledger([{"kind": "forecast", "i": 3}], led)
    rows = json.loads(led.read_text(encoding="utf-8"))["rows"]
    assert h1["row_count"] == 2 and h2["row_count"] == 3 and rows[0]["prev_sha256"] == dp.ZERO_SHA
    dp.check_head(rows, h2)
    with pytest.raises(dp.DpwPathError):
        dp.check_head(rows[:-1], h2)                                      # removing the last row is seen
    rows[1]["i"] = 99
    with pytest.raises(dp.DpwPathError):
        dp.verify_chain(rows)


def _series_doc(truth):
    blk = kit.synthetic_block()
    t = {"estimator": {"id": dp.TRUTH_ESTIMATOR_ID, "numerator_rate": 0.07, "denominator_rate": 0.07},
         "by_winter": {str(k): v for k, v in truth.items()}, "tau_by_winter": {"2026": 0.03},
         "term_mix_index": {"weights": dict(dp.TERM_MIX_WEIGHTS), "by_winter": {}, "dropped_buckets": {}},
         "scheduled_share_by_winter": {}}
    t["sha256"] = dp.sha256_of({k: t[k] for k in ("estimator", "by_winter", "tau_by_winter", "term_mix_index")})
    blk["truth"] = t
    blk["served_level"]["by_winter"] = {str(k): v * 0.88 for k, v in truth.items()}
    blk["enrichment"] = {"p20": True, "war_provider": "fwar", "use_ml": False,
                         "projection_switches": {"EEPHUS_FA_PTFIT": {"raw": None, "resolved": "hit"}}}
    return {"usd_per_war_by_winter": {str(k): int(v) for k, v in truth.items()}, "dpw_path": blk}


def _blind_reader(extra=None):
    docs = {"data/fa_dpw_series.json": {"usd_per_war_by_winter": {"2025": 1, "2026": 2},
                                        "dpw_path": {"path": {"usd_by_season": {"2027": 3}}}},
            "data/dpw_forecast_eval.json": {"test_winters": [2025, 2026], "per_winter": [{"winter": 2026}]}}
    docs.update(extra or {})
    return lambda rel: docs.get(rel)


@pytest.fixture
def no_errors(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("an error or the oracle was computed in --prelook")
    for name in ("compare", "losses", "g_star", "attach_g_star", "cells", "power_block", "run_look",
                 "delta_usd", "band_coverage", "descriptive_arms"):
        monkeypatch.setattr(lab, name, boom)


def test_prelook_writes_the_stub_and_blind_rows_with_no_error_and_no_oracle(tmp_path, no_errors):
    ev, led = tmp_path / "eval.json", tmp_path / "ledger.json"
    ev.write_text(json.dumps({"generated_at": "2026-08-19", "per_winter": []}), encoding="utf-8")
    stub = lab.prelook(series_doc=_series_doc(PASS_SERIES), eval_path=ev, ledger_path=led,
                       reader=_blind_reader(), deal_count=lambda w: 0, scrape_at="2026-11-02T09:00",
                       today="2026-11-02T10:00:00Z", check_epoch=False)
    doc = json.loads(ev.read_text(encoding="utf-8"))
    assert doc["generated_at"] == "2026-08-19"                            # the tool's stamp untouched
    blk = doc[lab.BLOCK_KEY]
    assert blk["verdict"] == "REGISTERED" and blk["truth_sha256"] == stub["truth_sha256"]
    assert blk["I5"]["parity_pass"] is True and blk["I3"]["p20"] is True
    assert blk["blind_check_origin"]["count"] == 0 and blk["blind_check_origin"]["blind"] is True
    rows = json.loads(led.read_text(encoding="utf-8"))["rows"]
    assert len(rows) == 6 * 5 and {r["arm"] for r in rows} == set(dp.METHODS)
    assert blk["ledger"] == dp.chain_head(rows)
    assert not any(k in blk for k in lab.RESULT_KEYS)
    assert all("forecast_usd" in r and "error" not in json.dumps(r) for r in rows)


def test_prelook_writes_no_rows_when_not_blind(tmp_path, no_errors):
    ev, led = tmp_path / "eval.json", tmp_path / "ledger.json"
    reader = _blind_reader({"data/fa_class.json": {"dpw_series_pricing": {"2026": 1, "2027": 2}}})
    lab.prelook(series_doc=_series_doc(PASS_SERIES), eval_path=ev, ledger_path=led, reader=reader,
                deal_count=lambda w: 0, check_epoch=False)
    blk = json.loads(ev.read_text(encoding="utf-8"))[lab.BLOCK_KEY]
    assert blk["blind_check_origin"]["count"] == 1 and blk["blind_check_origin"]["blind"] is False
    assert "ledger" not in blk and not led.exists()
    ev.unlink()
    lab.prelook(series_doc=_series_doc(PASS_SERIES), eval_path=ev, ledger_path=led, reader=_blind_reader(),
                deal_count=lambda w: 3, check_epoch=False)
    assert json.loads(ev.read_text(encoding="utf-8"))[lab.BLOCK_KEY]["blind_check_origin"]["blind"] is False


def test_prelook_refuses_once_the_block_carries_a_result(tmp_path, no_errors):
    ev = tmp_path / "eval.json"
    for blk in ({"verdict": "NULL"}, {"verdict": "REGISTERED", "power": {}}):
        ev.write_text(json.dumps({lab.BLOCK_KEY: blk}), encoding="utf-8")
        with pytest.raises(lab.LabRefused):
            lab.prelook(series_doc=_series_doc(PASS_SERIES), eval_path=ev, ledger_path=tmp_path / "l.json",
                        reader=_blind_reader(), deal_count=lambda w: 0, check_epoch=False)


def test_prelook_refuses_without_the_step_z_entry(tmp_path, monkeypatch, no_errors):
    monkeypatch.setattr(lab, "step_z_entry", lambda text=None: None)
    with pytest.raises(lab.LabRefused):
        lab.prelook(series_doc=_series_doc(PASS_SERIES), eval_path=tmp_path / "e.json",
                    ledger_path=tmp_path / "l.json", reader=_blind_reader(), deal_count=lambda w: 0)


def test_the_step_z_reader():
    empty = "## 9. Results\n\n**EMPTY AT REGISTRATION.**\n"
    assert lab.step_z_entry(empty) is None
    assert lab.step_z_entry(empty + "\n2026-11-20: step Z recorded at abc123\n") == "2026-11-20"


def test_the_blindness_check_named_paths_and_the_commit_recheck(scratch):
    docs = {"data/fa_dpw_series.json": {"usd_per_war_by_winter": {"2026": 1},
                                        "breakdown": {"by_winter": {"2026": {}}},
                                        "dpw_path": {"path": {"usd_by_season": {"2027": 5}},
                                                     "salary_index": {"league_min_by_season": {"2027": 1}},
                                                     "truth": {"by_winter": {"2026": 1}}},
                                        "other": {"2027": 1}},
            "data/fa_meta.json": {"dpw_series": {"usd_per_war_by_winter": {"2026": 1}}},
            "data/fa_archive.json": {"winters": [{"year": 2025}, {"year": 2026}]}}
    chk = lab.blindness(2026, reader=lambda rel: docs.get(rel), deal_count=lambda w: 0)
    assert chk["count"] == 0 and chk["blind"] is True
    assert any("other" in u for u in chk["unclassified_year_maps"])
    docs["data/fa_archive.json"]["winters"].append({"year": 2027})
    chk2 = lab.blindness(2026, reader=lambda rel: docs.get(rel), deal_count=lambda w: 0)
    assert chk2["count"] == 1 and chk2["blind"] is False
    # the re-check on the adding commit's blobs reads git show, not the working tree
    for rel, d in docs.items():
        p = scratch / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d), encoding="utf-8")
    _git(scratch, "add", ".")
    _git(scratch, "commit", "-q", "-m", "rows")
    c = _git(scratch, "rev-parse", "HEAD")
    (scratch / "data" / "fa_archive.json").write_text(json.dumps({"winters": []}), encoding="utf-8")

    def at_commit(rel):
        try:
            return json.loads(lab.show_at(c, rel, cwd=scratch))
        except subprocess.CalledProcessError:
            return None
    assert lab.blindness(2026, reader=at_commit, deal_count=lambda w: 0)["count"] == 1


def test_the_lab_never_touches_the_banned_modules_or_the_series_file():
    src = (ROOT / "tools" / "dpw_path_gate.py").read_text(encoding="utf-8")
    for banned in ("import backtest", "from backtest", "surplus_backtest_real", "run_market_gate(",
                   "SERIES_PATH.write_text", "fv_tier", "by_fv"):
        assert banned not in src.replace("imports neither backtest nor surplus_backtest_real", "").replace(
            "fa_backtest.run_market_gate, computes", ""), banned
    assert "dpw_path_forced(True, series_path=series_copy)" in src
