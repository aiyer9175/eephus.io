# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the DvM+ difficulty lab's study half (tools/dvm_difficulty_lab.py, DVM-3),
as docs/dvm-difficulty-2026-09-30/DVM_DIFFICULTY_GATE.md registers it.

FIXTURES ONLY: every row here is synthetic or hand-built. Nothing reads the store, a
served artifact or an outcome. Covered: the shrinkage of the origin-by-rung cells, the
spread floor, the Kish effective n, tenure shares summing to 1 per step, the censoring
rules and the three frames, the 60 to 70 against 40 to 50 ratio formula on a fixture
table, the club and player indices, the clock and the refusal of a second scored look,
and the dry run of the whole reporting path (which writes only where it is told).
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import efv_identity as ID
from tools import dvm_difficulty_lab as L

HERE = Path(__file__).resolve().parent
VERDICT_TEXT = ("## 8. Results (verbatim lab output)\n\n"
                "    VERDICT: SHIP CANDIDATE (owner's call); recommended arm B\n")
REGISTERED = "# gate\n\nRegistration status: REGISTERED\n"
ANCHOR_EMPTY = "## 18. Results\n\n**EMPTY AT REGISTRATION.**\n\nNo cell mean.\n"
ANCHOR_DONE = ANCHOR_EMPTY + "\n### 2026-11-20: the look\n\nverbatim output\n"
V2_EMPTY = "## 9. Results\n\n(Empty. Filled only by the look runner.)\n\n## 10. Next\n"
V2_DONE = "## 9. Results\n\n### 2026-12-02: R-LV look\n\nout\n\n## 10. Next\n"
SHA = "a" * 40


def _row(**kw) -> dict:
    r = {"src": "fangraphs", "pk": "p", "V": 2015, "h": 1, "side": "hit", "y": 0.0,
         "w": 0.0, "rung": "50", "fv_rung": "50", "g0": 50.0, "origin": "COL",
         "origin_raw": "COL", "level": "A/A+", "age_rel": 0.0, "agemiss": False,
         "gap": None, "status": "completed", "tau": {"NYY": 1.0}, "omega": 1.0,
         "trait": "FV"}
    r.update(kw)
    return r


def _pair(**kw) -> dict:
    p = {"src": "fangraphs", "pk": "p", "V": 2015, "h": 1, "side": "hit", "rung": "50",
         "g0": 50.0, "g1": 55.0, "status": "completed", "tools0": {}, "tools1": {},
         "present0": {}, "origin": "HS", "level": "A/A+", "age_rel": 0.5,
         "agemiss": False, "tau": {"NYY": 1.0}}
    p.update(kw)
    return p


class ValueTable(unittest.TestCase):
    """W is storage.FV_EXPECTED_WAR, copied; the lab never imports storage."""

    def test_parity_with_storage(self):
        import storage
        self.assertEqual({k: float(v) for k, v in storage.FV_EXPECTED_WAR.items()},
                         L.VALUE_TABLE)
        for g in np.arange(20.0, 80.01, 2.5):
            self.assertAlmostEqual(L.value_of(g), storage._fv_to_expected_war(g), places=9)

    def test_grade_and_rung(self):
        self.assertEqual(L.grade_value(45, True), 47.5)
        self.assertEqual(L.rung_of(47.5), "45")
        self.assertEqual(L.rung_of(35), "<=35")
        self.assertEqual(L.rung_of(67.5), "65+")
        self.assertEqual(L.h2_rung("65+"), "60+")
        self.assertEqual(L.fold_origin("JUCO"), "COL")
        self.assertEqual(L.fold_origin(None), "UNK")


class Shrinkage(unittest.TestCase):
    """Section 5: u_hat = n / (n + k_u) x mean residual, k_u = max(20, s2 / tau2)."""

    def test_method_of_moments_and_shrink(self):
        cells = {("HS", "40"): (100, 2.0), ("IFA", "40"): (50, -1.0),
                 ("COL", "40"): (200, 0.5), ("PRO", "40"): (10, 9.0)}
        s2 = 4.0
        out = L.shrink_cells(cells, s2)
        means = np.array([2.0, -1.0, 0.5])
        tau2 = float(np.var(means, ddof=1)) - np.mean([s2 / 100, s2 / 50, s2 / 200])
        self.assertAlmostEqual(out["tau2_u"], tau2)
        k = max(20.0, s2 / tau2)
        self.assertAlmostEqual(out["k_u"], k)
        self.assertEqual(k, 20.0)  # the floor binds here
        self.assertAlmostEqual(out["u_hat"][("HS", "40")], 100 / (100 + k) * 2.0)
        self.assertAlmostEqual(out["u_hat"][("IFA", "40")], 50 / (50 + k) * -1.0)
        # a cell under 20 pairs is never credited, however large its residual
        self.assertEqual(out["u_hat"][("PRO", "40")], 0.0)
        # the shrunk value is always smaller in size than the raw cell mean
        for c, (n, m) in cells.items():
            self.assertLessEqual(abs(out["u_hat"][c]), abs(m))

    def test_k_above_floor(self):
        cells = {("HS", "40"): (400, 0.3), ("IFA", "40"): (400, -0.3)}
        out = L.shrink_cells(cells, 100.0)
        tau2 = 0.18 - 0.25
        self.assertLess(tau2, 0)
        self.assertEqual(out["tau2_u"], 0.0)
        cells = {("HS", "40"): (400, 3.0), ("IFA", "40"): (400, -3.0)}
        out = L.shrink_cells(cells, 1000.0)
        self.assertAlmostEqual(out["tau2_u"], 18.0 - 2.5)
        self.assertAlmostEqual(out["k_u"], 1000.0 / 15.5)
        self.assertGreater(out["k_u"], L.K_U_FLOOR)
        self.assertAlmostEqual(out["u_hat"][("HS", "40")], 400 / (400 + 1000.0 / 15.5) * 3.0)

    def test_no_interaction_survives(self):
        out = L.shrink_cells({("HS", "40"): (100, 0.1), ("IFA", "40"): (100, 0.1)}, 4.0)
        self.assertEqual(out["tau2_u"], 0.0)
        self.assertIsNone(out["k_u"])
        self.assertTrue(all(v == 0.0 for v in out["u_hat"].values()))
        # one eligible cell: no variance across cells to read
        out = L.shrink_cells({("HS", "40"): (100, 5.0), ("IFA", "40"): (5, -5.0)}, 1.0)
        self.assertIsNone(out["k_u"])

    def test_fit_recovers_an_additive_table(self):
        a = {2014: 0.5, 2015: -0.5}
        b = {"40": 2.0, "50": 0.0, "60": -3.0}
        c = {"HS": 1.5, "COL": 0.0, "IFA": 0.75}
        rows = []
        i = 0
        for V in a:
            for rg in b:
                for g in c:
                    for _ in range(12):
                        rows.append(_row(pk=f"p{i}", V=V, rung=rg, origin=g,
                                         y=a[V] + b[rg] + c[g], w=0.0))
                        i += 1
        m = L.fit_expectation(rows)
        E = L.predict(m, rows)
        self.assertTrue(np.allclose(E, [r["y"] for r in rows], atol=1e-8))
        self.assertAlmostEqual(m["coef"]["c|HS"], 1.5, places=8)
        self.assertAlmostEqual(m["coef"]["c|IFA"], 0.75, places=8)
        self.assertLess(m["tau2_u"], 1e-12)
        self.assertTrue(all(abs(c["u_hat"]) < 1e-9 for c in m["u"].values()))
        # b pools across sources below 30 pairs a cell (36 per rung here: own cells)
        self.assertIn(["fangraphs", "40"], m["own_b"])
        m2 = L.fit_expectation([r for r in rows if r["origin"] == "HS"])
        self.assertTrue(all(c.startswith("b|*|") for c in m2["columns"] if c.startswith("b|")))


class SpreadFloor(unittest.TestCase):
    """s_hat = sqrt((nu s2_c + 30 s2_side) / (nu + 30)), nu = n - 1."""

    def test_formula(self):
        self.assertAlmostEqual(L.shrunk_spread(1, 100.0, 4.0), 2.0)
        self.assertAlmostEqual(L.shrunk_spread(31, 16.0, 4.0), math.sqrt((30 * 16 + 30 * 4) / 60))
        self.assertAlmostEqual(L.shrunk_spread(0, 9.0, 4.0), 2.0)
        # a thin cell with no spread of its own cannot read as certain
        self.assertGreater(L.shrunk_spread(3, 0.0, 25.0), 4.0)
        big = L.shrunk_spread(100000, 9.0, 4.0)
        self.assertAlmostEqual(big, 3.0, places=2)

    def test_fitted_spreads_follow_the_formula(self):
        pairs = L.fixture_pairs(players=120)
        rows = L.analysis_rows(pairs, side="hit")
        m = L.fit_expectation(rows)
        for rg, s in m["spread"].items():
            self.assertAlmostEqual(s["s_hat"], L.shrunk_spread(s["n"], s["s2"], m["s2_side"]))
            self.assertGreater(s["s_hat"], 0)


class KishAndClubs(unittest.TestCase):
    def test_kish_n(self):
        self.assertAlmostEqual(L.kish_n([1, 1, 1, 1]), 4.0)
        self.assertAlmostEqual(L.kish_n([0.5] * 10), 10.0)
        self.assertAlmostEqual(L.kish_n([3.0]), 1.0)
        self.assertAlmostEqual(L.kish_n([1, 0.5, 0.5]), 4.0 / 1.5)
        self.assertEqual(L.kish_n([]), 0.0)

    def test_aggregate_shrinks_toward_zero_and_floors_publication(self):
        items = [("NYY", 1.0, 2.0)] * 20 + [("BOS", 0.5, -1.0)] * 4
        agg = L.aggregate_clubs(items, 10.0, clubs=["NYY", "BOS", "TBR"])
        self.assertAlmostEqual(agg["NYY"]["D"], 2.0)
        self.assertAlmostEqual(agg["NYY"]["N"], 20.0)
        self.assertAlmostEqual(agg["NYY"]["D_shrunk"], 2.0 * 20 / 30)
        self.assertTrue(agg["NYY"]["publish"])
        self.assertFalse(agg["BOS"]["publish"])
        self.assertEqual(agg["TBR"], {"D": 0.0, "N": 0.0, "D_shrunk": 0.0, "sum_a": 0.0,
                                      "publish": False})

    def test_k_org_bounds(self):
        same = [(f"C{i}", 1.0, 0.0) for i in range(10) for _ in range(20)]
        self.assertEqual(L.k_org_mom(same)["k_org"], 50.0)
        spread = [(f"C{i}", 1.0, float(i)) for i in range(10) for _ in range(20)]
        spread += [(f"C{i}", 1.0, float(i) + 0.01) for i in range(10)]
        self.assertEqual(L.k_org_mom(spread)["k_org"], 5.0)

    def test_plus_index_and_rounding(self):
        idx = L.plus_index({"A": 1.0, "B": -1.0, "C": 0.0, "D": 0.0})
        sd = float(np.std([1.0, -1.0, 0.0, 0.0]))
        self.assertEqual(idx["A"], L.round_nearest(100 + 10 / sd))
        self.assertEqual(idx["C"], 100)
        self.assertEqual(L.round_nearest(114.5), 115)
        self.assertEqual(L.round_nearest(85.5), 86)

    def test_player_index(self):
        steps = {"a": {2019: [(1.0, 3.0)], 2022: [(0.5, 2.0), (0.5, 4.0)], 2023: [(1.0, 0.0)],
                       2024: [(1.0, 6.0)]},
                 "b": {2024: [(1.0, -3.0)]}}
        out = L.player_index(steps, ["a", "b"])
        sa = (3.0 + 0.0 + 6.0) / 3 * 3 / 5
        sb = -3.0 * 1 / 3
        sd = float(np.std([sa, sb]))
        self.assertEqual(out["a"], L.round_nearest(100 + 10 * sa / sd))
        self.assertEqual(out["b"], L.round_nearest(100 + 10 * sb / sd))


class TenureShares(unittest.TestCase):
    """Section 7 fallback: the shares of one step sum to 1."""

    def test_trade_inside_the_step(self):
        ev = [("2015-02-10", "NYY", "read"), ("2015-08-01", "BOS", "trade")]
        t = L.tenure_shares("2015-02-10", "2016-02-10", ev)
        self.assertAlmostEqual(sum(t.values()), 1.0)
        days = (L._day("2016-02-10") - L._day("2015-02-10")).days
        self.assertAlmostEqual(t["NYY"], (L._day("2015-08-01") - L._day("2015-02-10")).days / days)

    def test_trade_beats_a_read_the_same_day_and_reads_follow(self):
        ev = [("2015-02-10", "NYY", "read"), ("2015-06-01", "NYY", "read"),
              ("2015-06-01", "SEA", "trade"), ("2015-09-01", "SEA", "read"),
              ("2016-01-15", "TEX", "read")]
        t = L.tenure_shares("2015-02-10", "2016-02-10", ev)
        self.assertEqual(set(t), {"NYY", "SEA", "TEX"})
        self.assertAlmostEqual(sum(t.values()), 1.0)

    def test_degenerate_intervals(self):
        self.assertEqual(L.tenure_shares("2015-02-10", "2015-02-10",
                                         [("2015-02-10", "NYY", "read")]), {"NYY": 1.0})
        self.assertEqual(L.tenure_shares("2015-02-10", "2015-03-10",
                                         [("2015-02-20", "KCR", "read")]), {"KCR": 1.0})

    def test_every_fixture_step_sums_to_one(self):
        for p in L.fixture_pairs(players=80):
            self.assertAlmostEqual(sum(p["tau"].values()), 1.0)


class Censoring(unittest.TestCase):
    """Section 3: graduated, dropped and exited, and the frames S1 and S2."""

    def test_graduated(self):
        st, g = L.code_missing_end(50, debut_day="2016-04-20", end_close="2016-05-01",
                                   grad_grade=55, club_lowest=40, affiliated=True)
        self.assertEqual((st, g), ("graduated", 55.0))
        st, g = L.code_missing_end(50, debut_day="2015-07-01", end_close="2016-05-01",
                                   grad_grade=None, club_lowest=40, affiliated=None)
        self.assertEqual((st, g), ("graduated", 50.0))

    def test_debut_after_the_window_is_not_graduation(self):
        st, g = L.code_missing_end(50, debut_day="2016-05-01", end_close="2016-05-01",
                                   grad_grade=55, club_lowest=40, affiliated=True)
        self.assertEqual((st, g), ("dropped", 35.0))

    def test_dropped_one_rung_below_never_above_start(self):
        self.assertEqual(L.code_missing_end(50, debut_day=None, end_close="2016-05-01",
                                            grad_grade=None, club_lowest=40, affiliated=True),
                         ("dropped", 35.0))
        self.assertEqual(L.code_missing_end(40, debut_day=None, end_close="2016-05-01",
                                            grad_grade=None, club_lowest=47.5,
                                            affiliated=None), ("dropped", 40.0))

    def test_exited_is_coded_as_dropped(self):
        a = L.code_missing_end(45, debut_day=None, end_close="2016-05-01", grad_grade=None,
                               club_lowest=40, affiliated=False)
        b = L.code_missing_end(45, debut_day=None, end_close="2016-05-01", grad_grade=None,
                               club_lowest=40, affiliated=True)
        self.assertEqual(a, ("exited", 35.0))
        self.assertEqual(a[1], b[1])
        self.assertEqual(L.code_missing_end(45, debut_day=None, end_close="2016-05-01",
                                            grad_grade=None, club_lowest=None,
                                            affiliated=False), ("exited", None))

    def test_frames(self):
        grad = _pair(status="graduated", g1=50.0)
        drop = _pair(status="dropped", g1=35.0)
        done = _pair(status="completed", g1=55.0)
        self.assertEqual([L.end_grade(p) for p in (grad, drop, done)], [50.0, 35.0, 55.0])
        self.assertEqual([L.end_grade(p, "S1") for p in (grad, drop, done)], [None, None, 55.0])
        self.assertEqual([L.end_grade(p, "S2") for p in (grad, drop, done)], [55.0, 35.0, 55.0])

    def test_tool_frames(self):
        grad = _pair(status="graduated", tools0={"hit": 50.0}, tools1={"hit": 50.0})
        drop = _pair(status="exited", tools0={"hit": 50.0}, tools1=None)
        done = _pair(status="completed", tools0={"hit": 50.0}, tools1={"hit": 45.0})
        self.assertEqual([L.end_tool(p, "hit") for p in (grad, drop, done)], [50.0, None, 45.0])
        self.assertEqual([L.end_tool(p, "hit", "S1") for p in (grad, drop, done)],
                         [None, None, 45.0])
        self.assertEqual([L.end_tool(p, "hit", "S2") for p in (grad, drop, done)],
                         [55.0, None, 45.0])
        self.assertIsNone(L.end_tool(_pair(tools0={}), "hit"))

    def test_omega_counts_sources_inside_the_frame(self):
        pairs = [_pair(src=s) for s in L.SOURCES] + [_pair(src="fangraphs", pk="q")]
        pairs[1]["status"], pairs[1]["g1"] = "dropped", 45.0
        rows = L.analysis_rows(pairs)
        self.assertEqual(sorted(r["omega"] for r in rows if r["pk"] == "p"), [1 / 3] * 3)
        rows = L.analysis_rows(pairs, variant="S1")
        self.assertEqual(sorted(r["omega"] for r in rows if r["pk"] == "p"), [0.5, 0.5])
        self.assertEqual([r["omega"] for r in rows if r["pk"] == "q"], [1.0])

    def test_outcomes(self):
        r = L.analysis_rows([_pair(g0=60.0, g1=70.0, rung="60")])[0]
        self.assertEqual(r["y"], 10.0)
        self.assertAlmostEqual(r["w"], 13.0)
        r = L.analysis_rows([_pair(src="fangraphs", tools0={"throw": 55.0},
                                   tools1={"throw": 60.0}, present0={"throw": 40.0})],
                            trait="arm")[0]
        self.assertEqual((r["y"], r["rung"], r["gap"]), (5.0, "55", 15.0))

    def test_census_is_pooled(self):
        c = L.censoring_census([_pair(), _pair(status="graduated"), _pair(h=2)])
        self.assertEqual(set(c), {"12m", "24m"})
        self.assertEqual(c["12m"], {"completed": 1, "graduated": 1, "dropped": 0, "exited": 0})


SCHEMA = """
CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
  snapshot_date TEXT NOT NULL, interval_label TEXT NOT NULL, player_key TEXT NOT NULL,
  player_name TEXT NOT NULL, position TEXT, org TEXT, rank INTEGER, fv REAL,
  status TEXT NOT NULL, tools_json TEXT, fv_plus INTEGER NOT NULL DEFAULT 0);
CREATE TABLE players (player_key TEXT PRIMARY KEY, player_name TEXT, position TEXT,
  org TEXT, is_pitcher INTEGER, birth_date TEXT);
CREATE TABLE acquisitions (player_key TEXT PRIMARY KEY, method TEXT, year INTEGER,
  school TEXT, signing_date TEXT);
CREATE TABLE draft_players (player_key TEXT PRIMARY KEY, player_type TEXT, school TEXT,
  promoted_key TEXT);
CREATE TABLE draft_canonical_keys (draft_key TEXT PRIMARY KEY, milb_key TEXT);
CREATE TABLE overseas_players (player_key TEXT PRIMARY KEY, league TEXT,
  promoted_key TEXT);
CREATE TABLE overseas_canonical_keys (overseas_key TEXT PRIMARY KEY, milb_key TEXT);
CREATE TABLE trades (id INTEGER PRIMARY KEY AUTOINCREMENT, player_key TEXT NOT NULL,
  trade_date TEXT NOT NULL, from_org TEXT, to_org TEXT, source TEXT NOT NULL);
"""


class CensoringOnAFixtureStore(unittest.TestCase):
    """The censoring rules end to end on a hand-built store (the frame module builds
    the slots; pairs_from_frame codes the missing ends)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.con = sqlite3.connect(str(Path(self._tmp.name) / "f.db"))
        self.con.executescript(SCHEMA)
        fg = "fangraphs"

        def snap(day, pk, fv, org="NYY", pos="SS", tools=None):
            self.con.execute(
                "INSERT INTO snapshots (source, snapshot_date, interval_label, player_key, "
                "player_name, position, org, fv, status, tools_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (fg, day, f"{day[:4]}report", pk, pk.title(), pos, org, fv, "active",
                 json.dumps(dict(tools or {}, _extras={}))))
        # done: listed 2022 and 2023 (a completed 12-month pair)
        snap("2022-02-15", "done", 45, tools={"hit": 50})
        snap("2023-02-15", "done", 50, tools={"hit": 55})
        # grad: listed 2022, debuted 2022-08-01 (graduated: G_end = his 2022 read)
        snap("2022-02-15", "grad", 55, tools={"hit": 60})
        # drop: listed 2022 with NYY, off the 2023 list; NYY's lowest 2023 grade is 40
        snap("2022-02-15", "drop", 45)
        snap("2023-02-15", "low", 40)
        # traded: NYY at his start, BOS from 2022-08-01, absent in 2023; BOS's low is 50
        snap("2022-02-15", "trad", 50)
        snap("2023-02-15", "bosx", 50, org="BOS")
        self.con.execute("INSERT INTO trades (player_key, trade_date, to_org, source) "
                         "VALUES ('trad', '2022-08-01', 'BOS', 'mlb_api')")
        self.con.commit()

    def tearDown(self):
        self.con.close()
        self._tmp.cleanup()

    def test_pairs(self):
        debut = {"grad": "2022-08-01"}
        with mock.patch.object(L, "MIN_LIST_READS", 1):
            fr = L.build_frame(self.con, debut=debut, eta_text=VERDICT_TEXT,
                               index=ID.NameIndex(), person_seasons={}, draft_years={})
        players = {k[1] for k in fr["starts"]}
        events = L.load_club_events(self.con, players, debut, excluded=fr["excluded"],
                                    canon=lambda x: x)
        pairs, census = L.pairs_from_frame(fr, debut=debut, club_events=events,
                                           canon=lambda x: x,
                                           active_in=lambda person, season: None)
        by = {(p["pk"], p["h"]): p for p in pairs}
        done = by[("done", 1)]
        self.assertEqual((done["status"], done["g0"], done["g1"]), ("completed", 45.0, 50.0))
        self.assertEqual(done["tools1"], {"hit": 55.0})
        grad = by[("grad", 1)]
        self.assertEqual((grad["status"], grad["g1"]), ("graduated", 55.0))
        self.assertEqual(grad["tools1"], {"hit": 60.0})
        drop = by[("drop", 1)]
        self.assertEqual((drop["status"], drop["g1"]), ("dropped", 35.0))
        trad = by[("trad", 1)]
        self.assertEqual((trad["status"], trad["g1"]), ("dropped", 45.0))
        self.assertEqual(set(trad["tau"]), {"NYY", "BOS"})
        for p in pairs:
            self.assertAlmostEqual(sum(p["tau"].values()), 1.0)
        self.assertEqual(census["completed"], sum(1 for p in pairs
                                                  if p["status"] == "completed"))


class CreditRatio(unittest.TestCase):
    """Section 6: the 60 to 70 against 40 to 50 credit ratio on a fixture table."""

    def test_today(self):
        r = L.credit_ratio(None, None, None, None, None, None)
        self.assertAlmostEqual(r["today"]["ratio"], 13.0 / 2.5)
        self.assertAlmostEqual(r["today"]["ratio"], 5.2)
        self.assertIsNone(r["DV"]["ratio"])

    def test_dv_and_d0_formulas(self):
        r = L.credit_ratio(-1.0, 0.3, -2.0, 1.0, 6.0, 4.0)
        self.assertAlmostEqual(r["DV"]["numerator"], 14.0)
        self.assertAlmostEqual(r["DV"]["denominator"], 2.2)
        self.assertAlmostEqual(r["DV"]["ratio"], 14.0 / 2.2)
        self.assertAlmostEqual(r["D0"]["ratio"], (12.0 / 6.0) / (9.0 / 4.0))

    def test_undefined_denominator(self):
        r = L.credit_ratio(-1.0, 2.5, 0.0, 10.0, 5.0, 5.0)
        self.assertEqual(r["DV"]["ratio"], "undefined")
        self.assertAlmostEqual(r["DV"]["denominator"], 0.0)
        self.assertEqual(r["D0"]["ratio"], "undefined")
        self.assertAlmostEqual(r["D0"]["numerator"], 2.0)

    def test_standardized_expectation_on_a_fixture_table(self):
        model = {"kind": "fv", "coef": {"a|fangraphs|2015": 1.0, "b|*|60": -2.0,
                                        "b|*|40": 0.5, "c|HS": 1.0},
                 "own_b": [], "a_source_mean": {"fangraphs": 1.0},
                 "u": {"HS|60": {"u_hat": -0.5}}, "spread": {}, "s2_side": 4.0}
        rows = [_row(origin="HS", omega=1.0), _row(origin="COL", omega=0.5)]
        e60 = L.standardized_expectation(model, rows, "60")
        self.assertAlmostEqual(e60, ((1 - 2 + 1 - 0.5) * 1.0 + (1 - 2) * 0.5) / 1.5)
        e40 = L.standardized_expectation(model, rows, "40")
        self.assertAlmostEqual(e40, ((1 + 0.5 + 1) * 1.0 + (1 + 0.5) * 0.5) / 1.5)
        self.assertEqual(L.spread_of(model, "60"), 2.0)


class Inference(unittest.TestCase):
    def test_holm(self):
        self.assertEqual(L.holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])
        self.assertEqual(L.holm([1.0, 0.5]), [1.0, 1.0])

    def test_p_values_floor(self):
        self.assertEqual(L.p_two_sided(np.ones(100), 100), 0.01)
        self.assertEqual(L.p_two_sided([np.nan], 100), 1.0)
        self.assertEqual(L.p_one_sided_below(-np.ones(50), 50), 0.02)

    def test_spearman_ties(self):
        self.assertAlmostEqual(L.spearman([1, 2, 3, 4], [10, 20, 20, 40]),
                               float(np.corrcoef([1, 2, 3, 4], [1, 2.5, 2.5, 4])[0, 1]))
        self.assertIsNone(L.spearman([1, 1, 1], [1, 2, 3]))

    def test_h1_verdict(self):
        ok = L.h1_verdict(1.2, 0.01, True, [0.5, 0.9, 1.1, 0.2], [0.3, -0.1, 0.8], "HS", "COL")
        self.assertEqual(ok, "easier for HS than COL")
        self.assertEqual(L.h1_verdict(1.2, 0.01, True, [0.5, -0.9, 1.1, 0.2], [0.3, 0.1, 0.8],
                                      "HS", "COL"), "not resolved")
        self.assertEqual(L.h1_verdict(1.2, 0.01, True, [0.5, 0.9, 1.1, 0.2],
                                      [0.3, -0.1, None], "HS", "COL"), "not resolved")
        self.assertEqual(L.h1_verdict(-1.2, 0.2, True, [], [], "HS", "COL"), "not resolved")
        self.assertEqual(L.h1_verdict(1.2, 0.01, False, [], [], "HS", "COL"), "unpowered")

    def test_h2_statistics(self):
        p = {"40": 0.3, "45": 0.25, "50": 0.2, "55": 0.15, "60+": 0.1}
        self.assertLess(L.h2_trend(p), 0)
        self.assertAlmostEqual(L.h2_contrast(p), -0.2)

    def test_decision_rule(self):
        block = {"point": {"DV": {"VC": 0.15}, "C0": {"VC": 0.40}},
                 "deltas": {"DV|VP1": {"lower_95_one_sided": -0.04, "p": 0.5, "delta": 0.0},
                            "DV|VP2": {"p_holm": 0.5, "delta": 0.02},
                            "DV|VS": {"p_holm": 0.01, "delta": 0.05}}}
        d = L.decide(block)
        self.assertEqual(d["verdict"], "SHIP CANDIDATE")
        self.assertEqual(d["copy"], ["difficulty-adjusted; ties the previous index on prediction"])
        block["deltas"]["DV|VS"]["delta"] = -0.05
        self.assertEqual(L.decide(block)["verdict"], "NO SHIP")
        block["deltas"]["DV|VS"]["delta"] = 0.05
        block["deltas"]["DV|VP1"]["lower_95_one_sided"] = -0.06
        self.assertEqual(L.decide(block)["verdict"], "NO SHIP")
        block["deltas"]["DV|VP1"]["lower_95_one_sided"] = -0.01
        block["point"]["DV"]["VC"] = 0.25
        self.assertEqual(L.decide(block)["verdict"], "SHIP CANDIDATE")  # 0.10 below C0
        block["point"]["C0"]["VC"] = 0.30
        self.assertEqual(L.decide(block)["verdict"], "NO SHIP")


class Clock(unittest.TestCase):
    """Section 14: the lab refuses before its clock, on a look day, before the anchor
    record, and a second scored look."""

    def kw(self, **over):
        k = {"eta_text": VERDICT_TEXT, "dvm_text": REGISTERED, "anchor_text": ANCHOR_DONE,
             "efv_v2_text": V2_EMPTY, "rlv_record": None, "waiver": None}
        k.update(over)
        return k

    def test_today_refuses(self):
        with self.assertRaises(L.ClockError):
            L.look_frame("2026-10-08", **self.kw())
        with self.assertRaises(L.ClockError):
            L.look_frame("2026-10-08", **self.kw(anchor_text=ANCHOR_EMPTY))

    def test_complement_path(self):
        self.assertEqual(L.look_frame("2027-01-31", **self.kw()), "COMPLEMENT")
        with self.assertRaises(L.ClockError):
            L.look_frame("2027-01-30", **self.kw())
        with self.assertRaises(L.ClockError):
            L.look_frame("2027-02-01", **self.kw(anchor_text=ANCHOR_EMPTY))

    def test_full_path(self):
        self.assertEqual(L.look_frame("2026-12-02", **self.kw(efv_v2_text=V2_DONE,
                                                               rlv_record=SHA)), "FULL")
        with self.assertRaises(L.ClockError):
            L.look_frame("2026-11-30", **self.kw(efv_v2_text=V2_DONE, rlv_record=SHA))
        # the document and the frame switch must agree
        with self.assertRaises(L.ClockError):
            L.look_frame("2026-12-02", **self.kw(efv_v2_text=V2_DONE))
        with self.assertRaises(L.ClockError):
            L.look_frame("2027-02-01", **self.kw(rlv_record=SHA))

    def test_look_days_and_registration(self):
        for d in ("2026-12-01", "2026-12-03", "2027-01-12"):
            with self.assertRaises(L.ClockError):
                L.look_frame(d, **self.kw(efv_v2_text=V2_DONE, rlv_record=SHA))
        with self.assertRaises(L.ClockError):
            L.look_frame("2027-02-01", **self.kw(dvm_text="Registration status: DRAFT\n"))
        with self.assertRaises(L.ClockError):
            L.look_frame("2027-02-01", **self.kw(eta_text="## 8. Results\n\nnone\n"))

    def test_committed_documents(self):
        """At HEAD the anchor look is recorded (2026-10-14) and the R-LV record is
        EFV_V2_GATE section 11 with its artifact (amendment A-2): FULL from the waiver's
        date (amendment A-1), refused before it."""
        anchor = (HERE / L.ANCHOR_GATE_DOC).read_text(encoding="utf-8")
        v2 = (HERE / L.EFV_V2_GATE_DOC).read_text(encoding="utf-8")
        self.assertTrue(L.results_recorded(anchor, "18"))
        self.assertTrue(L.rlv_record_in_doc(v2))
        kw = {"eta_text": None, "dvm_text": None, "anchor_text": anchor, "efv_v2_text": v2}
        with self.assertRaises(L.ClockError):
            L.look_frame("2026-10-08", **kw)
        self.assertEqual(L.look_frame("2026-10-14", **kw), "FULL")
        with self.assertRaises(L.ClockError):
            L.look_frame("2026-10-14", **kw, waiver=None)
        with self.assertRaises(L.ClockError):
            L.look_frame("2026-10-14", **kw, rlv_record=None)

    def test_rlv_record_in_section_11(self):
        """Amendment A-2: section 11 counts only when it names the artifact AND the
        artifact exists; a dated part 9 entry counts as before."""
        s11 = ("## 9. Results\n\n(Empty.)\n\n## 11. Registration by EW2-6\n\n"
               "the numbers live in `data/_labs/efv_v3/efv_v3_confirm.json`\n")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(L.rlv_record_in_doc(s11, root))
            art = root / L.RLV_RECORD_ARTIFACT
            art.parent.mkdir(parents=True)
            art.write_text("{}", encoding="utf-8")
            self.assertTrue(L.rlv_record_in_doc(s11, root))
            self.assertFalse(L.rlv_record_in_doc(V2_EMPTY, root))
            self.assertTrue(L.rlv_record_in_doc(V2_DONE, root))
            self.assertEqual(L.look_frame("2026-10-15", **self.kw(
                efv_v2_text=s11, rlv_record=SHA, waiver=L.OWNER_WAIVER, root=root)), "FULL")

    def test_owner_waiver_a1(self):
        """Amendment A-1: EW3-5 opens the FULL look from 2026-10-14; the look days, the
        COMPLEMENT date and the anchor record stand."""
        w = L.OWNER_WAIVER
        self.assertEqual((w["decision"], w["from"]), ("EW3-5", "2026-10-14"))
        full = {"efv_v2_text": V2_DONE, "rlv_record": SHA, "waiver": w}
        self.assertEqual(L.look_frame("2026-10-14", **self.kw(**full)), "FULL")
        with self.assertRaises(L.ClockError):
            L.look_frame("2026-10-13", **self.kw(**full))
        for d in ("2026-10-21", "2026-10-23", "2026-11-20"):
            with self.assertRaises(L.ClockError):
                L.look_frame(d, **self.kw(**full))
        with self.assertRaises(L.ClockError):
            L.look_frame("2026-10-14", **self.kw(waiver=w))
        with self.assertRaises(L.ClockError):
            L.look_frame("2026-10-14", **self.kw(anchor_text=ANCHOR_EMPTY, **full))

    def test_lab_constants(self):
        self.assertEqual((L.SEED, L.BOOT_B, L.PERM_DRAWS), (20261201, 2000, 500))
        self.assertEqual((L.MIN_B_CELL, L.MIN_U_CELL, L.K_U_FLOOR, L.SPREAD_PSEUDO_DF),
                         (30, 20, 20.0, 30.0))
        self.assertEqual((L.K_ORG_BOUNDS, L.MIN_PUBLISH_N), ((5.0, 50.0), 10.0))
        self.assertEqual((L.H1_MIN_PAIRS, L.H2_MIN_PAIRS, L.H2_L2), (100, 50, 1.0))
        self.assertEqual((L.NONINF_MARGIN, L.VC_MAX, L.VC_BELOW_C0), (-0.05, 0.20, 0.10))
        self.assertEqual(sum(len(v) for v in L.TRAITS.values()) * len(L.H1_CONTRASTS),
                         L.H1_FAMILY)
        self.assertEqual(L.VALIDATION_YEARS["FULL"], tuple(range(2012, 2026)))
        self.assertEqual(L.VALIDATION_YEARS["COMPLEMENT"],
                         (2012, 2013, 2014, 2015, 2016, 2017, 2018, 2023, 2024, 2025))
        self.assertEqual(L.FROZEN_DB_SHA256, (
            "7d7e56533e6c62ef3ec3d8400e079974779ea59ca533dbc0e43939f596d6a56e"))


class LookRefusals(unittest.TestCase):
    """run_look: a stored result is re-printed, never re-scored; a look that began
    scoring and crashed refuses every rerun; the clock refuses before any write."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.task = self.root / "task"
        self.p = mock.patch.object(L, "CACHE_DIR", self.cache)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self._tmp.cleanup()

    def test_second_look_reprints(self):
        (self.data / L.EVAL_ARTIFACT).write_text(json.dumps({"decision": {"verdict": "X"}}),
                                                 encoding="utf-8")
        with mock.patch.object(L, "run_analysis", side_effect=AssertionError("scored")):
            self.assertEqual(L.run_look(self.task, today="2027-02-01", data_dir=self.data), 0)
        self.assertIn("No second scored look", (self.task / "look_stdout.txt").read_text())
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), [L.EVAL_ARTIFACT])

    def test_crashed_look_refuses(self):
        (self.cache / L.LOOK_MARKER).write_text("{}", encoding="utf-8")
        self.assertEqual(L.run_look(self.task, today="2027-02-01", data_dir=self.data), 2)
        self.assertEqual(list(self.data.iterdir()), [])

    def test_clock_refuses_before_any_write(self):
        with self.assertRaises(L.ClockError):
            L.run_look(self.task, today="2026-10-08", data_dir=self.data)
        self.assertEqual(list(self.data.iterdir()), [])
        self.assertFalse((self.cache / L.LOOK_MARKER).exists())

    def test_busy_processes(self):
        lines = [(1, "python run_monthly.py --phase all"), (2, "python -m http.server 8000"),
                 (3, "python -m pytest -q test_x.py"), (os.getpid(), "python -m pytest")]
        self.assertEqual(L.busy_processes(lines),
                         ["1: python run_monthly.py --phase all", "3: python -m pytest -q test_x.py"])
        with mock.patch.object(L, "_process_lines", return_value=None):
            self.assertEqual(L.busy_processes(), ["the process listing failed"])

    def test_shell_wrappers_are_not_busy(self):
        """Amendment A-6: a wrapper that only mentions a token is not a session."""
        lines = [(11, '"C:\\Program Files\\Git\\bin\\bash.exe" -c "tasklist | grep -i pytest; '
                      'python tools/fetch_x.py"'),
                 (12, "powershell -NoProfile -Command \"Get-Process | ? pytest\""),
                 (13, "/usr/bin/bash -c 'python -m pytest -q'"),
                 (14, "C:\\py\\python.exe -m pytest -q t.py"),
                 (15, '"C:\\Program Files\\Git\\usr\\bin\\timeout.exe" 1800 python -m pytest'),
                 (16, "bash deploy/nightly-build.sh")]
        self.assertEqual([b.split(":")[0] for b in L.busy_processes(lines)],
                         ["14", "15", "16"])

    def test_tenure_source(self):
        self.assertEqual(L.tenure_source(self.root), "fallback (gate section 7)")
        (self.root / L.VAL4_DIR).mkdir(parents=True)
        self.assertEqual(L.tenure_source(self.root), L.TENURE_VAL4)
        self.assertEqual(L.tenure_source(), L.TENURE_VAL4)  # VAL_4 is committed

    def test_the_one_look_is_stored(self):
        # DVM-4 (2026-10-14): the look ran once and wrote both artifacts; a later run
        # re-prints the stored result instead of scoring again (gate section 14).
        self.assertTrue((L.DATA_DIR / L.TABLE_ARTIFACT).exists())
        stored = L.stored_look()
        self.assertIsNotNone(stored)
        self.assertEqual(stored["frame"], "FULL")
        self.assertTrue(stored["receipt"]["owner_waived_early_read"])
        self.assertEqual(stored["decision"]["verdict"], "NO SHIP")
        self.assertEqual(set(stored["failed_arms"]), {"DV", "D0"})


class DryRun(unittest.TestCase):
    """The crash protocol's dry run: the whole reporting path on fixtures with nulls,
    written only where it is told."""

    def test_dry_run_reporting_path(self):
        stored = {n: (L.DATA_DIR / n).read_bytes() if (L.DATA_DIR / n).exists() else None
                  for n in (L.TABLE_ARTIFACT, L.EVAL_ARTIFACT)}
        with tempfile.TemporaryDirectory() as tmp:
            r = L.run_dry(Path(tmp), B=8, perms=3, players=160)
            names = sorted(p.name for p in Path(tmp).iterdir())
            self.assertEqual(names, sorted(["PROBES.jsonl", L.TABLE_ARTIFACT, "dry_run.txt",
                                            L.EVAL_ARTIFACT]))
            self.assertTrue(r["text"].startswith("FRAME: COMPLEMENT\n"))
            ev = json.loads((Path(tmp) / L.EVAL_ARTIFACT).read_text(encoding="utf-8"))
            table = json.loads((Path(tmp) / L.TABLE_ARTIFACT).read_text(encoding="utf-8"))
        self.assertEqual(ev["h1"]["families"]["12m|total"]["size"], 39)
        self.assertEqual(ev["h1"]["families"]["12m|direct"]["size"], 39)
        self.assertEqual(ev["h2"]["family_size"], 8)
        self.assertIn(ev["decision"]["verdict"], ("SHIP CANDIDATE", "NO SHIP"))
        self.assertTrue(ev["generated_at"] and table["generated_at"])  # A-7
        # section 13: a failed arm is a block of the eval artifact, never a new file
        self.assertEqual(set(ev["failed_arms"]),
                         {a for a, d in ev["validation"]["decision"].items()
                          if d["verdict"] != "SHIP CANDIDATE"})
        for blk in ev["failed_arms"].values():
            self.assertEqual(set(blk), {"decision", "point", "deltas"})
        self.assertEqual(set(table["models"]), {"12m|hit", "12m|pit", "24m|hit", "24m|pit"})
        for key in ("12m|hit", "12m|pit"):
            self.assertAlmostEqual(table["ratio"][key]["today"]["ratio"], 5.2)
        self.assertTrue(5.0 <= table["k_org"]["DV"]["k_org"] <= 50.0)
        # the dry run writes only where it is told: the stored look is untouched
        for n, before in stored.items():
            p = L.DATA_DIR / n
            self.assertEqual(p.read_bytes() if p.exists() else None, before, n)

    def test_receipt_paths_are_relative(self):
        self.assertEqual(L._rel(L.CACHE_DIR / L.FROZEN_DB),
                         ".cache/dvm_difficulty/" + L.FROZEN_DB)

    def test_fixture_carries_nulls(self):
        pairs = L.fixture_pairs(players=200)
        self.assertTrue(any(p["level"] is None for p in pairs))
        self.assertTrue(any(p["age_rel"] is None for p in pairs))
        self.assertTrue(any(p["origin"] == "UNK" for p in pairs))
        self.assertTrue(any(p["tools1"] is None for p in pairs))
        self.assertEqual({p["status"] for p in pairs}, set(L.STATUSES))
        self.assertFalse({p["V"] for p in pairs} & {2020, 2021})
        self.assertFalse({p["V"] + p["h"] for p in pairs} & {2020, 2021})


class Val4Calendar(unittest.TestCase):
    """Amendment A-3: VAL_4's org calendar as the tenure split, on a fixture store with
    nulls (a null org, a duplicated and a null trades row, an unresolvable signing, an
    R-VM input read, a player with nothing to place him)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.con = sqlite3.connect(str(Path(self._tmp.name) / "v.db"))
        self.con.executescript(
            "CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, "
            "snapshot_date TEXT, interval_label TEXT, player_key TEXT, fv REAL, org TEXT, "
            "status TEXT);"
            "CREATE TABLE trades (id INTEGER PRIMARY KEY AUTOINCREMENT, player_key TEXT, "
            "trade_date TEXT, from_org TEXT, to_org TEXT);"
            "CREATE TABLE player_transactions (player_key TEXT PRIMARY KEY, "
            "payload_json TEXT, fetched_at TEXT);")
        snaps = [("fangraphs", "2019-02-15", "p1", 45, "NYY"),
                 ("fangraphs", "2022-02-15", "p1", 50, "LAD"),
                 ("mlb_pipeline", "2019-03-01", "p2", 40, "NYY"),
                 ("mlb_pipeline", "2021-03-01", "p2", 45, "BOS"),
                 ("fangraphs", "2019-02-15", "p3", 40, "SEA"),
                 ("fangraphs", "2024-02-15", "p4", 50, "TBR"),
                 ("fangraphs", "2025-02-15", "p4", 77.5, "TBR"),
                 ("fangraphs", "2019-02-15", "p5", None, None)]
        for src, d, pk, fv, org in snaps:
            self.con.execute(
                "INSERT INTO snapshots (source, snapshot_date, interval_label, player_key, "
                "fv, org, status) VALUES (?,?,?,?,?,?,?)",
                (src, d, f"{d[:4]}report", pk, fv, org, "active"))
        for row in (("p2", "2020-08-01", "NYY", "BOS"), ("p2", "2020-08-01", "NYY", "BOS"),
                    ("p2", "2020-09-01", "BOS", None)):
            self.con.execute("INSERT INTO trades (player_key, trade_date, from_org, to_org) "
                             "VALUES (?,?,?,?)", row)
        txs = {"p1": [{"id": 1, "type_code": "DR", "date": "2018-06-10",
                       "to_team_name": "New York Yankees"},
                      {"id": 2, "type_code": "TR", "date": "2021-07-30",
                       "to_team_name": "Los Angeles Dodgers"}],
               "p3": [{"id": 3, "type_code": "SGN", "date": "2017-07-02",
                       "to_team_name": "Seattle Mariners"},
                      {"id": 4, "type_code": "REL", "date": "2020-05-28"},
                      {"id": 5, "type_code": "SFA", "date": "2021-03-01",
                       "to_team_name": "Sugar Land Skeeters"}]}
        for pk, t in txs.items():
            self.con.execute("INSERT INTO player_transactions VALUES (?,?,?)",
                             (pk, json.dumps(t), "2026-10-01"))
        self.con.commit()

    def tearDown(self):
        self.con.close()
        self._tmp.cleanup()

    def events(self, excluded=frozenset()):
        return L.val4_club_events(self.con, {"p1", "p2", "p3", "p4", "p5"},
                                  {"p4": "2025-06-10"}, excluded=excluded,
                                  today="2026-10-03", team_org={})

    def test_calendar_events(self):
        ev, diag = self.events()
        self.assertEqual([c for _, c, _ in ev["p1"]], ["NYY", "LAD"])
        self.assertEqual(ev["p1"][1][0], "2021-07-30")
        self.assertEqual([c for _, c, _ in ev["p2"]], ["NYY", "BOS"])
        self.assertEqual([c for _, c, _ in ev["p3"]], ["SEA", L.UNAFFILIATED])
        self.assertEqual([c for _, c, _ in ev["p4"]], ["TBR"])
        self.assertNotIn("p5", ev)
        self.assertEqual(diag["n_players"], 5)
        self.assertEqual(diag["players_with_calendar"], 4)
        self.assertTrue(all(k == "read" for e in ev.values() for _, _, k in e))

    def test_reserved_reads_never_open_a_calendar(self):
        # with list years 2019 and 2021 excluded p2 has no read the lab loads, so VAL_4
        # opens no calendar for him; p1 keeps his from the 2022 read and his transactions
        ev, _ = self.events(excluded=frozenset({2019, 2021}))
        self.assertNotIn("p2", ev)
        self.assertEqual([c for _, c, _ in ev["p1"]], ["NYY", "LAD"])

    def test_tenure_split_and_clean(self):
        ev, _ = self.events()
        tau = L.tenure_shares("2020-03-01", "2021-05-01", ev["p3"])
        self.assertAlmostEqual(sum(tau.values()), 1.0)
        self.assertIn(L.UNAFFILIATED, tau)
        pairs = [{"tau": dict(tau)}, {"tau": {L.UNAFFILIATED: 1.0}},
                 {"tau": {"NYY": 0.5, "XXX": 0.5}}, {"tau": {}}]
        census = L.val4_clean_tau(pairs, {"NYY", "SEA"})
        self.assertEqual(set(pairs[0]["tau"]), {"SEA"})
        self.assertLess(pairs[0]["tau"]["SEA"], 1.0)  # no renormalizing
        self.assertEqual(pairs[1]["tau"], {})
        self.assertEqual(pairs[2]["tau"], {"NYY": 0.5})
        self.assertEqual(census["pairs_with_dropped_share"], 3)
        self.assertEqual(census["pairs_with_no_club"], 2)

    def test_staff_units_map_absent(self):
        self.assertEqual(L.staff_units_map(Path(self._tmp.name) / "none.db"), ({}, None))
        self.assertEqual(L.staff_units_map(Path(self._tmp.name) / "v.db"), ({}, None))


if __name__ == "__main__":
    unittest.main()
