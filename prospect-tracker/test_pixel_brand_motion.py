# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PB-03 (owner ask 2, 2026-09-30; PB-Q4 pitch, replay, glint): the wordmark's
motion, on both sides of build_site.PIXEL_BRAND.

Static, over assets/site.css:
  - the pixel-wordmark block is assets/brand/wordmark.css (tools/pixel_brand.py)
    verbatim, so the site and the generator cannot drift;
  - every rule that runs a wm-* keyframe is step-end and plays once; no
    transition; the motion is CSS only (no script names a wordmark class, so
    no requestAnimationFrame drives it);
  - no reduced-motion rule touches a wordmark (wm-*, ew-*): the site policy
    (owner, 2026-10-01; plan 5.7.1 amendment) runs every animation under Reduce
    Motion as without it, superseding PB-03's "reduced motion stops everything".

In headless Chromium, on the served pages (flag off):
  - F2: the hero arc's load dash covers the arc's real screen length (it used
    to be 100 screen px against a 305 px arc, so it slid instead of tracing),
    is fully hidden at the start and traces from the left end;
  - F3: leaving a hover never restarts the load shot;
  - 3.2 s after load no wordmark animation runs;
  - F1: in dark, the nav arc's stops are the dark ramp, not the light hex;
  - F16: the sidebar .io is --logo-dot.
And with the flag on (the served homepage and /ledger/ with the pixel lockup
swapped in through a route, nothing written to disk): 0 wordmark animations run
3.2 s after load, hovering starts the replay, leaving starts nothing, and the
hero shows exactly one of its two fragments at desktop and at phone width.

Playwright/chromium are OPTIONAL; the browser tests skip cleanly when they are
unavailable (mirrors test_reduced_motion_runs.py)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import build_site as B
from conftest import serve_site

ROOT = Path(__file__).parent
CSS = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
GEN = (ROOT / "assets" / "brand" / "wordmark.css").read_text(encoding="utf-8")


def _rules(css: str):
    """(prelude, body) for every flat rule; @keyframes and @media bodies are
    walked one level down."""
    out = []
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    i = 0
    while True:
        j = css.find("{", i)
        if j < 0:
            return out
        prelude = css[i:j].strip()
        depth, k = 1, j + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        body = css[j + 1:k - 1]
        if prelude.startswith("@media"):
            out += [(prelude + " " + p, b) for p, b in _rules(body)]
        else:
            out.append((prelude, body))
        i = k


def test_site_css_carries_the_generated_wordmark_css_verbatim():
    m = re.search(r"/\* pixel-wordmark:begin \*/\n(.*?)\n/\* pixel-wordmark:end \*/", CSS, re.S)
    assert m, "the pixel-wordmark block moved out of assets/site.css"
    gen = [ln for ln in GEN.splitlines() if ln and not ln.startswith("/*")]
    assert m.group(1).splitlines() == gen


def test_every_wordmark_animation_is_step_end_and_plays_once():
    names = set(re.findall(r"@keyframes\s+(wm-[\w-]+)", CSS))
    assert {"wm-on", "wm-on-h", "wm-drop", "wm-drop-h", "wm-flash"} <= names, names
    users = [(p, b) for p, b in _rules(CSS) if re.search(r"animation(-name)?:\s*wm-", b)]
    assert len(users) >= 7, users
    for prelude, body in users:
        anim = re.search(r"animation:\s*([^;]+);", body).group(1)
        assert "step-end" in anim, prelude
        assert "infinite" not in anim, prelude
        assert "transition" not in body, prelude
    # Every wm-* keyframe is run by some rule (no orphan motion).
    run = {re.search(r"animation:\s*(wm-[\w-]+)", b).group(1) for _p, b in users}
    assert names == run, (names, run)


def test_the_motion_is_css_only():
    hits = []
    for js in sorted((ROOT / "assets").glob("*.js")):
        t = js.read_text(encoding="utf-8", errors="replace")
        for cls in ("wm-px", "eephus-wordmark", "ew-arc", "ew-ball"):
            if cls in t:
                hits.append(f"{js.name}: {cls}")
    assert not hits, hits
    assert "requestAnimationFrame" not in GEN


def test_no_reduced_motion_rule_touches_the_wordmark():
    for prelude, body in _rules(CSS):
        if "prefers-reduced-motion" in prelude:
            assert not re.search(r"\.(wm|ew)-|eephus-wordmark|eephus-logo", prelude), prelude


def test_flag_off_hover_and_load_ride_different_elements():
    # F3 by construction: the load shot runs on the outer SVGs, the hover replay
    # on the pieces inside them, so a hover ending cannot restart the load shot.
    rules = {p: b for p, b in _rules(CSS)}
    assert "ew-arc-draw" in rules[".eephus-logo--animate .ew-arc"]
    assert "ew-ball-settle" in rules[".eephus-logo--animate .ew-ball"]
    assert "ew-arc-redraw" in rules[".eephus-wordmark-merged:hover .ew-arc path"]
    assert "ew-ball-resettle" in rules[".eephus-wordmark-merged:hover .ew-ball > *"]
    for p, b in rules.items():
        if ":hover" in p and "eephus-wordmark-merged" in p:
            assert "ew-arc-draw" not in b and "ew-ball-settle" not in b, p


# ------------------------------------------------------------------ browser
_RUNNING_JS = r"""() => document.getAnimations()
  .filter(a => a.animationName && /^(ew|wm)-/.test(a.animationName) && a.playState === 'running')
  .map(a => a.animationName)"""

_ARC_JS = r"""
() => {
  const path = document.querySelector('.masthead .ew-arc path');
  const m = path.getScreenCTM(), n = 400, L = path.getTotalLength();
  let len = 0, prev = null;
  for (let i = 0; i <= n; i++) {
    const p = path.getPointAtLength(L * i / n);
    const x = m.a * p.x + m.c * p.y + m.e, y = m.b * p.x + m.d * p.y + m.f;
    if (prev) len += Math.hypot(x - prev[0], y - prev[1]);
    prev = [x, y];
  }
  // Restart the hero's load shot (it may have finished before this ran) and
  // hold it at its first frame.
  const logo = document.querySelector('.masthead .eephus-logo');
  logo.classList.remove('eephus-logo--animate');
  void logo.offsetWidth;
  logo.classList.add('eephus-logo--animate');
  let held = 0;
  for (const a of document.getAnimations()) {
    if (a.animationName === 'ew-arc-draw') { a.pause(); a.currentTime = 0; held++; }
  }
  const cs = getComputedStyle(path);
  return {len, held, dash: parseFloat(cs.strokeDasharray), offset: parseFloat(cs.strokeDashoffset)};
}
"""

_VECTOR_HERO_RE = re.compile(r'<h1 class="nameplate eephus-wordmark-merged">.*?</h1>')
_VECTOR_SPAN_RE = re.compile(
    r'<span class="nameplate eephus-wordmark-merged">.*?eephus<span class="dot">\.io</span></span>')


def _pixel_swap(html_text: str) -> str:
    """The served page as PIXEL_BRAND would build it, for the lockups only."""
    html_text = _VECTOR_HERO_RE.sub(lambda m: B.pixel_wordmark("mast", "h1"), html_text, count=1)
    return _VECTOR_SPAN_RE.sub(lambda m: B.pixel_wordmark("nav", "span"), html_text)


@pytest.fixture(scope="module")
def browser_runs():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    out: dict = {}
    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")

        def hover_cycle(page, sel):
            box = page.locator(sel).first.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.wait_for_timeout(80)
            on = page.evaluate(_RUNNING_JS)
            page.wait_for_timeout(1400)
            page.mouse.move(2, 2)
            page.wait_for_timeout(80)
            return on, page.evaluate(_RUNNING_JS)

        # Flag off: the served pages as they are.
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto(base + "index.html", wait_until="load", timeout=30_000)
        page.evaluate("document.fonts.ready")
        out["off_arc"] = page.evaluate(_ARC_JS)
        page.goto(base + "index.html", wait_until="load", timeout=30_000)
        page.wait_for_timeout(3200)
        out["off_settled"] = page.evaluate(_RUNNING_JS)
        out["off_hover"], out["off_leave"] = hover_cycle(page, ".masthead .nameplate")
        out["off_sidebar_dot"] = page.evaluate("""() => [
            getComputedStyle(document.querySelector('.sb-brand .wm .dot')).color,
            getComputedStyle(document.querySelector('.masthead .nameplate .dot')).color]""")
        page.goto(base + "ledger/index.html", wait_until="load", timeout=30_000)
        page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        out["off_dark_stops"] = page.evaluate("""() => [...document.querySelectorAll('.eephus-nav .ew-arc stop')]
            .map(s => getComputedStyle(s).stopColor)""")
        out["dark_ramp"] = page.evaluate("""() => { const d = document.createElement('i');
            document.body.append(d);
            return ['--ramp-1', '--ramp-2', '--ramp-3', '--ramp-5'].map(t => {
              d.style.color = 'var(' + t + ')'; return getComputedStyle(d).color; }); }""")
        ctx.close()

        # Flag on: the same pages with the pixel lockup routed in.
        for width in (1280, 390):
            ctx = browser.new_context(viewport={"width": width, "height": 900})
            for rel in ("index.html", "ledger/index.html"):
                served = (ROOT / rel).read_text(encoding="utf-8")
                ctx.route(base + rel, lambda route, _req, body=_pixel_swap(served): route.fulfill(
                    status=200, content_type="text/html; charset=utf-8", body=body))
            page = ctx.new_page()
            page.goto(base + "index.html", wait_until="load", timeout=30_000)
            out[f"on_shown_{width}"] = page.evaluate("""() => [...document.querySelectorAll('.masthead svg.wm-px')]
                .filter(s => s.getBoundingClientRect().width > 0).map(s => s.getAttribute('width'))""")
            out[f"on_running_at_load_{width}"] = page.evaluate(_RUNNING_JS)
            page.wait_for_timeout(3200)
            out[f"on_settled_{width}"] = page.evaluate(_RUNNING_JS)
            if width == 1280:
                out["on_hover"], out["on_leave"] = hover_cycle(page, ".masthead .nameplate")
                page.goto(base + "ledger/index.html", wait_until="load", timeout=30_000)
                out["on_nav_load"] = page.evaluate(_RUNNING_JS)
                out["on_nav_hover"], out["on_nav_leave"] = hover_cycle(page, ".eephus-nav .nameplate")
            ctx.close()
        browser.close()
    return out


def test_f2_the_load_dash_traces_the_whole_arc(browser_runs):
    arc = browser_runs["off_arc"]
    assert arc["held"] == 1, arc
    assert arc["len"] > 200, arc
    # Hidden at the start, and one dash covers the arc's real screen length
    # without overshooting it by more than 2 percent (the trace keeps its pace).
    assert arc["offset"] == pytest.approx(arc["dash"]), arc
    assert arc["len"] <= arc["dash"] <= 1.02 * arc["len"], arc


def test_f3_leaving_a_hover_never_replays_the_load_shot(browser_runs):
    assert browser_runs["off_settled"] == []
    assert "ew-arc-redraw" in browser_runs["off_hover"]
    assert browser_runs["off_leave"] == []


def test_f1_the_dark_arc_reads_the_dark_ramp(browser_runs):
    assert browser_runs["off_dark_stops"] == browser_runs["dark_ramp"]
    assert "rgb(14, 43, 77)" not in browser_runs["off_dark_stops"]


def test_f16_the_sidebar_io_takes_the_logo_accent(browser_runs):
    sidebar, hero = browser_runs["off_sidebar_dot"]
    assert sidebar == hero


def test_flag_on_hero_shows_one_fragment_per_width(browser_runs):
    assert browser_runs["on_shown_1280"] == ["330"]
    assert browser_runs["on_shown_390"] == ["220"]


@pytest.mark.parametrize("width", [1280, 390])
def test_flag_on_pitch_plays_once_and_settles(browser_runs, width):
    assert any(n.startswith("wm-") for n in browser_runs[f"on_running_at_load_{width}"])
    assert browser_runs[f"on_settled_{width}"] == []


def test_flag_on_hover_replays_and_leaving_starts_nothing(browser_runs):
    assert "wm-on-h" in browser_runs["on_hover"]
    assert browser_runs["on_leave"] == []
    assert browser_runs["on_nav_load"] == []
    assert "wm-on-h" in browser_runs["on_nav_hover"]
    assert browser_runs["on_nav_leave"] == []
