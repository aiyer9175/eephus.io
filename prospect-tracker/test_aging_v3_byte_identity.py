"""aging v3 byte identity (docs/AGING_V3_GATE.md section 12; task
AG_5_AGING_SERVICE_BUILD_DARK): with every consumer flag false, every door's
default equals its explicit aging="v2" call and matches the goldens recorded at
the build (contract_war_path, _trajectory_shape, prospect_prime_path,
prospect_peak_war, _aging_factor); proj_ml.build_features is byte-identical
between the v2 curves and the dark v3 curves; proj_ml and proj_eval pass
aging="v2" explicitly (source pin).

The exporter check (data/mlb_projections.json, data/fa_class.json and
data/trade_values.json byte-identical to a reference run of the pre-change
code) runs only when EEPHUS_AGING_V3_REF_DIR names a directory holding the
reference copies (pre_mlb_projections.json, pre_fa_class.json,
pre_trade_values.json): it re-runs the three exporters into data/ and compares
them with `generated_at` masked. The record of the build's own run is in the
task's FIX_REPORT; the default session never runs an exporter.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import aging_v3 as A
import bayes_trade_value as btv
import fa_market as fm
import fa_projection as fp
import proj_ml
import value_framework as vf
from test_aging_v3 import make_corpus

ROOT = Path(__file__).resolve().parent

# Recorded at the build (2026-10-09) from the config-driven incumbent code with
# every flag false. They are the v2 outputs; a change here is a changed served
# number and needs the flip's own commit.
GOLDENS = {'factor': {'22.0|0|False|SS': 1.1,
            '22.0|3|False|SS': 1.05,
            '25.0|2|True|RHP': 0.86,
            '27.0|3|False|C': 0.55,
            '31.0|4|False|C': 0.2,
            '33.0|5|True|SP': 0.25,
            'None|2|False|OF': 1.0},
 'peak': {'45|False|None': 1.1, '50|True|24.0': 2.0, '55|False|21.0': 2.6, '60|False|26.5': 3.7},
 'prime': {'45|False|None|False': {'mean': [0.9058823529411766,
                                            1.075735294117647,
                                            1.1889705882352941,
                                            1.2455882352941179,
                                            1.2455882352941179,
                                            1.1323529411764706,
                                            0.9058823529411766],
                                   'p10': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                                   'p90': [2.039439867037805,
                                           2.421834842107393,
                                           2.676764825487119,
                                           2.804229817176982,
                                           2.804229817176982,
                                           2.549299833797256,
                                           2.039439867037805],
                                   'peak': 1.1},
           '50|True|24.0|False': {'mean': [1.9329949238578679,
                                           2.0135363790186127,
                                           1.8725888324873095,
                                           1.7316412859560066,
                                           1.5906937394247038,
                                           1.449746192893401,
                                           1.3087986463620982],
                                  'p10': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                                  'p90': [4.785161866955382,
                                          4.984543611411857,
                                          4.635625558613026,
                                          4.286707505814196,
                                          3.9377894530153665,
                                          3.5888714002165365,
                                          3.2399533474177065],
                                  'peak': 2.0},
           '50|True|24.0|True': {'mean': [0.6234957289887306,
                                          0.6494747176965946,
                                          0.6040114874578327,
                                          0.5585482572190711,
                                          0.5130850269803097,
                                          0.467621796741548,
                                          0.4221585665027864],
                                 'p10': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                                 'p90': [1.555177606760499,
                                         1.6199766737088535,
                                         1.5065783065492333,
                                         1.3931799393896136,
                                         1.2797815722299941,
                                         1.1663832050703744,
                                         1.0529848379107545],
                                 'peak': 2.0},
           '55|False|21.0|False': {'mean': [1.9863636363636363,
                                            2.090909090909091,
                                            2.1954545454545453,
                                            2.3,
                                            2.4045454545454543,
                                            2.509090909090909,
                                            2.6136363636363638],
                                   'p10': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                                   'p90': [3.072276641648163,
                                           3.2339754122612248,
                                           3.3956741828742856,
                                           3.557372953487347,
                                           3.719071724100408,
                                           3.880770494713469,
                                           4.042469265326531],
                                   'peak': 2.6},
           '60|False|26.5|False': {'mean': [3.5979020979020975,
                                            3.5428321678321675,
                                            3.285839160839161,
                                            3.0288461538461533,
                                            2.7718531468531467,
                                            2.5148601398601396,
                                            2.257867132867133],
                                   'p10': [1.3357018551033808,
                                           1.3152574389538394,
                                           1.2198501635893122,
                                           1.1244428882247848,
                                           1.0290356128602578,
                                           0.9336283374957305,
                                           0.8382210621312034],
                                   'p90': [6.678509275516904,
                                           6.576287194769197,
                                           6.099250817946562,
                                           5.6222144411239245,
                                           5.145178064301289,
                                           4.668141687478653,
                                           4.191105310656017],
                                   'peak': 3.7}},
 'traj': {'hitter|20.0|None': [0.8571428571428571,
                               0.9047619047619048,
                               0.9523809523809524,
                               1.0,
                               1.0476190476190477,
                               1.0952380952380953,
                               1.1428571428571428],
          'hitter|22.5|None': [0.9025157232704403,
                               0.9465408805031447,
                               0.9905660377358491,
                               1.0345911949685533,
                               1.0786163522012577,
                               1.0621069182389937,
                               0.985062893081761],
          'hitter|25.0|None': [1.0420711974110033,
                               1.087378640776699,
                               1.132686084142395,
                               1.0533980582524272,
                               0.9741100323624596,
                               0.894822006472492,
                               0.8155339805825244],
          'hitter|28.0|None': [1.2916666666666665,
                               1.1944444444444444,
                               1.0972222222222223,
                               1.0,
                               0.9027777777777777,
                               0.8055555555555556,
                               0.7083333333333334],
          'pitcher|20.0|None': [0.8846761453396526,
                                0.9289099526066351,
                                0.9731437598736178,
                                1.0173775671406005,
                                1.061611374407583,
                                1.1058451816745656,
                                1.028436018957346],
          'pitcher|22.5|None': [1.0063897763578276,
                                1.0511182108626198,
                                1.0958466453674123,
                                1.079073482428115,
                                1.0007987220447285,
                                0.9225239616613419,
                                0.8442492012779553],
          'pitcher|25.0|None': [1.2658227848101267,
                                1.1772151898734178,
                                1.0886075949367089,
                                1.0000000000000002,
                                0.9113924050632912,
                                0.8227848101265822,
                                0.7341772151898734],
          'pitcher|28.0|None': [1.3620689655172415,
                                1.2413793103448276,
                                1.1206896551724137,
                                1.0,
                                0.8793103448275863,
                                0.7586206896551724,
                                0.6379310344827585]},
 'traj_none': {'hitter': [0.8235294117647058,
                          0.9779411764705881,
                          1.0808823529411764,
                          1.1323529411764706,
                          1.1323529411764706,
                          1.0294117647058822,
                          0.8235294117647058],
               'pitcher': [0.8235294117647058,
                           0.9779411764705881,
                           1.0808823529411764,
                           1.1323529411764706,
                           1.1323529411764706,
                           1.0294117647058822,
                           0.8235294117647058]}}


def _key(*parts):
    return "|".join(str(p) for p in parts)


# ---------------------------------------------------------------------------
# the consumer doors: default == explicit v2 == golden
# ---------------------------------------------------------------------------

def test_every_consumer_flag_is_false():
    for c in A.CONSUMERS:
        assert A.consumer_aging(c) == "v2", c
    assert A.health_enabled() is False


def test_trajectory_shape_golden_and_default_is_v2():
    for role in ("hitter", "pitcher"):
        for age in (20.0, 22.5, 25.0, 28.0):
            got = vf._trajectory_shape(role, age, None)
            assert got == GOLDENS["traj"][_key(role, age, None)], (role, age)
            assert got == vf._trajectory_shape(role, age, None, aging="v2")
            assert got == vf._trajectory_shape(role, age, None, aging="v2", bucket="SS", reliever=True)
        assert vf._trajectory_shape(role, None, None) == GOLDENS["traj_none"][role]
        assert vf._trajectory_shape(role, None, None) == vf._trajectory_shape(role, None, None, aging="v2")


def test_prospect_prime_path_golden_and_default_is_v2():
    for fv, p, age, rel in ((55, False, 21.0, False), (50, True, 24.0, False), (50, True, 24.0, True),
                            (60, False, 26.5, False), (45, False, None, False)):
        got = vf.prospect_prime_path(fv, p, age, rel)
        assert got == GOLDENS["prime"][_key(fv, p, age, rel)], (fv, p, age, rel)
        assert got == vf.prospect_prime_path(fv, p, age, rel, aging="v2")
        assert got == vf.prospect_prime_path(fv, p, age, rel, aging="v2", bucket="CF")


def test_prospect_peak_war_golden_and_default_is_v2():
    for fv, p, age in ((55, False, 21.0), (50, True, 24.0), (60, False, 26.5), (45, False, None)):
        got = vf.prospect_peak_war(fv, p, age)
        assert got == GOLDENS["peak"][_key(fv, p, age)], (fv, p, age)
        assert got == vf.prospect_peak_war(fv, p, age, aging="v2")
        assert got == vf.prospect_peak_war(fv, p, age, aging="v2", bucket="1B")


def test_aging_factor_golden_and_default_is_v2(monkeypatch):
    # the goldens are the v2 tent as built; TRADE_AGING_PREPEAK_FIX
    # (test_trade_aging_factor.py) owns the pre-peak branch, so pin it off here
    monkeypatch.setattr(btv, "TRADE_AGING_PREPEAK_FIX", False)
    for a, k, p, pos in ((22.0, 0, False, "SS"), (22.0, 3, False, "SS"), (27.0, 3, False, "C"),
                         (31.0, 4, False, "C"), (25.0, 2, True, "RHP"), (33.0, 5, True, "SP"),
                         (None, 2, False, "OF")):
        got = btv._aging_factor(a, k, p, pos)
        assert got == GOLDENS["factor"][_key(a, k, p, pos)], (a, k, p, pos)
        assert got == btv._aging_factor(a, k, p, pos, aging="v2")
    with pytest.raises(ValueError):
        btv._aging_factor(27.0, 1, False, "SS", aging="v9")


def test_v3_doors_raise_without_a_served_model(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "SERVED_CURVES_PATH", tmp_path / "absent.json")
    A.set_served_model(None)
    with pytest.raises(A.AgingV3Unavailable):
        vf._trajectory_shape("hitter", 22.0, None, aging="v3")
    with pytest.raises(A.AgingV3Unavailable):
        vf.prospect_peak_war(55, False, 21.0, aging="v3")
    with pytest.raises(A.AgingV3Unavailable):
        btv._aging_factor(27.0, 1, False, "SS", aging="v3")
    assert not (ROOT / "data" / "aging_v3_curves.json").exists(), \
        "the served fit exists before any flip: docs/AGING_V3_GATE.md section 16"


# ---------------------------------------------------------------------------
# the engine doors on a fixture corpus: v2 default == explicit v2 == dark v3
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fits(tmp_path_factory):
    corpus = make_corpus()
    d = tmp_path_factory.mktemp("aging_v3_cache")
    saved = (fp.CACHE_DIR, A.CACHE_DIR)
    fp.CACHE_DIR = d
    A.CACHE_DIR = d
    try:
        c2, w2 = fp.fitted_models(corpus, 2014, use_cache=False)
        c3, w3 = fp.fitted_models(corpus, 2014, use_cache=False, aging="v3")
    finally:
        fp.CACHE_DIR, A.CACHE_DIR = saved
    return corpus, c2, w2, c3, w3


def _histories(corpus, base):
    out = {"hit": [], "pit": []}
    for side in ("hit", "pit"):
        by = {}
        for r in corpus[side]:
            by.setdefault(r["mlbam"], {})[r["season"]] = r
        for mlbam, seasons in by.items():
            hist = [seasons[s] for s in (base - 1, base - 2, base - 3) if s in seasons]
            if hist and hist[0]["season"] == base - 1:
                out[side].append(hist)
    return out


def test_contract_war_path_default_is_v2_and_dark_v3_is_identical(fits):
    corpus, c2, w2, c3, w3 = fits
    league = corpus["league"]
    n = 0
    sha_default = hashlib.sha256()
    for side, hists in _histories(corpus, 2015).items():
        for hist in hists:
            age = proj_ml.age_from_history(hist, 2015)
            if age is None:
                continue
            p_def = fm.contract_war_path(hist, side, 2015, 10, age, c2, w2, league, use_ml=False)
            p_v2 = fm.contract_war_path(hist, side, 2015, 10, age, c2, w2, league, use_ml=False, aging="v2")
            p_v3 = fm.contract_war_path(hist, side, 2015, 10, age, c3, w3, league, use_ml=False, aging="v3")
            assert p_def == p_v2 == p_v3, (side, hist[0]["mlbam"])
            sha_default.update(json.dumps(p_def, sort_keys=True).encode())
            n += 1
    assert n >= 100
    with pytest.raises(ValueError):
        fm._decay_path(2.0, 600.0, "hit", "H", 27, c2, aging="v3")       # v2 curves carry no model
    with pytest.raises(ValueError):
        fm._decay_path(2.0, 600.0, "hit", "H", 27, c2, aging="v1")


def test_decay_path_default_is_v2(fits):
    corpus, c2, w2, c3, w3 = fits
    for side, role in (("hit", "H"), ("hit", "C"), ("pit", "SP"), ("pit", "RP"), ("pit", "SP|pwr")):
        for age in (22, 27, 33):
            for war1, expo in ((3.0, 650.0), (0.4, 120.0), (-0.5, 300.0)):
                d = fm._decay_path(war1, expo, side, role, age, c2)
                assert d == fm._decay_path(war1, expo, side, role, age, c2, aging="v2")
                assert d == fm._decay_path(war1, expo, side, role, age, c3, aging="v3")
                assert len(d) == fm.MAX_PATH_YEARS


def test_build_features_byte_identical_between_v2_and_dark_v3(fits):
    corpus, c2, w2, c3, w3 = fits
    league = corpus["league"]
    n = 0
    for side, hists in _histories(corpus, 2015).items():
        for hist in hists[:120]:
            age = proj_ml.age_from_history(hist, 2015)
            if age is None:
                continue
            f2 = proj_ml.build_features(hist, side, 2015, age, c2, w2, league)
            f3 = proj_ml.build_features(hist, side, 2015, age, c3, w3, league)
            assert json.dumps(f2) == json.dumps(f3)
            n += 1
    assert n >= 50


def test_project_player_year1_pt_identical_under_dark_v3(fits):
    corpus, c2, w2, c3, w3 = fits
    league = corpus["league"]
    for side, hists in _histories(corpus, 2015).items():
        for hist in hists[:150]:
            age = proj_ml.age_from_history(hist, 2015)
            p2 = fp.project_player(hist, side, 2015, c2, league, age)
            p3 = fp.project_player(hist, side, 2015, c3, league, age)
            assert p2 == p3


# ---------------------------------------------------------------------------
# source pins
# ---------------------------------------------------------------------------

def test_proj_ml_and_proj_eval_pass_aging_v2_explicitly():
    ml = (ROOT / "proj_ml.py").read_text(encoding="utf-8")
    ev = (ROOT / "proj_eval.py").read_text(encoding="utf-8")
    assert re.search(r"contract_war_path\([^)]*use_ml=False,\s*aging=\"v2\"\)", ml)
    assert re.search(r"fitted_models\(corpus, base - 1, aging=\"v2\"\)", ml)
    assert re.search(r"contract_war_path\([^)]*use_ml=False,\s*aging=\"v2\"\)", ev)
    assert ev.count("fitted_models(corpus, B - 1, aging=\"v2\")") == 2
    # the selectors default to "v2" and are call-scoped (no module global)
    import inspect
    assert inspect.signature(fp.fitted_models).parameters["aging"].default == "v2"
    assert inspect.signature(fm.contract_war_path).parameters["aging"].default == "v2"
    assert inspect.signature(fm._decay_path).parameters["aging"].default == "v2"
    assert inspect.signature(vf._trajectory_shape).parameters["aging"].default == "v2"
    assert inspect.signature(vf.prospect_prime_path).parameters["aging"].default == "v2"
    assert inspect.signature(vf.prospect_peak_war).parameters["aging"].default == "v2"
    assert inspect.signature(btv._aging_factor).parameters["aging"].default == "v2"
    for mod in (fp, fm, vf, btv, proj_ml):
        assert not any(k.upper().startswith("AGING_ENGINE") for k in vars(mod)), mod.__name__


def test_incumbent_cache_name_is_unchanged():
    src = (ROOT / "fa_projection.py").read_text(encoding="utf-8")
    assert 'f"fa_fits_{max_season}_{corpus[\'first\']}_{corpus[\'last\']}"' in src
    assert 'f"_{_corpus_sig(corpus)}{_suffix}.pkl"' in src


# ---------------------------------------------------------------------------
# the exporters, on request only
# ---------------------------------------------------------------------------

def _masked(raw: bytes) -> bytes:
    return re.sub(rb'"generated_at":\s*"[^"]*"', b'"generated_at":"X"', raw, count=1)


@pytest.mark.skipif(not os.environ.get("EEPHUS_AGING_V3_REF_DIR"),
                    reason="set EEPHUS_AGING_V3_REF_DIR to a directory of pre_*.json reference exports")
def test_exporters_byte_identical_to_the_reference_run():
    ref = Path(os.environ["EEPHUS_AGING_V3_REF_DIR"])
    env = dict(os.environ)
    for cmd in (["python", "proj_export.py"], ["python", "tools/export_trade_values.py"],
                ["python", "fa_export.py"]):
        subprocess.run(cmd, cwd=ROOT, env=env, check=True, capture_output=True)
    for name in ("mlb_projections.json", "fa_class.json", "trade_values.json"):
        got = _masked((ROOT / "data" / name).read_bytes())
        want = _masked((ref / f"pre_{name}").read_bytes())
        assert hashlib.sha256(got).hexdigest() == hashlib.sha256(want).hexdigest(), name
