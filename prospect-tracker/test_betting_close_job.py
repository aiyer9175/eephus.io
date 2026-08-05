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
