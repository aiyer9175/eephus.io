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


# ---- two-start projection ledger (2026-08-16) ------------------------------
# The instrument that grades projected second legs against the real probable
# postings (fantasy_export.update_two_start_ledger). Fixture-driven, temp file,
# no network. Covers: append, per-day idempotency, all three grade outcomes,
# grade idempotency, compaction, and the summary readout.
import json as _json
import tempfile as _tempfile
from pathlib import Path as _Path

import fantasy_export as _fe


def _ledger_path():
    return _Path(_tempfile.mkdtemp()) / "two_start_ledger.jsonl"


def _two_start_fixture(mid=10, first="2026-07-01", leg="2026-07-06"):
    return {str(mid): [
        {"mlbam": mid, "name": "P%d" % mid, "date": first, "team_org": "AAA",
         "opp_org": "BBB"},
        {"mlbam": mid, "name": "P%d" % mid, "date": leg, "team_org": "AAA",
         "opp_org": "CCC", "is_home": True, "venue": "Park", "projected": True},
    ]}


def _rows(path):
    return [_json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def test_ledger_appends_projected_leg_with_shape():
    p = _ledger_path()
    res = _fe.update_two_start_ledger(_two_start_fixture(), [], today="2026-07-01",
                                      path=p)
    assert res["projected_added"] == 1 and res["grades_added"] == 0
    rows = _rows(p)
    assert len(rows) == 1
    r = rows[0]
    assert r["kind"] == "projected" and r["mlbam"] == 10
    assert r["date_projected"] == "2026-07-01" and r["leg_date"] == "2026-07-06"
    assert r["leg_date_window"] == ["2026-07-05", "2026-07-07"]
    assert r["org"] == "AAA" and r["source_row"]["opp_org"] == "CCC"
    # announced legs are never ledgered: only the projected guess is a claim.
    assert all(row["leg_date"] != "2026-07-01" for row in rows)


def test_ledger_idempotent_per_day_and_appends_next_day():
    p = _ledger_path()
    two = _two_start_fixture()
    _fe.update_two_start_ledger(two, [], today="2026-07-01", path=p)
    res = _fe.update_two_start_ledger(two, [], today="2026-07-01", path=p)
    assert res["projected_added"] == 0, "same-day rerun must dedupe"
    assert len(_rows(p)) == 1
    # The same leg re-served the NEXT day is a new dated observation.
    res = _fe.update_two_start_ledger(two, [], today="2026-07-02", path=p)
    assert res["projected_added"] == 1
    assert len([r for r in _rows(p) if r["kind"] == "projected"]) == 2


def test_ledger_grades_started_and_never_regrades():
    p = _ledger_path()
    _fe.update_two_start_ledger(_two_start_fixture(), [], today="2026-07-01", path=p)
    ann = [{"mlbam": 10, "d": "2026-07-06"}]
    res = _fe.update_two_start_ledger({}, ann, today="2026-07-03", path=p)
    assert res["grades_added"] == 1
    g = [r for r in _rows(p) if r["kind"] == "grade"]
    assert len(g) == 1 and g[0]["resolved"] == "started"
    assert g[0]["projected_date"] == "2026-07-06" and g[0]["resolved_date"] == "2026-07-06"
    # A graded leg stays graded: rerunning with the same posting adds nothing.
    res = _fe.update_two_start_ledger({}, ann, today="2026-07-04", path=p)
    assert res["grades_added"] == 0
    assert len([r for r in _rows(p) if r["kind"] == "grade"]) == 1


def test_ledger_grades_pushed_on_slid_posting():
    p = _ledger_path()
    _fe.update_two_start_ledger(_two_start_fixture(), [], today="2026-07-01", path=p)
    # Posted a day late: same start, calendar slid. Slack is 2 days.
    res = _fe.update_two_start_ledger({}, [{"mlbam": 10, "d": "2026-07-07"}],
                                      today="2026-07-04", path=p)
    assert res["grades_added"] == 1
    g = [r for r in _rows(p) if r["kind"] == "grade"][0]
    assert g["resolved"] == "pushed" and g["resolved_date"] == "2026-07-07"


def test_ledger_grades_skipped_after_date_passes():
    p = _ledger_path()
    _fe.update_two_start_ledger(_two_start_fixture(), [], today="2026-07-01", path=p)
    # While the leg date is ahead and nothing posted, it stays PENDING.
    res = _fe.update_two_start_ledger({}, [], today="2026-07-05", path=p)
    assert res["grades_added"] == 0
    # Once the date passes with no matching posting ever seen, it is a skip.
    res = _fe.update_two_start_ledger({}, [], today="2026-07-09", path=p)
    assert res["grades_added"] == 1
    g = [r for r in _rows(p) if r["kind"] == "grade"][0]
    assert g["resolved"] == "skipped" and g["resolved_date"] == "2026-07-09"


def test_ledger_first_leg_cannot_confirm_itself():
    p = _ledger_path()
    # The announced FIRST leg (07-01) sits 5 days from the projected second
    # (07-06), outside the 2-day slack, so it never grades the projection.
    _fe.update_two_start_ledger(_two_start_fixture(),
                                [{"mlbam": 10, "d": "2026-07-01"}],
                                today="2026-07-01", path=p)
    assert [r for r in _rows(p) if r["kind"] == "grade"] == []


def test_ledger_compaction_bounds_the_file():
    p = _ledger_path()
    _fe.update_two_start_ledger(_two_start_fixture(mid=10), [],
                                today="2026-01-01", path=p)
    old = _rows(p)
    assert len(old) == 1
    # 200+ days later, the stale projection row is compacted away on write.
    res = _fe.update_two_start_ledger(
        _two_start_fixture(mid=11, first="2026-08-01", leg="2026-08-06"), [],
        today="2026-08-01", path=p)
    assert res["compacted_away"] == 1, res
    rows = _rows(p)
    assert all(r.get("date_projected", "2026-08-01") >= "2026-04-03" for r in rows)
    assert any(r["mlbam"] == 11 for r in rows)
    assert not any(r.get("mlbam") == 10 and r["kind"] == "projected" for r in rows)


def test_ledger_summary_counts_and_hit_rates():
    p = _ledger_path()
    two = {}
    two.update(_two_start_fixture(mid=10))
    two.update(_two_start_fixture(mid=11))
    two.update(_two_start_fixture(mid=12))
    _fe.update_two_start_ledger(two, [], today="2026-07-01", path=p)
    # Re-serve next day: distinct legs must stay 3, not 6.
    _fe.update_two_start_ledger(two, [], today="2026-07-02", path=p)
    # 10 starts as projected, 11 slides a day, 12 never posts and passes.
    _fe.update_two_start_ledger({}, [{"mlbam": 10, "d": "2026-07-06"},
                                     {"mlbam": 11, "d": "2026-07-07"}],
                                today="2026-07-09", path=p)
    s = _fe.two_start_ledger_summary(p)
    assert s["n_distinct_legs"] == 3 and s["n_projected_rows"] == 6
    assert s["n_graded"] == 3 and s["n_pending"] == 0
    assert s["by_outcome"] == {"started": 1, "pushed": 1, "skipped": 1}
    assert s["hit_rate_strict"] == round(1 / 3, 3)
    assert s["hit_rate_with_pushed"] == round(2 / 3, 3)
    assert s["first_projected"] == "2026-07-01"
    assert s["last_projected"] == "2026-07-02"


def test_ledger_tolerates_corrupt_line():
    p = _ledger_path()
    _fe.update_two_start_ledger(_two_start_fixture(), [], today="2026-07-01", path=p)
    with p.open("a", encoding="utf-8") as fh:
        fh.write("{torn write\n")
    res = _fe.update_two_start_ledger({}, [{"mlbam": 10, "d": "2026-07-06"}],
                                      today="2026-07-03", path=p)
    assert res["grades_added"] == 1


if __name__ == "__main__":
    import sys
    mod = sys.modules[__name__]
    fns = [f for n, f in vars(mod).items() if n.startswith("test_") and callable(f)]
    for f in fns:
        f()
    print(f"ALL {len(fns)} fantasy_two_start tests PASS")
