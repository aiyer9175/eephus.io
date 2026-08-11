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
        # The seed count is the CURRENTLY ELIGIBLE set: signed current-class
        # picks whose identity no real outlet has taken over yet.
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
        #
        # CORRECTED AGAIN 2026-08-09, and this time the DATE PROXY itself is what
        # broke. The 2026-07-25 rewrite still identified "this run's seeds" as
        # "the rows carrying the newest snapshot_date", which assumes the eligible
        # set can only shrink ACROSS days. It shrank WITHIN one. Measured: an
        # earlier run today re-stamped 59 rows to 2026-08-09; the Baseball America
        # 2026 midseason drop then landed (897 rows, as-of 2026-08-01, INSERTED
        # 2026-08-10 00:20Z) and graded 20 of those 59, so the guard now blocks
        # them and the run seeds 39. All 20 blockers are BA rows and nothing else.
        # The 20 keep the 2026-08-09 stamp because they really were written today,
        # so "newest stamp" holds 59 while the run returns 39. The count did not
        # rise; it FELL, from 59 to 39, exactly as a new real outlet should make
        # it fall. Only the frozen row count rose.
        #
        # So stop inferring the run's seed set from a date and state the property
        # directly: the run seeds exactly the draft_signing identities that no
        # real outlet owns. Measured on the live DB 2026-08-09 after the Natili
        # repair: 137 rows, 38 eligible (= the returned count), 99 already tracked,
        # 0 of the 99 without a real graded source.
        from consensus import PLAYER_KEY_ALIASES
        _SYN = "('draft_signing', 'performance_ingest', 'auto_detect')"

        def _canon(k):
            return (PLAYER_KEY_ALIASES.get(k) or {}).get("player_key") or k

        with closing(sqlite3.connect(DB_PATH)) as con:
            def _tracked(k):
                return con.execute(
                    f"SELECT 1 FROM snapshots WHERE player_key=? "
                    f"AND source NOT IN {_SYN} "
                    "AND interval_label NOT GLOB '20[0-9][0-9]draft' LIMIT 1",
                    (_canon(k),)).fetchone() is not None

            def _graded(k):
                return con.execute(
                    f"SELECT 1 FROM snapshots WHERE player_key=? AND fv IS NOT NULL "
                    f"AND source NOT IN {_SYN} LIMIT 1",
                    (_canon(k),)).fetchone() is not None

            tracked = {r["player_key"] for r in rows if _tracked(r["player_key"])}
            eligible = sorted({r["player_key"] for r in rows} - tracked)
            # Every row this run did NOT re-stamp is harmless ONLY while a real
            # outlet grades that player. A synthetic row that is somebody's ONLY
            # anchor is a manufactured grade with nothing behind it.
            orphans = sorted(k for k in tracked if not _graded(k))

        self.assertEqual(len(eligible), first,
                         "the run must seed exactly the identities no real outlet "
                         f"owns; eligible={len(eligible)} returned={first} "
                         f"sample={eligible[:5]}")
        self.assertEqual(orphans, [],
                         f"synthetic seed is the ONLY anchor for: {orphans[:5]}")
        this_year = str(date.today().year)
        for r in rows:
            # Only the current class is ever seeded.
            self.assertTrue(r["interval_label"].startswith(this_year),
                            f"stale-class seed: {dict(r)}")
            # Every seed carries an org and a real board grade.
            self.assertTrue(r["org"], f"org-less seed: {dict(r)}")
            self.assertIsNotNone(r["fv"], f"grade-less seed: {dict(r)}")

    def test_never_seeds_an_already_tracked_identity(self):
        """A milb_key with ANY real MiLB snapshot (graduated pro, org-
        source-covered prospect, or name-collided incumbent like the
        WSN Jake Bennett) must never receive a seed.

        ORDERED ON inserted_at, NOT snapshot_date. CORRECTED 2026-08-09: this
        used `o.snapshot_date < s.snapshot_date`, which reads the board's AS-OF
        date as if it were the ingest clock. It is not. The Baseball America
        2026 midseason drop published as of 2026-08-01 and was ingested on
        2026-08-09, so its rows landed BEHIND 20 seeds that had been written
        earlier the same day, and a guard that had never been violated read as
        20 violations. The seeds were correct; they simply predated the outlet.
        `inserted_at` is the real write time and is never touched by the
        insert_snapshots upsert (verified: rows re-stamped to 2026-08-09 still
        carry their original 2026-07-15..2026-07-27 inserted_at), so it is the
        only column here that orders cause before effect. Measured on the live
        DB 2026-08-09: 20 violations by snapshot_date, 0 by inserted_at.

        SECOND CHECK, added the same day. The query above can only see a
        collision that shares a player_key, so it was blind to the collision
        class this repo has actually been burned by: one human under two
        SPELLINGS. `jack_natili` carried a synthetic FV 45 seed while every
        real grade for the same human sat on `jackson_natili` (FanGraphs 45,
        Baseball America 40). That is the identity that once reached the served
        board twice at ranks 155 and 320 with his surplus double counted. So
        the seed set is also checked against consensus.PLAYER_KEY_ALIASES: no
        seed may sit on a spelling the alias table demotes, and the canonical
        spelling must be untracked too.
        """
        from contextlib import closing
        from consensus import PLAYER_KEY_ALIASES
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
                         AND o.inserted_at < s.inserted_at)
                   GROUP BY s.player_key LIMIT 5"""
            ).fetchall()
            self.assertFalse([dict(r) for r in bad],
                             "seed landed on an already-tracked identity")

            seeded = con.execute(
                "SELECT player_key, inserted_at FROM snapshots "
                "WHERE source='draft_signing'").fetchall()
            demoted = sorted({r["player_key"] for r in seeded
                              if r["player_key"] in PLAYER_KEY_ALIASES})
            self.assertEqual(demoted, [],
                             "seed sits on a spelling the alias table demotes; "
                             f"these are one human counted twice: {demoted[:5]}")
            # The same "already tracked when we wrote it" test as above, but
            # asked about the CANONICAL spelling, which is the one the board
            # serves. A no-op while `demoted` is empty; it is the check that
            # would have caught the Natili seed the day it was written.
            split = sorted({
                r["player_key"] for r in seeded
                if con.execute(
                    "SELECT 1 FROM snapshots WHERE player_key=? "
                    "AND source NOT IN ('draft_signing','performance_ingest',"
                    "'auto_detect') "
                    "AND interval_label NOT GLOB '20[0-9][0-9]draft' "
                    "AND inserted_at < ? LIMIT 1",
                    ((PLAYER_KEY_ALIASES.get(r["player_key"]) or {}).get("player_key")
                     or r["player_key"], r["inserted_at"])
                ).fetchone()})
        self.assertEqual(split, [],
                         "a real outlet already graded the canonical form of "
                         f"these keys when the seed was written: {split[:5]}")


if __name__ == "__main__":
    unittest.main()
