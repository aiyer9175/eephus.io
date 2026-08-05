"""R5.1 - the league-minimum ("prearb_min") salary basis on the trade board.

What these pin, and why each one is here:

  * the DISTINCT surplus_source. The whole point of pricing these rows was that
    they had been publishing as "unpriced" with a reason; if the basis were
    stamped "projection" like everything else, the census could not count them,
    the ledger could not drop them and nobody could filter them back out. The
    string is load-bearing, so it is pinned.
  * the NO-INVERSION invariant. Pre-arb is strictly cheaper than arbitration, so
    at one projection and one remaining-control window the league-minimum price
    can never sit below the arb price. This is the pre-registered gate for the
    change, and it is checked structurally (over a WAR sweep) rather than on one
    example, because one example passing is not the claim.
  * that the salary basis really IS the league minimum. A test that only checked
    "some number came out" would have passed just as happily against the arb
    ladder, which is the exact mistake that makes a basis change invisible.

Style follows test_bayes_trade_value_policy.py; the cases are unittest.TestCase
because the fixtures need a temp data directory and this file is run with
`python -m unittest`.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import bayes_trade_value as btv
import value_framework as vf
from proj_export import _season_value_usd


FIRST = 2027
DPW = 15_000_000.0
ROS = 0.30
HORIZON = 5


def _war(w: float) -> list[float]:
    return [w] * HORIZON


def _vet(key, war, **extra):
    row = {"key": key, "name": key.replace("_", " ").title(), "age": 24,
           "src": "vet", "pos": "H", "team": "TST", "war": list(war),
           "warP10": [x - 1.0 for x in war], "warP90": [x + 1.0 for x in war],
           "warTotal": round(sum(war), 1)}
    row.update(extra)
    return row


def _career(*years):
    return [{"y": y, "pa": 400, "war": 1.0} for y in years]


class _Fixture:
    """A minimal data/ directory: four artifacts, written to a temp dir.

    Nothing here touches the real data/ tree. `floor_filler` exists so the
    career-block floor season is pinned at 2014 - without it the earliest season
    any test player has would BE the floor, and `_prearb_service_seasons`
    correctly refuses to bound a count that may have been truncated."""

    def __init__(self, vets, detail, phases=None, xfv=None):
        self.dir = Path(tempfile.mkdtemp(prefix="prearb_"))
        (self.dir / "mlb_projections.json").write_text(json.dumps({
            "first_season": FIRST, "horizon": HORIZON, "dpw_usd": DPW,
            "ros_fraction": ROS, "vets": vets, "prospects": [],
        }), encoding="utf-8")
        det = dict(detail)
        det.setdefault("floor_filler", {"key": "floor_filler",
                                        "career": _career(2014)})
        (self.dir / "mlb_player_detail.json").write_text(
            json.dumps({"players": det}), encoding="utf-8")
        (self.dir / "debuts.json").write_text(json.dumps({"players": [
            {"player_key": k, "roster_status": {"service_phase": v}}
            for k, v in (phases or {}).items()]}), encoding="utf-8")
        (self.dir / "xfv.json").write_text(
            json.dumps({"by_player": xfv or {}}), encoding="utf-8")

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def _league_min_total(war, n_seasons, ros=True):
    """The league-minimum price of a WAR path over `n_seasons`, plus the balance
    of the season in progress. Written out longhand rather than imported so the
    test states the arithmetic it is checking instead of re-running it."""
    lm = btv._league_min_usd_fn()
    disc = float(vf._config()["discount_rate"])
    total = 0.0
    for t in range(n_seasons):
        total += (_season_value_usd(war[t], t, DPW) - lm(FIRST + t)) / ((1.0 + disc) ** t)
    if ros:
        # 2026-08-04d convention: the RoS leg prorates the full-season SURPLUS,
        # f * (V(w) - salary), not V(f*w) - f*salary. Pricing V(f*w) charged the
        # remainder a lower per-win tier than the season it is part of.
        total += ROS * (_season_value_usd(war[0], 0, DPW) - lm(FIRST - 1))
    return total


def _arb_total(war, n_seasons, ros=True):
    """The same path over the same window on the ARBITRATION ladder - the
    comparator the no-inversion gate is stated against. Held at ARB-1, the
    cheapest arbitration year there is, so the comparison is the hardest one the
    invariant has to survive."""
    st = vf._config()["service_time"]
    _pre_arb, fracs = vf._arb_ladder(st, False)
    lm = btv._league_min_usd_fn()
    disc = float(vf._config()["discount_rate"])
    total = 0.0
    for t in range(n_seasons):
        mkt = _season_value_usd(war[t], t, DPW)
        i = min(t, len(fracs) - 1)
        sal = max(lm(FIRST + t), fracs[i] * mkt)
        total += (mkt - sal) / ((1.0 + disc) ** t)
    if ros:
        # Same 2026-08-04d full-season-surplus proration as _league_min_total,
        # so the two bases stay comparable leg for leg.
        mkt0 = _season_value_usd(war[0], 0, DPW)
        total += ROS * (mkt0 - max(lm(FIRST - 1), fracs[0] * mkt0))
    return total


# ── the distinct basis stamp ─────────────────────────────────────────────────
class PreArbSourceStamp(unittest.TestCase):

    def setUp(self):
        self.fx = _Fixture(
            vets=[_vet("rookie_a", _war(2.0))],
            detail={"rookie_a": {"key": "rookie_a", "career": _career(2026)}},
        )

    def tearDown(self):
        self.fx.close()

    def test_priced_row_carries_the_prearb_source_not_projection(self):
        records: list = []
        stats = btv.apply_platform_surplus(records, self.fx.dir)
        row = next(r for r in records if r["player_key"] == "rookie_a")
        self.assertEqual(row["surplus_source"], "prearb_min")
        self.assertEqual(btv._PREARB_SOURCE, "prearb_min")
        # It must NOT masquerade as a contract-priced projection row: the census
        # and the ledger both key off this string.
        self.assertNotEqual(row["surplus_source"], "projection")
        self.assertEqual(stats["prearb_min"], 1)

    def test_the_salary_assumption_travels_with_the_row(self):
        records: list = []
        btv.apply_platform_surplus(records, self.fx.dir)
        meta = next(r for r in records if r["player_key"] == "rookie_a")["prearb"]
        self.assertEqual(meta["basis"], "league_minimum")
        self.assertEqual(meta["service_seasons_est"], 1)
        self.assertEqual(meta["service_source"], "mlb_appearance_seasons_proxy")
        self.assertEqual(meta["prearb_seasons_priced"], 2)   # pre_arb_years - 1
        self.assertTrue(meta["rest_of_season_priced"])

    def test_the_row_goes_through_the_same_tier_grade_and_band_logic(self):
        records: list = []
        btv.apply_platform_surplus(records, self.fx.dir)
        row = next(r for r in records if r["player_key"] == "rookie_a")
        mm = row["trade_value_mm"]
        self.assertEqual(row["trade_value_tier"], btv._platform_tier(mm))
        self.assertEqual(row["trade_value_grade"], btv._trade_value_grade(mm))
        self.assertEqual(row["posterior_surplus_mm"], mm)
        # The projection fan brackets it: a flat league minimum cancels out of a
        # p10-p90 difference exactly the way a contractual salary does.
        self.assertIsNotNone(row["trade_value_lo"])
        self.assertLess(row["trade_value_lo"], mm)
        self.assertGreater(row["trade_value_hi"], mm)


# ── the salary basis is the league minimum, not the arb ladder ───────────────
class PreArbSalaryBasis(unittest.TestCase):

    def setUp(self):
        # 4 WAR: high enough that the arb fraction of market clears the league
        # minimum by an order of magnitude, so the two bases cannot be confused.
        self.fx = _Fixture(
            vets=[_vet("good_rookie", _war(4.0))],
            detail={"good_rookie": {"key": "good_rookie", "career": _career(2026)}},
        )

    def tearDown(self):
        self.fx.close()

    def test_value_equals_the_league_minimum_construction(self):
        rows = btv._prearb_priced(self.fx.dir)
        got = rows["good_rookie"]["surTotal"]
        self.assertAlmostEqual(got, _league_min_total(_war(4.0), 2), delta=2.0)

    def test_value_is_NOT_the_arbitration_construction(self):
        rows = btv._prearb_priced(self.fx.dir)
        got = rows["good_rookie"]["surTotal"]
        arb = _arb_total(_war(4.0), 2)
        # Not "close enough either way" - a real separation, because the arb
        # ladder charges a fraction of a large market and the minimum does not.
        self.assertGreater(got - arb, 10_000_000.0)

    def test_the_minimum_comes_from_the_config_and_is_not_hardcoded(self):
        lm = btv._league_min_usd_fn()
        table = vf._config()["league_min_by_year"]
        for y, mm in table.items():
            self.assertAlmostEqual(lm(int(y)), float(mm) * 1e6, delta=1.0)
        # A projected season past the table carries the LAST tabled year, which
        # is fresher than the flat service_time default it would otherwise use.
        last = max(int(y) for y in table)
        self.assertAlmostEqual(lm(last + 4), float(table[last]) * 1e6, delta=1.0)

    def test_per_season_salary_charged_is_exactly_one_league_minimum(self):
        rows = btv._prearb_priced(self.fx.dir)
        sur = rows["good_rookie"]["sur"]
        lm = btv._league_min_usd_fn()
        for t in (0, 1):
            gross = _season_value_usd(4.0, t, DPW)
            self.assertAlmostEqual(sur[t] * 1e6, gross - lm(FIRST + t), delta=60_000.0)
        self.assertEqual(sur[2:], [None, None, None])       # window is 2 seasons


# ── the pre-registered gate: no inversion against an arb-eligible comparator ──
class PreArbNoInversion(unittest.TestCase):
    """A pre-arb player with projection X and remaining control W must never
    price BELOW an arbitration-eligible player with the same X and the same W,
    because pre-arb is strictly cheaper. Swept over WAR and window rather than
    asserted on one row: the claim is about the pricing rule, not about a
    fixture."""

    def test_league_minimum_never_prices_below_arbitration(self):
        # THE PRE-ARB LEG COMES FROM PRODUCTION, DELIBERATELY.
        #
        # This test used to compare _league_min_total against _arb_total, i.e.
        # one local reimplementation against another, and it was ALGEBRAICALLY
        # VACUOUS. Both charge the same market value over the same window at the
        # same discount; the only difference is the salary, lm versus
        # max(lm, frac*mkt), and max(lm, x) >= lm term by term. Measured
        # 2026-08-04: 50,000 random WAR paths (war ~ U(-6, +12), window ~
        # U{0..5}) produced 0 inversions and a MINIMUM GAP OF EXACTLY $0.000000.
        # Nothing could have made it fail, including a production bug, because
        # production was never called.
        #
        # Now the pre-arb side is priced by btv._prearb_priced through a real
        # fixture, so a window, curve, discount or salary-basis regression in
        # the shipped path breaks this. The arb side stays longhand: it is the
        # comparator the gate is stated against, not the thing under test.
        # Window 0 is excluded on purpose, not for convenience: a player past
        # his pre-arb window is not priced on this basis AT ALL (the row comes
        # back carrying reason 'past_prearb_window' and no surTotal), so there
        # is no pre-arb price to invert. test_an_established_veteran_is_NOT_
        # priced_at_the_minimum owns that case.
        lengths = {1: _career(2025, 2026),           # 2 seasons -> window 1
                   2: _career(2026)}                 # 1 season  -> window 2
        inversions = []
        for w in (0.0, 0.3, 1.0, 2.0, 3.5, 5.0, 8.0):
            for n, career in sorted(lengths.items()):
                fx = _Fixture(vets=[_vet("p", _war(w))],
                              detail={"p": {"key": "p", "career": career}})
                try:
                    row = btv._prearb_priced(fx.dir).get("p") or {}
                finally:
                    fx.close()
                self.assertIn("surTotal", row,
                              f"production declined to price w={w} window={n}")
                mn, ab = float(row["surTotal"]), _arb_total(_war(w), n)
                if mn < ab - 1.0:
                    inversions.append((w, n, mn, ab))
        self.assertEqual(inversions, [], f"pre-arb priced below arb: {inversions}")

    def test_the_comparison_above_is_not_vacuous(self):
        """The guard on the guard: prove the production leg can actually move.

        If _prearb_priced ever stops pricing (returns nothing, or a zero), the
        test above would read 0.0 against a negative arb total for a
        sub-replacement player and still pass. Pin that the fixture really is
        producing a live, WAR-responsive price."""
        got = []
        for w in (1.0, 4.0):
            fx = _Fixture(vets=[_vet("p", _war(w))],
                          detail={"p": {"key": "p", "career": _career(2026)}})
            try:
                got.append(float(btv._prearb_priced(fx.dir)["p"]["surTotal"]))
            finally:
                fx.close()
        self.assertGreater(got[0], 0.0)
        self.assertGreater(got[1] - got[0], 10_000_000.0)

    def test_the_gap_is_strict_once_the_arb_fraction_binds(self):
        # At a low projection both bases pay the minimum and the two agree; at a
        # real projection the arb share of market binds and pre-arb must win.
        self.assertGreater(_league_min_total(_war(3.0), 3) - _arb_total(_war(3.0), 3),
                           1_000_000.0)

    def test_a_longer_window_is_worth_more_than_a_shorter_one(self):
        # The ordering the board reads. Guards against a window bug quietly
        # pricing more seasons as less value.
        totals = [_league_min_total(_war(2.5), n) for n in (0, 1, 2, 3)]
        self.assertEqual(totals, sorted(totals))


# ── who is, and is NOT, inside a pre-arb window ──────────────────────────────
class PreArbWindowSelection(unittest.TestCase):

    def setUp(self):
        self.fx = _Fixture(
            vets=[_vet("rookie_a", _war(2.0)),
                  _vet("grizzled_b", _war(2.0)),
                  _vet("bounced_c", _war(2.0)),
                  _vet("overcounted_e", _war(2.0)),
                  _vet("truncated_d", _war(2.0))],
            detail={
                "rookie_a": {"key": "rookie_a", "career": _career(2025, 2026)},
                # Eleven seasons on file: an established veteran whose Spotrac
                # row simply failed to join. His salary is UNKNOWN, not minimum.
                "grizzled_b": {"key": "grizzled_b",
                               "career": _career(*range(2016, 2027))},
                # FIVE appearance seasons and the roster feed says pre_arb: he
                # bounced through the minors, so the label still wins. Five is
                # deliberately just UNDER _PREARB_LABEL_OVERRIDE_MAX, so this
                # and overcounted_e pin the two sides of that boundary rather
                # than one arbitrary point. (Was six until 2026-08-04, when the
                # threshold was measured and landed exactly on six.)
                "bounced_c": {"key": "bounced_c",
                              "career": _career(*range(2022, 2027))},
                # EIGHT appearance seasons and the roster feed ALSO says
                # pre_arb. The label is wrong and the count wins. This is the
                # nestor_cortes / joel_payamps shape, both of which the label
                # was forcing into the priced set before the threshold landed.
                "overcounted_e": {"key": "overcounted_e",
                                  "career": _career(*range(2019, 2027))},
                # First season on file IS the career-block floor, so the count
                # may have been truncated and bounds nothing.
                "truncated_d": {"key": "truncated_d", "career": _career(2014, 2026)},
            },
            phases={"bounced_c": "pre_arb", "overcounted_e": "pre_arb",
                    "grizzled_b": "arb_eligible"},
        )

    def tearDown(self):
        self.fx.close()

    def test_a_recent_debut_is_priced(self):
        m = btv._prearb_priced(self.fx.dir)["rookie_a"]["prearb"]
        self.assertTrue(m["priced"])
        self.assertEqual(m["prearb_seasons_priced"], 1)

    def test_an_established_veteran_is_NOT_priced_at_the_minimum(self):
        row = btv._prearb_priced(self.fx.dir)["grizzled_b"]
        self.assertIsNone(row.get("surTotal"))
        self.assertFalse(row["prearb"]["priced"])
        self.assertEqual(row["prearb"]["reason"], "past_prearb_window")

    def test_the_roster_label_overrides_a_PLAUSIBLE_appearance_count(self):
        # Five seasons: a real up-and-down career shape, so the label wins.
        m = btv._prearb_priced(self.fx.dir)["bounced_c"]["prearb"]
        self.assertTrue(m["priced"])
        self.assertEqual(m["service_source"], "debuts.roster_status.service_phase")

    def test_the_roster_label_does_NOT_override_an_IMPLAUSIBLE_count(self):
        """The other side of the boundary, added 2026-08-04.

        Eight appearance seasons on a pre_arb label is the nestor_cortes /
        joel_payamps shape. Holding 8 distinct seasons on under 3 years of
        service needs an average under 64 days a season, so the count is
        believed and the label is not."""
        row = btv._prearb_priced(self.fx.dir)["overcounted_e"]
        self.assertIsNone(row.get("surTotal"))
        self.assertFalse(row["prearb"]["priced"])
        self.assertEqual(row["prearb"]["reason"], "past_prearb_window")

    def test_the_boundary_itself_is_pinned(self):
        """Guards the threshold against a silent drift in either direction: the
        constant is a measured value, not a free parameter."""
        self.assertEqual(btv._PREARB_LABEL_OVERRIDE_MAX, 6)
        # Label wins strictly below the threshold and loses at or above it.
        # At est=5 the label caps svc to pre_arb_years-1 = 2, leaving a window
        # of 3-2 = 1 season; at est=6 the count stands and the window closes.
        self.assertEqual(btv._prearb_window(5, "pre_arb", 3, 5), (1, True))
        self.assertEqual(btv._prearb_window(6, "pre_arb", 3, 5), (0, False))
        # The label's REAL job is untouched: with no count at all it still wins.
        self.assertEqual(btv._prearb_window(None, "pre_arb", 3, 5), (1, True))

    def test_a_truncated_career_block_is_service_unknown_not_a_guess(self):
        row = btv._prearb_priced(self.fx.dir)["truncated_d"]
        self.assertIsNone(row.get("surTotal"))
        self.assertEqual(row["prearb"]["reason"], "service_unknown")
        self.assertIsNone(row["prearb"]["service_seasons_est"])


# ── scope: this basis fills gaps, it does not outrank an existing one ────────
class PreArbDoesNotOverrideOtherBases(unittest.TestCase):

    def test_a_contract_priced_vet_is_never_re_priced_at_the_minimum(self):
        fx = _Fixture(
            vets=[_vet("signed_e", _war(3.0), thru=2029, surTotal=99_000_000,
                       sur=[10.0, 10.0, 10.0, None, None], surNpv=99_000_000)],
            detail={"signed_e": {"key": "signed_e", "career": _career(2026)}},
        )
        try:
            self.assertNotIn("signed_e", btv._prearb_priced(fx.dir))
            records: list = []
            btv.apply_platform_surplus(records, fx.dir)
            row = next(r for r in records if r["player_key"] == "signed_e")
            self.assertEqual(row["surplus_source"], "projection")
            self.assertEqual(row["trade_value_mm"], 99.0)
        finally:
            fx.close()

    def test_an_efv_backgrade_row_keeps_its_own_basis(self):
        # 127 of the 359 no-contract vets are pre-arb, but ~100 of them already
        # price through the eFV backgrade - which values the whole remaining
        # career, where this basis values one or two seasons. Swapping them
        # would change the QUANTITY, not upgrade the basis.
        fx = _Fixture(
            vets=[_vet("prospecty_f", _war(3.0))],
            detail={"prospecty_f": {"key": "prospecty_f", "career": _career(2026)}},
            xfv={"prospecty_f": {"surplus_mm": 55.0, "xfv_war_6yr": 12.0,
                                 "realized_war": 1.0}},
        )
        try:
            records = [{"player_key": "prospecty_f", "player_name": "Prospecty F",
                        "status": "debuted", "age": 24, "trade_value_mm": 40.0}]
            btv.apply_platform_surplus(records, fx.dir)
            self.assertEqual(records[0]["surplus_source"], "xfv_backgrade")
        finally:
            fx.close()


# ── the census counts them, and the ledger lets them go ──────────────────────
class PreArbCoverageAndLedger(unittest.TestCase):

    def setUp(self):
        self.fx = _Fixture(
            vets=[_vet("rookie_a", _war(2.0)), _vet("grizzled_b", _war(2.0))],
            detail={
                "rookie_a": {"key": "rookie_a", "career": _career(2026)},
                "grizzled_b": {"key": "grizzled_b",
                               "career": _career(*range(2016, 2027))},
            },
        )
        self.records: list = []
        btv.apply_platform_surplus(self.records, self.fx.dir)

    def tearDown(self):
        self.fx.close()

    def test_the_priced_row_leaves_the_published_unpriced_ledger(self):
        on_board = {r["player_key"] for r in self.records
                    if r.get("trade_value_mm") is not None}
        keys = {r["key"] for r in btv._unpriced_vets(self.fx.dir, on_board)}
        self.assertNotIn("rookie_a", keys)
        self.assertIn("grizzled_b", keys)

    def test_the_remaining_row_now_publishes_WHY_it_is_unpriced(self):
        on_board = {r["player_key"] for r in self.records
                    if r.get("trade_value_mm") is not None}
        row = next(r for r in btv._unpriced_vets(self.fx.dir, on_board)
                   if r["key"] == "grizzled_b")
        # The top-level reason vocabulary is unchanged (the Trade Machine search
        # renders off it); the refinement rides alongside it.
        self.assertEqual(row["reason"], "no_contract")
        self.assertEqual(row["prearb_reason"], "past_prearb_window")
        self.assertEqual(row["svc_seasons_est"], 11)

    def test_the_census_counts_the_prearb_rows_on_their_own_line(self):
        cov = btv._projection_coverage(self.records, self.fx.dir)
        self.assertEqual(cov["unpriceable"], 2)
        self.assertEqual(cov["unpriceable_priced_prearb"], 1)
        self.assertEqual(cov["unpriceable_published"], 1)
        self.assertEqual(cov["unpriceable_no_contract"], 1)
        self.assertEqual(cov["unpriceable_no_contract_reasons"],
                         {"past_prearb_window": 1})

    def test_the_census_still_reconciles(self):
        cov = btv._projection_coverage(self.records, self.fx.dir)
        self.assertEqual(cov["unpriceable"],
                         cov["unpriceable_priced_elsewhere"] + cov["unpriceable_published"])
        self.assertEqual(cov["unpriceable_published"],
                         cov["unpriceable_expiring"] + cov["unpriceable_no_contract"])

    def test_the_payload_discloses_the_assumption(self):
        stamp = btv._prearb_basis_stamp()
        self.assertEqual(stamp["surplus_source"], "prearb_min")
        self.assertEqual(stamp["salary_basis"], "league_minimum")
        self.assertEqual(stamp["pre_arb_years"],
                         vf._config()["service_time"]["pre_arb_years"])
        # Service time is a PROXY and the arb tail is not priced. Both are stated
        # in the artifact, because a number shipped without the assumption that
        # produced it is what this board keeps having to go back and repair.
        self.assertIn("PROXY", stamp["service_time_source"])
        self.assertIn("FLOOR", stamp["window_priced"])


if __name__ == "__main__":
    unittest.main()
