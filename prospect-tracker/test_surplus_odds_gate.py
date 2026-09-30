# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""VAL_3 pins: the surplus-odds candidate (docs/efv-2026-09-25/SURPLUS_ODDS_GATE.md).

- value_framework prices a bucket mixture at a caller's odds with the bucket dollar
  values unchanged, and reproduces the plain distribution exactly without them;
- efv_score's flag defaults off and, on, makes the fan's bust share the served P(bust);
- V2 rows never hand odds to the re-price;
- the gate's scorer is pooled: no FV or tier stratum in its output or its artifact, and
  the module never calls backtest.run_backtest;
- the reserved frames are not read.
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import efv_odds_calibration as oc  # noqa: E402
import efv_score as S  # noqa: E402
import surplus_odds_gate as G  # noqa: E402
import value_framework as vf  # noqa: E402

CASES = [(55.0, False, "SS"), (62.0, False, "CF"), (48.0, True, "RHP"),
         (41.0, False, "C"), (38.0, True, "RP")]


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


@pytest.mark.parametrize("fv,ip,pos", CASES)
def test_curve_odds_reproduce_the_plain_distribution(fv, ip, pos):
    kw = {"age": 21.0, "eta_years": 1.0}
    plain = vf.sv_distribution(fv, ip, pos, **kw)
    same = vf.sv_distribution(fv, ip, pos, bucket_probs=vf.p_bucket_given_fv(fv, ip), **kw)
    assert plain == same
    assert vf.mixture_surplus_usd(fv, ip, pos, None, **kw) == vf.expected_surplus_usd(fv, ip, pos, **kw)
    assert vf.mixture_surplus_usd(fv, ip, pos, vf.p_bucket_given_fv(fv, ip), **kw) == \
        pytest.approx(vf.expected_surplus_usd(fv, ip, pos, **kw), rel=1e-12)


@pytest.mark.parametrize("fv,ip,pos", CASES)
def test_served_odds_make_one_object(fv, ip, pos):
    kw = {"age": 21.0, "eta_years": 1.0}
    odds = oc.recalibrate_bucket(vf.p_bucket_given_fv(fv - 8.0, ip), ip)
    d = vf.sv_distribution(fv, ip, pos, bucket_probs=odds, **kw)
    assert d["p_bust"] == pytest.approx(odds[0], abs=1e-4)
    assert d["mean"] == pytest.approx(vf.mixture_surplus_usd(fv, ip, pos, odds, **kw) / 1e6, abs=0.006)
    # bust mass >= 10 percent puts P10 on the bust atom ($0 raw)
    if odds[0] >= 0.105:
        assert d["percentiles"]["p10"] == 0.0
    # the bucket values are held: the candidate mean is the odds-weighted sum of them
    probs, eff_sv, _ = vf._mixture_bucket_values(fv, ip, pos, **kw)
    assert vf.mixture_surplus_usd(fv, ip, pos, odds, **kw) == \
        pytest.approx(sum(p * s for p, s in zip(odds, eff_sv)), rel=1e-12)


def test_bucket_probs_are_validated():
    for bad in ([0.2] * 4, [0.5, 0.5, -0.1, 0.05, 0.05], [0, 0, 0, 0, 0], [float("nan")] * 5):
        with pytest.raises(ValueError):
            vf.mixture_surplus_usd(50.0, False, "SS", bad)


def test_flag_defaults_off_and_env_toggles(monkeypatch):
    assert S.SURPLUS_FROM_SERVED_ODDS_DEFAULT is False
    monkeypatch.delenv("EEPHUS_SURPLUS_FROM_SERVED_ODDS", raising=False)
    assert S._surplus_odds_flag() is False
    monkeypatch.setenv("EEPHUS_SURPLUS_FROM_SERVED_ODDS", "1")
    assert S._surplus_odds_flag() is True
    monkeypatch.setenv("EEPHUS_SURPLUS_FROM_SERVED_ODDS", "0")
    assert S._surplus_odds_flag() is False


def _row(odds):
    return {"xfv_grade_display": 62.0, "p_bust": round(odds[0], 3),
            "dist": {"p_bust": round(odds[0], 3)}}


def test_reprice_ignores_odds_with_the_flag_off(monkeypatch):
    monkeypatch.setenv("EEPHUS_SURPLUS_FROM_SERVED_ODDS", "0")
    odds = oc.recalibrate_bucket(vf.p_bucket_given_fv(50.0, False), False)
    a, b = _row(odds), _row(odds)
    S._reprice_surplus_on_display(a, False, "SS", age=21.0, eta=1.0)
    S._reprice_surplus_on_display(b, False, "SS", age=21.0, eta=1.0, odds=odds)
    assert a == b


def test_reprice_with_the_flag_on_prices_from_the_served_odds(monkeypatch):
    monkeypatch.setenv("EEPHUS_SURPLUS_FROM_SERVED_ODDS", "1")
    odds = oc.recalibrate_bucket(vf.p_bucket_given_fv(50.0, False), False)
    assert odds[0] > 0.3
    inc, cand = _row(odds), _row(odds)
    S._reprice_surplus_on_display(inc, False, "SS", age=21.0, eta=1.0)
    S._reprice_surplus_on_display(cand, False, "SS", age=21.0, eta=1.0, odds=odds)
    kw = {"age": 21.0, "eta_years": 1.0}
    want = vf.apply_calibration(vf.mixture_surplus_usd(62.0, False, "SS", odds, **kw) / 1e6)
    assert cand["surplus_mm"] == round(want, 1)
    assert cand["surplus_mm"] < inc["surplus_mm"]
    # P(bust) is untouched, and the fan's low end sits on the served bust floor
    assert cand["p_bust"] == inc["p_bust"] == cand["dist"]["p_bust"]
    floor = round(vf.apply_calibration(0.0), 1)
    assert cand["dist"]["p10_mm"] == floor and cand["dist"]["p25_mm"] == floor
    assert inc["dist"]["p10_mm"] > floor


def test_only_the_three_platt_seams_pass_odds():
    src = inspect.getsource(S)
    tree = ast.parse(src)
    callers = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and getattr(sub.func, "id", None)
                        == "_reprice_surplus_on_display"):
                    callers.append((node.name, any(k.arg == "odds" for k in sub.keywords)))
    with_odds = sorted(n for n, has in callers if has)
    assert with_odds == ["run", "run_backgrade", "run_live"]
    assert ("_v2_entry", False) in callers


def test_calibrate_mm_matches_the_served_map():
    xs = np.linspace(-5.0, 700.0, 1413)
    got = G.calibrate_mm(xs)
    want = np.array([vf.apply_calibration(float(x)) for x in xs])
    assert np.allclose(got, want, atol=1e-9)


def test_randomized_pit_atom_and_continuous():
    floor = 1.0
    d = np.array([1.0] * 30 + list(np.linspace(2.0, 71.0, 70)))
    # at or below the floor: the bust event, PIT = u * F(floor)
    assert G.randomized_pit(d, 0.0, 0.5, floor) == pytest.approx(0.15)
    assert G.randomized_pit(d, -3.0, 1.0, floor) == pytest.approx(0.30)
    # strictly inside the continuous part: F(y-) + u * (F(y) - F(y-)), no atom at y
    assert G.randomized_pit(d, 2.5, 0.9, floor) == pytest.approx(0.31)
    assert G.randomized_pit(d, 1000.0, 0.2, floor) == pytest.approx(1.0)


def test_calibration_metrics_is_pooled_and_correct():
    rng = np.random.RandomState(3)
    p = rng.uniform(0, 50, 2000)
    r = p + rng.normal(0, 1, 2000)
    pit = rng.uniform(0, 1, 2000)
    m = G.calibration_metrics(p, r, pit)
    assert set(m) == {"n", "bias_mm", "slope", "intercept_mm", "pit_coverage", "pit_ks_stat"}
    assert not any("fv" in k.lower() or "tier" in k.lower() for k in m)
    assert m["slope"] == pytest.approx(1.0, abs=0.01)
    assert abs(m["bias_mm"]) < 0.1
    assert m["pit_coverage"] == pytest.approx(0.80, abs=0.03)


def test_verdict_rule():
    inc = {"pit_coverage": 0.60, "bias_mm": -3.0, "slope": 0.8}
    cand = {"pit_coverage": 0.75, "bias_mm": -2.0, "slope": 0.85}
    boot = {"D_cov": {"ci95": [0.05, 0.2]}, "H_bias": {"ci95": [-2.0, 0.5]},
            "H_slope": {"ci95": [-0.1, 0.02]}}
    assert G.verdict(inc, cand, boot, one_object_ok=True, n=500)["verdict"] == "PASS"
    boot["D_cov"]["ci95"] = [-0.01, 0.2]
    assert G.verdict(inc, cand, boot, one_object_ok=True, n=500)["verdict"] == "FAIL"
    boot["D_cov"]["ci95"] = [0.05, 0.2]
    boot["H_bias"]["ci95"] = [0.1, 0.9]
    assert G.verdict(inc, cand, boot, one_object_ok=True, n=500)["verdict"] == "FAIL"
    assert G.verdict(inc, cand, boot, one_object_ok=True, n=100)["verdict"] == "UNPOWERED"
    assert G.verdict(inc, cand, boot, one_object_ok=False, n=500)["verdict"] == "STOPPED"


def test_bootstrap_is_player_clustered_and_seeded():
    keys = ["a", "a", "b", "c", "d", "e"] * 20
    rng = np.random.RandomState(0)
    r = rng.uniform(0, 10, len(keys))
    args = (keys, r, r + 1.0, rng.uniform(size=len(keys)), r + 0.5, rng.uniform(size=len(keys)))
    b1 = G.paired_bootstrap(*args, b=50)
    b2 = G.paired_bootstrap(*args, b=50)
    assert b1 == b2
    assert b1["clusters"] == 5


def test_module_never_calls_run_backtest():
    tree = ast.parse(Path(G.__file__).read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    for banned in ("run_backtest", "_by_tier_metrics", "by_fv_tier", "fit_surplus_calibration"):
        assert banned not in names and banned not in imported


def test_reserved_frames_are_not_read():
    import efv_vintage_frame as F
    assert max(G.GATE_YEARS) < min(F.RESERVED_LV)
    assert max(G.GATE_YEARS) < F.R_VM_FIRST_DEBUT_YEAR
    G.assert_reserved_frames_untouched()
    with pytest.raises(Exception):
        G.assert_reserved_frames_untouched((2020,))


def test_artifact_has_no_fv_or_tier_stratum():
    art = ROOT / "data" / "surplus_backtest_real.json"
    if not art.exists():
        pytest.skip("the parent artifact is not generated on this machine")
    doc = json.loads(art.read_text(encoding="utf-8")).get(G.BLOCK_KEY)
    if doc is None:
        pytest.skip("the one read has not run")
    bad = [k for k in _keys(doc) if "fv" in k.lower() or "tier" in k.lower()]
    assert bad == []
    assert doc["gate_doc"] == G.GATE_DOC
    assert doc["frame"]["decision_years"] == list(G.GATE_YEARS)


def test_block_persists_beside_the_parent_keys(tmp_path):
    p = tmp_path / "parent.json"
    p.write_text(json.dumps({"accounting": {"scored": 1}}), encoding="utf-8")
    G.persist_block({"n": 3}, path=p)
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc == {"accounting": {"scored": 1}, G.BLOCK_KEY: {"n": 3}}


def test_parent_writer_carries_the_block_over():
    import surplus_backtest_real as sbr
    assert G.BLOCK_KEY in sbr.CARRIED_BLOCKS
    # the harness mirrors the gate's path, so compare the file each module names
    assert G.OUT_PATH.name == sbr.OUT_PATH.name == "surplus_backtest_real.json"
