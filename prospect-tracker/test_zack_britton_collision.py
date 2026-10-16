# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the zack_britton repair (BA_KEEP_FORWARD_READ Part B,
tools/repair_zack_britton_collision.py).

Baseball America's 2023 Blue Jays board printed the Blue Jays outfielder Zach
Britton (mlbam 676309) as "Zack Britton", and the ingest filed the row under the
veteran left-hander's key zack_britton (mlbam 502154). The same-name prune in
consensus then hid the veteran's 2011 history. These tests pin:

  1. the outcome-blind resolution (name, board year, side, pre-V minor league
     lines and draft picks only) routes the row to 676309;
  2. the ingest pins that keep a re-ingest from re-merging it;
  3. the repair on a fixture database (moves, deletions, idempotence);
  4. the consensus consequence on fixture snapshots: the veteran's 2011 points
     survive once the 2023 row is off his key;
  5. on the real database, once the repair has run there, the row stays put.

Fixture tests write only to tmp_path; the real database is opened read-only.
"""

from __future__ import annotations

import ast
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
DB = HERE / "prospects.db"
TOOL = HERE / "tools" / "repair_zack_britton_collision.py"


def _tool():
    spec = importlib.util.spec_from_file_location("repair_zack_britton_collision", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("repair_zack_britton_collision", mod)
    spec.loader.exec_module(mod)
    return mod


def _index():
    import efv_identity as ID
    idx = ID.NameIndex()
    # the veteran: pitching lines only, first in affiliated ball 2006
    for season, bf in ((2006, 153), (2010, 644), (2021, 21), (2022, 24)):
        idx.add("Zack Britton", 502154, season, "pitching", bf)
    # the outfielder: 2020 June pick, hitting lines 2021 and 2022
    idx.add("Zach Britton", 676309, 2020)
    idx.add("Zach Britton", 676309, 2021, "hitting", 333)
    idx.add("Zach Britton", 676309, 2022, "hitting", 312)
    # a same-side one-letter variant with no recent line must not compete
    idx.add("Zack Brittan", 111111, 2012, "hitting", 200)
    return idx


# ---------------------------------------------------------------------------
# 1. the outcome-blind resolution
# ---------------------------------------------------------------------------

def test_name_rule_alone_lands_on_the_veteran():
    import efv_identity as ID
    res = ID.resolve("Zack Britton", 2023, _index(), "hit")
    assert res.person_id == 502154 and res.how == ID.HOW_RESOLVED


def test_side_conflict_routes_the_hitter_row_to_the_outfielder():
    out = _tool().resolve_ba_row("Zack Britton", 2023, "hit", _index())
    assert out["person_id"] == 676309
    assert out["how"] == "variant_side"
    assert out["side_conflict"] == {"person_id": 502154, "group": "pitching"}


def test_a_pitcher_row_of_the_same_name_stays_with_the_veteran():
    out = _tool().resolve_ba_row("Zack Britton", 2023, "pit", _index())
    assert out["person_id"] == 502154 and out["how"] != "variant_side"


def test_nothing_after_the_board_year_is_read():
    # at V 2021 the outfielder has no pre-V line yet (first line 2021): unresolved,
    # never the veteran by default
    out = _tool().resolve_ba_row("Zack Britton", 2021, "hit", _index())
    assert out["person_id"] is None and out["how"] == "side_conflict_unresolved"


def test_resolver_reads_no_outcome():
    src = TOOL.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "resolve_ba_row")
    used = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Name):
            used.add(n.id)
        elif isinstance(n, ast.Attribute):
            used.add(n.attr)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            used.update(a.name for a in n.names)
            used.add(getattr(n, "module", None) or "")
    banned = {"career_war", "efv_labels", "fwar_vintage", "war_source", "effective_debut",
              "debut_day_for_cutoff", "resolved_debut_date", "season_totals", "milb_history"}
    assert not (used & banned), used & banned


def test_one_edit():
    t = _tool()
    assert t._one_edit("zackbritton", "zachbritton")
    assert t._one_edit("zackbritton", "zacbritton")
    assert not t._one_edit("zackbritton", "zackbritton")
    assert not t._one_edit("zackbritton", "jackbrittan")


def test_real_caches_resolve_the_board_row():
    import efv_identity as ID
    idx = ID.build_index(2022)
    if not idx.candidates("Zach Britton", 2023):
        pytest.skip("minor league caches not on disk")
    out = _tool().resolve_kid(idx)
    assert out["person_id"] == 676309 and out["how"] == "variant_side"


# ---------------------------------------------------------------------------
# 2. the ingest pins
# ---------------------------------------------------------------------------

def test_ingest_pins():
    import baseballamerica_csv as BAC
    from scrapers import split_key_for_mlbam
    assert BAC._BA_ORG_SPLIT_KEYS[("zack_britton", "TOR")] == "zach_britton"
    assert split_key_for_mlbam("zack_britton", 676309) == "zach_britton"
    assert split_key_for_mlbam("zack_britton", 502154) is None


# ---------------------------------------------------------------------------
# 3. the repair on a fixture database
# ---------------------------------------------------------------------------

def _fixture_db(path: Path) -> None:
    con = sqlite3.connect(str(path))
    con.executescript("""
    CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
        snapshot_date TEXT NOT NULL, interval_label TEXT NOT NULL, player_key TEXT NOT NULL,
        player_name TEXT NOT NULL, position TEXT, org TEXT, rank INTEGER, fv REAL,
        status TEXT NOT NULL, tools_json TEXT, fv_plus INTEGER NOT NULL DEFAULT 0,
        UNIQUE(source, interval_label, player_key));
    CREATE TABLE players (player_key TEXT PRIMARY KEY, player_name TEXT NOT NULL,
        position TEXT, org TEXT, is_pitcher INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')), birth_date TEXT);
    CREATE TABLE draft_canonical_keys (draft_key TEXT PRIMARY KEY, milb_key TEXT NOT NULL,
        promoted_at TEXT NOT NULL DEFAULT (datetime('now')));
    CREATE TABLE draft_players (player_key TEXT PRIMARY KEY, player_name TEXT,
        mlbam_id INTEGER, promoted_key TEXT);
    CREATE TABLE acquisitions (player_key TEXT PRIMARY KEY, method TEXT NOT NULL, year INTEGER,
        round_label TEXT, pick_round INTEGER, pick_overall INTEGER, bonus_usd INTEGER,
        team_name TEXT, school TEXT, signing_date TEXT, fetched_at TEXT);
    CREATE TABLE trades (id INTEGER PRIMARY KEY AUTOINCREMENT, player_key TEXT NOT NULL,
        trade_date TEXT NOT NULL, from_org TEXT, to_org TEXT, source TEXT NOT NULL,
        UNIQUE(player_key, trade_date, source));
    INSERT INTO snapshots (source, snapshot_date, interval_label, player_key, player_name,
        org, rank, fv, status) VALUES
        ('mlb_pipeline', '2011-01-22', 'MLB Pipeline 2011 Orioles Top 30', 'zack_britton',
         'Zack Britton', 'NYY', 1, NULL, 'active'),
        ('baseballamerica', '2023-02-15', 'Baseball America 2023 Blue Jays Top 30',
         'zack_britton', 'Zack Britton', 'TOR', 24, 40.0, 'active');
    INSERT INTO players (player_key, player_name, org) VALUES ('zack_britton', 'Zack Britton', 'NYY');
    INSERT INTO draft_canonical_keys (draft_key, milb_key) VALUES
        ('draft_2020_zack_britton', 'zack_britton'), ('draft_2020_zach_britton', 'zach_britton');
    INSERT INTO draft_players VALUES ('draft_2020_zack_britton', 'Zack Britton', NULL, 'zack_britton');
    INSERT INTO acquisitions (player_key, method, year, pick_overall, team_name) VALUES
        ('zack_britton', 'draft', 2020, 136, 'TOR'), ('zach_britton', 'draft', 2020, 136, 'TOR');
    INSERT INTO trades (player_key, trade_date, from_org, to_org, source) VALUES
        ('zack_britton', '2023-02-15', 'NYY', 'TOR', 'inferred');
    """)
    con.commit()
    con.close()


RES = {"person_id": 676309, "how": "variant_side"}


def test_repair_dry_run_writes_nothing(tmp_path):
    db = tmp_path / "p.db"
    _fixture_db(db)
    out = _tool().repair(db, apply=False, resolution=RES)
    assert out["writes"] == 6 and not out["ambiguous"] and out["refused"] is None
    con = sqlite3.connect(str(db))
    assert con.execute("SELECT COUNT(*) FROM snapshots WHERE player_key='zach_britton'"
                       ).fetchone()[0] == 0


def test_repair_moves_the_newcomer_and_is_idempotent(tmp_path):
    db = tmp_path / "p.db"
    _fixture_db(db)
    t = _tool()
    assert t.repair(db, apply=True, resolution=RES)["writes"] == 6
    con = sqlite3.connect(str(db))
    assert con.execute("SELECT player_key, player_name FROM snapshots WHERE source="
                       "'baseballamerica'").fetchone() == ("zach_britton", "Zach Britton")
    assert con.execute("SELECT player_key FROM snapshots WHERE source='mlb_pipeline'"
                       ).fetchone() == ("zack_britton",)
    assert con.execute("SELECT org, is_pitcher, birth_date FROM players WHERE "
                       "player_key='zach_britton'").fetchone() == ("TOR", 0, None)
    assert con.execute("SELECT milb_key FROM draft_canonical_keys WHERE draft_key="
                       "'draft_2020_zack_britton'").fetchone() == ("zach_britton",)
    assert con.execute("SELECT promoted_key FROM draft_players").fetchone() == ("zach_britton",)
    assert con.execute("SELECT COUNT(*) FROM acquisitions WHERE player_key='zack_britton'"
                       ).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 0
    con.close()
    assert t.repair(db, apply=True, resolution=RES)["writes"] == 0


def test_repair_refuses_without_the_resolution(tmp_path):
    db = tmp_path / "p.db"
    _fixture_db(db)
    out = _tool().repair(db, apply=True, resolution={"person_id": 502154, "how": "name_unique"})
    assert out["refused"] and out["writes"] == 0


# ---------------------------------------------------------------------------
# 4. the consensus consequence
# ---------------------------------------------------------------------------

def _snap(key, name, date, label, org, rank, fv, src):
    from scrapers import Snapshot
    return Snapshot(source=src, snapshot_date=date, interval_label=label, player_key=key,
                    player_name=name, position=None, org=org, rank=rank, fv=fv, status="active")


def test_the_2023_row_on_the_veterans_key_hides_his_2011_points():
    import consensus as C
    vet = [_snap("zack_britton", "Zack Britton", "2011-01-22", "MLB Pipeline 2011 Top 100",
                 "BAL", 19, None, "mlb_pipeline")]
    kid = ("Baseball America 2023 Blue Jays Top 30", "TOR", 24, 40.0, "baseballamerica")
    merged = C.build_timeseries(vet + [_snap("zack_britton", "Zack Britton", "2023-02-15", *kid)])
    pts = {p.player_key: [q.snapshot_date for q in p.points] for p in merged}
    assert pts["zack_britton"] == ["2023-02-15"]
    split = C.build_timeseries(vet + [_snap("zach_britton", "Zach Britton", "2023-02-15", *kid)])
    pts = {p.player_key: [q.snapshot_date for q in p.points] for p in split}
    assert pts["zack_britton"] == ["2011-01-22"]
    assert pts["zach_britton"] == ["2023-02-15"]


# ---------------------------------------------------------------------------
# 5. the real database, once the repair has run there
# ---------------------------------------------------------------------------

def test_real_db_stays_repaired():
    if not DB.exists():
        pytest.skip("no prospects.db")
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        if con.execute("SELECT 1 FROM players WHERE player_key='zach_britton'").fetchone() is None:
            pytest.skip("the repair has not run on this database yet")
        rows = con.execute("SELECT player_key FROM snapshots WHERE source='baseballamerica' AND "
                           "snapshot_date='2023-02-15' AND org='TOR' AND player_key IN "
                           "('zack_britton','zach_britton')").fetchall()
        assert rows == [("zach_britton",)]
        assert con.execute("SELECT COUNT(*) FROM snapshots WHERE player_key='zack_britton' AND "
                           "snapshot_date >= '2019-01-01'").fetchone()[0] == 0
    finally:
        con.close()
