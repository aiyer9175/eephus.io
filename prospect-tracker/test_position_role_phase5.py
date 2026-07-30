# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Phase 5 position + role resolvers (master plan 2026-07-30, LANE-P5).

Pure-function coverage for the two new resolvers, with every rule
pre-registered in docs/efv-2026-07-30/POSITION_ROLE_GATE.md:

  * fielding_positions.observed_position - most-played non-DH MiLB
    position from the game-data fielding census. DH exclusion, the
    exposure floor, the three-key deterministic tie-break, and the
    absent-player null.
  * role_usage.usage_role / reliever_by_usage / the both-directions
    usage_position_override - games started as the primary pitcher role
    source, the opener guard in BOTH directions, the deliberately
    unadjudicated swingman band, and the switch (SHIPPED ON 2026-07-30;
    the retired one-direction contract stays reachable via
    both_directions=False and is pinned so the regression argument the
    flip was granted on remains executable).

Extended 2026-07-30 (LANE-SHIP) with TestObservedPositionConsumers: which
consumers read the OBSERVATION and which deliberately stay on the
PROJECTION. Both halves are pinned, including the REFUSAL - the
disagreement is signed, so repointing positional scarcity would pay 318
players for a premium position the industry says they will not hold. The
two default-OFF flips are pinned off AND proved to be exact no-ops in that
state, because "gated" only means something if the gate holds the old
behaviour byte-for-byte.

No network, no cache, no DB: every usage line is passed in or mocked.
"""

import json
import unittest
from unittest import mock

import fielding_positions as fp
import role_usage
from fielding_positions import (
    load_observed_positions,
    observed_position,
    observed_position_detail,
)
from role_usage import (
    reliever_by_usage,
    usage_position_override,
    usage_role,
)


class TestObservedPosition(unittest.TestCase):
    def test_most_played_wins(self):
        # franklin_arias' real census: 2B 62, SS 498, DH 68.
        by_pos = {"2B": {"g": 62, "gs": 60},
                  "SS": {"g": 498, "gs": 494},
                  "DH": {"g": 68, "gs": 68}}
        self.assertEqual(observed_position(by_pos), "SS")

    def test_dh_never_wins_even_when_largest(self):
        # DH is the biggest bucket by a mile; the answer is still the
        # largest FIELDING bucket.
        by_pos = {"DH": {"g": 300, "gs": 300},
                  "1B": {"g": 40, "gs": 38},
                  "LF": {"g": 12, "gs": 10}}
        self.assertEqual(observed_position(by_pos), "1B")

    def test_only_dh_ph_pr_resolves_to_none(self):
        by_pos = {"DH": {"g": 120, "gs": 120},
                  "PH": {"g": 30, "gs": 0},
                  "PR": {"g": 9, "gs": 0}}
        self.assertIsNone(observed_position(by_pos))

    def test_below_exposure_floor_is_none(self):
        # 3 games / 3 starts at 2B: under both 10 games and 5 starts.
        self.assertIsNone(observed_position({"2B": {"g": 3, "gs": 3}}))

    def test_starts_clause_qualifies_a_midseason_regular(self):
        # 6 games but 6 starts clears the OR-starts branch (>= 5).
        d = observed_position_detail({"SS": {"g": 6, "gs": 6}})
        self.assertIsNotNone(d)
        self.assertEqual(d["pos"], "SS")
        self.assertTrue(d["qualified"])

    def test_tie_breaks_on_starts_then_spectrum(self):
        # Level on games -> more starts wins.
        self.assertEqual(
            observed_position({"LF": {"g": 50, "gs": 20},
                               "RF": {"g": 50, "gs": 45}}), "RF")
        # Level on games AND starts -> the harder position on the
        # spectrum wins (SS ahead of 2B, C ahead of everything).
        self.assertEqual(
            observed_position({"2B": {"g": 50, "gs": 50},
                               "SS": {"g": 50, "gs": 50}}), "SS")
        self.assertEqual(
            observed_position({"C": {"g": 40, "gs": 40},
                               "1B": {"g": 40, "gs": 40}}), "C")

    def test_tie_flag_is_reported(self):
        d = observed_position_detail({"2B": {"g": 50, "gs": 50},
                                      "SS": {"g": 50, "gs": 50}})
        self.assertTrue(d["tie"])
        clear = observed_position_detail({"SS": {"g": 90, "gs": 90},
                                          "2B": {"g": 10, "gs": 8}})
        self.assertFalse(clear["tie"])

    def test_tie_break_is_order_independent(self):
        # The same census in either insertion order must give one answer;
        # the shipped versa sort would fall back to dict order here.
        a = {"2B": {"g": 50, "gs": 50}, "SS": {"g": 50, "gs": 50}}
        b = {"SS": {"g": 50, "gs": 50}, "2B": {"g": 50, "gs": 50}}
        self.assertEqual(observed_position(a), observed_position(b))

    def test_share_is_over_non_dh_games_only(self):
        d = observed_position_detail({"SS": {"g": 75, "gs": 75},
                                      "2B": {"g": 25, "gs": 25},
                                      "DH": {"g": 100, "gs": 100}})
        self.assertEqual(d["pos"], "SS")
        self.assertAlmostEqual(d["share"], 0.75, places=4)

    def test_empty_and_malformed_are_none_not_raises(self):
        self.assertIsNone(observed_position({}))
        self.assertIsNone(observed_position(None))
        self.assertIsNone(observed_position({"SS": {}}))
        self.assertIsNone(observed_position({"": {"g": 99, "gs": 99}}))
        # Non-numeric counts read as zero rather than exploding.
        self.assertIsNone(observed_position({"SS": {"g": "x", "gs": None}}))

    def test_unknown_position_code_still_resolvable(self):
        # An unmapped code sorts last on the spectrum tie-break but is a
        # legal answer when it wins outright on games.
        self.assertEqual(observed_position({"XX": {"g": 40, "gs": 40}}), "XX")


class TestLoadObservedPositions(unittest.TestCase):
    def test_absent_player_yields_no_entry(self):
        doc = {"players": {
            "real_guy": {"by_pos": {"SS": {"g": 80, "gs": 80}}},
            "cameo_guy": {"by_pos": {"2B": {"g": 2, "gs": 1}}},
            "dh_only_guy": {"by_pos": {"DH": {"g": 90, "gs": 90}}},
        }}
        with mock.patch("pathlib.Path.read_text",
                        return_value=json.dumps(doc)):
            out = load_observed_positions("whatever.json")
        self.assertEqual(out, {"real_guy": "SS"})
        # A player with no usable observation is OMITTED, so .get() is
        # None either way - there is never a fabricated fallback.
        self.assertIsNone(out.get("cameo_guy"))
        self.assertIsNone(out.get("never_heard_of_him"))

    def test_missing_file_is_an_empty_map_not_an_exception(self):
        self.assertEqual(load_observed_positions("no/such/file.json"), {})

    def test_unparseable_file_is_an_empty_map(self):
        with mock.patch("pathlib.Path.read_text", return_value="{not json"):
            self.assertEqual(load_observed_positions("bad.json"), {})


class TestUsageRole(unittest.TestCase):
    def test_clemmey_shape_is_sp(self):
        # 19 G / 19 GS / 87 IP - the canonical stretched starter.
        self.assertEqual(usage_role(19, 19, 87.0), "SP")

    def test_opener_is_rp_not_sp(self):
        # Alex Cook 2026: 28 G / 5 GS / 32 IP, IP/G 1.13, GS-share 0.18.
        # The opener guard keeps him off SP; the reverse direction now
        # names him what he is.
        self.assertEqual(usage_role(28, 5, 32.0), "RP")
        self.assertFalse(role_usage.starter_by_usage(28, 5, 32.0))

    def test_pure_reliever_is_rp(self):
        # Dylan Lesko 2026: 21 G / 0 GS / 27 IP.
        self.assertEqual(usage_role(21, 0, 27.0), "RP")

    def test_swingman_band_is_unadjudicated(self):
        # GS-share 0.33: above the RP ceiling (0.25), below the SP floor
        # (0.50). Usage declines to rule; the published label stands.
        self.assertIsNone(usage_role(30, 10, 90.0))
        # Reliever-ish share but starter-length outings (long relief /
        # tandem): also unadjudicated, not called a reliever.
        self.assertIsNone(usage_role(20, 2, 70.0))

    def test_high_gs_share_short_outings_is_unadjudicated(self):
        # Piggyback: 20 G / 12 GS / 40 IP. Fails SP on IP/G 2.0 and fails
        # RP on GS-share 0.60. Neither - the label stands.
        self.assertIsNone(usage_role(20, 12, 40.0))

    def test_under_the_ip_floor_is_none_both_ways(self):
        self.assertIsNone(usage_role(4, 4, 18.0))     # starter-shaped cameo
        self.assertIsNone(usage_role(15, 0, 15.0))    # reliever-shaped cameo
        self.assertFalse(reliever_by_usage(15, 0, 15.0))

    def test_boundaries_are_inclusive_as_documented(self):
        # GS-share exactly 0.50 with IP/G 3.0 and IP 60 -> SP.
        self.assertEqual(usage_role(20, 10, 60.0), "SP")
        # GS-share exactly 0.25 with IP/G 1.5 and IP 30 -> RP.
        self.assertEqual(usage_role(20, 5, 30.0), "RP")
        # IP/G exactly 3.0 with a reliever's share is NOT RP (strict <).
        self.assertIsNone(usage_role(20, 0, 60.0))

    def test_bad_input_is_none(self):
        self.assertIsNone(usage_role(None, None, None))
        self.assertIsNone(usage_role(0, 0, 0))
        self.assertIsNone(usage_role("", "", ""))
        self.assertFalse(reliever_by_usage(None, 0, 40.0))


class TestBothDirectionsOverride(unittest.TestCase):
    """The flag shipped ON 2026-07-30 (owner decision). Both states are pinned:
    the DEFAULT (on) because that is what is served, and the explicit
    both_directions=False path because that is the retired rule D and it must stay
    byte-identical for the regression argument the flip was granted on."""

    def _line(self, g, gs, ip):
        return mock.patch.object(role_usage, "current_season_pitching",
                                 return_value={"g": g, "gs": gs, "ip": ip})

    def test_module_default_is_on_and_the_fingerprint_names_it(self):
        """The switch is a BOARD-ORDERING input, so the board basis fingerprint has
        to name it. Pinned together here because that coupling is the only thing
        stopping the switch from being flipped back silently: role mode decides
        efv_score._RP_DESIGNATIONS membership, which gates the reliever ceiling."""
        import storage
        self.assertTrue(role_usage.USAGE_ROLE_BOTH_DIRECTIONS)
        self.assertEqual(role_usage.role_resolution_mode(), "usage_both")
        self.assertIn("roles=usage_both", storage.board_basis_fingerprint())
        self.assertIn("roles=", storage.BOARD_BASIS_FINGERPRINT)

    def test_explicit_flag_off_still_reproduces_shipped_rule_d(self):
        with self._line(21, 0, 27.0):     # unambiguous reliever usage
            # The retired one-direction contract, kept reachable and pinned: this
            # is the exact behaviour the "same 103 arms, zero disagreements"
            # regression check was run against.
            for lbl in ("SP", "P", "RHP"):
                self.assertEqual(
                    usage_position_override(lbl, 700001, 2026,
                                            both_directions=False), lbl)
        with self._line(19, 19, 87.0):    # starter usage
            # RP -> SP fires in BOTH modes - that direction never changed.
            self.assertEqual(
                usage_position_override("MIRP", 700002, 2026,
                                        both_directions=False), "SP")
            self.assertEqual(
                usage_position_override("SIRP", 700002, 2026,
                                        both_directions=False), "SP")

    def test_module_default_now_runs_both_directions(self):
        """No both_directions argument: the caller gets the module switch, which
        is what storage's export pre-pass does."""
        with self._line(21, 0, 27.0):
            self.assertEqual(usage_position_override("SP", 700012, 2026), "RP")
            self.assertEqual(usage_position_override("P", 700012, 2026), "RP")
        with self._line(19, 19, 87.0):
            self.assertEqual(usage_position_override("P", 700013, 2026), "SP")
            self.assertEqual(usage_position_override("MIRP", 700013, 2026), "SP")

    def test_flag_on_flips_sp_to_rp_on_reliever_usage(self):
        with self._line(21, 0, 27.0):
            self.assertEqual(
                usage_position_override("SP", 700003, 2026,
                                        both_directions=True), "RP")

    def test_flag_on_resolves_roleless_labels_both_ways(self):
        with self._line(19, 19, 87.0):
            for lbl in ("P", "RHP", "LHP"):
                self.assertEqual(
                    usage_position_override(lbl, 700004, 2026,
                                            both_directions=True), "SP")
        with self._line(21, 0, 27.0):
            for lbl in ("P", "RHP", "LHP"):
                self.assertEqual(
                    usage_position_override(lbl, 700005, 2026,
                                            both_directions=True), "RP")

    def test_flag_on_keeps_the_opener_a_reliever(self):
        # The opener guard, running the direction it always implied.
        with self._line(28, 5, 32.0):
            self.assertEqual(
                usage_position_override("SP", 700006, 2026,
                                        both_directions=True), "RP")
            self.assertEqual(
                usage_position_override("MIRP", 700006, 2026,
                                        both_directions=True), "MIRP")

    def test_flag_on_leaves_the_swingman_band_alone(self):
        with self._line(30, 10, 90.0):
            for lbl in ("SP", "P", "RHP", "MIRP"):
                self.assertEqual(
                    usage_position_override(lbl, 700007, 2026,
                                            both_directions=True), lbl)

    def test_flag_on_never_touches_a_hitter_label(self):
        with mock.patch.object(
                role_usage, "current_season_pitching",
                side_effect=AssertionError("cache read for a hitter label")):
            for lbl in ("SS", "CF", "C", "DH", "SS/2B"):
                self.assertEqual(
                    usage_position_override(lbl, 700008, 2026,
                                            both_directions=True), lbl)

    def test_flag_on_no_usage_data_keeps_the_published_label(self):
        with mock.patch.object(role_usage, "current_season_pitching",
                               return_value=None):
            for lbl in ("SP", "P", "MIRP"):
                self.assertEqual(
                    usage_position_override(lbl, 700009, 2026,
                                            both_directions=True), lbl)

    def test_flag_on_missing_identity_keeps_the_published_label(self):
        with mock.patch.object(
                role_usage, "current_season_pitching",
                side_effect=AssertionError("cache read without an mlbam")):
            self.assertEqual(
                usage_position_override("SP", None, 2026,
                                        both_directions=True), "SP")
            self.assertIsNone(
                usage_position_override(None, 700010, 2026,
                                        both_directions=True))

    def test_flag_on_compound_labels_are_left_alone(self):
        # A compound carrying a non-role token is not a clean role claim;
        # neither direction touches it.
        with mock.patch.object(
                role_usage, "current_season_pitching",
                side_effect=AssertionError("cache read for a compound label")):
            self.assertEqual(
                usage_position_override("SP/MIRP", 700011, 2026,
                                        both_directions=True), "SP/MIRP")
            self.assertEqual(
                usage_position_override("RHP/DH", 700011, 2026,
                                        both_directions=True), "RHP/DH")

    def test_rp_label_is_a_member_of_the_efv_reliever_set(self):
        # The emitted label MUST land in efv_score._RP_DESIGNATIONS -
        # that membership is the whole reason this direction is gated.
        import efv_score
        self.assertIn(role_usage._RP_LABEL, efv_score._RP_DESIGNATIONS)


class TestSpectrumTable(unittest.TestCase):
    def test_spectrum_covers_every_position_the_census_produces(self):
        # Every non-DH code in the shipped sidecar must have a stated
        # spectrum rank, or the tie-break silently degrades to name order.
        try:
            doc = json.loads(
                (fp.Path(__file__).parent / "data" /
                 "positions_played.json").read_text(encoding="utf-8"))
        except OSError:
            self.skipTest("positions_played.json not present")
        codes = {p for rec in doc.get("players", {}).values()
                 for p in (rec.get("by_pos") or {})
                 if p not in fp._NON_FIELD}
        missing = codes - set(fp._SPECTRUM_RANK)
        self.assertEqual(missing, set(),
                         f"positions with no spectrum rank: {sorted(missing)}")


class TestObservedPositionConsumers(unittest.TestCase):
    """Which consumers read the OBSERVATION and which stay on the PROJECTION.

    The split is the whole decision, so it is pinned rather than left to a comment.
    The two flips that are default-OFF are pinned OFF *and* proved to be exact no-ops
    in that state, because "gated" is only meaningful if the gate actually holds the
    old behaviour byte-for-byte.
    """

    def test_pos_premium_flip_is_off_and_is_a_no_op_while_off(self):
        import efv_model as EM
        self.assertFalse(EM.POS_PREMIUM_USES_OBSERVED)
        rows = [{"player_key": "x", "position": "3B"},
                {"player_key": "x", "position": "SS"},
                {"player_key": "x", "position": None},
                {"player_key": "x", "position": "SS/2B"}]
        with mock.patch.object(EM, "_observed_pos_map",
                               return_value={"x": "SS"}):
            for r in rows:
                for side in ("hit", "pit"):
                    self.assertEqual(EM._pos_premium_for_row(r, side),
                                     EM._pos_premium(r["position"], side))

    def test_pos_premium_flip_reads_the_observation_when_on(self):
        import efv_model as EM
        r = {"player_key": "x", "position": "3B"}      # projected 3B, observed SS
        with mock.patch.object(EM, "POS_PREMIUM_USES_OBSERVED", True), \
                mock.patch.object(EM, "_observed_pos_map", return_value={"x": "SS"}):
            self.assertEqual(EM._pos_premium_for_row(r, "hit"), 1.0)
            self.assertEqual(EM._pos_premium(r["position"], "hit"), 0.0)
            # Pitchers are never repointed - the census has no pitcher rows and
            # the pitcher branch is a role question, not a position one.
            self.assertEqual(EM._pos_premium_for_row({"player_key": "x",
                                                      "position": "RP"}, "pit"), 0.0)
            # No observation -> the listed position, not a null.
            self.assertEqual(EM._pos_premium_for_row({"player_key": "zzz",
                                                      "position": "SS"}, "hit"), 1.0)

    def test_def_value_flip_is_off(self):
        """prospect_def_value is the one flip with a LEAKAGE blocker, not just a
        coverage one: its `position` is documented as the AS-OF-DECISION label and
        positions_played.json is a career-to-date census, so the observation contains
        games played after the decision the model is scored on predicting."""
        import prospect_def_value as pdv
        self.assertFalse(pdv.DEF_VALUE_USES_OBSERVED)

    def test_catcher_tool_weighting_reads_the_observation(self):
        """The ONE backend consumer flipped ON. _compute_tool_composites only asks
        "is this a catcher", to decide whether the D-Tool weights drop speed and bump
        field. A man who has caught 400 games is a catcher for that purpose."""
        import storage
        self.assertEqual(storage._position_bucket("C"), "C")
        self.assertEqual(storage._position_bucket("1B"), "IF")
        grades = {"field": 60.0, "throw": 55.0, "speed": 30.0}
        as_c = storage._compute_tool_composites(grades, False, position_bucket="C")
        as_if = storage._compute_tool_composites(grades, False, position_bucket="IF")
        self.assertIsNotNone(as_c["composite_def"])
        self.assertNotEqual(as_c["composite_def"], as_if["composite_def"],
                            "the catcher bucket must actually change the D-Tool "
                            "weights, or flipping its input is decorative")

    def test_the_projection_consumers_are_still_on_the_projection(self):
        """Guard the half of the decision that is a REFUSAL. The disagreement is
        SIGNED - FanGraphs projects a move DOWN the spectrum 318 times against 184
        up - so repointing the market-scarcity multiplier would pay 318 players for a
        premium position the industry says they will not hold."""
        import value_framework as vf
        # position_multiplier is the scarcity hook and it must keep taking a
        # position STRING from the caller (the payload's projected `position`),
        # with no observation lookup of its own.
        import inspect
        src = inspect.getsource(vf.position_multiplier)
        self.assertNotIn("observed", src)
        self.assertNotIn("positions_played", src)


if __name__ == "__main__":
    unittest.main()
