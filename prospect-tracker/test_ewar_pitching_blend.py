# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR pitching blend read's dry run on fixtures
(docs/ewar-v3/EWAR_PITCHING_BLEND_GATE.md part 11 step 1, task EWAR_PITCHING_BLEND).

Every reporting path runs on a synthetic design with null values, a missing source
and sparse cells; the runner-ownership walk charges runs as MLB does; the weight has
its limiting values; the planted machinery recovers a planted blend on a synthetic
design. Nothing here reads a cache, a served artifact or a real outcome.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ewar_pitching_blend as PB  # noqa: E402
import ewar_pitching_blend_lab as LAB  # noqa: E402
import ewar_team_accounting as TA  # noqa: E402
import test_ewar_team_accounting as TAT  # noqa: E402


# ------------------------------------------------------------------ the weight
def test_weight_limits():
    st_same = np.array([[0.25, 0.25], [0.25, 0.25]])
    se_f0 = np.array([[1e-12, 0.0], [0.0, 25.0]])
    # FanGraphs error-free and carrying all of the signal: w = 1
    assert PB.weight(st_same, se_f0, [100.0])[0] == pytest.approx(1.0, abs=1e-6)
    # runs allowed carry a part FIP misses: w falls as IP grows
    st = np.array([[0.25, 0.25], [0.25, 0.34]])
    se = np.array([[7.29, 6.75], [6.75, 25.0]])
    w = PB.weight(st, se, [5.0, 50.0, 200.0, 1e6])
    assert np.all(np.diff(w) < 0)
    assert w[-1] == pytest.approx(0.0, abs=1e-3)
    assert np.all((w >= 0) & (w <= 1))
    # no signal at all: w = 1 (the no-change blend)
    assert PB.weight(np.zeros((2, 2)), se, [50.0])[0] == 1.0


def test_oracle_weight_is_the_planted_formula():
    w_lo = PB.oracle_weight(0, 20.0)
    w_hi = PB.oracle_weight(0, 200.0)
    assert 0.0 <= w_hi < w_lo <= 1.0


def test_holm_and_decide():
    assert PB.holm({"i": 0.02, "ii": 0.04}) == {"i": True, "ii": True}
    assert PB.holm({"i": 0.03, "ii": 0.04}) == {"i": False, "ii": False}
    assert PB.holm({"i": 0.001, "ii": 0.06}) == {"i": True, "ii": False}
    assert PB.decide(0.001, 0.001, True, True)["verdict"] == "ADOPT"
    assert PB.decide(0.001, 0.001, None, True)["verdict"] == "NOT ADOPT"
    assert PB.decide(0.001, 0.001, False, True)["verdict"].startswith("UNRESOLVED")
    assert PB.decide(0.2, 0.001, True, True)["verdict"] == "NOT ADOPT"


def test_departure_repins_to_zero_and_is_zero_at_w_one():
    rng = np.random.default_rng(3)
    n = 40
    season = np.repeat([2016, 2017], n // 2)
    f9, b9 = rng.normal(0, 1, n), rng.normal(0, 1.5, n)
    b9[3] = np.nan
    ip = rng.uniform(5, 200, n)
    carry = np.ones(n, bool)
    carry[5] = False
    d = PB.departure_wins(f9, b9, np.full(n, 0.4), ip, np.full(n, 10.0), season, carry)
    for s in (2016, 2017):
        assert abs(d[season == s].sum()) < 1e-9
    assert d[5] == 0.0
    d1 = PB.departure_wins(f9, b9, np.ones(n), ip, np.full(n, 10.0), season, carry)
    assert np.all(d1 == 0.0)


def _pairs(n_per=60, seasons=(2017, 2018), seed=5, signal=0.5):
    rng = np.random.default_rng(seed)
    season = np.repeat(seasons, n_per)
    n = len(season)
    t = rng.normal(0, 1, n)
    f9 = t + rng.normal(0, 0.8, n)
    b9 = t + rng.normal(0, 1.2, n)
    target = signal * t + rng.normal(0, 1, n)
    return PB.Pairs(season=season, player=np.arange(n), club=rng.integers(0, 10, n), target=target,
                    series={"blend": 0.5 * f9 + 0.5 * b9, "F9": f9, "B9": b9})


def test_identity_check_reads_zero_and_never_passes():
    out = PB.identity_check(_pairs(), boot_b=50)
    assert out["all_zero"] and out["ok"] and out["gap_F9"] == 0.0


def test_test_i_cells_and_p():
    res = PB.test_i(_pairs(), boot_b=60, seed=1)
    assert set(res["cells"]) == {"F9", "B9"}
    for c in res["cells"].values():
        assert set(c["boot"]) == set(PB.BOOTS_I)
        assert all(0.0 <= v["p"] <= 1.0 for v in c["boot"].values())
    assert res["p_i"] == max(v["p"] for c in res["cells"].values() for v in c["boot"].values())


def test_spearman_ties_and_rank():
    assert PB._rank(np.array([3.0, 1.0, 3.0, 2.0])).tolist() == [3.5, 1.0, 3.5, 2.0]
    assert PB.spearman(np.array([1.0, 2.0, 3.0, 4.0]), np.array([10.0, 20.0, 30.0, 40.0])) == pytest.approx(1.0)


# ------------------------------------------------------------------ the walk
def _rec(plays, runners, pitchers, subs=None):
    return {"plays": pd.DataFrame(plays), "runners": pd.DataFrame(runners),
            "pitchers": pd.DataFrame(pitchers),
            "subs": pd.DataFrame(subs or [], columns=["game_pk", "player_id", "replaced_player_id"]),
            "source": "fixture"}


def test_walk_charges_runs_to_the_runner_owner():
    # A walks batter 11; B relieves, gives up a home run to 12: 11's run is A's, 12's is B's;
    # a pinch runner 21 for 13 (walked by B) scores on a double by 14 off B: B's.
    base = {"game_pk": 1, "half": "top", "inning": 1, "is_pa": True}
    plays = [
        dict(base, at_bat_index=0, batter_id=11, event_type="walk", outs_before=0, outs_after=0,
             on_first=None, on_second=None, on_third=None),
        dict(base, at_bat_index=1, batter_id=12, event_type="home_run", outs_before=0, outs_after=0,
             on_first=11, on_second=None, on_third=None),
        dict(base, at_bat_index=2, batter_id=13, event_type="walk", outs_before=0, outs_after=0,
             on_first=None, on_second=None, on_third=None),
        dict(base, at_bat_index=3, batter_id=14, event_type="double", outs_before=0, outs_after=0,
             on_first=21, on_second=None, on_third=None),
        dict(base, at_bat_index=4, batter_id=15, event_type="strikeout", outs_before=0, outs_after=3,
             on_first=None, on_second=14, on_third=None),
    ]
    runners = [
        {"game_pk": 1, "at_bat_index": 0, "runner_id": 11, "is_batter": True, "end": "1B", "is_out": False, "is_scoring": False},
        {"game_pk": 1, "at_bat_index": 1, "runner_id": 11, "is_batter": False, "end": "score", "is_out": False, "is_scoring": True},
        {"game_pk": 1, "at_bat_index": 1, "runner_id": 12, "is_batter": True, "end": "score", "is_out": False, "is_scoring": True},
        {"game_pk": 1, "at_bat_index": 2, "runner_id": 13, "is_batter": True, "end": "1B", "is_out": False, "is_scoring": False},
        {"game_pk": 1, "at_bat_index": 3, "runner_id": 21, "is_batter": False, "end": "score", "is_out": False, "is_scoring": True},
        {"game_pk": 1, "at_bat_index": 3, "runner_id": 14, "is_batter": True, "end": "2B", "is_out": False, "is_scoring": False},
        {"game_pk": 1, "at_bat_index": 4, "runner_id": 15, "is_batter": True, "end": None, "is_out": True, "is_scoring": False},
    ]
    pitchers = [{"game_pk": 1, "at_bat_index": a, "pitcher_id": (100 if a == 0 else 200)} for a in range(5)]
    app, cen = LAB.appearances(_rec(plays, runners, pitchers,
                                    [{"game_pk": 1, "player_id": 21, "replaced_player_id": 13}]), 2016)
    assert app[(1, 100)]["r"] == 1 and app[(1, 200)]["r"] == 2
    assert app[(1, 100)]["bb"] == 1 and app[(1, 200)]["hr"] == 1 and app[(1, 200)]["k"] == 1
    assert app[(1, 200)]["outs"] == 3 and app[(1, 100)]["outs"] == 0
    assert cen["runs"] == 3 and cen["runners_unplaced"] == 0


def test_walk_refuses_missing_pitchers():
    base = {"game_pk": 1, "half": "top", "inning": 1, "is_pa": True, "on_first": None,
            "on_second": None, "on_third": None, "event_type": "strikeout"}
    plays = [dict(base, at_bat_index=a, batter_id=10 + a, outs_before=a, outs_after=a + 1) for a in range(3)]
    runners = [{"game_pk": 1, "at_bat_index": a, "runner_id": 10 + a, "is_batter": True, "end": None,
                "is_out": True, "is_scoring": False} for a in range(3)]
    with pytest.raises(PB.BlendRefusal):
        LAB.appearances(_rec(plays, runners, [{"game_pk": 1, "at_bat_index": 0, "pitcher_id": 5}]), 2016)


# ------------------------------------------------------------------ the tool, on fixtures
SEASONS = (2016, 2017, 2018)


class FixtureInputs(LAB.Inputs):
    """Three seasons built on the team accounting fixture's clubs and pitchers (2018
    repeats 2017's pitchers so 2017 has pairs); a null fipMinus, a pitcher missing from
    the Baseball-Reference copy, a nopp row, and sparse cells."""

    def __init__(self, seed=17):
        rng = np.random.default_rng(seed)
        self.ta = TAT.FixtureInputs()
        vint = copy.deepcopy(self.ta._vint)
        vint["fields"]["pitching"] = vint["fields"]["pitching"] + ["fip", "fipMinus"]
        mids = {}
        for s in (2016, 2017):
            mids[s] = [int(m) for m in vint["seasons"][str(s)]["pitching"]["rows"]]
        mids[2018] = list(mids[2017])
        pit_rows_2017 = vint["seasons"]["2017"]["pitching"]["rows"]
        vint["seasons"]["2018"] = {"hitting": {"rows": {}},
                                   "pitching": {"rows": {k: list(v) for k, v in pit_rows_2017.items()}}}
        club_of = {}
        for r in self.ta._pit.itertuples(index=False):
            club_of[(int(r.year_ID), int(r.mlb_ID))] = r.team_ID
        for m in mids[2018]:
            club_of[(2018, m)] = club_of[(2017, m)]
        self._plays = {}
        bref = []
        self._prev = {"fwar_vintage_id": "fx", "seasons": {}}
        game = 10000
        for s in SEASONS:
            rows = vint["seasons"][str(s)]["pitching"]["rows"]
            plays, runners, pitchers = [], [], []
            prev_p = []
            for k, m in enumerate(mids[s]):
                vals = rows[str(m)]
                role_sp = vals[3] > 0
                n_g = 6
                outs_total = 0
                bid = 500000
                for g in range(n_g):
                    game += 1
                    innings = 3 if role_sp else 1
                    a = 0
                    for inn in range(innings):
                        outs = 0
                        on1 = None
                        while outs < 3:
                            bid += 1
                            u = rng.random()
                            ev = "strikeout" if u < 0.35 else "field_out" if u < 0.7 else "walk" if u < 0.85 else "home_run"
                            ob = outs
                            row = {"game_pk": game, "half": "top", "inning": inn + 1, "at_bat_index": a,
                                   "batter_id": bid, "event_type": ev, "is_pa": True, "outs_before": ob,
                                   "on_first": on1, "on_second": None, "on_third": None}
                            if ev in ("strikeout", "field_out"):
                                outs += 1
                                runners.append({"game_pk": game, "at_bat_index": a, "runner_id": bid,
                                                "is_batter": True, "end": None, "is_out": True, "is_scoring": False})
                            elif ev == "walk":
                                if on1 is not None:
                                    runners.append({"game_pk": game, "at_bat_index": a, "runner_id": on1,
                                                    "is_batter": False, "end": "score", "is_out": False,
                                                    "is_scoring": True})
                                runners.append({"game_pk": game, "at_bat_index": a, "runner_id": bid,
                                                "is_batter": True, "end": "1B", "is_out": False, "is_scoring": False})
                                on1 = bid
                            else:
                                if on1 is not None:
                                    runners.append({"game_pk": game, "at_bat_index": a, "runner_id": on1,
                                                    "is_batter": False, "end": "score", "is_out": False,
                                                    "is_scoring": True})
                                runners.append({"game_pk": game, "at_bat_index": a, "runner_id": bid,
                                                "is_batter": True, "end": "score", "is_out": False, "is_scoring": True})
                                on1 = None
                            row["outs_after"] = outs
                            plays.append(row)
                            pitchers.append({"game_pk": game, "at_bat_index": a, "pitcher_id": m})
                            a += 1
                        outs_total += 3
                fi = vint["fields"]["pitching"]
                vals[fi.index("outs")] = outs_total
                vals.append(float(rng.normal(4.0, 0.6)))                         # fip
                vals.append(None if (s == 2016 and k == 0) else float(rng.normal(100, 15)))  # fipMinus
                if not (s == 2017 and k == 1):
                    bref.append({"mlb_ID": m, "player_ID": f"x{m}", "year_ID": s, "team_ID": club_of[(s, m)],
                                 "IPouts": outs_total, "G": n_g, "WAR": float(rng.normal(1, 1)),
                                 "runs_above_avg": float(rng.normal(0, 4))})
                prev_p.append({"mlbam": m, "nopp": bool(s == 2016 and k == 2),
                               "ra9_star": float(rng.normal(4.2, 1.0)), "ip": outs_total / 3.0})
            self._plays[s] = {"plays": pd.DataFrame(plays), "runners": pd.DataFrame(runners),
                              "pitchers": pd.DataFrame(pitchers),
                              "subs": pd.DataFrame([], columns=["game_pk", "player_id", "replaced_player_id"]),
                              "source": "fixture"}
            self._prev["seasons"][str(s)] = {"pitchers": prev_p}
        self._vint = vint
        self.ta._vint = vint
        # the yardstick reads the same pitchers' IPouts from its own copy
        pit = self.ta._pit.copy()
        outs_by = {(int(b["year_ID"]), int(b["mlb_ID"])): b["IPouts"] for b in bref}
        pit["IPouts"] = [outs_by.get((int(y), int(m)), 3) for y, m in zip(pit["year_ID"], pit["mlb_ID"])]
        self.ta._pit = pit
        self._bref = pd.DataFrame(bref)

    def vintage(self):
        return self._vint

    def preview(self):
        return self._prev

    def bwar_pit(self):
        return self._bref

    def plays(self, season):
        return self._plays.get(int(season))

    def fg_rpw(self, season):
        return 9.8

    def ewar_v3(self):
        return self.ta._ev3

    def team_accounting(self):
        return self.ta

    def meta(self):
        return {"fixture": True}


@pytest.fixture
def small_constants(monkeypatch):
    monkeypatch.setattr(PB, "FIT_SEASONS", SEASONS)
    monkeypatch.setattr(PB, "PREDICTOR_SEASONS", (2017,))
    monkeypatch.setattr(PB, "CELL_MIN", 3)
    monkeypatch.setattr(PB, "SPLIT_MIN_IP", 1.0)
    monkeypatch.setattr(PB, "PAIR_FLOOR_IP", 1.0)
    monkeypatch.setattr(PB, "BOOT_B", 30)
    monkeypatch.setattr(PB, "PLANTED_REPS", 2)
    monkeypatch.setattr(PB, "PLANTED_B", 20)
    monkeypatch.setattr(TA, "PRIMARY_SEASONS", (2016, 2017))
    monkeypatch.setattr(TA, "BOOT_B", 30)
    monkeypatch.setattr(TA, "PERM_N", 10)
    monkeypatch.setattr(TA, "PLANTED_REPS", 2)
    monkeypatch.setattr(TA, "PLANTED_B", 20)
    monkeypatch.setattr(TA, "PLANTED_PERM", 10)


def test_frame_on_fixtures_counts_nulls_and_missing_source(small_constants):
    fr = LAB.build_frame(FixtureInputs(), log=lambda *a: None)
    cen = fr["census"]
    assert cen["seasons"]["2016"]["nopp"] == 1
    assert cen["seasons"]["2017"]["without_bref"] == 1
    assert cen["rows"]["both_sources"] < cen["rows"]["n"]
    assert cen["pairs"]["n"] > 0
    assert all(cen["seasons"][str(s)]["outs"] == cen["seasons"][str(s)]["league_outs_vintage"] for s in (2017, 2018))


def test_dry_run_on_fixtures_writes_every_block_and_refuses_a_second_read(tmp_path, small_constants):
    inp = FixtureInputs()
    out = tmp_path / "record.json"
    logs = []
    rec = LAB.run_read(inp, out, log=logs.append)
    assert out.exists()
    for k in ("inputs", "frame", "planted", "identity", "weights", "test_i", "test_ii", "decision",
              "reported_floor_20"):
        assert k in rec
    assert rec["decision"]["verdict"] in ("ADOPT", "NOT ADOPT",
                                          "UNRESOLVED (the design did not recover a planted blend)")
    assert set(rec["test_i"]["cells"]) == {"F9", "B9", "half", "RA9s_Y"}
    assert rec["test_ii"]["cell"]["k_star"] in ("F", "B")
    assert any(t["source"] != "cell" for t in rec["weights"]["build"])   # a sparse cell pooled
    assert rec["identity"]["ok"]
    assert logs.index("scoring begins") > max(i for i, line in enumerate(logs) if line.startswith("planted"))
    with pytest.raises(PB.BlendRefusal):
        LAB.run_read(inp, out, log=logs.append)


def test_planted_machinery_recovers_truth_on_a_synthetic_design():
    rng = np.random.default_rng(2)
    seasons = (2016, 2017, 2018, 2019)
    n_pl = 260
    season, player, role, ip, ipo, ipe = [], [], [], [], [], []
    for p in range(n_pl):
        r = p % 2
        for s in seasons:
            v = float(rng.uniform(60, 200) if r == 0 else rng.uniform(30, 80))
            season.append(s)
            player.append(p)
            role.append(r)
            ip.append(v)
            ipo.append(v / 2)
            ipe.append(v / 2)
    n = len(season)
    rows = PB.Rows(season=season, player=player, role=role, ip=ip, f9=np.zeros(n), b9=np.zeros(n),
                   ip_o=ipo, ip_e=ipe, f_o=np.zeros(n), f_e=np.zeros(n), b_o=np.zeros(n), b_e=np.zeros(n))
    at = {(s, p): i for i, (s, p) in enumerate(zip(season, player))}
    py = [at[(s, p)] for (s, p) in at if s in (2017, 2018)]
    py1 = [at[(rows.season[i] + 1, rows.player[i])] for i in py]
    pd_ = PB.PlantedDesign(rows=rows, pair_y=np.array(py), pair_y1=np.array(py1),
                           pair_club=np.array(py) % 30, seasons=seasons)
    out = PB.planted(pd_, reps=3, boot_b=60, seed=7)
    # the machinery, not the power of this small design: the truth world's blend beats F9,
    # the fake world's does not, and the fitted weights sit near the oracle's
    assert np.mean([x["gap_F9"] for x in out["truth"]]) > 0
    assert np.mean([x["gap_F9"] for x in out["fake"]]) < 0
    assert out["fake_pass"] <= 1
    assert out["w_mean_abs_diff"] < 0.2
    assert set(out) >= {"truth_pass", "fake_pass", "w_mean_abs_diff", "planted_pass"}
