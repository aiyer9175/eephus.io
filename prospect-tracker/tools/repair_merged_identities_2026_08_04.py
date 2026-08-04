# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""repair_merged_identities_2026_08_04.py - the five merges test_identity_collisions
found on 2026-08-04.

Follows tools/repair_identity_bindings.py's contract exactly: NO player_key is
ever renamed and no key is ever re-mapped. Repairs work by ATTACHING or
UNBINDING ids (and, where a NEWCOMER's own rows are unambiguous, by moving
those rows onto his discriminated key). Every write is guarded by the exact
value it expects to find, so the tool is idempotent and refuses to act on a
row that has drifted since the evidence was taken.

WHAT HAPPENED. At 2026-08-04 17:25:48Z a bulk id-resolution pass wrote 712
player_photos bindings. `stats.bulk_resolve_ids` resolves a key by NAME
against the current-season PlayerIndex, and `_apply_collision_guard` can only
refuse a binding when the key is ALREADY durably bound to a different id.
Three long-inactive prospect records had never been bound to anything, so the
name lookup handed each of them the id of a DIFFERENT, currently-active
player who happens to share the slug. Every keyed write that followed
(players.birth_date, roster_status, acquisitions, player_transactions, and
the fielding census that feeds C4) then landed on the wrong human.

  key                 INCUMBENT (owns the key)          NEWCOMER (bound by mistake)
  anthony_garcia      678803 b.2000-09-05 DR RF         805817 b.2002-03-28 CUB RHP
                      DSL/GCL/Pulaski/FCL/Tampa/          DSL Braves 2022, FCL Braves
                      Hudson Valley Yankees 2018-2023     + Augusta 2024-2025, ATL A
                      = the FanGraphs RF/NYY snapshots    = 32 career games, all at P
                      2019-02-13 .. 2023-02-23
  edgardo_rodriguez   678614 b.2000-11-29 VEN C         838012 b.2009-07-06 VEN RHP
                      DSL Rays 2 + GCL Rays 2018-2019,    DSL Mets Blue 2026, 11 games
                      FCL/Palm Beach Cardinals 2021-2022  all at P, age 17.1
                      = the C/TBR 2019 then C/STL
                      2020-2021 snapshots, in order
  luis_tejeda         683656 b.2002-08-26 DR SS/3B      802240 b.2004-12-13 DR RHP
                      DSL Pirates 1 2019, FCL Pirates     DSL Colorado 2022-2023, ACL
                      Black 2021, FCL Pirates 2022-2023   Rockies 2024-2025, COL CPX
                      = the 3B/PIT snapshots 2020-2021    = 55 career games, all at P

Each newcomer is arithmetically impossible as the incumbent: 805817 was 13.8
when the key's 2016 Pipeline snapshot was published and had no pro game before
2022; 838012 was 9.6 at the key's 2019 Rays snapshot; 802240 was 15.2 at the
key's 2020 Pirates snapshot and did not sign until 2022. The incumbents were
recovered from the MiLB registry (/api/v1/sports/{11,12,13,14,16,5442}/players)
for the seasons the snapshots were published in, and each one's affiliate
history reproduces the key's snapshot lineage club for club.

  jose_rodriguez      the ACTIVE board row, overall_rank 3143. Bound to 692064
                      (b.2001-07-18, Mexico, LAD RHP, Oklahoma City AAA) since
                      2026-07-06, and the record carries his birth_date, his
                      level and his 139-game all-pitching census. But its
                      POSITION and ORG came from the newest snapshot on the
                      key, which belongs to a different human, so the card is
                      published as an SS while its fielding log is a pitcher's
                      (C4, claimed_side H vs fielded_side P over 139 games).
                      Two FanGraphs player ids sit on this one key and settle
                      it outright:
                        sa3015437  age 25.01  sign_year 2019  J2  LAD  $15,000
                                   from Mexico   level AAA   -> 692064
                        sa3075073  age 17.54  sign_year 2026  Intl15  MIL
                                   $1,500,000 from Venezuela  level DSL
                                   -> 836624
                      836624 is the NEWCOMER (first snapshot 2026-01-15) and he
                      ALREADY HAS his discriminated key, jose_rodriguez_836624,
                      bound in player_photos on 2026-07-23 and carrying its own
                      players row (SS / MIL / b.2009-01-19). His three snapshots
                      are the only rows moved. With them gone the key's newest
                      snapshot is 692064's own SIRP/LAD row, which agrees with
                      the census, and the incumbent is not re-keyed.

  jack_natili         NOT REPAIRED, and not this class. See the KNOWN_MERGED
                      note added to test_identity_collisions.py: it is ONE human
                      on TWO keys, the inverse case, and the fix is a key merge
                      that needs a scrapers._CANONICAL_KEYS entry.

WHY THE CACHE IS PART OF THE REPAIR. For a key whose id is already in
.cache/mlbam_ids.json, bulk_resolve_ids applies the collision guard ONLY when
the pair is an allowlisted scrapers._SPLIT_KEYS split; otherwise the cached id
is returned as-is and becomes the board row's mlbam_id. So leaving
mlbam_ids.json pointing at the newcomer would silently re-merge the record on
the very next export and the DB repair would never be visible. The cache is
re-pointed at the incumbent under the same value guards. After that the
durable binding does the work on its own: with the plain key bound to the
incumbent, `_apply_collision_guard` case 2 forks any future name resolution of
the newcomer to "{slug}_{mlbam_id}" automatically and permanently.

Six groups:

  R1 attach_incumbent  insert the incumbent's player_photos binding on the
                       plain key (the key he has always owned).
  R2 split_newcomer    re-point the newcomer's EXISTING player_photos row from
                       the plain key to "{slug}_{mlbam_id}", the same
                       discriminated key mlbam_ingest._collision_safe_key and
                       stats._apply_collision_guard mint automatically. Nothing
                       is deleted, and no key is renamed.
  R3 birth_date        the players row carries the NEWCOMER's birth_date;
                       restore the incumbent's, guarded on the exact wrong value.
  R4 move_rows         roster_status / acquisitions / player_transactions were
                       all fetched today FROM THE NEWCOMER'S ID and name him
                       explicitly ("RHP Anthony Garcia", "Atlanta Braves").
                       They move to his discriminated key, guarded by fetched_at
                       plus a sha256 of the payload. No board record is minted
                       for him: like G1 in repair_identity_bindings.py, he is
                       reported, not published.
  R5 jose_rodriguez    move the three newcomer snapshots onto the discriminated
                       key that already exists, and correct the players row of
                       the incumbent (SS/MIL -> SIRP/LAD, is_pitcher 0 -> 1)
                       back to the human the key is bound to.
  R6 id_cache          .cache/mlbam_ids.json re-pointed, per the note above.
                       Gitignored derived cache; every edit value-guarded.

Usage:
    python tools/repair_merged_identities_2026_08_04.py              # dry run
    python tools/repair_merged_identities_2026_08_04.py --apply      # write
    python tools/repair_merged_identities_2026_08_04.py --apply --no-backup
    python tools/repair_merged_identities_2026_08_04.py --db PATH
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
DEFAULT_DB = _HERE.parent / "prospects.db"
ID_CACHE = _HERE.parent / ".cache" / "mlbam_ids.json"

# ---------------------------------------------------------------------------
# The three legacy records that were bound to an active same-name stranger.
# `fork` is exactly what _collision_safe_key / _apply_collision_guard would
# mint for this (slug, newcomer id) pair, so the repair and the automatic
# guard agree on where the newcomer lives.
# ---------------------------------------------------------------------------
SPLITS: list[dict] = [
    dict(
        key="anthony_garcia",
        inc_id=678803, inc_birth="2000-09-05",
        inc_note="Anthony Garcia, DR RF. DSL Yankees + GCL Yankees West + "
                 "Pulaski 2018, Pulaski 2019, FCL Yankees + Tampa 2021, Tampa "
                 "2022, Hudson Valley 2023. Reproduces the RF/NYY FanGraphs "
                 "snapshots 2019-02-13 (rank 17) through 2023-02-23 (rank 41); "
                 "last pro game 2023, and the board record is inactive.",
        new_id=805817, new_birth="2002-03-28",
        new_note="Anthony Garcia, Cuban RHP. DSL Braves 2022, FCL Braves + "
                 "Augusta 2024, Augusta 2025; 32 career games, every one at P. "
                 "Age 13.8 at the key's 2016 Pipeline snapshot and no pro game "
                 "before 2022.",
        fork="anthony_garcia_805817",
        acq=dict(method="international_fa", year=2022, team_name="Atlanta Braves",
                 fetched_at="2026-08-04 17:26:11"),
        rst=dict(fetched_at="2026-08-04 17:58:54", sha="566cfca06680d08f"),
        ptx=dict(fetched_at="2026-08-04 17:58:49", sha="f7247c2b2990a690"),
    ),
    dict(
        key="edgardo_rodriguez",
        inc_id=678614, inc_birth="2000-11-29",
        inc_note="Edgardo Rodriguez, VEN C. DSL Rays 2 2018, GCL Rays 2019, "
                 "FCL Cardinals + Palm Beach 2021, FCL Cardinals 2022. "
                 "Reproduces the key's snapshot lineage in order: C/TBR "
                 "2019-02-13 and 2019-07-31, then C/STL 2020-02-13 through "
                 "2021-07-30. Last pro game 2022.",
        new_id=838012, new_birth="2009-07-06",
        new_note="Edgardo Rodriguez, VEN RHP, age 17.1. DSL Mets Blue 2026, "
                 "11 games, all at P. He was 9.6 years old when this key's "
                 "first snapshot was published.",
        fork="edgardo_rodriguez_838012",
        acq=dict(method="international_fa", year=2026, team_name="New York Mets",
                 fetched_at="2026-08-04 17:26:11"),
        rst=dict(fetched_at="2026-08-04 17:58:54", sha="e3299a869deb5301"),
        ptx=dict(fetched_at="2026-08-04 17:58:49", sha="77d8373e80db9621"),
    ),
    dict(
        key="luis_tejeda",
        inc_id=683656, inc_birth="2002-08-26",
        inc_note="Luis Tejeda, DR SS/3B. DSL Pirates 1 2019 (40 g at SS), FCL "
                 "Pirates Black 2021 (35 g at SS), FCL Pirates 2022-2023 "
                 "(mostly 3B). Reproduces the 3B/PIT FanGraphs snapshots "
                 "2020-02-13 (rank 36) through 2021-07-30 (rank 57). Last pro "
                 "game 2023. Three other Luis Tejedas exist in the registry "
                 "(686509 P b.1998 MIA, 692549 P b.2001 ARI, 805072 OF "
                 "b.2005 KCR); none is a Pirate and none is an infielder on a "
                 "2020 list.",
        new_id=802240, new_birth="2004-12-13",
        new_note="Luis Tejeda, DR RHP. DSL Colorado 2022-2023, ACL Rockies "
                 "2024-2025; 55 career games, all at P. Age 15.2 at the key's "
                 "first snapshot and unsigned until 2022-01-21.",
        fork="luis_tejeda_802240",
        acq=dict(method="international_fa", year=2022, team_name="Colorado Rockies",
                 fetched_at="2026-08-04 17:26:11"),
        rst=dict(fetched_at="2026-08-04 17:58:54", sha="0844f6f4c69c2bbc"),
        ptx=dict(fetched_at="2026-08-04 17:58:49", sha="9df7353c60efcc86"),
    ),
]

# ---------------------------------------------------------------------------
# R5 - jose_rodriguez. The newcomer's own snapshots, moved onto the
# discriminated key that mlbam_ingest already minted and bound for him.
# (snapshot_id, snapshot_date, source, position, org, fv)
# ---------------------------------------------------------------------------
JR_KEY = "jose_rodriguez"
JR_FORK = "jose_rodriguez_836624"
JR_INCUMBENT = 692064
JR_NEWCOMER = 836624
JR_SNAPSHOTS = [
    (2821921, "2026-01-15", "mlb_pipeline_international", "SS", "MIL", 45.0),
    (4330087, "2026-08-02", "fangraphs", "SS", "MIL", 40.0),
    (4304291, "2026-08-04", "mlb_pipeline", "SS", "MIL", 40.0),
]
# The plain key's players row, restored to the human it is bound to. pos_new is
# taken from the SNAPSHOT LINEAGE OF THE BOUND HUMAN (FanGraphs 2026-07-23
# SIRP/LAD), not from StatsAPI primaryPosition.
JR_PLAYERS = dict(birth="2001-07-18", pos_now="SS", pos_new="SIRP",
                  org_now="MIL", org_new="LAD", isp_now=0, isp_new=1)

# ---------------------------------------------------------------------------
# R6 - the resolver cache. (key, expected_now, new_value)
# `expected_now` of None means the key must be ABSENT.
# ---------------------------------------------------------------------------
CACHE_FIX: list[tuple[str, object, int]] = [
    ("anthony_garcia", 805817, 678803),
    ("edgardo_rodriguez", 838012, 678614),
    ("luis_tejeda", 802240, 683656),
    # Pre-seed the discriminated key so the very next export resolves it
    # without a round trip. Mirrors the durable player_photos binding exactly.
    (JR_FORK, None, JR_NEWCOMER),
]

# ---------------------------------------------------------------------------
# Reported, never written.
# ---------------------------------------------------------------------------
REPORT_ONLY = [
    ("jack_natili",
     "NOT a two-humans-one-key merge: it is ONE human on TWO ACTIVE board "
     "keys. mlbam 814385 (Jack Natili, b.2005-03-10, USA, C, draftYear 2026, "
     "ACL Rockies) is bound to 'jackson_natili', which is published at "
     "overall_rank 160 with the FanGraphs C/COL rows 2026-07-23 and 2026-08-02 "
     "(rank 8, FV 45). 'jack_natili' is published at overall_rank 332 with the "
     "2026-08-04 draft_signing row (C/COL, FV 45) and no id, which is what "
     "trips C3. Same birth_date, same position, same org, same FV on both. The "
     "repair is a KEY MERGE (the michael_oliveto class), which needs a "
     "scrapers._CANONICAL_KEYS entry to stop the next FanGraphs drop from "
     "re-fracturing him, and scrapers.py is outside this lane. The id-side "
     "guards added 2026-08-04 (storage.bind_player_ids and "
     "draft_promotion) deliberately REFUSE to move 814385 onto jack_natili and "
     "are left untouched. Allowlisted in test_identity_collisions.py with this "
     "evidence -> OWNER DECISION."),
    ("jose_rodriguez (history)",
     "Two further humans' snapshots remain on the plain key and are NOT moved, "
     "because neither has a player_key of his own and minting one is a re-key: "
     "679563 (Jose Rodriguez, b.2001-05-13 DR SS, CHW system then PHI AA, MLB "
     "debut 2023-06-20) owns the SS/CHW FanGraphs rows 2020-02-13 through "
     "2023-08-01 and the '2B/SS Office of the Commissioner' Pipeline rows "
     "2021-2024; 800412 (Jose Rodriguez, b.2005-06-10 DR OF, MIN, Fort Myers) "
     "owns the two 'OF/MIN' Pipeline rows 2023-01-22 and 2024-01-22, whose "
     "writeup names his $650,000 2022 international bonus. They do not trip a "
     "detector (only the newest snapshot reaches the card) -> OWNER DECISION."),
    ("anthony_garcia (history)",
     "The 2016-01-22 Pipeline row (OF / Office of the Commissioner, rank 27) "
     "is a THIRD human: the incumbent 678803 was 15.4 that day and had not "
     "signed. Left in place; it does not trip a detector -> OWNER DECISION."),
    ("the three newcomers",
     "805817, 838012 and 802240 end up bound to their discriminated keys with "
     "no players row and no board record. That is deliberate and matches G1 in "
     "repair_identity_bindings.py: the second human is reported, not minted. "
     "mlbam_ingest will ingest each under the same forked key if he ever "
     "clears the performance threshold."),
]


def _p(action: str, *detail):
    print(f"  [{action}] " + " ".join(str(d) for d in detail))


def _one(con, sql, params=()):
    return con.execute(sql, params).fetchone()


def _sha16(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _backup(db_path: Path) -> None:
    stamp = time.strftime("%Y%m%dT%H%M%S")
    backup = db_path.with_name(f"{db_path.stem}.backup-{stamp}.db")
    print(f"\n-- backup --\n  {db_path} -> {backup}")
    # sqlite's online backup API, not a file copy: prospects.db runs in WAL
    # mode, so copying the main file alone can miss committed pages still
    # sitting in the -wal.
    t0 = time.monotonic()
    src = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(backup)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    print(f"  backup complete: {backup} "
          f"({backup.stat().st_size / 1e9:.3f} GB, {time.monotonic() - t0:.1f}s)")


def repair(db_path: Path, apply: bool, do_backup: bool) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== repair_merged_identities_2026_08_04 [{mode}] db={db_path} ===")
    if not db_path.exists():
        print(f"FATAL: db not found: {db_path}")
        return 2

    if apply and do_backup:
        _backup(db_path)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    changes = 0
    skipped: list[str] = []

    # ------------------------------------------------------------------ R1/R2
    print("\n-- R1/R2: attach the incumbent, split the newcomer onto his own key --")
    for s in SPLITS:
        key, fork = s["key"], s["fork"]
        pr = _one(con, "SELECT birth_date, position, org FROM players "
                       "WHERE player_key = ?", (key,))
        if pr is None:
            skipped.append(f"R1 {key}: no players row - NOT touched")
            continue
        new_row = _one(con, "SELECT player_key FROM player_photos WHERE mlbam_id = ?",
                       (s["new_id"],))
        inc_row = _one(con, "SELECT player_key FROM player_photos WHERE mlbam_id = ?",
                       (s["inc_id"],))

        # R2 first: the plain key may hold only ONE id at a time (player_photos
        # constrains uniqueness on mlbam_id alone, which is what lets two ids
        # fuse onto one key; C2 is a hard invariant in the gate).
        if new_row is None:
            skipped.append(f"R2 {key}: no player_photos row for newcomer "
                           f"{s['new_id']} - NOT touched")
        elif new_row["player_key"] == fork:
            _p("ok", f"{key}: newcomer {s['new_id']} already on {fork!r}")
        elif new_row["player_key"] != key:
            skipped.append(f"R2 {key}: newcomer {s['new_id']} is bound to "
                           f"{new_row['player_key']!r}, expected {key!r} - NOT touched")
        else:
            _p("split", f"player_photos[{s['new_id']}].player_key {key!r} -> "
                        f"{fork!r}  ({s['new_note']})")
            if apply:
                con.execute("UPDATE player_photos SET player_key = ? WHERE mlbam_id = ?",
                            (fork, s["new_id"]))
            changes += 1

        # R1: bind the incumbent onto the key he has always owned.
        if inc_row is not None and inc_row["player_key"] == key:
            _p("ok", f"{key}: incumbent {s['inc_id']} already bound")
        elif inc_row is not None:
            skipped.append(f"R1 {key}: incumbent {s['inc_id']} is already bound to "
                           f"{inc_row['player_key']!r} - NOT touched")
        else:
            still = _one(con, "SELECT mlbam_id FROM player_photos WHERE player_key = ?",
                         (key,))
            if still is not None and not apply and still["mlbam_id"] == s["new_id"]:
                still = None      # the dry-run R2 above would have cleared it
            if still is not None:
                skipped.append(f"R1 {key}: key still bound to {still['mlbam_id']} - "
                               "NOT touched (would double-bind)")
                continue
            _p("attach", f"player_photos INSERT {s['inc_id']} -> {key!r}  "
                         f"({s['inc_note']})")
            if apply:
                # headshot_ctx is NOT NULL; 'milb' is the provisional default the
                # snapshot binding path already uses. headshots.resolve_ctx
                # replaces it on the next run.
                con.execute(
                    "INSERT INTO player_photos (mlbam_id, headshot_ctx, player_key, "
                    "checked_at) VALUES (?, 'milb', ?, datetime('now'))",
                    (s["inc_id"], key))
            changes += 1

    # ------------------------------------------------------------------ R3
    print("\n-- R3: players.birth_date carries the NEWCOMER's biography --")
    for s in SPLITS:
        key = s["key"]
        pr = _one(con, "SELECT birth_date FROM players WHERE player_key = ?", (key,))
        if pr is None:
            skipped.append(f"R3 {key}: no players row - NOT touched")
            continue
        if pr["birth_date"] == s["inc_birth"]:
            _p("ok", f"{key}: birth_date already {s['inc_birth']}")
            continue
        if pr["birth_date"] != s["new_birth"]:
            skipped.append(f"R3 {key}: birth_date={pr['birth_date']!r} is neither "
                           f"{s['new_birth']!r} nor {s['inc_birth']!r} - NOT touched")
            continue
        _p("players", f"{key}: birth_date {s['new_birth']!r} (newcomer {s['new_id']}) "
                      f"-> {s['inc_birth']!r} (incumbent {s['inc_id']})")
        if apply:
            con.execute("UPDATE players SET birth_date = ?, "
                        "updated_at = datetime('now') WHERE player_key = ?",
                        (s["inc_birth"], key))
        changes += 1

    # ------------------------------------------------------------------ R4
    print("\n-- R4: move the newcomer's own fetched rows onto his key --")
    for s in SPLITS:
        key, fork = s["key"], s["fork"]
        # acquisitions: guarded on the signing itself, which names the club and
        # the year. Every incumbent signed with a different organization.
        acq = _one(con, "SELECT method, year, team_name, fetched_at FROM acquisitions "
                        "WHERE player_key = ?", (key,))
        clash = _one(con, "SELECT 1 FROM acquisitions WHERE player_key = ?", (fork,))
        g = s["acq"]
        if acq is None:
            _p("ok", f"{key}: no acquisitions row")
        elif clash is not None:
            skipped.append(f"R4 {key}: acquisitions row already exists on {fork!r} "
                           "- NOT merged")
        elif (acq["method"], acq["year"], acq["team_name"], acq["fetched_at"]) != (
                g["method"], g["year"], g["team_name"], g["fetched_at"]):
            skipped.append(f"R4 {key}: acquisitions row is "
                           f"({acq['method']!r}, {acq['year']!r}, {acq['team_name']!r}, "
                           f"{acq['fetched_at']!r}), expected "
                           f"({g['method']!r}, {g['year']!r}, {g['team_name']!r}, "
                           f"{g['fetched_at']!r}) - NOT touched")
        else:
            _p("rekey", f"acquisitions: {key!r} -> {fork!r} "
                        f"({g['team_name']} {g['year']} {g['method']}, the newcomer's "
                        "signing)")
            if apply:
                con.execute("UPDATE acquisitions SET player_key = ? WHERE player_key = ?",
                            (fork, key))
            changes += 1

        for table, guard in (("roster_status", s["rst"]),
                             ("player_transactions", s["ptx"])):
            row = _one(con, f"SELECT payload_json, fetched_at FROM {table} "
                            "WHERE player_key = ?", (key,))
            clash = _one(con, f"SELECT 1 FROM {table} WHERE player_key = ?", (fork,))
            if row is None:
                _p("ok", f"{key}: no {table} row")
                continue
            if clash is not None:
                skipped.append(f"R4 {key}: {table} row already exists on {fork!r} "
                               "- NOT merged")
                continue
            sha = _sha16(row["payload_json"])
            if row["fetched_at"] != guard["fetched_at"] or sha != guard["sha"]:
                skipped.append(f"R4 {key}: {table} row drifted "
                               f"(fetched_at={row['fetched_at']!r} sha={sha}, expected "
                               f"{guard['fetched_at']!r} sha={guard['sha']}) "
                               "- NOT touched")
                continue
            _p("rekey", f"{table}: {key!r} -> {fork!r} (fetched {guard['fetched_at']} "
                        f"from mlbam {s['new_id']}; payload names the newcomer)")
            if apply:
                con.execute(f"UPDATE {table} SET player_key = ? WHERE player_key = ?",
                            (fork, key))
            changes += 1

    # ------------------------------------------------------------------ R5
    print("\n-- R5: jose_rodriguez, split the 2026 MIL newcomer off the key --")
    ph = _one(con, "SELECT player_key FROM player_photos WHERE mlbam_id = ?",
              (JR_INCUMBENT,))
    fk = _one(con, "SELECT player_key FROM player_photos WHERE mlbam_id = ?",
              (JR_NEWCOMER,))
    if ph is None or ph["player_key"] != JR_KEY:
        skipped.append(f"R5 {JR_KEY}: incumbent {JR_INCUMBENT} is bound to "
                       f"{None if ph is None else ph['player_key']!r} - NOTHING touched")
    elif fk is None or fk["player_key"] != JR_FORK:
        skipped.append(f"R5 {JR_KEY}: newcomer {JR_NEWCOMER} is bound to "
                       f"{None if fk is None else fk['player_key']!r}, expected "
                       f"{JR_FORK!r} - NOTHING touched")
    else:
        for sid, sdate, source, pos, org, fv in JR_SNAPSHOTS:
            row = _one(con, "SELECT player_key, snapshot_date, source, position, org, fv "
                            "FROM snapshots WHERE id = ?", (sid,))
            if row is None:
                skipped.append(f"R5 snapshot {sid}: missing - NOT touched")
                continue
            if row["player_key"] == JR_FORK:
                _p("ok", f"snapshot {sid} ({sdate} {source}) already on {JR_FORK!r}")
                continue
            actual = (row["player_key"], row["snapshot_date"], row["source"],
                      row["position"], row["org"], float(row["fv"] or 0))
            if actual != (JR_KEY, sdate, source, pos, org, fv):
                skipped.append(f"R5 snapshot {sid}: row is {actual!r}, expected "
                               f"{(JR_KEY, sdate, source, pos, org, fv)!r} - NOT touched")
                continue
            dupe = _one(con, "SELECT id FROM snapshots WHERE player_key = ? AND "
                             "snapshot_date = ? AND source = ?", (JR_FORK, sdate, source))
            if dupe is not None:
                skipped.append(f"R5 snapshot {sid}: {JR_FORK} already has a {source} "
                               f"row on {sdate} (id {dupe['id']}) - NOT touched")
                continue
            _p("rekey", f"snapshot {sid} {sdate} {source} {pos}/{org} fv={fv}: "
                        f"{JR_KEY!r} -> {JR_FORK!r} (mlbam {JR_NEWCOMER}, "
                        "b.2009-01-19, DSL Brewers Blue, $1.5M Intl15 2026)")
            if apply:
                con.execute("UPDATE snapshots SET player_key = ? WHERE id = ?",
                            (JR_FORK, sid))
            changes += 1

        j = JR_PLAYERS
        pr = _one(con, "SELECT position, org, is_pitcher, birth_date FROM players "
                       "WHERE player_key = ?", (JR_KEY,))
        if pr is None:
            skipped.append(f"R5 {JR_KEY}: no players row - NOT touched")
        elif (pr["position"], pr["org"], int(pr["is_pitcher"] or 0)) == (
                j["pos_new"], j["org_new"], j["isp_new"]):
            _p("ok", f"{JR_KEY}: players row already repaired")
        elif pr["birth_date"] != j["birth"]:
            skipped.append(f"R5 {JR_KEY}: players.birth_date={pr['birth_date']!r} != "
                           f"{j['birth']!r} - NOT touched")
        elif (pr["position"], pr["org"], int(pr["is_pitcher"] or 0)) != (
                j["pos_now"], j["org_now"], j["isp_now"]):
            skipped.append(f"R5 {JR_KEY}: players row is ({pr['position']!r}, "
                           f"{pr['org']!r}, is_pitcher={pr['is_pitcher']!r}), expected "
                           f"({j['pos_now']!r}, {j['org_now']!r}, {j['isp_now']}) "
                           "- NOT touched")
        else:
            _p("players", f"{JR_KEY}: position {j['pos_now']!r} -> {j['pos_new']!r}, "
                          f"org {j['org_now']!r} -> {j['org_new']!r}, is_pitcher "
                          f"{j['isp_now']} -> {j['isp_new']} (the bound human 692064, "
                          "FanGraphs 2026-07-23 SIRP/LAD)")
            if apply:
                con.execute("UPDATE players SET position = ?, org = ?, is_pitcher = ?, "
                            "updated_at = datetime('now') WHERE player_key = ?",
                            (j["pos_new"], j["org_new"], j["isp_new"], JR_KEY))
            changes += 1

    # ------------------------------------------------------------------ R6
    print("\n-- R6: .cache/mlbam_ids.json (gitignored resolver cache) --")
    cache_writes = 0
    if not ID_CACHE.exists():
        _p("skip", f"{ID_CACHE} absent - nothing to re-point")
    else:
        try:
            cache = json.loads(ID_CACHE.read_text(encoding="utf-8"))
        except ValueError as exc:
            cache = None
            skipped.append(f"R6: {ID_CACHE} is not valid JSON ({exc}) - NOT touched")
        if isinstance(cache, dict):
            for ckey, expected, want in CACHE_FIX:
                have = cache.get(ckey, "__absent__")
                if have == want:
                    _p("ok", f"cache[{ckey!r}] already {want}")
                    continue
                matches = (have == "__absent__") if expected is None else (have == expected)
                if not matches:
                    shown = None if have == "__absent__" else have
                    skipped.append(f"R6 cache[{ckey!r}]={shown!r}, expected "
                                   f"{expected!r} - NOT touched")
                    continue
                _p("cache", f"mlbam_ids[{ckey!r}]: {expected!r} -> {want}")
                cache[ckey] = want
                cache_writes += 1
            if cache_writes and apply:
                # byte-for-byte the format stats._save_id_cache writes.
                ID_CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True))
            changes += cache_writes

    # ------------------------------------------------------------------
    print("\n-- reported, NOT touched --")
    for name, note in REPORT_ONLY:
        _p("owner", f"{name}: {note}")

    print("\n-- skipped / drifted --")
    for s in skipped or ["(none)"]:
        _p("skip", s)

    if apply:
        con.commit()
        print(f"\n=== APPLIED: {changes} write(s) committed "
              f"({cache_writes} of them in the id cache) ===")
    else:
        con.rollback()
        print(f"\n=== DRY-RUN: {changes} write(s) planned "
              f"({cache_writes} of them in the id cache); re-run with --apply ===")
    con.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Repair the five merged identities found on 2026-08-04.")
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="explicit no-op; a dry run is the default")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip the pre-apply prospects.db copy")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = ap.parse_args()
    if args.dry_run and args.apply:
        print("FATAL: --dry-run and --apply are mutually exclusive")
        return 2
    return repair(args.db, args.apply, not args.no_backup)


if __name__ == "__main__":
    sys.exit(main())
