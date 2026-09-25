# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""An eFV card whose dollar fan cannot hold beside its P(bust) says why.

WHY THIS EXISTS (census M01-08, 2026-09-24, two verifiers CONFIRMED). The eFV P(bust) is the
Platt-calibrated outcome odds; the dollar fan is priced from the uncalibrated outcome mix at
the display grade. The bust bucket prices at the $0.7M floor, so a P(bust) of 35% should put
P10 and P25 on that floor, yet Jesus Made's card printed P(bust) 35% beside P10 $26.8M. On
146 of 4,679 graded pages at least one of P10 / P25 / P50 contradicts P(bust) this way.

Pricing the fan from the calibrated mix moves served dollars and needs an owner call or a
registered gate, so it is not done here. What is pinned: those cards carry a visible
two-bases note, and cards where the two agree do not.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def test_the_conflict_rule_matches_the_floor_arithmetic():
    mr = pytest.importorskip("py_mini_racer")
    src = _src()
    m = re.search(r"^const _EFV_FAN_FLOOR_MM = [^\n]*\n^function efvFanBasisConflict\(x\) \{.*?\n\}\n",
                  src, re.S | re.M)
    assert m, "efvFanBasisConflict is missing"
    ctx = mr.MiniRacer()
    ctx.eval(m.group(0))
    cases = [
        ({"p_bust": 0.349, "dist": {"p10_mm": 26.8, "p25_mm": 47.4, "p50_mm": 90}}, True),
        ({"p_bust": 0.30, "dist": {"p10_mm": 0.7, "p25_mm": 12.0, "p50_mm": 40}}, True),
        ({"p_bust": 0.60, "dist": {"p10_mm": 0.7, "p25_mm": 0.7, "p50_mm": 39.3}}, True),
        ({"p_bust": 0.60, "dist": {"p10_mm": 0.7, "p25_mm": 0.7, "p50_mm": 0.7}}, False),
        ({"p_bust": 0.05, "dist": {"p10_mm": 30.0, "p25_mm": 50.0, "p50_mm": 90}}, False),
        ({"p_bust": 0.20, "dist": {"p10_mm": 0.7, "p25_mm": 9.0, "p50_mm": 20}}, False),
        ({"p_bust": None, "dist": {"p10_mm": 30.0}}, False),
    ]
    got = json.loads(ctx.eval("JSON.stringify(%s.map(x => efvFanBasisConflict(x)))"
                              % json.dumps([c for c, _ in cases])))
    assert got == [w for _, w in cases]


@pytest.fixture(scope="module")
def booted_page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page()
        page.add_init_script(
            "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}catch(e){}")
        errs: list[str] = []
        page.on("pageerror", lambda err: errs.append(err.message))
        page.goto(base + "prospx/index.html", wait_until="load", timeout=60_000)
        page.wait_for_function(
            "() => document.querySelectorAll('#rows .player-row').length > 5", timeout=120_000)
        # Let the provisional pool land first: its arrival re-renders the view.
        try:
            page.wait_for_function(
                "() => typeof provPlayers === 'function' && provPlayers().length > 0",
                timeout=60_000)
        except Exception:
            pass
        page.wait_for_timeout(800)
        yield page, errs
        browser.close()


def _open(page, key):
    name = page.evaluate(
        f"() => (DATA.players.find(p => p.player_key === '{key}') || {{}}).player_name || ''")
    page.evaluate(f"() => {{ location.hash = 'player={key}'; }}")
    # Wait for THIS player's page, not a previous one still in the body.
    page.wait_for_function(
        "(nm) => { const b = document.getElementById('player-detail-body');"
        " return b && /Surplus value/.test(b.innerText) && b.innerText.includes(nm); }",
        arg=name, timeout=30_000)
    return page.evaluate(
        "() => { const n = document.querySelector('#player-detail-body .efv-basis-note');"
        " return n ? n.innerText : null; }")


def test_conflicting_cards_carry_the_note_and_agreeing_cards_do_not(booted_page):
    page, errs = booted_page
    keys = page.evaluate("""() => {
      const g = DATA.players.filter(p => p && p.player_key && getEfv(p) && getEfv(p).surplus_mm != null);
      const bad = g.filter(p => efvFanBasisConflict(getEfv(p)));
      const ok = g.filter(p => !efvFanBasisConflict(getEfv(p)) && getEfv(p).dist
                             && getEfv(p).dist.p50_mm != null);
      return {n: g.length, nBad: bad.length, bad: bad.slice(0, 1).map(p => p.player_key),
              ok: ok.slice(0, 1).map(p => p.player_key)};
    }""")
    assert keys["n"] > 1000
    if not keys["bad"]:
        pytest.skip("no card's fan contradicts its P(bust) on this artifact")
    note = _open(page, keys["bad"][0])
    assert note and "Two bases" in note and "P(bust)" in note, (
        f"{keys['bad'][0]}: the fan contradicts P(bust) and the card does not say why")
    if keys["ok"]:
        assert _open(page, keys["ok"][0]) is None
    assert not errs, "JS errors: " + " | ".join(errs)
