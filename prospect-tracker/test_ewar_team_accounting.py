# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR team accounting read's dry run on fixtures
(docs/ewar-v3/EWAR_TEAM_ACCOUNTING_GATE.md part 10 step 1, task EWAR_TEAM_ACCOUNTING).

Every reporting path runs on a synthetic frame with null values, a missing xHEM+
preview and a short season; the planted machinery recovers a planted departure on a
synthetic design and rejects a permuted one. Nothing here reads a cache, a served
artifact or a club outcome.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ewar_team_accounting as TA  # noqa: E402
import ewar_team_accounting_lab as LAB  # noqa: E402


# ------------------------------------------------------------------ core
def _design(n_seasons=4, n_clubs=12, seed=1, short=False):
    rng = np.random.default_rng(seed)
    seasons = list(range(2016, 2016 + n_seasons))
    season, club, fr, g = [], [], [], []
    for s in seasons:
        for c in range(n_clubs):
            season.append(s)
            club.append(f"C{c}")
            fr.append(c)
            g.append(60 if short else 162)
    n = len(season)
    n_p = n * 4
    return TA.Design(season=season, club=club, franchise=fr, g=g, w=np.full(n, 81.0),
                     rs=np.full(n, 700.0), ra=np.full(n, 700.0),
                     players=[f"p{i}" for i in range(n_p)], seasons=tuple(seasons)), rng


def _series_and_dep(design, rng, dep_sd=1.0):
    n_c, n_p = design.n, len(design.players)
    bat = np.zeros((n_p, n_c))
    pit = np.zeros((n_p, n_c))
    for j in range(n_c):
        for k in range(2):
            bat[4 * j + k, j] = rng.normal(1.0, 1.5)
            pit[4 * j + 2 + k, j] = rng.normal(0.8, 1.2)
    rpw = np.full(n_c, 10.0)
    f = TA.Series(bat=bat, pit=pit, rpw=rpw)
    rows = [4 * j + 2 + k for j in range(n_c) for k in range(2)]
    shares = np.zeros((len(rows), n_c))
    for i, p in enumerate(rows):
        shares[i, (p - 2) // 4] = 1.0
    val = rng.normal(0.0, dep_sd, size=len(rows))
    seas = design.season[[(p - 2) // 4 for p in rows]]
    for s in np.unique(seas):
        m = seas == s
        val[m] -= val[m].mean()
    dep = TA.Departure(player=np.array(rows), season=seas, shares=shares, value=val)
    return f, dep


def test_identity_check_reads_zero_and_never_passes():
    design, rng = _design()
    f, _ = _series_and_dep(design, rng)
    out = TA.identity_check(design, f)
    assert out["all_d_zero"] and out["verdict"] != "PASS" and out["ok"]


def test_planted_truth_recovered_and_fake_rejected():
    design, rng = _design(n_seasons=6, n_clubs=20, seed=7)
    f, dep = _series_and_dep(design, rng, dep_sd=2.0)
    out = TA.planted(design, f, dep, reps=4, boot_b=60, perm_n=40, sigma_rd=20.0, sigma_w=2.0)
    assert out["truth_pass"] >= 3
    assert out["fake_pass"] <= 1
    assert out["planted_pass"] is True


def test_planted_check_reads_no_real_outcome():
    design, rng = _design(n_seasons=3, n_clubs=10, seed=3)
    f, dep = _series_and_dep(design, rng)
    a = TA.planted(design, f, dep, reps=2, boot_b=20, perm_n=10)
    weird = TA.Design(season=design.season, club=design.club, franchise=design.franchise, g=design.g,
                      w=design.w * 0 + 999, rs=design.rs * 3, ra=design.ra * 0.1,
                      players=design.players, seasons=design.seasons)
    b = TA.planted(weird, f, dep, reps=2, boot_b=20, perm_n=10)
    assert a["rows"] == b["rows"]


def test_score_without_null_or_planted_cannot_pass():
    design, rng = _design()
    f, dep = _series_and_dep(design, rng)
    e = TA.with_departure(f, dep, dep.value)
    syn = TA.synthetic_design(design, sum(e.sums()), f.rpw, rng, 1.0, 0.5)
    r = TA.score(syn, {"F": f, "B": f, "E": e}, "E", ("F", "B"), boot_b=40, perm_n=20)
    assert r["verdict"] == "NOT PASS"
    r = TA.score(syn, {"F": f, "B": f, "E": e}, "E", ("F", "B"), boot_b=40, perm_n=20,
                 dep=dep, null_key="F", planted_pass=False)
    assert r["verdict"].startswith("UNRESOLVED")


def test_permutation_keeps_season_sums():
    design, rng = _design()
    _, dep = _series_and_dep(design, rng)
    v = dep.permute(np.random.default_rng(5))
    for s in np.unique(dep.season):
        m = dep.season == s
        assert abs(v[m].sum() - dep.value[m].sum()) < 1e-9
    assert sorted(v) == sorted(dep.value)


def test_allocation_shares_fallbacks():
    assert TA.allocation_shares([("A", 300, 80), ("B", 100, 40)]) == {"A": 0.75, "B": 0.25}
    assert TA.allocation_shares([("A", 0, 3), ("B", 0, 1)]) == {"A": 0.75, "B": 0.25}
    assert TA.allocation_shares([("A", None, None), ("B", 0, 0)]) == {"A": 0.5, "B": 0.5}
    assert TA.allocation_shares([]) == {}


def test_predictions_reconcile_league_totals():
    design, rng = _design()
    f, _ = _series_and_dep(design, rng)
    bat, pit = f.sums()
    pred = TA.predictions(design, bat, pit, f.rpw)
    for s in design.seasons:
        m = design.season == s
        assert abs(pred["wins"][m].sum() - design.g[m].sum() / 2) < 1e-9
        assert abs(pred["rd"][m].sum()) < 1e-9


# ------------------------------------------------------------- the tool, on fixtures
CLUBS = sorted(set(__import__("ewar")._CLUB_TO_BREF.values()))


class FixtureInputs(LAB.Inputs):
    """Two full seasons and a 60-game one, 30 clubs, null WAR values, no Hx preview."""

    def __init__(self, seed=11):
        rng = np.random.default_rng(seed)
        self.seasons = (2016, 2017, 2020)
        self._vint = {"vintage_id": "fx", "fields": {
            "hitting": ["war", "plateAppearances"],
            "pitching": ["war", "gmli", "gamesPitched", "gamesStarted", "outs"]}, "seasons": {}}
        self._ev3 = {"fwar_vintage_id": "fx", "players": {}, "checks": {}}
        bat, pit = [], []
        self._stand = {}
        mid = 1000
        for s in self.seasons:
            games = 60 if s == 2020 else 162
            hit_rows, pit_rows = {}, {}
            deps = []
            for c in CLUBS:
                for k in range(3):
                    mid += 1
                    war = None if (k == 2 and c == CLUBS[0]) else float(rng.normal(1.5, 1.5))
                    hit_rows[str(mid)] = [war, 500]
                    bat.append({"mlb_ID": mid, "player_ID": f"x{mid}", "year_ID": s, "team_ID": c,
                                "PA": 500, "G": 120, "WAR": float(rng.normal(1.5, 1.5))})
                for k in range(2):
                    mid += 1
                    war = float(rng.normal(1.2, 1.2))
                    pit_rows[str(mid)] = [war, 1.0 + 0.2 * k, 30, 0 if k else 30, 300]
                    pit.append({"mlb_ID": mid, "player_ID": f"x{mid}", "year_ID": s, "team_ID": c,
                                "IPouts": 300, "G": 30, "WAR": float(rng.normal(1.2, 1.2))})
                    deps.append(mid)
            # one traded hitter, split by PA
            first = int(next(iter(hit_rows)))
            bat.append({"mlb_ID": first, "player_ID": f"x{first}", "year_ID": s, "team_ID": CLUBS[1],
                        "PA": 100, "G": 20, "WAR": 0.1})
            # one bWAR row with no MLBAM id
            bat.append({"mlb_ID": None, "player_ID": "nomlb", "year_ID": s, "team_ID": CLUBS[2],
                        "PA": 10, "G": 3, "WAR": -0.1})
            vals = rng.normal(0, 0.5, size=len(deps))
            vals -= vals.mean()
            for m, v in zip(deps, vals):
                self._ev3["players"].setdefault(str(m), {})[str(s)] = {"dr": {"pit": float(v)}, "dh": {}}
            self._ev3["checks"][str(s)] = {"rpw": 10.5, "r2_rounding_bound": 1e-6}
            self._vint["seasons"][str(s)] = {"hitting": {"rows": hit_rows}, "pitching": {"rows": pit_rows}}
            st = {}
            wins = rng.integers(games // 2 - 10, games // 2 + 10, size=30)
            wins = wins - (wins.sum() - 15 * games) // 30
            wins[0] += 15 * games - wins.sum()
            runs = rng.integers(600 if games == 162 else 220, 800 if games == 162 else 300, size=30)
            ra = np.roll(runs, 1)
            for i, c in enumerate(CLUBS):
                st[c] = {"w": int(wins[i]), "l": int(games - wins[i]), "rs": int(runs[i]), "ra": int(ra[i])}
            self._stand[s] = st
        self._bat = pd.DataFrame(bat)
        self._pit = pd.DataFrame(pit)

    def vintage(self):
        return self._vint

    def ewar_v3(self):
        return self._ev3

    def xhem_preview(self):
        return None

    def bwar(self, side):
        return self._bat if side == "bat" else self._pit

    def standings(self, seasons):
        return {s: self._stand[s] for s in seasons if s in self._stand}

    def fg_rpw(self, season):
        return 9.8

    def bref_rpw(self, bat, pit):
        return {}, {s: 9.6 for s in self.seasons}

    def park(self, season):
        return {c: (0.05 if i % 3 == 0 else -0.02) for i, c in enumerate(CLUBS)}

    def team_pitching(self, season):
        return {}

    def meta(self):
        return {"fixture": True}


@pytest.fixture
def small_constants(monkeypatch):
    monkeypatch.setattr(TA, "PRIMARY_SEASONS", (2016, 2017))
    monkeypatch.setattr(TA, "BOOT_B", 40)
    monkeypatch.setattr(TA, "PERM_N", 20)
    monkeypatch.setattr(TA, "PLANTED_REPS", 2)
    monkeypatch.setattr(TA, "PLANTED_B", 20)
    monkeypatch.setattr(TA, "PLANTED_PERM", 10)


def test_dry_run_on_fixtures_writes_every_block_and_refuses_a_second_read(tmp_path, small_constants):
    inp = FixtureInputs()
    out = tmp_path / "record.json"
    logs = []
    rec = LAB.run_read(inp, out, log=logs.append)
    assert out.exists()
    for k in ("inputs", "frame", "planted", "read", "miss", "sensitivity_2020"):
        assert k in rec
    assert rec["frame"]["xhem_preview"] == "absent"
    assert rec["frame"]["vintage_null_war"] == 2      # one per primary season
    assert rec["read"]["verdict"] in ("PASS", "NOT PASS",
                                      "UNRESOLVED (the design did not recover a planted departure)")
    assert set(rec["read"]["dispositions"]) == {"F", "B"}
    assert "Hx" not in rec["read"]["reported"]
    assert "sequencing" in rec["miss"]["E"]["wins"]["factors"]
    assert rec["miss"]["E"]["wins"]["factors"]["defense"] is None
    assert "points" in rec["sensitivity_2020"]
    assert any(line.startswith("scoring begins") for line in logs)
    assert logs.index("scoring begins") > max(i for i, line in enumerate(logs)
                                              if line.startswith("planted"))
    with pytest.raises(TA.AccountingRefusal):
        LAB.run_read(inp, out, log=logs.append)


def test_frame_refuses_unmapped_club(small_constants):
    inp = FixtureInputs()
    inp._bat.loc[0, "team_ID"] = "XXX"
    with pytest.raises(TA.AccountingRefusal):
        LAB.build_frame(inp, (2016, 2017), log=lambda *a: None)


def test_frame_refuses_unbalanced_standings(small_constants):
    inp = FixtureInputs()
    inp._stand[2016][CLUBS[0]]["rs"] += 1
    with pytest.raises(TA.AccountingRefusal):
        LAB.build_frame(inp, (2016, 2017), log=lambda *a: None)
