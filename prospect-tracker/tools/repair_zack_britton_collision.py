# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_zack_britton_collision.py - one-off repair for the zack_britton key
collision (BA_KEEP_FORWARD_READ Part B, docs/efv-v2/BA_KEEP_FORWARD_READ.md;
found by BA_GRADE_IN_CONSENSUS section 7a).

THE BUG. Baseball America's 2023 Blue Jays Top 30 (2023-02-15, rank 24, BA
Grade 40, risk High) printed its 24th player as "Zack Britton", with the
veteran's age (35) and B-T L-L, and baseballamerica_csv.resolve_identities
put the row on the existing key "zack_britton" by an exact slug match. The
row's own text is a different human: the Blue Jays' 2020 fifth-round pick
(136th overall) out of Louisville, a bat-first corner outfielder, Zach
Britton (MLBAM 676309). The key belongs to the veteran left-hander Zack
Britton (MLBAM 502154, MLB debut 2011).

  INCUMBENT  zack_britton, MLBAM 502154: the Pipeline 2011 Orioles Top 30 and
             Top 100 rows, the 2011 debut row, the career_war row.
  NEWCOMER   zach_britton, MLBAM 676309: the BA 2023 Blue Jays row, and the
             2020 draft spine that FanGraphs' 2020 draft board spelled "Zack"
             (draft_2020_zack_britton), which the draft promotion linked to
             the veteran's key and which wrote the newcomer's 2020 TOR draft
             acquisition onto it. The same pick is already promoted correctly
             under draft_2020_zach_britton -> zach_britton.

WHAT IT BROKE. consensus._prune_collision_cluster keeps only the newest
grading cluster of a key when two clusters sit more than eight years apart,
so the 2023 row hid the veteran's whole 2011 history in the served build, and
the board served a Blue Jays outfielder under the veteran's key and name.

THE RESOLUTION IS OUTCOME-BLIND (resolve_ba_row). It reads the printed name,
the board year V, the row's side (BA graded hit/power/run/field/arm, so a
hitter row) and the efv_identity name index of affiliated minor league stat
lines and June draft picks before V. Nothing else: no debut date, no MLB stat
line, no WAR, no label. The printed name's only candidate is 502154, whose
pre-2023 minor league lines are all pitching, so the name conflicts with the
row's side; the one candidate within one letter of the printed name whose
pre-V lines are on the row's side and recent (V - 1 or V - 2) is 676309,
"Zach Britton" (hitting lines 2021 and 2022, 2020 draft pick 136). That id's
key is "zach_britton", the key the database already holds for him
(draft_2020_zach_britton's promotion, acquisitions, mlb_trade_players).

THE REPAIR (follows tools/repair_garrett_wright_collision.py):
  (a) the INCUMBENT is never re-keyed; his rows are verified, not rewritten.
  (b) the NEWCOMER's rows move to "zach_britton":
        - the baseballamerica 2023-02-15 snapshot (org TOR), with the printed
          name corrected to the resolved person's name;
        - draft_canonical_keys[draft_2020_zack_britton].milb_key and
          draft_players[draft_2020_zack_britton].promoted_key;
        - a players row for zach_britton (TOR, hitter; birth_date left NULL,
          as in the precedent, so the next id-driven refresh fills it).
  (c) rows whose only evidence is the merge are removed, and listed:
        - acquisitions[zack_britton], the 2020 TOR draft record, when
          acquisitions[zach_britton] holds the same draft (year, overall pick,
          team);
        - the trades row the board-org inference wrote for zack_britton on
          2023-02-15 (source 'inferred', NYY to TOR), whose only evidence is
          the moved row.
  (d) everything else on the incumbent's key is LISTED and left alone
      (roster_status is refreshed by its own fetch).

WHY THE DATABASE REPAIR ALONE IS NOT ENOUGH (the carlos_castillo lesson): the
ingest pins baseballamerica_csv._BA_ORG_SPLIT_KEYS[("zack_britton", "TOR")]
and scrapers._SPLIT_KEYS[("zack_britton", 676309)] route a re-ingest of the
same row, by board org or by MLBAM id, to "zach_britton".

Idempotent: re-running after --apply reports 0 writes.

Usage:
    python tools/repair_zack_britton_collision.py            # dry run
    python tools/repair_zack_britton_collision.py --apply    # write
    python tools/repair_zack_britton_collision.py --db PATH  # other DB
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OLD_KEY = "zack_britton"          # stays with the INCUMBENT (MLBAM 502154)
NEW_KEY = "zach_britton"          # the NEWCOMER (MLBAM 676309)
NEW_NAME = "Zach Britton"
INCUMBENT_MLBAM = 502154
KID_MLBAM = 676309
KID_ORG = "TOR"
DRAFT_KEY = "draft_2020_zack_britton"
# The newcomer's one board row, identified by (source, date, org).
KID_SNAPSHOT = ("baseballamerica", "2023-02-15", KID_ORG)
KID_BOARD_YEAR = 2023
KID_SIDE = "hit"
KID_DRAFT = (2020, 136, "TOR")    # (year, overall pick, team) of the newcomer

DEFAULT_DB = ROOT / "prospects.db"


# ---------------------------------------------------------------------------
# the outcome-blind resolution
# ---------------------------------------------------------------------------

def _one_edit(a: str, b: str) -> bool:
    """True when a and b differ by exactly one substitution, insertion or deletion."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def resolve_ba_row(name: str, vintage: int, side: str, index) -> dict:
    """Resolve one board row from its printed name, its board year and its side, with
    efv_identity's rule first and one fallback: when the rule's resolution sits on the
    other side (its pre-V minor league exposure is in the other group), the candidates
    one letter away from the printed name that are on the row's side with a recent line
    are tried, and exactly one resolves the row. Reads the name index only (pre-V minor
    league lines and June draft picks), never a debut, a MLB line, WAR or a label."""
    import efv_identity as ID
    group = ID.SIDE_GROUP.get(side)
    res = ID.resolve(name, vintage, index, side)
    out = {"name": name, "vintage": int(vintage), "side": side,
           "rule_person_id": res.person_id, "rule_how": res.how,
           "person_id": res.person_id, "how": res.how, "variant_name_key": None}
    if res.person_id is None or group is None:
        return out
    own = ID._group_of(index.lines(name, res.person_id, vintage))
    if own == group:
        return out
    target = ID.norm_name(name)
    found = []
    for key in sorted(index._by_name):
        if not _one_edit(key, target):
            continue
        for pid, first in index._by_name[key].items():
            if first > int(vintage) - 1:
                continue
            lines = (index._lines.get(key) or {}).get(pid) or {}
            lines = {g: {s: x for s, x in rows.items() if s <= int(vintage) - 1}
                     for g, rows in lines.items()}
            if ID._group_of(lines) == group and ID._recent(lines, vintage):
                found.append((key, pid))
    out["side_conflict"] = {"person_id": res.person_id, "group": own}
    if len(found) == 1:
        out.update(person_id=found[0][1], how="variant_side", variant_name_key=found[0][0])
    else:
        out.update(person_id=None, how="side_conflict_unresolved",
                   variant_candidates=[pid for _k, pid in found])
    return out


def resolve_kid(index=None) -> dict:
    """The resolution of the BA 2023 Blue Jays row on the on-disk caches."""
    import efv_identity as ID
    idx = ID.build_index(KID_BOARD_YEAR - 1) if index is None else index
    return resolve_ba_row("Zack Britton", KID_BOARD_YEAR, KID_SIDE, idx)


# ---------------------------------------------------------------------------
# the repair
# ---------------------------------------------------------------------------

def _p(action: str, *detail):
    print(f"  [{action}] " + " ".join(str(d) for d in detail))


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def repair(db_path: Path, apply: bool, *, resolution: dict | None = None) -> dict:
    """Plan (and with apply, write) the repair. Returns {"writes", "ambiguous", "refused"}."""
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== repair_zack_britton_collision [{mode}] db={db_path} ===")
    out = {"writes": 0, "ambiguous": [], "refused": None}
    if not Path(db_path).exists():
        out["refused"] = f"db not found: {db_path}"
        print("FATAL:", out["refused"])
        return out
    res = resolve_kid() if resolution is None else resolution
    print(f"-- resolution: {res}")
    if res.get("person_id") != KID_MLBAM:
        out["refused"] = (f"the outcome-blind resolution gives {res.get('person_id')!r}, not "
                          f"{KID_MLBAM}; nothing is moved")
        print("REFUSED:", out["refused"])
        return out

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    tables = _tables(con)
    amb = out["ambiguous"]
    n = 0

    # 1. the board row
    print("\n-- snapshots --")
    src, date, org = KID_SNAPSHOT
    rows = con.execute(
        "SELECT id, player_key, interval_label, org, position FROM snapshots "
        "WHERE source = ? AND snapshot_date = ? AND player_key IN (?, ?)",
        (src, date, OLD_KEY, NEW_KEY)).fetchall()
    for r in rows:
        if r["player_key"] == NEW_KEY:
            _p("ok", f"snapshot {r['id']} ({r['interval_label']}) already on {NEW_KEY}")
            continue
        if r["org"] != org:
            amb.append(f"snapshot {r['id']}: org {r['org']!r} is not {org}; NOT moved")
            continue
        clash = con.execute(
            "SELECT id FROM snapshots WHERE source = ? AND interval_label = ? AND player_key = ?",
            (src, r["interval_label"], NEW_KEY)).fetchone()
        if clash is not None:
            amb.append(f"snapshot {r['id']}: {NEW_KEY} already holds {r['interval_label']} "
                       f"(id {clash['id']}); NOT moved")
            continue
        _p("rekey", f"snapshot {r['id']} ({r['interval_label']}): {OLD_KEY} -> {NEW_KEY}")
        con.execute("UPDATE snapshots SET player_key = ?, player_name = ? WHERE id = ?",
                    (NEW_KEY, NEW_NAME, r["id"]))
        n += 1
    if not rows:
        amb.append(f"no {src} {date} row on {OLD_KEY} or {NEW_KEY}")

    # 2. the players row of the split key
    print("\n-- players --")
    pr = con.execute("SELECT player_key FROM players WHERE player_key = ?", (NEW_KEY,)).fetchone()
    if pr is not None:
        _p("ok", f"players[{NEW_KEY}] exists")
    else:
        _p("create", f"players[{NEW_KEY}] ({NEW_NAME}, {KID_ORG}, hitter, birth_date NULL)")
        con.execute("INSERT INTO players (player_key, player_name, position, org, is_pitcher) "
                    "VALUES (?, ?, NULL, ?, 0)", (NEW_KEY, NEW_NAME, KID_ORG))
        n += 1

    # 3. the draft spine
    print("\n-- draft spine --")
    if "draft_canonical_keys" in tables:
        ck = con.execute("SELECT milb_key FROM draft_canonical_keys WHERE draft_key = ?",
                         (DRAFT_KEY,)).fetchone()
        if ck is None:
            _p("ok", f"draft_canonical_keys[{DRAFT_KEY}] absent")
        elif ck["milb_key"] == NEW_KEY:
            _p("ok", f"draft_canonical_keys[{DRAFT_KEY}] already -> {NEW_KEY}")
        elif ck["milb_key"] == OLD_KEY:
            _p("rekey", f"draft_canonical_keys[{DRAFT_KEY}]: {OLD_KEY} -> {NEW_KEY}")
            con.execute("UPDATE draft_canonical_keys SET milb_key = ? WHERE draft_key = ?",
                        (NEW_KEY, DRAFT_KEY))
            n += 1
        else:
            amb.append(f"draft_canonical_keys[{DRAFT_KEY}] -> {ck['milb_key']!r}; NOT touched")
    if "draft_players" in tables:
        dp = con.execute("SELECT promoted_key, mlbam_id FROM draft_players WHERE player_key = ?",
                         (DRAFT_KEY,)).fetchone()
        if dp is None:
            _p("ok", f"draft_players[{DRAFT_KEY}] absent")
        elif dp["promoted_key"] == NEW_KEY:
            _p("ok", f"draft_players[{DRAFT_KEY}].promoted_key already {NEW_KEY}")
        elif dp["mlbam_id"] not in (None, KID_MLBAM):
            amb.append(f"draft_players[{DRAFT_KEY}]: mlbam_id {dp['mlbam_id']!r}; NOT touched")
        else:
            _p("rekey", f"draft_players[{DRAFT_KEY}].promoted_key: {dp['promoted_key']} -> "
               f"{NEW_KEY}")
            con.execute("UPDATE draft_players SET promoted_key = ? WHERE player_key = ?",
                        (NEW_KEY, DRAFT_KEY))
            n += 1

    # 4. the misfiled acquisition
    print("\n-- acquisitions --")
    if "acquisitions" in tables:
        a_old = con.execute("SELECT * FROM acquisitions WHERE player_key = ?",
                            (OLD_KEY,)).fetchone()
        a_new = con.execute("SELECT * FROM acquisitions WHERE player_key = ?",
                            (NEW_KEY,)).fetchone()

        def _draft(r):
            return None if r is None else (r["year"], r["pick_overall"], r["team_name"])
        if a_old is None:
            _p("ok", f"acquisitions[{OLD_KEY}] absent")
        elif _draft(a_old) != KID_DRAFT:
            _p("keep", f"acquisitions[{OLD_KEY}] {_draft(a_old)} is not the newcomer's draft")
        elif a_new is None:
            _p("rekey", f"acquisitions[{OLD_KEY}] {_draft(a_old)} -> {NEW_KEY}")
            con.execute("UPDATE acquisitions SET player_key = ? WHERE player_key = ?",
                        (NEW_KEY, OLD_KEY))
            n += 1
        elif _draft(a_new) == KID_DRAFT:
            _p("delete", f"acquisitions[{OLD_KEY}] {_draft(a_old)}: the newcomer's draft, "
               f"already held by acquisitions[{NEW_KEY}]")
            con.execute("DELETE FROM acquisitions WHERE player_key = ?", (OLD_KEY,))
            n += 1
        else:
            amb.append(f"acquisitions[{NEW_KEY}] {_draft(a_new)} differs from the misfiled "
                       f"{_draft(a_old)}; NOT touched")

    # 5. the inferred trade written off the moved row
    print("\n-- trades --")
    if "trades" in tables:
        tr = con.execute("SELECT id, from_org, to_org FROM trades WHERE player_key = ? "
                         "AND source = 'inferred' AND trade_date = ? AND to_org = ?",
                         (OLD_KEY, date, KID_ORG)).fetchall()
        for r in tr:
            _p("delete", f"trades {r['id']}: inferred {r['from_org']} -> {r['to_org']} on "
               f"{date}, evidenced only by the moved row")
            con.execute("DELETE FROM trades WHERE id = ?", (r["id"],))
            n += 1
        if not tr:
            _p("ok", "no inferred trade on the moved row's date")

    # 6. listed, not touched
    print("\n-- reported, NOT touched --")
    for t in ("players", "roster_status", "career_war", "statlines", "career_stats",
              "player_transactions", "metric_snapshots", "trade_value_history",
              "player_photos", "fa_signings"):
        if t not in tables:
            continue
        k = con.execute(f"SELECT COUNT(*) FROM {t} WHERE player_key = ?", (OLD_KEY,)).fetchone()[0]
        if k:
            _p("keep", f"{t}: {k} row(s) on {OLD_KEY}")
    left = con.execute("SELECT COUNT(*) FROM snapshots WHERE player_key = ? AND snapshot_date >= ? "
                       "AND NOT (source = ? AND snapshot_date = ?)",
                       (OLD_KEY, "2019-01-01", src, date)).fetchone()[0]
    if left:
        amb.append(f"{left} snapshot(s) dated 2019 or later remain on {OLD_KEY}; review")

    if amb:
        print("\n-- AMBIGUOUS rows (listed, NOT touched) --")
        for a in amb:
            _p("ambiguous", a)
    if apply:
        con.commit()
        print(f"\n=== APPLIED: {n} write(s) committed ===")
    else:
        con.rollback()
        print(f"\n=== DRY-RUN: {n} write(s) planned; re-run with --apply to execute ===")
    con.close()
    out["writes"] = n
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Repair the zack_britton key collision (the BA 2023 Blue Jays row).")
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help=f"path to prospects.db (default: {DEFAULT_DB})")
    a = ap.parse_args(argv)
    out = repair(a.db, apply=a.apply)
    return 2 if out["refused"] else 0


if __name__ == "__main__":
    sys.exit(main())
