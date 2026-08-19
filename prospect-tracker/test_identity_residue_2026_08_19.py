# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the 2026-08-19 identity-residue batch repair.

tools/repair_identity_residue_2026_08_19.py resolved 11 of 12 open C7
name-variant splits (alias routes), 8 of 10 C4 side conflicts (wrong-era
photo bindings split off the incumbent keys) and re-bound junior_garcia to
his own mlbam id. These tests pin that the repaired keys STAY repaired,
the same way scrapers._SPLIT_KEYS pins protect the jesus_lopez and
garrett_wright repairs: a re-merge by a later ingest is the failure mode
that already happened once (carlos_castillo).

The DB is opened READ-ONLY; nothing here writes.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
DB = HERE / "prospects.db"

#: stale key -> canonical key, the 12 routes the repair shipped.
C7_ROUTES = {
    "bj_murray_jr": "bj_murray",
    "ben_cowles": "benjamin_cowles",
    "javi_vaz": "javier_vaz",
    "zach_thornton__noid": "zac_thornton",
    "alex_santos": "alex_santos_ii",
    "jay_allen": "jay_allen_ii",
    "lonnie_jr_white": "lonnie_white_jr",
    "jared_jones__sa3034881": "jared_jones_702262",
    "dennis_colleran": "dennis_colleran_jr",
    "dennis_colleran__noid": "dennis_colleran_jr",
    "leonardo_bernal__noid": "leo_bernal",
    "junior_garcia_815010": "junior_garcia",
}

#: incumbent key, the wrong-era pitcher id split off it, and the pitcher's
#: own dob that moved with him.
C4_SPLITS = [
    ("michael_perez", 805872, "2002-09-05", "MIA"),
    ("david_rodriguez", 815095, "2001-12-31", "ATL"),
    ("alexander_campos", 814226, "2003-04-14", "TBR"),
    ("enmanuel_rodriguez", 840917, "2006-12-18", "BAL"),
    ("jose_gomez", 823845, "2006-09-09", "NYM"),
    ("jose_rondon", 831791, "2005-03-24", "PIT"),
    ("aaron_brown", 676345, "1999-03-19", "HOU"),
]


@pytest.fixture(scope="module")
def con():
    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# ---------------------------------------------------------------------------
# C7: the alias routes stay live and unambiguous
# ---------------------------------------------------------------------------

def test_c7_alias_routes_present():
    from consensus import PLAYER_KEY_ALIASES
    for stale, canon in C7_ROUTES.items():
        route = (PLAYER_KEY_ALIASES.get(stale) or {}).get("player_key")
        assert route == canon, (
            f"PLAYER_KEY_ALIASES lost the {stale} -> {canon} route "
            f"(found {route!r}); the 2026-08-19 C7 batch would reopen")


def test_c7_alias_routes_do_not_chain():
    from consensus import PLAYER_KEY_ALIASES
    for stale, canon in C7_ROUTES.items():
        assert canon not in PLAYER_KEY_ALIASES, (
            f"canonical key {canon} became an alias source itself; the "
            f"{stale} route now chains and the read-time fold breaks")


def test_c7_canonical_keys_exist(con):
    for canon in set(C7_ROUTES.values()):
        row = con.execute("SELECT 1 FROM players WHERE player_key=?",
                          (canon,)).fetchone()
        assert row is not None, f"canonical key {canon} has no players row"


# ---------------------------------------------------------------------------
# C4: the wrong-era pitcher bindings stay split off the incumbents
# ---------------------------------------------------------------------------

def test_c4_bindings_stay_on_split_keys(con):
    for key, mid, _dob, _org in C4_SPLITS:
        split_key = f"{key}_{mid}"
        row = con.execute(
            "SELECT player_key FROM player_photos WHERE mlbam_id=?",
            (mid,)).fetchone()
        assert row is not None, f"binding for mlbam {mid} vanished"
        assert row["player_key"] == split_key, (
            f"mlbam {mid} re-merged onto {row['player_key']!r}; it belongs "
            f"on {split_key} (the carlos_castillo re-merge failure mode)")


def test_c4_split_rows_exist_as_pitchers(con):
    for key, mid, dob, org in C4_SPLITS:
        split_key = f"{key}_{mid}"
        row = con.execute(
            "SELECT is_pitcher, birth_date, org FROM players "
            "WHERE player_key=?", (split_key,)).fetchone()
        assert row is not None, f"players[{split_key}] vanished"
        assert row["is_pitcher"] == 1, f"{split_key} lost its pitcher side"
        assert str(row["birth_date"])[:10] == dob, (
            f"{split_key} lost the newcomer's dob {dob}")
        assert row["org"] == org, f"{split_key} lost its org {org}"


def test_c4_incumbents_no_longer_carry_the_newcomers_dob(con):
    for key, _mid, dob, _org in C4_SPLITS:
        row = con.execute(
            "SELECT birth_date FROM players WHERE player_key=?",
            (key,)).fetchone()
        assert row is not None, f"incumbent players[{key}] vanished"
        got = str(row["birth_date"] or "")[:10]
        assert got != dob, (
            f"players[{key}].birth_date is the split-off pitcher's {dob} "
            f"again; the one-row-two-humans chimera is back")


def test_c4_split_keys_pinned_in_scrapers():
    from scrapers import _SPLIT_KEYS
    wanted = [(k, m, f"{k}_{m}") for k, m, _d, _o in C4_SPLITS]
    wanted.append(("junior_garcia", 642371, "junior_garcia_642371"))
    for slug, mid, split_key in wanted:
        assert _SPLIT_KEYS.get((slug, mid)) == split_key, (
            f"_SPLIT_KEYS lost ({slug}, {mid}) -> {split_key}; the next "
            f"ingest can re-merge the two humans")


def test_c4_acquisitions_stay_with_the_pitchers(con):
    sigs = {
        "michael_perez_805872": ("international_fa", 2022, "Miami Marlins"),
        "alexander_campos_814226": ("international_fa", 2023, "Tampa Bay Rays"),
        "enmanuel_rodriguez_840917": ("international_fa", 2026, "Baltimore Orioles"),
        "jose_gomez_823845": ("international_fa", 2024, "New York Mets"),
        "jose_rondon_831791": ("international_fa", 2025, "Pittsburgh Pirates"),
        "david_rodriguez_815095": ("draft", 2023, "ATL"),
        "aaron_brown_676345": ("draft", 2021, "HOU"),
        "junior_garcia_642371": ("international_fa", 2012, "Houston Astros"),
    }
    for split_key, (method, year, team) in sigs.items():
        row = con.execute(
            "SELECT 1 FROM acquisitions WHERE player_key=? AND method=? "
            "AND year=? AND team_name=?",
            (split_key, method, year, team)).fetchone()
        assert row is not None, (
            f"the {split_key} acquisition ({method} {year} {team}) moved "
            f"off the split key")


# ---------------------------------------------------------------------------
# junior_garcia: his own id on his board key, the wrong id split off
# ---------------------------------------------------------------------------

def test_junior_garcia_bound_to_his_own_id(con):
    row = con.execute(
        "SELECT player_key FROM player_photos WHERE mlbam_id=815010").fetchone()
    assert row is not None and row["player_key"] == "junior_garcia", (
        "mlbam 815010 (the ATL OF's own id) is no longer bound to his "
        "board key junior_garcia")
    wrong = con.execute(
        "SELECT player_key FROM player_photos WHERE mlbam_id=642371").fetchone()
    assert wrong is not None and wrong["player_key"] == "junior_garcia_642371", (
        "mlbam 642371 (the 2012 HOU IFA LHP) crept back off "
        "junior_garcia_642371")


def test_junior_garcia_keeps_his_own_dob(con):
    row = con.execute(
        "SELECT birth_date, org FROM players WHERE player_key='junior_garcia'"
    ).fetchone()
    assert row is not None
    assert str(row["birth_date"])[:10] == "2005-07-13", (
        "junior_garcia lost the ATL OF's own dob")


# ---------------------------------------------------------------------------
# The report reflects the repair (regenerated 2026-08-19 post-apply)
# ---------------------------------------------------------------------------

def test_report_shows_the_residue_closed():
    doc = json.loads((HERE / "data" / "identity_collisions.json")
                     .read_text(encoding="utf-8"))
    resolved = {tuple(r["pair"]): r for r in doc["name_variant_splits"]}
    for stale, canon in C7_ROUTES.items():
        pair = tuple(sorted((stale, canon)))
        if pair not in resolved:
            continue    # a pair drops out entirely once a key goes dormant
        assert resolved[pair]["resolved_by_alias"], (
            f"the report shows {pair} unrouted again")
    # The one disclosed open case stays honest: it is either still open or
    # adjudicated later, but it must never silently exceed the batch's
    # disclosed remainder without a new repair.
    open_pairs = [r["pair"] for r in doc["name_variant_splits"]
                  if not r["resolved_by_alias"]
                  and r["status"] != "two_humans_distinct_ids"]
    assert len(open_pairs) <= 1, (
        f"c7 open regressed past the disclosed dom_keegan remainder: "
        f"{open_pairs}")
