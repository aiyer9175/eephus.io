# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The shared export feedback (the copy/export toast of eephus-export.js and
the GFX modal flash of eephus-gfx.js) eases in and out on the served page, the
same with and without Reduce Motion (animation audit 2026-10-01, findings A07
and A15).

The owner's asks, verbatim: "Make sure all animations run on Reduced Animation
setting, our animations are minimal and shouldn't be disabled entirely just
because of Reduce Motion" and "Ensure all animations run correctly on the site
as well".

What the audit measured, and what each test here pins on the SERVED /fa/ page:

  - A07: toast() created the toast, appended it and added is-on in one task,
    so the first toast of a page had no before-change style and popped in
    (opacity 1 at 60 ms, no transitionrun on show); later toasts eased.
    Now the first toast is mid-ease at 60 ms and a 150 ms opacity
    transitionrun fires on its show, as on the second.
  - A15: the GFX flash hide timer was never kept, so a second flash 800 ms
    after the first was hidden about 1600 ms after the FIRST. Now the hide
    lands about 1600 ms after the second; the first flash also eases in, so a
    200 ms opacity transitionrun fires on show and on hide.

Every probe runs once with prefers-reduced-motion emulated as "reduce" and
once as "no-preference", and the two (timing-free) summaries must be equal.

Playwright/chromium are OPTIONAL; the browser tests skip cleanly when they are
unavailable (mirrors test_reduced_motion_runs.py)."""
from __future__ import annotations

import pytest
from conftest import serve_site

MODES = ("reduce", "no-preference")

# In-page recorder: the time each feedback element gains or loses its "on"
# class, its computed opacity 60 ms after each show, and every transitionrun
# it fires. Read in the page so Playwright round trips add no jitter.
_RECORDER_JS = r"""
() => {
  const W = window.__fb = {shows: [], hides: [], runs: []};
  const ON = {'eephus-export-toast': 'is-on', 'egfx-flash': 'is-show'};
  const kind = (el) => Object.keys(ON).find((k) => el.classList && el.classList.contains(k));
  const state = new WeakMap();
  const look = (el) => {
    const k = kind(el);
    if (!k) return;
    const on = el.classList.contains(ON[k]);
    if (state.get(el) === on) return;
    state.set(el, on);
    const at = performance.now();
    if (on) {
      const rec = {k, at, op60: null};
      W.shows.push(rec);
      // Read on the first painted frame at or after 60 ms: a bare timer can
      // land before any frame, where the read itself starts the transition.
      const tick = () => {
        if (performance.now() - at >= 60) rec.op60 = Number(getComputedStyle(el).opacity);
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    } else if (state.has(el)) {
      W.hides.push({k, at});
    }
  };
  new MutationObserver((ms) => {
    for (const m of ms) {
      if (m.type === 'attributes') look(m.target);
      else m.addedNodes.forEach((n) => { if (n.nodeType === 1) look(n); });
    }
  }).observe(document.body, {subtree: true, childList: true, attributes: true, attributeFilter: ['class']});
  document.addEventListener('transitionrun', (e) => {
    const k = kind(e.target);
    if (!k || e.propertyName !== 'opacity') return;
    W.runs.push({k, at: performance.now(),
      dur: getComputedStyle(e.target).transitionDuration});
  }, true);
}
"""


def _context(browser, mode):
    ctx = browser.new_context(reduced_motion=mode, viewport={"width": 1280, "height": 900},
                              permissions=["clipboard-read", "clipboard-write"])
    ctx.add_init_script("try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}catch(e){}")
    return ctx


def _runs_near(fb, k, at, window_ms=300):
    return [r for r in fb["runs"] if r["k"] == k and at - 5 <= r["at"] <= at + window_ms]


def _toast_probe(browser, base, mode):
    """Two export copies on /fa/ through the export chip menu; summarize each
    toast's show (opacity at 60 ms, opacity transitionrun) and hide."""
    ctx = _context(browser, mode)
    page = ctx.new_page()
    out = []
    try:
        page.goto(base + "fa/", wait_until="load", timeout=45_000)
        page.wait_for_selector(".eephus-exportable .eephus-export-chip", state="attached", timeout=45_000)
        page.wait_for_timeout(500)
        page.evaluate(_RECORDER_JS)
        for _ in range(2):
            host = page.locator(".eephus-exportable").first
            host.scroll_into_view_if_needed()
            host.hover()
            page.wait_for_timeout(250)
            page.locator(".eephus-exportable:hover > .eephus-export-chip").first.click()
            page.wait_for_selector(".ex-menu-item", state="visible", timeout=10_000)
            page.locator(".ex-menu-item").first.click()
            page.wait_for_timeout(2400)
        fb = page.evaluate("window.__fb")
        shows = [s for s in fb["shows"] if s["k"] == "eephus-export-toast"]
        hides = [h for h in fb["hides"] if h["k"] == "eephus-export-toast"]
        for i, s in enumerate(shows):
            show_runs = _runs_near(fb, s["k"], s["at"])
            hide = hides[i] if i < len(hides) else None
            out.append({
                "mid_ease_at_60ms": s["op60"] is not None and 0 < s["op60"] < 1,
                "show_runs": [r["dur"] for r in show_runs],
                "hide_after_ms": round((hide["at"] - s["at"]) / 100) * 100 if hide else None,
                "hide_runs": [r["dur"] for r in _runs_near(fb, s["k"], hide["at"])] if hide else [],
            })
        out.append({"text": page.evaluate("document.getElementById('eephus-export-toast').textContent")})
    finally:
        ctx.close()
    return out


def _flash_probe(browser, base, mode):
    """Open the /fa/ class board GFX modal, then two downloads 800 ms apart
    (the hub export is stubbed to resolve at once so only the flash timing is
    measured); summarize when the flash shows, whether it still shows 1500 ms
    after the first, and when it hides."""
    ctx = _context(browser, mode)
    page = ctx.new_page()
    try:
        page.goto(base + "fa/", wait_until="load", timeout=45_000)
        page.wait_for_selector(".egfx-chip", state="visible", timeout=45_000)
        page.locator(".egfx-chip").first.click()
        page.wait_for_selector("#egfx-preview canvas", state="attached", timeout=30_000)
        page.evaluate("window.EEPHUS_HUB.exportCanvas = () => Promise.resolve('downloaded')")
        page.evaluate(_RECORDER_JS)
        at1500 = page.evaluate(r"""
          () => new Promise((done) => {
            const btn = document.getElementById('egfx-download');
            btn.click();
            setTimeout(() => btn.click(), 800);
            setTimeout(() => {
              const f = document.querySelector('.egfx-flash');
              done(!!f && f.classList.contains('is-show'));
            }, 1500);
          })
        """)
        page.wait_for_timeout(1600)
        fb = page.evaluate("window.__fb")
    finally:
        ctx.close()
    shows = [s for s in fb["shows"] if s["k"] == "egfx-flash"]
    hides = [h for h in fb["hides"] if h["k"] == "egfx-flash"]
    first = shows[0] if shows else None
    hide = hides[0] if hides else None
    # The second click re-adds is-show to a shown flash; its time is the
    # second click's, 800 ms after the first, which the recorder cannot see as
    # a class change. Measure the hide from the first show instead.
    return {
        "show_count": len(shows),
        "first_mid_ease_at_60ms": bool(first) and first["op60"] is not None and 0 < first["op60"] < 1,
        "shown_at_1500": at1500,
        "hide_count": len(hides),
        "hide_after_first_ms": (round((hide["at"] - first["at"]) / 100) * 100) if (hide and first) else None,
        "show_runs": [r["dur"] for r in _runs_near(fb, "egfx-flash", first["at"])] if first else [],
        "hide_runs": [r["dur"] for r in _runs_near(fb, "egfx-flash", hide["at"])] if hide else [],
    }


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
            out[mode] = {
                "toast": _toast_probe(browser, base, mode),
                "flash": _flash_probe(browser, base, mode),
            }
        browser.close()
    return out


def _all_150(durs):
    return bool(durs) and all(
        all(part.strip() == "0.15s" for part in d.split(",")) for d in durs)


def test_the_first_export_toast_eases_in_like_the_second(measured):
    """A07: the first toast of the page is mid-ease 60 ms after its show and
    fires a 150 ms opacity transitionrun on show, like the second, and both
    hide through the same transition after 1900 ms."""
    for mode in MODES:
        t = measured[mode]["toast"]
        assert len(t) == 3, f"{mode}: expected two toasts, got {t}"
        assert t[-1]["text"].startswith("Copied as"), t
        for i, show in enumerate(t[:2]):
            assert show["mid_ease_at_60ms"], f"{mode} toast {i + 1} popped in: {show}"
            assert _all_150(show["show_runs"]), f"{mode} toast {i + 1}: no 150 ms opacity run on show: {show}"
            assert show["hide_after_ms"] == 1900, f"{mode} toast {i + 1}: {show}"
            assert _all_150(show["hide_runs"]), f"{mode} toast {i + 1}: no 150 ms opacity run on hide: {show}"
    assert measured["reduce"]["toast"] == measured["no-preference"]["toast"]


def test_a_second_gfx_flash_keeps_its_own_hide_timer(measured):
    """A15: two flashes 800 ms apart: still shown 1500 ms after the first,
    hidden about 1600 ms after the second (2400 ms after the first), and a
    200 ms opacity transitionrun fires on show and on hide."""
    for mode in MODES:
        f = measured[mode]["flash"]
        assert f["show_count"] == 1 and f["hide_count"] == 1, f"{mode}: {f}"
        assert f["shown_at_1500"] is True, f"{mode}: {f}"
        assert f["hide_after_first_ms"] == 2400, f"{mode}: hidden early or late: {f}"
        assert f["first_mid_ease_at_60ms"], f"{mode}: the first flash popped in: {f}"
        assert f["show_runs"] == ["0.2s"], f"{mode}: {f}"
        assert f["hide_runs"] == ["0.2s"], f"{mode}: {f}"
    assert measured["reduce"]["flash"] == measured["no-preference"]["flash"]
