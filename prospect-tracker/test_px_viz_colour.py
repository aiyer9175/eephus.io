# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The pixel visualizations are coloured through theme tokens (owner ask
2026-10-02, "the pixel visualizations arent colored in on the site").

One pin per piece that its fills resolve to the named colour tokens and not
to the text-ink tokens, and one contrast pin per piece in both themes, held
to the 3:1 floor for graphic objects (WCAG 1.4.11) on every surface the
piece can sit on:

  PX-14 tied-game lamps   top halves --accent-cyan, bottom halves --accent-lilac
                          (were --text-dim / --text-primary), no red or green
  PX-16 step sparkline    .px-spark.up / .dn paint --accent-green / --accent-red
                          from the sheet; the ln path carries no fill attribute
                          for a direction colour (the var() in a presentation
                          attribute was the only route to colour)
  PX-17 wire pictograms   each type's own colour on the theme-fixed panel;
                          trade in the panel's ink (owner answer PX-Q3)
  PX-19 ruler key         the seven --vt-* steps
  PX-24 card-foil sprite  the --accent-lilac accent group
"""
from __future__ import annotations

import re
from pathlib import Path

import build_site as B

ROOT = Path(__file__).parent
CSS = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
SURFACES = ("--bg-primary", "--bg-secondary", "--bg-tertiary")
FLOOR = 3.0
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_HEX = re.compile(r"(--[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})\b")
_ALIAS = re.compile(r"(--[a-z0-9-]+)\s*:\s*var\(\s*(--[a-z0-9-]+)\s*\)")
_CSS = _COMMENT.sub("", CSS)


def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    x, y = _lum(a), _lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def _block(opener):
    i = _CSS.index(opener)
    j = _CSS.index("{", i)
    depth, k = 0, j
    while True:
        if _CSS[k] == "{":
            depth += 1
        elif _CSS[k] == "}":
            depth -= 1
            if depth == 0:
                return _CSS[j + 1:k]
        k += 1


def _tokens(body, base=None):
    out = dict(base or {})
    out.update({k: v.upper() for k, v in _HEX.findall(body)})
    for _ in range(3):  # alias chains (--vt-above: var(--accent-green))
        for k, ref in _ALIAS.findall(body):
            if ref in out:
                out[k] = out[ref]
    return out


def _themes():
    light = _tokens(_block(":root {"))
    dark = _tokens(_block('[data-theme="dark"] {'), light)
    dark = _tokens(_block('[data-theme="dark"] {'), dark)
    return {"light": light, "dark": dark}


THEMES = _themes()


def _rule(selector):
    """The declarations of the rule whose selector list is exactly `selector`."""
    m = re.search(r"(?:^|[}\n])\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", _CSS)
    assert m, selector
    return m.group(1)


def _fill_token(selector, prop="fill"):
    m = re.search(prop + r"\s*:\s*var\((--[a-z0-9-]+)\)", _rule(selector))
    assert m, (selector, _rule(selector))
    return m.group(1)


def _low(tokens, surfaces=SURFACES):
    bad = []
    for theme, tok in THEMES.items():
        for t in tokens:
            for s in surfaces:
                r = _ratio(tok[t], tok[s])
                if r < FLOOR:
                    bad.append("%s %s %s on %s %s = %.2f" % (theme, t, tok[t], s, tok[s], r))
    return bad


# ---- PX-14 tied-game lamps --------------------------------------------------
LAMP = {".px-lamp .lt": "--accent-cyan", ".px-lamp .lb": "--accent-lilac"}
KEY = {".px-lamp-key .px-lk.t": "--accent-cyan", ".px-lamp-key .px-lk.b": "--accent-lilac"}


def test_lamp_fills_resolve_to_colour_tokens_not_ink():
    for sel, want in LAMP.items():
        got = _fill_token(sel)
        assert got == want, (sel, got)
        assert not got.startswith("--text-"), sel
    for sel, want in KEY.items():
        assert _fill_token(sel, "background") == want, sel
    # no half reads as a verdict
    for sel in list(LAMP) + list(KEY):
        assert "accent-red" not in _rule(sel) and "accent-green" not in _rule(sel)


def test_lamp_contrast_both_themes():
    assert not _low(LAMP.values()), _low(LAMP.values())
    # the two halves differ from each other, not only from the board
    for theme, tok in THEMES.items():
        assert tok["--accent-cyan"] != tok["--accent-lilac"], theme


# ---- PX-16 step sparkline -------------------------------------------------
PTS = [{"consensus_fv_raw": v} for v in (45, 47.5, 50, 50, 55)]


def test_spark_direction_class_paints_from_the_sheet():
    assert _fill_token(".px-spark.up .ln") == "--accent-green"
    assert _fill_token(".px-spark.dn .ln") == "--accent-red"
    assert _fill_token(".px-spark .gl") == "--border"
    for colour, cls in (("var(--accent-green)", "up"), ("var(--accent-red)", "dn")):
        svg = B._fv_sparkline(PTS, colour, w=56, h=20)
        assert svg.startswith(f'<svg class="px-spark {cls}" '), svg[:60]
        assert '<path class="ln" d="' in svg and "fill=" not in svg
    # an off-token colour keeps an explicit fill, so it is never left black
    other = B._fv_sparkline(PTS, "var(--accent-lilac)", w=56, h=20)
    assert other.startswith('<svg class="px-spark" ')
    assert '<path class="ln" fill="var(--accent-lilac)" d="' in other


def test_served_homepage_sparks_carry_a_direction_class():
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    sparks = re.findall(r'<svg class="(px-spark[^"]*)"', page)
    assert sparks, "no step sparkline on the homepage"
    assert all(s in ("px-spark up", "px-spark dn") for s in sparks), sparks
    # the monochrome fallback route (a var() fill attribute on the line) is gone
    assert not re.search(r'<path class="ln" fill="var\(', page)


def test_spark_contrast_both_themes():
    toks = ("--accent-green", "--accent-red")
    assert not _low(toks), _low(toks)


# ---- PX-17 wire pictograms ----------------------------------------------------
WIRE_PANELS = {"feed": "#0B0E07", "feed dark": "#0A0C06", "ticker": "#0B0E07"}


def _root_token(name):
    m = re.search(r":root\s*\{[^}]*?%s:\s*(#[0-9A-Fa-f]{6})\s*;" % re.escape(name), _CSS)
    assert m, name
    return m.group(1).upper()


def test_wire_families_are_coloured_on_the_panel():
    """HOME_2: colour names the family, not the event type. Each family's panel
    token clears the floor on the ticker and feed panels, and the pictogram,
    an <svg> with no fill of its own, takes the row's family colour."""
    fams = {r["fam"] for r in B._WIRE_TYPES.values()}
    assert fams == set(B._WIRE_FAMILIES) == {"pro", "mlb", "fa", "trd", "inj"}
    for fam in fams:
        ink = _root_token(f"--wire-{fam}-panel")
        for name, bg in WIRE_PANELS.items():
            assert _ratio(ink, bg) >= FLOOR, (fam, name, round(_ratio(ink, bg), 2))
    assert re.search(r"\[data-fam\] > \.wire-ico, \[data-fam\] \.feed-val, \[data-fam\] \.wire-val\s*"
                     r"\{\s*color:\s*var\(--wire-c\);\s*\}", _CSS)
    item = B._wire_glyph("promo", "")
    assert item.startswith('<svg class="ico"') and "fill" not in item


def test_wire_panel_ink_contrast():
    assert _ratio("#E6FBEF", "#0B0E07") >= FLOOR


# ---- PX-19 ruler key, PX-24 card-foil sprite --------------------------------
VT = ("--vt-elite", "--vt-great", "--vt-good", "--vt-above", "--vt-avg", "--vt-below", "--vt-poor")


def test_ruler_meter_lit_cells_take_the_step_colour():
    assert _fill_token(".vt-meter .off") == "--border"
    assert re.search(r"fill\s*:\s*currentColor", _rule(".vt-meter .on"))
    assert not _low(VT), _low(VT)


def test_card_foil_accent_contrast_both_themes():
    assert "--ico-accent: var(--accent-lilac)" in _rule(".cf-badge")
    assert not _low(("--accent-lilac",)), _low(("--accent-lilac",))
