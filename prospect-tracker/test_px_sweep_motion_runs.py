# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The motions PX_SYSTEM_SWEEP converted to the pixel idiom, read computed on
the SERVED pages (docs/pixel/PX_SWEEP_2026-10.md, section 2).

Headless Chromium through the shared harness (conftest.serve_site), once with
prefers-reduced-motion emulated as "reduce" and once as "no-preference"; every
reading must be the same in both (owner, 2026-10-01: the site's animations run
with or without the preference). Pins, per motion:

  M13  a PROSPX in-app loader (pxLoadingHTML) draws the lamp loader: px-lob,
       1.6 s, step-end, infinite;
  M14  the FV badge edge pulse is fvIndicatorPulse 2.4 s step-end;
  M18  a board headshot's foil ring is foil-shift 8 s in steps(32, end);
  M12  the news ribbon marquee steps one whole pixel per step (steps(N) with N
       the measured copy width in px);
  M24  the GFX busy overlay carries the lamp loader;
  M26  the export toast transition is .15 s steps(4, start) on opacity and
       transform (the first step at once, so it never reads as a pop);
  M23  the glossary card highlight is 1.8 s steps(4, end).

Playwright/chromium are OPTIONAL; the tests skip cleanly when they are
unavailable (mirrors test_reduced_motion_runs.py)."""
from __future__ import annotations

import pytest
from conftest import serve_site

MODES = ("reduce", "no-preference")

_ANIM_JS = r"""
(el) => {
  if (!el) return null;
  const cs = getComputedStyle(el);
  return {name: cs.animationName, duration: cs.animationDuration,
          timing: cs.animationTimingFunction, count: cs.animationIterationCount};
}
"""

_LOADER_JS = r"""
() => {
  const host = document.createElement('div');
  host.id = 'px-sweep-loader';
  host.innerHTML = pxLoadingHTML('Loading draft data');
  document.body.prepend(host);
  const f = host.querySelector('.px-state.is-loading .px-lob .f');
  return f ? f : null;
}
"""

_MARQUEE_JS = r"""
() => {
  const root = document.createElement('div');
  root.style.width = '600px';
  root.innerHTML = '<div class="news-ticker"><div class="news-ticker-strip">'
    + Array.from({length: 6}, (_, i) => '<button class="chip" type="button">Chip number ' + i + '</button>').join('')
    + '</div></div>';
  document.body.prepend(root);
  marqueeifyTicker(root);
  const track = root.querySelector('.news-ticker-track');
  const shift = track.style.getPropertyValue('--ntk-shift');
  return {timing: track.style.animationTimingFunction, shift,
          computed: getComputedStyle(track).animationTimingFunction};
}
"""

_TOAST_JS = r"""
() => {
  const t = document.createElement('div');
  t.className = 'eephus-export-toast';
  document.body.appendChild(t);
  const cs = getComputedStyle(t);
  return {property: cs.transitionProperty, duration: cs.transitionDuration, timing: cs.transitionTimingFunction};
}
"""

_HIGHLIGHT_JS = r"""
() => {
  const app = document.querySelector('.gl-app') || document.body;
  const c = document.createElement('div');
  c.className = 'glossary-card is-highlighted';
  app.prepend(c);
  const cs = getComputedStyle(c);
  return {name: cs.animationName, duration: cs.animationDuration, timing: cs.animationTimingFunction};
}
"""


def _anim(page, sel):
    """The computed animation of the first match, scrolled into view first (board
    rows are content-visibility:auto, and the board re-renders after load)."""
    page.wait_for_timeout(1000)
    h = page.query_selector(sel)
    if not h:
        return None
    h.scroll_into_view_if_needed(timeout=10_000)
    page.wait_for_timeout(200)
    return h.evaluate(_ANIM_JS)


@pytest.fixture(scope="module")
def measured():
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
            ctx.add_init_script("try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}catch(e){}")
            page = ctx.new_page()
            res: dict = {}
            page.goto(base + "prospx/index.html", wait_until="load", timeout=60_000)
            page.wait_for_function("() => !!window.EephusState", timeout=30_000)
            res["loader"] = page.evaluate_handle(_LOADER_JS).evaluate(_ANIM_JS)
            try:
                page.wait_for_selector(".fv-badge.is-wide, .fv-badge.is-single-source, .fv-badge.is-upside, "
                                       ".fv-badge.is-breakout", state="attached", timeout=45_000)
            except Exception:
                pass
            res["badge"] = _anim(page, ".fv-badge.is-wide, .fv-badge.is-single-source, .fv-badge.is-upside, "
                                       ".fv-badge.is-breakout")
            res["foil"] = _anim(page, "span.headshot.fv-headshot-ring.card-rarity-foil")
            res["marquee"] = page.evaluate(_MARQUEE_JS)
            res["busy"] = page.evaluate("() => !!document.querySelector('#gfx-busy .px-lob .f') "
                                        "&& !document.querySelector('.gfx-busy-spin')")
            page.goto(base + "fa/index.html", wait_until="load", timeout=60_000)
            page.wait_for_selector(".eephus-export-chip", state="attached", timeout=30_000)
            res["toast"] = page.evaluate(_TOAST_JS)
            page.goto(base + "glossary/index.html", wait_until="load", timeout=60_000)
            res["highlight"] = page.evaluate(_HIGHLIGHT_JS)
            out[mode] = res
            ctx.close()
        browser.close()
    return out


def test_the_preference_changes_nothing(measured):
    assert measured["reduce"] == measured["no-preference"]


def test_m13_the_prospx_in_app_loader_is_the_lamp_loader(measured):
    for mode in MODES:
        a = measured[mode]["loader"]
        assert a == {"name": "px-lob", "duration": "1.6s", "timing": "steps(1)", "count": "infinite"}, (mode, a)


def test_m14_the_fv_badge_pulse_steps(measured):
    for mode in MODES:
        a = measured[mode]["badge"]
        if a is None:
            pytest.skip("no indicator badge on the first board page")
        assert a["name"].split(",")[0].strip() == "fvIndicatorPulse", a
        assert a["timing"].split(",")[0].strip() == "steps(1)" and a["duration"].startswith("2.4s"), (mode, a)


def test_m18_the_foil_ring_shimmers_in_whole_frames(measured):
    for mode in MODES:
        a = measured[mode]["foil"]
        if a is None:
            pytest.skip("no foil headshot on the first board page")
        names = [n.strip() for n in a["name"].split(",")]
        timings = [t.strip() for t in a["timing"].split(",")]
        assert names[0] == "foil-shift" and timings[0] == "steps(32)", (mode, a)


def test_m12_the_ribbon_marquee_moves_one_pixel_per_step(measured):
    for mode in MODES:
        m = measured[mode]["marquee"]
        px = int(round(float(m["shift"].lstrip("-").rstrip("px"))))
        assert m["timing"] == m["computed"] == f"steps({px})", (mode, m)  # end is the default


def test_m24_the_gfx_busy_overlay_draws_the_lamp_loader(measured):
    assert all(measured[mode]["busy"] for mode in MODES)


def test_m26_the_export_toast_rises_in_four_steps(measured):
    for mode in MODES:
        t = measured[mode]["toast"]
        assert t["property"] == "opacity, transform" and t["duration"] == "0.15s, 0.15s", (mode, t)
        assert t["timing"] == "steps(4, start), steps(4, start)", (mode, t)


def test_m23_the_glossary_highlight_dims_in_four_steps(measured):
    for mode in MODES:
        h = measured[mode]["highlight"]
        assert h == {"name": "glossary-highlight", "duration": "1.8s", "timing": "steps(4)"}, (mode, h)
