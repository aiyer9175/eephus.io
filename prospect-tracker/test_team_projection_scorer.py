# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""TM_2_TEAM_SCORER (docs/TEAM_PROJECTIONS_GATE.md; LANE_A section 3.3): the
team projection scorer in proj_backtest.py, dry-run on fixtures with nulls.

Pins: TARGETS, run(), _team_tables and the __main__ block are byte-identical
to the pre-scorer source; the GATE season refuses a read without look=True, a
second look, and any player-level 2026 residual; both arms are on aging v2;
the local Pythagenpat and nearest-rank helpers equal the exporter's and the
simulator's; proj_export._write_team_outlook_eval keeps team_projection_gate
across a re-export. Nothing here reads real 2026 standings."""

from __future__ import annotations

import hashlib
import inspect
import json
import random
from pathlib import Path

import pytest

import proj_backtest as pb

ROOT = Path(__file__).parent

# sha256 of inspect.getsource (LF-normalized) at 5c1f853d, the proj_backtest
# re-run M15 part (4) committed; the scorer added nothing above its block.
PINNED = {
    "run": "33c2293b7dc9453853aea30922b7a12eb54c44d1e9f9c63a566ba3d32fdf4b19",
    "_team_tables": "4ed71291fe38da2d5b09970dd4b3856ff946878a4e9d3e600bd91d5aa5da248d",
    "_project_targets": "73bd5537f940fd91f63f9a0e5d8b65ac54bb9bd06e547f2c10e1d750c41f4891",
    "_primary_teams": "2b26517c31287b33163a4a0f554521091b173bac6480846f923e5e7dc7089c43",
    "_served_intercepts": "ecb78609f98039f9986bf9c2acd7f57d2ae2328acec23e70c12a2f1fd8bb1fca",
    "_holdout_gap_ci": "30bfd1a1493be19126294db63cbb232d1c36665006227858020407ea4425bdc6",
}
PINNED_MAIN_BLOCK = "1d80f278523c5aec48a6cd3df196ac4cc0aa4ac2380ad0c2b60421117350aefb"


def _h(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# fixtures (a DEV season; every club code is a fixture, not a reading)
# ---------------------------------------------------------------------------

def _rows(target: int, with_act: bool = True) -> list[dict]:
    rows = [
        {"mlbam": 1, "target": target, "side": "hit", "role": "H", "band": "26-29", "age": 27,
         "pred": 4.0, "pa_proj": 600.0},
        {"mlbam": 2, "target": target, "side": "pit", "role": "SP", "band": "30-33", "age": 31,
         "pred": 2.0, "ip_proj": 180.0},
        {"mlbam": 3, "target": target, "side": "hit", "role": "C", "band": "0-25", "age": 24,
         "pred": 1.0, "pa_proj": 300.0},
        {"mlbam": 4, "target": target, "side": "pit", "role": "RP", "band": "34-99", "age": 35,
         "pred": 0.5, "ip_proj": 60.0},
        {"mlbam": 9, "target": target + 1, "side": "hit", "role": "H", "band": "26-29", "age": 28,
         "pred": 9.0, "pa_proj": 600.0},   # another target: filtered out
    ]
    if with_act:
        for r, a in zip(rows, (3.5, 1.0, 0.0, 0.2, 9.0)):
            r["act"] = a
    return rows


TEAMS = {(1, 2025): "AAA", (2, 2025): "AAA", (3, 2025): "BBB", (4, 2025): "ZZZ"}
ACTUAL = {"AAA": 94, "BBB": 81, "CCC": 70}


def _frame(**kw):
    base = dict(rows=_rows(2025), teams=TEAMS, exposure={"AAA": {"pa": 6100.0, "ip": 1440.0},
                                                          "BBB": {"pa": 6200.0, "ip": 1450.0}},
                actual_wins=ACTUAL)
    base.update(kw)
    return pb.team_frame(2025, **base)


# ---------------------------------------------------------------------------
# the retro block is untouched
# ---------------------------------------------------------------------------

def test_targets_run_and_the_retro_block_are_byte_identical():
    assert pb.TARGETS == (2022, 2023, 2024, 2025)
    assert pb.LEAGUE_WINS == 2430.0
    for name, want in PINNED.items():
        assert _h(inspect.getsource(getattr(pb, name))) == want, name
    src = (ROOT / "proj_backtest.py").read_text(encoding="utf-8")
    tail = src[src.index('if __name__ == "__main__":'):]
    assert _h(tail) == PINNED_MAIN_BLOCK
    # the scorer sits below run() and above the __main__ block
    assert src.index("def run(") < src.index("def team_frame(") < src.index('if __name__ == "__main__":')


# ---------------------------------------------------------------------------
# team_frame guards
# ---------------------------------------------------------------------------

def test_the_gate_season_needs_look_true():
    with pytest.raises(RuntimeError, match="GATE look"):
        pb.team_frame(2026, rows=[], teams={}, exposure={})
    with pytest.raises(RuntimeError, match="GATE"):
        pb.club_actuals(2026, table={})


def test_a_second_look_is_refused(tmp_path, monkeypatch):
    eval_path = tmp_path / "team_outlook_eval.json"
    eval_path.write_text(json.dumps({"retro_backtest": {"x": 1},
                                     "team_projection_gate": {"gate_2026": {"verdict": "null"}}}),
                         encoding="utf-8")
    monkeypatch.setattr(pb, "EVAL_PATH", eval_path)
    with pytest.raises(RuntimeError, match="second look"):
        pb.team_frame(2026, look=True, rows=[], teams={}, exposure={}, clubs=["AAA"])
    with pytest.raises(RuntimeError, match="second look"):
        pb.club_actuals(2026, look=True, table={})
    with pytest.raises(RuntimeError, match="first write wins"):
        pb.write_team_gate_block({"verdict": "again"}, path=eval_path)


def test_no_player_level_2026_residual(tmp_path, monkeypatch):
    eval_path = tmp_path / "team_outlook_eval.json"
    eval_path.write_text(json.dumps({"retro_backtest": {}}), encoding="utf-8")
    monkeypatch.setattr(pb, "EVAL_PATH", eval_path)
    rows = _rows(2026, with_act=True)
    with pytest.raises(RuntimeError, match="residual"):
        pb.team_frame(2026, look=True, rows=rows, teams={(1, 2026): "AAA"}, exposure={},
                      clubs=["AAA"])
    # the same rows without an actual are the GATE frame: no actual anywhere
    rows = _rows(2026, with_act=False)
    fr = pb.team_frame(2026, look=True, rows=rows, teams={(1, 2026): "AAA", (2, 2026): "BBB"},
                       exposure={}, clubs=["AAA", "BBB"])
    assert fr["frame"] == "GATE" and fr["look"] is True
    for c in fr["clubs"].values():
        assert c["actual"] is None
        assert all("act" not in p for p in c["players"])


def test_both_arms_are_pinned_to_aging_v2():
    assert pb.TEAM_AGING == "v2"
    with pytest.raises(ValueError, match="aging"):
        _frame(aging="v3")
    with pytest.raises(ValueError, match="aging"):
        pb._project_season(2025, {"league": {}, "hit": [], "pit": []}, aging="v3")
    assert _frame()["aging"] == "v2"


def test_only_dev_and_gate_targets():
    with pytest.raises(ValueError):
        pb.team_frame(2021, rows=[], teams={}, exposure={})
    with pytest.raises(ValueError):
        pb.team_frame(2027, rows=[], teams={}, exposure={})


# ---------------------------------------------------------------------------
# team_frame on a DEV fixture, with a club that has no rows
# ---------------------------------------------------------------------------

def test_team_frame_rolls_up_and_recenters():
    fr = _frame()
    assert fr["frame"] == "DEV" and fr["target"] == 2025 and fr["look"] is False
    clubs = fr["clubs"]
    assert set(clubs) == {"AAA", "BBB", "CCC"}       # the standings' clubs, CCC has no rows
    assert fr["league"]["n_rows"] == 4                # the other-target row is filtered
    assert clubs["AAA"]["n_players"] == 2 and clubs["AAA"]["n_hit"] == 1 and clubs["AAA"]["n_pit"] == 1
    assert clubs["AAA"]["roster_war"] == 6.0 and clubs["AAA"]["pa_proj_sum"] == 600.0
    assert clubs["AAA"]["ip_proj_sum"] == 180.0
    assert clubs["CCC"]["n_players"] == 0 and clubs["CCC"]["roster_war"] == 0.0
    assert clubs["CCC"]["wins_raw"] == pytest.approx(pb.REPLACEMENT_WINS)
    assert clubs["CCC"]["exposure"] is None and clubs["AAA"]["exposure"]["pa"] == 6100.0
    # player 4's club ZZZ is not in the standings: unassigned, never summed
    assert fr["unassigned"] == {"n": 1, "war_proj_sum": 0.5}
    assert fr["league"]["n_assigned"] == 3
    # recentering pins the league to 2,430 over the club universe
    assert sum(c["wins_recentered"] for c in clubs.values()) == pytest.approx(pb.LEAGUE_WINS, abs=0.01)
    assert sum(c["wins_served_recentered"] for c in clubs.values()) == pytest.approx(pb.LEAGUE_WINS, abs=0.01)
    assert clubs["AAA"]["wins_recentered"] - clubs["CCC"]["wins_recentered"] == pytest.approx(6.0, abs=0.01)
    assert clubs["AAA"]["actual"] == {"wins": 94} and clubs["CCC"]["actual"] == {"wins": 70}
    assert fr["league"]["exposure_mean"] == {"pa": 6150.0, "ip": 1445.0, "n_clubs": 2}
    for c in clubs.values():
        assert 0.20 <= c["p_prior"] <= 0.80


def test_team_frame_actual_wins_accept_dict_rows():
    fr = _frame(actual_wins={"AAA": {"wins": 94, "rs": 800}, "BBB": {"wins": 81}})
    assert fr["clubs"]["AAA"]["actual"] == {"wins": 94}
    assert set(fr["clubs"]) == {"AAA", "BBB"}


def test_talent_prior_matches_the_exporter_clamp():
    import proj_export as pe
    for w in (10.0, 40.0, 81.0, 100.0, 162.0):
        assert pb._talent_pct(w) == pe._talent_prior_pct(w)


# ---------------------------------------------------------------------------
# the standings bridge (fixture table in the parser's shape)
# ---------------------------------------------------------------------------

def test_club_actuals_parses_the_one_standings_table_shape():
    table = {"AAA": {2025: {"w": 94, "l": 68, "rs": 800, "ra": 700, "gp": 162}},
             "BBB": {2025: {"w": 81, "l": 81, "rs": None, "ra": 720, "gp": 162}},
             "CCC": {2024: {"w": 70, "l": 92, "rs": 600, "ra": 760, "gp": 162}},
             "DDD": {2025: {"w": None, "l": None, "rs": None, "ra": None, "gp": None}}}
    got = pb.club_actuals(2025, table=table)
    assert got == {"AAA": {"wins": 94, "losses": 68, "rs": 800, "ra": 700, "gp": 162},
                   "BBB": {"wins": 81, "losses": 81, "rs": None, "ra": 720, "gp": 162}}


# ---------------------------------------------------------------------------
# score_win_distribution: CRPS, coverage, Wilson, nulls
# ---------------------------------------------------------------------------

def _brute_crps(xs, y):
    n = len(xs)
    return (sum(abs(x - y) for x in xs) / n
            - sum(abs(a - b) for a in xs for b in xs) / (2 * n * n))


def test_crps_matches_the_brute_force_double_sum():
    rng = random.Random(7)
    for _ in range(20):
        xs = [rng.randint(60, 100) for _ in range(rng.randint(1, 40))]
        y = rng.uniform(55, 105)
        assert pb._crps_from_samples(sorted(xs), y) == pytest.approx(_brute_crps(xs, y), abs=1e-9)
    assert pb._crps_from_samples([90.0], 94.0) == pytest.approx(4.0)   # a point mass is its error
    with pytest.raises(ValueError):
        pb._crps_from_samples([], 1.0)


def test_nearest_rank_matches_the_simulator():
    import proj_current as pc
    for n in (1, 2, 5, 17, 100):
        s = sorted(random.Random(n).randint(50, 110) for _ in range(n))
        for q in (0.1, 0.5, 0.9):
            assert pb._nearest_rank(s, q) == pc._percentile(s, q)
    assert pb._nearest_rank([], 0.5) is None


def test_score_win_distribution_with_nulls():
    samples = {"AAA": [90, 92, 95, 97, 99], "BBB": [75, 80, 85], "CCC": [], "DDD": [80, 81]}
    actual = {"AAA": 94, "BBB": {"wins": 70}, "CCC": 80, "EEE": 85}
    out = pb.score_win_distribution(samples, actual)
    assert out["n_clubs"] == 2
    assert sorted(out["missing"]) == ["CCC", "DDD", "EEE"]   # no samples, no actual, no samples
    assert out["clubs"]["AAA"]["inside80"] is True and out["clubs"]["BBB"]["inside80"] is False
    assert out["clubs"]["AAA"]["p10"] == 90 and out["clubs"]["AAA"]["p90"] == 99
    assert out["crps_by_club"]["AAA"] == pytest.approx(_brute_crps([90, 92, 95, 97, 99], 94), abs=1e-4)
    assert out["crps_mean"] == pytest.approx((out["crps_by_club"]["AAA"] + out["crps_by_club"]["BBB"]) / 2, abs=1e-4)
    cov = out["coverage80"]
    assert cov["k"] == 1 and cov["n"] == 2 and cov["rate"] == 0.5
    assert cov["wilson95"]["lo"] < 0.5 < cov["wilson95"]["hi"]
    empty = pb.score_win_distribution({}, {"AAA": 90})
    assert empty["n_clubs"] == 0 and empty["crps_mean"] is None
    assert empty["coverage80"]["rate"] is None and empty["coverage80"]["wilson95"] is None


def test_wilson_interval_is_the_textbook_one():
    import math
    k, n, z = 24, 30, 1.96
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    w = pb._wilson(k, n)
    assert w == {"lo": round(centre - half, 4), "hi": round(centre + half, 4)} == {"lo": 0.6269, "hi": 0.905}
    assert pb._wilson(0, 30)["lo"] == 0.0 and pb._wilson(30, 30)["hi"] == 1.0
    assert pb._wilson(0, 0) is None


# ---------------------------------------------------------------------------
# score_team_wins, score_team_runs, _club_bootstrap
# ---------------------------------------------------------------------------

def test_score_team_wins_with_nulls():
    out = pb.score_team_wins({"AAA": 95.0, "BBB": None, "CCC": 82.0, "DDD": 70.0},
                             {"AAA": 94, "BBB": 81, "CCC": {"wins": 80}})
    assert out["n"] == 2 and out["mae"] == 1.5 and out["bias_pred_minus_act"] == 1.5
    assert out["r"] is None                      # fewer than three pairs
    assert out["abs_err_by_club"] == {"AAA": 1.0, "CCC": 2.0}
    assert out["missing"] == ["BBB", "DDD"]
    assert pb.score_team_wins({}, {})["mae"] is None


def test_club_bootstrap_is_seeded_and_drops_nulls():
    deltas = {"AAA": -3.0, "BBB": -1.0, "CCC": None, "DDD": float("nan"), "EEE": -2.0}
    a = pb._club_bootstrap(deltas, B=500, seed=20261208)
    b = pb._club_bootstrap(deltas, B=500, seed=20261208)
    assert a == b
    assert a["n"] == 3 and a["dropped"] == ["CCC", "DDD"] and a["mean"] == -2.0
    assert a["ub95"] <= -1.0 and a["pass"] is True and a["B"] == 500 and a["seed"] == 20261208
    c = pb._club_bootstrap({"AAA": 1.0, "BBB": -1.0}, B=500, seed=1)
    assert c["pass"] is False and c["lo05"] <= c["mean"] <= c["ub95"]
    null = pb._club_bootstrap({}, B=10, seed=1)
    assert null["n"] == 0 and null["pass"] is None and null["ub95"] is None
    lst = pb._club_bootstrap([-1.0, -2.0], B=50, seed=3)
    assert lst["n"] == 2 and lst["dropped"] == []
    assert pb.TM_BOOTSTRAP_B == 2000 and pb.TM_SEED_GATE_2026 == 20261208


def test_pythagenpat_matches_the_exporter():
    import proj_export as pe
    for rs, ra in ((800, 700), (650, 660), (700, 850), (900, 500)):
        assert pb._pythag_wins(rs, ra, 162) == pytest.approx(162 * pe._pythag_pct(rs, ra, 162))
    assert pb._pythag_wins(None, 700) is None and pb._pythag_wins(0, 0) is None


def test_score_team_runs_with_comparators_and_a_missing_rs():
    actual = {"AAA": {"rs": 800, "ra": 700, "wins": 94},
              "BBB": {"rs": None, "ra": 720, "wins": 81},     # a missing RS
              "CCC": {"rs": 650, "ra": 660, "wins": 80}}
    prior = {"AAA": {"rs": 790, "ra": 690}, "BBB": {"rs": 750, "ra": 730}, "CCC": {"rs": 640, "ra": 680}}
    pred_rs = {"AAA": 810, "BBB": 740, "CCC": 655}
    pred_ra = {"AAA": 705, "BBB": 710, "CCC": 670}
    out = pb.score_team_runs(pred_rs, pred_ra, actual, prior=prior,
                             pred_wins={"AAA": 93, "BBB": 82, "CCC": 79}, B=300)
    rs, ra = out["rs"], out["ra"]
    assert rs["n"] == 2 and rs["missing"] == ["BBB"] and rs["mae"] == 7.5
    assert ra["n"] == 3 and ra["missing"] == [] and ra["mae"] == pytest.approx(8.333, abs=1e-3)
    assert rs["vs_carry_forward"]["comparator_mae"] == 10.0
    assert rs["vs_carry_forward"]["delta_by_club"] == {"AAA": 0.0, "CCC": -5.0}
    assert rs["league_avg_comparator"] == pytest.approx((790 + 750 + 640) / 3, abs=0.01)
    assert rs["vs_league_avg"]["bootstrap"]["seed"] == 20261208 and rs["vs_league_avg"]["bootstrap"]["B"] == 300
    assert out["pass"]["rs"] is False            # carry-forward ub95 reaches 0 on two clubs
    assert out["pass"]["ra"] in (True, False)
    assert out["pythag_wins"]["n"] == 3 and set(out["pythag_wins"]["by_club"]) == {"AAA", "BBB", "CCC"}
    assert out["served_wins"]["n"] == 3 and out["served_wins"]["mae"] == pytest.approx(1.0)
    assert out["comparators"]["prior_clubs"] == 3
    # no prior: comparators and the pass are null findings, the MAE still reads
    bare = pb.score_team_runs(pred_rs, pred_ra, actual)
    assert bare["rs"]["vs_carry_forward"] is None and bare["pass"] == {"rs": None, "ra": None}
    assert bare["rs"]["mae"] == 7.5 and bare["served_wins"] is None
    # nothing at all
    none = pb.score_team_runs({}, {}, {}, prior={})
    assert none["rs"]["n"] == 0 and none["pythag_wins"]["n"] == 0 and none["pass"] == {"rs": None, "ra": None}


# ---------------------------------------------------------------------------
# the eval artifact keeps the gate block across a re-export
# ---------------------------------------------------------------------------

def test_write_team_gate_block_is_read_modify_write(tmp_path):
    p = tmp_path / "team_outlook_eval.json"
    p.write_text(json.dumps({"retro_backtest": {"generated_at": "x"}, "forward_gate": {"status": "pending"}}),
                 encoding="utf-8")
    cur = pb.write_team_gate_block({"verdict": "null", "n": 30}, key="gate_2026", path=p)
    back = json.loads(p.read_text(encoding="utf-8"))
    assert back == cur
    assert back["retro_backtest"] == {"generated_at": "x"} and back["forward_gate"] == {"status": "pending"}
    assert back["team_projection_gate"] == {"gate_2026": {"verdict": "null", "n": 30}}
    pb.write_team_gate_block({"verdict": "later"}, key="forward_2027", path=p)
    back = json.loads(p.read_text(encoding="utf-8"))
    assert set(back["team_projection_gate"]) == {"gate_2026", "forward_2027"}
    assert pb._gate_already_read(p) is True
    assert pb._gate_already_read(tmp_path / "absent.json") is False


def test_proj_export_keeps_team_projection_gate_across_a_re_export(tmp_path, monkeypatch):
    import proj_export as pe
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    gate = {"gate_2026": {"verdict": "null", "crps": {"candidate": 5.1, "incumbent": 5.0}}}
    retro = {"generated_at": "2026-10-09", "ship_decision": {"holdout_mae": {"served_recentered": 7.12,
                                                                              "recentered": 7.12}}}
    (data_dir / "team_outlook_eval.json").write_text(
        json.dumps({"retro_backtest": retro, "team_projection_gate": gate, "generated_at": "old"}),
        encoding="utf-8")
    monkeypatch.setattr(pe, "DATA_DIR", data_dir)
    monkeypatch.setattr(pe, "_cohort_intercepts", lambda: {})
    monkeypatch.setattr(pe, "_forward_vintage_on_record", lambda season: None)
    pe._write_team_outlook_eval([], 0.0, [0.0] * pe.HORIZON, {})
    back = json.loads((data_dir / "team_outlook_eval.json").read_text(encoding="utf-8"))
    assert back["team_projection_gate"] == gate, "the gate block must survive a re-export"
    assert back["retro_backtest"] == retro
    assert back["generated_at"] != "old" and back["serve_vector_flag"] is False
