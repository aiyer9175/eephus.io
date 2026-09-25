# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the ETA model — specifically the H1/H2 (pre / post All-Star
break) refinement.

The half-season-elapsed adjustment subtracts ~0.25 years from the ETA
when the snapshot is post-All-Star-break, because the prospect has
effectively consumed half of their current level's regular season by
that point.
"""

from __future__ import annotations

import unittest
from datetime import date

from eta import (
    ALL_STAR_BREAK_DAY,
    ALL_STAR_BREAK_MONTH,
    HALF_SEASON_ADJ,
    estimate_eta,
    season_phase,
)


class SeasonPhase(unittest.TestCase):
    def test_pre_break_in_april(self):
        self.assertEqual(season_phase(date(2026, 4, 15)), "pre_break")

    def test_pre_break_through_jul_14(self):
        # Jul 14 — one day before the break cutoff.
        self.assertEqual(season_phase(date(2026, 7, 14)), "pre_break")

    def test_post_break_on_boundary_day(self):
        # Boundary day (Jul 15) is INCLUSIVE — already post-break.
        self.assertEqual(season_phase(date(2026, 7, 15)), "post_break")

    def test_post_break_in_august(self):
        self.assertEqual(season_phase(date(2026, 8, 20)), "post_break")

    def test_post_break_through_october(self):
        # Postseason still counts as "post_break" (in-season window).
        self.assertEqual(season_phase(date(2026, 10, 12)), "post_break")

    def test_offseason_nov_dec(self):
        self.assertEqual(season_phase(date(2026, 11, 15)), "offseason")
        self.assertEqual(season_phase(date(2026, 12, 30)), "offseason")

    def test_offseason_jan_feb(self):
        self.assertEqual(season_phase(date(2027, 1, 20)), "offseason")
        self.assertEqual(season_phase(date(2027, 2, 28)), "offseason")

    def test_string_input_accepted(self):
        # ISO string input → parsed.
        self.assertEqual(season_phase("2026-06-10"), "pre_break")
        self.assertEqual(season_phase("2026-08-20"), "post_break")
        self.assertEqual(season_phase("2026-12-15"), "offseason")

    def test_none_defaults_to_pre_break(self):
        # None / empty → conservative "pre_break" default so old
        # callers don't accidentally fire the H1/H2 adjustment.
        self.assertEqual(season_phase(None), "pre_break")
        self.assertEqual(season_phase(""), "pre_break")

    def test_boundary_constants_match_docstring(self):
        self.assertEqual(ALL_STAR_BREAK_MONTH, 7)
        self.assertEqual(ALL_STAR_BREAK_DAY, 15)


class HalfSeasonAdjustment(unittest.TestCase):
    """The H1/H2 split is the only difference between two otherwise
    identical estimate_eta calls. Verifying the adjustment fires
    correctly + only post-break."""

    def _aaa_hitter_payload(self):
        # Standard AAA hitter, no stats / no health stuff — pure
        # base-years + age path.
        return dict(
            current_level="AAA",
            age=22.0,
            is_pitcher=False,
            fv=55.0,
            stats=None,
        )

    def test_pre_break_zero_adj(self):
        r = estimate_eta(snapshot_date=date(2026, 4, 15),
                         **self._aaa_hitter_payload())
        self.assertEqual(r.half_season_adj, 0.0)
        self.assertEqual(r.season_phase, "pre_break")

    def test_post_break_negative_adj(self):
        r = estimate_eta(snapshot_date=date(2026, 8, 20),
                         **self._aaa_hitter_payload())
        self.assertEqual(r.half_season_adj, HALF_SEASON_ADJ)
        self.assertLess(r.half_season_adj, 0)
        self.assertEqual(r.season_phase, "post_break")

    def test_offseason_zero_adj(self):
        # December — level cycle naturally rolls into next regular
        # season; no half-season adjustment.
        r = estimate_eta(snapshot_date=date(2026, 12, 15),
                         **self._aaa_hitter_payload())
        self.assertEqual(r.half_season_adj, 0.0)
        self.assertEqual(r.season_phase, "offseason")

    def test_post_break_pulls_eta_in(self):
        # All else equal, the post-break ETA must be ≤ the pre-break
        # ETA (in years) — the half-season elapsed shrinks the
        # remaining travel time.
        pre  = estimate_eta(snapshot_date=date(2026, 4, 15), **self._aaa_hitter_payload())
        post = estimate_eta(snapshot_date=date(2026, 8, 20), **self._aaa_hitter_payload())
        self.assertLessEqual(post.eta_year, pre.eta_year)
        # The half-season-adj field should be the only delta.
        self.assertEqual(pre.base_years, post.base_years)
        self.assertEqual(pre.perf_adj, post.perf_adj)
        self.assertEqual(pre.age_adj, post.age_adj)
        self.assertEqual(pre.fv_adj, post.fv_adj)

    def test_mlb_player_returns_today_with_phase(self):
        # MLB players short-circuit; still surface the phase + 0 adj
        # so the frontend can render the eyebrow consistently.
        r = estimate_eta(
            current_level="MLB", age=24.0, is_pitcher=False, fv=55.0,
            stats=None, snapshot_date=date(2026, 8, 20),
        )
        self.assertEqual(r.half_season_adj, 0.0)
        self.assertEqual(r.season_phase, "post_break")
        self.assertEqual(r.eta_year, date.today().year)

    def test_snapshot_date_defaults_to_pre_break(self):
        # Backward-compat: existing callers that don't pass
        # snapshot_date get the pre-break baseline (no adj).
        r = estimate_eta(**self._aaa_hitter_payload())
        self.assertEqual(r.half_season_adj, 0.0)
        self.assertEqual(r.season_phase, "pre_break")


class CalendarFloor(unittest.TestCase):
    """The eta_half bucket must never point at a sub-year window that has
    already passed at compute time: post-break, a current-year "early"
    (Apr-Jun) floors to "late"; in Nov/Dec a current-year ETA rolls to
    next year's early window; Jan/Feb leaves current-year "early" alone."""

    def _mlb_ready_payload(self):
        # base_years pinned to 0 → travel time rounds to a current-year
        # ETA and the sub-0.01 total forces the pre-clamp bucket to
        # "early" — isolating the calendar floor itself.
        return dict(
            current_level="AAA",
            age=24.0,
            is_pitcher=False,
            fv=55.0,
            stats=None,
            base_years={"AAA": 0.0},
        )

    def test_pre_break_keeps_early(self):
        r = estimate_eta(snapshot_date=date(2026, 4, 15),
                         **self._mlb_ready_payload())
        self.assertEqual(r.eta_year, date.today().year)
        self.assertEqual(r.eta_half, "early")

    def test_post_break_floors_current_year_to_late(self):
        r = estimate_eta(snapshot_date=date(2026, 8, 20),
                         **self._mlb_ready_payload())
        self.assertEqual(r.eta_year, date.today().year)
        self.assertEqual(r.eta_half, "late")

    def test_nov_dec_rolls_current_year_forward(self):
        # Season over — a current-year debut can no longer happen.
        r = estimate_eta(snapshot_date=date(2026, 11, 15),
                         **self._mlb_ready_payload())
        self.assertEqual(r.eta_year, date.today().year + 1)
        self.assertEqual(r.eta_half, "early")

    # Census M01-05 (2026-09-24): after the MLB regular season ends the season is
    # over, so a current-year ETA rolls to next year's early window, not in November.
    # Dates sit in the current year because the roll only fires when the snapshot and
    # the season end are both in the compute year (a backtest vintage never trips it).
    def test_after_regular_season_end_rolls_current_year_forward(self):
        y = date.today().year
        r = estimate_eta(snapshot_date=date(y, 9, 28), regular_season_end=date(y, 9, 27),
                         **self._mlb_ready_payload())
        self.assertEqual(r.eta_year, y + 1)
        self.assertEqual(r.eta_half, "early")
        self.assertTrue(r.season_end_roll)
        r = estimate_eta(snapshot_date=date(y, 10, 12), regular_season_end="%d-09-27" % y,
                         **self._mlb_ready_payload())
        self.assertEqual((r.eta_year, r.eta_half), (y + 1, "early"))

    def test_on_or_before_regular_season_end_keeps_late(self):
        y = date.today().year
        for d in (date(y, 9, 23), date(y, 9, 27)):
            r = estimate_eta(snapshot_date=d, regular_season_end=date(y, 9, 27),
                             **self._mlb_ready_payload())
            self.assertEqual((r.eta_year, r.eta_half), (y, "late"), d)
            self.assertFalse(r.season_end_roll)

    def test_no_season_end_keeps_the_old_floor(self):
        # eta_backtest passes no regular_season_end: an October snapshot keeps
        # current-year late, exactly as before the rule.
        y = date.today().year
        r = estimate_eta(snapshot_date=date(y, 10, 12), **self._mlb_ready_payload())
        self.assertEqual((r.eta_year, r.eta_half), (y, "late"))
        self.assertFalse(r.season_end_roll)

    def test_season_end_in_another_year_never_rolls(self):
        # A vintage snapshot from an earlier season is not "past this season's end".
        y = date.today().year
        r = estimate_eta(snapshot_date=date(y - 3, 10, 5),
                         regular_season_end=date(y - 3, 9, 29),
                         **self._mlb_ready_payload())
        self.assertEqual((r.eta_year, r.eta_half), (y, "late"))

    def test_the_aa_teenager_case(self):
        # The census row: a 19-year-old AA hitter whose ETA lands in the current
        # year (base years pinned to 0 so it does) reads next year's early window
        # once the regular season is over.
        y = date.today().year
        r = estimate_eta(current_level="AA", age=19.4, is_pitcher=False, fv=65.0,
                         stats=None, base_years={"AA": 0.0},
                         snapshot_date=date(y, 9, 30), regular_season_end=date(y, 9, 27))
        self.assertEqual((r.eta_year, r.eta_half), (y + 1, "early"))

    def test_jan_feb_offseason_not_rolled(self):
        # Jan/Feb offseason: April is still ahead — "early <current
        # year>" is legitimate.
        r = estimate_eta(snapshot_date=date(2027, 1, 20),
                         **self._mlb_ready_payload())
        self.assertEqual(r.eta_year, date.today().year)
        self.assertEqual(r.eta_half, "early")


class OrgPromotionTendency(unittest.TestCase):
    """Per-org H1/H2 promotion tendency scales the half-season ETA
    adjustment. H2-heavy orgs (≥60% promotions post-ASB) get a
    stronger pull-in; H1-heavy (≥70% pre-ASB) get a softer one."""

    def _aaa_hitter(self):
        return dict(
            current_level="AAA",
            age=22.0,
            is_pitcher=False,
            fv=55.0,
            stats=None,
        )

    def test_h2_heavy_org_pulls_in_harder_post_break(self):
        # 30 promotions, 25 in H2 (h2_rate=0.83). Post-break → ×1.4
        # multiplier on the -0.25 baseline → -0.35.
        tend = {"h1_rate": 0.17, "h2_rate": 0.83, "sample_n": 30}
        r = estimate_eta(snapshot_date=date(2026, 8, 20),
                         org_promotion_tendency=tend,
                         **self._aaa_hitter())
        self.assertAlmostEqual(r.half_season_adj, -0.35, places=2)
        self.assertEqual(r.org_promo_weight, 1.4)

    def test_h1_heavy_org_softens_post_break(self):
        # 20 promotions, 17 in H1 (h1_rate=0.85). Post-break → ×0.6
        # → -0.25 × 0.6 = -0.15.
        tend = {"h1_rate": 0.85, "h2_rate": 0.15, "sample_n": 20}
        r = estimate_eta(snapshot_date=date(2026, 8, 20),
                         org_promotion_tendency=tend,
                         **self._aaa_hitter())
        self.assertAlmostEqual(r.half_season_adj, -0.15, places=2)
        self.assertEqual(r.org_promo_weight, 0.6)

    def test_balanced_org_no_change(self):
        # 50/50 split → no deviation from baseline.
        tend = {"h1_rate": 0.50, "h2_rate": 0.50, "sample_n": 20}
        r = estimate_eta(snapshot_date=date(2026, 8, 20),
                         org_promotion_tendency=tend,
                         **self._aaa_hitter())
        self.assertAlmostEqual(r.half_season_adj, -0.25, places=2)
        self.assertEqual(r.org_promo_weight, 1.0)

    def test_h2_heavy_org_pushes_back_pre_break(self):
        # Pre-break + H2-heavy → +0.10 push-back (prospect even less
        # likely to debut before the break than baseline).
        tend = {"h1_rate": 0.17, "h2_rate": 0.83, "sample_n": 30}
        r = estimate_eta(snapshot_date=date(2026, 6, 1),
                         org_promotion_tendency=tend,
                         **self._aaa_hitter())
        self.assertAlmostEqual(r.half_season_adj, 0.10, places=2)
        self.assertEqual(r.season_phase, "pre_break")

    def test_sparse_sample_falls_back_to_neutral(self):
        # <5 promotions on file → ignore the tendency, use league
        # baseline. Post-break w/ 3-sample tendency stays at -0.25.
        tend = {"h1_rate": 0.00, "h2_rate": 1.00, "sample_n": 3}
        r = estimate_eta(snapshot_date=date(2026, 8, 20),
                         org_promotion_tendency=tend,
                         **self._aaa_hitter())
        self.assertAlmostEqual(r.half_season_adj, -0.25, places=2)
        self.assertEqual(r.org_promo_weight, 1.0)

    def test_no_tendency_arg_works(self):
        # Backward-compat: existing callers that don't pass
        # org_promotion_tendency still work.
        r = estimate_eta(snapshot_date=date(2026, 8, 20),
                         **self._aaa_hitter())
        self.assertEqual(r.org_promo_weight, 1.0)
        self.assertIsNone(r.org_promo_h1_rate)
        self.assertIsNone(r.org_promo_h2_rate)



class SeasonEndWiring(unittest.TestCase):
    """The live timeseries caller passes the season end; the backtest does not."""

    def test_live_caller_passes_it_and_backtest_does_not(self):
        from pathlib import Path
        here = Path(__file__).resolve().parent
        storage_src = (here / "storage.py").read_text(encoding="utf-8")
        self.assertIn("regular_season_end=_eta_season_end", storage_src)
        self.assertIn('"season_end_roll":', storage_src)
        bt = here / "eta_backtest.py"
        if bt.exists():
            self.assertNotIn("regular_season_end", bt.read_text(encoding="utf-8"))

class FanGraphsBlendArm(unittest.TestCase):
    """ETA_FG_BLEND_ARM (registered 2026-09-25, docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md).

    Default off, fixed constants, and the two arms' exact arithmetic."""

    def test_flag_defaults_off_and_constants_are_the_registered_ones(self):
        import eta
        self.assertIsNone(eta.ETA_FG_BLEND_ARM)
        self.assertEqual(eta.FG_BLEND_ARMS, ("A", "B"))
        self.assertEqual(eta.FG_BLEND_WEIGHT, 0.5)
        self.assertEqual(eta.FG_BLEND_FORTYMAN_SHIFT, 1)

    def test_round_half_up_not_bankers(self):
        from eta import round_half_up
        self.assertEqual(round_half_up(2026.5), 2027)
        self.assertEqual(round_half_up(2024.5), 2025)   # banker's round gives 2024
        self.assertEqual(round_half_up(2025.49), 2025)

    def test_arm_a_is_the_rounded_midpoint_floored(self):
        from eta import fg_blend_eta_year
        self.assertEqual(fg_blend_eta_year(2029, 2026, 2024, arm="A"), 2028)   # 2027.5 up
        self.assertEqual(fg_blend_eta_year(2028, 2026, 2024, arm="A"), 2027)
        self.assertEqual(fg_blend_eta_year(2026, 2026, 2024, arm="A"), 2026)
        # FanGraphs later than the champion pulls later
        self.assertEqual(fg_blend_eta_year(2025, 2028, 2024, arm="A"), 2027)
        # never before the floor year
        self.assertEqual(fg_blend_eta_year(2024, 2022, 2024, arm="A"), 2024)
        # the 40-man flag does nothing in arm A
        self.assertEqual(fg_blend_eta_year(2028, 2026, 2024, on40=True, arm="A"), 2027)

    def test_arm_b_shifts_forty_man_rows_one_year_then_floors(self):
        from eta import fg_blend_eta_year
        self.assertEqual(fg_blend_eta_year(2028, 2026, 2024, on40=True, arm="B"), 2026)
        self.assertEqual(fg_blend_eta_year(2028, 2026, 2024, on40=False, arm="B"), 2027)
        self.assertEqual(fg_blend_eta_year(2025, 2024, 2024, on40=True, arm="B"), 2024)

    def test_no_fangraphs_year_keeps_the_champion(self):
        from eta import fg_blend_eta_year
        self.assertEqual(fg_blend_eta_year(2029, None, 2024, on40=True, arm="B"), 2029)
        self.assertIsNone(fg_blend_eta_year(None, 2026, 2024, arm="A"))

    def test_unknown_arm_raises(self):
        from eta import fg_blend_eta_year
        with self.assertRaises(ValueError):
            fg_blend_eta_year(2028, 2026, 2024, arm="C")

    def test_fg_year_only_from_a_current_fangraphs_entry(self):
        from eta import fg_eta_year_from_per_source as f
        ok = {"fangraphs": {"dropped_off": False, "tools": {"_extras": {"eta_year": 2027}}}}
        self.assertEqual(f(ok), 2027)
        self.assertEqual(f({"fangraphs": {"tools": {"_extras": {"eta_year": "2028"}}}}), 2028)
        self.assertEqual(f({"fangraphs": {"tools": {"_extras": {"eta_year": 2028.0}}}}), 2028)
        dropped = {"fangraphs": {"dropped_off": True, "tools": {"_extras": {"eta_year": 2027}}}}
        self.assertIsNone(f(dropped))
        self.assertIsNone(f({"mlb": {"tools": {"_extras": {"eta_year": 2027}}}}))
        self.assertIsNone(f({"fangraphs": {"tools": {"_extras": {"eta_year": ""}}}}))
        self.assertIsNone(f({"fangraphs": {"tools": {"_extras": {"eta_year": "late"}}}}))
        self.assertIsNone(f({"fangraphs": {"tools": {"_extras": {"eta_year": 2027.5}}}}))
        self.assertIsNone(f({"fangraphs": {"tools": None}}))
        self.assertIsNone(f(None))

    def test_live_floor_year_rolls_after_the_season(self):
        from eta import live_floor_year
        self.assertEqual(live_floor_year(date(2026, 8, 1), "2026-09-27", 2026), 2026)
        self.assertEqual(live_floor_year(date(2026, 9, 28), "2026-09-27", 2026), 2027)
        self.assertEqual(live_floor_year(date(2026, 9, 28), None, 2026), 2026)
        self.assertEqual(live_floor_year(date(2026, 11, 3), None, 2026), 2027)

    def test_apply_is_identity_while_the_flag_is_off(self):
        from eta import apply_fg_blend
        r = estimate_eta("AA", 22.0, False, 50, {"ops": ".750"}, snapshot_date=date(2026, 4, 10))
        self.assertIs(apply_fg_blend(r, 2030, arm=None, floor_year=2026), r)
        self.assertIsNone(r.fg_blend_arm)
        self.assertIsNone(r.champion_eta_year)

    def test_apply_without_a_fangraphs_year_keeps_the_champion(self):
        from eta import apply_fg_blend
        r = estimate_eta("AA", 22.0, False, 50, {"ops": ".750"}, snapshot_date=date(2026, 4, 10))
        self.assertIs(apply_fg_blend(r, None, arm="A", floor_year=2026), r)

    def test_apply_serves_the_arm_and_keeps_the_champion_year(self):
        from eta import apply_fg_blend, fg_blend_eta_year
        r = estimate_eta("A", 20.0, False, 45, None, snapshot_date=date(2026, 4, 10))
        fg = r.eta_year - 2
        floor = date.today().year
        out = apply_fg_blend(r, fg, arm="B", on40=True, floor_year=floor)
        self.assertEqual(out.eta_year, fg_blend_eta_year(r.eta_year, fg, floor, on40=True, arm="B"))
        self.assertEqual(out.champion_eta_year, r.eta_year)
        self.assertEqual(out.fg_eta_year, fg)
        self.assertEqual(out.fg_blend_arm, "B")
        self.assertEqual(out.base_years, r.base_years)

    def test_live_caller_is_guarded_by_the_flag(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parent / "storage.py").read_text(encoding="utf-8")
        self.assertIn("if _eta_mod.ETA_FG_BLEND_ARM is not None:", src)
        self.assertIn("fg_eta_year_from_per_source(", src)
        # the served JSON gains blend keys only when a blend was served
        self.assertIn('if getattr(eta, "fg_blend_arm", None) else {})', src)


class OrgPromotionTendencies(unittest.TestCase):
    """eta.org_promotion_tendencies: the served computation (moved out of storage.py
    2026-09-25) and the point-in-time filters the org keep-or-remove gate uses."""

    @staticmethod
    def _events(dates, kind="promotion"):
        return [{"kind": kind, "date": d} for d in dates]

    def test_served_rules(self):
        from eta import org_promotion_tendencies
        lc = {
            "a": self._events(["2025-04-10", "2025-05-10", "2025-08-01"]),
            "b": self._events(["2025-07-20", "2025-08-20"], kind="debut"),
            "c": self._events(["2025-12-01", "2025-06-01"], kind="demotion"),   # skipped
            "d": self._events(["2025-01-15"]),                                   # offseason
        }
        orgs = {"a": "TBR", "b": "TBR", "c": "TBR", "d": "TBR"}
        out = org_promotion_tendencies(lc, orgs, min_year=2023)
        self.assertEqual(out["TBR"]["sample_n"], 5)
        self.assertEqual(out["TBR"]["h2_rate"], 0.6)
        self.assertEqual(out["TBR"]["h1_rate"], 0.4)
        self.assertEqual(out["TBR"]["aggressiveness_index"], 1.0)

    def test_thin_orgs_and_orgless_players_are_skipped(self):
        from eta import org_promotion_tendencies
        lc = {"a": self._events(["2025-04-10"] * 4), "b": self._events(["2025-04-10"] * 9)}
        out = org_promotion_tendencies(lc, {"a": "SEA"}, min_year=2023)
        self.assertEqual(out, {})

    def test_point_in_time_filters(self):
        from eta import org_promotion_tendencies
        lc = {"a": self._events(["2021-05-01"] * 6 + ["2022-05-01"] * 5 + ["2024-05-01"] * 7)}
        orgs = {"a": "SEA"}
        out = org_promotion_tendencies(lc, orgs, before="2024-03-01", seasons={2022, 2023})
        self.assertEqual(out["SEA"]["sample_n"], 5)
        out = org_promotion_tendencies(lc, orgs, before="2024-03-01")
        self.assertEqual(out["SEA"]["sample_n"], 11)

    def test_storage_serves_the_shared_function(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parent / "storage.py").read_text(encoding="utf-8")
        self.assertIn("from eta import org_promotion_tendencies as _org_tendencies", src)
        self.assertIn("min_year=_date.today().year - 3)", src)


if __name__ == "__main__":
    unittest.main()
