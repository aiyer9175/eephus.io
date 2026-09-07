# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A stylesheet may not name a design token that does not exist.

THIS DEFECT HAS NOW SHIPPED TWICE, which is why it gets a guard instead of another
fix. site.css carries a BUGFIX note dated 2026-07-31: two rules named
`var(--accent)`, "which this stylesheet has never defined (the tokens are
--accent-cyan / -gold / -green / -red / -navy / -orange / -lilac). A var() chain
that resolves to nothing makes the [declaration invalid]". Sort headers had no
focus ring.

MEASURED 2026-09-07, the same class in three newer files:

    hof.css          13 references to --card / --line / --line-soft
    management.css   10 references to the same three
    trademachine.css  2 references to --bg-card, with NO fallback at all

None of those five tokens exists. The hof/management references fell back to
hardcoded literals; the trademachine ones fell back to nothing, so `.tm-wrap` and
the `.tm-hit` search results rendered with no surface.

AND THE LITERALS GAVE THE GAME AWAY: hof.css hardcoded #0E2B4D, #C9A227 and
#1F7A3A, which are exactly --accent-navy, --accent-gold and --accent-green. The
palette had been inlined rather than referenced, so the module looked nearly right
in light mode and could not follow the theme anywhere else. In dark mode
--bg-secondary is #1A1A1E and --border-light is #1D1D21, while the literals stayed
#fff and #d8d8d8: white cards and light-grey rules on a near-black page, with
sticky table headers as solid white bars.

WHAT IS LEGITIMATE, and the test must not flag it. `var(--org-color,
var(--accent-cyan))` is the runtime-injected pattern: a team card sets --org-color
inline per club and the fallback is a real token. An undefined token is fine
exactly when its fallback resolves to a defined one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"

_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_DEF = re.compile(r"(--[a-z0-9-]+)\s*:")
_VAR = re.compile(r"var\(\s*(--[a-z0-9-]+)\s*(?:,([^()]*(?:\([^()]*\)[^()]*)*))?\)")


def _sheets():
    out = sorted(ASSETS.glob("*.css"))
    if not out:
        pytest.skip("no stylesheets on this machine")
    return out


def _defined() -> set[str]:
    """Every token the design system defines, in CSS or injected at runtime.

    A token set from JavaScript is as real as one in :root -- `--org-color` is
    written per club by fantasy.js and dynasty.js, and `--card-tracks-narrow` by
    projections.js, so a stylesheet naming either is correct. A guard that could
    not see those would flag three working rules and get deleted.
    """
    d: set[str] = set()
    for f in _sheets():
        d |= set(_DEF.findall(_COMMENT.sub("", f.read_text(encoding="utf-8"))))
    for f in sorted(ASSETS.glob("*.js")):
        txt = f.read_text(encoding="utf-8", errors="ignore")
        # `.` matches whichever quote character the call uses; no
        # nested quoting needed, which is what broke a first attempt.
        d |= set(re.findall(r"setProperty\(\s*.(--[a-z0-9-]+)", txt))
        # any `--token:` inside a JS string is a style declaration
        d |= set(re.findall(r"(--[a-z0-9-]+)\s*:", txt))
    return d


def _unresolved(text: str, defined: set[str]):
    """(token, fallback) for every var() that cannot resolve to a real token.

    Comments are stripped first: site.css documents the 2026-07-31 fix by QUOTING
    the broken `var(--accent)`, and a guard that reads its own history as a defect
    is a guard that gets deleted.
    """
    bad = []
    for m in _VAR.finditer(_COMMENT.sub("", text)):
        tok, fb = m.group(1), (m.group(2) or "").strip()
        if tok in defined:
            continue
        inner = re.search(r"var\(\s*(--[a-z0-9-]+)", fb) if fb else None
        if inner and inner.group(1) in defined:
            continue          # the runtime-injected pattern; the fallback is real
        bad.append((tok, fb or "NO FALLBACK"))
    return bad


def test_no_stylesheet_names_a_token_that_does_not_exist():
    defined = _defined()
    assert "--accent-cyan" in defined and "--bg-secondary" in defined, (
        "the token scan found no palette at all; the regex has drifted")
    problems = {}
    for f in _sheets():
        bad = _unresolved(f.read_text(encoding="utf-8"), defined)
        if bad:
            problems[f.name] = bad
    assert not problems, (
        "stylesheets naming undefined design tokens. A fallback to a hardcoded "
        "literal cannot follow the theme, and no fallback at all makes the whole "
        "declaration invalid: " + repr(problems)
    )


def test_the_two_new_modules_reference_the_palette_rather_than_copying_it():
    """The specific regression: the palette inlined as hex.

    Checked by value, not by name, so renaming a token cannot smuggle it back.
    """
    inlined = {"#0E2B4D": "--accent-navy", "#C9A227": "--accent-gold",
               "#1F7A3A": "--accent-green"}
    hits = {}
    for rel in ("hof.css", "management.css"):
        f = ASSETS / rel
        if not f.exists():
            continue
        body = _COMMENT.sub("", f.read_text(encoding="utf-8"))
        found = {h: t for h, t in inlined.items() if h.lower() in body.lower()}
        if found:
            hits[rel] = found
    assert not hits, (
        f"palette values hardcoded instead of referenced, so they cannot change "
        f"with the theme: {hits}")


def test_neither_module_hardcodes_a_light_mode_surface():
    """#fff / #eee / #d8d8d8 on a card or a rule is a light-mode assumption."""
    banned = ("#fff", "#ffffff", "#eee", "#eeeeee", "#d8d8d8")
    hits = {}
    for rel in ("hof.css", "management.css", "trademachine.css"):
        f = ASSETS / rel
        if not f.exists():
            continue
        body = _COMMENT.sub("", f.read_text(encoding="utf-8")).lower()
        found = [b for b in banned if b in body]
        if found:
            hits[rel] = found
    # A filled accent chip takes var(--bg-primary) as its foreground, never #fff:
    # --accent-navy is #0E2B4D in light and #4FD9FF in dark, so a white label is
    # white-on-bright-cyan the moment the theme flips.
    assert not hits, (
        f"hardcoded light-mode surfaces; in dark mode --bg-secondary is #1A1A1E "
        f"and these do not move: {hits}")


_FILLED_ACCENT = re.compile(
    r"\{[^{}]*background:\s*var\(--accent-[a-z]+[^)]*\)[^{}]*color:\s*#f{3,6}[^{}]*\}"
    r"|\{[^{}]*color:\s*#f{3,6}[^{}]*background:\s*var\(--accent-[a-z]+[^)]*\)[^{}]*\}",
    re.IGNORECASE)


def test_no_filled_accent_chip_carries_a_white_label():
    """White on a filled accent is legible in light mode and gone in dark.

    The accents INVERT: --accent-cyan is #0E7C86 light and #00D9FF dark,
    --accent-green #1F7A3A and #4FFF9E, --accent-red #B91C1C and #FF6B7A,
    --accent-navy #0E2B4D and #4FD9FF. A white label sits on the dark version in
    light mode and on the BRIGHT version in dark mode. Measured contrast against
    the 4.5:1 body-text requirement:

        chip                     white label    var(--bg-primary) label
        accent-green  dark          1.30:1              15.01:1
        accent-navy   dark          1.65:1              11.82:1
        accent-cyan   dark          1.70:1              11.51:1
        accent-red    dark          2.75:1               7.11:1

    1.30:1 is not "low contrast", it is invisible. site.css:1236 established the
    house pattern years earlier, `background: var(--accent-navy); color:
    var(--bg-primary)`, which inverts with the theme by construction. Seven chips
    across four files had drifted off it, including two on /fantasy/.

    The light-mode cost is real and small: white on accent-cyan is 4.95:1 and
    --bg-primary is 4.35:1, marginally under AA, against a dark-mode gain from
    1.70 to 11.51. Recorded rather than buried.
    """
    offenders = {}
    for f in sorted(list(ASSETS.glob("*.js")) + list(ASSETS.glob("*.css"))):
        hits = _FILLED_ACCENT.findall(f.read_text(encoding="utf-8", errors="ignore"))
        if hits:
            offenders[f.name] = len(hits)
    assert not offenders, (
        "filled accent chips with a hardcoded white label; the accents invert, so "
        "these read at about 1.3:1 to 2.8:1 in dark mode. Use "
        "color: var(--bg-primary), the pattern at site.css:1236: " + repr(offenders))
