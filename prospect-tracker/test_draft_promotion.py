# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for draft_promotion.py — the draft → MiLB bridge.

Focus areas:
  * Idempotency: running twice produces no change.
  * No empty / garbage keys.
  * Canonical-key mapping is consistent: same MiLB key for same name.
"""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from draft_promotion import (
    _better_draft_record,
    _milb_key_from_name,
    promote_drafted_players,
)

DB_PATH = Path(__file__).parent / "prospects.db"


class MilbKey(unittest.TestCase):
    def test_strips_accents(self):
        self.assertEqual(_milb_key_from_name("José Ramírez"),
                         _milb_key_from_name("Jose Ramirez"))

    def test_collapses_whitespace(self):
        self.assertEqual(_milb_key_from_name("JJ  Wetherholt"),
                         _milb_key_from_name("JJ Wetherholt"))


class PromotionIdempotency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DB_PATH.exists():
            raise unittest.SkipTest(
                f"no prospects.db at {DB_PATH} — run a backfill first"
            )

    def test_re_run_is_noop_for_links(self):
        """Re-running promote_drafted_players should produce 0 new links
        once a backfill has already populated them."""
        first = promote_drafted_players()
        second = promote_drafted_players()
        # `linked` counts only NEW canonical-key mappings; should be 0
        # on the second pass.
        self.assertEqual(second["linked"], 0,
                         f"expected 0 new links on re-run, got {second['linked']}")

    def test_all_promoted_have_acquisition_records(self):
        # contextlib.closing — sqlite3's own `with` doesn't close the
        # connection (it only manages the transaction). Closing leaks
        # otherwise surface as GC-time ResourceWarnings.
        from contextlib import closing
        with closing(sqlite3.connect(DB_PATH)) as con:
            con.row_factory = sqlite3.Row
            linked = con.execute(
                "SELECT milb_key FROM draft_canonical_keys"
            ).fetchall()
            if not linked:
                self.skipTest("no promotions on file yet")
            keys = [r["milb_key"] for r in linked]
            placeholders = ",".join("?" * len(keys))
            ac = con.execute(
                f"SELECT player_key FROM acquisitions "
                f"WHERE player_key IN ({placeholders}) AND method='draft'",
                keys,
            ).fetchall()
        # Allow ~5% miss rate for canonical-key name collisions (two
        # players normalizing to the same key — the second loses).
        coverage = len(ac) / max(1, len(keys))
        self.assertGreater(coverage, 0.90,
                           f"acquisitions coverage too low: {coverage:.1%}")


class MultiDraftCanonicalRecord(unittest.TestCase):
    """v29 — Players drafted multiple times (HS → didn't sign → re-
    drafted out of college) must resolve to the SIGNED draft as their
    canonical acquisition. Regression test for the Gage Jump case
    where the merge logic produced a frankenstein record (2024 bonus
    stitched onto 2021 team / round / year because field-merge blindly
    overwrote non-null fields). The fix: pick the SIGNED record; among
    same-signed, pick the newer year. Each draft is a distinct event,
    never field-merged."""

    def _rec(self, year, team, signed, bonus=None, round_label=None,
             pick_overall=None, school=None, draft_key=None):
        return {
            "method":       "draft",
            "year":         year,
            "round_label":  round_label,
            "pick_round":   None,
            "pick_overall": pick_overall,
            "bonus_usd":    bonus,
            "team_name":    team,
            "school":       school,
            "signing_date": None,
            "_signed":      bool(signed),
            "_draft_key":   draft_key or f"draft_{year}_test",
        }

    def test_signed_beats_unsigned_regardless_of_year(self):
        """Gage Jump shape — 2021 HS unsigned + 2024 college signed.
        The 2024 record must win even though 2021 came first."""
        unsigned_2021 = self._rec(2021, "SDP", signed=False,
                                  round_label="18", pick_overall=550,
                                  school="JSerra Catholic HS")
        signed_2024 = self._rec(2024, "ATH", signed=True, bonus=2_000_000,
                                round_label="CB-B", pick_overall=73,
                                school="LSU")

        # Both directions of the comparison: signed always wins.
        self.assertIs(_better_draft_record(signed_2024, unsigned_2021),
                      signed_2024)
        self.assertIs(_better_draft_record(unsigned_2021, signed_2024),
                      signed_2024)

    def test_signed_beats_unsigned_when_unsigned_is_newer(self):
        """Edge case: prospect was drafted, signed, then later
        re-drafted by a different team but didn't sign. The original
        signed pick should still be canonical."""
        signed_old = self._rec(2020, "BOS", signed=True, bonus=500_000)
        unsigned_new = self._rec(2024, "NYY", signed=False)
        self.assertIs(_better_draft_record(signed_old, unsigned_new),
                      signed_old)
        self.assertIs(_better_draft_record(unsigned_new, signed_old),
                      signed_old)

    def test_both_signed_is_a_collision_older_wins(self):
        """Both SIGNED can only be a NAME COLLISION between different
        people — a signed player is a pro and draft-ineligible forever.
        The incumbent (earlier) pro keeps the key. Regression for the
        Jake Bennett case: the 2022 WSN pick's acquisition was clobbered
        by 2026's TOR pick of a different Jake Bennett."""
        signed_2022 = self._rec(2022, "WSN", signed=True, bonus=1_734_800)
        signed_2026 = self._rec(2026, "TOR", signed=True, bonus=1_000)
        self.assertIs(_better_draft_record(signed_2022, signed_2026),
                      signed_2022)
        self.assertIs(_better_draft_record(signed_2026, signed_2022),
                      signed_2022)

    def test_newer_year_wins_among_unsigned(self):
        """Both unsigned (HS → college re-entry) → the most recent
        attempt is canonical."""
        unsigned_2021 = self._rec(2021, "BOS", signed=False)
        unsigned_2024 = self._rec(2024, "NYY", signed=False)
        self.assertIs(_better_draft_record(unsigned_2021, unsigned_2024),
                      unsigned_2024)

    def test_promote_picks_signed_in_real_db(self):
        """End-to-end check: after promote_drafted_players runs against
        the real prospects.db, every multi-draft prospect with at
        least one SIGNED entry should have its canonical acquisitions
        row pointing at the signed draft (year, team, bonus all match
        the signed record — NOT a merged frankenstein)."""
        if not DB_PATH.exists():
            self.skipTest("no prospects.db on file")
        from contextlib import closing
        from collections import defaultdict
        promote_drafted_players()
        with closing(sqlite3.connect(DB_PATH)) as con:
            con.row_factory = sqlite3.Row
            drafts = con.execute(
                "SELECT player_key, player_name, draft_year, team, signed, bonus_usd "
                "FROM draft_results"
            ).fetchall()
            by_milb: dict[str, list] = defaultdict(list)
            for r in drafts:
                by_milb[_milb_key_from_name(r["player_name"])].append(dict(r))
            multi_signed = [(mk, recs) for mk, recs in by_milb.items()
                            if len(recs) > 1 and any(r["signed"] for r in recs)]
            if not multi_signed:
                self.skipTest("no multi-draft prospects with a signed entry yet")
            ac_rows = con.execute(
                "SELECT player_key, year, team_name, bonus_usd FROM acquisitions"
            ).fetchall()
            ac_by_key = {r["player_key"]: dict(r) for r in ac_rows}

        mismatches = []
        for mk, recs in multi_signed:
            ac = ac_by_key.get(mk)
            if not ac:
                continue  # never linked — covered by other test
            signed_recs = [r for r in recs if r["signed"]]
            # Canonical = signed; multiple signed = name collision, the
            # incumbent (OLDEST) pro keeps the key.
            canonical = min(signed_recs, key=lambda r: r["draft_year"] or 0)
            ok = (ac["year"] == canonical["draft_year"]
                  and (ac["team_name"] or "").upper() == (canonical["team"] or "").upper())
            if not ok:
                mismatches.append((mk, canonical, ac))
        # Allow a tiny tolerance for canonical-key collisions, but the
        # bulk of multi-signed prospects should match.
        miss_rate = len(mismatches) / max(1, len(multi_signed))
        self.assertLess(miss_rate, 0.05,
                        f"multi-draft canonical mismatch rate {miss_rate:.1%}; "
                        f"sample: {mismatches[:3]}")


class SeedSignedDraftees(unittest.TestCase):
    """seed_signed_draftees — signed current-class picks surface on the
    MiLB board via a synthetic 'draft_signing' snapshot; everyone else
    is guarded out."""

    @classmethod
    def setUpClass(cls):
        if not DB_PATH.exists():
            raise unittest.SkipTest(f"no prospects.db at {DB_PATH}")

    def test_idempotent_and_current_class_only(self):
        from draft_promotion import seed_signed_draftees
        from contextlib import closing
        from datetime import date
        first = seed_signed_draftees()
        second = seed_signed_draftees()
        # UNIQUE(source, interval_label, player_key) upsert — the re-run
        # rewrites the same rows, never grows the table.
        with closing(sqlite3.connect(DB_PATH)) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT player_key, org, fv, interval_label, snapshot_date "
                "FROM snapshots WHERE source='draft_signing'"
            ).fetchall()
        self.assertEqual(first, second)
        # The seed count is the rows re-stamped by THIS run, not the size of the
        # table.
        #
        # CORRECTED 2026-07-25. This asserted len(rows) == first, which only holds
        # if the eligible set never shrinks. It does shrink, by design: a signed
        # draftee is seeded with a synthetic anchor only until a real outlet grades
        # him, after which the guard in seed_signed_draftees stops re-seeding him
        # and his old row stays behind at its old stamp. Measured on the live DB
        # 2026-07-25: 128 rows, 49 re-stamped today and 79 left at 2026-07-23 — and
        # ALL 79 of those players now carry a real graded source, so every stale row
        # is outvoted and not one player is stranded on a synthetic anchor. The
        # invariant was wrong, the data was right.
        newest = max(r["snapshot_date"] for r in rows)
        self.assertEqual(sum(1 for r in rows if r["snapshot_date"] == newest), first,
                         "the newest stamp must hold exactly this run's seeds")
        this_year = str(date.today().year)
        for r in rows:
            # Only the current class is ever seeded.
            self.assertTrue(r["interval_label"].startswith(this_year),
                            f"stale-class seed: {dict(r)}")
            # Every seed carries an org and a real board grade.
            self.assertTrue(r["org"], f"org-less seed: {dict(r)}")
            self.assertIsNotNone(r["fv"], f"grade-less seed: {dict(r)}")

        # THE INVARIANT THAT ACTUALLY MATTERS, and which the old size assertion
        # was standing in for badly: a row left behind at an older stamp is
        # harmless ONLY while a real outlet now grades that player. If a stale
        # synthetic row is somebody's ONLY anchor, he is serving a manufactured
        # grade with nothing behind it, which is a real defect rather than
        # bookkeeping.
        stale = [r["player_key"] for r in rows if r["snapshot_date"] != newest]
        if stale:
            with closing(sqlite3.connect(DB_PATH)) as con:
                qs = ",".join("?" * len(stale))
                graded = {x[0] for x in con.execute(
                    f"SELECT DISTINCT player_key FROM snapshots "
                    f"WHERE player_key IN ({qs}) AND fv IS NOT NULL "
                    "AND source NOT IN ('draft_signing','performance_ingest',"
                    "'auto_detect')", stale)}
            orphans = sorted(set(stale) - graded)
            self.assertEqual(orphans, [],
                             f"stale synthetic seed is the ONLY anchor for: {orphans[:5]}")

    def test_never_seeds_an_already_tracked_identity(self):
        """A milb_key with ANY real MiLB snapshot (graduated pro, org-
        source-covered prospect, or name-collided incumbent like the
        WSN Jake Bennett) must never receive a seed."""
        from contextlib import closing
        with closing(sqlite3.connect(DB_PATH)) as con:
            con.row_factory = sqlite3.Row
            bad = con.execute(
                """SELECT s.player_key, COUNT(*) n FROM snapshots s
                   WHERE s.source='draft_signing'
                     AND EXISTS (
                       SELECT 1 FROM snapshots o
                       WHERE o.player_key = s.player_key
                         AND o.source != 'draft_signing'
                         AND o.interval_label NOT GLOB '20[0-9][0-9]draft'
                         AND o.snapshot_date < s.snapshot_date)
                   GROUP BY s.player_key LIMIT 5"""
            ).fetchall()
        self.assertFalse([dict(r) for r in bad],
                         "seed landed on an already-tracked identity")


if __name__ == "__main__":
    unittest.main()
