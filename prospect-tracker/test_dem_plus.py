# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for dem_plus.py, the DEM+ fielding core.

The load-bearing properties: the pool scores mean 100 and sd exactly 10 on the
SHRUNK rates it serves; more runs per inning scores higher; a small sample is
pulled toward the pool; the positional adjustment never moves DEM+; framing
counts only for a fielder who caught; Team DEM+ is innings-weighted; nothing is
clamped; and the eval artifact records a gate.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest

import dem_plus as D
from dem_plus import Fielder

ROOT = Path(__file__).parent


def _f(key, runs, inn=1000.0, pos="SS", *, frm=None, pos_runs=None, team="AAA",
       po=0.0, a=0.0, e=0.0, extra=None):
    ib = {pos: inn}
    if extra:
        ib.update(extra)
    return Fielder(key=key, name=key, team=team, mlbam=None, inn_by_pos=ib,
                   fld_runs=runs, frm_runs=frm, pos_runs=pos_runs,
                   putouts=po, assists=a, errors=e)


def _pool():
    return [_f(f"p{i}", r) for i, r in enumerate((-8, -5, -3, -1, 0, 1, 2, 4, 6, 9))]


def test_pool_scores_mean_100_sd_10_on_the_shrunk_rates():
    out = D.score_pool(_pool())
    raws = [r["dem_plus_raw"] for r in out["fielders"]]
    assert statistics.mean(raws) == pytest.approx(100.0, abs=0.05)
    assert statistics.stdev(raws) == pytest.approx(10.0, abs=0.05)


def test_more_runs_scores_higher_and_nothing_is_clamped():
    # A pool of 40 so one outlier is not capped by its own share of the sd
    # (with n rows the largest attainable z is (n - 1) / sqrt(n)).
    fs = [_f(f"q{i}", r) for i, r in enumerate([-3, -2, -1, 0, 1, 2, 3, 0] * 5)]
    fs.append(_f("elite", 40.0, inn=1300))
    out = D.score_pool(fs)
    by = {r["key"]: r for r in out["fielders"]}
    assert by["elite"]["dem_plus"] > 130, "an honest outlier must print, not be clamped"
    order = [r["key"] for r in out["fielders"]]
    assert order[0] == "elite"


def test_a_small_sample_is_pulled_toward_the_pool():
    tiny = _f("tiny", 3.0, inn=150)     # 20 runs per 1,000 innings
    big = _f("big", 20.0, inn=1000)     # the same rate on a full season
    out = D.score_pool(_pool() + [tiny, big])
    by = {r["key"]: r for r in out["fielders"]}
    assert by["tiny"]["rate_1000"] == pytest.approx(by["big"]["rate_1000"], abs=0.01)
    assert by["tiny"]["dem_plus"] < by["big"]["dem_plus"]


def test_the_positional_adjustment_never_moves_dem_plus():
    a = D.score_pool(_pool() + [_f("x", 5.0, pos_runs=+50.0)])
    b = D.score_pool(_pool() + [_f("x", 5.0, pos_runs=-50.0)])
    ra = {r["key"]: r for r in a["fielders"]}["x"]
    rb = {r["key"]: r for r in b["fielders"]}["x"]
    assert ra["dem_plus_raw"] == rb["dem_plus_raw"]
    assert ra["def_runs"] - rb["def_runs"] == pytest.approx(100.0, abs=0.11)


def test_framing_counts_only_for_a_fielder_who_caught():
    non_c = _f("ss", 2.0, pos="SS", frm=9.0)
    catcher = _f("c", 2.0, pos="C", frm=9.0)
    out = D.score_pool(_pool() + [non_c, catcher])
    by = {r["key"]: r for r in out["fielders"]}
    assert "frm_runs" not in by["ss"], "a residual on a non-catcher is rounding, never framing"
    assert by["ss"]["fld_total"] == pytest.approx(2.0)
    assert by["c"]["frm_runs"] == pytest.approx(9.0)
    assert by["c"]["fld_total"] == pytest.approx(11.0)


def test_absent_framing_is_absent_not_zero():
    out = D.score_pool(_pool() + [_f("c", 2.0, pos="C", frm=None)])
    row = {r["key"]: r for r in out["fielders"]}["c"]
    assert "frm_runs" not in row


def test_pitcher_and_dh_innings_never_enter():
    f = _f("x", 5.0, inn=800, extra={"P": 50.0, "DH": 300.0})
    D.derive(f)
    assert f.inn == pytest.approx(800.0)


def test_shrink_constant_is_innings_weighted_over_positions_played():
    f = _f("x", 0.0, inn=500, pos="SS", extra={"1B": 500.0})
    assert D.shrink_k(f) == pytest.approx((D.K_INN["SS"] + D.K_INN["1B"]) / 2)


def test_primary_position_breaks_ties_to_the_harder_rung():
    f = _f("x", 0.0, inn=400, pos="1B", extra={"SS": 400.0})
    assert D.primary_position(f) == "SS"


def test_a_season_before_the_statcast_frame_is_refused():
    with pytest.raises(ValueError):
        D.score_pool(_pool(), season=2015)
    D.score_pool(_pool(), season=2016)


def test_team_rollup_withholds_framing_while_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(D, "TEAM_ROLLUP_FRAMING", False)
    fs = [_f("c", 5.0, pos="C", frm=9.0, team="T"), _f("ss", 5.0, team="T")] + _pool()
    t = {x["team"]: x for x in D.score_pool(fs)["teams"]}["T"]
    assert "team_frm_runs" not in t and t["n_fielders"] == 1
    assert all("frm_runs" not in s for s in t["alignment"])
    monkeypatch.setattr(D, "TEAM_ROLLUP_FRAMING", True)
    t = {x["team"]: x for x in D.score_pool(fs)["teams"]}["T"]
    assert t["team_frm_runs"] == pytest.approx(9.0) and t["n_fielders"] == 2


def test_team_dem_plus_is_innings_weighted():
    fs = [_f("a", 10.0, inn=1200, team="T"), _f("b", -10.0, inn=300, team="T")] + _pool()
    out = D.score_pool(fs)
    rows = {r["key"]: r for r in out["fielders"]}
    t = {x["team"]: x for x in out["teams"]}["T"]
    want = ((rows["a"]["dem_plus_raw"] * 1200 + rows["b"]["dem_plus_raw"] * 300) / 1500)
    assert t["team_dem_plus_raw"] == pytest.approx(want, abs=0.01)


def test_alignment_takes_the_most_innings_at_each_position():
    fs = [_f("ss1", 1.0, inn=900, team="T"), _f("ss2", 1.0, inn=300, team="T"),
          _f("cf", 1.0, inn=800, pos="CF", team="T")] + _pool()
    out = D.score_pool(fs)
    t = {x["team"]: x for x in out["teams"]}["T"]
    by = {s["pos"]: s["key"] for s in t["alignment"]}
    assert by["SS"] == "ss1" and by["CF"] == "cf"


def test_alignment_is_roster_filtered_but_the_aggregate_is_not():
    fs = [_f("ss1", 1.0, inn=900, team="T"), _f("ss2", 1.0, inn=300, team="T")]
    fs[0].mlbam, fs[1].mlbam = 1, 2
    out = D.score_pool(fs + _pool(), active_ids=frozenset({2}))
    t = {x["team"]: x for x in out["teams"]}["T"]
    assert {s["key"] for s in t["alignment"]} == {"ss2"}
    assert t["n_fielders"] == 2


def test_tiers_follow_the_warpa_breaks():
    assert (D.DEM_ELITE, D.DEM_ABOVE, D.DEM_AVG) == (120.0, 107.0, 93.0)


def test_the_shrink_constants_are_the_frozen_preregistered_values():
    """Changing a constant after the gate read its window is the tuning the
    pre-registration forbids; a change must come with a new registration."""
    assert D.K_INN == {"C": 417.0, "1B": 3116.0, "2B": 1151.0, "3B": 1018.0,
                       "SS": 616.0, "LF": 935.0, "CF": 452.0, "RF": 368.0}


def test_eval_artifact_records_the_gate():
    p = ROOT / "data" / "dem_plus_eval.json"
    if not p.exists():
        pytest.skip("dem_plus_eval.json not generated")
    ev = json.loads(p.read_text(encoding="utf-8"))
    assert ev["preregistration"].endswith("DEM_PLUS_GATE.md")
    assert "pass" in ev["gate"] and "fails_as_required" in ev["twin"]
    assert ev["k_fit"]["matches_frozen"] is True, (
        "the lab's refit on the pre-registered window no longer reproduces the "
        "frozen constants: the published series moved")
    if ev["gate"]["pass"]:
        assert ev["verdict"]["status"] == "validated"
        assert ev["twin"]["fails_as_required"] is True
