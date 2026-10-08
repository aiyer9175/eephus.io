# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Source Updates section (owner ask 2026-10-02): data/source_updates.json
and its view on /glossary/#view=source-updates.

Four guards, named for what they hold:
  * STRUCTURE: the payload's fields, newest first, every date parses, no
    duplicate (source, list, date), the owner's label form, under 100 KB.
  * RECONCILIATION (read-only over prospects.db): every row's date is a stored
    snapshot date for that list with the same player count, and each source's
    row count equals the count the database gives under the same rule,
    recomputed here by its own queries.
  * RENDER: the section lists the latest MLB Pipeline update in the owner's
    form, as list items, not a table.
  * INDEX: the page's section chips, the URL whitelist and the Library page
    index all carry the section; the nightly step and its ingest row exist.
The rule itself (dated list, live list changed, refetched list) is held on a
small fixture database so it cannot drift silently.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from conftest import serve_site

import source_updates_export as SU

ROOT = Path(__file__).parent
PAYLOAD = ROOT / "data" / "source_updates.json"
DB = ROOT / "prospects.db"
LABEL_RE = re.compile(r"^(?P<src>.+) Update - (?P<month>[A-Z][a-z]+) (?P<d>\d{1,2}), (?P<y>\d{4})$")
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def _doc() -> dict:
    if not PAYLOAD.exists():
        pytest.skip("data/source_updates.json not built")
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


# ---- the rule, on a fixture database ---------------------------------------

def _fixture_db(path: Path) -> Path:
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE snapshots (source TEXT, snapshot_date TEXT, interval_label TEXT,
                   player_key TEXT, rank INTEGER, fv REAL)""")
    con.execute("""CREATE TABLE draft_snapshots (source TEXT, snapshot_date TEXT, interval_label TEXT,
                   player_key TEXT, rank INTEGER, fv REAL)""")
    rows = [
        # a dated list: one name, one date
        ("baseballamerica", "2026-08-10", "Baseball America 2026 Midseason Rays Top 30", "a", 1, 50),
        ("baseballamerica", "2026-08-10", "Baseball America 2026 Midseason Rays Top 30", "b", 2, 45),
        ("baseballamerica", "2026-08-10", "Baseball America 2026 Midseason Cubs Top 30", "c", 1, 50),
        # a live list: day 1 first, day 2 identical, day 3 changed
        ("mlb_pipeline", "2026-09-01", "MLB Pipeline Live 2026-09-01", "a", 1, 60),
        ("mlb_pipeline", "2026-09-02", "MLB Pipeline Live 2026-09-02", "a", 1, 60),
        ("mlb_pipeline", "2026-09-03", "MLB Pipeline Live 2026-09-03", "a", 2, 60),
        # a refetched list: one name, two stored dates (last-seen dates)
        ("mlb_pipeline", "2026-01-22", "MLB Pipeline 2026 Rays Top 30", "x", 9, 40),
        ("mlb_pipeline", "2026-09-03", "MLB Pipeline 2026 Rays Top 30", "y", 1, 50),
        # not a publisher's list
        ("performance_ingest", "2026-09-03", "2026_performance", "z", None, 35),
    ]
    con.executemany("INSERT INTO snapshots VALUES (?,?,?,?,?,?)", rows)
    con.execute("INSERT INTO draft_snapshots VALUES ('fangraphs','2026-07-15','FG 2026 Draft (2026-07-15)','d',1,45)")
    con.commit()
    con.close()
    return path


def test_the_update_rule_on_a_fixture(tmp_path):
    doc = SU.build(_fixture_db(tmp_path / "fx.db"))
    rows = SU.flatten(doc)
    got = sorted((r["key"], r["list"], r["date"], r["basis"], r["n"]) for r in rows)
    assert got == sorted([
        ("baseballamerica", "Baseball America 2026 Midseason Cubs Top 30", "2026-08-10", "list_date", 1),
        ("baseballamerica", "Baseball America 2026 Midseason Rays Top 30", "2026-08-10", "list_date", 2),
        ("mlb_pipeline", "MLB Pipeline Live 2026-09-01", "2026-09-01", "first_fetch", 1),
        ("mlb_pipeline", "MLB Pipeline Live 2026-09-03", "2026-09-03", "changed", 1),
        ("fangraphs", "FG 2026 Draft (2026-07-15)", "2026-07-15", "list_date", 1),
    ])
    # the unchanged live fetch is counted, not listed; the refetched list is
    # named without a date; the ungraded floor never appears
    mlb = next(s for s in doc["sources"] if s["source"] == "MLB Pipeline")
    assert mlb["live_fetches_unchanged"] == 1
    assert [r["list"] for r in doc["refetched"]] == ["MLB Pipeline 2026 Rays Top 30"]
    assert all(r["key"] != "performance_ingest" for r in rows)
    # two club lists on one date fold into one set under their family
    ba = next(u for u in doc["updates"] if u["source"] == "Baseball America")
    assert ba["label"] == "Baseball America Update - August 10, 2026"
    assert len(ba["sets"]) == 1 and ba["sets"][0]["family"] == "Baseball America 2026 Midseason Top 30"


def test_the_label_is_the_owners_form():
    assert SU.update_label("MLB Pipeline", "2026-10-02") == "MLB Pipeline Update - October 2, 2026"
    assert SU.long_date("2011-01-22") == "January 22, 2011"
    assert SU.describe("snapshots", "fangraphs", "2026updated")[:2] == (
        "FanGraphs 2026 Updated Board", "midseason update")
    assert SU.describe("snapshots", "tjstats", "Live 2026-10-02")[:2] == (
        "TJStats Live Top 100", "live top 100")
    assert SU.describe("draft_snapshots", "mlb_pipeline_draft", "MLB Pipeline 2025 Draft Top 250")[1] == "draft board"


# ---- structure ---------------------------------------------------------------

def test_payload_structure():
    doc = _doc()
    assert doc["schema"] == SU.SCHEMA
    assert PAYLOAD.stat().st_size < 100_000
    for k in ("built", "through", "through_long", "label_form", "basis", "sources",
              "updates", "refetched", "excluded"):
        assert k in doc, k
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", doc["built"])
    rows = SU.flatten(doc)
    assert rows, "no update rows"
    seen = set()
    prev = None
    for u in doc["updates"]:
        d = date.fromisoformat(u["date"])                        # every date parses
        assert prev is None or d <= prev, f"not newest first at {u['date']}"
        prev = d
        m = LABEL_RE.match(u["label"])
        assert m, u["label"]
        assert m["src"] == u["source"]
        assert date(int(m["y"]), MONTHS.index(m["month"]) + 1, int(m["d"])) == d
        assert u["sets"], u
        for s in u["sets"]:
            assert s["basis"] in doc["basis"], s
            assert SU.PUBLISHERS[s["key"]] == u["source"]
            for lst in s["lists"]:
                assert isinstance(lst[0], str) and isinstance(lst[1], int) and lst[1] > 0
    for r in rows:
        k = (r["key"], r["table"], r["list"], r["date"])
        assert k not in seen, f"duplicate (source, list, date): {k}"
        seen.add(k)
    assert doc["through"] == max(r["date"] for r in rows)
    for s in doc["sources"]:
        mine = [r for r in rows if r["source"] == s["source"]]
        assert s["n_lists"] == len(mine)
        assert s["n_updates"] == len({r["date"] for r in mine})
        if mine:
            assert s["last"] == max(r["date"] for r in mine)
            assert s["last_label"] == SU.update_label(s["source"], s["last"])
    assert [s["source"] for s in doc["sources"]][:4] == [
        "MLB Pipeline", "Baseball America", "FanGraphs", "ESPN"]


# ---- reconciliation against the database (read-only) -------------------------

def _ro():
    if not DB.exists():
        pytest.skip("prospects.db not present")
    return sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)


def test_rows_reconcile_with_the_database():
    doc = _doc()
    rows = SU.flatten(doc)
    con = _ro()
    try:
        for r in rows:
            assert r["table"] in ("snapshots", "draft_snapshots")
            n = con.execute(
                f"SELECT COUNT(*) FROM {r['table']} WHERE source=? AND interval_label=? AND snapshot_date=?",
                (r["key"], r["list"], r["date"])).fetchone()[0]
            assert n == r["n"], f"{r['key']} {r['list']} {r['date']}: db {n}, payload {r['n']}"
        # The database's own count per (source, table), by its own queries:
        # a list name stored under one date is one update; a live list's
        # fetch counts when its (player, rank, grade) set differs from the
        # previous fetch's, the first fetch included.
        expected: dict[tuple, int] = {}
        live_re = re.compile(r"\bLive \d{4}-\d{2}-\d{2}$")
        for table in ("snapshots", "draft_snapshots"):
            labels = con.execute(
                f"SELECT source, interval_label, MIN(snapshot_date) FROM {table} "
                "GROUP BY source, interval_label HAVING COUNT(DISTINCT snapshot_date) = 1").fetchall()
            live: dict[str, list] = {}
            for key, label, d in labels:
                if key not in SU.PUBLISHERS:
                    continue
                if table == "snapshots" and live_re.search(label):
                    live.setdefault(key, []).append((d, label))
                else:
                    expected[(key, table)] = expected.get((key, table), 0) + 1
            for key, fetches in live.items():
                prev = None
                for d, label in sorted(fetches):
                    cur = set(con.execute(
                        "SELECT player_key, rank, fv FROM snapshots WHERE source=? AND interval_label=?",
                        (key, label)).fetchall())
                    if prev is None or cur != prev:
                        expected[(key, table)] = expected.get((key, table), 0) + 1
                    prev = cur
        refetched = con.execute(
            "SELECT COUNT(*) FROM (SELECT source, interval_label FROM snapshots GROUP BY 1, 2 "
            "HAVING COUNT(DISTINCT snapshot_date) > 1 UNION ALL SELECT source, interval_label "
            "FROM draft_snapshots GROUP BY 1, 2 HAVING COUNT(DISTINCT snapshot_date) > 1)").fetchone()[0]
        refetched_pub = sum(1 for r in doc["refetched"])
    finally:
        con.close()
    got: dict[tuple, int] = {}
    for r in rows:
        got[(r["key"], r["table"])] = got.get((r["key"], r["table"]), 0) + 1
    assert got == expected
    # every refetched list in the payload is one the database stores under
    # several dates (and the unlisted ones belong to excluded sources)
    assert refetched_pub <= refetched
    for r in doc["refetched"]:
        assert r["stored_dates"] > 1


# ---- the section index -------------------------------------------------------

def test_section_is_in_the_page_index_and_the_nightly():
    shell = (ROOT / "glossary" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert 'data-glossary-view="source-updates">Source Updates</button>' in shell
    assert 'id="source-updates-body"' in shell
    # registered once in the view registry (LIBRARY_3), on the Sources shelf
    assert '{ id: "source-updates", shelf: "sources", label: "Source Updates", body: "source-updates-body",' in js
    # the Library page index lists the section under the module's own name
    # (generated by build_site.page_index_groups() since LIBRARY_8)
    import build_site
    views = {r[0]: r[1] for g in build_site.page_index_groups() for r in g["rows"]}
    assert views["/glossary/#view=source-updates"] == (
        build_site.GLOSSARY_DISPLAY_NAME + " · Source Updates")
    assert 'id="page-index-data"' in shell
    assert re.search(r'<div class="gl-app" data-module-name="[^"]+" data-display-name="[^"]+">', shell)
    rm = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    assert '_step("d10g. Source update dates (source_updates.json)"' in rm
    import run_monthly
    assert "source_updates_export" in run_monthly.SCHEDULED_EXPORTS


# ---- render ------------------------------------------------------------------

@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        yield b
        b.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_section_lists_the_latest_pipeline_update(browser, width):
    doc = _doc()
    want = next(s for s in doc["sources"] if s["source"] == "MLB Pipeline")["last_label"]
    assert LABEL_RE.match(want)
    errors: list[str] = []
    with serve_site() as base:
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.on("pageerror", lambda e: errors.append(e.message))
        try:
            page.goto(base + "glossary/index.html#view=source-updates", wait_until="load", timeout=15_000)
            page.wait_for_selector("#source-updates-body .su-src", timeout=15_000)
            out = page.evaluate("""() => {
              const el = document.getElementById('source-updates-body');
              const sec = el.querySelector('section.su-src');
              return {
                head: sec.querySelector('h3').textContent,
                last: sec.querySelector('.su-last strong').innerText,
                first: sec.querySelector('ul.su-list > li .su-label').innerText,
                lis: el.querySelectorAll('ul.su-list > li').length,
                tables: el.querySelectorAll('table').length,
                active: document.querySelector('[data-glossary-view].active').dataset.glossaryView,
                scrollW: document.documentElement.scrollWidth,
              };
            }""")
        finally:
            page.close()
    assert not errors, errors
    assert out["head"].startswith("MLB Pipeline")
    assert out["last"] == want
    assert out["first"] == want
    assert out["lis"] == len(doc["updates"])
    assert out["tables"] == 0
    assert out["active"] == "source-updates"
    assert out["scrollW"] <= width
