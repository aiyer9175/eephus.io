# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The skill look's amended targets, pinned on fixtures (docs/ebr-2026-09-30/
EBR_GATE.md part 11: 11.2.10, 11.3.8, 11.4.7, 11.5.4, 11.6.4 and 11.7).

Every cell machinery test carries a null comparator and a planted recovery: a
delta planted as a fixed share of the target's own Y+1 deviation reads WIN on
both cells, an all-zero delta never reads WIN, and the planted delta's twin
fails. Nothing here reads real data or relates any real delta to a
next-season quantity.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import swar  # noqa: E402
import swar_lab as L  # noqa: E402
import swar_targets as T  # noqa: E402

BOOT = 300
A = dict(L.ANSWERS, void=False)


# --------------------------------------------------------------------------
# synthetic pairs: a talent per player, B0 and the target its noisy readings
# --------------------------------------------------------------------------

def _pairs(share: float, n_players: int = 300, seasons=(2021, 2022, 2023, 2024), seed: int = 1,
           sd_talent: float = 0.03, sd_noise: float = 8.0) -> list[dict]:
    rng = np.random.default_rng(seed)
    talent = rng.normal(0.0, sd_talent, n_players)
    out = []
    for y in seasons:
        for i in range(n_players):
            n0, n1 = float(rng.uniform(200, 700)), float(rng.uniform(200, 700))
            out.append({"mlbam": i, "y": y, "n0": n0, "n1": n1,
                        "b0": float(talent[i] * n0 + rng.normal(0, sd_noise)),
                        "tgt": float(talent[i] * n1 + rng.normal(0, sd_noise)),
                        "b0r": None, "m": 0.0, "sigma": 0.6, "tests": {}})
    mean = float(np.mean([p["tgt"] / p["n1"] for p in out]))
    for p in out:
        dev = (p["tgt"] / p["n1"] - mean) * p["n0"]      # the target's own Y+1 deviation, on Y's exposure
        p["tests"]["planted"] = p["b0"] + share * dev
        p["tests"]["zero"] = p["b0"]                     # the null comparator: an all-zero delta
    return out


def _family(part: str, frames_of, key: str, k_b1: float = 500.0, transport=None) -> dict:
    fam = {}
    for j, kind in enumerate((L.RATE, L.CUM)):
        rec = L.finish_primary(L.prep_primary(part, kind, frames_of(key), kind, k_b1, BOOT, L.SEED,
                                              L.SEED + 7 * j))
        if transport is not None:
            rec["transport"] = transport
        fam[kind] = rec
    return L.decide_family(fam)


@pytest.mark.parametrize("part", [L.PART_BATTING, L.PART_FIELDING, L.PART_PE_H])
def test_a_planted_delta_reads_win_on_both_cells_and_its_twin_fails(part):
    pairs = _pairs(0.5)
    fam = _family(part, lambda k: [("x", pairs, k)], "planted")
    for kind, r in fam.items():
        assert r["disposition"] == L.WIN_COMPONENTS, (kind, r["disposition"], r["gap"], r["b1_lo95"])
        assert r["twin_lo95"] <= 0.0
        assert r["b0r"] is None    # no B0r on these pairs: nothing to print beside


@pytest.mark.parametrize("part", [L.PART_BATTING, L.PART_PITCHING, L.PART_FIELDING, L.PART_PE_P, L.PART_PE_H])
def test_an_all_zero_delta_never_reads_win(part):
    pairs = _pairs(0.5)
    fam = _family(part, lambda k: [("x", pairs, k)], "zero", transport=True)
    for r in fam.values():
        assert r["gap"] == pytest.approx(0.0, abs=1e-12)
        assert r["disposition"] not in L.WINS + (L.SMALL_WIN,)


def test_the_pitching_parts_need_era_transport_for_win_components():
    pairs = _pairs(0.5)
    for part in (L.PART_PITCHING, L.PART_PE_P):
        fam = _family(part, lambda k: [("x", pairs, k)], "planted", transport=False)
        assert fam[L.RATE]["disposition"] == L.WIN_REGRESSION
        fam = _family(part, lambda k: [("x", pairs, k)], "planted", transport=True)
        assert fam[L.RATE]["disposition"] == L.WIN_COMPONENTS
    early = _pairs(0.5, seasons=(2016, 2017, 2018), seed=3)
    assert L.point_gap_frames([("p", early, "planted")], L.RATE, 400.0) > 0
    assert L.point_gap_frames([("p", early, "zero")], L.RATE, 400.0) == pytest.approx(0.0, abs=1e-12)


def test_s3t_scores_the_mean_of_per_system_gaps_in_one_bootstrap():
    systems = {name: _pairs(0.5, seed=s) for name, s in (("DRS", 11), ("Statcast", 12), ("UZR", 13))}
    frames = lambda k: [(n, ps, k) for n, ps in systems.items()]  # noqa: E731
    fam = _family(L.PART_FIELDING, frames, "planted", k_b1=1398.0)
    rate = fam[L.RATE]
    assert set(rate["per_system"]) == {"DRS", "Statcast", "UZR"}
    assert rate["gap"] == pytest.approx(np.mean([v["gap"] for v in rate["per_system"].values()]), abs=1e-9)
    assert rate["n_rows"] == 3 * rate["n_pairs"]       # the same 1,200 pairs, read by three systems
    assert rate["disposition"] == L.WIN_COMPONENTS and rate["twin_lo95"] <= 0.0
    null = _family(L.PART_FIELDING, frames, "zero", k_b1=1398.0)
    assert all(r["disposition"] not in L.WINS for r in null.values())


def test_pe_h_sensitivity_uses_the_same_bootstrap_draws():
    pairs = _pairs(0.5)
    a = L.prep_primary(L.PART_PE_H, "r", [("pe_h", pairs, "planted")], L.RATE, 427.0, 50, L.SEED, 1)
    alt = [dict(p, tgt=p["tgt"] + 1.0) for p in pairs]
    b = L.prep_primary(L.PART_PE_H, "s", [("pe_h", alt, "planted")], L.RATE, 427.0, 50, L.SEED, 1)
    assert a["n_pairs"] == b["n_pairs"]
    da, db = a["_draws"]["v2"]["b0"], b["_draws"]["v2"]["b0"]
    assert np.isfinite(da).all() and np.isfinite(db).all()


def test_a_contrast_between_arms_reads_the_better_arm_above_zero():
    pairs = _pairs(0.5)
    for p in pairs:
        p["tests"]["half"] = p["b0"] + 0.5 * (p["tests"]["planted"] - p["b0"])
    c = L.contrast_frames([("x", pairs, "planted")], "half", BOOT, L.SEED + 9001, 500.0)
    assert c["gap"] > 0 and c["lo95"] > 0
    c = L.contrast_frames([("x", pairs, "zero")], "zero", BOOT, L.SEED + 9001, 500.0)
    assert c["gap"] == pytest.approx(0.0, abs=1e-12)


# --------------------------------------------------------------------------
# the team guard (11.2.4)
# --------------------------------------------------------------------------

def _guard_mats(part_kind: str, seed: int = 5):
    rng = np.random.default_rng(seed)
    P, C = 600, 120
    clubs = [(2022 + j // 30, f"T{j % 30:02d}") for j in range(C)]
    frame = np.zeros((P, C))
    for i in range(P):
        frame[i, rng.integers(0, C)] = rng.normal(1.0, 1.0)
    pit = np.zeros((P, C))
    y = frame.sum(axis=0) + rng.normal(0, 1.0, C)
    if part_kind == "same":
        part = frame.copy()
    elif part_kind == "close":
        part = frame + np.where(frame != 0, rng.normal(0, 0.05, frame.shape), 0.0)
    else:
        part = np.where(frame != 0, rng.normal(1.0, 1.0, frame.shape), 0.0)
    mats = {"hit": {"frame": frame, "part": part, "ref": frame * 0.9},
            "pit": {"frame": pit, "part": pit, "ref": pit}}
    outcomes = {"run_differential": y, "wins": y / 10.0 + 81.0}
    return mats, outcomes, clubs


def test_the_team_guard_passes_an_identical_or_close_series_and_fails_a_destroyed_one():
    for kind, expect in (("same", True), ("close", True), ("noise", False)):
        mats, outcomes, clubs = _guard_mats(kind)
        g = T.team_guard(mats, outcomes, T.OUTCOMES_FIELD, clubs, boot=200, seed=T.GUARD_SEED)
        assert g["non_inferior"] is expect, (kind, g["outcomes"]["wins"])
        if kind == "same":
            assert g["outcomes"]["wins"]["dT"] == pytest.approx(0.0, abs=1e-12)
        for o in g["outcomes"].values():
            assert set(o["player"]) >= {"sd", "half_width95", "lower", "non_inferior"}
            assert o["r_bwar_reference"] is not None
    assert (T.GUARD_SEED, T.GUARD_BOOT, T.GUARD_Z, T.GUARD_MARGIN) == (20261024, 2000, 1.645, -0.02)


def test_the_roster_weighting_handles_turnover_and_absent_players():
    vals = {(2021, 1): 3.0, (2021, 2): 1.0, (2021, 3): None}
    expo = {(2021, 1): 600.0, (2021, 2): 0.0, (2021, 3): 300.0}
    nxt = {(2022, 1): {"AAA": 300.0, "BBB": 200.0}, (2022, 2): {"AAA": 100.0}, (2022, 4): {"BBB": 500.0}}
    M = T.roster_matrix(vals, expo, nxt, [1, 2, 3, 4], [(2022, "AAA"), (2022, "BBB")])
    assert M[0].tolist() == pytest.approx([1.5, 1.0])     # 3.0 / 600 x 300, x 200: split across clubs
    assert M[1:].sum() == 0.0                            # no Y exposure, no value, or no Y row: 0


# --------------------------------------------------------------------------
# admission, amended
# --------------------------------------------------------------------------

def _cells(**disp):
    return {c: {"disposition": d, "gap": 0.03} for c, d in disp.items()}


OK = {"non_inferior": True}
NO = {"non_inferior": False}


def test_batting_needs_the_guard_and_the_contrast_decides_between_qualifying_arms():
    cells = _cells(**{"HEM+ H-rate": L.WIN_COMPONENTS, "HEM+ H-cum": L.EQUIVALENT,
                      "xHEM+ H-rate": L.WIN_COMPONENTS, "xHEM+ H-cum": L.UNRESOLVED})
    out = L.admit_amended(L.PART_BATTING, cells, {"bat": OK, "batx": OK}, A)
    assert out["needs_contrast"] and not out["admitted"]
    out = L.admit_amended(L.PART_BATTING, cells, {"bat": OK, "batx": OK}, A, {"contrast": {"lo95": 0.004}})
    assert out["admitted"] and out["arm"] == "xHEM+"
    out = L.admit_amended(L.PART_BATTING, cells, {"bat": OK, "batx": OK}, A, {"contrast": {"lo95": -0.001}})
    assert out["arm"] == "HEM+"
    out = L.admit_amended(L.PART_BATTING, cells, {"bat": OK, "batx": NO}, A)
    assert out["admitted"] and out["arm"] == "HEM+" and not out["needs_contrast"]
    out = L.admit_amended(L.PART_BATTING, cells, {"bat": NO, "batx": NO}, A)
    assert not out["admitted"]


def test_fielding_arms_and_the_catcher_component_are_judged_apart():
    cells = _cells(**{"H-rate": L.LOSS, "H-cum": L.LOSS, "S3t H-rate": L.WIN_COMPONENTS,
                      "S3t H-cum": L.EQUIVALENT, "C-rate": L.WIN_COMPONENTS, "C-cum": L.UNRESOLVED})
    out = L.admit_amended(L.PART_FIELDING, cells, {"fld": OK, "fldt": OK, "cat": OK}, A)
    assert out["admitted"] and out["arm"] == "S3t" and out["catcher_component"]["admitted"]
    out = L.admit_amended(L.PART_FIELDING, cells, {"fld": OK, "fldt": OK, "cat": NO}, A)
    assert out["arm"] == "S3t" and not out["catcher_component"]["admitted"]
    both = dict(cells, **_cells(**{"H-rate": L.WIN_COMPONENTS, "H-cum": L.EQUIVALENT}))
    out = L.admit_amended(L.PART_FIELDING, both, {"fld": OK, "fldt": OK, "cat": OK}, A)
    assert out["needs_contrast"]
    out = L.admit_amended(L.PART_FIELDING, both, {"fld": OK, "fldt": OK, "cat": OK}, A, {"contrast": {"lo95": 0.0}})
    assert out["arm"] == "S3"


def test_pe_parts_position_and_void():
    pe_h = _cells(**{"PE-H rate": L.WIN_COMPONENTS, "PE-H total": L.EQUIVALENT})
    assert L.admit_amended(L.PART_PE_H, pe_h, {"peh": OK}, A, {"sensitivity": {"loss": False}})["admitted"]
    assert not L.admit_amended(L.PART_PE_H, pe_h, {"peh": OK}, A, {"sensitivity": {"loss": True}})["admitted"]
    pe_p = _cells(**{"PE-P rate": L.WIN_COMPONENTS, "PE-P total": L.LOSS})
    assert not L.admit_amended(L.PART_PE_P, pe_p, {"pep": OK}, A)["admitted"]
    assert L.admit_amended(L.PART_POSITION, {}, {"pos": OK}, A, {"ladder": {"passes": True}})["admitted"]
    assert not L.admit_amended(L.PART_POSITION, {}, {"pos": NO}, A, {"ladder": {"passes": True}})["admitted"]
    for part in L.PRIMARY_PARTS + (L.PART_POSITION,):
        out = L.admit_amended(part, pe_h, {"peh": OK}, {"void": True})
        assert not out["admitted"]


def test_the_ladder_test_reads_the_gate_and_its_null_control():
    ev = {"gate": "g", "seeds": {"bootstrap": 20261015, "draws": 2000},
          "tests": {"v1_minus_fg_inv_pooled": {"dmae": -0.2, "ci95": [-0.3, -0.1], "n_rows": 9, "n_players": 3},
                    "v1_minus_fg_table_pooled": {"dmae": 0.1, "ci95": [0.0, 0.2]}}}
    ve = {"zero_ladder": {"tests": {"v1_minus_zero": {"dmae": -0.5, "ci95": [-0.7, -0.3]}}}}
    out = T.ladder_test(ev, ve, "v1")
    assert out["dmae_ladder_favour"] == pytest.approx(0.2) and out["lo95"] == pytest.approx(0.1)
    assert out["control_fails"] and out["passes"]
    ve["zero_ladder"]["tests"]["v1_minus_zero"] = {"dmae": 0.84, "ci95": [0.66, 1.03]}
    assert not T.ladder_test(ev, ve, "v1")["passes"]
    assert not T.ladder_test(ev, ve, "v2")["available"]


def test_the_amended_sentences_name_the_component_and_the_frame():
    s = L.amended_sentence("bat", L.WIN_COMPONENTS, 0.031, 0.01, 0.05, 1234)
    assert s.startswith("ranked the next season's realized batting runs better than the season's own "
                        "batting runs did, and better than a uniformly shrunk version of them")
    assert "1,234 pairs" in s and "hitters with 200 or more PA" in s
    s = L.amended_sentence("pit", L.SMALL_WIN)
    assert "about as well as" in s and "runs allowed (adjusted for park, defense and inherited runners)" in s
    assert "pitchers with 50 or more IP" in s
    assert "catchers with 300 or more innings at C" in L.amended_sentence("cat", L.LOSS)
    assert L.amended_sentence("peh", L.UNRESOLVED) is None
    for comp in L.COMPONENT_RUNS:
        for d in L.DISPOSITIONS:
            t = L.amended_sentence(comp, d) or ""
            for banned in ("fWAR", "more accurate", "better than FanGraphs", "true talent", "regress"):
                assert banned not in t


# --------------------------------------------------------------------------
# the components on the fixture league
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def league():
    inputs = L.FixtureLabInputs()
    rows = L.season_rows(inputs.preview())
    consts = L.assemble(rows, inputs, range(2016, 2027), (2021, 2022, 2023, 2024, 2025), log=lambda *a: None)
    return inputs, rows, consts


def test_the_amended_deltas_sum_to_zero_and_spare_pitcher_batters(league):
    _inputs, rows, _consts = league
    for y, blk in rows.items():
        for key in ("cat", "fldt_FULL", "fldt_X_DRS", "peh"):
            d = [r["d"][key] for r in blk[L.HIT].values()]
            assert abs(sum(d)) < 1e-9 or key == "peh", (y, key)
        for m, r in blk[L.HIT].items():
            if r["pitcher_batter"]:
                assert r["d"]["cat"] == 0.0 and r["d"]["fldt_FULL"] == 0.0 and r["d"]["peh"] == 0.0
        if y in (2016, 2017, 2020, 2026):           # outside the corpus seasons asked for: 0, no W
            assert all(r["d"]["peh"] == 0.0 and r["W"] is None for r in blk[L.HIT].values())


def test_component_pairs_floors_frames_and_targets(league):
    _inputs, rows, consts = league
    for comp in L.COMPONENTS:
        ps = L.component_pairs(rows, comp, (2018, 2019, 2021, 2022, 2023, 2024), consts)
        assert all(p["y"] != 2019 and p["y"] != 2020 for p in ps)          # 2020 out on both sides
        side = L.COMPONENTS[comp]["side"]
        for p in ps:
            r0, r1 = rows[p["y"]][side][p["mlbam"]], rows[p["y"] + 1][side][p["mlbam"]]
            f = L.EXPOSURE[side]
            assert r0[f] >= L.FLOOR[side] and r1[f] >= L.FLOOR[side]
            if comp == "cat":
                assert r0["c_inn"] >= T.CATCHER_MIN_INN
            if comp == "fldt:UZR":
                assert p["y"] + 1 <= T.UZR_LAST
    blank = L.component_pairs(rows, "bat", (2021,), consts, with_tests=False)
    assert blank and all(p["tests"] == {} for p in blank)
    pit = L.component_pairs(rows, "pit", (2021,), consts)
    p = pit[0]
    r1 = rows[2022][L.PIT][p["mlbam"]]
    assert p["tgt"] == pytest.approx((consts[2022]["lg_ra9s"] - r1["ra9_star"]) * r1["ip"] / 9.0)
    assert set(p["tests"]) >= set(swar.HR_VARIANTS) | set(L.PB_VARIANTS) | {"pep_hr_shrunk", "pep_hr_fwar"}


def test_score_primary_scores_every_registered_cell_once(league):
    _inputs, rows, consts = league
    blk = L.score_primary(rows, consts, L.PREDICTOR_SEASONS, 40, log=lambda *a: None)
    fams = {p: list(c) for p, c in blk["cells"].items()}
    assert fams == {"batting": ["HEM+ H-rate", "HEM+ H-cum", "xHEM+ H-rate", "xHEM+ H-cum"],
                    "pitching": ["P-rate", "P-cum", "S2b P-rate", "S2b P-cum"],
                    "fielding": ["H-rate", "H-cum", "S3t H-rate", "S3t H-cum", "C-rate", "C-cum"],
                    "pe_p": ["PE-P rate", "PE-P total"], "pe_h": ["PE-H rate", "PE-H total"]}
    assert len(blk["cells"]["fielding"]) == 6        # k = 6 with S3t eligible (EW3-37, 11.7)
    for fam in blk["cells"].values():
        for r in fam.values():
            assert r["disposition"] in L.DISPOSITIONS and r["holm_family"] == list(fam)
    assert blk["cells"]["pitching"]["P-cum"]["transport"] == blk["cells"]["pitching"]["P-rate"]["transport"]
    assert "transport" in blk["cells"]["pe_p"]["PE-P rate"]
    assert blk["hr"]["variant"] in swar.HR_VARIANTS and "RA9*" in blk["hr"]["target"]
    assert set(blk["sensitivity"]) >= {"gap", "hi95", "loss"}
    assert all(k.count("|") == 2 for k in blk["floors"])


def test_admissions_compute_each_contrast_on_the_primary_pairs_when_two_arms_qualify(league):
    _inputs, rows, consts = league
    win = {"disposition": L.WIN_COMPONENTS, "gap": 0.05}
    cells = {L.PART_BATTING: {c: dict(win) for c in L.PRIMARY_FAMILIES[L.PART_BATTING]},
             L.PART_PITCHING: {c: dict(win) for c in L.PRIMARY_FAMILIES[L.PART_PITCHING]},
             L.PART_FIELDING: {c: dict(win) for c in L.PRIMARY_FAMILIES[L.PART_FIELDING]},
             L.PART_PE_P: {c: dict(win) for c in L.PRIMARY_FAMILIES[L.PART_PE_P]},
             L.PART_PE_H: {c: dict(win) for c in L.PRIMARY_FAMILIES[L.PART_PE_H]}}
    blk = {"cells": cells, "pairs": L.build_all_pairs(rows, L.PREDICTOR_SEASONS, consts),
           "variant": swar.HR_SHRUNK, "sensitivity": {"loss": False}}
    guards = {k: OK for k in L.GUARD_SERIES}
    adm = L.admissions_amended(blk, guards, {"passes": False}, 40, A, log=lambda *a: None)
    for part in (L.PART_BATTING, L.PART_PITCHING, L.PART_FIELDING):
        assert adm[part]["admitted"] and "contrast" in adm[part], part
        assert adm[part]["contrast"]["n_pairs"] > 0
    assert adm[L.PART_FIELDING]["catcher_component"]["admitted"]
    assert adm[L.PART_PE_P]["admitted"] and adm[L.PART_PE_H]["admitted"]
    assert not adm[L.PART_POSITION]["admitted"]
    s = L.amended_sentences(cells, adm, {"passes": False}, "look")
    assert s[L.PART_POSITION] is None and s["fielding_catcher_component"].startswith("ranked")


def test_s3t_ineligible_drops_its_cells(league, monkeypatch):
    monkeypatch.setattr(L, "S3T_ELIGIBLE", False)
    assert list(L.primary_families()["fielding"]) == ["H-rate", "H-cum", "C-rate", "C-cum"]
    assert "S3t H-rate" not in L.secondary_cells()["fielding"]


# --------------------------------------------------------------------------
# B1, the fielding rule, the catcher component, the preview, the record
# --------------------------------------------------------------------------

def test_b1_component_constants_are_frozen_with_their_fit_log():
    assert set(L.B1_K_AMENDED) == {"bat", "pit", "fld", "cat", "pep", "peh"}
    for comp, k in L.B1_K_AMENDED.items():
        f = L.B1_AMENDED_FIT_LOG[comp]
        assert f["k"] == k == round(f["hm"] * (1 - f["r"]) / f["r"]), comp
        assert f["fit_seasons"] == list(L.B1_AMENDED_SEASONS[comp])
    assert L.B1_AMENDED_SEASONS["peh"] == (2018,)
    assert L.B1_COMPONENT["S3t"] == "fld"            # S3t takes the fielding k (11.5.2)
    assert L.B1_K == {"hit": 662.0, "pit": 244.0}    # the secondary estimand keeps a32ff1bb's


def test_the_b1_fit_reads_b0_and_the_target_only(league):
    _inputs, rows, consts = league
    ps = L.component_pairs(rows, "bat", (2016, 2017, 2018), consts, with_tests=False)
    f = L.fit_b1_pairs(ps)
    assert f["k"] == round(f["hm"] * (1 - f["r"]) / f["r"])
    with pytest.raises(L.LabStop):
        L.fit_b1_pairs(ps[:10])


def test_the_fielding_target_rule_and_the_systems_table():
    assert T.fielding_target("fld", 2022) == "bref_runs_field"
    T.PART_SOURCES["_drs_led"] = ("fg_drs",)
    try:
        assert T.fielding_target("_drs_led", 2022) == "savant_frv"
    finally:
        del T.PART_SOURCES["_drs_led"]
    tab = T.system_table([2024, 2025])
    assert "fg_uzr" in tab["2024"] and "fg_uzr" not in tab["2025"]
    assert all(v["documentation"] for v in tab["2024"].values())


def test_the_catcher_component_invariants():
    pa = {1: 500.0, 2: 400.0, 3: 300.0, 4: 250.0}
    rows = {1: {"sc": 8.0, "b0": 5.0, "nonc_frp": 0.0, "c_inn": 900.0},
            2: {"sc": None, "b0": 3.0, "nonc_frp": 0.0, "c_inn": 0.0},        # no catcher row
            3: {"sc": -2.0, "b0": 1.0, "nonc_frp": 2.0, "c_inn": 350.0},
            4: {"sc": 4.0, "b0": 4.0, "nonc_frp": 0.0, "c_inn": 600.0}}       # a pitcher-batter
    assert T.catcher_g(None, 3.0, 0.0, 0.0) == 0.0
    assert T.catcher_g(-2.0, 1.0, 2.0, 350.0) == pytest.approx(-1.0)          # SC - (Fld + Frm - O)
    d = T.catcher_deltas(rows, pa, [4])
    assert d[4] == 0.0 and abs(sum(d.values())) < 1e-9
    same = {m: dict(r, sc=r["b0"] - r["nonc_frp"]) for m, r in rows.items()}
    assert all(v == 0.0 for v in T.catcher_deltas(same, pa, [4]).values())


def test_the_pitching_targets():
    assert T.runs_prevented(4.5, 3.6, 90.0) == pytest.approx(9.0)          # fewer runs rank higher
    assert T.rsb(150.0, 4.2, 3.0) == pytest.approx(150 / 27 * 1.2)
    rows = [{"ra9_star": 4.0, "ip": 100.0, "g": 20, "gs": 20}, {"ra9_star": 3.0, "ip": 50.0, "g": 50, "gs": 0},
            {"ra9_star": None, "ip": 10.0, "g": 5, "gs": 0}]
    assert T.league_ra9_star(rows) == pytest.approx((400 + 150) / 150)
    assert T.league_ra9_star(rows, relievers_only=True) == pytest.approx(3.0)


def test_an_older_preview_without_the_bases_is_refused():
    payload = L.FixtureLabInputs(n_hit=20, n_pit=20).preview()
    L.check_amended_preview(payload)
    for blk in payload["seasons"].values():
        for h in blk["hitters"]:
            h["parts"]["bat"].pop("wraa")
    with pytest.raises(L.LabStop):
        L.check_amended_preview(payload)


def test_the_dry_run_record_carries_the_primary_and_the_secondary(tmp_path):
    out = L.dry_run(log=lambda *a: None, boot=40, tmp_dir=tmp_path)
    rec = json.loads(Path(out["record"]).read_text(encoding="ascii"))
    look = rec["look"]
    assert rec["schema"] == "swar_lab/2" and "11.2.1" in look["estimand"]
    assert set(look["cells"]) == set(L.PRIMARY_PARTS)
    assert set(look["secondary"]["cells"]) == set(L.PRIMARY_PARTS) | {L.PART_POSITION}
    assert set(look["team_guard"]) == set(L.GUARD_SERIES)
    assert set(look["admission"]) == set(L.PRIMARY_PARTS) | {L.PART_POSITION}
    assert look["s3t_eligible"]["eligible"] is True and "EW3-37" in look["s3t_eligible"]["by"]
    assert look["b1"]["k"] == L.B1_K_AMENDED
    assert "next_season_wins" not in look["descriptive"]["team_wins"]
    assert rec["params"]["team_guard"]["seed"] == 20261024
