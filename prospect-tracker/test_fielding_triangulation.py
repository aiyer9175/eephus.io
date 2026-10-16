# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""fielding_triangulation.py and tools/fielding_triangulation_lab.py on fixtures
(docs/ewar/FIELDING_TRIANGULATION_GATE.md).

Pins the part 4 invariants, that the fit reads no season after 2018, the whole
reporting path on fixtures with nulls (catchers without OAA or UZR, no UZR after
2024, SDR only on 300-inning rows from 2017, players without a vintage row), a
planted recovery (readings of one persistent skill: the triangulation must load the
low-noise readings, beat a single reading on L1 at LB95, and its twin must fail),
and a null comparator (readings of pure noise: L1 never passes).
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

import fielding_triangulation as FT          # noqa: E402
import fielding_triangulation_lab as L       # noqa: E402

TEAMS = list(range(1, 31))


def fixture_inputs(seed: int = 7, planted: bool = True, n_players: int = 520) -> L.Inputs:
    rng = np.random.default_rng(seed)
    positions = list(FT.NONC_POS) + [FT.CATCHER]
    rows, split, vint, rf = [], [], [], []
    theta = rng.normal(0, 10, n_players)
    pos_of = rng.choice(positions, n_players)
    team_of = rng.choice(TEAMS, n_players)
    defense = {}
    for s in L.SEASONS:
        theta = 0.8 * theta + 0.6 * rng.normal(0, 10, n_players)
        sig = theta if planted else np.zeros(n_players)
        team_of = np.where(rng.random(n_players) < 0.3, rng.choice(TEAMS, n_players), team_of)
        inn = rng.uniform(120, 1400, n_players)
        sc = np.sqrt(1000.0 / inn)
        shared_sc = rng.normal(0, 1, n_players)
        shared_sis = rng.normal(0, 1, n_players)
        e = {k: rng.normal(0, 1, n_players) for k in ("oaa", "frp", "drs", "uzr")}
        rate = {
            "oaa": sig + 6 * sc * (0.3 * shared_sc + 0.95 * e["oaa"]),
            "frp": sig + 7 * sc * (0.3 * shared_sc + 0.95 * e["frp"]),
            "drs": 0.9 * sig + 9 * sc * (0.5 * shared_sis + 0.87 * e["drs"]),
            "uzr": 0.9 * sig + 10 * sc * (0.5 * shared_sis + 0.87 * e["uzr"]),
        }
        for i in range(n_players):
            pos = pos_of[i]
            n = float(inn[i])
            r = {"player_id": 1000 + i, "season": s, "pos": pos, "inn": n}
            for k in ("drs", "uzr", "oaa", "frp"):
                r[k] = rate[k][i] * n / 1000.0
            if pos == FT.CATCHER:
                r["oaa"] = np.nan
                r["uzr"] = np.nan
                r["cframing"] = (0.8 * sig[i] + 8 * sc[i] * rng.normal()) * n / 1000.0
                r["bfrp"] = (0.2 * sig[i] + 3 * sc[i] * rng.normal()) * n / 1000.0
                r["tfrp"] = (0.2 * sig[i] + 3 * sc[i] * rng.normal()) * n / 1000.0
            else:
                r["cframing"] = r["bfrp"] = r["tfrp"] = np.nan
            if s >= 2025:
                r["uzr"] = np.nan
            if pos != FT.CATCHER and rng.random() < 0.08:
                r["oaa"] = np.nan
            if s >= 2017 and n >= 300 and pos != FT.CATCHER:
                z = [r[k] for k in ("oaa", "drs", "frp") if np.isfinite(r[k])]
                shr = n / (n + 269)
                r["sdr"] = shr * float(np.mean(z))
                r["sdr_no_drs"] = shr * float(np.mean([r[k] for k in ("oaa", "frp") if np.isfinite(r[k])]))
                r["sdr_no_statcast"] = shr * r["drs"]
            else:
                r["sdr"] = r["sdr_no_drs"] = r["sdr_no_statcast"] = np.nan
            rows.append(r)
            split.append({"season": s, "player_id": 1000 + i, "teamid": int(team_of[i]), "inn": n})
            if i % 37 != 0:
                vint.append({"player_id": 1000 + i, "season": s,
                             "fld": r["frp"] if pos != FT.CATCHER else (r["bfrp"] + r["tfrp"]),
                             "frm": r["cframing"] if pos == FT.CATCHER else 0.0, "pa": 450.0})
            rf.append({"player_id": 1000 + i, "season": s, "runs_field": r["drs"], "inn": n})
            defense[(s, int(team_of[i]))] = defense.get((s, int(team_of[i])), 0.0) + sig[i] * n / 1000.0
    team = {}
    for s in L.SEASONS:
        fip = rng.normal(4.2, 0.3, len(TEAMS))
        ip = np.full(len(TEAMS), 1450.0)
        runs = fip * ip / 9 - np.array([defense.get((s, t), 0.0) for t in TEAMS]) + rng.normal(0, 12, len(TEAMS))
        team[s] = pd.DataFrame({"teamid": TEAMS, "R": runs, "FIP": fip, "IP": ip})
    return L.Inputs(rows=pd.DataFrame(rows), split=pd.DataFrame(split), team=team,
                    vintage=pd.DataFrame(vint), rfield=pd.DataFrame(rf), meta={"fixture": seed})


@pytest.fixture(scope="module")
def planted():
    inp = fixture_inputs(7, planted=True)
    fitd = L.fit(inp)
    return inp, fitd, L.evaluate(inp, fitd, b=120, log=lambda *a: None)


@pytest.fixture(scope="module")
def null():
    inp = fixture_inputs(11, planted=False)
    fitd = L.fit(inp)
    return inp, fitd, L.evaluate(inp, fitd, b=120, log=lambda *a: None)


# ---------------------------------------------------------------------------
# part 4 invariants
# ---------------------------------------------------------------------------

def _toy_model():
    return {"series": ["oaa", "frp"], "lambda": [8.0, 9.0],
            "A": [[90.0, 60.0], [60.0, 100.0]], "Psi": [[2000.0, 300.0], [300.0, 2500.0]]}


def test_a_row_with_no_reading_carries_zero():
    assert FT.t_rate(_toy_model(), {}, 900.0, ("oaa", "frp")) == 0.0
    assert FT.t_rate(_toy_model(), {"oaa": np.nan}, 900.0, ("oaa", "frp")) == 0.0


def test_one_reading_closed_form():
    m = _toy_model()
    got = FT.t_rate(m, {"oaa": 5.0}, 800.0, ("oaa", "frp"))
    want = 9.0 * 8.0 * 5.0 / (90.0 + 2000.0 * 1000.0 / 800.0)
    assert got == pytest.approx(want, rel=1e-12)


def test_an_absent_reading_changes_nothing():
    m = _toy_model()
    rows = pd.DataFrame({"inn": [500.0, 1200.0], "x_oaa": [3.0, -2.0], "x_frp": [1.0, 4.0]})
    base = FT.t_rates(m, rows, ("oaa", "frp"))
    rows2 = rows.assign(x_sdr=np.nan)
    assert np.allclose(base, FT.t_rates(m, rows2, ("sdr", "oaa", "frp")))


def test_fewer_innings_shrink_harder():
    m = _toy_model()
    lo = FT.t_rate(m, {"oaa": 5.0, "frp": 5.0}, 200.0, ("oaa", "frp"))
    hi = FT.t_rate(m, {"oaa": 5.0, "frp": 5.0}, 1400.0, ("oaa", "frp"))
    assert 0 < lo < hi


def test_season_part_recentres_to_zero_and_pitcher_batters_carry_zero():
    rows = {1: {"t_runs": 4.0, "fld": 2.0, "frm": 0.0, "caught": False, "pa": 600},
            2: {"t_runs": -3.0, "fld": -6.0, "frm": 5.0, "caught": True, "pa": 450},
            3: {"t_runs": 0.0, "fld": 0.0, "frm": None, "caught": False, "pa": 20},
            4: {"t_runs": 9.0, "fld": 1.0, "frm": 0.0, "caught": False, "pa": 3, "pitcher_batter": True}}
    out = FT.season_part(rows)
    assert abs(sum(v["d"] for k, v in out.items() if k != 4)) < 1e-9
    assert out[4] == {"g": 0.0, "d": 0.0}
    assert out[2]["g"] == pytest.approx(-3.0 - (-6.0 + 5.0))
    assert out[1]["g"] == pytest.approx(2.0)


def test_catcher_k_unfitted_or_infinite_gives_zero():
    rows = pd.DataFrame({"inn": [700.0], "x_framing": [10.0], "x_blocking": [2.0], "x_throwing": [1.0]})
    none = {c: {"K": None} for c in FT.CATCHER_COMPONENTS}
    assert FT.catcher_runs(none, rows)[0] == 0.0
    big = {c: {"K": 1e15} for c in FT.CATCHER_COMPONENTS}
    assert abs(FT.catcher_runs(big, rows)[0]) < 1e-9


def test_no_fg_leaderboards_import_and_no_ewar_json_write():
    for p in (ROOT / "fielding_triangulation.py", ROOT / "tools" / "fielding_triangulation_lab.py"):
        src = p.read_text(encoding="utf-8")
        assert "fg_leaderboards" not in src
        assert "ewar.json" not in src


def test_the_fit_reads_no_season_after_2018():
    inp = fixture_inputs(5, planted=True, n_players=300)
    a = L.fit(inp)
    rows = inp.rows.copy()
    late = rows.season >= 2019
    for c in ("drs", "uzr", "oaa", "frp", "sdr", "cframing"):
        rows.loc[late, c] = rows.loc[late, c] * 3.0 + 1.0
    b = L.fit(L.Inputs(rows=rows, split=inp.split, team=inp.team, vintage=inp.vintage,
                       rfield=inp.rfield))
    for pos in FT.NONC_POS:
        assert a["positions"][pos]["lambda"] == b["positions"][pos]["lambda"]
        assert a["positions"][pos]["Psi"] == b["positions"][pos]["Psi"]
    assert a["catcher"] == b["catcher"]


def test_permute_within_keeps_each_group_multiset():
    g = pd.DataFrame({"pos": ["SS"] * 4 + ["CF"] * 3, "season": [2019] * 7})
    v = np.arange(7.0)
    p = FT.permute_within(v, g, 3)
    assert sorted(p[:4]) == [0, 1, 2, 3] and sorted(p[4:]) == [4, 5, 6]


# ---------------------------------------------------------------------------
# the reporting path, planted recovery, null comparator
# ---------------------------------------------------------------------------

def test_planted_weights_load_the_signal_readings(planted):
    _, fitd, _ = planted
    for pos in ("SS", "CF"):
        lam = dict(zip(fitd["positions"][pos]["series"], fitd["positions"][pos]["lambda"]))
        assert lam["oaa"] > 3 and lam["frp"] > 3 and lam["drs"] > 2
    assert fitd["catcher"]["framing"]["K"] is not None


def test_planted_recovery_l1_passes_and_its_twin_fails(planted):
    _, _, res = planted
    l1 = res["legs"]["L1"]
    assert l1["gap_point"] > 0 and l1["lb95"] > 0
    assert l1["twin"]["passes_rule"] is False
    assert l1["twin"]["lb95"] is None or l1["twin"]["lb95"] <= 0.02


def test_planted_l2_reads_and_has_floors(planted):
    _, _, res = planted
    l2 = res["legs"]["L2"]
    assert l2["n_club_pairs"] == 7 * 30
    assert l2["sd"] is not None and l2["mde95"] is not None
    assert "club_clustered_beside" in l2 and isinstance(l2["non_inferior"], bool)
    assert res["verdict"] in ("PASS", "PARTIAL", "FAIL")


def test_null_comparator_never_passes(null):
    _, _, res = null
    assert res["legs"]["L1"]["passes"] is False
    assert res["s3t_eligible_for_skill_look"] is False


def test_reported_cells_exist_with_nulls(planted):
    _, _, res = planted
    rep = res["reported"]
    assert set(rep["per_position"]) == set(FT.NONC_POS)
    assert rep["catchers"]["n_pairs"] > 0
    assert set(rep["sdr_alone_minus_triangulation"]["per_system"]) == {"DRS", "Statcast", "UZR"}
    assert rep["sdr_alone_minus_triangulation"]["per_system"]["UZR"]["n_pairs"] > 0
    assert set(rep["weights_by_position"]["SS"]["w_1000"]) <= set(FT.CONFIGS["FULL"])
    assert rep["face_validity"]["season"] == 2026


def test_dry_run_main_exits_zero(capsys):
    assert L.main(["--dry-run"]) == 0
    assert "verdict" in capsys.readouterr().out
