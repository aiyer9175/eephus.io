# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""T6 of the pixel system (final-pass plan 5.7.4): reduced motion and budgets.

  - owner rule 2026-10-01 (supersedes plan 5.7.1 line 11): the site's motion is
    minimal and runs on the OS Reduce Motion setting; no prefers-reduced-motion
    rule anywhere in site.css, the PROSPX <style>, the export asset or the
    animated mark sets animation:none, transition:none or a slowed duration,
    and the old global animation reset is gone;
  - the old 0.8 s steps(8) square and its 2.4 s reduced-motion spin are gone
    (from site.css and from the PROSPX <style>);
  - every px animation steps (step-end), and its base style is the still
    frame: the loader rests on the apex ball, the 404 on its final frame;
  - no requestAnimationFrame in the state code;
  - the loader and the 404 each fit 8 KB with their CSS (plan 5.7.1 line 14).
"""
from __future__ import annotations

import re
from pathlib import Path

import build_site

ROOT = Path(__file__).parent
CSS = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
STATE_JS = (ROOT / "assets" / "eephus-state.js").read_text(encoding="utf-8")
PROSPX = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
EXPORT_JS = (ROOT / "assets" / "eephus-export.js").read_text(encoding="utf-8")
ARC_SVG = (ROOT / "branding" / "animated" / "eephus-arc.svg").read_text(encoding="utf-8")


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _blocks(css: str):
    """Top-level (prelude, body) pairs, brace-matched."""
    out, i, n = [], 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        depth, k = 1, j + 1
        while depth and k < n:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        out.append((css[i:j].strip(), css[j + 1:k - 1]))
        i = k
    return out


def _rules(css: str):
    """(selector list, declarations) for plain rules, at the top level."""
    return [([s.strip() for s in pre.split(",")], body) for pre, body in _blocks(css)
            if not pre.startswith("@")]


CLEAN = _strip_comments(CSS)
TOP = _blocks(CLEAN)
KEYFRAMES = sorted({m.group(1) for m in re.finditer(r"@keyframes\s+(px-[\w-]+)", CLEAN)})
REDUCE = "".join(body for pre, body in TOP
                 if pre.startswith("@media") and "prefers-reduced-motion" in pre and "reduce" in pre)


def _px_rule_block() -> str:
    i = CLEAN.index(".px-state {")
    return CLEAN[i:CLEAN.index(".fa-app .fa-thin", i)]


def test_the_pixel_keyframes_exist():
    assert KEYFRAMES == ["px-hide", "px-lob", "px-show"], KEYFRAMES


def test_every_px_keyframe_is_used():
    for name in KEYFRAMES:
        users = [s for sels, body in _rules(CLEAN)
                 if re.search(r"animation(?:-name)?\s*:[^;]*\b" + re.escape(name) + r"\b", body)
                 for s in sels]
        assert users, f"@keyframes {name} is never used"


_STILL = re.compile(r"(animation|transition)(-duration|-iteration-count|-play-state)?\s*:\s*"
                    r"(none|0\.0*1ms|0s|1\s*!|paused)")

POLICY = ("Reduce Motion does not disable this site's animations: they are minimal by "
          "design (owner, 2026-10-01). Every animation and transition runs as it does "
          "without the preference. The one exception is pointer-tracking movement (the "
          "background parallax), which keeps honoring the preference because it is "
          "coupled to the pointer, not a timed animation.")


def test_the_policy_heads_the_reduced_motion_section():
    flat = " ".join(CSS.replace("/*", " ").replace("*/", " ").split())
    assert POLICY in flat


def test_nothing_is_switched_off_under_reduced_motion():
    """Owner rule 2026-10-01: the animations are minimal and keep running on the
    Reduce Motion setting; the one exception, the pointer-tracking parallax,
    lives in eephus-bg.js, not in a stylesheet."""
    assert not _STILL.search(REDUCE), REDUCE
    assert "animation" not in REDUCE and "transition" not in REDUCE, REDUCE
    assert "!important" not in REDUCE, "the global animation reset is back"
    style = _strip_comments(PROSPX[PROSPX.index("<style>"):PROSPX.index("</style>")])
    for pre, body in _blocks(style):
        if pre.startswith("@media") and "prefers-reduced-motion" in pre:
            assert not _STILL.search(body), (pre, body)
    # comments may mention the setting; no rule or query may act on it
    assert "prefers-reduced-motion" not in _strip_comments(EXPORT_JS)
    assert "prefers-reduced-motion" not in _strip_comments(re.sub(r"<!--.*?-->", "", ARC_SVG, flags=re.S))
    gl = (ROOT / "assets" / "eephus-gl.js").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" not in gl, "the glossary tooltip delay reads the preference again"
    bg = (ROOT / "assets" / "eephus-bg.js").read_text(encoding="utf-8")
    assert "prefers-reduced-motion: reduce" in bg, "the pointer parallax keeps honoring the preference"


def test_the_old_spinner_and_its_slowed_spin_are_gone():
    assert "2.4s" not in CLEAN.replace(" ", ""), "the 2.4 s reduced-motion spin is back"
    assert "steps(8)" not in CLEAN
    assert "eephus-spin" not in CLEAN
    assert ".state-message.is-loading" not in CLEAN
    style = PROSPX[PROSPX.index("<style>"):PROSPX.index("</style>")]
    assert "animation-duration: 2.4s" not in style
    assert ".state-message.is-loading::before { animation: none; }" not in style


def test_px_animations_step_and_rest_on_the_still_frame():
    block = _px_rule_block()
    assert "px-lob 1.6s step-end infinite" in block
    assert block.count("animation-timing-function: step-end") == 2
    rules = dict((",".join(s), b) for s, b in _rules(block))
    assert "opacity: 0" in rules[".px-lob .f"] and "opacity: 1" in rules[".px-lob .r"], \
        "the loader's base style is the apex ball alone"
    # the last foul ball is also a .b: its rule must come after .b to win
    assert block.index(".px-foul .z {") > block.index(".px-foul .b {")
    assert "opacity: 1" in rules[".px-foul .z"] and "px-hide" in rules[".px-foul .z"]
    # the trail is visible at rest (no opacity on .t): the final frame
    assert "opacity" not in rules[".px-foul .t"]


def test_the_px_block_draws_in_tokens_only():
    block = _px_rule_block()
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", block)
    assert "border-radius" not in block and "accent-red" not in block
    assert "gradient" not in block.replace("var(--iridescent)", "")


def test_no_frame_loop_in_the_state_code():
    assert "requestAnimationFrame" not in STATE_JS
    assert "requestAnimationFrame" not in build_site._PX_404_ART


def test_the_loader_and_the_404_fit_their_budgets():
    block = _px_rule_block()
    lob_css = block[block.index(".px-lob {"):block.index(".px-404 {")]
    lob_js = STATE_JS[STATE_JS.index("var LOB ="):STATE_JS.index("var ART =")]
    assert len(lob_css.encode()) + len(lob_js.encode()) <= 8192
    foul_css = block[block.index(".px-404 {"):]
    assert len(foul_css.encode()) + len(build_site._PX_404_ART.encode()) <= 8192


def test_the_404_draws_the_foul_ball_and_keeps_its_copy():
    out = build_site.build_404()
    assert f'<div class="px-404">{build_site._PX_404_ART}</div>' in out
    assert "<h1>404: page not found</h1>" in out
    assert '<span class="section-sub">no page at this address</span>' in out
    assert "<p>Player search: <strong>Ctrl+K</strong> (⌘K on Mac).</p>" in out
    art = build_site._PX_404_ART
    assert 'aria-hidden="true"' in art and 'shape-rendering="crispEdges"' in art
    assert art.count('class="b z"') == 1, "one ball stays"
    # one shot: the animation never repeats
    assert "infinite" not in art and "iteration" not in art
