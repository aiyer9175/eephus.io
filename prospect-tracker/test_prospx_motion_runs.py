# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PROSPX motion runs as specified on the served page (owner, 2026-10-01).

The owner's asks, verbatim: "Make sure all animations run on Reduced Animation
setting, our animations are minimal and shouldn't be disabled entirely just
because of Reduce Motion" and "Ensure all animations run correctly on the site
as well". The animation audit of 2026-10-01 found PROSPX motion that reported
running but moved nothing, or was missing. Each check below drives headless
Chromium through the shared harness (conftest.serve_site) once with
prefers-reduced-motion emulated as "reduce" and once as "no-preference",
asserts the animation runs with the expected name, duration and play state on
the SERVED page, and asserts the two runs measure the same:

  - A01: the headshot rarity rings on the /prospx/ board move. Their
    background-position was pinned by an !important background shorthand, so
    foil-shift, chrome-shimmer and holo-shift reported running and held still.
  - A09: the rank diamonds run no loop. They are static by spec but inherited
    the generic .card-rarity-* loops, which ran on every rarity diamond and
    moved nothing; switching them off leaves each diamond pixel-identical.

Playwright/chromium are OPTIONAL; the browser tests skip cleanly when they are
unavailable (mirrors test_reduced_motion_runs.py)."""
from __future__ import annotations

import pytest
from conftest import serve_site

MODES = ("reduce", "no-preference")

# Expected loop per headshot ring tier (prospx/index.html .headshot.fv-headshot-ring
# rules): the moving gradient, never the 2 s outline pulse layered beside it.
RING_LOOPS = {
    "foil": ("foil-shift", 8000),
    "chrome": ("chrome-shimmer", 4200),
    "holo": ("holo-shift", 5000),
    "legendary": ("holo-shift", 3000),
}

_INIT = ("try{localStorage.setItem('prospect-tracker.gate-unlocked','1');"
         "localStorage.setItem('prospect-tracker.theme','light')}catch(e){}")

# One ring per tier: scroll it into view (board rows are content-visibility:
# auto, and Chromium does not advance animations in a skipped row), then read
# background-position three times 300 ms apart and list its CSS animations.
_RING_JS = r"""
async (tier) => {
  const el = document.querySelector('span.headshot.fv-headshot-ring.card-rarity-' + tier);
  if (!el) return null;
  el.scrollIntoView({block: 'center'});
  await new Promise((r) => setTimeout(r, 200));
  const pos = [];
  for (let i = 0; i < 3; i++) {
    if (i) await new Promise((r) => setTimeout(r, 300));
    pos.push(getComputedStyle(el).backgroundPosition);
  }
  const anims = el.getAnimations().filter((a) => a.animationName).map((a) => {
    const t = a.effect.getComputedTiming();
    return {name: a.animationName, duration: t.duration, iterations: t.iterations,
            state: a.playState};
  });
  anims.sort((a, b) => (a.name < b.name ? -1 : 1));
  return {moves: new Set(pos).size > 1, anims};
}
"""


# Every rank diamond carrying a rarity class, and how many run an animation.
_DIAMONDS_JS = r"""
() => {
  const els = Array.from(document.querySelectorAll('.rank-num[class*="card-rarity-"]'));
  return {count: els.length, looping: els.filter((e) => e.getAnimations().length > 0).length};
}
"""

# The loops the diamonds inherited before A09 (the generic .card-rarity-*
# rules), re-applied at the diamond's own specificity to rebuild the pre-change
# frame for the pixel comparison.
_PRE_A09_CSS = (
    ".rank-num.card-rarity-foil{animation:foil-shift 8s linear infinite}"
    ".rank-num.card-rarity-chrome{animation:chrome-shimmer 4.2s linear infinite}"
    ".rank-num.card-rarity-holo{animation:holo-shift 6s linear infinite}"
    ".rank-num.card-rarity-legendary{animation:legendary-shift 3s linear infinite}"
)


def _diamond_shots(page) -> dict:
    """{tier: (served png, pre-change png)} for the first diamond of each tier."""
    out = {}
    for tier in RING_LOOPS:
        loc = page.locator(".rank-num.card-rarity-" + tier).first
        if not loc.count():
            continue
        loc.scroll_into_view_if_needed(timeout=10_000)
        page.wait_for_timeout(200)
        served = loc.screenshot(animations="allow")
        page.evaluate("(css) => { const s = document.createElement('style'); s.id = 'pre-a09';"
                      " s.textContent = css; document.head.appendChild(s); }", _PRE_A09_CSS)
        page.wait_for_timeout(1000)
        pre = loc.screenshot(animations="allow")
        page.evaluate("() => document.getElementById('pre-a09').remove()")
        out[tier] = (served, pre)
    return out


@pytest.fixture(scope="module")
def measured():
    """{mode: {probe: result}} for both modes, from one chromium launch."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    out: dict[str, dict] = {}
    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        for mode in MODES:
            ctx = browser.new_context(reduced_motion=mode, viewport={"width": 1280, "height": 900})
            ctx.add_init_script(_INIT)
            page = ctx.new_page()
            res: dict = {}
            page.goto(base + "prospx/index.html", wait_until="load", timeout=60_000)
            res["emulated"] = page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
            try:
                page.wait_for_selector("span.headshot.fv-headshot-ring[class*='card-rarity-']",
                                       state="attached", timeout=60_000)
            except Exception:
                pass
            page.wait_for_timeout(1000)
            for tier in RING_LOOPS:
                res["ring:" + tier] = page.evaluate(_RING_JS, tier)
            res["diamonds"] = page.evaluate(_DIAMONDS_JS)
            res["diamond_shots"] = {t: a == b for t, (a, b) in _diamond_shots(page).items()}
            out[mode] = res
            ctx.close()
        browser.close()
    return out


def test_the_preference_is_emulated(measured):
    assert measured["reduce"]["emulated"] is True
    assert measured["no-preference"]["emulated"] is False


def test_a01_headshot_rarity_rings_move(measured):
    """A01: each rarity ring present on the board moves its gradient, with the
    tier's loop name and duration, infinite and running, the same under both
    motion settings."""
    present = [t for t in RING_LOOPS if measured["no-preference"]["ring:" + t] is not None]
    assert "foil" in present, "no foil headshot ring on the served board"
    for tier in present:
        name, dur = RING_LOOPS[tier]
        for mode in MODES:
            got = measured[mode]["ring:" + tier]
            assert got is not None, f"{tier}: ring missing under {mode}"
            assert got["moves"], f"{tier} under {mode}: background-position never changed"
            loop = [a for a in got["anims"] if a["name"] == name]
            assert loop, f"{tier} under {mode}: no {name} in {got['anims']}"
            assert loop[0]["duration"] == dur, loop
            assert loop[0]["iterations"] == float("inf"), loop
            assert loop[0]["state"] == "running", loop
        assert measured["reduce"]["ring:" + tier] == measured["no-preference"]["ring:" + tier]


def test_a09_rank_diamonds_run_no_loop(measured):
    """A09: no rarity diamond runs an animation, and each tier's diamond is
    pixel-identical to the frame the inherited loops painted, under both motion
    settings."""
    for mode in MODES:
        d = measured[mode]["diamonds"]
        assert d["count"] > 0, f"no rarity diamond on the served board under {mode}"
        assert d["looping"] == 0, f"{d['looping']} of {d['count']} diamonds run a loop under {mode}"
        shots = measured[mode]["diamond_shots"]
        assert "foil" in shots, shots
        assert all(shots.values()), f"diamond frame changed under {mode}: {shots}"
    assert measured["reduce"]["diamonds"] == measured["no-preference"]["diamonds"]
    assert measured["reduce"]["diamond_shots"] == measured["no-preference"]["diamond_shots"]
