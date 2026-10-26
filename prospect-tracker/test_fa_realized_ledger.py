# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /fa/ Archive's realized ledger is rebuilt once after each regular season
(owner answer M14-3, 2026-09-25) on the displayed eWAR (PE-Q2, 2026-10-03).

Pinned here:
  - last_completed_season reads the season calendar on disk and falls back to
    October 15 only when it has none;
  - rebuild_realized_ledger acts once per season and records it, and a failed
    WAR read records nothing;
  - backfill_historical(completed_season=S, from_store=True) counts season S as
    elapsed, stamps the displayed provider, prorates the NPV guarantee, strips
    a stale ledger from a row that no longer resolves, and persists nothing
    when the WAR frames do not load;
  - run_monthly calls the rebuild before the FA export step;
  - the served Archive names one basis, the displayed one, in both files.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import fa_pipeline as fpl
import war_source

HERE = Path(__file__).parent


def _calendar(monkeypatch, ends: dict):
    import mgmt_decisions
    monkeypatch.setattr(mgmt_decisions, "regular_season_end_on_disk",
                        lambda season, **k: ends.get(int(season)))


def test_last_completed_season_reads_the_calendar(monkeypatch):
    _calendar(monkeypatch, {2025: "2025-09-28", 2026: "2026-09-27"})
    assert fpl.last_completed_season(date(2026, 9, 28)) == (2026, "regular season ended 2026-09-27")
    assert fpl.last_completed_season(date(2026, 9, 27))[0] == 2025
    assert fpl.last_completed_season(date(2026, 3, 1))[0] == 2025


def test_last_completed_season_falls_back_without_a_calendar(monkeypatch):
    _calendar(monkeypatch, {})
    season, basis = fpl.last_completed_season(date(2026, 10, 16))
    assert season == 2026 and basis.startswith("fallback end 2026-10-15")
    assert fpl.last_completed_season(date(2026, 10, 15))[0] == 2025


def test_the_rebuild_runs_once_per_season(monkeypatch):
    _calendar(monkeypatch, {2026: "2026-09-27"})
    checks, calls = {}, []

    def fake_backfill(**kw):
        calls.append(kw)
        return {"persisted": True, "ledger_rows": 7}

    monkeypatch.setattr(fpl, "backfill_historical", fake_backfill)
    monkeypatch.setattr(fpl.storage, "load_source_checks", lambda: dict(checks))
    monkeypatch.setattr(fpl.storage, "record_source_check",
                        lambda src, scope="", n_rows=None: checks.__setitem__(
                            (src, scope), {"checked_at": "2026-10-08", "n_rows": n_rows}))
    # the stored ledger already reads the displayed series (the basis check has its own test)
    monkeypatch.setattr(fpl, "_ledger_bases_off_display", lambda last_year: {})
    today = date(2026, 10, 8)
    first = fpl.rebuild_realized_ledger(today=today)
    assert first["ran"] and first["season"] == 2026
    assert first["war_basis"] == war_source.DISPLAY_PROVIDER
    assert calls == [{"completed_season": 2026, "from_store": True}]
    assert checks[(fpl.REALIZED_LEDGER_CHECK, "2026")]["n_rows"] == 7
    second = fpl.rebuild_realized_ledger(today=today)
    assert second["ran"] is False and "already rebuilt" in second["reason"]
    assert len(calls) == 1
    assert fpl.rebuild_realized_ledger(today=today, force=True)["ran"]
    assert fpl.rebuild_realized_ledger(2026)["ran"]
    assert len(calls) == 3


def test_a_recorded_season_rebuilds_once_more_when_the_displayed_war_moved(monkeypatch):
    """PORT_RED_TESTS_CLEAR (2026-10-26): the 2026 rebuild ran on 2026-10-08 on eWAR v2 and
    recorded the season, the display then moved to eWAR v3, and the once-per-season check
    kept the archive on v2 (1,576 rows). A recorded season whose stored rows read another
    series rebuilds once more; after that the rows read the displayed series and it stops."""
    _calendar(monkeypatch, {2026: "2026-09-27"})
    want = war_source.DISPLAY_PROVIDER
    stored = {2026: {("a", 2026): {"player_key": "a", "ledger": {"war_basis": "ewar_v2"}},
                     ("b", 2026): {"player_key": "b", "ledger": {}},
                     ("c", 2026): {"player_key": "c", "ledger": {"war_basis": want}}},
              2025: {("d", 2025): {"player_key": "d", "ledger": {"method": "x"}}}}
    calls = []

    def fake_backfill(**kw):
        calls.append(kw)
        for rows in stored.values():
            for r in rows.values():
                if r.get("ledger"):
                    r["ledger"]["war_basis"] = want
        return {"persisted": True, "ledger_rows": 3}

    monkeypatch.setattr(fpl, "get_config", lambda: {"backfill": {"first_class_year": 2025}})
    monkeypatch.setattr(fpl.storage, "load_fa_signings", lambda y: stored.get(y, {}))
    monkeypatch.setattr(fpl, "backfill_historical", fake_backfill)
    monkeypatch.setattr(fpl.storage, "load_source_checks", lambda: {
        (fpl.REALIZED_LEDGER_CHECK, "2026"): {"checked_at": "2026-10-08"}})
    monkeypatch.setattr(fpl.storage, "record_source_check", lambda *a, **k: None)
    # an unstamped row is the legacy bWAR basis
    assert fpl._ledger_bases_off_display(2026) == {"ewar_v2": 1, "bwar": 1}
    out = fpl.rebuild_realized_ledger(today=date(2026, 10, 26))
    assert out["ran"] and want in out["basis"] and len(calls) == 1
    assert fpl._ledger_bases_off_display(2026) == {}
    again = fpl.rebuild_realized_ledger(today=date(2026, 10, 26))
    assert again["ran"] is False and "already rebuilt" in again["reason"] and len(calls) == 1


def test_a_failed_war_read_records_nothing(monkeypatch):
    _calendar(monkeypatch, {2026: "2026-09-27"})
    recorded = []
    monkeypatch.setattr(fpl, "backfill_historical",
                        lambda **kw: {"persisted": False, "ledger_rows": 0,
                                      "error": "war_daily unavailable"})
    monkeypatch.setattr(fpl.storage, "load_source_checks", lambda: {})
    monkeypatch.setattr(fpl.storage, "record_source_check",
                        lambda *a, **k: recorded.append(a))
    out = fpl.rebuild_realized_ledger(today=date(2026, 10, 8))
    assert out["ran"] and out["persisted"] is False and recorded == []


_STORED = {
    2026: {("ace_pitcher", 2026): {"player_key": "ace_pitcher", "player_name": "Ace Pitcher",
                                   "class_year": 2026, "mlb_deal": True, "years": 2,
                                   "guarantee_usd": 40_000_000, "position": "SP"},
           ("gone_guy", 2026): {"player_key": "gone_guy", "player_name": "Gone Guy",
                                "class_year": 2026, "mlb_deal": True, "years": 1,
                                "guarantee_usd": 5_000_000, "position": "RP",
                                "ledger": {"war_to_date": 9.9, "method": "old"}}},
}


def _fixture_backfill(monkeypatch, resolved=True):
    import fa_class
    import fa_market
    upserts = {}
    monkeypatch.setattr(fpl, "get_config", lambda: {"backfill": {"first_class_year": 2026}})
    monkeypatch.setattr(fpl.storage, "load_fa_signings",
                        lambda year: {k: dict(v) for k, v in _STORED.get(year, {}).items()})
    monkeypatch.setattr(fpl.storage, "upsert_fa_signings",
                        lambda year, rows: upserts.setdefault(year, [dict(r) for r in rows]) and len(rows))
    monkeypatch.setattr(fa_class, "build_historical_class",
                        lambda *a, **k: pytest.fail("from_store must not scrape a class page"))
    # A deferred deal: NPV 30M against a 40M sticker.
    monkeypatch.setattr(fa_market, "npv_guarantee_usd",
                        lambda key, year, g: (30_000_000, True) if key == "ace_pitcher" else (g, False))
    monkeypatch.setattr(fa_class, "dollars_per_war_for_season", lambda s, cur=None: 10_000_000.0)

    def fake_resolve(classes, first_year, last_year):
        if not resolved:
            return {}, {}, {"error": "war_daily unavailable"}
        return ({"ace_pitcher": 123},
                {"ace_pitcher": {"seasons": {"2026": 3.5}, "source": war_source.DISPLAY_PROVIDER}},
                {"seen": 2, "resolved": 1, "no_match": 1, "ambiguous": 0})

    monkeypatch.setattr(fpl, "_resolve_signed_via_war_daily", fake_resolve)
    return upserts


def test_the_yearly_backfill_counts_the_season_just_played(monkeypatch):
    upserts = _fixture_backfill(monkeypatch)
    out = fpl.backfill_historical(completed_season=2026, from_store=True)
    assert out["persisted"] and out["last_year"] == 2026 and out["ledger_rows"] == 1
    rows = {r["player_key"]: r for r in upserts[2026]}
    led = rows["ace_pitcher"]["ledger"]
    assert led["elapsed_years"] == 1 and led["war_to_date"] == 3.5
    assert led["war_basis"] == war_source.DISPLAY_PROVIDER
    assert led["paid_to_date_usd"] == 15_000_000          # NPV 30M over 2 years, not 20M
    assert led["deferral_adjusted"] is True
    assert led["realized_value_usd"] == 35_000_000
    assert rows["ace_pitcher"]["mlbam_id"] == 123
    assert "ledger" not in rows["gone_guy"]                # a stale-basis figure never survives
    assert all("npv_guarantee_usd" not in r for r in rows.values())


def test_a_failed_war_read_persists_nothing(monkeypatch):
    upserts = _fixture_backfill(monkeypatch, resolved=False)
    out = fpl.backfill_historical(completed_season=2026, from_store=True)
    assert out["persisted"] is False and upserts == {}


def test_run_monthly_rebuilds_before_the_fa_export():
    src = (HERE / "run_monthly.py").read_text(encoding="utf-8")
    i_pre = src.index('_step("6-pre. FA realized ledger (once after each regular season)"')
    i_six = src.index('_step("6. FA refresh + export (fa_* sidecars)"')
    assert i_pre < i_six
    assert "fa_pipeline.rebuild_realized_ledger()" in src[i_pre:i_six]


def test_the_served_archive_names_the_displayed_basis():
    arc = json.loads((HERE / "data" / "fa_archive.json").read_text(encoding="utf-8"))
    meta = json.loads((HERE / "data" / "fa_meta.json").read_text(encoding="utf-8"))
    if arc.get("warBasis") == "bwar":
        pytest.skip("the archive on disk predates the M14-3 rebuild")
    assert arc["warBasis"] == meta["archive_war_basis"] == war_source.DISPLAY_PROVIDER
    assert set(arc["warBasisCounts"]) == {war_source.DISPLAY_PROVIDER}
    last = max(arc["winters"], key=lambda w: w["year"])
    priced = [s for s in last["signings"] if s.get("warTd") is not None]
    assert len(priced) >= 0.8 * sum(1 for s in last["signings"] if not s.get("milb")), (
        f"winter {last['year']}: only {len(priced)} rows carry realized WAR")
