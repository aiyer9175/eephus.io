# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV tool inputs on eTools (EFV_ETOOLS_REWEIGHT, docs/efv-v2/EFV_ETOOLS_REWEIGHT.md).

Fixtures only; nothing real is scored here.
1. The flag is dark and the served path refuses an unprepared read.
2. The registered sub-driver lists are the served eTools' and the look's.
3. The eTool on a cohort (the formula, the re-centring, the NaN and clip rules) and its
   identity with etools' own construction; the live formula reproduces the served eTools.
4. The fit masks (forward chained, players out) and a planted shift recovered by the joint
   fit; the nulls (consensus values, a permuted shift).
5. The configurations' candidate lists, the V2 key removal, the injection is undone.
6. The ship rule and the attribution check.
7. Gate compliance: no FV-cell grouping, no dash characters.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

import efv5_combined as V5C
import efv5_refit as RF
import efv_etools_reweight as X
import efv_v3 as V3
import etools as E
from test_efv5_combined import _attach_noise
from test_efv_v3 import _rows

ROOT = Path(__file__).parent
SRC = ROOT / "efv_etools_reweight.py"
DOC = ROOT / X.DOC


# ---------------------------------------------------------------------------
# 1. the flag
# ---------------------------------------------------------------------------

def test_the_reweight_is_dark():
    assert X.EFV_ETOOLS_REWEIGHT_ON is False
    assert X.SERVE_CANDIDATE is None


def test_the_served_path_refuses_an_unprepared_read(monkeypatch, tmp_path):
    p = tmp_path / "w.json"
    p.write_text(json.dumps({"prepared": False, "candidate": "E", "passing": [],
                             "models_by_candidate": {}}), encoding="utf-8")
    monkeypatch.setattr(RF, "EFV_V5_REFIT_ON", True)
    with pytest.raises(RuntimeError, match="nothing is prepared"):
        X.production_models(p)
    p.write_text(json.dumps({"prepared": True, "candidate": "E", "passing": ["E"],
                             "models_by_candidate": {}}), encoding="utf-8")
    monkeypatch.setattr(X, "SERVE_CANDIDATE", "ED")
    with pytest.raises(RuntimeError, match="did not pass"):
        X.production_models(p)
    monkeypatch.setattr(RF, "EFV_V5_REFIT_ON", False)
    with pytest.raises(RuntimeError, match="EFV_V5_REFIT_ON"):
        X.production_models(p)


# ---------------------------------------------------------------------------
# 2. the registered lists
# ---------------------------------------------------------------------------

def test_the_sub_drivers_are_the_served_and_the_looks():
    served = json.loads(X.SERVED_ETOOLS_PATH.read_text(encoding="utf-8"))["tools"]
    for tool, spec in served.items():
        assert tuple(spec["admitted"]) == X.SUBDRIVERS[tool], tool
        assert spec["construction"] == "recentred"
    look = json.loads(X.ETOOLS_EVAL_PATH.read_text(encoding="utf-8"))["etools"]
    for tool in X.SUBDRIVERS:
        assert tuple(look[tool]["admitted"]) == X.SUBDRIVERS[tool], tool


def test_every_slot_and_removal_names_a_real_column():
    for side in ("hit", "pit"):
        base = RF.refit_candidates(side, "skill", dark=True)
        for s in X.SLOTS[side]:
            if s["kind"] == "column":
                assert s["replaces"] in base
                assert X.NEW_COLUMNS[s["name"]]["side"] == side
                assert X.NEW_COLUMNS[s["name"]]["sign"] == 1
        for n in X.DEDUPE[side]["columns"]:
            assert n in base, n
    assert X.DEDUPE["hit"]["v2"] == ("contact",)


# ---------------------------------------------------------------------------
# 3. the eTool on a cohort and on a live row
# ---------------------------------------------------------------------------

def _fit(c=(2.0, -1.0), lines=((0.0, 0.0, True), (1.0, 0.1, True)), mu=(0.0, 0.0)):
    return {"lines": [list(x) for x in lines], "c": list(c), "mu_tr": list(mu)}


def test_the_etool_formula_by_hand():
    g = np.array([50.0, 60.0, np.nan, 40.0])
    Z = np.array([[1.0, 7.0], [np.nan, 6.0], [0.5, 5.0], [np.nan, np.nan]])
    fit = _fit()
    e = X.etool_cohort(g, Z, fit, centre=False)
    # row 0: 2 * (1 - 0) - 1 * (7 - (1 + 5)) = 2 - 1 = 1
    assert e[0] == pytest.approx(51.0)
    # row 1: only j=1: -1 * (6 - (1 + 6)) = +1
    assert e[1] == pytest.approx(61.0)
    assert np.isnan(e[2])                     # no observed g: no eTool
    assert e[3] == pytest.approx(40.0)        # g and no sub-driver: g
    # the re-centring: the cohort's mean residual of j minus the training mean
    ec = X.etool_cohort(g, Z, fit, centre=True)
    d0 = 1.0                                  # rows 0 only carry j=0 with g: residual 1
    d1 = np.mean([7 - 6, 6 - 7])              # rows 0 and 1 carry j=1
    assert ec[0] == pytest.approx(50 + 2 * (1 - d0) - 1 * (1 - d1))
    assert ec[1] == pytest.approx(60 - 1 * (-1 - d1))
    assert X.etool_cohort(np.array([79.0]), np.array([[30.0, 0.0]]), fit, centre=False)[0] == 80.0


def test_the_cohort_etool_is_etools_own_construction():
    rng = np.random.default_rng(4)
    n = 200
    gc = np.round(rng.normal(50, 8, n) * 2) / 2
    Z = rng.normal(size=(n, 3))
    Z[rng.random((n, 3)) < 0.3] = np.nan
    lines = [(0.1, 0.01, True), (-0.2, 0.004, True), (0.0, 0.0, False)]
    c = [3.0, -2.0, 1.5]
    mu_tr = np.array([0.05, -0.02, 0.0])
    U = E.etool_residuals(gc, Z, lines)
    delta = E._present_mean(U, Z) - mu_tr
    want, _ = E.etool_centred(gc, Z, lines, c, delta)
    got = X.etool_cohort(gc, Z, {"lines": lines, "c": c, "mu_tr": list(mu_tr)})
    assert np.allclose(got, want, atol=1e-12)


def test_the_live_formula_reproduces_the_served_etools():
    served = X._served_etools()
    cb = X.final_fit_cb()
    n = 0
    for pk, p in list(served.items())[:400]:
        for tool, rec in (p.get("tools") or {}).items():
            if rec.get("etool") is None or tool not in cb:
                continue
            got = X.live_etool(rec["consensus"], rec, cb[tool])
            assert got == pytest.approx(rec["etool"], abs=0.03), (pk, tool)
            # away from the served consensus the value moves by 1 - sum c_j b_j per grade
            present = [d[0] for d in rec["drivers"]]
            slope = 1.0 - sum(cb[tool][j] for j in present)
            g2 = rec["consensus"] + 1.0
            if 21 < got < 79 and 21 < got + slope < 79:
                assert X.live_etool(g2, rec, cb[tool]) == pytest.approx(got + slope, abs=1e-9)
            n += 1
    assert n > 100
    assert X.live_etool(None, {}, {}) is None
    assert X.live_etool(47.5, None, {}) == 47.5


# ---------------------------------------------------------------------------
# 4. the fit masks, a planted shift, the nulls
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def bank():
    return X.Bank(E.fixture_frames(seed=7, n_players=260))


def test_a_fit_reads_only_its_board_years_and_leaves_its_players_out(bank):
    fr = bank.frames["hit"]
    years = [2011, 2012, 2013, 2014]
    excl = set(fr.pid[:40].tolist())
    fit = bank.fit("hit", years, excl, tag="t")
    want = int((np.isin(fr.year, years) & ~np.isin(fr.pid, list(excl))).sum())
    assert fit["n_rows"] == want
    assert fit["years"] == years and fit["players_out"] == len(excl)
    assert bank.fit("hit", years, excl) is fit                   # memoized
    other = bank.fit("hit", years, set())
    assert other["n_rows"] > fit["n_rows"]
    assert len(fit["mu_tr"]) == len(X.SUBDRIVERS["hit"])


def test_the_planted_sub_driver_carries_a_positive_slope(bank):
    # the fixture's first sub-driver follows the true grade: its slope is positive
    fit = bank.fit("hit", [y for y in E.DEV_YEARS], set())
    assert fit["c"][0] > 0


def test_the_nulls_consensus_and_permutation():
    rm = X.RowMeta.__new__(X.RowMeta)
    rm.Z = {}
    rng = np.random.default_rng(1)
    n = 60
    rows = [{"player_key": f"p{i}", "v2": {}} for i in range(n)]
    metas = [{"pid": i, "b": 2015, "raw": {"hit": float(45 + i % 10)}} for i in range(n)]
    for i in range(n):
        rm.Z[("hit", i, 2015)] = {"k_rw": float(rng.normal()), "ppa_par": None, "babip_rw": float(rng.normal())}
    fit = {"lines": [(0.0, 0.0, True)] * 3, "c": [2.0, 1.0, 1.0], "mu_tr": [0.0, 0.0, 0.0]}
    v_e, p = X.cohort_values(rows, metas, "hit", ["hit"], {"hit": fit}, "etool", rm)
    v_c, _ = X.cohort_values(rows, metas, "hit", ["hit"], {"hit": fit}, "consensus", rm)
    v_p, _ = X.cohort_values(rows, metas, "hit", ["hit"], {"hit": fit}, "perm", rm,
                             rng=np.random.default_rng(X.PERM_SEED))
    g = p["hit"][0]
    assert np.allclose(v_c["hit"], g)
    assert np.allclose(np.sort(v_p["hit"] - g), np.sort(v_e["hit"] - g))
    assert not np.allclose(v_p["hit"], v_e["hit"])


def test_write_slots_leaves_an_unobserved_grade_alone():
    cfg = X.CONFIGS["E"]
    rows = [{"player_key": "a", "v2": {"tool_hit": 50.0}}, {"player_key": "b", "v2": {"tool_hit": 55.0}}]
    vals = {"hit": np.array([np.nan, 57.5]), "game_pwr": np.array([np.nan, 60.0])}
    out = X.write_slots(rows, "hit", cfg, [{}, {}], vals)
    assert out[0]["v2"]["tool_hit"] == 50.0 and out[0]["v2"]["scr_e5_pow_hit"] is None
    assert out[1]["v2"]["tool_hit"] == 57.5 and out[1]["v2"]["scr_e5_pow_hit"] == 60.0
    assert rows[1]["v2"]["tool_hit"] == 55.0                       # copies


def test_the_joint_fit_recovers_a_planted_etool_column():
    train = _attach_noise(_rows(years=range(2011, 2017), n=150), "hit")
    rng = np.random.default_rng(9)
    planted = [dict(r, v2=dict(r["v2"], scr_e5_pow_hit=float(r["target"]) + float(rng.normal(0, 0.3))))
               for r in train]
    sk = X.skill_candidates("hit", X.CONFIGS["E"])
    tm = RF.refit_candidates("hit", "timing", dark=True)
    lam = {"skill": 100.0, "timing": 100.0}
    with X.injected():
        m = RF.fit_heads(planted, "lv", planted, "lv", "hit", cands_skill=sk, cands_timing=tm,
                         timing_outcome_blind=True, absent_ok=False, lam=lam)
    beta = dict(zip(m["skill"]["keys"], m["skill"]["beta"]))
    assert beta["scr_e5_pow_hit"] > 0
    shuffled = [dict(r, v2=dict(r["v2"], scr_e5_pow_hit=planted[i]["v2"]["scr_e5_pow_hit"]))
                for r, i in zip(train, rng.permutation(len(train)))]
    with X.injected():
        m0 = RF.fit_heads(shuffled, "lv", shuffled, "lv", "hit", cands_skill=sk, cands_timing=tm,
                          timing_outcome_blind=True, absent_ok=False, lam=lam)
    beta0 = dict(zip(m0["skill"]["keys"], m0["skill"]["beta"]))
    assert beta0["scr_e5_pow_hit"] < 0.25 * beta["scr_e5_pow_hit"]


# ---------------------------------------------------------------------------
# 5. the configurations
# ---------------------------------------------------------------------------

def test_the_candidate_lists():
    for side in ("hit", "pit"):
        rt = X.skill_candidates(side, X.CONFIGS["RT"])
        assert rt == RF.refit_candidates(side, "skill", dark=True)
        e = X.skill_candidates(side, X.CONFIGS["E"])
        assert X.skill_candidates(side, X.CONFIGS["EC"]) == e == X.skill_candidates(side, X.CONFIGS["EP"])
        for s in X.SLOTS[side]:
            if s["kind"] == "column":
                assert s["replaces"] not in e and s["name"] in e
        ed = X.skill_candidates(side, X.CONFIGS["ED"])
        assert set(e) - set(ed) == set(X.DEDUPE[side]["columns"])
        assert len(e) == len(rt)
    assert [s["tool"] for s in X.slots_of("hit", X.CONFIGS["ES"])] == ["hit", "game_pwr", "speed"]
    assert [s["tool"] for s in X.slots_of("pit", X.CONFIGS["ES"])] == ["cmd", "fb"]


def test_the_v2_removal_and_the_injection_are_undone():
    with X.v2_removed("hit", ("contact",)):
        assert V3.base_config()["remove"]["hit"]["skill"] == ["contact"]
    assert V3.base_config()["remove"]["hit"]["skill"] == []
    with X.injected() as c:
        assert "e5_fb_pit" in c and "e5_fb_pit" in V5C.side_candidates("pit", "skill")
    assert "e5_fb_pit" not in V5C.candidates()
    assert not any(n.startswith("e5_") for n in V5C.side_candidates("hit") + V5C.side_candidates("pit"))


# ---------------------------------------------------------------------------
# 6. the ship rule
# ---------------------------------------------------------------------------

def _frames(d):
    out = {}
    for fid, n in (("lv_dev", 3000), ("vm_dev", 800)):
        deltas = {}
        for comp, v in d[fid].items():
            deltas[comp] = {"spearman": {"delta": v, "ci95": [v - 0.02, v + 0.02], "sd": 0.01}}
        out[fid] = {"n": n, "deltas": deltas}
    return out


def _d(e_rt, ed_rt, e_ec=0.01, e_ep=0.01):
    base = {}
    for fid in ("lv_dev", "vm_dev"):
        base[fid] = {"E_vs_RT": e_rt[fid], "ED_vs_RT": ed_rt[fid], "E_vs_prospx_consensus": 0.0,
                     "ED_vs_prospx_consensus": 0.0, "E_vs_EC": e_ec, "E_vs_EP": e_ep,
                     "ED_vs_EC": e_ec, "ED_vs_EP": e_ep}
    return _frames(base)


def test_the_ship_rule():
    s = X.ship_reading(_d({"lv_dev": 0.001, "vm_dev": 0.01}, {"lv_dev": -0.006, "vm_dev": 0.05}))
    assert s["candidates"]["E"]["passes"] and not s["candidates"]["ED"]["passes"]
    assert s["prepared"] == "E" and s["etool_gain"]
    s = X.ship_reading(_d({"lv_dev": 0.001, "vm_dev": 0.01}, {"lv_dev": 0.002, "vm_dev": 0.02}))
    assert s["prepared"] == "ED"
    s = X.ship_reading(_d({"lv_dev": -0.002, "vm_dev": 0.01}, {"lv_dev": -0.01, "vm_dev": 0.0},
                          e_ec=-0.001))
    assert s["candidates"]["E"]["passes"] and s["prepared"] == "E" and not s["etool_gain"]
    s = X.ship_reading(_d({"lv_dev": -0.001, "vm_dev": 0.0}, {"lv_dev": -0.001, "vm_dev": 0.0}))
    assert s["prepared"] is None and s["passing"] == []
    assert X.lower_bound({"delta": 0.01, "sd": 0.01}) == pytest.approx(0.01 - 0.016449, abs=1e-5)


# ---------------------------------------------------------------------------
# 7. gate compliance
# ---------------------------------------------------------------------------

def test_the_module_groups_nothing_by_consensus_fv_level():
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for bad in ("fv_cell", "fv_bucket", "by_fv", "fv_level", "fv_bin", "fv_stratum"):
        assert not any(bad in n.lower() for n in names), bad
    for ch in (chr(0x2014), chr(0x2013)):
        assert ch not in src
        assert ch not in DOC.read_text(encoding="utf-8")
        assert ch not in Path(__file__).read_text(encoding="utf-8")


def test_no_reserved_board_year_enters_the_etools_frame():
    assert not set(E.DEV_YEARS) & set(X.F.RESERVED_LV)
    assert max(E.DEV_YEARS) < X.F.R_VM_FIRST_DEBUT_YEAR
    assert X.MAX_TRAIL == 0.005 and X.PARITY_TOL == 1e-4
