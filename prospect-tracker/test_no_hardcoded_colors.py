# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Regression guard against hardcoded color drift.

Phase 1 of the UI restructure migrated 5 known offenders that hardcoded
`#fff` / `rgba(251, 248, 240, 0.78)` (paper-cream) onto theme-aware
tokens (`--text-on-accent`, `--text-on-dark-muted`). These tests block
new code from re-introducing the same patterns inside CSS rules.

Allowlist: inline `style=""` attributes inside JS template literals can
still hardcode colors when the value is computed (FV-tier tints, org
team-colors) — those are already theme-aware via JS palette lookups.
The guards focus on STATIC CSS rules inside the `<style>` block.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

INDEX = Path(__file__).parent / "prospx" / "index.html"


@pytest.fixture(scope="module")
def style_block() -> str:
    """Returns just the contents of the first <style>...</style> block —
    the global stylesheet. JS-template inline styles live below this in
    <script> blocks and aren't checked here."""
    text = INDEX.read_text(encoding="utf-8")
    m = re.search(r"<style>(.*?)</style>", text, re.DOTALL)
    assert m, "no <style> block found in index.html"
    return m.group(1)


# ---------------------------------------------------------------------------
# `#fff` / `#FFF` / `color: white` in static CSS — these always break
# the cross-theme contract. Use --text-on-accent / --text-on-dark-muted.
# ---------------------------------------------------------------------------

def test_no_color_white_hex(style_block):
    pattern = re.compile(r"\bcolor:\s*#fff\b", re.IGNORECASE)
    matches = pattern.findall(style_block)
    assert len(matches) == 0, (
        f"found {len(matches)} `color: #fff` declarations in <style>. "
        "Use var(--text-on-accent) [text over neon accents] or "
        "var(--text-on-dark-muted) [text over the dark header band]."
    )


def test_no_color_white_named(style_block):
    pattern = re.compile(r"\bcolor:\s*white\b", re.IGNORECASE)
    matches = pattern.findall(style_block)
    assert len(matches) == 0, (
        f"found {len(matches)} `color: white` declarations. Replace "
        "with var(--text-on-accent) or var(--text-on-dark-muted)."
    )


# ---------------------------------------------------------------------------
# Hardcoded paper-cream `rgba(251, 248, 240, ...)` in static CSS
# ---------------------------------------------------------------------------

def test_no_hardcoded_paper_cream_rgba(style_block):
    # 4 instances of `color: rgba(251, 248, 240, 0.78)` were migrated to
    # var(--text-on-dark-muted) in Phase 1. New code shouldn't reintro.
    pattern = re.compile(r"\bcolor:\s*rgba\(\s*251\s*,\s*248\s*,\s*240")
    matches = pattern.findall(style_block)
    assert len(matches) == 0, (
        f"found {len(matches)} hardcoded paper-cream rgba() declarations. "
        "Use var(--text-on-dark-muted) — it carries the right alpha and "
        "doesn't fight the theme system."
    )


# ---------------------------------------------------------------------------
# Loose cap — total hardcoded-hex `color:` declarations in <style>
# ---------------------------------------------------------------------------

def test_hardcoded_hex_color_count_bounded(style_block):
    # FV tier badges, level pills, and a few signature accents legitimately
    # use hardcoded hex values inside the :root token block (`--fv-80-bg:
    # #FFE08A`). Outside of token DEFINITIONS, hex usage in `color:` /
    # `background:` should be rare — every theme-aware case has a token.
    # Strip token-definition lines first, then count.
    no_tokens = re.sub(r"^\s*--[\w-]+\s*:\s*[^;]+;", "",
                       style_block, flags=re.MULTILINE)
    # Count `color: #XXX[XXX]` outside token defs.
    pattern = re.compile(
        r"\bcolor:\s*#[0-9a-fA-F]{3,8}\b"
    )
    matches = pattern.findall(no_tokens)
    # Post-Phase-1 floor. Bring under 5 in Phase 2; new code should
    # use tokens.
    assert len(matches) <= 30, (
        f"found {len(matches)} hardcoded hex `color:` outside token "
        f"definitions — Phase 1 caps this at 30. Examples: {matches[:5]}"
    )


# ---------------------------------------------------------------------------
# T4 (final-pass plan 5.7.4), extended for PX-14 to PX-19 and PX-24: the pixel
# visualization, key-strip and card-foil sprite rules in assets/site.css paint
# through tokens only (no hex, no rgb, no gradient), so both themes resolve
# them; the PROSPX <style> budget above is untouched by them.
# ---------------------------------------------------------------------------

_PX_VIZ_SEL = re.compile(r"\.(?:px-spark|px-lamp|px-lamp-wrap|px-lamp-key|px-lk|vt-key|vt-meter|px-fvkey|cf-badge)(?![\w-])")


def test_pixel_viz_and_key_rules_use_tokens_only():
    css = (Path(__file__).parent / "assets" / "site.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rules = [(sel.strip(), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
             if _PX_VIZ_SEL.search(sel)]
    assert len(rules) >= 15, "the PX viz / key rules moved out of assets/site.css"
    bad = [f"{sel} {{{body.strip()}}}" for sel, body in rules
           if re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|gradient\(", body)]
    assert not bad, bad


def test_px_viz_rules_live_outside_the_prospx_style(style_block):
    assert not _PX_VIZ_SEL.search(style_block)


# ---------------------------------------------------------------------------
# I15 (AWARDS_PLAN 6, AWARDS_7, AWARDS_9): the /awards/ stylesheets and clients type no
# colour; every paint is a site.css token, so both themes resolve them.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel", ["assets/awards.css", "assets/awards.js",
                                 "assets/awards-ballot.css", "assets/awards-ballot.js"])
def test_awards_assets_type_no_colour(rel):
    text = (Path(__file__).parent / rel).read_text(encoding="utf-8")
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", text)
    assert not re.search(r"\brgba?\(|\bhsla?\(|gradient\(", text)


def test_the_awards_gfx_painter_reads_tokens_only():
    """AWARDS_10: the kind:"awards" painter in eephus-gfx.js types no colour; every paint
    is palette() or tok() of a site.css token (AWARDS_PLAN 5.16)."""
    text = (Path(__file__).parent / "assets" / "eephus-gfx.js").read_text(encoding="utf-8")
    block = text[text.index("// ---- canvas awards renderer"):text.index("// ---- render dispatch")]
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", block)
    assert not re.search(r"\brgba?\(|\bhsla?\(", block)
    assert 'tok("--up", P.pos)' in block and 'tok("--down", P.neg)' in block
    assert 'tok("--bg-header", fg)' in block and 'tok("--text-on-accent", P.bg)' in block
