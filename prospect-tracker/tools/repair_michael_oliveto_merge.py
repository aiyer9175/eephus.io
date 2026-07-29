# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_michael_oliveto_merge.py - one-off repair for the michael_oliveto
identity fracture.

THE INVERSE OF THE VALDEZ / CASTILLO CASES. Those were two humans sharing one
key, and the fix was to SPLIT the newcomer onto a discriminated key. This is
ONE human spread across THREE keys, so the fix is a MERGE, and a merge destroys
history if the wrong survivor is chosen. The survivor is therefore justified
below from the data rather than from the slug's appearance.

THE HUMAN (resolved against StatsAPI, not from memory):

    mlbam 834672  Michael Oliveto  b. 2007-02-03  C  West Islip NY
    Detroit Tigers, 2025 draft CB-A pick 34 out of Hauppauge HS (NY),
    $2,447,500 bonus, currently Lakeland Flying Tigers (A).

StatsAPI /people/search returns exactly ONE Michael Oliveto. There is no
second human anywhere in this cluster.

THE THREE KEYS, all carrying player_name "Michael Oliveto", position C,
org DET and birth_date 2007-02-03:

  michael_oliveto              THE SURVIVOR. Bare normalize_key() output.
  michael_oliveto__noid        fork, 1 FanGraphs snapshot (2025-07-31).
  michael_oliveto__sa3069256   fork, 1 FanGraphs snapshot (2026-02-12),
                               plus 6 trade_value_history rows.

WHY THE BARE KEY IS THE SURVIVOR (five independent joins agree):
  1. player_photos binds mlbam 834672 -> michael_oliveto.
  2. data/rosters_by_org.json binds mlbam 834672 -> michael_oliveto.
  3. draft_players.promoted_key for draft_2025_michael_oliveto is
     michael_oliveto.
  4. It owns every piece of real performance data: career_stats, the 2026
     statline, statcast_metrics, zone_metrics, 44 metric_snapshots and 21 of
     the 27 trade_value_history rows.
  5. It is what normalize_key("Michael Oliveto") produces, so every name-only
     ingest lands there. The suffixes are FanGraphs-PID artifacts, not names.

WHY THE FORKS ARE THE SAME HUMAN AND NOT A SECOND ONE:
  - identical birth_date, position, org and player_name on all three;
  - identical acquisitions row (2025 draft, CB-A, pick 34, $2,447,500,
    Hauppauge HS (NY));
  - the fork player_transactions payloads are byte-identical 7-event PREFIXES
    of the survivor's 11-event StatsAPI log;
  - the fork roster_status payloads are strict subsets of the survivor's;
  - decisively, the FanGraphs "2026tradedeadline" snapshot sitting ON THE BARE
    KEY carries _extras.fg_player_id_str == "sa3069256". The suffix that names
    a fork is this same human's own FanGraphs id.

ROOT CAUSE (reported, not fixed here - fangraphs_csv.py is out of lane):
fangraphs_csv._canonical_owners() scores the PIDs seen for a slug by
(cycle_count, max_fv). Oliveto appeared once with pid None (the 2025-07-31
board, before he had a FanGraphs minor-league page) and once with pid
"sa3069256" (2026-02-12), a 1-1 tie on both terms. The None entry sorted
first, so canonical_pid came back None and the "__all_noid__" sentinel fired,
which suffixes EVERY row - that is why neither of those two snapshots kept the
bare key. A later run that saw only "sa3069256" had nothing to tie against and
wrote the bare key. Hence one human, three keys.

THE SERVED DAMAGE this repairs. The published board row is the fork:
data/timeseries.json carries player_key michael_oliveto__sa3069256 with
mlbam_id null, statline null, career_stats [], career_war {}, statcast_metrics
null, zone_metrics null and the stale acquisition row, while every one of
those values exists in the DB under the bare key. consensus.build_timeseries
dedupes by normalized player_name and keeps whichever non-"__noid" key it
meets first, so the winner is not stable within a run: the 2026-07-24/25
builds swung this player 149 places on the top-500 board with no new
information, and the live row still shows consensus_live_rank_delta 193.

THE REPAIR:
  (a) the SURVIVOR is never re-keyed. michael_oliveto keeps everything.
  (b) fork rows that carry information the survivor lacks are MOVED onto the
      survivor (the two FanGraphs snapshots, the 5 non-colliding
      trade_value_history rows).
  (c) fork rows that are provable duplicates of a fresher survivor row are
      DELETED, each printed in full first. "Provable" is checked per table by
      _redundancy_check below, never assumed; a fork row that fails its check
      is reported as ambiguous and LEFT ALONE.
  (d) rows that cannot be attributed with confidence are LISTED and left
      alone. The trade_value_history row for 2026-07-24 exists under BOTH
      keys with different values and the composite primary key
      (player_key, snapshot_date) cannot hold both. That one row is an OWNER
      DECISION and this script never touches it.

Unique/primary-key constraints are discovered at runtime from PRAGMA
index_list / PRAGMA table_info over sqlite_master rather than hardcoded, so a
schema change cannot silently turn a move into a constraint violation.

Idempotent: re-running after --apply reports "already merged" and changes
nothing.

NOTE ON THE AUDIT: data/timeseries.json is BUILT from the DB, so
test_identity_collisions still reports michael_oliveto__sa3069256 until the
next export regenerates the board, exactly as with the carlos_castillo repair.
That is expected and must not be forced green by hand.

Usage:
    python tools/repair_michael_oliveto_merge.py            # dry run
    python tools/repair_michael_oliveto_merge.py --apply    # write
    python tools/repair_michael_oliveto_merge.py --db PATH  # other DB
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

SURVIVOR = "michael_oliveto"
FORKS = ("michael_oliveto__noid", "michael_oliveto__sa3069256")

MLBAM = 834672
BIRTH = "2007-02-03"
POSITION = "C"
ORG = "DET"
NAME = "Michael Oliveto"

DEFAULT_DB = Path(__file__).resolve().parent.parent / "prospects.db"


def _p(action: str, *detail):
    print(f"  [{action}] " + " ".join(str(d) for d in detail))


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------

def _tables_with_player_key(con) -> list[str]:
    """Every table carrying a player_key column, from sqlite_master."""
    names = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    out = []
    for t in names:
        cols = [c[1] for c in con.execute(f'PRAGMA table_info("{t}")')]
        if "player_key" in cols:
            out.append(t)
    return out


def _discriminators(con, table: str) -> list[tuple[str, ...]]:
    """Column tuples that must stay unique alongside player_key.

    Returns, for every PRIMARY KEY or UNIQUE constraint that INCLUDES
    player_key, the remaining columns of that constraint. An empty tuple means
    player_key alone is unique, so the survivor having any row at all is a
    collision. A table with no such constraint returns [], meaning a rekey can
    never collide.
    """
    out: list[tuple[str, ...]] = []

    pk_cols = [c[1] for c in con.execute(f'PRAGMA table_info("{table}")')
               if c[5]]
    if "player_key" in pk_cols:
        out.append(tuple(c for c in pk_cols if c != "player_key"))

    for idx in con.execute(f'PRAGMA index_list("{table}")'):
        # (seq, name, unique, origin, partial)
        if not idx[2]:
            continue
        cols = [r[2] for r in con.execute(f'PRAGMA index_info("{idx[1]}")')]
        if "player_key" in cols:
            rest = tuple(c for c in cols if c != "player_key")
            if rest not in out:
                out.append(rest)
    return out


# ---------------------------------------------------------------------------
# Per-table redundancy proofs. A fork row may only be DELETED when the
# survivor demonstrably already carries everything it holds.
# ---------------------------------------------------------------------------

def _tx_events(payload) -> set:
    try:
        rows = json.loads(payload or "[]")
    except (ValueError, TypeError):
        return set()
    if not isinstance(rows, list):
        return set()
    return {(r.get("date"), r.get("type_code"), r.get("description"))
            for r in rows if isinstance(r, dict)}


def _json_obj(payload) -> dict | None:
    try:
        obj = json.loads(payload or "")
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _redundancy_check(table: str, fork_row, surv_row) -> tuple[bool, str]:
    """(is_redundant, why). Conservative: unknown table -> not redundant."""
    f, s = dict(fork_row), dict(surv_row)

    if table == "players":
        fields = ("player_name", "position", "org", "is_pitcher", "birth_date")
        diff = [k for k in fields if f.get(k) != s.get(k)]
        if diff:
            return False, f"players rows differ on {diff}"
        return True, "identical name/position/org/is_pitcher/birth_date"

    if table == "acquisitions":
        # team_name and pick_round differ in FORMATTING only ("Detroit Tigers"
        # vs "DET", "CB-A" vs 2). The survivor's row is the fresher MLB StatsAPI
        # form and agrees with draft_results (round_label CB-A, pick_in_round 2),
        # so only the substantive fields are compared.
        fields = ("method", "year", "pick_overall", "bonus_usd", "school")
        diff = [k for k in fields if f.get(k) != s.get(k)]
        if diff:
            return False, f"acquisitions rows differ on {diff}"
        return True, ("same draft event (method/year/pick_overall/bonus/school); "
                      "survivor row is the fresher StatsAPI form")

    if table == "player_transactions":
        fe = _tx_events(f.get("payload_json"))
        se = _tx_events(s.get("payload_json"))
        if not fe:
            return False, "fork transaction payload unreadable"
        extra = fe - se
        if extra:
            return False, f"fork holds {len(extra)} transaction(s) the survivor lacks"
        return True, (f"fork's {len(fe)} transactions are a subset of the "
                      f"survivor's {len(se)}")

    if table == "roster_status":
        fo, so = _json_obj(f.get("payload_json")), _json_obj(s.get("payload_json"))
        if fo is None or so is None:
            return False, "roster_status payload unreadable"
        missing = [k for k in fo if k not in so]
        if missing:
            return False, f"fork holds roster_status keys the survivor lacks: {missing}"
        conflict = [k for k, v in fo.items() if so.get(k) != v]
        if conflict:
            return False, f"roster_status values disagree on {conflict}"
        return True, "fork payload is a subset of the survivor's, no value disagrees"

    return False, f"no redundancy proof defined for table {table!r}"


# ---------------------------------------------------------------------------
# Preconditions. Refuse to merge anything the evidence does not support.
# ---------------------------------------------------------------------------

def _verify_identity(con, ambiguous: list[str]) -> bool:
    print("-- preconditions --")
    rows = {r["player_key"]: r for r in con.execute(
        "SELECT * FROM players WHERE player_key IN (?, ?, ?)",
        (SURVIVOR,) + FORKS)}

    surv = rows.get(SURVIVOR)
    if surv is None:
        ambiguous.append(
            f"players[{SURVIVOR}] does not exist. The survivor must already "
            "hold the identity before anything is merged into it. ABORT.")
        return False

    for field, want in (("player_name", NAME), ("position", POSITION),
                        ("org", ORG), ("birth_date", BIRTH)):
        if surv[field] != want:
            ambiguous.append(
                f"players[{SURVIVOR}].{field} is {surv[field]!r}, expected "
                f"{want!r} (StatsAPI mlbam {MLBAM}). ABORT.")
            return False
    _p("ok", f"survivor {SURVIVOR}: {NAME} / {POSITION} / {ORG} / b.{BIRTH}")

    present = 0
    for fk in FORKS:
        r = rows.get(fk)
        if r is None:
            _p("ok", f"fork {fk}: no players row (already merged)")
            continue
        present += 1
        bad = [fld for fld, want in (("player_name", NAME), ("position", POSITION),
                                     ("org", ORG), ("birth_date", BIRTH))
               if r[fld] != want]
        if bad:
            ambiguous.append(
                f"players[{fk}] disagrees with the survivor on {bad}. That is "
                "the signature of a SECOND HUMAN, not a fork. ABORT.")
            return False
        _p("ok", f"fork {fk}: same human ({POSITION}/{ORG}/b.{BIRTH})")

    photo = con.execute(
        "SELECT mlbam_id, player_key FROM player_photos WHERE mlbam_id = ?",
        (MLBAM,)).fetchone()
    if photo is None:
        _p("warn", f"player_photos has no row for mlbam {MLBAM}")
    elif photo["player_key"] == SURVIVOR:
        _p("ok", f"player_photos binds mlbam {MLBAM} -> {SURVIVOR}")
    else:
        _p("warn", f"player_photos binds mlbam {MLBAM} -> "
                   f"{photo['player_key']!r}, not the survivor. The merge "
                   "makes the survivor the only key that exists; rebind after "
                   "applying.")

    if present == 0:
        _p("ok", "no fork players rows remain")
    return True


# ---------------------------------------------------------------------------
# The merge
# ---------------------------------------------------------------------------

def repair(db_path: Path, apply: bool) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== repair_michael_oliveto_merge [{mode}] db={db_path} ===")
    print(f"    survivor: {SURVIVOR}  (mlbam {MLBAM}, b.{BIRTH}, {POSITION}/{ORG})")
    print(f"    forks:    {', '.join(FORKS)}\n")
    if not db_path.exists():
        print(f"FATAL: db not found: {db_path}")
        return 2

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    changes = 0
    ambiguous: list[str] = []

    if not _verify_identity(con, ambiguous):
        print("\n-- REFUSED --")
        for a in ambiguous:
            _p("abort", a)
        con.rollback()
        con.close()
        return 1

    tables = _tables_with_player_key(con)
    print(f"\n-- scanning {len(tables)} table(s) carrying player_key --")

    touched_any = False
    for table in tables:
        fork_rows = con.execute(
            f'SELECT rowid AS _rid, * FROM "{table}" '
            "WHERE player_key IN (?, ?) ORDER BY player_key",
            FORKS).fetchall()
        if not fork_rows:
            continue
        touched_any = True
        discs = _discriminators(con, table)
        print(f"\n-- {table} ({len(fork_rows)} fork row(s), "
              f"unique-with-player_key: {discs if discs else 'none'}) --")

        for row in fork_rows:
            fk = row["player_key"]
            label = _describe(table, row)

            # Does moving this row onto the survivor violate a constraint?
            clash = None
            for rest in discs:
                where = " AND ".join(f'"{c}" IS ?' for c in rest)
                sql = f'SELECT rowid AS _rid, * FROM "{table}" WHERE player_key IS ?'
                params: list = [SURVIVOR]
                if rest:
                    sql += " AND " + where
                    params += [row[c] for c in rest]
                hit = con.execute(sql, params).fetchone()
                if hit is not None:
                    clash = (rest, hit)
                    break

            if clash is None:
                _p("rekey", f"{table}: {label}: {fk} -> {SURVIVOR}")
                con.execute(
                    f'UPDATE "{table}" SET player_key = ? WHERE rowid = ?',
                    (SURVIVOR, row["_rid"]))
                changes += 1
                continue

            rest, hit = clash
            redundant, why = _redundancy_check(table, row, hit)
            if redundant:
                _p("drop", f"{table}: {label}: duplicate of the survivor's row "
                           f"({why}); deleting the fork copy")
                _p("dropped-row", _full(table, row))
                con.execute(f'DELETE FROM "{table}" WHERE rowid = ?',
                            (row["_rid"],))
                changes += 1
            else:
                on = ", ".join(rest) if rest else "player_key alone"
                ambiguous.append(
                    f"{table}: fork row {label} collides with an existing "
                    f"{SURVIVOR} row on ({on}) and is NOT a proven duplicate "
                    f"({why}). LEFT ALONE - owner decision.\n"
                    f"        fork    : {_full(table, row)}\n"
                    f"        survivor: {_full(table, hit)}")

    if not touched_any:
        _p("ok", "no fork rows anywhere: already merged")

    # ------------------------------------------------------------------
    # Advisory: the earlier repair script points the binding the other way.
    # ------------------------------------------------------------------
    print("\n-- advisories --")
    other = db_path.parent / "tools" / "repair_identity_bindings.py"
    if other.exists():
        try:
            txt = other.read_text(encoding="utf-8")
        except OSError:
            txt = ""
        if f'"{SURVIVOR}", "michael_oliveto__sa3069256"' in txt:
            _p("advisory",
               "tools/repair_identity_bindings.py still carries a G2 ATTACH "
               f"row moving mlbam {MLBAM} from {SURVIVOR} to "
               "michael_oliveto__sa3069256. That was correct while the fork "
               "was the published key; after this merge it would rebind the "
               "id to a key that no longer exists. Retire that ATTACH entry.")

    _p("advisory",
       "data/timeseries.json is BUILT from this DB. test_identity_collisions "
       "keeps reporting michael_oliveto__sa3069256 until the next export "
       "regenerates the board. Do not force it green.")

    if ambiguous:
        print("\n-- AMBIGUOUS rows (listed, NOT touched) --")
        for a in ambiguous:
            _p("ambiguous", a)

    if apply:
        con.commit()
        print(f"\n=== APPLIED: {changes} write(s) committed; "
              f"{len(ambiguous)} row(s) left for the owner ===")
    else:
        con.rollback()
        print(f"\n=== DRY-RUN: {changes} write(s) planned; "
              f"{len(ambiguous)} row(s) would be left for the owner. "
              "Re-run with --apply to execute ===")
    con.close()
    return 0


def _describe(table: str, row) -> str:
    d = dict(row)
    for keys in (("snapshot_date", "interval_label"), ("snapshot_date",),
                 ("season",)):
        if all(k in d for k in keys):
            return " ".join(str(d[k]) for k in keys)
    return "row"


def _full(table: str, row) -> str:
    skip = {"_rid", "payload_json", "tools_json"}
    d = {k: v for k, v in dict(row).items() if k not in skip and v is not None}
    return json.dumps(d, default=str, ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Merge the three michael_oliveto keys onto the survivor "
                    "(one human, three keys).")
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help=f"path to prospects.db (default: {DEFAULT_DB})")
    args = ap.parse_args()
    return repair(args.db, apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
