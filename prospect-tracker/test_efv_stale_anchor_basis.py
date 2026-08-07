# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""E-STALE date basis: a fresh CONSTANT stamp must not read as a fresh grade.

THE DEFECT (Lane C2, 2026-08-05). `_stale_anchor_discount` was handed the
consensus POINT date. build_timeseries forward-fills every source into a point at
every event date, so the point date is the newest date ANY row touched the
player, including rows that carry no scouting opinion.
mlbam_ingest.refresh_performance_anchors re-stamps the fabricated FV 35 daily for
every auto-tracked player who still qualifies, so a player whose real published
grade froze 18+ months ago read as "graded today" and took a 0.00 discount. The
per-source date that consensus already records (consensus.compute_consensus_point,
`per_source[src]["snapshot_date"]`) is the honest read and is never rebased by
forward-fill.

WHAT THIS FILE PINS
  1. `_anchor_asof_date` follows compute_consensus_point's OWN precedence for
     where the anchor came from: real published FV, then the folded-back constant,
     then rank-implied. The tiering is not cosmetic. Taking "newest non-constant
     FV date, full stop" DISARMS the ramp for the 2,691 active rows whose only FV
     row IS the constant (measured 2026-08-05: -182 decayed rows at +12 months and
     -2,691 at +24 months on a frozen board), and that cohort is exactly the one
     refresh_performance_anchors intends to decay when the stamp stops being
     re-asserted.
  2. The headline regression: a player whose only fresh row is a constant stamp
     over an 18+ month old real grade takes a NONZERO discount under the source
     basis and 0.00 under the shipped point basis.
  3. The basis switch defaults to the SHIPPED behavior. This is basis-adjacent
     (fv_effective is the model's dominant feature), so it does not flip itself.
  4. `asof_date` is the DECISION-POINT date and never moves. The labs read it as
     the decision vintage (tools/fv_outcome_curves_lab.py,
     tools/efv_gradenorm_basis_lab.py) and training rows carry the same field.

Pure unit tests over the helpers plus one source-level wiring pin. No DB, no
network, no matrix build.
"""
from __future__ import annotations

import pytest

# IMPLEMENTED 2026-08-06. The spec below was landed skipped on 2026-08-05 with
# the code unwritten; efv_dataset._anchor_asof_date and _constant_anchor_sources
# now exist and these assertions run.
#
# FLIPPED TO "source" 2026-08-07 (owner decision 3, omnibus-3 Lane B3), and the
# pin below moved with it in the same commit, which is the whole point of pinning
# a default: a flip cannot be silent.
#
# THE MOVER TABLE THE FLIP OWED REFUTED THE PREMISE ABOVE, and the docstring's
# numbers are left standing with this correction beneath them rather than quietly
# edited, because the discrepancy is the finding. Paragraph 1 of "WHAT THIS FILE
# PINS" quotes -182 decayed rows at +12 months and -2,691 at +24 as the cost of
# the naive fix, which is a real property of the TIERING. The flip's own effect is
# a different quantity and it is approximately zero: measured on the 2026-08-06
# board (4,586 active rows, tools/efv_stale_anchor_mover_table.py), point and
# source decay the SAME 279 rows today, the same 701 at +12 months, the same 4,473
# at +24, and the two bases disagree on 16 rows with a maximum delta of 0.11 FV.
#
# The reason is mlbam_ingest.refresh_performance_anchors, which stamps only
# `_synthetic_only_keys()` and states in its own docstring that it "never touches a
# player who has a real published anchor". The headline defect this file describes
# is therefore already scoped out at the ingest, and the class it was built for is
# 13 rows whose real grade is ONE DAY older than the point date. The flip ships as
# a correctness change made while it is free, not as a measured improvement, and
# the tests below still pin the BEHAVIOUR because that is what has to keep holding
# if a future ingest stops being careful.


import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_dataset as ed          # noqa: E402
from consensus import CONSTANT_ANCHOR_SOURCES   # noqa: E402

TODAY = date(2026, 8, 5)
FROZEN = "2024-12-05"     # ~20.0 months before TODAY: onto the 18mo ramp, not terminal
ANCIENT = "2024-01-22"    # ~30.6 months: past the 30mo ramp end, full terminal


def _pt(per_source):
    return {"snapshot_date": max(
        (e.get("snapshot_date") or "") for e in per_source.values()),
        "per_source": per_source}


def _src(date_str, fv=None, rank=None):
    return {"fv_published": fv, "rank": rank, "snapshot_date": date_str,
            "dropped_off": False, "interval_label": "x", "status": "active"}


class TestAnchorAsofDate(unittest.TestCase):

    def test_constant_stamp_does_not_refresh_a_frozen_real_grade(self):
        """The headline case. A daily performance_ingest stamp sits on top of a
        Pipeline grade frozen 18+ months ago; the anchor date is the GRADE's."""
        per = {"mlb_pipeline": _src(FROZEN, fv=40.0, rank=30),
               "performance_ingest": _src("2026-08-04", fv=35.0)}
        self.assertEqual(ed._anchor_asof_date(_pt(per)), FROZEN)

    def test_synthetic_only_player_keeps_the_constant_date(self):
        """The cohort the naive fix would break. With NO real grade the constant
        IS the anchor (consensus folds it back as a last resort), so its own date
        is the honest one and the ramp still fires once re-stamping stops."""
        per = {"performance_ingest": _src(ANCIENT, fv=35.0)}
        self.assertEqual(ed._anchor_asof_date(_pt(per)), ANCIENT)

    def test_rank_only_source_is_the_last_tier(self):
        """A rank-bearing row with no FV feeds the rank-implied fallback, so it
        dates the anchor when nothing published an FV at all."""
        per = {"baseballamerica": _src("2026-06-03", rank=44)}
        self.assertEqual(ed._anchor_asof_date(_pt(per)), "2026-06-03")

    def test_real_fv_outranks_a_newer_rank_only_row(self):
        per = {"mlb_pipeline": _src(FROZEN, fv=40.0),
               "baseballamerica": _src("2026-08-01", rank=12)}
        self.assertEqual(ed._anchor_asof_date(_pt(per)), FROZEN)

    def test_newest_of_several_real_grades_wins(self):
        per = {"mlb_pipeline": _src(ANCIENT, fv=40.0),
               "fangraphs": _src(FROZEN, fv=45.0)}
        self.assertEqual(ed._anchor_asof_date(_pt(per)), FROZEN)

    def test_same_date_extras_are_walked(self):
        """v10 packs a same-day second publication into `extras`. It must not be
        able to hide the newest date if that packing ever changes."""
        primary = _src(ANCIENT, fv=40.0)
        primary["extras"] = [_src(FROZEN, fv=40.0)]
        self.assertEqual(ed._anchor_asof_date(_pt({"mlb_pipeline": primary})), FROZEN)

    def test_no_dated_entry_returns_none_so_the_caller_can_fall_back(self):
        self.assertIsNone(ed._anchor_asof_date({"per_source": {}}))
        self.assertIsNone(ed._anchor_asof_date(
            {"per_source": {"mlb_pipeline": _src(None, fv=40.0)}}))

    def test_constant_source_set_is_read_from_consensus_not_copied(self):
        self.assertEqual(ed._constant_anchor_sources(),
                         frozenset(CONSTANT_ANCHOR_SOURCES))


class TestDiscountUnderEachBasis(unittest.TestCase):
    """THE REGRESSION THIS LANE OWES: a player whose only fresh row is a constant
    stamp must still receive a nonzero staleness discount."""

    PER = {"mlb_pipeline": _src(FROZEN, fv=40.0, rank=30),
           "performance_ingest": _src("2026-08-04", fv=35.0)}

    def test_point_basis_shows_no_decay(self):
        pt = _pt(self.PER)
        self.assertEqual(pt["snapshot_date"], "2026-08-04")
        self.assertEqual(
            ed._stale_anchor_discount(pt["snapshot_date"], 40.0, today=TODAY), 0.0)

    def test_source_basis_shows_real_decay(self):
        disc = ed._stale_anchor_discount(
            ed._anchor_asof_date(_pt(self.PER)), 40.0, today=TODAY)
        self.assertGreater(disc, 0.0)
        # 20 months in: onto the 18 -> 30 month ramp, nowhere near terminal
        self.assertLess(disc, ed.STALE_ANCHOR_TERMINAL[40])

    def test_source_basis_reaches_terminal_on_an_ancient_grade(self):
        per = {"mlb_pipeline": _src(ANCIENT, fv=40.0),
               "performance_ingest": _src("2026-08-04", fv=35.0)}
        self.assertEqual(
            ed._stale_anchor_discount(ed._anchor_asof_date(_pt(per)), 40.0, today=TODAY),
            ed.STALE_ANCHOR_TERMINAL[40])

    def test_fresh_real_grade_still_decays_on_neither_basis(self):
        per = {"fangraphs": _src("2026-07-23", fv=45.0),
               "performance_ingest": _src("2026-08-04", fv=35.0)}
        pt = _pt(per)
        for d in (pt["snapshot_date"], ed._anchor_asof_date(pt)):
            self.assertEqual(ed._stale_anchor_discount(d, 45.0, today=TODAY), 0.0)


class TestBasisSwitchAndWiring(unittest.TestCase):

    def test_switch_pins_the_shipped_basis(self):
        """Basis-adjacent: fv_effective is the model's dominant feature, so this
        constant does not move without an owner decision, a mover table and a
        fingerprint bump. Flipped point -> source on 2026-08-07 (owner decision 3);
        the mover table it was blocked on is
        docs/efv-2026-08-07/STALE_ANCHOR_MOVER_TABLE.json and it measured 0 movers
        at +0 and +12 months, 16 at +24.

        If this fails you changed the basis. Rebuild the mover table, restamp
        storage.BOARD_BASIS_FINGERPRINT's stale= term, and decide the epoch
        question (it was deliberately NOT bumped for this flip: zero movers means
        there is no re-rank to hide from the movement engine)."""
        self.assertEqual(ed.STALE_ANCHOR_DATE_BASIS, "source")

    def test_the_fingerprint_names_this_basis(self):
        """The gap this flip closed. STALE_ANCHOR_DATE_BASIS has decided
        fv_effective since 2026-07-14 and the board fingerprint never named it, so
        a flip could not trip the coordination check at all. A fingerprint only
        guards what it names."""
        import storage
        self.assertIn(f"stale={ed.STALE_ANCHOR_DATE_BASIS}",
                      storage.board_basis_fingerprint())
        self.assertIn("stale=", storage.BOARD_BASIS_FINGERPRINT)

    def test_constant_only_predicate_matches_the_roster_stamp_rule(self):
        """run_monthly stamps fv_synthetic_only as
        `bool(srcs) and srcs <= CONSTANT_ANCHOR_SOURCES`. The live matrix derives
        the same thing off the point so the scorer does not inherit the site
        export's file ordering. The EMPTY set must read False: "no sources at all"
        is not "only constant sources"."""
        self.assertTrue(ed._anchor_is_constant_only(
            {"sources_contributing": ["performance_ingest"]}))
        self.assertTrue(ed._anchor_is_constant_only(
            {"sources_contributing": list(CONSTANT_ANCHOR_SOURCES)}))
        self.assertFalse(ed._anchor_is_constant_only(
            {"sources_contributing": ["performance_ingest", "fangraphs"]}))
        self.assertFalse(ed._anchor_is_constant_only({"sources_contributing": []}))
        self.assertFalse(ed._anchor_is_constant_only({}))

    def test_live_path_stamps_the_constant_only_flag(self):
        src = (ROOT / "efv_dataset.py").read_text(encoding="utf-8")
        self.assertIn('row["anchor_constant_only"] = _anchor_is_constant_only(pt)', src)

    def test_live_path_reads_the_switch_and_falls_back_to_the_point_date(self):
        src = (ROOT / "efv_dataset.py").read_text(encoding="utf-8")
        self.assertIn('if STALE_ANCHOR_DATE_BASIS == "source":', src)
        self.assertIn("_anchor_asof = _anchor_asof_date(pt) or _anchor_asof", src)
        self.assertIn("_disc = _stale_anchor_discount(_anchor_asof, "
                      'row.get("consensus_fv_raw"))', src)

    def test_decision_point_date_is_not_rebased(self):
        """asof_date is the decision vintage the labs read; only the staleness
        read gets the new field."""
        src = (ROOT / "efv_dataset.py").read_text(encoding="utf-8")
        self.assertIn('"asof_date": pt.get("snapshot_date"),', src)
        self.assertIn('row["anchor_asof_date"] = _anchor_asof', src)

    def test_training_path_is_untouched(self):
        """build_matrix rows carry no anchor_asof_date and no fv_effective: a
        training row's decision point IS its last listing event."""
        src = (ROOT / "efv_dataset.py").read_text(encoding="utf-8")
        head, _, live = src.partition("def build_live_matrix")
        self.assertNotIn("anchor_stale_discount", head)
        self.assertNotIn('row["anchor_asof_date"]', head)
        self.assertIn("anchor_stale_discount", live)


if __name__ == "__main__":
    unittest.main()
