#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""fetch_win_prob_old - the play-by-play the PE-H old-seasons read needs for 2002 to
2010 (docs/ewar-v3/EWAR_PEH_OLD_SEASONS_GATE.md, owner decision EW3-50).

WHAT IT WRITES. The winProbability payload of every FINAL regular-season game of
2002 to 2010 into ``.cache/win_prob_old/<game_pk>.json``, with the schedule, the
receipts, the summary and the log beside it, through the paced receipt fetcher
``tools/fetch_win_prob_hist.py`` (its run(), Pacer, receipts, healing and tie rule,
unchanged). 2011 to 2015 are already in ``.cache/win_prob_hist`` and are not
fetched again. The directory is a sibling of the history directory, never
``.cache/win_prob`` (the corpus and the win-expectancy table glob that one), never
``.cache/win_prob_hist`` (eBR's runner record reads that one's seasons), and never
the corpus or the runner record.

POLITE. One request a second at most (the history fetcher's Pacer), the house
User-Agent, one payload at a time, and no request between 06:00 and 11:00 UTC, the
nightly fetch window: a request due inside it waits until 11:00 UTC.

Run (outside any pipeline run; about 21,900 games, about 16 GB, about seven hours):
    python tools/fetch_win_prob_old.py [--seasons 2002-2010] [--limit N]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import logging
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parent
for _p in (str(REPO_ROOT), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fetch_win_prob_hist as FH  # noqa: E402

OLD_SEASONS: tuple[int, ...] = tuple(range(2002, 2011))
OLD_DIR = REPO_ROOT / ".cache" / "win_prob_old"
#: The nightly fetch window, UTC hours [start, end).
QUIET_UTC = (6, 11)


def seconds_until_open(now: _dt.datetime, quiet=QUIET_UTC) -> float:
    """0 outside the nightly window; else the seconds until it closes."""
    a, b = quiet
    if a <= now.hour < b:
        end = now.replace(hour=b, minute=0, second=0, microsecond=0)
        return max(0.0, (end - now).total_seconds())
    return 0.0


class WindowPacer(FH.Pacer):
    """The history fetcher's Pacer, plus no request inside the nightly window."""

    def __init__(self, *a, utcnow=None, **k):
        super().__init__(*a, **k)
        self.utcnow = utcnow or (lambda: _dt.datetime.now(_dt.timezone.utc))

    def wait(self) -> None:
        gap = seconds_until_open(self.utcnow())
        if gap > 0:
            logging.getLogger("fetch_win_prob_old").info("nightly window: waiting %.0f s", gap)
            self.sleep(gap + 1.0)
        super().wait()


def parse_seasons(s: str) -> list:
    out = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    bad = [x for x in out if x not in OLD_SEASONS]
    if bad:
        raise SystemExit(f"old seasons are {OLD_SEASONS}; refusing {bad}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2002-2010")
    ap.add_argument("--limit", type=int, default=None, help="at most N requests this run")
    a = ap.parse_args(argv)
    out_dir = FH.check_out_dir(OLD_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(out_dir / "fetch.log", encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])
    t0 = time.time()
    summ = FH.run(parse_seasons(a.seasons), out_dir=out_dir, limit=a.limit, pacer=WindowPacer())
    tot = sum(b["fetched"] for b in summ["seasons"].values())
    mb = sum(b["bytes"] for b in summ["seasons"].values()) / 1e6
    print(f"done: {tot} payloads, {mb:.1f} MB, {summ['requests']} requests in {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
