# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""T3 (final-pass plan 5.7.4): pixel icons render at 12, 16, 24 or 32 px only.

One drawing, three sizes (plan 5.7.1 line 2): 12 px is the 12 x 12 core
(viewBox "2 2 12 12"), 16 px the full 16 x 16 box, 24 px the core at 2x and
32 px the box at 2x. Any other size, or an em size that follows the font,
resamples the pixels and the set goes soft; 18 px and em sizes are banned.
This pins the helper (build_site._ico), every icon tag in a served page or
module script, and every CSS rule that targets .ico.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import build_site

ROOT = Path(__file__).parent
SIZES = {12, 16, 24, 32}
CORE_VIEWBOX = "2 2 12 12"
BOX_VIEWBOX = "0 0 16 16"
_ICO_SEL = re.compile(r"\.ico(?![\w-])")
_SVG_ICO = re.compile(r"<svg\b[^>]*\bclass=\"(?:[^\"]*\s)?ico(?:\s[^\"]*)?\"[^>]*>", re.I)
_ATTR = re.compile(r'\b(width|height|viewBox)="([^"]*)"')


def _attrs(tag: str) -> dict:
    return dict(_ATTR.findall(tag))


def _check_tag(tag: str) -> str | None:
    a = _attrs(tag)
    w, h, vb = a.get("width"), a.get("height"), a.get("viewBox")
    if w is None or h is None or w != h or not w.isdigit() or int(w) not in SIZES:
        return f"size {w}x{h}"
    want = CORE_VIEWBOX if int(w) in (12, 24) else BOX_VIEWBOX
    if vb != want:
        return f"{w} px with viewBox {vb!r}, want {want!r}"
    return None


# --------------------------------------------------------------- the helper

@pytest.mark.parametrize("size", sorted(SIZES))
def test_helper_emits_only_the_four_sizes(size):
    tag = _SVG_ICO.search(build_site._ico("ledger", size)).group(0)
    assert _check_tag(tag) is None, tag
    assert 'aria-hidden="true"' in tag


@pytest.mark.parametrize("size", [8, 10, 14, 18, 20, 28, 48])
def test_helper_refuses_any_other_size(size):
    with pytest.raises(ValueError):
        build_site._ico("ledger", size)


def test_helper_refuses_a_key_with_no_drawing():
    with pytest.raises(ValueError):
        build_site._ico("no-such-icon", 16)


def test_core_sizes_crop_and_box_sizes_do_not():
    for size in (12, 24):
        out = build_site._ico("ledger", size)
        assert f'viewBox="{CORE_VIEWBOX}"' in out and 'width="16" height="16"/>' in out
    for size in (16, 32):
        out = build_site._ico("ledger", size)
        assert f'viewBox="{BOX_VIEWBOX}"' in out


def test_every_literal_helper_call_uses_an_allowed_size():
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    bad = [m.group(0) for m in re.finditer(r"\b_ico\(\s*[^()]*?,\s*(\d+)\s*\)", src)
           if int(m.group(1)) not in SIZES]
    assert not bad, bad


# --------------------------------------------------- tags in served markup

def _served_sources() -> list[Path]:
    files = [ROOT / "index.html", ROOT / "404.html"]
    files += [p for p in ROOT.glob("*/index.html") if p.parts[-2] not in ("data", "vendor")]
    files += [p for p in ROOT.glob("*/*/index.html") if p.parts[-3] not in ("data", "vendor")]
    files += [ROOT / "collegesavant" / "pitcher_index.html"] + sorted(ROOT.glob("assets/*.js"))
    return [p for p in files if p.is_file()]


def test_every_icon_tag_in_served_markup_is_a_pixel_size():
    bad = []
    for p in _served_sources():
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in _SVG_ICO.finditer(text):
            tag = m.group(0)
            if "{" in tag:
                continue  # a template literal sized at runtime; pinned by its own module test
            why = _check_tag(tag)
            if why:
                bad.append(f"{p.relative_to(ROOT).as_posix()}: {why}: {tag[:120]}")
    assert not bad, "\n  ".join(bad)


# ------------------------------------------------------------- CSS rules

def _rules(css: str) -> list[tuple[str, str]]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(sel.strip(), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def _css_sources() -> dict[str, str]:
    prospx = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    style = re.search(r"<style>(.*?)</style>", prospx, re.S).group(1)
    return {"assets/site.css": (ROOT / "assets" / "site.css").read_text(encoding="utf-8"),
            "prospx <style>": style}


@pytest.mark.parametrize("name", ["assets/site.css", "prospx <style>"])
def test_ico_css_rules_never_size_by_em_or_off_grid(name):
    css = _css_sources()[name]
    rules = [(s, b) for s, b in _rules(css) if _ICO_SEL.search(s)]
    assert rules, f"{name}: no .ico rule found (PX-03 mirrors it in both places)"
    bad = []
    for sel, body in rules:
        for prop, val in re.findall(r"(?:^|;)\s*([\w-]+)\s*:\s*([^;]+)", body):
            prop, val = prop.lower(), val.strip().lower()
            if prop in ("width", "height", "min-width", "min-height", "max-width", "max-height",
                        "inline-size", "block-size", "font-size"):
                if re.search(r"\d(?:r?em|ex|ch|vw|vh|%)\b", val):
                    bad.append(f"{sel} {{{prop}: {val}}}")
                for px in re.findall(r"(\d+(?:\.\d+)?)px", val):
                    if prop != "font-size" and float(px) not in SIZES:
                        bad.append(f"{sel} {{{prop}: {val}}}")
    assert not bad, f"{name}:\n  " + "\n  ".join(bad)


def test_base_ico_rule_is_mirrored_in_prospx():
    want = "display:inline-block;flex:none;vertical-align:top;fill:currentColor;shape-rendering:crispEdges"
    for name, css in _css_sources().items():
        bodies = [re.sub(r"\s+", "", b).rstrip(";") for s, b in _rules(css) if s == ".ico"]
        assert want in bodies, f"{name}: the base .ico rule is missing or differs"


# ------------------------------------------------- no monogram below 40 px

def test_no_monogram_call_below_40px():
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    small = []
    for m in re.finditer(r"\bprospx_ball_logo\(\s*([^()]*)\)", src):
        args = [a.strip() for a in m.group(1).split(",")]
        if args and args[0].startswith(("uid:", "uid :")):
            continue  # the def line
        px = int(args[1]) if len(args) > 1 and args[1].isdigit() else 16
        if px < 40:
            small.append(m.group(0))
    assert not small, small
