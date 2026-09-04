# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Widen the stored transaction history back to the eFV label window (2011).

WHY. `stats.TRANSACTIONS_LOOKBACK_SEASONS` is 7, so every stored payload starts at
today.year - 7, which is 2019. Its comment says older rows "aren't load-bearing for any
downstream derivation", and that was true when it was written. It stopped being true when
the health-profile lane started reading injured-list history: the eFV label window opens at
debut year 2011, so pre-decision injury coverage was 0 percent for every 2016-2018 debut and
the lane could only score about half its pool. Not one of the 2,260 matrix players with an
mlbam id carried a single pre-2019 transaction.

The endpoint is NOT the constraint. Probed 2026-09-04 with an explicit start_year: Byron
Buxton returns injured-list events back to 2014, Aaron Nola to 2016, Mike Trout to 2017.
The window we ask for is the whole limit.

THE SUPERSET GUARD is the reason this is a tool and not a one-liner. `upsert_player_
transactions` REPLACES a player's payload with whatever list it is handed, so a fetch that
half-fails would silently truncate real history. A widened window can only ever return a
superset of a narrower one, so this refuses to write any player whose new list is shorter
than the stored one, and reports those players instead of overwriting them.

Run:
    python tools/backfill_player_transactions.py                 # DRY RUN, no writes
    python tools/backfill_player_transactions.py --apply
    python tools/backfill_player_transactions.py --apply --first 2011 --workers 8
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import stats                                # noqa: E402
import storage                              # noqa: E402

DEFAULT_FIRST = 2011        # efv_dataset's label window opens here
MATRICES = ("data/xfv_hitter_matrix.json", "data/xfv_pitcher_matrix.json")


def targets() -> dict[str, int]:
    out: dict[str, int] = {}
    for f in MATRICES:
        p = ROOT / f
        if not p.exists():
            continue
        for r in json.loads(p.read_text(encoding="utf-8")):
            mid = r.get("mlbam_id")
            if mid and r.get("player_key"):
                try:
                    out[r["player_key"]] = int(mid)
                except (TypeError, ValueError):
                    continue
    return out


def stored() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    with storage.connect() as con:
        for key, payload in con.execute(
                "select player_key, payload_json from player_transactions"):
            try:
                out[key] = json.loads(payload) or []
            except (TypeError, ValueError):
                out[key] = []
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write; default is a dry run")
    ap.add_argument("--first", type=int, default=DEFAULT_FIRST)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="probe the first N players only")
    a = ap.parse_args()

    tgt = targets()
    have = stored()
    keys = sorted(tgt)
    if a.limit:
        keys = keys[:a.limit]
    print(f"targets {len(keys)} players | window {a.first}-{time.gmtime().tm_year} "
          f"| {'APPLY' if a.apply else 'DRY RUN'}", flush=True)

    fetched: dict[str, list[dict]] = {}
    t0 = time.time()
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        futs = {ex.submit(stats.fetch_player_transactions, k, tgt[k], start_year=a.first): k
                for k in keys}
        for fut in concurrent.futures.as_completed(futs):
            k = futs[fut]
            done += 1
            try:
                fetched[k] = fut.result() or []
            except Exception:
                fetched[k] = []
            if done % 200 == 0:
                print(f"  {done}/{len(keys)}  {time.time()-t0:.0f}s", flush=True)

    write: dict[str, list[dict]] = {}
    refused, empty, gained_rows, gained_pre = [], 0, 0, 0
    players_gaining_pre = 0
    for k, rows in fetched.items():
        old = have.get(k) or []
        if not rows:
            empty += 1
            continue
        if len(rows) < len(old):
            refused.append((k, len(old), len(rows)))
            continue
        pre_new = sum(1 for t in rows if str(t.get("date") or "")[:4] < "2019")
        pre_old = sum(1 for t in old if str(t.get("date") or "")[:4] < "2019")
        if pre_new > pre_old:
            players_gaining_pre += 1
        gained_pre += max(0, pre_new - pre_old)
        gained_rows += max(0, len(rows) - len(old))
        write[k] = rows

    print(f"\nfetched {len(fetched)} | empty {empty} | REFUSED (new shorter than stored) "
          f"{len(refused)} | writable {len(write)}")
    print(f"  rows gained {gained_rows} | PRE-2019 events gained {gained_pre} "
          f"across {players_gaining_pre} players")
    for k, o, n in refused[:10]:
        print(f"    refused {k}: stored {o} rows, fetch returned {n}")

    if not a.apply:
        print("\nDRY RUN: no writes. Pass --apply.")
        return 0
    n = storage.upsert_player_transactions(write)
    print(f"wrote {n} player rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
