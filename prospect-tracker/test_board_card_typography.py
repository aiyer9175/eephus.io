# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Typography regression tests for the MLB board cards and the font stacks.

Two defects are pinned here, both found 2026-08-05.

1. THE NAME CLIP (owner-reported: every player name on /projections/ rendered
   with its top sliced off). `.mlb-name` carries `overflow: hidden` for its
   ellipsis, which makes it a grid item whose automatic minimum size is 0, so it
   can be compressed BELOW its own line box without any visible overflow
   anywhere else on the card. It was measured at a 17.66px box around a 22px
   line box: a silent 4px clip, identical in both themes at DPR 1.0 and 1.25.
   The guard is deliberately `scrollHeight <= clientHeight` on the name itself
   rather than a pixel assertion on the card, because the failure mode is the
   element clipping its OWN content - a card-height assertion would keep passing
   while a future font-metric or chip change re-ate the text.

2. THE MIRRORED FONT TOKENS. `--font-retro` / `--font-retro-mono` are defined
   twice on purpose (assets/site.css and prospx/index.html's own :root, which
   wins the cascade inside the PROSPX app). If only one copy gains a family,
   Apple renders PROSPX and the editorial pages in two different faces. Both
   files' comments say "mirrors the other"; this asserts it.

Playwright/chromium are OPTIONAL; the browser tests skip cleanly when
unavailable (mirrors test_index_html_loads.py). The stack tests are pure text
and always run."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).parent
SITE_CSS = ROOT / "assets" / "site.css"
PROSPX = ROOT / "prospx" / "index.html"

# The two faces that must lead every copy stack, in order: Windows first (so a
# Windows reader never downloads a webfont), then the self-hosted stand-in.
_EXPECTED_HEAD = ["MS UI Gothic", "MS Gothic", "PixelMplus12"]


def _token(text: str, name: str) -> str:
    """Return the raw value of a CSS custom property (may span lines)."""
    m = re.search(re.escape(name) + r"\s*:\s*(.*?);", text, re.S)
    assert m, f"{name} not found"
    return " ".join(m.group(1).split())


def _families(value: str) -> list[str]:
    return [f.strip().strip('"\'') for f in value.split(",")]


# ---------------------------------------------------------------- font stacks

def test_font_face_files_exist():
    """A @font-face src that 404s degrades silently to the next family, which is
    exactly the bug this face was added to fix."""
    css = SITE_CSS.read_text(encoding="utf-8")
    for url in re.findall(r'url\("(/assets/fonts/[^"]+)"\)', css):
        assert (ROOT / url.lstrip("/")).is_file(), f"@font-face src missing: {url}"


def test_pixelmplus_declared_with_both_weights():
    """`font-synthesis: none` is set on body, so a face without a real 700 makes
    every bold on the site render regular for anyone off Windows."""
    css = SITE_CSS.read_text(encoding="utf-8")
    blocks = re.findall(r"@font-face\s*\{[^}]*\}", css, re.S)
    pixel = [b for b in blocks if "PixelMplus12" in b]
    weights = {re.search(r"font-weight:\s*(\d+)", b).group(1) for b in pixel}
    assert weights == {"400", "700"}, f"expected 400+700, got {weights or 'none'}"


@pytest.mark.parametrize("token", ["--font-retro", "--font-retro-mono"])
def test_copy_stacks_lead_with_windows_then_the_selfhosted_face(token):
    css = _families(_token(SITE_CSS.read_text(encoding="utf-8"), token))
    head = css[: len(_EXPECTED_HEAD)]
    if token == "--font-retro-mono":
        # the mono token leads MS Gothic before MS UI Gothic
        assert head[0] == "MS Gothic" and head[1] == "MS UI Gothic"
    else:
        assert head[0] == "MS UI Gothic" and head[1] == "MS Gothic"
    assert head[2] == "PixelMplus12", f"{token} must fall to PixelMplus12, got {head}"
    assert "monospace" in css[-1], "the monospace ladder must remain as last resort"


@pytest.mark.parametrize("token", ["--font-retro", "--font-retro-mono"])
def test_prospx_token_mirrors_site_css(token):
    """PROSPX's own :root wins inside the app, so a one-sided edit splits the
    site's type identity in half without any test failing elsewhere."""
    a = _families(_token(SITE_CSS.read_text(encoding="utf-8"), token))
    b = _families(_token(PROSPX.read_text(encoding="utf-8"), token))
    assert a == b, f"{token} drifted:\n  site.css: {a}\n  prospx:   {b}"


# ------------------------------------------------------------- the name clip

@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


@pytest.mark.parametrize("route,card", [
    ("projections/", ".proj-card"),
    ("fa/", ".fa-card"),
])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_board_card_names_are_not_self_clipped(server, route, card, theme):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1226, "height": 900})
            page.add_init_script(
                "localStorage.setItem('prospect-tracker.theme', %r)" % theme)
            page.goto(server + route, wait_until="networkidle", timeout=60_000)
            page.wait_for_selector(card, timeout=30_000)
            page.wait_for_timeout(1200)
            clipped = page.evaluate(
                """(sel) => [...document.querySelectorAll(sel)].slice(0, 25)
                     .map(c => c.querySelector('.mlb-name'))
                     .filter(Boolean)
                     .map(n => ({t: (n.textContent || '').trim().slice(0, 24),
                                 clip: n.scrollHeight - n.clientHeight}))
                     .filter(x => x.clip > 0)""",
                card,
            )
            assert not clipped, (
                f"{route} ({theme}): {len(clipped)} name(s) clip their own line box "
                f"- the identity block does not fit row 1. First: {clipped[:3]}"
            )
        finally:
            browser.close()
