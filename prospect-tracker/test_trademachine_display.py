# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The /trademachine/ display pass (DISPLAY_trademachine, 2026-10-07).

One test per surface-quality finding the pass closes (qualaudit 2026-10-02):
claims (QCLC02, QCLC04, QCLC05), payload and layout (QCLP01-03) and keyboard,
names and state (QCLA05-07, QCLA17). Source checks run anywhere; the served
checks drive headless Chromium over conftest.serve_site and skip where the
gitignored trade_values.json is not built.
"""
from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path

import pytest

from conftest import serve_site

ROOT = Path(__file__).resolve().parent
JS = ROOT / "assets" / "trademachine.js"


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _gl(slug: str) -> dict:
    doc = json.loads(_src("data/glossary.json"))
    return next(e for e in doc["entries"] if e["id"] == slug)


@pytest.fixture(scope="module")
def server():
    if not (ROOT / "data" / "trade_values.json").exists():
        pytest.skip("trade_values.json not built on this machine")
    with serve_site() as base:
        yield base


@contextlib.contextmanager
def _page(server, w=1280, h=900, touch=False, hash_="", requests=None):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=touch)
            pg = ctx.new_page()
            if requests is not None:
                pg.on("request", lambda r: requests.append(r.url))
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(server + "trademachine/" + hash_, wait_until="load", timeout=90_000)
            pg.wait_for_selector(".tm-board-table tbody tr", timeout=90_000)
            yield pg, errors
        finally:
            browser.close()


def _add(pg, side: str, query: str):
    """Add the first priced hit for `query` to `side`, by mouse."""
    inp = pg.locator(f'input[data-tm-search="{side}"]')
    inp.click()
    inp.fill(query)
    pg.wait_for_selector(f'[data-tm-results="{side}"] .tm-hit:not(.is-unpriced)', timeout=20_000)
    pg.locator(f'[data-tm-results="{side}"] .tm-hit:not(.is-unpriced)').first.click()
    pg.wait_for_timeout(150)


# ------------------------------------------------------------- QCLC02 ------ #

_BEHAVIOUR = re.compile(r"hesitat|reject|won't do|wont do|lopsided|likely fair|\bfair\b", re.I)


def test_verdict_source_names_no_club_behaviour():
    src = JS.read_text(encoding="utf-8")
    block = src.split("let vClass", 1)[1].split("const verdict =", 1)[0]
    assert not _BEHAVIOUR.search(block), _BEHAVIOUR.search(block).group(0)
    gfx = src.split("const vWord =", 1)[1].split(";", 1)[0]
    assert not _BEHAVIOUR.search(gfx)
    assert "is-warn" not in src and "is-bad" not in src


def test_verdict_states_the_gap_on_the_served_page(server):
    with _page(server) as (pg, errors):
        _add(pg, "a", "Skenes")
        _add(pg, "b", "Skenes")
        same = pg.inner_text("#trade-machine .tm-balverdict").strip()
        assert same == "Balanced: within $5M.", same
        pg.locator("[data-tm-remove]").last.click()
        _add(pg, "b", "Hugus")
        text = pg.inner_text("#trade-machine .tm-balverdict").strip()
        assert re.fullmatch(r"Side B receives \$[0-9]+\.[0-9]M less \([0-9]+% gap\)\.", text), text
        assert not _BEHAVIOUR.search(text)
        assert not errors, errors


def test_trade_machine_glossary_matches_the_verdict():
    e = _gl("trade_machine")
    assert "winning side" not in e["formula"]
    assert "predicts no club's answer" in e["formula"]
    assert "predicts no club's answer" in e["definition"]
    para = "An MLB player's range is the projection P10-P90"
    assert e["methodology"].count(para) == 1


# ------------------------------------------------------------- QCLC04 ------ #

def test_surplus_glossary_names_the_projection_basis_the_hooks_price_on():
    sv = _gl("surplus_value")["definition"]
    assert "PROJECTION surplus for MLB players" in sv
    assert "Trade Machine" in sv and "Club Ledger" in sv
    assert "Two kinds" not in sv
    assert "debuted players are valued on realized WAR" not in _gl("tvi")["definition"]
    # the hooks it now describes are still there
    assert 'data-gl="surplus_value"' in JS.read_text(encoding="utf-8")


# ------------------------------------------------------------- QCLC05 ------ #

def test_grpo_chip_word_is_the_registry_verdict():
    src = JS.read_text(encoding="utf-8")
    word = re.search(r'const _TB_GRPO_VERDICT = "([a-z_]+)";', src).group(1)
    reg = json.loads(_src("data/model_registry.json"))
    row = next(m for m in reg["models"] if m["model_id"] == "grpo_prospect")
    assert word == row["verdict"], (word, row["verdict"])
    chip = src.split("GRPO within-cohort breakout score", 1)[1][:120]
    assert "${_TB_GRPO_VERDICT}" in chip


# ------------------------------------------------------------- QCLP01 ------ #

def test_boot_reads_neither_the_detail_file_nor_the_group_sidecar(server):
    reqs: list = []
    with _page(server, requests=reqs) as (pg, errors):
        pg.wait_for_timeout(1500)
        boot = [u for u in reqs if "/data/" in u]
        assert not [u for u in boot if "mlb_player_detail" in u or "grpo_public" in u], boot
        # the first focus in an Add player box asks for the detail file
        pg.locator('input[data-tm-search="a"]').focus()
        pg.wait_for_timeout(300)
        assert any("mlb_player_detail" in u for u in reqs)
        # the first breakout-chip click asks for the sidecar and fills the panel
        chip = pg.locator(".tm-signals button.chip").first
        if chip.count():
            chip.click()
            pg.wait_for_function(
                "(document.getElementById('tb-group-title').textContent || '').startsWith('GRPO group for')",
                timeout=30_000)
            assert any("grpo_public" in u for u in reqs)
        assert not errors, errors


def test_an_mlb_seed_still_loads_the_detail_file(server):
    reqs: list = []
    with _page(server, hash_="#tm=mlb:paul_skenes", requests=reqs) as (pg, errors):
        pg.wait_for_function("document.querySelectorAll('#trade-machine [data-tm-remove]').length > 0",
                             timeout=30_000)
        assert any("mlb_player_detail" in u for u in reqs)
        assert not errors, errors


# ------------------------------------------------------------- QCLP02 ------ #

def test_logos_come_from_the_hub_builder_at_twice_their_size(server):
    src = JS.read_text(encoding="utf-8")
    assert "teamlogos/mlb/500/${" not in src
    with _page(server) as (pg, errors):
        logos = pg.eval_on_selector_all(
            ".tm-board-table img.tm-logo", "els => els.map(e => [e.getAttribute('src'), e.alt])")
        assert logos
        assert all("/combiner/i?" in s and "&h=32&w=32" in s for s, _a in logos), logos[:3]
        assert all(a == "" for _s, a in logos), "the board prints the club code beside the mark"


# ------------------------------------------------------------- QCLP03 ------ #

def test_the_loader_holds_a_viewport_and_the_builder_its_height(server):
    css = _src("assets/trademachine.css")
    assert "#tradeboard-content:has(> .px-state.is-loading)" in css
    assert "#trade-machine:empty" in css
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            pg = b.new_page(viewport={"width": 1280, "height": 900})
            pg.add_init_script(
                "window.__cls=0;try{new PerformanceObserver(l=>{for(const e of l.getEntries())"
                "{if(!e.hadRecentInput)window.__cls+=e.value}}).observe({type:'layout-shift',buffered:true})}catch(e){}")
            pg.goto(server + "trademachine/")
            pg.wait_for_selector(".tm-board-table tbody tr", timeout=90_000)
            pg.wait_for_timeout(1000)
            cls = pg.evaluate("window.__cls")
        finally:
            b.close()
    assert cls < 0.1, cls   # 0.569 before the fix (qualaudit median of 3)


# ------------------------------------------------------------- QCLA05 ------ #

def test_adding_by_keyboard_keeps_the_place_and_says_what_changed(server):
    with _page(server) as (pg, errors):
        inp = pg.locator('input[data-tm-search="a"]')
        inp.focus()
        pg.keyboard.type("Skenes")
        pg.wait_for_selector('[data-tm-results="a"] .tm-hit:not(.is-unpriced)', timeout=20_000)
        # results may refresh once when the detail file lands; tab from the box
        pg.wait_for_timeout(1500)
        pg.locator('input[data-tm-search="a"]').focus()
        pg.keyboard.press("Tab")
        assert pg.evaluate("document.activeElement.classList.contains('tm-hit')")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(200)
        active = pg.evaluate("document.activeElement.getAttribute('data-tm-search')")
        assert active == "a", "focus fell out of the builder after the add"
        live = pg.locator("#tm-live")
        assert live.get_attribute("role") == "status" and live.get_attribute("aria-live") == "polite"
        said = live.inner_text()
        assert "added to Side A." in said and "Side A receives $" in said, said
        # remove by keyboard: focus returns to the same side's box
        pg.locator('[data-tm-remove^="a:"]').first.focus()
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(200)
        assert pg.evaluate("document.activeElement.getAttribute('data-tm-search')") == "a"
        assert "removed from Side A." in pg.locator("#tm-live").inner_text()
        assert not errors, errors


# ------------------------------------------------------------- QCLA06 ------ #

def test_sorting_by_keyboard_keeps_focus_on_the_header(server):
    with _page(server) as (pg, errors):
        pg.locator('th[data-tb-sortcol="age"]').focus()
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(200)
        got = pg.evaluate("[document.activeElement.tagName, document.activeElement.dataset.tbSortcol,"
                          " document.activeElement.getAttribute('aria-sort')]")
        assert got == ["TH", "age", "ascending"], got
        # no Tab stop nested inside a sort header; the term rides aria-describedby
        nested = pg.eval_on_selector_all(
            "th[data-tb-sortcol] *",
            "els => els.filter(e => e.tabIndex >= 0 || e.matches('a,button,input,select')).length")
        assert nested == 0
        assert pg.get_attribute('th[data-tb-sortcol="fv"]', "aria-describedby") == "gl-def-fv"
        # the table is named by the board heading, an h2
        lab = pg.get_attribute(".tm-board-table", "aria-labelledby")
        assert pg.evaluate(f"document.getElementById('{lab}').tagName") == "H2"
        assert not errors, errors


def test_the_export_chip_clears_the_header_row_at_390(server):
    with _page(server, w=390, h=844, touch=True) as (pg, _e):
        pg.wait_for_selector("#tradeboard-content .eephus-export-chip", state="attached", timeout=20_000)
        hits = pg.evaluate("""() => {
          const out = [];
          document.querySelectorAll('th[data-tb-sortcol]').forEach(th => {
            th.scrollIntoView({block: 'center', inline: 'nearest'});
            const b = th.getBoundingClientRect();
            const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
            if (hit && !th.contains(hit)) out.push(th.dataset.tbSortcol);
          });
          return out; }""")
        assert hits == [], hits


# ------------------------------------------------------------- QCLA07 ------ #

def test_filter_chips_pager_and_boxes_carry_state_and_names(server):
    with _page(server) as (pg, errors):
        chips = pg.eval_on_selector_all(
            "[data-tb-pool],[data-tb-tier],[data-tb-pos]", "els => els.map(e => e.getAttribute('aria-pressed'))")
        assert chips and all(c in ("true", "false") for c in chips)
        assert chips.count("true") == 3
        pg.locator(".filter-toggle").first.click()
        pg.locator('[data-tb-pool="mlb"]').click()
        pressed = pg.eval_on_selector_all("[data-tb-pool]", "els => els.map(e => e.getAttribute('aria-pressed'))")
        assert pressed == ["false", "false", "true"], pressed
        cur = pg.eval_on_selector_all('.pg-chip[aria-current="page"]', "els => els.map(e => e.textContent)")
        assert cur and set(cur) == {"1"}
        assert pg.get_attribute(".pg-chip >> nth=1", "aria-label").startswith("Page ")
        for sel in ('input[data-tm-search="a"]', 'input[data-tm-search="b"]', "#tb-search"):
            assert pg.get_attribute(sel, "aria-label"), sel
        assert not errors, errors


def test_touch_targets_reach_44_px_at_390(server):
    with _page(server, w=390, h=844, touch=True) as (pg, _e):
        pg.wait_for_selector("#tradeboard-content .eephus-export-chip", state="attached", timeout=20_000)
        small = pg.evaluate("""() => {
          const sel = ['.tm-board-table td.tm-player a', 'th[data-tb-sortcol]', '.pg-chip', '.pg-nav',
                       '#tradeboard-content .eephus-export-chip', '.filter-toggle', 'input.tm-search', '#tb-search'];
          const out = [];
          sel.forEach(s => document.querySelectorAll(s).forEach(e => {
            const b = e.getBoundingClientRect();
            if (b.width && (b.height < 44 || b.width < 24)) out.push([s, Math.round(b.width), Math.round(b.height)]);
          }));
          return out; }""")
        assert small == [], small[:5]
