# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Every reading-text token clears WCAG AA 4.5:1 on every page surface, in both
themes (census X06-03, 2026-09-25).

site.css said "--text-tertiary ... ~4.7:1 on warm paper (WCAG AA)" and, dark,
"~4.9:1 on near-black (WCAG AA)", and "--accent-orange ... alpha/beta version
chips (warm, AA on paper)". Measured on the three surfaces a label can land on
(--bg-primary, --bg-secondary, --bg-tertiary):

    --text-tertiary light #706B5C   4.68 / 4.88 / 4.27
    --text-tertiary dark  #7C808A   4.94 / 4.39 / 3.96
    --accent-orange light #C2540A   4.04 / 4.22 / 3.69   (the 10px masthead chip)

so the tertiary token failed on card and panel fills in dark, on the panel fill
in light, and the stage chip failed everywhere in light. These tokens carry
filter labels, row counts, hub notes, tile labels and every masthead chip; a
label cannot know which surface it will be painted on, so each token is held
to all three. PROSPX redefines the tokens inline in its own :root, which wins
inside that app, so its blocks are measured separately against its own
surfaces.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
TEXT_TOKENS = ("--text-primary", "--text-secondary", "--text-tertiary", "--text-dim",
               "--text-gold", "--accent-orange")
SURFACES = ("--bg-primary", "--bg-secondary", "--bg-tertiary")
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_HEX = re.compile(r"(--[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})\b")
_ALIAS = re.compile(r"(--[a-z0-9-]+)\s*:\s*var\(\s*(--[a-z0-9-]+)\s*\)")


def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    x, y = _lum(a), _lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def _block(text, opener):
    """The declarations of the first rule whose selector is `opener`."""
    text = _COMMENT.sub("", text)
    i = text.index(opener)
    j = text.index("{", i)
    depth, k = 0, j
    while True:
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return text[j + 1:k]
        k += 1


def _tokens(body, base=None):
    out = dict(base or {})
    out.update({k: v.upper() for k, v in _HEX.findall(body)})
    for k, ref in _ALIAS.findall(body):
        if ref in out:
            out[k] = out[ref]
    return out


def _themes(path, light_open, dark_open):
    text = path.read_text(encoding="utf-8")
    light = _tokens(_block(text, light_open))
    dark = _tokens(_block(text, dark_open), light)
    # an alias in the dark block (--text-gold: var(--accent-gold)) resolves
    # against the dark value of its target
    dark = _tokens(_block(text, dark_open), dark)
    return {"light": light, "dark": dark}


def _failures(themes, tokens):
    bad = []
    for theme, tok in themes.items():
        for t in tokens:
            if t not in tok:
                continue
            for s in SURFACES:
                r = _ratio(tok[t], tok[s])
                if r < 4.5:
                    bad.append("%s %s %s on %s %s = %.2f" % (theme, t, tok[t], s, tok[s], r))
    return bad


def test_site_text_tokens_clear_aa_on_every_surface():
    themes = _themes(ROOT / "assets" / "site.css", ":root {", '[data-theme="dark"] {')
    for theme in themes.values():
        for t in TEXT_TOKENS + SURFACES:
            assert t in theme, t
    assert not _failures(themes, TEXT_TOKENS), _failures(themes, TEXT_TOKENS)


def test_prospx_inline_tokens_clear_aa_on_its_own_surfaces():
    path = ROOT / "prospx" / "index.html"
    if not path.exists():
        pytest.skip("prospx/index.html not on this machine")
    text = path.read_text(encoding="utf-8")
    # PROSPX's :root and dark blocks sit inside its first <style>
    style = text[text.index("<style"):]
    style = style[:style.index("</style>")]
    tmp = _COMMENT.sub("", style)
    themes = {"light": _tokens(_block(tmp, ":root")), "dark": None}
    themes["dark"] = _tokens(_block(tmp, '[data-theme="dark"]'), themes["light"])
    have = [t for t in TEXT_TOKENS if t in themes["light"]]
    assert "--text-tertiary" in have
    assert not _failures(themes, have), _failures(themes, have)


def test_chart_series_tokens_hold_their_validated_values_and_contrast():
    """--viz-1 and --viz-2 are graphics tokens, never text (a chart's labels
    wear --text-secondary or --text-tertiary). Both themes carry the values the
    LTS lane validated on the card surface. The first series clears the 3:1
    floor for graphics in both themes; the light gold second series measures
    2.22:1 on paper, a WARN the end labels and the numbers table relieve, so it
    is pinned by value and held only above 2:1."""
    themes = _themes(ROOT / "assets" / "site.css", ":root {", '[data-theme="dark"] {')
    want = {"light": {"--viz-1": "#1D4ED8", "--viz-2": "#C9A227", "--bg-secondary": "#FAF5E6"},
            "dark": {"--viz-1": "#3B7FCC", "--viz-2": "#B08526", "--bg-secondary": "#1A1A1E"}}
    for theme, tok in want.items():
        for k, v in tok.items():
            assert themes[theme][k] == v, (theme, k, themes[theme].get(k))
        assert _ratio(tok["--viz-1"], tok["--bg-secondary"]) >= 3.0, theme
        assert _ratio(tok["--viz-2"], tok["--bg-secondary"]) >= 2.0, theme
    assert round(_ratio("#1D4ED8", "#FAF5E6"), 2) == 6.15
    assert round(_ratio("#3B7FCC", "#1A1A1E"), 2) == 4.21
    assert round(_ratio("#C9A227", "#FAF5E6"), 2) == 2.22
    assert "--viz-1" not in TEXT_TOKENS and "--viz-2" not in TEXT_TOKENS


def test_canvas_fallbacks_match_the_tokens():
    """The share-card painters fall back to literal copies of --text-tertiary
    when the computed token is empty; a stale copy paints the old colour."""
    themes = _themes(ROOT / "assets" / "site.css", ":root {", '[data-theme="dark"] {')
    want = '"%s" : "%s"' % (themes["dark"]["--text-tertiary"], themes["light"]["--text-tertiary"])
    for name in ("eephus-hub.js", "eephus-gfx.js", "eephus-export.js"):
        src = (ROOT / "assets" / name).read_text(encoding="utf-8").upper()
        assert want.upper() in src, (name, want)
