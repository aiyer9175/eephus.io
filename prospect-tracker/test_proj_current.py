# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Current-season (2026) Team Outlook overlay guards. Fully synthetic — no
network, no corpus — so they run locally and in CI. Covers the shared machinery
(log5, Monte-Carlo bracket, schedule fallback), the widened standings parser,
the Bayesian+Pythag blend, and the load-bearing invariant: the overlay must
NEVER move the published 2027 projection output."""

from __future__ import annotations

import copy
import json

import pytest

import proj_current as pc
import proj_export as pe
import fa_fit_backtest as fb


# --------------------------------------------------------------------------- #
# log5
# --------------------------------------------------------------------------- #
def test_log5_properties():
    assert abs(pc.log5(0.6, 0.5) - 0.6) < 1e-9        # vs .500 -> p itself
    assert abs(pc.log5(0.5, 0.5) - 0.5) < 1e-9        # equal -> coin flip
    assert abs(pc.log5(0.7, 0.3) + pc.log5(0.3, 0.7) - 1.0) < 1e-9  # mirror sums to 1
    assert 0.0 <= pc.log5(1e-12, 1 - 1e-12) <= 1.0    # rails: no div-by-zero


# --------------------------------------------------------------------------- #
# Pythag + talent prior + blend
# --------------------------------------------------------------------------- #
def test_pythag_fixed_183():
    p = pe._pythag_pct(750, 650)
    assert 0.56 < p < 0.58                             # ~.571 at league avg
    assert pe._pythag_pct(0, 0) is None
    assert pe._pythag_pct(None, 5) is None


def test_talent_prior_clamped():
    assert pe._talent_prior_pct(81) == 0.5
    assert pe._talent_prior_pct(10) == 0.20            # clamps low
    assert pe._talent_prior_pct(160) == 0.80           # clamps high


def test_blend_weights_and_shift():
    rec = {"wins": 20, "losses": 20, "pct": 0.5, "gamesPlayed": 40,
           "rs": 180, "ra": 170, "divGb": 2.0}
    b = pe._current_blend(rec, 0.560, k=40)
    assert b["blendWeights"]["prior"] == 0.5           # k/(k+G) at G=40
    assert abs(sum(b["blendWeights"].values()) - 1.0) < 1e-9
    assert b["actualPct"] == 0.5
    assert 0 <= b["curWins"] <= 162 and b["curWins"] + b["curLosses"] == 162
    # prior weight strictly decreases as games accumulate
    prev = None
    for g in (1, 10, 40, 81, 162):
        wp = 40 / (40 + g)
        assert prev is None or wp < prev
        prev = wp


def test_blend_full_season_is_actual():
    """At 162 games there are no games left, so the projected record equals the
    actual record regardless of prior/Pythag."""
    rec = {"wins": 95, "losses": 67, "pct": 95 / 162, "gamesPlayed": 162,
           "rs": 800, "ra": 700, "divGb": 0.0}
    b = pe._current_blend(rec, 0.55, k=40)
    assert b["curWins"] == 95 and b["curLosses"] == 67


def test_blend_prefers_statsapi_pythag():
    """When StatsAPI ships xWinLoss, the blend uses it over the RS/RA compute."""
    rec = {"wins": 50, "losses": 40, "gamesPlayed": 90, "rs": 400, "ra": 380,
           "pythagWins": 48, "pythagLosses": 42, "divGb": 0.0}
    b = pe._current_blend(rec, 0.55)
    assert abs(b["pythagPct"] - 48 / 90) < 1e-3


# --------------------------------------------------------------------------- #
# Monte-Carlo bracket
# --------------------------------------------------------------------------- #
def _league30():
    teams = {}
    for dv, members in pc._DIVISIONS.items():
        lg = 103 if dv.startswith("AL") else 104
        for org in members:
            teams[org] = {"wins": 50, "losses": 50, "p": 0.5, "league": lg, "div": dv}
    return teams


def test_mc_bracket_invariant():
    odds = pc.simulate_playoffs(_league30(), [], n_sims=400)
    assert len(odds) == 30
    teams = _league30()
    for lg in (103, 104):
        play = sum(odds[o]["playoffPct"] for o, t in teams.items() if t["league"] == lg)
        div = sum(odds[o]["divisionPct"] for o, t in teams.items() if t["league"] == lg)
        assert abs(play - 6.0) < 0.02                  # 3 div + 3 WC per league
        assert abs(div - 3.0) < 0.02
    # playoffPct is derived as exactly divisionPct + wildcardPct (disjoint sets).
    for v in odds.values():
        assert abs(v["playoffPct"] - (v["divisionPct"] + v["wildcardPct"])) < 1e-9


def test_mc_empty_schedule_keeps_current_wins():
    odds = pc.simulate_playoffs(_league30(), [], n_sims=100)
    assert all(o["projWinsMean"] == 50.0 for o in odds.values())


def test_mc_strong_beats_weak():
    t = {"AAA": {"wins": 0, "losses": 0, "p": 0.99, "league": 103, "div": "AL_E"},
         "BBB": {"wins": 0, "losses": 0, "p": 0.01, "league": 103, "div": "AL_E"}}
    odds = pc.simulate_playoffs(t, [("AAA", "BBB")] * 40, n_sims=200)
    assert odds["AAA"]["projWinsMean"] > odds["BBB"]["projWinsMean"]


def test_mc_degrades_on_partial_standings():
    # missing league/div -> no odds
    assert pc.simulate_playoffs({"X": {"wins": 1, "losses": 1, "p": 0.5}}, []) == {}
    assert pc.simulate_playoffs({}, []) == {}


def test_mc_reproducible():
    t = _league30()
    a = pc.simulate_playoffs(t, [("NYY", "BOS")] * 10, n_sims=100, seed=7)
    b = pc.simulate_playoffs(t, [("NYY", "BOS")] * 10, n_sims=100, seed=7)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# --------------------------------------------------------------------------- #
# schedule fallback
# --------------------------------------------------------------------------- #
def test_balanced_fallback_covers_teams():
    teams = [o for members in pc._DIVISIONS.values() for o in members]
    sched = pc.balanced_remaining(teams, default_games=60)
    assert all(len(sched[t]) == 60 for t in teams)
    # ~76% intra-division on average
    div_of = pc._div_of
    intra = sum(1 for t in teams for o in sched[t] if div_of(o) == div_of(t))
    total = sum(len(v) for v in sched.values())
    assert 0.68 <= intra / total <= 0.84


# --------------------------------------------------------------------------- #
# standings_now parser
# --------------------------------------------------------------------------- #
def _fake_fetch(payload):
    class FR:
        status = 200
        body = json.dumps(payload)
    return lambda *a, **k: FR()


def test_standings_now_parse(monkeypatch):
    payload = {"records": [{"league": {"id": 103}, "division": {"id": 201},
        "teamRecords": [
          {"team": {"name": "Boston Red Sox"}, "wins": "55", "losses": "40",
           "winningPercentage": "0.579", "gamesPlayed": 95, "runsScored": 480,
           "runsAllowed": 410, "runDifferential": 70, "gamesBack": "-",
           "divisionGamesBack": "-", "wildCardGamesBack": "2.5",
           "divisionRank": "1", "leagueRank": "2", "streak": {"streakCode": "W3"},
           "records": {"expectedRecords": [{"type": "xWinLoss", "wins": 53, "losses": 42}]}},
          {"team": {"name": "Some Very Long Affiliate Name"}, "wins": "1"},  # dropped
        ]}]}
    monkeypatch.setattr(fb, "_fetch", _fake_fetch(payload))
    out = fb.standings_now(2026)
    assert set(out) == {"BOS"}
    b = out["BOS"]
    assert b["wins"] == 55 and b["losses"] == 40 and abs(b["pct"] - 0.579) < 1e-9
    assert b["rs"] == 480 and b["ra"] == 410 and b["runDiff"] == 70
    assert b["gb"] == 0.0 and b["wcGb"] == 2.5 and b["league"] == 103 and b["div"] == 201
    assert b["pythagWins"] == 53 and b["pythagLosses"] == 42


def test_standings_now_degrades(monkeypatch):
    class FR0:
        status = 500
        body = ""
    monkeypatch.setattr(fb, "_fetch", lambda *a, **k: FR0())
    assert fb.standings_now(2026) == {}


def test_sn_coercion_helpers():
    assert fb._sn_float("-", dash=None) is None
    assert fb._sn_float("-") == 0.0
    assert fb._sn_float("0.5") == 0.5
    assert fb._sn_int("7") == 7 and fb._sn_int(None) is None and fb._sn_int("x") is None


# --------------------------------------------------------------------------- #
# the load-bearing invariant: overlay never moves the 2027 output
# --------------------------------------------------------------------------- #
def _row(tm, wins):
    return {"team": tm, "war": 10.0, "wins": wins, "losses": 162 - wins,
            "winsRaw": wins, "depthWar": 1.0, "n": 20,
            "byYear": [{"season": 2027, "war": 10.0, "wins": wins,
                        "losses": 162 - wins, "winsRaw": wins, "depthWar": 1.0, "n": 20}],
            "lockedPct": 0.7, "ctrlWar5y": 40.0, "fullWar5y": 55.0,
            "top": [{"name": "X", "key": "x", "war": 5.0}], "farm": None}


def test_overlay_noop_on_empty_standings():
    rows = [_row("BOS", 90), _row("NYY", 95)]
    base = copy.deepcopy(rows)
    assert pe._attach_current_season(rows, {}, season=2026) is None
    assert rows == base


def test_overlay_preserves_2027_fields(monkeypatch):
    # force the fallback schedule (no network) for determinism
    monkeypatch.setattr(pc, "remaining_schedule", lambda season, today=None: {})
    monkeypatch.setattr(pc, "remaining_pairs", lambda season, today=None: [])
    rows = [_row("BOS", 90), _row("NYY", 95)]
    base = copy.deepcopy(rows)
    standings = {
        "BOS": {"wins": 55, "losses": 40, "pct": 0.579, "gamesPlayed": 95,
                "rs": 480, "ra": 410, "runDiff": 70, "divGb": 0.0,
                "league": 103, "div": 201, "pythagWins": 53, "pythagLosses": 42},
        "NYY": {"wins": 58, "losses": 37, "pct": 0.611, "gamesPlayed": 95,
                "rs": 500, "ra": 400, "runDiff": 100, "divGb": 0.0,
                "league": 103, "div": 201, "pythagWins": 57, "pythagLosses": 38},
    }
    src = pe._attach_current_season(rows, standings, season=2026)
    assert src == "balanced_fallback"
    new_keys = {"current", "curWins", "curPct"}
    for r, b in zip(rows, base):
        stripped = {k: v for k, v in r.items() if k not in new_keys}
        assert stripped == b            # every 2027 field byte-identical
        assert r["current"] is not None
        for f in ("curPct", "actualPct", "pythagPct", "talentPriorPct",
                  "sos", "remGames", "playoffPct", "projWinsMean"):
            assert f in r["current"]
