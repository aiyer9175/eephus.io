# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One PROSPX card prints one consensus FV, and never prints a placeholder as one.

RPR01 (served-number reconciliation audit, 2026-10-01): the card eyebrow printed the
producer's ceiling (timeseries fv_close; consensus.py ceils the UNROUNDED consensus)
while the eFV header printed ceil(xfv.json consensus_fv), which efv_score.py rounds to
one decimal first. jackson_flora read 'Consensus FV 52' over 'Consensus FV 51' with the
delta chip on 51. The fix is display only: efvConsensusDisplay prints fv_close whenever
the timeseries row is loaded, and the chip differences the same number.

RPR03: 2,693 board actives carry consensus_is_placeholder (no source published an FV,
the 35 is a fixed anchor). The eyebrow printed 'Consensus FV 35' beside 'no source grade
published'. The card now prints 'No source grade' and drops the Range/O/C line and the
'35 FV' quick-read part.

Every check reads the SERVED artifacts (data/timeseries.json, data/xfv.json) and the
served page, so it follows the board through nightly regenerations: the asserted
consensus is the served fv_close, not a number frozen into this file.
"""
from __future__ import annotations

import math
import re

import pytest
from conftest import load_data_doc, serve_site

PROSPX = "prospx/index.html"
SPLIT_KEYS = ("jackson_flora", "jurrangelo_cijntje")
PLACEHOLDER_KEY = "alison_zacarias"


def _served():
    ts = load_data_doc("timeseries.json")
    xf = load_data_doc("xfv.json")
    if not ts or not xf:
        pytest.skip("timeseries.json or xfv.json not built")
    players = {p["player_key"]: p for p in ts.get("players") or [] if p.get("player_key")}
    return players, (xf.get("by_player") or {})


def _split_keys(players, bp):
    """Actives whose producer ceiling and ceil(xfv consensus_fv) differ."""
    out = []
    for k, p in players.items():
        x = bp.get(k) or {}
        if p.get("fv_close") is None or x.get("consensus_fv") is None:
            continue
        if math.ceil(p["fv_close"]) != math.ceil(x["consensus_fv"]):
            out.append(k)
    return sorted(out)


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
  const eb = Array.from(document.querySelectorAll('.newsprint-eyebrow-meta'))
    .find(e => /Consensus FV|No source grade/.test(e.textContent));
  const hdr = document.querySelector('.detail-page-header');
  const right = hdr ? hdr.querySelector(':scope > div[style*="text-align:right"]') : null;
  const badge = hdr ? hdr.querySelector('.fv-badge.size-lg') : null;
  // The card's own header: eyebrow, header block and the quick-read under it. The
  // rest of #content lists OTHER players (comps, org board) with their own tooltips.
  const qr = document.querySelector('.quick-read');
  const own = [eb && eb.parentElement, hdr, qr].filter(Boolean);
  return {eyebrow: eb ? eb.textContent.trim() : null,
          right: right ? right.innerText.replace(/\s+/g, ' ').trim() : '',
          badge: badge ? badge.textContent.trim() : null,
          html: own.map(e => e.outerHTML).join(' | '),
          text: own.map(e => e.innerText).join(' | ')};
}"""


def _card(pg, base, key):
    pg.goto(base + PROSPX + "#player=" + key, wait_until="load", timeout=120_000)
    pg.wait_for_function(
        "(k) => { const h = document.querySelector('.detail-page-header');"
        " return !!h && !!document.querySelector('.newsprint-eyebrow-meta')"
        " && document.body.innerText.length > 0; }", arg=key, timeout=180_000)
    pg.wait_for_timeout(800)
    return pg.evaluate(_CARD_JS)


def test_helper_prints_the_producer_ceiling_on_every_split_key(page):
    """Data-level: for every active where the two artifacts round apart, the
    helper's chosen number (and the chip's consensus) is the served fv_close."""
    pg, _, errs = page
    players, bp = _served()
    keys = _split_keys(players, bp)
    if not keys:
        pytest.skip("no active row rounds apart between the two artifacts today")
    got = pg.evaluate(r"""(keys) => {
      const by = new Map(DATA.players.map(p => [p.player_key, p]));
      return keys.map(k => {
        const p = by.get(k), x = p ? getEfv(p) : null;
        const d = x ? efvMinusConsensusDisplay(x) : null;
        return {k, fc: p ? p.fv_close : null, shown: x ? efvConsensusDisplay(x) : null,
                g: x ? efvGradeDisplay(x) : null, d};
      });
    }""", keys)
    assert not errs, errs[:3]
    bad = [r for r in got if r["fc"] is None or r["shown"] != math.ceil(r["fc"])]
    assert not bad, f"{len(bad)} of {len(keys)} split keys print a second consensus: {bad[:5]}"
    chip_bad = [r for r in got if r["d"] is not None and r["d"] != r["g"] - r["shown"]]
    assert not chip_bad, chip_bad[:5]


@pytest.mark.parametrize("key", SPLIT_KEYS)
def test_split_card_prints_one_consensus_and_the_chip_on_it(page, key):
    pg, base, errs = page
    players, bp = _served()
    p, x = players.get(key), bp.get(key) or {}
    if not p or p.get("fv_close") is None or x.get("consensus_fv") is None:
        pytest.skip(f"{key} is not a graded active today")
    want = math.ceil(p["fv_close"])     # 52 for jackson_flora, 49 for cijntje on 2026-10-02
    c = _card(pg, base, key)
    assert not errs, errs[:3]
    assert c["eyebrow"] == f"Consensus FV {want}", c["eyebrow"]
    m = re.search(r"Consensus FV (\d+)(?: · eFV ([+-]?\d+))?", c["right"])
    assert m, c["right"]
    assert int(m.group(1)) == want, c["right"]
    if m.group(2) is not None:
        assert int(c["badge"]) - want == int(m.group(2)), (c["badge"], c["right"])
    # No second consensus number anywhere in the header.
    others = {int(v) for v in re.findall(r"Consensus FV (\d+)", c["html"])}
    assert others == {want}, others


def test_placeholder_card_prints_no_consensus_fv(page):
    pg, base, errs = page
    players, bp = _served()
    x = bp.get(PLACEHOLDER_KEY) or {}
    if PLACEHOLDER_KEY not in players or not x.get("consensus_is_placeholder"):
        pytest.skip(f"{PLACEHOLDER_KEY} no longer carries a placeholder consensus")
    c = _card(pg, base, PLACEHOLDER_KEY)
    assert not errs, errs[:3]
    assert c["eyebrow"] == "No source grade", c["eyebrow"]
    assert "Consensus FV 35" not in c["html"], "placeholder printed as a consensus FV"
    assert not re.search(r"Range \S+.* · O \S+ · C ", c["right"]), c["right"]
    assert not re.search(r"\b35 FV\b", c["text"]), "quick-read still prints the placeholder"
    # No delta chip against the placeholder, on the card or in the helper.
    assert not re.search(r"· eFV [+-]?\d", c["right"]), c["right"]
    assert pg.evaluate(
        "(k) => efvMinusConsensusDisplay(getEfv(DATA.players.find(p => p.player_key === k)))",
        PLACEHOLDER_KEY) is None
