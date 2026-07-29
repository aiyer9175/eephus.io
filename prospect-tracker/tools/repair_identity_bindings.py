# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_identity_bindings.py - targeted identity repair by ATTACHING IDS.

NO player_key is ever renamed and no key is ever re-mapped. Every write is
guarded by the exact value it expects to find, so the tool is idempotent
and refuses to act on a row that has drifted since the evidence was taken.

Evidence for every decision below is a StatsAPI /people/{id} birthDate plus
the player's own /stats?stats=yearByYear&group=fielding&leagueListId=mlb_milb
log, cross-checked against prospects.db players.birth_date, the embedded
mlbam_id on the key's 2026 statline, and data/rosters_by_org.json.

Five repair groups:

  G1 unbind_wrong_id   player_photos has its uniqueness constraint on
                       mlbam_id ALONE, so two ids can point at one key. For
                       each of the 11 double-bound keys the id whose
                       birthDate does NOT match players.birth_date is
                       unbound (player_key -> NULL). The photo context row
                       itself is kept, so the OTHER human is NOT re-minted
                       as a board record by mlbam_ingest; he is reported.

  G2 attach_id         michael_oliveto__sa3069256 is the served board row
                       (rank 337) but mlbam 834672 was bound to the
                       duplicate key "michael_oliveto", which is on no board
                       slice. All three michael_oliveto* keys are the SAME
                       human (identical birth_date 2007-02-03); the binding
                       is moved onto the served key.

  G3 merged_attrs      Four active rows were assembled from two humans: the
                       performance_ingest snapshot that minted them (its
                       position + org) came from one person, the birth_date
                       and the roster join from the other. The snapshot FV
                       is the flat provisional 35.0 that mlbam_ingest writes
                       for EVERY performance_ingest row, so correcting its
                       position/org destroys no source opinion.

  G4 position_kind     Seven keys whose players.position contradicts the
                       side of the ball of the mlbam id the key is actually
                       bound to. Only the players row is corrected. The
                       stale SNAPSHOTS that belong to the other human are
                       reported, never moved: moving them needs a new key.

  G5 is_pitcher        players.is_pitcher is written by NOTHING in the
                       pipeline (both INSERT INTO players paths omit the
                       column, DEFAULT 0), so it is frozen at whatever a
                       long-removed writer left and goes stale on every
                       position change. Recomputed from the position label.

Usage:
    python tools/repair_identity_bindings.py             # dry run
    python tools/repair_identity_bindings.py --apply     # write (backs up first)
    python tools/repair_identity_bindings.py --apply --no-backup
    python tools/repair_identity_bindings.py --db PATH
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
DEFAULT_DB = _HERE.parent / "prospects.db"
sys.path.insert(0, str(_HERE.parent))

from identity_audit import position_kind  # noqa: E402

# ---------------------------------------------------------------------------
# G1 - the 11 double-bound keys.
# (key, keep_id, keep_birth, drop_id, drop_birth, drop_note)
# keep_birth is what players.birth_date must equal for the repair to run.
# ---------------------------------------------------------------------------
UNBIND = [
    ("alexander_de_los_santos", 808167, "2006-08-23", 822195, "2009-02-11",
     "DR RHP, 3 seasons younger"),
    ("carlos_gonzalez", 801262, "2003-11-20", 808712, "2006-02-14",
     "VEN RHP, KCR DSL; already tracked as mlbam_808712 in xfv_ungraded"),
    ("christian_rodriguez", 815184, "2004-10-12", 691010, "2002-01-12",
     "USA RHP"),
    ("david_hernandez", 830395, "2005-08-31", 829967, "2007-05-21",
     "MEX RHP"),
    ("jesus_flores", 808222, "2005-03-16", 837965, "2008-11-06",
     "VEN C, TEX DSL Rangers Blue; already tracked as mlbam_837965 in xfv_ungraded"),
    ("jose_perez", 699077, "2004-03-12", 814545, "2005-05-15",
     "DR SS"),
    ("juan_medina", 821265, "2006-10-28", 839782, "2006-09-19",
     "DR RHP"),
    ("luis_carrasco", 816263, "2005-01-22", 682918, "2001-12-19",
     "VEN RHP"),
    ("luis_leon", 830020, "2008-02-04", 828783, "2006-07-21",
     "CUB SS"),
    ("robinson_martinez", 660822, "1998-03-20", 842067, "2007-12-04",
     "DR RHP, 9 seasons younger"),
    ("ryan_brown", 811286, "2002-10-09", 688664, "2000-11-02",
     "USA RHP"),
]

# ---------------------------------------------------------------------------
# G2 - move a binding onto the served duplicate key. Same human, no rename.
# (mlbam_id, from_key, to_key, shared_birth)
# ---------------------------------------------------------------------------
#
# One human, three keys (michael_oliveto, michael_oliveto__noid,
# michael_oliveto__sa3069256; all b.2007-02-03, all C/DET).
# consensus.build_timeseries collapses duplicate rows by normalized
# player_name and keeps whichever non-"__noid" key it meets first, so the
# PUBLISHED key is not stable within a single pipeline run: the
# mid-run export at 11:01:03Z served "michael_oliveto" (rank 486, id
# attached) and the final export five minutes later served
# "michael_oliveto__sa3069256" (rank 336, id null). Both FINISHED builds
# (2026-07-24 and 2026-07-25) published __sa3069256 and neither published
# the plain key on any slice, so the binding follows the published record.
# Merging the three keys is a re-key and stays an owner decision.
ATTACH: list[tuple[int, str, str, str]] = [
    (834672, "michael_oliveto", "michael_oliveto__sa3069256", "2007-02-03"),
]

# ---------------------------------------------------------------------------
# G3 - merged-record attribute repair.
# key -> (bound_id, birth, players_pos_now, players_pos_new, players_org_now,
#         players_org_new, snap_source, snap_pos_now, snap_pos_new,
#         snap_org_now, snap_org_new)
# ---------------------------------------------------------------------------
MERGED = [
    dict(key="jesus_flores", bound_id=808222, birth="2005-03-16",
         pos_now="DH", pos_new="RHP", org_now="TEX", org_new="MIL",
         snap_source="performance_ingest", snap_pos_now="DH", snap_pos_new="RHP",
         snap_org_now="TEX", snap_org_new="MIL",
         why="808222 has pitched every season 2023-2026 (DSL Brewers 2 -> "
             "Carolina -> Wisconsin); DH/TEX came from catcher 837965"),
    dict(key="carlos_gonzalez", bound_id=801262, birth="2003-11-20",
         pos_now="P", pos_new="C", org_now="KCR", org_new="SEA",
         snap_source="performance_ingest", snap_pos_now="P", snap_pos_new="C",
         snap_org_now="KCR", snap_org_new="SEA",
         why="801262 has caught every season 2022-2026 for DSL/ACL Mariners; "
             "P/KCR came from RHP 808712"),
    dict(key="omar_calcurian", bound_id=821598, birth="2005-05-25",
         pos_now="2B", pos_new="RHP", org_now="SFG", org_new="SFG",
         snap_source="performance_ingest", snap_pos_now="2B", snap_pos_new="RHP",
         snap_org_now="SFG", snap_org_new="SFG",
         why="821598 is the only Omar Calcurian on any roster and has pitched "
             "in relief for DSL Giants Orange 2024-2026 (0 games at any other "
             "position)"),
    dict(key="michael_braswell_iii", bound_id=691771, birth="2002-08-29",
         pos_now="SS", pos_new="RHP", org_now="KCR", org_new="KCR",
         snap_source="performance_ingest", snap_pos_now="SS", snap_pos_new="RHP",
         snap_org_now="KCR", snap_org_new="KCR",
         why="691771 is the only Michael Braswell III on any roster; StatsAPI "
             "primaryPosition P, pitchHand R, draftYear 2025, and his entire "
             "fielding log is 2026 ACL Royals as a pitcher"),
]

# ---------------------------------------------------------------------------
# G4 - players.position contradicts the bound identity's side of the ball.
# (key, bound_id, birth, pos_now, pos_new, isp_now, isp_new, stale_snapshot_note)
# pos_new is taken from the SNAPSHOT LINEAGE OF THE BOUND HUMAN, not from the
# StatsAPI primaryPosition (which defaults to "P" for gameless records).
# ---------------------------------------------------------------------------
KIND_FIX = [
    ("adrian_rodriguez", 689583, "2001-05-18", "SS", "SIRP", 1, 1,
     "all 6 FanGraphs snapshots 2023-2025 say SIRP/TEX; players.position SS "
     "is the only hitter artifact on the record"),
    ("jose_fermin", 820862, "2001-11-28", "SS", "SIRP", 0, 1,
     "OWNER: the 5 CLE/STL 'SS' snapshots 2019-2021 belong to a DIFFERENT "
     "Jose Fermin - the bound id 820862 is the DR RHP who debuted 2025-04-26 "
     "for LAA"),
    ("jose_fernandez", 699912, "2003-09-22", "RHP", "SS", 1, 0,
     "OWNER: the 3 'RHP/MIA' Pipeline snapshots 2012-2013 belong to the late "
     "Marlins ace - the bound id 699912 is the VEN infielder who debuted "
     "2026-03-31 for ARI"),
    ("luis_castillo", 699127, "2003-10-11", "RHP", "LF", 1, 0,
     "OWNER: the 2 'RHP' snapshots 2017 belong to the CIN/SEA starter - the "
     "bound id 699127 is the DR outfielder on the 2023 MIL lists"),
    ("luis_rodriguez", 812160, "2003-12-29", "OF", "SP", 0, 1,
     "OWNER: the LAD 'OF/CF' snapshots 2019-2022 and the STL 'C' row belong "
     "to other humans - the bound id 812160 is the VEN pitcher on the 2022-"
     "2023 NYM lists"),
    ("wilmer_flores", 695865, "2001-02-20", "2B", "MIRP", 0, 1,
     "OWNER: the '2B / Office of the Commissioner' Pipeline snapshots 2011-"
     "2014 and 2024 belong to the MLB infielder - the bound id 695865 is the "
     "VEN pitcher in the DET system"),
]

# Reported, never written: the players row already matches the bound human.
KIND_REPORT_ONLY = [
    ("jared_jones", 683003,
     "players row (RHP / is_pitcher 1) already matches the bound id, the PIT "
     "RHP who debuted 2024-03-30. The two 2026 FanGraphs '1B/PIT' snapshots "
     "are a SECOND Jared Jones in the same organization. Splitting them needs "
     "a new key -> OWNER DECISION."),
    ("jandaniel_gonzalez", None,
     "players row says RHP/SDP, the only snapshot says C/SDP, and the key has "
     "NO mlbam binding at all, so nothing can adjudicate it -> OWNER DECISION."),
    ("alex_weingartner", None,
     "NOT a defect: TWP (two-way) vs the draft_signing 'SS' row is a genuine "
     "two-way 2026 draftee. position_kind() maps TWP to the pitcher side by "
     "design; no write."),
    ("michael_oliveto", 834672,
     "ONE human, THREE keys (michael_oliveto, michael_oliveto__noid, "
     "michael_oliveto__sa3069256; all b.2007-02-03, all C/DET). "
     "consensus.build_timeseries dedupes by normalized player_name and keeps "
     "whichever non-__noid key it meets first, so the published key flips "
     "between builds: 2026-07-24 served __sa3069256 at rank 337 with mlbam_id "
     "null, 2026-07-25 served the plain key at rank 486 with 834672 attached. "
     "A 149-place rank swing with no new information. Merging the keys is a "
     "re-key -> OWNER DECISION."),
    ("carlos_castillo", 807962,
     "Newly observed, not in the audit's lists: players row is OF/LAA "
     "(b.2006-02-04) but the 2024 FanGraphs snapshots say SP/PIT. Single "
     "binding, so no C2; the latest snapshot agrees with the players row, so "
     "no D4. Looks like a second two-humans-one-key merge -> OWNER DECISION. "
     "G5 sets is_pitcher 1 -> 0 to match the CURRENT label only."),
]


def _p(action: str, *detail):
    print(f"  [{action}] " + " ".join(str(d) for d in detail))


def _one(con, sql, params=()):
    return con.execute(sql, params).fetchone()


def repair(db_path: Path, apply: bool, do_backup: bool) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== repair_identity_bindings [{mode}] db={db_path} ===")
    if not db_path.exists():
        print(f"FATAL: db not found: {db_path}")
        return 2

    if apply and do_backup:
        stamp = time.strftime("%Y%m%dT%H%M%S")
        backup = db_path.with_name(f"{db_path.stem}.backup-{stamp}.db")
        print(f"\n-- backup --\n  {db_path} -> {backup}")
        # sqlite's online backup API, not a file copy: prospects.db runs in
        # WAL mode, so copying the main file alone can miss committed pages
        # still sitting in the -wal.
        t0 = time.monotonic()
        src = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        dst = sqlite3.connect(backup)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        print(f"  backup complete: {backup} "
              f"({backup.stat().st_size / 1e9:.3f} GB, "
              f"{time.monotonic() - t0:.1f}s)")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    changes = 0
    skipped: list[str] = []
    needs_record: list[str] = []

    # ------------------------------------------------------------------ G1
    print("\n-- G1: unbind the wrong mlbam id on double-bound keys --")
    for key, keep_id, keep_birth, drop_id, drop_birth, note in UNBIND:
        pr = _one(con, "SELECT birth_date FROM players WHERE player_key = ?", (key,))
        drop_row = _one(con, "SELECT player_key FROM player_photos WHERE mlbam_id = ?",
                        (drop_id,))
        keep_row = _one(con, "SELECT player_key FROM player_photos WHERE mlbam_id = ?",
                        (keep_id,))
        if drop_row is None or drop_row["player_key"] != key:
            _p("ok", f"{key}: {drop_id} no longer bound to this key "
                     f"(now {None if drop_row is None else drop_row['player_key']!r})")
            continue
        if pr is None or pr["birth_date"] != keep_birth:
            skipped.append(f"G1 {key}: players.birth_date="
                           f"{None if pr is None else pr['birth_date']!r} != "
                           f"{keep_birth!r} (evidence stale) - NOT touched")
            continue
        if keep_row is None or keep_row["player_key"] != key:
            skipped.append(f"G1 {key}: keeper {keep_id} is bound to "
                           f"{None if keep_row is None else keep_row['player_key']!r}, "
                           "not this key - NOT touched")
            continue
        _p("unbind", f"{key}: player_photos[{drop_id}].player_key -> NULL "
                     f"(b.{drop_birth}, {note}); keeps {keep_id} (b.{keep_birth})")
        needs_record.append(f"mlbam {drop_id} (b.{drop_birth}) - {note}")
        if apply:
            con.execute("UPDATE player_photos SET player_key = NULL WHERE mlbam_id = ?",
                        (drop_id,))
        changes += 1

    # ------------------------------------------------------------------ G2
    print("\n-- G2: attach the id to the served duplicate key --")
    for mid, from_key, to_key, birth in ATTACH:
        row = _one(con, "SELECT player_key FROM player_photos WHERE mlbam_id = ?", (mid,))
        if row is None:
            skipped.append(f"G2 {to_key}: no player_photos row for {mid} - NOT touched")
            continue
        if row["player_key"] == to_key:
            _p("ok", f"{to_key}: already bound to {mid}")
            continue
        if row["player_key"] != from_key:
            skipped.append(f"G2 {to_key}: {mid} is bound to {row['player_key']!r}, "
                           f"expected {from_key!r} - NOT touched")
            continue
        a = _one(con, "SELECT birth_date FROM players WHERE player_key = ?", (from_key,))
        b = _one(con, "SELECT birth_date FROM players WHERE player_key = ?", (to_key,))
        if not a or not b or a["birth_date"] != birth or b["birth_date"] != birth:
            skipped.append(f"G2 {to_key}: birth_date mismatch "
                           f"({from_key}={a and a['birth_date']!r}, "
                           f"{to_key}={b and b['birth_date']!r}, expected {birth!r}) "
                           "- NOT touched (they may not be the same human)")
            continue
        _p("attach", f"player_photos[{mid}].player_key {from_key!r} -> {to_key!r} "
                     f"(same human, b.{birth}; {to_key} is the served board row)")
        if apply:
            con.execute("UPDATE player_photos SET player_key = ? WHERE mlbam_id = ?",
                        (to_key, mid))
        changes += 1

    # ------------------------------------------------------------------ G3
    print("\n-- G3: merged-record attribute repair (players + provisional snapshot) --")
    for m in MERGED:
        key = m["key"]
        pr = _one(con, "SELECT position, org, is_pitcher, birth_date FROM players "
                       "WHERE player_key = ?", (key,))
        if pr is None:
            skipped.append(f"G3 {key}: no players row - NOT touched")
            continue
        if pr["birth_date"] != m["birth"]:
            skipped.append(f"G3 {key}: players.birth_date={pr['birth_date']!r} != "
                           f"{m['birth']!r} - NOT touched")
            continue
        ph = _one(con, "SELECT player_key FROM player_photos WHERE mlbam_id = ?",
                  (m["bound_id"],))
        if ph is None or ph["player_key"] != key:
            skipped.append(f"G3 {key}: bound id {m['bound_id']} points at "
                           f"{None if ph is None else ph['player_key']!r} - NOT touched")
            continue
        if pr["position"] == m["pos_now"] and pr["org"] == m["org_now"]:
            _p("players", f"{key}: position {m['pos_now']!r} -> {m['pos_new']!r}, "
                          f"org {m['org_now']!r} -> {m['org_new']!r}  ({m['why']})")
            if apply:
                con.execute("UPDATE players SET position = ?, org = ?, "
                            "updated_at = datetime('now') WHERE player_key = ?",
                            (m["pos_new"], m["org_new"], key))
            changes += 1
        elif pr["position"] == m["pos_new"] and pr["org"] == m["org_new"]:
            _p("ok", f"{key}: players row already repaired")
        else:
            skipped.append(f"G3 {key}: players row is "
                           f"({pr['position']!r}, {pr['org']!r}), expected "
                           f"({m['pos_now']!r}, {m['org_now']!r}) - NOT touched")

        sn = _one(con, "SELECT id, position, org, fv FROM snapshots WHERE player_key = ? "
                       "AND source = ?", (key, m["snap_source"]))
        if sn is None:
            skipped.append(f"G3 {key}: no {m['snap_source']} snapshot - snapshot NOT touched")
            continue
        if sn["position"] == m["snap_pos_new"] and sn["org"] == m["snap_org_new"]:
            _p("ok", f"{key}: {m['snap_source']} snapshot already repaired")
            continue
        if sn["position"] != m["snap_pos_now"] or sn["org"] != m["snap_org_now"]:
            skipped.append(f"G3 {key}: snapshot is ({sn['position']!r}, {sn['org']!r}), "
                           f"expected ({m['snap_pos_now']!r}, {m['snap_org_now']!r}) "
                           "- NOT touched")
            continue
        if float(sn["fv"] or 0) != 35.0:
            skipped.append(f"G3 {key}: snapshot fv={sn['fv']!r} is not the flat "
                           "provisional 35.0 - NOT touched (it may carry a real opinion)")
            continue
        _p("snapshot", f"{key}: {m['snap_source']} position {m['snap_pos_now']!r} -> "
                       f"{m['snap_pos_new']!r}, org {m['snap_org_now']!r} -> "
                       f"{m['snap_org_new']!r} (fv 35.0 flat provisional, unchanged)")
        if apply:
            con.execute("UPDATE snapshots SET position = ?, org = ? WHERE id = ?",
                        (m["snap_pos_new"], m["snap_org_new"], sn["id"]))
        changes += 1

    # ------------------------------------------------------------------ G4
    print("\n-- G4: players.position vs the side of the ball of the bound id --")
    for key, mid, birth, pos_now, pos_new, isp_now, isp_new, note in KIND_FIX:
        pr = _one(con, "SELECT position, is_pitcher, birth_date FROM players "
                       "WHERE player_key = ?", (key,))
        if pr is None:
            skipped.append(f"G4 {key}: no players row - NOT touched")
            continue
        if pr["position"] == pos_new:
            _p("ok", f"{key}: already {pos_new!r}")
            continue
        if pr["birth_date"] != birth or pr["position"] != pos_now:
            skipped.append(f"G4 {key}: row is ({pr['position']!r}, "
                           f"b.{pr['birth_date']!r}), expected ({pos_now!r}, b.{birth!r})"
                           " - NOT touched")
            continue
        ph = _one(con, "SELECT player_key FROM player_photos WHERE mlbam_id = ?", (mid,))
        if ph is None or ph["player_key"] != key:
            skipped.append(f"G4 {key}: id {mid} is bound to "
                           f"{None if ph is None else ph['player_key']!r} - NOT touched")
            continue
        _p("players", f"{key}: position {pos_now!r} -> {pos_new!r}, is_pitcher "
                      f"{pr['is_pitcher']} -> {isp_new} (bound id {mid}); {note}")
        if apply:
            con.execute("UPDATE players SET position = ?, is_pitcher = ?, "
                        "updated_at = datetime('now') WHERE player_key = ?",
                        (pos_new, isp_new, key))
        changes += 1
    for key, mid, note in KIND_REPORT_ONLY:
        _p("report", f"{key}: {note}")

    # ------------------------------------------------------------------ G5
    print("\n-- G5: recompute players.is_pitcher from the position label --")
    rows = con.execute("SELECT player_key, position, is_pitcher FROM players").fetchall()
    to_1, to_0, unknown = [], [], 0
    for r in rows:
        kind = position_kind(r["position"])
        if kind is None:
            unknown += 1
            continue
        want = 1 if kind == "P" else 0
        if int(r["is_pitcher"] or 0) == want:
            continue
        (to_1 if want else to_0).append(r["player_key"])
    print(f"  rows={len(rows)}  indeterminate_position={unknown}  "
          f"is_pitcher 0->1: {len(to_1)}  1->0: {len(to_0)}")
    for k in to_1[:5]:
        _p("sample 0->1", k)
    for k in to_0[:5]:
        _p("sample 1->0", k)
    if apply and (to_1 or to_0):
        con.executemany("UPDATE players SET is_pitcher = 1 WHERE player_key = ?",
                        [(k,) for k in to_1])
        con.executemany("UPDATE players SET is_pitcher = 0 WHERE player_key = ?",
                        [(k,) for k in to_0])
    changes += len(to_1) + len(to_0)

    # ------------------------------------------------------------------
    print("\n-- needs a NEW record (NOT minted here; owner decision) --")
    for n in needs_record or ["(none)"]:
        _p("owner", n)

    print("\n-- skipped / ambiguous --")
    for s in skipped or ["(none)"]:
        _p("skip", s)

    if apply:
        con.commit()
        print(f"\nCOMMITTED {changes} row writes.")
    else:
        con.rollback()
        print(f"\nDRY-RUN: {changes} row writes would be made. Re-run with --apply.")
    con.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--apply", action="store_true", help="write changes")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip the pre-apply prospects.db copy")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = ap.parse_args()
    return repair(args.db, args.apply, not args.no_backup)


if __name__ == "__main__":
    raise SystemExit(main())
