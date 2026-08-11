# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Merged-identity detector (the "Jesus Flores" class).

Two different humans whose names normalize to the same slug can end up
sharing ONE board record. The pipeline already has three guards, and none
of them can see this class:

  * scrapers.split_key_for_mlbam returns None on a null mlbam_id (its first
    line), so it only splits players that ALREADY have an id - but these
    records merge precisely BECAUSE no id was ever bound.
  * mlbam_ingest._collision_safe_key forks correctly, but only when the
    slug is ALREADY durably bound in player_photos to a different id.
  * consensus._prune_collision_cluster needs two or more dated snapshots to
    find a gap; a merged record minted by a single performance_ingest
    snapshot has exactly one.

So the failure is silent: the built card looks coherent and nothing is
null. This module makes it loud. It is pure detection - it never writes to
prospects.db, never re-keys anything, and never mutates a build artifact
other than its own report at data/identity_collisions.json.

The detectors are plain functions over plain data (lists of dicts) so the
test suite can feed them a synthetic reconstruction of a known defect
without touching the real tree. build() is the thin wrapper that loads the
real artifacts and writes the report.

Five detectors, named the way the audit named them:

  C1 unsplit_collisions   one name slug, two or more real mlbam ids on the
                          StatsAPI rosters, and NOT two or more board keys
  C2 double_bound_keys    one player_key bound to two or more mlbam ids in
                          player_photos (the canonical binding table)
  C3 unresolved_active    an active board row with mlbam_id null that also
                          carries an assigned level (a real, placed player
                          we cannot identify - the merge-prone shape)
  C4 side_conflicts       a board record scored on one side of the ball
                          whose entire fielding log is the other side
  C5 birthdate_conflicts  board birth_date inconsistent with the roster age
                          of the mlbam id actually bound to that key

Severity: C2, C3, C4 and C5 are "critical" (a served record is wrong right
now). C1 splits: "shared_key" and "unattributed" are critical, "shadowed"
is a warning (the board record is correctly bound, the second human is
simply missing), and "split" / "untracked" are informational.
"""

from __future__ import annotations

import datetime
import json
import logging
from collections import defaultdict
from pathlib import Path

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
DATA_DIR = _HERE / "data"
REPORT_PATH = DATA_DIR / "identity_collisions.json"

# Age tolerance for C5. Roster ages are stamped at build time; the implied
# as-of date over 4191 correctly-bound rows spans 2026-07-07 to 2026-08-09
# (p5/p95) around a 2026-07-23 median, i.e. about +/-0.09y of stamping
# noise. 1.0y is far outside that and only fires on a real identity swap.
AGE_TOLERANCE_YEARS = 1.0

# C4 only fires on an unambiguous fielding record: at least this many games
# and no games at all on the side the board claims.
MIN_FIELDING_GAMES = 10

_PITCHER_TOKENS = frozenset({
    "P", "SP", "RP", "LHP", "RHP", "LHRP", "RHRP", "SIRP", "MIRP",
    "LHSP", "RHSP", "SP/RP", "RP/SP", "PITCHER", "TWP",
})
_HITTER_TOKENS = frozenset({
    "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "IF", "DH",
    "INF", "UTIL", "UT", "CIF", "MIF", "CATCHER",
})


def position_kind(position) -> str | None:
    """"P", "H", or None for a position label of unknown side.

    TWP (two-way) is deliberately treated as a pitcher token so a genuine
    two-way player never trips C4 from the hitter direction; C4 also
    requires a ZERO-game count on the claimed side, which a real two-way
    player can never satisfy."""
    if not position:
        return None
    tok = str(position).strip().upper()
    if tok in _PITCHER_TOKENS:
        return "P"
    if tok in _HITTER_TOKENS:
        return "H"
    return None


def normalize_name(name: str) -> str:
    """The pipeline's own slug function, so this audit groups names exactly
    the way the ingest paths key them. Falls back to a local
    reimplementation if scrapers is unavailable (standalone use)."""
    try:
        from scrapers import normalize_key
        return normalize_key(name)
    except Exception:  # pragma: no cover - import-time fallback
        import re
        import unicodedata
        s = unicodedata.normalize("NFKD", name or "")
        s = "".join(c for c in s if not unicodedata.combining(c))
        s = re.sub(r"[^a-z0-9\s]", "", s.lower().strip())
        return re.sub(r"\s+", "_", s)


# ---------------------------------------------------------------------------
# C7 - one human, two keys: the name-variant class C1 cannot see
# ---------------------------------------------------------------------------

_NAME_SUFFIX_TOKENS = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})


def _variant_tokens(name: str) -> list[str]:
    toks = normalize_name(name or "").split("_")
    return [t for t in toks if t and t not in _NAME_SUFFIX_TOKENS]


def _variant_names_match(a: str, b: str) -> bool:
    """True when two printed names are plausibly one human's name in two
    forms: identical after suffix/punctuation stripping (Wen Hui / Wen-Hui,
    Bergolla / Bergolla Jr.), or same surname with one given name a short
    form of the other (Zac/Zach, Cam/Cameron, Kam/Kamden)."""
    ta, tb = _variant_tokens(a), _variant_tokens(b)
    if not ta or not tb:
        return False
    if "".join(ta) == "".join(tb):
        return True
    if ta[-1] != tb[-1]:
        return False
    fa, fb = ta[0], tb[0]
    if len(fa) > len(fb):
        fa, fb = fb, fa
    return len(fa) >= 3 and fb.startswith(fa)


def find_name_variant_splits(players_rows, aliases=None,
                             active_within_days: int = 400,
                             as_of=None) -> list[dict]:
    """One human under two keys, found WITHOUT relying on the slug.

    C1 groups by name slug, so a spelling change that produces a DIFFERENT
    slug (Zac/Zach, Cam/Cameron, a gained suffix, a hyphen) is invisible to
    it by construction: that is how william_bergolla / william_bergolla_jr
    sat live while the report said zero. This detector keys on what a
    spelling change cannot alter, the stored (birth_date, org) pair, and
    then requires the two printed names to be plausible forms of one name.

    A pair already routed by consensus.PLAYER_KEY_ALIASES is reported with
    resolved_by_alias=True and is NOT critical (the read path folds it).
    A pair with no alias is the live defect this class exists to surface.
    Pairs where neither key has a snapshot within `active_within_days` are
    dropped: two long-dead cards colliding is archival noise, not a defect.
    """
    aliases = aliases or {}
    alias_to = {k: (v or {}).get("player_key") for k, v in aliases.items()}
    if as_of is None:
        as_of = datetime.date.today()
    cutoff = (as_of - datetime.timedelta(days=active_within_days)).isoformat()

    by_dob_org: dict[tuple, list[dict]] = defaultdict(list)
    for r in players_rows or []:
        dob, org = r.get("birth_date"), r.get("org")
        if not dob or not org or not r.get("player_key"):
            continue
        by_dob_org[(str(dob)[:10], org)].append(r)

    out: list[dict] = []
    for (dob, org), rows in sorted(by_dob_org.items()):
        if len(rows) < 2:
            continue
        rows = sorted(rows, key=lambda r: r["player_key"])
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                # A namespaced interim key (slug__sa<id> from CollegeSavant,
                # slug__noid from an unresolved ingest) sharing its own base
                # slug is a DELIBERATE split with its own linkage mechanism
                # (draft promotion / id resolution), not a spelling split.
                # Flagging those buried the real findings 246-to-6 on the
                # first run of this detector.
                if (a["player_key"].split("__")[0]
                        == b["player_key"].split("__")[0]):
                    continue
                if not _variant_names_match(a.get("player_name"),
                                            b.get("player_name")):
                    continue
                dates = [d for d in (a.get("last_snapshot_date"),
                                     b.get("last_snapshot_date")) if d]
                if not dates or max(dates) < cutoff:
                    continue
                ka, kb = a["player_key"], b["player_key"]
                # The bound MLBAM ids are the decisive disambiguator when
                # both exist: two DIFFERENT ids is two humans (the King
                # twins share a birthday, an org and a surname), and the
                # SAME id on both keys is one human beyond argument
                # (zach_root / zachary_root both bind 702539).
                ma, mb = _as_int(a.get("mlbam_id")), _as_int(b.get("mlbam_id"))
                if ma is not None and mb is not None and ma != mb:
                    status = "two_humans_distinct_ids"
                elif ma is not None and ma == mb:
                    status = "one_human_shared_id"
                else:
                    status = "unadjudicated"
                resolved = (alias_to.get(ka) == kb or alias_to.get(kb) == ka)
                # The staler key is the one a repair would fold away; name it
                # as the row's player_key so the critical list points at it.
                stale = min(
                    (a, b),
                    key=lambda r: r.get("last_snapshot_date") or "")
                out.append({
                    "pair": [ka, kb],
                    "player_key": stale["player_key"],
                    "names": [a.get("player_name"), b.get("player_name")],
                    "birth_date": dob,
                    "org": org,
                    "mlbam_ids": [ma, mb],
                    "status": status,
                    "last_snapshot_dates": [a.get("last_snapshot_date"),
                                            b.get("last_snapshot_date")],
                    "resolved_by_alias": resolved,
                })
    return out


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# C1 - one slug, two or more real humans, not two or more board keys
# ---------------------------------------------------------------------------

def find_unsplit_collisions(roster_rows, board_by_key=None) -> list[dict]:
    """Group StatsAPI roster rows by name slug and report every slug that
    covers more than one distinct mlbam id.

    `roster_rows` is a flat iterable of dicts with at least mlbam_id and
    fullName; player_key (the run_monthly roster join result), position,
    org, level and age are used for the report body when present.

    status is one of:
      shared_key   two or more distinct mlbam ids carry the SAME non-null
                   player_key - a hard merge, both humans on one record
      unattributed the slug HAS a board record but that record's mlbam_id
                   is null while two or more real ids exist (Jesus Flores)
      shadowed     one id owns the key, the other humans are untracked -
                   correct today, uningestible forever (the slug is taken)
      split        every tracked id has its own distinct player_key
      untracked    no id on this slug reaches the board at all
    """
    board_by_key = board_by_key or {}
    by_slug: dict[str, list[dict]] = defaultdict(list)
    for row in roster_rows:
        mid = _as_int(row.get("mlbam_id"))
        name = row.get("fullName") or row.get("player_name") or ""
        if mid is None or not name:
            continue
        by_slug[normalize_name(name)].append({
            "mlbam_id": mid,
            "name": name,
            "player_key": row.get("player_key"),
            "position": row.get("position"),
            "org": row.get("org"),
            "level": row.get("level"),
            "age": row.get("age"),
        })

    out: list[dict] = []
    for slug, rows in sorted(by_slug.items()):
        by_id: dict[int, dict] = {}
        for r in rows:
            by_id.setdefault(r["mlbam_id"], r)
        if len(by_id) < 2:
            continue
        members = sorted(by_id.values(), key=lambda r: r["mlbam_id"])
        keys = [r["player_key"] for r in members if r["player_key"]]
        distinct_keys = set(keys)
        board_row = board_by_key.get(slug)

        # The board record that OWNS the bare slug, if any. This is the one
        # a reader sees when two humans have been fused: it keeps the plain
        # key while the roster join hands the key to whichever id it
        # resolved. Prefer it over a discriminated key for reporting.
        if board_row is None and len(distinct_keys) == 1:
            board_row = board_by_key.get(next(iter(distinct_keys)))

        # An id-less board record standing on a slug that two or more real
        # humans answer to is the Jesus Flores signature: we are serving a
        # record we cannot attribute to either of them.
        unattributed = (board_row is not None
                        and board_row.get("mlbam_id") is None)

        if len(keys) > len(distinct_keys):
            status = "shared_key"
        elif unattributed:
            status = "unattributed"
        elif not distinct_keys and board_row is None:
            status = "untracked"
        elif len(distinct_keys) == len(by_id):
            status = "split"
        else:
            status = "shadowed"

        out.append({
            "check": "C1",
            "slug": slug,
            "status": status,
            "n_humans": len(by_id),
            "board_key": (board_row or {}).get("player_key"),
            "board_scope": (board_row or {}).get("scope"),
            "board_mlbam_id": (board_row or {}).get("mlbam_id"),
            "board_position": (board_row or {}).get("position"),
            "board_level": (board_row or {}).get("current_level"),
            "board_rank": (board_row or {}).get("overall_rank"),
            "members": members,
        })
    return out


# ---------------------------------------------------------------------------
# C2 - one player_key, two or more mlbam ids in player_photos
# ---------------------------------------------------------------------------

def find_double_bound_keys(photo_bindings) -> list[dict]:
    """`photo_bindings` is the {mlbam_id: player_key} player_photos map.

    player_photos has its uniqueness constraint on mlbam_id ALONE (see the
    two ON CONFLICT(mlbam_id) writers), so nothing stops two ids pointing
    at one key. Every hit here is two humans fused into one record."""
    by_key: dict[str, set[int]] = defaultdict(set)
    for mid, key in (photo_bindings or {}).items():
        mid_i = _as_int(mid)
        if mid_i is None or not key:
            continue
        by_key[key].add(mid_i)
    return [
        {"check": "C2", "player_key": key, "mlbam_ids": sorted(ids)}
        for key, ids in sorted(by_key.items()) if len(ids) > 1
    ]


# ---------------------------------------------------------------------------
# C3 - active board row with no id but an assigned level
# ---------------------------------------------------------------------------

def find_unresolved_active(board_rows) -> list[dict]:
    """A row with mlbam_id null AND current_level set is a real player who
    has been PLACED on a club but never identified.

    Rows with no level are 2026 draftees / IFA signings that legitimately
    have no assignment yet; they are counted separately and are not a
    defect on their own. Only the ACTIVE board is checked: graduated and
    inactive rows are 30-70 percent id-less by construction (pre-2015
    cohorts predate the id map) and are not a live product surface. A row
    with no `scope` tag is treated as active so synthetic fixtures work."""
    out: list[dict] = []
    for p in board_rows:
        if p.get("scope", "active") != "active":
            continue
        if p.get("mlbam_id") is not None:
            continue
        if not p.get("current_level"):
            continue
        out.append({
            "check": "C3",
            "player_key": p.get("player_key"),
            "position": p.get("position"),
            "org": p.get("org"),
            "current_level": p.get("current_level"),
            "overall_rank": p.get("overall_rank"),
            "birth_date": p.get("birth_date"),
        })
    return sorted(out, key=lambda r: (r["overall_rank"] is None,
                                      r["overall_rank"] or 0))


# ---------------------------------------------------------------------------
# C4 - scored side vs actual fielding log
# ---------------------------------------------------------------------------

def find_side_conflicts(board_rows, positions_played,
                        min_games: int = MIN_FIELDING_GAMES) -> list[dict]:
    """The board says one side of the ball, the game log says the other.

    `positions_played` is the {player_key: {"by_pos": {POS: {"g": n}}}} map.
    Fires only when the claimed side has ZERO recorded games and the other
    side has at least `min_games`, so a position change or a two-way player
    cannot trip it."""
    out: list[dict] = []
    for p in board_rows:
        key = p.get("player_key")
        claimed = position_kind(p.get("position"))
        entry = (positions_played or {}).get(key)
        if not key or claimed is None or not entry:
            continue
        games = {"P": 0, "H": 0}
        for pos, stat in (entry.get("by_pos") or {}).items():
            kind = position_kind(pos)
            if kind is None:
                continue
            games[kind] += int((stat or {}).get("g") or 0)
        other = "H" if claimed == "P" else "P"
        if games[claimed] == 0 and games[other] >= min_games:
            out.append({
                "check": "C4",
                "player_key": key,
                "board_position": p.get("position"),
                "claimed_side": claimed,
                "fielded_side": other,
                "fielded_games": games[other],
                "mlbam_id": p.get("mlbam_id"),
                "scope": p.get("scope", "active"),
                "overall_rank": p.get("overall_rank"),
            })
    return sorted(out, key=lambda r: -r["fielded_games"])


# ---------------------------------------------------------------------------
# C5 - board birth_date vs the roster age of the bound id
# ---------------------------------------------------------------------------

def find_birthdate_conflicts(board_rows, roster_rows, as_of=None,
                             tolerance=AGE_TOLERANCE_YEARS) -> list[dict]:
    """Cross-check the birth_date a record CARRIES against the age StatsAPI
    reports for the mlbam id that record is BOUND to.

    This is the check that proves a binding is wrong rather than merely
    missing: if the two disagree by more than a year, the biography and the
    id belong to different humans."""
    as_of = as_of or datetime.date.today()
    ages_by_id: dict[int, float] = {}
    for row in roster_rows:
        mid = _as_int(row.get("mlbam_id"))
        age = row.get("age")
        if mid is None or age is None:
            continue
        try:
            ages_by_id.setdefault(mid, float(age))
        except (TypeError, ValueError):
            continue

    out: list[dict] = []
    for p in board_rows:
        mid = _as_int(p.get("mlbam_id"))
        born = p.get("birth_date")
        if mid is None or not born or mid not in ages_by_id:
            continue
        try:
            bd = datetime.date.fromisoformat(str(born)[:10])
        except ValueError:
            continue
        implied = (as_of - bd).days / 365.25
        roster_age = ages_by_id[mid]
        if abs(implied - roster_age) > tolerance:
            out.append({
                "check": "C5",
                "player_key": p.get("player_key"),
                "mlbam_id": mid,
                "birth_date": born,
                "age_from_birth_date": round(implied, 2),
                "roster_age": round(roster_age, 2),
                "delta_years": round(implied - roster_age, 2),
            })
    return sorted(out, key=lambda r: -abs(r["delta_years"]))


# ---------------------------------------------------------------------------
# C6 - snapshot org vs displayed org on an id-less record
# ---------------------------------------------------------------------------

def find_org_splits(board_rows, snapshot_orgs) -> list[dict]:
    """The Frankenstein seam, stated exactly.

    A merged record is assembled from two different humans' rows: the
    SNAPSHOT that minted it (position and org come from there, via the
    consensus timeseries) and the ROSTER row the run_monthly join resolved
    (org and level come from there). When those two are different humans on
    different clubs, the built card shows a player whose own snapshot says
    one organization and whose displayed org says another.

    An org mismatch on its own is ordinary trade/promotion freshness: over
    the 4467 active rows with a snapshot org, 1572 disagree. Requiring
    mlbam_id to be NULL as well cuts that to 2, both of them independently
    confirmed merged records. So this check is only run on id-less rows,
    and that restriction is the whole point of it."""
    out: list[dict] = []
    for p in board_rows:
        if p.get("scope", "active") != "active":
            continue
        if p.get("mlbam_id") is not None:
            continue
        key = p.get("player_key")
        snap = (snapshot_orgs or {}).get(key)
        built = p.get("org")
        if not key or not snap or not built or snap == built:
            continue
        out.append({
            "check": "C6",
            "player_key": key,
            "snapshot_org": snap,
            "displayed_org": built,
            "current_level": p.get("current_level"),
            "position": p.get("position"),
        })
    return sorted(out, key=lambda r: r["player_key"])


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

_C1_CRITICAL = frozenset({"shared_key", "unattributed"})


def audit(board_rows, roster_rows, photo_bindings=None,
          positions_played=None, snapshot_orgs=None, as_of=None,
          players_rows=None, aliases=None) -> dict:
    """Run all seven detectors and return the report body. `players_rows`
    and `aliases` are optional so a caller exercising only C1-C6 (every
    pre-2026-08-10 test) is byte-identical; C7 runs when they are given."""
    board_rows = list(board_rows or [])
    roster_rows = list(roster_rows or [])
    # One key can appear in more than one slice (a graduate still carries an
    # active-board row during the changeover). Active wins the lookup.
    board_by_key: dict[str, dict] = {}
    for p in board_rows:
        key = p.get("player_key")
        if not key:
            continue
        prior = board_by_key.get(key)
        if prior is None or (prior.get("scope") != "active"
                             and p.get("scope", "active") == "active"):
            board_by_key[key] = p

    c1 = find_unsplit_collisions(roster_rows, board_by_key)
    c2 = find_double_bound_keys(photo_bindings)
    c3 = find_unresolved_active(board_rows)
    c4 = find_side_conflicts(board_rows, positions_played)
    c5 = find_birthdate_conflicts(board_rows, roster_rows, as_of=as_of)
    c6 = find_org_splits(board_rows, snapshot_orgs)
    c7 = find_name_variant_splits(players_rows, aliases=aliases,
                                  as_of=as_of) if players_rows else []
    # Open = still needs a human: not routed by an alias, and not proven to
    # be two distinct humans by two distinct bound MLBAM ids.
    c7_open = [r for r in c7 if not r["resolved_by_alias"]
               and r["status"] != "two_humans_distinct_ids"]

    c1_critical = [r for r in c1 if r["status"] in _C1_CRITICAL]
    c1_warning = [r for r in c1 if r["status"] == "shadowed"]

    critical_keys: set[str] = set()
    for row in c1_critical:
        if row.get("board_key"):
            critical_keys.add(row["board_key"])
    for rows in (c2, c3, c4, c5, c6, c7_open):
        critical_keys.update(r["player_key"] for r in rows if r.get("player_key"))

    # The composite fingerprint: an ACTIVE record that is simultaneously
    # unidentified, placed on a club, and fielding on the other side of the
    # ball from the position it is published under. Every single field on
    # such a card is individually plausible and collectively impossible.
    frankenstein = sorted(
        {r["player_key"] for r in c3 if r.get("player_key")}
        & {r["player_key"] for r in c4
           if r.get("player_key") and r.get("scope", "active") == "active"})

    active_rows = [p for p in board_rows if p.get("scope", "active") == "active"]
    null_id_no_level = sum(
        1 for p in active_rows
        if p.get("mlbam_id") is None and not p.get("current_level"))

    # The ACTIVE subset is the live product surface (prospect board, trade
    # machine, farm pages). Graduated and inactive rows are still published
    # but are historical; they get their own count so a regression on the
    # live board cannot hide inside the larger number.
    active_keys = {p["player_key"] for p in active_rows if p.get("player_key")}
    critical_active = sorted(k for k in critical_keys if k in active_keys)

    return {
        "generated_at": datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {
            "board_rows": len(board_rows),
            "active_board_rows": len(active_rows),
            "roster_rows": len(roster_rows),
            "colliding_slugs": len(c1),
            "critical_player_keys": len(critical_keys),
            "critical_active_player_keys": len(critical_active),
            "c1_shared_key": sum(1 for r in c1 if r["status"] == "shared_key"),
            "c1_unattributed": sum(1 for r in c1 if r["status"] == "unattributed"),
            "c1_shadowed": len(c1_warning),
            "c1_split": sum(1 for r in c1 if r["status"] == "split"),
            "c1_untracked": sum(1 for r in c1 if r["status"] == "untracked"),
            "c2_double_bound": len(c2),
            "c3_unresolved_active": len(c3),
            "c4_side_conflicts": len(c4),
            "c5_birthdate_conflicts": len(c5),
            "c6_org_splits": len(c6),
            "c7_name_variant_splits": len(c7),
            "c7_name_variant_open": len(c7_open),
            "frankenstein_records": len(frankenstein),
            "unassigned_null_id_rows": null_id_no_level,
        },
        "critical_player_keys": sorted(critical_keys),
        "critical_active_player_keys": critical_active,
        "frankenstein_records": frankenstein,
        "unsplit_collisions": c1_critical,
        "shadowed_slugs": [
            {"slug": r["slug"], "board_key": r["board_key"],
             "n_humans": r["n_humans"],
             "mlbam_ids": [m["mlbam_id"] for m in r["members"]]}
            for r in c1_warning
        ],
        "double_bound_keys": c2,
        "unresolved_active": c3,
        "side_conflicts": c4,
        "birthdate_conflicts": c5,
        "org_splits": c6,
        "name_variant_splits": c7,
    }


# ---------------------------------------------------------------------------
# Real-artifact loaders + build()
# ---------------------------------------------------------------------------

def _load_json(name):
    try:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


_BOARD_SLICES = (
    ("active", "timeseries.json"),
    ("graduated", "debuts.json"),
    ("inactive", "inactive.json"),
)


def _slice_rows(doc) -> list[dict]:
    if doc is None:
        return []
    if isinstance(doc, list):
        return doc
    return doc.get("players") or doc.get("debuts") or []


def load_board_rows(doc=None) -> list[dict]:
    """Every tracked row, each tagged with its `scope`.

    The graduated and inactive slices matter here because the two most
    valuable merged records the audit found (michael_perez, luis_garcia)
    are NOT on the active board - they still get scored and published, and
    their slugs are still taken on the current StatsAPI rosters."""
    if doc is not None:
        return [{**r, "scope": r.get("scope", "active")} for r in _slice_rows(doc)]
    rows: list[dict] = []
    for scope, name in _BOARD_SLICES:
        for row in _slice_rows(_load_json(name)):
            if isinstance(row, dict):
                rows.append({**row, "scope": scope})
    return rows


def load_roster_rows(doc=None) -> list[dict]:
    """Flatten data/rosters_by_org.json into rows carrying org + level."""
    doc = doc if doc is not None else _load_json("rosters_by_org.json")
    rows: list[dict] = []
    for org, levels in (doc or {}).items():
        if not isinstance(levels, dict):
            continue
        for level, players in levels.items():
            for row in players or []:
                if isinstance(row, dict):
                    rows.append({**row, "org": org, "level": level})
    return rows


def load_positions_played(doc=None) -> dict:
    doc = doc if doc is not None else _load_json("positions_played.json")
    if not isinstance(doc, dict):
        return {}
    return doc.get("players") or doc


def _query_db(sql: str) -> list:
    """Run a SELECT against prospects.db opened READ-ONLY.

    This module never writes to prospects.db, so no backup is ever needed
    to run it. Returns [] when the DB is absent or the table is missing."""
    import sqlite3
    db = _HERE / "prospects.db"
    if not db.exists():
        return []
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:  # pragma: no cover
        log.debug("identity_audit: prospects.db unavailable: %s", exc)
        return []
    try:
        return con.execute(sql).fetchall()
    except sqlite3.Error as exc:  # pragma: no cover
        log.debug("identity_audit: query failed (%s): %s", sql, exc)
        return []
    finally:
        con.close()


def load_photo_bindings() -> dict:
    """{mlbam_id: player_key} from player_photos, the canonical binding."""
    rows = _query_db(
        "SELECT mlbam_id, player_key FROM player_photos "
        "WHERE mlbam_id IS NOT NULL AND player_key IS NOT NULL")
    out = {}
    for mid, key in rows:
        mid_i = _as_int(mid)
        if mid_i is not None:
            out[mid_i] = key
    return out


def load_snapshot_orgs() -> dict:
    """{player_key: org} from the LATEST dated snapshot carrying an org."""
    rows = _query_db(
        "SELECT player_key, org FROM snapshots "
        "WHERE org IS NOT NULL AND player_key IS NOT NULL "
        "ORDER BY snapshot_date")
    return {key: org for key, org in rows}


def load_players_rows() -> list[dict]:
    """One row per players-table key, carrying the identity fields C7 keys on
    plus the key's newest snapshot date (its activity witness)."""
    rows = _query_db(
        "SELECT p.player_key, p.player_name, p.org, p.birth_date, "
        "       (SELECT MAX(s.snapshot_date) FROM snapshots s "
        "        WHERE s.player_key = p.player_key), "
        "       (SELECT ph.mlbam_id FROM player_photos ph "
        "        WHERE ph.player_key = p.player_key) "
        "FROM players p")
    return [{"player_key": k, "player_name": n, "org": o, "birth_date": b,
             "last_snapshot_date": d, "mlbam_id": m}
            for k, n, o, b, d, m in rows]


def build(write: bool = True, path: Path | None = None) -> dict:
    """Load the real artifacts, run the audit, write the report."""
    try:
        from consensus import PLAYER_KEY_ALIASES as _aliases
    except Exception:  # pragma: no cover - standalone use without consensus
        _aliases = {}
    report = audit(
        board_rows=load_board_rows(),
        roster_rows=load_roster_rows(),
        photo_bindings=load_photo_bindings(),
        positions_played=load_positions_played(),
        snapshot_orgs=load_snapshot_orgs(),
        players_rows=load_players_rows(),
        aliases=_aliases,
    )
    if write:
        target = Path(path) if path else REPORT_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=1, ensure_ascii=False),
                          encoding="utf-8")
        log.info("identity_audit: wrote %s (%d critical keys)", target,
                 report["summary"]["critical_player_keys"])
    return report


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    report = build()
    print(json.dumps(report["summary"], indent=1))
    for key in report["frankenstein_records"]:
        print("  FRANKENSTEIN", key)
    for key in report["critical_active_player_keys"]:
        print("  CRITICAL(active)", key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
