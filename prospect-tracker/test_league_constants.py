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
