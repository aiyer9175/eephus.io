# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the Library's WAR Framework Comparison view (LIB_WAR_COMPARISON,
owner EW3-22, 2026-10-15): the fWAR, bWAR and eWAR method table on the Methods
shelf, copied word for word from the owner's comparison artifact.

1. The view is registered on the Methods shelf and the Page Index lists it.
2. The copy: 12 rows in the artifact's order, three columns, four candidate
   tags, the caption, three notes, and the "Standalone version" link to the
   artifact. UPKEEP: when an eWAR part is admitted or rejected, the eWAR cell in
   assets/glossary.js _warcData() changes and the pins below change with it.
3. The render: at 390 px the page does not scroll sideways and the table
   scrolls inside its own frame, in the light and the dark theme.

Playwright is optional; the browser test skips cleanly without it."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from conftest import serve_site

import build_site as B

ROOT = Path(__file__).parent
GLJS = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8").replace("\r\n", "\n")
URL = "https://claude.ai/artifact/UghNTdvm8aLES39nnk9aYj"
ROW_LABELS = ["Objective", "Inclusion rule", "Hitting", "Pitching", "Pitch economy",
              "Defense, non-catchers", "Defense, catchers", "ABS challenges", "Baserunning",
              "Positional adjustment", "Prospects (MiLB)", "Uses"]
# The rows whose eWAR cell carries the candidate tag, as of 2026-10-15.
CANDIDATE_ROWS = ["Pitching", "Pitch economy", "ABS challenges", "Positional adjustment"]


def _block() -> str:
    start = GLJS.index("// ---- Methods > WAR Framework Comparison")
    return GLJS[start:GLJS.index("// ---- Library view")]


def _data() -> dict:
    blk = re.search(r"function _warcData\(\) \{(.*?)\n\}\n", _block(), re.S).group(1)
    rows = [json.loads(ln.strip().rstrip(",")) for ln in blk.splitlines() if ln.strip().startswith('["')]
    one = lambda k: json.loads(re.search(k + r': (".*?"),\n', blk).group(1))  # noqa: E731
    notes = json.loads("[" + re.search(r"notes: \[(.*?)\],\n", blk, re.S).group(1).strip().rstrip(",") + "]")
    cols = json.loads(re.search(r"cols: (\[.*?\]),", blk).group(1))
    return {"rows": rows, "cols": cols, "notes": notes, "url": one("url"), "title": one("title"),
            "caption": one("caption"), "meta": one("meta")}


def test_the_view_is_registered_on_the_methods_shelf():
    v = {x["id"]: x for x in B.GLOSSARY_VIEWS}["war-comparison"]
    assert (v["shelf"], v["label"], v["body"]) == ("methods", "WAR Framework Comparison", "war-comparison-body")
    assert ('{ id: "war-comparison", shelf: "methods", label: "WAR Framework Comparison", '
            'body: "war-comparison-body", render: renderWarComparison, aliases: [] },') in GLJS
    assert any(h == "/glossary/#view=war-comparison" for h, _n, _p in B.PAGE_INDEX_VIEWS)
    # the upkeep note sits on both registry rows
    assert "UPKEEP (LIB_WAR_COMPARISON)" in GLJS
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    assert "UPKEEP: when an eWAR part is admitted or" in src


def test_the_copy_is_the_artifacts():
    d = _data()
    assert d["url"] == URL
    assert d["title"] == "WAR framework comparison: fWAR, bWAR, eWAR"
    assert d["cols"] == ["Component", "fWAR (FanGraphs)", "bWAR (Baseball-Reference)", "eWAR"]
    assert [r[0] for r in d["rows"]] == ROW_LABELS
    assert all(len(r) == 4 for r in d["rows"])
    assert [r[0] for r in d["rows"] if "[candidate]" in r[3]] == CANDIDATE_ROWS
    assert not any("[candidate]" in c for r in d["rows"] for c in r[:3])
    assert d["caption"].startswith("Rows marked candidate enter eWAR only if")
    assert len(d["notes"]) == 3
    blk = _block()
    assert ">Standalone version</a>" in blk
    # no em-dash or en-dash anywhere in the view
    assert chr(0x2014) not in blk and chr(0x2013) not in blk


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


_PROBE = """() => {
  const el = document.getElementById('war-comparison-body');
  const fr = el && el.querySelector('.warc-frame');
  const a = el && el.querySelector('.warc-link a');
  const cs = el ? getComputedStyle(el.querySelector('.warc-table td.warc-e')) : null;
  return { shown: !!el && el.style.display !== 'none',
           rows: el ? el.querySelectorAll('.warc-table tbody tr').length : 0,
           tags: el ? el.querySelectorAll('.warc-tag').length : 0,
           notes: el ? el.querySelectorAll('.warc-notes li').length : 0,
           href: a ? a.getAttribute('href') : null, link: a ? a.textContent : null,
           frameScroll: fr ? fr.scrollWidth > fr.clientWidth : null,
           frameRight: fr ? fr.getBoundingClientRect().right : null,
           ink: cs ? cs.color : null, bg: getComputedStyle(document.body).backgroundColor,
           theme: document.documentElement.getAttribute('data-theme'),
           scrollW: document.documentElement.scrollWidth, innerW: innerWidth };
}"""


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_view_renders_at_390_without_a_page_scroll(browser, theme):
    errors: list[str] = []
    with serve_site() as base:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.add_init_script(f'try {{ localStorage.setItem("prospect-tracker.theme", "{theme}"); }} catch (e) {{}}')
        page.on("pageerror", lambda e: errors.append(e.message))
        try:
            page.goto(base + "glossary/index.html#view=war-comparison", wait_until="load", timeout=15_000)
            page.wait_for_selector("#war-comparison-body .warc-table", timeout=10_000)
            out = page.evaluate(_PROBE)
        finally:
            page.close()
    assert not errors, errors
    assert out["theme"] == theme
    assert out["shown"] and out["rows"] == 12 and out["tags"] == 4 and out["notes"] == 3
    assert (out["href"], out["link"]) == (URL, "Standalone version")
    assert out["scrollW"] == out["innerW"], "the page scrolls sideways at 390"
    assert out["frameScroll"], "the table does not scroll inside its own frame"
    assert out["frameRight"] <= out["innerW"]
