# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Guards for the Phase 1 design-system tokens.

The UI restructure landed a 6-step spacing scale, 7-step type scale, and
a small set of interaction tokens (`--text-on-accent`, `--text-on-dark`,
`--bg-hover`, `--transition-hover`). These tests assert the tokens
exist in the `<style>` block + catch regressions where new code
re-introduces fractional font-sizes (the old `9.5/10.5/11.5/12.5px`
chaos) by checking the count stays bounded.

Run after any large CSS edit to confirm the foundation didn't drift.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

INDEX = Path(__file__).parent / "prospx" / "index.html"
SITE_CSS = Path(__file__).parent / "assets" / "site.css"


@pytest.fixture(scope="module")
def html_text() -> str:
    return INDEX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def css_text() -> str:
    return SITE_CSS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Token-existence guards
# ---------------------------------------------------------------------------

REQUIRED_TOKENS = [
    # Spacing scale (P1-A)
    "--space-1", "--space-2", "--space-3",
    "--space-4", "--space-5", "--space-6",
    # Type scale (P1-B)
    "--fs-xs", "--fs-sm", "--fs-base", "--fs-md",
    "--fs-lg", "--fs-xl", "--fs-xxl",
    # Interaction + theme-aware text tokens (P1-C, P1-D)
    "--text-on-accent",
    "--bg-hover",
    "--transition-hover",
]


@pytest.mark.parametrize("token", REQUIRED_TOKENS)
def test_token_defined(html_text, token):
    # Each token must be declared in :root (or a theme override). Allow
    # either `--token:` (definition) or `var(--token` (usage); the
    # definition form is what we want at least once.
    pattern = re.compile(rf"{re.escape(token)}\s*:", re.MULTILINE)
    assert pattern.search(html_text), (
        f"design token {token} is not defined in <style>. "
        "Check the :root block in index.html."
    )


# ---------------------------------------------------------------------------
# Dark-theme overrides for theme-aware tokens
# ---------------------------------------------------------------------------

def test_dark_theme_overrides_text_on_accent(html_text):
    # `--text-on-accent` flips per theme: cream in light, near-black in
    # dark. Find the [data-theme="dark"] block and confirm the override.
    dark_block = re.search(
        r'\[data-theme="dark"\]\s*\{([^}]+)\}', html_text, re.DOTALL
    )
    assert dark_block, "missing [data-theme=\"dark\"] block"
    assert "--text-on-accent" in dark_block.group(1), (
        "[data-theme=\"dark\"] must override --text-on-accent (light "
        "accents in dark mode need dark text on top)."
    )


def test_dark_theme_overrides_bg_hover(html_text):
    dark_block = re.search(
        r'\[data-theme="dark"\]\s*\{([^}]+)\}', html_text, re.DOTALL
    )
    assert dark_block
    assert "--bg-hover" in dark_block.group(1), (
        "[data-theme=\"dark\"] must override --bg-hover (lift over dark "
        "surface vs darken over light)."
    )


# ---------------------------------------------------------------------------
# No new fractional font-sizes — the old 9.5/10.5/11.5/12.5 chaos
# ---------------------------------------------------------------------------

def test_fractional_font_sizes_bounded(html_text):
    # The legacy file shipped ~15 fractional sizes (8.5, 9.5, 10.5, 11.5,
    # 12.5) and the count crept to 73 across UI iterations. The 2026-06-12
    # cleanup snapped ALL of them: 10.5/11.5/12.5 -> var(--fs-xs/sm/base),
    # sub-scale micros (7.5/8.5/9.5) -> 8/9/10px. The cap is now 0: new
    # font-sizes use the 7-step scale (or an integer px for micros the
    # scale doesn't cover). Bumping this UP requires intent.
    fractional_pattern = re.compile(r"font-size:\s*\d+\.\d+px")
    matches = fractional_pattern.findall(html_text)
    assert len(matches) == 0, (
        f"found {len(matches)} fractional font-sizes — the 2026-06-12 "
        f"cleanup brought this to 0. Snap new sizes to var(--fs-*). "
        f"Examples: {matches[:5]}"
    )


def test_no_em_or_rem_for_font_size_in_new_rules(html_text):
    # Mixed-unit font-size scatter (`0.9em`, `1.7rem`) hurts the scale.
    # Phase 1 doesn't fix every existing case (some are inside SVGs);
    # the cap below tracks the floor. New rules should use --fs-*.
    em_rem_pattern = re.compile(r"font-size:\s*\d+(?:\.\d+)?(?:em|rem)\b")
    matches = em_rem_pattern.findall(html_text)
    assert len(matches) <= 20, (
        f"found {len(matches)} font-size with em/rem units — Phase 1 "
        f"caps this at 20. Examples: {matches[:5]}"
    )


# ---------------------------------------------------------------------------
# Sanity — the tokens are actually being USED somewhere
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token", [
    "--text-on-accent",
])
def test_token_is_referenced_somewhere(html_text, token):
    # A defined-but-unused token = dead weight. After Phase 1 each of
    # these should have at least one `var(--token)` callsite that we
    # migrated from the hardcoded color it replaced.
    var_ref = re.compile(rf"var\(\s*{re.escape(token)}\s*[,)]")
    assert var_ref.search(html_text), (
        f"{token} is defined but never referenced via var(); migrate at "
        "least one callsite or remove the token."
    )


# ---------------------------------------------------------------------------
# Shared site.css :root coverage - the cross-surface drift the audit caught.
# The editorial pages, the /projections/ .mlbp player cards, and the homepage
# cross-module strip all reference these tokens off the SHARED site.css, not
# prospx's scoped block. They were missing at site.css :root, so those shipped
# surfaces fell back to UA serif/sans. These guards keep them defined.
# ---------------------------------------------------------------------------

SITE_CSS_REQUIRED_TOKENS = [
    "--font-sans", "--font-serif", "--font-mono",   # the MS-Gothic aliases
    "--space-1", "--space-6",                       # spacing scale endpoints
    "--fs-xs", "--fs-xxl",                           # type scale endpoints
    "--text-on-accent", "--bg-hover",
]


@pytest.mark.parametrize("token", SITE_CSS_REQUIRED_TOKENS)
def test_site_css_token_defined(css_text, token):
    pattern = re.compile(rf"{re.escape(token)}\s*:", re.MULTILINE)
    assert pattern.search(css_text), (
        f"shared design token {token} is not defined in assets/site.css. "
        "Module shells (/projections/, homepage strip, editorial pages) "
        "reference it; without it they fall back to UA defaults."
    )


def test_site_css_dark_overrides_theme_tokens(css_text):
    blocks = re.findall(r'\[data-theme="dark"\]\s*\{([^}]*)\}', css_text, re.DOTALL)
    assert blocks, 'missing a bare [data-theme="dark"] token block in site.css'
    joined = "\n".join(blocks)
    for t in ("--text-on-accent", "--bg-hover"):
        assert t in joined, (
            f'site.css [data-theme="dark"] must override {t} (theme-aware token).'
        )


# BR-02 (owner ask 2): the pixel brand tokens are defined in the light deck
# and overridden in the dark deck, so the stepped arc flips with the theme.
BRAND_TOKENS = (
    [f"--ramp-{i}" for i in range(1, 6)] + [f"--arc-{i}" for i in range(1, 9)]
    + ["--iridescent-steps", "--ball-face"] + [f"--seam-{i}" for i in range(1, 5)]
)


@pytest.mark.parametrize("token", BRAND_TOKENS)
def test_brand_token_defined_in_both_decks(css_text, token):
    light = re.search(r"^:root \{$(.*?)^\}", css_text, re.M | re.S)
    dark = re.search(r'^\[data-theme="dark"\] \{$(.*?)^\}', css_text, re.M | re.S)
    assert light and dark
    pattern = re.compile(rf"^\s*{re.escape(token)}\s*:", re.M)
    assert pattern.search(light.group(1)), f"{token} missing from the site.css :root deck"
    assert pattern.search(dark.group(1)), f"{token} missing from the site.css dark deck"


def test_no_undefined_border_color_token():
    # The token is --border; --border-color was never defined anywhere and left
    # the /projections/ compare button AND the PROSPX Trade Machine cards
    # borderless. Guard the shared CSS, prospx, and the module JS against its
    # return.
    root = Path(__file__).parent
    scanned = [root / "assets" / "site.css", root / "prospx" / "index.html",
               *(root / "assets").glob("*.js")]
    offenders = [str(p.relative_to(root)) for p in scanned
                 if p.is_file() and "var(--border-color)" in p.read_text(encoding="utf-8")]
    assert not offenders, (
        f"use var(--border), not the undefined var(--border-color), in: {offenders}"
    )
