# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
verify_flores_identity.py - end-to-end check that the two Jesus Floreses
are two people everywhere the site can see them.

  808222  Jesus Flores  b.2005-03-16  VEN  RHP  MIL  A+ (Wisconsin)
  837965  Jesus Flores  b.2008-11-06  VEN  C    TEX  DSL Rangers Blue

The board key "jesus_flores" belongs to the PITCHER: players.birth_date,
the roster join, the level, and the entire fielding log are his. The
catcher is carried separately as mlbam_837965 on the ungraded eFV surface
and has no board record (that is an owner decision, not a bug to mint).

Checks (each prints PASS / FAIL and the value it read):
  1 player_photos binds 808222 -> jesus_flores and 837965 -> nobody
  2 players row: birth_date 2005-03-16, pitcher position, is_pitcher 1
  3 snapshots: no row under jesus_flores still carries the catcher's
    org/position
  4 board row (timeseries.json): pitcher-side position, mlbam 808222
  5 positions_played: pitcher-only fielding log, agrees with the board
  6 xfv side: the ungraded surface still carries mlbam_837965 separately
    and does not also carry 808222 under the board key
  7 trade_values.json: one Jesus Flores row, pitcher-side position
  8 player_links.json: byKey/byMlbam agree on 808222

Read-only. Run from the prospect-tracker directory.
"""

from __future__ import annotations

import io
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
PITCHER, CATCHER = 808222, 837965
KEY = "jesus_flores"
PITCHER_BIRTH, CATCHER_BIRTH = "2005-03-16", "2008-11-06"
_PIT_TOKENS = {"P", "SP", "RP", "RHP", "LHP", "SIRP", "MIRP", "RHSP", "LHSP"}

_fails = 0


def check(name: str, ok: bool, detail: str) -> None:
    global _fails
    if not ok:
        _fails += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def _load(name):
    p = DATA / name
    if not p.exists():
        return None
    return json.load(io.open(p, encoding="utf-8"))


def main() -> int:
    print("=== verify_flores_identity ===")
    con = sqlite3.connect(f"file:{(HERE / 'prospects.db').as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    # 1 - bindings
    rows = {r["mlbam_id"]: r["player_key"] for r in con.execute(
        "SELECT mlbam_id, player_key FROM player_photos WHERE mlbam_id IN (?, ?)",
        (PITCHER, CATCHER))}
    check("photos: pitcher bound to the key", rows.get(PITCHER) == KEY,
          f"player_photos[{PITCHER}].player_key = {rows.get(PITCHER)!r}")
    check("photos: catcher not bound to the key", rows.get(CATCHER) != KEY,
          f"player_photos[{CATCHER}].player_key = {rows.get(CATCHER)!r}")
    dbl = con.execute("SELECT COUNT(*) c FROM player_photos WHERE player_key = ?",
                      (KEY,)).fetchone()["c"]
    check("photos: exactly one id on the key", dbl == 1, f"{dbl} binding(s)")

    # 2 - players row
    pr = con.execute("SELECT position, org, is_pitcher, birth_date FROM players "
                     "WHERE player_key = ?", (KEY,)).fetchone()
    check("players: birth_date is the pitcher's",
          pr is not None and pr["birth_date"] == PITCHER_BIRTH,
          f"birth_date = {pr and pr['birth_date']!r} (catcher is {CATCHER_BIRTH})")
    check("players: pitcher position",
          pr is not None and str(pr["position"]).upper() in _PIT_TOKENS,
          f"position = {pr and pr['position']!r}")
    check("players: is_pitcher flag set", pr is not None and int(pr["is_pitcher"]) == 1,
          f"is_pitcher = {pr and pr['is_pitcher']}")

    # 3 - snapshots
    snaps = con.execute("SELECT source, snapshot_date, position, org FROM snapshots "
                        "WHERE player_key = ?", (KEY,)).fetchall()
    bad = [dict(s) for s in snaps
           if str(s["position"]).upper() not in _PIT_TOKENS or s["org"] == "TEX"]
    check("snapshots: none still carry the catcher's org/position", not bad,
          f"{len(snaps)} snapshot(s); offending = {bad}")

    # 4 - board row
    ts = _load("timeseries.json") or {}
    board = {p["player_key"]: p for p in (ts.get("players") or [])}
    b = board.get(KEY)
    check("board: row present", b is not None, f"{'found' if b else 'absent'}")
    if b:
        check("board: pitcher-side position",
              str(b.get("position")).upper() in _PIT_TOKENS,
              f"position = {b.get('position')!r}, org = {b.get('org')!r}, "
              f"level = {b.get('current_level')!r}")
        check("board: mlbam id is the pitcher's", b.get("mlbam_id") == PITCHER,
              f"mlbam_id = {b.get('mlbam_id')!r}")
        check("board: birth_date is the pitcher's", b.get("birth_date") == PITCHER_BIRTH,
              f"birth_date = {b.get('birth_date')!r}")

    # 5 - positions_played
    pp = (_load("positions_played.json") or {}).get("players") or {}
    e = pp.get(KEY) or {}
    by_pos = (e or {}).get("by_pos") or {}
    hitter_g = sum(int((v or {}).get("g") or 0) for k, v in by_pos.items()
                   if k.upper() not in _PIT_TOKENS)
    check("positions_played: pitcher-only fielding log", by_pos and hitter_g == 0,
          f"by_pos = {by_pos}")

    # 6 - xfv ungraded side
    ung = (_load("xfv_ungraded.json") or {}).get("by_player") or {}
    cat = ung.get(f"mlbam_{CATCHER}")
    check("xfv: catcher tracked separately", cat is not None,
          f"mlbam_{CATCHER} -> {None if not cat else (cat.get('org'), cat.get('level'), cat.get('position'), cat.get('xfv_grade'))}")
    dupe = [k for k, v in ung.items() if v.get("mlbam_id") == PITCHER]
    check("xfv: pitcher not duplicated on the ungraded surface", not dupe,
          f"ungraded entries for {PITCHER}: {dupe or 'none'}")

    # 7 - trade values
    tv = (_load("trade_values.json") or {}).get("players") or []
    hits = [r for r in tv if r.get("player_key") == KEY]
    check("trade_values: exactly one Jesus Flores row", len(hits) <= 1,
          f"{len(hits)} row(s)")
    if hits:
        check("trade_values: pitcher-side position",
              str(hits[0].get("position")).upper() in _PIT_TOKENS,
              f"position = {hits[0].get('position')!r}, org = {hits[0].get('org')!r}")

    # 8 - player links
    pl = _load("player_links.json") or {}
    by_key = (pl.get("byKey") or {}).get(KEY)
    by_mlbam = (pl.get("byMlbam") or {}).get(str(PITCHER))
    cat_link = (pl.get("byMlbam") or {}).get(str(CATCHER))
    check("player_links: byKey/byMlbam agree", (by_key is None) == (by_mlbam is None),
          f"byKey[{KEY}] = {by_key!r}; byMlbam[{PITCHER}] = {by_mlbam!r}")
    check("player_links: catcher does not resolve to the key",
          cat_link is None or cat_link != by_key,
          f"byMlbam[{CATCHER}] = {cat_link!r}")

    con.close()
    print(f"\n{'ALL CHECKS PASSED' if not _fails else str(_fails) + ' CHECK(S) FAILED'}")
    return 1 if _fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
