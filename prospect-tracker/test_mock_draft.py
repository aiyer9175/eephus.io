# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for mock_draft: board-anchored, tendency-nudged pick assignment."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import mock_draft
from mock_draft import (
    build_mock_draft, _score_candidate, _pos_bucket, _is_pitcher, _is_hs,
    _is_up_the_middle, _round_num, _trait_fit,
)


def _prospect(pick, *, ptype="COLh", pos="SS", fv=50, name=None,
              ds=None, tools=None, key=None):
    return {
        "player_key":       key or f"draft_2026_p{pick}",
        "player_name":      name or f"Prospect {pick}",
        "position":         pos,
        "school":           "Test U",
        "player_type":      ptype,
        "consensus_fv":     fv,
        "consensus_fv_raw": float(fv),
        "consensus_fv_plus": False,
        "consensus_pick":   pick,
        # Default DS+ tracks rank (better rank -> higher), so the deterministic
        # tiebreak never inverts the board.
        "draft_stock_plus": ds if ds is not None else 140 - pick,
        "tool_grades":      {"fangraphs": tools} if tools else {},
    }


def _order(n, team="LAD", start=1):
    return [{"pick_overall": start + i, "round_label": "1",
             "pick_in_round": start + i, "team": team,
             "slot_usd": 5_000_000 - i * 10_000}
            for i in range(n)]


def _cls(prospects, order, *, is_current=True):
    return {"year": 2026, "is_current": is_current,
            "prospects": prospects, "draft_order": order}


class Helpers(unittest.TestCase):
    def test_pos_bucket(self):
        self.assertEqual(_pos_bucket(_prospect(1, ptype="COLp", pos="RHP")), "P")
        self.assertEqual(_pos_bucket(_prospect(1, ptype="HSp", pos="LHP")), "P")
        self.assertEqual(_pos_bucket(_prospect(1, pos="C")), "C")
        self.assertEqual(_pos_bucket(_prospect(1, pos="SS")), "MI")
        self.assertEqual(_pos_bucket(_prospect(1, pos="2B/3B")), "MI")
        self.assertEqual(_pos_bucket(_prospect(1, pos="3B")), "CI")
        self.assertEqual(_pos_bucket(_prospect(1, pos="1B")), "CI")
        self.assertEqual(_pos_bucket(_prospect(1, pos="OF")), "OF")
        self.assertEqual(_pos_bucket(_prospect(1, pos="CF")), "OF")

    def test_is_pitcher_by_type_and_pos(self):
        self.assertTrue(_is_pitcher(_prospect(1, ptype="COLp", pos="RHP")))
        self.assertTrue(_is_pitcher(_prospect(1, ptype="HSp", pos="LHP")))
        # Two-way listed as a bat-primary with no 'p' type is not a pitcher.
        self.assertFalse(_is_pitcher(_prospect(1, ptype="COLh", pos="SS")))
        # Position-driven even if type missing.
        self.assertTrue(_is_pitcher({"position": "RHP", "player_type": None}))

    def test_is_hs(self):
        self.assertTrue(_is_hs(_prospect(1, ptype="HSh")))
        self.assertTrue(_is_hs(_prospect(1, ptype="HSp")))
        self.assertFalse(_is_hs(_prospect(1, ptype="COLh")))

    def test_up_the_middle(self):
        self.assertTrue(_is_up_the_middle(_prospect(1, pos="SS")))
        self.assertTrue(_is_up_the_middle(_prospect(1, pos="CF")))
        self.assertTrue(_is_up_the_middle(_prospect(1, pos="C")))
        self.assertTrue(_is_up_the_middle(_prospect(1, pos="2B")))
        self.assertFalse(_is_up_the_middle(_prospect(1, pos="3B")))
        self.assertFalse(_is_up_the_middle(_prospect(1, pos="OF")))
        # A pitcher is never "up the middle".
        self.assertFalse(_is_up_the_middle(_prospect(1, ptype="COLp", pos="RHP")))

    def test_round_num(self):
        self.assertEqual(_round_num("1"), 1)
        self.assertEqual(_round_num("2"), 2)
        self.assertEqual(_round_num("1A"), 1)
        self.assertEqual(_round_num("10"), 10)
        self.assertIsNone(_round_num("CB-A"))
        self.assertIsNone(_round_num(None))


class BestPlayerAvailable(unittest.TestCase):
    """With no tendencies the mock is a straight best-player-available board."""

    def test_bpa_follows_board_order(self):
        prospects = [_prospect(i) for i in range(1, 11)]
        cls = _cls(prospects, _order(5))
        mock = build_mock_draft(cls, {}, rounds=1)
        self.assertIsNotNone(mock)
        self.assertFalse(mock["used_tendencies"])
        picks = mock["picks"]
        self.assertEqual([p["consensus_pick"] for p in picks], [1, 2, 3, 4, 5])
        # No player assigned twice.
        keys = [p["player_key"] for p in picks]
        self.assertEqual(len(keys), len(set(keys)))
        # No BPA passed when we always take the top board guy.
        self.assertTrue(all(p["bpa_passed"] is None for p in picks))

    def test_value_delta_zero_on_slot(self):
        # Board #1 taken at overall pick 1 -> delta 0 (on slot).
        prospects = [_prospect(i) for i in range(1, 11)]
        mock = build_mock_draft(_cls(prospects, _order(5)), {}, rounds=1)
        self.assertEqual(mock["picks"][0]["value_delta"], 0)

    def test_value_delta_negative_for_faller(self):
        # When the order starts at overall pick 10, board #1 taken first is a
        # faller: value_delta = 1 - 10 = -9 (negative = value to the org).
        prospects = [_prospect(i) for i in range(1, 11)]
        mock = build_mock_draft(_cls(prospects, _order(3, start=10)), {}, rounds=99)
        first = mock["picks"][0]
        self.assertEqual(first["consensus_pick"], 1)
        self.assertEqual(first["value_delta"], 1 - 10)
        self.assertLess(first["value_delta"], 0)

    def test_value_delta_positive_for_reach(self):
        # A prep-heavy org reaching one spot for the HS bat at overall pick 1
        # takes board #2: value_delta = 2 - 1 = +1 (positive = reach).
        prospects = [
            _prospect(1, ptype="COLh", pos="SS"),
            _prospect(2, ptype="HSh", pos="SS"),
        ] + [_prospect(i) for i in range(3, 8)]
        tend = {"draftPos": {"orgs": {"LAD": {
            "zPrep": 2.0, "zPitch": 0.0, "zUpMid": 0.0, "posBucketsZ": {}}}}}
        mock = build_mock_draft(_cls(prospects, _order(1)), tend, rounds=1)
        first = mock["picks"][0]
        self.assertEqual(first["consensus_pick"], 2)
        self.assertEqual(first["value_delta"], 2 - 1)
        self.assertGreater(first["value_delta"], 0)


class TendencyNudge(unittest.TestCase):
    """A strong, aligned tendency can move a pick a spot or two off best-available,
    but cannot pull a clearly-better player from outside the candidate window."""

    def _prep_heavy(self):
        return {"draftPos": {"orgs": {"LAD": {
            "zPrep": 2.0, "zPitch": 0.0, "zUpMid": 0.0,
            "posBucketsZ": {"P": 0, "C": 0, "MI": 0, "CI": 0, "OF": 0},
        }}}}

    def test_prep_org_takes_nearby_hs_over_marginal_college(self):
        # Board: #1 college (idx0), #2 HS (idx1). A strongly prep-heavy org at
        # pick 1 reaches one spot for the prep bat.
        prospects = [
            _prospect(1, ptype="COLh", pos="SS", name="College Guy"),
            _prospect(2, ptype="HSh", pos="SS", name="Prep Guy"),
        ] + [_prospect(i) for i in range(3, 8)]
        mock = build_mock_draft(_cls(prospects, _order(1)), self._prep_heavy(),
                                rounds=1)
        first = mock["picks"][0]
        self.assertTrue(mock["used_tendencies"])
        self.assertEqual(first["player_name"], "Prep Guy")
        # The college #1 it passed is recorded.
        self.assertIsNotNone(first["bpa_passed"])
        self.assertEqual(first["bpa_passed"]["player_name"], "College Guy")
        self.assertIn("Prep-heavy org", first["fit_tags"])

    def test_bounded_cannot_pull_from_outside_window(self):
        # Only HS guy sits at board #7 (idx6 >= window 7 edge); five college
        # guys ahead. Even max prep lean cannot reach that far - BPA wins.
        prospects = [_prospect(i, ptype="COLh") for i in range(1, 7)]
        prospects.append(_prospect(7, ptype="HSh", name="Deep Prep"))
        prospects += [_prospect(i) for i in range(8, 12)]
        mock = build_mock_draft(_cls(prospects, _order(1)), self._prep_heavy(),
                                rounds=1, window=6)
        first = mock["picks"][0]
        self.assertEqual(first["consensus_pick"], 1)
        self.assertIsNone(first["bpa_passed"])


class SlotSignability(unittest.TestCase):
    """The slot-money signal acts on fallers: over-slot orgs chase the tough
    sign, disciplined orgs are penalized for it."""

    def test_over_slot_org_scores_faller_higher(self):
        pick = {"pick_overall": 20, "team": "LAD", "slot_usd": 3_000_000}
        faller = _prospect(5, ptype="HSh")  # value_delta -15 -> faller
        over = {"zOver": 2.0}
        disc = {"zOver": -2.0}
        s_over, tags_over, _ = _score_candidate(faller, 0, pick, None, over, None)
        s_disc, _, _ = _score_candidate(faller, 0, pick, None, disc, None)
        self.assertGreater(s_over, s_disc)
        self.assertIn("Over-slot fit", tags_over)

    def test_non_faller_gets_no_slot_term(self):
        pick = {"pick_overall": 20, "team": "LAD", "slot_usd": 3_000_000}
        non_faller = _prospect(30)  # value_delta +10, a reach not a faller
        over = {"zOver": 2.0}
        s, tags, _ = _score_candidate(non_faller, 0, pick, None, over, None)
        self.assertNotIn("Over-slot fit", tags)


class TraitFit(unittest.TestCase):
    def test_tool_match_rewarded_and_tagged(self):
        traits = {"tilts": {"fb": 0.8}, "top": [{"tool": "fb", "z": 0.8}]}
        flame = _prospect(10, ptype="COLp", pos="RHP",
                          tools={"fb": 70, "sl": 50, "cmd": 50})
        soft = _prospect(10, ptype="COLp", pos="RHP",
                         tools={"fb": 40, "sl": 50, "cmd": 50})
        term_flame, tool_flame = _trait_fit(flame, traits)
        term_soft, _ = _trait_fit(soft, traits)
        self.assertGreater(term_flame, term_soft)
        self.assertEqual(tool_flame, "fb")
        pick = {"pick_overall": 10, "team": "LAD"}
        _, tags, _ = _score_candidate(flame, 0, pick, None, None, traits)
        self.assertIn("Tool fit: Fastball", tags)


class Gating(unittest.TestCase):
    def test_post_draft_class_returns_none(self):
        prospects = [_prospect(i) for i in range(1, 6)]
        order = _order(3)
        order[0]["player_key"] = "draft_2026_p1"  # already drafted
        order[0]["signed"] = 1
        self.assertIsNone(build_mock_draft(_cls(prospects, order), {}))

    def test_non_current_class_returns_none(self):
        prospects = [_prospect(i) for i in range(1, 6)]
        self.assertIsNone(
            build_mock_draft(_cls(prospects, _order(3), is_current=False), {}))

    def test_empty_inputs_return_none(self):
        self.assertIsNone(build_mock_draft(_cls([], _order(3)), {}))
        self.assertIsNone(build_mock_draft(_cls([_prospect(1)], []), {}))

    def test_round_limit_respected(self):
        prospects = [_prospect(i) for i in range(1, 50)]
        order = (_order(5, start=1)  # round 1
                 + [{"pick_overall": 31 + i, "round_label": "2",
                     "pick_in_round": i + 1, "team": "LAD",
                     "slot_usd": 2_000_000} for i in range(5)]  # round 2
                 + [{"pick_overall": 61 + i, "round_label": "3",
                     "pick_in_round": i + 1, "team": "LAD",
                     "slot_usd": 1_000_000} for i in range(5)])  # round 3
        mock1 = build_mock_draft(_cls(prospects, order), {}, rounds=1)
        mock2 = build_mock_draft(_cls(prospects, order), {}, rounds=2)
        self.assertEqual(mock1["n_picks"], 5)
        self.assertEqual(mock2["n_picks"], 10)


class Determinism(unittest.TestCase):
    def test_identical_runs(self):
        prospects = [_prospect(i, ptype=("HSh" if i % 2 else "COLp"),
                               pos=("SS" if i % 2 else "RHP"))
                     for i in range(1, 40)]
        tend = {"draftPos": {"orgs": {"LAD": {
            "zPrep": 1.2, "zPitch": -0.8, "zUpMid": 0.6,
            "posBucketsZ": {"P": -0.5, "C": 0, "MI": 0.7, "CI": 0, "OF": 0},
        }}}, "slot": {"orgs": {"LAD": {"zOver": 1.5}}}}
        a = build_mock_draft(_cls(prospects, _order(20)), tend)
        b = build_mock_draft(_cls(prospects, _order(20)), tend)
        self.assertEqual([p["player_key"] for p in a["picks"]],
                         [p["player_key"] for p in b["picks"]])

    def test_no_duplicate_assignments_large(self):
        prospects = [_prospect(i, ptype=("HSh" if i % 3 else "COLp"))
                     for i in range(1, 60)]
        mock = build_mock_draft(_cls(prospects, _order(40)), {})
        keys = [p["player_key"] for p in mock["picks"]]
        self.assertEqual(len(keys), len(set(keys)))


class BranchCoverage(unittest.TestCase):
    """The materially-risky branches in the shipped path: team filter, board
    exhaustion, build-level slot tagging, the attach entry point, and the
    load_tendencies fallback."""

    def test_pick_with_no_team_is_skipped(self):
        prospects = [_prospect(i) for i in range(1, 11)]
        order = _order(3)
        order[1]["team"] = None  # overall pick 2 has no team -> dropped
        mock = build_mock_draft(_cls(prospects, order), {}, rounds=1)
        self.assertEqual(mock["n_picks"], 2)
        self.assertTrue(all(p["team"] for p in mock["picks"]))
        self.assertEqual([p["pick_overall"] for p in mock["picks"]], [1, 3])

    def test_board_exhaustion_caps_picks(self):
        # 3 ranked prospects, 8 picks -> mock caps at the board, no crash/dup.
        prospects = [_prospect(i) for i in range(1, 4)]
        mock = build_mock_draft(_cls(prospects, _order(8)), {}, rounds=1)
        self.assertEqual(mock["n_picks"], 3)
        keys = [p["player_key"] for p in mock["picks"]]
        self.assertEqual(len(keys), len(set(keys)))

    def test_build_level_over_slot_tag(self):
        # An over-slot org taking a faller (board #1 at overall pick 20) earns
        # the "Over-slot fit" tag through the full build, not just _score_candidate.
        prospects = [_prospect(i) for i in range(1, 11)]
        tend = {"slot": {"orgs": {"LAD": {"zOver": 2.0}}}}
        mock = build_mock_draft(_cls(prospects, _order(1, start=20)), tend, rounds=99)
        first = mock["picks"][0]
        self.assertEqual(first["consensus_pick"], 1)
        self.assertLessEqual(first["value_delta"], -6)  # a faller
        self.assertIn("Over-slot fit", first["fit_tags"])

    def test_window_default_is_seven(self):
        # The as-shipped default window (7) cannot pull an 8th-best HS bat up.
        prospects = [_prospect(i, ptype="COLh") for i in range(1, 8)]
        prospects.append(_prospect(8, ptype="HSh", name="Deep Prep"))
        prospects += [_prospect(i) for i in range(9, 13)]
        tend = {"draftPos": {"orgs": {"LAD": {
            "zPrep": 2.0, "zPitch": 0.0, "zUpMid": 0.0, "posBucketsZ": {}}}}}
        mock = build_mock_draft(_cls(prospects, _order(1)), tend, rounds=1)  # default window
        self.assertEqual(mock["picks"][0]["consensus_pick"], 1)

    def test_attach_mock_draft_bakes_in_place(self):
        cls = _cls([_prospect(i) for i in range(1, 11)], _order(3))
        mock_draft.attach_mock_draft([cls], {})
        self.assertIn("mock_draft", cls)
        self.assertEqual(cls["mock_draft"]["n_picks"], 3)
        # A non-current (already-drafted-era) class is left untouched.
        cls2 = _cls([_prospect(1)], _order(1), is_current=False)
        mock_draft.attach_mock_draft([cls2], {})
        self.assertNotIn("mock_draft", cls2)

    def test_attach_does_not_mutate_prospects(self):
        prospects = [_prospect(i, ptype=("HSh" if i % 2 else "COLp")) for i in range(1, 12)]
        snapshot = json.loads(json.dumps(prospects))
        mock_draft.attach_mock_draft(
            [_cls(prospects, _order(5))],
            {"draftPos": {"orgs": {"LAD": {"zPrep": 1.5, "zPitch": -1.0,
                                           "zUpMid": 0.5, "posBucketsZ": {}}}}})
        self.assertEqual(prospects, snapshot)  # inputs untouched

    def test_load_tendencies_missing_returns_empty(self):
        self.assertEqual(
            mock_draft.load_tendencies("does/not/exist_mock_xyz.json"), {})

    def test_used_tendencies_false_basis(self):
        mock = build_mock_draft(_cls([_prospect(i) for i in range(1, 11)],
                                     _order(3)), {}, rounds=1)
        self.assertFalse(mock["used_tendencies"])
        self.assertIn("best-player-available", mock["basis"])


@unittest.skipUnless(Path("data/draft_timeseries.json").exists(),
                     "needs the committed draft_timeseries.json")
class RealDataSmoke(unittest.TestCase):
    def test_current_class_mock_is_wellformed(self):
        data = json.loads(Path("data/draft_timeseries.json").read_text("utf-8"))
        cur = next((c for c in data["classes"]
                    if c.get("is_current") and c.get("prospects")
                    and c.get("draft_order")), None)
        if cur is None:
            self.skipTest("no pre-draft class on file")
        tend = mock_draft.load_tendencies()
        mock = build_mock_draft(cur, tend)
        if mock is None:
            self.skipTest("current class is already drafted")
        picks = mock["picks"]
        # Picks are in ascending overall order.
        overalls = [p["pick_overall"] for p in picks]
        self.assertEqual(overalls, sorted(overalls))
        # Every assigned player is unique and is a real board prospect.
        board_keys = {p["player_key"] for p in cur["prospects"]}
        assigned = [p["player_key"] for p in picks]
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertTrue(set(assigned).issubset(board_keys))
        # value_delta is internally consistent.
        for p in picks:
            self.assertEqual(p["value_delta"],
                             p["consensus_pick"] - p["pick_overall"])


if __name__ == "__main__":
    unittest.main()
