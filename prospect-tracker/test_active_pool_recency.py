"""Data-integrity guards for the current active-prospect pool.

These guard against the 2017-2020 historical-leak regression: purely-historical
or graduated players must never appear in the current active pool that feeds farm
rankings, counts, leaderboards, the prospect list, and surplus rollups. The
historical record (snapshots / Time Machine) is a separate, append-only scope and
is intentionally NOT checked here.

Skipped when data/timeseries.json hasn't been built yet (CI without a DB).
"""
from __future__ import annotations

from datetime import date

HARD_FV_STALE_YEARS = 2  # mirrors storage.export_timeseries_json (calendar-year basis)

# Data access: the session-shared conftest.timeseries_doc fixture (one parse
# of the ~65MB artifact per suite run, skip-if-missing preserved). Every test
# below only READS the doc.


def _latest(p):
    pts = p.get("points") or []
    return pts[-1].get("snapshot_date") if pts else None


def _latest_year(p):
    ld = _latest(p)
    try:
        return int(ld[:4]) if ld else None
    except ValueError:
        return None


def test_no_aged_out_player_in_active_pool(timeseries_doc):
    """No active prospect may have aged out of the recency ceiling: a grade in
    the current year or within HARD_FV_STALE_YEARS prior calendar years is
    required (no source update in 2+ calendar years = aged out)."""
    d = timeseries_doc
    min_year = date.today().year - HARD_FV_STALE_YEARS
    aged = [(p["player_name"], _latest(p)) for p in d["players"]
            if (_latest_year(p) is not None and _latest_year(p) < min_year)]
    assert not aged, f"{len(aged)} aged-out players leaked into the active pool: {aged[:8]}"


def test_no_graduated_player_in_active_pool(timeseries_doc):
    """The active pool is current prospects only - no debuted/graduated players."""
    d = timeseries_doc
    grad = [p["player_name"] for p in d["players"] if p.get("status") == "debuted"]
    assert not grad, f"{len(grad)} graduated players leaked into the active pool: {grad[:8]}"


def test_farm_surplus_counts_active_only(timeseries_doc):
    """Each org's active-surplus count never exceeds its active prospect count -
    surplus must roll up active prospects only, never stale/graduated value."""
    d = timeseries_doc
    from collections import Counter
    active_by_org = Counter(p.get("org") for p in d["players"])
    for o in d["org_summary"]:
        n_surplus = o.get("_active_surplus_count") or 0
        n_active = active_by_org.get(o["org"], 0)
        assert n_surplus <= n_active, (
            f"{o['org']}: surplus count {n_surplus} > active prospects {n_active} "
            "— non-active value leaking into farm surplus")


def test_active_count_header_matches_players(timeseries_doc):
    """The stamped active_count equals the actual active player list length."""
    d = timeseries_doc
    assert d.get("active_count") == len(d["players"]), (
        f"active_count header {d.get('active_count')} != players {len(d['players'])}")
