# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Staff Gems stage 1, identity (staff_identity.py): a person is the MLBAM id, never the name.
No name-only join creates or merges a person; a two-people-one-name fixture stays two. Every
person id below is a pseudonym (900000 and up); no network, no database."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import staff_identity as sid  # noqa: E402


def _row(pid, name, season, job="COAT"):
    person = {"fullName": name}
    if pid is not None:
        person["id"] = pid
    return {"person": person, "jobId": job, "title": "Hitting Coach", "season": season}


def _spell(pid, org, season):
    return {"person_id": pid, "org_id": org, "season": season}


# two different people who share one name, at two organizations, and a third person elsewhere
ROWS = [_row(900101, "Staff Person Same", 2023), _row(900101, "Staff Person Same", 2024),
        _row(900102, "Staff Person Same", 2024), _row(900103, "Staff Person Other", 2024)]
SPELLS = [_spell(900101, 147, 2023), _spell(900101, 147, 2024), _spell(900102, 120, 2024),
          _spell(900103, 120, 2024)]


def test_two_people_with_one_name_stay_two():
    persons, rejects = sid.build_persons(ROWS)
    assert rejects == []
    assert sorted(persons) == [900101, 900102, 900103]
    assert persons[900101]["full_name"] == persons[900102]["full_name"] == "Staff Person Same"
    assert (persons[900101]["first_season"], persons[900101]["last_season"]) == (2023, 2024)
    assert sid.shared_names(persons) == {"staff person same": [900101, 900102]}


def test_one_id_under_two_spellings_stays_one_person():
    persons, _ = sid.build_persons([_row(900201, "Staff Persón Twelve", 2019),
                                    _row(900201, "Staff Person Twelve Jr.", 2022)])
    assert list(persons) == [900201]
    p = persons[900201]
    assert p["full_name"] == "Staff Person Twelve Jr." and len(p["names"]) == 2


def test_a_row_without_an_mlbam_id_creates_no_person():
    persons, rejects = sid.build_persons([_row(None, "Staff Person Nameonly", 2024),
                                          _row("abc", "Staff Person Badid", 2024),
                                          _row(0, "Staff Person Zero", 2024),
                                          _row(True, "Staff Person Bool", 2024)])
    assert persons == {} and len(rejects) == 4


def test_a_name_only_row_joins_only_one_person_holding_a_spell_at_that_org_and_season():
    persons, _ = sid.build_persons(ROWS)
    before = {k: dict(v) for k, v in persons.items()}
    idx = sid.SpellIndex(persons, SPELLS)
    rows = [
        {"name": "Staff Person Same", "org_id": 147, "season": 2024, "note": "a"},   # one match
        {"name": "staff  person SAME", "org_id": 120, "season": 2024, "note": "b"},  # the other one
        {"name": "Staff Person Same", "org_id": 147, "season": 2025, "note": "c"},   # no spell that season
        {"name": "Staff Person New", "org_id": 147, "season": 2024, "note": "d"},    # nobody by that name
        {"name": "Staff Person Same", "org_id": None, "season": 2024, "note": "e"},  # no org
    ]
    joined, review = sid.resolve_name_only(rows, idx, source="press_release_fixture")
    assert [(j["note"], j["person_id"]) for j in joined] == [("a", 900101), ("b", 900102)]
    assert [(r["payload"]["note"], r["reason"]) for r in review] == [
        ("c", "no_match"), ("d", "no_match"), ("e", "no_org_season")]
    assert all("person_id" not in r for r in review)
    # nothing was created, merged or renamed
    assert {k: dict(v) for k, v in persons.items()} == before


def test_two_people_with_one_name_at_one_org_and_season_go_to_review():
    rows = ROWS + [_row(900104, "Staff Person Same", 2024)]
    spells = SPELLS + [_spell(900104, 147, 2024)]
    persons, _ = sid.build_persons(rows)
    joined, review = sid.resolve_name_only(
        [{"name": "Staff Person Same", "org_id": 147, "season": 2024}], sid.SpellIndex(persons, spells),
        source="press_release_fixture")
    assert joined == []
    assert [(r["reason"], r["candidates"]) for r in review] == [("ambiguous", [900101, 900104])]
    assert len(persons) == 4


def test_name_normalization_is_for_lookup_only():
    assert sid.normalize_name("  José  A. Pérez ") == sid.normalize_name("jose a perez")
    assert sid.normalize_name(None) == ""
    persons, _ = sid.build_persons([_row(900301, "José Pérez", 2024)])
    idx = sid.SpellIndex(persons, [_spell(900301, 147, 2024)])
    joined, _ = sid.resolve_name_only([{"name": "Jose Perez", "org_id": 147, "season": 2024}], idx, "x")
    assert joined[0]["person_id"] == 900301
    assert persons[900301]["full_name"] == "José Pérez"


def test_identity_reads_no_database_grade_or_outcome():
    src = (ROOT / "staff_identity.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(storage|sqlite3|requests|urllib)", src, re.M)
    for banned in ("fv", "war", "efv", "snapshots", "career"):
        assert not re.search(rf"\b{banned}\b", src), banned
    assert chr(0x2014) not in src and chr(0x2013) not in src
