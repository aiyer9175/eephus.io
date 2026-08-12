# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The close-snapshot job fires once, in the right window, and never twice.

This job is cron'd every 15 minutes and spends real API credits when it fires,
so the gating IS the product. The failure modes that matter are (a) firing after
first pitch, which records something that is not a closing line while looking
correct, and (b) firing more than once for a slate, which drains a 500/month
free tier. Both are pinned here.

decide() is pure: it reads artifacts and returns a verdict without spending a
credit or writing a file, so these tests never touch the network.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import betting_export as be
import betting_ingest as bi
import betting_close_job as job

FIRST = datetime(2026, 8, 5, 23, 5, tzinfo=timezone.utc)   # 7:05pm ET


class _Slate(unittest.TestCase):
    """Installs a two-game slate and an unconfigured-free environment."""

    def setUp(self):
        self._games, self._close, self._conf = be.slate_games, bi.closing_snapshot, bi.configured
        be.slate_games = lambda on_date=None: [
            {"date": "2026-08-05", "datetime": FIRST.isoformat()},
            {"date": "2026-08-05", "datetime": (FIRST + timedelta(hours=1)).isoformat()},
        ]
        bi.closing_snapshot = lambda day: None
        bi.configured = lambda: True

    def tearDown(self):
        be.slate_games, bi.closing_snapshot, bi.configured = self._games, self._close, self._conf


class TheWindow(_Slate):
    def test_it_does_not_fire_in_the_morning(self):
        self.assertFalse(job.decide(now=FIRST - timedelta(hours=8))["fire"])

    def test_it_does_not_fire_just_before_the_window(self):
        self.assertFalse(job.decide(now=FIRST - timedelta(minutes=21))["fire"])

    def test_it_fires_exactly_at_the_target(self):
        d = job.decide(now=FIRST - timedelta(minutes=job.LEAD_MINUTES))
        self.assertTrue(d["fire"])
        self.assertEqual(d["credits"], bi.credits_for())

    def test_it_still_fires_late_but_before_first_pitch(self):
        """A box that woke up late should still capture a line that is nearly
        the close, rather than skip and leave the pick ungraded forever."""
        d = job.decide(now=FIRST - timedelta(minutes=1))
        self.assertTrue(d["fire"])
        self.assertTrue(d.get("late"))

    def test_it_refuses_at_and_after_first_pitch(self):
        """The defect this prevents is subtle: an in-game line looks like a
        number and grades like a number, but it is not a closing line, and the
        record would silently be measuring the wrong thing."""
        for now in (FIRST, FIRST + timedelta(minutes=1), FIRST + timedelta(hours=2)):
            d = job.decide(now=now)
            self.assertFalse(d["fire"])
            self.assertIn("too late", d["reason"])

    def test_the_window_is_anchored_on_the_EARLIEST_first_pitch(self):
        """A 4:05 getaway game in front of a 7:05 slate moves the window; the
        close must precede the first game, not the modal one."""
        early = FIRST - timedelta(hours=3)
        be.slate_games = lambda on_date=None: [
            {"date": "2026-08-05", "datetime": FIRST.isoformat()},
            {"date": "2026-08-05", "datetime": early.isoformat()},
        ]
        d = job.decide(now=early - timedelta(minutes=job.LEAD_MINUTES))
        self.assertTrue(d["fire"])
        d2 = job.decide(now=FIRST - timedelta(minutes=job.LEAD_MINUTES))
        self.assertFalse(d2["fire"])


class TheGuards(_Slate):
    def test_one_slate_gets_one_snapshot(self):
        """The quota guard. A cron every 15 minutes means a missing guard costs
        the whole month, so it is a real lookup rather than a lockfile."""
        bi.closing_snapshot = lambda day: {"kind": "close"}
        d = job.decide(now=FIRST - timedelta(minutes=5))
        self.assertFalse(d["fire"])
        self.assertIn("already exists", d["reason"])

    def test_no_key_is_a_quiet_no_op(self):
        bi.configured = lambda: False
        d = job.decide(now=FIRST - timedelta(minutes=5))
        self.assertFalse(d["fire"])
        self.assertIn(bi.ENV_KEY, d["reason"])

    def test_an_off_day_is_a_quiet_no_op(self):
        be.slate_games = lambda on_date=None: []
        d = job.decide(now=FIRST)
        self.assertFalse(d["fire"])
        self.assertIn("no games", d["reason"])

    def test_a_slate_with_no_stamps_does_not_crash(self):
        be.slate_games = lambda on_date=None: [{"date": "2026-08-05"}]
        d = job.decide(now=FIRST)
        self.assertFalse(d["fire"])

    def test_deciding_spends_nothing(self):
        """decide() must never reach the network: it is called every 15 minutes
        and only one of those calls is allowed to cost anything."""
        def _boom(*a, **k):
            raise AssertionError("decide() attempted to fetch")
        real = bi.fetch_snapshot
        bi.fetch_snapshot = _boom
        try:
            for offset in (-480, -21, -10, -1, 0, 120):
                job.decide(now=FIRST + timedelta(minutes=offset))
        finally:
            bi.fetch_snapshot = real


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# THE HEARTBEAT, and why the RED needed one.
#
# snapshot_health could see that no close snapshot existed and had to guess
# between two very different repairs: "the close cron is either not installed or
# is running in the wrong timezone window". Nothing on disk could separate them,
# because a job that runs 96 times a day and correctly no-ops 95 of them leaves
# no trace at all until the night it fires. The job now stamps every invocation,
# refusals included, and the diagnosis reads that stamp.
# ---------------------------------------------------------------------------
def test_the_heartbeat_records_a_refusal_not_just_a_capture(tmp_path):
    """A no-op is the case the RED could not see, so it is the case pinned."""
    hb = tmp_path / "close_job_heartbeat.json"
    decision = {"fire": False, "reason": "too early: 240 min until the window opens",
                "slate_date": "2026-08-12", "games": 11}
    job.write_heartbeat(decision, path=hb)
    got = job.read_heartbeat(hb)
    assert got["fired"] is False
    assert got["slate_date"] == "2026-08-12"
    assert "too early" in got["reason"]
    assert got["last_run_utc"], "a heartbeat with no timestamp cannot age"


def test_the_heartbeat_never_breaks_the_capture(tmp_path):
    """Telemetry must never be the reason a close capture does not happen."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("i am a file", encoding="utf-8")
    # mkdir under a regular file fails on every platform, unlike chmod, which
    # does not restrict writes on Windows and would have made this vacuous here.
    try:
        job.write_heartbeat({"fire": True, "reason": "inside the closing window"},
                            path=blocker / "sub" / "hb.json")
    except Exception as exc:                      # pragma: no cover
        raise AssertionError(f"write_heartbeat raised {exc!r}") from exc


def test_the_diagnosis_separates_not_scheduled_from_never_firing(tmp_path, monkeypatch):
    """The two states name two different repairs, so they get two messages."""
    import betting_export as be
    hb = tmp_path / "close_job_heartbeat.json"

    monkeypatch.setattr(be, "CLOSE_HEARTBEAT_PATH", hb)
    never = be.snapshot_health(14)
    if never["n_slates_with_close"] == 0:
        assert "never run on this machine" in never["diagnosis"], never["diagnosis"]
        assert never["close_job_ever_ran"] is False

    job.write_heartbeat({"fire": False, "reason": "too late: first pitch has passed",
                         "slate_date": "2026-08-12"}, path=hb)
    running = be.snapshot_health(14)
    if running["n_slates_with_close"] == 0:
        assert "never run on this machine" not in running["diagnosis"]
        assert "firing window is never opening" in running["diagnosis"], \
            running["diagnosis"]
        assert running["close_job_ever_ran"] is True
