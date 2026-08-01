# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_sabermetrics_stint_rows.py - repair stored sabermetrics rows that hold a
single STINT instead of the player's season total.

THE BUG (fixed in stats.py 2026-07-31). stats.fetch_sabermetrics is season-scoped,
so more than one split never means more than one season. It means STINTS: StatsAPI
returns the season aggregate first, marked with numTeams and carrying no team block,
then one row per club. The parser took splits[-1] under the comment "last in list is
usually most recent season slice", which is the LAST STINT for anyone traded
mid-season. A player who was never traded has exactly one split, so both readings
agree, which is how it survived.

WHY IT MATTERS. prospx renders this wRC+ as a headline chip. Measured against the
authoritative bulk call on 2026-07-31, 160 of 511 stored hitters (31.3%) were off by
more than 0.5, 80 by more than 2.0, 18 by more than 10 and 8 by more than 25. Worst
row: mlbam 677956 stored -100.0 against a season total of -9.8.

THE REPAIR. The code fix corrects future fetches but the stored rows stay wrong until
their TTL turns over, and 515 of them were refetched on 2026-07-31, so that is not
soon. This rewrites them in place from ONE bulk StatsAPI call, which is also the
authoritative source: it returns season totals by construction and covers more players
than the per-player loop does.

  https://statsapi.mlb.com/api/v1/stats?stats=sabermetrics&group=hitting
      &season={season}&sportId=1&playerPool=All&limit=2000

Only rows whose stored value DISAGREES with the season total are touched, so a clean
row keeps its fetched_at and the diff stays honest about what moved.

DEPLOY: the box is the single writer for its own prospects.db, so this must be run
there too, exactly like the other one-off repairs. Dry-run first, both places.

Usage:
    python tools/repair_sabermetrics_stint_rows.py            # dry-run, reports
    python tools/repair_sabermetrics_stint_rows.py --apply    # write

Idempotent: re-running after --apply reports zero rows to repair.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "prospects.db"
BULK = ("https://statsapi.mlb.com/api/v1/stats?stats=sabermetrics&group={group}"
        "&season={season}&sportId=1&playerPool=All&limit=2000")

# Payload key -> StatsAPI stat key, per side. These are exactly the fields
# fetch_sabermetrics stores, so nothing else in the row is rewritten.
HIT_FIELDS = {"wrc_plus": ("wRcPlus", 1), "woba": ("woba", 3), "war": ("war", 2)}
PIT_FIELDS = {"xfip": ("xfip", 2), "fip": ("fip", 2), "fip_minus": ("fipMinus", 1),
              "era_minus": ("eraMinus", 1), "war": ("war", 2)}


def _bulk(season: int, group: str) -> dict[int, tuple[dict, int]]:
    """mlbam id -> (season-total stat block, numTeams).

    One call, season totals by construction, and it carries numTeams per player,
    which is exactly the marker that identifies who the stint bug can reach.
    """
    url = BULK.format(group=group, season=season)
    with urllib.request.urlopen(url, timeout=60) as r:
        doc = json.loads(r.read())
    out: dict[int, tuple[dict, int]] = {}
    for block in doc.get("stats", []):
        for s in block.get("splits", []):
            pid = (s.get("player") or {}).get("id")
            if pid is not None:
                out[int(pid)] = (s.get("stat") or {}, int(s.get("numTeams") or 1))
    return out


def _num(v, nd):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def repair(db_path: Path, season: int, apply: bool) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== repair_sabermetrics_stint_rows [{mode}] {db_path} season={season} ===")
    if not db_path.exists():
        print(f"  db not found: {db_path}")
        return 1

    con = sqlite3.connect(db_path)
    rows = con.execute(
        "select player_key, payload_json from sabermetrics where season=?",
        (season,)).fetchall()
    print(f"  stored rows for {season}: {len(rows)}")
    if not rows:
        con.close()
        return 0

    truth = {"hitting": _bulk(season, "hitting"), "pitching": _bulk(season, "pitching")}
    print(f"  bulk season totals: {len(truth['hitting'])} hitters, "
          f"{len(truth['pitching'])} pitchers")

    changed, unmatched, skipped_untraded, examples = [], 0, 0, []
    for key, raw in rows:
        try:
            pay = json.loads(raw)
        except ValueError:
            continue
        mid = pay.get("mlbam_id")
        if mid is None:
            continue
        is_pit = bool(pay.get("is_pitcher"))
        hit = truth["pitching" if is_pit else "hitting"].get(int(mid))
        if not hit:
            unmatched += 1
            continue
        stat, n_teams = hit
        # ONLY traded players. This is the whole point of scoping the repair by
        # numTeams rather than by "disagrees with the bulk call": a single-stint
        # player's stored row was parsed CORRECTLY, and any gap against today's
        # bulk figure is ordinary drift because he has played more games since it
        # was fetched. Rewriting those would launder normal staleness as a bug fix,
        # touch about 1,000 rows instead of the affected few, and destroy the
        # honest meaning of fetched_at. Measured 2026-07-31: scoping on
        # disagreement alone flagged 1,025 of 1,120 rows.
        if n_teams <= 1:
            skipped_untraded += 1
            continue
        fields = PIT_FIELDS if is_pit else HIT_FIELDS
        new = dict(pay)
        moved = []
        for pk, (sk, nd) in fields.items():
            v = _num(stat.get(sk), nd)
            if v is None:
                continue
            if pay.get(pk) is not None and abs(float(pay[pk]) - v) > 10 ** (-nd) / 2:
                moved.append((pk, pay[pk], v))
                new[pk] = v
        if moved:
            new["fetched_at"] = date.today().isoformat()
            changed.append((key, json.dumps(new)))
            if len(examples) < 8:
                examples.append((key, mid, moved))

    print(f"  rows needing repair: {len(changed)} of {len(rows)}"
          f"   (single-club, not reachable by this bug: {skipped_untraded}; "
          f"no bulk match: {unmatched})")
    for key, mid, moved in examples:
        bits = ", ".join(f"{p} {o} -> {n}" for p, o, n in moved)
        print(f"    {key[:28]:28s} mlbam {mid}: {bits}")

    if apply and changed:
        con.executemany(
            "update sabermetrics set payload_json=? where player_key=? and season=?",
            [(pj, k, season) for k, pj in changed])
        con.commit()
        print(f"  WROTE {len(changed)} rows")
    elif changed:
        print(f"\n  === DRY-RUN: re-run with --apply to write {len(changed)} rows ===")
    else:
        print("  already repaired, nothing to do")
    con.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write the repair")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--season", type=int, default=date.today().year)
    a = ap.parse_args()
    return repair(Path(a.db), a.season, a.apply)


if __name__ == "__main__":
    sys.exit(main())
