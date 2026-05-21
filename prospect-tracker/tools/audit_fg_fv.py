"""Audit FanGraphs FV values stored in the snapshots table against the
raw CSVs in `data/fangraphs_imports/processed/`. Reports any drift so
we can verify a re-ingest landed.

Exit code:
  0 — every CSV row has a matching DB snapshot with the same FV
  1 — drift exists (each mismatch printed to stdout)

Usage:
    python tools\\audit_fg_fv.py
"""

from __future__ import annotations

import csv
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from fangraphs_csv import _parse_summary_row  # type: ignore


def _slug_from_folder(folder: Path) -> str:
    return folder.name.split("__", 1)[0]


def _expected_rows_for_slug(slug_folder: Path) -> dict[str, float]:
    """Walk summary-<slug>.csv inside the slug folder. Returns a dict
    {player_key: fv} after applying the same name-key collision rule as
    `_join_report_set` (higher FV wins)."""
    by_key: dict[str, tuple[str | None, float]] = {}
    for csv_path in slug_folder.glob("summary-*.csv"):
        with csv_path.open(encoding="utf-8") as fp:
            for raw in csv.DictReader(fp):
                parsed = _parse_summary_row(raw)
                if not parsed:
                    continue
                pk = parsed["player_key"]
                fv = parsed.get("fv")
                if fv is None:
                    continue
                pid = parsed.get("fg_player_id")
                existing = by_key.get(pk)
                if existing is None:
                    by_key[pk] = (pid, fv)
                elif fv > existing[1]:
                    by_key[pk] = (pid, fv)
    return {k: v[1] for k, v in by_key.items()}


def main() -> int:
    db_path = _ROOT / "prospects.db"
    if not db_path.exists():
        print(f"audit_fg_fv: db not found at {db_path}")
        return 1
    drops_root = _ROOT / "data" / "fangraphs_imports" / "processed"
    if not drops_root.exists():
        print(f"audit_fg_fv: drops not found at {drops_root}")
        return 1

    con = sqlite3.connect(str(db_path))
    drift = 0
    missing = 0
    for slug_folder in sorted(drops_root.iterdir()):
        if not slug_folder.is_dir():
            continue
        slug = _slug_from_folder(slug_folder)
        # interval_label in the snapshots table is the slug verbatim
        # (see fangraphs_csv._build_snapshot).
        interval_label = slug

        expected = _expected_rows_for_slug(slug_folder)
        if not expected:
            continue

        # Pull all FG snapshots for this interval_label in one shot.
        db_rows = {
            pk: fv
            for pk, fv in con.execute(
                "SELECT player_key, fv FROM snapshots "
                "WHERE source='fangraphs' AND interval_label=?",
                (interval_label,),
            )
        }

        for pk, csv_fv in expected.items():
            db_fv = db_rows.get(pk)
            if db_fv is None:
                missing += 1
                print(f"MISSING  {slug:<25} {pk:<35} csv_fv={csv_fv}")
            elif abs(csv_fv - db_fv) > 1e-6:
                drift += 1
                print(
                    f"DRIFT    {slug:<25} {pk:<35} "
                    f"csv_fv={csv_fv} db_fv={db_fv} delta={db_fv - csv_fv:+.1f}"
                )

    if drift == 0 and missing == 0:
        print("audit_fg_fv: clean — every CSV row matches the DB.")
        return 0
    print(f"audit_fg_fv: {drift} drift, {missing} missing.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
