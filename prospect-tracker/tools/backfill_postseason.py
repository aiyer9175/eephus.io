"""One-off backfill of the postseason series cache (F-SCORE plan FS-1).

    python tools/backfill_postseason.py --seasons 2000-2026 [--write-tracked]
        [--max-calls N] [--retries N] [--promote-rejected]

Fetches each season through postseason.fetch() into
.cache/statsapi_postseason_{Y}.json (a frozen season already cached costs no
call), reads each back through postseason.load(), and prints its identity
result and any feed note. --write-tracked also writes the trimmed, tracked,
unpublished copy of every complete season under data/_labs/postseason/.

THE CALL BUDGET. One GET per season, one retry allowed in all, and never more
than MAX_CALLS calls: 27 seasons and one retry is 28. --max-calls and
--retries only lower the budget, for a second run that must stay inside what
the first one left. The tool stops before a call that would pass the budget.
It makes no other network call of any kind.

A response the parser refuses is kept beside the cache (postseason.fetch
writes it as .rejected.json) and the run goes on to the next season, so one
refusal does not cost the rest of the budget; --promote-rejected re-validates
kept responses under the current parser, with no call, before fetching.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import postseason  # noqa: E402

MAX_CALLS = 28
RETRIES_ALLOWED = 1
PAUSE_S = 0.5


class BudgetSpent(Exception):
    pass


def _seasons(arg: str) -> list:
    if "-" in arg:
        a, b = arg.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in arg.split(",") if x.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seasons", default="2000-2026")
    ap.add_argument("--write-tracked", action="store_true")
    ap.add_argument("--max-calls", type=int, default=MAX_CALLS)
    ap.add_argument("--retries", type=int, default=RETRIES_ALLOWED)
    ap.add_argument("--promote-rejected", action="store_true")
    args = ap.parse_args(argv)
    seasons = _seasons(args.seasons)
    max_calls = min(int(args.max_calls), MAX_CALLS)
    retries_allowed = min(int(args.retries), RETRIES_ALLOWED)
    if len(seasons) + retries_allowed > MAX_CALLS:
        print(f"refused: {len(seasons)} seasons and {retries_allowed} retry pass the "
              f"{MAX_CALLS}-call budget")
        return 2

    state = {"calls": 0, "retries": 0}
    refused: list = []

    def counted_get(url: str):
        if state["calls"] >= max_calls:
            raise BudgetSpent(f"call {state['calls'] + 1} would pass the budget of {max_calls}")
        state["calls"] += 1
        if state["calls"] > 1:
            time.sleep(PAUSE_S)
        return postseason._http_get(url)

    today = date.today()
    failures = 0
    total_bytes = 0
    for y in seasons:
        got = None
        if args.promote_rejected and postseason.rejected_path(y).exists():
            try:
                got = postseason.promote_rejected(y)
            except postseason.PostseasonError as e:
                print(f"{y}: REFUSED again {e}")
                refused.append(y)
                continue
        while got is None:
            try:
                got = postseason.fetch(y, today=today, http_get=counted_get)
                break
            except BudgetSpent as e:
                print(f"{y}: STOP {e}")
                return 3
            except postseason.PostseasonError as e:
                print(f"{y}: REFUSED {e} (response kept beside the cache)")
                refused.append(y)
                break
            except Exception as e:                              # noqa: BLE001
                if state["retries"] < retries_allowed:
                    state["retries"] += 1
                    print(f"{y}: retry after {type(e).__name__}: {e}")
                    continue
                print(f"{y}: STOP fetch failed after the one retry: {type(e).__name__}: {e}")
                return 5
        if got is None:
            continue
        try:
            parsed = postseason.load(y)
        except postseason.PostseasonError as e:
            print(f"{y}: STOP identity: {e}")
            return 4
        if parsed is None:
            print(f"{y}: {got['action']} ({got['reason']}); nothing on disk")
            failures += 1
            continue
        if parsed["complete"] and parsed["placeholders"]:
            print(f"{y}: STOP placeholder ids on a complete season: {parsed['placeholders']}")
            return 4
        clubs = parsed["clubs"]
        champ = [c for c, v in clubs.items() if v["round_reached"] == 5]
        pennants = sorted(c for c, v in clubs.items() if v["round_reached"] >= 4)
        n1 = sum(1 for v in clubs.values() if v["round_reached"] >= 1)
        byes = sorted(c for c, v in clubs.items() if v["bye"])
        counts = tuple(sum(1 for v in clubs.values() if v["round_reached"] >= k) for k in range(1, 6))
        status = "identities hold" if parsed["complete"] else "in progress, identities not asserted"
        line = (f"{y}: {got['action']} ({got['reason']}); {status}; series {len(parsed['series'])}; "
                f"round-1 {n1}; counts {counts}; champion {','.join(champ) or '-'}; "
                f"pennants {','.join(pennants) or '-'}; byes {','.join(byes) or '-'}")
        for note in postseason.feed_notes(parsed):
            line += f"; {note}"
        if args.write_tracked and parsed["complete"]:
            w = postseason.write_tracked(y)
            total_bytes += w["bytes"]
            line += f"; tracked {w['bytes']} bytes"
        print(line)
    print(f"calls {state['calls']} (retries {state['retries']}); tracked bytes {total_bytes}"
          + (f"; REFUSED {refused}" if refused else ""))
    if refused:
        return 4
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
