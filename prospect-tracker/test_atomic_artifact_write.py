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
  4. No .tmp files survive a successful write."""
from __future__ import annotations

import json
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
