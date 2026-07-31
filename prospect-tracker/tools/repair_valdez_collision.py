# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_valdez_collision.py — one-off repair for the jose_a_valdez name-slug
key collision.

THE BUG (verified 2026-07-23): the 2026 DSL Giants OF signee Jose Valdez
(mlbam 838649, b. 2009-03-05) and the retired Tigers RHP Jose A. Valdez
(MLB debut 2015-04-01, career bWAR -0.54) both normalize to the slug
"jose_a_valdez". The signee's keyed rows (statlines mlbam 838649,
career_stats 2026 DSL line, player_transactions 2026 signing + DSL
assignment, roster_status never-debuted, player_photos 838649) all landed
on the row that carries the retiree's Pipeline 2014-2016 snapshots, the
2015 auto_detect debut snapshot, and the bbref career_war payload. The
merged record is status=debuted with org "Office of the Commissioner",
so the young player fails every active-board gate.

THE REPAIR:
  (a) re-key the SIGNEE's rows from "jose_a_valdez" to "jose_valdez_sfg"
      (the discriminated key registered in scrapers._SPLIT_KEYS) in:
      statlines, career_stats, player_transactions, roster_status,
      player_photos.
  (b) LEAVE the retiree's rows under "jose_a_valdez": the 4 snapshots
      (Pipeline 2014/2015/2016 + auto_detect 2015 debut) and career_war.
  (c) players table: the retiree keeps jose_a_valdez (RHP, is_pitcher=1)
      but loses the signee's misattributed birth_date 2009-03-05; the
      signee gets his own row (jose_valdez_sfg / Jose Valdez / OF / SFG /
      b. 2009-03-05).

Every row touched is printed. Rows that cannot be attributed with
confidence are LISTED and left alone. Idempotent: re-running after
--apply reports "already repaired" and changes nothing.

Usage:
    python tools/repair_valdez_collision.py            # dry run (default)
    python tools/repair_valdez_collision.py --apply    # write changes
    python tools/repair_valdez_collision.py --db PATH  # non-default DB
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

OLD_KEY = "jose_a_valdez"        # stays with the retired Tigers RHP
NEW_KEY = "jose_valdez_sfg"      # the 2026 DSL Giants OF signee
KID_MLBAM = 838649
KID_NAME = "Jose Valdez"         # what his own MLB transactions call him
KID_POS = "OF"
KID_ORG = "SFG"
KID_BIRTH = "2009-03-05"
RETIREE_DEBUT = "2015-04-01"

DEFAULT_DB = Path(__file__).resolve().parent.parent / "prospects.db"


def _p(action: str, *detail):
    print(f"  [{action}] " + " ".join(str(d) for d in detail))


def _row(con: sqlite3.Connection, sql: str, params=()):
    return con.execute(sql, params).fetchone()


def repair(db_path: Path, apply: bool) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== repair_valdez_collision [{mode}] db={db_path} ===")
    if not db_path.exists():
        print(f"FATAL: db not found: {db_path}")
        return 2

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    changes = 0          # rows that were (or would be) written
    ambiguous: list[str] = []

    # ------------------------------------------------------------------
    # 1. statlines — the signee's 2026 line, attributable by embedded
    #    mlbam_id == 838649. Re-key + rewrite the embedded player_key.
    # ------------------------------------------------------------------
    print("\n-- statlines --")
    old = _row(con, "SELECT * FROM statlines WHERE player_key = ?", (OLD_KEY,))
    new = _row(con, "SELECT * FROM statlines WHERE player_key = ?", (NEW_KEY,))
    if old is None and new is not None:
        _p("ok", f"already repaired: statline lives under {NEW_KEY}")
    elif old is None:
        _p("ok", f"no statline under {OLD_KEY}; nothing to do")
    else:
        try:
            payload = json.loads(old["payload_json"])
        except ValueError:
            payload = {}
        if payload.get("mlbam_id") != KID_MLBAM:
            ambiguous.append(
                f"statlines[{OLD_KEY}]: payload mlbam_id="
                f"{payload.get('mlbam_id')!r} != {KID_MLBAM} — NOT touched")
        elif new is not None:
            ambiguous.append(
                f"statlines: BOTH {OLD_KEY} and {NEW_KEY} rows exist — "
                "NOT touched, resolve manually")
        else:
            payload["player_key"] = NEW_KEY
            _p("rekey", f"statlines {OLD_KEY} -> {NEW_KEY} "
               f"(season={old['season']}, mlbam={KID_MLBAM}; embedded "
               "player_key rewritten; note payload is_pitcher="
               f"{payload.get('is_pitcher')!r} is stale merged-identity "
               "data — the nightly statline refresh overwrites it)")
            if apply:
                con.execute(
                    "UPDATE statlines SET player_key = ?, payload_json = ? "
                    "WHERE player_key = ?",
                    (NEW_KEY, json.dumps(payload), OLD_KEY))
            changes += 1

    # ------------------------------------------------------------------
    # 2. career_stats — attributable when EVERY season row is the signee's
    #    (2026+, org SFG). The retiree's career would carry pre-2019 rows.
    # ------------------------------------------------------------------
    print("\n-- career_stats --")
    old = _row(con, "SELECT * FROM career_stats WHERE player_key = ?", (OLD_KEY,))
    new = _row(con, "SELECT * FROM career_stats WHERE player_key = ?", (NEW_KEY,))
    if old is None and new is not None:
        _p("ok", f"already repaired: career_stats lives under {NEW_KEY}")
    elif old is None:
        _p("ok", f"no career_stats under {OLD_KEY}; nothing to do")
    else:
        try:
            seasons = json.loads(old["payload_json"])
        except ValueError:
            seasons = None
        is_kids = (
            isinstance(seasons, list) and seasons
            and all(int(s.get("season") or 0) >= 2026
                    and (s.get("org") == KID_ORG) for s in seasons)
        )
        if not is_kids:
            ambiguous.append(
                f"career_stats[{OLD_KEY}]: rows not all 2026+/SFG — NOT "
                f"touched (payload head: {old['payload_json'][:120]}...)")
        elif new is not None:
            ambiguous.append(
                f"career_stats: BOTH {OLD_KEY} and {NEW_KEY} rows exist — "
                "NOT touched, resolve manually")
        else:
            _p("rekey", f"career_stats {OLD_KEY} -> {NEW_KEY} "
               f"({len(seasons)} season row(s), all 2026 DSL/SFG)")
            if apply:
                con.execute(
                    "UPDATE career_stats SET player_key = ? WHERE player_key = ?",
                    (NEW_KEY, OLD_KEY))
            changes += 1

    # ------------------------------------------------------------------
    # 3. player_transactions — attributable when EVERY entry is 2026+
    #    (the signee's SFA 2026-01-30 + DSL assignment 2026-02-15). Any
    #    pre-2026 entry would be the retiree's -> ambiguous, untouched.
    # ------------------------------------------------------------------
    print("\n-- player_transactions --")
    old = _row(con, "SELECT * FROM player_transactions WHERE player_key = ?", (OLD_KEY,))
    new = _row(con, "SELECT * FROM player_transactions WHERE player_key = ?", (NEW_KEY,))
    if old is None and new is not None:
        _p("ok", f"already repaired: transactions live under {NEW_KEY}")
    elif old is None:
        _p("ok", f"no transactions under {OLD_KEY}; nothing to do")
    else:
        try:
            txs = json.loads(old["payload_json"])
        except ValueError:
            txs = None
        is_kids = (
            isinstance(txs, list) and txs
            and all((t.get("date") or "") >= "2026-01-01" for t in txs)
        )
        if not is_kids:
            ambiguous.append(
                f"player_transactions[{OLD_KEY}]: contains pre-2026 entries "
                "— NOT touched (would need a per-entry split)")
        elif new is not None:
            ambiguous.append(
                f"player_transactions: BOTH {OLD_KEY} and {NEW_KEY} rows "
                "exist — NOT touched, resolve manually")
        else:
            dates = [t.get("date") for t in txs]
            _p("rekey", f"player_transactions {OLD_KEY} -> {NEW_KEY} "
               f"({len(txs)} entries, dates {dates})")
            if apply:
                con.execute(
                    "UPDATE player_transactions SET player_key = ? "
                    "WHERE player_key = ?", (NEW_KEY, OLD_KEY))
            changes += 1

    # ------------------------------------------------------------------
    # 4. roster_status — the stored payload has mlb_debut_date NULL, i.e.
    #    it was fetched for mlbam 838649 (never debuted). The retiree
    #    debuted 2015-04-01, so a NULL-debut payload is the signee's.
    # ------------------------------------------------------------------
    print("\n-- roster_status --")
    old = _row(con, "SELECT * FROM roster_status WHERE player_key = ?", (OLD_KEY,))
    new = _row(con, "SELECT * FROM roster_status WHERE player_key = ?", (NEW_KEY,))
    if old is None and new is not None:
        _p("ok", f"already repaired: roster_status lives under {NEW_KEY}")
    elif old is None:
        _p("ok", f"no roster_status under {OLD_KEY}; nothing to do")
    else:
        try:
            rs = json.loads(old["payload_json"])
        except ValueError:
            rs = {}
        if rs.get("mlb_debut_date") is not None:
            ambiguous.append(
                f"roster_status[{OLD_KEY}]: mlb_debut_date="
                f"{rs.get('mlb_debut_date')!r} (a debuted payload could be "
                "the retiree's) — NOT touched")
        elif new is not None:
            ambiguous.append(
                f"roster_status: BOTH {OLD_KEY} and {NEW_KEY} rows exist — "
                "NOT touched, resolve manually")
        else:
            _p("rekey", f"roster_status {OLD_KEY} -> {NEW_KEY} "
               "(mlb_debut_date NULL = never-debuted signee payload)")
            if apply:
                con.execute(
                    "UPDATE roster_status SET player_key = ? WHERE player_key = ?",
                    (NEW_KEY, OLD_KEY))
            changes += 1

    # ------------------------------------------------------------------
    # 5. player_photos — keyed by mlbam_id (PK), so just repoint the
    #    signee's id at his new key.
    # ------------------------------------------------------------------
    print("\n-- player_photos --")
    ph = _row(con, "SELECT * FROM player_photos WHERE mlbam_id = ?", (KID_MLBAM,))
    if ph is None:
        _p("ok", f"no player_photos row for mlbam {KID_MLBAM}; nothing to do")
    elif ph["player_key"] == NEW_KEY:
        _p("ok", f"already repaired: photos[{KID_MLBAM}].player_key = {NEW_KEY}")
    else:
        _p("update", f"player_photos[{KID_MLBAM}].player_key "
           f"{ph['player_key']!r} -> {NEW_KEY!r}")
        if apply:
            con.execute(
                "UPDATE player_photos SET player_key = ? WHERE mlbam_id = ?",
                (NEW_KEY, KID_MLBAM))
        changes += 1

    # ------------------------------------------------------------------
    # 6. players — retiree keeps jose_a_valdez (RHP) minus the signee's
    #    birth date; signee gets his own row.
    # ------------------------------------------------------------------
    print("\n-- players --")
    ret = _row(con, "SELECT * FROM players WHERE player_key = ?", (OLD_KEY,))
    if ret is None:
        _p("warn", f"no players row for {OLD_KEY} (unexpected); skipping")
    else:
        if ret["birth_date"] == KID_BIRTH:
            _p("update", f"players[{OLD_KEY}].birth_date {KID_BIRTH!r} -> NULL "
               "(that DOB is the signee's; the retiree's real DOB is not on "
               "file locally — the next bbref/statsapi enrich may restore it)")
            if apply:
                con.execute(
                    "UPDATE players SET birth_date = NULL, "
                    "updated_at = datetime('now') WHERE player_key = ?",
                    (OLD_KEY,))
            changes += 1
        else:
            _p("ok", f"players[{OLD_KEY}].birth_date = {ret['birth_date']!r} "
               "(not the signee's; leaving)")
        if ret["position"] != "RHP" or not ret["is_pitcher"]:
            _p("update", f"players[{OLD_KEY}] position={ret['position']!r} "
               f"is_pitcher={ret['is_pitcher']!r} -> RHP / 1 (retiree)")
            if apply:
                con.execute(
                    "UPDATE players SET position = 'RHP', is_pitcher = 1, "
                    "updated_at = datetime('now') WHERE player_key = ?",
                    (OLD_KEY,))
            changes += 1
        else:
            _p("ok", f"players[{OLD_KEY}] already RHP / is_pitcher=1 (retiree)")

    kid = _row(con, "SELECT * FROM players WHERE player_key = ?", (NEW_KEY,))
    if kid is not None and (kid["player_name"], kid["position"], kid["org"],
                            kid["birth_date"], kid["is_pitcher"]) == (
                                KID_NAME, KID_POS, KID_ORG, KID_BIRTH, 0):
        _p("ok", f"already repaired: players[{NEW_KEY}] present and correct")
    else:
        verb = "update" if kid is not None else "insert"
        _p(verb, f"players[{NEW_KEY}] = name={KID_NAME!r} pos={KID_POS} "
           f"org={KID_ORG} birth={KID_BIRTH} is_pitcher=0")
        if apply:
            con.execute(
                """INSERT INTO players
                     (player_key, player_name, position, org, is_pitcher,
                      birth_date, updated_at)
                   VALUES (?, ?, ?, ?, 0, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                     player_name = excluded.player_name,
                     position    = excluded.position,
                     org         = excluded.org,
                     is_pitcher  = 0,
                     birth_date  = excluded.birth_date,
                     updated_at  = datetime('now')""",
                (NEW_KEY, KID_NAME, KID_POS, KID_ORG, KID_BIRTH))
        changes += 1

    # ------------------------------------------------------------------
    # 7. Rows deliberately LEFT under jose_a_valdez (the retiree's), plus
    #    advisories on adjacent tables outside this repair's remit.
    # ------------------------------------------------------------------
    print("\n-- left in place (retiree) --")
    for r in con.execute(
            "SELECT id, source, snapshot_date, interval_label, status "
            "FROM snapshots WHERE player_key = ? ORDER BY snapshot_date",
            (OLD_KEY,)):
        _p("keep", f"snapshots#{r['id']} {r['source']} {r['snapshot_date']} "
           f"({r['interval_label']}, status={r['status']})")
    cw = _row(con, "SELECT payload_json FROM career_war WHERE player_key = ?",
              (OLD_KEY,))
    if cw:
        _p("keep", f"career_war[{OLD_KEY}] = {cw['payload_json'][:100]}")

    print("\n-- acquisitions (signee's IFA record; authorized follow-up 2026-07-23) --")
    acq = _row(con, "SELECT * FROM acquisitions WHERE player_key = ?", (OLD_KEY,))
    acq_new = _row(con, "SELECT * FROM acquisitions WHERE player_key = ?", (NEW_KEY,))
    if acq and not acq_new:
        if acq["method"] == "international_fa":
            _p("rekey", f"acquisitions[{OLD_KEY}] method={acq['method']} "
               f"year={acq['year']} team={acq['team_name']!r} -> {NEW_KEY} "
               "(the SIGNEE's IFA record; the retiree was a 2005-era Tigers "
               "signee with no row here)")
            if apply:
                con.execute("UPDATE acquisitions SET player_key = ? "
                            "WHERE player_key = ?", (NEW_KEY, OLD_KEY))
                changes += 1
        else:
            _p("advisory", f"acquisitions[{OLD_KEY}] method={acq['method']} is "
               "NOT international_fa - ambiguous attribution, left alone")
    elif acq_new:
        _p("keep", f"acquisitions[{NEW_KEY}] already repaired")

    print("\n-- advisories (NOT touched: outside this repair's table list) --")
    try:
        tvh = con.execute(
            "SELECT COUNT(*) AS n FROM trade_value_history WHERE player_key = ?",
            (OLD_KEY,)).fetchone()
        if tvh and tvh["n"]:
            _p("advisory", f"trade_value_history has {tvh['n']} computed rows "
               f"under {OLD_KEY} (valuations of the merged record); "
               "regenerated by the pipeline — left alone")
    except sqlite3.OperationalError:
        pass

    cache_file = db_path.parent / ".cache" / "mlbam_ids.json"
    if cache_file.exists():
        try:
            idc = json.loads(cache_file.read_text(encoding="utf-8"))
            if idc.get(OLD_KEY) == KID_MLBAM:
                _p("advisory", f".cache/mlbam_ids.json still binds {OLD_KEY} "
                   f"-> {KID_MLBAM}; the resolver's collision guard "
                   "(stats._apply_collision_guard) heals this stale binding "
                   "on the next resolve — no manual edit needed")
            else:
                _p("ok", f".cache/mlbam_ids.json[{OLD_KEY}] = "
                   f"{idc.get(OLD_KEY)!r} (no stale kid-binding)")
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Finish
    # ------------------------------------------------------------------
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
        description="Repair the jose_a_valdez name-slug key collision "
                    "(2026 DSL Giants signee vs retired Tigers RHP).")
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help=f"path to prospects.db (default: {DEFAULT_DB})")
    args = ap.parse_args()
    return repair(args.db, apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
