# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the draft polish: sequential consensus_pick + integer FV
+ lottery odds plumbing."""

from __future__ import annotations

import unittest

from draft_export import (
    _projected_round, build_draft_export, _consensus, _consensus_rank,
    _edit_distance_le1, _same_person, _name_part, _dedupe_merge_map,
    _name_first_last, _canon_player_type,
)


class PlayerTypeCanon(unittest.TestCase):
    """player_type canonicalization: casing folds, JuCo -> COL, untyped rows
    (2Way / null) get pool+side backfilled from school + position."""

    def test_casing_folds(self):
        self.assertEqual(_canon_player_type("ColH"), "COLh")
        self.assertEqual(_canon_player_type("Colp"), "COLp")
        self.assertEqual(_canon_player_type("HsP"), "HSp")
        self.assertEqual(_canon_player_type("COLh"), "COLh")   # already canonical

    def test_juco_maps_to_college(self):
        self.assertEqual(_canon_player_type("JCp"), "COLp")
        self.assertEqual(_canon_player_type("JCh"), "COLh")

    def test_backfills_null_from_school_and_position(self):
        self.assertEqual(_canon_player_type(None, "Independence HS TN", "CF"), "HSh")
        self.assertEqual(_canon_player_type(None, "Watson Chapel HS AR", "RHP"), "HSp")
        self.assertEqual(_canon_player_type(None, "Duke", "C"), "COLh")
        self.assertEqual(_canon_player_type(None, "Oklahoma State", "LHP"), "COLp")

    def test_two_way_gets_bucketed(self):
        # 2Way previously vanished under any pool/side filter; now it lands
        # somewhere sane rather than dropping out entirely.
        self.assertEqual(_canon_player_type("2Way", "Tennessee", "OF/RHP"), "COLh")

    def test_unresolvable_left_alone(self):
        self.assertIsNone(_canon_player_type(None, None, None))
        self.assertEqual(_canon_player_type("2Way", None, None), "2Way")


class ProjectedRound(unittest.TestCase):
    def test_round_buckets(self):
        self.assertEqual(_projected_round(1), 1)
        self.assertEqual(_projected_round(30), 1)
        self.assertEqual(_projected_round(31), 2)
        self.assertEqual(_projected_round(60), 2)
        self.assertEqual(_projected_round(150), 5)

    def test_none_safe(self):
        self.assertIsNone(_projected_round(None))
        self.assertIsNone(_projected_round(0))


class SequentialRanking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.export = build_draft_export()

    def test_picks_are_sequential_no_dupes(self):
        for klass in self.export["classes"]:
            ranked = [p for p in klass["prospects"]
                      if p.get("consensus_pick") is not None]
            if not ranked:
                continue
            picks = sorted(p["consensus_pick"] for p in ranked)
            self.assertEqual(picks, list(range(1, len(ranked) + 1)),
                             f"class {klass['year']} has non-sequential picks")
            self.assertEqual(len(picks), len(set(picks)),
                             f"class {klass['year']} has duplicate picks")

    def test_picks_track_consensus_rank_order(self):
        """Lower averaged rank → lower pick number."""
        for klass in self.export["classes"]:
            ranked = sorted(
                (p for p in klass["prospects"] if p.get("consensus_pick") is not None),
                key=lambda p: p["consensus_pick"]
            )
            for prev, cur in zip(ranked, ranked[1:]):
                self.assertLessEqual(
                    prev["consensus_rank"], cur["consensus_rank"] + 1e-6,
                    f"pick {prev['consensus_pick']} has higher raw rank "
                    f"than pick {cur['consensus_pick']} in {klass['year']}"
                )


    def test_ba_global_rank_survives_a_later_scope_board(self):
        """M03-01 artifact invariant: every prospect BA ranked on its global
        Top 100 keeps a whole-class rank, even when a later BA scope board
        (HS Top 150, College Top 100) also lists him."""
        for klass in self.export["classes"]:
            for p in klass["prospects"]:
                has_global = any(
                    pt.get("source") == "baseballamerica_draft"
                    and pt.get("rank") is not None
                    and ((pt.get("tools") or {}).get("_extras") or {}).get("ba_rank_is_global") is True
                    for pt in p.get("points") or [])
                if has_global:
                    self.assertIsNotNone(
                        p.get("consensus_rank"),
                        f"{klass['year']} {p['player_name']} lost its BA global rank")


class ScopeBoardRankVote(unittest.TestCase):
    """M03-01: a scoped BA board carries no whole-class rank, so it must not
    stand as BA's latest snapshot in the rank vote."""

    @staticmethod
    def _ba(date, rank, is_global, label):
        return {"source": "baseballamerica_draft", "snapshot_date": date,
                "interval_label": label, "rank": rank, "fv": None,
                "tools": {"_extras": {"ba_rank_is_global": is_global,
                                      "ba_scope_rank": 1}}}

    def test_global_rank_kept_after_later_scope_snapshot(self):
        snaps = [self._ba("2026-07-15", 1, True, "Top 100"),
                 self._ba("2026-07-17", None, False, "HS Top 150")]
        self.assertEqual(_consensus_rank(snaps), 1.0)
        # The plain latest-per-source vote is what dropped it.
        self.assertIsNone(_consensus(snaps, "rank"))

    def test_scope_board_alone_is_unranked(self):
        snaps = [self._ba("2026-07-17", None, False, "HS Top 100")]
        self.assertIsNone(_consensus_rank(snaps))

    def test_other_sources_later_null_rank_still_ends_its_vote(self):
        """Only scope boards step aside. A FanGraphs board that no longer
        ranks the player still ends FG's vote (2026 stays byte-identical)."""
        snaps = [
            {"source": "fangraphs", "snapshot_date": "2026-05-22", "rank": 22, "tools": {}},
            {"source": "fangraphs", "snapshot_date": "2026-07-15", "rank": None, "tools": {}},
            {"source": "mlb_pipeline_draft", "snapshot_date": "2026-07-01", "rank": 140, "tools": None},
        ]
        self.assertEqual(_consensus_rank(snaps), 140.0)


class IntegerFV(unittest.TestCase):
    def test_consensus_fv_is_integer(self):
        export = build_draft_export()
        for klass in export["classes"]:
            for p in klass["prospects"]:
                fv = p.get("consensus_fv")
                if fv is None:
                    continue
                self.assertIsInstance(fv, int, f"{p['player_name']} FV is not int")

    def test_consensus_fv_raw_preserved(self):
        """The raw average stays alongside for tooltips."""
        export = build_draft_export()
        for klass in export["classes"]:
            for p in klass["prospects"]:
                if p.get("consensus_fv") is None:
                    continue
                self.assertIn("consensus_fv_raw", p,
                              f"{p['player_name']} missing consensus_fv_raw")


class LotteryPlumbing(unittest.TestCase):
    def test_lottery_odds_field_present(self):
        export = build_draft_export()
        for klass in export["classes"]:
            self.assertIn("lottery_odds", klass)
            self.assertIsInstance(klass["lottery_odds"], list)

    def test_lottery_odds_sorted_by_pick_pos(self):
        # Post-v4 the lottery_odds field carries the full projected
        # first round + comp picks, sorted by pick_pos ascending so
        # the consumer renders the natural draft order. Picks 7+ have
        # odds_pct=None (deterministic slots).
        export = build_draft_export()
        for klass in export["classes"]:
            odds = klass["lottery_odds"]
            if len(odds) < 2:
                continue
            positions = [o["pick_pos"] for o in odds]
            self.assertEqual(positions, sorted(positions),
                             f"lottery odds for {klass['year']} not sorted by pick_pos")


class WeightedConsensus(unittest.TestCase):
    """The FV consensus is an accuracy-weighted mean when the draft backtest
    ships weights (data/draft_source_weights.json); equal otherwise."""

    def _snaps(self):
        return [
            {"source": "fangraphs", "snapshot_date": "2026-05-22", "fv": 55.0},
            {"source": "mlb_pipeline_draft", "snapshot_date": "2026-06-18", "fv": 65.0},
        ]

    def test_equal_when_no_weights(self):
        # No weights / empty weights -> plain mean (60.0).
        self.assertEqual(_consensus(self._snaps(), "fv"), 60.0)
        self.assertEqual(_consensus(self._snaps(), "fv", weights={}), 60.0)

    def test_weighted_mean_pulls_toward_higher_weight(self):
        # Up-weighting MLB Pipeline pulls the blend toward its 65.
        w = {"mlb_pipeline_draft": 1.5, "fangraphs": 0.6}
        got = _consensus(self._snaps(), "fv", weights=w)
        self.assertAlmostEqual(got, (1.5 * 65 + 0.6 * 55) / (1.5 + 0.6), places=2)

    def test_absent_source_votes_one(self):
        # A source missing from the weights map votes at 1.0 (not dropped).
        w = {"mlb_pipeline_draft": 1.4}  # fangraphs absent -> 1.0
        got = _consensus(self._snaps(), "fv", weights=w)
        self.assertAlmostEqual(got, (1.4 * 65 + 1.0 * 55) / (1.4 + 1.0), places=2)


class DraftDedupe(unittest.TestCase):
    """Split name-variant duplicates (one real prospect listed under two name
    forms) merge; genuinely distinct same-school players stay separate."""

    @staticmethod
    def _rep(name, school, pos):
        parts = name.split()
        return {"name": name, "first": _name_part(parts[0]),
                "last": _name_part(parts[-1]), "school": _name_part(school), "pos": pos}

    def test_edit_distance(self):
        self.assertTrue(_edit_distance_le1("kaeden", "kaden"))   # one delete
        self.assertTrue(_edit_distance_le1("issac", "isaac"))    # one swap-ish
        self.assertFalse(_edit_distance_le1("camden", "cameron"))

    def test_merges_nickname_and_spelling_variants(self):
        # prefix (Chris/Christopher, Cam/Camden, Will/William) + edit-distance.
        for a, b in [("Chris Hacopian", "Christopher Hacopian"),
                     ("Cam Kozeal", "Camden Kozeal"),
                     ("Will Taylor", "William Taylor")]:
            self.assertTrue(_same_person(self._rep(a, "Texas A&M", "2B"),
                                         self._rep(b, "Texas A&M", "3B")), f"{a}~{b}")
        self.assertTrue(_same_person(self._rep("Kaeden Waechter", "Jesuit", "SP"),
                                     self._rep("Kaden Waechter", "Jesuit", "RHP")))

    def test_keeps_distinct_people_separate(self):
        # Different first name AND hitter-vs-pitcher -> two real players.
        self.assertFalse(_same_person(self._rep("Camden Johnson", "Oklahoma", "3B"),
                                      self._rep("Cameron Johnson", "Oklahoma", "LHP")))
        # Same name, different school -> separate.
        self.assertFalse(_same_person(self._rep("Jacob Smith", "Vanderbilt", "SS"),
                                      self._rep("Jacob Smith", "LSU", "SS")))

    def test_merge_map_picks_fuller_name_as_canonical(self):
        by_player = {
            "draft_2026_chris_hacopian": [
                {"player_key": "draft_2026_chris_hacopian", "player_name": "Chris Hacopian",
                 "school": "Texas A&M", "position": "2B", "snapshot_date": "2026-06-18"}],
            "draft_2026_christopher_hacopian": [
                {"player_key": "draft_2026_christopher_hacopian", "player_name": "Christopher Hacopian",
                 "school": "Texas A&M", "position": "3B", "snapshot_date": "2026-05-22"}],
        }
        merge_map, name_map = _dedupe_merge_map(by_player)
        canon = merge_map["draft_2026_chris_hacopian"]
        self.assertEqual(canon, "draft_2026_christopher_hacopian")
        self.assertEqual(merge_map["draft_2026_christopher_hacopian"], canon)
        self.assertEqual(name_map[canon], "Christopher Hacopian")

    def test_name_first_last_strips_suffixes_and_commas(self):
        # Generational suffixes must not become the "last name" bucket key.
        self.assertEqual(_name_first_last("Robert Hassell III"), ("robert", "hassell"))
        self.assertEqual(_name_first_last("Robert Hassell"), ("robert", "hassell"))
        self.assertEqual(_name_first_last("Michael Harris II"), ("michael", "harris"))
        # Comma-mangled suffix form unmangles to the same parts.
        self.assertEqual(_name_first_last("Lonnie, Jr. White"), ("lonnie", "white"))
        self.assertEqual(_name_first_last("Lonnie White Jr."), ("lonnie", "white"))

    def test_merges_generational_suffix_variants(self):
        # The bug: "Robert Hassell" and "Robert Hassell III" bucketed apart and
        # shipped as two records. They must now merge onto one canonical key.
        by_player = {
            "draft_2020_robert_hassell": [
                {"player_key": "draft_2020_robert_hassell", "player_name": "Robert Hassell",
                 "school": "Independence HS", "position": "OF", "snapshot_date": "2020-05-01"}],
            "draft_2020_robert_hassell_iii": [
                {"player_key": "draft_2020_robert_hassell_iii", "player_name": "Robert Hassell III",
                 "school": "Independence HS", "position": "OF", "snapshot_date": "2020-06-10"}],
        }
        merge_map, name_map = _dedupe_merge_map(by_player)
        self.assertTrue(merge_map, "suffix-variant twins should merge")
        canon = merge_map["draft_2020_robert_hassell"]
        self.assertEqual(merge_map["draft_2020_robert_hassell_iii"], canon)
        # Canonical = fuller display name (carries the suffix).
        self.assertEqual(name_map[canon], "Robert Hassell III")


if __name__ == "__main__":
    unittest.main()
