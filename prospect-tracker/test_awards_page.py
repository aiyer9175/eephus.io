# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /awards/ assets (AWARDS_7_PAGE_SELECTIONS; AWARDS_PLAN 5.12 'Theme and the pixel
idiom', 5.14 'Motion and budgets' and 6 'Invariants and tests' row I15).

Budgets: assets/awards.js at most 60 KB raw and assets/awards.css at most 12 KB. No
@keyframes in awards.css and no requestAnimationFrame in awards.js (the page adds no motion;
the loading lamp is EephusState's). awards.css types no hex and holds no theme media query.
The two Awards symbols are drawn in the sprite and mapped in ICON_FOR. The client reads the
payload's own fields for every number and label it prints, never a typed WAR unit. No test
opens a socket or a browser; the page against the payload is tools/awards_render_check.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import build_site as B

ROOT = Path(__file__).resolve().parent
JS = ROOT / "assets" / "awards.js"
CSS = ROOT / "assets" / "awards.css"
HEX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{1,5})?\b")


def _js() -> str:
    return JS.read_text(encoding="utf-8")


def _css() -> str:
    return CSS.read_text(encoding="utf-8")


def test_budgets():
    assert JS.stat().st_size <= 60 * 1024, JS.stat().st_size
    assert CSS.stat().st_size <= 12 * 1024, CSS.stat().st_size


def test_no_new_motion():
    assert "@keyframes" not in _css()
    assert not re.search(r"\banimation(-[a-z]+)?\s*:", _css())
    assert "requestAnimationFrame" not in _js()


def test_css_is_tokens_only():
    css = _css()
    assert not HEX.findall(css), HEX.findall(css)
    assert "prefers-color-scheme" not in css
    assert "@media (prefers" not in css
    for prop in re.findall(r"(?:^|[;{\s])(?:color|fill|stroke|background(?:-color)?)\s*:\s*([^;}]+)", css):
        v = prop.strip()
        assert v.startswith(("var(", "none", "inherit", "transparent", "color-mix(in srgb, currentColor")), v


def test_js_types_no_colour_and_reuses_the_shared_pieces():
    js = _js()
    assert not HEX.findall(js), HEX.findall(js)
    assert "rgb(" not in js and "hsl(" not in js
    assert "EephusState" in js and "EephusTiers" in js
    assert "EephusUI.wireTablist" in js, "the shared tablist handler (QCLA19) is reused"
    for kind in ("loading", "failed", "unmeasured"):
        assert f'stateBox("{kind}"' in js


def test_the_state_sentences_are_the_plans():
    js = _js()
    for s in ("Loading the awards.", "The awards could not load.", "This section is being built.",
              "Weekly standings are not on file for ", ". The card shows the season-end order only.",
              "numbers may be out of date."):
        assert s in js, s


def test_no_share_control_until_awards_10():
    js = _js()
    assert "Share" not in js and "eephus-gfx" not in js


def test_no_war_unit_is_typed_in_the_client():
    js = _js()
    for unit in ("eWAR v2", "eWAR v3", "fWAR"):
        assert unit not in js, unit
    assert "rule.unit" in js and "dr.unit_label" in js


def test_the_awards_symbols_are_drawn_and_mapped():
    keys = set(json.loads((ROOT / "assets" / "eephus-icons.json").read_text(encoding="utf-8")))
    svg = (ROOT / "assets" / "eephus-icons.svg").read_text(encoding="utf-8")
    for k in ("aw-podium", "aw-ballot"):
        assert k in keys and B.ICON_FOR[k] == k and k in B.ICON_KEYS
        assert f'<symbol id="i-{k}"' in svg
    assert B.ICON_FOR["hof"] == "hof", "the leaf icon stays i-hof"
    assert "#i-aw-ballot" not in _js() and 'ico("aw-ballot", 12)' in _js()
    assert 'ico("aw-podium", 16)' in _js()


def test_lamp_geometry_is_the_plans():
    js = _js()
    assert "s: { w: 4, h: 10, p: 5 }, l: { w: 6, h: 12, p: 8 }" in js
    assert "MAX_LAMPS = 60" in js
    assert "p === 1 ? 12 : p === 2 ? 8 : 4" in js
    assert 'shape-rendering="crispEdges"' in js
    assert 'preserveAspectRatio="none"' not in js
