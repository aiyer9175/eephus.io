# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Outcome-blind identity resolution for list-vintage rows (DS-03, bug B4 in
docs/efv-v2/DRIVER_SYSTEM_V2.md).

WHY THIS EXISTS. A prospect row on the list-vintage frame F-LV needs a StatsAPI person id
to read its MiLB record. The ids on the repo's own records were attached mostly when a
player reached the majors: 72% of debuts.json records carry one against 44% of
inactive.json records, and the birth date travels with the id. So "this row has an id"
and "this row has a MiLB block" are largely "this player debuted". A resolver that uses
the debut, or that prefers the ids the records already carry, hands every missingness
indicator the label. Lane I2 measured it: a name-plus-debut-year resolver made an age
plus level model "beat" consensus by +0.0304 (CI95 +0.0125 to +0.0496) on the
development vintages; outcome-blind resolution gave +0.0003 (CI95 -0.0174 to +0.0176).

THE RULE. A row at list vintage V is resolved from three inputs only: the player's name
as the list printed it, V, and the side the frame routed the row to (hitter or pitcher,
efv_dataset._side_match, which the frame applies before any resolution). Its candidates
are the person ids whose normalized name matches and who were in affiliated minor
league baseball before the V read: a stat line at a minor league level (StatsAPI sports
11 to 16) in a season up to V - 1, or a draft selection in a June up to V - 1. One
candidate resolves the row; none leaves it unresolved. Several candidates pass two
tiebreaks, applied in this order and each only to the survivors of the one before
(EFV3 lane A, G5):

    SIDE      keep the candidates whose pre-V minor league lines are in the row's own
              group: hitting for a hitter row, pitching for a pitcher row. A
              candidate's group is the one that holds more of his pre-V exposure
              (plate appearances against batters faced), because a pitcher who batted
              carries a hitting line and a position player who pitched an inning
              carries a pitching line. A candidate with no line (a draft selection
              only) or with equal exposure has no group and is not kept.
    RECENCY   keep the candidates with a stat line in V - 1 or V - 2.

A tiebreak that leaves exactly one candidate resolves the row (how = "name_side" or
"name_recency"); otherwise the row stays ambiguous. Both tiebreaks read pre-V minor
league stat lines only, the evidence class the rule already reads. The prior, counted by
the lane on lv_dev before the rules were written (SP/efv3/LANE_A.md s1.8): 412
ambiguous rows, 127 resolved by side, 140 more by recency, 141 remaining ambiguous and
4 with no recent candidate. The balance receipt below is the measure that matters.

Nothing else is read:

    - no debut date, debut year or first-major-league season,
    - no major league stat line (the sport-1 files are never opened),
    - no WAR, label or outcome module,
    - not the record's own stored id or birth date, both of which were attached mostly on
      reaching the majors (the id is kept on the row for audit, never used to resolve).

test_efv_identity.py enforces this on the source (an AST scan) and on behaviour (a row's
resolution does not move when every outcome field on its record is changed).

WHAT IT COSTS. A common name with two candidates on the same side with recent lines
stays unresolved whether or not the player debuted, so resolution is symmetric in the
outcome by construction. Balance on the label is then MEASURED, not assumed:
tools/efv_identity_balance.py reports the W3 > 0 share by every missingness indicator
and by each tiebreak route on the development vintages (data/efv_identity_balance.json).

RESERVED FRAMES. The resolver computes nothing about a vintage beyond names and ids, but
callers that go on to read a row pass through efv_vintage_frame.guard_score_request
first. Nothing here groups rows by any grade.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import milb_history as mh

ROOT = Path(__file__).parent
DRAFT_DIR = ROOT / ".cache" / "draft_history"

#: The only StatsAPI sports the index reads: affiliated minor league levels. The major
#: league sport is deliberately absent.
INDEX_SPORTS: tuple[int, ...] = tuple(mh.MINOR_SPORTS)
#: The first season the minor league cache holds.
FIRST_INDEX_SEASON = 2005
GROUPS = ("hitting", "pitching")
#: The frame's side names and the stat group each one reads (SIDE tiebreak).
SIDE_GROUP = {"hit": "hitting", "pit": "pitching"}
#: The exposure field of a lean stat line per group: plate appearances, batters faced.
EXPOSURE_FIELD = {"hitting": "pa", "pitching": "bf"}
#: RECENCY keeps a candidate with a stat line in one of this many seasons before V.
RECENT_SEASONS = 2

HOW_RESOLVED = "name_unique"
HOW_SIDE = "name_side"
HOW_RECENCY = "name_recency"
HOW_NONE = "no_candidate"
HOW_AMBIGUOUS = "ambiguous"
HOW_NO_NAME = "no_name"
#: Every route that ends in a person id.
HOW_WITH_ID = (HOW_RESOLVED, HOW_SIDE, HOW_RECENCY)

_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
_NON_ALPHA = re.compile(r"[^a-z]")


def norm_name(name: str | None) -> str:
    """Accent-folded, lower-case letters only, generational suffix removed."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    s = _SUFFIX.sub("", s.lower())
    return _NON_ALPHA.sub("", s)


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class Resolution:
    person_id: int | None
    how: str
    n_candidates: int


class NameIndex:
    """{normalized name: {person id: first season he was in affiliated ball}}, plus,
    per (name, person id, group), the exposure of each minor league season's stat line.

    First season is the earliest minor league season with a stat line, or draft year + 0
    for a June selection (the pick is known from that June on). A read at list vintage
    V may use only entries whose first season is at most V - 1."""

    def __init__(self, entries: dict[str, dict[int, int]] | None = None):
        self._by_name: dict[str, dict[int, int]] = entries or {}
        self._lines: dict[str, dict[int, dict[str, dict[int, float]]]] = {}

    def add(self, name: str | None, person_id, season: int, group: str | None = None,
            exposure=None) -> None:
        """Register a season for a person: a stat line when `group` is given (with its
        exposure, plate appearances or batters faced), a draft selection otherwise."""
        key = norm_name(name)
        if not key or not person_id:
            return
        try:
            pid = int(person_id)
        except (TypeError, ValueError):
            return
        slot = self._by_name.setdefault(key, {})
        prev = slot.get(pid)
        if prev is None or int(season) < prev:
            slot[pid] = int(season)
        if group is not None:
            per = self._lines.setdefault(key, {}).setdefault(pid, {}).setdefault(group, {})
            per[int(season)] = per.get(int(season), 0.0) + _num(exposure)

    def candidates(self, name: str | None, vintage: int) -> dict[int, int]:
        """Person ids for `name` already in affiliated ball before the V read."""
        last = int(vintage) - 1
        return {pid: s for pid, s in (self._by_name.get(norm_name(name)) or {}).items()
                if s <= last}

    def lines(self, name: str | None, person_id: int, vintage: int) -> dict[str, dict[int, float]]:
        """{group: {season: exposure}} of the person's stat lines before the V read."""
        last = int(vintage) - 1
        per = (self._lines.get(norm_name(name)) or {}).get(int(person_id)) or {}
        return {g: {s: x for s, x in rows.items() if s <= last} for g, rows in per.items()}

    def __len__(self) -> int:
        return len(self._by_name)


_INDEX_MEMO: dict[int, NameIndex] = {}


def build_index(last_season: int, *, draft_dir: Path = DRAFT_DIR) -> NameIndex:
    """The name index over minor league seasons FIRST_INDEX_SEASON..last_season and draft
    classes up to last_season, from the on-disk caches only (never fetches)."""
    last = int(last_season)
    if last in _INDEX_MEMO and draft_dir == DRAFT_DIR:
        return _INDEX_MEMO[last]
    idx = NameIndex()
    for season in range(FIRST_INDEX_SEASON, last + 1):
        for sport in INDEX_SPORTS:
            for group in GROUPS:
                field = EXPOSURE_FIELD[group]
                for r in mh.season_splits(sport, season, group, fetch=False):
                    idx.add(r.get("name"), r.get("mlbam"), season, group, r.get(field))
    if Path(draft_dir).is_dir():
        for p in sorted(Path(draft_dir).glob("*.json")):
            stem = p.stem[:4]
            if not stem.isdigit() or int(stem) > last:
                continue
            try:
                picks = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for x in picks or []:
                idx.add(x.get("name"), x.get("mlbam"), int(stem))
    if draft_dir == DRAFT_DIR:
        _INDEX_MEMO[last] = idx
    return idx


def _group_of(lines: dict[str, dict[int, float]]) -> str | None:
    """The group holding more of a candidate's pre-V exposure; None when he has no
    line or the two groups tie (a draft selection only, or no usable exposure)."""
    tot = {g: sum(lines.get(g, {}).values()) for g in GROUPS}
    best = max(GROUPS, key=lambda g: tot[g])
    others = [tot[g] for g in GROUPS if g != best]
    if not lines or tot[best] <= max(others):
        return None
    return best


def _recent(lines: dict[str, dict[int, float]], vintage: int) -> bool:
    """True when any group holds a stat line in V - 1 .. V - RECENT_SEASONS."""
    first = int(vintage) - RECENT_SEASONS
    return any(s >= first for rows in lines.values() for s in rows)


def resolve(name: str | None, vintage: int, index: NameIndex,
            side: str | None = None) -> Resolution:
    """Resolve one list row from its printed name, its list vintage and the side the
    frame routed it to. With no side the tiebreaks do not run."""
    if not norm_name(name):
        return Resolution(None, HOW_NO_NAME, 0)
    cands = index.candidates(name, vintage)
    n = len(cands)
    if n == 1:
        return Resolution(next(iter(cands)), HOW_RESOLVED, 1)
    if not cands:
        return Resolution(None, HOW_NONE, 0)
    group = SIDE_GROUP.get(side or "")
    if group is None:
        return Resolution(None, HOW_AMBIGUOUS, n)
    lines = {pid: index.lines(name, pid, vintage) for pid in cands}
    kept = [pid for pid in cands if _group_of(lines[pid]) == group]
    if len(kept) == 1:
        return Resolution(kept[0], HOW_SIDE, n)
    recent = [pid for pid in kept if _recent(lines[pid], vintage)]
    if len(recent) == 1:
        return Resolution(recent[0], HOW_RECENCY, n)
    return Resolution(None, HOW_AMBIGUOUS, n)


def resolve_record(rec: dict, vintage: int, index: NameIndex,
                   side: str | None = None) -> Resolution:
    """resolve() on a universe record: reads its printed name and nothing else."""
    return resolve(rec.get("player_name"), vintage, index, side)
