# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Model Accountability verdict badges read 4.5:1 in both themes.

The 2026-10-22 audit gave every badge a fixed near-black ink, which cleared dark
mode (bright refractor fills) but left the light theme's darker fills at 3.0 to
3.7:1 (Unvalidated on --down 3.04, Deprecated on --text-tertiary 3.43, Validated
on --accent-green 3.66; the 2026-10-27 site audit, group A). Each verdict now
names its ink: the three dark-in-light fills take --text-on-accent (cream in
light, near-black in dark) and the gold fill, light in both themes, keeps the
near-black.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
CSS = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")

_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _braced(text: str, j: int) -> str:
    depth, k = 0, j
    while True:
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    return text[j:k]


def _theme_block(theme: str) -> str:
    """The token block of a theme: the first :root rule, or the
    [data-theme="dark"] rule that redeclares --bg-primary."""
    text = _COMMENT.sub("", CSS)
    opener = ":root" if theme == "light" else '[data-theme="dark"]'
    start = 0
    while True:
        i = text.index(opener, start)
        j = text.index("{", i)
        block = _braced(text, j)
        if "--bg-primary" in block:
            return block
        start = j + 1


def _hex(block: str, token: str) -> str:
    m = re.search(re.escape(token) + r":\s*(#[0-9A-Fa-f]{6})", block)
    assert m, token
    return m.group(1)


def _resolve(block: str, token: str, hops: int = 4) -> str:
    """A token's hex, following var() aliases such as --down: var(--accent-red).
    A token the theme block does not redeclare (the dark theme keeps --down)
    is read from the light :root block, as the cascade does."""
    light = _theme_block("light")
    for _ in range(hops):
        m = re.search(re.escape(token) + r":\s*([^;]+);", block) or re.search(re.escape(token) + r":\s*([^;]+);", light)
        assert m, token
        val = m.group(1).strip()
        if val.startswith("#"):
            return val[:7]
        inner = re.match(r"var\((--[a-z0-9-]+)\)", val)
        assert inner, (token, val)
        token = inner.group(1)
    raise AssertionError(token)


def _contrast(a: str, b: str) -> float:
    def lum(h):
        r, g, bl = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(bl)
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _verdict_meta() -> dict:
    block = JS[JS.index("const VERDICT_META = {"):]
    block = block[:block.index("};")]
    out = {}
    for m in re.finditer(r"(\w+):\s*\{\s*label:\s*\"[^\"]+\",\s*col:\s*\"([^\"]+)\",\s*ink:\s*\"([^\"]+)\"", block):
        out[m.group(1)] = {"col": m.group(2), "ink": m.group(3)}
    return out


def _as_hex(block: str, css_value: str) -> str:
    css_value = css_value.strip()
    if css_value.startswith("#"):
        return css_value
    m = re.match(r"var\((--[a-z0-9-]+)(?:,\s*[^)]+)?\)", css_value)
    assert m, css_value
    return _resolve(block, m.group(1))


def test_every_verdict_names_a_fill_and_an_ink():
    meta = _verdict_meta()
    assert set(meta) == {"validated", "provisional", "unvalidated", "deprecated"}
    assert "color:${m.ink};background:${m.col};" in JS


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("verdict", ["validated", "provisional", "unvalidated", "deprecated"])
def test_the_badge_ink_reads_4_5_on_its_fill(theme, verdict):
    block = _theme_block(theme)
    meta = _verdict_meta()[verdict]
    fill = _as_hex(block, meta["col"])
    ink = _as_hex(block, meta["ink"])
    assert _contrast(ink, fill) >= 4.5, (theme, verdict, ink, fill, round(_contrast(ink, fill), 2))


def test_the_dark_in_light_fills_take_the_on_accent_ink_and_gold_keeps_near_black():
    meta = _verdict_meta()
    for v in ("validated", "unvalidated", "deprecated"):
        assert meta[v]["ink"].startswith("var(--text-on-accent"), v
    assert meta["provisional"]["ink"] == "#0b0b0b"
    light, dark = _theme_block("light"), _theme_block("dark")
    assert _hex(light, "--text-on-accent") != _hex(dark, "--text-on-accent")
