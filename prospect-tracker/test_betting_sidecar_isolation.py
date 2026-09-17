# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""No test may write a served betting or DFS artifact.

Repair 2 of docs/master-plan-2026-09-11-war-epoch-drivers-betting.md section
4.2, and the enforcement of its stop item X6 ("letting tests write betting
artifacts"). The machinery lives in conftest.py; this file holds it to its
contract.

WHY THIS EXISTS AS A TEST FILE AND NOT ONLY AS A FIXTURE. Two leaks were found
by hand on 2026-09-11, both through constants nobody had listed, and both had
been running for weeks: a props pull booked four phantom credits per run to the
SHARED tier ledger, and an ingest run ended in write_status() over the real
data/betting_status.json, so the served page said props were armed with a cap
of 6 and zero snapshots. Risk 13 of the plan is the same failure one step
later: a commit or a publish made from that tree ships the fixture's status.
A fixture that silently stops working reintroduces exactly that, so the
redirect is asserted from the outside, and the tripwire that catches an
unlisted writer is tested on its own.

THE PROPERTIES PINNED HERE:
  1. every default write target really is redirected out of the checkout while
     a test is running, AT EVERY FIXTURE SCOPE (test_every_default_write_...,
     test_the_redirect_is_already_in_place_at_module_fixture_setup);
  2. the redirect does not change what a test READS: the mirror is seeded with
     the checkout's own bytes, and a published path still reads as the
     checkout-relative one (test_the_mirror_serves_..., test_a_published_...);
  3. no betting or DFS module still resolves a WATCHED artifact by default,
     which is the part that fails when someone adds a new sidecar next month
     (test_no_module_still_resolves_...);
  4. the golden hash names the file, names the test, fails the run, and says
     so in the one shape the chunked runner can read (the _sidecar_changes
     tests and test_the_verdict_reaches_the_chunked_runner).

Property 4 is tested on the pure functions with synthetic snapshots. Writing a
real artifact to prove the detector works would be the very thing the detector
exists to forbid.

SCOPE IS THE POINT OF HALF THIS FILE. The first cut of the fixture was function
scoped, and pytest sets up module-, class- and session-scoped fixtures FIRST, so
every one of them ran against the real constants; the module-scoped fixture in
test_betting_publish_hygiene.py topped up the real results cache on every run.
Assertions written only inside a test body cannot see that hole, which is why
the scope tests below capture the constants from fixtures of each scope.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import conftest as ct

ROOT = Path(__file__).resolve().parent

#: The module families that own a path under data/ or .cache/ on the betting,
#: props, DFS or fantasy side, as GLOBS rather than a hand-kept list: a list is
#: exactly what let tools/betting_close_job.py, the module that writes the
#: close-job heartbeat and the attach result by default, sit outside the census
#: while three READ-ONLY copies of the same two paths were redirected.
_MODULE_GLOBS = (
    ("betting*.py", ""), ("dfs*.py", ""), ("fantasy*.py", ""),
    ("betting*.py", "tools"), ("dfs*.py", "tools"),
)


def _discovered_modules() -> list[str]:
    """Every module in those families, plus every module conftest already
    names. The second half matters as much as the first: it is what re-scans
    mgmt_teams, which holds a watched path and is in none of the families, and
    what catches a SECOND constant appearing in a module already listed.

    THE GAP, STATED. A brand new module in no family and on no list is not
    scanned here. A one-off census over every top-level module was run on
    2026-09-17 and found no other watched path; the golden hash is what covers
    the case between censuses, because it does not need to know who wrote."""
    names = set()
    for pat, sub in _MODULE_GLOBS:
        base = ROOT / sub if sub else ROOT
        for p in sorted(base.glob(pat)):
            if p.name.startswith("test_"):
                continue
            names.add(f"{sub}.{p.stem}" if sub else p.stem)
    for mod, _attr, _rel in ct._SIDECAR_WRITE_TARGETS + ct._SIDECAR_WRITE_DIRS:
        names.add(mod)
    return sorted(names)


def _module(name):
    try:
        return importlib.import_module(name)
    except Exception:                                     # noqa: BLE001
        return None


def _inside_checkout(p) -> bool:
    try:
        Path(p).resolve().relative_to(ROOT)
    except (ValueError, OSError):
        return False
    return True


def _redirect_state() -> dict[str, str]:
    """{module.attr: str(path)} for every redirected constant, as it stands at
    the moment of the call. Used from fixtures of three different scopes."""
    out = {}
    for mod_name, attr, _rel in (ct._SIDECAR_WRITE_TARGETS
                                 + ct._SIDECAR_WRITE_DIRS):
        mod = _module(mod_name)
        if mod is not None and hasattr(mod, attr):
            out[f"{mod_name}.{attr}"] = str(getattr(mod, attr))
    return out


# ---------------------------------------------------------------------------
# 1. the redirect is live, at every scope
# ---------------------------------------------------------------------------
def test_every_default_write_target_is_redirected_out_of_the_checkout():
    """The constants named in conftest resolve OUTSIDE the checkout for the
    whole of every test, so a no-argument generator call cannot land on the
    served file."""
    targets = ct._SIDECAR_WRITE_TARGETS + ct._SIDECAR_WRITE_DIRS
    assert targets, "the redirect list is empty; nothing is isolated"
    for mod_name, attr, rel in targets:
        mod = _module(mod_name)
        if mod is None:
            continue
        assert hasattr(mod, attr), (
            f"{mod_name}.{attr} no longer exists. It is in the sidecar "
            f"redirect list for {rel}: either the writer moved (point the list "
            "at its new home) or the artifact is gone (drop the row)")
        got = getattr(mod, attr)
        assert not _inside_checkout(got), (
            f"{mod_name}.{attr} still points inside the checkout at {got}. "
            "A test that calls its writer with no path overwrites the served "
            f"{rel} (plan repair 2, stop item X6)")


def test_no_listed_module_failed_to_import():
    """A module conftest could not import is a module whose constants were
    never redirected. That is the one state in which the guard is off, so it
    must not also be the one state nothing reports."""
    assert not ct._SIDECAR_IMPORT_FAILURES, (
        "conftest could not import these modules, so their write targets ran "
        f"unprotected for the whole session: {ct._SIDECAR_IMPORT_FAILURES}")


@pytest.fixture(scope="module")
def _constants_at_module_setup():
    """The redirected constants as a MODULE-scoped fixture sees them."""
    return _redirect_state()


@pytest.fixture(scope="session")
def _constants_at_session_setup():
    """The redirected constants as a SESSION-scoped fixture sees them."""
    return _redirect_state()


def test_the_redirect_is_already_in_place_at_module_fixture_setup(
        _constants_at_module_setup):
    """THE SCOPE TEST, and the reason the fixture is session scoped.

    pytest sets up higher-scoped fixtures before function-scoped ones, so a
    module-scoped fixture that calls a generator runs during the window this
    redirect has to already cover. test_betting_publish_hygiene.py builds its
    whole payload from exactly such a fixture.

    MUTATION: change conftest._isolate_betting_sidecar_writes back to
    `@pytest.fixture(autouse=True)` with the `monkeypatch` fixture. Every
    constant below is back inside the checkout at module-fixture setup and this
    test fails, while an assertion written in a test body would still pass."""
    assert _constants_at_module_setup, "no redirected constant was resolvable"
    inside = {k: v for k, v in _constants_at_module_setup.items()
              if _inside_checkout(v)}
    assert not inside, (
        "these constants were still inside the checkout when a MODULE-scoped "
        f"fixture ran, so anything such a fixture writes hits the served file: "
        f"{inside}")


def test_the_redirect_is_already_in_place_at_session_fixture_setup(
        _constants_at_session_setup):
    """Same property one scope up. A session-scoped fixture that builds a board
    once for a whole file is the cheapest way to write a served artifact 900
    tests before anyone reads the report."""
    inside = {k: v for k, v in _constants_at_session_setup.items()
              if _inside_checkout(v)}
    assert not inside, (
        "these constants were still inside the checkout when a SESSION-scoped "
        f"fixture ran: {inside}")


def test_the_redirect_list_and_the_watch_list_agree():
    """Every redirected path is either a watched artifact or the directory that
    holds one. A redirect nobody watches would hide its own failure."""
    for _mod, _attr, rel in ct._SIDECAR_WRITE_TARGETS:
        assert ct._sidecar_is_watched(rel), (
            f"{rel} is redirected but not covered by _SIDECAR_GLOBS, so if the "
            "redirect ever fails the golden hash will not notice")
    for _mod, _attr, rel in ct._SIDECAR_WRITE_DIRS:
        assert any(pat.startswith(rel + "/") for pat in ct._SIDECAR_GLOBS), (
            f"the redirected directory {rel} has no watched glob beneath it")


def test_the_watch_reaches_inside_a_nested_directory():
    """The slot lock the next repair in this plan section adds lands at
    .cache/betting/published_slots/<slate>.json, a first-write-wins vintage
    record. A flat `.cache/betting/*` glob stops at the directory and would
    leave it unwatched, so the recursion is pinned rather than assumed."""
    assert ct._sidecar_is_watched(".cache/betting/published_slots/2026-09-17.json")
    assert ct._sidecar_is_watched(".cache/betting/shadow.json")
    assert ct._sidecar_is_watched("data/betting_record.json")
    assert not ct._sidecar_is_watched("data/timeseries.json")
    assert not ct._sidecar_is_watched("data/betting/nested.json"), (
        "a data/ glob must not claim a nested path it cannot see")


def test_the_odds_snapshots_are_watched_even_though_they_are_not_redirected():
    """`.cache/odds` is deliberately NOT redirected: two tests replay a real
    snapshot through the live pipeline, and pointing the directory elsewhere
    would turn them into skips. That exemption is only safe because the
    snapshots are watched, so state it here rather than leaving it to a
    comment."""
    bi = _module("betting_ingest")
    assert bi is not None
    assert _inside_checkout(bi.CACHE_DIR), (
        "betting_ingest.CACHE_DIR has been redirected; test_betting_event_match "
        "and test_betting_line_consistency replay a real snapshot from it")
    assert ct._sidecar_is_watched(".cache/odds/2026-09-01-1300.json")


# ---------------------------------------------------------------------------
# 2. the redirect does not change what a test reads, or what it publishes
# ---------------------------------------------------------------------------
def test_the_mirror_serves_the_same_bytes_the_checkout_holds():
    """Isolation that changed the CONTENT would be a worse bug than the one it
    fixes: betting_model.CONTEXT_PATH is the served context every pricing test
    reads, and GAME_CACHE holds the completed-game results an offline build
    reads back. The mirror is seeded from the real files, so every redirected
    artifact that exists in the checkout is byte-identical through it."""
    checked = 0
    for mod_name, attr, rel in ct._SIDECAR_WRITE_TARGETS:
        real = ROOT / rel
        if not real.is_file():
            continue
        mod = _module(mod_name)
        if mod is None:
            continue
        seen = Path(getattr(mod, attr))
        assert seen.is_file(), (
            f"{mod_name}.{attr} points at {seen}, which does not exist, while "
            f"the checkout holds {rel}. A reader would see an absent file "
            "where production sees a populated one")
        assert seen.read_bytes() == real.read_bytes(), (
            f"the mirrored {rel} does not match the checkout's bytes; tests "
            "are now reading something the served build never reads")
        checked += 1
    assert checked, "no redirected artifact existed to compare; the seed is unproven"


def test_a_published_path_still_reads_as_the_checkout_relative_one():
    """The redirect must not change the PAYLOAD. betting_export._public_path
    publishes a path relative to the checkout root and echoes anything outside
    it verbatim, which is how the build box's OS username reached data/
    betting.json until 2026-08-16. Point a write target at a tmp mirror without
    telling the formatter and the published field becomes an absolute tmp path,
    so test_betting_publish_hygiene goes red for a reason that has nothing to
    do with what it asserts.

    MUTATION: drop _SIDECAR_PUBLIC_PATH_MODULES from the session fixture. The
    first assertion below returns an absolute AppData path and fails here, one
    file earlier than the hygiene test it would otherwise break."""
    be = _module("betting_export")
    assert be is not None
    assert be._public_path(be.RECORD_PATH) == "data/betting_record.json"
    assert be._public_path(be.RECORD_JSONL) == ".cache/betting/record.jsonl"
    assert be._public_path(be.OUT_PATH) == "data/betting.json"
    assert be._public_path(ROOT / "data" / "dfs.json") == "data/dfs.json", (
        "a real checkout path must still go through the real formatter")
    outside = Path.home() / "not-in-the-mirror" / "x.json"
    assert be._public_path(outside) == str(outside), (
        "a path outside both the checkout and the mirror is echoed verbatim; "
        "test_betting.py pins that behaviour")


def test_a_write_through_the_redirected_constant_never_reaches_the_checkout():
    """The end-to-end shape of the leak, run for real: write through the
    module's own constant, the way a generator called with no path does, and
    the served file is untouched."""
    be = _module("betting_export")
    real = ROOT / "data" / "betting.json"
    if be is None or not real.is_file():
        pytest.skip("betting_export or data/betting.json is absent")
    was = real.read_bytes()
    Path(be.OUT_PATH).write_text('{"poisoned": true}', encoding="utf-8")
    assert real.read_bytes() == was, (
        "a write through betting_export.OUT_PATH reached the served board")


def test_the_mirror_is_put_back_after_a_test_dirties_it(tmp_path):
    """The mirror must not become a cross-test channel of its own, which is the
    failure mode of every "just point it at a shared tmp dir" isolation. All
    three shapes: a file changed, a file created, a file deleted."""
    work, seed = tmp_path / "work", tmp_path / "seed"
    (work / "data").mkdir(parents=True)
    (seed / "data").mkdir(parents=True)
    for tree in (work, seed):
        (tree / "data" / "betting.json").write_text("served", encoding="utf-8")
        (tree / "data" / "dfs.json").write_text("board", encoding="utf-8")
    sigs = {p.relative_to(seed).as_posix(): ct._sidecar_sig(p)
            for p in seed.rglob("*") if p.is_file()}

    (work / "data" / "betting.json").write_text("poisoned board",
                                                encoding="utf-8")
    (work / "data" / "dfs.json").unlink()
    (work / "data" / "betting_record.json").write_text("junk", encoding="utf-8")

    ct._sidecar_restore_mirror(work, seed, sigs)

    assert (work / "data" / "betting.json").read_text(encoding="utf-8") == "served"
    assert (work / "data" / "dfs.json").read_text(encoding="utf-8") == "board"
    assert not (work / "data" / "betting_record.json").exists()


def test_the_sweep_reaches_a_directory_that_was_empty_when_it_was_seeded(tmp_path):
    """A sweep derived from the SEED MANIFEST only ever visits directories that
    happened to hold a file at session start. A watched directory that is empty
    in the checkout would then never be swept, and a file a test created there
    would survive as an input to every later test: the cross-test channel this
    mirror exists to prevent.

    MUTATION: rebuild _sidecar_sweep_dirs from `sigs` instead of the declared
    lists. The lock below survives the restore and this test fails."""
    work, seed = tmp_path / "work", tmp_path / "seed"
    for tree in (work, seed):
        (tree / ".cache" / "betting" / "published_slots").mkdir(parents=True)
        (tree / "data").mkdir(parents=True)
    sigs = {}
    (work / ".cache" / "betting" / "published_slots" / "2026-09-17.json"
     ).write_text("a slot lock a test wrote", encoding="utf-8")
    (work / ".cache" / "betting" / "record.jsonl").write_text("x", encoding="utf-8")

    ct._sidecar_restore_mirror(work, seed, sigs)

    assert not (work / ".cache" / "betting" / "record.jsonl").exists()
    assert not (work / ".cache" / "betting" / "published_slots"
                / "2026-09-17.json").exists(), (
        "a file created in a nested, initially empty mirror directory outlived "
        "the test that created it")


def test_the_sweep_set_is_declared_not_discovered():
    """Stated directly, because the property above is only visible in a
    fixture-shaped test: the directories swept come from the redirect lists,
    so adding a write target adds its directory to the sweep automatically."""
    dirs = set(ct._sidecar_sweep_dirs())
    assert ".cache/betting" in dirs and "data" in dirs
    assert ".cache/dfs_history" in dirs
    assert ".cache" in dirs, (
        "the two-start ledger sits directly in .cache and its parent must be "
        "swept")


# ---------------------------------------------------------------------------
# 3. nothing unlisted still writes a watched artifact
# ---------------------------------------------------------------------------
def test_no_module_still_resolves_a_watched_artifact_by_default():
    """THE FUTURE-PROOFING TEST. Every module-level Path in the betting, props,
    DFS and fantasy families, plus every module conftest already names, is
    resolved as the test run sees it. Any one still landing on a WATCHED
    artifact inside the checkout is an unlisted default writer, and this fails
    until it is listed.

    This is the test that would have caught both 2026-09-11 leaks the day they
    were written, and it is discovered by glob rather than hand-listed because
    a hand-list is what hid tools/betting_close_job.py."""
    offenders = []
    for mod_name in _discovered_modules():
        mod = _module(mod_name)
        if mod is None:
            continue
        for attr, val in sorted(vars(mod).items()):
            if attr.startswith("__") or not isinstance(val, Path):
                continue
            if not _inside_checkout(val):
                continue
            rel = val.resolve().relative_to(ROOT).as_posix()
            if ct._sidecar_is_watched(rel):
                offenders.append(f"{mod_name}.{attr} -> {rel}")
    assert not offenders, (
        "these module constants still resolve to a watched betting artifact "
        "during a test run, so a no-argument writer would overwrite the served "
        "file: " + "; ".join(offenders) + ". Add each to "
        "conftest._SIDECAR_WRITE_TARGETS, or to _SIDECAR_WRITE_DIRS when it is "
        "a directory")


def test_the_census_actually_covers_the_modules_that_write():
    """The discovery above has to reach the writers the first cut missed. If a
    future rename moves one out of the families AND off the redirect list, this
    names it instead of the census quietly shrinking."""
    found = set(_discovered_modules())
    for name in ("betting_export", "betting_model", "dfs_export",
                 "fantasy_export", "tools.betting_close_job",
                 "tools.betting_market_blend_lab", "tools.betting_calibration",
                 "mgmt_teams"):
        assert name in found, f"{name} dropped out of the sidecar census"


# ---------------------------------------------------------------------------
# 4. the golden hash itself
# ---------------------------------------------------------------------------
def test_the_snapshot_reads_the_watched_set_and_nothing_else(tmp_path):
    """_sidecar_snapshot picks up exactly the artifacts the globs name, in a
    tree of its own, and a changed byte changes its hash."""
    (tmp_path / "data").mkdir()
    (tmp_path / ".cache" / "betting" / "published_slots").mkdir(parents=True)
    (tmp_path / ".cache" / "odds").mkdir(parents=True)
    (tmp_path / "data" / "betting.json").write_text("a", encoding="utf-8")
    (tmp_path / "data" / "betting_status.json").write_text("b", encoding="utf-8")
    (tmp_path / "data" / "dfs.json").write_text("c", encoding="utf-8")
    (tmp_path / ".cache" / "betting" / "shadow.json").write_text("d", encoding="utf-8")
    (tmp_path / ".cache" / "betting" / "published_slots" / "2026-09-17.json"
     ).write_text("lock", encoding="utf-8")
    (tmp_path / ".cache" / "odds" / "2026-09-01-1300.json").write_text("e", encoding="utf-8")
    (tmp_path / "data" / "timeseries.json").write_text("not watched", encoding="utf-8")

    snap = ct._sidecar_snapshot(tmp_path)
    assert set(snap) == {
        "data/betting.json", "data/betting_status.json", "data/dfs.json",
        ".cache/betting/shadow.json",
        ".cache/betting/published_slots/2026-09-17.json",
        ".cache/odds/2026-09-01-1300.json",
    }, "the watched set drifted from the artifacts the plan names"
    assert "data/timeseries.json" not in snap

    before = dict(snap)
    (tmp_path / "data" / "betting.json").write_text("A", encoding="utf-8")
    after = ct._sidecar_snapshot(tmp_path)
    assert after["data/betting.json"] != before["data/betting.json"]


def test_a_changed_artifact_is_named_and_so_is_the_test_that_changed_it():
    """The report names the file and the test. "Some test in a 900-test run
    rewrote a sidecar" is not a finding anyone can act on."""
    before = {"data/betting.json": "aaa", "data/dfs.json": "ccc"}
    after = {"data/betting.json": "bbb", "data/dfs.json": "ccc"}
    rows = ct._sidecar_changes(
        before, after, {"data/betting.json": ["test_betting.py::test_x"]})
    assert len(rows) == 1
    assert "data/betting.json" in rows[0]
    assert "changed" in rows[0]
    assert "test_betting.py::test_x" in rows[0]


def test_the_named_test_is_reported_as_a_suspect_not_a_culprit():
    """A cron or a regen writing the same store during a run is indistinguish-
    able from a test writing it, so the report says the file changed WHILE the
    test ran rather than that the test wrote it. The runbook already tells you
    not to run the suite alongside a regen; the wording must not contradict
    it."""
    row = ct._sidecar_changes({"data/dfs.json": "a"}, {"data/dfs.json": "b"},
                              {"data/dfs.json": ["test_x.py::test_y"]})[0]
    assert "while running" in row
    assert "rewritten by" not in row and "written by" not in row


def test_an_unattributed_change_says_so_rather_than_blaming_a_test():
    """Nothing the per-test watch saw means nothing to name, and the report
    must not reach for the last test that happened to run."""
    row = ct._sidecar_changes({"data/dfs.json": "a"}, {"data/dfs.json": "b"})[0]
    assert "no test the watch could see" in row


def test_a_created_or_deleted_artifact_is_reported_as_such():
    """A snapshot a test WRITES and a ledger a test DELETES are both leaks, and
    neither is a byte difference in a file present at both ends."""
    rows = ct._sidecar_changes(
        {".cache/betting/record.jsonl": "aaa"},
        {".cache/betting/record.jsonl": None,
         ".cache/odds/2026-09-01-1300.json": "new"},
        {".cache/odds/2026-09-01-1300.json": ["test_x.py::test_pull"]})
    joined = " | ".join(rows)
    assert "record.jsonl: disappeared" in joined
    assert "2026-09-01-1300.json: appeared while running test_x.py::test_pull" in joined


def test_a_write_the_build_artifact_guard_put_back_is_still_reported():
    """THE ONE THAT MATTERS MOST. _restore_committed_build_artifacts finalizes
    BEFORE the session-end sweep, so a tracked sidecar a test overwrote is
    already back to its committed bytes when the sweep runs, and the start and
    end hashes agree. The per-test watch sees the write while it is still on
    disk, and that mid-run reading is what keeps the leak visible."""
    rows = ct._sidecar_changes(
        {"data/betting_status.json": "committed"},
        {"data/betting_status.json": "committed"},
        {"data/betting_status.json": ["test_betting_props.py::test_pull"]},
        {"data/betting_status.json": "fixture_state"})
    assert len(rows) == 1
    assert "data/betting_status.json" in rows[0]
    assert "test_betting_props.py::test_pull" in rows[0]
    assert "put back" in rows[0]


def test_an_identical_rewrite_is_not_reported():
    """A generator that writes the same bytes back moves the mtime and is not a
    leak. The verdict is the hash, never the timestamp, so this stays quiet."""
    assert ct._sidecar_changes({"data/dfs.json": "aaa"}, {"data/dfs.json": "aaa"},
                               {"data/dfs.json": ["test_x.py::test_y"]},
                               {"data/dfs.json": "aaa"}) == []


def test_the_run_fails_on_a_changed_artifact_even_when_every_test_passed(monkeypatch):
    """A green suite that rewrote data/betting.json is not green: the next
    build publishes whatever the test left behind. pytest returns
    session.exitstatus after pytest_sessionfinish, so raising it there is what
    makes the tripwire binding rather than advisory."""
    class _S:
        exitstatus = 0

    monkeypatch.setattr(ct, "_SIDECAR_REPORT", ["data/betting.json: changed"])
    s = _S()
    ct.pytest_sessionfinish(s, 0)
    assert s.exitstatus == 1, (
        "a changed betting artifact must fail the run on its own")

    monkeypatch.setattr(ct, "_SIDECAR_REPORT", [])
    clean = _S()
    ct.pytest_sessionfinish(clean, 0)
    assert clean.exitstatus == 0

    monkeypatch.setattr(ct, "_SIDECAR_REPORT", ["data/dfs.json: changed"])
    failed = _S()
    failed.exitstatus = 2
    ct.pytest_sessionfinish(failed, 2)
    assert failed.exitstatus == 2, "a real failure code must not be overwritten"


def test_an_unimportable_module_is_part_of_the_verdict(monkeypatch):
    """The redirect being OFF is worse than an artifact having moved, so an
    import failure fails the run too, and the row names the artifact that ran
    unprotected.

    MUTATION: go back to swallowing the ImportError in _sidecar_module. The
    session ends green with the redirect off."""
    monkeypatch.setattr(ct, "_SIDECAR_REPORT", None)
    monkeypatch.setattr(ct, "_SIDECAR_IMPORT_FAILURES",
                        {"betting_export": "ImportError: no pandas"})
    monkeypatch.setattr(ct, "_sidecar_snapshot", lambda root: dict(ct._SIDECAR_GOLDEN))
    rows = ct._sidecar_final_report()
    assert any("betting_export" in r and "could not be imported" in r
               for r in rows), rows
    assert any("data/betting.json" in r for r in rows), (
        "the row must name what ran unprotected, not only the module")


def test_the_verdict_reaches_the_chunked_runner():
    """tools/run_suite.py is how this suite is run, and its verdict is built
    ONLY from stdout lines starting with FAILED or ERROR:

        return 0 if (n_crash == 0 and not unexpected) else 1

    A sidecar-only violation is exactly a chunk that exits 1 with no such line,
    so without these rows the runner prints "No unexpected failures" and exits
    0 over a run that rewrote a served artifact.

    MUTATION: drop the _sidecar_runner_rows loop from pytest_terminal_summary.
    A bare pytest still exits 1 and the runner still exits 0, which is the
    state this test exists to forbid."""
    rows = ct._sidecar_runner_rows(
        ["data/betting.json: changed while running test_a.py::test_b"])
    assert len(rows) == 1
    assert rows[0].startswith("ERROR "), (
        "run_suite collects a failure only from a line starting FAILED or ERROR")
    assert "data/betting.json" in rows[0]
    assert "test_a.py:test_b" in rows[0]

    run_suite = _module("tools.run_suite")
    if run_suite is None:
        pytest.skip("tools/run_suite.py is absent")
    known = run_suite.KNOWN_BASELINE_REDS
    assert known, "the runner no longer keeps a baseline list"
    for name in known:
        row = ct._sidecar_runner_rows(
            [f"data/betting.json: changed while running {name}"])[0]
        assert not any(k in row for k in known), (
            "a leak blamed on a known baseline red would be absorbed into the "
            f"baseline and vanish from the runner's verdict: {row}")


def test_the_golden_hashes_were_actually_taken():
    """The session-start hash runs in pytest_sessionstart. If the hook were
    renamed or dropped, every report above would compare nothing to nothing and
    pass forever."""
    if not any((ROOT / rel).exists()
               for rel in ("data/betting.json", "data/dfs.json")):
        pytest.skip("no betting artifact is built in this tree")
    assert ct._SIDECAR_GOLDEN, (
        "no golden hash was taken at session start; the tripwire is inert")
    assert all(isinstance(v, str) or v is None
               for v in ct._SIDECAR_GOLDEN.values())
