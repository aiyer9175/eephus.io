# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A failed war_daily download must not blank a board.

THE OUTAGE THIS CLOSES AT THE SOURCE (2026-08-04, root-caused 2026-08-06).
test_fa_ident_half_index.py holds the symptom: a failed PITCHING frame returned
a batting-only identity index that every downstream check passed, and 79 of 228
free agents went blank with nothing logged. That test makes the damage
announce itself. This one stops it happening.

The asymmetry is structural, not luck. `pybaseball.bwar_bat` resolves into
pybaseball/cache/cache.py, so it is disk-cached; `pybaseball.bwar_pitch`
resolves to its own module with no decorator, so it is a live download on every
process. The pitching side is the one exposed to the network every single time,
which is exactly why the pitching side is the one that failed.

WHAT THESE TESTS HOLD
  1. A successful read is cached to disk, so there is something to fall back to.
  2. A later failure serves that copy instead of raising.
  3. Falling back is RECORDED. Silent recovery would be a new silent failure
     inside the fix for one, and a caller must be able to refuse to publish a
     board built on a stale frame.
  4. With no cached copy the original exception still propagates. The cache is
     a safety net, not a mask for a permanent break.
  5. allow_stale=False opts out entirely.
  6. A live read CLEARS a previous stale record, so the flag tracks the current
     process rather than latching forever.
"""
from __future__ import annotations

import pytest

war_source = pytest.importorskip("war_source")
pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")


FRAME = pd.DataFrame({
    "mlb_ID": [111, 222, 333],
    "year_ID": [2024, 2024, 2025],
    "WAR": [3.1, -0.4, 1.8],
    "name_common": ["A Pitcher", "B Pitcher", "C Pitcher"],
})


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Point the last-good cache at a temp dir, and clear the stale record on
    both sides of the test so ordering cannot leak state."""
    monkeypatch.setattr(war_source, "_cache_dir", lambda: tmp_path)
    war_source._SERVED_STALE.clear()
    yield tmp_path
    war_source._SERVED_STALE.clear()


def _fake_pyb(monkeypatch, *, bat=None, pit=None):
    """Replace pybaseball's two entry points for the duration of a test."""
    import pybaseball as pyb

    def ok(df):
        return lambda *a, **k: df

    def boom(msg):
        def _f(*a, **k):
            raise RuntimeError(msg)
        return _f

    monkeypatch.setattr(pyb, "bwar_bat",
                        ok(bat) if bat is not None else boom("bat down"))
    monkeypatch.setattr(pyb, "bwar_pitch",
                        ok(pit) if pit is not None else boom("pit down"))


def test_a_good_read_is_cached(isolated_cache, monkeypatch):
    _fake_pyb(monkeypatch, pit=FRAME)
    out = war_source.stint_frame("pit")
    assert len(out) == 3
    assert war_source._cache_path("pit").exists(), (
        "a successful read must leave a copy behind, or there is nothing to "
        "fall back to when the next one fails")
    assert war_source.served_stale() == {}


def test_a_failure_serves_the_cached_copy(isolated_cache, monkeypatch):
    """THE REGRESSION TEST. Warm the cache, then break the download."""
    _fake_pyb(monkeypatch, pit=FRAME)
    war_source.stint_frame("pit")

    _fake_pyb(monkeypatch)                      # both sides now raise
    out = war_source.stint_frame("pit")
    assert len(out) == 3, (
        "the pitching frame must come back from disk; returning nothing here "
        "is what blanked 79 free agents")
    assert list(out["mlb_ID"]) == [111, 222, 333]


def test_falling_back_is_recorded(isolated_cache, monkeypatch):
    """Recovering quietly would rebuild the original defect inside the fix."""
    _fake_pyb(monkeypatch, pit=FRAME)
    war_source.stint_frame("pit")
    _fake_pyb(monkeypatch)
    war_source.stint_frame("pit")

    stale = war_source.served_stale()
    assert "pit" in stale, (
        "a caller must be able to see that the board it is about to publish "
        "was built on a stale frame")
    assert stale["pit"]["rows"] == 3
    assert "pit down" in stale["pit"]["error"]
    assert "bat" not in stale, "only the failing side is stale"


def test_no_cache_means_the_error_still_propagates(isolated_cache, monkeypatch):
    """The net catches a network blip. It must not hide a real break, and on a
    fresh checkout there is nothing to serve anyway."""
    _fake_pyb(monkeypatch)
    with pytest.raises(RuntimeError, match="pit down"):
        war_source.stint_frame("pit")


def test_allow_stale_false_opts_out(isolated_cache, monkeypatch):
    _fake_pyb(monkeypatch, pit=FRAME)
    war_source.stint_frame("pit")
    _fake_pyb(monkeypatch)
    with pytest.raises(RuntimeError, match="pit down"):
        war_source.stint_frame("pit", allow_stale=False)


def test_a_live_read_clears_the_stale_flag(isolated_cache, monkeypatch):
    """Otherwise one blip would mark the process degraded for its whole life
    and the signal would stop meaning anything."""
    _fake_pyb(monkeypatch, pit=FRAME)
    war_source.stint_frame("pit")
    _fake_pyb(monkeypatch)
    war_source.stint_frame("pit")
    assert "pit" in war_source.served_stale()

    _fake_pyb(monkeypatch, pit=FRAME)
    war_source.stint_frame("pit")
    assert war_source.served_stale() == {}, (
        "the flag must describe the current read, not latch on the first "
        "failure the process ever saw")


def test_the_cached_frame_is_a_sibling_of_its_target(isolated_cache, monkeypatch):
    """No .tmp file survives a successful write, and the temp lands beside the
    target so os.replace stays a same-filesystem rename."""
    _fake_pyb(monkeypatch, pit=FRAME)
    war_source.stint_frame("pit")
    leftovers = [p.name for p in isolated_cache.iterdir() if ".tmp" in p.name]
    assert not leftovers, f"temp files survived: {leftovers}"


# --- the wiring: a stale frame has to reach the people who can act on it ----

def test_a_stale_frame_makes_the_fa_board_degraded(isolated_cache, monkeypatch):
    """Resolution RATES can look fine on a stale frame, because they are
    computed against whatever loaded. The staleness itself is the signal."""
    fa_export = pytest.importorskip("fa_export")
    war_source._SERVED_STALE["pit"] = {
        "age_days": 9.25, "rows": 12345,
        "error": "RuntimeError: simulated outage"}

    ident = {"hit": {"n": 100, "ok": 98}, "pit": {"n": 100, "ok": 97}}
    health = fa_export._identity_health(ident, 2027)

    assert health["degraded"] is True, (
        "a board built on a cached frame is degraded even when both sides "
        "resolve, or the guard only fires after the damage is visible")
    assert "stale_frames" in health and "pit" in health["stale_frames"]
    assert health["stale_frames"]["pit"]["age_days"] == 9.25
    why = health["degraded_why"]
    assert "cached frame was served" in why and "9.2" in why, (
        "the artifact must carry the cause and the age, so nobody has to read "
        "a run log that was not kept")


def test_the_identity_outage_row_can_reach_ingest_red():
    """The row was being filed and then filtered out, so the ledger knew about
    the outage and the operator did not."""
    run_monthly = pytest.importorskip("run_monthly")
    assert "fa_class_identity" in run_monthly.SCHEDULED_EXPORTS, (
        "fa_export._record_identity_outage files under this name; without it "
        "in SCHEDULED_EXPORTS the row is dropped from red[] and the deploy "
        "shell never prints INGEST RED for a blanked board")
