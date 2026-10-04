# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Staff Gems stage 1: who a staff person is (design docs/staff-gems/DESIGN.md section 2.2).

THE RULE. A person is the MLBAM person id, never the name.
  - persons are built ONLY from rows that carry an MLBAM id; a row without one is rejected and
    counted, and creates nothing;
  - two ids that share a name are two persons (in the 2008 to 2026 StatsAPI staff lists, 45 exact
    names, 52 after normalize_name, are carried by more than one id), and one id seen under two
    spellings stays one person;
  - a name-only row (a future source with names and no id, for example a press release) joins a
    person ONLY when its name matches exactly one person holding a spell at the same organization
    in the same season. Anything else (no match, two or more matches, no organization or season)
    goes to the identity review queue and is not used. A name never creates or merges a person.

The site has served two humans merged under one key before (census X03-01); staff names repeat
across the game, and a merged coach would carry another man's record.

This module reads no grade, no outcome and no database; it is pure functions over rows.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Iterable


def normalize_name(name: str | None) -> str:
    """The comparison key for a name: accents stripped, case folded, periods dropped,
    whitespace collapsed. Used only to look a name up, never to create or merge a person."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace(".", " ")
    return re.sub(r"\s+", " ", s).strip().casefold()


def person_id_of(row: dict) -> int | None:
    """The MLBAM id on a StatsAPI staff row, or None. A non-integer id is no id."""
    pid = (row.get("person") or {}).get("id")
    if pid is None or isinstance(pid, bool):
        return None
    try:
        out = int(pid)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def build_persons(rows: Iterable[dict]) -> tuple[dict[int, dict], list[dict]]:
    """Persons from StatsAPI staff rows, keyed by MLBAM id.

    Each row is a staff-list row with `season` added. Returns ({person_id: person}, rejects), where
    a person is {person_id, full_name (the name on the latest season), names (every distinct name,
    sorted), first_season, last_season} and rejects are the rows with no usable id."""
    by_id: dict[int, dict] = {}
    rejects: list[dict] = []
    for r in rows:
        pid = person_id_of(r)
        if pid is None:
            rejects.append(r)
            continue
        name = str((r.get("person") or {}).get("fullName") or "").strip()
        season = int(r["season"])
        p = by_id.get(pid)
        if p is None:
            by_id[pid] = {"person_id": pid, "full_name": name, "names": {name} - {""},
                          "first_season": season, "last_season": season, "_name_season": season}
            continue
        if name:
            p["names"].add(name)
            if season >= p["_name_season"] or not p["full_name"]:
                p["full_name"], p["_name_season"] = name, season
        p["first_season"] = min(p["first_season"], season)
        p["last_season"] = max(p["last_season"], season)
    for p in by_id.values():
        p["names"] = sorted(p["names"])
        p.pop("_name_season", None)
    return by_id, rejects


class SpellIndex:
    """Which persons held a spell at (organization, season), looked up by normalized name."""

    def __init__(self, persons: dict[int, dict], spells: Iterable[dict]):
        self._persons = persons
        self._at: dict[tuple[int, int], set[int]] = defaultdict(set)
        for s in spells:
            pid = s.get("person_id")
            if pid is None or int(pid) not in persons:
                continue
            self._at[(int(s["org_id"]), int(s["season"]))].add(int(pid))

    def candidates(self, name: str, org_id: int, season: int) -> list[int]:
        key = normalize_name(name)
        if not key:
            return []
        out = []
        for pid in sorted(self._at.get((int(org_id), int(season)), ())):
            names = self._persons[pid]["names"] or [self._persons[pid]["full_name"]]
            if any(normalize_name(n) == key for n in names):
                out.append(pid)
        return out


def resolve_name_only(rows: Iterable[dict], index: SpellIndex,
                      source: str) -> tuple[list[dict], list[dict]]:
    """Join name-only rows ({name, org_id, season, ...}) to persons under THE RULE.

    Returns (joined, review). A joined row is the input row plus `person_id`. A review row is
    {source, name, org_id, season, reason, candidates, payload}, reason one of no_org_season,
    no_match, ambiguous. Nothing is ever added to the persons."""
    joined: list[dict] = []
    review: list[dict] = []
    for r in rows:
        name = str(r.get("name") or "").strip()
        org_id, season = r.get("org_id"), r.get("season")
        base = {"source": source, "name": name, "org_id": org_id, "season": season,
                "payload": {k: v for k, v in r.items() if k not in ("name", "org_id", "season")}}
        if org_id is None or season is None or not name:
            review.append({**base, "reason": "no_org_season", "candidates": []})
            continue
        cands = index.candidates(name, int(org_id), int(season))
        if len(cands) == 1:
            joined.append({**r, "person_id": cands[0]})
        elif not cands:
            review.append({**base, "reason": "no_match", "candidates": []})
        else:
            review.append({**base, "reason": "ambiguous", "candidates": cands})
    return joined, review


def shared_names(persons: dict[int, dict]) -> dict[str, list[int]]:
    """{normalized name: [person ids]} for every name more than one person carries."""
    by_name: dict[str, set[int]] = defaultdict(set)
    for pid, p in persons.items():
        for n in p["names"] or [p["full_name"]]:
            k = normalize_name(n)
            if k:
                by_name[k].add(pid)
    return {k: sorted(v) for k, v in sorted(by_name.items()) if len(v) > 1}
