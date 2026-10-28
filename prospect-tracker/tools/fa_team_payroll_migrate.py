# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Replay a fa_team_payroll snapshot into prospects.db, or dump one.

The Club Ledger's Payroll now block reads fa_team_payroll (Spotrac's tax and
payroll pages, upserted by fa_pipeline.refresh_payroll) while its payroll
history row for the same season reads the cached pages. A refetch run in a
worktree lands in that worktree's copy of the database, so the rows it wrote
travel as a snapshot (tools/migrations/fa_team_payroll_<date>.json) and this
script replays them on the main tree: same payload, same fetched_at, so the
served figures and their capture dates come out identical. Idempotent: a row
already equal to the snapshot is left alone and counted as unchanged.

    python tools/fa_team_payroll_migrate.py tools/migrations/fa_team_payroll_2026-10-27.json
    python tools/fa_team_payroll_migrate.py --dump tools/migrations/fa_team_payroll_<date>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import storage  # noqa: E402


def dump(path: Path) -> int:
    rows = []
    with storage.connect() as con:
        for team, season, payload, at in con.execute(
                "SELECT team, season, payload_json, fetched_at FROM fa_team_payroll ORDER BY season, team"):
            rows.append({"team": team, "season": int(season), "fetched_at": at, "payload": json.loads(payload)})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"table": "fa_team_payroll", "rows": rows}, indent=1, ensure_ascii=False) + chr(10),
                    encoding="utf-8")
    return len(rows)


def apply(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc.get("table") == "fa_team_payroll", path
    n = {"inserted": 0, "updated": 0, "unchanged": 0}
    with storage.connect() as con:
        for r in doc["rows"]:
            payload = json.dumps(r["payload"])
            cur = con.execute("SELECT payload_json, fetched_at FROM fa_team_payroll WHERE team = ? AND season = ?",
                              (r["team"], r["season"])).fetchone()
            if cur and json.loads(cur[0]) == r["payload"] and cur[1] == r["fetched_at"]:
                n["unchanged"] += 1
                continue
            con.execute(
                "INSERT INTO fa_team_payroll (team, season, payload_json, fetched_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(team, season) DO UPDATE SET payload_json = excluded.payload_json, "
                "fetched_at = excluded.fetched_at",
                (r["team"], r["season"], payload, r["fetched_at"]))
            n["updated" if cur else "inserted"] += 1
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="replay or dump a fa_team_payroll snapshot")
    ap.add_argument("path", type=Path)
    ap.add_argument("--dump", action="store_true", help="write the table to PATH instead of replaying it")
    args = ap.parse_args(argv)
    if args.dump:
        print(f"dumped {dump(args.path)} rows to {args.path}")
        return 0
    print(f"fa_team_payroll from {args.path}: {apply(args.path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
