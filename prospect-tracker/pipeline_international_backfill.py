# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Pipeline international-list backfill, 2021 -> current (owner ask
2026-06-12).

mlb.com serves year-keyed international Top-50 pages
(`/milb/prospects/{year}/international/`) with the same Apollo cache the
Top-100 archive uses; each row may carry a 20-80 "Overall:" grade. The
list mixes two populations, routed per the owner's sorting directive:

  1. names matching a TRACKED PROSPECT -> the grade lands on that
     prospect's source history as an era-dated
     `mlb_pipeline_international` snapshot (the IFA signees, plus posted
     pros who have since become stateside prospects);
  2. names matching an OVERSEAS PLAYER (the FG NPB/KBO/CPBL boards) ->
     the grade lands in overseas_snapshots as an `mlb_pipeline` row, so
     the Overseas section gains a second source;
  3. neither -> data/intl_amateur_unmatched.json (nothing silently
     dropped; unsigned July-2 names match on a later run once their
     class signs and they enter the players table).

Era dating: {year}-01-15 - the signing-window open the lists are built
around. The current year's live list stays the monthly scraper's job;
this module only backfills the year-keyed archive pages.

Run: python pipeline_international_backfill.py [--force]
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

from scrapers import scrape_mlb_international
from intl_amateur import match_player, _player_index, UNMATCHED_PATH

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
YEARS = (2021, 2022, 2023, 2024, 2025)


def _overseas_index() -> dict[str, dict]:
    """normalized name -> {player_key, league, country} from the overseas store."""
    import storage
    from scrapers import normalize_key, fix_mojibake
    with storage.connect() as con:
        rows = con.execute(
            "SELECT player_key, player_name, league, country FROM overseas_players").fetchall()
    idx = {}
    for key, name, league, country in rows:
        nk = normalize_key(fix_mojibake(name or ""))
        idx.setdefault(nk, {"player_key": key, "league": league, "country": country})
    return idx


def run(force: bool = False, years=YEARS) -> dict:
    import storage
    from scrapers import normalize_key, fix_mojibake
    pidx = _player_index()
    oidx = _overseas_index()
    totals = {"prospect_snapshots": 0, "overseas_snapshots": 0, "unmatched": 0,
              "rows_seen": 0, "rows_with_fv": 0}
    unmatched_all: list[dict] = []
    for y in years:
        snap_date = f"{y}-01-15"
        label = f"MLB Pipeline {y} International ({snap_date})"
        rows = scrape_mlb_international(
            f"https://www.mlb.com/milb/prospects/{y}/international/",
            label, snap_date, y, force=force, skip_unaffiliated=False)
        totals["rows_seen"] += len(rows)
        pros, overseas_rows, unmatched = [], [], []
        for r in rows:
            if r.fv is None:
                continue
            totals["rows_with_fv"] += 1
            nk = normalize_key(fix_mojibake(r.player_name or ""))
            if nk in pidx:
                pros.append(r._replace(player_key=pidx[nk]) if hasattr(r, "_replace")
                            else r)
                continue
            o = oidx.get(nk)
            if o:
                overseas_rows.append({
                    "source": "mlb_pipeline",
                    "snapshot_date": snap_date,
                    "interval_label": label,
                    "player_key": o["player_key"],
                    "player_name": r.player_name,
                    "position": r.position,
                    "league": o.get("league"),
                    "country": o.get("country"),
                    "current_team": None, "proj_team": None,
                    "proj_bonus_usd": None, "eta_year": None,
                    "fv": r.fv,
                })
                continue
            unmatched.append({"player_name": r.player_name, "fv": r.fv,
                              "position": r.position, "snapshot_date": snap_date,
                              "interval_label": label, "source": "mlb_pipeline"})
        if pros:
            # dataclass Snapshot is frozen=False in scrapers; ensure the key
            # points at the tracked player (accent-normalized names can
            # differ from the page's normalize_key output).
            for r in pros:
                r.player_key = pidx[normalize_key(fix_mojibake(r.player_name or ""))]
            totals["prospect_snapshots"] += storage.insert_snapshots(pros)
        if overseas_rows:
            totals["overseas_snapshots"] += storage.insert_overseas_snapshots(overseas_rows)
        unmatched_all.extend(unmatched)
        log.info("pipeline intl %d: %d rows, %d prospect snaps, %d overseas, %d unmatched",
                 y, len(rows), len(pros), len(overseas_rows), len(unmatched))
    totals["unmatched"] = len(unmatched_all)
    if unmatched_all:
        try:
            existing = json.loads(UNMATCHED_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = []
        seen = {(e.get("player_name"), e.get("snapshot_date")) for e in existing}
        for u in unmatched_all:
            sig = (u.get("player_name"), u.get("snapshot_date"))
            if sig not in seen:
                existing.append(u)
                seen.add(sig)
        UNMATCHED_PATH.write_text(json.dumps(existing, indent=1, ensure_ascii=False),
                                  encoding="utf-8")
    return totals


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(json.dumps(run(force="--force" in sys.argv), indent=1))
