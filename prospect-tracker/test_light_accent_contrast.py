# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Light-mode accent contrast (owner answer Q4, 2026-10-22, 'Darken to 4.5:1').

The final site audit measured five accent families below 4.5:1 as reading text on
the light paper: farm grade letters (B- 2.37:1), IL day counts (2.28:1), draft
projected-round chips (R1 2.09:1), the '+ upside' driver tag (1.78:1) and the park
factor cold cells (4.35:1). Each now reads through a light-mode ink that clears
4.5:1 on every paper fill (and on its own chip tint), and the dark theme aliases
each ink back to the accent it had, so dark does not move.
"""
from __future__ import annotations

import colorsys
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
PX = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
PARKS_CSS = (ROOT / "assets" / "parks.css").read_text(encoding="utf-8")
SITE = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")

_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_DECL = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")


def _block(text, opener, must_hold=None):
    text = _COMMENT.sub("", text)
    start = 0
    while True:
        i = text.index(opener, start)
        j = text.index("{", i)
        depth, k = 0, j
        while True:
            if text[k] == "{":
                depth += 1
            elif text[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        body = text[j + 1:k]
        if must_hold is None or must_hold in body:
            return {m.group(1): m.group(2).strip() for m in _DECL.finditer(body)}
        start = k


LIGHT = _block(PX, ":root {", "--upside-ink")
DARK = _block(PX, '[data-theme="dark"] {', "--upside-ink")
SITE_LIGHT = _block(SITE, ":root {", "--text-gold")
PAPERS = [LIGHT["--bg-primary"], LIGHT["--bg-secondary"], LIGHT["--bg-tertiary"]]


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(c):
    v = [x / 255 for x in c]
    v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]


def _ratio(a, b):
    x, y = _lum(a), _lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def _over(fg, alpha, bg):
    return tuple(fg[i] * alpha + bg[i] * (1 - alpha) for i in range(3))


def _grounds(tint=None, alpha=0.0):
    out = [_rgb(p) for p in PAPERS]
    if tint is not None:
        out += [_over(tint, alpha, g) for g in list(out)]
    return out


# ink token -> (the chip tint it sits on, tint alpha, the exact dark value it must keep)
INKS = {
    "--upside-ink": (_rgb("#F4A6C8"), 0.18, "var(--upside-pink)"),
    "--draft-r1-ink": ((245, 200, 66), 0.18, "#E8A020"),
    "--draft-r2-ink": ((190, 195, 205), 0.20, "#A8ADB8"),
    "--draft-r35-ink": ((184, 115, 51), 0.18, "#C28250"),
}


@pytest.mark.parametrize("ink", sorted(INKS))
def test_light_ink_reads_4_5_on_every_paper_and_its_tint(ink):
    tint, alpha, _ = INKS[ink]
    fg = _rgb(LIGHT[ink])
    for g in _grounds(tint, alpha):
        assert _ratio(fg, g) >= 4.5, f"{ink} {LIGHT[ink]} reads {_ratio(fg, g):.2f}:1"


@pytest.mark.parametrize("ink", sorted(INKS))
def test_dark_ink_keeps_the_old_accent(ink):
    assert DARK[ink] == INKS[ink][2]


def test_upside_tag_text_takes_the_ink_and_keeps_its_fill():
    css = _COMMENT.sub("", PX)
    body = re.search(r"\.driver-tag\.is-upside\s*\{([^}]*)\}", css).group(1)
    assert "color: var(--upside-ink);" in body
    assert "border-color: var(--upside-pink);" in body
    assert "var(--upside-pink) 18%" in body


def test_draft_round_chips_read_the_inks():
    fn = PX[PX.index("const _pRoundColor = (() => {"):PX.index("// Tools: latest per source")]
    for ink in ("--draft-r1-ink", "--draft-r2-ink", "--draft-r35-ink"):
        assert f'fg: "var({ink})"' in fn
    assert not re.search(r'fg: "#[0-9A-Fa-f]{6}"', fn)


def test_il_day_counts_use_the_gold_reading_ink():
    gold = _rgb(SITE_LIGHT["--text-gold"])
    for g in _grounds():
        assert _ratio(gold, g) >= 4.5
    il_tab = "days > 14 ? 'var(--text-gold)' : 'var(--text-secondary)'"
    assert il_tab in PX
    assert "days > 14 ? 'var(--neon-amber)'" not in PX
    head = PX[PX.index("const headlineColor = hp.is_post_tj"):]
    head = head[:head.index(";")]
    assert '"var(--text-gold)"' in head and "neon-amber" not in head


def _palette():
    body = PX[PX.index("const _GRADE_PALETTE = {"):]
    body = body[:body.index("};")]
    out = {}
    for letter, h, s, l in re.findall(r"'([A-F][+-]?)':\s*'hsl\((\d+),\s*(\d+)%,\s*(\d+)%\)'", body):
        r, g, b = colorsys.hls_to_rgb(int(h) / 360, int(l) / 100, int(s) / 100)
        out[letter] = (round(r * 255), round(g * 255), round(b * 255))
    return out


def test_farm_grade_letters_read_4_5_in_light_and_keep_their_hue_in_dark():
    pal = _palette()
    assert len(pal) == 13
    mix = float(LIGHT["--grade-ink-mix"].rstrip("%")) / 100
    assert DARK["--grade-ink-mix"] == "100%"
    grounds = _grounds((255, 255, 255), 0.04)  # the letter box's own 4% white wash
    for letter, c in pal.items():
        ink = tuple(round(x * mix) for x in c)
        for g in grounds:
            assert _ratio(ink, g) >= 4.5, f"{letter} reads {_ratio(ink, g):.2f}:1"


def test_farm_letters_render_through_the_ink():
    assert "return `color-mix(in srgb, ${tone} var(--grade-ink-mix, 100%), #000)`;" in PX
    assert '<span class="fg-comp-letter" style="color:${farmLetterInk(tone)};">' in PX
    assert PX.count('<span class="fg-letter" style="color:${farmLetterInk(gradeColorVal)};') == 2
    assert 'class="fg-letter" style="color:${gradeColorVal}' not in PX


def test_park_cold_cells_use_the_cyan_reading_ink():
    css = _COMMENT.sub("", PARKS_CSS)
    assert ".parks-app .pk-cold { color: var(--text-cyan); }" in css
    cyan = _rgb(SITE_LIGHT["--text-cyan"])
    for p in (SITE_LIGHT["--bg-primary"], SITE_LIGHT["--bg-secondary"], SITE_LIGHT["--bg-tertiary"]):
        assert _ratio(cyan, _rgb(p)) >= 4.5
