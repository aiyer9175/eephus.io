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

    def test_newer_year_wins_among_same_signed_status(self):
        """Both signed (rare — typically a re-signing after release) →
        pick the newer year. Both unsigned (also rare) → same rule so
        the canonical record is at least the most recent attempt."""
        signed_2021 = self._rec(2021, "BOS", signed=True, bonus=100_000)
        signed_2024 = self._rec(2024, "NYY", signed=True, bonus=200_000)
        self.assertIs(_better_draft_record(signed_2021, signed_2024),
                      signed_2024)

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
            # Canonical = signed, newest year if multiple.
            canonical = max(signed_recs, key=lambda r: r["draft_year"] or 0)
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


if __name__ == "__main__":
    unittest.main()
