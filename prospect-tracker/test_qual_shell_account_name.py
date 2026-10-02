# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Surface-quality audit 2026-10-02, findings QHOA01, QMLA04 and QREA04.

At 640 px or less the shared nav account button lost its accessible name:
its only text child (.eph-acct-label) was display:none and the glyph is
aria-hidden, so axe reported button-name on every page at 390 px, and the
homepage drawer button showed only the glyph. The label is now clipped
(visually hidden, still in the accessibility tree) and only inside the
header nav, and both account buttons carry an aria-label so the name never
depends on CSS.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import serve_site
from test_smoke_home_otd_account import _media_block

ROOT = Path(__file__).parent


def test_phone_block_does_not_display_none_the_account_label():
    css = (ROOT / "assets" / "eephus-account.css").read_text(encoding="utf-8")
    block = _media_block(css, "max-width: 640px")
    rules = re.findall(r"([^{}]*\.eph-acct-label[^{}]*)\{([^}]*)\}", block)
    assert rules, "the 640px block no longer styles .eph-acct-label"
    for sel, body in rules:
        assert not re.search(r"display\s*:\s*none", body), (sel, body)
        assert ".eephus-nav" in sel, sel  # the homepage drawer keeps its text
        assert re.search(r"clip-path\s*:\s*inset\(50%\)", body), body


def test_every_account_button_markup_carries_an_aria_label():
    js = (ROOT / "assets" / "eephus-ui.js").read_text(encoding="utf-8")
    tags = re.findall(r"<button class=\"eph-acct-btn[^\"]*\"[^>]*>", js)
    acts = {re.search(r'data-act="(\w+)"', t).group(1): t for t in tags}
    assert {"signin", "menu", "bell"} <= set(acts), acts
    for act, tag in acts.items():
        m = re.search(r'aria-label="([^"]*)"', tag)
        assert m and m.group(1).strip(), (act, tag)


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


def test_account_button_name_at_phone_width(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            out = {}
            for route in ("news/", "404.html"):
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.goto(server + route, wait_until="networkidle", timeout=60_000)
                page.wait_for_selector('.eephus-nav .eph-acct-btn[data-act="signin"]', timeout=30_000)
                cdp = page.context.new_cdp_session(page)
                doc = cdp.send("DOM.getDocument", {"depth": -1})
                nid = cdp.send("DOM.querySelector", {"nodeId": doc["root"]["nodeId"],
                                                     "selector": '.eephus-nav .eph-acct-btn[data-act="signin"]'})["nodeId"]
                ax = cdp.send("Accessibility.getPartialAXTree", {"nodeId": nid, "fetchRelatives": False})["nodes"]
                btn = [n for n in ax if n.get("role", {}).get("value") == "button"]
                box = page.eval_on_selector('.eephus-nav .eph-acct-btn[data-act="signin"]',
                                            "b => { const r = b.getBoundingClientRect(); return [r.width, r.height]; }")
                out[route] = (btn[0].get("name", {}).get("value", "") if btn else "", box)
                page.close()
        finally:
            browser.close()
    for route, (name, (w, h)) in out.items():
        assert name == "Sign in", (route, name)
        assert w >= 44 and h >= 44, (route, w, h)
