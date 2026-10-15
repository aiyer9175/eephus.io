# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV_X1_MLE_TRANSLATION (docs/efv-v2/EFV_X1_MLE_TRANSLATION.md s9): the translation
recovers MLB rates on held-out consecutive-level pairs, the shrinkage is monotone in
sample size, nothing reads past a row's as-of, and the source groups nothing by
consensus-FV level."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np
import pytest

import efv_x1_fetch as XF
import efv_x1_translate as T

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "efv_x1_translate.py"
DOC = ROOT / "docs" / "efv-v2" / "EFV_X1_MLE_TRANSLATION.md"


def _have_cache(*seasons) -> bool:
    return all(XF.path_for("players", "hitting", sp, s).exists()
               and XF.path_for("teams", "pitching", sp, s).exists()
               for s in seasons for sp in XF.SPORTS)


def _synthetic(seed=7, n_players=1500, d=600.0, noise=True):
    """Lines of one season over a known ladder: MLB 1.0, AAA 0.80, AA 0.70, A 0.62 (the
    league factor of a strikeout-like rate). Each player plays one league or two adjacent
    ones the same season."""
    rng = np.random.default_rng(seed)
    ladder = [("MLB", "MLB", 1.0), ("AAA|X", "AAA", 0.80), ("AA|Y", "AA", 0.70),
              ("A|Z", "A", 0.62)]
    lines = []
    for p in range(n_players):
        theta = rng.uniform(0.15, 0.30)
        i = int(rng.integers(0, len(ladder)))
        legs = [i]
        if rng.random() < 0.4 and i + 1 < len(ladder):
            legs.append(i + 1)
        for j in legs:
            lg, lvl, lam = ladder[j]
            mu = d * theta * lam
            n = float(rng.poisson(mu)) if noise else mu
            lines.append({"mlbam": 10_000 + p, "lg": lg, "level": lvl, "team": None,
                          "nt": 1, "age": 22, "exp": d, "c": {"k": (n, d, None)}})
    return lines, {lg: lam for lg, _lvl, lam in ladder}


# ---------------------------------------------------------------------------
# 1. translation
# ---------------------------------------------------------------------------

def test_fit_recovers_known_league_factors_within_two_percent():
    lines, truth = _synthetic()
    f = T.fit_league_factors(lines, "k")
    for lg, lam in truth.items():
        assert lg in f["identified"]
        assert abs(f["lambda"][lg] / lam - 1.0) < 0.02, (lg, f["lambda"][lg], lam)
    assert f["lambda"]["MLB"] == 1.0


def test_unlinked_league_is_not_identified():
    lines, _truth = _synthetic()
    lines.append({"mlbam": 999_999, "lg": "DSL|ISO", "level": "DSL", "team": None, "nt": 1,
                  "age": 18, "exp": 300.0, "c": {"k": (60.0, 300.0, None)}})
    f = T.fit_league_factors(lines, "k")
    assert "DSL|ISO" not in f["identified"]


def test_heldout_pairs_translated_closer_than_raw_synthetic(monkeypatch):
    lines, _truth = _synthetic(seed=11)
    monkeypatch.setattr(T, "season_lines", lambda s, side: tuple(lines))
    monkeypatch.setattr(T, "park_factors", lambda s, side, st: {})
    for lo, hi in (("AAA", "MLB"), ("AA", "AAA")):
        r = T.recovery(2015, "hit", "k", lo, hi)
        assert r is not None
        assert abs(r["translated_rel_err"]) < abs(r["untranslated_rel_err"])
        assert abs(r["translated_rel_err"]) < 0.03


@pytest.mark.skipif(not _have_cache(2017, 2018), reason="EFV_X1 cache absent")
def test_heldout_pairs_translated_closer_than_raw_real_season():
    T.clear_caches()
    for side, st, lo, hi in (("hit", "k", "AAA", "MLB"), ("hit", "iso", "AAA", "MLB"),
                             ("hit", "k", "AA", "AAA"), ("pit", "k", "AAA", "MLB"),
                             ("pit", "bb", "AA", "AAA")):
        r = T.recovery(2018, side, st, lo, hi)
        assert r is not None, (side, st, lo, hi)
        assert abs(r["translated_rel_err"]) < abs(r["untranslated_rel_err"]), (side, st, r)


# ---------------------------------------------------------------------------
# 2. shrinkage
# ---------------------------------------------------------------------------

def test_shrinkage_monotone_in_sample_size():
    ns = [1, 10, 50, 100, 300, 600, 2000]
    for k in (5.0, 60.0, 400.0):
        w = [T.reliability(n, k) for n in ns]
        assert all(a < b for a, b in zip(w, w[1:]))
        x, mu = 0.30, 0.20
        dist = [abs(T.shrink(x, n, k, mu) - mu) for n in ns]
        assert all(a < b for a, b in zip(dist, dist[1:]))
        assert all(abs(T.shrink(x, n, k, mu) - x) < abs(x - mu) for n in ns)
    assert T.shrink(0.3, 10, None, 0.2) == 0.3
    assert T.reliability(10, None) == 1.0


# ---------------------------------------------------------------------------
# 3. no look-ahead
# ---------------------------------------------------------------------------

def test_top_season_follows_the_as_of_rule():
    assert T.top_season(2018, "2018-01-01") == 2017
    assert T.top_season(2018, "2017-10-15") == 2017
    assert T.top_season(2018, "2017-06-01") == 2016
    assert T.top_season(2021, "2021-01-01") == 2019      # 2020 had no season
    assert T._played_window(2021, 3) == [2021, 2019, 2018]


@pytest.mark.skipif(not _have_cache(2011, 2012, 2013), reason="EFV_X1 cache absent")
def test_factors_and_features_unchanged_when_later_seasons_are_removed(monkeypatch):
    T.clear_caches()
    s = 2012
    tab = {st: T.league_table(s, "hit", st) for st in ("k", "iso")}
    cst = T.constants(s, "hit")
    ps = T.player_seasons(s, "hit")
    pid = next(p for p, v in ps.items() if v["exp"] >= 300)
    f1 = T.features(pid, s + 1, None, "hit")
    assert all(x <= s for x in f1["_seasons"])
    orig = XF.load

    def hide(kind, group, sport, season):
        return [] if int(season) > s else orig(kind, group, sport, season)
    monkeypatch.setattr(T.X, "load", hide)
    T.clear_caches()
    for st in ("k", "iso"):
        t2 = T.league_table(s, "hit", st)
        assert {g: v["lambda"] for g, v in t2.items()} == \
            {g: v["lambda"] for g, v in tab[st].items()}
    c2 = T.constants(s, "hit")
    assert {k: v["k"] for k, v in c2.items()} == {k: v["k"] for k, v in cst.items()}
    f2 = T.features(pid, s + 1, None, "hit")
    assert f1 == f2
    T.clear_caches()


def test_every_season_read_is_dated_before_the_as_of(monkeypatch):
    lines, _truth = _synthetic(seed=3)
    seen = []

    def ps(season, side):
        seen.append(season)
        return {}
    monkeypatch.setattr(T, "player_seasons", ps)
    monkeypatch.setattr(T, "constants", lambda t, side: {st: {"k": None, "mu_cell": {},
                                                               "mu_level": {}}
                                                          for st in T.STATS[side]})
    T.features(123, 2019, "2018-07-01", "hit")
    assert seen and max(seen) <= 2017
    seen.clear()
    T.features(123, 2019, None, "pit")
    assert seen and max(seen) <= 2018


# ---------------------------------------------------------------------------
# 4. the read machinery and the flag
# ---------------------------------------------------------------------------

def test_loyo_score_uses_the_feature_and_flag_rule():
    rng = np.random.default_rng(5)
    rows, vals = [], {}
    for y in (2017, 2018, 2019):
        for i in range(120):
            talent = rng.normal()
            fv = 40 + 5 * round(float(talent + rng.normal()) / 1.5)
            war = max(talent + rng.normal(scale=0.7), 0.0)
            k = (f"p{y}_{i}", y)
            rows.append({"key": f"p{y}_{i}", "year": y, "group": f"hit|{y}",
                         "grades": {"prospx_consensus": float(fv)},
                         "outcome": {"war": war}, "_rk": k})
            vals[k] = talent + rng.normal(scale=0.3)
    score, slopes = T.loyo_score(rows, "f", vals)
    assert all(v is not None and v[2] > 0 for v in slopes.values())
    lv = {"delta": 0.02, "ci95": [0.001, 0.04], "twin_delta": 0.001}
    vm = {"delta": 0.01, "ci95": [-0.01, 0.03], "twin_delta": 0.0}
    assert T.flag(lv, vm) is True
    assert T.flag(lv, dict(vm, delta=-0.001)) is False
    assert T.flag(dict(lv, ci95=[-0.01, 0.05]), vm) is False
    assert T.flag(lv, dict(vm, twin_delta=0.02)) is False


# ---------------------------------------------------------------------------
# 5. gate compliance and isolation
# ---------------------------------------------------------------------------

def test_the_module_groups_nothing_by_consensus_fv_level():
    for path in (SRC, ROOT / "efv_x1_fetch.py"):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names |= {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for bad in ("fv_cell", "fv_bucket", "by_fv", "fv_level", "fv_bin", "fv_stratum"):
            assert not any(bad in n.lower() for n in names), (path.name, bad)
        for ch in (chr(0x2014), chr(0x2013)):
            assert ch not in src
    for ch in (chr(0x2014), chr(0x2013)):
        assert ch not in DOC.read_text(encoding="utf-8")


def test_no_served_module_imports_the_translation():
    pat = re.compile(r"^\s*(import|from)\s+efv_x1_(translate|fetch)\b", re.M)
    allowed = {"efv_x1_translate.py", "efv_x1_fetch.py", "test_efv_x1_translate.py"}
    for p in list(ROOT.glob("*.py")) + list((ROOT / "tools").glob("*.py")):
        if p.name in allowed:
            continue
        assert not pat.search(p.read_text(encoding="utf-8", errors="ignore")), p.name


def test_the_read_never_opens_a_reserved_frame():
    src = SRC.read_text(encoding="utf-8")
    assert "gate_sha" not in src
    assert "build_reserved" not in src
    assert "ReservedFrameError" in src
