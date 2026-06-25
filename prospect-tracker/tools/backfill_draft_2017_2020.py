# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""One-time, re-runnable backfill: populate draft_results (the drafting org) for
the 2017-2020 classes so those draftees resolve to "Draft", not "International FA".

Root cause this addresses: the FanGraphs draft summary "Pick" cell encodes the
pick + org as ``<overall>/<TEAM>`` in 2019 but ``<TEAM>/<overall>`` in 2018 &
2020. The old fixed-order parser silently dropped the 2018/2020 picks, so no
draft_results rows were written -> draft_promotion had nothing to link -> the
acquisition-type classifier fell back to International FA. draft_csv._parse_pick_cell
is now order-agnostic; the 2017 board is pre-draft (no picks at all), so its org
comes from the MLB Stats API draft tracker.

Idempotent: draft_results upserts on (draft_year, pick_overall); promotion and
export are safe to re-run. draft_snapshots are NOT touched here (they already
exist; promote_drafted_players flips their status from the new results).

Durable fix: the parser change in draft_csv.py means every future run_monthly
re-derives 2018/2019/2020 results correctly from the CSVs, and run_monthly now
scrapes the 2017+ tracker. This script just applies the fix to the current DB.

Usage:
    python tools/backfill_draft_2017_2020.py --dry-run   # report only, no writes
    python tools/backfill_draft_2017_2020.py             # apply
"""
from __future__ import annotations

import logging
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("backfill_draft")


def _result_counts() -> dict:
    from storage import load_draft_results
    return dict(sorted(Counter(r["draft_year"] for r in load_draft_results()).items()))


def main(dry_run: bool = False) -> None:
    from draft_csv import (DROP_DIR, _group_flat, _group_subfolders,
                           _merged_to_result_row, _parse_draft_summary_row)
    from fangraphs_csv import _read_csv_rows
    from storage import upsert_draft_results

    print("draft_results BEFORE:", _result_counts())

    # 1) Re-derive draft_results from the FG draft summary CSVs using the now
    #    order-agnostic Pick parser. A result row needs only the summary row.
    groups = _group_subfolders(DROP_DIR) + _group_flat(DROP_DIR)
    for grp in sorted(groups, key=lambda g: g.get("draft_year") or 0):
        if "summary" not in grp:
            continue
        year = grp["draft_year"]
        summ = [r for r in (_parse_draft_summary_row(x, year)
                            for x in _read_csv_rows(grp["summary"])) if r]
        results = [r for r in (_merged_to_result_row(m) for m in summ) if r]
        no_pick = sum(1 for m in summ if not m.get("pick_overall"))
        print(f"  {year}: {len(summ)} summary rows -> {len(results)} draft_results "
              f"({no_pick} rows carry no pick)")
        if not dry_run and results:
            upsert_draft_results(results)

    # 2) 2017 org from the MLB Stats API draft tracker (the FG 2017 board is a
    #    pre-draft ranking with no picks).
    from scrapers import scrape_mlb_draft_tracker
    rows17 = scrape_mlb_draft_tracker(2017) or []
    print(f"  2017 MLB tracker: scraped {len(rows17)} pick rows")
    if not dry_run and rows17:
        upsert_draft_results(rows17)

    if dry_run:
        print("DRY RUN — no writes performed. draft_results unchanged:", _result_counts())
        return

    # 3) Promote: acquisitions (method='draft') + draft->MiLB link + status flip.
    from draft_promotion import promote_drafted_players
    promote_drafted_players()

    # 4) Re-export the frontend draft sidecar.
    from draft_export import export_draft_json
    n = export_draft_json(ROOT / "data" / "draft_timeseries.json")
    print(f"  export_draft_json: {n} prospects")

    print("draft_results AFTER:", _result_counts())


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
