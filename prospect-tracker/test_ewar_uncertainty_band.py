# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The eWAR uncertainty band's core and its fixture dry run
(docs/ewar-v3/EWAR_UNCERTAINTY_BAND_GATE.md part 11 step 1, amendment 13.1).

Every reporting path of tools/ewar_uncertainty_band_lab.py runs here on a synthetic
league with null values, a short family and an empty exposure band; the planted
machinery recovers a planted band on a synthetic design. No real input is read.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import ewar_uncertainty_band as U  # noqa: E402
import ewar_uncertainty_band_lab as L  # noqa: E402


# ------------------------------------------------------------------ the core
def test_season_roles_and_bands():
    assert [U.role(s) for s in (2000, 2001, 2002, 2003)] == ["TEST", "FIT", "CAL", "TEST"]
    assert U.role(2020) is None and U.role(2026) is None
    assert [U.role(s) for s in (2018, 2019, 2023, 2024, 2025)] == ["TEST", "FIT", "CAL", "TEST", "FIT"]
    assert U.band_index("bat", 19.9) is None and U.band_index("bat", 20) == 0
    assert U.band_index("bat", 299) == 1 and U.band_index("bat", 500) == 3
    assert U.band_index("pit", 4.9) is None and U.band_index("pit", 60) == 2
    assert U.band_index("pit", None) is None and U.band_index("pit", float("nan")) is None
    assert U.EQUIV == (0.70, 0.90) and U.TRAIN_ROLES == ("FIT", "CAL")


def _fam(name, rows, k=1.0, seed=3, excess=1.0, D=True):
    rng = np.random.default_rng(seed)
    side = U.FAMILY_SIDE[name]
    seasons = rng.choice([2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024], rows)
    e = (rng.choice([40, 150, 400, 600], rows) if side == "bat" else rng.choice([10, 40, 80, 150], rows)) * \
        rng.uniform(0.8, 1.2, rows)
    band = np.array([U.band_index(side, x) for x in e])
    if U.FAMILY_KIND[name] == "c1":
        g, s = 2 * e, np.ones(rows)
    else:
        ea = e * rng.uniform(0.3, 0.7, rows)
        g, s = e * e * (1 / ea + 1 / (e - ea)), e * e
    fam = U.Family(name, seasons, band, g, s, rng.integers(0, rows // 3, rows), rng.integers(0, 30, rows),
                   n1_k=(k if U.FAMILY_KIND[name] == "c1" else None))
    if D:
        fam = fam.with_D(np.sqrt(k * g) * rng.standard_normal(rows) * np.where(band == 0, excess, 1.0))
        fam.n1_k = k if U.FAMILY_KIND[name] == "c1" else None
    return fam


def test_fit_k_is_the_registered_formula():
    xa, xb = np.array([0.1, -0.2, 0.05]), np.array([0.0, 0.1, -0.05])
    ea, eb = np.array([50.0, 200.0, 300.0]), np.array([60.0, 180.0, 310.0])
    rows = [U.c2_row(a, b, c, d) for a, b, c, d in zip(xa, xb, ea, eb)]
    fam = U.Family("C2-bat", [2016] * 3, [1, 3, 3], [r[1] for r in rows], [r[2] for r in rows], [1, 2, 3],
                   [1, 1, 1], D=[r[0] for r in rows])
    want = float(np.sum((xa - xb) ** 2) / np.sum(1 / ea + 1 / eb))
    assert U.fit_k(fam) == pytest.approx(want)
    d, e = np.array([1.0, -2.0]), np.array([300.0, 600.0])
    rows = [U.c1_row(x, y) for x, y in zip(d, e)]
    fam = U.Family("C1-bat", [2017, 2016], [2, 3], [r[1] for r in rows], [r[2] for r in rows], [1, 2], [1, 2],
                   D=[r[0] for r in rows])
    assert U.fit_k(fam) == pytest.approx(float(np.sum(d * d) / (2 * np.sum(e))))
    assert U.c2_row(None, 0.1, 10, 10)[0] is None


def test_multipliers_always_applied_and_conformal():
    fam = _fam("C1-bat", 4000, excess=2.0)
    k = U.fit_k(fam)
    mult = U.multipliers(fam, k)
    assert all(v["applied"] for v in mult.values())
    assert mult[0]["m"] > 1.4 and mult[0]["raw_coverage"] < 0.7
    off = U.multipliers(fam, k, apply=False)
    assert all(v["m"] == 1.0 and not v["applied"] for v in off.values())


def test_score_calibrated_on_a_true_band_and_fails_an_empty_cell():
    fams = {n: _fam(n, 6000, seed=i) for i, (n, _, _) in enumerate(U.FAMILIES)}
    res = U.score(fams, n_rep=200)
    assert len(res["cells"]) == 24
    assert res["calibrated"], res["failing_cells"]
    assert res["families"]["C2-bat"]["comparisons"]["n1"]["win"]
    assert not res["families"]["C1-bat"]["comparisons"]["n1"]["deciding"]
    short = dict(fams)
    f = fams["C2-fip"]
    keep = f.band != 3
    short["C2-fip"] = U.Family("C2-fip", f.season[keep], f.band[keep], f.g[keep], f.s[keep], f.player[keep],
                               f.club[keep], D=f.D[keep])
    res2 = U.score(short, n_rep=100)
    assert not res2["calibrated"] and "C2-fip IP 120+" in res2["failing_cells"]
    assert U.disposition(res, False).startswith("UNRESOLVED")
    assert U.disposition(res2, True) == "NOT PASS"


def test_planted_machinery_recovers_a_planted_band():
    design = {n: _fam(n, 8000, seed=10 + i, D=False) for i, (n, _, _) in enumerate(U.FAMILIES)}
    pl = U.planted(design, n_rep=3, n_boot=150)
    assert pl["truth_pass"] >= 2 and pl["broken_pass"] == 0
    assert U.identity_check(_fam("C1-pit", 500))


def test_served_sigma_form():
    c = {"k": {"src_bat": 0.0005, "src_pit": 0.004, "bat": 0.25, "ebr": 0.01, "fip": 0.9, "ra": 2.0},
         "m": {t: [1.0, 1.1, 1.0, 0.9] for t in U.TERM_FAMILY}}
    sg = U.sigma(c, pa=600, ip=None, rpw=10.0)
    want_samp = (0.81 * 0.25 * 600 + 0.81 * 0.01 * 600) / 100.0
    want_src = 0.81 * 0.0005 * 600
    assert sg["sigma"] == pytest.approx(math.sqrt(want_samp + want_src))
    real = U.sigma(c, pa=None, ip=150, rpw=10.0, pit_basis="ra")
    assert real["samp"] == pytest.approx(math.sqrt(0.81 * 2.0 * 150 / 100.0))
    assert U.sigma(c, pa=10, ip=2, rpw=10.0) is None
    res = {"families": {f: {"k": 1.0, "multipliers": {b: {"m": 1.0} for b in range(4)}} for f, _, _ in U.FAMILIES}}
    assert set(U.constants_from(res)["k"]) == set(U.TERM_FAMILY)


# ------------------------------------------------------------------ the lab on fixtures
class FakeInputs(L.Inputs):
    """A synthetic league: two families of seasons, null values in every series."""

    def __init__(self, seed=5, n=420):
        import pandas as pd
        self.pd = pd
        self.rng = np.random.default_rng(seed)
        self.n = n
        self._bwar = None
        self._vint = None
        self._pa = {}
        self._plays = {}

    def vintage(self):
        if self._vint is None:
            rng = self.rng
            seasons = {}
            for s in sorted(set(L.C1_SEASONS) | set(L.SERVED_SEASONS)):
                hit, pit = {}, {}
                for i in range(self.n):
                    pa = int(rng.integers(5, 700))
                    war = None if i % 97 == 0 else float(rng.normal(1, 2))
                    hit[str(100000 + i)] = [war] + [0.0] * 10 + [pa] + [0.0] * 6
                    outs = int(rng.integers(6, 600))
                    pit[str(200000 + i)] = [float(rng.normal(1, 2))] + [0.0] * 14 + [outs, 10, 0]
                seasons[str(s)] = {"hitting": {"rows": hit}, "pitching": {"rows": pit}}
            fh = ["war", "rar", "batting", "baseRunning", "fielding", "positional", "wLeague", "replacement",
                  "wSb", "ubr", "wGdp", "plateAppearances", "numTeams", "woba", "wRaa", "wRc", "wRcPlus", "spd"]
            fp = ["war", "rar", "fip", "xfip", "ra9War", "gmli", "exli", "pli", "inli", "eraMinus", "fipMinus",
                  "md", "sd", "numTeams", "inningsPitched", "outs", "gamesPitched", "gamesStarted"]
            self._vint = {"vintage_id": "fixture", "fields": {"hitting": fh, "pitching": fp}, "seasons": seasons}
        return self._vint

    def ewar_v3(self):
        players = {}
        for i in range(0, self.n, 3):
            players[str(200000 + i)] = {str(s): {"dr": {"pit": 0.1}, "parts": {"r2": 0.1}}
                                        for s in L.C1_SEASONS if s >= 2016}
        return {"fwar_vintage_id": "fixture", "players": players}

    def bwar(self, side):
        if self._bwar is None:
            vint = self.vintage()
            rows = {"bat": [], "pit": []}
            for s, blk in vint["seasons"].items():
                for mid, v in blk["hitting"]["rows"].items():
                    w = None if int(mid) % 89 == 0 else (v[0] or 0.0) + float(self.rng.normal(0, 0.3))
                    rows["bat"].append({"mlb_ID": int(mid), "year_ID": int(s), "team_ID": f"T{int(mid) % 30}",
                                        "PA": v[11], "WAR": w, "player_ID": f"p{mid}", "G": 10})
                for mid, v in blk["pitching"]["rows"].items():
                    rows["pit"].append({"mlb_ID": int(mid), "year_ID": int(s), "team_ID": f"T{int(mid) % 30}",
                                        "IPouts": v[15], "WAR": v[0] + float(self.rng.normal(0, 0.4)),
                                        "player_ID": f"q{mid}", "G": 10})
            self._bwar = {k: self.pd.DataFrame(v) for k, v in rows.items()}
        return self._bwar[side]

    def woba(self, season):
        return {"ubb": 0.69, "hbp": 0.72, "1b": 0.88, "2b": 1.25, "3b": 1.58, "hr": 2.03}, 1.23

    def rpw(self, season):
        return 10.0

    def runner_pa(self, season):
        if season not in self._pa:
            rng = np.random.default_rng(season)
            evs = np.array(["field_out", "strikeout", "single", "double", "walk", "home_run", "hit_by_pitch"])
            p = np.array([0.45, 0.22, 0.15, 0.05, 0.08, 0.03, 0.02])
            recs = []
            for i in range(self.n):
                n_pa = int(rng.integers(10, 650))
                games = rng.integers(0, 400, n_pa)
                ev = rng.choice(evs, n_pa, p=p)
                for j in range(n_pa):
                    recs.append((int(games[j]), j, 100000 + i, 100 + i % 30, 130 + i % 30, ev[j], True))
            self._pa[season] = self.pd.DataFrame(recs, columns=["game_pk", "at_bat_index", "batter_id",
                                                                "bat_team_id", "fld_team_id", "event_type",
                                                                "is_pa"])
        return self._pa[season]

    def corpus_plays(self, season):
        if season not in self._plays:
            rng = np.random.default_rng(season + 7)
            evs = np.array(["field_out", "strikeout", "single", "walk", "home_run", "intent_walk"])
            p = np.array([0.5, 0.23, 0.17, 0.07, 0.025, 0.005])
            recs = []
            for i in range(self.n):
                n_pa = int(rng.integers(20, 900))
                games = rng.integers(0, 400, n_pa)
                ev = rng.choice(evs, n_pa, p=p)
                for j in range(n_pa):
                    out = 1 if ev[j] in ("field_out", "strikeout") else 0
                    recs.append((int(games[j]), j, 200000 + i, ev[j], 0, out, int(ev[j] == "home_run")))
            self._plays[season] = self.pd.DataFrame(recs, columns=["game_pk", "at_bat_index", "pitcher_id",
                                                                   "event_type", "outs_before", "outs_after",
                                                                   "runs_scored_on_play"])
        return self._plays[season]

    def ebr_credits(self, season):
        rng = np.random.default_rng(season + 11)
        return [(100000 + i, "T", int(rng.integers(0, 400)), "sb", float(rng.normal(0, 0.2)))
                for i in range(self.n) for _ in range(5)] + [(None, "T", 1, "sb", 0.3)]

    def n1_constants(self, bat_df, pit_df):
        return {"bat": 0.0005, "pit": 0.004, "source": "fixture"}

    def meta(self):
        return {"fixture": True}


@pytest.fixture()
def small_frame(monkeypatch):
    monkeypatch.setattr(L, "C1_SEASONS", (2016, 2017, 2018))
    monkeypatch.setattr(L, "C2_BAT_SEASONS", (2016, 2017, 2018))
    monkeypatch.setattr(L, "C2_PIT_SEASONS", (2018, 2019, 2023))
    monkeypatch.setattr(L, "SERVED_SEASONS", (2016, 2017, 2018, 2026))
    monkeypatch.setattr(U, "MIN_TEST_ROWS", 5)
    monkeypatch.setattr(U, "MIN_CAL_ROWS", 5)
    return FakeInputs()


def test_lab_dry_run_every_reporting_path(small_frame, tmp_path, capsys):
    rep = L.Reporter()
    record = L.run_read(small_frame, rep, n_boot=60, planted_reps=2, planted_boot=40)
    assert record["disposition"] in ("PASS", "NOT PASS", "UNRESOLVED (the design did not recover a planted band)")
    assert len(record["cells"]) == 24
    assert set(record["families"]) == {n for n, _, _ in U.FAMILIES}
    assert record["planted"]["identity_check"] is True
    assert record["n1"]["source"] == "fixture"
    rc = record["reported"]["c1_realized_pit"]
    assert len(rc) == 4 and any(r["n"] for r in rc)
    sc = record["reported"]["served"]
    assert set(sc["median_half_width_wins"]) == {"headline", "realized"}
    assert "2026" in sc["counts"]
    blob = json.dumps(L._jsonable(record))
    assert "NaN" not in blob
    out = capsys.readouterr().out
    assert "VERDICT:" in out and "PLANTED CHECK" in out and "INTERVAL SCORE" in out


def test_frame_refuses_a_short_family(small_frame, monkeypatch):
    monkeypatch.setattr(U, "MIN_TEST_ROWS", 10 ** 6)
    with pytest.raises(U.BandRefusal):
        L.build_frame(small_frame, with_values=False, log=lambda s: None)


def test_frame_refuses_a_vintage_mismatch(small_frame, monkeypatch):
    monkeypatch.setattr(FakeInputs, "ewar_v3", lambda self: {"fwar_vintage_id": "other", "players": {}})
    with pytest.raises(U.BandRefusal):
        L.build_frame(small_frame, with_values=False, log=lambda s: None)


def test_second_read_refuses(tmp_path):
    out = tmp_path / "record.json"
    out.write_text("{}", encoding="utf-8")
    assert L.main(["--read", "--out", str(out)]) == 2
