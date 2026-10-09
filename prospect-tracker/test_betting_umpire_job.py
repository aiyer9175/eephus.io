# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The dark umpire capture records the plate assignment and nothing beside it.

The registration ("The home-plate umpire: a dark pregame assignment capture" in
docs/diamond-betting.md, long form docs/BETTING_UMPIRE_GATE.md) counts an
assignment only when a row here was captured before the slate's price vintage,
and forbids relating any of it to a game outcome or a price outside its look.
So the properties pinned here are:

  * no outcome field sits beside an assignment: the parse is an allowlist, and
    every file the job writes is walked for score, winner, line and price keys
    after a run fed a payload that carries them;
  * nothing served imports the job, and the job imports no pricer, settle,
    scores or results module;
  * a row is written only on a CHANGE of the plate assignment, only while the
    game is pregame and at least 5 minutes from first pitch;
  * one call per invocation, counted on the fetch helper, at the one endpoint;
  * a written capture is immutable.

Nothing here touches the network.
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
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import betting_umpire_job as job  # noqa: E402

FIRST = datetime(2027, 5, 4, 23, 5, tzinfo=timezone.utc)
JOB_SRC = ROOT / "tools" / "betting_umpire_job.py"


@functools.lru_cache(maxsize=1)
def _tree() -> ast.Module:
    return ast.parse(JOB_SRC.read_text(encoding="utf-8"))


def _imported_names() -> set[str]:
    out: set[str] = set()
    for n in ast.walk(_tree()):
        if isinstance(n, ast.Import):
            for a in n.names:
                out.add(a.name)
                out.add(a.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
            out.add(n.module.split(".")[0])
    return out


def _sched_game(pk=900001, first_pitch=None, *, hp=(5001, "Plate Umpire"),
                state="Preview", detail="Scheduled", game_type="R", with_outcome=True):
    """One game in the StatsAPI /schedule shape, deliberately carrying the
    outcome-shaped keys a real payload can carry, so the allowlist is tested."""
    officials = []
    if hp is not None:
        officials = [
            {"official": {"id": hp[0], "fullName": hp[1]}, "officialType": "Home Plate"},
            {"official": {"id": 5002, "fullName": "First Base"}, "officialType": "First Base"},
        ]
    g = {
        "gamePk": pk,
        "gameType": game_type,
        "officialDate": "2027-05-04",
        "gameDate": (first_pitch or FIRST).isoformat().replace("+00:00", "Z"),
        "doubleHeader": "N",
        "status": {"abstractGameState": state, "detailedState": detail},
        "venue": {"id": 3},
        "officials": officials,
        "teams": {
            "home": {"team": {"id": 111, "name": "Boston Red Sox"}},
            "away": {"team": {"id": 147, "name": "New York Yankees"}},
        },
    }
    if with_outcome:
        g["teams"]["home"].update({"score": 5, "isWinner": True,
                                   "leagueRecord": {"wins": 1, "losses": 0}})
        g["teams"]["away"].update({"score": 3, "isWinner": False})
        g["linescore"] = {"teams": {"home": {"runs": 5}, "away": {"runs": 3}}}
        g["seriesStatus"] = {"result": "BOS leads 1-0"}
        g["decisions"] = {"winner": {"id": 1}}
    return g


def _payload(*games):
    return {"dates": [{"date": "2027-05-04", "games": list(games)}]}


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


class _Store(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Path(self._tmp.name)
        job.reset_calls()

    def tearDown(self):
        self._tmp.cleanup()

    def install_slate(self, payload, fetched_at):
        job.write_slate(job.parse_games(payload), fetched_at, job.span_for(fetched_at),
                        path=self.store / job.SLATE_NAME)

    def run_with(self, payload, now):
        def fake_fetch(start, end):
            job.CALLS["n"] += 1
            return payload
        return job.run(now, store=self.store, fetch=fake_fetch)

    def captures(self):
        return [json.loads(p.read_text(encoding="utf-8")) for p in job.capture_files(self.store)]


class NoOutcomeBesideAnAssignment(_Store):
    def test_the_parse_is_an_allowlist(self):
        g = job.parse_games(_payload(_sched_game()))[0]
        self.assertEqual(g["hp_umpire_id"], 5001)
        self.assertEqual(g["hp_umpire_name"], "Plate Umpire")
        for k in _walk_keys(g):
            self.assertNotIn(k, job.OUTCOME_KEYS, f"outcome key {k!r} survived the parse")

    def test_every_file_the_job_writes_is_free_of_outcome_keys(self):
        now = FIRST - timedelta(hours=6)
        d = self.run_with(_payload(_sched_game()), now)
        self.assertEqual(d["decision"], "captured")
        job.write_heartbeat(d, store=self.store)
        job.append_runlog(d, now, store=self.store)
        files = [p for p in self.store.iterdir() if p.is_file()]
        self.assertTrue(any(job.CAPTURE_NAME_RE.match(p.name) for p in files))
        for p in files:
            text = p.read_text(encoding="utf-8")
            docs = ([json.loads(ln) for ln in text.splitlines() if ln.strip()]
                    if p.suffix == ".jsonl" else [json.loads(text)])
            for doc in docs:
                bad = [k for k in _walk_keys(doc) if k in job.OUTCOME_KEYS]
                self.assertEqual(bad, [], f"{p.name} carries outcome keys {bad}")

    def test_a_row_carries_exactly_the_registered_fields(self):
        self.run_with(_payload(_sched_game()), FIRST - timedelta(hours=6))
        cap = self.captures()[0]
        self.assertEqual(cap["schema"], job.CAPTURE_SCHEMA)
        self.assertEqual(list(cap["rows"][0].keys()), list(job.ROW_FIELDS))
        self.assertEqual(cap["rows"][0]["crew"],
                         [{"type": "Home Plate", "id": 5001}, {"type": "First Base", "id": 5002}])

    def test_the_call_asks_for_officials_and_nothing_else(self):
        params = job.schedule_params("2027-05-03", "2027-05-06")
        self.assertEqual(params["hydrate"], "officials")
        self.assertEqual(params["gameType"], "R,F,D,L,W")


class TheChangeRule(_Store):
    def test_a_first_sighting_with_a_plate_umpire_writes_one_row(self):
        d = self.run_with(_payload(_sched_game()), FIRST - timedelta(hours=6))
        self.assertEqual(d["rows_written"], 1)
        row = self.captures()[0]["rows"][0]
        self.assertEqual(row["hp_umpire_id"], 5001)
        self.assertIsNone(row["last_unassigned_at"])
        self.assertAlmostEqual(row["lead_minutes"], 360.0)

    def test_an_unassigned_sighting_writes_nothing_and_brackets_the_next_row(self):
        t1 = FIRST - timedelta(hours=20)
        d1 = self.run_with(_payload(_sched_game(hp=None)), t1)
        self.assertEqual(d1["rows_written"], 0)
        self.assertEqual(self.captures(), [])
        t2 = t1 + timedelta(minutes=45)
        d2 = self.run_with(_payload(_sched_game()), t2)
        self.assertEqual(d2["rows_written"], 1)
        row = self.captures()[0]["rows"][0]
        self.assertEqual(row["last_unassigned_at"], job._iso(t1))
        self.assertEqual(row["captured_at"], job._iso(t2))

    def test_an_unchanged_assignment_writes_nothing(self):
        t1 = FIRST - timedelta(hours=6)
        self.run_with(_payload(_sched_game()), t1)
        d = self.run_with(_payload(_sched_game()), t1 + timedelta(minutes=40))
        self.assertEqual(d["rows_written"], 0)
        self.assertEqual(d["decision"], "no_change")
        self.assertEqual(len(self.captures()), 1)

    def test_a_different_umpire_writes_a_row(self):
        t1 = FIRST - timedelta(hours=6)
        self.run_with(_payload(_sched_game()), t1)
        d = self.run_with(_payload(_sched_game(hp=(5009, "Swap"))), t1 + timedelta(minutes=40))
        self.assertEqual(d["rows_written"], 1)
        self.assertEqual(self.captures()[-1]["rows"][0]["hp_umpire_id"], 5009)

    def test_a_retraction_writes_a_null_row(self):
        t1 = FIRST - timedelta(hours=6)
        self.run_with(_payload(_sched_game()), t1)
        d = self.run_with(_payload(_sched_game(hp=None)), t1 + timedelta(minutes=40))
        self.assertEqual(d["rows_written"], 1)
        row = self.captures()[-1]["rows"][0]
        self.assertIsNone(row["hp_umpire_id"])
        self.assertIsNone(row["hp_umpire_name"])


class TheRefusalBoundary(_Store):
    def test_no_row_inside_five_minutes(self):
        d = self.run_with(_payload(_sched_game()), FIRST - timedelta(minutes=4))
        self.assertEqual(d["rows_written"], 0)
        self.assertEqual(d["refused"]["late"], 1)

    def test_a_row_at_the_boundary_is_written(self):
        d = self.run_with(_payload(_sched_game()), FIRST - timedelta(minutes=5))
        self.assertEqual(d["rows_written"], 1)

    def test_a_live_game_is_refused(self):
        d = self.run_with(_payload(_sched_game(state="Live", detail="Warmup")),
                          FIRST - timedelta(hours=1))
        self.assertEqual(d["rows_written"], 0)
        self.assertEqual(d["refused"]["not_pregame"], 1)

    def test_a_postponed_game_is_refused(self):
        d = self.run_with(_payload(_sched_game(detail="Postponed")), FIRST - timedelta(hours=1))
        self.assertEqual(d["rows_written"], 0)

    def test_beyond_36_hours_is_out_of_window(self):
        d = self.run_with(_payload(_sched_game()), FIRST - timedelta(hours=37))
        self.assertEqual(d["rows_written"], 0)
        self.assertEqual(d["refused"]["out_of_window"], 1)


class TheGate(_Store):
    def test_no_slate_calls_and_says_so(self):
        d = job.decide(FIRST, slate=None, slate_path=self.store / "none.json")
        self.assertTrue(d["call"])
        self.assertEqual(d["decision"], "no_local_slate")

    def test_in_window_calls_only_after_the_interval(self):
        t0 = FIRST - timedelta(hours=6)
        self.install_slate(_payload(_sched_game()), t0)
        slate = job.read_slate(self.store / job.SLATE_NAME)
        self.assertEqual(job.decide(t0 + timedelta(minutes=10), slate)["decision"], "too_soon")
        self.assertFalse(job.decide(t0 + timedelta(minutes=10), slate)["call"])
        d = job.decide(t0 + timedelta(minutes=30), slate)
        self.assertTrue(d["call"])
        self.assertEqual(d["decision"], "capture")

    def test_a_stale_slate_is_an_error_that_still_calls(self):
        t0 = datetime(2027, 5, 4, 1, 0, tzinfo=timezone.utc)
        self.install_slate(_payload(_sched_game(first_pitch=FIRST + timedelta(days=3))), t0)
        slate = job.read_slate(self.store / job.SLATE_NAME)
        d = job.decide(t0 + timedelta(hours=7), slate)
        self.assertEqual(d["decision"], "slate_stale")
        self.assertTrue(d["error"])
        self.assertTrue(d["call"])

    def test_the_span_reaches_two_utc_dates_ahead(self):
        self.assertEqual(job.span_for(datetime(2027, 5, 4, 23, 0, tzinfo=timezone.utc)),
                         ("2027-05-03", "2027-05-06"))


class OneCallAndImmutability(_Store):
    def test_an_acting_invocation_calls_exactly_once(self):
        self.run_with(_payload(_sched_game()), FIRST - timedelta(hours=6))
        self.assertEqual(job.CALLS["n"], 1)

    def test_a_no_op_invocation_calls_zero_times(self):
        t0 = FIRST - timedelta(hours=6)
        self.install_slate(_payload(_sched_game()), t0)
        job.reset_calls()
        d = self.run_with(_payload(_sched_game()), t0 + timedelta(minutes=5))
        self.assertEqual(d["decision"], "too_soon")
        self.assertEqual(job.CALLS["n"], 0)

    def test_the_real_fetch_helper_makes_one_request_at_the_schedule(self):
        seen = []

        class _Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(url, timeout=30):
            seen.append(url)
            return _Resp(json.dumps(_payload()).encode("utf-8"))

        with mock.patch.dict(sys.modules, {"feed_cache": None}), \
                mock.patch.object(job.urllib.request, "urlopen", fake_urlopen):
            job.fetch_schedule("2027-05-03", "2027-05-06")
        self.assertEqual(len(seen), 1)
        self.assertEqual(job.CALLS["n"], 1)
        self.assertTrue(seen[0].startswith(job.SCHEDULE_API + "?"))
        self.assertIn("hydrate=officials", seen[0])
        self.assertNotIn("linescore", seen[0])

    def test_a_failed_call_is_loud(self):
        def boom(start, end):
            raise OSError("down")
        d = job.run(FIRST - timedelta(hours=6), store=self.store, fetch=boom)
        self.assertTrue(d["error"])
        self.assertEqual(d["decision"], "fetch_failed")

    def test_a_second_write_in_the_same_minute_raises_and_keeps_the_first(self):
        now = FIRST - timedelta(hours=6)
        row = {k: None for k in job.ROW_FIELDS}
        p = job.write_capture([dict(row, game_pk=1)], now, store=self.store)
        first = p.read_bytes()
        with self.assertRaises(FileExistsError):
            job.write_capture([dict(row, game_pk=2)], now, store=self.store)
        self.assertEqual(p.read_bytes(), first)

    def test_only_captures_match_the_capture_name(self):
        self.run_with(_payload(_sched_game()), FIRST - timedelta(hours=6))
        job.write_heartbeat({"decision": "x"}, store=self.store)
        names = sorted(p.name for p in job.capture_files(self.store))
        self.assertEqual(len(names), 1)
        for other in (job.SLATE_NAME, job.UNASSIGNED_NAME, job.HEARTBEAT_NAME):
            self.assertIsNone(job.CAPTURE_NAME_RE.match(other))


class NothingServedReadsThisJob(unittest.TestCase):
    IMPORT_RE = re.compile(
        r"^\s*(?:import\s+betting_umpire_job"
        r"|from\s+betting_umpire_job\s+import"
        r"|from\s+tools\s+import\s+[^\n]*betting_umpire_job"
        r"|from\s+tools\.betting_umpire_job\s+import)"
        r"|import_module\(\s*['\"](?:tools\.)?betting_umpire_job['\"]",
        re.M)

    def test_no_module_in_the_tree_imports_the_job(self):
        me = {"betting_umpire_job.py", "test_betting_umpire_job.py"}
        offenders = []
        for p in list(ROOT.glob("*.py")) + list((ROOT / "tools").glob("*.py")):
            if p.name in me or p.name.startswith("test_") or p.name == "conftest.py":
                continue
            if self.IMPORT_RE.search(p.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(p.name)
        self.assertEqual(offenders, [], f"the capture must stay dark; these import it: {offenders}")

    def test_no_page_script_or_build_names_the_job_or_its_store(self):
        targets = list((ROOT / "assets").glob("*.js")) + [ROOT / "build_site.py",
                                                          ROOT / "run_monthly.py"]
        for p in targets:
            if not p.exists():
                continue
            src = p.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("betting_umpire_job", src, p.name)
            self.assertNotIn("umpire_captures", src, p.name)

    def test_the_job_imports_no_pricer_or_outcome_module(self):
        imported = _imported_names()
        allowed = {"__future__", "argparse", "json", "logging", "os", "re", "sys",
                   "urllib", "urllib.parse", "urllib.request", "datetime", "pathlib",
                   "feed_cache"}
        self.assertEqual(imported - allowed, set(),
                         "the capture job may import only the standard library and "
                         "the fetch session")

    def test_the_only_endpoint_in_the_file_is_the_statsapi_schedule(self):
        urls = [n.value for n in ast.walk(_tree())
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and "http" in n.value]
        self.assertEqual(urls, ["https://statsapi.mlb.com/api/v1/schedule"])

    def test_the_job_never_names_a_game_feed(self):
        src = JOB_SRC.read_text(encoding="utf-8")
        for needle in ("feed/live", "game_feeds", "boxscore", "/linescore"):
            self.assertNotIn(needle, src)


class TheOfflineChecks(unittest.TestCase):
    def test_selfcheck_is_nonzero_when_never_run(self):
        with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()):
            self.assertEqual(job.main(["--selfcheck", "--store", d]), 1)

    def test_why_makes_no_call(self):
        job.reset_calls()
        with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(job.main(["--why", "--store", d]), 0)
        self.assertEqual(job.CALLS["n"], 0)
        self.assertIn("no_local_slate", out.getvalue())


if __name__ == "__main__":
    unittest.main()
