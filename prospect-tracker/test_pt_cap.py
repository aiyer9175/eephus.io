"""The veteran playing-time cap (task AG_4_CHAMPION_PT_CAP, owner answer AG-Q5).

fa_market._decay_path added the pool-average PT delta at every age with no
ceiling, so a 22-year-old 650-PA regular walked to about 800 PA by 26. The fit
now stores meta["pt_cap"] (the 99.5th percentile of single-season exposure by
side and base role over corpus rows with season <= max_season), and a
CALL-SCOPED pt_cap argument (None reads projection.pt_cap_enabled, an explicit
value wins) clamps exposure in the year-1 PT and every decay step.

Pinned here: the fitted cap; exposure never above it on a fixture 21-year-old;
flag off, contract_war_path for 30 fixture players matches the goldens recorded
from the pre-change code; the cache suffix; the ML feature vector byte-identical
with the flag on (train/serve parity with the shipped bundle); the explicit
pt_cap=False at the fantasy, hitter and FA Fit call sites; and the FA Fit field
(byYear[].winsFaFit) equal to the uncapped frame's wins.

The exporter check (data/fa_class.json byte-identical between two fa_export runs
that differ only in the Team Outlook input) runs only when EEPHUS_PT_CAP_FA_REF
names a directory holding fa_class_a.json and fa_class_b.json from those two
runs; the record of the run is in the task's FIX_REPORT.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np
import pytest

import fa_class
import fa_fit
import fa_market as fm
import fa_projection as fp
import proj_ml
from test_aging_v3 import make_corpus

ROOT = Path(__file__).resolve().parent

# contract_war_path(hist, side, 2015, 10, age, ..., use_ml=False) for the first
# 15 hitters and 15 pitchers (by mlbam) of make_corpus() with a 2014 base season,
# sha256 of json.dumps([[side, mlbam, path], ...], sort_keys=True). Recorded on
# 2026-10-21 from the pre-change code (HEAD e3e8e432) and reproduced by the
# changed code with the flag off.
GOLDEN_SHA = "f32e65ddd104d548b7315e3a0fbf1eed6f76631575a66bc0e0a02096bd28a612"
GOLDEN_WAR_TOTAL = {
    "hit:100004": 15.22, "hit:100006": 4.49, "hit:100007": 9.59, "hit:100009": 6.09,
    "hit:100010": 12.8, "hit:100014": 1.13, "hit:100016": 14.33, "hit:100018": 7.26,
    "hit:100019": 4.74, "hit:100023": 5.47, "hit:100026": 6.07, "hit:100028": 21.58,
    "hit:100030": 2.04, "hit:100034": 10.93, "hit:100035": 9.17, "pit:100261": 43.52,
    "pit:100263": 13.09, "pit:100266": 23.33, "pit:100267": 8.58, "pit:100269": 46.02,
    "pit:100270": 16.18, "pit:100271": 6.41, "pit:100273": 23.1, "pit:100275": 8.73,
    "pit:100279": 5.77, "pit:100284": 24.46, "pit:100285": 23.5, "pit:100288": 26.44,
    "pit:100290": 4.8, "pit:100293": 20.66}


@pytest.fixture(scope="module")
def fits(tmp_path_factory):
    corpus = make_corpus()
    d = tmp_path_factory.mktemp("pt_cap_cache")
    saved = fp.CACHE_DIR
    fp.CACHE_DIR = d
    try:
        curves, war_map = fp.fitted_models(corpus, 2014, use_cache=False)
    finally:
        fp.CACHE_DIR = saved
    return corpus, curves, war_map


def _flag(monkeypatch, on: bool):
    cfg = copy.deepcopy(fa_class.get_config())
    cfg["projection"]["pt_cap_enabled"] = on
    monkeypatch.setattr(fa_class, "get_config", lambda *a, **k: cfg)


def _players(corpus, n_side=15):
    out = []
    for side in ("hit", "pit"):
        by = {}
        for r in corpus[side]:
            by.setdefault(r["mlbam"], {})[r["season"]] = r
        n = 0
        for mlbam in sorted(by):
            seasons = by[mlbam]
            hist = [seasons[s] for s in (2014, 2013, 2012) if s in seasons]
            if not hist or hist[0]["season"] != 2014:
                continue
            age = proj_ml.age_from_history(hist, 2015)
            if age is None:
                continue
            out.append((side, mlbam, hist, age))
            n += 1
            if n == n_side:
                break
    return out


def test_config_flag_ships_off():
    assert fa_class.get_config()["projection"]["pt_cap_enabled"] is False
    assert fp._pt_cap_on() is False
    assert fp._pt_cap_on(True) is True


def test_fit_stores_the_995th_percentile_by_side_and_base_role(fits):
    corpus, curves, _ = fits
    cap = curves["meta"]["pt_cap"]
    assert set(cap) == {"hit", "pit"}
    assert set(cap["hit"]) == {"C", "H"} and set(cap["pit"]) == {"SP", "RP"}
    for side, key, roles in (("hit", "pa", ("C", "H")), ("pit", "bf", ("SP", "RP"))):
        for role in roles:
            v = [r[key] for r in corpus[side]
                 if r["season"] <= 2014 and (r.get(key) or 0) > 0
                 and fp._pt_cap_base_role(side, r["role"]) == role]
            assert cap[side][role] == round(float(np.percentile(v, 99.5)), 1)
    # profile-extended roles read their base role's cap
    assert fp.pt_cap_value(curves, "pit", "SP|fin") == cap["pit"]["SP"]
    assert fp.pt_cap_value(curves, "hit", "H|pwr") == cap["hit"]["H"]


def test_a_capped_call_on_curves_without_the_cap_raises():
    with pytest.raises(ValueError):
        fp.pt_cap_value({"meta": {}}, "hit", "H")
    with pytest.raises(ValueError):
        fm._decay_path(3.0, 650.0, "hit", "H", 22, {"meta": {}}, pt_cap=True)


def _flat_rate(curves):
    """The fixture curves with every war_rate delta zeroed, so a decay path's
    WAR is proportional to its exposure and the exposure can be read back."""
    c = copy.deepcopy(curves)
    for side in ("hit", "pit"):
        for role, comps in c[side].items():
            for cell in (comps.get("war_rate") or {}).values():
                cell["delta"] = 0.0
                cell["delta_smooth"] = 0.0
    return c


@pytest.mark.parametrize("side,role", [("hit", "H"), ("hit", "C"), ("pit", "SP"), ("pit", "RP")])
def test_exposure_never_above_the_cap_on_a_21_year_old(fits, side, role):
    _, curves, _ = fits
    flat = _flat_rate(curves)
    cap = fp.pt_cap_value(curves, side, role)
    expo = cap - 5.0
    war1 = 3.0
    for capped in (True, False):
        path = fm._decay_path(war1, expo, side, role, 21, flat, pt_cap=capped)
        exp = [w / path[0] * expo for w in path]
        if capped:
            assert max(exp) <= cap + 1e-6, (side, role, max(exp), cap)
        else:
            # the uncapped walk does pass the cap, so the test bites
            assert max(exp) > cap, (side, role)


def test_year1_pt_never_above_the_cap(fits):
    corpus, curves, _ = fits
    league = corpus["league"]
    for side, key in (("hit", "pa"), ("pit", "bf")):
        for role in (("H", "C") if side == "hit" else ("SP", "RP")):
            cap = fp.pt_cap_value(curves, side, role)
            big = cap * 1.6
            hist = []
            for k, s in enumerate((2014, 2013, 2012)):
                r = dict(next(r for r in corpus[side] if r["season"] == s))
                r.update({"season": s, "age": 20 - k, "role": role, key: big, "mlbam": -1})
                if side == "pit":
                    r["ip"] = round(big / 4.3, 1)
                hist.append(r)
            off = fp.project_player(hist, side, 2015, curves, league, 21, pt_cap=False)
            on = fp.project_player(hist, side, 2015, curves, league, 21, pt_cap=True)
            assert off["pt_proj"] > cap
            assert on["pt_proj"] <= cap
            if side == "pit":
                assert on["ip_proj"] <= round(cap / 4.3, 1)


def test_flag_off_contract_war_path_matches_the_pre_change_goldens(fits):
    corpus, curves, war_map = fits
    league = corpus["league"]
    out, tot = [], {}
    for side, mlbam, hist, age in _players(corpus):
        p = fm.contract_war_path(hist, side, 2015, 10, age, curves, war_map, league, use_ml=False)
        assert p == fm.contract_war_path(hist, side, 2015, 10, age, curves, war_map, league,
                                         use_ml=False, pt_cap=False)
        out.append([side, mlbam, p])
        tot[f"{side}:{mlbam}"] = p["war_total"]
    assert len(out) == 30
    assert tot == GOLDEN_WAR_TOTAL
    assert hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest() == GOLDEN_SHA


def test_config_on_equals_explicit_true_and_explicit_false_wins(fits, monkeypatch):
    corpus, curves, war_map = fits
    league = corpus["league"]
    _flag(monkeypatch, True)
    for side, mlbam, hist, age in _players(corpus):
        d = fm.contract_war_path(hist, side, 2015, 10, age, curves, war_map, league, use_ml=False)
        t = fm.contract_war_path(hist, side, 2015, 10, age, curves, war_map, league,
                                 use_ml=False, pt_cap=True)
        f = fm.contract_war_path(hist, side, 2015, 10, age, curves, war_map, league,
                                 use_ml=False, pt_cap=False)
        assert d == t
        assert f["war_total"] == GOLDEN_WAR_TOTAL[f"{side}:{mlbam}"]


def test_cache_suffix_only_when_on(fits, tmp_path, monkeypatch):
    corpus = make_corpus(n_hit=40, n_pit=40)
    monkeypatch.setattr(fp, "CACHE_DIR", tmp_path)
    fp.fitted_models(corpus, 2014)
    fp.fitted_models(corpus, 2014, pt_cap=True)
    names = sorted(p.name for p in tmp_path.glob("fa_fits_*.pkl"))
    assert len(names) == 2
    assert sum(n.endswith("_ptcap1.pkl") for n in names) == 1
    src = (ROOT / "fa_projection.py").read_text(encoding="utf-8")
    assert 'f"fa_fits_{max_season}_{corpus[\'first\']}_{corpus[\'last\']}"' in src
    assert '_suffix += "_ptcap1"' in src


def test_ml_feature_vector_byte_identical_with_the_flag_on(fits, monkeypatch):
    corpus, curves, war_map = fits
    league = corpus["league"]
    players = _players(corpus)
    off = [proj_ml.build_features(h, s, 2015, a, curves, war_map, league)
           for s, _, h, a in players]
    # the live dispatch: contract_war_path hands build_features the champion;
    # capture the vectors it builds with a sentinel bundle
    captured = {}
    real = proj_ml.build_features

    def _spy(*a, **k):
        v = real(*a, **k)
        captured.setdefault(flag_state[0], []).append(v)
        return v
    monkeypatch.setattr(proj_ml, "build_features", _spy)
    monkeypatch.setattr(proj_ml, "predict_path", lambda *a, **k: None)
    flag_state = [False]
    for s, _, h, a in players:
        fm.contract_war_path(h, s, 2015, 10, a, curves, war_map, league, ml_models={"x": 1})
    _flag(monkeypatch, True)
    flag_state[0] = True
    on = [real(h, s, 2015, a, curves, war_map, league) for s, _, h, a in players]
    for s, _, h, a in players:
        fm.contract_war_path(h, s, 2015, 10, a, curves, war_map, league, ml_models={"x": 1})
    assert json.dumps(off) == json.dumps(on)
    assert json.dumps(captured[False]) == json.dumps(captured[True])
    assert json.dumps(captured[False]) == json.dumps(off)


@pytest.mark.parametrize("path,pattern", [
    ("proj_ml.py", r"contract_war_path\([^)]*pt_cap=False,\s*use_ml=False,\s*aging=\"v2\"\)"),
    ("proj_ml.py", r"project_player\(hist, side, base, curves, league, int\(age\),\s*pt_cap=False\)"),
    ("fantasy_export.py", r"fp\.project_player\(hist, side, cur \+ 1,[^)]*pt_cap=False\)"),
    ("hitter_export.py", r"fp\.project_player\(hist, \"hit\", target,[^)]*pt_cap=False\)"),
    ("fa_fit.py", r"fp\.project_player\(hist, side, class_year,[^)]*pt_cap=False\)"),
])
def test_explicit_pt_cap_false_call_sites(path, pattern):
    src = (ROOT / path).read_text(encoding="utf-8")
    assert re.search(pattern, src), (path, pattern)


def test_fantasy_and_hitter_projection_do_not_move_with_the_flag(fits, monkeypatch):
    """The two call sites' own arguments: a project_player call carrying
    pt_cap=False returns the flag-off projection with the flag on."""
    corpus, curves, _ = fits
    league = corpus["league"]
    base = [fp.project_player(h, s, 2015, curves, league, a, pt_cap=False)
            for s, _, h, a in _players(corpus)]
    _flag(monkeypatch, True)
    again = [fp.project_player(h, s, 2015, curves, league, a, pt_cap=False)
             for s, _, h, a in _players(corpus)]
    assert base == again


# ---------------------------------------------------------------------------
# the FA Fit field (PLAN 9.7 R4a)
# ---------------------------------------------------------------------------

def _read_through_fa_fit(monkeypatch, doc: dict, season: int) -> dict:
    """fa_fit._outlook_wins on a given mlb_projections payload (its own reader,
    pointed at the payload instead of the file)."""
    import pathlib
    real = pathlib.Path.read_text
    text = json.dumps(doc)

    def _rt(self, *a, **k):
        if self.name == "mlb_projections.json":
            return text
        return real(self, *a, **k)
    with monkeypatch.context() as m:
        m.setattr(pathlib.Path, "read_text", _rt)
        return fa_fit._outlook_wins(season)


def test_fa_fit_field_is_the_uncapped_frame(monkeypatch):
    """proj_export._stamp_fa_fit_wins writes byYear[].winsFaFit from a second
    roll-up on the uncapped champion; fa_fit's per-club input wins read from it
    (flag on) equal the wins it read before (flag off, the frame's `wins`), so
    the repoint moves the FA Fit across no frame."""
    import proj_export as pe
    orgs = sorted(fa_fit.ORGS)
    vets_off, vets_on = [], []
    for i, org in enumerate(orgs):
        for j in range(3):
            mid = 900000 + 10 * i + j
            unc = [round(3.0 - 0.2 * t + 0.1 * j, 2) for t in range(pe.HORIZON)]
            cap = [round(w - (0.15 * t if i % 2 else 0.0), 2) for t, w in enumerate(unc)]
            row = {"mlbam": mid, "team": org, "age": 24 + j, "src": "vet",
                   "thru": pe.FIRST_SEASON + pe.HORIZON, "name": f"P{mid}", "key": f"p{mid}"}
            vets_off.append(dict(row, warChamp=unc, war=unc))
            vets_on.append(dict(row, warChamp=cap, war=cap))
    depth_unc = {org: [1.0] * pe.HORIZON for org in orgs}
    depth_cap = {org: [0.8] * pe.HORIZON for org in orgs}
    acct: dict = {}
    monkeypatch.setattr(pe, "_org_farm_blocks", lambda: {})
    monkeypatch.setattr(pe, "_cohort_intercepts", lambda: {})
    off = pe._team_outlook(vets_off, [], depth_unc, acct, {}, live=False)
    on = pe._team_outlook(vets_on, [], depth_cap, acct, {}, live=False)
    pe._FA_FIT_CHAMP.clear()
    pe._FA_FIT_CHAMP.update({m["mlbam"]: m["warChamp"] for m in vets_off})
    try:
        pe._stamp_fa_fit_wins(on, vets_on, [], depth_unc, acct)
    finally:
        pe._FA_FIT_CHAMP.clear()
    moved = 0
    for season in range(pe.FIRST_SEASON, pe.FIRST_SEASON + pe.HORIZON):
        before = _read_through_fa_fit(monkeypatch, {"team_outlook": off}, season)
        after = _read_through_fa_fit(monkeypatch, {"team_outlook": on}, season)
        assert len(before) == 30 and before == after, season
        moved += sum(1 for t in on for b in t["byYear"]
                     if b["season"] == season and b["wins"] != b["winsFaFit"])
    assert moved > 0     # the served wins moved, the FA Fit field did not


@pytest.mark.skipif(not os.environ.get("EEPHUS_PT_CAP_FA_REF"),
                    reason="exporter check runs on request (EEPHUS_PT_CAP_FA_REF)")
def test_fa_class_identical_across_team_outlook_inputs():
    d = Path(os.environ["EEPHUS_PT_CAP_FA_REF"])

    def _masked(p):
        doc = json.loads(p.read_text(encoding="utf-8"))
        for k in ("generated_at", "generated", "built_at"):
            doc.pop(k, None)
        return json.dumps(doc, sort_keys=True)
    assert _masked(d / "fa_class_a.json") == _masked(d / "fa_class_b.json")
