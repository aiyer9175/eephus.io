# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The glossary module reads "Library" (owner ask 2026-10-02, LIBRARY_2).

Pins: the display name comes from one constant; no served nav, footer,
masthead, rail or page title says "Glossary"; the module key "glossary" and
the URL /glossary/ stay; /library/ is a noindex redirect stub to /glossary/
that ships; the Library draws its own pixel icon (i-library, an open book),
and i-glossary survives only as an alias of it for the URL-keyed canvas
painters.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import build_site as B

ROOT = Path(__file__).parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _served_pages() -> list[str]:
    pages = ["index.html", "404.html", "prospx/index.html",
             "collegesavant/index.html", "collegesavant/pitcher_index.html"]
    for p in sorted(ROOT.glob("*/index.html")):
        rel = p.relative_to(ROOT).as_posix()
        if rel.split("/")[0] in ("data", "vendor", "node_modules", "library"):
            continue
        pages.append(rel)
    return sorted(set(pages))


def test_display_name_is_one_constant_and_the_key_and_url_stay():
    assert B.GLOSSARY_DISPLAY_NAME == "Library"
    leaves = {k: (label, href) for k, label, href in B.nav_leaves()}
    assert leaves["glossary"] == ("Library", "/glossary/")


@pytest.mark.parametrize("rel", _served_pages())
def test_no_served_nav_masthead_or_title_says_glossary(rel):
    text = _src(rel)
    if 'http-equiv="refresh"' in text:
        pytest.skip("redirect stub, no nav")
    title = re.search(r"<title>(.*?)</title>", text, re.S)
    assert title and "Glossary" not in title.group(1), (rel, title and title.group(1))
    for pat in (r'<nav\s+class="eephus-links">(.*?)</nav>',
                r'<nav class="eephus-footer-links"[^>]*>(.*?)</nav>',
                r'<footer class="eephus-footer">(.*?)</footer>',
                r'<nav class="sb-nav">(.*?)</nav>',
                r'<div class="section-head[^"]*">(.*?)</div>'):
        for block in re.findall(pat, text, re.S):
            assert ">Glossary<" not in block and "Glossary &amp;" not in block, (rel, pat)
    # every link to the module carries the display name, never the old one
    for label in re.findall(r'<a [^>]*href="/glossary/"[^>]*>(?:<span[^>]*>)?(?:<svg.*?</svg>)?(?:</span>)?([^<]*)</a>', text, re.S):
        assert "Glossary" not in label, (rel, label)
    assert "#i-glossary" not in text, rel


def test_glossary_page_masthead_title_and_meta_read_library():
    out = B.build_glossary()
    assert "<title>Library - eephus.io</title>" in out
    h1 = re.search(r"<h1>(.*?)</h1>", out, re.S).group(1)
    assert h1.endswith("Library") and "#i-library" in h1
    desc = re.search(r'<meta name="description" content="([^"]*)"', out).group(1)
    assert desc.startswith("The eephus.io Library:")
    # the page-index view keeps its key and URL; its chip no longer repeats the module name
    assert '<button class="chip" data-glossary-view="library">Page Index</button>' in out
    assert _src("glossary/index.html").count("<title>Library - eephus.io</title>") == 1


def test_rail_footer_and_404_read_library():
    home = B.build_home([], {})
    rail = re.search(r'<nav class="sb-nav">(.*?)</nav>', home, re.S).group(1)
    assert re.search(r'href="/glossary/"[^>]*>.*?</span>Library</a>', rail, re.S)
    assert '<a href="/glossary/">Library</a>' in B._footer()
    assert '<a href="/glossary/">Library</a>' in B.build_404()


def test_library_redirect_stub():
    rel = "library/index.html"
    text = _src(rel)
    assert text.replace("\r\n", "\n") == B.build_library_redirect()
    assert '<meta name="robots" content="noindex">' in text
    assert '<meta http-equiv="refresh" content="0; url=/glossary/">' in text
    assert '<link rel="canonical" href="https://eephus.io/glossary/">' in text
    assert '<a href="/glossary/">/glossary/</a>' in text
    assert 'location.replace("/glossary/"+(location.hash||""))' in text
    assert '_write("library/index.html", build_library_redirect())' in _src("build_site.py")
    publish = _src("deploy/publish_paths.txt").split()
    assert "library" in publish and "glossary" in publish
    assert "/library/" not in B.build_sitemap([]), "a noindex stub stays out of the sitemap"


def test_library_icon_is_drawn_and_glossary_is_only_its_alias():
    assert B.ICON_FOR["glossary"] == "library"
    table = json.loads(_src("assets/eephus-icons.json"))
    lib = table["library"]
    assert lib["label"] == "Library" and lib["group"] == "nav" and "rows" in lib
    assert table["glossary"] == {"label": "Library", "group": "nav", "alias": "library"}
    sprite = _src("assets/eephus-icons.svg")
    assert '<symbol id="i-library"' in sprite
    assert re.search(r'<symbol id="i-glossary"[^>]*><use href="#i-library"/></symbol>', sprite)
    rows = lib["rows"]
    lit = "".join(rows)
    assert set(lit) <= set("#+.") and "+" in lit and "#" in lit, "ink plus one accent group"
    # an open book: symmetric about the centre spine, 2 px stems at both page edges
    assert all(r == r[::-1] for r in rows)
    body = [r for r in rows if r.strip(".")]
    assert all(r[0:2] == "##" and r[-2:] == "##" for r in body[1:])
    for size in B.ICON_SIZES:
        assert "#i-library" in B._ico("glossary", size)
