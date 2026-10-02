# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A graduate's PROSPX card prints no ETA and never says he is awaiting a pro debut.

RPR04 (served-number reconciliation audit, 2026-10-01): every graduate record in the
debuts slice still carries its last pre-debut ETA, and the card printed it under the
Debuted pill: collin_snider 'Late 2028, P(debut) 1y 77%' beside 'Debuted 2022-04-09'.
ETA is the estimated MLB arrival year, so a graduate has none; etaServed(p) returns
null for status 'debuted' and every card surface that printed it reads that helper.

RPR05: efv_score flags xfv_provisional on any row with no MiLB line, debuted rows
included, and the card header then read 'prior-anchored, awaiting pro debut' for a
player with an MLB debut (charlie_leesman, debuted 2013-04-01). gradeBlock now keeps
priorAnchored false on kind 'debuted', and the header reads 'locked at debut'.

Every check reads the SERVED artifacts and the served page.
"""
from __future__ import annotations

import pytest
from conftest import load_data_doc, serve_site

PROSPX = "prospx/index.html"
GRAD_KEYS = ("collin_snider", "charlie_leesman", "shane_drohan")
ACTIVE_KEY = "jacob_reimer"


def _debuts():
    d = load_data_doc("debuts.json")
    if not isinstance(d, list) or not d:
        pytest.skip("debuts.json not built")
    return d


def test_every_debuts_row_is_status_debuted():
    """The display gate keys on status 'debuted'; the slice must carry it on every row."""
    rows = _debuts()
    bad = [r.get("player_key") for r in rows if r.get("status") != "debuted"]
    assert not bad, f"{len(bad)} of {len(rows)} debuts rows are not status 'debuted': {bad[:5]}"


@pytest.fixture(scope="module")
def page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:                              # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        errs: list[str] = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        try:
            pg.goto(base + PROSPX, wait_until="load", timeout=120_000)
            try:
                pg.wait_for_function(
                    "() => typeof DATA !== 'undefined' && DATA && Array.isArray(DATA.players)"
                    " && DATA.players.length > 0 && typeof _EFV !== 'undefined' && _EFV"
                    " && Object.keys(_EFV).length > 0", timeout=180_000)
            except Exception as exc:                          # noqa: BLE001
                pytest.skip(f"board data did not load: {exc}")
            yield pg, base, errs
        finally:
            browser.close()


_CARD_JS = r"""() => {
  const root = document.querySelector('#content') || document.body;
  const tiles = Array.from(document.querySelectorAll('.stat-tile'))
    .map(t => t.innerText.replace(/\s+/g, ' ').trim());
  const hdr = document.querySelector('.detail-page-header');
  const right = hdr ? hdr.querySelector(':scope > div[style*="text-align:right"]') : null;
  const pill = document.querySelector('.debut-pill');
  return {tiles, text: root.innerText, html: root.innerHTML,
          right: right ? right.innerText.replace(/\s+/g, ' ').trim() : '',
          pill: pill ? pill.textContent.trim() : null};
}"""


def _card(pg, base, key, tab=None):
    pg.goto(base + PROSPX + "#player=" + key, wait_until="load", timeout=120_000)
    pg.wait_for_function(
        "() => !!document.querySelector('.detail-page-header')"
        " && document.querySelectorAll('.stat-tile').length > 0", timeout=180_000)
    pg.wait_for_timeout(800)
    if tab:
        pg.evaluate("(t) => { state.playerTab = t; render(); }", tab)
        pg.wait_for_timeout(800)
    return pg.evaluate(_CARD_JS)


def _grad_keys():
    keys = {r.get("player_key") for r in _debuts()}
    return keys


@pytest.mark.parametrize("key", GRAD_KEYS)
def test_graduate_card_prints_no_eta_and_no_awaiting_debut(page, key):
    pg, base, errs = page
    if key not in _grad_keys():
        pytest.skip(f"{key} is not in the debuts slice today")
    c = _card(pg, base, key)
    assert not errs, errs[:3]
    assert c["pill"] and c["pill"].startswith("Debuted"), c["pill"]
    assert not [t for t in c["tiles"] if t.startswith("ETA")], c["tiles"]
    assert "P(debut)" not in c["text"]
    assert "awaiting pro debut" not in c["html"]
    assert "Prior-anchored eFV" not in c["html"]
    assert "locked at debut" in c["right"], c["right"]
    d = _card(pg, base, key, tab="details")
    assert "ETA breakdown" not in d["text"]


def test_active_card_keeps_its_eta_tile(page):
    pg, base, errs = page
    ts = load_data_doc("timeseries.json") or {}
    p = next((r for r in ts.get("players") or [] if r.get("player_key") == ACTIVE_KEY), None)
    if not p or not (p.get("eta") or {}).get("year"):
        pytest.skip(f"{ACTIVE_KEY} is not an active with an ETA today")
    c = _card(pg, base, ACTIVE_KEY)
    assert not errs, errs[:3]
    eta_tiles = [t for t in c["tiles"] if t.startswith("ETA")]
    assert len(eta_tiles) == 1 and str(p["eta"]["year"]) in eta_tiles[0], c["tiles"]
    assert "locked at debut" not in c["right"], c["right"]
    # The tab switch the graduate test relies on does reach the ETA breakdown.
    d = _card(pg, base, ACTIVE_KEY, tab="details")
    assert "ETA breakdown" in d["text"]


def test_no_graduate_reaches_an_eta_or_the_prior_anchored_flag(page):
    """Helper level, over every graduate the page holds: etaServed is null and
    gradeBlock never flags prior-anchored on a debuted row."""
    pg, _, errs = page
    got = pg.evaluate(r"""async () => {
      if (typeof ensureDebutsFull === 'function') await ensureDebutsFull();
      const rows = DATA.debuts || [];
      let eta = 0, prior = 0, withEta = 0;
      for (const p of rows) {
        if (p.eta && p.eta.year != null) withEta++;
        if (etaServed(p) != null) eta++;
        if (gradeBlock(p).priorAnchored) prior++;
      }
      return {n: rows.length, eta, prior, withEta};
    }""")
    assert not errs, errs[:3]
    if not got["n"] or not got["withEta"]:
        pytest.skip(f"no graduate row carries an ETA to gate today: {got}")
    assert got["eta"] == 0, got
    assert got["prior"] == 0, got
