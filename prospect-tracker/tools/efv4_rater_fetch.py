"""Fetch the public historical rater lists for the eFV v4 rater panel (EFV4_RATER_PANEL).

Owner decision EW2-11 (2026-10-08): network fetches are allowed on 2026-10-08, 10-09 and 10-10
ONLY into this task's own cache folder `.cache/efv4_raters/`, never between 06:00 and 11:00 UTC,
politely (a descriptive User-Agent, one request at a time, a pause between requests, back off on
429 and 5xx) and resumably (a page already cached is never fetched again).

Only public pages are read. Baseball America's archive answers 403 without a subscription and is
skipped and named, never fetched with credentials; ESPN's Insider lists are paywalled, and their
Wayback copies carry the paywall shell only (probe: 2016 index, 2026-10-09), so they are named and
skipped; Baseball Prospectus put its 2021 list behind its paywall, so that page is cached
but holds no list. Each list's publication date is recorded so the builder can keep only lists dated inside
[V-01-01, V-05-01).

Attribution: Baseball Prospectus Top 101 (baseballprospectus.com) and FanGraphs prospect lists
(blogs.fangraphs.com, Marc Hulet 2011 to 2014, Kiley McDaniel 2015). The cached pages are research
inputs for an unserved lab column; nothing from them is displayed.

Usage:  python tools/efv4_rater_fetch.py            (fetch whatever is not cached)
        python tools/efv4_rater_fetch.py --dry-run  (list the plan)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "efv4_raters"
RAW = CACHE / "raw"
MANIFEST = CACHE / "manifest.json"

USER_AGENT = ("Mozilla/5.0 (compatible; prospx-efv4-raters/1.0; research, polite, "
              "one request at a time)")
PAUSE_S = 2.0

# (list_id, rater, year, url). Years 2011 to 2021 per the task; 2020 and 2021 are fetched as raw
# pages but the builder does not build a row of them until the registration names them.
SOURCES: list[tuple[str, str, int, str]] = [
    ("bp_2011", "bp", 2011, "https://www.baseballprospectus.com/prospects/article/13078/"),
    ("bp_2012", "bp", 2012, "http://www.baseballprospectus.com/article.php?articleid=16020"),
    ("bp_2013", "bp", 2013, "http://www.baseballprospectus.com/article.php?articleid=19694"),
    ("bp_2014", "bp", 2014, "http://www.baseballprospectus.com/article.php?articleid=22670"),
    ("bp_2015", "bp", 2015, "http://www.baseballprospectus.com/article.php?articleid=25538"),
    ("bp_2016", "bp", 2016, "http://www.baseballprospectus.com/article.php?articleid=28319"),
    ("bp_2017", "bp", 2017, "https://www.baseballprospectus.com/prospects/article/31160/"
                            "2017-prospects-the-top-101-prospects-of-2017/"),
    ("bp_2018", "bp", 2018, "https://www.baseballprospectus.com/prospects/article/37535/"
                            "baseball-prospectus-top-101-prospects-2018-top-mlb-prospects-ronald-"
                            "acuna-victor-robles-vladimir-guerrero-jr-eloy-jimenez/"),
    ("bp_2019", "bp", 2019, "https://www.baseballprospectus.com/news/article/46653/"
                            "2019-prospects-the-top-101/"),
    ("bp_2020", "bp", 2020, "https://www.baseballprospectus.com/prospects/article/56649/"
                            "2020-prospects-the-top-101-wander-franco-jo-adell-gavin-lux/"),
    ("bp_2021", "bp", 2021, "https://www.baseballprospectus.com/prospects/article/64061/"
                            "2021-prospects-the-top-101/"),
    ("fg_2011", "fg", 2011, "https://blogs.fangraphs.com/fangraphs-top-100-prospects/"),
    ("fg_2012", "fg", 2012, "https://blogs.fangraphs.com/top-100-prospects-for-2012/"),
    ("fg_2013", "fg", 2013, "https://blogs.fangraphs.com/fangraphs-top-100-prospects-2/"),
    ("fg_2014", "fg", 2014, "https://blogs.fangraphs.com/2014-top-100-prospects/"),
    ("fg_2015", "fg", 2015, "https://blogs.fangraphs.com/the-fangraphs-top-200-prospect-list/"),
]

# Named and skipped, with the reason recorded in the manifest.
SKIPPED: list[dict] = [
    {"rater": "ba", "years": "2011-2021",
     "reason": "baseballamerica.com archive and list pages answer 403 without a subscription "
               "(probe 2026-10-09); behind a login, never fetched with credentials"},
    {"rater": "espn", "years": "2011-2019",
     "reason": "Keith Law lists are ESPN Insider; the live page and the Wayback copy of the 2016 "
               "index (14740563, capture 20160323) carry the paywall shell only, no list"},
    {"rater": "bp", "years": "2021",
     "reason": "the 2021 Top 101 page (article 64061) is subscriber-only on the live site and "
               "on every Wayback capture of 2021-01-21 to 2021-01-29; the cached page holds "
               "no list"},
    {"rater": "fg", "years": "2016",
     "reason": "no FanGraphs overall 2016 top 100 found on blogs.fangraphs.com (site search and "
               "slug probes 2026-10-09); FanGraphs 2017 on is already a consensus source"},
]


def _fetch_window_open(now: dt.datetime | None = None) -> bool:
    """EW2-11: never fetch between 06:00 and 11:00 UTC."""
    now = now or dt.datetime.now(dt.timezone.utc)
    return not (6 <= now.hour < 11)


def _load_manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"lists": {}, "skipped": SKIPPED}


def fetch_all(dry_run: bool = False) -> dict:
    import requests  # local import: tests import this module without the network stack

    RAW.mkdir(parents=True, exist_ok=True)
    man = _load_manifest()
    man["skipped"] = SKIPPED
    sess = requests.Session()
    sess.headers["User-Agent"] = USER_AGENT
    for list_id, rater, year, url in SOURCES:
        out = RAW / f"{list_id}.html"
        if out.exists() and out.stat().st_size > 1000:
            man["lists"].setdefault(list_id, {"rater": rater, "year": year, "url": url})
            continue
        if dry_run:
            print("would fetch", list_id, url)
            continue
        if not _fetch_window_open():
            print("fetch window closed (06:00 to 11:00 UTC); stopping", file=sys.stderr)
            break
        for attempt in range(4):
            r = sess.get(url, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(PAUSE_S * (4 ** attempt))
                continue
            break
        rec = {"rater": rater, "year": year, "url": url, "final_url": r.url,
               "status": r.status_code, "bytes": len(r.content),
               "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        if r.status_code == 200:
            out.write_text(r.text, encoding="utf-8")
        man["lists"][list_id] = rec
        print(list_id, r.status_code, len(r.content))
        time.sleep(PAUSE_S)
    if not dry_run:
        MANIFEST.write_text(json.dumps(man, indent=1, sort_keys=True), encoding="utf-8")
    return man


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    fetch_all(dry_run=a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
