# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the 2026-09-30 identity split (census M02-11).

tools/repair_identity_split_2026_09_30.py moved other humans' board rows off
three debuted keys (jose_rodriguez, michael_massey, carlos_rodriguez), using
the MLB Pipeline Person id on each cached row as the proof of who the row
was. These tests pin the repair in the DB and pin the ingest seams that
re-merged jose_rodriguez after the 2026-08-04 repair: the Pipeline scraper
now routes a row by its Person id, FanGraphs and Spotrac route by club.

The DB is opened READ-ONLY; nothing here writes.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
DB = HERE / "prospects.db"

#: incumbent key -> (bound mlbam id, side of the ball the id plays)
INCUMBENTS = {
    "jose_rodriguez": (692064, "P"),
    "michael_massey": (686681, "H"),
    "carlos_rodriguez": (692230, "P"),
}

#: (slug, newcomer mlbam) -> the key that newcomer's rows live under
SPLITS = {
    ("jose_rodriguez", 679563): "jose_rodriguez_679563",
    ("jose_rodriguez", 800412): "jose_rodriguez_800412",
    ("jose_rodriguez", 836624): "jose_rodriguez_836624",
    ("michael_massey", 695602): "michael_massey__sa3037259",
    ("carlos_rodriguez", 677578): "carlos_d_rodriguez",
}


@pytest.fixture(scope="module")
def con():
    if not DB.exists():
        pytest.skip("prospects.db unavailable")
    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# ---------------------------------------------------------------------------
# The ingest seams
# ---------------------------------------------------------------------------

def test_split_keys_pinned_in_scrapers():
    import scrapers
    for (slug, mid), target in SPLITS.items():
        assert scrapers.split_key_for_mlbam(slug, mid) == target, (slug, mid)
    # The incumbents' own ids never route away from their keys.
    for key, (mid, _side) in INCUMBENTS.items():
        assert scrapers.split_key_for_mlbam(key, mid) is None, key


def _pipeline_page(persons: list[tuple[int, str, str, str]]) -> str:
    """A minimal Apollo cache page: one Person + Team per entry and a
    RankedPlayerEntity per person, in rank order."""
    parts = []
    for i, (pid, first, last, team) in enumerate(persons, start=1):
        parts.append(f'"Person:{pid}":{{"useName":"{first}","useLastName":"{last}",'
                     f'"activeRoster":{{"__ref":"Team:{i}"}}}},')
        parts.append(f'"Team:{i}":{{"name":"{team}","parentOrgName":null}},')
    for i, (pid, _f, _l, _t) in enumerate(persons, start=1):
        parts.append('{"__typename":"RankedPlayerEntity",'
                     f'"rank":{i},"player":{{"__ref":"Person:{pid}"}},"position":"SS"}},')
    return "{" + "".join(parts) + "}"


def test_pipeline_scrape_routes_a_known_newcomer_by_person_id(tmp_path, monkeypatch):
    """The 2026-08-05 and 2026-09-30 Pipeline upserts re-minted the MIL SS's
    rows on the TOR RHP's key because the scraper keyed by name alone while
    holding MLB's id for the row. It now consults scrapers._SPLIT_KEYS."""
    import scrapers
    monkeypatch.setattr(scrapers, "CACHE_DIR", tmp_path)
    page = _pipeline_page([
        (836624, "Jose", "Rodriguez", "Milwaukee Brewers"),
        (692064, "Jose", "Rodriguez", "Toronto Blue Jays"),
        (700000, "Konnor", "Griffin", "Pittsburgh Pirates"),
    ])
    (tmp_path / "pipeline_fixture.html").write_text(page, encoding="utf-8")
    rows = scrapers.scrape_mlb_pipeline(
        "https://example.invalid/", "fixture", "2026-01-22", 2026,
        cache_key="pipeline_fixture")
    keys = {r.rank: r.player_key for r in rows}
    assert keys == {1: "jose_rodriguez_836624", 2: "jose_rodriguez",
                    3: "konnor_griffin"}


def test_fangraphs_org_pins_route_the_newcomers():
    import fangraphs_csv as F
    assert F._row_id({"name": "Michael Massey", "org": "DET"})[0] == \
        "michael_massey__sa3037259"
    assert F._row_id({"name": "Michael Massey", "org": "KCR"})[0] == "michael_massey"
    assert F._row_id({"name": "Jose Rodriguez", "org": "MIL"})[0] == \
        "jose_rodriguez_836624"
    assert F._row_id({"name": "Jose Rodriguez", "org": "LAD"})[0] == "jose_rodriguez"


def test_spotrac_bonus_does_not_follow_the_slug_to_the_incumbent():
    """Spotrac's 2026 MIL $1.5M signing is 836624's; by name it landed on the
    TOR RHP, a 2019 LAD signing (served as his IFA bonus until 2026-09-30)."""
    import spotrac
    out = spotrac.build_ifa_bonus_by_key([
        {"year": 2022, "player_key": "jose_rodriguez", "org": "MIN",
         "bonus_usd": 650000},
        {"year": 2026, "player_key": "jose_rodriguez", "org": "MIL",
         "bonus_usd": 1500000},
        {"year": 2025, "player_key": "someone_else", "org": "MIL",
         "bonus_usd": 10000},
    ])
    assert "jose_rodriguez" not in out
    assert out["jose_rodriguez_836624"] == 1500000
    assert out["jose_rodriguez_800412"] == 650000
    assert out["someone_else"] == 10000


def _snap(key, name, date, pos, org, fv=40.0, source="fangraphs"):
    from scrapers import Snapshot
    return Snapshot(source=source, snapshot_date=date, interval_label=f"l{date}",
                    player_key=key, player_name=name, position=pos, org=org,
                    rank=1, fv=fv, status="active")


def test_same_name_humans_stay_apart_at_read_time():
    """build_timeseries merges any two keys whose printed names match (the v7
    __noid dedup), which put the DET RHP's rows back on the KCR 2B's card even
    after a key split. A SAME_NAME_NOT_DUPES pair keeps them apart; an
    unlisted same-name pair still merges as before."""
    import consensus as C
    assert frozenset(("michael_massey", "michael_massey__sa3037259")) in         C.SAME_NAME_NOT_DUPES
    snaps = [
        _snap("michael_massey", "Michael Massey", "2021-02-26", "2B", "KCR"),
        _snap("michael_massey__sa3037259", "Michael Massey", "2025-02-13", "SIRP", "DET"),
        _snap("some_player", "Some Player", "2021-02-26", "SS", "NYY"),
        _snap("some_player__noid", "Some Player", "2022-02-26", "SS", "NYY"),
    ]
    rows = {p.player_key: p for p in C.build_timeseries(snaps)}
    assert rows["michael_massey"].position == "2B"
    assert rows["michael_massey__sa3037259"].position == "SIRP"
    assert len(rows["michael_massey"].points) == 1
    assert "some_player__noid" not in rows
    assert len(rows["some_player"].points) == 2


def test_fragment_aliases_fold_onto_the_right_human():
    import consensus as C
    to = {k: v["player_key"] for k, v in C.PLAYER_KEY_ALIASES.items()}
    assert to["jose_rodriguez__sa3015437"] == "jose_rodriguez"
    assert to["michael_massey__noid"] == "michael_massey__sa3037259"
    assert to["carlos_rodriguez__sa3005478"] == "carlos_d_rodriguez"
    assert to["carlos_rodriguez__noid"] == "carlos_d_rodriguez"
    # No allowlisted pair is also folded together by an alias.
    for pair in C.SAME_NAME_NOT_DUPES:
        a, b = sorted(pair)
        assert to.get(a, a) != to.get(b, b), pair


# ---------------------------------------------------------------------------
# The repaired DB state
# ---------------------------------------------------------------------------

def test_bindings_name_one_human_per_key(con):
    bound = {r["mlbam_id"]: r["player_key"] for r in con.execute(
        "SELECT mlbam_id, player_key FROM player_photos WHERE mlbam_id IN "
        "(692064, 686681, 692230, 679563, 800412, 836624, 695602, 677578)")}
    for key, (mid, _side) in INCUMBENTS.items():
        assert bound.get(mid) == key, key
    for (_slug, mid), target in SPLITS.items():
        assert bound.get(mid) == target, (mid, target)


def test_incumbent_keys_carry_only_their_own_board_rows(con):
    """The three keys hold no board row of another human: every snapshot's
    position sits on the incumbent's side of the ball (auto_detect debut rows
    included, since their position came from the players row)."""
    import identity_audit as ia
    for key, (_mid, side) in INCUMBENTS.items():
        rows = con.execute(
            "SELECT source, snapshot_date, position, org FROM snapshots "
            "WHERE player_key = ? AND position IS NOT NULL", (key,)).fetchall()
        assert rows, key
        wrong = [tuple(r) for r in rows
                 if ia.position_kind(r["position"]) not in (None, side)]
        assert not wrong, f"{key} carries another side's rows: {wrong}"


def test_players_rows_describe_the_incumbent(con):
    for key, (_mid, side) in INCUMBENTS.items():
        r = con.execute("SELECT position, is_pitcher FROM players "
                        "WHERE player_key = ?", (key,)).fetchone()
        assert r is not None, key
        assert bool(r["is_pitcher"]) == (side == "P"), key


def test_split_keys_hold_the_moved_rows(con):
    expect = {
        "jose_rodriguez_679563": 13,
        "jose_rodriguez_800412": 2,
        "jose_rodriguez_836624": 4,
        "michael_massey__sa3037259": 6,
        "carlos_d_rodriguez": 14,
    }
    for key, at_least in expect.items():
        n = con.execute("SELECT COUNT(*) FROM snapshots WHERE player_key = ?",
                        (key,)).fetchone()[0]
        assert n >= at_least, (key, n)
        assert con.execute("SELECT 1 FROM players WHERE player_key = ?",
                           (key,)).fetchone(), key


def test_the_rhp_fragments_no_longer_carry_the_second_basemans_birth_date(con):
    for key in ("michael_massey__sa3037259", "michael_massey__noid"):
        r = con.execute("SELECT birth_date FROM players WHERE player_key = ?",
                        (key,)).fetchone()
        assert r is not None and r["birth_date"] != "1998-03-22", key


def test_report_shows_the_three_debuted_conflicts_closed():
    path = HERE / "data" / "identity_collisions.json"
    if not path.exists():
        pytest.skip("identity_collisions.json not built")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc.get("debuted_side_conflicts") == []
    assert not set(INCUMBENTS) & set(doc["critical_player_keys"])
