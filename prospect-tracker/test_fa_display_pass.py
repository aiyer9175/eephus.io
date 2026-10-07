# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DISPLAY_fa (surface-quality audit 2026-10-02, findings QMLA11, QMLP04,
QMLP08, QMLP10, QMLP12, QMLC10 and the Signing Tracker closed state).

Source pins for the wiring, then one served-page pass in Chromium for what
only a browser can measure: layout shift on load, the logo size asked for,
coarse-pointer tap extents, the view tablist and the phone filter drawer.
"""
from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "fa.js").read_text(encoding="utf-8")
CSS = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    """One top-level function's source, both ends asserted."""
    head = f"function {name}("
    assert head in JS, name
    body = JS.split(head, 1)[1]
    return body.split("\n  function ", 1)[0].split("\r\n  function ", 1)[0]


# ---- QMLP08: logos at drawn size --------------------------------------------
def test_board_logos_are_asked_for_at_twice_the_drawn_size():
    assert "https://a.espncdn.com/i/teamlogos/" not in JS, "a 500 x 500 master logo URL survives"
    assert "const FA_LOGO_PX = 32;" in JS
    src = _fn("teamLogoSrc")
    assert "teamLogoURL(org, FA_LOGO_PX)" in src and "combiner/i?img=" in src


# ---- QMLP10: headshots from the payload's own mlbam -------------------------
def test_exporter_writes_mlbam_on_every_resolved_member():
    src = (ROOT / "fa_export.py").read_text(encoding="utf-8")
    block = src.split("mlbam, why = fa_ident.resolve_with_reason(", 1)[1][:900]
    assert 'm["mlbam"] = int(mlbam)' in block


def test_served_mlbam_count_equals_the_resolved_count():
    """Skips on a payload written before the field (the board then keeps the
    links-map fallback); once present, one id per resolved member."""
    for name in ("fa_class.json", "fa_class_2028.json", "fa_class_2029.json"):
        p = ROOT / "data" / name
        if not p.exists():
            continue
        cls = json.loads(p.read_text(encoding="utf-8"))
        n = sum(1 for m in cls.get("members") or [] if m.get("mlbam"))
        if not n:
            pytest.skip(f"{name} predates the mlbam field")
        h = cls.get("identity_health") or {}
        assert n == h.get("hit_resolved", 0) + h.get("pit_resolved", 0), (name, n, h)


def test_board_draws_headshots_without_the_links_map():
    photo = _fn("rowPhoto")
    assert "if (m.mlbam)" in photo and "faHeadshotURL(m.mlbam, 24)" in photo
    assert "if (!_faPhotoLegacy || !window.EEPHUS_HUB) return;" in _fn("fillRowPhotos")
    assert "_faPhotoLegacy = !cls.members.some(m => m.mlbam);" in JS
    # links() is read only by the legacy fill and by an opened card.
    callers = [f for f in ("fillRowPhotos", "renderPlayer") if "EEPHUS_HUB.links()" in _fn(f)]
    assert callers == ["fillRowPhotos", "renderPlayer"]
    assert JS.count("EEPHUS_HUB.links()") == 2


# ---- QMLP12: fa_archive only for the Archive view ---------------------------
def test_only_the_archive_view_waits_on_the_archive():
    body = JS.split("async function render()", 1)[1].split("\n  function statusChip", 1)[0]
    assert 'load("fa_archive")])' not in body
    assert 'const needArchive = state.view === "archive" && !state.player;' in body
    assert 'if (needArchive) want.push(load("fa_archive"));' in body
    assert "requestIdleCallback" in body


# ---- QMLP04 ----------------------------------------------------------------
def test_tall_views_hold_a_viewport_while_loading():
    assert ".fa-app #fa-rows.fa-hold:has(> .px-state.is-loading) { min-height: 100vh; }" in CSS
    page = (ROOT / "fa" / "index.html").read_text(encoding="utf-8")
    assert 'id="fa-rows" class="fa-hold"' in page
    assert 'classList.toggle("fa-hold", !state.player && state.view !== "tracker")' in JS


# ---- QMLC10 ----------------------------------------------------------------
def test_value_map_legend_names_the_line_and_the_colour():
    vm = _fn("faValueMap")
    assert "above the line = value, below = overpay" not in JS
    assert "above the line: rational value over price" in vm
    assert "colour: verdict (Deal+ band ${bandWhere})" in vm
    assert 'edges.band_mode === "group" ? "within position group" : "corpus-wide"' in vm


# ---- Signing Tracker closed state (sitepass section 5) ---------------------
def test_closed_tracker_uses_the_unmeasured_state():
    tr = _fn("renderTracker")
    assert 'pxState("unmeasured"' in tr
    assert "state-message" not in tr


# ---- served page -----------------------------------------------------------
_PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                     "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082")
_CLS_INIT = """window.__cls = 0; new PerformanceObserver(l => { for (const e of l.getEntries())
  if (!e.hadRecentInput) window.__cls += e.value; }).observe({type: 'layout-shift', buffered: true});"""


@pytest.fixture(scope="module")
def site():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    from conftest import serve_site
    with serve_site() as base, sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"chromium unavailable: {e}")
        yield base, b
        b.close()


@contextlib.contextmanager
def _page(site, w, h, hash_="", coarse=False):
    base, b = site
    ctx = b.new_context(viewport={"width": w, "height": h}, is_mobile=coarse, has_touch=coarse)
    ctx.add_init_script(_CLS_INIT)
    logos = []

    def _logo(route):
        logos.append(route.request.url)
        route.fulfill(status=200, content_type="image/png", body=_PNG)
    ctx.route(re.compile(r"^https://a\.espncdn\.com/.*"), _logo)
    ctx.route(re.compile(r"^https://img\.mlbstatic\.com/.*"),
              lambda r: r.fulfill(status=200, content_type="image/png", body=_PNG))
    ctx.route(re.compile(r"^(?!http://127\.0\.0\.1:|https://a\.espncdn\.com/|https://img\.mlbstatic\.com/).*"),
              lambda r: r.abort())
    page = ctx.new_page()
    try:
        page.goto(base + "fa/" + hash_, wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(500)
        yield page, logos
    finally:
        ctx.close()


def test_board_load_is_stable_and_logos_are_small(site):
    with _page(site, 1280, 900) as (page, logos):
        page.wait_for_selector("table.fa-board-table tbody tr[data-key]")
        cls = page.evaluate("window.__cls")
        assert cls < 0.1, f"board CLS {cls:.3f}"
        assert logos, "no logo was requested"
        big = [u for u in logos if "&w=32" not in u]
        assert not big, big[:3]
        tabs = page.evaluate("""() => ({
            lists: document.querySelectorAll('#fa-view-chips [role=tablist]').length,
            tabs: document.querySelectorAll('#fa-view-chips [role=tab]').length,
            on: document.querySelectorAll('#fa-view-chips [role=tab][aria-selected=true]').length})""")
        assert tabs == {"lists": 1, "tabs": 5, "on": 1}, tabs
        assert page.evaluate("getComputedStyle(document.getElementById('fa-filter-toggle')).display") == "none"


_TAP = r"""
() => {
  const hit = (el, x, y) => { const t = document.elementFromPoint(x, y); return !!t && (t === el || el.contains(t)); };
  const ext = el => { const r = el.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    let u = 0, d = 0, l = 0, rr = 0;
    while (u < 80 && hit(el, cx, cy - u - 1)) u++;  while (d < 80 && hit(el, cx, cy + d + 1)) d++;
    while (l < 80 && hit(el, cx - l - 1, cy)) l++;   while (rr < 80 && hit(el, cx + rr + 1, cy)) rr++;
    return [l + rr + 1, u + d + 1]; };
  const pick = s => [...document.querySelectorAll(s)].filter(e => { const r = e.getBoundingClientRect();
    return r.width > 0 && r.top > 80 && r.bottom < innerHeight - 10; }).slice(0, 12).map(ext);
  return {band: pick('table.fa-board-table [data-band]'), verdict: pick('table.fa-board-table .fa-verdict')};
}
"""


def test_phone_tap_targets_and_filter_drawer(site):
    """QMLA11: with a coarse pointer the band and verdict cells take the tap
    over the whole cell, 44px tall and at least 44px wide at 390."""
    with _page(site, 390, 844, coarse=True) as (page, _):
        page.wait_for_selector("table.fa-board-table tbody tr[data-key]")
        page.evaluate("window.scrollTo(0, document.querySelector('table.fa-board-table').getBoundingClientRect().top + scrollY - 60)")
        page.wait_for_timeout(200)
        t = page.evaluate(_TAP)
        for k in ("band", "verdict"):
            assert t[k], f"no {k} target on screen"
            assert min(w for w, _ in t[k]) >= 44 and min(h for _, h in t[k]) >= 44, (k, t[k])
        assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0
        bar = "getComputedStyle(document.getElementById('fa-filter-bar')).display"
        assert page.evaluate(bar) == "none"
        page.click("#fa-filter-toggle")
        assert page.evaluate(bar) != "none"
        assert page.get_attribute("#fa-filter-toggle", "aria-expanded") == "true"


def test_closed_tracker_paints_the_pixel_state(site):
    cls = json.loads((ROOT / "data" / "fa_class.json").read_text(encoding="utf-8"))
    if cls.get("events") or any(m.get("status") == "signed" for m in cls.get("members") or []):
        pytest.skip("the winter has opened")
    with _page(site, 1280, 900, "#view=tracker") as (page, _):
        page.wait_for_selector("#fa-rows .px-state.is-unmeasured")
        assert "has not opened" in page.inner_text("#fa-rows")
        assert page.evaluate("window.__cls") < 0.1
