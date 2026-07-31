# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Sync signing bonuses from the FG 2026 trade-deadline board CSV into
draft_results + acquisitions where ours are NULL/missing. Idempotent;
--dry-run default, --apply to write. Only touches 2026 draft-market rows
whose CSV Bonus is present AND our stored bonus is absent; never
overwrites an existing nonzero bonus (conflicts are listed, not touched).
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scrapers import normalize_key  # noqa: E402

CSV = (ROOT / "data" / "fangraphs_imports" / "processed"
       / "2026tradedeadline__2026-07-23" / "summary-2026tradedeadline.csv")


def main() -> int:
    apply = "--apply" in sys.argv
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== sync_fg_bonus_2026td [{mode}] ===")
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    cand = []
    for r in rows:
        if (r.get("Sign Yr") or "").strip() != "2026":
            continue
        if "draft" not in (r.get("Sign Mkt") or "").lower():
            continue
        b = (r.get("Bonus") or "").strip().replace(",", "").replace("$", "")
        if not b:
            continue
        try:
            bonus = int(float(b))
        except ValueError:
            continue
        cand.append((normalize_key(r["Name"]), r["Name"], bonus))
    print(f"CSV bonus candidates (2026 draft market): {len(cand)}")
    con = sqlite3.connect(ROOT / "prospects.db")
    con.row_factory = sqlite3.Row
    writes = 0
    for key, name, bonus in cand:
        dr = con.execute(
            "SELECT rowid, bonus_usd FROM draft_results WHERE player_key = ? "
            "AND draft_year = 2026", (key,)).fetchone()
        if dr is None:
            print(f"  [skip] {name}: no 2026 draft_results row (key {key})")
        elif dr["bonus_usd"]:
            if int(dr["bonus_usd"]) != bonus:
                print(f"  [conflict] {name}: ours {dr['bonus_usd']} vs FG "
                      f"{bonus} - NOT touched")
        else:
            print(f"  [set] draft_results {name} bonus_usd -> {bonus}")
            if apply:
                con.execute("UPDATE draft_results SET bonus_usd = ? WHERE "
                            "rowid = ?", (bonus, dr["rowid"]))
                writes += 1
        aq = con.execute(
            "SELECT rowid, bonus_usd FROM acquisitions WHERE player_key = ? "
            "AND year = 2026 AND method LIKE '%draft%'", (key,)).fetchone()
        if aq is not None and not aq["bonus_usd"]:
            print(f"  [set] acquisitions {name} bonus_usd -> {bonus}")
            if apply:
                con.execute("UPDATE acquisitions SET bonus_usd = ? WHERE "
                            "rowid = ?", (bonus, aq["rowid"]))
                writes += 1
    if apply:
        con.commit()
        print(f"=== APPLIED: {writes} write(s) ===")
    else:
        con.rollback()
        print("=== DRY-RUN: re-run with --apply to write ===")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
