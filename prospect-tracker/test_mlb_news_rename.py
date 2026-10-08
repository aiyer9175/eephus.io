# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /news/ feed is called "MLB News" everywhere it is named (owner ask
2026-10-02, HOME_0_RENAME_MLB_NEWS).

Static checks over the committed build artifacts and the builder strings:
the homepage rail head and ticker tag, the /news/ h1, title and meta, every
footer link to /news/, the Generate GFX card specs and the Library page-index
row. The URL stays /news/. PROSPX keeps its own "Prospect news" ribbon (it
lists prospect events only), so prospx/index.html is exempt from the
no-old-name check. The claims rule (C9) is pinned too: the descriptive copy
names MLB transactions now that the Q9_22c flip serves MLB rows (copy rows
CP-019, CP-020, CP-185, CP-210), and only while the flag is on."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import build_site as B

ROOT = Path(__file__).parent
OLD = "Prospect News"
NEW = "MLB News"
FOOTER_RE = re.compile(r'<nav class="eephus-footer-links"[^>]*>(.*?)</nav>', re.S)


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        pytest.skip(f"{rel} not built")
    return p.read_text(encoding="utf-8")


def _built_pages() -> list[Path]:
    pages = [ROOT / "404.html", ROOT / "index.html"]
    for p in sorted(ROOT.glob("*/**/index.html")):
        rel = p.relative_to(ROOT).as_posix()
        if rel.split("/")[0] in {"node_modules", "data", "docs", "tools", "branding"}:
            continue
        pages.append(p)
    return [p for p in pages if p.exists()]


def test_label_constant():
    assert B.NEWS_LABEL == NEW


def test_homepage_rail_and_ticker():
    html = _read("index.html")
    assert OLD not in html
    assert 'title="All MLB News"><span class="blip"></span>MLB News<' in html
    # tabindex=-1 since QHOA06: the ticker is aria-hidden, so its tag leaves the Tab order
    assert '<span class="ticker-tag"><a href="/news/" tabindex="-1"><span class="blip"></span>MLB News</a></span>' in html


def test_news_page_head():
    html = _read("news/index.html")
    assert OLD not in html
    assert "<title>MLB News - eephus.io</title>" in html
    assert re.search(r"</svg>MLB News</h1>", html)
    meta = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
    assert meta == ("MLB and MiLB transactions, debuts, IL moves, eFV changes and FA signings, "
                    "filterable by type."), meta
    assert ('<span class="section-sub">MLB and MiLB transactions · eFV moves · FA · last 30 days</span>'
            in html)


def test_every_footer_links_mlb_news():
    pages = _built_pages()
    assert len(pages) >= 20, f"only {len(pages)} built pages found"
    with_footer = 0
    for p in pages:
        html = p.read_text(encoding="utf-8")
        m = FOOTER_RE.search(html)
        if not m:
            continue
        links = m.group(1)
        assert OLD not in links, f"{p.relative_to(ROOT)} footer still says {OLD}"
        # PROSPX carries its own hand-written footer with no /news/ link.
        if 'href="/news/"' in links:
            with_footer += 1
            assert '<a href="/news/">MLB News</a>' in links, f"{p.relative_to(ROOT)} footer news link is not MLB News"
        if p.relative_to(ROOT).as_posix() != "prospx/index.html":
            assert OLD not in html, f"{p.relative_to(ROOT)} still says {OLD}"
    assert with_footer >= 20, f"only {with_footer} footers link /news/"
    assert B._footer().count('<a href="/news/">MLB News</a>') == 1


def test_gfx_spec_strings():
    for src in (B._NEWS_GFX_JS, _read("news/index.html")):
        assert "module:'MLB News'" in src
        assert "title:'MLB News - '+mon" in src
        assert "title:'MLB News - '+lbl" in src
        assert "filenameBase:'mlb-news-'+iso" in src
        assert "filenameBase:'mlb-news-'+day" in src
        assert "prospect-news-" not in src
        assert OLD not in src


def test_ticker_empty_fallback():
    assert "MLB News · live" in B._ticker_html([])


def test_library_page_index_row():
    """The Page Index is generated in build_site since LIBRARY_8; its /news/ row
    names MLB transactions while they are served (CP-210)."""
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert '["/news/", "Prospect News"' not in js
    assert B.PAGE_INDEX_NAMES["/news/"] == NEW
    assert B.PAGE_INDEX_PURPOSE["/news/"] == "MLB and MiLB transactions, debuts, IL, eFV changes, FA signings"
    gl = _read("glossary/index.html")
    assert '["/news/","MLB News","MLB and MiLB transactions, debuts, IL, eFV changes, FA signings"]' in gl


def test_prospx_ribbon_keeps_its_name():
    html = _read("prospx/index.html")
    assert ">Prospect news</span>" in html


def test_claims_rule_names_mlb_transactions_once_served():
    """The flip (Q9_22c) serves MLB rows, so the copy says so; a build with the
    flag off would say nothing of them (test_mlb_events_rows pins that side)."""
    import mlb_events
    assert mlb_events.MLB_EVENTS_LIVE is True
    html = _read("news/index.html")
    assert "MLB and MiLB transactions" in html
    gl = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    entry = next(e for e in gl["entries"] if e.get("id") == "wire_ticker")
    assert entry["definition"] == ("The homepage MLB News feed and ticker: MLB and MiLB transactions, "
                                   "debuts, IL moves, eFV changes and FA events, dated, typed by colour "
                                   "and glyph.")
    assert "MLB transactions" not in entry["definition"]
