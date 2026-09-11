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
    every file restored, so a new leak is visible instead of silent."""
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
    shutil.rmtree(aside, ignore_errors=True)


_RESTORED_BY_GUARD: list[str] = []


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Name every locally-modified file a test overwrote (and the guard put
    back). A non-empty list is a test-isolation bug, even though the guard
    repaired the tree."""
    if not _RESTORED_BY_GUARD:
        return
    terminalreporter.write_sep("-", "build-artifact guard")
    terminalreporter.write_line(
        f"restored {len(_RESTORED_BY_GUARD)} locally-modified file(s) a test "
        "overwrote (a test-isolation bug to fix):")
    for rel in _RESTORED_BY_GUARD:
        terminalreporter.write_line(f"  {rel}")
