# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One-shot v26 migration: restore '+' upside flag + canonical tier FV.

Before v26, `_parse_fv("55+")` returned 57.5 (interpolated halfway to the
next tier). Snapshots accumulated two forms of legacy data:

  1. fv = 57.5 (REAL, from a fresh ingest under the old parser)
  2. fv = 57 (INTEGER, after some int-cast path truncated 57.5 → 57)

Both shapes need the same fix: snap fv DOWN to the canonical 20-80 tier
(57.5 → 55, 57 → 55) and SET fv_plus = 1. Tier-aligned values (multiples
of 5 within 20-80) stay untouched.

Targets snapshots, draft_snapshots, and overseas_snapshots. Idempotent —
running it twice does nothing on the second pass because all rows have
been snapped to multiples of 5.

Usage:
    python tools/migrate_fv_plus_from_decimal.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "prospects.db"
TABLES = ("snapshots", "draft_snapshots", "overseas_snapshots")


def main() -> int:
    if not DB_PATH.exists():
        print(f"no DB at {DB_PATH} - nothing to migrate")
        return 0
    total = 0
    con = sqlite3.connect(str(DB_PATH))
    try:
        for tbl in TABLES:
            try:
                # Off-tier = fv not a multiple of 5 inside the 20-80 band.
                # Captures both .5 floats (57.5) and post-truncation ints
                # (57). The 20-80 band excludes garbage outliers (e.g., 4.0).
                n_before = con.execute(
                    f"SELECT COUNT(*) FROM {tbl} "
                    "WHERE fv IS NOT NULL AND fv BETWEEN 20 AND 80 "
                    "  AND (CAST(fv AS INTEGER) % 5) != 0 "
                    "OR (fv IS NOT NULL AND fv != CAST(fv AS INTEGER))"
                ).fetchone()[0]
            except sqlite3.OperationalError as e:
                print(f"skip {tbl}: {e}")
                continue
            if n_before == 0:
                print(f"{tbl}: 0 off-tier rows (already migrated)")
                continue
            # Snap fv DOWN to the nearest multiple of 5. Works for both
            # 57.5 (REAL) and 57 (INTEGER): CAST to INT then floor-div by 5
            # times 5 → 55. Apply fv_plus = 1 in the same UPDATE.
            n = con.execute(
                f"""UPDATE {tbl}
                    SET fv_plus = 1,
                        fv = (CAST(fv AS INTEGER) / 5) * 5
                    WHERE fv IS NOT NULL AND fv BETWEEN 20 AND 80
                      AND ((CAST(fv AS INTEGER) % 5) != 0
                           OR fv != CAST(fv AS INTEGER))"""
            ).rowcount
            con.commit()
            print(f"{tbl}: migrated {n} rows (off-tier fv -> canonical tier + fv_plus=1)")
            total += n
        print(f"\ntotal: {total} rows migrated across {len(TABLES)} tables")
        return total
    finally:
        con.close()


if __name__ == "__main__":
    main()
