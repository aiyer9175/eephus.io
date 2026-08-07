# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A job that never fires must be visible without a person noticing.

THE CLASS THIS CLOSES. Three scheduled jobs were configured and inert on
2026-08-06 and every one looked healthy in its own artifact:

  * the betting odds snapshot: key set, provider named, step present,
    .cache/odds/ never created, and data/betting_status.json reporting
    `configured: true` the whole time;
  * the completed-games cache, which could never advance past the day it was
    first written, so the validation clock read as running and was not;
  * build_context and backtest, which ran only in main() and therefore moved
    once a month while every input to them was nightly.

The missing fact in all three was never "is this value wrong". It was "did this
job happen at all", and nothing recorded that.

WHAT THESE TESTS HOLD
  1. A run is recorded, and success is distinguished from an attempt.
  2. NEVER-REPORTED is distinguished from LATE. The first is usually a wiring
     bug and the second an outage; merging them re-creates the confusion this
     module exists to remove.
  3. A job that attempts and always fails is stale even while its attempt
     counter climbs. Counting attempts alone would have called the odds
     snapshot healthy the moment it started erroring.
  4. Recording NEVER raises into the caller. A heartbeat that can break the job
     it observes is worse than none.
  5. The three known offenders are actually wired into run_daily.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

hb = pytest.importorskip("job_heartbeat")


@pytest.fixture
def led(tmp_path):
    return tmp_path / "job_heartbeat.json"


def test_a_run_is_recorded(led):
    hb.record("demo", ok=True, result="fine", path=led)
    jobs = hb.load(led)
    assert jobs["demo"]["n_attempts"] == 1
    assert jobs["demo"]["n_successes"] == 1
    assert jobs["demo"]["last_success_at"]
    assert jobs["demo"]["last_result"] == "fine"


def test_an_attempt_is_not_a_success(led):
    hb.record("demo", ok=False, result="boom", path=led)
    row = hb.load(led)["demo"]
    assert row["n_attempts"] == 1
    assert row.get("n_successes", 0) == 0
    assert "last_success_at" not in row, (
        "a failed run must not stamp a success, or a job failing every night "
        "reads as healthy")


def test_never_reported_is_not_the_same_as_late(led):
    """THE DISTINCTION THAT MATTERS. A job that never reported is usually a
    wiring bug; a job that ran and is overdue is usually an outage. They get
    fixed in different places."""
    s = hb.stale("nobody", max_age_hours=24, path=led)
    assert s["stale"] is True
    assert s["known"] is False, (
        "an unreported job must be flagged as UNKNOWN, not merely late")
    assert "never reported" in s["why"]

    hb.record("ran", ok=True, path=led)
    t = hb.stale("ran", max_age_hours=24, path=led)
    assert t["known"] is True and t["stale"] is False


def test_a_job_that_always_fails_is_stale_however_often_it_tries(led):
    """The odds snapshot shape. An attempt counter alone would have called it
    healthy the moment it started erroring every night."""
    for _ in range(30):
        hb.record("flaky", ok=False, result="down", path=led)
    s = hb.stale("flaky", max_age_hours=24, path=led)
    assert s["stale"] is True, (
        "30 attempts and zero successes is not a healthy job")
    assert s["n_attempts"] == 30 and s["n_successes"] == 0
    assert "never succeeded" in s["why"]


def test_a_stale_success_is_caught(led, monkeypatch):
    hb.record("old", ok=True, path=led)
    d = json.loads(led.read_text(encoding="utf-8"))
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=100)).replace(
        microsecond=0).isoformat()
    d["jobs"]["old"]["last_success_at"] = long_ago
    d["jobs"]["old"]["last_attempt_at"] = long_ago
    led.write_text(json.dumps(d), encoding="utf-8")
    s = hb.stale("old", max_age_hours=24, path=led)
    assert s["stale"] is True and s["age_hours"] > 90


def test_recording_never_raises_into_the_caller(monkeypatch, tmp_path):
    """A heartbeat that can break the job it observes is worse than none."""
    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(hb, "_write", boom)
    out = hb.record("demo", ok=True, path=tmp_path / "x.json")   # must not raise
    assert out == {}


def test_an_unreadable_ledger_is_empty_not_fatal(led):
    led.write_text("{ not json", encoding="utf-8")
    assert hb.load(led) == {}


def test_report_separates_unrecognised_jobs(led):
    """A renamed job silently dropping out of coverage is how a heartbeat stops
    watching the thing it was added for."""
    hb.record("known", ok=True, path=led)
    hb.record("mystery", ok=True, path=led)
    r = hb.report({"known": 24}, path=led)
    assert r["unrecognised_jobs"] == ["mystery"]
    assert r["all_healthy"] is False, (
        "an unrecognised job must break the healthy verdict, not be ignored")


def test_the_three_known_offenders_are_wired_into_the_nightly():
    """Each of these was configured and inert on 2026-08-06."""
    src = (Path(__file__).parent / "run_monthly.py").read_text(encoding="utf-8")
    _, _, tail = src.partition("def run_daily")
    daily, _, _ = tail.partition("\ndef main")
    for job in ("betting_odds_snapshot", "leaderboard_vintage",
                "betting_model_refit"):
        assert job in daily, (
            f"{job} is not reporting a heartbeat from run_daily. It was "
            "configured and never fired once already.")
