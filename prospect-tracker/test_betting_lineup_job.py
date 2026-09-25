# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The dark lineup capture job captures the right minutes and nothing else.

This job spends no credits, so the usual "did it drain the tier" worry does not
apply. What matters instead is that the EVIDENCE it leaves is trustworthy, and
that means four properties, each pinned below:

  * it acts inside the registered window and refuses after first pitch, because
    a row stamped before first pitch that was taken after it would let 5j's
    Leg M grade an arm on a card the price could not have seen;
  * one call per invocation, counted on the fetch helper itself so the claim
    covers every caller and not just `run`;
  * a written capture is immutable, because it is the only record of what was
    knowable at that instant and it cannot be rebuilt afterwards;
  * the starting nine is read off the N00 batting-order CODES, never off the
    boxscore's `battingOrder` array, which differs on 78.8% of completed sides.

Plus the two negative properties that keep phase 1 dark: nothing served imports
the job, and the job imports no pricer.

Nothing here touches the network. The one test that exercises the real fetch
helper blocks `feed_cache` and installs a fake `urlopen`, so a regression that
made the helper call twice fails here rather than on the box.
"""
from __future__ import annotations

import ast
import functools
import io
import json
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import betting_lineup_job as job

FIRST = datetime(2026, 9, 17, 23, 5, tzinfo=timezone.utc)   # 7:05pm ET

JOB_SRC = ROOT / "tools" / "betting_lineup_job.py"


@functools.lru_cache(maxsize=1)
def _tree() -> ast.Module:
    return ast.parse(JOB_SRC.read_text(encoding="utf-8"))


def _imported_names() -> set[str]:
    """Every module this file imports, including the lazy in-function ones."""
    out: set[str] = set()
    for n in ast.walk(_tree()):
        if isinstance(n, ast.Import):
            out.update(a.name.split(".")[0] for a in n.names)
            out.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
            out.add(n.module.split(".")[0])
    return out


def _called_names() -> set[str]:
    """Every attribute or bare name this file CALLS, which is what a dependency
    on another module's helper actually looks like."""
    out: set[str] = set()
    for n in ast.walk(_tree()):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


def _game(pk=800001, first_pitch=None, *, home_ids=(), away_ids=(),
          home_prob=None, away_prob=None, state="Preview", detail="Scheduled",
          game_type="R"):
    """One game in the job's flattened shape."""
    return {
        "game_pk": pk,
        "game_type": game_type,
        "official_date": "2026-09-17",
        "first_pitch": (first_pitch or FIRST).isoformat().replace("+00:00", "Z"),
        "abstract_state": state,
        "status": detail,
        "double_header": False,
        "sides": {
            "home": {"team_id": 111, "team": "Boston Red Sox",
                     "posted_ids": list(home_ids), "probable_id": home_prob},
            "away": {"team_id": 147, "team": "New York Yankees",
                     "posted_ids": list(away_ids), "probable_id": away_prob},
        },
    }


def _payload(games):
    """The StatsAPI `/schedule` shape the job parses, built from _game rows."""
    return {"dates": [{"date": "2026-09-17", "games": [
        {
            "gamePk": g["game_pk"],
            "gameType": g["game_type"],
            "officialDate": g["official_date"],
            "gameDate": g["first_pitch"],
            "doubleHeader": "N",
            "status": {"abstractGameState": g["abstract_state"],
                       "detailedState": g["status"]},
            "lineups": {
                "homePlayers": [{"id": i} for i in g["sides"]["home"]["posted_ids"]],
                "awayPlayers": [{"id": i} for i in g["sides"]["away"]["posted_ids"]],
            },
            "teams": {
                side: {
                    "team": {"id": g["sides"][side]["team_id"],
                             "name": g["sides"][side]["team"]},
                    "probablePitcher": ({"id": g["sides"][side]["probable_id"]}
                                        if g["sides"][side]["probable_id"] else {}),
                } for side in ("home", "away")
            },
        } for g in games]}]}


class _Store(unittest.TestCase):
    """A temp store, a temp slate, and an org lookup that never imports trades."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Path(self._tmp.name)
        self.slate = self.store / "slate.json"
        self._org = job._org
        job._org = lambda name: {"Boston Red Sox": "BOS",
                                 "New York Yankees": "NYY"}.get(name)
        job.reset_calls()

    def tearDown(self):
        job._org = self._org
        self._tmp.cleanup()

    def install_slate(self, games, now):
        job.write_slate(games, now, job.span_for(now), path=self.slate)


class TheWindow(_Store):
    """[10, 180] minutes from first pitch, and the gate that decides the call."""

    def test_it_acts_inside_the_window(self):
        now = FIRST - timedelta(minutes=90)
        self.install_slate([_game(first_pitch=FIRST)], now)
        d = job.decide(now, slate_path=self.slate)
        self.assertTrue(d["call"])
        self.assertEqual(d["decision"], "capture")
        self.assertEqual(d["in_window"], 1)

    def test_it_acts_at_both_edges_and_not_outside_them(self):
        for lead, inside in ((181, False), (180, True), (10, True), (9, False)):
            now = FIRST - timedelta(minutes=lead)
            self.assertEqual(job.in_window(_game(first_pitch=FIRST), now), inside,
                             f"lead {lead} should be in_window={inside}")

    def test_a_quiet_hour_makes_no_call_at_all(self):
        """C1 step 1: outside the window the job exits without a network call."""
        now = FIRST - timedelta(minutes=200)
        self.install_slate([_game(first_pitch=FIRST)], now)
        d = job.decide(now, slate_path=self.slate)
        self.assertFalse(d["call"])
        self.assertEqual(d["decision"], "idle")

    def test_a_postponed_game_is_not_in_the_window(self):
        now = FIRST - timedelta(minutes=90)
        g = _game(first_pitch=FIRST, detail="Postponed")
        self.assertFalse(job.in_window(g, now))

    def test_the_span_covers_the_neighbouring_utc_dates(self):
        """A 02:10Z game carries the PREVIOUS officialDate and a 23:50Z
        invocation looks into the next one, so one call spans three UTC days
        rather than choosing a date and silently skipping the other."""
        self.assertEqual(job.span_for(datetime(2026, 9, 17, 23, 50, tzinfo=timezone.utc)),
                         ("2026-09-16", "2026-09-18"))


class TheGateIsThisJobsOwn(_Store):
    """The pre-call gate must never be a quiet no-op on a bad read, and it must
    not sit on data/fantasy.json, which was measured empty on a full slate."""

    def test_no_slate_here_calls_and_says_so(self):
        d = job.decide(FIRST, slate_path=self.store / "nothing.json")
        self.assertTrue(d["call"])
        self.assertEqual(d["decision"], "no_local_slate")

    def test_a_slate_hours_old_is_an_error_not_a_quiet_day(self):
        now = FIRST - timedelta(minutes=90)
        self.install_slate([_game(first_pitch=FIRST)], now - timedelta(hours=12))
        # The stamp is written from `now`, so age it by rewriting the stamp.
        doc = json.loads(self.slate.read_text(encoding="utf-8"))
        doc["fetched_at"] = job._iso(now - timedelta(minutes=job.SLATE_HARD_STALE_MINUTES + 5))
        doc["span"] = list(job.span_for(now))
        self.slate.write_text(json.dumps(doc), encoding="utf-8")
        d = job.decide(now, slate_path=self.slate)
        self.assertTrue(d["error"])
        self.assertEqual(d["decision"], "slate_stale")

    def test_an_hour_old_slate_refreshes_even_with_nothing_in_the_window(self):
        now = FIRST - timedelta(minutes=600)
        self.install_slate([_game(first_pitch=FIRST)], now)
        doc = json.loads(self.slate.read_text(encoding="utf-8"))
        doc["fetched_at"] = job._iso(now - timedelta(minutes=job.SLATE_REFRESH_MINUTES + 1))
        self.slate.write_text(json.dumps(doc), encoding="utf-8")
        d = job.decide(now, slate_path=self.slate)
        self.assertTrue(d["call"])
        self.assertEqual(d["decision"], "slate_refresh")

    def test_the_job_never_reads_the_reverted_nightly_artifact(self):
        """data/fantasy.json is tracked and deploy/nightly-build.sh reverts it,
        its producer returns [] on any failure, and it is regular-season only.
        None of those may decide whether a capture happens. Checked on the
        syntax tree, not on the prose, so a comment explaining WHY the gate
        avoids that artifact does not trip it."""
        called = _called_names()
        for banned in ("resolve_slate", "slate_games", "fetch_probables",
                       "fetch_lineups"):
            self.assertNotIn(banned, called,
                             f"the gate must not depend on {banned}")

    def test_the_call_asks_for_the_postseason_game_types(self):
        self.assertEqual(job.GAME_TYPES, "R,F,D,L,W")


class TheRefusal(_Store):
    """No row is ever written for a side once first pitch is close or past."""

    def test_no_row_after_first_pitch(self):
        for after in (timedelta(0), timedelta(minutes=1), timedelta(hours=3)):
            now = FIRST + after
            g = _game(first_pitch=FIRST, home_ids=range(1, 10), home_prob=99)
            rows, refused = job.changed_rows([g], now, {})
            self.assertEqual(rows, [], f"wrote a row {after} after first pitch")
            self.assertTrue(refused["late"] or refused["not_pregame"])

    def test_no_row_inside_the_refusal_boundary(self):
        now = FIRST - timedelta(minutes=job.MIN_LEAD_MINUTES - 1)
        g = _game(first_pitch=FIRST, home_ids=range(1, 10))
        rows, refused = job.changed_rows([g], now, {})
        self.assertEqual(rows, [])
        self.assertEqual(refused["late"], 1)

    def test_a_row_at_the_boundary_itself_is_written(self):
        now = FIRST - timedelta(minutes=job.MIN_LEAD_MINUTES)
        g = _game(first_pitch=FIRST, home_ids=range(1, 10))
        rows, _ = job.changed_rows([g], now, {})
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["lead_minutes"], job.MIN_LEAD_MINUTES)

    def test_a_live_game_is_refused_whatever_the_clock_says(self):
        now = FIRST - timedelta(minutes=60)
        g = _game(first_pitch=FIRST, home_ids=range(1, 10), state="Live",
                  detail="In Progress")
        rows, refused = job.changed_rows([g], now, {})
        self.assertEqual(rows, [])
        self.assertEqual(refused["not_pregame"], 1)


class WhatCountsAsAChange(_Store):
    """5j: a first posting, a changed card, OR a changed probable."""

    def test_a_first_card_writes_one_row_per_posted_side(self):
        now = FIRST - timedelta(minutes=90)
        g = _game(first_pitch=FIRST, home_ids=range(1, 10))
        rows, _ = job.changed_rows([g], now, {})
        self.assertEqual([r["side"] for r in rows], ["home"])
        self.assertEqual(rows[0]["org"], "BOS")
        self.assertEqual(rows[0]["posted_ids"], list(range(1, 10)))

    def test_an_unchanged_card_writes_nothing(self):
        now = FIRST - timedelta(minutes=90)
        g = _game(first_pitch=FIRST, home_ids=range(1, 10), home_prob=99)
        rows, _ = job.changed_rows([g], now, {})
        again, _ = job.changed_rows([g], now + timedelta(minutes=15),
                                    {(g["game_pk"], "home"): rows[0]})
        self.assertEqual(again, [])

    def test_a_probable_change_on_a_CARDLESS_side_still_writes_a_row(self):
        """The easy clause to lose. A side that has not filed a card but whose
        probable changed has changed its posted state, and R4's count C is
        precisely about probables. The row carries an empty `posted_ids`, which
        says on its face that no card is filed."""
        now = FIRST - timedelta(minutes=150)
        g1 = _game(first_pitch=FIRST, away_prob=500)
        first, _ = job.changed_rows([g1], now, {})
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["posted_ids"], [])
        self.assertEqual(first[0]["probable_id"], 500)

        g2 = _game(first_pitch=FIRST, away_prob=501)
        seen = {(g2["game_pk"], "away"): first[0]}
        second, _ = job.changed_rows([g2], now + timedelta(minutes=15), seen)
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]["probable_id"], 501)
        self.assertEqual(second[0]["posted_ids"], [])

    def test_a_side_with_neither_a_card_nor_a_probable_is_not_a_posted_state(self):
        now = FIRST - timedelta(minutes=90)
        rows, _ = job.changed_rows([_game(first_pitch=FIRST)], now, {})
        self.assertEqual(rows, [])

    def test_the_row_carries_every_registered_field(self):
        now = FIRST - timedelta(minutes=90)
        g = _game(first_pitch=FIRST, home_ids=range(1, 10), home_prob=99)
        row = job.changed_rows([g], now, {})[0][0]
        for field in ("game_pk", "game_type", "side", "org", "posted_ids",
                      "probable_id", "captured_at", "first_pitch",
                      "lead_minutes", "status"):
            self.assertIn(field, row)


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


class TheOneCallRule(_Store):
    """One StatsAPI call per invocation, counted on the FETCH HELPER.

    The counter lives on `fetch_schedule` rather than inside `run` because a
    counter inside `run` cannot see a call made anywhere else. These tests drive
    the real helper with `feed_cache` blocked and `urlopen` faked, so they prove
    the helper's own count, not a double's."""

    def setUp(self):
        super().setUp()
        self._feed = sys.modules.get("feed_cache", "absent")
        sys.modules["feed_cache"] = None          # makes `import feed_cache` raise

    def tearDown(self):
        if self._feed == "absent":
            sys.modules.pop("feed_cache", None)
        else:
            sys.modules["feed_cache"] = self._feed
        super().tearDown()

    def _fake_urlopen(self, payload):
        def _open(url, timeout=None):
            return _FakeResponse(json.dumps(payload).encode("utf-8"))
        return _open

    def test_an_acting_invocation_calls_exactly_once(self):
        now = FIRST - timedelta(minutes=90)
        self.install_slate([_game(first_pitch=FIRST)], now)
        payload = _payload([_game(first_pitch=FIRST, home_ids=range(1, 10))])
        with mock.patch.object(job.urllib.request, "urlopen",
                               self._fake_urlopen(payload)):
            d = job.run(now, store=self.store, slate_path=self.slate)
        self.assertEqual(job.CALLS["n"], 1)
        self.assertEqual(d["rows_written"], 1)

    def test_a_no_op_invocation_calls_zero_times(self):
        now = FIRST - timedelta(minutes=300)
        self.install_slate([_game(first_pitch=FIRST)], now)
        with mock.patch.object(job.urllib.request, "urlopen",
                               self._fake_urlopen(_payload([]))):
            d = job.run(now, store=self.store, slate_path=self.slate)
        self.assertEqual(job.CALLS["n"], 0)
        self.assertFalse(d["call"])

    def test_the_url_asks_for_both_hydrates_in_one_request(self):
        with mock.patch.object(job.urllib.request, "urlopen",
                               self._fake_urlopen(_payload([]))):
            job.fetch_schedule("2026-09-16", "2026-09-18")
        self.assertEqual(job.CALLS["n"], 1)
        url = job.CALLS["urls"][0]
        self.assertIn("hydrate=lineups%2CprobablePitcher", url)
        self.assertIn("gameType=R%2CF%2CD%2CL%2CW", url)

    def test_a_failed_call_is_loud_rather_than_a_clean_no_op(self):
        """Leg M excludes games by looking for GAPS, so a failure that exits 0
        gets the games dropped as 'no capture row' instead of flagged."""
        now = FIRST - timedelta(minutes=90)
        self.install_slate([_game(first_pitch=FIRST)], now)

        def _boom(url, timeout=None):
            raise OSError("no route to host")

        with mock.patch.object(job.urllib.request, "urlopen", _boom), \
             self.assertLogs(job.log, level="ERROR"):
            d = job.run(now, store=self.store, slate_path=self.slate)
        self.assertTrue(d["error"])
        self.assertEqual(d["decision"], "fetch_failed")
        self.assertEqual(job.CALLS["n"], 1)


class TheCaptureIsImmutable(_Store):
    """A capture is evidence about an instant; a later copy must never replace
    an earlier one. Same rule as the odds snapshots and the weather forecasts."""

    def test_a_second_write_in_the_same_minute_raises(self):
        now = FIRST - timedelta(minutes=90)
        job.write_capture([{"game_pk": 1, "side": "home"}], now, store=self.store)
        with self.assertRaises(FileExistsError):
            job.write_capture([{"game_pk": 1, "side": "away"}], now, store=self.store)

    def test_the_first_bytes_survive_the_collision(self):
        now = FIRST - timedelta(minutes=90)
        path = job.write_capture([{"game_pk": 1, "side": "home"}], now, store=self.store)
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            job.write_capture([{"game_pk": 2, "side": "away"}], now, store=self.store)
        self.assertEqual(path.read_bytes(), before)

    def test_a_run_that_collides_writes_nothing_and_does_not_fail(self):
        now = FIRST - timedelta(minutes=90)
        self.install_slate([_game(first_pitch=FIRST)], now)
        job.write_capture([], now, store=self.store)      # occupy the minute
        payload = _payload([_game(first_pitch=FIRST, home_ids=range(1, 10))])
        d = job.run(now, store=self.store, slate_path=self.slate,
                    fetch=lambda a, b: payload)
        self.assertEqual(d["decision"], "same_minute_collision")
        self.assertEqual(d["rows_written"], 0)
        self.assertFalse(d["error"])

    def test_the_store_holds_only_captures_under_the_capture_name(self):
        """Readers select on the name, so the slate, the heartbeat and the run
        log sharing the directory must not be mistaken for captures."""
        now = FIRST - timedelta(minutes=90)
        job.write_capture([{"game_pk": 1}], now, store=self.store)
        self.install_slate([], now)
        job.append_runlog({"decision": "idle"}, now, store=self.store)
        names = [p.name for p in job.capture_files(self.store)]
        self.assertEqual(names, [f"{now.strftime('%Y-%m-%d-%H%M')}.json"])
        self.assertTrue(all(re.match(r"^\d{4}-\d{2}-\d{2}-\d{4}\.json$", n)
                            for n in names))

    def test_everything_the_job_writes_stays_under_its_own_store(self):
        now = FIRST - timedelta(minutes=90)
        self.install_slate([_game(first_pitch=FIRST)], now)
        payload = _payload([_game(first_pitch=FIRST, home_ids=range(1, 10))])
        d = job.run(now, store=self.store, slate_path=self.slate,
                    fetch=lambda a, b: payload)
        job.write_heartbeat(d, path=self.store / "heartbeat.json")
        job.append_runlog(d, now, store=self.store)
        written = sorted(p.relative_to(self.store).as_posix()
                         for p in self.store.rglob("*") if p.is_file())
        self.assertEqual(written, sorted([
            f"{now.strftime('%Y-%m-%d-%H%M')}.json",
            "heartbeat.json",
            f"runlog-{now.date().isoformat()}.jsonl",
            "slate.json",
        ]))


class TheStartingNine(unittest.TestCase):
    """The N00 codes, never the boxscore's battingOrder array.

    The array names the CURRENT occupant of each slot, substitutes included,
    and differs from the true starting nine on 3,464 of 4,394 completed sides
    (78.8%; 5j, R4 count A). The fixture below is that disagreement in
    miniature: a pinch hitter took the sixth slot, so the array holds him and
    the starter is gone from it."""

    FEED = {
        "liveData": {"boxscore": {"teams": {"home": {
            # The array as the completed feed writes it: slot 6 now holds 9006.
            "battingOrder": [9001, 9002, 9003, 9004, 9005, 9006, 9007, 9008, 9009],
            "players": {
                "ID9001": {"person": {"id": 9001}, "battingOrder": "100"},
                "ID9002": {"person": {"id": 9002}, "battingOrder": "200"},
                "ID9003": {"person": {"id": 9003}, "battingOrder": "300"},
                "ID9004": {"person": {"id": 9004}, "battingOrder": "400"},
                "ID9005": {"person": {"id": 9005}, "battingOrder": "500"},
                "ID9060": {"person": {"id": 9060}, "battingOrder": "600"},
                "ID9006": {"person": {"id": 9006}, "battingOrder": "601"},
                "ID9007": {"person": {"id": 9007}, "battingOrder": "700"},
                "ID9008": {"person": {"id": 9008}, "battingOrder": "800"},
                "ID9009": {"person": {"id": 9009}, "battingOrder": "900"},
                "ID9099": {"person": {"id": 9099}, "battingOrder": None},
            }}}}}
    }

    def test_it_reads_the_codes_and_returns_nine_in_slot_order(self):
        self.assertEqual(job.starting_nine(self.FEED, "home"),
                         [9001, 9002, 9003, 9004, 9005, 9060,
                          9007, 9008, 9009])

    def test_it_is_NOT_the_battingOrder_array(self):
        array = self.FEED["liveData"]["boxscore"]["teams"]["home"]["battingOrder"]
        nine = job.starting_nine(self.FEED, "home")
        self.assertNotEqual(nine, array)
        self.assertIn(9060, nine)        # the starter the array lost
        self.assertNotIn(9006, nine)     # the substitute the array kept

    def test_a_missing_side_is_empty_rather_than_an_exception(self):
        self.assertEqual(job.starting_nine(self.FEED, "away"), [])
        self.assertEqual(job.starting_nine({}, "home"), [])


class NothingServedReadsThisJob(unittest.TestCase):
    """Phase 1 is dark. The job reaches no served path, and no served path
    reaches the job."""

    #: An import of the job, in any of the four spellings that reach one. Naming
    #: it in a comment or a log message is not reaching it, and run_monthly does
    #: exactly that: it WATCHES the capture store by reading the directory, and
    #: the comment there says why it must never import the job.
    IMPORT_RE = re.compile(
        r"^\s*(?:import\s+betting_lineup_job"
        r"|from\s+betting_lineup_job\s+import"
        r"|from\s+tools\s+import\s+betting_lineup_job"
        r"|from\s+tools\.betting_lineup_job\s+import)"
        r"|import_module\(\s*['\"](?:tools\.)?betting_lineup_job['\"]",
        re.M)

    def test_no_module_in_the_tree_imports_the_job(self):
        me = {"betting_lineup_job.py", "test_betting_lineup_job.py"}
        offenders = []
        for p in list(ROOT.glob("*.py")) + list((ROOT / "tools").glob("*.py")):
            if p.name in me:
                continue
            if self.IMPORT_RE.search(p.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(p.name)
        self.assertEqual(offenders, [],
                         f"phase 1 must stay dark; these import it: {offenders}")

    def test_the_pipeline_watches_the_store_without_reaching_the_job(self):
        """The one thing the pipeline is allowed to know about this job is
        whether its captures are arriving. A dark job with no health row is how
        the close capture sat at zero snapshots for months with nothing saying
        so, and the fix must not make the job reachable from a build."""
        rm = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
        self.assertIn('"betting_lineup_capture"', rm,
                      "the capture must be on the watch list or its absence is silent")
        self.assertIn(".cache\" / \"lineup_captures", rm,
                      "the health row must be filed off the store, which survives "
                      "`git checkout -- .`, not off a tracked heartbeat")
        self.assertIsNone(self.IMPORT_RE.search(rm),
                          "the pipeline must read the store, never import the job")

    def test_the_job_imports_no_pricer(self):
        """On the syntax tree, so that naming a pricer in a comment (the
        module docstring says at length which ones it stays away from and why)
        is not confused with reaching one."""
        imported = _imported_names()
        for banned in ("betting_model", "betting_export", "betting_ingest",
                       "betting_credits", "betting_shadow", "betting_calibration",
                       "betting_learning", "dfs_export", "leaderboard_vintages"):
            self.assertNotIn(banned, imported,
                             f"the capture job must not reach {banned}")

    def test_the_only_endpoint_in_the_file_is_statsapi(self):
        """Zero Odds API credits, structurally: there is no other endpoint in
        the file to spend them at."""
        tree = _tree()
        urls = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and "http" in n.value]
        self.assertTrue(urls, "expected at least the StatsAPI constant")
        for u in urls:
            self.assertTrue(u.startswith("https://statsapi.mlb.com/"),
                            f"unexpected endpoint in the capture job: {u}")


class TheOfflineChecks(_Store):
    """--why and --selfcheck both spend nothing, and --selfcheck is the one
    that can tell a working install from a decoration."""

    def test_selfcheck_is_nonzero_when_the_scheduler_has_never_run_it(self):
        out = io.StringIO()
        with mock.patch.object(job, "HEARTBEAT_PATH", self.store / "none.json"), \
             mock.patch.object(sys, "argv", ["j", "--selfcheck"]), \
             mock.patch.object(sys, "stdout", out):
            rc = job.main()
        self.assertEqual(rc, 1)
        self.assertIn("NEVER RUN", out.getvalue())
        self.assertEqual(job.CALLS["n"], 0)

    def test_selfcheck_is_nonzero_after_a_loud_decision(self):
        hb = self.store / "heartbeat.json"
        job.write_heartbeat({"decision": "fetch_failed", "reason": "no route",
                             "error": True}, path=hb)
        out = io.StringIO()
        with mock.patch.object(job, "HEARTBEAT_PATH", hb), \
             mock.patch.object(sys, "argv", ["j", "--selfcheck"]), \
             mock.patch.object(sys, "stdout", out):
            rc = job.main()
        self.assertEqual(rc, 1)
        self.assertIn("BAD", out.getvalue())

    def test_selfcheck_is_zero_on_an_ordinary_no_op(self):
        hb = self.store / "heartbeat.json"
        job.write_heartbeat({"decision": "idle", "reason": "nothing in the window"},
                            path=hb)
        out = io.StringIO()
        with mock.patch.object(job, "HEARTBEAT_PATH", hb), \
             mock.patch.object(job, "STORE", self.store), \
             mock.patch.object(sys, "argv", ["j", "--selfcheck"]), \
             mock.patch.object(sys, "stdout", out):
            rc = job.main()
        self.assertEqual(rc, 0)

    def test_why_says_plainly_that_it_reports_the_gate_and_not_the_schedule(self):
        out = io.StringIO()
        with mock.patch.object(job, "SLATE_PATH", self.store / "none.json"), \
             mock.patch.object(sys, "argv", ["j", "--why"]), \
             mock.patch.object(sys, "stdout", out):
            rc = job.main()
        self.assertEqual(rc, 0)
        self.assertIn("makes no network call", out.getvalue())
        self.assertEqual(job.CALLS["n"], 0)


class TheRunLogExistsForLegM(_Store):
    """5j excludes a game unless the heartbeat shows no gap longer than 30
    minutes between T-180 and T-5. A last-run file is overwritten every fifteen
    minutes and can never show a gap, so the gap evidence is the run log."""

    def test_every_invocation_appends_one_line(self):
        now = FIRST - timedelta(minutes=90)
        for i in range(3):
            job.append_runlog({"decision": "idle", "call": False},
                              now + timedelta(minutes=15 * i), store=self.store)
        lines = job.runlog_path(now, store=self.store).read_text(
            encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(all(json.loads(x)["at"] for x in lines))


class TheRegistrationNote(unittest.TestCase):
    """The dated note in docs/diamond-betting.md 5j, pinned on the sentences
    that make it BIND rather than on its headings.

    A heading-only test passes a gutted document: the sibling lane's epoch test
    recorded that its heading-only draft caught 12 of 12 dropped sections and
    missed 7 of 9 dropped teeth. Each clause below is a tooth."""

    @classmethod
    def setUpClass(cls):
        doc = (ROOT / "docs" / "diamond-betting.md").read_text(encoding="utf-8")
        cls.flat = re.sub(r"\s+", " ", doc)

    def clause(self, text, why):
        self.assertIn(re.sub(r"\s+", " ", text), self.flat, why)

    def test_the_arming_is_dated_and_bounded_to_phase_1(self):
        self.clause("armed on 2026-09-17 by owner decision, phase 1 capture only, "
                    "at zero credits, and it moves no served price",
                    "the arming must name its date, its phase and its price effect")

    def test_the_cron_install_state_is_stated_in_the_same_breath(self):
        self.clause("The cron line is NOT installed by this change",
                    "a note that says armed without saying not installed asserts a "
                    "state of the box that does not hold")

    def test_o16_is_recorded_as_declined(self):
        self.clause("O16 is answered NO", "the correction must name the decision")

    def test_o18_is_recorded_as_pinned_by_its_own_condition(self):
        self.clause("O18 therefore stays at L-0 by its own conditional default",
                    "a reader must not think flipping O18 alone reopens Leg M")

    def test_leg_m_is_blocked_and_not_replaced(self):
        self.clause("Leg M is BLOCKED, not replaced", "O19's default stands")
        self.clause("This is not a switch to the fallback form",
                    "the fallback form activates only on an O19 no")

    def test_the_false_consequence_is_explicitly_denied(self):
        self.clause("It does NOT block the third publish gate",
                    "graded_price_history counts settled rows carrying the taken "
                    "price from that slate's OPEN snapshot, not a close")

    def test_the_true_consequences_are_listed(self):
        for item in ("no CLV for any 2026 slate",
                     "attach_closes` never fires",
                     "market-move block stays empty"):
            self.clause(item, f"the consequence list must carry: {item}")

    def test_the_note_carries_no_number_and_no_relation(self):
        self.clause("No count, capture tally, result or price relation is recorded "
                    "here, and no number has been computed",
                    "a dated note under a pre-registered section must not relate "
                    "anything to an outcome")

    def test_the_note_is_plain_ascii_without_a_dash(self):
        doc = (ROOT / "docs" / "diamond-betting.md").read_text(encoding="utf-8")
        start = doc.index("**Correction (2026-09-17), the arming of the capture job")
        note = doc[start:doc.index("## 5k.", start)]
        self.assertTrue(note.isascii(), "the note must be plain ASCII")
        # By codepoint, never by literal: the house copy rule bans these
        # characters and this file is not an exception to it.
        for dash in (chr(0x2014), chr(0x2013)):
            self.assertNotIn(dash, note)


class TheCronExampleShipsTheEntry(unittest.TestCase):
    """--selfcheck tells the box owner to install this job from
    deploy/betting-crontab.example, so the example has to carry the line.
    It did not until 2026-09-25: the job was armed on 2026-09-17 with no
    entry to copy, the same shape as the close job that went weeks unrun."""

    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "deploy" / "betting-crontab.example").read_text(
            encoding="utf-8")
        cls.lines = [ln for ln in cls.text.splitlines()
                     if ln.strip() and not ln.lstrip().startswith("#")
                     and "betting_lineup_job.py" in ln]

    def test_exactly_one_entry_every_fifteen_minutes_all_day(self):
        self.assertEqual(len(self.lines), 1, repr(self.lines))
        self.assertEqual(self.lines[0].split()[0:5], ["*/15", "*", "*", "*", "*"],
                         "the job decides its own window; the cron line must "
                         "not add one")

    def test_the_entry_runs_under_utc_with_the_close_job_wrapper(self):
        self.assertRegex(self.text, r"(?m)^TZ=UTC\s")
        line = self.lines[0]
        self.assertIn("cd $EEPHUS && ", line)
        self.assertIn("$PY tools/betting_lineup_job.py", line)
        self.assertIn(">> logs/betting-lineup.log 2>&1", line)

    def test_the_free_capture_does_not_depend_on_the_key_file(self):
        self.assertNotIn("/etc/eephus.env", self.lines[0],
                         "the job spends no credit and needs no key; a missing "
                         "env file must not stop the capture")


if __name__ == "__main__":
    unittest.main()
