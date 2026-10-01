# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The homepage blink dots and the 404 foul ball play as written, with and
without Reduce Motion (owner asks, 2026-10-01: "Make sure all animations run on
Reduced Animation setting" and "Ensure all animations run correctly on the site
as well").

Two findings from the 2026-10-01 animation audit, checked on the SERVED pages
through the shared harness (conftest.serve_site) in headless Chromium, once per
prefers-reduced-motion mode ("reduce" and "no-preference"), and the two modes
must measure the same:

  A08  The WIRE tag dot (.home-ticker .ticker-tag .blip) and the sidebar feed
       dot (.sb-feed .feed-head .blip) blink between two states. They ran
       ticker-blip with steps(2), which steps inside each keyframe interval,
       so the sampled opacity walked 1, 0.625, 0.25, 0.625. With step-end the
       dot holds 1 for 0.7 s, then .25 for 0.7 s. Sampled every 50 ms for
       1.5 s, the distinct values are exactly {1, 0.25}, and the running
       animation is ticker-blip, 1400 ms, infinite, playState running.
  A10  The 404 foul ball (svg.px-foul, 11 trail lamps and 11 ball frames)
       plays once in 0.75 s: every one of the 22 rects starts and ends, the
       last animationend lands 0.75 s (plus or minus 0.1 s) after the first
       animationstart, and the final frame shows all 11 trail lamps and the
       last ball (.z) lit with the other 10 ball frames dark.

Playwright/chromium are OPTIONAL; the browser tests skip cleanly when they are
unavailable (mirrors test_reduced_motion_runs.py)."""
from __future__ import annotations

import pytest
from conftest import serve_site

MODES = ("reduce", "no-preference")
BLIPS = (".home-ticker .ticker-tag .blip", ".sb-feed .feed-head .blip")

# Animation events bubble, so a capturing window listener registered before
# any page script sees every rect of the 404 art from its first frame.
_FOUL_LOG_INIT = r"""
window.__foulLog = [];
const __foulRec = (e) => {
  const t = e.target;
  if (!(t instanceof Element) || !t.closest || !t.closest('svg.px-foul')) return;
  const rects = Array.from(document.querySelectorAll('svg.px-foul rect'));
  window.__foulLog.push({type: e.type, i: rects.indexOf(t), name: e.animationName, t: performance.now()});
};
window.addEventListener('animationstart', __foulRec, true);
window.addEventListener('animationend', __foulRec, true);
"""

_SAMPLE_JS = r"""
async (sels) => {
  const out = {};
  for (const s of sels) out[s] = [];
  for (let i = 0; i < 31; i++) {
    for (const s of sels) {
      const el = document.querySelector(s);
      out[s].push(el ? parseFloat(getComputedStyle(el).opacity) : null);
    }
    await new Promise((r) => setTimeout(r, 50));
  }
  return out;
}
"""

_ANIMS_JS = r"""
(sels) => sels.map((s) => {
  const el = document.querySelector(s);
  if (!el) return null;
  return el.getAnimations().map((a) => {
    const t = a.effect.getTiming();
    return {name: a.animationName, duration: t.duration,
            iterations: String(t.iterations), playState: a.playState};
  });
})
"""

_FOUL_FINAL_JS = r"""
() => {
  const svg = document.querySelector('svg.px-foul');
  if (!svg) return null;
  const op = (el) => parseFloat(getComputedStyle(el).opacity);
  const t = Array.from(svg.querySelectorAll('rect.t'));
  const b = Array.from(svg.querySelectorAll('rect.b:not(.z)'));
  const z = svg.querySelector('rect.b.z');
  return {
    rects: svg.querySelectorAll('rect').length,
    trail_total: t.length, trail_lit: t.filter((el) => op(el) === 1).length,
    balls_total: b.length, balls_dark: b.filter((el) => op(el) === 0).length,
    z_lit: !!z && op(z) === 1,
  };
}
"""


@pytest.fixture(scope="module")
def measured():
    """{mode: {...}} for both reduced-motion modes, from one chromium launch."""
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
            ctx.add_init_script(_FOUL_LOG_INIT)
            page = ctx.new_page()
            res: dict = {}

            page.goto(base + "index.html", wait_until="load", timeout=30_000)
            res["emulated"] = page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
            samples = page.evaluate(_SAMPLE_JS, list(BLIPS))
            res["blip_values"] = {s: sorted({round(v, 4) for v in vals if v is not None})
                                  for s, vals in samples.items()}
            res["blip_missing"] = [s for s, vals in samples.items() if any(v is None for v in vals)]
            res["blip_anims"] = dict(zip(BLIPS, page.evaluate(_ANIMS_JS, list(BLIPS))))

            page.goto(base + "404.html", wait_until="load", timeout=30_000)
            page.wait_for_timeout(1500)
            log = page.evaluate("window.__foulLog")
            starts = [e for e in log if e["type"] == "animationstart"]
            ends = [e for e in log if e["type"] == "animationend"]
            res["foul_started"] = sorted({e["i"] for e in starts})
            res["foul_ended"] = sorted({e["i"] for e in ends})
            res["foul_span_s"] = ((max(e["t"] for e in ends) - min(e["t"] for e in starts)) / 1000
                                  if starts and ends else None)
            res["foul_final"] = page.evaluate(_FOUL_FINAL_JS)
            out[mode] = res
            ctx.close()
        browser.close()
    return out


def _other(mode: str) -> str:
    return MODES[1] if mode == MODES[0] else MODES[0]


@pytest.mark.parametrize("mode", MODES)
def test_the_preference_is_emulated(measured, mode):
    assert measured[mode]["emulated"] is (mode == "reduce")


@pytest.mark.parametrize("mode", MODES)
def test_a08_blink_dots_hold_two_states(measured, mode):
    res = measured[mode]
    assert not res["blip_missing"], f"blink dot absent on /: {res['blip_missing']}"
    for sel in BLIPS:
        assert res["blip_values"][sel] == [0.25, 1.0], (sel, res["blip_values"][sel])
        anims = res["blip_anims"][sel]
        assert anims == [{"name": "ticker-blip", "duration": 1400,
                          "iterations": "Infinity", "playState": "running"}], (sel, anims)
    other = measured[_other(mode)]
    assert res["blip_values"] == other["blip_values"]
    assert res["blip_anims"] == other["blip_anims"]


@pytest.mark.parametrize("mode", MODES)
def test_a10_foul_ball_plays_once_in_075s(measured, mode):
    res = measured[mode]
    final = res["foul_final"]
    assert final is not None, "svg.px-foul absent on /404.html"
    assert final["rects"] == 22, final
    assert res["foul_started"] == list(range(22)), res["foul_started"]
    assert res["foul_ended"] == list(range(22)), res["foul_ended"]
    assert res["foul_span_s"] is not None and abs(res["foul_span_s"] - 0.75) <= 0.1, res["foul_span_s"]
    assert final == {"rects": 22, "trail_total": 11, "trail_lit": 11,
                     "balls_total": 10, "balls_dark": 10, "z_lit": True}, final
    other = measured[_other(mode)]
    assert res["foul_started"] == other["foul_started"]
    assert res["foul_ended"] == other["foul_ended"]
    assert res["foul_final"] == other["foul_final"]
    assert abs(res["foul_span_s"] - other["foul_span_s"]) <= 0.1
