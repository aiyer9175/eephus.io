# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Verify the multi-cycle scout_reports sidecar shape (per-source list,
deduped by SHA1 hash, newest-first)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


SR_PATH = Path(__file__).parent / "data" / "scout_reports.json"


class ScoutReportHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SR_PATH.exists():
            raise unittest.SkipTest("scout_reports.json missing — run rebuild_only first")
        cls.sidecar = json.loads(SR_PATH.read_text(encoding="utf-8"))

    @staticmethod
    def _sources(by_src):
        """(src, entries) for real per-source report lists, SKIPPING reserved
        underscore-prefixed metadata keys. The builder rides `_ids` (the
        source-id alias map the frontend reads as sidecar._ids) alongside the
        report lists as a reserved sub-key — see storage.py — so it is metadata,
        not a report list."""
        return [(s, e) for s, e in by_src.items() if not s.startswith("_")]

    def test_entries_are_lists(self):
        """Every per-source entry must be a list (not the legacy dict shape)."""
        for pkey, by_src in self.sidecar.items():
            for src, entries in self._sources(by_src):
                self.assertIsInstance(entries, list,
                    f"{pkey}/{src} should be a list, got {type(entries).__name__}")

    def test_entries_newest_first(self):
        for pkey, by_src in self.sidecar.items():
            for src, entries in self._sources(by_src):
                if len(entries) < 2:
                    continue
                dates = [e.get("date") for e in entries]
                self.assertEqual(dates, sorted(dates, reverse=True),
                    f"{pkey}/{src} not newest-first: {dates}")

    def test_no_duplicate_hashes_within_source(self):
        """Dedup invariant: no two cycles for the same source should
        carry the same SHA1 hash (i.e. identical text)."""
        for pkey, by_src in self.sidecar.items():
            for src, entries in self._sources(by_src):
                hashes = [e.get("hash") for e in entries if e.get("hash")]
                self.assertEqual(len(hashes), len(set(hashes)),
                    f"{pkey}/{src} has duplicate hashes — dedup broken")

    def test_at_least_some_prospects_have_multi_cycle(self):
        """Sanity: across the whole sidecar at least 100 prospects should
        carry ≥2 cycles for ≥1 source (FG re-ships writeups across cycles)."""
        n_multi = sum(1 for pkey, by_src in self.sidecar.items()
                      if any(isinstance(es, list) and len(es) >= 2 for es in by_src.values()))
        self.assertGreater(n_multi, 100,
                           f"only {n_multi} prospects with multi-cycle history — too few")


if __name__ == "__main__":
    unittest.main()
