# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Ingest observability (2026-07-31).

THE OUTAGE THIS EXISTS FOR: TJStats wrote ZERO rows from 2026-07-08 to
2026-07-21 while seven full monthly runs completed and reported success.
Nothing recorded it. Three independent gaps produced that silence:

  1. run_tjstats_pipeline never raises (correct) and its returned status was
     DISCARDED by both callers, so a skipped ingest looked like a done one;
  2. logs/pipeline_latest.log was last written in May - all pipeline logging
     goes to stdout and nothing captured stdout;
  3. the end-of-run summary reports STEP DURATIONS only, and a step that
     fetched nothing still shows a healthy-looking duration.

data/ingest_health.json plus a RED summary line closes (1) and (3);
deploy/nightly-build.sh's tee closes (2).

The DURABLE half rides storage.record_source_check / load_source_checks -
the table the FA module already added - rather than a second mechanism.

Offline: isolated per-test DB + tmp out_dir. No network."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import run_monthly
import storage
import tjstats


class ScheduledSources(unittest.TestCase):
    def test_tjstats_is_watched(self):
        """The source whose 8-day outage nobody saw."""
        self.assertIn("tjstats", run_monthly.SCHEDULED_GRADE_SOURCES)

    def test_pipeline_captures_are_watched(self):
        self.assertIn("mlb_pipeline_live", run_monthly.SCHEDULED_GRADE_SOURCES)
        self.assertIn("mlb_pipeline_org", run_monthly.SCHEDULED_GRADE_SOURCES)


class TJStatsStatusIsLegible(unittest.TestCase):
    def test_pipeline_returns_an_explicit_ok_flag(self):
        """A caller must not be able to mistake 'returned a dict' for
        'ingested a board'. The health-check path returns early."""
        real = tjstats.health_check
        tjstats.health_check = lambda: ["rankings: only 3 entries"]
        try:
            out = tjstats.run_tjstats_pipeline(live=True, history=False)
        finally:
            tjstats.health_check = real
        self.assertIn("ok", out)
        self.assertFalse(out["ok"])
        self.assertEqual(out["n_rows"], 0)
        self.assertTrue(out["health"])

    def test_a_crash_is_reported_not_raised(self):
        real = tjstats.health_check

        def boom():
            raise RuntimeError("endpoint moved")

        tjstats.health_check = boom
        try:
            out = tjstats.run_tjstats_pipeline(live=True, history=False)
        finally:
            tjstats.health_check = real
        self.assertFalse(out["ok"])
        self.assertIn("endpoint moved", out["error"])


# ---------------------------------------------------------------------------
# Ledger behaviour. pytest style so each test gets its own DB + out_dir.
# ---------------------------------------------------------------------------

def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    storage.init_db()
    run_monthly._INGEST_HEALTH.clear()
    return tmp_path


def _load(tmp_path):
    return json.loads((tmp_path / "ingest_health.json").read_text(encoding="utf-8"))


def test_healthy_run_has_no_red(tmp_path, monkeypatch):
    out = _fresh(tmp_path, monkeypatch)
    for src in run_monthly.SCHEDULED_GRADE_SOURCES:
        run_monthly._record_ingest(src, True, 100)
    run_monthly.write_ingest_health(out, "daily")
    assert _load(out)["red"] == []


def test_zero_rows_from_a_scheduled_source_is_red(tmp_path, monkeypatch):
    """The exact TJStats case: the step ran, did not raise, wrote nothing."""
    out = _fresh(tmp_path, monkeypatch)
    run_monthly._record_ingest("tjstats", False, 0, "health check failed")
    run_monthly._record_ingest("mlb_pipeline_live", True, 100)
    run_monthly._record_ingest("mlb_pipeline_org", True, 800)
    run_monthly.write_ingest_health(out, "daily")
    assert _load(out)["red"] == ["tjstats"]


def test_a_step_that_never_ran_is_also_red(tmp_path, monkeypatch):
    """Absence must not read as success. If a scheduled source recorded
    nothing at all, its step crashed before reporting or was never wired."""
    out = _fresh(tmp_path, monkeypatch)
    run_monthly._record_ingest("mlb_pipeline_live", True, 100)
    run_monthly.write_ingest_health(out, "daily")
    doc = _load(out)
    assert "tjstats" in doc["red"]
    row = next(r for r in doc["sources"] if r["source"] == "tjstats")
    assert "no ingest attempt recorded" in row["message"]


def test_a_non_scheduled_source_is_reported_but_not_red(tmp_path, monkeypatch):
    """Just Baseball legitimately publishes nothing for months; a quiet
    rolling board must not be alarmed on."""
    out = _fresh(tmp_path, monkeypatch)
    for src in run_monthly.SCHEDULED_GRADE_SOURCES:
        run_monthly._record_ingest(src, True, 100)
    run_monthly._record_ingest("just_baseball", True, 0, "unchanged")
    run_monthly.write_ingest_health(out, "daily")
    doc = _load(out)
    assert doc["red"] == []
    assert any(r["source"] == "just_baseball" for r in doc["sources"])


def test_success_stamps_the_durable_ledger(tmp_path, monkeypatch):
    out = _fresh(tmp_path, monkeypatch)
    run_monthly._record_ingest("tjstats", True, 100, scope="daily-am")
    checks = storage.load_source_checks()
    assert ("tjstats", "daily-am") in checks
    assert checks[("tjstats", "daily-am")]["n_rows"] == 100
    run_monthly.write_ingest_health(out, "daily")
    row = next(r for r in _load(out)["sources"] if r["source"] == "tjstats")
    assert row["last_ok_at"]


def test_failure_does_not_refresh_the_stamp(tmp_path, monkeypatch):
    """record_source_check's own contract: only a VERIFIED-GOOD check may
    move the stamp. A frozen stamp IS the outage signal - refreshing it on a
    failed run is precisely how an 8-day gap stays invisible."""
    out = _fresh(tmp_path, monkeypatch)
    run_monthly._record_ingest("tjstats", True, 100)
    before = storage.load_source_checks()[("tjstats", "")]["checked_at"]
    run_monthly._record_ingest("tjstats", False, 0, "endpoint down")
    after = storage.load_source_checks()[("tjstats", "")]
    assert after["checked_at"] == before
    assert after["n_rows"] == 100


def test_last_ok_survives_a_run_that_produced_nothing(tmp_path, monkeypatch):
    """The single number that would have made the outage obvious on day one:
    'last OK' stays visible even when this run wrote zero rows."""
    out = _fresh(tmp_path, monkeypatch)
    run_monthly._record_ingest("tjstats", True, 100)
    run_monthly._INGEST_HEALTH.clear()
    run_monthly._record_ingest("tjstats", False, 0, "health check failed")
    run_monthly.write_ingest_health(out, "daily")
    row = next(r for r in _load(out)["sources"] if r["source"] == "tjstats")
    assert row["ok"] is False
    assert row["last_ok_at"], "last-known-good stamp must survive the failure"
    assert row["last_ok_rows"] == 100


def test_payload_shape(tmp_path, monkeypatch):
    out = _fresh(tmp_path, monkeypatch)
    run_monthly._record_ingest("tjstats", True, 100, "", scope="daily-am")
    doc = run_monthly.write_ingest_health(out, "monthly")
    assert set(doc) == {"generated_at", "mode", "sources", "red"}
    assert doc["mode"] == "monthly"
    row = next(r for r in doc["sources"] if r["source"] == "tjstats")
    assert set(row) >= {"source", "scope", "ok", "n_rows", "message", "date",
                        "last_ok_at", "last_ok_rows"}


def test_write_never_raises_on_an_unwritable_dir(tmp_path, monkeypatch):
    """Observability must never be the thing that fails the run. The path
    below has a FILE as its parent, so mkdir cannot succeed."""
    _fresh(tmp_path, monkeypatch)
    for src in run_monthly.SCHEDULED_GRADE_SOURCES:
        run_monthly._record_ingest(src, True, 100)
    bad = tmp_path / "t.db" / "nope"
    doc = run_monthly.write_ingest_health(bad, "daily")
    assert doc["red"] == []                       # still computed in memory
    assert not (bad / "ingest_health.json").exists()


if __name__ == "__main__":
    unittest.main()
