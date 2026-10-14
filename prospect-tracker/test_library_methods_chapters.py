# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""LIBRARY_5: the Methodology view reads as seven chapters.

The plan is LIBRARY_PLAN.md sections 3 and 5 (lane LANE_STRUCTURE.md section 4,
the Methodology rows, and 5.3 'In-page sections'). Pinned here:

  * the chapters, in order, each an h2 with its id; #industry-comparison keeps
    its id and still scrolls;
  * the view makes no request for data/model_registry.json until the Generate
    GFX button is clicked (the registry table retired: /models/ is the ledger);
  * the two data-source sections became a pointer to /sources/;
  * the Methodology changelog moved into Model Updates note rows: every line's
    date, and its model where the line names one, is in data/model_updates.json,
    and the heading is gone from assets/glossary.js;
  * the calibration measurements render on Evidence > Calibration.

Playwright is optional; the browser tests skip cleanly without it."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).parent
GLJS = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8").replace("\r\n", "\n")

CHAPTERS = [
    ("meth-efv", "eFV"),
    ("meth-consensus", "Consensus FV"),
    ("meth-arkmetrics", "Arkmetrics"),
    ("meth-value", "Value and surplus"),
    ("meth-farm", "Farm grade"),
    ("industry-comparison", "Our tables vs the industry's"),
    ("meth-faq", "FAQ"),
]

# The 18 lines of the retired Methodology changelog (the 13 the plan counted,
# the four DISPLAY_glossary_models QREC16 added and the fWAR epoch line), each
# with its date as written and its model (None for the one line naming none).
MIGRATED = [
    ("2026-10-03", "xfv_fwar_label_epoch"),
    ("2026-09-30", "eta"),
    ("2026-09-25", "efv_v2"),
    ("2026-09-25", "xfv_headtohead_frame"),
    ("2026-09-04", "xfv_ewar_label_epoch"),
    ("2026-07-31", "prospect_surplus"),
    ("2026-07-30", "efv_v1"),
    ("2026-07-29/30", "prospect_surplus"),
    ("2026-07-25", "consensus_fv"),
    ("2026-07", "grade_normalization"),
    ("2026-06", "source_track_record"),
    ("2026-06", "prospect_surplus"),
    ("2026-06", None),
    ("2026-06", "farm_grades"),
    ("2026-05", "farm_grades"),
    ("2026-06", "consensus_fv"),
    ("2026-05", "source_track_record"),
    ("2026-04", "consensus_fv"),
]


def _fn(name: str) -> str:
    start = GLJS.index(f"function {name}(")
    return GLJS[start:GLJS.index("\nfunction ", start + 1)]


# ---- static -----------------------------------------------------------------

def test_the_chapters_are_registered_in_order():
    body = _fn("_methChapters")
    got = re.findall(r'\{ id: "([a-z-]+)", label: "([^"]+)" \}', body)
    assert got == CHAPTERS
    rm = _fn("renderMethodology")
    assert '<h2 class="meth-chapter-h" id="${c.id}">' in rm
    assert "meth-rail" in rm and "meth-chsel" in rm
    # the print export and Generate GFX stay
    assert "_printMethodology()" in rm and '"gl-meth-gfx", "Generate GFX"' in rm


def test_the_rail_lamp_uses_the_px_lamp_tokens():
    assert 'class="px-lamp meth-rail-lamp"' in _fn("_methRailLamp")
    wire = _fn("_methWireChapters")
    assert "IntersectionObserver" in wire
    assert 'r.setAttribute("class", on ? "lt" : "lo")' in wire
    css = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
    assert re.search(r"\.gl-app \.meth-chapters \{ max-width: 72ch;", css)
    assert re.search(r"\.gl-app \.meth-rail \{ display: block; position: sticky;", css)


def test_the_registry_is_fetched_only_by_the_gfx_click():
    assert "_methRegistryHTML" not in GLJS
    assert "Which models are validated" not in GLJS
    rm = _fn("renderMethodology")
    assert "model_registry.json" not in rm and "fetch(" not in rm
    assert "gfxBtn.onclick = () => _loadRegistryThen(" in rm
    assert 'fetch("/data/model_registry.json"' in _fn("_loadRegistryThen")
    # the eFV chapter ends with the sentence that links the ledger
    assert re.search(r'"meth-efv": prose\(P\.efv \+ `[^`]*<a href="/models/">Models</a>[^`]*`\)', rm)


def test_the_data_source_sections_point_at_sources():
    for gone in ("Data sources &amp; references", "Data sources &amp; attribution",
                 "The full attribution page lives at", "article-grid"):
        assert gone not in GLJS, gone
    rm = _fn("renderMethodology")
    assert rm.count('<a href="/sources/">Data Sources</a>') == 1


def test_the_changelog_lines_are_model_update_notes():
    assert "Methodology changelog" not in GLJS
    assert "meth-changelog" not in GLJS and "mc-date" not in GLJS
    doc = json.loads((ROOT / "data" / "model_updates.json").read_text(encoding="utf-8"))
    notes = [e for e in doc["events"] if e.get("layer") == "note"
             and e.get("origin") == "methodology changelog"]
    have = [(e["date"], e.get("model_id")) for e in notes]
    for date, mid in MIGRATED:
        assert (date, mid) in have, (date, mid)
    assert len(notes) >= len(MIGRATED)
    assert not doc.get("note_problems")
    typed = json.loads((ROOT / "data" / "model_updates_typed.json").read_text(encoding="utf-8"))
    rows = [(n["date"], n.get("model_id")) for n in typed["notes"]
            if n.get("origin") == "methodology changelog"]
    assert sorted(rows, key=str) == sorted(MIGRATED, key=str)
    # the one line that names no model carries a route-table family
    (fam,) = [n.get("family") for n in typed["notes"] if n.get("model_id") is None
              and n.get("origin") == "methodology changelog"]
    assert fam


def test_the_calibration_measurements_left_methodology():
    rm = _fn("renderMethodology")
    for gone in ("_methReliabilityHTML", "_methValuationCurveHTML", "_loadReliability",
                 "xfv_valuation_curve.json"):
        assert gone not in rm, gone
    assert '<a href="#view=calibration">' in _fn("_methCalibCrossLink")
    assert "_renderPendingLeaf" not in GLJS


# ---- rendered -----------------------------------------------------------------

@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


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


def _page(browser, width, errors, requests):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(e.message))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("request", lambda r: requests.append(r.url))
    return ctx, page


def _ready(page):
    page.wait_for_function("() => !!document.getElementById('meth-faq')", timeout=15_000)
    page.wait_for_load_state("networkidle")


def test_methodology_renders_chapters_and_fetches_the_registry_on_click(server, browser):
    errors, requests = [], []
    ctx, page = _page(browser, 1280, errors, requests)
    try:
        page.goto(server + "glossary/index.html#view=methodology", wait_until="load", timeout=15_000)
        _ready(page)
        ids = page.evaluate("() => Array.from(document.querySelectorAll("
                            "'#methodology-body h2.meth-chapter-h')).map(h => h.id)")
        assert ids == [c for c, _ in CHAPTERS]
        # tools/verify_site.py 42 reads this selector on the view
        assert page.query_selector("#methodology-body .meth-table, #methodology-body .meth-chart")
        assert page.is_visible(".meth-rail") and not page.is_visible(".meth-chsel")
        assert not [u for u in requests if "model_registry.json" in u]
        page.click('[data-meth-go="industry-comparison"]')
        page.wait_for_function(
            "() => Math.abs(document.getElementById('industry-comparison').getBoundingClientRect().top) < 40",
            timeout=5_000)
        page.wait_for_function(
            "() => document.querySelector('.meth-rail a[aria-current]').dataset.methGo === 'industry-comparison'",
            timeout=5_000)
        assert page.evaluate("document.querySelectorAll('.meth-rail-lamp rect.lt').length") == 1
        assert page.evaluate("Math.round(document.querySelector('.meth-rail').getBoundingClientRect().top)") >= 0
        page.click("#gl-meth-gfx")
        page.wait_for_timeout(1500)
        assert len([u for u in requests if "model_registry.json" in u]) == 1
        assert page.evaluate("document.documentElement.scrollWidth") == 1280
    finally:
        ctx.close()
    assert not errors, errors


def test_the_bare_chapter_id_scrolls_at_390(server, browser):
    errors, requests = [], []
    ctx, page = _page(browser, 390, errors, requests)
    try:
        page.goto(server + "glossary/index.html#industry-comparison", wait_until="load", timeout=15_000)
        _ready(page)
        page.wait_for_timeout(600)
        top = page.evaluate("document.getElementById('industry-comparison').getBoundingClientRect().top")
        assert 0 <= top < 120, top
        assert page.is_visible(".meth-chsel") and not page.is_visible(".meth-rail")
        assert page.evaluate("document.getElementById('meth-chsel').value") == "industry-comparison"
        page.select_option("#meth-chsel", "meth-farm")
        page.wait_for_function(
            "() => Math.abs(document.getElementById('meth-farm').getBoundingClientRect().top - 64) < 40",
            timeout=5_000)
        assert page.evaluate("document.documentElement.scrollWidth") == 390
        assert not [u for u in requests if "model_registry.json" in u]
    finally:
        ctx.close()
    assert not errors, errors


def test_the_calibration_leaf_renders_both_tables(server, browser):
    errors, requests = [], []
    ctx, page = _page(browser, 390, errors, requests)
    try:
        page.goto(server + "glossary/index.html#view=calibration", wait_until="load", timeout=15_000)
        page.wait_for_load_state("networkidle")
        html = page.evaluate("document.getElementById('calibration-body').innerHTML")
        rel = json.loads((ROOT / "data" / "xfv_reliability.json").read_text(encoding="utf-8"))
        if (rel.get("tripwire") or {}).get("threshold"):
            assert "Calibration monitor: eFV v1 reliability by bin" in html
            tw = rel["tripwire"]
            lit = round(tw["bust_ece"] / tw["threshold"] * 10)
            got = page.evaluate("document.querySelectorAll('.meth-trip-lamp rect.lt, .meth-trip-lamp rect.lb').length")
            assert got == lit
        if (ROOT / "data" / "xfv_valuation_curve.json").is_file():
            assert "What an eFV grade is worth" in html
        assert page.evaluate("document.documentElement.scrollWidth") == 390
    finally:
        ctx.close()
    assert not errors, errors
