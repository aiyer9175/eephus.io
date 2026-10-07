# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/scores_job.py (SCORES_2_JOB_AND_DEPLOY): the MLB Scores job.

Hermetic: a fake StatsAPI adapter, a fake monotonic clock, fixed UTC instants
and temp directories. No test touches the network, the repo's data/ or a real
.cache/scores/: conftest.py points EEPHUS_SCORES_STORE and EEPHUS_SCORES_OUT at
a session temp directory before this module imports the job, every test below
re-points them at its own tmp_path, the served reads go to a temp webroot
(EEPHUS_WEBROOT), and the epoch sentinel and the house caches are monkeypatched
to temp paths.
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import scores_core as sc  # noqa: E402
import scores_job as job  # noqa: E402

FIX = ROOT / "test_fixtures" / "scores"
UTC = timezone.utc


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# The kit: a fake StatsAPI, a fake clock, an isolated environment
# --------------------------------------------------------------------------- #
class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += max(0.0, float(s))


class FakeAPI:
    """Routes a StatsAPI URL to a fixture payload. `cost` is the fake time a
    request takes (it advances the fake clock, never the real one); a request
    whose cost passes its deadline raises TimeoutError, as urllib does."""

    def __init__(self, clock: FakeClock, schedule, *, wp=None, box=None, feed=None, people=None, series=None,
                 cost=0.1, content=None):
        self.clock, self.schedule, self.series = clock, schedule, series
        self.wp, self.box, self.feed = dict(wp or {}), dict(box or {}), dict(feed or {})
        self.content = dict(content or {})          # SCORES_4a: /game/{pk}/content
        self.people = people if people is not None else {"people": []}
        self.cost = cost
        self.calls: list[tuple[str, float]] = []
        self.status: dict = {}          # (kind, pk) -> (status, headers)

    def __call__(self, url, timeout):
        self.calls.append((url, timeout))
        cost = self.cost(url) if callable(self.cost) else self.cost
        if cost > timeout:
            self.clock.t += timeout
            raise TimeoutError(f"fake timeout after {timeout}")
        self.clock.t += cost
        m = re.search(r"/game/(\d+)/(winProbability|boxscore|feed/live|content)", url)
        if job.BRACKET_PATH in url:
            st = self.status.get(("series", None))
            if st:
                return st[0], st[1], b""
            if self.series is None:
                return 404, {}, b""
            return 200, {}, json.dumps(self.series).encode("utf-8")
        if "/api/v1/schedule" in url:
            st = self.status.get(("schedule", None))
            if st:
                return st[0], st[1], b""
            body = self.schedule(url) if callable(self.schedule) else self.schedule
            return 200, {}, json.dumps(body).encode("utf-8")
        if "/api/v1/people" in url:
            return 200, {}, json.dumps(self.people).encode("utf-8")
        if m:
            pk, kind = int(m.group(1)), {"winProbability": "wp", "boxscore": "box", "feed/live": "feed",
                                         "content": "content"}[m.group(2)]
            st = self.status.get((kind, pk)) or self.status.get((kind, None))
            if st:
                return st[0], st[1], b""
            src = getattr(self, kind)
            if pk in src:
                return 200, {}, json.dumps(src[pk]).encode("utf-8")
            if "*" in src:
                return 200, {}, json.dumps(src["*"]).encode("utf-8")
        return 404, {}, b""

    def urls(self, kind=None):
        out = [u for u, _t in self.calls]
        if kind == "wp":
            return [u for u in out if "/winProbability" in u]
        if kind == "box":
            return [u for u in out if "/boxscore" in u]
        if kind == "feed":
            return [u for u in out if "/feed/live" in u]
        if kind == "series":
            return [u for u in out if job.BRACKET_PATH in u]
        if kind == "schedule":
            return [u for u in out if "/schedule" in u and job.BRACKET_PATH not in u]
        if kind == "content":
            return [u for u in out if u.endswith("/content")]
        return out


def _game(pk, coded, sched=None):
    sched = sched or load("schedule_states.json")
    for d in sched["dates"]:
        for g in d["games"]:
            if g["gamePk"] == pk and g["status"]["codedGameState"] == coded:
                return copy.deepcopy(g)
    raise KeyError((pk, coded))


COPYRIGHT = load("box_849845.json")["copyright"]


def schedule_of(*games, copyright=COPYRIGHT):
    dates: dict = {}
    for g in games:
        dates.setdefault(g["officialDate"], []).append(g)
    return {"copyright": copyright, "dates": [{"date": d, "games": gs} for d, gs in sorted(dates.items())]}


def base_games():
    """A slate across 2026-09-29 and 2026-09-30: a final (849845, every fixture),
    a live game in the 1st (849846), a scheduled game (849848)."""
    return [_game(849845, "F"), _game(849846, "I"), _game(849848, "S")]


def base_payloads():
    return {"wp": {849845: load("wp_849845_ext.json"), 849846: load("wp_849846_live.json")},
            "box": {849845: load("box_849845.json"), 849846: load("box_849845.json")},
            "feed": {849845: load("feed_849845.json")}}


#: 21:40Z on 2026-09-30: 849846 live, the week cycle done for the day.
NOW = datetime(2026, 9, 30, 21, 40, tzinfo=UTC)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """An isolated job: store, out, a temp webroot holding the three served
    reads, the epoch sentinel and the house caches under tmp_path."""
    store, out, web = tmp_path / "store", tmp_path / "out_env", tmp_path / "web"
    monkeypatch.setenv("EEPHUS_SCORES_STORE", str(store))
    monkeypatch.setenv("EEPHUS_SCORES_OUT", str(out))
    monkeypatch.setenv("EEPHUS_WEBROOT", str(web))
    monkeypatch.delenv("EEPHUS_SCORES_EMBED", raising=False)
    (web / "data").mkdir(parents=True)
    lc = load("league_constants_2026.json")
    (web / "data" / "league_constants.json").write_text(json.dumps({"seasons": {"2026": lc, "2025": lc}}),
                                                         encoding="utf-8")
    we = {"generated_at": "2026-09-11T01:06:34+00:00", "seasons": ["2018", "2026"], "n_plays_fit": 1448965,
          "calibration": {"feed_brier": 0.157516, "brier_base_rate_only": 0.249754},
          # a decoy: index.json's pregame_values must never come from this file
          "pregame_values": {"999": 7}}
    (web / "data" / "win_expectancy.json").write_text(json.dumps(we), encoding="utf-8")
    reg = {"models": [{"model_id": "scores_mlb_wp", "verdict": "provisional"},
                      {"model_id": "scores_stars_rule", "verdict": "provisional"}]}
    (web / "data" / "model_registry.json").write_text(json.dumps(reg), encoding="utf-8")
    monkeypatch.setattr(job, "EPOCH_SNAPSHOT", tmp_path / "no_pre_epoch_snapshot")
    monkeypatch.setattr(job, "EPOCH_GATE_DOC", tmp_path / "no_gate.md")
    monkeypatch.setattr(job, "HOUSE_WP_CACHE", tmp_path / "house" / "win_prob")
    monkeypatch.setattr(job, "HOUSE_FEED_CACHE", tmp_path / "house" / "game_feeds")
    monkeypatch.setattr(job, "DATA_DIR", tmp_path / "app" / "data")
    monkeypatch.setattr(job, "GAME_FILE_HOOK", None)
    monkeypatch.setattr(sc, "SCORES_LIVE", False)
    job.reset_calls()
    paths = job.resolve_paths()
    return {"tmp": tmp_path, "store": store, "out": paths["out"], "web": web, "paths": paths}


def run_once(env, api, clock, now=NOW, *, start=None, **kw):
    return job.run(start=now.timestamp() if start is None else start, now_fn=lambda: now, adapter=api,
                   clock=clock, sleep=clock.sleep, **kw)


def seed_state(env, **state):
    env["paths"]["store"].mkdir(parents=True, exist_ok=True)
    job.save_state(env["paths"], state)


def files_under(d: Path) -> set[str]:
    return {p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()} if d.exists() else set()


# --------------------------------------------------------------------------- #
# Isolation
# --------------------------------------------------------------------------- #
def test_every_resolved_path_sits_inside_the_session_temp_directory_under_pytest():
    root = os.environ.get("EEPHUS_SCORES_TEST_ROOT")
    assert root, "conftest.py must set the scores test root before the job is imported"
    assert os.environ["EEPHUS_SCORES_STORE"].startswith(root)
    assert os.environ["EEPHUS_SCORES_OUT"].startswith(root)
    for key, p in job.resolve_paths().items():
        assert job._inside(p, Path(root)), (key, p)
        assert not job._inside(p, ROOT / "data"), (key, p)
        assert not job._inside(p, ROOT / ".cache"), (key, p)


def test_module_flag_off_means_preview_whatever_the_environment_says(env, monkeypatch):
    assert sc.SCORES_LIVE is False
    assert env["out"] == env["store"] / "preview"
    monkeypatch.setattr(sc, "SCORES_LIVE", True)
    assert job.out_dir() == env["tmp"] / "out_env"
    monkeypatch.delenv("EEPHUS_SCORES_OUT")
    assert job.out_dir() == env["store"] / "out"


# --------------------------------------------------------------------------- #
# decide(): every cycle type on fixture slates
# --------------------------------------------------------------------------- #
def _row(pk, date, start, state, **kw):
    r = {"pk": pk, "date": date, "type": "R", "season": 2026, "start": start, "tbd": False, "state": state,
         "hash": "h", "final_seen_at": None, "probables": []}
    r.update(kw)
    return r


def _slate(*rows, fetched="2026-09-30T21:00:00Z"):
    return {"fetched_at": fetched, "span": ["2026-09-29", "2026-10-01"], "games": list(rows)}


def test_decide_live_on_an_in_progress_game():
    t = int(NOW.timestamp())
    d = job.decide(NOW, _slate(_row(1, "2026-09-30", "2026-09-30T21:00:00Z", "live")),
                   {"week_date": "2026-09-30", "last_live_tick": job.tick_of(t) - 120, "last_cycle_tick": job.tick_of(t) - 120})
    assert d["acts"] and d["cycle"] == "live"


def test_decide_west_coast_0210z_game_carries_the_previous_official_date_and_opens_the_live_window():
    now = datetime(2026, 9, 30, 1, 55, tzinfo=UTC)
    slate = _slate(_row(2, "2026-09-29", "2026-09-30T02:10:00Z", "scheduled"))
    d = job.decide(now, slate, {"week_date": "2026-09-29", "last_cycle_tick": job.tick_of(now.timestamp()) - 240})
    assert d["cycle"] == "live" and d["live_games"] == 1
    early = datetime(2026, 9, 30, 1, 40, tzinfo=UTC)
    d2 = job.decide(early, slate, {"week_date": "2026-09-29", "last_cycle_tick": job.tick_of(early.timestamp()) - 240})
    assert d2["live_games"] == 0 and not d2["acts"]


def test_decide_doubleheader_postponement_and_tbd_time():
    rows = [_row(3, "2026-09-30", "2026-09-30T17:05:00Z", "final", final_seen_at="2026-09-30T20:00:00Z"),
            _row(4, "2026-09-30", "2026-09-30T21:35:00Z", "pregame"),           # game 2, 5 minutes out
            _row(5, "2026-09-30", "2026-09-30T21:45:00Z", "postponed"),
            _row(6, "2026-09-30", "2026-09-30T21:45:00Z", "scheduled", tbd=True)]
    live = job.live_games(rows, NOW)
    assert [r["pk"] for r in live] == [4]
    d = job.decide(NOW, _slate(*rows), {"week_date": "2026-09-30"})
    assert d["cycle"] == "live"


def test_decide_idle_then_quiet_then_idle_again():
    rows = [_row(7, "2026-10-01", "2026-10-01T23:00:00Z", "scheduled")]
    tick = job.tick_of(NOW.timestamp())
    st = {"week_date": "2026-09-30", "last_cycle_tick": tick - 600}
    d = job.decide(NOW, _slate(*rows), st, tick=tick)
    assert not d["acts"] and d["action"] == "none"
    st["last_cycle_tick"] = tick - job.IDLE_INTERVAL_S
    d = job.decide(NOW, _slate(*rows), st, tick=tick)
    assert d["acts"] and d["cycle"] == "idle"


def test_decide_week_on_the_first_tick_at_or_after_10_utc_and_on_the_utc_date_roll():
    rows = [_row(7, "2026-10-01", "2026-10-01T23:00:00Z", "scheduled")]
    before = datetime(2026, 10, 1, 9, 58, tzinfo=UTC)
    st = {"week_date": "2026-09-30", "last_cycle_tick": job.tick_of(before.timestamp()) - 60}
    assert job.decide(before, _slate(*rows), st)["cycle"] is None
    after = datetime(2026, 10, 1, 10, 0, 30, tzinfo=UTC)
    d = job.decide(after, _slate(*rows), st)
    assert d["cycle"] == "week"
    st["week_date"] = "2026-10-01"
    assert job.decide(after, _slate(*rows), st)["cycle"] != "week"


def test_decide_offseason_every_six_hours():
    now = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
    tick = job.tick_of(now.timestamp())
    st = {"week_date": "2026-11-20", "last_cycle_tick": tick - 3 * 3600}
    d = job.decide(now, _slate(fetched="2026-11-20T10:00:00Z"), st, tick=tick)
    assert not d["acts"] and "offseason" in d["reason"]
    st["last_cycle_tick"] = tick - job.OFFSEASON_INTERVAL_S
    assert job.decide(now, _slate(fetched="2026-11-20T10:00:00Z"), st, tick=tick)["cycle"] == "offseason"


def test_decide_due_work_backoff_and_no_slate():
    tick = job.tick_of(NOW.timestamp())
    rows = [_row(7, "2026-10-01", "2026-10-01T23:00:00Z", "scheduled")]
    st = {"week_date": "2026-09-30", "last_cycle_tick": tick - 120, "pending": {"finalize": [849845]}}
    d = job.decide(NOW, _slate(*rows), st, tick=tick)
    assert d["cycle"] == "due" and d["due"] == ["finalize:1"]
    # a game in its own backoff is not due work
    st["games"] = {"849845": {"backoff_until": NOW.timestamp() + 600}}
    assert job.decide(NOW, _slate(*rows), st, tick=tick)["cycle"] is None
    # the embed switch changing is due work
    st2 = {"week_date": "2026-09-30", "last_cycle_tick": tick - 120, "embed": True}
    assert job.decide(NOW, _slate(*rows), st2, tick=tick, embed=False)["due"] == ["embed_switch"]
    st3 = {"backoff_until": NOW.timestamp() + 100, "backoff_n": 1}
    d3 = job.decide(NOW, _slate(*rows), st3)
    assert d3["action"] == "backoff" and not d3["acts"]
    d4 = job.decide(NOW, None, {})
    assert d4["acts"] and d4["cycle"] == "week" and "no_local_slate" in d4["reason"]


def test_ticks_with_jitter_100_s_apart_still_run_consecutive_live_cycles():
    t0 = 1_790_000_040        # a tick boundary (a multiple of 120)
    assert t0 % 120 == 0
    # cron fires at t0 and t0+120; the jitter lands the runs at t0+20 and t0+120
    assert job.tick_of(t0 + 1) == t0 and job.tick_of(t0 + 121) == t0 + 120
    now2 = datetime.fromtimestamp(t0 + 120, UTC)
    rows = [_row(1, now2.date().isoformat(), job.iso(now2 - timedelta(hours=1)), "live")]
    st = {"week_date": now2.date().isoformat(), "last_live_tick": t0, "last_cycle_tick": t0}
    d = job.decide(now2, _slate(*rows), st, tick=job.tick_of(t0 + 121))
    assert d["cycle"] == "live"
    # under SC-TERMS (c) the 280 s gate on 120 s ticks runs every 360 s
    assert job.ceil_tick(t0 + 280) - t0 == 360 and job.ceil_tick(t0 + 90) - t0 == 120


def test_next_by_for_every_cycle_type():
    tick = job.tick_of(NOW.timestamp())
    live = [_row(1, "2026-09-30", "2026-09-30T21:00:00Z", "live")]
    assert job.next_by(tick, live, NOW, {"week_date": "2026-09-30"}) == job.iso(tick + 120 + 360)
    idle = [_row(2, "2026-10-01", "2026-10-01T23:00:00Z", "scheduled")]
    assert job.next_by(tick, idle, NOW, {"week_date": "2026-09-30"}) == job.iso(tick + 1800 + 360)
    soon = [_row(3, "2026-09-30", "2026-09-30T22:30:00Z", "scheduled")]   # live window opens 22:10
    want = job.ceil_tick(datetime(2026, 9, 30, 22, 10, tzinfo=UTC).timestamp()) + 360
    assert job.next_by(tick, soon, NOW, {"week_date": "2026-09-30"}) == job.iso(want)
    off_now = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
    otick = job.tick_of(off_now.timestamp())
    assert job.next_by(otick, [], off_now, {"week_date": "2026-11-20"}) == job.iso(otick + 21600 + 360)
    early = datetime(2026, 11, 20, 2, 0, tzinfo=UTC)
    etick = job.tick_of(early.timestamp())
    assert job.next_by(etick, [], early, {"week_date": "2026-11-19"}) == job.iso(etick + 21600 + 360)
    seven = datetime(2026, 11, 20, 7, 0, tzinfo=UTC)       # the 10:00 UTC week tick comes first
    stick = job.tick_of(seven.timestamp())
    assert job.next_by(stick, [], seven, {"week_date": "2026-11-19"}) == job.iso(
        job.ceil_tick(datetime(2026, 11, 20, 10, 0, tzinfo=UTC).timestamp()) + 360)


# --------------------------------------------------------------------------- #
# One run with a fake fetch
# --------------------------------------------------------------------------- #
def test_one_run_writes_the_five_file_kinds_in_order_with_revs_equal_to_the_bytes(env, monkeypatch):
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    order = []
    real = job.write_bytes

    def spy(path, data, **kw):
        order.append(Path(path))
        return real(path, data, **kw)

    monkeypatch.setattr(job, "write_bytes", spy)
    seed_state(env, week_date="2026-09-30")
    res = run_once(env, api, clock)
    assert res["exit"] == 0, res
    out = env["out"]
    names = files_under(out)
    assert {"latest.json", "index.json", "index-2026.json", "2026-09-29.json", "2026-09-30.json",
            "games/849845.json", "games/849846.json"} <= names
    # every request inside the budget; one winProbability call per live or final game
    assert res["requests"] <= job.MAX_REQUESTS_PER_RUN
    assert sorted(api.urls("wp")) == sorted({u for u in api.urls("wp")})
    assert len(api.urls("wp")) == 2
    assert all(u.startswith("https://statsapi.mlb.com/") for u in api.urls())
    # write order: games, then date, then season index, index, latest
    outs = [p for p in order if job._inside(p, out)]
    kinds = [sc.kind_of_name(p.relative_to(out).as_posix()) for p in outs]
    rank = {"game": 0, "date": 1, "season_index": 2, "index": 3, "latest": 4}
    assert kinds == sorted(kinds, key=lambda k: rank[k]), kinds
    assert kinds[-1] == "latest"
    # rule 11: every rev in latest.json and index.json equals the bytes on disk
    w = job.Writer(out)
    assert job.verify_revs(w) == []
    latest = w.read("latest.json")
    assert latest["window"]["2026-09-30"]["rev"] == sc.rev_of((out / "2026-09-30.json").read_bytes())
    for name in names:
        if sc.kind_of_name(name):
            res_v = sc.validate_payload(sc.kind_of_name(name), json.loads((out / name).read_text(encoding="utf-8")),
                                        name=name)
            assert res_v["ok"], (name, res_v["refused"])
    # heartbeat and one run-log line
    # the first run has no slate yet, so it acts to establish one (idle; the week cycle is done)
    assert res["action"] == "idle" and "no_local_slate" in res["reason"] and res["job_state"] == "ok"
    hb = json.loads(env["paths"]["heartbeat"].read_text(encoding="utf-8"))
    assert hb["action"] == "idle" and hb["exit"] == 0 and hb["scores_live"] is False
    lines = (env["store"] / "runlog-2026-09-30.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["action"] == "idle"
    if os.name != "nt":
        for name in names:
            assert (out / name).stat().st_mode & 0o777 == 0o644, name
    # dh {kind, n} and start ride on every card (the standings race orders doubleheaders by them)
    for d in ("2026-09-29.json", "2026-09-30.json"):
        for card in json.loads((out / d).read_text(encoding="utf-8"))["games"]:
            assert set(card["dh"]) == {"kind", "n"} and card["start"]
    # nothing under OUT/standings/, reserved for STANDINGS_2
    assert not (out / "standings").exists()


def test_a_second_cycle_refetches_only_the_game_whose_state_changed(env):
    clock = FakeClock()
    games = base_games()
    api = FakeAPI(clock, schedule_of(*games), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    assert run_once(env, api, clock)["exit"] == 0
    n_wp = len(api.urls("wp"))
    later = NOW + timedelta(seconds=120)
    assert run_once(env, api, clock, now=later)["action"] == "live"
    assert len(api.urls("wp")) == n_wp                      # nothing changed: no winProbability call
    g2 = copy.deepcopy(games)
    g2[1]["linescore"]["outs"] = 2
    api.schedule = schedule_of(*g2)
    assert run_once(env, api, clock, now=later + timedelta(seconds=120))["action"] == "live"
    new = api.urls("wp")[n_wp:]
    assert new == [u for u in new if "/849846/" in u] and len(new) == 1


def test_the_index_carries_registry_accuracy_rules_and_the_copyright_line(env):
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    run_once(env, api, clock)
    idx = json.loads((env["out"] / "index.json").read_text(encoding="utf-8"))
    assert idx["copyright"] == COPYRIGHT and sc.MLB_TERMS_URL in idx["copyright"]
    assert idx["registry"] == [{"model_id": "scores_mlb_wp", "verdict": "provisional", "sentence": "MLB, provisional"},
                               {"model_id": "scores_stars_rule", "verdict": "provisional",
                                "sentence": "Eephus rule, provisional"}]
    acc = idx["accuracy"]["mlb_wp"]
    assert acc["feed_brier"] == 0.157516 and acc["base_rate_brier"] == 0.249754 and acc["n_plays"] == 1448965
    assert idx["rules"]["stars"]["rule"] == "stars_v1" and idx["rules"]["plays"]["rule"] == "bp_v1"
    assert len(sc.dumps(idx).encode()) < 12 * 1024        # room for STANDINGS_2's standings_seasons
    latest = json.loads((env["out"] / "latest.json").read_text(encoding="utf-8"))
    assert len(sc.dumps(latest).encode()) < 12 * 1024     # room for STANDINGS_2's standings block


def test_pregame_values_count_the_season_game_files_and_never_read_win_expectancy(env, monkeypatch):
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    reads = []
    real = job.read_served

    def spy(name):
        doc = real(name)
        reads.append((name, copy.deepcopy(doc)))
        return doc

    monkeypatch.setattr(job, "read_served", spy)
    run_once(env, api, clock)
    out = env["out"]
    counts: dict = {}
    for p in (out / "games").glob("*.json"):
        v = json.loads(p.read_text(encoding="utf-8"))["wp"]["pregame_home"]
        if v is not None:
            counts[str(v)] = counts.get(str(v), 0) + 1
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert idx["accuracy"]["mlb_wp"]["pregame_values"] == counts == {"500": 2}
    assert "999" not in idx["accuracy"]["mlb_wp"]["pregame_values"]          # the decoy never feeds it
    assert [n for n, _d in reads].count("win_expectancy.json") == 1
    # an empty season prints no 50 percent sentence: the map is empty, not invented
    cyc = job.Cycle(env["paths"], {"catalog": {}}, job.served_blocks({}, current_season=2026), lambda: NOW, action="x")
    assert cyc.pregame_values() == {}


def test_served_reads_come_from_the_webroot_and_carry_forward_when_a_read_fails(env):
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    run_once(env, api, clock)
    (env["web"] / "data" / "win_expectancy.json").write_text("", encoding="utf-8")       # written non-atomically
    (env["web"] / "data" / "model_registry.json").write_text("{", encoding="utf-8")
    run_once(env, api, clock, now=NOW + timedelta(seconds=240))
    idx = json.loads((env["out"] / "index.json").read_text(encoding="utf-8"))
    assert idx["accuracy"]["mlb_wp"]["feed_brier"] == 0.157516
    assert idx["registry"][0]["model_id"] == "scores_mlb_wp"
    st = job.load_state(env["paths"])
    assert st["served"]["accuracy"]["feed_brier"] == 0.157516 and st["served"]["constants"]["2026"]["rpw"]


# --------------------------------------------------------------------------- #
# The limiter: deadlines, the 90 s bound, backoff
# --------------------------------------------------------------------------- #
def test_a_slow_adapter_proves_the_per_request_deadline_and_the_90_s_bound(env):
    clock = FakeClock()
    many = []
    g = _game(849846, "I")
    for i in range(30):
        x = copy.deepcopy(g)
        x["gamePk"] = 700000 + i
        many.append(x)
    api = FakeAPI(clock, schedule_of(*many), wp={"*": load("wp_849846_live.json")},
                  box={"*": load("box_849845.json")}, cost=14.0)
    seed_state(env, week_date="2026-09-30")
    t_start = clock.t
    res = run_once(env, api, clock)
    starts = []
    t = t_start
    for (_u, timeout) in api.calls:
        assert timeout <= job.REQUEST_TIMEOUT_S
        starts.append(timeout)
    assert clock.t - t_start <= job.RUN_DEADLINE_S
    # no request may start after 75 s: 14 s each plus 0.5 s spacing allows 6 starts
    assert len(api.calls) <= int(job.LAST_START_S // 14) + 1
    assert res["counts"]["rolled_over"] > 0 and job.load_state(env["paths"])["pending"]["rollover"]
    # a request that would take 30 s is cut at its deadline and counts as a per-game failure
    clock2 = FakeClock()
    api2 = FakeAPI(clock2, schedule_of(_game(849846, "I")), cost=lambda u: 30.0 if "/game/" in u else 0.1)
    seed_state(env, week_date="2026-09-30")
    res2 = run_once(env, api2, clock2)
    assert all(t <= 15 for _u, t in api2.calls)
    assert res2["counts"]["game_fetch_failed"] >= 1 and res2["exit"] == 0


def test_the_limiter_hands_out_deadlines_of_the_remaining_budget():
    clock = FakeClock()
    lim = job.Limiter(clock=clock, sleep=clock.sleep)
    assert lim.acquire() == 15
    lim.release()
    clock.t += 70
    assert lim.acquire() <= 90 - 70
    lim.release()
    clock.t += 6
    with pytest.raises(job.BudgetExhausted):
        lim.acquire()
    lim2 = job.Limiter(clock=clock, sleep=clock.sleep, max_requests=2)
    lim2.acquire(); lim2.release(); lim2.acquire(); lim2.release()
    assert clock.sleeps[-1] == pytest.approx(0.5)
    with pytest.raises(job.BudgetExhausted):
        lim2.acquire()


def test_a_429_with_retry_after_sets_backoff_until_and_ends_the_invocation(env):
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    api.status[("wp", None)] = (429, {"retry-after": "600"})
    seed_state(env, week_date="2026-09-30")
    res = run_once(env, api, clock)
    st = job.load_state(env["paths"])
    assert st["backoff_until"] == pytest.approx(NOW.timestamp() + 600)
    assert len(api.urls("wp")) == 1 and not api.urls("box") and not api.urls("feed")
    assert res["exit"] == 0 and res["job_state"] == "backoff"
    later = NOW + timedelta(seconds=120)
    nxt = run_once(env, api, clock, now=later)
    assert nxt["action"] == "backoff" and nxt["exit"] == 0
    # the schedule itself failing is job-level: degraded latest.json, exit 2
    seed_state(env, week_date="2026-09-30")
    api.status[("schedule", None)] = (503, {"retry-after": "5"})
    bad = run_once(env, api, clock)
    assert bad["action"] == "fetch_failed" and bad["exit"] == 2
    latest = json.loads((env["out"] / "latest.json").read_text(encoding="utf-8"))
    assert latest["job"]["state"] == "backoff" and latest["job"]["action"] == "fetch_failed"
    assert job.load_state(env["paths"])["backoff_until"] >= NOW.timestamp() + 120


def test_retry_after_parses_seconds_and_dates():
    assert job.parse_retry_after("120") == 120
    assert job.parse_retry_after("Wed, 30 Sep 2026 21:50:00 GMT", now=NOW.timestamp()) == pytest.approx(600)
    assert job.parse_retry_after(None) is None and job.parse_retry_after("soon") is None


def test_a_per_game_500_stamps_that_game_and_leaves_the_others_and_job_state_alone(env):
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    api.status[("wp", 849846)] = (500, {})
    seed_state(env, week_date="2026-09-30")
    res = run_once(env, api, clock)
    assert res["exit"] == 0 and res["job_state"] == "ok" and res["counts"]["game_fetch_failed"] == 1
    st = job.load_state(env["paths"])
    g = st["games"]["849846"]
    assert g["stale_since"] == job.iso(NOW) and g["backoff_until"] == pytest.approx(NOW.timestamp() + 120)
    assert "backoff_until" not in st or not st.get("backoff_until")
    assert (env["out"] / "games" / "849845.json").exists()
    cards = {c["pk"]: c for c in json.loads((env["out"] / "2026-09-30.json").read_text(encoding="utf-8"))["games"]}
    assert cards[849846]["stale_since"] == job.iso(NOW)
    latest = json.loads((env["out"] / "latest.json").read_text(encoding="utf-8"))
    assert latest["job"]["state"] == "ok" and latest["window"]["2026-09-30"]["stale_since"] == job.iso(NOW)


def test_a_per_file_refusal_keeps_the_last_good_copy_and_job_state_ok(env, monkeypatch):
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    run_once(env, api, clock)
    good = (env["out"] / "games" / "849846.json").read_bytes()
    g2 = base_games()
    g2[1]["linescore"]["outs"] = 1
    api.schedule = schedule_of(*g2)

    def poison(gf):
        if gf["pk"] == 849846:
            gf = dict(gf, edge=0.1)          # a forbidden key: rule 9 refuses the file
        return gf

    monkeypatch.setattr(job, "GAME_FILE_HOOK", poison)
    res = run_once(env, api, clock, now=NOW + timedelta(seconds=120))
    assert res["exit"] == 0 and res["job_state"] == "ok"
    assert (env["out"] / "games" / "849846.json").read_bytes() == good
    st = job.load_state(env["paths"])
    assert st["refused_files"]["games/849846.json"]["n"] == 1
    latest = json.loads((env["out"] / "latest.json").read_text(encoding="utf-8"))
    assert latest["job"]["state"] == "ok" and latest["job"]["refusals_24h"] == 1
    cards = {c["pk"]: c for c in json.loads((env["out"] / "2026-09-30.json").read_text(encoding="utf-8"))["games"]}
    assert cards[849846]["stale_since"]


def test_the_if_necessary_pair_on_disk(env):
    clock = FakeClock()
    before, after = load("schedule_2025_wc_before.json"), load("schedule_2025_wc_after.json")
    for d in (before, after):
        d["copyright"] = COPYRIGHT
    api = FakeAPI(clock, before)
    now = datetime(2025, 10, 3, 9, 0, tzinfo=UTC)
    seed_state(env, week_date="2025-10-03")
    run_once(env, api, clock, now=now)
    d1 = json.loads((env["out"] / "2025-10-02.json").read_text(encoding="utf-8"))
    assert 813067 in {c["pk"] for c in d1["games"]}
    # MLB deletes the unneeded Game 3 after the sweep: the card drops
    api.schedule = after
    res = run_once(env, api, clock, now=now + timedelta(seconds=1800))
    d2 = json.loads((env["out"] / "2025-10-02.json").read_text(encoding="utf-8"))
    assert 813067 not in {c["pk"] for c in d2["games"]} and res["exit"] == 0
    # a game that vanishes without a moved status or an if-necessary mark is refused
    gone = copy.deepcopy(after)
    gone["dates"][-1]["games"] = [g for g in gone["dates"][-1]["games"] if g["gamePk"] != 813065]
    api.schedule = gone
    res3 = run_once(env, api, clock, now=now + timedelta(seconds=3600))
    d3 = json.loads((env["out"] / "2025-10-02.json").read_text(encoding="utf-8"))
    assert 813065 in {c["pk"] for c in d3["games"]}          # the last good copy stays
    assert res3["exit"] == 0 and res3["job_state"] in ("ok", "idle")
    st = job.load_state(env["paths"])
    assert "8" in st["refused_files"]["2025-10-02.json"]["rule"]
    latest = json.loads((env["out"] / "latest.json").read_text(encoding="utf-8"))
    assert latest["job"]["state"] in ("ok", "idle")


def test_a_finalize_larger_than_one_invocation_rolls_over_and_is_due_on_the_next_tick(env):
    clock = FakeClock()
    base = _game(849845, "F")
    games = []
    for i in range(25):
        g = copy.deepcopy(base)
        g["gamePk"] = 800000 + i
        g["officialDate"] = "2026-09-29"
        games.append(g)
    api = FakeAPI(clock, schedule_of(*games), wp={"*": load("wp_849845_ext.json")}, box={"*": load("box_849845.json")},
                  feed={"*": load("feed_849845.json")})
    now = datetime(2026, 9, 30, 10, 0, 10, tzinfo=UTC)
    seed_state(env, week_date="2026-09-29")
    res = run_once(env, api, clock, now=now)
    assert res["action"] == "week" and res["requests"] <= job.MAX_REQUESTS_PER_RUN
    st = job.load_state(env["paths"])
    left = st["pending"]["finalize"]
    assert left and res["counts"]["rolled_over"] > 0
    frozen = [pk for pk, g in st["games"].items() if g.get("frozen")]
    assert len(frozen) + len(left) == 25
    nxt = now + timedelta(seconds=120)
    slate = job.read_json(env["paths"]["slate"])
    d = job.decide(nxt, slate, st, tick=job.tick_of(nxt.timestamp()))
    assert d["acts"] and d["cycle"] == "due" and any(x.startswith(("finalize", "rollover")) for x in d["due"])
    res2 = run_once(env, api, clock, now=nxt)
    assert res2["action"] == "due"
    st2 = job.load_state(env["paths"])
    assert len(st2["pending"]["finalize"]) < len(left)
    # a frozen game's work file keeps no payload
    w = json.loads((env["store"] / "work" / f"{frozen[0]}.json").read_text(encoding="utf-8"))
    assert w["frozen"] and "wp" not in w and "box" not in w


# --------------------------------------------------------------------------- #
# The lock, the overlap, the epoch hold, bad_out
# --------------------------------------------------------------------------- #
def test_an_overlap_stamps_the_heartbeat_and_a_run_log_line(env):
    lock = job.JobLock(env["paths"]["lock"])
    assert lock.acquire()
    try:
        clock = FakeClock()
        api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
        res = run_once(env, api, clock)
        assert res["action"] == "overlap" and res["exit"] == 0 and api.calls == []
        hb = json.loads(env["paths"]["heartbeat"].read_text(encoding="utf-8"))
        assert hb["action"] == "overlap"
        assert json.loads((env["store"] / "runlog-2026-09-30.jsonl").read_text(encoding="utf-8")
                          .splitlines()[-1])["action"] == "overlap"
        assert not env["out"].exists()
    finally:
        lock.release()


def test_a_killed_holder_leaves_no_lock_that_blocks_the_next_run(env):
    code = ("import sys, time; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2]); "
            "import scores_job as j; from pathlib import Path; l = j.JobLock(Path(sys.argv[3])); "
            "assert l.acquire(); print('held', flush=True); time.sleep(120)")
    proc = subprocess.Popen([sys.executable, "-c", code, str(ROOT), str(ROOT / "tools"), str(env["paths"]["lock"])],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "held"
        probe = job.JobLock(env["paths"]["lock"])
        assert not probe.acquire()                     # held by the live process
        proc.kill()
        proc.wait(timeout=30)
        deadline = time.time() + 10
        got = False
        while time.time() < deadline and not got:
            got = probe.acquire()
            if not got:
                time.sleep(0.1)
        assert got, "a killed holder left a lock behind"
        probe.release()
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=30)
        for s in (proc.stdout, proc.stderr):
            s.close()


def test_the_job_never_opens_the_nightly_lock(env, monkeypatch):
    import builtins
    opened = []
    real_open, real_os_open = builtins.open, os.open

    def spy_open(file, *a, **k):
        opened.append(str(file))
        return real_open(file, *a, **k)

    def spy_os_open(path, *a, **k):
        opened.append(str(path))
        return real_os_open(path, *a, **k)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(os, "open", spy_os_open)
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    run_once(env, api, clock)
    assert opened and not [p for p in opened if "nightly" in p]
    assert all(job._inside(Path(p), env["tmp"]) or not job._inside(Path(p), ROOT) for p in opened
               if Path(p).is_absolute())


def test_the_epoch_hold_with_a_temp_sentinel(env, monkeypatch):
    snap = env["tmp"] / "_pre_epoch_fwar_2026-10"
    snap.mkdir()
    doc = env["tmp"] / "gate.md"
    monkeypatch.setattr(job, "EPOCH_SNAPSHOT", snap)
    monkeypatch.setattr(job, "EPOCH_GATE_DOC", doc)
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    for text in ("# gate\n\n## 9. Results\n\n### 2026-10-02: the arm set is fixed\n",
                 "## 9. Results\n\n  eWAR v2 only after step Z, in its own task.\n",
                 "## 9. Results\n\n### 2026-10-09: rows land before step Z\n"):
        doc.write_text(text, encoding="utf-8")
        res = run_once(env, api, clock)
        assert res["action"] == "epoch_hold" and res["exit"] == 0, text
    assert api.calls == [] and job.CALLS["n"] == 0
    assert files_under(env["store"]) <= {"heartbeat.json", "runlog-2026-09-30.jsonl"}
    assert json.loads(env["paths"]["heartbeat"].read_text(encoding="utf-8"))["action"] == "epoch_hold"
    doc.write_text("## 9. Results\n\n### 2026-10-12: step Z recorded at abc123\n", encoding="utf-8")
    assert job.step_z_entry() == "2026-10-12"
    seed_state(env, week_date="2026-09-30")
    assert run_once(env, api, clock)["action"] == "idle" and api.urls("schedule")
    snap.rmdir()
    doc.write_text("## 9. Results\n", encoding="utf-8")
    assert job.epoch_hold()[0] is False


def test_an_out_under_data_is_refused(env, monkeypatch):
    data = env["tmp"] / "app" / "data"
    monkeypatch.setattr(sc, "SCORES_LIVE", True)
    monkeypatch.setenv("EEPHUS_SCORES_OUT", str(data / "scores"))
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    res = run_once(env, api, clock)
    assert res == {"action": "bad_out", "exit": 2, "reason": res["reason"]} and "data/" in res["reason"]
    assert api.calls == [] and not data.exists()
    assert job.main(["--no-jitter"]) == 2
    # the store under data/ is refused too, and an OUT inside the webroot
    monkeypatch.setenv("EEPHUS_SCORES_OUT", str(env["tmp"] / "fine"))
    monkeypatch.setenv("EEPHUS_SCORES_STORE", str(data / "store"))
    assert job.bad_out(job.resolve_paths())
    monkeypatch.setenv("EEPHUS_SCORES_STORE", str(env["store"]))
    monkeypatch.setenv("EEPHUS_SCORES_OUT", str(env["web"] / "data" / "scores"))
    assert "webroot" in job.bad_out(job.resolve_paths())


def test_scores_live_false_writes_only_under_the_preview_directory(env):
    elsewhere = env["tmp"] / "out_env"
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    run_once(env, api, clock)
    assert not elsewhere.exists()
    written = {p for p in files_under(env["tmp"]) if not p.startswith("web/")}
    assert written and all(p.startswith("store/") for p in written), written
    published = {p for p in written if sc.kind_of_name(p.split("/", 2)[-1]) and not p.startswith("store/work/")}
    assert published and all(p.startswith("store/preview/") for p in published), published


# --------------------------------------------------------------------------- #
# --backfill
# --------------------------------------------------------------------------- #
def test_backfill_refusals_and_history_floor(env):
    ok_now = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    assert job.backfill_refusal("2026-03-24", "2026-04-01", ok_now, None).startswith("2026-03-24 is before")
    assert job.HISTORY_FLOOR == "2026-03-25"
    assert "nightly window" in job.backfill_refusal("2026-04-01", "2026-04-02", datetime(2026, 10, 3, 7, 30, tzinfo=UTC), None)
    assert job.backfill_refusal("2026-04-01", "2026-04-02", datetime(2026, 10, 3, 11, 0, tzinfo=UTC), None) is None
    live = _slate(_row(1, "2026-10-03", "2026-10-03T11:30:00Z", "live"), fetched="2026-10-03T11:58:00Z")
    assert "live" in job.backfill_refusal("2026-04-01", "2026-04-02", ok_now, live)
    # a slate the job wrote hours ago says nothing about now
    old = _slate(_row(1, "2026-10-03", "2026-10-03T11:30:00Z", "live"), fetched="2026-10-03T07:00:00Z")
    assert job.backfill_refusal("2026-04-01", "2026-04-02", ok_now, old) is None
    assert "past date" in job.backfill_refusal("2026-04-01", "2026-10-03", ok_now, None)
    assert job.main(["--backfill", "2026-03-01:2026-03-30"]) == 2


def test_a_cached_win_probability_file_is_accepted_only_when_complete_and_scored_as_the_schedule(env):
    g = _game(849845, "F")
    wp = load("wp_849845_full.json")
    cache = env["tmp"] / "house" / "win_prob"
    cache.mkdir(parents=True)
    (cache / "849845.json").write_text(json.dumps(wp), encoding="utf-8")
    assert job.cached_wp_ok(849845, g) is not None
    bad_score = copy.deepcopy(g)
    bad_score["linescore"]["teams"]["home"]["runs"] = 9
    bad_score["teams"]["home"]["score"] = 9
    assert job.cached_wp_ok(849845, bad_score) is None
    partial = copy.deepcopy(wp)
    els = partial if isinstance(partial, list) else partial["winProbability"]
    last = max(els, key=lambda e: e["atBatIndex"])
    last["about"]["isComplete"] = False
    (cache / "849845.json").write_text(json.dumps(partial), encoding="utf-8")
    assert job.cached_wp_ok(849845, g) is None
    feeds = env["tmp"] / "house" / "game_feeds"
    feeds.mkdir(parents=True)
    feed = load("feed_849845.json")
    (feeds / "849845.json").write_text(json.dumps(feed), encoding="utf-8")
    assert job.cached_feed_ok(849845) is not None
    live = copy.deepcopy(feed)
    live["gameData"]["status"] = {"abstractGameState": "Live", "codedGameState": "I", "detailedState": "In Progress"}
    (feeds / "849845.json").write_text(json.dumps(live), encoding="utf-8")
    assert job.cached_feed_ok(849845) is None


def test_backfill_uses_the_cached_finals_and_writes_no_shared_cache(env, monkeypatch):
    cache = env["tmp"] / "house" / "win_prob"
    feeds = env["tmp"] / "house" / "game_feeds"
    cache.mkdir(parents=True)
    feeds.mkdir(parents=True)
    (cache / "849845.json").write_text(json.dumps(load("wp_849845_full.json")), encoding="utf-8")
    (feeds / "849845.json").write_text(json.dumps(load("feed_849845.json")), encoding="utf-8")
    before = {p: p.stat().st_mtime_ns for p in (cache / "849845.json", feeds / "849845.json")}
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(_game(849845, "F")), box={849845: load("box_849845.json")})
    now = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    res = job.backfill("2026-09-29", "2026-09-29", paths=env["paths"], now_fn=lambda: now, adapter=api,
                       clock=clock, sleep=clock.sleep)
    assert res["exit"] == 0 and res["counts"]["wp_cached"] == 1 and res["counts"]["feed_cached"] == 1, res
    assert not api.urls("wp") and not api.urls("feed") and len(api.urls("box")) == 1
    assert files_under(cache.parent) == {"win_prob/849845.json", "game_feeds/849845.json"}
    assert {p: p.stat().st_mtime_ns for p in before} == before
    gf = json.loads((env["out"] / "games" / "849845.json").read_text(encoding="utf-8"))
    assert [s["name"] for s in gf["stars"]][:1] and gf["card"]["state"] == "final"
    assert job.load_state(env["paths"])["games"]["849845"]["frozen"] is True
    assert job.verify_revs(job.Writer(env["out"])) == []


# --------------------------------------------------------------------------- #
# The command line
# --------------------------------------------------------------------------- #
def test_why_and_dry_run_write_nothing_and_selfcheck_says_never_run(env, capsys):
    assert job.main(["--why"]) == 0
    assert job.main(["--dry-run"]) == 0
    assert not env["store"].exists()
    assert job.main(["--selfcheck"]) == 1
    assert "NEVER RUN on this machine" in capsys.readouterr().out


def test_strip_emdashes_targets_the_job():
    sys.path.insert(0, str(ROOT / "tools"))
    import strip_emdashes
    assert "tools/scores_job.py" in strip_emdashes.TARGETS
    text = (ROOT / "tools" / "scores_job.py").read_text(encoding="utf-8")
    assert chr(0x2014) not in text and chr(0x2013) not in text


def test_the_owner_answers_and_cadence_literals():
    assert (job.SC_TERMS, job.SC_HISTORY, job.SC_KEEP) == ("a", "a", "a")
    assert job.LIVE_GATE_S == 90 and job.IDLE_INTERVAL_S == 1800 and job.OFFSEASON_INTERVAL_S == 21600
    assert (job.MAX_REQUESTS_PER_RUN, job.RUN_DEADLINE_S, job.LAST_START_S, job.REQUEST_TIMEOUT_S,
            job.MIN_SPACING_S) == (60, 90, 75, 15, 0.5)
    assert (job.BACKOFF_BASE_S, job.BACKOFF_CAP_S) == (120, 1800)
    assert job.USER_AGENT == "eephus.io scores job (+https://eephus.io/scores/)"
    assert job.SCHEDULE_HYDRATE == "team,linescore,probablePitcher,decisions,seriesStatus,lineups,flags,weather,broadcasts(all)"
    assert job.GAME_TYPES == "R,F,D,L,W,A"
    assert (job.DOWN_AFTER_S, job.POLL_LIVE_S, job.POLL_IDLE_S) == (1800, 45, 300)

# --------------------------------------------------------------------------- #
# The October bracket (SCORES_4b): one call per idle cycle, first postseason
# date to the last, written into the season index
# --------------------------------------------------------------------------- #
def test_bracket_due_runs_from_the_first_postseason_date_to_the_last():
    d = datetime(2026, 9, 30, tzinfo=UTC).date()
    reg = [{"gameType": "R", "officialDate": "2026-09-27"}]
    assert job.bracket_due({}, reg, d) is None                              # regular season only
    assert job.bracket_due({}, [{"gameType": "F", "officialDate": "2026-10-01"}], d) is None   # not yet started
    assert job.bracket_due({}, [{"gameType": "F", "officialDate": "2026-09-29"}], d) == 2026
    block = {"first": "2026-09-29", "last": "2026-10-31", "done": False}
    st = {"bracket": {"2026": block}}
    for day, want in (("2026-10-05", 2026), ("2026-10-31", 2026), ("2026-11-01", 2026), ("2026-11-02", None),
                      ("2026-09-28", None)):
        assert job.bracket_due(st, reg, datetime.fromisoformat(day).date()) == want, day
    st["bracket"]["2026"]["done"] = True
    assert job.bracket_due(st, [{"gameType": "W", "officialDate": "2026-10-31"}],
                           datetime(2026, 11, 1).date()) is None              # the final state is on file


def _upcoming():
    """A scheduled game three days out, so the slate is not the offseason."""
    g = _game(849848, "S")
    g.update(officialDate="2026-10-10", gameDate="2026-10-10T20:00:00Z")
    return g


def _idle_bracket_run(env, clock, series, *, now):
    api = FakeAPI(clock, schedule_of(_game(849845, "F"), _upcoming()), series=series, **base_payloads())
    return api, run_once(env, api, clock, now=now)


def test_an_idle_cycle_reads_the_bracket_once_and_the_season_index_carries_it(env):
    clock = FakeClock()
    seed_state(env, week_date="2026-10-07")
    now = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)           # before 10:00 UTC: idle, not week
    api, res = _idle_bracket_run(env, clock, load("postseason_series_2026.json"), now=now)
    assert res["exit"] == 0 and res["action"] == "idle", res
    assert api.urls("series") == ["https://statsapi.mlb.com/api/v1/schedule/postseason/series?sportId=1&season=2026"]
    doc = json.loads((env["out"] / "index-2026.json").read_text(encoding="utf-8"))
    assert doc["bracket"] == sc.build_bracket(load("postseason_series_2026.json"), season=2026)
    assert sc.validate_payload("season_index", doc, name="index-2026.json")["ok"]
    assert job.verify_revs(job.Writer(env["out"])) == []


def test_a_live_cycle_never_reads_the_bracket(env):
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), series=load("postseason_series_2026.json"), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    assert run_once(env, api, clock)["action"] == "idle"
    n = len(api.urls("series"))
    assert n == 1                                            # 849845 (gameType F) is dated before today
    assert run_once(env, api, clock, now=NOW + timedelta(seconds=120))["action"] == "live"
    assert len(api.urls("series")) == n


def test_a_failed_bracket_read_keeps_the_last_block_and_a_new_one_replaces_it(env):
    clock = FakeClock()
    seed_state(env, week_date="2026-10-07")
    t0 = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
    _idle_bracket_run(env, clock, load("postseason_series_2026.json"), now=t0)
    first = json.loads((env["out"] / "index-2026.json").read_text(encoding="utf-8"))["bracket"]
    api = FakeAPI(clock, schedule_of(_game(849845, "F"), _upcoming()), series=None, **base_payloads())
    api.status[("series", None)] = (500, {})
    t1 = t0 + timedelta(seconds=job.IDLE_INTERVAL_S)
    res = run_once(env, api, clock, now=t1)
    assert res["exit"] == 0 and res["action"] == "idle" and len(api.urls("series")) == 1, res
    assert json.loads((env["out"] / "index-2026.json").read_text(encoding="utf-8"))["bracket"] == first
    t2 = t1 + timedelta(seconds=job.IDLE_INTERVAL_S)
    _idle_bracket_run(env, clock, load("postseason_series_2026-10-07.json"), now=t2)
    now_doc = json.loads((env["out"] / "index-2026.json").read_text(encoding="utf-8"))
    assert now_doc["bracket"] != first
    assert now_doc["bracket"]["rounds"][0]["series"][0]["text"] == "CHW wins 2-0"
    assert job.verify_revs(job.Writer(env["out"])) == []
