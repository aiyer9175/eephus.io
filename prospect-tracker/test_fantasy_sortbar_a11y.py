# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /fantasy/ card boards' div sort bars announce their sort state the ARIA
way (census M24-4, owner answer 2026-09-25).

The Redraft and Dynasty card boards are not tables: their sort controls are
<span role="button"> chips in a .ff-sortbar strip and a .ff-card-head grid.
They used to carry aria-sort, which ARIA reads only on a columnheader or
rowheader, so a screen reader heard nothing. The served contract is now:

  * no element outside a table header carries aria-sort;
  * the active chip is class="is-sorted" aria-pressed="true" and holds its
    state as .visually-hidden text (", sorted descending" / ", sorted
    ascending"); every other chip is aria-pressed="false" with no such text;
  * the active paint rides the .is-sorted class in assets/site.css, not an
    attribute selector;
  * Enter on a focused chip re-sorts the board, and Enter again flips it.

The source and CSS guards always run; the rendered half needs playwright.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import serve_site

ROOT = Path(__file__).parent
CSS = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
SORT_TEXT = (", sorted ascending", ", sorted descending")


def _sort_btn(name: str) -> str:
    src = (ROOT / "assets" / name).read_text(encoding="utf-8")
    return src.split("function sortBtn(")[1].split("\n  function ")[0]


@pytest.mark.parametrize("name", ["redraft.js", "dynasty.js"])
def test_sort_chip_source_carries_no_aria_sort(name):
    body = _sort_btn(name)
    assert "aria-sort" not in body, name
    assert "aria-pressed" in body and "is-sorted" in body and "visually-hidden" in body, name


def test_sortbar_paint_is_a_class_not_an_attribute_selector():
    rules = [ln for ln in CSS.splitlines()
             if re.match(r"\s*\.(ff-sortbar|ff-card-head|mlb-sortbar)\b", ln)]
    assert rules, "the sort bar rules moved; re-point this guard"
    assert not [ln for ln in rules if "aria-sort" in ln], rules
    assert any(".is-sorted" in ln for ln in rules), rules


def test_site_css_defines_the_visually_hidden_utility():
    m = re.search(r"\.visually-hidden\s*\{([^}]*)\}", CSS)
    assert m, "no .visually-hidden utility in assets/site.css"
    body = m.group(1)
    for decl in ("position: absolute", "width: 1px", "height: 1px", "overflow: hidden"):
        assert decl in body, decl


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


_STATE = """sel => [...document.querySelectorAll(sel)].map(h => {
  const sr = h.querySelector('.visually-hidden');
  return {key: h.getAttribute('data-rdsort') || h.getAttribute('data-dynsort'),
          pressed: h.getAttribute('aria-pressed'), cls: h.className,
          sr: sr ? sr.textContent : null,
          srPos: sr ? getComputedStyle(sr).position : null,
          srW: sr ? sr.getBoundingClientRect().width : null}; })"""

_ORDER = """root => [...document.querySelectorAll(root + ' .ff-card')].slice(0, 12)
  .map(c => c.innerText.split('\\n').slice(0, 3).join(' '))"""

_BAD_ARIA = """() => [...document.querySelectorAll('[aria-sort]')]
  .filter(e => e.tagName !== 'TH' || e.hasAttribute('role'))
  .map(e => e.tagName + '.' + e.className)"""


def _check_board(page, root, attr):
    chips = root + " [" + attr + "]"
    st = page.evaluate(_STATE, chips)
    assert st, root + ": no sort chips rendered"
    assert page.evaluate(_BAD_ARIA) == [], "aria-sort outside a table header"
    on = [s for s in st if s["pressed"] == "true"]
    assert on, (root, st)
    assert all("is-sorted" in s["cls"] and s["sr"] in SORT_TEXT for s in on), on
    assert all(s["srPos"] == "absolute" and s["srW"] <= 1 for s in on), on
    off = [s for s in st if s["pressed"] != "true"]
    assert all(s["pressed"] == "false" and s["sr"] is None and "is-sorted" not in s["cls"]
               for s in off), off
    # keyboard: Enter on an inactive tape chip sorts the board by it
    target = page.evaluate(
        "sel => { const h = [...document.querySelectorAll(sel)]"
        ".find(h => h.getAttribute('aria-pressed') === 'false');"
        " return h ? h.getAttribute('" + attr + "') : null; }", root + " .ff-sortbar [" + attr + "]")
    assert target, root + ": no inactive tape chip"
    one = root + " .ff-sortbar [" + attr + '="' + target + '"]'
    before = page.evaluate(_ORDER, root)
    page.wait_for_function(
        "sel => { const h = document.querySelector(sel); if (!h) return false;"
        " if (document.activeElement !== h) { h.focus(); return false; } return true; }",
        arg=one, timeout=15_000)
    page.keyboard.press("Enter")
    page.wait_for_function(
        "sel => { const h = document.querySelector(sel); return !!h && h.getAttribute('aria-pressed') === 'true'; }",
        arg=one, timeout=15_000)
    after = page.evaluate(_ORDER, root)
    assert after != before, root + ": Enter on " + target + " did not re-sort the board"
    first = page.evaluate(_STATE, one)[0]
    assert first["sr"] in SORT_TEXT and "is-sorted" in first["cls"], first
    assert page.evaluate("sel => document.activeElement === document.querySelector(sel)", one), \
        "focus did not return to the chip after the re-render"
    page.keyboard.press("Enter")
    page.wait_for_function(
        "a => { const s = document.querySelector(a[0]); const sr = s && s.querySelector('.visually-hidden');"
        " return !!sr && sr.textContent !== a[1]; }", arg=[one, first["sr"]], timeout=15_000)
    assert page.evaluate(_BAD_ARIA) == []


def test_fantasy_card_boards_sort_chips_rendered(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errs: list[str] = []
            page.on("pageerror", lambda e: errs.append(e.message))
            page.goto(server + "fantasy/", wait_until="load", timeout=90_000)
            page.wait_for_selector('[data-redraftsection="ros_hitter"]', timeout=60_000)
            page.click('[data-redraftsection="ros_hitter"]')
            try:
                page.wait_for_function(
                    "() => document.querySelectorAll('#redraft-app-root .ff-sortbar [data-rdsort]').length > 2",
                    timeout=60_000)
            except Exception:  # noqa: BLE001
                pytest.skip("the Redraft ROS Hitters board painted no cards on this machine's data")
            _check_board(page, "#redraft-app-root", "data-rdsort")
            page.click('[data-fantasymodule="dynasty"]')
            page.wait_for_function(
                "() => document.querySelectorAll('#dynasty-app-root .ff-sortbar [data-dynsort]').length > 2",
                timeout=60_000)
            _check_board(page, "#dynasty-app-root", "data-dynsort")
            assert not errs, errs
        finally:
            browser.close()
