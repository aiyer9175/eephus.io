# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Light-theme reading inks for the accent hues (QUAL_2, surface-quality audit
2026-10-02: QMLA01, QMLA02, QMLA03, QREA03, QCLA02, QCLA03).

As reading text on the warm paper, accent cyan #0E7C86 measured 4.35:1, accent
gold #C9A227 2.13:1, the violet #b47cff 2.54:1, and green on its own 8 to 12%
tint 4.04 to 4.28:1. Element opacity on the /franchise/ tile lines and count
notes composited a green dollar down to 2.44:1 and an orange verdict chip to
3.05:1. The fix is a reading ink per hue in the light :root (aliased to the
neon twin in dark, so dark does not move) and a colour in place of every
opacity. These tests hold the inks to AA on every paper and hold each named
rule to an ink.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
SITE = ROOT / "assets" / "site.css"
ACCOUNT = ROOT / "assets" / "eephus-account.css"
FRANCHISE = ROOT / "assets" / "franchise.css"
TM = ROOT / "assets" / "trademachine.js"

INKS = ("--text-cyan", "--text-amber", "--text-violet", "--text-green")
# the dark twin each ink must alias, so dark keeps its colour exactly
DARK_TWIN = {"--text-cyan": "--accent-cyan", "--text-amber": "--accent-gold",
             "--text-violet": "--neon-violet", "--text-green": "--accent-green"}
PAPERS = ("#F4F0E6", "#FAF5E6")

_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_HEX = re.compile(r"(--[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})\b")
_ALIAS = re.compile(r"(--[a-z0-9-]+)\s*:\s*var\(\s*(--[a-z0-9-]+)\s*\)")
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    x, y = _lum(a), _lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def _block(text, opener):
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
    for _ in range(3):
        for k, ref in _ALIAS.findall(body):
            if ref in out:
                out[k] = out[ref]
    return out


def _light_dark():
    text = SITE.read_text(encoding="utf-8")
    light = _tokens(_block(text, ":root {"))
    dark = _tokens(_block(text, '[data-theme="dark"] {'), base=light)
    return light, dark


def _rule(path, selector):
    """Declarations of every innermost rule whose selector list names `selector`."""
    text = _COMMENT.sub("", path.read_text(encoding="utf-8"))
    bodies = [body for sel, body in _RULE.findall(text)
              if selector in [s.strip() for s in sel.split(",")]]
    assert bodies, f"{path.name}: no rule for {selector}"
    return ";".join(bodies)


def _decl(body, prop):
    m = re.findall(r"(?:^|[;\s{])" + re.escape(prop) + r"\s*:\s*([^;]+)", body)
    return m[-1].strip() if m else None


@pytest.mark.parametrize("ink", INKS)
def test_light_ink_clears_aa_on_every_paper(ink):
    light, _ = _light_dark()
    assert ink in light, f"{ink} is not defined (or does not resolve) in the light :root"
    grounds = [light["--bg-primary"], light["--bg-secondary"], light["--bg-tertiary"], *PAPERS]
    for g in grounds:
        r = _ratio(light[ink], g)
        assert r >= 4.5, f"{ink} {light[ink]} on {g} reads {r:.2f}:1"


@pytest.mark.parametrize("ink", INKS)
def test_dark_ink_aliases_its_neon_twin(ink):
    _, dark = _light_dark()
    assert dark[ink] == dark[DARK_TWIN[ink]], f"dark {ink} {dark[ink]} moved off {DARK_TWIN[ink]}"


def test_selected_projections_tab_paper_on_cyan_ink():
    light, _ = _light_dark()
    body = _rule(SITE, '.mlbp-tabs .chip.mlbp-tab[aria-selected="true"]')
    assert _decl(body, "background") == "var(--text-cyan)"
    assert _decl(body, "color") == "var(--bg-primary)"
    assert _ratio(light["--bg-primary"], light["--text-cyan"]) >= 4.5


# (file, selector): each must take its TEXT colour from a reading ink or --text-*
INKED = [
    (SITE, ".proj-app .proj-ct-signed"),
    (SITE, ".tier-key i"),
    (SITE, ".fa-app .fa-verdict-value"),
    (SITE, ".fa-app .fa-block-mlb i"),
    (SITE, ".bp-validated"),
    (SITE, ".pal-tier--t1"),
    (SITE, ".pal-tier--t3"),
    (SITE, ".pal-sev--marked"),
    (ACCOUNT, ".eph-demo-flag"),
    (FRANCHISE, ".fr-app .fr-count"),
    (FRANCHISE, ".fr-app .fr-tile-sub"),
    (FRANCHISE, ".fr-app .fr-tile-title"),
    (FRANCHISE, ".fr-app .fr-chip-prov"),
]
# rules that must carry no dimming opacity (their text colour may be inherited)
NO_OPACITY = [sel for sel in INKED] + [(SITE, ".fa-app .fa-th-unit"), (FRANCHISE, ".fr-app .fr-verdict")]


@pytest.mark.parametrize("path,selector", INKED, ids=[s for _, s in INKED])
def test_named_rule_text_takes_an_ink(path, selector):
    color = _decl(_rule(path, selector), "color")
    assert color and re.fullmatch(r"var\(--text-[a-z]+\)", color), f"{selector} color is {color!r}"


@pytest.mark.parametrize("path,selector", NO_OPACITY, ids=[s for _, s in NO_OPACITY])
def test_named_rule_has_no_opacity(path, selector):
    op = _decl(_rule(path, selector), "opacity")
    assert op is None or float(op) >= 1, f"{selector} opacity {op}"


def test_franchise_svg_provisional_chip_reads():
    light, dark = _light_dark()
    chip = _rule(FRANCHISE, ".fr-app .fr-svg-chip")
    text = _rule(FRANCHISE, ".fr-app .fr-svg-chip-text")
    assert _decl(chip, "fill") == "var(--text-gold)"
    assert _decl(text, "fill") == "var(--bg-secondary)"
    assert float(_decl(text, "font-size").rstrip("px")) >= 9
    for th in (light, dark):
        assert _ratio(th["--bg-secondary"], th["--text-gold"]) >= 4.5


def test_trademachine_chip_text_off_the_neon():
    src = TM.read_text(encoding="utf-8")
    assert not re.search(r"color:\s*var\(--neon-(amber|violet)\)", src), "inline neon text colour remains"
    # every remaining neon amber / violet feeds a border variable only
    for line in src.splitlines():
        if re.search(r"--neon-(amber|violet)", line):
            assert re.match(r"\s*const \w*[Bb]ord\w* = ", line), f"neon used outside a border: {line.strip()}"
    # the four audited chips
    assert 'const statusCol = isMlb ? "var(--text-violet)"' in src
    assert 'pOpts ? `<span style="color:var(--text-amber);' in src
    assert re.search(r'const grpoCol = [^;]*"var\(--text-amber\)"', src)
    assert re.search(r'const col = sc >= 55 \? [^;]*"var\(--text-amber\)"', src)
    assert "border-color:${grpoBord}" in src and "border-color:${bord}" in src
