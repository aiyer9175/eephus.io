# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""rpw_fit (docs/ewar/RPW_GATE.md) on fixtures: the candidates, leave one season out,
the bootstrap and the pass rule, the pitcher leg and its refusals, and a dry run of
tools/build_rpw_fit.py on a fixture cache (no real cache is read or written)."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import fwar_frame  # noqa: E402
import rpw_fit as rf  # noqa: E402

CLUBS = ["ARI", "ATH", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE", "COL", "DET", "HOU",
         "KCR", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY", "PHI", "PIT", "SDP", "SEA",
         "SFG", "STL", "TBR", "TEX", "TOR", "WSN"]


def _rows(seasons=rf.PRIMARY_SEASONS, rpw=10.0, seed=7):
    """Synthetic team-seasons whose wins follow G/2 + RD/rpw exactly (rounded runs kept
    zero-sum per season)."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in seasons:
        rd = rng.normal(0.0, 90.0, 30)
        rd = rd - rd.mean()
        for i, c in enumerate(CLUBS):
            rs = 700.0 + rd[i] / 2.0
            ra = 700.0 - rd[i] / 2.0
            w = 81.0 + rd[i] / rpw
            rows.append({"season": s, "club": c, "w": w, "l": 162.0 - w, "rs": rs, "ra": ra,
                         "pf": 1.0 + 0.01 * (i % 5 - 2), "rpw_fg": 9.8, "rpw_bref": 10.4,
                         "L": 1400.0 * 2 / 162.0})
    return rows


# ----------------------------------------------------------------- candidates
def test_pythag_even_club_wins_half():
    assert rf.pythag_wins([700.0], [700.0], [162.0], 0.28)[0] == pytest.approx(81.0)


def test_fit_pythag_z_recovers_the_generating_exponent():
    rng = np.random.default_rng(3)
    rs = rng.uniform(550, 900, 200)
    ra = rng.uniform(550, 900, 200)
    g = np.full(200, 162.0)
    w = rf.pythag_wins(rs, ra, g, 0.2875)
    assert rf.fit_pythag_z(rs, ra, g, w) == pytest.approx(0.2875)


def test_pythag_league_rpw_matches_the_marginal_at_even_runs():
    L = 9.0
    r = L / 2.0 * 162.0
    m = rf.pythag_marginal_rpw([r], [r], [162.0], 0.29)[0]
    assert m == pytest.approx(rf.pythag_league_rpw(L, 0.29), rel=1e-4)
    assert rf.pythag_league_rpw(L, 0.29) == pytest.approx(2.0 * 9.0 ** 0.71)


def test_slope_and_env_recover_their_coefficients():
    f = rf.frame(_rows(rpw=9.5))
    assert 1.0 / rf.fit_slope(f["rd"], f["g"], f["w"]) == pytest.approx(9.5)
    rng = np.random.default_rng(11)
    n = 400
    rd = rng.normal(0, 80, n)
    L = rng.uniform(8.5, 9.8, n)
    t = L + rng.normal(0, 0.5, n)
    pf = 1.0 + rng.normal(0, 0.03, n)
    coef = [0.102, -0.004, -0.003, 0.01]
    g = np.full(n, 162.0)
    w = g / 2 + rd * rf.env_wins_per_run(coef, L, t, pf)
    got = rf.fit_env(rd, L, t, pf, g, w)
    assert got == pytest.approx(coef, abs=1e-9)
    assert rf.env_league_rpw(coef, 9.0) == pytest.approx(1 / 0.102)


def test_dynamic_form_equals_fangraphs_when_the_pitcher_has_outs():
    ip, g, ra, lg = 180.0, 30.0, 70.0, 4.5
    ra9 = 9.0 * ra / ip
    want = fwar_frame.dynamic_rpw(ip, g, lg, ra9)
    assert rf.dynamic_rpw_runs(ip / g, ra, g, lg) == pytest.approx(want)
    # no outs: finite, the RA9 term weighted by ipg 0 collapses to 9 RA / G
    assert math.isfinite(float(rf.dynamic_rpw_runs(0.0, 3.0, 1.0, lg)))


# ------------------------------------------------------------- the estimand
def test_loso_fits_exclude_the_held_out_season():
    rows = _rows(rpw=10.0)
    for r in rows:                      # one season with a different slope
        if r["season"] == 2022:
            rd = r["rs"] - r["ra"]
            r["w"] = 81.0 + rd / 7.0
            r["l"] = 162.0 - r["w"]
    f = rf.frame(rows)
    held = rf.loso(f, ("c",))
    assert held["c"]["fits"][2022]["rpw"] == pytest.approx(10.0)
    assert held["c"]["fits"][2023]["rpw"] != pytest.approx(10.0)


def test_incumbent_and_bref_fit_nothing_and_r0_is_half_the_games():
    f = rf.frame(_rows())
    held = rf.loso(f, ("a", "e", "r0"))
    assert np.allclose(held["a"]["pred"], f["g"] / 2 + f["rd"] / 9.8)
    assert np.allclose(held["e"]["pred"], f["g"] / 2 + f["rd"] / 10.4)
    assert np.allclose(held["r0"]["pred"], f["g"] / 2)


def test_env_candidate_void_on_nonpositive_rpw():
    f = rf.frame(_rows())
    f["w"] = f["g"] / 2 - f["rd"] / 10.0          # wins fall with run differential
    held = rf.loso(f, ("c",))
    assert held["c"]["void"] is True


def test_boot_index_is_the_registered_draw():
    idx = rf.boot_index(300)
    assert idx.shape == (2000, 300)
    want = np.random.default_rng(20261025).integers(0, 300, size=(2000, 300))
    assert np.array_equal(idx, want)


def test_contrast_sign_and_verdict():
    rng = np.random.default_rng(5)
    base = rng.normal(0, 4, 300)
    idx = rf.boot_index(300)
    better = rf.contrast(base, base * 0.5, idx)
    assert better["d_mae"] > 0 and better["lo95"] > 0
    same = rf.contrast(base, base, idx)
    assert same["d_mae"] == 0 and same["lo95"] == 0 and same["p_le_0"] == 1.0
    worse = rf.contrast(base, base * 2.0, idx)
    c = {"b": better, "c": same, "d": worse, "e": dict(better)}
    v = rf.verdict(c, {})
    assert v["status"] == "PRIMARY PASS, GUARD PENDING"
    assert v["candidate"] == "b" and v["passing"] == ["b", "e"]       # tie: earlier letter
    assert rf.verdict(c, {"b": True, "e": True})["status"] == "INCUMBENT HOLDS"
    assert rf.pitcher_verdict(better) == "beats"
    assert rf.pitcher_verdict(worse) == "does worse"
    assert rf.pitcher_verdict(same) == "does not separate"


def test_holm_step_down():
    h = rf.holm({"b": 0.001, "c": 0.015, "d": 0.04, "e": 0.5})
    assert h["b"]["rejects"] and h["c"]["rejects"]
    assert not h["d"]["rejects"] and not h["e"]["rejects"]


# ------------------------------------------------------------ refusals and part 5
def test_check_season_refusals():
    good = [{"w": 81, "l": 81, "rs": 700, "ra": 700} for _ in range(30)]
    rf.check_season(2024, good)
    with pytest.raises(rf.RpwRefusal):
        rf.check_season(2024, good[:29])
    bad = [dict(c) for c in good]
    bad[0]["rs"] = 701
    with pytest.raises(rf.RpwRefusal):
        rf.check_season(2024, bad)
    bad = [dict(c) for c in good]
    bad[0]["w"] = 82
    with pytest.raises(rf.RpwRefusal):
        rf.check_season(2024, bad)


def _stints_for(f):
    out = []
    for i, club in enumerate(f["club"]):
        s = int(f["season"][i])
        ra = f["ra"][i]
        out.append({"season": s, "club": club, "pid": f"{club}{s}a", "g": 32, "outs": 600, "ra": ra - 3})
        out.append({"season": s, "club": club, "pid": f"pos{club}{s}", "g": 1, "outs": 0, "ra": 3})
    return out


def test_pitcher_arms_identity_and_refusal():
    rows = _rows(seasons=(2024,))
    for r in rows:
        r["rs"] = round(r["rs"])
        r["ra"] = round(r["ra"])
    f = rf.frame(rows)
    st = _stints_for(f)
    arms = rf.pitcher_arms(f, st, {2024: 4.5})
    assert np.allclose(arms["L"], f["g"] / 2 + f["rd"] / f["rpw_fg"], atol=1e-9)
    assert np.all(np.isfinite(arms["D"]))
    st[0]["ra"] += 1
    with pytest.raises(rf.RpwRefusal):
        rf.pitcher_arms(f, st, {2024: 4.5})


# ----------------------------------------------------- dry run of the build tool
def _write_fixture_cache(tmp: Path):
    import pandas as pd
    rng = np.random.default_rng(17)
    (tmp / "team_stats").mkdir(parents=True)
    (tmp / "fangraphs").mkdir()
    (tmp / "war_daily").mkdir()
    bat, pit = [], []
    for s in rf.ALL_SEASONS:
        g = 60 if s == 2020 else 162
        rd = np.round(rng.normal(0, 90 * g / 162, 30))
        rd[-1] = -rd[:-1].sum()
        recs, ts, pf = [], [], []
        for i, c in enumerate(CLUBS):
            rs = int(round(4.5 * g)) + int(rd[i] // 2)
            ra = int(rs - rd[i])
            w = int(round(g / 2 + rd[i] / 10.0 + rng.normal(0, 3)))
            recs.append({"team": {"id": 100 + i}, "wins": w, "losses": g - w,
                         "runsScored": rs, "runsAllowed": ra})
            ts.append({"team_id": 100 + i, "club": c})
            pf.append({"Team": c, "Basic (5yr)": 100.0 + i % 7 - 3, "team_id": 100 + i})
            pit.append({"year_ID": s, "team_ID": "OAK" if c == "ATH" else c, "player_ID": f"p{c}",
                        "G": 30, "IPouts": 1300, "RA": ra - 10, "runs_above_avg_adj": rd[i] / 4,
                        "WAA": rd[i] / 40})
            pit.append({"year_ID": s, "team_ID": "OAK" if c == "ATH" else c, "player_ID": f"q{c}{s}",
                        "G": 40, "IPouts": 158, "RA": 10, "runs_above_avg_adj": 0.0, "WAA": 0.0})
            bat.append({"year_ID": s, "team_ID": c, "runs_above_avg": rd[i] / 2, "WAA": rd[i] / 20})
        # keep the fixture's league wins equal to losses
        tot_w = sum(r["wins"] for r in recs)
        recs[-1]["wins"] -= tot_w - 15 * g
        recs[-1]["losses"] = g - recs[-1]["wins"]
        (tmp / f"statsapi_standings_{s}.json").write_text(
            json.dumps({"records": [{"teamRecords": recs}]}), encoding="utf-8")
        (tmp / "team_stats" / f"{s}_pit.json").write_text(json.dumps({"rows": ts}), encoding="utf-8")
        (tmp / "fangraphs" / f"park_factors_{s}.json").write_text(
            json.dumps({"complete": s != 2026, "rows": pf}), encoding="utf-8")
    pd.DataFrame(bat).to_parquet(tmp / "war_daily" / "bat.parquet")
    pd.DataFrame(pit).to_parquet(tmp / "war_daily" / "pit.parquet")


def test_build_dry_run_on_fixtures(tmp_path, monkeypatch):
    import build_rpw_fit
    import league_constants
    _write_fixture_cache(tmp_path)
    monkeypatch.setattr(league_constants, "league_totals",
                        lambda s: {"rpw": 9.9, "lg_ra9": 4.5})
    lines = []
    doc = build_rpw_fit.build(cache=tmp_path, log=lines.append)
    assert doc["rpw_fit_version"] == "rpw_fit_v1"
    assert doc["frame"]["team_seasons"] == 300
    assert doc["frame"]["park_factor_season_used"]["2026"] == 2025
    assert set(doc["candidates"]) == {"a", "b", "c", "d", "e", "r0", "r1"}
    assert set(doc["contrasts_vs_a"]) == {"b", "c", "d", "e"}
    assert doc["verdict"]["status"] in ("INCUMBENT HOLDS", "PRIMARY PASS, GUARD PENDING")
    assert set(doc["rpw_by_season"]["a"]) == {str(s) for s in rf.ALL_SEASONS}
    assert doc["pitcher_leg"]["arm_L_max_abs_vs_a"] <= 1e-9
    assert doc["pitcher_leg"]["finding"] in ("beats", "does worse", "does not separate")
    assert "2020" in doc["per_season_slope_reported"]
    assert doc["sensitivity_2020"]["a"]["mae_per_162"] is not None
    json.dumps(doc)                                    # serializable
    assert any(line.startswith("war_daily pit sha256") for line in lines)
