# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_jesus_lopez_collision.py - one-off repair for the jesus_lopez name-slug
key collision, the first one to reach the ACTIVE board since the gate was armed.

HOW IT SURFACED. test_identity_collisions::test_no_new_merged_identity_on_the
_active_board went red on 2026-08-12 naming jesus_lopez. The key was already
carried in KNOWN_MERGED_INACTIVE, so this is not a new collision: it is a known
inactive one that CROSSED ONTO THE LIVE BOARD when the newcomer signed and took
a roster spot. The committed data/identity_collisions.json (2026-08-11T00:03Z)
still reads critical_active_player_keys: [], the regen at 15:55Z reads
["jesus_lopez"], so the crossing is datable to that window.

FIVE HUMANS share this slug (data/identity_collisions.json shadowed_slugs:
n_humans 5, mlbam 805052 / 806882 / 808362 / 821805 / 838819). Resolved against
the cached StatsAPI people records:

  805052  b. 2005-05-24  C    <- THE INCUMBENT
  806882  b. 2006-03-14  P
  808362  b. 2005-03-03  P    <- already split, key jesus_lopez_808362 (SFG)
  821805  b. unknown     ?
  838819  b. 2008-07-07  P    <- THE NEWCOMER

  INCUMBENT  mlbam 805052, b. 2005-05-24, CATCHER. Owns the board history on
             this key: FanGraphs TEX 2023-02-23 (rank 15, FV 40) and 2023-08-01
             (rank 12, FV 40), MLB Pipeline TEX 2024-01-22 (rank 30, FV 40).
             He is the only CATCHER among the five ids, and every snapshot on
             the key is published at C, which is the two-signal match.

  NEWCOMER   mlbam 838819, b. 2008-07-07, RHP, Boston. International free agent
             signed 2026-02-13 for $347,500, assigned to DSL Red Sox Blue on
             2026-04-03. He has NO board snapshot anywhere: he reached the
             active board purely through the roster and acquisition path, which
             is why no board-ingest pin is needed and the MLBAM pin is.

THE PROOF THAT THE RECORD WAS MERGED, and it is on one row. players[jesus_lopez]
reads position C / org TEX / is_pitcher 0 (the CATCHER's) carrying birth_date
2008-07-07 (the PITCHER's). One row, two humans, and the date of birth is the
half that is wrong: the catcher is b. 2005-05-24. Downstream that chimera served
a card at age 18.1 under a C at BOS with 10 games FIELDED AT PITCHER, which is
the C4 side conflict the audit fired on.

THE REPAIR (follows tools/repair_garrett_wright_collision.py exactly):
  (a) the INCUMBENT is never re-keyed. "jesus_lopez" stays the catcher. His
      players row is REPAIRED IN PLACE on the one contaminated field
      (birth_date -> 2005-05-24); position, org and is_pitcher are already his
      and are verified rather than rewritten.
  (b) the NEWCOMER's rows move to "jesus_lopez_bos", registered in
      scrapers._SPLIT_KEYS[("jesus_lopez", 838819)]. Four tables carry rows
      that are unambiguously his, each identified on two independent signals:
        - acquisitions   international_fa 2026 / Boston / 2026-02-13
        - player_transactions  the BOS signing + DSL assignment, which name him
                               RHP in their own text
        - roster_status  the key is on a roster in 2026 only because of him
        - player_photos  bound to mlbam 838819 directly
      A players row is created for the split key: RHP / BOS / is_pitcher 1 /
      b. 2008-07-07, all four fields published by MLB rather than inferred.
  (c) rows that cannot be attributed with confidence are LISTED and left alone,
      per the carlos_castillo precedent. Two classes here:
        - the 2015-01-22 MLB Pipeline row (2B, "Office of the Commissioner")
          belongs to NEITHER of these two humans: the incumbent was nine years
          old on that date. It is a fourth identity on the slug and needs its
          own resolution, so it is reported and untouched.
        - metric_snapshots (7) and trade_value_history (7) dated 2026-08-04 to
          2026-08-11 were COMPUTED WHILE THE KEY WAS MERGED. They describe the
          chimera and belong cleanly to neither human: the org and age are the
          newcomer's, the FV is graded off the incumbent's board rows. Moving
          them would assert a board history the newcomer never had; they are
          append-only history and are left in place and disclosed. They stop
          being written the moment the split lands.

WHY THE DB REPAIR ALONE IS NOT ENOUGH: carlos_castillo was repaired once and
then RE-MERGED by the next ingest. The pin that makes this stick is
scrapers._SPLIT_KEYS[("jesus_lopez", 838819)] -> "jesus_lopez_bos", consulted
wherever a key is resolved with an MLBAM id in hand. No board-ingest pin
(_BA_ORG_SPLIT_KEYS / _FG_ORG_SPLIT_KEYS) is added because the newcomer has
never appeared on a published board; if he ever does, add one then.

NOT DONE ON PURPOSE: data/sources/mlbam_id_overrides.json is not given a
jesus_lopez -> 805052 entry. That file has 735 entries and no production
reader (its only consumer is a lab harness), so an entry there would look like
a fix and do nothing. The incumbent's binding heals through the normal
id-resolution path once 838819 is routed away.

Idempotent: re-running after --apply reports "already repaired" and changes
nothing.

Usage:
    python tools/repair_jesus_lopez_collision.py            # dry run
    python tools/repair_jesus_lopez_collision.py --apply    # write
    python tools/repair_jesus_lopez_collision.py --db PATH  # other DB
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

OLD_KEY = "jesus_lopez"        # stays with the INCUMBENT catcher
NEW_KEY = "jesus_lopez_bos"    # discriminated key for the NEWCOMER

INCUMBENT_MLBAM = 805052
INCUMBENT_POS = "C"
INCUMBENT_ORG = "TEX"
INCUMBENT_BIRTH = "2005-05-24"

KID_MLBAM = 838819
KID_POS = "P"
KID_ORG = "BOS"
KID_BIRTH = "2008-07-07"
KID_NAME = "Jesus Lopez"

#: The newcomer's acquisition, identified by (method, year, team_name,
#: signing_date). The incumbent is a 2023-board catcher and has never had an
#: international-free-agent row on this key.
KID_ACQUISITION = ("international_fa", 2026, "Boston Red Sox", "2026-02-13")

#: The 2015 row belongs to a FOURTH human (see module docstring). Identified so
#: it can be reported rather than silently swept along with the incumbent's.
FOURTH_HUMAN_SNAPSHOT = ("mlb_pipeline", "2015-01-22")

DEFAULT_DB = Path(__file__).resolve().parent.parent / "prospects.db"


def _p(action: str, *detail):
    print(f"  [{action}] " + " ".join(str(d) for d in detail))


def repair(db_path: Path, apply: bool) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== repair_jesus_lopez_collision [{mode}] db={db_path} ===")
    if not db_path.exists():
        print(f"FATAL: db not found: {db_path}")
        return 2

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    changes = 0
    ambiguous: list[str] = []
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    # ------------------------------------------------------------------
    # 1. players - repair the incumbent's one wrong field, create the newcomer.
    # ------------------------------------------------------------------
    print("\n-- players --")
    inc = con.execute("SELECT * FROM players WHERE player_key = ?",
                      (OLD_KEY,)).fetchone()
    if inc is None:
        ambiguous.append(f"players[{OLD_KEY}]: row missing - NOT created")
    else:
        if inc["position"] != INCUMBENT_POS or inc["org"] != INCUMBENT_ORG:
            ambiguous.append(
                f"players[{OLD_KEY}]: position/org is "
                f"{inc['position']}/{inc['org']}, expected "
                f"{INCUMBENT_POS}/{INCUMBENT_ORG} - NOT touched, review first")
        elif str(inc["birth_date"])[:10] == INCUMBENT_BIRTH:
            _p("ok", f"already repaired: {OLD_KEY} b.{INCUMBENT_BIRTH}")
        elif str(inc["birth_date"])[:10] == KID_BIRTH:
            _p("restore", f"players[{OLD_KEY}].birth_date: {inc['birth_date']} "
               f"(the NEWCOMER's) -> {INCUMBENT_BIRTH} (mlbam "
               f"{INCUMBENT_MLBAM}, the catcher this key belongs to). "
               f"position/org/is_pitcher are already his and stay.")
            con.execute("UPDATE players SET birth_date = ? WHERE player_key = ?",
                        (INCUMBENT_BIRTH, OLD_KEY))
            changes += 1
        else:
            ambiguous.append(
                f"players[{OLD_KEY}].birth_date is {inc['birth_date']!r}, "
                f"neither the incumbent's {INCUMBENT_BIRTH} nor the newcomer's "
                f"{KID_BIRTH} - NOT touched")

    kid = con.execute("SELECT * FROM players WHERE player_key = ?",
                      (NEW_KEY,)).fetchone()
    if kid is not None:
        _p("ok", f"already repaired: {NEW_KEY} players row exists")
    else:
        _p("create", f"players[{NEW_KEY}]: {KID_NAME} / {KID_POS} / {KID_ORG} "
           f"/ is_pitcher=1 / b.{KID_BIRTH} (the Boston DSL RHP, mlbam "
           f"{KID_MLBAM}; every field published by MLB, none inferred)")
        con.execute(
            "INSERT INTO players (player_key, player_name, position, org, "
            "is_pitcher, birth_date) VALUES (?, ?, ?, ?, 1, ?)",
            (NEW_KEY, KID_NAME, KID_POS, KID_ORG, KID_BIRTH))
        changes += 1

    # ------------------------------------------------------------------
    # 2. the newcomer's four identity tables.
    # ------------------------------------------------------------------
    print("\n-- acquisitions --")
    if "acquisitions" in tables:
        for r in con.execute(
                "SELECT rowid, * FROM acquisitions WHERE player_key IN (?, ?)",
                (OLD_KEY, NEW_KEY)).fetchall():
            if r["player_key"] == NEW_KEY:
                _p("ok", f"already on {NEW_KEY}: {r['method']} {r['year']}")
                continue
            sig = (r["method"], r["year"], r["team_name"],
                   str(r["signing_date"])[:10])
            if sig != KID_ACQUISITION:
                _p("keep", f"acquisition {sig} is not the newcomer's; stays "
                   f"on {OLD_KEY}")
                continue
            _p("rekey", f"acquisitions: {r['method']} {r['year']} "
               f"{r['team_name']} ${r['bonus_usd']} -> {NEW_KEY}")
            con.execute("UPDATE acquisitions SET player_key = ? WHERE rowid = ?",
                        (NEW_KEY, r["rowid"]))
            changes += 1

    print("\n-- player_transactions --")
    if "player_transactions" in tables:
        row = con.execute(
            "SELECT rowid, payload_json FROM player_transactions "
            "WHERE player_key = ?", (OLD_KEY,)).fetchone()
        if row is None:
            _p("ok", f"no player_transactions row on {OLD_KEY}")
        else:
            blob = str(row["payload_json"])
            # Two independent signals in the payload's own text: the club that
            # signed him and the DSL affiliate he was assigned to. Refuse if
            # either is missing rather than moving a row on one signal.
            if "Boston Red Sox" in blob and "DSL Red Sox" in blob:
                _p("rekey", f"player_transactions: the BOS signing + DSL "
                   f"assignment log -> {NEW_KEY}")
                con.execute("UPDATE player_transactions SET player_key = ? "
                            "WHERE rowid = ?", (NEW_KEY, row["rowid"]))
                changes += 1
            else:
                ambiguous.append(
                    "player_transactions: payload does not carry both the "
                    "Boston signing and the DSL assignment - NOT moved")

    print("\n-- roster_status --")
    if "roster_status" in tables:
        row = con.execute(
            "SELECT rowid, payload_json FROM roster_status WHERE player_key = ?",
            (OLD_KEY,)).fetchone()
        if row is None:
            _p("ok", f"no roster_status row on {OLD_KEY}")
        else:
            try:
                st = json.loads(row["payload_json"])
            except ValueError:
                st = {}
            # The incumbent last appeared on a board in January 2024 and has no
            # 2026 roster presence of his own. A row claiming no debut, no MLB
            # season and three options is the DSL signee's.
            if not st.get("mlb_seasons") and not st.get("mlb_debut_date"):
                _p("rekey", f"roster_status: the 2026 DSL roster row -> {NEW_KEY}")
                con.execute("UPDATE roster_status SET player_key = ? "
                            "WHERE rowid = ?", (NEW_KEY, row["rowid"]))
                changes += 1
            else:
                ambiguous.append(
                    f"roster_status: carries MLB history "
                    f"{st.get('mlb_seasons')!r} - NOT moved")

    print("\n-- player_photos --")
    if "player_photos" in tables:
        # Keyed on mlbam_id, not rowid: player_photos is WITHOUT ROWID, so a
        # rowid predicate raises rather than matching nothing.
        for r in con.execute(
                "SELECT mlbam_id, player_key FROM player_photos "
                "WHERE player_key IN (?, ?)", (OLD_KEY, NEW_KEY)).fetchall():
            if r["player_key"] == NEW_KEY:
                _p("ok", f"already on {NEW_KEY}: mlbam {r['mlbam_id']}")
            elif r["mlbam_id"] == KID_MLBAM:
                _p("rekey", f"player_photos: mlbam {KID_MLBAM} is the "
                   f"newcomer's own id -> {NEW_KEY}")
                con.execute("UPDATE player_photos SET player_key = ? "
                            "WHERE mlbam_id = ?", (NEW_KEY, r["mlbam_id"]))
                changes += 1
            else:
                _p("keep", f"player_photos: mlbam {r['mlbam_id']} stays on "
                   f"{OLD_KEY}")

    # ------------------------------------------------------------------
    # 3. snapshots - the incumbent's stay; the 2015 row is a fourth human.
    # ------------------------------------------------------------------
    print("\n-- snapshots --")
    for r in con.execute(
            "SELECT id, player_key, source, snapshot_date, position, org, "
            "rank, fv FROM snapshots WHERE player_key IN (?, ?) "
            "ORDER BY snapshot_date", (OLD_KEY, NEW_KEY)).fetchall():
        if r["player_key"] == NEW_KEY:
            _p("ok", f"already on {NEW_KEY}: {r['snapshot_date']} "
               f"{r['position']}/{r['org']}")
            continue
        if (r["source"], r["snapshot_date"]) == FOURTH_HUMAN_SNAPSHOT:
            ambiguous.append(
                f"snapshots id={r['id']}: {r['source']} {r['snapshot_date']} "
                f"{r['position']}/{r['org']} belongs to NEITHER human here - "
                f"the incumbent (b.{INCUMBENT_BIRTH}) was nine years old on "
                f"that date. Fourth identity on this slug, left in place.")
            continue
        _p("keep", f"snapshot {r['source']} {r['snapshot_date']} "
           f"{r['position']}/{r['org']} FV {r['fv']} is the incumbent "
           f"catcher's and stays on {OLD_KEY}")

    # ------------------------------------------------------------------
    # 4. derived history computed during the merge window: report, do not move.
    # ------------------------------------------------------------------
    print("\n-- derived history, REPORTED and left in place --")
    for t in ("metric_snapshots", "trade_value_history", "trades"):
        if t not in tables:
            continue
        n = con.execute(f"SELECT COUNT(*) FROM {t} WHERE player_key = ?",
                        (OLD_KEY,)).fetchone()[0]
        if n:
            _p("disclose", f"{t}: {n} row(s) computed while the key was merged. "
               f"They describe the chimera (the newcomer's org and age, the "
               f"incumbent's FV) and belong cleanly to neither human. "
               f"Append-only history: left in place, stops being written now.")

    if ambiguous:
        print("\n-- AMBIGUOUS rows (listed, NOT touched) --")
        for a in ambiguous:
            _p("ambiguous", a)

    if apply:
        con.commit()
        print(f"\n=== APPLIED: {changes} write(s) committed ===")
    else:
        con.rollback()
        print(f"\n=== DRY-RUN: {changes} write(s) planned; re-run with "
              "--apply to execute ===")
    con.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Repair the jesus_lopez name-slug key collision "
                    "(Boston DSL RHP vs Texas catcher).")
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help=f"path to prospects.db (default: {DEFAULT_DB})")
    args = ap.parse_args()
    return repair(args.db, apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
