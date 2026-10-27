# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PROSPX board downloads every row it holds as a CSV, built from data.

WHY THIS EXISTS (census M01-10, 2026-09-24, two verifiers CONFIRMED). The flagship board had
no export: prospx did not load eephus-csv.js, and the shared helper scrapes the DOM, which on
a paginated card grid would carry one page of badge text. The board now builds a
{headers, rows} model from the data it renders and hands it to EephusCSV.downloadModel.

Contract pinned here: the page loads the helper; the file has one row per board row after
the provisional pool lands, in board order; printed grades match the board's own formatter;
the stamp columns are present; no internal sort key is exported. Owner answer M8-2
(2026-09-25): the file carries one grade column per public source (FanGraphs, MLB Pipeline,
Baseball America, ESPN), the grade on the player's latest point as published, blank where
the source has none.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"
CSVJS = ROOT / "assets" / "eephus-csv.js"


def test_prospx_loads_the_csv_helper_after_the_export_runtime():
    src = PROSPX.read_text(encoding="utf-8")
    exp = re.search(r'<script src="/assets/eephus-export\.js\?v=[0-9a-f]+" defer></script>', src)
    csvt = re.search(r'<script src="/assets/eephus-csv\.js\?v=[0-9a-f]+" defer></script>', src)
    assert exp and csvt, "prospx must load eephus-export.js and eephus-csv.js"
    assert exp.start() < csvt.start(), "eephus-csv.js must load after eephus-export.js"


def test_the_helper_documents_and_exposes_the_data_contract():
    js = CSVJS.read_text(encoding="utf-8")
    assert "downloadModel: downloadModel" in js
    assert "THE SECOND CONTRACT" in js


@pytest.fixture(scope="module")
def booted_page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page(accept_downloads=True)
        page.add_init_script(
            "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}catch(e){}")
        errs: list[str] = []
        page.on("pageerror", lambda err: errs.append(err.message))
        page.goto(base + "prospx/index.html", wait_until="load", timeout=60_000)
        page.wait_for_function(
            "() => document.querySelectorAll('#rows .player-row').length > 5", timeout=120_000)
        try:
            page.wait_for_function(
                "() => typeof provPlayers === 'function' && provPlayers().length > 0",
                timeout=60_000)
        except Exception:
            pytest.skip("the provisional pool never loaded")
        page.wait_for_timeout(800)
        yield page, errs
        browser.close()


def test_the_download_holds_the_whole_filtered_board(booted_page):
    page, errs = booted_page
    n = page.evaluate("() => getFilteredActives().length")
    label = page.evaluate(
        "() => (document.querySelector('#board-csv-btn .board-csv-n') || {}).textContent || ''")
    assert label.replace(",", "").startswith(str(n)), f"button reads {label!r} for {n} rows"
    # every PROSPX filter bar opens closed since the sections redesign (9fd2dcdc,
    # 2026-10-08), and the Download CSV control sits in the board's bar
    page.evaluate("() => { const b = document.getElementById('filter-bar');"
                  " if (b && !b.classList.contains('is-open'))"
                  " document.getElementById('filter-toggle').click(); }")
    with page.expect_download(timeout=30_000) as dl:
        page.click("#board-csv-btn")
    d = dl.value
    assert re.fullmatch(r"eephus-prospx-board-\d{4}-\d{2}-\d{2}\.csv", d.suggested_filename)
    raw = Path(d.path()).read_bytes().decode("utf-8")
    assert raw.startswith("﻿"), "no BOM: Excel would mangle accented names"
    rows = list(csv.reader(io.StringIO(raw.lstrip("﻿"))))
    head, body = rows[0], rows[1:]
    assert len(body) == n, f"file has {len(body)} rows, the board holds {n}"
    for col in ("rank", "player_key", "efv", "efv_printed", "consensus_fv_printed",
                "provisional", "grade_basis", "sort", "asof"):
        assert col in head
    banned = [h for h in head if re.search(r"board_sort_key", h, re.I)]
    assert not banned, f"internal columns exported: {banned}"
    src_cols = ["fangraphs_fv", "mlb_pipeline_fv", "baseball_america_fv", "espn_fv"]
    for col in src_cols:
        assert col in head, f"per-source grade column {col} missing (owner answer M8-2)"
    ix = {h: i for i, h in enumerate(head)}
    # Each per-source cell is the grade on the row's latest point, as published, or blank.
    want = page.evaluate(r"""() => getFilteredActives().map(p => {
        const pts = p.points || [], last = pts.length ? pts[pts.length - 1] : null;
        const ps = (last && last.per_source) || {};
        return ["fangraphs", "mlb_pipeline", "baseballamerica", "espn"].map(s => {
          const v = ps[s];
          return (!v || v.fv_published == null) ? "" : String(Number(v.fv_published)) + (v.fv_plus ? "+" : "");
        });
      })""")
    got = [[r[ix[c]] for c in src_cols] for r in body]
    assert got == want, "per-source grade cells differ from the rows' latest per_source map"
    for j, col in enumerate(src_cols):
        filled = [g[j] for g in got if g[j]]
        assert filled, f"{col} is blank on every row"
        assert all(re.fullmatch(r"\d{2}(\.\d)?\+?", v) for v in filled), (col, filled[:5])
    assert [r[ix["rank"]] for r in body[:5]] == ["1", "2", "3", "4", "5"]
    assert all(r[ix["asof"]] for r in body[:5])
    assert sum(r[ix["provisional"]] == "1" for r in body) > 0
    first = page.evaluate(
        "() => getFilteredActives().slice(0, 50).map(p => [p.player_key, gradeBlock(p).efvVal])")
    for (key, efv), r in zip(first, body[:50]):
        assert r[ix["player_key"]] == key, "file order differs from the board"
        assert r[ix["efv_printed"]] == ("" if efv is None else str(efv)), (
            f"{key}: file prints eFV {r[ix['efv_printed']]!r}, the board prints {efv}")
    assert "—" not in raw, "em-dash in the export"
    assert not errs, "JS errors: " + " | ".join(errs)
