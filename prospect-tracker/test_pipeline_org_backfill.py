# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Verify the 2021-2024 MLB Pipeline org top-30 backfill landed."""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

DB = Path(__file__).parent / "prospects.db"


class PipelineOrgBackfill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DB.exists():
            raise unittest.SkipTest("no prospects.db")
        cls.con = sqlite3.connect(DB)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "con"):
            cls.con.close()

    def test_each_year_has_snapshots(self):
        for y in (2021, 2022, 2023, 2024, 2025, 2026):
            n = self.con.execute(
                "SELECT COUNT(*) FROM snapshots "
                "WHERE source='mlb_pipeline' AND interval_label LIKE ?",
                (f"%{y}%",),
            ).fetchone()[0]
            self.assertGreater(n, 50,
                f"year {y} has only {n} MLB Pipeline snapshots — expected ≥50")

    def test_total_org_year_combos(self):
        # 30 orgs × 6 years = 180 expected. Some org-years return 0
        # (selector-fragile pages); allow a couple of misses.
        n_labels = self.con.execute(
            "SELECT COUNT(DISTINCT interval_label) FROM snapshots "
            "WHERE source='mlb_pipeline' "
            "AND interval_label LIKE '%Top 30%'"
        ).fetchone()[0]
        self.assertGreater(n_labels, 150,
            f"only {n_labels} distinct org-year labels — backfill failed")


if __name__ == "__main__":
    unittest.main()
