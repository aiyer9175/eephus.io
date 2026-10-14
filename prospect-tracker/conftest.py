# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Shared test fixtures.

RAW-ENGINE MODULES: the surplus test files below pin the mixture model's
ALGEBRA (mean preservation, role ratios, portfolio additivity, anchor
reconciliation). The WS-6 empirical calibration layer (isotonic-real,
value_framework_config calibration block) sits ON TOP of that algebra via
apply_calibration and intentionally bends levels to match realized
outcomes — so it is disabled for these modules. The layer itself is
tested explicitly in test_value_framework.py::test_calibration_layer_*
and test_backtest.py."""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import socketserver
import threading
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# MLB Scores job isolation (SCORES_2_JOB_AND_DEPLOY). Every path
# tools/scores_job.py writes resolves through EEPHUS_SCORES_STORE and
# EEPHUS_SCORES_OUT, so both point at one session temp directory here, at
# conftest import, BEFORE any test imports the job. .cache/scores is
# gitignored, so the artifact guard below can neither revert nor protect it;
# test_scores_job.py asserts every resolved path sits inside this directory.
# ---------------------------------------------------------------------------
import atexit as _atexit
import os as _os
import shutil as _shutil
import tempfile as _tempfile

_SCORES_TEST_ROOT = Path(_tempfile.mkdtemp(prefix="eephus_scores_tests_"))
_os.environ["EEPHUS_SCORES_TEST_ROOT"] = str(_SCORES_TEST_ROOT)
_os.environ["EEPHUS_SCORES_STORE"] = str(_SCORES_TEST_ROOT / "store")
_os.environ["EEPHUS_SCORES_OUT"] = str(_SCORES_TEST_ROOT / "out")
_atexit.register(_shutil.rmtree, str(_SCORES_TEST_ROOT), True)

# A persisted FA gate re-runs the FA export (fa_backtest.reexport_fa_sidecars,
# owner answer M14-1), which writes the served data/fa_* sidecars. No test may
# reach that second output path through a gate run: the harness turns it off,
# and test_fa_gate_reexport.py drives the re-export against a temp directory.
_os.environ["FA_GATE_REEXPORT"] = "0"

# ---------------------------------------------------------------------------
# Session-shared parses of the large data/ JSON artifacts.
#
# timeseries.json is ~65MB and was being independently json.load-ed by many
# test modules (~36 parses per full-suite run, ~25s locally, more on the
# deploy box). Parse each artifact ONCE per session and share the object.
#
# READ-ONLY CONTRACT: every consumer shares the SAME parsed object. A
# consumer must never mutate the returned doc (no .pop/del/assignment into
# entries). All converted call sites were audited read-only on 2026-07-17
# (including spotlights.compute_movement, which copies driver dicts before
# annotating). A future consumer that needs to mutate must deepcopy its
# slice instead of writing into the shared doc.
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent / "data"
_SITE_ROOT = Path(__file__).resolve().parent


class _QuietHTTP(http.server.SimpleHTTPRequestHandler):
    """Static handler for the browser tests. TWO non-default settings, both
    load-bearing, which is why this lives in ONE place instead of being
    re-typed in each test module.

    HTTP/1.1 (the stdlib default is HTTP/1.0) -- THIS IS THE BUG FIX.
    Under HTTP/1.0 the handler sets close_connection after every response, so
    the server signals end-of-body by CLOSING THE SOCKET. On Windows that
    close races the send buffer: for a small file the whole body is already
    buffered and delivered, but for a large one the close can discard the
    tail, and the browser sits waiting for bytes that will never arrive until
    page.goto times out. Measured 2026-08-04: assets/site.css is 211KB and was
    the ONLY asset big enough to lose the race, which is exactly why the
    failures looked random and hit a different subset of tests every run.
    Under HTTP/1.1 the response is framed by Content-Length (which
    SimpleHTTPRequestHandler already sends), so no close is needed to mark the
    end and there is nothing to race. Verified: same page, same file, HTTP/1.0
    times out at 12s and HTTP/1.1 loads in 0.02s.

    log_message silenced so a failing assertion is not buried in access logs.
    """

    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002 (matches stdlib sig)
        pass


def make_static_server(directory: str | Path | None = None):
    """(httpd, port), already serving on a background thread.

    THREADING IS REQUIRED, not an optimisation, for TWO independent reasons.
    Both were learned the hard way in separate test modules and are recorded
    here so a future consolidation cannot drop one of them:
      * The homepage boot path kicks off a large async fetch of
        data/timeseries.json (~58MB). On a single-threaded server that blocks
        the remaining load-blocking resources and pushes
        page.goto(wait_until="load") past its timeout. A threaded server
        serves concurrently, like real static hosting.
      * HTTP/1.1 keeps connections alive and a browser opens several in
        parallel for one page, so a single-threaded server would hold the
        first open and DEADLOCK on the rest.
    daemon_threads so a kept-alive connection cannot outlive the test and hang
    server_close().

    Caller owns shutdown, and owes BOTH calls: shutdown() stops serve_forever,
    server_close() releases the listening socket. Without the latter the socket
    lingers until GC and surfaces as a ResourceWarning on Python 3.13+.
    Prefer serve_site(), which does both, where the `with` shape fits.
    """
    root = str(directory or _SITE_ROOT)
    handler = functools.partial(_QuietHTTP, directory=root)
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler,
                                            bind_and_activate=False)
    httpd.daemon_threads = True
    httpd.allow_reuse_address = True
    httpd.server_bind()
    httpd.server_activate()
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


@contextlib.contextmanager
def serve_site(directory: str | Path | None = None):
    """Serve the site root over loopback; yields the base URL with a trailing
    slash. Use in a `with` block or wrap in a fixture."""
    httpd, port = make_static_server(directory)
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        httpd.shutdown()
        httpd.server_close()


@functools.lru_cache(maxsize=None)
def load_data_doc(name: str):
    """Session-cached json.load of data/<name>. Returns None when the
    artifact is missing or unparseable (callers turn that into a skip -
    the same skip-if-missing semantics the per-module loaders had).

    Plain function (not a fixture) so unittest-style modules can share the
    cache too: `from conftest import load_data_doc` works because the
    prospect-tracker dir is on sys.path both under pytest and standalone."""
    path = _DATA_DIR / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _player_list(doc):
    """Normalize a timeseries/debuts doc to its player list (mirrors the
    per-module _load helpers this cache replaced)."""
    if isinstance(doc, list):
        return doc
    return doc.get("players") or doc.get("debuts") or []


@pytest.fixture(scope="session")
def timeseries_doc():
    """The parsed data/timeseries.json doc, shared session-wide. Read-only."""
    doc = load_data_doc("timeseries.json")
    if doc is None:
        pytest.skip("data/timeseries.json not built")
    return doc


@pytest.fixture(scope="session")
def debuts_doc():
    """The parsed data/debuts.json doc, shared session-wide. Read-only."""
    doc = load_data_doc("debuts.json")
    if doc is None:
        pytest.skip("data/debuts.json not present")
    return doc


@pytest.fixture(scope="session")
def players_by_key(timeseries_doc, debuts_doc):
    """The pros+grads merged {player_key: player} dict several modules used
    to rebuild from their own parses. Shared session-wide. Read-only."""
    pros = _player_list(timeseries_doc)
    grads = _player_list(debuts_doc)
    return {p["player_key"]: p for p in (pros + grads) if p.get("player_key")}

_RAW_ENGINE_MODULES = (
    "test_config_base_verification",
    "test_debuted",
    "test_pitcher_roles",
    "test_portfolio",
    "test_source_disagreement",
    "test_value_framework_integration",
)


@pytest.fixture(autouse=True)
def _raw_surplus_engine(request):
    if request.module.__name__ not in _RAW_ENGINE_MODULES:
        yield
        return
    import value_framework as vf
    cfg = vf._config().get("calibration", {})
    saved = cfg.get("enabled")
    cfg["enabled"] = False
    try:
        yield
    finally:
        cfg["enabled"] = saved


# Modules that pin base-engine ALGEBRA / calibration MAGNITUDES (discount + $/WAR
# reference values, surplus continuity/convexity/escalation, WAG talent convergence,
# FA winter-dpw math). These were calibrated under the base-identity set. The
# 2026-07 production-default flip to clemens_2026 overlays the SHARED $/WAR + salary
# + discount conventions, which shifts those magnitudes site-wide; pin these unit
# tests to the base set (prospx_current) so they keep testing the mechanics against
# their stable reference. The SHIPPED production numbers (now clemens) are covered
# by test_value_framework_integration + reports/validation.md, not these unit tests.
_BASE_SET_MODULES = (
    "test_config_base_verification",
    "test_debuted",
    "test_pitcher_roles",
    "test_fa_class",
    "test_fa_market",
    "test_proj_export",
    "test_wag",
)


@pytest.fixture(autouse=True)
def _pin_base_valuation_set(request):
    if request.module.__name__ not in _BASE_SET_MODULES:
        yield
        return
    import value_framework as vf
    with vf.valuation_set("prospx_current"):
        yield


@pytest.fixture(autouse=True)
def _isolate_odds_credit_ledgers(tmp_path_factory, monkeypatch):
    """No test may book credits to the REAL odds ledgers.

    Found 2026-09-11: test_betting_props armed a pull with a fake session and
    injected only the props-only ledger path, while betting_ingest also books
    every props pull to the SHARED tier ledger (.cache/betting/credits-*.json).
    Each run added four phantom credits under the test's fake event id `ev9`; thirty
    runs read as the whole 120-credit props allocation spent, which then refused
    the test's own pull and would have refused every real props pull this month.
    No request ever left the box, but the ledger is what the pre-request guard
    reads, so a polluted ledger is a real outage.

    Both ledgers are redirected for every test; a test that wants its own path
    still passes one explicitly."""
    d = tmp_path_factory.mktemp("odds_ledgers")
    try:
        import betting_credits
        monkeypatch.setattr(betting_credits, "LEDGER_DIR", d / "betting")
    except Exception:                                     # noqa: BLE001
        pass
    try:
        import betting_ingest
        monkeypatch.setattr(betting_ingest, "PROPS_SPEND_PATH", d / "props_spend.json")
        # Found 2026-09-11 (second leak, same test): bi.run() ends in
        # write_status(), which wrote the REAL data/betting_status.json with the
        # fixture's state (props armed, cap 6, events ev9/ev10, zero snapshots).
        # The page would have told readers props were armed.
        monkeypatch.setattr(betting_ingest, "STATUS_PATH", d / "betting_status.json")
    except Exception:                                     # noqa: BLE001
        pass
    yield


@pytest.fixture(scope="session")
def _schema5_tally_path(tmp_path_factory):
    """A per-session copy of the pinch-hit tally memo. Seeded from the real memo
    when one exists (read, never written), so a suite run pays the season's feed
    scan at most once and never touches .cache/betting/ph_tally.json."""
    import shutil
    p = tmp_path_factory.mktemp("schema5") / "ph_tally.json"
    try:
        import betting_usage
        if betting_usage.PH_TALLY_PATH.exists():
            shutil.copyfile(betting_usage.PH_TALLY_PATH, p)
    except Exception:                                     # noqa: BLE001
        pass
    return p


@pytest.fixture(autouse=True)
def _isolate_schema5_capture(_schema5_tally_path, monkeypatch):
    """No test may write the real schema-5 capture state or reach the network
    through it (docs/diamond-betting.md 5f and 5g).

    Any test that calls leaderboard_vintages.reduce_current runs every schema-5
    builder. Two of them have side effects outside a tmp dir: the pinch-hit tally
    memoizes into .cache/betting/ph_tally.json, and the team-fielding loader goes
    through the shared scraper cache, which REFETCHES a stale season file. The
    memo is redirected to a session copy and the fielding loader returns nothing,
    which the builder records as a stated null; a test of that builder injects
    its own loader."""
    try:
        import betting_usage
        monkeypatch.setattr(betting_usage, "PH_TALLY_PATH", _schema5_tally_path)
    except Exception:                                     # noqa: BLE001
        pass
    try:
        import leaderboard_vintages
        monkeypatch.setattr(leaderboard_vintages, "_load_fld_sources",
                            lambda season: None)
    except Exception:                                     # noqa: BLE001
        pass
    yield


@pytest.fixture(autouse=True)
def _isolate_game_intensity_capture(monkeypatch):
    """No test reaches StatsAPI or the results cache through the game-intensity
    capture (the section "Game intensity: stakes, matchup quality and the
    postseason"): a live snapshot written today by a test would otherwise fetch
    two schedules and run 20,000 simulations. The read returns nothing, which the
    builder records as a stated null; a test of the builder passes its own inputs."""
    try:
        import intensity_vintage
        monkeypatch.setattr(intensity_vintage, "load_inputs", lambda *a, **k: None)
    except Exception:                                     # noqa: BLE001
        pass
    yield


@pytest.fixture(autouse=True)
def _isolate_starter_workload_capture(tmp_path_factory, monkeypatch):
    """No test writes the real starter-workload tally memo or scans a season of
    feeds through the schema-7 capture (the section "Starter workload: expected
    outs and pitches per start"). The memo goes to a temp file and the stage-1
    record path to an absent file, so a reduce_current call inside an unrelated
    test opens no feed and stores the five columns as stated nulls; a test of the
    builder passes its own record, memo and feeds."""
    try:
        import betting_usage
        d = tmp_path_factory.mktemp("schema7")
        monkeypatch.setattr(betting_usage, "SW_TALLY_PATH", d / "workload_tally.json")
        monkeypatch.setattr(betting_usage, "SW_ARTIFACT", d / "absent_stage1.json")
    except Exception:                                     # noqa: BLE001
        pass
    yield


@pytest.fixture(scope="session", autouse=True)
def _restore_committed_build_artifacts():
    """Test-hygiene guard for committed BUILD ARTIFACTS (data/ sidecars +
    generated HTML pages).

    Many tests invoke generators whose output path DEFAULTS to the real tree:
    build_site rewrites the homepage + module shells (index.html, 404.html,
    fa/, projections/, glossary/, news/, ...) and the wire ledger; eval/export
    helpers rewrite data/*.json (model_registry, trade_values, the *_eval
    sidecars, collegesavant_*, etc.). That leaves the working tree dirty after
    a run, and one writer can overwrite data/scout_reports.json - which a
    SIBLING test (test_scout_report_history) validates - leaving a corrupted
    file that fails on the NEXT run even though the suite was green.
    (prospx/index.html is hand-maintained source and build_site never writes
    it, so it is never touched here.)

    Snapshot which tracked files are clean at session start, then `git checkout`
    any the suite dirtied at session end. Files the dev/user had ALREADY
    modified (uncommitted source edits, a fresh run_monthly regen) are detected
    as dirty-at-start and left untouched by the git revert - so that half only
    reverts churn the TESTS introduced. No-ops cleanly when git is unavailable.
    `--relative` restricts the scope to this project subtree.

    The dirty-at-start half (2026-09-11). A fresh local regen leaves ~100
    tracked data files dirty, and the git revert cannot see a test overwrite
    one of those: that is how fixture state reached data/betting_status.json.
    So each dirty-at-start file's BYTES are copied aside at session start and
    put back at the end if a test changed them, and the terminal summary names
    every file restored, so a new leak is visible instead of silent.

    The UNTRACKED half (2026-09-17). Both halves above are keyed off `git
    diff`, which sees only TRACKED files, so a served artifact that is new and
    not yet committed is covered by neither. That is not hypothetical: the day
    war_board_export started writing data/war_seasons.json beside the eWAR
    board, test_war_board_export_contract's harness redirected OUT_PATH but not
    the new SEASONS_OUT_PATH, and one pytest run replaced a 5,149-player
    substrate with a 20-player fixture named H1..H20. Nothing could put it back.
    So every untracked file under data/ is snapshotted too: one a test CHANGED
    is restored from its bytes, one a test CREATED is deleted, and both are
    named in the terminal summary. A brand-new artifact is exactly the case
    where the tree has no other copy to recover from."""
    import hashlib
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path
    here = Path(__file__).resolve().parent

    def _dirty() -> set[str]:
        try:
            out = subprocess.run(
                ["git", "diff", "--name-only", "--relative"],
                cwd=here, capture_output=True, text=True, check=False)
        except (FileNotFoundError, OSError):
            return set()  # no git in this environment -> guard is a no-op
        return {ln.strip() for ln in out.stdout.splitlines() if ln.strip()}

    def _digest(p: Path) -> str | None:
        try:
            return hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            return None

    def _untracked_data() -> set[str]:
        """Untracked files under data/, which `git diff` never reports."""
        try:
            out = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard",
                 "--", "data"],
                cwd=here, capture_output=True, text=True, check=False)
        except (FileNotFoundError, OSError):
            return set()
        return {ln.strip() for ln in out.stdout.splitlines() if ln.strip()}

    dirty_at_start = _dirty()
    aside = Path(tempfile.mkdtemp(prefix="pt_dirty_at_start_"))
    kept: dict[str, str | None] = {}
    for rel in sorted(dirty_at_start):
        if rel.startswith("..") or "/.." in rel:
            continue
        src = here / rel
        if not src.is_file():
            continue
        dst = aside / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        kept[rel] = _digest(src)
    untracked_at_start: dict[str, str | None] = {}
    for rel in sorted(_untracked_data()):
        if rel.startswith("..") or "/.." in rel:
            continue
        src = here / rel
        if not src.is_file():
            continue
        dst = aside / "_untracked" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        untracked_at_start[rel] = _digest(src)
    yield
    polluted = sorted(p for p in (_dirty() - dirty_at_start)
                      if not p.startswith("..") and "/.." not in p)
    if polluted:
        subprocess.run(["git", "checkout", "--", *polluted],
                       cwd=here, check=False)
    for rel, before in kept.items():
        if _digest(here / rel) != before:
            shutil.copy2(aside / rel, here / rel)
            _RESTORED_BY_GUARD.append(rel)
    for rel, before in untracked_at_start.items():
        if _digest(here / rel) != before:
            shutil.copy2(aside / "_untracked" / rel, here / rel)
            _RESTORED_BY_GUARD.append(rel + " (untracked)")
    for rel in sorted(_untracked_data() - set(untracked_at_start)):
        if rel.startswith("..") or "/.." in rel:
            continue
        target = here / rel
        if not target.is_file():
            continue
        try:
            target.unlink()
        except OSError:
            continue
        _RESTORED_BY_GUARD.append(rel + " (untracked, created by a test)")
    shutil.rmtree(aside, ignore_errors=True)


_RESTORED_BY_GUARD: list[str] = []


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Name every locally-modified file a test overwrote (and the guard put
    back), then the betting sidecar golden-hash verdict. A non-empty list is a
    test-isolation bug, even though the guard repaired the tree."""
    changed = _sidecar_final_report()
    if changed:
        terminalreporter.write_sep("-", "betting sidecar golden hash")
        terminalreporter.write_line(
            f"{len(changed)} watched artifact(s) moved during this run, so the "
            "run fails on that alone (repair 2, stop item X6). The likeliest "
            "cause is a test writing a served betting or DFS sidecar; a regen "
            "or a cron writing the same store while the suite ran looks the "
            "same from here, and the runbook says not to run the two "
            "together:")
        for row in changed:
            terminalreporter.write_line(f"  {row}")
        # Machine-readable duplicates for tools/run_suite.py, which reads only
        # lines beginning FAILED or ERROR. See _sidecar_runner_rows.
        for row in _sidecar_runner_rows(changed):
            terminalreporter.write_line(row)
    if not _RESTORED_BY_GUARD:
        return
    terminalreporter.write_sep("-", "build-artifact guard")
    terminalreporter.write_line(
        f"restored {len(_RESTORED_BY_GUARD)} locally-modified file(s) a test "
        "overwrote (a test-isolation bug to fix):")
    for rel in _RESTORED_BY_GUARD:
        terminalreporter.write_line(f"  {rel}")


# ===========================================================================
# BETTING AND DFS SIDECAR ISOLATION
#
# Repair 2 of docs/master-plan-2026-09-11-war-epoch-drivers-betting.md section
# 4.2, and the enforcement of its stop item X6 ("letting tests write betting
# artifacts").
#
# TWO INDEPENDENT HALVES, because neither one can be trusted alone.
#
#   1. A REDIRECT. Every betting/DFS module constant that names a write target
#      by default is pointed at a per-session mirror BEFORE THE FIRST FIXTURE
#      OF ANY SCOPE IS SET UP, so a generator invoked with no explicit path
#      writes the mirror and not the checkout. This is prevention, and it only
#      ever covers the names in _SIDECAR_WRITE_TARGETS.
#
#   2. A GOLDEN HASH. The bytes of every watched artifact are hashed at session
#      start and again at session end; any difference fails the run and names
#      the file, plus the test that was running when it moved, where the
#      per-test watch could see it. This is detection, it covers writers nobody
#      listed, and it is the half that survives a module growing a new default
#      path next month.
#
# WHY DETECTION IS NOT ENOUGH ALONE: the two leaks found on 2026-09-11 (the
# shared credit ledger, then data/betting_status.json) had been running for
# weeks before anyone looked. WHY PREVENTION IS NOT ENOUGH ALONE: both of them
# went through constants nobody had thought to list.
#
# THE REDIRECT IS SESSION SCOPED, AND THAT IS THE WHOLE POINT. The first cut of
# this fixture was function scoped, and pytest sets up higher-scoped fixtures
# FIRST: every module-, class- and session-scoped fixture therefore ran against
# the real constants. That is not a hypothetical shape, it is the shape already
# in the tree. test_betting_publish_hygiene.py::built_payload is a module
# scoped fixture that calls be.build(write=False), and it has to hand-redirect
# bi.STATUS_PATH itself precisely because nothing else reached it; under the
# function-scoped cut it also topped up the real
# .cache/betting/completed_games.json through betting_model.GAME_CACHE, so the
# suite exited 1 on a run in which every test passed. A prevention half that
# misses the fixtures doing the heaviest work is prevention in name only.
#
# THE GOLDEN HASH DOES NOT REPAIR. _restore_committed_build_artifacts puts
# TRACKED files back, but .cache/ is gitignored, so a leak there leaves the
# store dirty on purpose: the fix is to redirect the writer, and a silent
# restore would race a real nightly writing the same store while a suite runs.
# ===========================================================================

#: The artifacts a test run must leave byte-identical, as globs under the
#: checkout root. The first four are the plan's list: the betting sidecars, the
#: DFS board, the durable betting store and the odds snapshot cache.
#: `.cache/odds/**/*` is watched even though nothing under it is redirected
#: below, because a captured board is the only copy that exists and no credit
#: buys it back.
#:
#: The last two are added here, because they are the same class of file and
#: nothing else guards them: `.cache/` is gitignored, so
#: _restore_committed_build_artifacts cannot see either one, and both are the
#: only record of a day that has passed. The DFS slate archive is what the
#: season-end DFS archive grader reads, and the two-start ledger is what the
#: two-start grader audit reads.
#:
#: RECURSIVE ON PURPOSE (`**/*`, not `*`). A single-star glob stops at the
#: directory itself, and the next repair in this same plan section puts the
#: slot lock at .cache/betting/published_slots/<slate>.json, a first-write-wins
#: vintage record that would have landed unwatched under a flat glob.
#:
#: .cache/betting/completed_games.json IS WATCHED, and it is a derived cache
#: rather than a served sidecar, so the decision is stated rather than implied:
#: it is the offline record of which games have finished, every grader and the
#: park gate read it, and a test's view of "completed" is a fixture. A test
#: topping it up writes fixture truth into the file the graders trust, so it
#: stays watched, and betting_model.GAME_CACHE is redirected so a top-up during
#: a test lands in the mirror instead.
_SIDECAR_GLOBS = (
    "data/betting*.json",
    "data/dfs.json",
    ".cache/betting/**/*",
    ".cache/odds/**/*",
    ".cache/dfs_history/**/*",
    ".cache/two_start_ledger.jsonl",
    # EV-00: the eFV progress ledger and its durable untracked copy. Both are
    # append-only records a test must never write into.
    "data/efv_progress.json",
    ".cache/efv_progress/**/*",
    # LIBRARY_11: the Model Updates record and its durable untracked copy,
    # append-only like the progress ledger it copies from.
    "data/model_updates.json",
    ".cache/model_updates/**/*",
    # EV-09: the development read of eFV v2 champion H0, a spent-frame record
    # the progress ledger copies from.
    "data/efv_v2_dev_eval.json",
    # DS-11 and DS-17: the overlay read and the P(bust) calibration read, both
    # development records the progress ledger copies from.
    "data/efv_overlay_oos_eval.json",
    "data/efv_v2_pbust_eval.json",
    # EFV3_D2: the scoreboard matrix artifact and its durable append-only
    # history copy, both written by tools/efv_matrix.py.
    "data/efv_matrix_eval.json",
    ".cache/efv_matrix/**/*",
    # EFV3_C05: the MC-5 pricing read, a development record the progress ledger
    # copies from (tools/efv_v2_pricing_calibration.py).
    "data/efv_v2_pricing_calibration_eval.json",
    # EFV3_C03: the one model-class screen (tools/efv_v2_model_class_screen.py), a
    # spent-frame record the progress ledger and the arm ledger copy from; and the
    # arm ledger itself, which the screen regenerates.
    "data/efv_v2_model_class_screen.json",
    "data/xfv_arm_ledger.json",
    # M21-4: the Fantasy Rank, its monthly model cache and its backtest.
    "data/fantasy_rank.json",
    "data/fantasy_rank_eval.json",
    ".cache/fantasy_rank_model.json",
    # Part 8 W04: the Dynasty lens Next to be graded.
    "data/fantasy_next_graded.json",
    # PV-02: the retained served provisional grade (untracked snapshots plus
    # the durable digest copy) and its tracked digest.
    ".cache/provisional_history/**/*",
    "data/provisional_history/digest.json",
    # PV-04: the append-only provisional track record and its durable copy.
    "data/provisional_track_eval.json",
    ".cache/provisional_track/**/*",
    # PV-06: provisional v2, the served heads and their BACKCAST eval.
    "data/provisional_v2.json",
    "data/provisional_v2_eval.json",
    # BRACKET_SIM_BUILD: the postseason bracket simulator's payload, its
    # first-write-wins forward record (source of truth and derived copy) and
    # the StatsAPI receipts it caches.
    "data/bracket_sim*.json",
    ".cache/bracket_sim/**/*",
    ".cache/bracket/**/*",
    # VAL_5: the one $/WAR series (whose writer gains the dpw_path block), the
    # gate's eval artifact (the tool's carry-forward and the lab's block), the
    # owner record and the prospective ledger. A test writes none of them.
    "data/fa_dpw_series.json",
    "data/dpw_forecast_eval.json",
    "data/dpw_path_owner.json",
    "data/dpw_path_ledger.json",
    # QPRP08: eta_backtest's served P(debut) curves (redirected below).
    "data/eta_curves.json",
    # PJ_6: proj_export's second output, the component lines (the preview under
    # .cache while dark, the card source under data/ once live).
    ".cache/proj_components/preview/**/*",
    "data/mlb_proj_components.json",
    # TL_22: tools/scouting_export.py's two outputs, the preview under .cache
    # while SCOUTING_PAGE_LIVE is False and the payload under data/ once live,
    # plus the preview page build_site writes beside it.
    ".cache/scouting/preview/**/*",
    "data/scouting_reference.json",
)

#: The small directories the PER-TEST watch re-lists, so a file a test CREATES
#: (a close-job heartbeat, a new snapshot, a slate archive, a slot lock) is
#: attributed to that test and not merely noticed at the end. data/ is not
#: re-listed per test (439 entries); a new data/betting*.json is caught by the
#: session-end sweep instead. 60 files across the three, walked recursively.
_SIDECAR_WATCH_DIRS = (".cache/betting", ".cache/odds", ".cache/dfs_history")


def _sidecar_files(root: Path) -> list[Path]:
    """Every watched file under `root`, deduplicated and sorted."""
    out: set[Path] = set()
    for pat in _SIDECAR_GLOBS:
        for p in root.glob(pat):
            if p.is_file():
                out.add(p)
    return sorted(out)


def _sidecar_is_watched(rel: str) -> bool:
    """Whether a checkout-relative posix path is one of the watched artifacts.

    Matched the way _SIDECAR_GLOBS is written rather than with fnmatch, which
    has no notion of `**` and would answer NO for every file sitting directly
    under .cache/betting. The directory half of a pattern is compared exactly
    and only the basename is globbed, so "data/betting*.json" cannot quietly
    claim data/betting/something.json."""
    import fnmatch
    for pat in _SIDECAR_GLOBS:
        if pat.endswith("/**/*"):
            if rel.startswith(pat[:-4]):
                return True
            continue
        pdir, _, pname = pat.rpartition("/")
        rdir, _, rname = rel.rpartition("/")
        if pdir == rdir and fnmatch.fnmatchcase(rname, pname):
            return True
    return False


def _sidecar_hash(p: Path) -> str | None:
    """sha256 of a file, or None when it is absent or unreadable. Absence is a
    state the report has to be able to name, so it is not an error here."""
    import hashlib
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def _sidecar_sig(p: Path):
    """The CHEAP per-test signal: (size, mtime_ns). It can fire when the bytes
    did not move (a rewrite of identical content), which is why the verdict is
    the hash and this only ever supplies the blame."""
    try:
        st = p.stat()
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)


def _sidecar_dir_sigs(root: Path, rel_dir: str) -> dict:
    """{relative posix path: signature} for one directory TREE, from scandir.

    The directory entry already carries the stat on Windows, so this is one
    pass per directory instead of one stat per file, which is what keeps a
    per-test guard off the suite's critical path. RECURSIVE, because a nested
    directory is exactly where a first-write-wins vintage record lands, and a
    flat scan would neither watch it in the checkout nor sweep it out of the
    mirror."""
    import os
    out = {}
    stack = [rel_dir]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(root / cur) as it:
                for e in it:
                    try:
                        if e.is_dir():
                            stack.append(f"{cur}/{e.name}")
                            continue
                        if not e.is_file():
                            continue
                        st = e.stat()
                    except OSError:
                        continue
                    out[f"{cur}/{e.name}"] = (st.st_size, st.st_mtime_ns)
        except OSError:
            continue
    return out


def _sidecar_snapshot(root: Path) -> dict[str, str | None]:
    """{relative posix path: sha256} for every watched file under `root`."""
    return {p.relative_to(root).as_posix(): _sidecar_hash(p)
            for p in _sidecar_files(root)}


def _sidecar_changes(before: dict, after: dict, blame: dict | None = None,
                     moved: dict | None = None) -> list[str]:
    """One report line per artifact whose BYTES moved.

    `before` and `after` are the session-start and session-end snapshots.
    `moved` carries the hashes the per-test watch saw MID-RUN, which is how a
    leak survives being repaired: _restore_committed_build_artifacts finalizes
    before the session-end sweep, so a tracked file a test overwrote is already
    back to its committed bytes by then and `after` alone would call the run
    clean. The per-test watch runs at each test's own teardown, earlier than
    any session fixture, so it sees the write while it is still on disk.

    THE NAMED TEST IS A SUSPECT, NOT A VERDICT, and the wording says so. All
    the watch knows is that the file changed while that test was running. A
    close-job cron or a run_monthly regen writing the same store during a suite
    run looks identical from here, which is why tools/run_suite.py already says
    not to run the suite alongside an edit or a regen.

    Pure, and takes its inputs as arguments, so the tripwire itself can be
    tested without writing to anything real (test_betting_sidecar_isolation)."""
    blame, moved = blame or {}, moved or {}
    rows = []
    for rel in sorted(set(before) | set(after) | set(moved)):
        was, now = before.get(rel), after.get(rel)
        who = list(blame.get(rel) or [])
        named = (", ".join(who[:4]) + (" and more" if len(who) > 4 else "")
                 if who else "no test the watch could see")
        if was != now:
            what = ("appeared" if was is None
                    else "disappeared" if now is None else "changed")
            rows.append(f"{rel}: {what} while running {named}")
        elif rel in moved and moved[rel] != was:
            rows.append(f"{rel}: changed while running {named}, and was put "
                        "back afterwards (a leak the build-artifact guard hid)")
    return rows


_SIDECAR_GOLDEN: dict[str, str | None] = {}
_SIDECAR_SIG: dict[str, object] = {}
_SIDECAR_BLAME: dict[str, list[str]] = {}
_SIDECAR_MOVED: dict[str, str | None] = {}
_SIDECAR_REPORT: list[str] | None = None
#: Modules in _SIDECAR_WRITE_TARGETS that would not import. Collected rather
#: than swallowed: the one state in which the redirect is silently OFF must not
#: also be the one state nothing reports.
_SIDECAR_IMPORT_FAILURES: dict[str, str] = {}


def pytest_sessionstart(session):
    """Hash every watched artifact before a single test runs."""
    _SIDECAR_GOLDEN.clear()
    _SIDECAR_SIG.clear()
    _SIDECAR_BLAME.clear()
    _SIDECAR_MOVED.clear()
    for p in _sidecar_files(_SITE_ROOT):
        rel = p.relative_to(_SITE_ROOT).as_posix()
        _SIDECAR_GOLDEN[rel] = _sidecar_hash(p)
        _SIDECAR_SIG[rel] = _sidecar_sig(p)


@pytest.fixture(autouse=True)
def _watch_betting_sidecars(request):
    """Attribute a moved artifact to the test that was running when it moved.

    Three directory walks plus one stat per watched file outside them (about
    15), which buys a named test in the failure instead of "somewhere in a
    900-test run"."""
    yield
    live = {}
    for d in _SIDECAR_WATCH_DIRS:
        live.update(_sidecar_dir_sigs(_SITE_ROOT, d))
    covered = tuple(f"{d}/" for d in _SIDECAR_WATCH_DIRS)
    for rel in _SIDECAR_SIG:
        if rel.startswith(covered):
            live.setdefault(rel, None)       # watched, and now gone
        else:
            live[rel] = _sidecar_sig(_SITE_ROOT / rel)
    node = request.node.nodeid
    for rel, sig in live.items():
        if rel in _SIDECAR_SIG and sig == _SIDECAR_SIG[rel]:
            continue
        _SIDECAR_SIG[rel] = sig
        # Only a HASH that left the golden value is a violation: a rewrite of
        # identical bytes moves the mtime and is not one.
        digest = _sidecar_hash(_SITE_ROOT / rel)
        if digest == _SIDECAR_GOLDEN.get(rel):
            continue
        _SIDECAR_MOVED[rel] = digest
        who = _SIDECAR_BLAME.setdefault(rel, [])
        if node not in who:
            who.append(node)


def _sidecar_final_report() -> list[str]:
    """The session verdict, computed once however it is first reached (the
    terminal summary under the default plugins, sessionfinish otherwise).

    A module this conftest could not import is part of the verdict: its
    constants were never redirected, so the run had a hole in it whatever the
    hashes say."""
    global _SIDECAR_REPORT
    if _SIDECAR_REPORT is None:
        rows = _sidecar_changes(
            _SIDECAR_GOLDEN, _sidecar_snapshot(_SITE_ROOT),
            _SIDECAR_BLAME, _SIDECAR_MOVED)
        for name in sorted(_SIDECAR_IMPORT_FAILURES):
            covers = sorted({rel for mod, _a, rel in _SIDECAR_WRITE_TARGETS
                             if mod == name})
            rows.append(
                f"{name}: could not be imported, so its redirect never "
                f"happened and {', '.join(covers) or 'its targets'} ran "
                f"unprotected ({_SIDECAR_IMPORT_FAILURES[name]})")
        _SIDECAR_REPORT = rows
    return _SIDECAR_REPORT


def _sidecar_runner_rows(changed: list[str]) -> list[str]:
    """The same verdict in the ONE shape tools/run_suite.py can read.

    The canonical way to run this suite is the chunked runner, and its verdict
    is built only from stdout lines that start with FAILED or ERROR:

        return 0 if (n_crash == 0 and not unexpected) else 1

    A sidecar-only violation is precisely a chunk that exits 1 with no such
    line, so without these rows the runner prints "No unexpected failures" and
    exits 0 over a run that rewrote a served artifact. The tripwire would bind
    for a bare `python -m pytest` and stay invisible to the runner everyone
    actually uses, which is the same thing as having no tripwire.

    The blamed node id is written with a SINGLE colon. run_suite decides a
    failure is expected by `any(known in node for known in
    KNOWN_BASELINE_REDS)`, and every entry in that list is a `file.py::test`
    string, so a leak blamed on one of those two tests would otherwise be
    absorbed into the baseline and disappear."""
    return [f"ERROR betting_sidecar_golden_hash::{row.replace('::', ':')}"
            for row in changed]


def pytest_sessionfinish(session, exitstatus):
    """FAIL THE RUN on a changed artifact, even when every test passed.

    A green suite that rewrote data/betting.json is not green: the next build
    publishes whatever the test left behind. pytest returns session.exitstatus
    after this hook, so setting it here is what makes the tripwire binding."""
    if _sidecar_final_report() and getattr(session, "exitstatus", 0) in (0, 5):
        session.exitstatus = 1


# ---------------------------------------------------------------------------
# The redirect
# ---------------------------------------------------------------------------

#: (module, attribute, path relative to the checkout root) for every betting or
#: DFS module-level constant that resolves onto a WATCHED artifact. A test that
#: passes its own path is unaffected; this is only about the no-argument call.
#:
#: WRITE TARGETS AND READERS ARE BOTH LISTED, deliberately. Three of these are
#: read-only today (tools.betting_floor_census.COMPLETED,
#: tools.dfs_park_gate.GAMES and mgmt_teams.GROUND_TRUTH, all three the results
#: cache). Pointing a reader at a mirror seeded from the real file changes no
#: byte it reads, and it makes the rule this block enforces the simple one: a
#: module-level path that lands on a watched artifact is redirected, with no
#: exceptions to remember. The first cut drew the line at "writers" and got it
#: wrong in a way worth recording: it redirected the three READ-ONLY copies of
#: the close-job heartbeat and attach-result paths in betting_learning and
#: betting_export, and left tools/betting_close_job.py, the module that
#: actually writes both files by default, untouched.
#:
#: NOT REDIRECTED, deliberately:
#:   * betting_ingest.CACHE_DIR (.cache/odds). Two tests replay a real snapshot
#:     through the live pipeline (test_betting_event_match,
#:     test_betting_line_consistency) and redirecting the directory would turn
#:     them into skips. The golden hash covers the snapshots instead, including
#:     one a test creates.
#:   * betting_credits.LEDGER_DIR, betting_ingest.PROPS_SPEND_PATH and
#:     STATUS_PATH, betting_usage.PH_TALLY_PATH: already redirected above by
#:     _isolate_odds_credit_ledgers and _isolate_schema5_capture.
_SIDECAR_WRITE_TARGETS = (
    ("betting_export", "OUT_PATH", "data/betting.json"),
    ("betting_export", "PREVIEW_PATH", "data/betting_preview.json"),
    ("betting_export", "RECORD_PATH", "data/betting_record.json"),
    ("betting_export", "RECORD_JSONL", ".cache/betting/record.jsonl"),
    ("betting_export", "SETTLEMENT_PATH", "data/betting_settlement.json"),
    ("betting_export", "CLV_PATH", "data/betting_clv.json"),
    ("betting_export", "PUBLISHED_CHAIN_PATH",
     ".cache/betting/published_chain.json"),
    ("betting_export", "MARKET_GATE_STATE_PATH",
     ".cache/betting/market_gate_state.json"),
    ("betting_export", "CLOSE_HEARTBEAT_PATH",
     ".cache/betting/close_job_heartbeat.json"),
    ("betting_learning", "LEARNING_PATH", "data/betting_learning.json"),
    ("betting_learning", "CLOSE_JOB_HEARTBEAT_PATH",
     ".cache/betting/close_job_heartbeat.json"),
    ("betting_learning", "CLOSE_ATTACH_RESULT_PATH",
     ".cache/betting/close_attach_result.json"),
    ("betting_model", "CONTEXT_PATH", "data/betting_model_context.json"),
    ("betting_model", "EVAL_PATH", "data/betting_model_eval.json"),
    ("betting_shadow", "SHADOW_CACHE_PATH", ".cache/betting/shadow.json"),
    ("betting_shadow", "SHADOW_PATH", ".cache/betting/shadow.json"),
    ("betting_shadow", "SHADOW_DERIVED_PATH", "data/betting_shadow.json"),
    ("betting_shadow", "READINESS_PATH", "data/betting_subledger.json"),
    ("betting_props_dark", "OUT", "data/betting_props_dark_eval.json"),
    ("dfs_export", "OUT_PATH", "data/dfs.json"),
    ("fantasy_export", "LEDGER_PATH", ".cache/two_start_ledger.jsonl"),
    # M21-4 (2026-10-01): fantasy_export's second output, the Dynasty Fantasy
    # Rank, plus the monthly model cache it re-ranks from nightly and the
    # registered backtest's artifact. All three resolve at call time.
    ("fantasy_rank", "RANK_PATH", "data/fantasy_rank.json"),
    ("fantasy_rank", "MODEL_CACHE", ".cache/fantasy_rank_model.json"),
    ("fantasy_rank", "EVAL_PATH", "data/fantasy_rank_eval.json"),
    # Part 8 W04 (2026-10-07): fantasy_export's third output, the Dynasty
    # lens Next to be graded, resolved at call time (_export_next_graded).
    ("fantasy_export", "NEXT_GRADED_PATH", "data/fantasy_next_graded.json"),
    # LIBRARY_11: the Model Updates record and its durable copy. Both resolve
    # at call time (model_updates._resolve), so a test that names no path
    # writes the mirror.
    ("model_updates", "OUT_PATH", "data/model_updates.json"),
    ("model_updates", "LEDGER_PATH", ".cache/model_updates/ledger.jsonl"),
    ("tools.betting_calibration", "LEDGER_PATH",
     ".cache/betting/calibration.jsonl"),
    # The close-job WRITER itself: `p = path or HEARTBEAT_PATH` and
    # `p = path or ATTACH_RESULT_PATH`.
    ("tools.betting_close_job", "HEARTBEAT_PATH",
     ".cache/betting/close_job_heartbeat.json"),
    ("tools.betting_close_job", "ATTACH_RESULT_PATH",
     ".cache/betting/close_attach_result.json"),
    # The market-blend lab writes its eval sidecar and appends the SAME
    # calibration ledger tools.betting_calibration owns.
    ("tools.betting_market_blend_lab", "OUT",
     "data/betting_market_blend_eval.json"),
    ("tools.betting_market_blend_lab", "LEDGER",
     ".cache/betting/calibration.jsonl"),
    # Readers of the results cache. See the note above: listed so the rule has
    # no exceptions, and so the day one of them grows a write it is covered.
    ("tools.betting_floor_census", "COMPLETED",
     ".cache/betting/completed_games.json"),
    ("tools.dfs_park_gate", "GAMES", ".cache/betting/completed_games.json"),
    ("mgmt_teams", "GROUND_TRUTH", ".cache/betting/completed_games.json"),
    # EV-00 progress ledger: the served file and the durable copy. update()
    # and the backfill tool resolve both at call time, so a test that runs
    # either against the real data dir writes the mirror.
    ("efv_progress", "OUT_PATH", "data/efv_progress.json"),
    ("efv_progress", "LEDGER_PATH", ".cache/efv_progress/ledger.jsonl"),
    # EV-09: tools/efv_v2_dev_read.py writes through efv_v2_model.DEV_EVAL_PATH,
    # resolved at call time.
    ("efv_v2_model", "DEV_EVAL_PATH", "data/efv_v2_dev_eval.json"),
    # DS-17: efv_v2_model.pbust_serving_arm reads the committed P(bust) read
    # through PBUST_EVAL_PATH, resolved at call time; mirrored like DEV_EVAL_PATH.
    ("efv_v2_model", "PBUST_EVAL_PATH", "data/efv_v2_pbust_eval.json"),
    # EFV3_D2: tools/efv_matrix.run and write_artifact resolve both at call time.
    ("tools.efv_matrix", "OUT_PATH", "data/efv_matrix_eval.json"),
    ("tools.efv_matrix", "HISTORY_PATH", ".cache/efv_matrix/history.jsonl"),
    # EFV3_C05: tools/efv_v2_pricing_calibration.write resolves OUT_PATH at call time.
    ("tools.efv_v2_pricing_calibration", "OUT_PATH",
     "data/efv_v2_pricing_calibration_eval.json"),
    # EFV3_C03: tools/efv_v2_model_class_screen.main resolves OUT_PATH at call time;
    # tools/efv_arm_ledger.main writes OUT, resolved at call time.
    ("tools.efv_v2_model_class_screen", "OUT_PATH", "data/efv_v2_model_class_screen.json"),
    ("tools.efv_arm_ledger", "OUT", "data/xfv_arm_ledger.json"),
    # VAL_3 surplus-odds gate: surplus_odds_gate.run writes its one read as a block
    # of its parent artifact through OUT_PATH, resolved at call time.
    ("surplus_odds_gate", "OUT_PATH", "data/surplus_backtest_real.json"),
    # M27-4: the Ledger exporter's second output, the Trade Machine's CBT
    # slice; write_trade_cbt resolves TRADE_CBT_OUT at call time.
    ("ledger_export", "TRADE_CBT_OUT", "data/trade_cbt.json"),
    # PV-02: provisional_history.retain resolves its tracked digest at call
    # time; the snapshot store is the CACHE_DIR directory below.
    ("provisional_history", "DIGEST_PATH", "data/provisional_history/digest.json"),
    # PV-04: provisional_track resolves both at call time (update / commit_rows).
    ("provisional_track", "OUT_PATH", "data/provisional_track_eval.json"),
    ("provisional_track", "LEDGER_PATH", ".cache/provisional_track/ledger.jsonl"),
    # PV-06: provisional_v2.build resolves both at call time (efv_export.regen_all
    # calls it when persisting).
    ("provisional_v2", "OUT_PATH", "data/provisional_v2.json"),
    ("provisional_v2", "EVAL_PATH", "data/provisional_v2_eval.json"),
    # BRACKET_SIM_BUILD: bracket_sim.run resolves all four at call time. The
    # board is only READ there (gate 3.1); it is listed so the rule has no
    # exception, the same reasoning as the results-cache readers above.
    ("bracket_sim", "OUT_PATH", "data/bracket_sim.json"),
    ("bracket_sim", "RECORD_PATH", ".cache/bracket_sim/record.json"),
    ("bracket_sim", "RECORD_DERIVED_PATH", "data/bracket_sim_record.json"),
    ("bracket_sim", "BOARD_PATH", "data/betting.json"),
    # VAL_5: the one writer's output and its readers, the files the dpw_path
    # block code reads, and the eval tool's output, all resolved at call time.
    ("fa_market", "DPW_SERIES_PATH", "data/fa_dpw_series.json"),
    ("value_framework", "_DPW_SERIES_PATH", "data/fa_dpw_series.json"),
    ("fa_class", "_DPW_SERIES_PATH", "data/fa_dpw_series.json"),
    ("fa_market", "DPW_OWNER_PATH", "data/dpw_path_owner.json"),
    ("fa_market", "DPW_EVAL_PATH", "data/dpw_forecast_eval.json"),
    ("tools.fit_dpw_forecast", "DEFAULT_OUT", "data/dpw_forecast_eval.json"),
    # VAL_5 commit 2b: the gate lab writes its block and ledger rows, and reads
    # the owner record and the series file, through these.
    ("tools.dpw_path_gate", "EVAL_PATH", "data/dpw_forecast_eval.json"),
    ("tools.dpw_path_gate", "LEDGER_PATH", "data/dpw_path_ledger.json"),
    ("tools.dpw_path_gate", "OWNER_PATH", "data/dpw_path_owner.json"),
    ("tools.dpw_path_gate", "SERIES_PATH", "data/fa_dpw_series.json"),
    # QPRP08: eta_backtest's second output, the served P(debut) curves.
    ("eta_backtest", "CURVES_PATH", "data/eta_curves.json"),
    # M11 prospect arbitration: arb_export's third output, the prospect rung
    # model, and its one reader; both resolved at call time.
    ("arb_export", "PROSPECT_RUNGS_PATH", "data/arb_prospect_rungs.json"),
    ("value_framework", "_ARB_PROSPECT_PATH", "data/arb_prospect_rungs.json"),
    # PJ_6: proj_export's second output, the component lines, and their one
    # reader; _write_components and _component_rows resolve them at call time.
    ("proj_export", "COMPONENTS_PREVIEW_PATH",
     ".cache/proj_components/preview/components.json"),
    ("proj_export", "COMPONENTS_LIVE_PATH", "data/mlb_proj_components.json"),
    ("mlb_player_export", "COMPONENTS_PATH", "data/mlb_proj_components.json"),
    # TL_22: tools/scouting_export.py's preview and its live payload, resolved
    # at call time by output_path() and write_payload().
    ("tools.scouting_export", "PREVIEW_PATH",
     ".cache/scouting/preview/scouting_reference.json"),
    ("tools.scouting_export", "OUT_PATH", "data/scouting_reference.json"),
)

#: Directory constants, redirected so a path BUILT from one at call time lands
#: in the mirror too (betting_export.BETTING_CACHE_DIR.mkdir, and the
#: betting_model.GAME_CACHE / "completed_games.json" top-up).
_SIDECAR_WRITE_DIRS = (
    ("betting_export", "BETTING_CACHE_DIR", ".cache/betting"),
    ("betting_shadow", "BETTING_CACHE_DIR", ".cache/betting"),
    ("betting_model", "GAME_CACHE", ".cache/betting"),
    ("dfs_export", "ARCHIVE_DIR", ".cache/dfs_history"),
    ("provisional_history", "CACHE_DIR", ".cache/provisional_history"),
    ("bracket_sim", "FETCH_CACHE_DIR", ".cache/bracket"),
)

#: Modules that turn one of these paths into a STRING for readers of a
#: published payload. See _sidecar_public_path for why the redirect owes them a
#: shim.
_SIDECAR_PUBLIC_PATH_MODULES = ("betting_export",)

#: Directories the mirror copies WHOLE, because a redirected directory constant
#: is read back as well as written (the results cache, the slate archive the
#: pruner counts) and a file nobody listed still has to be there to be read.
_SIDECAR_SEED_DIRS = (".cache/betting", ".cache/dfs_history")


_SIDECAR_MODULES: dict[str, object] = {}


def _sidecar_module(name: str):
    """The imported module, or None, resolved once per session.

    An import failure is RECORDED in _SIDECAR_IMPORT_FAILURES, not swallowed. A
    module this conftest cannot import is a module whose constants are not
    redirected, and the whole point of this block is that a guard which quietly
    stops working puts the original bug back."""
    if name not in _SIDECAR_MODULES:
        import importlib
        try:
            _SIDECAR_MODULES[name] = importlib.import_module(name)
        except Exception as exc:                          # noqa: BLE001
            _SIDECAR_MODULES[name] = None
            _SIDECAR_IMPORT_FAILURES[name] = f"{type(exc).__name__}: {exc}"
    return _SIDECAR_MODULES[name]


@pytest.fixture(scope="session")
def _betting_sidecar_mirror(tmp_path_factory):
    """A per-session copy of the sidecar tree, SEEDED FROM THE REAL FILES.

    Seeded, not empty, because most of these constants are read as well as
    written: betting_model.CONTEXT_PATH is the served context every pricing
    test reads, and GAME_CACHE / completed_games.json is the results cache an
    offline build reads back. An empty mirror would silently change what the
    tests price against, which is a worse bug than the one being fixed. The
    whole of .cache/betting and .cache/dfs_history is copied (3.7MB, about
    0.2s warm, once per session) so a file nobody listed is still there to be
    read.

    A second pristine copy sits beside it so the per-test fixture can put back
    whatever a test changed, which keeps the mirror from becoming a cross-test
    channel of its own. Returns (work, seed, seed signatures)."""
    import shutil
    root = tmp_path_factory.mktemp("betting_sidecars")
    work, seed = root / "work", root / "seed"
    (work / "data").mkdir(parents=True, exist_ok=True)
    for rel in _SIDECAR_SEED_DIRS:
        (work / rel).mkdir(parents=True, exist_ok=True)
        src_dir = _SITE_ROOT / rel
        if src_dir.is_dir():
            shutil.copytree(src_dir, work / rel, dirs_exist_ok=True)
    for _mod, _attr, rel in _SIDECAR_WRITE_TARGETS:
        src, dst = _SITE_ROOT / rel, work / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_file() and not dst.exists():
            shutil.copy2(src, dst)
    shutil.copytree(work, seed)
    # The seed manifest is taken ONCE. Walking it per test would double the
    # teardown cost of every test in the suite for a tree that cannot change.
    sigs = {p.relative_to(seed).as_posix(): _sidecar_sig(p)
            for p in seed.rglob("*") if p.is_file()}
    return work, seed, sigs


def _sidecar_sweep_dirs() -> tuple[str, ...]:
    """Every mirror directory the per-test restore has to re-list.

    Derived from the DECLARED set (the seeded directories, the parent of every
    redirected path, and every redirected directory), never from the seed
    manifest. A manifest-derived sweep only ever visits directories that
    happened to hold a file at session start, so a watched directory that is
    empty in the checkout would never be swept and a file a test created there
    would survive for the rest of the session: exactly the cross-test channel
    this mirror exists to prevent."""
    dirs = set(_SIDECAR_SEED_DIRS)
    for _mod, _attr, rel in _SIDECAR_WRITE_TARGETS:
        if "/" in rel:
            dirs.add(rel.rsplit("/", 1)[0])
    for _mod, _attr, rel in _SIDECAR_WRITE_DIRS:
        dirs.add(rel)
    return tuple(sorted(d for d in dirs if d))


def _sidecar_restore_mirror(work: Path, seed: Path, sigs: dict) -> None:
    """Put the mirror back to its seeded bytes: re-copy what a test changed,
    drop what it created, restore what it deleted.

    Runs at the teardown of EVERY test, so it reads the mirror by directory
    tree rather than walking every file individually."""
    import shutil
    have = {}
    for d in _sidecar_sweep_dirs():
        have.update(_sidecar_dir_sigs(work, d))
    for rel, sig in have.items():
        if rel not in sigs:
            (work / rel).unlink(missing_ok=True)
        elif sig != sigs[rel]:
            shutil.copy2(seed / rel, work / rel)
    for rel in sigs:
        if rel not in have:
            (work / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(seed / rel, work / rel)


def _sidecar_public_path(work: Path, real):
    """betting_export._public_path, told where the test mirror is.

    _public_path publishes a path RELATIVE TO THE CHECKOUT ROOT and returns
    anything outside that root verbatim, because on the build box a verbatim
    path is absolute and would carry the OS username onto a public artifact.
    Redirect a write target into a tmp mirror and the published field becomes
    that absolute tmp path, which fails
    test_betting_publish_hygiene.py on the AppData pattern: those two hygiene
    tests passed under the function-scoped cut only because the redirect never
    reached the module-scoped fixture that builds the payload, so widening the
    redirect without this shim would have turned a real assertion red for a
    reason that has nothing to do with what it asserts.

    So the mirror gets the treatment the checkout gets, and only the mirror: a
    path under `work` publishes the relative form it would have had in the
    checkout, and every other path goes to the real function unchanged,
    including the tmp paths test_betting.py pins the verbatim echo on. Nothing
    in the production module moves. This is the harness telling the formatter
    where its own root went."""
    def _shim(p):
        try:
            return Path(p).resolve().relative_to(work.resolve()).as_posix()
        except (ValueError, OSError):
            return real(p)
    return _shim


@pytest.fixture(scope="session", autouse=True)
def _isolate_betting_sidecar_writes(_betting_sidecar_mirror):
    """No test writes a betting or DFS sidecar inside the checkout.

    SESSION SCOPED AND AUTOUSE, so the redirect is in place before the first
    fixture of any scope is set up. An autouse session fixture is ordered ahead
    of the module-, class- and session-scoped fixtures a test requests, and
    that ordering is the only one under which a module-scoped `be.build()`
    writes the mirror rather than the checkout. pytest.MonkeyPatch() rather
    than the `monkeypatch` fixture, because that one is function scoped by
    construction and was the whole defect in the first cut.

    Autouse for EVERY test file, not only the betting modules, because the
    leaks that reached the working tree came from tests whose names say nothing
    about betting (a props pull; a status write at the end of an ingest run)."""
    work, _seed, _sigs = _betting_sidecar_mirror
    mp = pytest.MonkeyPatch()
    try:
        for mod_name, attr, rel in _SIDECAR_WRITE_TARGETS + _SIDECAR_WRITE_DIRS:
            mod = _sidecar_module(mod_name)
            if mod is not None and hasattr(mod, attr):
                mp.setattr(mod, attr, work / rel)
        for mod_name in _SIDECAR_PUBLIC_PATH_MODULES:
            mod = _sidecar_module(mod_name)
            if mod is not None and hasattr(mod, "_public_path"):
                mp.setattr(mod, "_public_path",
                           _sidecar_public_path(work, mod._public_path))
        yield work
    finally:
        mp.undo()


@pytest.fixture(autouse=True)
def _reset_betting_sidecar_mirror(_isolate_betting_sidecar_writes,
                                  _betting_sidecar_mirror):
    """Put the mirror back between tests, so one test's write is never the next
    test's input. Depends on the session redirect so the ordering is declared
    rather than assumed."""
    yield
    _sidecar_restore_mirror(*_betting_sidecar_mirror)
