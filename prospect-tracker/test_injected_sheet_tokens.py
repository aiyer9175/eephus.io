# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Every token a JS-injected style sheet references must resolve.

The documented regression (diamond.js, fixed 2026-08-05, first real-browser
render): the sheet was written against --border-subtle, which site.css did
not then define. getPropertyValue of an undefined token is "", so every rule
fell through to its hardcoded #333 / #222 fallback - unnoticeable in dark,
but in LIGHT it painted a near-black 1px hairline around every card on a
cream page. A var() chain that resolves to nothing with NO fallback is worse
still: the whole declaration goes invalid at computed-value time and a
border falls back to currentColor, a full-strength text-coloured rule (the
site.css BUGFIX 2026-08-05 comment documents nine such places).

So the guard is: for every var(--x[,fallback]) reference inside a
document.createElement("style") sheet in the Diamond and fantasy clients,
either site.css defines --x (any selector, either theme) or the reference
carries a literal fallback. And --border-subtle specifically must not appear
in a sheet at all, fallback or not: site.css now aliases it to
--border-light, but the sheets were migrated to --border / --border-light
and a new reference would be the 2026-08-05 pattern walking back in.
fantasy.js's eight pre-existing fallback-carrying uses are burn-down debt,
counted so they can shrink but not grow.

test_design_tokens.py owns the prospx/index.html + site.css token
foundation; this file owns the INJECTED sheets, which that test never reads.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
SITE_CSS = ASSETS / "site.css"

# The clients that inject (or may inject) a module sheet. cards.js currently
# links assets/cards.css instead of injecting; it stays on the list so a
# future injected sheet there is scanned the day it lands.
CLIENTS = [
    "diamond.js",
    "betting.js",
    "fantasy.js",
    "dynasty.js",
    "redraft.js",
    "dfs.js",
    "fantasy-hub.js",
    "fantasy-card.js",
    "cards.js",
]

# Files known to carry exactly one injected sheet today (2026-08-16). If the
# extractor rots and starts finding zero sheets, every downstream assertion
# would pass vacuously, so the census is pinned.
SHEET_CARRIERS = [c for c in CLIENTS if c != "cards.js"]

CREATE_STYLE = re.compile(r"createElement\(\s*[\"']style[\"']\s*\)")
VAR_REF = re.compile(r"var\(\s*--([A-Za-z0-9-]+)\s*([^)]*)\)")
CSS_DEF = re.compile(r"--([A-Za-z0-9-]+)\s*:")

# fantasy.js referenced var(--border-subtle,#333)-style rules before the
# 2026-08-05 fix and survived it because every use carries a literal
# fallback (site.css's own BUGFIX comment cites them). Eight uses measured
# 2026-08-16. The count may shrink; at zero the entry must be deleted.
BORDER_SUBTLE_BURN_DOWN = {"fantasy.js": 8}


def extract_sheets(src: str) -> list[str]:
    """The text between createElement("style") and the appendChild that
    mounts it - the region the sheet's CSS strings are assembled in."""
    sheets = []
    for m in CREATE_STYLE.finditer(src):
        end = src.find("appendChild", m.end())
        sheets.append(src[m.end():end if end != -1 else len(src)])
    return sheets


def var_refs(sheet: str) -> list[tuple[str, bool]]:
    """(token, has_literal_fallback) per reference. A nested fallback like
    var(--a,var(--b,#fff)) yields both the outer and inner reference."""
    out = []
    for m in VAR_REF.finditer(sheet):
        rest = m.group(2).strip()
        out.append((m.group(1), rest.startswith(",") and len(rest) > 1))
    return out


@pytest.fixture(scope="module")
def defined_tokens() -> set[str]:
    return set(CSS_DEF.findall(SITE_CSS.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def client_sheets() -> dict[str, list[str]]:
    return {
        name: extract_sheets((ASSETS / name).read_text(encoding="utf-8"))
        for name in CLIENTS
    }


def test_extractor_actually_finds_the_sheets(client_sheets):
    for name in SHEET_CARRIERS:
        assert len(client_sheets[name]) >= 1, (
            f"{name} carried an injected sheet on 2026-08-16 and the extractor "
            "now finds none; fix the extractor (or record the sheet's removal "
            "here) before trusting the token assertions below")
    total = sum(len(s) for s in client_sheets.values())
    assert total >= len(SHEET_CARRIERS)


def test_site_css_defines_a_real_token_set(defined_tokens):
    assert len(defined_tokens) > 50, (
        f"only {len(defined_tokens)} custom properties parsed out of site.css; "
        "the definition regex is broken")
    for t in ("border", "border-light", "bg-secondary", "text-primary"):
        assert t in defined_tokens


def test_every_injected_sheet_token_resolves(client_sheets, defined_tokens):
    violations = []
    for name, sheets in client_sheets.items():
        for sheet in sheets:
            for token, has_fb in var_refs(sheet):
                if token not in defined_tokens and not has_fb:
                    violations.append(f"{name}: var(--{token}) with no fallback")
    assert not violations, (
        "injected-sheet tokens that site.css does not define and that carry no "
        "literal fallback (these render as currentColor borders / invalid "
        "declarations, the 2026-08-05 light-theme regression): "
        + "; ".join(sorted(set(violations))))


def test_border_subtle_never_appears_in_an_injected_sheet(client_sheets):
    counts = {}
    for name, sheets in client_sheets.items():
        n = sum(1 for sheet in sheets for tok, _ in var_refs(sheet)
                if tok == "border-subtle")
        if n:
            counts[name] = n
    new_offenders = {n: c for n, c in counts.items()
                     if n not in BORDER_SUBTLE_BURN_DOWN}
    assert not new_offenders, (
        f"--border-subtle referenced in injected sheets outside the burn-down: "
        f"{new_offenders}. Use --border or --border-light (the 2026-08-05 "
        "regression tokens); site.css only aliases --border-subtle for legacy "
        "callers")
    for name, ceiling in BORDER_SUBTLE_BURN_DOWN.items():
        got = counts.get(name, 0)
        assert got > 0, (
            f"{name} no longer references --border-subtle: delete its "
            "BORDER_SUBTLE_BURN_DOWN entry so the ban becomes total there")
        assert got <= ceiling, (
            f"{name} grew from {ceiling} to {got} --border-subtle references; "
            "the burn-down only shrinks")


# ---------------------------------------------------------------------------
# Mutation proofs on in-memory sheet copies.
# ---------------------------------------------------------------------------

def _violations(sheet: str, defined: set[str]) -> list[str]:
    return [t for t, fb in var_refs(sheet) if t not in defined and not fb]


def test_mutation_nonexistent_token_is_caught(defined_tokens):
    sheet = '".x{border:1px solid var(--ghost-token-xyz)}"'
    assert _violations(sheet, defined_tokens) == ["ghost-token-xyz"]


def test_mutation_literal_fallback_excuses_an_unknown_token(defined_tokens):
    sheet = '".x{border:1px solid var(--ghost-token-xyz,#333)}"'
    assert _violations(sheet, defined_tokens) == []


def test_mutation_border_subtle_reference_is_caught_even_with_fallback():
    sheet = '".x{border:1px solid var(--border-subtle,#333)}"'
    assert [t for t, _ in var_refs(sheet)] == ["border-subtle"]


def test_mutation_tampered_real_sheet_fails(client_sheets, defined_tokens):
    # Take diamond.js's real sheet and tamper a real token into a ghost.
    sheet = client_sheets["diamond.js"][0]
    assert _violations(sheet, defined_tokens) == []
    tampered = sheet.replace("var(--bg-secondary)", "var(--bg-secondary-ghost)")
    assert tampered != sheet, (
        "diamond.js no longer uses bare var(--bg-secondary); pick another "
        "fallback-free reference for this tamper")
    assert _violations(tampered, defined_tokens) == ["bg-secondary-ghost"]
