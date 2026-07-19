# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Projection-engine guards: assembly algebra, Marcel regression behavior,
aging-curve application, and the committed Gate-1 artifact. Pure unit tests
on synthetic inputs — no network, no corpus build."""

from __future__ import annotations

import pytest

import fa_projection as fp

LEAGUE = {2026: {"season": 2026, "woba": 0.315, "r_pa": 0.118,
                 "k_pct": 0.222, "bb_pct": 0.084, "iso": 0.158, "babip": 0.291,
                 "hr_pa": 0.031, "fip_constant": 3.13, "lg_fip": 4.16,
                 "p_k_pct": 0.222, "p_bb_pct": 0.084, "p_hr_bf": 0.031}}
NO_CURVES = {"hit": {}, "pit": {}}


def _hist_hitter(**over) -> dict:
    base = {"mlbam": 1, "season": 2026, "age": 29, "role": "H", "pa": 650.0,
            "k_pct": 0.18, "bb_pct": 0.10, "iso": 0.220, "babip": 0.310,
            "hr_pa": 0.045, "war": 4.0}
    base.update(over)
    return base


def test_league_average_player_projects_near_100_wrc():
    """A player whose components ARE the league rates must assemble to
    wRC+ ~ 100 — the core scale-calibration identity."""
    lg = LEAGUE[2026]
    hist = [_hist_hitter(k_pct=lg["k_pct"], bb_pct=lg["bb_pct"], iso=lg["iso"],
                         babip=lg["babip"], hr_pa=lg["hr_pa"])]
    proj = fp.project_player(hist, "hit", 2027, NO_CURVES, LEAGUE, age=27)
    assert proj is not None
    assert proj["wrc_plus_proj"] == pytest.approx(100, abs=6)


def test_regression_pulls_thin_samples_harder():
    """60 PA of a .350-ISO binge regresses far closer to league than a
    600-PA season of the same rates — the stabilization-point contract."""
    big = fp.project_player([_hist_hitter(pa=600.0, iso=0.350)], "hit", 2027,
                            NO_CURVES, LEAGUE, age=27)
    thin = fp.project_player([_hist_hitter(pa=60.0, iso=0.350)], "hit", 2027,
                             NO_CURVES, LEAGUE, age=27)
    lg_iso = LEAGUE[2026]["iso"]
    assert big["iso"] > thin["iso"] > lg_iso
    assert (0.350 - big["iso"]) < (0.350 - thin["iso"])


def test_marcel_weights_favor_recent_season():
    hist = [_hist_hitter(season=2026, iso=0.300),
            _hist_hitter(season=2025, iso=0.150),
            _hist_hitter(season=2024, iso=0.150)]
    proj = fp.project_player(hist, "hit", 2027, NO_CURVES, LEAGUE, age=28)
    blend = fp.project_player([_hist_hitter(season=2026, iso=0.150)], "hit", 2027,
                              NO_CURVES, LEAGUE, age=28)
    assert proj["iso"] > blend["iso"]


def test_aging_curve_applies_in_direction():
    curves = {"hit": {"H": {"iso": {"33": {"delta": -0.015, "delta_smooth": -0.015, "n": 99}}}},
              "pit": {}}
    young = fp.project_player([_hist_hitter()], "hit", 2027, NO_CURVES, LEAGUE, age=33)
    aged = fp.project_player([_hist_hitter()], "hit", 2027, curves, LEAGUE, age=33)
    assert aged["iso"] == pytest.approx(young["iso"] - 0.015, abs=1e-9)


def test_curve_delta_clamps_to_support():
    curves = {"hit": {"H": {"iso": {"30": {"delta": -0.01, "delta_smooth": -0.01},
                                    "36": {"delta": -0.02, "delta_smooth": -0.02}}}}}
    assert fp.curve_delta(curves, "hit", "H", "iso", 45) == -0.02   # clamps high
    assert fp.curve_delta(curves, "hit", "H", "iso", 22) == -0.01   # clamps low
    assert fp.curve_delta(curves, "hit", "H", "missing", 30) == 0.0


def test_pitcher_fip_assembly_sane():
    hist = [{"mlbam": 2, "season": 2026, "age": 30, "role": "SP", "bf": 800.0,
             "ip": 190.0, "k_pct": 0.28, "bb_pct": 0.06, "hr_bf": 0.025,
             "fip": 3.40, "war": 4.0}]
    proj = fp.project_player(hist, "pit", 2027, NO_CURVES, LEAGUE, age=31)
    assert proj is not None and 2.5 < proj["fip_proj"] < 5.0
    assert proj["ip_proj"] > 100


def test_no_history_returns_none():
    assert fp.project_player([], "hit", 2027, NO_CURVES, LEAGUE, age=30) is None
    old = [_hist_hitter(season=2020)]                       # outside the 3-season window
    assert fp.project_player(old, "hit", 2027, NO_CURVES, LEAGUE, age=30) is None


def test_fitted_models_cache_key_invalidates_on_corpus_refresh(tmp_path, monkeypatch):
    """A corpus refresh (corpus['last'] rolls forward: annual rollover, the
    in-progress season going partial->full, or bWAR revisions) must force a refit
    at the SAME max_season -- not serve the previous vintage's stale aging curves +
    WAR map from the disk cache. The fits cache key therefore includes
    corpus['last'] (mirrors proj_ml's frame-cache key)."""
    monkeypatch.setattr(fp, "CACHE_DIR", tmp_path)
    calls = []

    def _fake_curves(corpus, max_season=None, write=True):
        calls.append(("curves", corpus["last"]))
        return {"vintage": corpus["last"]}

    def _fake_war(corpus, max_season=None):
        calls.append(("war", corpus["last"]))
        return {"vintage": corpus["last"]}

    monkeypatch.setattr(fp, "fit_aging_curves", _fake_curves)
    monkeypatch.setattr(fp, "fit_war_map", _fake_war)

    v1 = {"first": 2000, "last": 2026, "hit": [], "pit": [], "league": {}}
    v2 = {"first": 2000, "last": 2027, "hit": [], "pit": [], "league": {}}

    c1, w1 = fp.fitted_models(v1, 2026)
    assert (c1, w1) == ({"vintage": 2026}, {"vintage": 2026})

    # Same max_season + first, but the corpus vintage advanced -> MUST refit and
    # return the fresh fits, not v1's cached ones.
    c2, w2 = fp.fitted_models(v2, 2026)
    assert (c2, w2) == ({"vintage": 2027}, {"vintage": 2027})

    # Two distinct on-disk cache files (the key carries corpus['last']).
    names = [p.name for p in tmp_path.glob("fa_fits_*.pkl")]
    assert len(names) == 2, names
    assert any("2027" in n for n in names) and any("2026" in n for n in names)

    # Re-requesting v1 still hits its own cache -- no spurious refit.
    calls.clear()
    c1b, _ = fp.fitted_models(v1, 2026)
    assert c1b == {"vintage": 2026}
    assert calls == []


# ---- HARD GATE 1 artifact ------------------------------------------------------

def test_gate1_artifact_committed_and_passing():
    """The ship/no-ship contract: Stage 3+ may not build unless the
    persisted projection-gate artifact says pass=True with the documented
    criteria intact. (The gate itself runs via `python fa_backtest.py
    --gate1`; this asserts its committed verdict.)"""
    import storage
    evals = storage.load_fa_model_eval()
    row = next((v for (mv, gate), v in evals.items() if gate == "projection"), None)
    if row is None:
        pytest.skip("projection gate not yet run on this machine")
    assert row["pass"] is True, f"GATE 1 FAILING: {row['gates']}"
    assert row["gates"]["war"] and row["gates"]["wrc_plus"] and row["gates"]["fip"]
    assert 0.75 <= row["coverage_p10_p90"] <= 0.85
    assert row["pooled"]["war"]["n"] > 15000          # real population, not a toy slice
