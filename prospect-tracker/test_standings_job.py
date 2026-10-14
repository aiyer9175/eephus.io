# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The standings half of tools/scores_job.py (STANDINGS_2_JOB_AND_BACKFILL;
STANDINGS_PLAN 4.1 to 4.5 and 6).

Hermetic: a fake StatsAPI that answers the standings call from a synthetic
30-club season (test_standings_core's generator, so the fake is honest
standings through the date asked), fixed UTC instants, a fake clock and temp
directories through test_scores_job's `env` fixture. No test touches the
network, the repo's data/ (the tracked copy is replaced by a temp copy of a
fixture) or a real .cache/scores/.
"""
from __future__ import annotations

import builtins
import copy
import io
import json
import os
import random
import re
import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import scores_core as sc  # noqa: E402
import scores_job as job  # noqa: E402
import standings_core as st  # noqa: E402
from test_scores_job import FakeClock, _row, env  # noqa: E402,F401  (the isolated job environment)
from test_standings_core import synth_standings  # noqa: E402

UTC = timezone.utc
FIX = ROOT / "test_fixtures" / "standings"
COPYRIGHT = json.loads((FIX / "standings_2026.json").read_text(encoding="utf-8"))["copyright"]
GEN = "2026-04-06T12:00:00Z"
#: A quiet hand-run instant: past every synthetic date, outside 06:00 to 11:00 UTC.
LATER = datetime(2026, 4, 20, 14, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# A synthetic 30-club season shaped like the race schedule call's answer
# --------------------------------------------------------------------------- #
def season_schedule(n_final=8, n_future=2, start="2026-03-26", seed=5):
    """`dates[].games[]` with the race fields: n_final days of finals, then
    n_future days still scheduled. Day 2: one game postponed and never made
    up. Day 3: one game cancelled. Day 4: a split doubleheader whose game 2
    carries the SMALLER pk (so only the game number orders it) and whose clubs
    split it (the away club loses game 1 and wins game 2)."""
    rng = random.Random(seed)
    ids = sorted(sc.CLUB_BY_ID)
    d0 = date.fromisoformat(start)
    pk = 800000
    dates = []
    for i in range(n_final + n_future):
        d = (d0 + timedelta(days=i)).isoformat()
        order = ids[:]
        rng.shuffle(order)
        games = []
        for j in range(0, 30, 2):
            pk += 10
            a, h = order[j], order[j + 1]
            g = {"gamePk": pk, "gameType": "R", "officialDate": d, "gameDate": f"{d}T23:05:00Z", "gameNumber": 1,
                 "doubleHeader": "N", "teams": {"away": {"team": {"id": a}}, "home": {"team": {"id": h}}}}
            if i < n_final:
                ar, hr = rng.randint(0, 10), rng.randint(0, 10)
                hr = hr + 1 if ar == hr else hr
                g["status"] = {"codedGameState": "F"}
                g["teams"]["away"]["score"], g["teams"]["home"]["score"] = ar, hr
            else:
                g["status"] = {"codedGameState": "S"}
            games.append(g)
        if i == 2:
            g = games[0]
            g["status"] = {"codedGameState": "D"}
            g["teams"]["away"].pop("score", None)
            g["teams"]["home"].pop("score", None)
        if i == 3:
            g = games[1]
            g["status"] = {"codedGameState": "C"}
            g["teams"]["away"].pop("score", None)
            g["teams"]["home"].pop("score", None)
        if i == 4:
            g1 = games[2]
            g1.update(doubleHeader="S", gameDate=f"{d}T17:05:00Z")
            g1["teams"]["away"]["score"], g1["teams"]["home"]["score"] = 1, 4
            g2 = copy.deepcopy(g1)
            g2.update(gamePk=g1["gamePk"] - 5, gameNumber=2, gameDate=f"{d}T22:10:00Z")
            g2["teams"]["away"]["score"], g2["teams"]["home"]["score"] = 6, 2
            games.append(g2)
        dates.append({"date": d, "games": games})
    return {"dates": dates}


SCHED = season_schedule()
GAMES = st.games_from_schedule(SCHED)
FINAL_DATES = sorted({g["date"] for g in st.final_games(GAMES)})
DH = next(d["games"][-1] for d in SCHED["dates"] if d["games"][-1].get("gameNumber") == 2)
PPD = SCHED["dates"][2]["games"][0]
CAN = SCHED["dates"][3]["games"][1]


class StandingsAPI:
    """Routes the race schedule call (season=Y&gameType=R) to SCHED, the
    window schedule call to `window`, and the standings call to honest
    synthetic standings through its `date` (or, for a date in `lag`, through
    the day before: MLB lagging a final)."""

    def __init__(self, clock: FakeClock, *, games=None, sched=None, window=None, lag=(), tamper=None):
        self.clock = clock
        self.games = GAMES if games is None else games
        self.sched = SCHED if sched is None else sched
        self.window = window
        self.lag = set(lag)
        self.tamper = tamper
        self.calls: list[str] = []

    def __call__(self, url, timeout):
        self.calls.append(url)
        self.clock.t += 0.1
        q = dict(re.findall(r"[?&]([^=&]+)=([^&]*)", url))
        if "/api/v1/standings" in url:
            assert q.get("date") and "hydrate" not in q, url
            d = q["date"]
            through = (date.fromisoformat(d) - timedelta(days=1)).isoformat() if d in self.lag else d
            pay = synth_standings(self.games, through)
            if self.tamper:
                pay = self.tamper(d, pay)
            return 200, {}, json.dumps(pay).encode("utf-8")
        if "/api/v1/schedule" in url and "season=" in url and "gameType=R" in url:
            return 200, {}, json.dumps(self.sched).encode("utf-8")
        if "/api/v1/schedule" in url and self.window is not None:
            body = self.window(url) if callable(self.window) else self.window
            return 200, {}, json.dumps(body).encode("utf-8")
        return 404, {}, b""

    def standings_urls(self):
        return [u for u in self.calls if "/api/v1/standings" in u]


def kw(clock, now=LATER):
    return {"now_fn": lambda: now, "clock": clock, "sleep": clock.sleep}


def sdir(env) -> Path:
    return env["paths"]["standings_out"] / "standings"


def race_and_snapshots(env, clock, a=None, b=None, now=LATER, **api):
    """--backfill-race 2026 then --backfill-standings over the final dates."""
    p = env["paths"]
    r = job.backfill_race(2026, 2026, paths=p, adapter=StandingsAPI(clock, **api), **kw(clock, now))
    assert r["exit"] == 0, r
    api_s = StandingsAPI(clock, **api)
    res = job.backfill_standings(a or FINAL_DATES[0], b or FINAL_DATES[-1], paths=p, adapter=api_s,
                                 **kw(clock, now))
    return res, api_s


# --------------------------------------------------------------------------- #
# decide(): the due reasons of plan 4.1, the spacing, no call out of season
# --------------------------------------------------------------------------- #
NOW = datetime(2026, 6, 10, 23, 30, tzinfo=UTC)


def _iso(dt):
    return job.iso(dt)


def _slate(*rows):
    return {"fetched_at": _iso(NOW), "span": ["2026-06-09", "2026-06-11"], "games": list(rows)}


def test_reason_a_a_final_since_the_last_call_on_a_live_cycle():
    rows = [_row(1, "2026-06-10", "2026-06-10T20:05:00Z", "final", final_seen_at=_iso(NOW - timedelta(minutes=10))),
            _row(2, "2026-06-10", "2026-06-10T23:10:00Z", "live")]
    sd = job.standings_due(NOW, _slate(*rows), {"last_call_epoch": (NOW - timedelta(hours=2)).timestamp()},
                           cycle="live")
    assert sd["due"] and sd["reason"] == "a" and sd["date"] == "2026-06-10" and sd["season"] == 2026
    # nothing new since the last call: no call
    sd2 = job.standings_due(NOW, _slate(*rows), {"last_call_epoch": (NOW - timedelta(minutes=5)).timestamp()},
                            cycle="live")
    assert not sd2["due"]


def test_reason_b_the_last_final_of_a_date_plus_60_minutes_makes_a_quiet_tick_act():
    fin = NOW - timedelta(minutes=61)
    rows = [_row(1, "2026-06-10", "2026-06-10T17:05:00Z", "final", final_seen_at=_iso(fin - timedelta(hours=1))),
            _row(2, "2026-06-10", "2026-06-10T19:05:00Z", "final", final_seen_at=_iso(fin)),
            _row(3, "2026-06-11", "2026-06-11T17:05:00Z", "scheduled")]
    sst = {"last_call_epoch": (fin + timedelta(minutes=1)).timestamp(), "calls": {}}
    sd = job.standings_due(NOW, _slate(*rows), sst, cycle=None)
    assert sd["due"] and sd["reason"] == "b" and sd["date"] == "2026-06-10"
    t = int(NOW.timestamp())
    d = job.decide(NOW, _slate(*rows), {"week_date": "2026-06-10", "last_cycle_tick": job.tick_of(t) - 120},
                   standings_state=sst)
    assert d["acts"] and d["cycle"] == "due" and d["standings"]["reason"] == "b"
    # 59 minutes after the last final: not yet
    early = fin + timedelta(minutes=59)
    sd2 = job.standings_due(early, _slate(*rows), {"last_call_epoch": fin.timestamp() - 600}, cycle=None)
    assert sd2.get("reason") != "b"
    # a date already called after its due time is not called again
    sst2 = dict(sst, calls={"2026-06-10": NOW.timestamp() - 30}, last_call_epoch=NOW.timestamp() - 400)
    assert job.standings_due(NOW, _slate(*rows), sst2, cycle=None).get("reason") != "b"


def test_reason_c_the_week_cycle_finalizes_yesterday():
    now = datetime(2026, 6, 11, 10, 2, tzinfo=UTC)
    rows = [_row(1, "2026-06-10", "2026-06-10T17:05:00Z", "final", final_seen_at="2026-06-10T20:00:00Z"),
            _row(2, "2026-06-10", "2026-06-10T23:05:00Z", "postponed"),
            _row(3, "2026-06-11", "2026-06-11T17:05:00Z", "scheduled")]
    sst = {"last_call_epoch": datetime(2026, 6, 11, 2, 0, tzinfo=UTC).timestamp(),
           "calls": {"2026-06-10": datetime(2026, 6, 11, 2, 0, tzinfo=UTC).timestamp()}}
    sd = job.standings_due(now, _slate(*rows), sst, cycle="week")
    assert sd["due"] and sd["reason"] == "c" and sd["date"] == "2026-06-10"
    # once frozen, never again
    assert not job.standings_due(now, _slate(*rows), dict(sst, frozen=["2026-06-10"]), cycle="week")["due"]
    d = job.decide(now, _slate(*rows), {"week_date": "2026-06-10"}, standings_state=sst)
    assert d["cycle"] == "week" and d["standings"]["reason"] == "c"


def test_an_owed_retry_is_due_in_season():
    rows = [_row(3, "2026-06-11", "2026-06-11T17:05:00Z", "scheduled")]
    sd = job.standings_due(NOW, _slate(*rows), {"retry_date": "2026-06-09", "last_call_epoch": 0}, cycle=None)
    assert sd["due"] and sd["reason"] == "retry" and sd["date"] == "2026-06-09"


@pytest.mark.parametrize("rows", [
    [],                                                                         # offseason: nothing in the window
    [dict(_row(9, "2026-10-14", "2026-10-14T23:08:00Z", "final", final_seen_at="2026-10-14T21:00:00Z"),
          type="L")],                                                           # postseason: an LCS final
], ids=["offseason", "postseason"])
def test_no_call_in_the_postseason_or_the_offseason_even_with_a_retry_owed(rows):
    now = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    sst = {"retry_date": "2026-09-27", "last_call_epoch": 0}
    sd = job.standings_due(now, {"games": rows}, sst, cycle="week")
    assert not sd["due"] and "frozen" in sd["why"]
    d = job.decide(now, {"fetched_at": _iso(now), "games": rows}, {"week_date": "2026-10-15"}, standings_state=sst)
    assert not d["standings"]["due"]


def test_the_300_second_spacing():
    rows = [_row(1, "2026-06-10", "2026-06-10T20:05:00Z", "final", final_seen_at=_iso(NOW - timedelta(minutes=2)))]
    near = {"last_call_epoch": NOW.timestamp() - 299}
    sd = job.standings_due(NOW, _slate(*rows), near, cycle="live")
    assert not sd["due"] and sd["waiting"] == "a" and "300 s" in sd["why"]
    far = {"last_call_epoch": NOW.timestamp() - 300}
    assert job.standings_due(NOW, _slate(*rows), far, cycle="live")["due"]


# --------------------------------------------------------------------------- #
# The race from the season schedule, extended by the job's date files
# --------------------------------------------------------------------------- #
def _date_file(env, d, games):
    cards = [sc.build_card(g, generated_at=GEN) for g in games]
    job.write_bytes(env["paths"]["out"] / f"{d}.json",
                    sc.dumps(sc.build_date_file(d, cards, {}, generated_at=GEN)).encode("utf-8"))


def test_the_race_from_the_schedule_extended_by_date_files_keeps_the_doubleheader_in_order(env):
    p = env["paths"]
    d4 = SCHED["dates"][4]["date"]
    # the saved schedule still lists game 2 of the doubleheader as scheduled
    sched = copy.deepcopy(SCHED)
    g2 = next(g for g in sched["dates"][4]["games"] if g["gamePk"] == DH["gamePk"])
    g2["status"] = {"codedGameState": "S"}
    for side in ("away", "home"):
        g2["teams"][side].pop("score", None)
    job.write_json_plain(job.raw_schedule_path(p, 2026), sched)
    before = job.season_games(p, 2026)
    assert DH["gamePk"] not in {g["pk"] for g in st.final_games(before)}
    # the job's own date file for that date carries both games final
    _date_file(env, d4, [g for g in SCHED["dates"][4]["games"] if g.get("doubleHeader") == "S"])
    games = job.season_games(p, 2026)
    fins = [g for g in st.final_games(games) if g["date"] == d4 and g["gn"] in (1, 2)
            and {g["away"], g["home"]} == {DH["teams"]["away"]["team"]["id"], DH["teams"]["home"]["team"]["id"]}]
    assert [g["gn"] for g in fins] == [1, 2] and fins[1]["pk"] < fins[0]["pk"]
    away = sc.club_code(DH["teams"]["away"]["team"]["id"])
    race = st.build_race(games, 2026)
    i4 = race["dates"].index(d4)
    assert st.last_results(games, away, d4).endswith("LW")
    # the race at that date counts both games once each
    assert race["clubs"][away][i4][0] + race["clubs"][away][i4][1] == \
        race["clubs"][away][i4 - 1][0] + race["clubs"][away][i4 - 1][1] + 2
    # a postponed game and a cancelled game are never counted, never left
    assert PPD["gamePk"] not in {g["pk"] for g in st.final_games(games)}
    assert CAN["gamePk"] not in {g["pk"] for g in st.final_games(games)}


def test_a_game_listed_final_under_two_dates_counts_once_on_its_official_date():
    # StatsAPI's 2026 schedule lists 824912 (ATH at ATL) final under 2026-06-16
    # and 2026-06-17, officialDate 2026-06-16; MLB's standings count it
    # through 2026-06-16 (league W 1093 there)
    g = {"gamePk": 824912, "officialDate": "2026-06-16", "gameNumber": 1, "doubleHeader": "N",
         "status": {"codedGameState": "F"},
         "teams": {"away": {"team": {"id": 133}, "score": 7}, "home": {"team": {"id": 144}, "score": 2}}}
    sched = {"dates": [{"date": "2026-06-16", "games": [g]}, {"date": "2026-06-17", "games": [copy.deepcopy(g)]}]}
    games = st.games_from_schedule(sched)
    fins = st.final_games(games)
    assert len(fins) == 1 and fins[0]["date"] == "2026-06-16"
    race = st.build_race(games, 2026)
    assert race["dates"] == ["2026-06-16"] and race["clubs"]["ATH"] == [[1, 0, 7, 2]]
    assert job.decided_through(games, "2026-06-16") == 1
    # a suspended entry is still never counted: the final entry's date wins
    susp = copy.deepcopy(sched)
    susp["dates"][0]["games"][0]["status"] = {"codedGameState": "U", "detailedState": "Suspended: Rain"}
    susp["dates"][1]["games"][0]["officialDate"] = "2026-06-17"
    assert [x["date"] for x in st.final_games(st.games_from_schedule(susp))] == ["2026-06-17"]


def test_left_excludes_the_postponed_and_the_cancelled_game_and_is_zero_in_a_final_file():
    last = FINAL_DATES[-1]
    ppd_club = PPD["teams"]["away"]["team"]["id"]
    sched_left = sum(1 for d in SCHED["dates"] for g in d["games"]
                     if g["status"]["codedGameState"] == "S" and ppd_club in
                     (g["teams"]["away"]["team"]["id"], g["teams"]["home"]["team"]["id"]))
    assert st.games_left(GAMES, ppd_club, last) == sched_left
    can_club = CAN["teams"]["home"]["team"]["id"]
    assert st.games_left(GAMES, can_club, last) == sum(
        1 for d in SCHED["dates"] for g in d["games"] if g["status"]["codedGameState"] == "S"
        and can_club in (g["teams"]["away"]["team"]["id"], g["teams"]["home"]["team"]["id"]))
    pay = synth_standings(GAMES, last)
    f = st.build_season_file(pay, as_of=last, final=False, generated_at=GEN, games=GAMES)
    for r in f["rows"]:
        assert r["left"] == st.games_left(GAMES, r["team_id"], last)
    assert not job.season_complete(GAMES, last)
    # the same season with its unplayed days dropped is complete: left 0 for every club
    done = st.games_from_schedule({"dates": SCHED["dates"][:len(FINAL_DATES)]})
    assert job.season_complete(done, last)
    ff = st.build_season_file(pay, as_of=last, final=True, generated_at=GEN, games=done)
    assert all(r["left"] == 0 for r in ff["rows"])


def test_streak_last_and_next_game_ride_on_the_race(env):
    clock = FakeClock()
    res, _api = race_and_snapshots(env, clock)
    assert res["exit"] == 0, res
    race = json.loads((sdir(env) / "2026-race.json").read_text(encoding="utf-8"))
    season = json.loads((sdir(env) / "2026.json").read_text(encoding="utf-8"))
    for r in season["rows"]:
        c = r["code"]
        assert race["streak"][c] == r["streak"], c
        assert race["last10"][c] == r["l10_seq"]
        lg = race["last_game"][c]
        assert lg is not None and lg["d"] <= season["as_of"]
        ng = race["next_game"][c]
        assert ng is not None and ng["d"] > season["as_of"], c
    ppd_away = sc.club_code(PPD["teams"]["away"]["team"]["id"])
    assert race["next_game"][ppd_away]["pk"] != PPD["gamePk"]


# --------------------------------------------------------------------------- #
# The backfills: one call a game date, T13 at every date, refusals
# --------------------------------------------------------------------------- #
def test_backfill_writes_a_frozen_snapshot_per_game_date_and_t13_holds_at_every_date(env):
    clock = FakeClock()
    res, api = race_and_snapshots(env, clock)
    assert res["exit"] == 0, res
    assert len(api.standings_urls()) == len(FINAL_DATES) == res["counts"]["snapshots"]
    assert all("date=" in u and "hydrate" not in u for u in api.standings_urls())
    snaps = job.load_snapshots(env["paths"]["standings_out"], 2026)
    assert sorted(snaps) == FINAL_DATES
    race = json.loads((sdir(env) / "2026-race.json").read_text(encoding="utf-8"))
    assert st.race_matches_snapshots(race, snaps) == []
    assert res["t13"]["dates"] == len(FINAL_DATES) and res["t13"]["clubs"] == 30 and res["t13"]["mismatches"] == []
    assert race["dates"][0] == FINAL_DATES[0]
    season = json.loads((sdir(env) / "2026.json").read_text(encoding="utf-8"))
    assert season["as_of"] == FINAL_DATES[-1] and season["opening_day"] == FINAL_DATES[0]
    assert season["final"] is False
    # the raw responses are kept, never served
    raw = env["paths"]["standings_work"] / "2026"
    assert sorted(p.stem for p in raw.glob("*.json")) == FINAL_DATES
    # a rerun resumes: every date is frozen, so no call
    api2 = StandingsAPI(clock)
    res2 = job.backfill_standings(FINAL_DATES[0], FINAL_DATES[-1], paths=env["paths"], adapter=api2, **kw(clock))
    assert res2["exit"] == 0 and api2.standings_urls() == [] and res2["counts"]["skipped_frozen"] == len(FINAL_DATES)


def test_the_request_cap_splits_a_backfill_into_chunks(env):
    clock = FakeClock()
    p = env["paths"]
    assert job.backfill_race(2026, 2026, paths=p, adapter=StandingsAPI(clock), **kw(clock))["exit"] == 0
    api = StandingsAPI(clock)
    r1 = job.backfill_standings(FINAL_DATES[0], FINAL_DATES[-1], paths=p, adapter=api, max_requests=3, **kw(clock))
    assert r1["requests"] == 3 and r1["resume_from"] == FINAL_DATES[3]
    r2 = job.backfill_standings(FINAL_DATES[0], FINAL_DATES[-1], paths=p, adapter=api, **kw(clock))
    assert r2["exit"] == 0 and r2["counts"]["skipped_frozen"] == 3 and len(api.standings_urls()) == len(FINAL_DATES)


def test_the_lag_guard_keeps_the_last_snapshot_and_sets_stale_since(env):
    clock = FakeClock()
    p = env["paths"]
    d_ok, d_lag = FINAL_DATES[-2], FINAL_DATES[-1]
    res, _ = race_and_snapshots(env, clock, b=d_ok, now=datetime.fromisoformat(f"{d_lag}T14:00:00+00:00"))
    assert res["exit"] == 0
    snap_ok = (sdir(env) / "2026" / f"{d_ok}.json").read_bytes()
    season_before = (sdir(env) / "2026.json").read_bytes()
    # a cycle's call for the last date gets MLB's previous day back
    sst = job.load_sstate(p)
    cyc = types.SimpleNamespace(paths=p, state={}, counts={"files_written": 0, "files_refused": 0})
    rows = [_row(1, d_lag, f"{d_lag}T20:05:00Z", "final", final_seen_at=f"{d_lag}T23:00:00Z")]
    now = datetime.fromisoformat(f"{d_lag}T23:30:00+00:00")
    out = job.standings_step(cyc, {"games": rows}, job.Fetcher(job.Limiter(clock=clock, sleep=clock.sleep),
                                                                 StandingsAPI(clock, lag=[d_lag])), now, "live")
    assert out["called"] and out["accepted"] is False and "differs" in out["guard"]
    assert not (sdir(env) / "2026" / f"{d_lag}.json").exists()
    assert (sdir(env) / "2026" / f"{d_ok}.json").read_bytes() == snap_ok
    assert (sdir(env) / "2026.json").read_bytes() == season_before
    sst = job.load_sstate(p)
    assert sst["stale_since"] and sst["retry_date"] == d_lag
    assert not (p["standings_work"] / "2026" / f"{d_lag}.json").exists()       # a lagging response is not kept
    pub = job.publish_indexes(p, lambda: now, "test")
    assert pub["rev_mismatch"] == []
    latest = json.loads((p["out"] / "latest.json").read_text(encoding="utf-8"))
    assert latest["standings"]["stale_since"] == sst["stale_since"]
    assert latest["standings"]["as_of"] == d_ok
    # the retry, answered in step, clears it
    later = now + timedelta(minutes=10)
    sd = job.standings_due(later, {"games": rows}, sst, cycle=None)
    assert sd["due"] and sd["date"] == d_lag
    out2 = job.standings_step(cyc, {"games": rows}, job.Fetcher(job.Limiter(clock=clock, sleep=clock.sleep),
                                                                  StandingsAPI(clock)), later, "due")
    assert out2["accepted"] is True
    sst2 = job.load_sstate(p)
    assert "stale_since" not in sst2 and "retry_date" not in sst2
    assert json.loads((sdir(env) / "2026.json").read_text(encoding="utf-8"))["as_of"] == d_lag


def test_the_validator_refuses_a_snapshot_that_differs_from_the_race_at_its_date(env):
    clock = FakeClock()
    d_bad = FINAL_DATES[3]

    def tamper(d, pay):
        if d != d_bad:
            return pay
        tr = pay["records"][0]["teamRecords"][0]
        tr["runsScored"] += 1
        tr["runDifferential"] += 1
        return pay

    res, _ = race_and_snapshots(env, clock, tamper=tamper)
    assert res["exit"] == 2
    assert [d for d, _r in res["counts"]["refused"]] == [d_bad]
    assert any(rule == "T13" for rule, _m in res["counts"]["refused"][0][1])
    assert not (sdir(env) / "2026" / f"{d_bad}.json").exists()
    # the other dates stand, each equal to the race
    snaps = job.load_snapshots(env["paths"]["standings_out"], 2026)
    assert sorted(snaps) == [d for d in FINAL_DATES if d != d_bad]
    race = json.loads((sdir(env) / "2026-race.json").read_text(encoding="utf-8"))
    assert st.race_matches_snapshots(race, snaps) == []
    # a rerun fetches the refused date again (its saved copy disagreed with the race) and nothing else
    api2 = StandingsAPI(clock)
    res2 = job.backfill_standings(FINAL_DATES[0], FINAL_DATES[-1], paths=env["paths"], adapter=api2, **kw(clock))
    assert res2["exit"] == 0 and len(api2.standings_urls()) == 1 and f"date={d_bad}" in api2.standings_urls()[0]
    assert (sdir(env) / "2026" / f"{d_bad}.json").exists() and not job.load_sstate(env["paths"]).get("refetch")


def test_a_saved_response_refused_by_another_law_is_rebuilt_with_no_call(env, monkeypatch):
    clock = FakeClock()
    real = st.validate_standings
    d_bad = FINAL_DATES[2]

    def strict(kind, obj, **k):
        res = real(kind, obj, **k)
        if kind == st.KIND_SNAPSHOT and obj.get("as_of") == d_bad:
            res = dict(res, ok=False, refused=list(res["refused"]) + [("T7", "a stricter law of an older build")])
        return res

    monkeypatch.setattr(st, "validate_standings", strict)
    res, _ = race_and_snapshots(env, clock)
    assert res["exit"] == 2 and [d for d, _r in res["counts"]["refused"]] == [d_bad]
    monkeypatch.setattr(st, "validate_standings", real)
    api2 = StandingsAPI(clock)
    res2 = job.backfill_standings(FINAL_DATES[0], FINAL_DATES[-1], paths=env["paths"], adapter=api2, **kw(clock))
    assert res2["exit"] == 0 and api2.calls == [] and res2["counts"]["reused"] == 1, res2
    assert (sdir(env) / "2026" / f"{d_bad}.json").exists()


def test_a_snapshot_on_disk_that_differs_from_the_race_refuses_the_race_file(env):
    clock = FakeClock()
    res, _ = race_and_snapshots(env, clock)
    assert res["exit"] == 0
    f = sdir(env) / "2026" / f"{FINAL_DATES[2]}.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    doc["rows"][0]["w"] += 1
    f.write_bytes(st.encode(doc))
    race_before = (sdir(env) / "2026-race.json").read_bytes()
    out = job.build_standings(2026, 2026, paths=env["paths"], now_fn=lambda: LATER + timedelta(hours=1))
    assert out["exit"] == 2
    assert out["seasons"][2026]["t13"]["mismatches"][0][:2] == [FINAL_DATES[2], doc["rows"][0]["code"]]
    assert out["seasons"][2026]["files"]["race"]["ok"] is False
    assert (sdir(env) / "2026-race.json").read_bytes() == race_before


@pytest.mark.parametrize("a,b,now,why", [
    ("2026-03-20", "2026-04-01", LATER, "HISTORY_FLOOR"),
    ("2026-04-02", "2026-04-01", LATER, "backwards"),
    ("2026-04-01", "2026-04-20", LATER, "not a past date"),
    ("2026-04-01", "2026-04-02", datetime(2026, 4, 20, 7, 30, tzinfo=UTC), "nightly window"),
    ("2026-09-01", "2027-04-02", datetime(2027, 5, 1, 14, 0, tzinfo=UTC), "two seasons"),
])
def test_backfill_standings_refusals(env, a, b, now, why):
    clock = FakeClock()
    api = StandingsAPI(clock)
    res = job.backfill_standings(a, b, paths=env["paths"], adapter=api, **kw(clock, now))
    assert res["exit"] == 2 and res["action"] == "backfill_standings_refused" and why in res["reason"], res
    assert api.calls == []


def test_backfill_standings_needs_the_race_schedule_first(env):
    clock = FakeClock()
    api = StandingsAPI(clock)
    res = job.backfill_standings("2026-03-26", "2026-03-28", paths=env["paths"], adapter=api, **kw(clock))
    assert res["exit"] == 2 and "--backfill-race 2026 first" in res["reason"] and api.calls == []


def test_a_backfill_refuses_while_a_game_is_live(env):
    clock = FakeClock()
    now = LATER
    slate = {"fetched_at": job.iso(now - timedelta(minutes=5)),
             "games": [_row(5, "2026-04-20", job.iso(now - timedelta(hours=1)), "live")]}
    job.write_json_plain(env["paths"]["slate"], slate)
    for fn, args in ((job.backfill_standings, ("2026-03-26", "2026-03-27")), (job.backfill_race, (2026, 2026))):
        api = StandingsAPI(clock)
        res = fn(*args, paths=env["paths"], adapter=api, **kw(clock, now))
        assert res["exit"] == 2 and "live" in res["reason"] and api.calls == [], res


@pytest.mark.parametrize("ya,yb,now,why", [
    (2014, 2016, LATER, "before 2015"),
    (2026, 2025, LATER, "backwards"),
    (2026, 2027, LATER, "future season"),
    (2026, 2026, datetime(2026, 4, 20, 10, 59, tzinfo=UTC), "nightly window"),
])
def test_backfill_race_refusals(env, ya, yb, now, why):
    clock = FakeClock()
    api = StandingsAPI(clock)
    res = job.backfill_race(ya, yb, paths=env["paths"], adapter=api, **kw(clock, now))
    assert res["exit"] == 2 and why in res["reason"] and api.calls == [], res


def test_backfill_race_is_one_schedule_call_a_season_and_writes_no_date_file_or_game_card(env):
    clock = FakeClock()
    api = StandingsAPI(clock)
    res = job.backfill_race(2026, 2026, paths=env["paths"], adapter=api, **kw(clock))
    assert res["exit"] == 0 and res["requests"] == 1 and len(api.calls) == 1
    u = api.calls[0]
    assert "season=2026" in u and "gameType=R" in u and "fields=" in u
    for f in ("codedGameState", "gameNumber", "doubleHeader", "officialDate", "score"):
        assert f in u, f
    out = env["paths"]["out"]
    assert not list(out.glob("????-??-??.json")) and not (out / "games").exists()
    assert (sdir(env) / "2026-race.json").exists()
    assert not (sdir(env) / "2026.json").exists()          # no standings response on disk yet
    assert (env["paths"]["standings_work"] / "2026-schedule.json").exists()


def test_build_standings_writes_past_season_files_from_the_tracked_copy_with_zero_calls(env, monkeypatch):
    labs = env["tmp"] / "labs"
    labs.mkdir()
    (labs / "statsapi_standings_2016.json").write_bytes((FIX / "standings_2016.json").read_bytes())
    monkeypatch.setattr(job, "LABS_STANDINGS_DIR", labs)
    job.reset_calls()
    res = job.build_standings(2016, 2016, paths=env["paths"], now_fn=lambda: LATER)
    assert res["exit"] == 0 and res["requests"] == 0 and job.CALLS["n"] == 0, res
    f = json.loads((sdir(env) / "2016.json").read_text(encoding="utf-8"))
    assert f["final"] is True and f["season"] == 2016 and all(r["left"] == 0 for r in f["rows"])
    assert f["copyright"] == json.loads((FIX / "standings_2016.json").read_text(encoding="utf-8"))["copyright"]
    assert not (sdir(env) / "2016-race.json").exists() and not (sdir(env) / "2016").exists()
    idx = json.loads((env["paths"]["out"] / "index.json").read_text(encoding="utf-8"))
    e = next(x for x in idx["standings_seasons"] if x["season"] == 2016)
    assert e["final"] is True and e["by_date"] is False and e["n_dates"] == 0 and e["race_rev"] is None


# --------------------------------------------------------------------------- #
# Write order, revs, compact files, keys
# --------------------------------------------------------------------------- #
def _phist(season, paths, standings_state, generated_at):
    return st.build_phist_file(season, generated_at=generated_at, copyright=COPYRIGHT,
                               post={"as_of": [FINAL_DATES[-1]], "sha256": ["0" * 64],
                                     "clubs": {"NYY": [[0.25, 0.1]]}}, switch_as_of=FINAL_DATES[-1])


def _window(now):
    """The cycle's own schedule window: the synthetic games of D-1 to D+1
    with a team block the card builder reads."""
    d0 = now.date()
    want = {(d0 + timedelta(days=i)).isoformat() for i in (-1, 0, 1)}
    return {"copyright": COPYRIGHT, "dates": [copy.deepcopy(d) for d in SCHED["dates"] if d["date"] in want]}


def test_an_acting_cycle_writes_in_the_plan_order_with_one_standings_call_and_equal_revs(env, monkeypatch):
    clock = FakeClock()
    p = env["paths"]
    monkeypatch.setattr(job, "PHIST_BUILDER", _phist)
    d_last = FINAL_DATES[-1]
    now = datetime.fromisoformat(f"{d_last}T12:00:00+00:00") + timedelta(days=1)
    writes = []
    real = job.write_bytes

    def spy(path, data, **k):
        writes.append(Path(path))
        return real(path, data, **k)

    monkeypatch.setattr(job, "write_bytes", spy)
    api = StandingsAPI(clock, window=_window(now))
    res = job.run(start=now.timestamp(), now_fn=lambda: now, adapter=api, clock=clock, sleep=clock.sleep)
    assert res["exit"] == 0, res
    assert len(api.standings_urls()) == 1 and f"date={d_last}" in api.standings_urls()[0]
    out = p["out"]
    rel = [w.relative_to(out).as_posix() for w in writes if job._inside(w, out)]

    def first(pred):
        return next(i for i, r in enumerate(rel) if pred(r))
    i_date = max(i for i, r in enumerate(rel) if re.match(r"^\d{4}-\d{2}-\d{2}\.json$", r))
    i_snap = first(lambda r: r == f"standings/2026/{d_last}.json")
    i_season, i_race = first(lambda r: r == "standings/2026.json"), first(lambda r: r == "standings/2026-race.json")
    i_phist = first(lambda r: r == "standings/2026-phist.json")
    i_sidx, i_idx, i_latest = first(lambda r: r == "index-2026.json"), first(lambda r: r == "index.json"), \
        first(lambda r: r == "latest.json")
    assert i_date < i_snap < i_season < i_race < i_phist < i_sidx < i_idx < i_latest, rel
    latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    blk = latest["standings"]
    assert set(blk) == {"season", "as_of", "rev", "race_rev", "phist_rev", "stale_since"}
    e = next(x for x in index["standings_seasons"] if x["season"] == 2026)
    assert set(e) == {"season", "rev", "race_rev", "phist_rev", "phist_from", "n_dates", "by_date", "final"}
    for k in ("rev", "race_rev", "phist_rev"):
        assert blk[k] == e[k] and blk[k] is not None, k
    assert blk["rev"] == sc.rev_of((out / "standings" / "2026.json").read_bytes())
    assert blk["race_rev"] == sc.rev_of((out / "standings" / "2026-race.json").read_bytes())
    assert blk["phist_rev"] == sc.rev_of((out / "standings" / "2026-phist.json").read_bytes())
    assert e["phist_from"] == FINAL_DATES[-1] and e["n_dates"] == 1 and e["by_date"] is True
    assert blk["as_of"] == d_last and blk["stale_since"] is None
    assert job.verify_revs(job.Writer(out)) == []


def test_every_standings_file_is_compact_and_passes_its_validator(env, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(job, "PHIST_BUILDER", _phist)
    res, _ = race_and_snapshots(env, clock)
    assert res["exit"] == 0
    files = sorted(sdir(env).rglob("*.json"))
    assert len(files) == len(FINAL_DATES) + 3
    for f in files:
        data = f.read_bytes()
        assert st.encode(json.loads(data.decode("utf-8"))) == data, f.name
        assert b"\n" not in data
        rel = f.relative_to(env["paths"]["standings_out"]).as_posix()
        kind = sc.kind_of_name(rel)
        assert kind in st.STANDINGS_KINDS, rel
        assert sc.find_forbidden_keys(json.loads(data)) == [], rel


def test_the_contract_keys_with_nothing_on_disk(env):
    p = env["paths"]
    pub = job.build_standings(2026, 2026, paths=p, now_fn=lambda: LATER)
    assert pub["exit"] == 2                                     # nothing on disk to build 2026 from
    latest = json.loads((p["out"] / "latest.json").read_text(encoding="utf-8"))
    index = json.loads((p["out"] / "index.json").read_text(encoding="utf-8"))
    assert latest["standings"] is None and index["standings_seasons"] == []


# --------------------------------------------------------------------------- #
# Where the standings land: the preview while STANDINGS_LIVE is off
# --------------------------------------------------------------------------- #
def test_the_flags_default_off_and_the_standings_out_is_the_preview(env):
    assert st.STANDINGS_LIVE is False and st.STANDINGS_CHARTS is False
    assert job.standings_out_dir() == env["store"] / "preview"
    assert env["paths"]["standings_out"] == env["store"] / "preview" == env["paths"]["out"]
    assert job.standings_served(env["paths"])


def test_scores_live_with_standings_dark_keeps_every_standings_file_in_the_preview(env, monkeypatch):
    monkeypatch.setattr(sc, "SCORES_LIVE", True)
    p = job.resolve_paths()
    assert p["out"] == env["tmp"] / "out_env" and p["standings_out"] == env["store"] / "preview"
    assert not job.standings_served(p)
    clock = FakeClock()
    assert job.backfill_race(2026, 2026, paths=p, adapter=StandingsAPI(clock), **kw(clock))["exit"] == 0
    res = job.backfill_standings(FINAL_DATES[0], FINAL_DATES[2], paths=p, adapter=StandingsAPI(clock), **kw(clock))
    assert res["exit"] == 0, res
    assert (env["store"] / "preview" / "standings" / "2026.json").exists()
    served = env["tmp"] / "out_env"
    assert not (served / "standings").exists()
    # the served scores files are not written by a standings hand run and name no standings file
    assert not (served / "latest.json").exists() and not (served / "index.json").exists()
    # a scores cycle's index and latest carry no standings key while the standings are dark
    cyc = job.Cycle(p, {}, {"registry": [], "accuracy": {}, "constants": {}}, lambda: LATER, action="t")
    assert "standings_seasons" not in cyc.index()
    lat = job.build_latest(cyc, action="t", job_state="idle", next_by_iso=job.iso(LATER), index_rev=None, rows=[],
                           now=LATER)
    assert "standings" not in lat
    # with both flags on, the standings sit beside the scores files
    monkeypatch.setattr(st, "STANDINGS_LIVE", True)
    p2 = job.resolve_paths()
    assert p2["standings_out"] == p2["out"] == served and job.standings_served(p2)


def test_every_write_lands_under_the_store_or_out_and_no_fenced_store_is_opened(env, monkeypatch):
    opened, writes = [], []
    real_open, real_io_open, real_os_open, real_replace = builtins.open, io.open, os.open, os.replace

    def spy_open(file, mode="r", *a, **k):
        opened.append(str(file))
        if any(c in str(mode) for c in "wax+"):
            writes.append(Path(file))
        return real_open(file, mode, *a, **k)

    def spy_io_open(file, mode="r", *a, **k):
        opened.append(str(file))
        if any(c in str(mode) for c in "wax+"):
            writes.append(Path(file))
        return real_io_open(file, mode, *a, **k)

    def spy_os_open(path, flags, *a, **k):
        opened.append(str(path))
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            writes.append(Path(path))
        return real_os_open(path, flags, *a, **k)

    def spy_replace(src, dst, *a, **k):
        writes.append(Path(dst))
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(io, "open", spy_io_open)
    monkeypatch.setattr(os, "open", spy_os_open)
    monkeypatch.setattr(os, "replace", spy_replace)
    clock = FakeClock()
    res, _ = race_and_snapshots(env, clock)
    assert res["exit"] == 0
    assert job.build_standings(2026, 2026, paths=env["paths"], now_fn=lambda: LATER)["exit"] == 0
    assert writes
    store = env["paths"]["store"]
    for w in writes:
        assert job._inside(w, store), w
        assert not job._inside(w, ROOT / "data") and not job._inside(w, ROOT / ".cache"), w
    for f in opened:
        norm = f.replace("\\", "/")
        for fenced in (".cache/betting", ".cache/odds", ".cache/lineup_captures", ".cache/weather_forecasts"):
            assert fenced not in norm, f


def test_neither_standings_module_names_a_fenced_store():
    for path in (ROOT / "standings_core.py", ROOT / "tools" / "scores_job.py"):
        text = path.read_text(encoding="utf-8")
        code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
        for s in ("completed_games", "lineup_captures", "weather_forecasts"):
            assert s not in code, (path.name, s)
        assert not re.search(r"\.cache[/\\]+(odds|betting)\b", code), path.name
        assert not re.search(r"[\"']\.cache[\"']\s*/\s*[\"'](odds|betting)[\"']", code), path.name


def test_why_prints_the_standings_decision(env, capsys):
    p = env["paths"]
    rows = [_row(1, "2026-06-10", "2026-06-10T20:05:00Z", "final", final_seen_at="2026-06-10T21:00:00Z")]
    job.write_json_plain(p["slate"], {"fetched_at": "2026-06-10T21:05:00Z", "games": rows})
    job.save_sstate(p, {"retry_date": "2026-06-09", "stale_since": "2026-06-10T03:00:00Z"})
    assert job.main(["--why"]) == 0
    text = capsys.readouterr().out
    assert re.search(r"^standings: (call|no call)", text, re.M), text
    assert "stale_since 2026-06-10T03:00:00Z" in text and "owed 2026-06-09" in text
