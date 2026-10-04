# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""pitch_rates.py, the one definition of P/IP, P/BF, P/PA and PAR (plan P8.1, PM-02).

What these pin:
  * innings are outs / 3, so "6.1" is 19 outs;
  * a zero or missing denominator gives None;
  * league anchors are pooled sums over sums, never a mean of player rates;
  * tracking() reproduces the lane's section 2.2 table on a fixture (CPX 2023
    untracked, A+ 2017 partial, AA 2014 usable);
  * par() rounds nearest (halves up), team_par() values average 100;
  * a role split that misses the season line falls back and says so
    (season_line_fallback), and one that misses by more than 5 percent is excluded
    (role_split_mismatch);
  * nothing is written under data/ while SERVE_PITCH_RATES is False.
No test reaches the network: every cache path points at tmp_path and the HTTP
helper raises.
"""
from __future__ import annotations

import json
import random

import pytest

import pitch_rates as P


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    cache = tmp_path / "cache" / "pitch_rates"
    mlb = tmp_path / "cache"
    data = tmp_path / "data"
    cache.mkdir(parents=True)
    data.mkdir()
    monkeypatch.setattr(P, "CACHE_DIR", cache)
    monkeypatch.setattr(P, "MLB_CACHE_DIR", mlb)
    monkeypatch.setattr(P, "PLATOON_DIR", tmp_path / "cache" / "milb_platoon")
    monkeypatch.setattr(P, "PREVIEW_PATH", cache / "preview.json")
    monkeypatch.setattr(P, "DATA_PATH", data / "pitch_rates.json")

    def _no_network(url):
        raise AssertionError(f"network call in a test: {url}")
    monkeypatch.setattr(P, "_http_json", _no_network)
    filed = []
    monkeypatch.setattr(P, "_record", lambda source, **kw: filed.append((source, kw)))
    return {"cache": cache, "mlb": mlb, "data": data, "filed": filed}


def _put(cache, name, rows):
    (cache / name).write_text(json.dumps({"meta": {}, "rows": rows}), encoding="utf-8")


def _hit(pid, team, np_, pa, league="L", level="AAA", pos="C"):
    return {"mlbam": pid, "team_id": team, "league": league, "level": level,
            "np": np_, "g": 10, "pa": pa, "pos": pos}


def _pit(pid, team, np_, outs, bf, g, gs, level="AAA", code=None, league="L"):
    r = {"mlbam": pid, "team_id": team, "league": league, "level": level,
         "np": np_, "g": g, "bf": bf, "outs": outs, "gs": gs}
    if code:
        r["code"] = code
    return r


# --------------------------------------------------------------------------- #
# Innings and rates
# --------------------------------------------------------------------------- #
def test_innings_are_outs_over_three_and_6_1_is_19_outs():
    assert P.outs_from_ip("6.1") == 19
    assert P.outs_from_ip("6.2") == 20
    assert P.outs_from_ip("6.0") == 18
    assert P.outs_from_ip(6.1) == 19
    assert P.outs_from_ip("0.2") == 2
    assert P.innings(19) == pytest.approx(19 / 3)
    assert P.p_ip(96, 18) == pytest.approx(16.0)
    # 6.1 innings is 19 outs, so 100 pitches is 100 / 6.333 = 15.79, never 100 / 6.1
    assert P.p_ip(100, P.outs_from_ip("6.1")) == pytest.approx(100 / (19 / 3))


def test_a_line_with_innings_but_no_outs_field_reads_the_notation():
    split = {"player": {"id": 1}, "team": {"id": 2}, "league": {"name": "PCL"},
             "stat": {"numberOfPitches": 100, "inningsPitched": "6.1",
                      "battersFaced": 26, "gamesPitched": 1, "gamesStarted": 1}}
    row = P._lean(split, 11, "pitching")
    assert row["outs"] == 19
    assert row["level"] == "AAA" and row["team_id"] == 2


def test_rates_are_none_on_zero_or_missing_denominators():
    assert P.p_ip(50, 0) is None
    assert P.p_bf(50, 0) is None
    assert P.p_pa(50, 0) is None
    assert P.p_pa(50, None) is None
    assert P.p_ip(None, 9) is None
    assert P.par(15.0, 0) is None
    assert P.par(None, 16.0) is None
    assert P.par_delta(None, 16.0) is None


def test_par_rounds_nearest_with_halves_up():
    assert P.par(15.6, 16.4) == 95          # the glossary example
    assert P.par(100.4, 100.0) == 100
    assert P.par(100.5, 100.0) == 101
    assert P.par(102.5, 100.0) == 103       # banker's rounding would give 102
    assert P.par(99.5, 100.0) == 100
    assert P.par(3.9, 3.9) == 100


def test_team_par_values_average_100():
    rng = random.Random(20260930)
    rates = {club: rng.uniform(15.0, 18.0) for club in range(108, 138)}
    rates[999] = None                        # a club with no rate stays out of the mean
    tp = P.team_par(rates)
    vals = [v for v in tp.values() if v is not None]
    assert len(vals) == 30
    assert sum(vals) / len(vals) == pytest.approx(100.0, abs=1e-9)
    assert tp[999] is None
    hi = max(rates, key=lambda k: rates[k] or 0)
    assert tp[hi] == pytest.approx(100.0 * rates[hi] / (sum(v for v in rates.values() if v) / 30))


# --------------------------------------------------------------------------- #
# Tracking: the lane's section 2.2 table on a fixture
# --------------------------------------------------------------------------- #
def _clubs(level, league, p_pa_by_club, pa_each=4000, pid0=1000):
    rows = []
    for i, (club, rate) in enumerate(p_pa_by_club.items()):
        pa = pa_each if not isinstance(rate, tuple) else rate[1]
        rate = rate if not isinstance(rate, tuple) else rate[0]
        rows.append(_hit(pid0 + i, club, int(round(rate * pa)), pa, league=league, level=level))
    return rows


def test_tracking_reproduces_the_lane_table(sandbox):
    c = sandbox["cache"]
    # CPX 2023: the complex leagues printed about 1.9 pitches per PA (untracked).
    # A DSL club in the same sport-16 file must not leak into CPX.
    cpx = _clubs("CPX", "ACL", {i: 1.9 + 0.02 * (i % 5) for i in range(1, 15)})
    cpx += _clubs("DSL", "DSL", {i: 3.8 for i in range(100, 104)}, pid0=5000)
    _put(c, "hitting_16_2023.json", cpx)
    # A+ 2017: tracked, but one of 15 clubs sits under 3.3 (about 6.7% of PA): partial.
    ap = _clubs("A+", "Carolina League", {i: 3.85 for i in range(1, 15)})
    ap += _clubs("A+", "Carolina League", {99: 2.1}, pid0=9000)
    _put(c, "hitting_13_2017.json", ap)
    # AA 2014: every club with 200+ PA at 3.3 or more: usable. A club under the PA
    # floor with an untracked rate does not flip it.
    aa = _clubs("AA", "Eastern League", {i: 3.7 + 0.01 * i for i in range(1, 13)})
    aa += _clubs("AA", "Eastern League", {77: (2.0, 150)}, pid0=7000)
    _put(c, "hitting_12_2014.json", aa)

    assert P.tracking("CPX", 2023) == "untracked"
    assert P.tracking("A+", 2017) == "partial"
    assert P.tracking("AA", 2014) == "usable"
    det = P.tracking_detail("A+", 2017)
    assert det["n_clubs_under"] == 1
    assert det["pa_share_under"] == pytest.approx(1 / 15, abs=1e-4)
    assert P.tracking("DSL", 2023) == "usable"
    # no hitting lines at all is untracked, never usable
    assert P.tracking("AAA", 2020) == "untracked"


def test_a_minority_of_pa_under_the_floor_is_partial_and_a_majority_untracked():
    # AA 2011 in the lane's table: 39.2 percent of PA on clubs under 3.3 is
    # partial even though the pooled rate sits under the floor; complex 2017 at
    # 64.7 percent is untracked.
    rows = _clubs("AA", "Eastern League", {i: 3.7 for i in range(1, 19)})
    rows += _clubs("AA", "Eastern League", {i: 2.4 for i in range(50, 62)}, pid0=8000)
    det = P.classify_tracking(rows)
    assert det["pa_share_under"] == pytest.approx(0.4)
    assert det["status"] == "partial"
    rows += _clubs("AA", "Eastern League", {i: 2.4 for i in range(70, 80)}, pid0=8500)
    assert P.classify_tracking(rows)["status"] == "untracked"


def test_a_role_split_row_naming_the_dominican_league_in_full_is_dsl():
    # The statSplits response names the league in full; the season lines use the
    # abbreviation. Both must land on DSL, or every DSL role line folds into CPX.
    for name in ("Dominican Summer League", "DSL", "Venezuelan Summer League"):
        split = {"player": {"id": 1}, "team": {"id": 2}, "league": {"name": name},
                 "split": {"code": "sp"},
                 "stat": {"numberOfPitches": 50, "outs": 9, "battersFaced": 13}}
        assert P._lean(split, 16, "pitching", role=True)["level"] == "DSL"
    split["league"] = {"name": "Florida Complex League"}
    assert P._lean(split, 16, "pitching", role=True)["level"] == "CPX"


def test_untracked_level_season_gives_no_rate(sandbox):
    c = sandbox["cache"]
    _put(c, "hitting_16_2023.json",
         _clubs("CPX", "ACL", {i: 1.9 for i in range(1, 10)}))
    lr = P.league_rates("CPX", 2023)
    assert lr["hit"]["p_pa"] is None and lr["hit"]["np"] > 0
    pl = P.player_lines(2023, "CPX")
    assert pl and all(v["hit"]["p_pa"] is None for v in pl.values())


# --------------------------------------------------------------------------- #
# Anchors: pooled sums over sums
# --------------------------------------------------------------------------- #
def _aaa_2025(c, sp_bf_scale=1.0, drop_role_for=None):
    hit = [_hit(1, 10, 400, 100), _hit(2, 10, 1950, 500), _hit(3, 11, 3900, 1000),
           _hit(4, 11, 1200, 300), _hit(5, 12, 4000, 1000),
           _hit(6, 12, 40, 30, pos="P"),            # a pitcher's bat: out of the anchor
           _hit(7, None, 99999, 1)]                 # no club: skipped everywhere
    _put(c, "hitting_11_2025.json", hit)
    season = [_pit(21, 10, 1700, 300, 420, 20, 20), _pit(22, 11, 1500, 240, 360, 40, 0),
              _pit(23, 12, 1600, 270, 380, 25, 12), _pit(24, None, 5000, 3, 4, 1, 0)]
    _put(c, "pitching_11_2025.json", season)
    roles = [_pit(21, 10, 1700, 300, int(420 * sp_bf_scale), 20, 20, code="sp"),
             _pit(22, 11, 1500, 240, int(360 * sp_bf_scale), 40, 0, code="rp"),
             _pit(23, 12, 1100, 180, int(250 * sp_bf_scale), 12, 12, code="sp"),
             _pit(23, 12, 500, 90, int(130 * sp_bf_scale), 13, 0, code="rp")]
    if drop_role_for is not None:
        roles = [r for r in roles if r["mlbam"] != drop_role_for]
    _put(c, "pitching_sprp_11_2025.json", roles)


def test_pooled_anchors_are_sums_over_sums(sandbox):
    _aaa_2025(sandbox["cache"])
    lr = P.league_rates("AAA", 2025)
    assert lr["tracking"] == "usable" and lr["basis"] == P.BASIS_ROLE
    np_ = 400 + 1950 + 3900 + 1200 + 4000
    pa = 100 + 500 + 1000 + 300 + 1000
    assert lr["hit"]["p_pa"] == pytest.approx(np_ / pa)
    mean_of_rates = sum([4.0, 3.9, 3.9, 4.0, 4.0]) / 5
    assert lr["hit"]["p_pa"] != pytest.approx(mean_of_rates, abs=1e-6)
    assert lr["sp"]["p_ip"] == pytest.approx((1700 + 1100) / ((300 + 180) / 3))
    assert lr["sp"]["p_bf"] == pytest.approx((1700 + 1100) / (420 + 250))
    assert lr["sp"]["pit_per_gs"] == pytest.approx((1700 + 1100) / 32)
    assert lr["rp"]["p_ip"] == pytest.approx((1500 + 500) / ((240 + 90) / 3))
    assert lr["role_parity"]["verdict"] == "ok"


def test_player_lines_sum_stints_and_take_the_majority_role(sandbox):
    c = sandbox["cache"]
    _aaa_2025(c)
    rows = json.loads((c / "hitting_11_2025.json").read_text())["rows"]
    rows.append(_hit(1, 11, 410, 100))                  # a second stint for player 1
    _put(c, "hitting_11_2025.json", rows)
    pl = P.player_lines(2025, "AAA")
    assert pl[1]["hit"]["pa"] == 200 and pl[1]["hit"]["np"] == 810
    assert pl[1]["hit"]["p_pa"] == pytest.approx(810 / 200)
    assert 7 not in pl                                   # the no-club row is skipped
    p23 = pl[23]["pit"]
    assert p23["role"] == "SP" and p23["basis"] == P.BASIS_ROLE
    assert p23["p_ip"] == pytest.approx(1100 / 60)
    lr = P.league_rates("AAA", 2025)
    assert P.par(p23["p_ip"], lr["sp"]["p_ip"]) == round(100 * (1100 / 60) / lr["sp"]["p_ip"])


# --------------------------------------------------------------------------- #
# Role-split parity: fallback and exclusion
# --------------------------------------------------------------------------- #
def test_role_split_off_by_more_than_half_a_percent_stamps_season_line_fallback(sandbox):
    _aaa_2025(sandbox["cache"], sp_bf_scale=0.98)
    lr = P.league_rates("AAA", 2025)
    assert lr["role_parity"]["verdict"] == "fallback"
    assert lr["basis"] == P.BASIS_FALLBACK
    assert lr["pitching_status"] == "usable"
    # the fallback anchors come from the season lines: GS/G >= 0.8 starts, GS = 0 relief
    assert lr["sp"]["p_ip"] == pytest.approx(1700 / 100)
    assert lr["rp"]["p_ip"] == pytest.approx(1500 / 80)
    pl = P.player_lines(2025, "AAA")
    assert all(v["pit"]["basis"] == P.BASIS_FALLBACK for v in pl.values() if v["pit"])


def test_a_pitcher_missing_from_the_role_split_is_stamped_fallback(sandbox):
    _aaa_2025(sandbox["cache"], drop_role_for=21)
    # dropping one pitcher moves the level-season's BF far past 5 percent, so build
    # the level-season parity from a larger pool first
    c = sandbox["cache"]
    season = json.loads((c / "pitching_11_2025.json").read_text())["rows"]
    roles = json.loads((c / "pitching_sprp_11_2025.json").read_text())["rows"]
    for i in range(400):
        season.append(_pit(1000 + i, 13, 1600, 270, 380, 30, 0))
        roles.append(_pit(1000 + i, 13, 1600, 270, 380, 30, 0, code="rp"))
    _put(c, "pitching_11_2025.json", season)
    _put(c, "pitching_sprp_11_2025.json", roles)
    lr = P.league_rates("AAA", 2025)
    assert lr["basis"] == P.BASIS_ROLE
    pl = P.player_lines(2025, "AAA")
    assert pl[21]["pit"]["basis"] == P.BASIS_FALLBACK
    assert pl[21]["pit"]["role"] == "SP"
    assert pl[21]["pit"]["p_ip"] == pytest.approx(1700 / 100)
    assert pl[22]["pit"]["basis"] == P.BASIS_ROLE


def test_role_split_off_by_more_than_five_percent_is_excluded_not_a_stop(sandbox):
    _aaa_2025(sandbox["cache"], sp_bf_scale=0.9)
    lr = P.league_rates("AAA", 2025)
    assert lr["role_parity"]["verdict"] == "excluded"
    assert lr["pitching_status"] == "untracked"
    assert lr["pitching_stamp"] == P.STAMP_MISMATCH
    assert lr["sp"]["p_ip"] is None and lr["rp"]["p_ip"] is None
    assert lr["hit"]["p_pa"] is not None                 # hitters are unaffected
    pl = P.player_lines(2025, "AAA")
    assert all(v["pit"]["p_ip"] is None for v in pl.values() if v["pit"])


# --------------------------------------------------------------------------- #
# Fetchers: no network, and a failure files ingest health
# --------------------------------------------------------------------------- #
def test_a_failed_fetch_keeps_the_cache_and_files_a_red(sandbox):
    c = sandbox["cache"]
    _put(c, "hitting_11_2026.json", [_hit(1, 10, 400, 100)])
    old = c / "hitting_11_2026.json"
    import os
    os.utime(old, (0, 0))                                # stale for the current season
    rows = P.fetch_season_lines(11, 2026, "hitting", fetch=True)
    assert rows and rows[0]["mlbam"] == 1
    reds = [kw for src, kw in sandbox["filed"] if src == P.INGEST_SEASON]
    assert reds and reds[0]["ok"] is False


def test_cache_only_reads_never_reach_the_network(sandbox):
    assert P.fetch_season_lines(12, 2014, "pitching", fetch=False) == []
    assert P.fetch_role_splits(12, 2014, fetch=False) == []
    assert P.mlb_season_lines(2025, "hitting", fetch=False) == []


# --------------------------------------------------------------------------- #
# Build: preview only while the flag is False
# --------------------------------------------------------------------------- #
def _mlb_raw(mlb_dir, season):
    def split(pid, team, st, pos="C"):
        return {"player": {"id": pid}, "team": {"id": team}, "league": {"name": "AL"},
                "position": {"abbreviation": pos}, "stat": st}
    hit = [split(i, 100 + i % 30, {"numberOfPitches": 2300 + i, "plateAppearances": 600})
           for i in range(60)]
    pit = [split(500 + i, 100 + i % 30, {"numberOfPitches": 2900, "outs": 540,
                                         "battersFaced": 750, "gamesPitched": 30,
                                         "gamesStarted": 30}, pos="P") for i in range(30)]
    for group, splits in (("hitting", hit), ("pitching", pit)):
        (mlb_dir / f"fa_statsapi_{group}_{season}.json").write_text(
            json.dumps({"stats": [{"splits": splits}]}), encoding="utf-8")


def test_build_writes_nothing_under_data_while_the_flag_is_false(sandbox, monkeypatch):
    _mlb_raw(sandbox["mlb"], 2025)
    _aaa_2025(sandbox["cache"])
    assert P.SERVE_PITCH_RATES is False
    out = P.build(write=True)
    assert P.PREVIEW_PATH.exists()
    assert not P.DATA_PATH.exists()
    assert list(sandbox["data"].iterdir()) == []
    assert out["serve_flag"] is False
    assert out["milb"]["AAA"]["2025"]["tracking"] == "usable"
    assert out["mlb"]["2025"]["hit"]["p_pa"] is not None
    assert {"r", "pairs"} <= set(out["stability"]["hitter_p_pa"])
    lineup = out["teams"]["mlb"]["2025"]["lineup"]
    exact = [v["par_exact"] for v in lineup.values() if v["par_exact"] is not None]
    assert len(exact) == 30 and sum(exact) / 30 == pytest.approx(100.0, abs=1e-3)
    # the flag, and only the flag, routes the artifact to data/
    monkeypatch.setattr(P, "SERVE_PITCH_RATES", True)
    P.build(write=True)
    assert P.DATA_PATH.exists()


def test_the_real_data_path_is_untouched_by_the_flag_off_module():
    import pathlib
    real = pathlib.Path(P.__file__).resolve().parent / "data" / "pitch_rates.json"
    if not P.SERVE_PITCH_RATES:
        assert not real.exists()
