# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB News feed FV-item dating - the first-seen ledger.

The daily Live snapshot re-stamps its point's snapshot_date on every run,
so a grade change detected against it re-dates daily and pins the player
to the wire's most-recent-day bucket indefinitely (Cleiner Ramirez, three
straight days, reported 2026-06-12). The ledger records the date each
(player, new grade) pair was FIRST published and serves it forever."""

from __future__ import annotations

import pytest

import build_site


@pytest.fixture()
def ledger_path(tmp_path, monkeypatch):
    p = tmp_path / "wire_fv_first_seen.json"
    monkeypatch.setattr(build_site, "_WIRE_FV_LEDGER", p)
    return p


def _player(key, points):
    return {"player_key": key, "player_name": key.title(), "org": "CLE",
            "points": [{"snapshot_date": d, "consensus_fv_label": v}
                       for d, v in points]}


def _fv_dates(events):
    return {e[4]: e[0] for e in events if e[1] in ("grade_up", "grade_down")}


def test_fv_item_keeps_its_first_seen_date_across_live_redating(ledger_path):
    # Day 1: the live point publishes the new grade (35 -> 43) dated 06-10.
    p1 = _player("cleiner_ramirez", [("2026-02-12", 35), ("2026-06-10", 43)])
    ev1 = build_site._collect_events([p1], [], [])
    assert _fv_dates(ev1) == {"cleiner_ramirez": "2026-06-10"}

    # Days 2 and 3: the daily capture RE-STAMPS the live point. The wire
    # date must stay pinned at first sight, not ride to today.
    for redated in ("2026-06-11", "2026-06-12"):
        p = _player("cleiner_ramirez", [("2026-02-12", 35), (redated, 43)])
        ev = build_site._collect_events([p], [], [])
        assert _fv_dates(ev) == {"cleiner_ramirez": "2026-06-10"}, redated


def test_a_further_grade_change_re_dates(ledger_path):
    p1 = _player("riser", [("2026-02-12", 35), ("2026-06-10", 43)])
    build_site._collect_events([p1], [], [])
    # The grade moves AGAIN (43 -> 46) on 06-12: that is fresh news.
    p2 = _player("riser", [("2026-02-12", 35), ("2026-06-08", 43),
                           ("2026-06-12", 46)])
    ev = build_site._collect_events([p2], [], [])
    assert _fv_dates(ev) == {"riser": "2026-06-12"}


def test_ledger_prunes_departed_players_and_writes_stably(ledger_path):
    p1 = _player("stays", [("2026-02-12", 35), ("2026-06-10", 43)])
    p2 = _player("leaves", [("2026-02-12", 40), ("2026-06-10", 45)])
    build_site._collect_events([p1, p2], [], [])
    raw1 = ledger_path.read_text(encoding="utf-8")
    assert "leaves" in raw1
    build_site._collect_events([p1], [], [])
    raw2 = ledger_path.read_text(encoding="utf-8")
    assert "leaves" not in raw2 and "stays" in raw2
    # No-op rebuild: identical content, no churn (mtime-stable contract is
    # the byte-stable contract).
    build_site._collect_events([p1], [], [])
    assert ledger_path.read_text(encoding="utf-8") == raw2
