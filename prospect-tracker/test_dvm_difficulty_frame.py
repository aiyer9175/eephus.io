# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the DvM+ difficulty lab's frame module (tools/dvm_difficulty_lab.py, DVM-1).

The frame rules F-R1 to F-R5 of the dvm_difficulty design, held in code: no read from
the reserved 2020 and 2021 lists before the R-LV look record (owner answer Q-DVM-1); no
R-VM input read (a 2025-or-later debut's debut-year preseason read: neither its grade nor
its printed origin); the frame refuses before the ETA blend look is recorded, and every
growth computation refuses before that record and before the difficulty gate is
registered; an AST scan finds no label, career_war or efv_* import (efv_identity, the
outcome-blind name resolver the design names for level and age, is the one allowed
efv_ module, and it imports no outcome module itself). Plus the counts contract: a grade
rung only ever sits beside START reads, and whether a start read has a slot is decided
per source and year, never per player.
"""

from __future__ import annotations

import ast
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import efv_dataset as D
import efv_identity as ID
import efv_vintage_frame as VF
from tools import dvm_difficulty_lab as L

HERE = Path(__file__).resolve().parent
LAB = HERE / "tools" / "dvm_difficulty_lab.py"

VERDICT_TEXT = ("## 7. Gate\n\ntext\n\n## 8. Results (verbatim lab output)\n\n"
                "    VERDICT: SHIP CANDIDATE (owner's call); recommended arm B\n")
VOID_TEXT = "## 8. Results\n\nVOID: the rerun did not reproduce the first run.\n"
EMPTY_TEXT = ("## 8. Results (verbatim lab output)\n\nNo look yet. A rerun that does not "
              "reproduce the first run makes the look VOID.\n\n## 9. Next\n\nVERDICT: x\n")
SENTINEL_FV = 77.5

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
"""


def _snap(con, src, day, pk, fv, pos="SS", extras=None, label=None):
    con.execute(
        "INSERT INTO snapshots (source, snapshot_date, interval_label, player_key, "
        "player_name, position, org, fv, status, tools_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (src, day, label or f"{day[:4]}report", pk, pk.title(), pos, "NYY", fv, "active",
         json.dumps({"_extras": extras or {}})))


def fixture_db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.executescript(SCHEMA)
    fg = "fangraphs"
    # alpha: listed every year 2019 to 2022; the reserved 2020 and 2021 reads carry the
    # sentinel grade, the only list-printed origin sits on the 2021 read
    _snap(con, fg, "2019-02-15", "alpha", 45)
    _snap(con, fg, "2020-02-15", "alpha", SENTINEL_FV)
    _snap(con, fg, "2021-02-15", "alpha", SENTINEL_FV,
          extras={"signed_from": "Vanderbilt", "sign_market": "Draft"})
    _snap(con, fg, "2022-02-15", "alpha", 50)
    _snap(con, fg, "2023-02-15", "alpha", 50)
    # beta: debuted 2025-06-10, so his 2025 preseason read is an R-VM input; it carries
    # the sentinel grade and the only list-printed origin
    _snap(con, fg, "2023-02-15", "beta", 45, pos="RHP")
    _snap(con, fg, "2024-02-15", "beta", 50, pos="RHP")
    _snap(con, fg, "2025-02-15", "beta", SENTINEL_FV, pos="RHP",
          extras={"signed_from": "Venezuela", "sign_market": "J2"})
    # gamma: same source and years as beta, no debut (the debut-blind slot control)
    _snap(con, fg, "2023-02-15", "gamma", 45, pos="RHP",
          extras={"signed_from": "Westlake (TX)", "sign_market": "Draft"})
    _snap(con, fg, "2024-02-15", "gamma", 50, pos="RHP")
    _snap(con, fg, "2025-02-15", "gamma", 50, pos="RHP")
    # a midseason read and an international board read are not preseason list reads
    _snap(con, fg, "2023-07-30", "gamma", 55, pos="RHP")
    _snap(con, fg, "2024-02-01", "delta", 45, label="FG 2024 Int'l Board (2024-02-01)")
    for pk in ("alpha", "beta", "gamma"):
        con.execute("INSERT INTO players (player_key, player_name, position) VALUES (?,?,?)",
                    (pk, pk.title(), "SS"))
    con.commit()
    return con


def build(con, **kw):
    # The reserved-list rule is tested with no R-LV record (gate amendment A-2 set the
    # module's record; a caller passing None still gets the exclusion).
    kw.setdefault("rlv_record", None)
    with mock.patch.object(L, "MIN_LIST_READS", 1):
        return L.build_frame(con, debut={"beta": "2025-06-10"},
                             eta_text=kw.pop("eta_text", VERDICT_TEXT),
                             index=ID.NameIndex(), person_seasons={}, draft_years={}, **kw)


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.con = fixture_db(Path(self._tmp.name) / "f.db")

    def tearDown(self):
        self.con.close()
        self._tmp.cleanup()


class ReservedListVintages(FixtureCase):
    """F-R1, Q-DVM-1 A: no 2020 or 2021 endpoint before the R-LV look record."""

    def test_record_set_by_amendment_a2(self):
        self.assertEqual(L.RLV_LOOK_RECORD, "1c73c420ad68bc6a8061859c6e82757589ef20c6")
        self.assertEqual(L.excluded_list_years(), frozenset())
        self.assertEqual(L.excluded_list_years(None), frozenset({2020, 2021}))
        self.assertEqual(L.excluded_list_years("not-a-sha"), frozenset({2020, 2021}))

    def test_no_reserved_read_or_endpoint(self):
        fr = build(self.con)
        self.assertFalse([k for k in fr["reads"] if k[2] in (2020, 2021)])
        self.assertNotIn(SENTINEL_FV, {r["fv"] for r in fr["reads"].values()})
        for sl in fr["slots"]:
            V = sl["key"][2]
            self.assertNotIn(V, (2020, 2021))
            self.assertNotIn(V + sl["h"], (2020, 2021))
        # alpha 2019 reaches neither 2020 nor 2021, so it has no slot at all
        self.assertNotIn(("fangraphs", "alpha", 2019), fr["starts"])
        self.assertIn(("fangraphs", "alpha", 2022), fr["starts"])

    def test_reserved_read_gives_no_origin(self):
        fr = build(self.con)
        self.assertEqual(fr["starts"][("fangraphs", "alpha", 2022)]["origin"], "UNK")


class ReservedDebutCohort(FixtureCase):
    """F-R2: an R-VM input (a 2025+ debut's debut-year preseason read) is never read."""

    def test_rvm_rule(self):
        self.assertTrue(L.is_rvm_input(2025, "2025-06-10"))
        self.assertTrue(L.is_rvm_input(2026, "2026-04-02"))
        self.assertFalse(L.is_rvm_input(2024, "2025-06-10"))
        self.assertFalse(L.is_rvm_input(2024, "2024-06-10"))
        self.assertFalse(L.is_rvm_input(2025, None))

    def test_rvm_grade_and_origin_never_loaded(self):
        fr = build(self.con)
        self.assertNotIn(("fangraphs", "beta", 2025), fr["reads"])
        self.assertIn(("fangraphs", "beta", 2025), fr["rvm"])
        self.assertNotIn(SENTINEL_FV, {r["fv"] for r in fr["reads"].values()})
        # the only list-printed origin rides the R-VM row, so beta stays unknown
        self.assertEqual(fr["starts"][("fangraphs", "beta", 2024)]["origin"], "UNK")

    def test_rvm_end_leaves_the_modeling_frame(self):
        fr = build(self.con)
        beta = [s for s in fr["slots"] if s["key"] == ("fangraphs", "beta", 2024)
                and s["h"] == 1]
        self.assertEqual(len(beta), 1)
        self.assertFalse(beta[0]["in_frame"])
        self.assertFalse(beta[0]["completed"])

    def test_slots_are_decided_per_source_year(self):
        fr = build(self.con)
        b = fr["starts"][("fangraphs", "beta", 2024)]["horizons"]
        g = fr["starts"][("fangraphs", "gamma", 2024)]["horizons"]
        self.assertEqual(b, g)


class Clocks(FixtureCase):
    """F-R3: the frame and every growth computation wait for the ETA look record."""

    def test_record_detection(self):
        self.assertTrue(L.eta_look_recorded(VERDICT_TEXT))
        self.assertTrue(L.eta_look_recorded(VOID_TEXT))
        self.assertFalse(L.eta_look_recorded(EMPTY_TEXT))
        self.assertFalse(L.eta_look_recorded(None))

    def test_committed_gate_carries_its_record(self):
        text = (HERE / L.ETA_GATE_DOC).read_text(encoding="utf-8")
        self.assertTrue(L.eta_look_recorded(text))

    def test_frame_refuses_before_the_record(self):
        with self.assertRaises(L.ClockError):
            build(self.con, eta_text=EMPTY_TEXT)
        build(self.con, eta_text=VOID_TEXT)

    def test_growth_refuses_before_the_record(self):
        registered = "# gate\n\nRegistration status: REGISTERED\n"
        with self.assertRaises(L.ClockError):
            L.assert_growth_allowed(EMPTY_TEXT, registered)
        with self.assertRaises(L.ClockError):
            L.assert_growth_allowed(VERDICT_TEXT, "Registration status: DRAFT\n")
        with self.assertRaises(L.ClockError):
            L.assert_growth_allowed(VERDICT_TEXT, "")
        L.assert_growth_allowed(VOID_TEXT, registered)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def _non_doc_strings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant):
                docs.add(id(body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docs]


class SourceScan(unittest.TestCase):
    """F-R4, F-R5: no label, career_war or efv_* import; no WAR or eFV input."""

    def test_no_outcome_or_efv_import(self):
        mods = _imports(LAB)
        for m in mods:
            low = m.lower()
            self.assertNotIn("label", low, m)
            self.assertNotIn("career_war", low, m)
            self.assertNotIn("value_framework", low, m)
            if low.split(".")[-1].startswith("efv_") or low.startswith("efv_"):
                self.assertEqual(m, "efv_identity", m)
        self.assertNotIn("storage", mods)

    def test_identity_module_is_outcome_blind(self):
        mods = _imports(HERE / "efv_identity.py") | _imports(HERE / "milb_history.py")
        for m in mods:
            self.assertFalse(m.startswith("efv_"), m)
            self.assertNotIn("label", m.lower())
            self.assertNotIn("war", m.lower())

    def test_no_banned_names_in_code(self):
        banned = ("career_war", "xfv", "fv_to_6yr", "efv_labels", "value_framework",
                  "birth_date", "ewar", "fwar")
        for s in _non_doc_strings(LAB):
            for b in banned:
                self.assertNotIn(b, s.lower(), s)
        tree = ast.parse(LAB.read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
                {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for b in ("career_war", "fv_to_6yr_avg_war", "label_6yr", "war"):
            self.assertNotIn(b, names)


class Parity(unittest.TestCase):
    """The lab re-states, without importing them, the eFV frame's window, reserved
    years and level constants; these pins keep the copies equal."""

    def test_frame_constants(self):
        self.assertEqual(L.RESERVED_LV, VF.RESERVED_LV)
        self.assertEqual(L.R_VM_FIRST_DEBUT_YEAR, VF.R_VM_FIRST_DEBUT_YEAR)
        for v, d in ((2019, None), (2023, "2023-04-12"), (2024, "2024-07-01"),
                     (2022, "2021-09-01")):
            self.assertEqual(L.window_bounds(v, d), VF.window_bounds(v, d))
        self.assertEqual(L.TYPICAL_LEVEL_AGE, D._TYPICAL_LEVEL_AGE)
        self.assertEqual(L.LEVEL_RANK, D._LEVEL_RANK)
        self.assertEqual(L.SEASON_START_MMDD, D.SEASON_START_MMDD)

    def test_debut_day_matches_efv_dataset(self):
        recs = [
            {"player_key": "a", "debut_date": "2023-06-01"},
            {"player_key": "b", "debut_date": "2023-06-01", "debut_date_is_placeholder": True},
            {"player_key": "c", "debut_date": "2022-06-15"},
            {"player_key": "d", "debut_date": "2022-06-15"},
            {"player_key": "e", "debut_date": None},
        ]
        redates = {"c": ("2022-06-15", "2022-08-02"), "d": ("2022-06-15", None)}
        with mock.patch.object(D, "_REDATES", dict(redates)):
            for r in recs:
                self.assertEqual(L.debut_day(r, redates), D.debut_day_for_cutoff(r)[0], r)


class Origin(unittest.TestCase):
    def test_fg_print(self):
        cn = frozenset({"miami"})
        cases = {("Harvard Westlake (CA)", None): "HS", ("Miami (OH)", "Draft"): "COL",
                 ("Chipola JC", None): "JUCO", ("Dominican Republic", None): "IFA",
                 ("Japan", "Free Agent"): "PRO", ("Vanderbilt", "Draft"): "COL",
                 ("Oviedo HS (FL)", "Draft"): "HS", ("", "J2"): "IFA", ("", None): None,
                 ("Florida - Manatee (JC)", None): "JUCO"}
        for (sf, mk), want in cases.items():
            self.assertEqual(L.origin_from_fg(sf, mk, cn), want, sf)

    def test_report_text(self):
        cases = {
            "The Curacao native made his United States debut in 2010.": "IFA",
            "Signed out of Venezuela for $1.5 million in 2016, he moved fast.": "IFA",
            "The Princeton product led the Minors in saves.": "COL",
            "The junior college product had a solid debut.": "JUCO",
            "The Rays took the Alabama high school product in the second round.": "HS",
            ("He honored his commitment to Nebraska after high school and was drafted "
             "in the second round three years later."): "COL",
            ("The Cubs signed him away from his commitment to Vanderbilt out of high "
             "school."): "HS",
            "He was posted by his NPB club last winter.": "PRO",
            "His fastball sits at 95 mph.": None,
        }
        for text, want in cases.items():
            self.assertEqual(L.origin_from_report(text, frozenset({"princeton"})), want,
                             text)

    def test_age_rule(self):
        self.assertEqual(L.age_rule(2015, [("decimal", 22.5, "2017-02-15")]), "COL")
        self.assertEqual(L.age_rule(2015, [("decimal", 19.0, "2017-02-15")]), "HS")
        # 21.9 in February 2017 is 20.3 on 2015-06-30: born 1995, a draft-year gap of 20
        self.assertEqual(L.age_rule(2015, [("decimal", 21.9, "2017-02-15")]), "HS")
        self.assertEqual(L.age_rule(2015, [("int", 20, 2016)]), "HS")
        self.assertEqual(L.age_rule(2015, [("int", 21, 2016)]), "COL")
        self.assertIsNone(L.age_rule(None, [("int", 21, 2016)]))
        self.assertIsNone(L.age_rule(2015, []))

    def test_pro_entry_rule(self):
        self.assertEqual(L.pro_entry_rule(2010, {"DSL"}, 17.0, False), "IFA")
        self.assertEqual(L.pro_entry_rule(2010, {"A"}, 17.0, False), "IFA")
        self.assertIsNone(L.pro_entry_rule(2010, {"A"}, 19.0, False))
        self.assertIsNone(L.pro_entry_rule(2010, {"DSL"}, 17.0, True))
        self.assertIsNone(L.pro_entry_rule(2005, {"DSL"}, 17.0, False))

    def test_precedence(self):
        ev = {"fg": {"p": [("2019-02-15", "Vanderbilt", "Draft", None, 21.0)]},
              "draft_type": {"p": "HS", "q": "HS"}, "overseas": set(),
              "acq": {"q": {"method": "draft", "year": 2015, "school": "Arkansas"},
                      "r": {"method": "draft", "year": 2015, "school": "Arkansas"}},
              "pipeline": {"r": [("2016-01-22", "HS")], "s": [("2016-01-22", "COL")]},
              "ages": {"s": [("int", 18, 2016)]}, "fg_college_names": frozenset()}
        self.assertEqual(L.classify_origin("p", ev)[:2], ("COL", "fg_print"))
        self.assertEqual(L.classify_origin("q", ev)[:2], ("HS", "draft_type"))
        self.assertEqual(L.classify_origin("r", ev)[:2], ("COL", "acquisitions"))
        self.assertEqual(L.classify_origin("s", ev, draft_year_hint=2015)[:2],
                         ("COL", "pipeline_text"))
        self.assertEqual(L.classify_origin("t", dict(ev, ages={"t": [("int", 18, 2016)]}),
                                           draft_year_hint=2015)[:2], ("HS", "age_rule"))
        self.assertEqual(L.classify_origin("u", ev, pro_entry="IFA")[:2],
                         ("IFA", "pro_entry"))
        self.assertEqual(L.classify_origin("v", ev)[:2], ("UNK", "none"))


RUNG_LABELS = set(L.RUNGS)


def _paths(obj, prefix=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield prefix + (str(k),)
            yield from _paths(v, prefix + (str(k),))


class CountsContract(FixtureCase):
    def test_rung_only_beside_start_reads(self):
        c = L.summarize(build(self.con))
        for path in _paths(c):
            parts = [seg for p in path for seg in p.split("|")]
            if RUNG_LABELS & set(parts):
                self.assertEqual(path[0], "origin_coverage", path)
                self.assertNotIn("completed", " ".join(path))
        for path in _paths(c["pairs"]):
            self.assertFalse(RUNG_LABELS & {seg for p in path for seg in p.split("|")},
                             path)

    def test_power_block_reads_pooled_completion_only(self):
        c = L.summarize(build(self.con))
        pb = c["power_block"]
        for hz in ("12m", "24m"):
            blk = c["pairs"][hz]
            self.assertEqual(pb[hz]["pooled_completion_share"],
                             L._share(blk["total_completed_pairs"], blk["total_list_slots"])
                             or 0.0)
            self.assertEqual(set(pb[hz]), {"pooled_completion_share", "by_side"})
        self.assertEqual(pb["assumptions"]["base_rate_p"], 0.20)

    def test_p2_check(self):
        from collections import Counter
        cells = {("hit", "45"): Counter({"HS": 95, "UNK": 5}),
                 ("pit", "60"): Counter({"COL": 8, "UNK": 2})}
        r = L.p2_check(cells)
        self.assertEqual(r["cells_over_ceiling"], ["pit|60"])
        self.assertFalse(r["holds"])
        cells[("pit", "60")] = Counter({"COL": 10})
        r = L.p2_check(cells)
        self.assertTrue(r["holds"])
        self.assertEqual(r["unknown"], 5)


class Freeze(unittest.TestCase):
    def test_backup_copy_and_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "live.db"
            con = sqlite3.connect(str(src))
            con.execute("CREATE TABLE t (x INTEGER)")
            con.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(50)])
            con.commit()
            rec = L.freeze_db(src, Path(td) / "frozen")
            con.close()
            out = Path(rec["path"])
            self.assertEqual(rec["sha256"], L.sha256_file(out))
            self.assertEqual(rec["method"], "sqlite3.Connection.backup")
            c2 = sqlite3.connect(str(out))
            self.assertEqual(c2.execute("SELECT COUNT(*), SUM(x) FROM t").fetchone(),
                             (50, sum(range(50))))
            c2.close()
            saved = json.loads((Path(td) / "frozen" / L.FROZEN_RECEIPT)
                               .read_text(encoding="utf-8"))
            self.assertEqual(saved["sha256"], rec["sha256"])


if __name__ == "__main__":
    unittest.main()
