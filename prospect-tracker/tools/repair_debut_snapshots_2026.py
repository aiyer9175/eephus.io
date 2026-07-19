# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Re-date the 2026 run-date-stamped veteran debut snapshots (Vilade class).

Before the re-fire guard landed (storage.auto_debut_player now suppresses when
ANY debuted snapshot exists, and clamps to roster_status.mlb_debut_date), the
2026-05-17/18 pipeline runs auto-detected veteran RE-APPEARANCES as fresh MLB
debuts and stamped the debut snapshot with the RUN date. Type case: Ryan
Vilade — debut snapshot dated 2026-05-17 against a true 2021-09-18 debut. The
2026-07-14 audit counted 41 such rows (the eFV dataset labels were repaired at
the dataset layer; the underlying snapshot rows were not).

What this tool does — for every `source='auto_detect'`, `status='debuted'`
snapshot stamped in 2026 whose evidence shows an EARLIER-SEASON true debut:

  * re-dates the snapshot to the true debut date, resolved per row as:
      1. roster_status.mlb_debut_date, when present AND a plausible game date
         (a handful of payloads carry mid-November 40-man-selection dates —
         2019-11-20 and friends — which cannot be debut games and are skipped);
      2. else `{first MLB season}-04-01` from the earliest MLB season across
         career_stats / career_war — the same Opening-Day stand-in convention
         storage._resolve_first_mlb_game_date uses;
  * rows with NO resolvable true date are NOT touched by default — they are
    flagged as deletion-only candidates and removed only under
    --delete-spurious (verified 0 such rows on the dev DB);
  * rows where roster_status and the career tables disagree on the debut YEAR
    are still re-dated (roster_status wins — it is the API's mlbDebutDate) but
    flagged as evidence conflicts for owner review;
  * same-season misdates (2026 debuts stamped with the later run date, e.g.
    jeferson_quero 2026-03-29 stamped 2026-05-18) are reported but only
    repaired under --include-same-season — the authorized scope is the 41
    veteran rows.

Safety rails:
  * dry-run by default — prints the full per-row plan, changes nothing;
  * --apply requires a fresh backup (pass --backup PATH, or drop a copy named
    <db>.backup* / <db>.bak* next to the DB, mtime < 24h);
  * preflight aborts when the veteran repair count strays >25% from the
    expected ~41 (override with --expect);
  * runs inside a single transaction, each UPDATE guarded by the old date and
    asserted to touch exactly one row;
  * idempotent — re-dated rows leave the 2026 detection window (or match
    their roster_status date), so a second run finds nothing to do.

Usage:
    python tools/repair_debut_snapshots_2026.py                  # dry-run (default)
    python tools/repair_debut_snapshots_2026.py --apply --backup prospects.db.backup-20260716
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WINDOW_START = "2026-01-01"  # the corruption class is a 2026-run artifact
EXPECTED_ROWS = 41           # verified 2026-07-16 on the dev DB
COUNT_TOLERANCE = 0.25       # abort when the veteran count strays >25%
MAX_BACKUP_AGE_HOURS = 24.0
MIN_BACKUP_SIZE_RATIO = 0.5

CANDIDATE_SQL = (
    "SELECT id, player_key, player_name, snapshot_date, inserted_at FROM snapshots "
    "WHERE source='auto_detect' AND status='debuted' "
    "AND interval_label='Auto-detected MLB debut' "
    f"AND snapshot_date >= '{WINDOW_START}' "
    "ORDER BY snapshot_date, player_key"
)
UPDATE_SQL = "UPDATE snapshots SET snapshot_date = ? WHERE id = ? AND snapshot_date = ?"
DELETE_SQL = "DELETE FROM snapshots WHERE id = ?"


# ---------------------------------------------------------------- backup gate
def _backup_hint(db_path: Path) -> str:
    stamp = date.today().strftime("%Y%m%d")
    dst = f"{db_path.name}.backup-{stamp}"
    return (
        "make one from the DB directory with either:\n"
        f'  sqlite3 {db_path.name} ".backup \'{dst}\'"\n'
        "or (no sqlite3 CLI needed):\n"
        f"  python -c \"import sqlite3; s=sqlite3.connect('{db_path.name}'); "
        f"d=sqlite3.connect('{dst}'); s.backup(d); d.close(); s.close()\""
    )


def find_fresh_backup(db_path: Path, explicit: str | None) -> Path | None:
    """Return a usable backup path, or None (with reasons printed)."""
    candidates: list[Path] = []
    if explicit:
        p = Path(explicit)
        if not p.exists():
            print(f"preflight: --backup {p} does not exist")
            return None
        candidates = [p]
    else:
        for pat in (f"{db_path.name}.backup*", f"{db_path.name}.bak*"):
            candidates.extend(db_path.parent.glob(pat))
        if not candidates:
            print(f"preflight: no {db_path.name}.backup* / .bak* file found next to the DB")
            return None
    db_size = db_path.stat().st_size
    now = time.time()
    for p in sorted(candidates, key=lambda x: x.stat().st_mtime, reverse=True):
        age_h = (now - p.stat().st_mtime) / 3600.0
        if age_h > MAX_BACKUP_AGE_HOURS:
            print(f"preflight: {p.name} is {age_h:.1f}h old (> {MAX_BACKUP_AGE_HOURS:.0f}h) — too stale")
            continue
        if p.stat().st_size < db_size * MIN_BACKUP_SIZE_RATIO:
            print(f"preflight: {p.name} is {p.stat().st_size} bytes vs DB {db_size} — not a full backup")
            continue
        return p
    return None


# ------------------------------------------------------------ evidence lookups
def _roster_debut(con: sqlite3.Connection, player_key: str) -> str | None:
    row = con.execute(
        "SELECT payload_json FROM roster_status WHERE player_key = ?", (player_key,)
    ).fetchone()
    if not row:
        return None
    try:
        d = (json.loads(row["payload_json"]) or {}).get("mlb_debut_date")
    except (TypeError, ValueError):
        return None
    return str(d) if d else None


def _career_stats_first_mlb(con: sqlite3.Connection, player_key: str) -> int | None:
    row = con.execute(
        "SELECT payload_json FROM career_stats WHERE player_key = ?", (player_key,)
    ).fetchone()
    if not row:
        return None
    try:
        rows = json.loads(row["payload_json"])
    except (TypeError, ValueError):
        return None
    if not isinstance(rows, list):
        return None
    seasons = [int(r["season"]) for r in rows
               if isinstance(r, dict) and r.get("level") == "MLB" and r.get("season")]
    return min(seasons) if seasons else None


def _career_war_first(con: sqlite3.Connection, player_key: str) -> int | None:
    row = con.execute(
        "SELECT payload_json FROM career_war WHERE player_key = ?", (player_key,)
    ).fetchone()
    if not row:
        return None
    try:
        seasons = (json.loads(row["payload_json"]) or {}).get("seasons") or {}
    except (TypeError, ValueError):
        return None
    years = [int(k) for k in seasons if str(k).isdigit()]
    return min(years) if years else None


def _plausible_game_date(iso: str) -> bool:
    """MLB debuts cannot fall in the offseason dead zone (mid-Nov .. Feb).
    Filters the 40-man-selection dates (2019-11-20 etc.) that a few
    roster_status payloads carry in mlb_debut_date."""
    try:
        month, day = int(iso[5:7]), int(iso[8:10])
    except (ValueError, IndexError):
        return False
    if month in (12, 1, 2):
        return False
    if month == 11 and day >= 10:
        return False
    return True


# -------------------------------------------------------------- classification
def build_plan(con: sqlite3.Connection):
    """Classify every 2026-stamped auto-detect debut snapshot.

    Returns (veterans, same_season, no_target, clean_count); the first three
    are lists of dicts with the per-row evidence and repair target."""
    veterans, same_season, no_target = [], [], []
    clean = 0
    for r in con.execute(CANDIDATE_SQL):
        pk = r["player_key"]
        snap = r["snapshot_date"]
        rs = _roster_debut(con, pk)
        cs = _career_stats_first_mlb(con, pk)
        cw = _career_war_first(con, pk)
        career_first = min([v for v in (cs, cw) if v is not None], default=None)
        evidence_years = [int(rs[:4])] if rs else []
        if career_first is not None:
            evidence_years.append(career_first)
        evidence_year = min(evidence_years) if evidence_years else None

        target, target_src, conflict = None, None, ""
        if rs and _plausible_game_date(rs) and rs < snap:
            target, target_src = rs, "roster_status"
            if career_first is not None and int(rs[:4]) != career_first:
                conflict = f"roster_status year {rs[:4]} vs career first MLB season {career_first}"
        elif career_first is not None and career_first < int(snap[:4]):
            target, target_src = f"{career_first}-04-01", "career_first_season"

        row = {"id": r["id"], "player_key": pk, "player_name": r["player_name"],
               "old": snap, "inserted_at": r["inserted_at"], "rs": rs, "cs": cs,
               "cw": cw, "target": target, "target_src": target_src,
               "conflict": conflict}
        if evidence_year is None or evidence_year >= int(snap[:4]):
            # not a veteran: either a clean 2026 debut or a same-season misdate
            if rs and rs < snap:
                same_season.append(row)
            else:
                clean += 1
        elif target is None:
            no_target.append(row)
        else:
            veterans.append(row)
    return veterans, same_season, no_target, clean


def _print_rows(rows, header):
    print(header)
    if not rows:
        print("  (none)")
        return
    for w in rows:
        tgt = f"-> {w['target']} [{w['target_src']}]" if w["target"] else "-> NO TARGET"
        extra = f"  CONFLICT: {w['conflict']}" if w["conflict"] else ""
        print(f"  id={w['id']} {w['player_key']} ({w['player_name']}) "
              f"stamped={w['old']} rs={w['rs']} career_first={w['cs']}/{w['cw']} {tgt}{extra}")


# ------------------------------------------------------------------------ main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(ROOT / "prospects.db"),
                    help="path to prospects.db (default: repo root)")
    ap.add_argument("--apply", action="store_true",
                    help="execute the repair (default is dry-run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report only (the default; explicit flag for symmetry)")
    ap.add_argument("--backup", default=None,
                    help="path to a fresh backup of the DB (required with --apply)")
    ap.add_argument("--expect", type=int, default=EXPECTED_ROWS,
                    help=f"expected veteran repair rowcount (default {EXPECTED_ROWS}); "
                         "the run aborts when the actual count strays >25%% from this")
    ap.add_argument("--delete-spurious", action="store_true",
                    help="DELETE rows with no resolvable true debut date "
                         "(default: flag them and leave them in place)")
    ap.add_argument("--include-same-season", action="store_true",
                    help="also re-date same-season misdates (2026 debuts stamped "
                         "with a later 2026 run date); default scope is the "
                         "veteran class only")
    args = ap.parse_args(argv)
    if args.apply and args.dry_run:
        ap.error("--apply and --dry-run are mutually exclusive")
    apply = args.apply

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"no DB at {db_path} — nothing to do")
        return 1

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        veterans, same_season, no_target, clean = build_plan(con)
        print(f"2026-stamped auto-detect debut snapshots: "
              f"{len(veterans) + len(same_season) + len(no_target) + clean} "
              f"({clean} clean 2026 debuts left alone)\n")
        _print_rows(veterans, f"VETERAN run-date stamps to re-date ({len(veterans)}):")
        print()
        _print_rows(same_season,
                    f"same-season misdates ({len(same_season)}) — "
                    f"{'repairing (--include-same-season)' if args.include_same_season else 'NOT repaired by default; pass --include-same-season'}:")
        print()
        _print_rows(no_target,
                    f"deletion-only candidates ({len(no_target)}) — no resolvable true debut date; "
                    f"{'DELETING (--delete-spurious)' if args.delete_spurious else 'left in place; pass --delete-spurious to remove'}:")
        conflicts = [w for w in veterans if w["conflict"]]
        if conflicts:
            print(f"\nevidence conflicts for owner review ({len(conflicts)}) — "
                  "re-dated to roster_status.mlb_debut_date, career tables disagree "
                  "(possible name-slug collision in career payloads):")
            for w in conflicts:
                print(f"  {w['player_key']}: {w['conflict']}")

        if not veterans and not no_target and not (args.include_same_season and same_season):
            print("\nnothing to repair — the 2026 run-date stamps are already fixed (idempotent no-op)")
            return 0

        # ---- preflight assertions ---------------------------------------
        lo = int(args.expect * (1 - COUNT_TOLERANCE))
        hi = round(args.expect * (1 + COUNT_TOLERANCE))
        if veterans and not (lo <= len(veterans) <= hi):
            print(f"\nABORT: veteran repair count {len(veterans)} is outside the expected "
                  f"band [{lo}, {hi}] (expected ~{args.expect}); re-scope or pass --expect")
            return 1
        print(f"\npreflight OK: {len(veterans)} veteran re-dates within expected band [{lo}, {hi}]; "
              f"{len(no_target)} deletion-only; {len(same_season)} same-season")

        updates = list(veterans) + (list(same_season) if args.include_same_season else [])
        deletes = list(no_target) if args.delete_spurious else []
        if not updates and not deletes:
            print("\nnothing actionable under the current flags — no-op")
            return 0

        if not apply:
            print(f"\nDRY-RUN: would execute -> {UPDATE_SQL}")
            print(f"DRY-RUN: {len(updates)} UPDATEs" +
                  (f" + {len(deletes)} DELETEs ({DELETE_SQL})" if deletes else ""))
            print("DRY-RUN: re-run with --apply (after a backup) to execute")
            return 0

        # ---- backup gate (apply only) -----------------------------------
        bkp = find_fresh_backup(db_path, args.backup)
        if bkp is None:
            print("\nABORT: --apply requires a fresh backup (<24h) of the DB;")
            print(_backup_hint(db_path))
            return 1
        print(f"backup accepted: {bkp}")

        # ---- apply inside one transaction --------------------------------
        con.execute("BEGIN IMMEDIATE")
        try:
            for w in updates:
                n = con.execute(UPDATE_SQL, (w["target"], w["id"], w["old"])).rowcount
                if n != 1:
                    raise RuntimeError(
                        f"update for id={w['id']} ({w['player_key']}) touched {n} rows, expected 1")
            for w in deletes:
                n = con.execute(DELETE_SQL, (w["id"],)).rowcount
                if n != 1:
                    raise RuntimeError(
                        f"delete for id={w['id']} ({w['player_key']}) touched {n} rows, expected 1")
            # verification inside the transaction: the repaired rows must be
            # gone from a fresh classification pass
            v2, s2, n2, _ = build_plan(con)
            if v2 or (args.delete_spurious and n2) or (args.include_same_season and s2):
                raise RuntimeError(
                    f"post-apply recheck still finds {len(v2)} veteran / "
                    f"{len(s2)} same-season / {len(n2)} no-target rows")
            con.commit()
        except Exception as exc:  # noqa: BLE001 - roll back on ANY failure
            con.rollback()
            print(f"ABORT: rolled back — {exc}")
            return 1
        print(f"re-dated {len(updates)} debut snapshots"
              + (f", deleted {len(deletes)} spurious rows" if deletes else "")
              + "; post-apply recheck clean")
        print("next: rebuild exports (run_monthly rebuild-only hook) and restamp the "
              "production golden — debut labels feed the eFV dataset")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
