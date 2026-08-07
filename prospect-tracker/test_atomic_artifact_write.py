# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A reader must never see half an exported artifact.

THE CORRUPTION THIS PINS (2026-08-06). data/timeseries.json was found with a
JSON decode error 42.9MB into a 74MB file. The artifact has TWO writers and
nothing serialises them: storage.export_timeseries_json builds it, and
run_monthly._patch_export_run_summary reads it whole and RE-SERIALISES it to
stamp a run summary. Both wrote IN PLACE, so an interrupted or raced write left
a truncated file that was still structurally plausible enough to be served, and
nothing raised. It is gitignored, so there was no copy to restore from.

It also manufactured a phantom bug: five players appeared to be served on an org
MLB's feed contradicts, and that was chased as a fifth precedence layer in the
org resolver. It was not. The test was reading a truncated file.

WHAT THIS HOLDS
  1. The exported bytes are complete and parse, which an in-place write cannot
     promise if it is interrupted.
  2. A reader concurrent with a rewrite sees a COMPLETE document every time,
     old or new, never a partial one. This is the property os.replace buys and
     the one the corruption proved was missing.
  3. The temp file lands in the SAME directory as its target. That is not
     cosmetic: a temp in the system temp dir would make os.replace a
     cross-device copy, which is not atomic and would silently reintroduce the
     bug on any box where /tmp is a different filesystem.
  4. No .tmp files survive a successful write.
  5. HOW MANY WRITERS THERE ARE (added 2026-08-07). Atomicity made the race
     survivable, not absent. A monthly night stamped the run summary into the
     same 74MB file THREE times (main before the chain, the chained daily's d9
     rebuild, then the daily tail), each one superseded by the next. The last
     four tests hold the count down to one on the success path and hold the
     fallback stamp on the failure path, because dropping the redundant writes
     without the fallback would lose the site's "as of" block on a bad night."""
from __future__ import annotations

import ast
import inspect
import json
import logging
import threading

import pytest

storage = pytest.importorskip("storage")


def _dump_via_export(obj, path):
    """Drive the real shared writer rather than a copy of its logic."""
    data = storage._dump_bytes(obj) if hasattr(storage, "_dump_bytes") else json.dumps(obj).encode()
    tmp = path.with_name(path.name + ".tmpTEST")
    tmp.write_bytes(data)
    # Drive the REAL swap, retry included. Using os.replace directly here is
    # what made the first run of this test fail on Windows, which was the point:
    # the helper exists because the naive call raises when a reader has the
    # target open.
    storage._atomic_replace(tmp, path)


def test_dump_bytes_round_trips(tmp_path):
    """The serialiser itself is sound: whatever atomicity does, the bytes it
    moves have to be a complete document."""
    if not hasattr(storage, "_dump_bytes"):
        pytest.skip("storage._dump_bytes not exposed")
    obj = {"players": [{"player_key": f"p{i}", "org": "STL"} for i in range(5000)]}
    blob = storage._dump_bytes(obj)
    assert json.loads(blob)["players"][4999]["player_key"] == "p4999"


def test_a_concurrent_reader_never_sees_a_partial_document(tmp_path):
    """THE REGRESSION TEST. Rewrite a large file repeatedly while a reader
    hammers it. Every read must parse. With an in-place write this fails: the
    reader catches the file mid-write and gets exactly the truncated JSON that
    took down timeseries.json."""
    target = tmp_path / "artifact.json"
    small = {"players": [{"k": i} for i in range(200)]}
    big = {"players": [{"k": i, "pad": "x" * 200} for i in range(20000)]}
    _dump_via_export(small, target)

    failures: list[str] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                raw = target.read_bytes()
            except OSError:
                continue          # a rename can briefly race open() on Windows
            if not raw:
                continue
            try:
                json.loads(raw)
            except ValueError as e:
                failures.append(f"partial read of {len(raw)} bytes: {e}")
                return

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        for i in range(12):
            _dump_via_export(big if i % 2 else small, target)
    finally:
        stop.set()
        t.join(timeout=10)

    assert not failures, (
        "a reader saw a partial document, so the write is not atomic: "
        f"{failures[:2]}")


def test_the_temp_file_is_a_sibling_not_a_system_temp(tmp_path):
    """os.replace is atomic only within one filesystem. A temp in the system
    temp dir would degrade it to a cross-device copy on any box where /tmp is a
    separate mount, which is exactly where this bug would come back."""
    import inspect
    src = inspect.getsource(storage.export_timeseries_json)
    assert "with_name(" in src, (
        "the atomic write must build its temp path from the TARGET's directory "
        "(path.with_name), not from tempfile/gettempdir")
    assert "tempfile" not in src and "gettempdir" not in src, (
        "a system-temp path would make the swap a cross-device COPY, which is "
        "not atomic, on any box where /tmp is a separate filesystem")
    # The swap itself lives in the shared helper, which is also where the
    # Windows open-file retry lives; assert on the helper rather than on the
    # caller so moving the swap into one place does not read as a regression.
    assert "os.replace(" in inspect.getsource(storage._atomic_replace), (
        "the swap must be os.replace, not a copy or an in-place write")


def test_no_temp_files_are_left_behind(tmp_path):
    target = tmp_path / "artifact.json"
    _dump_via_export({"players": []}, target)
    leftovers = [p.name for p in tmp_path.iterdir() if ".tmp" in p.name]
    assert not leftovers, f"temp files survived a successful write: {leftovers}"


def test_the_swap_gives_up_loudly_rather_than_writing_in_place(tmp_path, monkeypatch):
    """The deadline exists so a stuck reader cannot hang an export forever. What
    happens when it expires is the part that matters: the helper must RAISE and
    leave the previous file untouched. Falling back to an in-place write here
    would rebuild the exact corruption this module exists to prevent, under
    precisely the conditions that cause it."""
    import os as _os
    target = tmp_path / "artifact.json"
    _dump_via_export({"players": [{"k": 1}]}, target)
    before = target.read_bytes()

    def always_busy(a, b):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(storage.os, "replace", always_busy)
    tmp = target.with_name(target.name + ".tmpBUSY")
    tmp.write_bytes(b'{"players": []}')

    with pytest.raises(PermissionError, match="was NOT"):
        storage._atomic_replace(tmp, target, timeout=0.3)

    assert target.read_bytes() == before, (
        "the previous artifact must survive a failed swap; overwriting it here "
        "is the corruption, not the fix")
    assert _os.path.exists(tmp), "the temp is left for inspection, not silently lost"


def test_a_brief_collision_is_ridden_out(tmp_path, monkeypatch):
    """The common case: a reader holds the file for a moment and lets go. The
    swap must succeed rather than surfacing a transient error to the export."""
    target = tmp_path / "artifact.json"
    _dump_via_export({"players": [{"k": 1}]}, target)
    real = storage.os.replace
    calls = {"n": 0}

    def busy_twice(a, b):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError(5, "Access is denied")
        return real(a, b)

    monkeypatch.setattr(storage.os, "replace", busy_twice)
    tmp = target.with_name(target.name + ".tmpBRIEF")
    tmp.write_bytes(b'{"players": [{"k": 2}]}')
    storage._atomic_replace(tmp, target, timeout=5.0)

    assert json.loads(target.read_bytes())["players"][0]["k"] == 2
    assert calls["n"] == 3, "it must retry, not give up on the first refusal"


# --------------------------------------------------------------------------- #
# ONE WRITER PER RUN. The stamp is the second writer to timeseries.json, so the
# question these tests settle is how many times a run performs it.
# --------------------------------------------------------------------------- #

run_monthly = pytest.importorskip("run_monthly")


def _stamp_calls(fn_node):
    """(success_path, failure_path) line numbers of _patch_export_run_summary
    calls in a function body, split by whether the call sits inside an
    except handler."""
    in_handler = set()
    for node in ast.walk(fn_node):
        if isinstance(node, ast.ExceptHandler):
            for sub in ast.walk(node):
                in_handler.add(id(sub))
    ok, failed = [], []
    for node in ast.walk(fn_node):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_patch_export_run_summary"):
            (failed if id(node) in in_handler else ok).append(node.lineno)
    return ok, failed


def _top_level_functions():
    tree = ast.parse(inspect.getsource(run_monthly))
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def test_a_monthly_success_path_stamps_the_run_summary_exactly_once():
    """THE GATE. Count the stamps a successful monthly night performs, by the
    structure of the code rather than by running a six-hour pipeline.

    main() chains run_daily unconditionally, and run_daily reaches the d9
    rebuild before its own finish_run, so all three of those sites used to
    stamp the same file for the same purpose. Only the last one survives on
    the success path: main() must not stamp before the chain, and d9 must
    defer to the caller."""
    fns = _top_level_functions()

    main_ok, main_fail = _stamp_calls(fns["main"])
    assert not main_ok and not main_fail, (
        "main() must not stamp the run summary itself: its stamp is always "
        f"superseded by the chained daily's, lines {main_ok + main_fail}")

    chain_ok, chain_fail = _stamp_calls(fns["_chain_daily_and_stamp"])
    assert not chain_ok, (
        "the chain helper may only stamp on the raise path; a stamp outside "
        f"the handler duplicates run_daily's, lines {chain_ok}")
    assert len(chain_fail) == 1

    daily_ok, daily_fail = _stamp_calls(fns["run_daily"])
    assert len(daily_ok) == 1, (
        "run_daily owns the one success-path stamp for both the daily and the "
        f"monthly cadence, found {daily_ok}")
    assert len(daily_fail) == 1, (
        "and it must carry the fallback stamp d9 no longer provides, so a "
        "crash after the rebuild still leaves a data_freshness block")

    # d9 is inside run_daily, so its stamp would count against the total above
    # unless the call site suppresses it.
    d9 = [n for n in ast.walk(fns["run_daily"])
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
          and n.func.id == "rebuild_only"]
    assert len(d9) == 1
    assert any(kw.arg == "stamp_summary" and kw.value.value is False
               for kw in d9[0].keywords), (
        "run_daily must call rebuild_only(stamp_summary=False): its own tail "
        "stamp supersedes d9's within the same run")

    rebuild_ok, _ = _stamp_calls(fns["rebuild_only"])
    assert len(rebuild_ok) == 1, "the standalone --rebuild-only path still stamps"

    monthly_success_stamps = (len(main_ok) + len(chain_ok) + len(daily_ok)
                              + 0)          # rebuild_only, suppressed at d9
    assert monthly_success_stamps == 1, (
        f"a monthly success path performs {monthly_success_stamps} stamps of a "
        "74MB artifact; the count of writers to this file is the thing that "
        "corrupted it")


def test_a_failed_chain_still_leaves_a_stamped_summary(tmp_path, monkeypatch):
    """The reason the redundant stamp was left in place for a year. If the
    chained daily dies before its own stamp, the served file is the step-5
    export: its run block was read before finish_run and it has no
    data_freshness block at all, so the site loses its "as of" line."""
    target = tmp_path / "timeseries.json"
    target.write_text(json.dumps({"players": [], "run": {"id": 1}}),
                      encoding="utf-8")
    monkeypatch.setattr(run_monthly, "latest_run_summary",
                        lambda: {"id": 7, "finished_at": "2026-08-07T05:00:00"})
    monkeypatch.setattr(storage, "data_freshness",
                        lambda: {"grades_updated_at": "2026-08-07T04:00:00",
                                 "transactions_updated_at": "2026-08-07T05:00:00",
                                 "last_run_kind": "daily"})

    def chain_that_dies():
        raise RuntimeError("d5e game logs blew up")

    outcome = run_monthly._chain_daily_and_stamp(
        target, logging.getLogger("test_chain"), chain_that_dies)

    assert outcome == "fallback"
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["run"]["id"] == 7, "the fallback must refresh the run block"
    assert payload["data_freshness"]["last_run_kind"] == "daily", (
        "and the freshness block, which only the stamp writes")


def test_a_successful_chain_is_not_stamped_twice(tmp_path, monkeypatch):
    """The chain's own stamp is newer than anything the helper could write, so
    the helper must stay out of the way when the chain returns."""
    target = tmp_path / "timeseries.json"
    target.write_text(json.dumps({"players": []}), encoding="utf-8")
    stamps: list[str] = []
    monkeypatch.setattr(run_monthly, "_patch_export_run_summary",
                        lambda path, log: stamps.append(str(path)))

    outcome = run_monthly._chain_daily_and_stamp(
        target, logging.getLogger("test_chain"),
        lambda: run_monthly._patch_export_run_summary(target, None))

    assert outcome == "chained"
    assert stamps == [str(target)], (
        f"the success path performed {len(stamps)} stamps, expected the "
        "chain's one")


def test_rebuild_only_can_defer_its_stamp_to_the_caller():
    """d9 runs inside run_daily, mid-run: its stamp reads a run row that has no
    finished_at yet and is replaced minutes later. The parameter is what lets
    the manual --rebuild-only path keep stamping while the chained one does
    not."""
    sig = inspect.signature(run_monthly.rebuild_only)
    assert "stamp_summary" in sig.parameters
    assert sig.parameters["stamp_summary"].default is True, (
        "standalone callers must keep the stamp: export_timeseries_json does "
        "not write a data_freshness block, only the stamp does")
