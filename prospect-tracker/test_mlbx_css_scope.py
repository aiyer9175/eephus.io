# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /mlbstats/ column-view CSS may restyle /mlbstats/ and nothing else.

.mlbstats-app is NOT a page scope: ten module roots carry it (arbitration, MLB
Stats, the Alchemy Lab, fantasy, betting, Diamond, parks, management, Hall of
Fame, account), because they all ride the shared leaderboard table. A rule
scoped to it would narrow the padding and drop the uppercase headers on every
one of those tables. So the column-view block in site.css (between the mlbx
markers) scopes every selector under .mlbx, a class build_site puts on the
/mlbstats/ root only. Measured when the block landed: the /betting/ tables are
identical with and without it.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent
SITE_CSS = ROOT / "assets" / "site.css"
BEGIN = "/* ---- mlbx begin ---- */"
END = "/* ---- mlbx end ---- */"
_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_SCOPE = re.compile(r"^\.mlbx(?![\w-])")


def _block() -> str:
    css = SITE_CSS.read_text(encoding="utf-8")
    assert css.count(BEGIN) == 1 and css.count(END) == 1, "the mlbx markers must each appear once"
    i, j = css.index(BEGIN), css.index(END)
    assert i < j
    return css[i + len(BEGIN):j]


def _split_top(prelude: str) -> list[str]:
    """Split a selector list on the commas outside parentheses, so
    `:is(.a, .b)` stays one selector."""
    parts, depth, cur = [], 0, ""
    for ch in prelude:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def _selectors(css: str) -> list[str]:
    """Every style-rule selector in `css`, at-rule preludes excluded, nested
    @media bodies included. Braces are balanced by hand: the block holds no
    strings or url()s that could carry one."""
    css = _COMMENT.sub("", css)
    out, buf, depth_stack = [], "", []
    for ch in css:
        if ch == "{":
            prelude = buf.strip()
            buf = ""
            if prelude.startswith("@"):
                depth_stack.append("at")
            else:
                depth_stack.append("rule")
                out.extend(s.strip() for s in _split_top(prelude) if s.strip())
        elif ch == "}":
            assert depth_stack, "unbalanced braces in the mlbx block"
            depth_stack.pop()
            buf = ""
        elif ch == ";" and depth_stack and depth_stack[-1] == "rule":
            buf = ""
        else:
            buf += ch
    assert not depth_stack, "unbalanced braces in the mlbx block"
    return out


def test_every_selector_in_the_block_is_scoped_under_mlbx():
    sels = _selectors(_block())
    assert len(sels) >= 20, "the column-view block looks empty"
    bad = [s for s in sels if not _SCOPE.match(s)]
    assert not bad, "selectors that escape the /mlbstats/ scope: %r" % bad


def test_the_block_scopes_on_mlbx_and_never_on_the_shared_app_class():
    for s in _selectors(_block()):
        assert not s.startswith(".mlbstats-app"), s


def test_only_the_mlbstats_root_carries_the_scope_class():
    """The scope is only a scope while exactly one root carries it."""
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    roots = [m.group(0) for m in re.finditer(r'class="[^"]*\bmlbx\b(?!-)[^"]*"', src)]
    assert roots == ['class="fa-app mlbstats-app mlbx"'], roots
    i = src.index("def build_mlbstats(")
    j = src.index("\ndef ", i + 1)
    assert 'class="fa-app mlbstats-app mlbx"' in src[i:j], "the scope class left the /mlbstats/ shell"
    for js in (ROOT / "assets").glob("*.js"):
        text = js.read_text(encoding="utf-8", errors="replace")
        assert not re.search(r'class="[^"]*\bmlbx\b(?!-)[^"]*"', text), js.name


def test_the_selector_reader_sees_nested_media_rules():
    sample = (".mlbx .a { x: 1; } @media (max-width: 640px) { .mlbx .b, .c { y: 2; }"
              " .mlbx td > :is(.d, .e) { z: 3; } }")
    assert _selectors(sample) == [".mlbx .a", ".mlbx .b", ".c", ".mlbx td > :is(.d, .e)"]
