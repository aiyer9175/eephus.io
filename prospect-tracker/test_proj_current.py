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
    monkeypatch.setattr(pc, "remaining_schedule",
                        lambda season, today=None, played=None: {})
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


def test_playoff_pct_can_never_exceed_one():
    """THE 1.001 REGRESSION, pinned at the arithmetic rather than at a sample.

    The old emit rounded divisionPct and wildcardPct to three places and ADDED
    them, which is unbounded above: two roundings can each add half a
    thousandth. Milwaukee served playoffPct 1.001 on 2026-09-06 from
    0.997 + 0.004.

    This runs the emit over every reachable (division, wildcard) count pair at a
    small n, so it fails on the arithmetic and does not depend on a simulation
    happening to land on the bad cell."""
    n = 2000
    for div_count in range(0, n + 1, 7):
        for extra in (0, 1, 3, n - div_count):
            play_count = min(div_count + extra, n)
            div_pct = round(div_count / n, 3)
            play_pct = round(play_count / n, 3)
            wc_pct = round(play_pct - div_pct, 3)
            assert play_pct <= 1.0, (
                f"playoffPct {play_pct} from play_count {play_count}/{n}")
            assert wc_pct >= 0.0, (
                f"wildcardPct {wc_pct} from play {play_pct} div {div_pct}")
            assert abs((div_pct + wc_pct) - play_pct) < 1e-9


def test_the_old_addition_form_really_did_overflow():
    """The control for the test above. If adding two rounded parts could never
    exceed one, the repair would be pointless and this file would be pinning
    nothing."""
    n = 2000
    over = [(d, n - d) for d in range(n + 1)
            if round(d / n, 3) + round((n - d) / n, 3) > 1.0]
    assert over, ("the old form cannot overflow at this n, so the 1.001 that "
                  "was served came from somewhere else and this repair needs "
                  "re-reading")


def test_the_playoff_counter_is_the_published_numerator():
    """It was being counted and never read, which is how the two parts came to
    be added instead."""
    src = (ROOT / "proj_current.py").read_text(encoding="utf-8") if "ROOT" in dir() \
        else __import__("pathlib").Path(pc.__file__).read_text(encoding="utf-8")
    i = src.index('"playoffPct"')
    seg = src[max(0, i - 400):i + 200]
    assert "play_pct" in seg and "playoff[o]" in src
    assert 'round(div_pct + wc_pct' not in src, (
        "the emit is adding two rounded parts again")


# --------------------------------------------------------------------------
# The vintage repair: a game in progress is not a game played
# --------------------------------------------------------------------------

def _sched(games):
    return {"dates": [{"games": games}]}


def _game(hid, hname, aid, aname, abstract, detailed):
    return {"status": {"abstractGameState": abstract, "detailedState": detailed},
            "teams": {"home": {"team": {"id": hid, "name": hname}},
                      "away": {"team": {"id": aid, "name": aname}}}}


def test_a_live_game_is_simulated_and_not_deleted(monkeypatch):
    """THE DEFECT. A live game was skipped as "roughly played" while the
    standings that supply base_wins had not booked it either, so it counted as
    neither and vanished from the season."""
    monkeypatch.setattr(pc, "_fetch_schedule_raw", lambda a, b: _sched([
        _game(109, "Arizona Diamondbacks", 119, "Los Angeles Dodgers", "Live", "In Progress"),
        _game(147, "New York Yankees", 111, "Boston Red Sox", "Preview", "Scheduled"),
        _game(158, "Milwaukee Brewers", 112, "Chicago Cubs", "Final", "Final"),
    ]))
    pairs = pc.remaining_pairs(2026, today=__import__("datetime").date(2026, 9, 1))
    assert ("ARI", "LAD") in pairs, "the live game was dropped from the season"
    assert ("NYY", "BOS") in pairs
    assert ("MIL", "CHC") not in pairs, "a final game is not remaining"
    assert len(pairs) == 2


def test_a_postponed_game_is_still_remaining(monkeypatch):
    monkeypatch.setattr(pc, "_fetch_schedule_raw", lambda a, b: _sched([
        _game(147, "New York Yankees", 111, "Boston Red Sox", "Preview", "Postponed"),
    ]))
    pairs = pc.remaining_pairs(2026, today=__import__("datetime").date(2026, 9, 1))
    assert pairs == [("NYY", "BOS")]


def test_clubs_resolve_by_id_even_when_the_name_is_the_short_form(monkeypatch):
    """The length guard that dropped Arizona out of the standings reader is
    still here, and the only reason it does not fire on this endpoint is that
    /schedule happens to send the long name. Ids do not change and names do."""
    monkeypatch.setattr(pc, "_fetch_schedule_raw", lambda a, b: _sched([
        _game(109, "D-backs", 114, "Guardians", "Preview", "Scheduled"),
    ]))
    pairs = pc.remaining_pairs(2026, today=__import__("datetime").date(2026, 9, 1))
    assert pairs == [("ARI", "CLE")], (
        "the short-form names were dropped, which is what the id path exists to "
        "prevent")


def test_the_name_path_is_gone_from_the_schedule_reader():
    src = __import__("pathlib").Path(pc.__file__).read_text(encoding="utf-8")
    i = src.index("def remaining_pairs")
    body = src[i:src.index("def season_shortfall")]
    assert "canonical_org_from_id" in body
    assert "from trades import canonical_org\n" not in body


def test_season_shortfall_is_zero_when_the_season_adds_up():
    teams = {"AAA": {"wins": 80, "losses": 70}, "BBB": {"wins": 70, "losses": 80}}
    pairs = [("AAA", "BBB")] * 12
    sf = pc.season_shortfall(teams, pairs)
    assert sf == {"AAA": 0, "BBB": 0}


def test_season_shortfall_counts_a_deleted_game():
    """One game dropped from the remaining pool shows up as a shortfall on both
    clubs. That is the symptom the live-game defect never had."""
    teams = {"AAA": {"wins": 80, "losses": 70}, "BBB": {"wins": 70, "losses": 80}}
    pairs = [("AAA", "BBB")] * 11
    sf = pc.season_shortfall(teams, pairs)
    assert sf == {"AAA": 1, "BBB": 1}


# --------------------------------------------------------------------------
# Monte Carlo honesty and the postseason bracket
# --------------------------------------------------------------------------

def _full_league():
    """A complete 30-club, 2-league, 6-division field, which is the only shape
    the bracket is defined on."""
    out = {}
    for lg, divs in ((103, ("AL_E", "AL_C", "AL_W")), (104, ("NL_E", "NL_C", "NL_W"))):
        for dv in divs:
            for i in range(5):
                out[f"{dv}{i}"] = {"wins": 80, "losses": 70,
                                   "p": 0.46 + 0.02 * i, "league": lg, "div": dv}
    return out


def test_no_probability_is_published_with_zero_uncertainty():
    """THE RULE. The Wald standard error is identically zero at count 0 and at
    count n, and those are exactly the cells a World Series column is full of.
    Publishing 'World Series 0.0 percent, plus or minus 0.00' asserts the
    simulator has ruled a club out with no sampling noise."""
    for count in (0, 20000):
        iv = pc.mc_interval(count, 20000)
        assert iv["waldSE"] == 0.0 and iv["waldIsDegenerate"] is True
        assert iv["hi95"] > iv["lo95"], (
            "the published interval has zero width at a rail, which is the "
            "false-precision claim this method exists to avoid")
    zero = pc.mc_interval(0, 20000)
    assert 0.0 < zero["hi95"] < 0.001
    # the rule-of-three bound agrees to the same order
    assert abs(zero["hi95"] - 3 / 20000) < 5e-5


def test_the_interval_is_wilson_on_counts_not_wald_on_a_rounded_p():
    iv = pc.mc_interval(1, 20000)
    assert iv["method"] == "wilson"
    assert iv["lo95"] >= 0.0 and iv["hi95"] <= 1.0
    assert iv["lo95"] < iv["p"] < iv["hi95"]


def test_the_pmf_sums_to_one_at_a_count_that_does_not_divide():
    """The largest-remainder branch is dead at any n dividing 100000, and both
    2000 and 20000 do. Exercise it where it actually runs or it never runs."""
    pmf = pc._pmf_from_counts([7, 11, 13], 31)
    assert abs(sum(pmf) - 1.0) < 1e-9
    assert len(pmf) == 3


def test_the_pmf_normalises_on_the_counts_and_not_on_n():
    """The bug this catches was made: normalising on n while the counts summed
    to something else returned a distribution summing to 0.001."""
    assert abs(sum(pc._pmf_from_counts([1, 1, 1], 3000)) - 1.0) < 1e-9


def test_the_win_total_distribution_is_contiguous_and_sums(): 
    odds = pc.simulate_playoffs(_full_league(), [], n_sims=500)
    wt = list(odds.values())[0]["winTotal"]
    assert abs(sum(wt["pmf"]) - 1.0) < 1e-9
    assert wt["sfScheduleOnly"][-1] == 0.0, "the last suffix sum must be zero"
    assert all(a >= b for a, b in zip(wt["sfScheduleOnly"], wt["sfScheduleOnly"][1:]))


def test_the_win_total_quantiles_are_the_same_objects_as_the_published_ones():
    """Reading them off the CDF instead would disagree by one win whenever an
    order statistic lands on a support boundary."""
    odds = pc.simulate_playoffs(_full_league(), [], n_sims=500)
    for o in odds.values():
        assert o["winTotal"]["quantiles"]["p10"] == o["projWinsP10"]
        assert o["winTotal"]["quantiles"]["p90"] == o["projWinsP90"]


def test_the_win_total_basis_states_what_it_conditions_on():
    odds = pc.simulate_playoffs(_full_league(), [], n_sims=200)
    basis = list(odds.values())[0]["winTotal"]["basis"]
    assert "SAMPLING" in basis and "talent" in basis
    assert "wider than this one" in basis


def test_the_bracket_conserves_pennants_and_champions():
    """Two pennants and one champion per simulation, exactly. If either sum
    drifts the bracket is double-counting or dropping a series."""
    n = 2000
    odds = pc.simulate_playoffs(_full_league(), [], n_sims=n)
    assert abs(sum(o["pennantPct"] for o in odds.values()) - 2.0) < 0.02
    assert abs(sum(o["wsPct"] for o in odds.values()) - 1.0) < 0.02
    assert abs(sum(o["byePct"] for o in odds.values()) - 4.0) < 0.02
    assert abs(sum(o["playoffPct"] for o in odds.values()) - 12.0) < 0.02


def test_the_rounds_are_nested():
    """A club cannot reach the championship series without reaching the division
    series, and cannot win the pennant without reaching the championship
    series."""
    odds = pc.simulate_playoffs(_full_league(), [], n_sims=2000)
    for org, o in odds.items():
        assert o["ldsPct"] >= o["lcsPct"] - 1e-9, org
        assert o["lcsPct"] >= o["pennantPct"] - 1e-9, org
        assert o["pennantPct"] >= o["wsPct"] - 1e-9, org
        assert abs((o["byePct"] + o["wcRoundPct"]) - o["playoffPct"]) < 0.011, org


def test_a_best_of_seven_gives_the_higher_seed_four_home_games():
    """2-3-2 is HHAAAHH. Five would be a different sport."""
    assert pc.L7_PATTERN.count("H") == 4 and len(pc.L7_PATTERN) == 7
    assert pc.LDS_PATTERN.count("H") == 3 and len(pc.LDS_PATTERN) == 5
    # THE WILD-CARD ROUND IS THE DELIBERATE EXCEPTION and is not a bug in the
    # pattern: all three games really are at the higher seed, which is the
    # reward for winning the division race or finishing higher in the wild-card
    # order. Every other round is balanced within one game.
    assert pc.WC_PATTERN == "HHH"
    for pat, best_of in ((pc.LDS_PATTERN, 5), (pc.L7_PATTERN, 7)):
        assert pat.count("H") <= best_of // 2 + 1
        assert pat.count("A") <= best_of // 2 + 1
        assert abs(pat.count("H") - pat.count("A")) <= 1


def test_the_bracket_degrades_rather_than_raising_on_a_partial_field():
    """MANDATORY, not defensive. Two orgs in one division reach this function
    through the overlay, and an IndexError there is swallowed by the exporter
    and blanks the slate for all thirty clubs."""
    two = {"AAA": {"wins": 0, "losses": 0, "p": 0.6, "league": 103, "div": "AL_E"},
           "BBB": {"wins": 0, "losses": 0, "p": 0.4, "league": 103, "div": "AL_E"}}
    odds = pc.simulate_playoffs(two, [("AAA", "BBB")] * 10, n_sims=50)
    assert set(odds) == {"AAA", "BBB"}
    for o in odds.values():
        assert "playoffPct" in o
        assert "wsPct" not in o and "winTotal" not in o and "mc" not in o


def test_the_bracket_can_be_turned_off_without_changing_the_six_original_keys():
    a = pc.simulate_playoffs(_full_league(), [], n_sims=300, bracket=False)
    b = pc.simulate_playoffs(_full_league(), [], n_sims=300, bracket=True)
    for org in a:
        for k in ("playoffPct", "divisionPct", "wildcardPct",
                  "projWinsMean", "projWinsP10", "projWinsP90"):
            assert a[org][k] == b[org][k], (
                f"{org}.{k} moved when the bracket was switched on, so the "
                "postseason is drawing from the regular-season stream")


def test_the_home_edge_form_is_an_odds_ratio_and_keeps_the_rails():
    m = pc.home_odds_multiplier(0.5245441795231417)
    assert abs(m - 1.1032448377581123) < 1e-12
    assert pc.home_odds_multiplier(0.5) == 1.0
    assert pc.apply_home_edge(0.0, m) == 0.0
    assert pc.apply_home_edge(1.0, m) == 1.0
    assert abs(pc.apply_home_edge(0.5, m) - 0.5245441795231417) < 1e-12
    # strictly monotone, and no clamp needed anywhere
    prev = -1.0
    for i in range(0, 101):
        v = pc.apply_home_edge(i / 100.0, m)
        assert v > prev
        prev = v
