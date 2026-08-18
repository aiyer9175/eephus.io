# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Rolling-permalink capture discipline (2026-07-31 ingest repair).

These pin the three rules that stop a rewritten permalink from corrupting a
stored point-in-time board:

  1. the label is DATE-STAMPED, never fixed;
  2. a write only happens when the board's CONTENT FINGERPRINT changed;
  3. a degraded parse is refused by a health gate.

The regression they exist for: Just Baseball's rolling permalink was pinned
to 'JB 2026 Preseason' / 2026-03-04. JB rewrote the page, insert_snapshots
upserted on (source, interval_label, player_key), and the stored March board
became a 126-row chimera with 26 duplicate ranks - two #1s (Konnor Griffin
FV 70 from March beside Jesus Made FV 60 from June), still dated March.

Offline: parsing runs off .cache/, storage writes are stubbed. No network,
no DB writes."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import scrapers
import storage
from scrapers import Snapshot

CACHE = Path(__file__).parent / ".cache"
JB_CACHE = "jb_jb_2026_preseason.html"


def _snap(key, rank, fv, *, date="2026-01-01", label="L", source="s",
          pos=None, org=None, tools=None):
    return Snapshot(source=source, snapshot_date=date, interval_label=label,
                    player_key=key, player_name=key.replace("_", " ").title(),
                    position=pos, org=org, rank=rank, fv=fv, status="active",
                    tools=tools)


def _board(n=100, fv=50.0):
    return [_snap(f"p{i}", i + 1, fv) for i in range(n)]


class Fingerprint(unittest.TestCase):
    def test_ignores_date_label_org_and_tools(self):
        """The fingerprint answers 'is this the same BOARD', not 'is this the
        same row'. Outlets re-edit prose and backfill orgs constantly; only a
        rank/FV move is a new edition."""
        a = [_snap("k", 1, 50.0)]
        b = [_snap("k", 1, 50.0, date="2026-09-09", label="OTHER",
                   pos="SS", org="NYY", tools={"hit": 60})]
        self.assertEqual(scrapers.board_fingerprint(a),
                         scrapers.board_fingerprint(b))

    def test_detects_rank_move(self):
        self.assertNotEqual(scrapers.board_fingerprint([_snap("k", 1, 50.0)]),
                            scrapers.board_fingerprint([_snap("k", 2, 50.0)]))

    def test_detects_fv_move(self):
        self.assertNotEqual(scrapers.board_fingerprint([_snap("k", 1, 50.0)]),
                            scrapers.board_fingerprint([_snap("k", 1, 55.0)]))

    def test_detects_roster_change(self):
        self.assertNotEqual(scrapers.board_fingerprint(_board(100)),
                            scrapers.board_fingerprint(_board(99)))

    def test_order_independent(self):
        b = _board(20)
        self.assertEqual(scrapers.board_fingerprint(b),
                         scrapers.board_fingerprint(list(reversed(b))))


class JBHealthGate(unittest.TestCase):
    def test_rejects_duplicate_ranks(self):
        """THE regression test. A chimera has two players at each of several
        ranks; that shape must never be written."""
        chimera = _board(100) + [_snap(f"x{i}", i + 1, 60.0) for i in range(26)]
        problems = scrapers.validate_jb_board(chimera)
        self.assertTrue(any("duplicate ranks" in p for p in problems), problems)

    def test_rejects_thin_parse(self):
        problems = scrapers.validate_jb_board(_board(40))
        self.assertTrue(any("only 40" in p for p in problems), problems)

    def test_rejects_missing_fv_coverage(self):
        thin_fv = ([_snap(f"p{i}", i + 1, None) for i in range(60)]
                   + [_snap(f"q{i}", 61 + i, 50.0) for i in range(40)])
        problems = scrapers.validate_jb_board(thin_fv)
        self.assertTrue(any("FV coverage" in p for p in problems), problems)

    def test_accepts_a_healthy_board(self):
        self.assertEqual(scrapers.validate_jb_board(_board(100)), [])


class _StubbedWrites:
    """Context manager: capture insert_snapshots calls instead of writing."""

    def __enter__(self):
        self.written: list[list] = []
        self._real = storage.insert_snapshots
        storage.insert_snapshots = self._capture
        return self

    def _capture(self, rows):
        rows = list(rows)
        self.written.append(rows)
        return len(rows)

    def __exit__(self, *exc):
        storage.insert_snapshots = self._real
        return False

    @property
    def n_rows(self):
        return sum(len(w) for w in self.written)


class JBRollingCapture(unittest.TestCase):
    def setUp(self):
        if not (CACHE / JB_CACHE).exists():
            self.skipTest("no cached Just Baseball page")
        body = (CACHE / JB_CACHE).read_text(encoding="utf-8")
        self._real_fetch = scrapers._fetch
        scrapers._fetch = lambda url, key, force=False, accept_json=False: \
            scrapers.FetchResult(body=body, status=200, from_cache=True, url=url)

    def tearDown(self):
        scrapers._fetch = self._real_fetch

    def test_jb_intervals_no_longer_pins_the_rolling_url(self):
        """The rolling permalink must not appear in the fixed-date archive
        list - that pairing is exactly what built the chimera."""
        for url, _label, _snap_date in scrapers.JB_INTERVALS:
            self.assertNotEqual(url, scrapers.JB_ROLLING_URL)

    def test_label_is_date_stamped_when_the_board_changed(self):
        """A genuinely NEW edition lands in its own dated interval, so it can
        never overwrite the ranks of the edition before it."""
        real_scrape = scrapers.scrape_just_baseball
        # A board no stored fingerprint can match -> forces the write path.
        scrapers.scrape_just_baseball = lambda url, label, snap, force=False: [
            _snap(f"novel_player_{i}", i + 1, 50.0, date=snap, label=label,
                  source=scrapers.JB_SOURCE) for i in range(100)]
        try:
            with _StubbedWrites() as w:
                res = scrapers.run_just_baseball_live(snap_date="2026-08-15")
        finally:
            scrapers.scrape_just_baseball = real_scrape
        self.assertIn("live", res, res)
        self.assertEqual(res["live"]["label"], "JB Live 2026-08-15")
        self.assertEqual(w.n_rows, 100)
        for row in w.written[0]:
            self.assertEqual(row.interval_label, "JB Live 2026-08-15")
            self.assertEqual(row.snapshot_date, "2026-08-15")

    def test_degraded_parse_is_never_written(self):
        real_scrape = scrapers.scrape_just_baseball
        scrapers.scrape_just_baseball = lambda url, label, snap, force=False: [
            _snap(f"p{i}", i + 1, 50.0, date=snap, label=label,
                  source=scrapers.JB_SOURCE) for i in range(30)]
        try:
            with _StubbedWrites() as w:
                res = scrapers.run_just_baseball_live(snap_date="2026-08-15")
        finally:
            scrapers.scrape_just_baseball = real_scrape
        self.assertIn("health", res, res)
        self.assertEqual(w.n_rows, 0)

    def test_chimera_shaped_parse_is_never_written(self):
        """The exact 126-row / 26-duplicate-rank shape that corrupted the
        stored March board must be refused at the gate."""
        real_scrape = scrapers.scrape_just_baseball
        scrapers.scrape_just_baseball = lambda url, label, snap, force=False: (
            [_snap(f"a{i}", i + 1, 50.0, date=snap, label=label,
                   source=scrapers.JB_SOURCE) for i in range(100)]
            + [_snap(f"b{i}", i + 1, 60.0, date=snap, label=label,
                     source=scrapers.JB_SOURCE) for i in range(26)])
        try:
            with _StubbedWrites() as w:
                res = scrapers.run_just_baseball_live(snap_date="2026-08-15")
        finally:
            scrapers.scrape_just_baseball = real_scrape
        self.assertIn("health", res, res)
        self.assertTrue(any("duplicate ranks" in p for p in res["health"]))
        self.assertEqual(w.n_rows, 0)

    def test_unchanged_board_writes_nothing(self):
        """A permalink that has not moved must not mint a new interval every
        run - that is what date-stamping alone would do."""
        rows = scrapers.scrape_just_baseball(
            scrapers.JB_ROLLING_URL, "probe", "2026-07-31")
        fp = scrapers.board_fingerprint(rows)
        # The gate dedupes against the NEWEST stored interval for the source
        # (latest_stored_board), never a fixed label, so the guard must ask
        # the same question. The old guard checked the fixed Midseason label
        # and went stale the day a real JB Live capture outran the cached
        # fixture page (2026-08-18: prev_label JB Live 2026-08-18 vs the
        # 2026-07-31 cached page): the unchanged branch legitimately cannot
        # fire when the newest stored board differs from the fixture. That
        # is fixture staleness, not a dedupe defect, and it skips with the
        # reason named. The dedupe itself stays pinned by the stubbed-write
        # tests above, which carry their own boards.
        _, _, newest_fp = scrapers.latest_stored_board(scrapers.JB_SOURCE)
        if newest_fp != fp:
            self.skipTest("this box's newest stored JB board no longer "
                          "matches the cached fixture page; the unchanged "
                          "branch cannot fire here")
        with _StubbedWrites() as w:
            res = scrapers.run_just_baseball_live(snap_date="2026-07-31")
        self.assertIn("unchanged", res, res)
        self.assertEqual(w.n_rows, 0)

    def test_parses_a_full_board_from_cache(self):
        rows = scrapers.scrape_just_baseball(
            scrapers.JB_ROLLING_URL, "probe", "2026-07-31")
        self.assertGreaterEqual(len(rows), 90)
        ranks = [r.rank for r in rows if r.rank is not None]
        self.assertEqual(len(ranks), len(set(ranks)), "parsed board has dupes")


class InternationalStableDate(unittest.TestCase):
    def test_interval_carries_no_baked_today(self):
        """The constant must not evaluate date.today() at import time - that
        is what re-dated all 50 rows on every run."""
        for _url, _label, snap, _year in scrapers.MLB_INTERNATIONAL_INTERVALS:
            self.assertIsNone(
                snap, "the rolling international interval must resolve its "
                      "date at scrape time, not freeze one at import")

    def test_unknown_interval_falls_back_to_the_sibling_convention(self):
        got = scrapers.resolve_international_snapshot_date(
            "MLB Pipeline 2099 International", 2099)
        self.assertEqual(got, "2099-01-15")

    def test_known_interval_reuses_the_stored_date(self):
        label = "MLB Pipeline 2026 International"
        _fp, stored = scrapers.stored_board_fingerprint(
            scrapers.MLB_INTERNATIONAL_SOURCE, label)
        if stored is None:
            self.skipTest("no international rows on file")
        self.assertEqual(
            scrapers.resolve_international_snapshot_date(label, 2026), stored,
            "a re-scrape must reuse the stored date, never stamp today")


class ESPNArticleProbe(unittest.TestCase):
    def test_known_ids_come_from_the_wired_urls(self):
        ids = scrapers.known_espn_article_ids()
        self.assertEqual(len(ids), len(scrapers.ESPN_INTERVALS))
        for i in ids:
            self.assertTrue(i.isdigit(), i)

    def test_probe_never_raises_on_a_bad_payload(self):
        real = scrapers._fetch
        scrapers._fetch = lambda url, key, force=False, accept_json=False: \
            scrapers.FetchResult(body="not json", status=200,
                                 from_cache=True, url=url)
        try:
            out = scrapers.probe_espn_new_prospect_article()
        finally:
            scrapers._fetch = real
        self.assertEqual(out["candidates"], [])
        self.assertIn("error", out)

    def test_probe_flags_only_unwired_ranking_headlines(self):
        import json as _json
        known = sorted(scrapers.known_espn_article_ids())[0]
        payload = {"articles": [
            {"id": known, "headline": "Top 100 MLB prospects for 2026",
             "links": {"web": {"href": "https://espn.com/x"}}},          # wired
            {"id": "99999999", "headline": "Updated top 100 MLB prospect rankings",
             "links": {"web": {"href": "https://espn.com/new"}}},        # NEW
            {"id": "88888888", "headline": "Prospect mailbag: your questions",
             "links": {"web": {"href": "https://espn.com/mb"}}},         # not a list
            {"id": "77777777", "headline": "Power rankings: every MLB team",
             "links": {"web": {"href": "https://espn.com/pr"}}},         # not prospects
        ]}
        real = scrapers._fetch
        scrapers._fetch = lambda url, key, force=False, accept_json=False: \
            scrapers.FetchResult(body=_json.dumps(payload), status=200,
                                 from_cache=True, url=url)
        try:
            out = scrapers.probe_espn_new_prospect_article()
        finally:
            scrapers._fetch = real
        self.assertEqual([c["id"] for c in out["candidates"]], ["99999999"])

    def test_probe_does_not_write_snapshots(self):
        """It logs a prompt for a human. It must never ingest: an article id
        is not evidence of editorial intent."""
        import json as _json
        payload = {"articles": [
            {"id": "99999999", "headline": "Top 100 MLB prospect rankings",
             "links": {"web": {"href": "https://espn.com/new"}}}]}
        real = scrapers._fetch
        scrapers._fetch = lambda url, key, force=False, accept_json=False: \
            scrapers.FetchResult(body=_json.dumps(payload), status=200,
                                 from_cache=True, url=url)
        with _StubbedWrites() as w:
            try:
                scrapers.probe_espn_new_prospect_article()
            finally:
                scrapers._fetch = real
        self.assertEqual(w.n_rows, 0)


if __name__ == "__main__":
    unittest.main()
