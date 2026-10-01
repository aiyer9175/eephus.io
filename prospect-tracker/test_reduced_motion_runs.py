# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Reduce Motion does not disable the site's animations (owner, 2026-10-01).

The owner's ask, verbatim: "Make sure all animations run on Reduced Animation
setting, our animations are minimal and shouldn't be disabled entirely just
because of Reduce Motion". Until this file, assets/site.css carried a global
reduced-motion reset (animation-duration .001ms, iteration-count 1, transition
shortening, all !important) plus per-feature stops, so a reader with the OS
setting on saw every animation collapse to its last frame.

This test drives headless Chromium twice per page through the shared harness
(conftest.serve_site), once with prefers-reduced-motion emulated as "reduce"
(Playwright's reducedMotion context option) and once as "no-preference", and
asserts on the SERVED pages:

  - the computed animation-duration and iteration count of the wire ticker and
    a blink dot (homepage), the lamp loader (the shipped EephusState loading
    scene, drawn on the 404 page, which loads the component), the 404 foul
    ball and a PROSPX headshot's foil ring are the same with and without the
    preference, and none is 0.001ms;
  - no rule inside a (prefers-reduced-motion: reduce) query in any stylesheet
    the page loads (site.css, the PROSPX <style>, injected sheets) sets
    animation: none, an animation-duration under 0.1s, animation-iteration-
    count: 1 or transition: none. Nothing is allowlisted.

The one exception the policy keeps, the pointer-tracking background parallax,
is JavaScript (assets/eephus-bg.js), not a stylesheet rule, so the stylesheet
scan needs no allowlist.

Playwright/chromium are OPTIONAL; the browser tests skip cleanly when they are
unavailable (mirrors test_index_html_loads.py)."""
from __future__ import annotations

import pytest
from conftest import serve_site

MODES = ("reduce", "no-preference")

# Walk every stylesheet the page loaded (same origin, plus inline and injected
# <style>) and return each rule nested in a reduced-motion media query that
# stills, shortens or switches off motion.
_SCAN_JS = r"""
() => {
  const bad = [], seen = [];
  const secs = (v) => {
    v = (v || '').trim();
    if (!v) return null;
    return v.split(',').map((t) => {
      t = t.trim();
      if (t.endsWith('ms')) return parseFloat(t) / 1000;
      if (t.endsWith('s')) return parseFloat(t);
      return NaN;
    });
  };
  const check = (rule, where) => {
    const s = rule.style;
    if (!s) return;
    const why = [];
    const name = s.getPropertyValue('animation-name').trim();
    const anim = s.getPropertyValue('animation').trim();
    if (name === 'none' || anim === 'none' || /(^|\s)none(\s|$)/.test(anim)) why.push('animation: none');
    const d = secs(s.getPropertyValue('animation-duration'));
    if (d && d.some((x) => x < 0.1)) why.push('animation-duration under 0.1s');
    const ic = s.getPropertyValue('animation-iteration-count').trim();
    if (ic === '1') why.push('animation-iteration-count: 1');
    const tp = s.getPropertyValue('transition-property').trim();
    const tr = s.getPropertyValue('transition').trim();
    if (tp === 'none' || tr === 'none' || /^none(\s|$)/.test(tr)) why.push('transition: none');
    const td = secs(s.getPropertyValue('transition-duration'));
    if (td && td.some((x) => x < 0.1)) why.push('transition-duration under 0.1s');
    if (why.length) bad.push(where + ' :: ' + rule.cssText + ' :: ' + why.join(', '));
  };
  const walk = (rules, inReduce, where) => {
    for (const r of Array.from(rules || [])) {
      const cond = (r.conditionText || (r.media && r.media.mediaText) || '');
      const reduce = inReduce || (/prefers-reduced-motion/.test(cond) && /reduce/.test(cond));
      if (r.cssRules && r.cssRules.length) {
        if (reduce && !inReduce) seen.push(where + ' @media ' + cond);
        walk(r.cssRules, reduce, where);
      } else if (inReduce) {
        check(r, where);
      }
    }
  };
  for (const sh of Array.from(document.styleSheets)) {
    let rules;
    try { rules = sh.cssRules; } catch (e) { continue; }
    walk(rules, false, sh.href || ('inline <style> #' + Array.from(document.styleSheets).indexOf(sh)));
  }
  return {bad, seen, sheets: document.styleSheets.length};
}
"""

_MEASURE_JS = r"""
(sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const cs = getComputedStyle(el);
  return {name: cs.animationName, duration: cs.animationDuration,
          count: cs.animationIterationCount};
}
"""

# The lamp state: the shipped component's loading scene, drawn into the page by
# the same call every module makes (window.EephusState.render).
_LAMP_JS = r"""
() => {
  const host = document.createElement('div');
  host.id = 'rm-lamp-probe';
  document.body.prepend(host);
  window.EephusState.render(host, 'loading', 'Loading');
  return !!host.querySelector('.px-lob .f');
}
"""


# A board headshot's foil ring. The bare .card-rarity-foil selector first
# matched a rank diamond, which is static by spec and opts out of the loop
# (A09, 2026-10-01).
_FOIL_RING = "span.headshot.fv-headshot-ring.card-rarity-foil"


def _seconds(v: str) -> float:
    v = v.split(",")[0].strip()
    return float(v[:-2]) / 1000 if v.endswith("ms") else float(v[:-1])


@pytest.fixture(scope="module")
def measured():
    """{mode: {probe: computed animation, 'scan:<page>': scan}} for both modes,
    from one chromium launch."""
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
            ctx.add_init_script(
                "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}catch(e){}")
            page = ctx.new_page()
            res: dict = {}

            page.goto(base + "index.html", wait_until="load", timeout=30_000)
            res["emulated"] = page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
            res["ticker"] = page.evaluate(_MEASURE_JS, ".home-ticker .ticker-track")
            res["blink"] = page.evaluate(_MEASURE_JS, ".home-ticker .ticker-tag .blip")
            res["scan:home"] = page.evaluate(_SCAN_JS)

            page.goto(base + "404.html", wait_until="load", timeout=30_000)
            res["foul"] = page.evaluate(_MEASURE_JS, ".px-foul .b")
            assert page.evaluate(_LAMP_JS), "EephusState drew no lamp loader"
            res["lamp"] = page.evaluate(_MEASURE_JS, "#rm-lamp-probe .px-lob .f")
            res["scan:404"] = page.evaluate(_SCAN_JS)

            page.goto(base + "prospx/index.html", wait_until="load", timeout=30_000)
            try:
                page.wait_for_selector(_FOIL_RING, state="attached", timeout=45_000)
            except Exception:
                pass
            res["foil"] = page.evaluate(_MEASURE_JS, _FOIL_RING)
            res["scan:prospx"] = page.evaluate(_SCAN_JS)
            out[mode] = res
            ctx.close()
        browser.close()
    return out


def test_the_preference_is_emulated(measured):
    assert measured["reduce"]["emulated"] is True
    assert measured["no-preference"]["emulated"] is False


@pytest.mark.parametrize("probe,name", [
    ("ticker", "ticker-scroll"),
    ("blink", "ticker-blip"),
    ("lamp", "px-lob"),
    ("foul", "px-show"),
    ("foil", "foil-shift"),
])
def test_each_animation_runs_the_same_under_reduce_motion(measured, probe, name):
    on, off = measured["reduce"][probe], measured["no-preference"][probe]
    assert off is not None and on is not None, f"{probe}: element not found on the served page"
    assert off["name"] == name, off
    assert on == off, f"{probe}: {on} under Reduce Motion, {off} without it"
    assert on["duration"] != "0.001ms" and _seconds(on["duration"]) >= 0.01, on
    if probe in ("ticker", "blink", "lamp", "foil"):
        assert on["count"] == "infinite", on


@pytest.mark.parametrize("page_key", ["scan:home", "scan:404", "scan:prospx"])
def test_no_reduced_motion_rule_stills_anything(measured, page_key):
    for mode in MODES:
        scan = measured[mode][page_key]
        assert scan["sheets"] > 0
        assert not scan["bad"], "\n".join(scan["bad"])
