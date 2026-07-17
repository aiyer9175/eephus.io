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

import functools
import json
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
    as dirty-at-start and left untouched - so this only reverts churn the TESTS
    introduced. No-ops cleanly when git is unavailable. `--relative` restricts
    the scope to this project subtree."""
    import subprocess
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

    dirty_at_start = _dirty()
    yield
    polluted = sorted(p for p in (_dirty() - dirty_at_start)
                      if not p.startswith("..") and "/.." not in p)
    if polluted:
        subprocess.run(["git", "checkout", "--", *polluted],
                       cwd=here, check=False)
