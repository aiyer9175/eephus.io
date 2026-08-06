# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Half an identity index must announce itself.

THE OUTAGE THIS PINS (2026-08-04, diagnosed 2026-08-05). `war_daily_index` is
built from TWO Baseball-Reference frames and used to swallow a per-frame failure
with `except: continue`. A failed PITCHING frame therefore returned a
BATTING-ONLY index that is structurally perfect: right shape, right types, real
names, and every downstream check passes. Every hitter resolved; every
pitcher-only player silently did not. That blanked 79 of 228 free agents on the
2027 board (2028: 181 -> 111, 2029: 133 -> 83), and nothing anywhere raised or
logged an error. It was found only because the owner noticed the blank rows.

It is always the PITCHING side, and that is structural rather than luck:
pybaseball decorates `bwar_bat` with a disk cache and `bwar_pitch` with nothing,
so batting serves from a 7-day parquet cache while pitching is a live download
on every process that builds the index.

WHAT THESE TESTS HOLD
  1. A whole index reports no missing sides.
  2. A failed side is RECORDED, so a caller can refuse to publish off it. This
     is the assertion that would have caught the original outage on the day.
  3. The completeness record never leaks into the index's own key space - the
     index is consumed as {name: ...} and several callers iterate it, so a
     sentinel key would be a fresh silent defect inside the fix for one.
  4. A surviving side still resolves, i.e. the guard reports the damage without
     causing more: a degraded index is still the best available answer for the
     half that loaded, and the caller decides what to do about it."""
from __future__ import annotations

import pytest

fa_ident = pytest.importorskip("fa_ident")


@pytest.fixture
def clean_index():
    """Every test here mutates the lru_cache, so clear on the way in AND out."""
    fa_ident.war_daily_index.cache_clear()
    yield
    fa_ident.war_daily_index.cache_clear()


def _break_side(monkeypatch, side_to_break):
    """Make war_source.stint_frame raise for ONE side, exactly as a failed
    Baseball-Reference download does."""
    import war_source
    real = war_source.stint_frame

    def flaky(side, *a, **kw):
        if side == side_to_break:
            raise RuntimeError(f"simulated {side_to_break} frame outage")
        return real(side, *a, **kw)

    monkeypatch.setattr(war_source, "stint_frame", flaky)


def test_whole_index_reports_no_missing_sides(clean_index):
    fa_ident.war_daily_index()
    assert fa_ident.index_sides_missing() == (), (
        "a healthy build must report an empty tuple, or callers cannot tell "
        "'whole' from 'never asked'")


def test_a_failed_pitching_frame_is_recorded_not_swallowed(clean_index, monkeypatch):
    """THE REGRESSION TEST. Before the fix this returned a bat-only index and
    said nothing, and 79 free agents went blank."""
    _break_side(monkeypatch, "pit")
    fa_ident.war_daily_index()
    assert fa_ident.index_sides_missing() == ("pit",), (
        "a half-loaded index must name the missing side so the caller can "
        "refuse to publish a board off it")


def test_a_failed_batting_frame_is_recorded_too(clean_index, monkeypatch):
    """Symmetric on purpose. The batting frame is disk-cached so it fails far
    less often, which is exactly why nobody would notice if this half were
    unguarded."""
    _break_side(monkeypatch, "bat")
    fa_ident.war_daily_index()
    assert fa_ident.index_sides_missing() == ("bat",)


def test_the_completeness_record_never_pollutes_the_index(clean_index, monkeypatch):
    _break_side(monkeypatch, "pit")
    idx = fa_ident.war_daily_index()
    assert all(isinstance(k, str) for k in idx), "index keys must stay names"
    assert not [k for k in idx if k.startswith("__")], (
        "the completeness stamp must live on the module, not in the index: "
        "callers iterate this dict")


def test_the_surviving_side_still_resolves(clean_index, monkeypatch):
    """The guard reports the damage without adding to it. With pitching gone,
    a hitter must still resolve - otherwise the 'fix' would turn a partial
    outage into a total one."""
    _break_side(monkeypatch, "pit")
    idx = fa_ident.war_daily_index()
    if not idx:
        pytest.skip("no war_daily frames reachable in this environment")
    assert len(idx) > 100, (
        "the batting half loaded, so the index must still carry its names")
