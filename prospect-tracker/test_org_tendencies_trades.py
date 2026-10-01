# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The org Tendencies trade profile counts real trades between the 30 clubs.

WHY THIS EXISTS (census M02-05, 2026-09-25, two verifiers PARTLY, one raising it to
P0). Four stacked defects built the served trade panel: inferred rows re-fired daily
(easton_mcgee's one NAS -> KCR move sat on 45 rows), affiliate codes counted as clubs
(SAL -> LAA, ALB -> COL, OMA -> KCR roster changes read as trades), the league mean
and sd ran over 69 codes before the 30-club filter (24 of 30 clubs read trade-happy
and none trade-reluctant, a dead filter chip), and every mlb_api row was dropped for
carrying a full club name. After de-duplication, inferred moves were still mostly
two sources disagreeing on a player's org (1,512 of 3,706 moves were A -> B -> A round
trips), so the panel counted the MLB transaction feed only. Owner answer M8-3
(2026-09-25): the panel counts the feed PLUS the inferred moves after an A -> B -> A
round-trip filter (ROUND_TRIP_DAYS, 90): two feed legs both count, a feed leg outranks
an inferred one, and two inferred legs both drop.

Contract pinned here:
  * trade_moves canonicalises full club names, keeps only moves between two
    different clubs of the 30, counts a move once, and leaves inferred rows out
    unless asked (then de-duplicated on (player, from, to, date_range_start) and
    superseded by a feed row for the same player and clubs);
  * trades_panel's league stats run over the 30 clubs (the 30 zVolume average 0);
  * a second inference run on a rolling snapshot date inserts no row;
  * the served artifact has labels on both sides of the volume axis.
"""
from __future__ import annotations

import sqlite3
import statistics

import pytest

import org_tendencies as ot
import storage

MLB30 = set(storage.MLB_30_ORGS)


def test_trade_moves_counts_feed_trades_once():
    rows = [
        ("p1", "2026-07-14", "Milwaukee Brewers", "Kansas City Royals", "mlb_api", None),
        ("p1", "2026-07-25", "NAS", "KCR", "inferred", "2022-10-02"),
        ("p1", "2026-07-26", "NAS", "KCR", "inferred", "2022-10-02"),
        ("p2", "2025-04-01", "SAL", "LAA", "inferred", "2025-03-01"),       # affiliate -> parent
        ("p3", "2025-05-01", "Caliente de Durango", "Texas Rangers", "mlb_api", None),
        ("p4", "2025-06-01", "LAD", "NYM", "inferred", "2025-05-01"),
        ("p4", "2025-06-02", "LAD", "NYM", "inferred", "2025-05-01"),
    ]
    assert ot.trade_moves(rows, MLB30) == [("p1", "2026-07-14", "MIL", "KCR")]
    with_inf = ot.trade_moves(rows, MLB30, include_inferred=True)
    assert sorted(with_inf) == [("p1", "2026-07-14", "MIL", "KCR"), ("p4", "2025-06-01", "LAD", "NYM")]


def _mem_con(rows):
    con = sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE trades (id INTEGER PRIMARY KEY, player_key TEXT, trade_date TEXT,
                   from_org TEXT, to_org TEXT, source TEXT, description TEXT,
                   date_range_start TEXT, date_range_end TEXT)""")
    con.execute("CREATE TABLE snapshots (player_key TEXT, snapshot_date TEXT, fv REAL)")
    con.executemany("INSERT INTO trades (player_key, trade_date, from_org, to_org, source, description) "
                    "VALUES (?, ?, ?, ?, 'mlb_api', ?)", rows)
    return con


def test_league_stats_run_over_the_thirty_clubs():
    clubs = sorted(MLB30)
    rows = []
    for i, club in enumerate(clubs):
        for j in range(i % 7 + 1):
            rows.append((f"k{i}_{j}", "2025-07-01", club, clubs[(i + 1) % 30], "x traded y"))
    # a foreign-league row must not enter the league stats
    rows.append(("kf", "2025-07-01", "Leones de Yucatan", "Texas Rangers", "x traded y"))
    panel = ot.trades_panel(_mem_con(rows), MLB30)
    assert set(panel["orgs"]) == MLB30
    zs = [r["zVolume"] for r in panel["orgs"].values()]
    assert statistics.mean(zs) == pytest.approx(0, abs=0.01)
    labels = {r["volLabel"] for r in panel["orgs"].values()}
    assert "trade-happy" in labels and "trade-reluctant" in labels


def test_rolling_inference_inserts_no_duplicate(tmp_path, monkeypatch):
    from trades import Trade
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE trades (id INTEGER PRIMARY KEY AUTOINCREMENT, player_key TEXT NOT NULL,
                   trade_date TEXT NOT NULL, from_org TEXT, to_org TEXT, source TEXT NOT NULL,
                   description TEXT, date_range_start TEXT, date_range_end TEXT,
                   inserted_at TEXT NOT NULL DEFAULT (datetime('now')),
                   UNIQUE(player_key, trade_date, source))""")
    con.commit(); con.close()
    monkeypatch.setattr(storage, "DB_PATH", db)
    day1 = Trade("easton_mcgee", "2026-07-25", "NAS", "KCR", "inferred", None, "2022-10-02", "2026-07-25")
    day2 = Trade("easton_mcgee", "2026-07-26", "NAS", "KCR", "inferred", None, "2022-10-02", "2026-07-26")
    assert storage.insert_trades([day1]) == 1
    assert storage.insert_trades([day2]) == 0
    other = Trade("easton_mcgee", "2026-08-01", "KCR", "MIL", "inferred", None, "2026-07-26", "2026-08-01")
    assert storage.insert_trades([other]) == 1


def test_served_trade_panel_is_thirty_club_relative():
    from conftest import load_data_doc
    doc = load_data_doc("org_tendencies.json")
    if not doc:
        pytest.skip("org_tendencies.json not exported")
    orgs = doc["trades"]["orgs"]
    assert set(orgs) == MLB30
    zs = [r["zVolume"] for r in orgs.values() if r["zVolume"] is not None]
    assert statistics.mean(zs) == pytest.approx(0, abs=0.02)
    labels = [r["volLabel"] for r in orgs.values()]
    assert "trade-reluctant" in labels and "trade-happy" in labels


# Owner answer M8-3 (2026-09-25): feed + inferred moves after an A -> B -> A filter.
def _rt(rows, days=90):
    return sorted(ot.trade_moves(rows, MLB30, include_inferred=True, round_trip_days=days))


def test_round_trip_of_two_inferred_legs_drops_both():
    rows = [
        ("kl", "2025-05-01", "TOR", "NYY", "inferred", "2025-04-20"),
        ("kl", "2025-05-28", "NYY", "TOR", "inferred", "2025-05-02"),
        ("ok", "2025-06-01", "LAD", "NYM", "inferred", "2025-05-01"),
    ]
    assert _rt(rows) == [("ok", "2025-06-01", "LAD", "NYM")]
    # Without the filter both legs of the round trip count.
    assert len(ot.trade_moves(rows, MLB30, include_inferred=True)) == 3


def test_round_trip_outside_the_window_keeps_both_legs():
    rows = [
        ("kl", "2025-01-01", "TOR", "NYY", "inferred", "2024-12-01"),
        ("kl", "2025-06-01", "NYY", "TOR", "inferred", "2025-01-02"),
    ]
    assert len(_rt(rows, days=90)) == 2
    assert _rt(rows, days=365) == []


def test_feed_legs_are_authoritative():
    # Two feed legs are two real transactions: both count.
    feed2 = [
        ("w", "2025-03-01", "Seattle Mariners", "Tampa Bay Rays", "mlb_api", None),
        ("w", "2025-04-01", "Tampa Bay Rays", "Seattle Mariners", "mlb_api", None),
    ]
    assert len(_rt(feed2)) == 2
    # A feed leg and an inferred reverse: the feed leg stays, the inferred one drops.
    mixed = [
        ("m", "2025-07-01", "Milwaukee Brewers", "Kansas City Royals", "mlb_api", None),
        ("m", "2025-07-20", "KCR", "MIL", "inferred", "2025-07-02"),
    ]
    assert _rt(mixed) == [("m", "2025-07-01", "MIL", "KCR")]
    # An inferred leg then a feed reverse: the feed leg stays.
    mixed2 = [
        ("n", "2025-07-01", "KCR", "MIL", "inferred", "2025-06-01"),
        ("n", "2025-07-20", "Milwaukee Brewers", "Kansas City Royals", "mlb_api", None),
    ]
    assert _rt(mixed2) == [("n", "2025-07-20", "MIL", "KCR")]


def test_flip_flop_keeps_at_most_one_move():
    rows = [
        ("f", "2025-05-01", "TOR", "NYY", "inferred", "2025-04-01"),
        ("f", "2025-05-10", "NYY", "TOR", "inferred", "2025-05-02"),
        ("f", "2025-05-20", "TOR", "NYY", "inferred", "2025-05-11"),
    ]
    assert _rt(rows) == [("f", "2025-05-20", "TOR", "NYY")]


def test_trades_panel_counts_feed_plus_filtered_inferred():
    con = sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE trades (id INTEGER PRIMARY KEY, player_key TEXT, trade_date TEXT,
                   from_org TEXT, to_org TEXT, source TEXT, description TEXT,
                   date_range_start TEXT, date_range_end TEXT)""")
    con.execute("CREATE TABLE snapshots (player_key TEXT, snapshot_date TEXT, fv REAL)")
    con.executemany(
        "INSERT INTO trades (player_key, trade_date, from_org, to_org, source, description, "
        "date_range_start) VALUES (?, ?, ?, ?, ?, ?, ?)", [
            ("a", "2025-07-01", "Seattle Mariners", "Tampa Bay Rays", "mlb_api", "x traded a", None),
            ("b", "2025-08-01", "SEA", "TBR", "inferred", None, "2025-07-15"),
            ("c", "2025-08-01", "SEA", "TBR", "inferred", None, "2025-07-15"),
            ("c", "2025-08-20", "TBR", "SEA", "inferred", None, "2025-08-02"),
        ])
    panel = ot.trades_panel(con, MLB30)
    assert panel["roundTripDays"] == ot.ROUND_TRIP_DAYS == 90
    assert panel["orgs"]["TBR"]["in"] == 2 and panel["orgs"]["SEA"]["out"] == 2
    assert "A to B to A" in panel["note"]


def test_served_trade_panel_carries_the_round_trip_filter():
    from conftest import load_data_doc
    doc = load_data_doc("org_tendencies.json")
    if not doc:
        pytest.skip("org_tendencies.json not exported")
    tr = doc["trades"]
    assert tr.get("roundTripDays") == ot.ROUND_TRIP_DAYS, (
        "the served trade profile predates owner answer M8-3; re-run org_tendencies.export")
    assert "board snapshots" in tr["note"] and "A to B to A" in tr["note"]
