# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_identity_residue_2026_08_19.py - batch repair of the identity residue
in data/identity_collisions.json (2026-08-19T19:36Z regen): 12 open C7
name-variant splits, 10 C4 side conflicts, 22 unassigned null-id rows.

Follows tools/repair_jesus_lopez_collision.py and the garrett_wright pattern:
idempotent, the incumbent is never re-keyed, derived history is disclosed
rather than moved when attribution is not two-signal, ambiguous cases are
SKIPPED with a printed reason. A wrong merge of two humans is a P0; the
design bias throughout is skip-and-report.

FROZEN CASE POLICY (written before the lab ran; the per-case verdicts below
each case were confirmed by this script's own precondition checks).

C7 name-variant splits, 12 open
-------------------------------
One human under two spellings. Fix = consensus.PLAYER_KEY_ALIASES route
(the jack_natili / william_bergolla spelling-splits precedent), NEVER a DB
key remap and NEVER a row delete: the alias canonicalises at read time and
is undone by deleting four lines. Merge bar, frozen: the two keys must agree
exactly on mlbam id, OR on (birth_date AND org AND side). Every open pair
already shares (birth_date, org) by construction of the C7 detector; this
script re-verifies dob, org and is_pitcher equality from the players table,
and additionally refuses any pair where both keys carry a snapshot from the
SAME source on the SAME date (one list cannot rank one human twice, so an
overlap would prove two humans). Canonical key = the member holding the
MLBAM photo binding and the fresher snapshot history.

  MERGED (11 routes):
    bj_murray_jr           -> bj_murray            (681230 on canonical)
    ben_cowles             -> benjamin_cowles      (701496)
    javi_vaz               -> javier_vaz           (805834)
    zach_thornton__noid    -> zac_thornton         (804267; the __noid twin
                              of the already-routed zach_thornton key)
    alex_santos            -> alex_santos_ii       (691012)
    jay_allen              -> jay_allen_ii         (695481)
    lonnie_jr_white        -> lonnie_white_jr      (696145; comma-mangled)
    jared_jones__sa3034881 -> jared_jones_702262   (702262; the PIT 1B,
                              b.2003-08-01 and 1B/PIT on both keys; the
                              OTHER Jared Jones keys are untouched)
    dennis_colleran        -> dennis_colleran_jr   (701207)
    dennis_colleran__noid  -> dennis_colleran_jr   (701207)
    leonardo_bernal__noid  -> leo_bernal           (699024)
    plus, from the C4 lane below:
    junior_garcia_815010   -> junior_garcia        (815010 after re-bind)

  SKIPPED (1): dom_keegan / dominic_keegan. The dom_keegan key's own 2026
  snapshots contradict each other on org (Pipeline TBR 2026-01-22, FG TBR
  2026-06-26, then FG BAL 2026-07-23 and 2026-08-02) while dominic_keegan
  is TBR throughout. A key whose own org witness flips BAL/TBR inside one
  cycle may itself hold two humans; dob+org+side cannot adjudicate it.
  Left open, reported.

C4 side conflicts, 10 cases
---------------------------
All ten: a board record claiming a HITTER whose bound mlbam id fields only
as a PITCHER. Root cause in 8 of 10: a name-search binding made before the
F2 vintage guard existed handed an OLD board record the mlbam id of a young
same-name pitcher, and today's ingest (fetched_at 2026-08-19) then wrote
that pitcher's acquisition, transaction log and roster status onto the
incumbent's key.

TWO-HUMANS PROOF, frozen: the stored players.birth_date must imply age
UNDER 16.0 YEARS at the key's EARLIEST snapshot date. MLB's own rules make
that categorically impossible for one human: the IFA signing-age floor is
16 and every published list postdates signing. The stored dob is then the
NEWCOMER's (verified against the roster-cache age within 0.6y), so the one
players row provably mixes two humans, the jesus_lopez tell.

REPAIR per proven case (the split template):
  (a) player_photos binding re-keyed (never deleted) to <key>_<mlbam>;
  (b) a players row is created for the split key from PUBLISHED fields
      only: name and org from the roster cache, RHP/LHP from MLB's own
      transaction text, birth_date = the stored dob the roster age just
      verified as the newcomer's;
  (c) the incumbent players.birth_date, proven the newcomer's, moves with
      him: the incumbent's true dob is not in any cached source, so the
      incumbent row is set to NULL rather than left wrong or guessed;
  (d) newcomer rows in acquisitions (matched on method/year/team
      signature), player_transactions (payload must name the newcomer's
      club AND his RHP/LHP role in MLB's own text), roster_status
      (fetched 2026-08-19 via the newcomer's bound id; content shows no
      MLB history where the michael_perez / jose_rondon incumbents have
      MLB careers), statlines and career_stats (only where the payload
      carries the newcomer's own id, level-era or org) are re-keyed to
      the split key;
  (e) scrapers._SPLIT_KEYS gains (slug, mlbam) -> split key so the next
      ingest cannot re-merge (the carlos_castillo lesson).

  REPAIRED (7 standard):
    michael_perez      / 805872 (MIA AA P, age 24.0)  earliest snap 2012-01-22, dob-implied 9.4y
    david_rodriguez    / 815095 (ATL A+ P, age 24.6)  2017-01-22, 15.1y
    alexander_campos   / 814226 (TBR CPX P, age 23.3) 2018-01-22, 14.8y
    enmanuel_rodriguez / 840917 (BAL DSL P, age 19.7) 2019-07-31, 12.6y
    jose_gomez         / 823845 (NYM DSL P, age 19.9) 2017-01-22, 10.4y
    jose_rondon        / 831791 (PIT DSL P, age 21.4) 2013-01-22,  7.8y
    aaron_brown        / 676345 (HOU AAA P, age 27.4) 2015-01-22, 15.8y

  REPAIRED (1 special): junior_garcia. The bare key holds the ATL OF's
  board history (FG 2024 RF ATL, BA 2025 OF ATL, b.2005-07-13) but binds
  mlbam 642371, a 2012 HOU IFA LHP (his own acquisition and transaction
  rows prove the era; the kid was seven when 642371 signed). The kid's own
  id 815010 sits on the ingest-forked key junior_garcia_815010 (roster:
  ATL A OF age 21.1 = b.2005-07 exactly). Repair: 642371's binding and
  rows -> junior_garcia_642371; 815010's binding -> junior_garcia (the
  board key, his own id on two signals: name+org+age exact); alias
  junior_garcia_815010 -> junior_garcia folds the fork. The incumbent dob
  2005-07-13 is the kid's own and STAYS.

  SKIPPED (2):
    adrian_hernandez / 681753 - the key itself fuses two humans' SNAPSHOTS
      (NYM OF 2018-2021 + international RHP 2022-2023) and the bound id is
      on no cached roster (il_status shows Mexican League). Needs its own
      snapshot-level split with people-record evidence this repair does
      not have. Disclosed, untouched.
    miguel_gomez / 685777 - the two-humans proof FAILS the frozen bar: the
      stored dob implies 16.4y at the key's earliest snapshot (2018-01-22
      Pipeline international row), which a July-2017 IFA signee can
      legitimately be. The FG 2018 SFG 3B rows are almost certainly the
      older MLB infielder, but "almost certainly" does not clear a P0 bar.
      Disclosed, untouched.

Unassigned null-id rows, 22
---------------------------
All 22 route through the EXISTING bulk path, stats.bulk_resolve_ids (never
resolve_mlbam_id; the 2026-08-03 negative-id-cache trap is handled inside
bulk_resolve_ids itself: fresh misses are skipped, stamps older than
NEG_ID_CACHE_TTL_DAYS=3 are retried). Measured before the run: 21 of 22
carry a miss stamp from the 2026-08-18 nightly (27.5h old, fresh), one
(christopher_suero) is unstamped and eligible. Rows that stay null are
left, counted and reported; the path retries them automatically once the
stamp expires. NOTE hua_ho / ho_hua (both PHI P) look like one human under
a name-order flip; C7 cannot see it (different surname token) and it is
reported as a followup, not guessed at here.

Idempotent: re-running after --apply reports "already repaired" and
changes nothing.

Usage:
    python tools/repair_identity_residue_2026_08_19.py            # dry run
    python tools/repair_identity_residue_2026_08_19.py --apply    # write
    python tools/repair_identity_residue_2026_08_19.py --db PATH  # other DB
"""

from __future__ import annotations

import argparse
import datetime
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DEFAULT_DB = HERE / "prospects.db"
ROSTER_CACHE = HERE / "data" / "rosters_by_org.json"

sys.path.insert(0, str(HERE))

# ---------------------------------------------------------------------------
# Case tables (frozen; every entry re-verified against the DB before writing)
# ---------------------------------------------------------------------------

#: C7 routes: stale key -> canonical key. The DB is NOT written for these;
#: the fix is the consensus.PLAYER_KEY_ALIASES entry (read-time fold, the
#: standing "alias maps, NEVER a DB remap" rule). This script verifies the
#: merge bar on the DB and that the alias entry is live.
C7_ROUTES: dict[str, str] = {
    "bj_murray_jr": "bj_murray",
    "ben_cowles": "benjamin_cowles",
    "javi_vaz": "javier_vaz",
    "zach_thornton__noid": "zac_thornton",
    "alex_santos": "alex_santos_ii",
    "jay_allen": "jay_allen_ii",
    "lonnie_jr_white": "lonnie_white_jr",
    "jared_jones__sa3034881": "jared_jones_702262",
    "dennis_colleran": "dennis_colleran_jr",
    "dennis_colleran__noid": "dennis_colleran_jr",
    "leonardo_bernal__noid": "leo_bernal",
    "junior_garcia_815010": "junior_garcia",
}

C7_SKIPPED = {
    "dom_keegan / dominic_keegan": (
        "the dom_keegan key's own 2026 snapshots flip org BAL/TBR inside one "
        "cycle; the key may itself hold two humans, dob+org+side cannot "
        "adjudicate it"),
}

#: C4 standard cases. Fields:
#:   key, mlbam       incumbent key and the WRONG bound id (the newcomer's)
#:   newcomer_dob     the stored players.birth_date, proven the newcomer's
#:   roster           (org, level, age) expected in data/rosters_by_org.json
#:   position         RHP/LHP from MLB's own transaction text
#:   acq_sig          (method, year, team_name) of the newcomer's acquisition
#:   tx_tokens        substrings that must BOTH appear in the transaction
#:                    payload before it moves (club + role, MLB's own words)
C4_CASES = [
    dict(key="michael_perez", mlbam=805872, newcomer_dob="2002-09-05",
         name="Michael Perez", roster=("MIA", 24.0), position="RHP",
         acq_sig=("international_fa", 2022, "Miami Marlins"),
         tx_tokens=("Miami Marlins", "RHP Michael Perez")),
    dict(key="david_rodriguez", mlbam=815095, newcomer_dob="2001-12-31",
         name="David Rodriguez", roster=("ATL", 24.6), position="RHP",
         acq_sig=("draft", 2023, "ATL"),
         tx_tokens=("Atlanta Braves", "RHP David Rodriguez")),
    dict(key="alexander_campos", mlbam=814226, newcomer_dob="2003-04-14",
         name="Alexander Campos", roster=("TBR", 23.3), position="RHP",
         acq_sig=("international_fa", 2023, "Tampa Bay Rays"),
         tx_tokens=("Tampa Bay Rays", "RHP Alexander Campos")),
    dict(key="enmanuel_rodriguez", mlbam=840917, newcomer_dob="2006-12-18",
         name="Enmanuel Rodriguez", roster=("BAL", 19.7), position="RHP",
         acq_sig=("international_fa", 2026, "Baltimore Orioles"),
         tx_tokens=("Baltimore Orioles", "RHP Enmanuel Rodriguez")),
    dict(key="jose_gomez", mlbam=823845, newcomer_dob="2006-09-09",
         name="Jose Gomez", roster=("NYM", 19.9), position="LHP",
         acq_sig=("international_fa", 2024, "New York Mets"),
         tx_tokens=("New York Mets", "LHP Jose Gomez")),
    dict(key="jose_rondon", mlbam=831791, newcomer_dob="2005-03-24",
         name="Jose Rondon", roster=("PIT", 21.4), position="RHP",
         acq_sig=("international_fa", 2025, "Pittsburgh Pirates"),
         tx_tokens=("Pittsburgh Pirates", "RHP Jose Rondon")),
    dict(key="aaron_brown", mlbam=676345, newcomer_dob="1999-03-19",
         name="Aaron Brown", roster=("HOU", 27.4), position="RHP",
         acq_sig=("draft", 2021, "HOU"),
         tx_tokens=("Houston Astros", "RHP Aaron Brown")),
]

#: Two-humans proof bar: stored dob must imply age under this at the key's
#: earliest snapshot. 16.0 is MLB's own IFA signing-age floor; no human
#: appears on a published list before turning 16.
AGE_PROOF_BAR_YEARS = 16.0

#: Roster-age agreement bar for "the stored dob is the newcomer's".
ROSTER_AGE_TOL_YEARS = 0.6

C4_SKIPPED = {
    "adrian_hernandez / 681753": (
        "the key fuses two humans' snapshots (NYM OF 2018-2021 + intl RHP "
        "2022-2023); the bound id is on no cached roster (il_status: Mexican "
        "League). Needs its own snapshot-level split, not this batch"),
    "miguel_gomez / 685777": (
        "two-humans proof fails the frozen bar: stored dob implies 16.4y at "
        "the earliest snapshot (2018-01-22 intl row), a legitimate IFA age. "
        "Left for a case with real people-record evidence"),
}

#: The 22 unassigned null-id keys, (player_key, player_name, position),
#: read from data/timeseries.json active rows with mlbam_id null and no
#: current_level on 2026-08-19.
NULL_ID_ROWS = [
    ("tyler_bell", "Tyler Bell", "SS"),
    ("sean_duncan", "Sean Duncan", "SP"),
    ("alejandro_rosario", "Alejandro Rosario", "SP"),
    ("myles_bailey", "Myles Bailey", "1B"),
    ("griffin_hugus", "Griffin Hugus", "SP"),
    ("christopher_suero", "Christopher Suero", "C"),
    ("drew_petska", "Drew Petska", "SIRP"),
    ("micah_bucknam", "Micah Bucknam", "MIRP"),
    ("logan_schmidt", "Logan Schmidt", "SP"),
    ("tyson_leblanc", "Tyson LeBlanc", "2B"),
    ("jared_spencer", "Jared Spencer", "SIRP"),
    ("chanmin_park", "Chan-Min Park", "SP"),
    ("junsang_eom", "Jun-Sang Eom", "SS"),
    ("peyton_prescott", "Peyton Prescott", "SIRP"),
    ("sean_episcope", "Sean Episcope", "MIRP"),
    ("ho_hua", "Ho Hua", "SP"),
    ("reid_worley", "Reid Worley", "SP"),
    ("river_hamilton__sa3069294", "River Hamilton", "SP"),
    ("dahian_santos", "Dahian Santos", "MIRP"),
    ("peter_kussow__sa3069274", "Peter Kussow", "SP"),
    ("gleider_figueroa", "Gleider Figueroa", "3B"),
    ("hua_ho", "Hua Ho", "RHP"),
]

# The junior_garcia special: the kid's own id, re-bound to his board key.
JUNIOR_KEY = "junior_garcia"
JUNIOR_WRONG_ID = 642371
JUNIOR_RIGHT_ID = 815010
JUNIOR_FORK_KEY = "junior_garcia_815010"
JUNIOR_SPLIT_KEY = "junior_garcia_642371"
JUNIOR_DOB = "2005-07-13"


def _p(action: str, *detail):
    print(f"  [{action}] " + " ".join(str(d) for d in detail))


def _years_between(d0: str, d1: str) -> float:
    a = datetime.date.fromisoformat(str(d0)[:10])
    b = datetime.date.fromisoformat(str(d1)[:10])
    return (b - a).days / 365.25


def _load_roster_index() -> dict[int, dict]:
    """{mlbam_id: {org, level, name, pos, age}} from the cached StatsAPI
    rosters artifact."""
    doc = json.loads(ROSTER_CACHE.read_text(encoding="utf-8"))
    out: dict[int, dict] = {}
    for org, levels in doc.items():
        if not isinstance(levels, dict):
            continue
        for level, players in levels.items():
            for row in players or []:
                if isinstance(row, dict) and row.get("mlbam_id") is not None:
                    out.setdefault(int(row["mlbam_id"]), {
                        "org": org, "level": level,
                        "name": row.get("fullName") or row.get("player_name"),
                        "pos": row.get("position"), "age": row.get("age"),
                    })
    return out


# ---------------------------------------------------------------------------
# C7 verification (no DB writes; the alias is the fix)
# ---------------------------------------------------------------------------

def verify_c7(con, problems: list[str]) -> None:
    print("\n== C7 name-variant routes (fix lives in consensus."
          "PLAYER_KEY_ALIASES; DB untouched) ==")
    try:
        from consensus import PLAYER_KEY_ALIASES as aliases
    except Exception as exc:
        aliases = {}
        problems.append(f"consensus import failed: {exc}")

    for stale, canon in C7_ROUTES.items():
        a = con.execute("SELECT * FROM players WHERE player_key=?",
                        (stale,)).fetchone()
        b = con.execute("SELECT * FROM players WHERE player_key=?",
                        (canon,)).fetchone()
        if a is None or b is None:
            problems.append(f"C7 {stale}->{canon}: players row missing")
            continue
        checks = []
        if stale != JUNIOR_FORK_KEY:
            # The merge bar: dob AND org AND side agree exactly.
            if str(a["birth_date"])[:10] != str(b["birth_date"])[:10]:
                checks.append("birth_date differs")
            if (a["org"] or "") != (b["org"] or ""):
                checks.append(f"org differs ({a['org']} vs {b['org']})")
        if (a["is_pitcher"] or 0) != (b["is_pitcher"] or 0):
            checks.append("side differs")
        overlap = con.execute(
            "SELECT s1.source, s1.snapshot_date FROM snapshots s1 "
            "JOIN snapshots s2 ON s1.source = s2.source "
            "AND s1.snapshot_date = s2.snapshot_date "
            "WHERE s1.player_key = ? AND s2.player_key = ?",
            (stale, canon)).fetchall()
        if overlap:
            checks.append(
                f"SAME source+date on both keys ({overlap[0]['source']} "
                f"{overlap[0]['snapshot_date']}): would prove two humans")
        if checks:
            problems.append(f"C7 {stale}->{canon}: " + "; ".join(checks))
            continue
        route = (aliases.get(stale) or {}).get("player_key")
        if route == canon:
            _p("ok", f"{stale} -> {canon}: merge bar holds, alias live")
        else:
            _p("PENDING", f"{stale} -> {canon}: merge bar holds, alias "
               f"NOT yet in consensus.PLAYER_KEY_ALIASES (found {route!r})")
    for name, why in C7_SKIPPED.items():
        _p("skip", f"{name}: {why}")


# ---------------------------------------------------------------------------
# C4 repairs
# ---------------------------------------------------------------------------

def _move_rows(con, apply: bool, table: str, key: str, split_key: str,
               where_extra: str = "", params: tuple = ()) -> int:
    """Re-key rows in `table` from key to split_key via rowid. Returns count."""
    rows = con.execute(
        f"SELECT rowid FROM {table} WHERE player_key = ? {where_extra}",
        (key, *params)).fetchall()
    for r in rows:
        con.execute(f"UPDATE {table} SET player_key = ? WHERE rowid = ?",
                    (split_key, r["rowid"]))
    return len(rows)


def repair_c4_case(con, apply: bool, roster: dict[int, dict],
                   case: dict, problems: list[str], changes: list[int]) -> None:
    key, mid = case["key"], case["mlbam"]
    split_key = f"{key}_{mid}"
    print(f"\n-- C4 {key} / mlbam {mid} -> {split_key} --")

    inc = con.execute("SELECT * FROM players WHERE player_key=?",
                      (key,)).fetchone()
    if inc is None:
        problems.append(f"C4 {key}: incumbent players row missing")
        return

    # Proof 1: era impossibility. Stored dob vs earliest snapshot date.
    first = con.execute(
        "SELECT MIN(snapshot_date) FROM snapshots WHERE player_key=?",
        (key,)).fetchone()[0]
    dob = str(inc["birth_date"] or "")[:10]
    already = dob == "" or dob == "None"
    if not already:
        if dob != case["newcomer_dob"]:
            problems.append(
                f"C4 {key}: stored dob {dob!r} is not the expected "
                f"{case['newcomer_dob']!r} - NOT touched, review first")
            return
        if first is None:
            problems.append(f"C4 {key}: no snapshots, era proof impossible")
            return
        implied = _years_between(dob, first)
        if implied >= AGE_PROOF_BAR_YEARS:
            problems.append(
                f"C4 {key}: era proof FAILS ({implied:.1f}y at {first} >= "
                f"{AGE_PROOF_BAR_YEARS}) - two humans not proven, skipping")
            return
        _p("proof", f"stored dob {dob} implies {implied:.1f}y at the key's "
           f"earliest snapshot {first}: impossible for the incumbent "
           f"(IFA floor is 16), so the dob is the newcomer's")

    # Proof 2: the roster cache agrees the bound id is a young pitcher whose
    # age matches that dob.
    r = roster.get(mid)
    exp_org, exp_age = case["roster"]
    if r is None:
        problems.append(f"C4 {key}: mlbam {mid} not in roster cache - the "
                        "published-fields source is gone, skipping")
        return
    if r["org"] != exp_org or r["pos"] != "P":
        problems.append(
            f"C4 {key}: roster cache says {r['org']}/{r['pos']}, expected "
            f"{exp_org}/P - NOT touched, review first")
        return
    implied_now = _years_between(case["newcomer_dob"], "2026-07-23")
    if r["age"] is not None and abs(float(r["age"]) - implied_now) > ROSTER_AGE_TOL_YEARS:
        problems.append(
            f"C4 {key}: roster age {r['age']} vs dob-implied {implied_now:.1f} "
            f"differ by more than {ROSTER_AGE_TOL_YEARS}y - skipping")
        return
    _p("proof", f"roster cache: mlbam {mid} is a P at {r['org']} {r['level']} "
       f"age {r['age']} (dob-implied {implied_now:.1f}), the newcomer")

    # (a) player_photos binding re-keyed, never deleted.
    ph = con.execute("SELECT player_key FROM player_photos WHERE mlbam_id=?",
                     (mid,)).fetchone()
    if ph is None:
        _p("ok", f"no photo binding for {mid}")
    elif ph["player_key"] == split_key:
        _p("ok", f"already repaired: binding {mid} -> {split_key}")
    elif ph["player_key"] == key:
        _p("rekey", f"player_photos: {mid} {key} -> {split_key}")
        con.execute("UPDATE player_photos SET player_key=? WHERE mlbam_id=?",
                    (split_key, mid))
        changes[0] += 1
    else:
        problems.append(f"C4 {key}: binding {mid} sits on unexpected key "
                        f"{ph['player_key']!r} - NOT touched")

    # (b) players row for the split key, published fields only.
    sp = con.execute("SELECT * FROM players WHERE player_key=?",
                     (split_key,)).fetchone()
    if sp is not None:
        _p("ok", f"already repaired: players[{split_key}] exists")
    else:
        _p("create", f"players[{split_key}]: {case['name']} / "
           f"{case['position']} / {r['org']} / is_pitcher=1 / "
           f"b.{case['newcomer_dob']} (name+org from the roster cache, "
           f"RHP/LHP from MLB's transaction text, dob verified on roster age)")
        con.execute(
            "INSERT INTO players (player_key, player_name, position, org, "
            "is_pitcher, birth_date, updated_at) VALUES (?, ?, ?, ?, 1, ?, "
            "datetime('now'))",
            (split_key, case["name"], case["position"], r["org"],
             case["newcomer_dob"]))
        changes[0] += 1

    # (c) the incumbent's contaminated birth_date. His true dob is in no
    # cached source, so NULL rather than wrong or guessed.
    if already:
        _p("ok", f"already repaired: players[{key}].birth_date is NULL")
    else:
        _p("restore", f"players[{key}].birth_date: {dob} (the newcomer's) -> "
           f"NULL (the incumbent's true dob is not in any cached source; "
           f"NULL is honest, the newcomer's dob is not)")
        con.execute("UPDATE players SET birth_date = NULL WHERE player_key=?",
                    (key,))
        changes[0] += 1

    # (d) the newcomer's rows in the four identity tables.
    method, year, team = case["acq_sig"]
    for row in con.execute(
            "SELECT rowid, player_key, method, year, team_name FROM "
            "acquisitions WHERE player_key IN (?, ?)",
            (key, split_key)).fetchall():
        if row["team_name"] is None:
            continue
        sig = (row["method"], row["year"], row["team_name"])
        if sig != (method, year, team):
            _p("keep", f"acquisition {sig} is not the newcomer's; stays")
            continue
        if row["player_key"] == split_key:
            _p("ok", f"already repaired: acquisition {sig} on {split_key}")
            continue
        _p("rekey", f"acquisitions: {sig} -> {split_key}")
        con.execute("UPDATE acquisitions SET player_key=? WHERE rowid=?",
                    (split_key, row["rowid"]))
        changes[0] += 1

    tx = con.execute("SELECT rowid, payload_json FROM player_transactions "
                     "WHERE player_key=?", (key,)).fetchone()
    if tx is None:
        _p("ok", f"no player_transactions row on {key}")
    else:
        blob = str(tx["payload_json"])
        if all(tok in blob for tok in case["tx_tokens"]):
            _p("rekey", f"player_transactions: payload names "
               f"{case['tx_tokens']} in MLB's own text -> {split_key}")
            con.execute("UPDATE player_transactions SET player_key=? "
                        "WHERE rowid=?", (split_key, tx["rowid"]))
            changes[0] += 1
        else:
            problems.append(
                f"C4 {key}: player_transactions payload lacks "
                f"{case['tx_tokens']} - NOT moved, disclosed")

    rs = con.execute("SELECT rowid, payload_json, fetched_at FROM "
                     "roster_status WHERE player_key=?", (key,)).fetchone()
    if rs is None:
        _p("ok", f"no roster_status row on {key}")
    else:
        try:
            st = json.loads(rs["payload_json"])
        except ValueError:
            st = {}
        if not st.get("mlb_seasons") and not st.get("mlb_debut_date") \
                and str(rs["fetched_at"] or "") >= "2026-08":
            _p("rekey", f"roster_status: fetched {rs['fetched_at']} via the "
               f"newcomer's bound id, no MLB history -> {split_key}")
            con.execute("UPDATE roster_status SET player_key=? WHERE rowid=?",
                        (split_key, rs["rowid"]))
            changes[0] += 1
        else:
            problems.append(f"C4 {key}: roster_status carries MLB history or "
                            f"predates the merge window - NOT moved")

    # statlines / career_stats: only where the payload carries the
    # newcomer's own id or his level-era + org.
    for row in con.execute("SELECT rowid, payload_json FROM statlines "
                           "WHERE player_key=?", (key,)).fetchall():
        if f'"mlbam_id": {mid}' in str(row["payload_json"]):
            _p("rekey", f"statlines: payload carries mlbam {mid} -> {split_key}")
            con.execute("UPDATE statlines SET player_key=? WHERE rowid=?",
                        (split_key, row["rowid"]))
            changes[0] += 1
        else:
            _p("keep", "statlines row without the newcomer's id; stays")
    cs = con.execute("SELECT rowid, payload_json FROM career_stats "
                     "WHERE player_key=?", (key,)).fetchone()
    if cs is not None:
        blob = str(cs["payload_json"])
        try:
            seasons = json.loads(blob)
        except ValueError:
            seasons = []
        orgs = {s.get("org") for s in seasons if isinstance(s, dict)}
        years = [s.get("season") for s in seasons if isinstance(s, dict)
                 and isinstance(s.get("season"), int)]
        sign_year = int(case["newcomer_dob"][:4]) + 16
        if orgs and orgs <= {exp_org} and years and min(years) >= sign_year:
            _p("rekey", f"career_stats: seasons {min(years)}-{max(years)} all "
               f"{exp_org}, within the newcomer's own era -> {split_key}")
            con.execute("UPDATE career_stats SET player_key=? WHERE rowid=?",
                        (split_key, cs["rowid"]))
            changes[0] += 1
        else:
            _p("keep", f"career_stats orgs={sorted(o for o in orgs if o)} "
               f"years={sorted(set(years))}: not two-signal the newcomer's; "
               f"stays, disclosed")

    # (e) is enforced in scrapers._SPLIT_KEYS; verified in verify_pins().


def repair_junior_garcia(con, apply: bool, roster: dict[int, dict],
                         problems: list[str], changes: list[int]) -> None:
    print(f"\n-- C4 special {JUNIOR_KEY}: wrong id {JUNIOR_WRONG_ID} out, "
          f"his own {JUNIOR_RIGHT_ID} in --")
    inc = con.execute("SELECT * FROM players WHERE player_key=?",
                      (JUNIOR_KEY,)).fetchone()
    if inc is None:
        problems.append("junior_garcia: players row missing")
        return
    # Proof the board key is the ATL kid: dob+org vs the roster row of his
    # own id (name, ATL, age 21.1 = b.2005-07).
    r = roster.get(JUNIOR_RIGHT_ID)
    if (str(inc["birth_date"])[:10] != JUNIOR_DOB or inc["org"] != "ATL"
            or r is None or r["org"] != "ATL"
            or abs(float(r["age"]) - _years_between(JUNIOR_DOB, "2026-07-23")) > ROSTER_AGE_TOL_YEARS):
        problems.append("junior_garcia: kid-identity proof failed, skipping")
        return
    _p("proof", f"board key is the ATL OF b.{JUNIOR_DOB}; his own id "
       f"{JUNIOR_RIGHT_ID} is on the ATL roster at age {r['age']}")
    # Proof 642371 is another human: his acquisition (IFA 2012 HOU) and
    # transaction log (LHP, ARI chain from 2019) predate the kid's career.
    acq = con.execute(
        "SELECT rowid, player_key, method, year, team_name, signing_date "
        "FROM acquisitions WHERE player_key IN (?, ?)",
        (JUNIOR_KEY, JUNIOR_SPLIT_KEY)).fetchall()
    old_acq = [a for a in acq if a["method"] == "international_fa"
               and a["year"] == 2012 and a["team_name"] == "Houston Astros"
               and a["player_key"] == JUNIOR_KEY]
    if not old_acq and not con.execute(
            "SELECT 1 FROM acquisitions WHERE player_key=?",
            (JUNIOR_SPLIT_KEY,)).fetchone():
        problems.append("junior_garcia: the 2012 HOU acquisition that proves "
                        "the wrong-human era is absent, skipping")
        return
    _p("proof", "the key carries a 2012 HOU IFA acquisition; the kid was "
       "seven years old in 2012, so those rows are another human's "
       f"(mlbam {JUNIOR_WRONG_ID})")

    # 642371's binding and rows -> junior_garcia_642371.
    ph = con.execute("SELECT player_key FROM player_photos WHERE mlbam_id=?",
                     (JUNIOR_WRONG_ID,)).fetchone()
    if ph and ph["player_key"] == JUNIOR_KEY:
        _p("rekey", f"player_photos: {JUNIOR_WRONG_ID} -> {JUNIOR_SPLIT_KEY}")
        con.execute("UPDATE player_photos SET player_key=? WHERE mlbam_id=?",
                    (JUNIOR_SPLIT_KEY, JUNIOR_WRONG_ID))
        changes[0] += 1
    elif ph and ph["player_key"] == JUNIOR_SPLIT_KEY:
        _p("ok", "already repaired: wrong binding re-keyed")
    elif ph:
        problems.append(f"junior_garcia: binding {JUNIOR_WRONG_ID} on "
                        f"unexpected key {ph['player_key']!r} - NOT touched")

    if con.execute("SELECT 1 FROM players WHERE player_key=?",
                   (JUNIOR_SPLIT_KEY,)).fetchone() is None:
        _p("create", f"players[{JUNIOR_SPLIT_KEY}]: Junior Garcia / LHP / "
           "org NULL / is_pitcher=1 / dob NULL (LHP is MLB's own transaction "
           "text; he is on no cached roster, so org and dob are honestly "
           "unknown rather than inferred)")
        con.execute(
            "INSERT INTO players (player_key, player_name, position, org, "
            "is_pitcher, birth_date, updated_at) VALUES (?, 'Junior Garcia', "
            "'LHP', NULL, 1, NULL, datetime('now'))", (JUNIOR_SPLIT_KEY,))
        changes[0] += 1
    else:
        _p("ok", f"already repaired: players[{JUNIOR_SPLIT_KEY}] exists")

    for a in old_acq:
        _p("rekey", f"acquisitions: IFA 2012 Houston Astros -> {JUNIOR_SPLIT_KEY}")
        con.execute("UPDATE acquisitions SET player_key=? WHERE rowid=?",
                    (JUNIOR_SPLIT_KEY, a["rowid"]))
        changes[0] += 1

    tx = con.execute("SELECT rowid, payload_json FROM player_transactions "
                     "WHERE player_key=?", (JUNIOR_KEY,)).fetchone()
    if tx is not None:
        blob = str(tx["payload_json"])
        if "LHP Junior Garcia" in blob and ("Diamondbacks" in blob
                                            or "Astros" in blob):
            _p("rekey", f"player_transactions: the LHP's ARI/HOU log -> "
               f"{JUNIOR_SPLIT_KEY}")
            con.execute("UPDATE player_transactions SET player_key=? "
                        "WHERE rowid=?", (JUNIOR_SPLIT_KEY, tx["rowid"]))
            changes[0] += 1
        else:
            problems.append("junior_garcia: transaction payload is not "
                            "two-signal the LHP's - NOT moved, disclosed")

    cs = con.execute("SELECT rowid, payload_json FROM career_stats "
                     "WHERE player_key=?", (JUNIOR_KEY,)).fetchone()
    if cs is not None:
        try:
            seasons = json.loads(str(cs["payload_json"]))
        except ValueError:
            seasons = []
        years = [s.get("season") for s in seasons if isinstance(s, dict)
                 and isinstance(s.get("season"), int)]
        if years and min(years) <= 2021:
            _p("rekey", f"career_stats: seasons back to {min(years)} predate "
               f"the kid's career -> {JUNIOR_SPLIT_KEY}")
            con.execute("UPDATE career_stats SET player_key=? WHERE rowid=?",
                        (JUNIOR_SPLIT_KEY, cs["rowid"]))
            changes[0] += 1
        else:
            _p("keep", f"career_stats years {sorted(set(years))}: could be "
               "the kid's, stays")

    rs = con.execute("SELECT rowid, payload_json, fetched_at FROM roster_status "
                     "WHERE player_key=?", (JUNIOR_KEY,)).fetchone()
    if rs is not None:
        try:
            st = json.loads(rs["payload_json"])
        except ValueError:
            st = {}
        if not st.get("mlb_seasons") and not st.get("mlb_debut_date") \
                and str(rs["fetched_at"] or "") >= "2026-08":
            _p("rekey", f"roster_status: fetched {rs['fetched_at']} via the "
               f"wrong bound id -> {JUNIOR_SPLIT_KEY}")
            con.execute("UPDATE roster_status SET player_key=? WHERE rowid=?",
                        (JUNIOR_SPLIT_KEY, rs["rowid"]))
            changes[0] += 1
        else:
            problems.append("junior_garcia: roster_status not provably the "
                            "LHP's - NOT moved")

    # The kid's own id comes home to his board key.
    ph2 = con.execute("SELECT player_key FROM player_photos WHERE mlbam_id=?",
                      (JUNIOR_RIGHT_ID,)).fetchone()
    if ph2 and ph2["player_key"] == JUNIOR_FORK_KEY:
        _p("rekey", f"player_photos: {JUNIOR_RIGHT_ID} {JUNIOR_FORK_KEY} -> "
           f"{JUNIOR_KEY} (his own id: name + ATL + age all match the board "
           "row; the fork key folds back via PLAYER_KEY_ALIASES)")
        con.execute("UPDATE player_photos SET player_key=? WHERE mlbam_id=?",
                    (JUNIOR_KEY, JUNIOR_RIGHT_ID))
        changes[0] += 1
    elif ph2 and ph2["player_key"] == JUNIOR_KEY:
        _p("ok", "already repaired: the kid's id is on his board key")
    elif ph2:
        problems.append(f"junior_garcia: binding {JUNIOR_RIGHT_ID} on "
                        f"unexpected key {ph2['player_key']!r} - NOT touched")
    else:
        problems.append(f"junior_garcia: no binding for {JUNIOR_RIGHT_ID}")


def verify_pins(problems: list[str]) -> None:
    print("\n== scrapers._SPLIT_KEYS pins (the anti-re-merge lock) ==")
    try:
        from scrapers import _SPLIT_KEYS
    except Exception as exc:
        problems.append(f"scrapers import failed: {exc}")
        return
    wanted = [(c["key"], c["mlbam"], f"{c['key']}_{c['mlbam']}")
              for c in C4_CASES]
    wanted.append((JUNIOR_KEY, JUNIOR_WRONG_ID, JUNIOR_SPLIT_KEY))
    for slug, mid, split_key in wanted:
        got = _SPLIT_KEYS.get((slug, mid))
        if got == split_key:
            _p("ok", f"({slug}, {mid}) -> {split_key}")
        else:
            _p("PENDING", f"({slug}, {mid}) -> {split_key} NOT pinned "
               f"(found {got!r})")


# ---------------------------------------------------------------------------
# Null-id lane: the existing bulk path, nothing else
# ---------------------------------------------------------------------------

def run_null_id_lane(apply: bool) -> None:
    print("\n== unassigned null-id rows, via stats.bulk_resolve_ids ==")
    import stats
    stamps = {}
    try:
        stamps = json.loads(stats.MISS_STAMP_FILE.read_text())
    except (OSError, ValueError):
        pass
    import time as _t
    fresh, eligible = [], []
    for key, name, pos in NULL_ID_ROWS:
        ts = stamps.get(key)
        if isinstance(ts, (int, float)) and \
                (_t.time() - ts) < stats.NEG_ID_CACHE_TTL_DAYS * 86400.0:
            fresh.append(key)
        else:
            eligible.append(key)
    _p("state", f"{len(fresh)} of {len(NULL_ID_ROWS)} carry a FRESH negative "
       f"stamp (< {stats.NEG_ID_CACHE_TTL_DAYS}d): the path skips them by "
       f"design and retries after the TTL")
    _p("state", f"eligible for a retry now: {eligible or 'none'}")
    if not apply:
        _p("dry-run", "resolver not called (it writes its cache files); "
           "--apply runs it")
        return
    ids, bds, _idx = stats.bulk_resolve_ids(NULL_ID_ROWS)
    resolved = {k: v for k, v in ids.items() if v is not None}
    _p("result", f"resolved now: {resolved or 'none'}")
    _p("result", f"still unresolved: {len(NULL_ID_ROWS) - len(resolved)} of "
       f"{len(NULL_ID_ROWS)} (fresh-stamped rows retry automatically from "
       "2026-08-21; KBO signees and unassigned draftees resolve once "
       "StatsAPI registers them)")


# ---------------------------------------------------------------------------

def repair(db_path: Path, apply: bool) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== repair_identity_residue_2026_08_19 [{mode}] db={db_path} ===")
    if not db_path.exists():
        print(f"FATAL: db not found: {db_path}")
        return 2

    roster = _load_roster_index()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    problems: list[str] = []
    changes = [0]

    verify_c7(con, problems)
    for case in C4_CASES:
        repair_c4_case(con, apply, roster, case, problems, changes)
    repair_junior_garcia(con, apply, roster, problems, changes)
    for name, why in C4_SKIPPED.items():
        _p("skip", f"{name}: {why}")
    verify_pins(problems)

    if problems:
        print("\n-- PROBLEMS / AMBIGUOUS (listed, NOT touched) --")
        for p in problems:
            _p("ambiguous", p)

    if apply:
        con.commit()
        print(f"\n=== APPLIED: {changes[0]} write(s) committed ===")
    else:
        con.rollback()
        print(f"\n=== DRY-RUN: {changes[0]} write(s) planned; re-run with "
              "--apply to execute ===")
    con.close()

    run_null_id_lane(apply)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Batch repair of the 2026-08-19 identity residue "
                    "(C7 spelling splits, C4 wrong-era bindings, null ids).")
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help=f"path to prospects.db (default: {DEFAULT_DB})")
    args = ap.parse_args()
    return repair(args.db, apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
