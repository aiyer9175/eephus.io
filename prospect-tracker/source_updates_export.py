# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Build data/source_updates.json, the payload behind the Source Updates
section of /glossary/ (owner ask 2026-10-02: "a simple list of dates that
tracks each date that an FV update was published from a source").

WHERE THE DATES COME FROM. Only the database's own snapshot dates
(prospects.db, read-only): the `snapshots` table for prospect lists and the
`draft_snapshots` table for draft boards, one row per (source, list, list
date) with the number of players stored under it. No date is typed here and
none is inferred.

WHAT COUNTS AS AN UPDATE. The tables hold three shapes of list, and only two
of them can say when a source published:

  * A DATED LIST, one list name stored under exactly one date (a FanGraphs
    board pinned to its calendar date, a Baseball America Top 30, an ESPN Top
    100, an archived MLB Pipeline Top 100). That date is the list's date and
    the list is one update (basis "list_date").
  * A LIVE LIST, fetched every night under a dated name ("MLB Pipeline Live
    2026-10-02", TJStats "Live ...", Just Baseball "JB Live ..."). A fetch is
    an update only when its players, ranks or grades differ from the previous
    fetch of the same source's live list (basis "changed"); the first fetch on
    record is kept as basis "first_fetch". A fetch identical to the one before
    is not an update and is counted, not listed.
  * A REFETCHED LIST, one list name stored under several dates (the MLB
    Pipeline 2026 per-club Top 30s and the 2026 Draft Top 250, refetched each
    night under one name). The table keeps one row per player, dated the last
    fetch that carried him, so its dates are last-seen dates and not
    publication dates. These lists are NOT dated as updates; they ride in
    `refetched` with their last fetch date so the page can say they exist.

Sources that publish no grade or rank of their own are left out and named in
`excluded` with the reason.

Deterministic apart from the `built` stamp. python source_updates_export.py
writes the file; build() returns the document and never writes, so a test can
call it against any database path. --check-timeseries prints, per source, the
dates present in the database and missing from data/timeseries.json's grade
history and the reverse (a report, never a fix).
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "prospects.db"
OUT = ROOT / "data" / "source_updates.json"
SCHEMA = 1
SIZE_LIMIT = 100_000

# Publisher display names, one per database source key. The prospect-list
# keys read the same as movement._SOURCE_LABELS (the site's display map);
# the draft and international keys roll up to their publisher, because the
# page groups by who published, not by which table the rows sit in.
PUBLISHERS = {
    "mlb_pipeline": "MLB Pipeline",
    "mlb_pipeline_international": "MLB Pipeline",
    "mlb_pipeline_draft": "MLB Pipeline",
    "baseballamerica": "Baseball America",
    "baseballamerica_draft": "Baseball America",
    "fangraphs": "FanGraphs",
    "espn": "ESPN",
    "espn_draft": "ESPN",
    "just_baseball": "Just Baseball",
    "tjstats": "TJStats",
}
# Page order: the four outlets the owner named first, then the rest.
PUBLISHER_ORDER = ("MLB Pipeline", "Baseball America", "FanGraphs", "ESPN",
                   "Just Baseball", "TJStats")
# Database source keys that are not a publisher's list, with the reason.
EXCLUDED = {
    "performance_ingest": "our own ungraded floor for players no outlet ranks, not a published list",
    "auto_detect": "MLB debut records, not a list",
    "draft_signing": "draft signing records, not a list",
    "baseballamerica_statcast_by_age": "article standouts with no grade or rank",
}
TABLES = ("snapshots", "draft_snapshots")

_LIVE_RE = re.compile(r"\bLive \d{4}-\d{2}-\d{2}$")
_DATE_SUFFIX_RE = re.compile(r"\s*\(\d{4}-\d{2}-\d{2}\)$")
_FG_BOARD_RE = re.compile(r"^(\d{4})(report|updated|graduates|tradedeadline|overseas)$")
_FG_BOARD = {"report": ("Preseason Board", "preseason board"),
             "updated": ("Updated Board", "midseason update"),
             "graduates": ("Graduates", "graduates list"),
             "tradedeadline": ("Trade Deadline Board", "trade deadline update"),
             "overseas": ("Overseas Board", "overseas board")}
_FG_ORG_SLUG_RE = re.compile(r"^([a-z]+(?:_[a-z]+)+)_(\d{4})$")      # tampa_bay_rays_2026
_FG_ORG_ABBR_RE = re.compile(r"^([a-z]{3})(\d{4})([a-z]+)$")          # bos2026may
_ABBR_ORG_RE = re.compile(r"^([A-Z]{3}) Top (\d+)$")                  # SFG Top 50
_CLUBS = ("Angels", "Astros", "Athletics", "Blue Jays", "Braves", "Brewers",
          "Cardinals", "Cubs", "Diamondbacks", "Dodgers", "Giants", "Guardians",
          "Mariners", "Marlins", "Mets", "Nationals", "Orioles", "Padres",
          "Phillies", "Pirates", "Rangers", "Rays", "Red Sox", "Reds", "Rockies",
          "Royals", "Tigers", "Twins", "White Sox", "Yankees")
_CLUB_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in _CLUBS) + r")\b")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def long_date(iso: str) -> str:
    """'2026-10-02' -> 'October 2, 2026' (the owner's <Month D, YYYY>)."""
    d = date.fromisoformat(iso)
    return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"


def update_label(publisher: str, iso: str) -> str:
    """The owner's exact form: '<Source> Update - <Month D, YYYY>'."""
    return f"{publisher} Update - {long_date(iso)}"


def describe(table: str, key: str, label: str) -> tuple[str, str, str | None]:
    """(display name, kind, family) for one stored list name. The family is
    the name with the club taken out, set only on a per-club list, so the page
    can fold thirty club lists from one date into one line."""
    pub = PUBLISHERS.get(key, key)
    if table == "draft_snapshots":
        name = _DATE_SUFFIX_RE.sub("", label)
        if name.startswith("FG "):
            name = "FanGraphs " + name[3:]
        return name, "draft board", None
    if _LIVE_RE.search(label):
        return f"{pub} Live Top 100", "live top 100", None
    m = _FG_BOARD_RE.match(label)
    if m:
        nm, kind = _FG_BOARD[m.group(2)]
        return f"FanGraphs {m.group(1)} {nm}", kind, None
    m = _FG_ORG_SLUG_RE.match(label)
    if m:
        club = " ".join(w.capitalize() for w in m.group(1).split("_"))
        return f"FanGraphs {m.group(2)} {club} List", "org list", None
    m = _FG_ORG_ABBR_RE.match(label)
    if m:
        return (f"FanGraphs {m.group(2)} {m.group(1).upper()} List "
                f"({m.group(3).capitalize()})", "org list", None)
    m = _ABBR_ORG_RE.match(label)
    if m:
        return f"{pub} {label}", "org list", None
    name = _DATE_SUFFIX_RE.sub("", label)
    name = re.sub(r"\s(\d{4})-\d{2}-\d{2}(?= Top)", r" \1", name)   # 'BA 2026-06-03 Top 100'
    if name.startswith("FG "):
        name = "FanGraphs " + name[3:]
    elif name.startswith("JustBaseball "):
        name = "Just Baseball " + name[len("JustBaseball "):]
    elif name.startswith("JB "):
        name = "Just Baseball " + name[3:]
    elif name.startswith("TJ "):
        name = "TJStats " + name[3:]
    low = name.lower()
    club = _CLUB_RE.search(name)
    if club:
        family = re.sub(r"\s+", " ", name.replace(club.group(1), "")).strip()
        return name, ("midseason org list" if "midseason" in low else "org list"), family
    if "international" in low or "int'l" in low:
        return name, "international board", None
    if "midseason" in low:
        return name, "midseason list", None
    if "in-season" in low:
        return name, "in-season update", None
    if "preseason" in low or "pre-season" in low:
        return name, "preseason list", None
    if re.search(r"\b(April|May|June|July|August|September)\b", name):
        return name, "monthly update", None
    if "top 100" in low:
        return name, "top 100", None
    return name, "list", None


def _connect(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)


def _groups(con: sqlite3.Connection, table: str) -> list[tuple]:
    """(source, label, date, n) for every stored list date of a published
    source, plus the number of dates each label is stored under."""
    rows = con.execute(
        f"SELECT source, interval_label, snapshot_date, COUNT(*) FROM {table} "
        "GROUP BY source, interval_label, snapshot_date").fetchall()
    return [r for r in rows if r[0] in PUBLISHERS]


def _live_content(con, table, key, label) -> frozenset:
    return frozenset(con.execute(
        f"SELECT player_key, rank, fv FROM {table} WHERE source = ? AND interval_label = ?",
        (key, label)).fetchall())


def build(db: Path = DB, *, today: date | None = None) -> dict:
    """The whole document. Reads the database read-only and writes nothing."""
    con = _connect(db)
    try:
        rows: list[dict] = []
        refetched: list[dict] = []
        unchanged: dict[str, int] = {}
        for table in TABLES:
            groups = _groups(con, table)
            dates_by_label: dict[tuple, list] = {}
            for key, label, d, n in groups:
                dates_by_label.setdefault((key, label), []).append((d, n))
            live: dict[str, list] = {}
            for (key, label), ds in sorted(dates_by_label.items()):
                name, kind, family = describe(table, key, label)
                base = {"key": key, "list": label, "name": name, "kind": kind}
                if family:
                    base["family"] = family
                if len(ds) > 1:
                    last = max(d for d, _ in ds)
                    refetched.append({**base, "table": table, "last_fetch": last,
                                      "n_current": dict(ds)[last],
                                      "stored_dates": len(ds)})
                    continue
                d, n = ds[0]
                if table == "snapshots" and _LIVE_RE.search(label):
                    live.setdefault(key, []).append((d, label, n, base))
                    continue
                rows.append({**base, "table": table, "date": d, "n": n,
                             "basis": "list_date"})
            for key, fetches in live.items():
                prev = None
                for d, label, n, base in sorted(fetches):
                    cur = _live_content(con, table, key, label)
                    if prev is None:
                        basis = "first_fetch"
                    elif cur != prev:
                        basis = "changed"
                    else:
                        basis = None
                        unchanged[key] = unchanged.get(key, 0) + 1
                    prev = cur
                    if basis:
                        rows.append({**base, "table": table, "date": d, "n": n,
                                     "basis": basis})
    finally:
        con.close()

    order = {p: i for i, p in enumerate(PUBLISHER_ORDER)}
    for r in rows:
        r["source"] = PUBLISHERS[r["key"]]
        r["label"] = update_label(r["source"], r["date"])
    for r in refetched:
        r["source"] = PUBLISHERS[r["key"]]
        r["last_fetch_long"] = long_date(r["last_fetch"])
    rows.sort(key=lambda r: (-int(r["date"].replace("-", "")),
                             order.get(r["source"], 99), r["name"], r["list"]))
    refetched.sort(key=lambda r: (order.get(r["source"], 99), r["name"]))

    sources = []
    for pub in sorted({r["source"] for r in rows} | {r["source"] for r in refetched},
                      key=lambda p: (order.get(p, 99), p)):
        mine = [r for r in rows if r["source"] == pub]
        dates = sorted({r["date"] for r in mine})
        keys = sorted({r["key"] for r in mine} |
                      {r["key"] for r in refetched if r["source"] == pub})
        sources.append({
            "source": pub, "keys": keys,
            "n_updates": len(dates), "n_lists": len(mine),
            "first": dates[0] if dates else None,
            "first_long": long_date(dates[0]) if dates else None,
            "last": dates[-1] if dates else None,
            "last_label": update_label(pub, dates[-1]) if dates else None,
            "live_fetches_unchanged": sum(unchanged.get(k, 0) for k in keys),
        })
    through = max((r["date"] for r in rows), default=None)
    # One entry per update (publisher, date) in the owner's label form, newest
    # first. Its lists are folded into sets that share a database key, table,
    # kind, basis and family, so thirty club lists from one date are one set;
    # each list is [stored name, players] plus its display name when that
    # differs. Flat rows measured 227 KB against the 100 KB line; flatten()
    # gives the flat one-row-per-(source, list, date) view back.
    updates: list[dict] = []
    for r in rows:
        if not updates or (updates[-1]["source"], updates[-1]["date"]) != (r["source"], r["date"]):
            updates.append({"source": r["source"], "date": r["date"], "label": r["label"],
                            "sets": []})
        sig = (r["key"], r["table"], r["kind"], r["basis"], r.get("family"))
        sets = updates[-1]["sets"]
        hit = next((s for s in sets if (s["key"], s["table"], s["kind"], s["basis"],
                                        s.get("family")) == sig), None)
        if hit is None:
            hit = {"key": r["key"], "table": r["table"], "kind": r["kind"], "basis": r["basis"]}
            if r.get("family"):
                hit["family"] = r["family"]
            hit["lists"] = []
            sets.append(hit)
        hit["lists"].append([r["list"], r["n"]] + ([r["name"]] if r["name"] != r["list"] else []))
    return {
        "schema": SCHEMA,
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "through": through,
        "through_long": long_date(through) if through else None,
        "label_form": "<Source> Update - <Month D, YYYY>",
        "basis": {
            "list_date": "a list stored under one date; that date is the list's date",
            "changed": "a nightly fetch of a live list whose players, ranks or grades differ from the previous fetch",
            "first_fetch": "the first fetch of a live list on record",
        },
        "note": ("Dates are the database's snapshot dates. A refetched list keeps one row per player "
                 "dated the last fetch that carried him, so it carries no publication date and is "
                 "listed under refetched instead."),
        "sources": sources,
        "updates": updates,
        "refetched": refetched,
        "excluded": [{"key": k, "reason": v} for k, v in sorted(EXCLUDED.items())],
    }


def flatten(doc: dict) -> list[dict]:
    """One dict per (source, list, list date), newest first, from `updates`."""
    out = []
    for u in doc.get("updates") or []:
        for s in u["sets"]:
            for lst in s["lists"]:
                out.append({"source": u["source"], "date": u["date"], "label": u["label"],
                            "key": s["key"], "table": s["table"], "kind": s["kind"],
                            "basis": s["basis"], "family": s.get("family"),
                            "list": lst[0], "n": lst[1],
                            "name": lst[2] if len(lst) > 2 else lst[0]})
    return out


def write(doc: dict, out: Path = OUT) -> int:
    """Write compact JSON; refuse a payload over SIZE_LIMIT bytes."""
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    data = text.encode("utf-8")
    if len(data) > SIZE_LIMIT:
        raise ValueError(f"source_updates.json would be {len(data):,} bytes, over {SIZE_LIMIT:,}")
    out.write_bytes(data)
    return len(data)


def timeseries_dates(path: Path = ROOT / "data" / "timeseries.json") -> dict[str, set]:
    """Per database source key, every list date data/timeseries.json's grade
    history carries (each player's points, per_source and its extras)."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, set] = {}
    for p in doc.get("players") or []:
        for pt in p.get("points") or []:
            for key, ps in (pt.get("per_source") or {}).items():
                for e in [ps] + list(ps.get("extras") or []):
                    d = e.get("snapshot_date")
                    if d:
                        out.setdefault(key, set()).add(d)
    return out


def timeseries_mismatch(doc: dict, ts: dict[str, set], db: Path = DB) -> dict:
    """Per prospect-list source key: list dates in the database and not in the
    timeseries grade history, and the reverse. Draft boards are not in the
    timeseries and are not compared."""
    con = _connect(db)
    try:
        db_dates: dict[str, set] = {}
        for key, d in con.execute(
                "SELECT DISTINCT source, snapshot_date FROM snapshots").fetchall():
            if key in PUBLISHERS:
                db_dates.setdefault(key, set()).add(d)
    finally:
        con.close()
    served = {}
    for r in flatten(doc):
        if r["table"] == "snapshots":
            served.setdefault(r["key"], set()).add(r["date"])
    out = {}
    for key in sorted(db_dates):
        t = ts.get(key, set())
        out[key] = {
            "update_dates_not_in_timeseries": sorted(served.get(key, set()) - t),
            "db_dates_not_in_timeseries": sorted(db_dates[key] - t),
            "timeseries_dates_not_in_db": sorted(t - db_dates[key]),
        }
    return out


def main(argv: list[str]) -> int:
    doc = build()
    n = write(doc)
    print(f"source_updates.json: {len(flatten(doc))} rows, {len(doc['updates'])} updates, {len(doc['refetched'])} refetched "
          f"lists, {n:,} bytes, through {doc['through']}")
    for s in doc["sources"]:
        print(f"  {s['source']}: {s['n_updates']} update dates, {s['n_lists']} lists, "
              f"{s['first']} to {s['last']}, {s['live_fetches_unchanged']} unchanged live fetches")
    if "--check-timeseries" in argv:
        mm = timeseries_mismatch(doc, timeseries_dates())
        print(json.dumps(mm, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
