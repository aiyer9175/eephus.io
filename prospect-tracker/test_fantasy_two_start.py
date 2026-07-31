# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Unit tests for fantasy_schedule's projected two-start builder (synthetic
games, no network).

Probables only post ~4-5 days out, so the announced-only two_start_pitchers()
was empty by construction over a 7-day window. projected_two_start() fills the
gap: a pitcher with one announced start on date D gets a PROJECTED second leg
on the team's next slate day in D+4..D+6 (normal rest) inside the window,
flagged `projected: True`. Covers: the projected pair, the no-game-in-range
miss, the untouched announced pair, the window_end cutoff, and team_schedule's
doubleheader dedupe."""
from __future__ import annotations

import fantasy_schedule as fsched


WINDOW_END = "2026-07-07"


def _side(org, team_id, pp_mlbam=None):
    return {"team_id": team_id, "team": org, "org": org,
            "probable": ({"mlbam": pp_mlbam, "name": "P%d" % pp_mlbam}
                         if pp_mlbam else None),
            "record": None}


def _game(pk, d, home, away, *, home_pp=None, away_pp=None, venue="Park", dh=False):
    """One game in fetch_probables' output shape. home/away = (org, team_id)."""
    return {"game_pk": pk, "date": d, "datetime": d + "T17:00:00Z",
            "status": "Preview", "double_header": dh,
            "venue": {"id": 1, "name": venue},
            "home": _side(home[0], home[1], home_pp),
            "away": _side(away[0], away[1], away_pp)}


AAA, BBB, CCC, DDD, EEE = ("AAA", 1), ("BBB", 2), ("CCC", 3), ("DDD", 4), ("EEE", 5)


def _build(games):
    starts = fsched.starts_index(games)
    sched = fsched.team_schedule(games)
    return fsched.projected_two_start(starts, sched, WINDOW_END)


# ---- team_schedule ---------------------------------------------------------
def test_team_schedule_ignores_probable_filter_and_sorts():
    games = [_game(2, "2026-07-06", AAA, CCC),                 # no probables at all
             _game(1, "2026-07-01", AAA, BBB, home_pp=10)]
    sched = fsched.team_schedule(games)
    assert [g["date"] for g in sched["AAA"]] == ["2026-07-01", "2026-07-06"]
    leg = sched["AAA"][1]
    assert leg["opp_org"] == "CCC" and leg["opp_team_id"] == 3
    assert leg["is_home"] is True and leg["venue"] == "Park"
    # Both sides of every game are indexed.
    assert [g["date"] for g in sched["CCC"]] == ["2026-07-06"]
    assert sched["CCC"][0]["is_home"] is False


def test_team_schedule_dedupes_doubleheader_dates():
    games = [_game(1, "2026-07-02", AAA, BBB, dh=True),
             _game(2, "2026-07-02", AAA, BBB, dh=True)]
    sched = fsched.team_schedule(games)
    assert len(sched["AAA"]) == 1 and len(sched["BBB"]) == 1


# ---- projected_two_start ---------------------------------------------------
def test_announced_start_plus_team_game_projects_second_leg():
    # P10 announced 07-01; AAA's next game 07-06 (D+5, in D+4..D+6) -> pair.
    games = [_game(1, "2026-07-01", AAA, BBB, home_pp=10),
             _game(2, "2026-07-06", AAA, CCC)]                 # no probable posted
    two = _build(games)
    assert set(two) == {10}
    legs = two[10]
    assert len(legs) == 2
    assert legs[0]["date"] == "2026-07-01" and "projected" not in legs[0]
    proj = legs[1]
    assert proj["projected"] is True
    assert proj["date"] == "2026-07-06" and proj["opp_org"] == "CCC"
    assert proj["opp_team_id"] == 3 and proj["team_org"] == "AAA"
    assert proj["mlbam"] == 10 and proj["name"] == "P10"


def test_no_team_game_in_rest_window_means_no_pair():
    # P20 announced 07-01; DDD's only other game is 07-02 (D+1, outside D+4..D+6).
    games = [_game(1, "2026-07-01", DDD, BBB, home_pp=20),
             _game(2, "2026-07-02", DDD, CCC)]
    assert _build(games) == {}


def test_two_announced_starts_stay_untouched():
    # P30 announced twice -> the announced pair passes through, no projection.
    games = [_game(1, "2026-07-01", EEE, BBB, home_pp=30),
             _game(2, "2026-07-06", CCC, EEE, away_pp=30)]
    two = _build(games)
    assert set(two) == {30}
    legs = two[30]
    assert [l["date"] for l in legs] == ["2026-07-01", "2026-07-06"]
    assert all("projected" not in l for l in legs)


def test_rest_window_game_beyond_window_end_is_ignored():
    # AAA's candidate game sits in D+4..D+6 but past window_end -> no pair.
    games = [_game(1, "2026-07-04", AAA, BBB, home_pp=10),
             _game(2, "2026-07-08", AAA, CCC)]                 # beyond 2026-07-07
    assert _build(games) == {}


def test_first_slate_day_in_rest_window_wins():
    # Games on D+4 and D+6: the projected leg lands on D+4 (earliest in range).
    games = [_game(1, "2026-07-01", AAA, BBB, home_pp=10),
             _game(2, "2026-07-05", AAA, CCC),
             _game(3, "2026-07-07", AAA, DDD)]
    two = _build(games)
    assert two[10][1]["date"] == "2026-07-05"
    assert two[10][1]["opp_org"] == "CCC"


if __name__ == "__main__":
    import sys
    mod = sys.modules[__name__]
    fns = [f for n, f in vars(mod).items() if n.startswith("test_") and callable(f)]
    for f in fns:
        f()
    print(f"ALL {len(fns)} fantasy_two_start tests PASS")
