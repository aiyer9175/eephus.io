# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The module app loaders, the eWAR caret and the betting button run their
motion on the served pages, the same with and without Reduce Motion
(animation audit 2026-10-01, findings A02, A03, A04, A06 and A12).

The owner's asks, verbatim: "Make sure all animations run on Reduced Animation
setting, our animations are minimal and shouldn't be disabled entirely just
because of Reduce Motion" and "Ensure all animations run correctly on the site
as well".

What the audit measured, and what each test here pins on the SERVED page:

  - A02, A03: with the board payload held, /ledger/ /franchise/ /hof/
    /management/ /betting/ /pal/ /fantasy/ /trademachine/ painted no state at
    all (the four A02 boards called render() only after the fetch settled).
    Now the module root carries the lamp loader (.px-state.is-loading) whose
    frames run px-lob, 1600 ms, infinite, running; on release the loader goes
    and the board renders.
  - A04: /mlbstats/ Overall eWAR painted the unmeasured kind while
    war_leaderboards.json was in flight. Now it is the lamp loader; a 502 is
    the failed kind.
  - A06: the eWAR season caret was rebuilt already open, so its .12s turn
    never ran (0 transitionrun over 928 carets). Now one click is one
    transitionrun on transform for that caret's ::before, on open and on close.
  - A12: the betting button declared its 120 ms transition on :hover only, so
    hover-out snapped. Now the base rule carries it and both directions ease.

Every probe runs twice per page, once with prefers-reduced-motion emulated as
"reduce" and once as "no-preference", and the two results must be equal.

Playwright/chromium are OPTIONAL; the browser tests skip cleanly when they are
unavailable (mirrors test_reduced_motion_runs.py)."""
from __future__ import annotations

import pytest
from conftest import serve_site

MODES = ("reduce", "no-preference")

# (key, path, module root selector, payload URL globs to hold)
HELD = [
    ("ledger", "ledger/", "#ledger-app-root", ["**/data/ledger_board.json*"]),
    ("franchise", "franchise/", "#franchise-app-root", ["**/data/franchise_board.json*"]),
    ("hof", "hof/", "#hof-app-root", ["**/data/hof_board.json*"]),
    ("management", "management/", "#mgmt-app-root", ["**/data/management_board.json*"]),
    ("betting", "betting/", "#betting-app-root",
     ["**/data/betting.json*", "**/data/betting_preview.json*"]),
    ("pal", "pal/", "#pal-app-root", ["**/data/pal.json*"]),
    ("fantasy", "fantasy/", "#redraft-app-root", ["**/data/fantasy.json*"]),
    ("trademachine", "trademachine/", "#tradeboard-content", ["**/data/trade_values.json*"]),
    ("mlbstats_war", "mlbstats/#section=war", "#mlbstats-war-root", ["**/data/war_leaderboards.json*"]),
]

# The lamp loader inside a root: the state's classes and the first frame's
# running animation, read off the computed style and the Web Animations API.
_LAMP_JS = r"""
(sel) => {
  const root = document.querySelector(sel);
  if (!root) return {root: false};
  const st = root.querySelector('.px-state');
  const f = root.querySelector('.px-state.is-loading .px-lob .f');
  if (!f) return {root: true, state: st ? st.className : null, frame: false};
  const cs = getComputedStyle(f);
  const anims = f.getAnimations().filter((a) => a.animationName === 'px-lob');
  const a = anims[0];
  const t = a ? a.effect.getComputedTiming() : null;
  return {
    root: true, state: st.className, frame: true,
    name: cs.animationName, duration: cs.animationDuration,
    count: cs.animationIterationCount,
    wa_duration: t ? t.duration : null,
    wa_iterations: t ? String(t.iterations) : null,
    play: a ? a.playState : null,
  };
}
"""

_SETTLED_JS = r"""
(sel) => {
  const root = document.querySelector(sel);
  return !!root && !root.querySelector('.px-state.is-loading')
    && root.textContent.trim().length > 40;
}
"""

_LISTEN_JS = r"""
(prop) => {
  window.__tr = [];
  document.addEventListener('transitionrun', (e) => {
    if (e.propertyName !== prop) return;
    const t = e.target;
    window.__tr.push({
      prop: e.propertyName, pseudo: e.pseudoElement || '',
      cls: (t.getAttribute && t.getAttribute('class')) || '',
      id: (t.getAttribute && t.getAttribute('data-mlbexpand')) || '',
      dur: getComputedStyle(t, e.pseudoElement || null).transitionDuration,
    });
  }, true);
}
"""


def _context(browser, mode):
    ctx = browser.new_context(reduced_motion=mode, viewport={"width": 1280, "height": 900})
    ctx.add_init_script("try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}catch(e){}")
    return ctx


def _held_probe(browser, base, mode, path, root, globs, status=None):
    """Hold (or answer with `status`) the payload; return the loader reading,
    then release and report whether the board rendered."""
    ctx = _context(browser, mode)
    page = ctx.new_page()
    held = []

    def hold(route):
        if status is not None:
            route.fulfill(status=status, body="")
        else:
            held.append(route)

    for g in globs:
        page.route(g, hold)
    out = {}
    try:
        page.goto(base + path, wait_until="load", timeout=45_000)
        sel = root + (" .px-state.is-failed" if status else " .px-state.is-loading .px-lob .f")
        try:
            page.wait_for_selector(sel, state="attached", timeout=20_000)
        except Exception:
            pass
        page.wait_for_timeout(250)
        out["loading"] = page.evaluate(_LAMP_JS, root)
        if status is None:
            page.unroute_all(behavior="ignoreErrors")
            for r in held:
                try:
                    r.continue_()
                except Exception:
                    pass
            held.clear()
            try:
                page.wait_for_function(_SETTLED_JS, arg=root, timeout=45_000)
                out["settled"] = True
            except Exception:
                out["settled"] = False
    finally:
        for r in held:
            try:
                r.continue_()
            except Exception:
                pass
        ctx.close()
    return out


def _caret_probe(browser, base, mode):
    ctx = _context(browser, mode)
    page = ctx.new_page()
    out = {}
    try:
        page.goto(base + "mlbstats/#section=war", wait_until="load", timeout=45_000)
        page.wait_for_selector("#mlbstats-war-root .mlbx-caret", state="attached", timeout=45_000)
        page.evaluate(_LISTEN_JS, "transform")
        mid = page.evaluate("document.querySelector('#mlbstats-war-root .mlbx-caret').getAttribute('data-mlbexpand')")
        sel = f'#mlbstats-war-root .mlbx-caret[data-mlbexpand="{mid}"]'
        for step in ("open", "close"):
            page.evaluate("window.__tr = []")
            page.click(sel)
            page.wait_for_timeout(400)
            out[step] = {
                "events": page.evaluate("window.__tr"),
                "is_open": page.evaluate(f"document.querySelector('{sel}').classList.contains('is-open')"),
                "aria": page.evaluate(f"document.querySelector('{sel}').getAttribute('aria-expanded')"),
            }
        out["mid"] = mid
    finally:
        ctx.close()
    return out


def _button_probe(browser, base, mode):
    ctx = _context(browser, mode)
    page = ctx.new_page()
    out = {}
    try:
        page.goto(base + "betting/#section=mybets", wait_until="load", timeout=45_000)
        page.wait_for_selector("#betting-app-root .bt-btn", state="visible", timeout=45_000)
        page.mouse.move(1, 1)
        page.wait_for_timeout(300)
        btn = "#betting-app-root .bt-btn"
        out["base_duration"] = page.evaluate(f"getComputedStyle(document.querySelector('{btn}')).transitionDuration")
        out["base_property"] = page.evaluate(f"getComputedStyle(document.querySelector('{btn}')).transitionProperty")
        page.evaluate(_LISTEN_JS, "background-color")
        page.hover(btn)
        page.wait_for_timeout(300)
        out["in"] = page.evaluate("window.__tr.length")
        page.evaluate("window.__tr = []")
        page.mouse.move(1, 1)
        page.wait_for_timeout(300)
        out["out"] = page.evaluate("window.__tr.length")
    finally:
        ctx.close()
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
            res: dict = {}
            for key, path, root, globs in HELD:
                res[key] = _held_probe(browser, base, mode, path, root, globs)
            res["war_502"] = _held_probe(browser, base, mode, "mlbstats/#section=war",
                                         "#mlbstats-war-root", ["**/data/war_leaderboards.json*"], status=502)
            res["caret"] = _caret_probe(browser, base, mode)
            res["button"] = _button_probe(browser, base, mode)
            out[mode] = res
        browser.close()
    return out


@pytest.mark.parametrize("key", [h[0] for h in HELD])
def test_a_held_board_shows_the_running_lamp_loader_then_the_board(measured, key):
    """A02, A03 and A04: the loading kind, px-lob at 1600 ms, infinite and
    running, while the payload is held; the board once it is released."""
    for mode in MODES:
        got = measured[mode][key]
        lo = got["loading"]
        assert lo.get("frame"), f"{key} ({mode}): no lamp loader in the module root: {lo}"
        assert "is-loading" in lo["state"] and "is-unmeasured" not in lo["state"], lo
        assert lo["name"] == "px-lob", lo
        assert lo["duration"] == "1.6s" and lo["wa_duration"] == 1600, lo
        assert lo["count"] == "infinite" and lo["wa_iterations"] == "Infinity", lo
        assert lo["play"] == "running", lo
        assert got["settled"], f"{key} ({mode}): the board did not replace the loader"
    assert measured["reduce"][key] == measured["no-preference"][key]


def test_a_failed_ewar_fetch_is_the_failed_kind(measured):
    """A04: a 502 on war_leaderboards.json paints the failed kind, not the
    loader and not the unmeasured note."""
    for mode in MODES:
        st = measured[mode]["war_502"]["loading"]["state"]
        assert st and "is-failed" in st and "is-loading" not in st and "is-unmeasured" not in st, st
    assert measured["reduce"]["war_502"] == measured["no-preference"]["war_502"]


def test_the_ewar_caret_turns_on_open_and_on_close(measured):
    """A06: one transitionrun on transform for the clicked caret's ::before,
    120 ms, in each direction, and no other caret moves."""
    for mode in MODES:
        c = measured[mode]["caret"]
        for step, want_open in (("open", True), ("close", False)):
            ev = c[step]["events"]
            assert len(ev) == 1, f"{mode} {step}: {ev}"
            e = ev[0]
            assert e["prop"] == "transform" and e["pseudo"] == "::before", e
            assert "mlbx-caret" in e["cls"] and e["id"] == c["mid"], e
            assert e["dur"] == "0.12s", e
            assert c[step]["is_open"] is want_open
            assert c[step]["aria"] == ("true" if want_open else "false")
    assert measured["reduce"]["caret"] == measured["no-preference"]["caret"]


def test_the_betting_button_eases_in_and_out(measured):
    """A12: the base .bt-btn rule carries the 120 ms transition, so a
    background-color transitionrun fires on hover in and on hover out."""
    for mode in MODES:
        b = measured[mode]["button"]
        assert all(d.strip() == "0.12s" for d in b["base_duration"].split(",")), b
        assert "background-color" in b["base_property"], b
        assert b["in"] >= 1 and b["out"] >= 1, b
    assert measured["reduce"]["button"] == measured["no-preference"]["button"]
