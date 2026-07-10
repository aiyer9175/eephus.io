# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Backfill real per-player transactions for TRADED graduates + purge the bogus
"inferred" trades that polluted their ledgers.

Why: graduated players aren't re-scanned by run_monthly (their career is frozen),
so their /transactions cache is stale — e.g. Cole Ragans had a single transaction
row and five WRONG source='inferred' KCR<->TEX offseason "trades" (2017-2019),
while his real 2023 KC option + Omaha Storm Chasers assignments were never stored.
The MLB transactions API has no "TR" row for some real trades (the Ragans/Chapman
deal is one), so the inferred fallback is unreliable; for traded graduates we now
hold the authoritative org-per-season timeline (career_stats stints), so the
inferred trades add nothing but noise.

This script, for every graduate whose career spans 2+ orgs:
  1. Fetches the real /transactions history (options, recalls, assignments,
     waivers, DFAs, IL) across their career window and upserts player_transactions.
  2. Deletes their source='inferred' trades.

The authoritative MLB-API trades (source='mlb_api') are left untouched. After
running, regenerate the exports (run_monthly.rebuild_only). Idempotent.

Usage:
    python tools/backfill_graduate_transactions.py --limit=5   # smoke test
    python tools/backfill_graduate_transactions.py             # all traded grads
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
logging.basicConfig(level=logging.ERROR)


def _traded_graduates() -> list[tuple[str, int, int]]:
    """[(player_key, mlbam_id, first_season)] for graduates with 2+ career orgs."""
    con = sqlite3.connect(str(ROOT / "prospects.db"))
    con.row_factory = sqlite3.Row
    grads = json.loads((ROOT / "data" / "debuts.json").read_text(encoding="utf-8"))
    mlbam = {p["player_key"]: p.get("mlbam_id") for p in grads if p.get("mlbam_id")}
    out: list[tuple[str, int, int]] = []
    for key, mid in mlbam.items():
        r = con.execute("SELECT payload_json FROM career_stats WHERE player_key=?", (key,)).fetchone()
        if not r:
            continue
        rows = json.loads(r["payload_json"]) or []
        orgs, seasons = set(), []
        for s in rows:
            if s.get("org"):
                orgs.add(s["org"])
            for st in (s.get("stints") or []):
                if st.get("org"):
                    orgs.add(st["org"])
            if s.get("season"):
                seasons.append(int(s["season"]))
        if len(orgs) >= 2:
            out.append((key, int(mid), min(seasons) if seasons else 2010))
    con.close()
    return out


def main(limit: int | None = None) -> None:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import date
    from stats import fetch_player_transactions
    from storage import upsert_player_transactions

    targets = _traded_graduates()
    if limit:
        targets = targets[:limit]
    keys = [t[0] for t in targets]
    print(f"traded graduates: {len(targets)}")

    this_year = date.today().year

    def _work(item):
        key, mid, first = item
        try:
            return key, fetch_player_transactions(key, mid, start_year=min(first, this_year), end_year=this_year)
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
                upsert_player_transactions(batch)
                batch = {}
            if (i + 1) % 250 == 0:
                print(f"  {i + 1}/{len(targets)} (ok={n_ok} fail={n_fail})")
    if batch:
        upsert_player_transactions(batch)
    print(f"player_transactions refreshed: ok={n_ok} fail/empty={n_fail}")

    # Purge bogus inferred trades for these traded graduates (authoritative
    # mlb_api trades are kept).
    con = sqlite3.connect(str(ROOT / "prospects.db"))
    placeholders = ",".join("?" * len(keys))
    before = con.execute(
        f"SELECT COUNT(*) FROM trades WHERE source='inferred' AND player_key IN ({placeholders})",
        keys,
    ).fetchone()[0]
    con.execute(
        f"DELETE FROM trades WHERE source='inferred' AND player_key IN ({placeholders})",
        keys,
    )
    con.commit()
    con.close()
    print(f"purged {before} bogus inferred trades across traded graduates")


if __name__ == "__main__":
    _limit = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--limit=")), None)
    main(limit=_limit)
