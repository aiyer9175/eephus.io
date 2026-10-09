# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""/arbitration/ display pass (2026-10-03): the four surface-quality findings.

QCLA16  logos beside their code read alt="", filter chips carry aria-pressed,
        the History and Team View heads are scoped and draw no pointer, the
        caveat heading is an h2, the masthead term is wired, and the row links
        and sort heads are 44px tall at phone width.
QCLP04  the board does not fetch the 1.9 MB identity map (the exporter writes
        each row's link token) and paints 100 rows, not all of them.
QCLP05  every hub logo comes through ESPN's resizing combiner at twice its
        drawn size (34px by default), not as the 500px master.
QCLC21  the Model tab and the Club Ledger quote the a6 statement without the
        unmeasured counting-stats mechanism; the gate artifact is not edited.

External logo requests are answered with a 1px PNG here, so the test reads the
URLs the page asks for without depending on the network.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest

from conftest import load_data_doc, serve_site

ROOT = Path(__file__).resolve().parent
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
COMBINER = "https://a.espncdn.com/combiner/i?img=/i/teamlogos/mlb/500/"


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


def _board():
    b = load_data_doc("arbitration.json")
    if not b or not b.get("rows"):
        pytest.skip("data/arbitration.json not built")
    return b


def _page(p, url, width=1280, height=900, fetched=None):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": width, "height": height})
    page.route("https://a.espncdn.com/**",
               lambda r: r.fulfill(status=200, content_type="image/png", body=PNG))
    if fetched is not None:
        page.on("request", lambda r: fetched.append(r.url))
    page.goto(url, wait_until="networkidle", timeout=60_000)
    page.wait_for_selector("#arb-panel-projections tbody tr", timeout=30_000)
    return browser, page


_A11Y = """() => {
  const vis = e => !e.closest('[hidden]');
  const logos = [...document.querySelectorAll('#arb-panel-projections img.eephus-teamlogo')];
  const chips = [...document.querySelectorAll('#arb-panel-projections .filter-bar button.chip')];
  const heads = [...document.querySelectorAll('h1,h2,h3,h4')].filter(h => vis(h) && h.offsetParent !== null)
    .map(h => +h.tagName[1]);
  const term = document.querySelector('.arb-app .section-head [data-gl]');
  return {
    logos: logos.length, logoAlt: [...new Set(logos.map(i => i.getAttribute('alt')))],
    logoSrc: logos.map(i => i.getAttribute('src')),
    chips: chips.map(b => [b.classList.contains('active'), b.getAttribute('aria-pressed')]),
    heads, termDesc: term ? term.getAttribute('aria-describedby') : null,
    rows: document.querySelectorAll('#arb-panel-projections tbody tr').length,
    nodes: document.getElementsByTagName('*').length,
  };
}"""

_HEADS = """(panel) => {
  const ths = [...document.querySelectorAll('#arb-panel-' + panel + ' table th')];
  return {n: ths.length, noScope: ths.filter(t => t.getAttribute('scope') !== 'col').length,
          pointer: ths.filter(t => getComputedStyle(t).cursor === 'pointer').length,
          chips: [...document.querySelectorAll('#arb-panel-' + panel + ' .filter-bar button.chip')]
            .map(b => [b.classList.contains('active'), b.getAttribute('aria-pressed')])};
}"""


def _states_agree(chips):
    return bool(chips) and all(p == ("true" if on else "false") for on, p in chips)


def test_qcla16_names_states_and_heads(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    _board()
    with sync_playwright() as p:
        browser, page = _page(p, server + "arbitration/")
        try:
            page.wait_for_function(
                "() => !!document.querySelector('.arb-app .section-head [data-gl][aria-describedby]')",
                timeout=30_000)
            a = page.evaluate(_A11Y)
            page.click('#arb-panel-projections [data-cls="2"]')
            after = page.evaluate(_A11Y)
            page.click('[data-arbsection="history"]')
            page.wait_for_selector("#arb-panel-history tbody tr", timeout=30_000)
            hist = page.evaluate(_HEADS, "history")
            page.click('[data-arbsection="teams"]')
            page.wait_for_selector("#arb-panel-teams tbody tr", timeout=30_000)
            teams = page.evaluate(_HEADS, "teams")
        finally:
            browser.close()
    # the mark is decorative: the code follows it as text
    assert a["logos"] > 0 and a["logoAlt"] == [""], a["logoAlt"]
    # every chip says its state, and the state follows a click
    assert _states_agree(a["chips"]), a["chips"]
    assert after["chips"][2] == [True, "true"] and after["chips"][0] == [False, "false"]
    assert _states_agree(hist["chips"]), hist["chips"]
    # headings step h1 to h2, never h1 to h3
    assert a["heads"][:2] == [1, 2], a["heads"]
    assert a["termDesc"], "the masthead glossary term has no aria-describedby"
    for t in (hist, teams):
        assert t["n"] > 0 and t["noScope"] == 0, t
        assert t["pointer"] == 0, "a head that does not sort draws a pointer"


def test_qcla16_touch_targets_at_390(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    _board()
    with sync_playwright() as p:
        browser, page = _page(p, server + "arbitration/", width=390, height=844)
        try:
            r = page.evaluate("""() => {
              const h = s => [...document.querySelectorAll(s)].map(e => e.getBoundingClientRect().height);
              return {links: h('#arb-panel-projections tbody td a'), sorts: h('#arb-panel-projections .arb-sort'),
                      sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth};
            }""")
        finally:
            browser.close()
    assert r["links"] and min(r["links"]) >= 44, min(r["links"] or [0])
    assert r["sorts"] and min(r["sorts"]) >= 44, min(r["sorts"] or [0])
    assert r["sw"] <= r["cw"], "the page scrolls sideways at 390"


def test_qclp04_no_identity_map_and_a_100_row_window(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    b = _board()
    assert all(r.get("h") is None or re.match(r"^[px]:.+", r["h"]) for r in b["rows"])
    assert sum(1 for r in b["rows"] if r.get("h")) >= 800
    fetched = []
    with sync_playwright() as p:
        browser, page = _page(p, server + "arbitration/", fetched=fetched)
        try:
            a = page.evaluate(_A11Y)
        finally:
            browser.close()
    assert not [u for u in fetched if "player_links" in u]
    assert a["rows"] == min(100, len(b["rows"]))
    # 16,181 elements with every row painted (2026-10-02); the window holds it near 2,400
    assert a["nodes"] < 4000, a["nodes"]


def test_qclp05_logos_come_resized(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    _board()
    fetched = []
    with sync_playwright() as p:
        browser, page = _page(p, server + "arbitration/", fetched=fetched)
        try:
            a = page.evaluate(_A11Y)
            hub = page.evaluate("""() => ({
              url96: EEPHUS_HUB.teamLogoURL('PIT', 96), url: EEPHUS_HUB.teamLogoURL('PIT'),
              clubLogo: EEPHUS_HUB.club('KC').logo, tag: EEPHUS_HUB.teamLogo('NYY'),
              deco: EEPHUS_HUB.teamLogo('NYY', null, {decorative: true})})""")
        finally:
            browser.close()
    assert a["logoSrc"] and all(s.startswith(COMBINER) and s.endswith("&h=34&w=34") for s in a["logoSrc"])
    espn = [u for u in fetched if "teamlogos" in u]
    assert espn and all(u.startswith(COMBINER) for u in espn), [u for u in espn if not u.startswith(COMBINER)][:3]
    assert hub["url"] == COMBINER + "pit.png&h=34&w=34"
    assert hub["url96"] == COMBINER + "pit.png&h=96&w=96"
    assert hub["clubLogo"] == COMBINER + "kc.png&h=34&w=34"
    assert 'alt="NYY"' in hub["tag"] and 'alt=""' in hub["deco"]


def test_qclc21_the_a6_mechanism_is_not_claimed():
    import build_site as B
    ev = load_data_doc("arbitration_eval.json")
    if not ev or not ev.get("a6_swartz"):
        pytest.skip("no a6 arm in the eval artifact")
    html = B._arb_model_panel()
    assert "not mysterious" not in html and "actually reward" not in html
    if "The mechanism is not mysterious" in str(ev["a6_swartz"].get("statement")):
        assert ("Swartz uses counting stats (HR, RBI, saves, wins) this model excludes; "
                "how much of the gap that explains is not measured.") in html
    # the verdict and its receipt stay
    assert "NULL" in html and "on %d settled seasons" % ev["a6_swartz"]["n"] in html
    js = (ROOT / "assets" / "ledger.js").read_text(encoding="utf-8")
    assert 'swartzCopy(copy("swartz_a6"))' in js and "swartzCopy(E.statement)" in js
    assert "how much of the gap that explains is not measured" in js


def test_display_pass_keeps_every_pinned_disclosure(server):
    """The copy pass compressed the caveats; it deleted none of them."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    b = _board()
    with sync_playwright() as p:
        browser, page = _page(p, server + "arbitration/")
        try:
            cav = page.eval_on_selector(".arb-caveatbar", "e => e.textContent")
            sub = page.eval_on_selector(".arb-app .section-head .section-sub", "e => e.textContent")
            page.click('[data-arbsection="teams"]')
            page.wait_for_selector("#arb-panel-teams tbody tr", timeout=30_000)
            note = page.eval_on_selector("#arb-panel-teams .arb-note", "e => e.textContent")
        finally:
            browser.close()
    assert "club control ends" in cav and "overstate" in cav
    assert b["rules"]["expires"] in cav and "no interval covers" in cav
    # The masthead's arb-2+ clause follows the artifact's verdict
    # (build_site._arb_masthead_verdict; docs/ARBITRATION_GATE.md section 15).
    a2 = ((json.loads((ROOT / "data" / "arbitration_eval.json").read_text(encoding="utf-8"))
           .get("results") or {}).get("arb2plus") or {}).get("verdict")
    assert "beat its baseline" in sub and "step multiplier" in sub
    assert ("now beats it" if a2 == "PASS" else "did not") in sub
    assert "Not a payroll forecast" in note and "tendered" in note
