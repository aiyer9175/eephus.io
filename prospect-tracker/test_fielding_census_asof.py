# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""The as-of-aware season census in fielding_positions.

Every rule pinned here is pre-registered in
docs/efv-2026-07-30/POSITION_CENSUS_ASOF.md. Pure functions only - nothing in
this file touches the network, prospects.db, or any artifact under data/.

Run directly (the suite is not invoked here; concurrent lanes own it):
    python test_fielding_census_asof.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fielding_positions as fp  # noqa: E402


class TestSeasonVisibility(unittest.TestCase):
    """season_visible_through IS the as-of rule; if it drifts, the census leaks."""

    def test_preseason_decision_sees_only_prior_seasons(self):
        self.assertEqual(fp.season_visible_through("2024-01-22"), 2023)

    def test_midseason_decision_still_sees_only_prior_seasons(self):
        # The endpoint returns a season TOTAL, so an August 2024 decision must
        # NOT be credited with the 2024 line - most of it postdates the call.
        self.assertEqual(fp.season_visible_through("2024-08-15"), 2023)

    def test_boundary_is_inclusive_on_season_end(self):
        self.assertEqual(fp.season_visible_through("2024-09-30"), 2023)
        self.assertEqual(fp.season_visible_through("2024-10-01"), 2024)
        self.assertEqual(fp.season_visible_through("2024-12-31"), 2024)

    def test_accepts_a_date_object_and_a_timestamp_string(self):
        self.assertEqual(fp.season_visible_through(date(2024, 10, 2)), 2024)
        self.assertEqual(fp.season_visible_through("2024-01-22T00:00:00"), 2023)

    def test_unusable_input_is_none_not_a_guess(self):
        for bad in (None, "", "not-a-date", 2024, {}):
            self.assertIsNone(fp.season_visible_through(bad), bad)


class TestAsOfSummation(unittest.TestCase):
    SM = {"2021": {"SS": [40, 38], "2B": [10, 9]},
          "2022": {"SS": [80, 78]},
          "2024": {"3B": [100, 99]}}

    def test_career_sums_every_season(self):
        self.assertEqual(fp.career_by_pos(self.SM),
                         {"SS": {"g": 120, "gs": 116}, "2B": {"g": 10, "gs": 9},
                          "3B": {"g": 100, "gs": 99}})

    def test_as_of_truncates_later_seasons(self):
        self.assertEqual(fp.as_of_by_pos(self.SM, "2023-06-01"),
                         {"SS": {"g": 120, "gs": 116}, "2B": {"g": 10, "gs": 9}})

    def test_as_of_truncates_the_decision_season_itself(self):
        self.assertEqual(fp.as_of_by_pos(self.SM, "2022-03-01"),
                         {"SS": {"g": 40, "gs": 38}, "2B": {"g": 10, "gs": 9}})

    def test_bad_as_of_yields_nothing_never_the_career_total(self):
        # The failure mode this guards is the whole point of the module: a
        # caller asking for a DATED read must never silently receive a
        # career-to-date one.
        self.assertEqual(fp.as_of_by_pos(self.SM, "garbage"), {})
        self.assertEqual(fp.as_of_by_pos(self.SM, None), {})

    def test_reads_the_versa_dict_cell_form_too(self):
        sm = {"2022": {"SS": {"g": 50, "gs": 49}}}
        self.assertEqual(fp.career_by_pos(sm), {"SS": {"g": 50, "gs": 49}})

    def test_malformed_cells_and_seasons_are_skipped_not_raised(self):
        sm = {"2021": {"SS": [10, 9]}, "notayear": {"CF": [99, 99]},
              "2022": {"1B": None}}
        self.assertEqual(fp.career_by_pos(sm),
                         {"SS": {"g": 10, "gs": 9}, "1B": {"g": 0, "gs": 0}})

    def test_empty_census_entry(self):
        self.assertEqual(fp.career_by_pos({}), {})
        self.assertEqual(fp.as_of_by_pos({}, "2024-01-01"), {})


class TestObservedPositionAsOf(unittest.TestCase):
    """The resolver rules are observed_position's; only the window changes."""

    def test_position_can_differ_between_as_of_and_career(self):
        sm = {"2021": {"SS": [120, 118]}, "2025": {"1B": [300, 298]}}
        self.assertEqual(fp.observed_position_as_of(sm, "2022-02-01"), "SS")
        self.assertEqual(fp.observed_position(fp.career_by_pos(sm)), "1B")

    def test_dh_is_still_never_eligible(self):
        sm = {"2022": {"DH": [100, 100], "1B": [20, 18]}}
        self.assertEqual(fp.observed_position_as_of(sm, "2023-06-01"), "1B")

    def test_dh_only_resolves_to_none(self):
        self.assertIsNone(fp.observed_position_as_of(
            {"2022": {"DH": [100, 100]}}, "2023-06-01"))

    def test_exposure_floor_still_applies_inside_the_window(self):
        self.assertIsNone(fp.observed_position_as_of(
            {"2022": {"SS": [3, 2]}}, "2023-06-01"))
        self.assertEqual(fp.observed_position_as_of(
            {"2022": {"SS": [3, 5]}}, "2023-06-01"), "SS")   # OR-starts clause

    def test_nothing_before_the_as_of_date_is_none(self):
        self.assertIsNone(fp.observed_position_as_of(
            {"2024": {"SS": [120, 118]}}, "2021-03-01"))

    def test_tie_breaks_on_the_defensive_spectrum_within_the_window(self):
        sm = {"2021": {"3B": [50, 50], "SS": [50, 50]}}
        self.assertEqual(fp.observed_position_as_of(sm, "2022-01-01"), "SS")


class TestObservedPositionsAsOfMap(unittest.TestCase):
    CENSUS = {"100": {"2021": {"SS": [120, 118]}},
              "200": {"2024": {"CF": [120, 118]}},
              "300": {"2021": {"SS": [2, 1]}}}

    def test_each_key_uses_its_own_as_of_date(self):
        out = fp.observed_positions_as_of(
            self.CENSUS,
            {"a": "2022-01-01", "b": "2022-01-01"},
            {"a": 100, "b": 200})
        self.assertEqual(out, {"a": "SS"})   # b's only season is 2024, unseen

    def test_omits_rather_than_nulls_every_way_of_having_no_observation(self):
        out = fp.observed_positions_as_of(
            self.CENSUS,
            {"no_id": "2022-01-01", "no_entry": "2022-01-01",
             "no_date": None, "below_floor": "2022-01-01"},
            {"no_entry": 999, "no_date": 100, "below_floor": 300})
        self.assertEqual(out, {})
        self.assertIsNone(out.get("no_id"))

    def test_empty_inputs(self):
        self.assertEqual(fp.observed_positions_as_of({}, {}, {}), {})
        self.assertEqual(fp.observed_positions_as_of(self.CENSUS, None, None), {})


class TestCensusNameIndex(unittest.TestCase):
    ROWS = [
        {"mlbam": 1, "name": "Jose Ramirez", "season": 2015, "age": 22, "pos": "SS"},
        {"mlbam": 1, "name": "José Ramírez", "season": 2016, "age": 23, "pos": "SS"},
        {"mlbam": 2, "name": "Jose Ramirez", "season": 2019, "age": 20, "pos": "CF"},
        {"mlbam": 3, "name": "", "season": 2019, "age": 20, "pos": "CF"},
    ]

    def test_accent_variants_collapse_onto_one_id(self):
        idx = fp.census_name_index(self.ROWS)
        self.assertEqual(set(idx["jose ramirez"]), {1, 2})
        self.assertEqual(idx["jose ramirez"][1]["seasons"], {2015, 2016})

    def test_birth_years_are_implied_from_season_minus_age(self):
        idx = fp.census_name_index(self.ROWS)
        self.assertEqual(idx["jose ramirez"][1]["birth_years"], {1993})
        self.assertEqual(idx["jose ramirez"][2]["birth_years"], {1999})

    def test_nameless_and_malformed_rows_are_skipped(self):
        idx = fp.census_name_index(self.ROWS + [{"name": "x"}, {"mlbam": "zz", "name": "y"}])
        self.assertNotIn("", idx)
        self.assertNotIn("y", idx)

    def test_missing_age_yields_no_birth_year_rather_than_a_wrong_one(self):
        idx = fp.census_name_index([{"mlbam": 9, "name": "No Age", "season": 2019}])
        self.assertEqual(idx["no age"][9]["birth_years"], set())


class TestIdentityResolution(unittest.TestCase):
    IDX = fp.census_name_index([
        {"mlbam": 1, "name": "Jose Ramirez", "season": 2015, "age": 22},
        {"mlbam": 2, "name": "Jose Ramirez", "season": 2019, "age": 20},
        {"mlbam": 7, "name": "Solo Guy", "season": 2016, "age": 21},
        {"mlbam": 8, "name": "Late Guy", "season": 2022, "age": 19},
    ])

    def test_known_binding_always_wins_and_is_labelled(self):
        ids, prov = fp.resolve_census_ids(
            [{"player_key": "k", "name": "Jose Ramirez"}], self.IDX, known={"k": 55})
        self.assertEqual(ids["k"], 55)
        self.assertEqual(prov["k"], "known")

    def test_unique_name_match_resolves(self):
        ids, prov = fp.resolve_census_ids(
            [{"player_key": "k", "name": "Solo Guy", "by_year": 2018}], self.IDX)
        self.assertEqual((ids["k"], prov["k"]), (7, "name"))

    def test_ambiguous_names_are_dropped_never_guessed(self):
        ids, prov = fp.resolve_census_ids(
            [{"player_key": "k", "name": "Jose Ramirez", "by_year": 2021}], self.IDX)
        self.assertNotIn("k", ids)
        self.assertEqual(prov["k"], "ambiguous")

    def test_by_year_guard_disambiguates_and_rejects_later_debuts(self):
        # Only id 1 is playing by 2016, so the name stops being ambiguous.
        ids, _ = fp.resolve_census_ids(
            [{"player_key": "k", "name": "Jose Ramirez", "by_year": 2016}], self.IDX)
        self.assertEqual(ids["k"], 1)
        # A candidate who first appears AFTER the decision is a different player.
        ids, prov = fp.resolve_census_ids(
            [{"player_key": "k", "name": "Late Guy", "by_year": 2019}], self.IDX)
        self.assertNotIn("k", ids)
        self.assertEqual(prov["k"], "unresolved")

    def test_birth_year_guard_disambiguates_two_players_of_the_same_name(self):
        # id 1 was born ~1993, id 2 ~1999. Both are playing by 2021, so the
        # vintage guard alone leaves this ambiguous; the birth year settles it.
        ids, prov = fp.resolve_census_ids(
            [{"player_key": "k", "name": "Jose Ramirez", "by_year": 2021,
              "birth_year": 1999}], self.IDX)
        self.assertEqual((ids["k"], prov["k"]), (2, "name"))

    def test_birth_year_guard_rejects_a_unique_but_wrong_match(self):
        ids, prov = fp.resolve_census_ids(
            [{"player_key": "k", "name": "Solo Guy", "by_year": 2018,
              "birth_year": 1975}], self.IDX)
        self.assertNotIn("k", ids)
        self.assertEqual(prov["k"], "unresolved")

    def test_birth_year_tolerance_absorbs_the_statsapi_age_cutoff(self):
        # id 7 implies 1995; +-1 year must still bind, because StatsAPI age is
        # as of a season cutoff rather than a birthday.
        for by in (1994, 1995, 1996):
            ids, _ = fp.resolve_census_ids(
                [{"player_key": "k", "name": "Solo Guy", "by_year": 2018,
                  "birth_year": by}], self.IDX)
            self.assertEqual(ids.get("k"), 7, by)

    def test_a_guard_with_no_input_is_skipped_not_failed(self):
        # No birth year on our side must not manufacture a rejection.
        ids, _ = fp.resolve_census_ids(
            [{"player_key": "k", "name": "Solo Guy", "by_year": 2018}], self.IDX)
        self.assertEqual(ids["k"], 7)
        # ... and neither must a missing age on the feed side.
        idx = fp.census_name_index([{"mlbam": 9, "name": "No Age", "season": 2016}])
        ids, _ = fp.resolve_census_ids(
            [{"player_key": "k", "name": "No Age", "by_year": 2018,
              "birth_year": 1800}], idx)
        self.assertEqual(ids["k"], 9)

    def test_accent_and_suffix_folding(self):
        for a, b in (("José Ramírez", "Jose Ramirez"),
                     ("Bobby Witt Jr.", "Bobby Witt"),
                     ("Cal Ripken, Jr", "Cal Ripken")):
            self.assertEqual(fp.normalize_name(a), fp.normalize_name(b), (a, b))

    def test_rows_without_a_key_are_skipped(self):
        ids, prov = fp.resolve_census_ids([{"name": "Solo Guy"}], self.IDX)
        self.assertEqual((ids, prov), ({}, {}))


class TestLoadSeasonCensus(unittest.TestCase):
    def test_missing_or_corrupt_file_is_empty_never_raises(self):
        self.assertEqual(fp.load_season_census("does/not/exist.json"), {})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{not json")
            p = fh.name
        try:
            self.assertEqual(fp.load_season_census(p), {})
        finally:
            os.unlink(p)

    def test_round_trip_through_the_written_shape(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            json.dump({"players": {"100": {"2021": {"SS": [120, 118]}}}}, fh)
            p = fh.name
        try:
            c = fp.load_season_census(p)
            self.assertEqual(fp.observed_position_as_of(c["100"], "2022-01-01"), "SS")
        finally:
            os.unlink(p)


class TestBuilderIsOfflineSafe(unittest.TestCase):
    def test_fetch_false_never_touches_the_network(self):
        # A cache-only build of a league-season that cannot exist must return []
        # rather than firing a request. If this ever hangs, the guard is gone.
        self.assertEqual(fp.fetch_season_fielding(99, 1901, fetch=False), [])

    def test_build_with_fetch_false_and_an_empty_allowlist_writes_a_valid_shell(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "census.json"
            doc = fp.build_positions_played_seasons(
                seasons=[1901], sports=(99,), out_path=out,
                keep_mlbam=set(), fetch=False)
            self.assertEqual(doc["players"], {})
            self.assertEqual(doc["season_end"], "10-01")
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["players"], {})


def _split(pos, sport, g, gs):
    return {"position": {"abbreviation": pos}, "sport": {"abbreviation": sport},
            "stat": {"games": g, "gamesStarted": gs}}


class TestCareerRollupDedupe(unittest.TestCase):
    """The 'Minors' split RESTATES the non-MLB per-level splits. Summing both
    weighted every MiLB game twice against MLB's once - which flipped resolved
    positions for mixed MLB/MiLB players (dawel_lugo: SS on the doubled counts,
    3B on the true ones)."""

    LUGO = [_split("SS", "A", 153, 153), _split("SS", "A(Short)", 16, 16),
            _split("SS", "A+", 81, 80), _split("SS", "AA", 22, 20),
            _split("SS", "AAA", 1, 0), _split("SS", "ROK", 95, 95),
            _split("SS", "Minors", 368, 364),
            _split("3B", "A+", 60, 60), _split("3B", "AA", 147, 138),
            _split("3B", "AAA", 105, 103), _split("3B", "MLB", 78, 72),
            _split("3B", "Minors", 312, 301)]

    def test_the_rollup_is_discarded_when_levels_are_present(self):
        got = fp.aggregate_career_splits(self.LUGO)
        self.assertEqual(got["SS"], {"g": 368, "gs": 364})
        self.assertEqual(got["3B"], {"g": 390, "gs": 373})   # 312 MiLB + 78 MLB

    def test_the_double_count_used_to_flip_the_resolved_position(self):
        self.assertEqual(fp.observed_position(fp.aggregate_career_splits(self.LUGO)), "3B")
        doubled = {"SS": {"g": 736, "gs": 728}, "3B": {"g": 702, "gs": 674}}
        self.assertEqual(fp.observed_position(doubled), "SS")   # the shipped artifact

    def test_a_rollup_only_player_is_kept_not_dropped(self):
        got = fp.aggregate_career_splits(
            [_split("SS", "Minors", 100, 99), _split("1B", "MLB", 5, 4)])
        self.assertEqual(got, {"SS": {"g": 100, "gs": 99}, "1B": {"g": 5, "gs": 4}})

    def test_mlb_only_player_is_unaffected(self):
        got = fp.aggregate_career_splits([_split("CF", "MLB", 140, 138)])
        self.assertEqual(got, {"CF": {"g": 140, "gs": 138}})

    def test_malformed_splits_do_not_raise(self):
        got = fp.aggregate_career_splits(
            [{"stat": {}}, {"position": {"abbreviation": ""}},
             _split("SS", "A", "x", None), _split("SS", "A", 10, 9)])
        self.assertEqual(got["SS"], {"g": 10, "gs": 9})


class TestTheOldCensusIsUntouched(unittest.TestCase):
    """This lane is additive. The shipped versa artifact and its resolver keep
    their exact behaviour, because the versa chip and _up_mid_share_map are
    legitimate present-day reads."""

    def test_the_pre_debut_builders_signature_and_defaults_are_unchanged(self):
        import inspect
        sig = inspect.signature(fp.build_positions_played)
        self.assertEqual(sig.parameters["out_path"].default,
                         "data/positions_played.json")
        self.assertEqual(fp.VERSA_MIN_GAMES, 10)
        self.assertEqual(fp.VERSA_MIN_STARTS, 5)

    def test_observed_position_still_reads_the_career_dict_form(self):
        self.assertEqual(
            fp.observed_position({"SS": {"g": 100, "gs": 99}, "DH": {"g": 200, "gs": 200}}),
            "SS")


class TestEfvModelReadsTheAsOfCensus(unittest.TestCase):
    """The 2026-08-07 repoint (LANE P, docs/efv-pos-census-repoint-2026-08-07/).

    efv_model used to resolve the observed position out of
    data/positions_played.json, which is career-to-BUILD-DATE and pre-debut
    scoped. Measured on the current hitter matrix, the career read disagrees with
    the as-of read on 18.8% of bound training rows and the median row has 63% of
    its career fielding games AFTER its own decision date. What is pinned here is
    the SHAPE of the fix, not the coverage number: the model asks the census a
    DATED question, a row that cannot answer it degrades to its listed position,
    and none of it can fire while the flag is off.
    """

    # SS through 2023, then a move to 1B. A 2024 decision must see the SS.
    CENSUS = {"111": {"2022": {"SS": [80, 78]}, "2023": {"SS": [90, 88]},
                      "2024": {"1B": [120, 118]}, "2025": {"1B": [130, 128]}}}

    def _model(self):
        import efv_model as em
        em._SEASON_CENSUS_CACHE = dict(self.CENSUS)
        em._OBSERVED_POS_CACHE = None
        return em

    def tearDown(self):
        import efv_model as em
        em._SEASON_CENSUS_CACHE = None
        em._OBSERVED_POS_CACHE = None
        em.POS_PREMIUM_USES_OBSERVED = False

    def test_the_flag_is_still_off(self):
        import efv_model as em
        self.assertFalse(em.POS_PREMIUM_USES_OBSERVED)

    def test_as_of_read_ignores_seasons_after_the_decision(self):
        em = self._model()
        row = {"player_key": "x", "mlbam_id": 111, "asof_date": "2024-01-22"}
        self.assertEqual(em._observed_pos_as_of(row), "SS")

    def test_a_later_decision_sees_the_move(self):
        em = self._model()
        row = {"player_key": "x", "mlbam_id": 111, "asof_date": "2026-02-01"}
        self.assertEqual(em._observed_pos_as_of(row), "1B")

    def test_a_row_with_no_id_or_no_date_is_no_observation_not_a_career_total(self):
        em = self._model()
        self.assertIsNone(em._observed_pos_as_of(
            {"player_key": "x", "asof_date": "2024-01-22"}))
        self.assertIsNone(em._observed_pos_as_of(
            {"player_key": "x", "mlbam_id": 111}))
        self.assertIsNone(em._observed_pos_as_of(
            {"player_key": "x", "mlbam_id": 111, "asof_date": "not-a-date"}))

    def test_an_id_outside_the_census_is_no_observation(self):
        em = self._model()
        self.assertIsNone(em._observed_pos_as_of(
            {"player_key": "x", "mlbam_id": 999, "asof_date": "2024-01-22"}))

    def test_the_deprecated_player_key_map_is_empty_by_default(self):
        em = self._model()
        self.assertEqual(em._observed_pos_map(), {})

    def test_the_model_no_longer_reads_the_pre_debut_artifact(self):
        """The whole defect in one assertion: a career-to-build-date map keyed by
        player_key must not be able to reach pos_prem any more. Asserted on the
        EXECUTABLE body (the docstring still names the artifact it retired) and
        again behaviourally, by making the old loader fatal."""
        import inspect
        import efv_model as em
        # Cut the docstring out by delimiter. __doc__ is not usable for this:
        # Python 3.13 dedents docstrings at compile time, so it no longer matches
        # the text inspect.getsource returns.
        head, _, rest = inspect.getsource(em._observed_pos_map).partition('"""')
        body = head + rest.partition('"""')[2]
        self.assertNotIn("load_observed_positions", body)
        self.assertNotIn("positions_played.json", body)

        def _boom(*a, **k):
            raise AssertionError("efv_model reached the pre-debut census")
        orig = fp.load_observed_positions
        fp.load_observed_positions = _boom
        try:
            em._OBSERVED_POS_CACHE = None
            self.assertEqual(em._observed_pos_map(), {})
        finally:
            fp.load_observed_positions = orig

    def test_pos_prem_prefers_the_as_of_census_when_the_flag_is_on(self):
        em = self._model()
        row = {"player_key": "x", "mlbam_id": 111, "asof_date": "2024-01-22",
               "position": "1B"}                      # listed 1B, observed SS
        self.assertEqual(em._pos_premium(row["position"], "hit"), 0.0)
        em.POS_PREMIUM_USES_OBSERVED = True
        self.assertEqual(em._pos_premium_for_row(row, "hit"), 1.0)

    def test_pos_prem_falls_back_to_the_listed_position_with_no_observation(self):
        em = self._model()
        row = {"player_key": "x", "mlbam_id": 999, "asof_date": "2024-01-22",
               "position": "SS"}
        em.POS_PREMIUM_USES_OBSERVED = True
        self.assertEqual(em._pos_premium_for_row(row, "hit"), 1.0)

    def test_the_flag_off_is_an_exact_no_op_even_where_the_census_disagrees(self):
        em = self._model()
        for pos in ("1B", "SS", None, "SS/2B", "3B"):
            row = {"player_key": "x", "mlbam_id": 111, "asof_date": "2024-01-22",
                   "position": pos}
            for side in ("hit", "pit"):
                self.assertEqual(em._pos_premium_for_row(row, side),
                                 em._pos_premium(pos, side))

    def test_pitchers_are_never_repointed(self):
        em = self._model()
        em.POS_PREMIUM_USES_OBSERVED = True
        row = {"player_key": "x", "mlbam_id": 111, "asof_date": "2024-01-22",
               "position": "RP"}
        self.assertEqual(em._pos_premium_for_row(row, "pit"), 0.0)

    def test_a_missing_census_file_degrades_and_never_raises(self):
        import efv_model as em
        em._SEASON_CENSUS_CACHE = None
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "nope.json"
            self.assertEqual(fp.load_season_census(missing), {})
        em._SEASON_CENSUS_CACHE = {}
        em.POS_PREMIUM_USES_OBSERVED = True
        row = {"player_key": "x", "mlbam_id": 111, "asof_date": "2024-01-22",
               "position": "3B"}
        self.assertEqual(em._pos_premium_for_row(row, "hit"), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
