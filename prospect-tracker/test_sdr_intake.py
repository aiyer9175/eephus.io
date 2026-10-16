# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Will drop seam, tested against Will's OWN fixtures (W0, 2026-08-18).

The pitcher-eWAR stream validates against his committed contract and his
committed fixture, so a drift in either is a red HERE before a real drop ever
lands. The defense card has no contract of Will's (no export adapter exists),
so the declared contract's rules are pinned instead, above all the refusal
that keeps the banned OAA/rfield blend class from re-entering through a new
door (ewar.py:806-812)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

import sdr_intake as si

FIXTURES = Path(si.ROOT).parent / "milb-projections" / "fixtures"


def _defense_frame(**over) -> pd.DataFrame:
    base = {
        "player_id": [999001, 999002, 999003],
        "season": [2024, 2024, 2025],
        "primary_position": ["SS", "C", "CF"],
        "innings": [1100.0, 900.0, 1200.0],
        "sdr_runs": [7.5, 4.0, -2.0],
        "range_runs": [5.0, 0.0, -1.0],
        "arm_runs": [1.5, 1.0, -1.0],
        "framing_runs": [None, 2.5, None],
        "blocking_runs": [None, 0.5, None],
        "dp_runs": [1.0, None, None],
        "level": ["MLB", "MLB", "MLB"],
        "as_of_date": ["2026-08-01"] * 3,
    }
    base.update(over)
    return pd.DataFrame(base)


# ---------------------------------------------------------------------------
# Will's contract + fixture are the authority for the eWAR streams
# ---------------------------------------------------------------------------

def test_contract_comes_from_wills_file_not_a_restatement():
    spec = si.contract_for("pitcher_ewar_mlb")
    doc = json.loads(si.WILLS_CONTRACT.read_text(encoding="utf-8"))
    art = doc["artifacts"]["mlb_pitcher_ewar"]
    assert spec["required_columns"] == art["required_columns"]
    assert spec["primary_key"] == art["primary_key"]
    assert spec["required_columns"], "an empty required set validates anything"


def test_wills_own_fixture_passes_his_own_contract(tmp_path):
    rows = json.loads(
        (FIXTURES / "pitcher_ewar_mlb.fixture.json").read_text(
            encoding="utf-8"))["rows"]
    p = tmp_path / "pitcher_ewar_mlb__2026-08-18.parquet"
    pd.DataFrame(rows).to_parquet(p)
    v = si.validate(p, "pitcher_ewar_mlb", db_path=tmp_path / "absent.db")
    assert v["problems"] == [], v["problems"]
    assert v["ok"] is True
    assert v["rows"] == len(rows)
    assert "rows_by_season" in v["census"]


def test_unknown_stream_raises():
    with pytest.raises(ValueError):
        si.contract_for("card_prices")


# ---------------------------------------------------------------------------
# the declared defense contract
# ---------------------------------------------------------------------------

def test_defense_card_good_drop_validates_with_census(tmp_path):
    p = tmp_path / "sdr_defense_card__2026-08-18.parquet"
    _defense_frame().to_parquet(p)
    v = si.validate(p, "sdr_defense_card", db_path=tmp_path / "absent.db")
    assert v["ok"] is True, v["problems"]
    assert v["census"]["rows_by_position"] == {"SS": 1, "C": 1, "CF": 1}
    assert v["census"]["component_coverage"]["framing_runs"] == 1


def test_range_only_blend_is_refused_with_the_clause_named(tmp_path):
    df = _defense_frame(arm_runs=[None] * 3, framing_runs=[None] * 3,
                        blocking_runs=[None] * 3, dp_runs=[None] * 3)
    p = tmp_path / "sdr_defense_card__2026-08-18.parquet"
    df.to_parquet(p)
    v = si.validate(p, "sdr_defense_card", db_path=tmp_path / "absent.db")
    assert v["ok"] is False
    assert any("ewar.py:806-812" in pr for pr in v["problems"])


def test_duplicate_primary_key_is_refused(tmp_path):
    df = _defense_frame(player_id=[999001, 999001, 999003],
                        season=[2024, 2024, 2025],
                        primary_position=["SS", "SS", "CF"])
    p = tmp_path / "sdr_defense_card__2026-08-18.parquet"
    df.to_parquet(p)
    v = si.validate(p, "sdr_defense_card", db_path=tmp_path / "absent.db")
    assert any("duplicate" in pr for pr in v["problems"])


def test_missing_required_column_is_refused(tmp_path):
    df = _defense_frame().drop(columns=["sdr_runs"])
    p = tmp_path / "sdr_defense_card__2026-08-18.parquet"
    df.to_parquet(p)
    v = si.validate(p, "sdr_defense_card", db_path=tmp_path / "absent.db")
    assert any("missing required" in pr for pr in v["problems"])


def test_entirely_null_required_column_is_refused(tmp_path):
    df = _defense_frame(innings=[None, None, None])
    p = tmp_path / "sdr_defense_card__2026-08-18.parquet"
    df.to_parquet(p)
    v = si.validate(p, "sdr_defense_card", db_path=tmp_path / "absent.db")
    assert any("entirely null" in pr for pr in v["problems"])


# ---------------------------------------------------------------------------
# identity: reported, never bound
# ---------------------------------------------------------------------------

def test_identity_misses_are_reported_not_bound(tmp_path):
    db = tmp_path / "p.db"
    con = sqlite3.connect(str(db))
    con.execute("create table players (mlbam integer)")
    con.execute("insert into players values (999001)")
    con.commit(); con.close()
    p = tmp_path / "sdr_defense_card__2026-08-18.parquet"
    _defense_frame().to_parquet(p)
    v = si.validate(p, "sdr_defense_card", db_path=db)
    ident = v["census"]["identity"]
    assert ident["resolved_mlbam"] == 1
    assert ident["unresolved"] == 2
    assert v["ok"] is True, "identity misses warn, they do not refuse"
    assert any("never auto-bound" in w for w in v["warnings"])


def test_identity_reads_the_live_schema(tmp_path):
    """The live players table has no mlbam column; the ids live in
    player_photos and mlb_trade_players (2026-10-15 defect: the query raised)."""
    db = tmp_path / "p.db"
    con = sqlite3.connect(str(db))
    con.execute("create table players (player_key text, player_name text)")
    con.execute("create table player_photos (mlbam_id text, player_key text)")
    con.execute("insert into player_photos values ('999001', 'a_b')")
    con.execute("create table mlb_trade_players (mlbam_id integer)")
    con.execute("insert into mlb_trade_players values (999002)")
    con.commit(); con.close()
    assert si._mlbam_set(db) == {999001, 999002}
    p = tmp_path / "sdr_defense_card__2026-08-18.parquet"
    _defense_frame().to_parquet(p)
    v = si.validate(p, "sdr_defense_card", db_path=db)
    assert v["census"]["identity"]["resolved_mlbam"] == 2


# ---------------------------------------------------------------------------
# acceptance: census first, append-only ledger, load-through-manifest
# ---------------------------------------------------------------------------

def test_accept_writes_census_and_ledger_and_roundtrips(tmp_path):
    p = tmp_path / "sdr_defense_card__2026-08-18.parquet"
    _defense_frame().to_parquet(p)
    man, cen = tmp_path / "manifest.json", tmp_path / "census.json"
    v = si.accept(p, "sdr_defense_card", db_path=tmp_path / "absent.db",
                  manifest_path=man, census_path=cen)
    assert v.get("accepted") is True
    census = json.loads(cen.read_text(encoding="utf-8"))
    assert census["streams"]["sdr_defense_card"]["rows"] == 3
    ledger = json.loads(man.read_text(encoding="utf-8"))
    assert len(ledger) == 1 and ledger[0]["sha256"]
    got = si.newest_accepted("sdr_defense_card", manifest_path=man,
                             drops_dir=tmp_path)
    assert got == p
    assert si.newest_accepted("pitcher_ewar_mlb", manifest_path=man,
                              drops_dir=tmp_path) is None


def test_a_refused_drop_is_never_accepted_or_ledgered(tmp_path):
    df = _defense_frame().drop(columns=["sdr_runs"])
    p = tmp_path / "sdr_defense_card__2026-08-18.parquet"
    df.to_parquet(p)
    man, cen = tmp_path / "manifest.json", tmp_path / "census.json"
    v = si.accept(p, "sdr_defense_card", db_path=tmp_path / "absent.db",
                  manifest_path=man, census_path=cen)
    assert v.get("accepted") is not True
    assert not man.exists() and not cen.exists()
