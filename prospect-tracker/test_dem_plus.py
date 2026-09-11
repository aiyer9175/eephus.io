# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for dem_plus.py, the DEM+ fielding core.

The load-bearing properties: the pool scores mean 100 and sd exactly 10 on the
SHRUNK rates it serves; more runs per inning scores higher; a small sample is
pulled toward the pool; the positional adjustment never moves DEM+; framing
counts only for a fielder who caught; Team DEM+ is innings-weighted and, by
owner decision 17 (2026-09-11), carries catchers and their framing; Def's
positional term is our ladder pro-rated by innings with FanGraphs' own riding
beside it (owner decision 18); nothing is clamped; and the eval artifact records
a gate.
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


def test_the_club_rollup_carries_framing_by_owner_decision():
    """Owner decision 17 (2026-09-11): club framing shows now. Mutation: the
    constant flipped back, or the catcher slot stripped of his framing."""
    assert D.TEAM_ROLLUP_FRAMING is True
    fs = [_f("c", 5.0, pos="C", frm=9.0, team="T"), _f("ss", 5.0, team="T")] + _pool()
    t = {x["team"]: x for x in D.score_pool(fs)["teams"]}["T"]
    assert t["rollup_includes_catchers"] is True and t["n_fielders"] == 2
    assert t["team_frm_runs"] == pytest.approx(9.0)
    assert t["team_fld_total"] == pytest.approx(19.0)          # 5 + 9 framing + 5
    c = {s["pos"]: s for s in t["alignment"]}["C"]
    assert c["frm_runs"] == pytest.approx(9.0)
    assert "frm_runs" not in {s["pos"]: s for s in t["alignment"]}["SS"]


# --- the positional term: our ladder (owner decision 18) ----------------------

_LAD = {"C": 10.0, "1B": -8.0, "2B": 5.0, "3B": 4.0, "SS": 8.0,
        "LF": -6.0, "CF": 4.0, "RF": -6.0}


def test_our_ladder_is_pro_rated_by_innings_and_skips_dh_and_p():
    got = D.ladder_pos_runs({"SS": 650.0, "1B": 325.0, "DH": 400.0, "P": 10.0}, _LAD, 1300.0)
    assert got == pytest.approx(8.0 * 650 / 1300 - 8.0 * 325 / 1300)
    # a full 650-PA season's worth of innings at one position earns the rung
    assert D.ladder_pos_runs({"C": 1277.7}, _LAD, 1277.7) == pytest.approx(10.0)


def test_our_ladder_is_none_never_partial():
    assert D.ladder_pos_runs({"SS": 900.0}, None, 1277.7) is None
    assert D.ladder_pos_runs({"SS": 900.0}, _LAD, None) is None
    assert D.ladder_pos_runs({"SS": 900.0}, _LAD, 0.0) is None
    short = {k: v for k, v in _LAD.items() if k != "CF"}
    assert D.ladder_pos_runs({"SS": 900.0, "CF": 10.0}, short, 1277.7) is None


def test_def_sums_our_term_and_fangraphs_rides_beside_it():
    """Mutation: FanGraphs' positional left inside Def, or dropped from the row."""
    f = _f("x", 4.0, pos_runs=3.0)
    f.pos_runs_fg = -5.0
    g = _f("y", 1.0, team="AAA", pos_runs=-1.0)
    g.pos_runs_fg = 2.0
    out = D.score_pool(_pool() + [f, g])
    row = {r["key"]: r for r in out["fielders"]}["x"]
    assert row["pos_runs"] == pytest.approx(3.0)
    assert row["pos_runs_fg"] == pytest.approx(-5.0)
    assert row["def_runs"] == pytest.approx(row["fld_total"] + 3.0)
    t = {x["team"]: x for x in out["teams"]}["AAA"]
    assert t["team_pos_runs"] == pytest.approx(2.0)
    assert t["team_pos_runs_fg"] == pytest.approx(-3.0)


def _write_fit(tmp_path, *, conv=1277.7, drop=None, folklore=None):
    lad = {"values": dict(_LAD, DH=-13.7), "seasons": [2021, 2026],
           "n_player_seasons": 2023, "inn_per_pa": 1.9657}
    if drop:
        lad["values"].pop(drop)
    if folklore is not None:
        lad["folklore_basis"] = {"pa_equivalent_innings": folklore}
    fit = {"ladder": lad}
    if conv is not None:
        fit["inn_per_650pa"] = conv
    p = tmp_path / "positional_fit.json"
    p.write_text(json.dumps({"generated_at": "2026-08-12", "fit": fit}), encoding="utf-8")
    return p


def test_the_exporter_reads_the_ladder_by_reference(tmp_path, monkeypatch):
    import defense_export as DE
    monkeypatch.setattr(DE, "POSITIONAL_FIT", _write_fit(tmp_path))
    DE.load_ladder.cache_clear()
    try:
        lad = DE.load_ladder()
        assert lad["available"] and lad["inn_per_650"] == pytest.approx(1277.7)
        assert lad["values"] == _LAD                               # DH never enters
        monkeypatch.setattr(DE, "POSITIONAL_FIT", _write_fit(tmp_path, conv=None, folklore=1300.0))
        DE.load_ladder.cache_clear()
        assert DE.load_ladder()["inn_per_650"] == pytest.approx(1300.0)
        monkeypatch.setattr(DE, "POSITIONAL_FIT", _write_fit(tmp_path, conv=None))
        DE.load_ladder.cache_clear()
        assert DE.load_ladder()["inn_per_650"] == pytest.approx(650.0 * 1.9657)
        monkeypatch.setattr(DE, "POSITIONAL_FIT", _write_fit(tmp_path, drop="SS"))
        DE.load_ladder.cache_clear()
        assert DE.load_ladder()["available"] is False
    finally:
        DE.load_ladder.cache_clear()


def test_build_fielders_carries_both_terms_and_never_swaps_bases(monkeypatch):
    """Our ladder goes in pos_runs, the feed's positional in pos_runs_fg; with
    the ladder unavailable pos_runs is absent, not FanGraphs' number."""
    import defense_export as DE
    pub = {"values": {7: {"fld": 2.0, "frm": None, "pos": -4.5, "name": "X", "team_id": 1}}}
    inn = {"players": {7: {"inn": {"SS": 650.0, "1B": 325.0}, "po": 1.0, "a": 1.0,
                           "e": 0.0, "name": "X", "team_id": 1}}}
    monkeypatch.setattr(DE, "load_published_fielding", lambda s: pub)
    monkeypatch.setattr(DE, "load_season_innings", lambda s: inn)
    monkeypatch.setattr(DE, "_identity_rows", lambda s, ids: [])
    monkeypatch.setattr(DE, "_tmap", lambda: {1: "AAA"})
    monkeypatch.setattr(DE, "load_ladder", lambda: {"available": True, "values": _LAD,
                                                    "inn_per_650": 1300.0})
    (f,), _rows, src = DE.build_fielders(2026, log=None)
    assert f.pos_runs == pytest.approx(2.0) and f.pos_runs_fg == pytest.approx(-4.5)
    assert src["ladder"]["available"] is True
    monkeypatch.setattr(DE, "load_ladder", lambda: {"available": False, "reason": "x"})
    (f,), _rows, _src = DE.build_fielders(2026, log=None)
    assert f.pos_runs is None and f.pos_runs_fg == pytest.approx(-4.5)
    row = D.fielder_row(f)
    assert "def_runs" not in row and "pos_runs" not in row and row["pos_runs_fg"] == -4.5


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
