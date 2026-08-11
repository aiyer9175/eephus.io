# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_garrett_wright_collision.py - one-off repair for the garrett_wright
name-slug key collision.

THE BUG (found by the 2026-08-09 BA-ingest adversarial verification): two
different humans drafted three years apart normalize to the slug
"garrett_wright".

  INCUMBENT  mlbam 695057, b. 2002-02-11, RHP, White Sox org, TCU,
             drafted 2023 round 20 pick 599.
             Owns: the players row, the 2026 A+ statline (37.1 IP, embedded
             mlbam_id 695057), career_stats, the 2023 acquisitions row, the
             full RHP/TCU/Kannapolis transaction log, roster_status,
             zone_metrics, 37 metric_snapshots, 35 trade_value_history rows,
             the headshot, and the performance_ingest snapshot (CHW / P).

  NEWCOMER   mlbam 835226, C/OF, Angels org, Tennessee (via Bowling Green),
             drafted 2026 round 8 pick 229. Arrived on the Baseball America
             2026 midseason Angels board (rank 20, adjusted grade 35) and
             landed on the incumbent's key.

HOW THE MERGE HAPPENED, precisely: draft promotion mapped
draft_2026_garrett_wright -> garrett_wright on 2026-07-14, but the 2023
draft_results row that would have made the collision guard fire was not
fetched until 2026-08-09. The guard collides draft picks against other draft
picks, so a pick colliding with an ALREADY-TRACKED non-draft identity sailed
through. The BA ingest then wrote onto the merged key via an exact key match,
which the admission bar now catches (age 20 vs b.2002 is a >= 2 year
contradiction) but did not exist at ingest time.

THE REPAIR (follows tools/repair_carlos_castillo_collision.py exactly):
  (a) the INCUMBENT is never re-keyed. "garrett_wright" stays the White Sox
      pitcher; his players row is already correct (P / CHW / is_pitcher=1 /
      b.2002-02-11) and is verified, not rewritten.
  (b) the NEWCOMER's rows move to "garrett_wright_laa", the discriminated
      key registered in scrapers._SPLIT_KEYS[("garrett_wright", 835226)]
      and in the per-source ingest pins (see below):
        - the baseballamerica 2026-08-01 snapshot (C / LAA), and
        - draft_canonical_keys[draft_2026_garrett_wright].milb_key, and
        - draft_players[draft_2026_garrett_wright].promoted_key.
      A players row is created for the split key. birth_date is left NULL:
      no source in this database publishes the catcher's DOB yet, and a NULL
      heals on the next id-driven refresh while a guessed date poisons the
      admission bar that keys on it.
  (c) rows that cannot be attributed with confidence are LISTED and left
      alone, per the carlos_castillo precedent.

WHY THE DB REPAIR ALONE IS NOT ENOUGH: carlos_castillo was repaired once and
then RE-MERGED by the next board, because nothing stopped the next ingest
re-minting the bare key. So this repair ships together with ingest-side pins:
_BA_ORG_SPLIT_KEYS[("garrett_wright", "LAA")] in baseballamerica_csv.py and
scrapers._SPLIT_KEYS[("garrett_wright", 835226)]. The repair script itself
only fixes the stored rows; the pins are what make it stick.

Idempotent: re-running after --apply reports "already repaired" and changes
nothing.

Usage:
    python tools/repair_garrett_wright_collision.py            # dry run
    python tools/repair_garrett_wright_collision.py --apply    # write
    python tools/repair_garrett_wright_collision.py --db PATH  # other DB
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

OLD_KEY = "garrett_wright"        # stays with the INCUMBENT pitcher
NEW_KEY = "garrett_wright_laa"    # discriminated key for the NEWCOMER
DRAFT_KEY = "draft_2026_garrett_wright"

INCUMBENT_MLBAM = 695057
INCUMBENT_POS = "P"
INCUMBENT_ORG = "CHW"
INCUMBENT_BIRTH = "2002-02-11"

KID_MLBAM = 835226
KID_POS = "C"
KID_ORG = "LAA"

# The newcomer's one snapshot, identified by (source, date, org, position).
# The pitcher never appears as a C, and no other source has ever written an
# LAA row onto this key, so this is a sufficient discriminator.
KID_SNAPSHOT = ("baseballamerica", "2026-08-01", KID_ORG, KID_POS)

DEFAULT_DB = Path(__file__).resolve().parent.parent / "prospects.db"


def _p(action: str, *detail):
    print(f"  [{action}] " + " ".join(str(d) for d in detail))


def repair(db_path: Path, apply: bool) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== repair_garrett_wright_collision [{mode}] db={db_path} ===")
    if not db_path.exists():
        print(f"FATAL: db not found: {db_path}")
        return 2

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    changes = 0
    ambiguous: list[str] = []

    # ------------------------------------------------------------------
    # 1. snapshots - move the newcomer's BA row onto the split key.
    # ------------------------------------------------------------------
    print("\n-- snapshots --")
    rows = con.execute(
        "SELECT id, source, snapshot_date, interval_label, player_key, "
        "position, org FROM snapshots WHERE player_key IN (?, ?) "
        "ORDER BY snapshot_date",
        (OLD_KEY, NEW_KEY),
    ).fetchall()
    for r in rows:
        if r["player_key"] == NEW_KEY:
            _p("ok", f"already on {NEW_KEY}: {r['snapshot_date']} "
               f"{r['position']}/{r['org']}")
            continue
        is_kid = ((r["source"], r["snapshot_date"], r["org"], r["position"])
                  == KID_SNAPSHOT)
        if not is_kid:
            _p("keep", f"incumbent snapshot {r['source']} "
               f"{r['snapshot_date']} {r['position']}/{r['org']} stays on "
               f"{OLD_KEY}")
            continue
        _p("rekey", f"snapshot id={r['id']} {r['source']} "
           f"{r['snapshot_date']} ({r['interval_label']}) "
           f"{r['position']}/{r['org']}: {r['player_key']} -> {NEW_KEY}")
        con.execute("UPDATE snapshots SET player_key = ? WHERE id = ?",
                    (NEW_KEY, r["id"]))
        changes += 1

    # ------------------------------------------------------------------
    # 2. players - verify the incumbent, create the newcomer.
    # ------------------------------------------------------------------
    print("\n-- players --")
    inc = con.execute("SELECT * FROM players WHERE player_key = ?",
                      (OLD_KEY,)).fetchone()
    if inc is None:
        ambiguous.append(f"players[{OLD_KEY}]: row missing - NOT created")
    elif (inc["position"] == INCUMBENT_POS and inc["org"] == INCUMBENT_ORG
          and inc["is_pitcher"] == 1
          and str(inc["birth_date"])[:10] == INCUMBENT_BIRTH):
        _p("ok", f"incumbent intact: {OLD_KEY} is {INCUMBENT_POS}/"
           f"{INCUMBENT_ORG} is_pitcher=1 b.{INCUMBENT_BIRTH}")
    else:
        _p("restore", f"players[{OLD_KEY}]: {inc['position']}/{inc['org']} "
           f"is_pitcher={inc['is_pitcher']} b.{inc['birth_date']} -> "
           f"{INCUMBENT_POS}/{INCUMBENT_ORG} is_pitcher=1 "
           f"b.{INCUMBENT_BIRTH} (the White Sox RHP)")
        con.execute(
            "UPDATE players SET position = ?, org = ?, is_pitcher = 1, "
            "birth_date = ? WHERE player_key = ?",
            (INCUMBENT_POS, INCUMBENT_ORG, INCUMBENT_BIRTH, OLD_KEY))
        changes += 1

    kid = con.execute("SELECT * FROM players WHERE player_key = ?",
                      (NEW_KEY,)).fetchone()
    if kid is not None:
        _p("ok", f"already repaired: {NEW_KEY} players row exists")
    else:
        _p("create", f"players[{NEW_KEY}]: Garrett Wright / {KID_POS} / "
           f"{KID_ORG} / is_pitcher=0 / b.NULL (the Angels catcher; DOB "
           "unpublished, heals on the next id-driven refresh)")
        con.execute(
            "INSERT INTO players (player_key, player_name, position, org, "
            "is_pitcher, birth_date) VALUES (?, ?, ?, ?, 0, NULL)",
            (NEW_KEY, "Garrett Wright", KID_POS, KID_ORG))
        changes += 1

    # ------------------------------------------------------------------
    # 3. the draft spine - repoint the 2026 pick at the split key.
    # ------------------------------------------------------------------
    print("\n-- draft spine --")
    ck = con.execute(
        "SELECT milb_key FROM draft_canonical_keys WHERE draft_key = ?",
        (DRAFT_KEY,)).fetchone()
    if ck is None:
        ambiguous.append(f"draft_canonical_keys[{DRAFT_KEY}]: row missing")
    elif ck["milb_key"] == NEW_KEY:
        _p("ok", f"draft_canonical_keys[{DRAFT_KEY}] already -> {NEW_KEY}")
    else:
        _p("rekey", f"draft_canonical_keys[{DRAFT_KEY}]: "
           f"{ck['milb_key']} -> {NEW_KEY}")
        con.execute(
            "UPDATE draft_canonical_keys SET milb_key = ? WHERE draft_key = ?",
            (NEW_KEY, DRAFT_KEY))
        changes += 1

    dp = con.execute(
        "SELECT promoted_key, mlbam_id FROM draft_players "
        "WHERE player_key = ?", (DRAFT_KEY,)).fetchone()
    if dp is None:
        ambiguous.append(f"draft_players[{DRAFT_KEY}]: row missing")
    elif dp["promoted_key"] == NEW_KEY:
        _p("ok", f"draft_players[{DRAFT_KEY}].promoted_key already {NEW_KEY}")
    else:
        if dp["mlbam_id"] not in (None, KID_MLBAM):
            ambiguous.append(
                f"draft_players[{DRAFT_KEY}]: mlbam_id={dp['mlbam_id']!r} is "
                f"not the expected {KID_MLBAM} - promoted_key NOT touched")
        else:
            _p("rekey", f"draft_players[{DRAFT_KEY}].promoted_key: "
               f"{dp['promoted_key']} -> {NEW_KEY}")
            con.execute(
                "UPDATE draft_players SET promoted_key = ? "
                "WHERE player_key = ?", (NEW_KEY, DRAFT_KEY))
            changes += 1

    # The 2023 pick's mapping is the incumbent's and must NOT move.
    ck23 = con.execute(
        "SELECT draft_key, milb_key FROM draft_canonical_keys "
        "WHERE draft_key = 'draft_2023_garrett_wright'").fetchone()
    if ck23 is not None:
        if ck23["milb_key"] == OLD_KEY:
            _p("keep", f"draft_canonical_keys[{ck23['draft_key']}] -> "
               f"{OLD_KEY} is the incumbent's own 2023 pick; correct as-is")
        else:
            ambiguous.append(
                f"draft_canonical_keys[draft_2023_garrett_wright] -> "
                f"{ck23['milb_key']!r}, expected {OLD_KEY} - NOT touched")

    # ------------------------------------------------------------------
    # 4. report (do not move) everything else on the incumbent's key.
    # ------------------------------------------------------------------
    print("\n-- reported, NOT touched --")
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in ("statlines", "career_stats", "acquisitions",
              "player_transactions", "roster_status", "zone_metrics",
              "metric_snapshots", "trade_value_history", "player_photos"):
        if t not in tables:
            continue
        n = con.execute(f"SELECT COUNT(*) FROM {t} WHERE player_key = ?",
                        (OLD_KEY,)).fetchone()[0]
        if n:
            _p("keep", f"{t}: {n} row(s) are the incumbent pitcher's "
               f"(mlbam {INCUMBENT_MLBAM}) and stay on {OLD_KEY}")

    st = con.execute("SELECT season, payload_json FROM statlines "
                     "WHERE player_key = ?", (OLD_KEY,)).fetchone()
    if st is not None:
        try:
            mid = json.loads(st["payload_json"]).get("mlbam_id")
        except ValueError:
            mid = None
        if mid != INCUMBENT_MLBAM:
            ambiguous.append(
                f"statlines[{OLD_KEY}]: payload mlbam_id={mid!r} is not the "
                f"incumbent {INCUMBENT_MLBAM} - review")

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
        description="Repair the garrett_wright name-slug key collision "
                    "(Angels C vs White Sox RHP).")
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help=f"path to prospects.db (default: {DEFAULT_DB})")
    args = ap.parse_args()
    return repair(args.db, apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
