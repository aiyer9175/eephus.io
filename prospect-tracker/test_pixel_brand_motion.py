# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PB-03 (owner ask 2, 2026-09-30; PB-Q4 pitch, replay, glint): the wordmark's
motion.

Static, over assets/site.css:
  - the pixel-wordmark block is assets/brand/wordmark.css (tools/pixel_brand.py)
    verbatim, so the site and the generator cannot drift;
  - every rule that runs a wm-* keyframe is step-end and plays once; no
    transition; the motion is CSS only (no script names a wordmark class, so
    no requestAnimationFrame drives it);
  - no reduced-motion rule touches a wordmark (wm-*, ew-*): the site policy
    (owner, 2026-10-01; plan 5.7.1 amendment) runs every animation under Reduce
    Motion as without it, superseding PB-03's "reduced motion stops everything".

In headless Chromium, on the served pages (the pixel lockup serves on every
page since the owner's 2026-10-02 ask, PX_LOGO_ANIMATION; the retired vector
draw-on and its F1, F2 and F3 checks went with it): 0 wordmark animations run
3.2 s after load, hovering starts the replay, leaving starts nothing, the nav
mark is still on load, the hero shows exactly one of its two fragments at
desktop and at phone width, the sidebar .io takes the hero's accent (F16), and
in dark the arc bands read the dark --arc tokens.

Playwright/chromium are OPTIONAL; the browser tests skip cleanly when they are
unavailable (mirrors test_reduced_motion_runs.py)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

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


# ------------------------------------------------------------------ browser
_RUNNING_JS = r"""() => document.getAnimations()
  .filter(a => a.animationName && /^(ew|wm)-/.test(a.animationName) && a.playState === 'running')
  .map(a => a.animationName)"""


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

        for width in (1280, 390):
            ctx = browser.new_context(viewport={"width": width, "height": 900})
            page = ctx.new_page()
            page.goto(base + "index.html", wait_until="load", timeout=30_000)
            out[f"shown_{width}"] = page.evaluate("""() => [...document.querySelectorAll('.masthead svg.wm-px')]
                .filter(s => s.getBoundingClientRect().width > 0).map(s => s.getAttribute('width'))""")
            out[f"running_at_load_{width}"] = page.evaluate(_RUNNING_JS)
            page.wait_for_timeout(3200)
            out[f"settled_{width}"] = page.evaluate(_RUNNING_JS)
            if width == 1280:
                out["hover"], out["leave"] = hover_cycle(page, ".masthead .nameplate")
                out["sidebar_dot"] = page.evaluate("""() => [
                    getComputedStyle(document.querySelector('.eephus-nav .wm-dot')).fill,
                    getComputedStyle(document.querySelector('.masthead .wm-dot')).fill]""")
                page.goto(base + "ledger/index.html", wait_until="load", timeout=30_000)
                out["nav_load"] = page.evaluate(_RUNNING_JS)
                out["nav_hover"], out["nav_leave"] = hover_cycle(page, ".eephus-nav .nameplate")
                page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
                out["dark_bands"] = page.evaluate("""() => {
                    const svg = document.querySelector('.eephus-nav svg.wm-px');
                    const d = document.createElement('i'); document.body.append(d);
                    return [0, 1, 2, 3, 4, 5, 6, 7].map(k => {
                      const el = svg.querySelector('.wm-b' + k);
                      d.style.color = 'var(--arc-' + (k + 1) + ')';
                      return [getComputedStyle(el).fill, getComputedStyle(d).color]; }); }""")
            ctx.close()
        browser.close()
    return out


def test_hero_shows_one_fragment_per_width(browser_runs):
    # The homepage masthead is slim (HOME_4): its s 4 lockup at every width.
    assert browser_runs["shown_1280"] == ["220"]
    assert browser_runs["shown_390"] == ["220"]


@pytest.mark.parametrize("width", [1280, 390])
def test_pitch_plays_once_and_settles(browser_runs, width):
    assert any(n.startswith("wm-") for n in browser_runs[f"running_at_load_{width}"])
    assert not any(n.startswith("ew-") for n in browser_runs[f"running_at_load_{width}"])
    assert browser_runs[f"settled_{width}"] == []


def test_hover_replays_and_leaving_starts_nothing(browser_runs):
    assert "wm-on-h" in browser_runs["hover"]
    assert browser_runs["leave"] == []
    assert browser_runs["nav_load"] == []
    assert "wm-on-h" in browser_runs["nav_hover"]
    assert browser_runs["nav_leave"] == []


def test_f16_the_header_io_takes_the_logo_accent(browser_runs):
    # The homepage carries the shared header since HOME_4 (the sidebar is gone).
    sidebar, hero = browser_runs["sidebar_dot"]
    assert sidebar == hero


def test_f1_the_dark_arc_reads_the_dark_ramp(browser_runs):
    for fill, token in browser_runs["dark_bands"]:
        assert fill == token
    assert "rgb(14, 43, 77)" not in {f for f, _t in browser_runs["dark_bands"]}
