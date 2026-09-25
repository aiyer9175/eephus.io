# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-09: backfill the LEAGUE-WIDE MLB transaction feed for 2008 to 2014.

WHY. The eFV V2 timing head reads protection status (on the 40-man at the list-vintage
read; a contract selection in November of V - 1) for list vintages from 2011. The monthly
league-wide cache .cache/mlb_transactions/tx_YYYY_MM.json.gz starts at 2015-01
(tools/pt_risk_lab.py fetch), so a 2011 to 2015 list row had no history before its read.
This tool fetches the 84 missing months, 2008-01 to 2014-12, in the same format.

WHY LEAGUE-WIDE AND NOT PER PLAYER. The per-player store (storage table
player_transactions, tools/backfill_player_transactions.py) is fetched by each record's
stored mlbam id, and records gained ids mostly on reaching the majors (bug B4), so its
coverage is a debut proxy. The league feed covers every player in a month whether he
later debuted or not; efv_drivers joins it on the OUTCOME-BLIND id (efv_identity).

Resumable: a month already on disk is skipped. Each month is written atomically.

Run:  python tools/backfill_mlb_transactions.py            (fetches what is missing)
      python tools/backfill_mlb_transactions.py --check    (lists missing months only)
"""
from __future__ import annotations

import argparse
import calendar
import gzip
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TX_DIR = ROOT / ".cache" / "mlb_transactions"
FIRST = (2008, 1)
LAST = (2014, 12)
URL = ("https://statsapi.mlb.com/api/v1/transactions"
       "?startDate={y}-{m:02d}-01&endDate={y}-{m:02d}-{d:02d}")


def months(first=FIRST, last=LAST):
    y, m = first
    while (y, m) <= last:
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def month_path(y: int, m: int) -> Path:
    return TX_DIR / f"tx_{y}_{m:02d}.json.gz"


def missing(first=FIRST, last=LAST) -> list[tuple[int, int]]:
    return [(y, m) for y, m in months(first, last) if not month_path(y, m).exists()]


def _get_json(url: str, tries: int = 3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "eephus-efv-v2-ds09"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  retry {i + 1} after {e}")
            time.sleep(2.0 * (i + 1))


def fetch(first=FIRST, last=LAST) -> dict:
    TX_DIR.mkdir(parents=True, exist_ok=True)
    done = {}
    for y, m in missing(first, last):
        url = URL.format(y=y, m=m, d=calendar.monthrange(y, m)[1])
        d = _get_json(url)
        out = month_path(y, m)
        tmp = out.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(d, fh)
        tmp.replace(out)
        done[f"{y}-{m:02d}"] = len(d.get("transactions", []))
        print(f"tx {y}-{m:02d}: {done[f'{y}-{m:02d}']}", flush=True)
        time.sleep(0.3)
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    gap = missing()
    print(f"missing months {FIRST[0]}-{FIRST[1]:02d}..{LAST[0]}-{LAST[1]:02d}: {len(gap)}")
    if args.check or not gap:
        return 0
    got = fetch()
    print(f"fetched {len(got)} months, {sum(got.values())} transactions")
    return 0 if not missing() else 1


if __name__ == "__main__":
    raise SystemExit(main())
