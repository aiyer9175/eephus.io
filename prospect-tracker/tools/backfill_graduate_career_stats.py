# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Re-fetch career_stats for graduated players with the current builder so each
season row carries its per-season org + per-org split stints.

Graduated players' career stats are intentionally "frozen" (run_monthly skips
them — their MiLB career is over), but many were frozen BEFORE the per-season
org + split-stints feature existed, so their stored rows lack `org` and
`stints`. That made the prospect-detail career table fall back to the current
org (e.g. Cole Ragans 2022 showing KCR instead of TEX) and never render the
in-season-trade dual chips (his 2023 KC split was dropped entirely).

Re-fetching rebuilds each career via stats._row_from_split + _combine_stints
(org per (season, level); stints for multi-org seasons). Idempotent. After
running, regenerate the exports (run_monthly.rebuild_only) so debuts.json /
timeseries.json carry the refreshed rows.

Usage:
    python tools/backfill_graduate_career_stats.py --limit=5   # smoke test
    python tools/backfill_graduate_career_stats.py --stale     # only org-less rows
    python tools/backfill_graduate_career_stats.py             # all graduates
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
logging.basicConfig(level=logging.ERROR)


def _is_pitcher_map() -> tuple[dict, set]:
    """{player_key: is_pitcher} + the set of stale (org-less) keys, from the
    existing career_stats payloads."""
    con = sqlite3.connect(str(ROOT / "prospects.db"))
    con.row_factory = sqlite3.Row
    isp, stale = {}, set()
    for r in con.execute("SELECT player_key, payload_json FROM career_stats"):
        try:
            rows = json.loads(r["payload_json"]) or []
        except Exception:
            rows = []
        if rows:
            isp[r["player_key"]] = bool(rows[0].get("is_pitcher"))
            if all("org" not in s for s in rows):
                stale.add(r["player_key"])
    con.close()
    return isp, stale


def main(only_stale: bool = False, limit: int | None = None) -> None:
    from stats import fetch_career_stats
    from storage import upsert_career_stats

    isp, stale = _is_pitcher_map()
    grads = json.loads((ROOT / "data" / "debuts.json").read_text(encoding="utf-8"))
    targets = [(p["player_key"], p.get("mlbam_id")) for p in grads
               if p.get("player_key") and p.get("mlbam_id")]
    if only_stale:
        targets = [t for t in targets if t[0] in stale]
    if limit:
        targets = targets[:limit]
    print(f"re-fetching career_stats for {len(targets)} graduates "
          f"(only_stale={only_stale})")

    def _work(item):
        key, mlbam = item
        try:
            rows = fetch_career_stats(key, int(mlbam), is_pitcher=isp.get(key, False))
            return key, rows
        except Exception:
            return key, None

    n_ok = n_fail = 0
    batch: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(_work, t) for t in targets]
        for i, f in enumerate(as_completed(futs)):
            key, rows = f.result()
            if rows:
                batch[key] = rows
                n_ok += 1
            else:
                n_fail += 1
            if len(batch) >= 250:
                upsert_career_stats(batch)
                batch = {}
            if (i + 1) % 250 == 0:
                print(f"  {i + 1}/{len(targets)} (ok={n_ok} fail={n_fail})")
    if batch:
        upsert_career_stats(batch)
    print(f"done: refreshed={n_ok} failed/empty={n_fail}")


if __name__ == "__main__":
    _limit = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--limit=")), None)
    main(only_stale="--stale" in sys.argv, limit=_limit)
