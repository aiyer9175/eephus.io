"""Data-integrity guards for the current active-prospect pool.

These guard against the 2017-2020 historical-leak regression: purely-historical
or graduated players must never appear in the current active pool that feeds farm
rankings, counts, leaderboards, the prospect list, and surplus rollups. The
historical record (snapshots / Time Machine) is a separate, append-only scope and
is intentionally NOT checked here.

Skipped when data/timeseries.json hasn't been built yet (CI without a DB).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

TS = Path(__file__).resolve().parent / "data" / "timeseries.json"
HARD_FV_STALE_YEARS = 5  # mirrors storage.export_timeseries_json


def _load():
    if not TS.exists():
        pytest.skip("data/timeseries.json not built")
    return json.loads(TS.read_text(encoding="utf-8"))


def _latest(p):
    pts = p.get("points") or []
    return pts[-1].get("snapshot_date") if pts else None


def test_no_aged_out_player_in_active_pool():
    """No active prospect may have a latest FV snapshot older than the ceiling."""
    d = _load()
    today = date.today()
    try:
        cutoff = date(today.year - HARD_FV_STALE_YEARS, today.month, today.day).isoformat()
    except ValueError:
        cutoff = date(today.year - HARD_FV_STALE_YEARS, today.month, 28).isoformat()
    aged = [(p["player_name"], _latest(p)) for p in d["players"]
            if _latest(p) and _latest(p) < cutoff]
    assert not aged, f"{len(aged)} aged-out players leaked into the active pool: {aged[:8]}"


def test_no_graduated_player_in_active_pool():
    """The active pool is current prospects only — no debuted/graduated players."""
    d = _load()
    grad = [p["player_name"] for p in d["players"] if p.get("status") == "debuted"]
    assert not grad, f"{len(grad)} graduated players leaked into the active pool: {grad[:8]}"


def test_farm_surplus_counts_active_only():
    """Each org's active-surplus count never exceeds its active prospect count —
    surplus must roll up active prospects only, never stale/graduated value."""
    d = _load()
    from collections import Counter
    active_by_org = Counter(p.get("org") for p in d["players"])
    for o in d["org_summary"]:
        n_surplus = o.get("_active_surplus_count") or 0
        n_active = active_by_org.get(o["org"], 0)
        assert n_surplus <= n_active, (
            f"{o['org']}: surplus count {n_surplus} > active prospects {n_active} "
            "— non-active value leaking into farm surplus")


def test_active_count_header_matches_players():
    """The stamped active_count equals the actual active player list length."""
    d = _load()
    assert d.get("active_count") == len(d["players"]), (
        f"active_count header {d.get('active_count')} != players {len(d['players'])}")
