# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Per-season league constants, and the two properties the wOBA-scale repair
rests on (audit F01-03).

The constant `fa_config.yaml assembly.woba_scale` was 1.15 for every season from
2000 to 2026 while the reference says the value varies year to year to keep wOBA
on the league-OBP scale. It is 7.2 percent low against 2026 and the served
projected wRC+ was that much too wide on 3,205 rows.

The two properties that make the repair safe rather than merely correct:

  * wRC+ MOVES, because that column divides by the scale directly.
  * WAR DOES NOT, because the WAR map is fitted on wraa_pa and scored on wraa_pa,
    so a change of scale cancels PROVIDED the fit is regenerated. That proviso is
    the whole risk: the fit cache key digested rows and the league block but not
    the scale, so a changed constant would have loaded a fit built on the old one
    and scored it with the new one, which moves WAR rather than leaving it alone.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import league_constants as LC

ROOT = Path(__file__).resolve().parent


def test_the_identity_comes_back_essentially_exact():
    """This is an identity being read back, not a model being estimated. If r
    ever falls the feed changed shape and the constant must not be served."""
    tbl = LC.load()
    if not tbl:
        pytest.skip("data/league_constants.json not built")
    for season, blk in tbl.items():
        assert blk["r"] >= LC.MIN_R, (
            f"{season} solved at r={blk['r']}, below {LC.MIN_R}; a constant this "
            "loose is a changed feed, not a league that moved")
        assert blk["n"] >= LC.MIN_ROWS


def test_the_solved_scales_are_in_the_published_range():
    """The reference prints 1.26 for 2011 and 1.277 for 2013. A solved value
    outside a generous band around those is a broken join, not a discovery."""
    tbl = LC.load()
    if not tbl:
        pytest.skip("data/league_constants.json not built")
    for season, blk in tbl.items():
        assert 1.10 < blk["woba_scale"] < 1.40, f"{season}: {blk['woba_scale']}"
        assert 0.29 < blk["lg_woba"] < 0.34, f"{season}: {blk['lg_woba']}"


def test_a_future_season_never_borrows_a_constant_from_an_unplayed_one():
    tbl = LC.load()
    if not tbl:
        pytest.skip("data/league_constants.json not built")
    newest = max(tbl)
    assert LC.woba_scale(newest + 4) == tbl[newest]["woba_scale"]


def test_an_absent_artifact_falls_back_rather_than_raising(monkeypatch):
    monkeypatch.setattr(LC, "load", lambda: {})
    assert LC.woba_scale(2026, default=1.15) == 1.15
    assert LC.woba_scale(2026) is None


def test_the_engine_prefers_the_solved_scale_and_falls_back_below_coverage():
    import fa_projection as fp
    tbl = LC.load()
    if not tbl:
        pytest.skip("data/league_constants.json not built")
    newest = max(tbl)
    assert fp._woba_scale(newest) == pytest.approx(tbl[newest]["woba_scale"])
    cfg = float(fp._pcfg()["assembly"]["woba_scale"])
    assert fp._woba_scale(min(tbl) - 5) == pytest.approx(cfg), (
        "a season the feed does not cover must degrade to the config constant, "
        "not to a borrowed one")


def test_the_second_hardcoded_scale_is_gone():
    """positional_fit carried its own 1.15 with a comment pointing at fa_config,
    and no fitted coefficient to absorb it, so its runs conversion was inflated
    by the same 7.8 percent. A fix in the config alone would have left the two
    copies disagreeing, which is how the first one survived."""
    src = (ROOT / "positional_fit.py").read_text(encoding="utf-8")
    assert "WOBA_SCALE = 1.15" not in src
    assert "_woba_scale(" in src
    import positional_fit as pf
    import fa_projection as fp
    assert pf._woba_scale(2026) == pytest.approx(fp._woba_scale(2026))


def test_the_fit_cache_key_depends_on_the_scale():
    """THE SAFETY PROPERTY. The WAR map is invariant to the scale only when the
    fit and the score see the same one. The key digested rows and the league
    block but not the constant, so a changed scale would have served a stale fit
    and moved WAR."""
    import fa_projection as fp
    corpus = {"first": 2020, "last": 2024, "league": {2024: {"woba": 0.31}},
              "hit": [{"mlbam": 1, "season": 2024, "war": 2.0, "pa": 600}],
              "pit": []}
    base = fp._corpus_sig(dict(corpus))
    real = fp._woba_scale

    def bumped(season):
        return real(season) * 1.10

    fp._woba_scale = bumped
    try:
        moved = fp._corpus_sig(dict(corpus))
    finally:
        fp._woba_scale = real
    assert base != moved, (
        "the fit cache key ignores the wOBA scale, so changing the constant "
        "would load a fit built on the old one and score it with the new one")


def test_war_is_invariant_to_the_scale_when_the_fit_is_regenerated():
    """The reason this repair may ship as a display change: the feature carries
    1/scale and the fitted coefficient carries scale, so the product cancels.
    Verified on the real OLS rather than asserted.

    Each arm scores with the SAME scale it fitted with, which is the condition
    the cache-key test above exists to guarantee in production."""
    import fa_projection as fp
    league = {2023: {"woba": 0.310, "r_pa": 0.118, "babip": 0.295, "lg_fip": 4.10},
              2024: {"woba": 0.312, "r_pa": 0.119, "babip": 0.296, "lg_fip": 4.08}}
    rows = []
    for i in range(80):
        rows.append({"mlbam": i, "season": 2023, "pa": 300 + i * 6,
                     "war": 0.5 + (i % 11) * 0.35,
                     "role": "C" if i % 5 == 0 else "OF",
                     "avg": 0.245 + (i % 7) * 0.006, "obp": 0.310 + (i % 6) * 0.006,
                     "iso": 0.130 + (i % 8) * 0.011, "babip": 0.290 + (i % 4) * 0.004,
                     "bb_pct": 0.06 + (i % 5) * 0.008, "k_pct": 0.18 + (i % 6) * 0.012,
                     "hr_pa": 0.020 + (i % 9) * 0.003})
    # the pitcher side must be non-empty or the shared lstsq raises on an empty
    # design matrix; these rows exist only to keep that side well posed and carry
    # nothing this test asserts on
    pit = [{"mlbam": 900 + i, "season": 2023, "ip": 60 + i * 3,
            "war": 0.4 + (i % 6) * 0.3, "role": "SP" if i % 3 else "RP",
            "fip": 3.4 + (i % 7) * 0.18} for i in range(40)]
    corpus = {"first": 2020, "last": 2024, "league": league, "hit": rows, "pit": pit}
    comp = {"pa": 600, "avg": 0.270, "obp": 0.340, "iso": 0.180, "babip": 0.300,
            "bb_pct": 0.09, "k_pct": 0.21, "hr_pa": 0.038, "role": "OF",
            "season": 2024}

    def arm(scale):
        """Fit AND score under one scale, which is the condition the cache-key
        test guarantees in production."""
        real = fp._woba_scale
        fp._woba_scale = lambda season: scale
        try:
            m = fp.fit_war_map(corpus, max_season=2024, use_def=False)
            asm = fp._assemble_hitter(comp, league, 2024)
            proj = {"pt_proj": 600.0, "wraa_pa": asm["wraa_pa"], "role": "OF"}
            return fp.war_from_projection(proj, "hit", m, league, 2024), asm
        finally:
            fp._woba_scale = real

    (war_a, asm_a), (war_b, asm_b) = arm(1.15), arm(1.24)
    assert war_a is not None and war_b is not None
    # the wRAA feature itself MUST move, or the test is vacuous
    assert asm_a["wraa_pa"] != pytest.approx(asm_b["wraa_pa"], rel=1e-6)
    assert asm_a["wrc_plus_proj"] != pytest.approx(asm_b["wrc_plus_proj"], rel=1e-6), (
        "wRC+ must move on a scale change; that is the served column this repair fixes")
    assert war_a == pytest.approx(war_b, abs=0.02), (
        f"WAR moved {war_a} -> {war_b} on a pure scale change; the fit must "
        "absorb it, and if it does not the repair is a model change wearing a "
        "display fix's clothes")


# The FanGraphs Guts table, transcribed twice independently on 2026-09-09 (audit
# sheet C1, lines 604-620). Complete seasons only: an in-progress season moves
# daily and the transcription is a single moment of it.
#   season: (scale, wBB, wHBP, w1B, w2B, w3B, wHR, runCS, R/PA, R/W, cFIP)
GUTS = {
    2025: (1.232, .691, .722, .882, 1.252, 1.584, 2.037, -.410, .118, 9.774, 3.135),
    2024: (1.242, .689, .720, .882, 1.254, 1.590, 2.050, -.405, .117, 9.683, 3.166),
    2023: (1.204, .696, .726, .883, 1.244, 1.569, 2.004, -.422, .122, 10.028, 3.255),
    2022: (1.259, .689, .720, .884, 1.261, 1.601, 2.072, -.397, .114, 9.524, 3.112),
    2021: (1.209, .692, .722, .879, 1.242, 1.568, 2.007, -.419, .121, 9.973, 3.170),
    2020: (1.185, .699, .728, .883, 1.238, 1.558, 1.979, -.435, .125, 10.282, 3.191),
    2019: (1.157, .690, .719, .870, 1.217, 1.529, 1.940, -.435, .126, 10.296, 3.214),
    2018: (1.226, .690, .720, .880, 1.247, 1.578, 2.031, -.407, .117, 9.714, 3.160),
    2017: (1.185, .693, .723, .877, 1.232, 1.552, 1.980, -.423, .122, 10.048, 3.158),
    2016: (1.212, .691, .721, .878, 1.242, 1.569, 2.015, -.410, .118, 9.778, 3.147),
    2015: (1.251, .687, .718, .881, 1.256, 1.594, 2.065, -.392, .112, 9.421, 3.134),
    2014: (1.304, .689, .722, .892, 1.283, 1.635, 2.135, -.377, .107, 9.117, 3.132),
    2013: (1.277, .690, .722, .888, 1.271, 1.616, 2.101, -.384, .110, 9.264, 3.048),
    2012: (1.245, .691, .722, .884, 1.257, 1.593, 2.058, -.398, .114, 9.544, 3.094),
    2011: (1.264, .694, .726, .890, 1.270, 1.611, 2.086, -.394, .112, 9.454, 3.025),
}

#: Half a unit in the third printed decimal plus the solve's own rounding.
_THIRD = 0.0015


def _solved_or_skip():
    tbl = LC.load()
    missing = [s for s in GUTS if s not in tbl or "woba_weights" not in tbl[s]]
    if missing:
        pytest.skip(f"artifact lacks solved weights for {missing}")
    return tbl


def test_the_solved_scale_reproduces_the_published_table():
    tbl = _solved_or_skip()
    for season, g in GUTS.items():
        assert tbl[season]["woba_scale"] == pytest.approx(g[0], abs=_THIRD), season


def test_the_solved_weights_reproduce_the_published_table():
    """The weights are an identity in the feed, so every one must land on the
    printed value. A miss here is a broken join or a changed feed, never a
    league that moved."""
    tbl = _solved_or_skip()
    for season, g in GUTS.items():
        w = tbl[season]["woba_weights"]
        got = tuple(w[k] for k in LC.WEIGHT_KEYS)
        for k, a, b in zip(LC.WEIGHT_KEYS, got, g[1:7]):
            assert a == pytest.approx(b, abs=_THIRD), f"{season} {k}: {a} vs {b}"
        assert tbl[season]["weights_worst_residual"] <= LC.WEIGHT_TOL


def test_the_league_totals_reproduce_runs_per_win_fip_constant_and_runcs():
    """Runs per win is FanGraphs' closed form on league R/IP; the FIP constant
    includes intentional walks in BB, the only reading that reproduces the
    table; runCS is -(2*R/outs + 0.075)."""
    tbl = _solved_or_skip()
    for season, g in GUTS.items():
        b = tbl[season]
        assert b["run_cs"] == pytest.approx(g[7], abs=_THIRD), season
        assert b["lg_r_pa"] == pytest.approx(g[8], abs=0.0006), season
        assert b["rpw"] == pytest.approx(g[9], abs=_THIRD), season
        assert b["fip_constant"] == pytest.approx(g[10], abs=_THIRD), season
        assert b["run_sb"] == LC.RUN_SB


def test_the_weights_and_the_scale_describe_the_same_league():
    """Two independent solves from the same feed: the scale from the wRAA
    identity, the weights from the wOBA identity. League wOBA rebuilt from the
    weights and the season totals must land near the league wOBA the scale
    solve returned, or one of the two joins is wrong."""
    tbl = _solved_or_skip()
    for season in GUTS:
        b = tbl[season]
        assert 0.29 < b["lg_woba"] < 0.34
        assert b["lg_wsb"] is not None and abs(b["lg_wsb"]) < 0.02, season


def test_earlier_seasons_are_published_but_reach_no_consumer():
    """Seasons before SERVED_FROM are solved and reviewable in the artifact, but
    the projection corpus keeps reading its fallback for them: widening the
    served table is a measured move of its own. Since 2026-09-11 that means
    2011-2014."""
    tbl = LC.load()
    early = [s for s in tbl if s < LC.SERVED_FROM]
    if not early:
        pytest.skip("no pre-served seasons in the artifact")
    s = min(early)
    assert LC.woba_scale(s, default=1.15) == 1.15
    assert LC.constants(s) is None
    assert set(LC.served()) == {x for x in tbl if x >= LC.SERVED_FROM}


def test_2015_through_2020_are_served_by_owner_decision():
    """Owner decision 14 (2026-09-11): the solved 2015-2020 scales reach the
    projection corpus, so the fit no longer mixes the solved scale with the 1.15
    config constant across those feature rows. 2011-2014 stay unserved because
    the decision named 2015, and the artifact's own served_from must say what
    the module does."""
    assert LC.SERVED_FROM == 2015
    tbl = LC.load()
    if not tbl:
        pytest.skip("data/league_constants.json not built")
    import fa_projection as fp
    for s in range(2015, 2021):
        assert s in tbl, f"{s} missing from the artifact"
        assert LC.woba_scale(s) == tbl[s]["woba_scale"], s
        assert fp._woba_scale(s) == pytest.approx(tbl[s]["woba_scale"]), s
    assert LC.woba_scale(2014, default=1.15) == 1.15
    blob = json.loads(LC.OUT_PATH.read_text(encoding="utf-8"))
    assert blob["served_from"] == LC.SERVED_FROM
