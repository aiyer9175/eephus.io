# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""AAA Statcast hitter sidecar - the batter analog of stuff_plus_aaa.json.

  DATA     the CACHED Savant minors batter aggregates (the statcast-search
           minors player CSV arkmetric_forward_eval.savant_rows already
           maintains per season; AAA tracked parks, coverage begins 2023).
           OFFLINE ONLY: this module never fetches - the SC+ eval refresh
           owns the cache.
  ROWS     each mlbam with >= 100 PA in a season; the LATEST qualified
           season wins (seasons walked ascending, later overwrites).
  FIELDS   xwoba / woba / xslg / slg, ev (launch_speed), hardhit_percent,
           barrels_per_bbe_percent, whiff (swing_miss_percent), bat_speed
           (null - the minors aggregate export does not carry it yet),
           luck_gap = round(xwoba - woba, 3) (positive = under-performed
           the contact quality), pa, season.

Sidecar: data/statcast_aaa_hitters.json {"generated_at", "note",
"by_mlbam": {mlbam: {...}}}. Consumer: a PROSPX hitter-card pill lands in
a later pass; until it does the file stays in deploy/data_exclude.txt.

Run: python statcast_aaa_hitters.py    (bake the sidecar from the cache)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "statcast_aaa_hitters.json"

SEASONS = (2023, 2024, 2025, 2026)   # AAA Statcast tracking begins 2023
MIN_PA = 100

NOTE = ("Savant minors (AAA tracked parks) batter aggregates 2023+, latest "
        ">=100 PA season per player; luck_gap = round(xwoba - woba, 3), "
        "positive = under-performed the contact quality")


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _r(v, nd: int):
    return None if v is None else round(v, nd)


def _row(r: dict, season: int) -> dict:
    xwoba = _r(_f(r.get("xwoba")), 3)
    woba = _r(_f(r.get("woba")), 3)
    return {
        "xwoba": xwoba,
        "woba": woba,
        "xslg": _r(_f(r.get("xslg")), 3),
        "slg": _r(_f(r.get("slg")), 3),
        "ev": _r(_f(r.get("launch_speed")), 1),
        "hardhit_percent": _r(_f(r.get("hardhit_percent")), 1),
        "barrels_per_bbe_percent": _r(_f(r.get("barrels_per_bbe_percent")), 1),
        "whiff": _r(_f(r.get("swing_miss_percent")), 1),
        "bat_speed": _r(_f(r.get("bat_speed")), 1),
        "luck_gap": (round(xwoba - woba, 3)
                     if xwoba is not None and woba is not None else None),
        "pa": int(_f(r.get("pa")) or 0),
        "season": season,
    }


def build(seasons=SEASONS) -> dict:
    """Payload from the cached CSVs only (fetch=False everywhere)."""
    import arkmetric_forward_eval as af
    by_mlbam: dict[str, dict] = {}
    for season in seasons:                       # ascending: latest wins
        n = 0
        for r in af.savant_rows(season, "batter", fetch=False):
            mid = _f(r.get("player_id"))
            pa = _f(r.get("pa"))
            if mid is None or pa is None or pa < MIN_PA:
                continue
            by_mlbam[str(int(mid))] = _row(r, season)
            n += 1
        log.info("aaa statcast hitters %d: %d qualified rows", season, n)
    return {"generated_at": date.today().isoformat(),
            "note": NOTE,
            "by_mlbam": by_mlbam}


def bake(persist: bool = True) -> dict:
    payload = build()
    if persist and payload["by_mlbam"]:
        OUT_PATH.write_text(json.dumps(payload, separators=(",", ":")),
                            encoding="utf-8")
        log.info("wrote %s (%d hitters)", OUT_PATH, len(payload["by_mlbam"]))
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = bake(persist="--dry-run" not in sys.argv)
    print("hitters:", len(out["by_mlbam"]))
