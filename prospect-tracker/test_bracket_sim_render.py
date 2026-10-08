# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The postseason bracket simulator on its two surfaces, rendered in headless
Chromium at 390 and 1280 px in both themes (docs/betting-2026-10/
BRACKET_SIM_GATE.md section 14). Every payload is a FIXTURE: the Futures board
and the bracket payload are built here from test_bracket_sim's fixture league,
and the Franchise board is the served file with a fixture bracket block laid
over it, so no number from the real 2026 bracket is computed.

Pinned: the Pennant and World Series columns carry the label and the line,
the interval and price cells print a dash, the postseason table draws one row
per club, nothing scrolls sideways, no console error; and with the flag off
(or no payload) the Futures panel renders byte for byte as it does without
the simulator."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import bracket_sim as bs  # noqa: E402
import test_bracket_sim as fx  # noqa: E402

WIDTHS = (390, 1280)
THEMES = ("light", "dark")


def _bracket_payload(tmp_path_factory, *, flag=True):
    d = tmp_path_factory.mktemp("bracket_render")
    saved = {k: getattr(bs, k) for k in ("RECORD_PATH", "RECORD_DERIVED_PATH", "OUT_PATH",
                                         "FETCH_CACHE_DIR", "BOARD_PATH", "FUTURES_PATH",
                                         "STANDINGS_DIR", "SERVE_BRACKET_SIM")}
    import betting_model as bm
    saved_cg = bm.completed_games
    try:
        bs.RECORD_PATH = d / "record.json"
        bs.RECORD_DERIVED_PATH = d / "record_copy.json"
        bs.OUT_PATH = d / "bracket_sim.json"
        bs.FETCH_CACHE_DIR = d / "fetch"
        bs.BOARD_PATH = d / "betting.json"
        bs.FUTURES_PATH = d / "futures.json"
        bs.STANDINGS_DIR = d
        bs.SERVE_BRACKET_SIM = flag
        (d / "statsapi_standings_2026.json").write_text(
            json.dumps({"records": fx.standings_records()}), encoding="utf-8")
        (d / "futures.json").write_text(json.dumps(_futures()), encoding="utf-8")
        bm.completed_games = lambda season=None, refresh=True: fx.elo_games()
        bs.run(now=fx.NOW, fetch=fx._fetcher(fx.WC_OPEN), machine="local")
        return json.loads(bs.OUT_PATH.read_text(encoding="utf-8"))
    finally:
        for k, v in saved.items():
            setattr(bs, k, v)
        bm.completed_games = saved_cg


def _futures():
    clubs = []
    for i, org in enumerate(sorted(fx.TEAM_ID)):
        p = 0.02 + (i % 7) / 100
        clubs.append({"team": org, "record": "81-81", "projWins": 81.0, "winTotalP10": 81,
                      "winTotalP90": 81, "winTotalSd": 0, "divisionPct": p, "playoffPct": p,
                      "byePct": p / 2, "pennantPct": p / 3, "wsPct": p / 6,
                      "impliedAmericanWS": 2400, "mcWs": {"lo95": p / 7, "hi95": p / 5}})
    clubs.sort(key=lambda c: -c["wsPct"])
    return {"generated_at": "2026-10-12T07:00:00+00:00", "season": 2026,
            "regular_season_end": "2026-09-27",
            "as_of_note": ("As of the end of the regular season (2026-09-27): postseason "
                           "results are not in these odds."),
            "content_hash": "fixture", "sims": 20000, "clubs": clubs,
            "no_market": {"captured": False, "what_is_missing": "No futures price has been captured.",
                          "what_would_have_to_happen": "Capture is an owner decision.",
                          "and_then_still_not_an_edge": "A captured price would still be unvalidated."},
            "why_the_price_column_is_not_called_fair": "Not fair.",
            "what_the_intervals_are": "Monte Carlo sampling intervals only.",
            "win_total_basis": "Schedule noise only.",
            "ledger": {"n_entries": 3, "n_resolved": 0, "first_as_of": "2026-09-06",
                       "what_it_is": "Each build appends."}}


@pytest.fixture(scope="module")
def payloads(tmp_path_factory):
    return {"on": _bracket_payload(tmp_path_factory, flag=True),
            "off": _bracket_payload(tmp_path_factory, flag=False)}


def _browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    return sync_playwright


def _page(browser, width, theme, routes):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, device_scale_factor=1)
    ctx.route(re.compile(r"^(?!http://127\.0\.0\.1:).*"), lambda route: route.abort())
    ctx.add_init_script("try{localStorage.setItem('prospect-tracker.theme',%r);}catch(e){}" % theme)
    for pattern, handler in routes:
        ctx.route(pattern, handler)
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    page.on("console", lambda m: errs.append("console.error: " + m.text) if m.type == "error" else None)
    return ctx, page, errs


def _json_route(doc):
    body = json.dumps(doc)
    return lambda route: route.fulfill(status=200, content_type="application/json", body=body)


def _futures_routes(bracket):
    routes = [(re.compile(r".*/data/futures\.json.*"), _json_route(_futures()))]
    if bracket is None:
        routes.append((re.compile(r".*/data/bracket_sim\.json.*"),
                       lambda route: route.fulfill(status=404, body="")))
    else:
        routes.append((re.compile(r".*/data/bracket_sim\.json.*"), _json_route(bracket)))
    return routes


def _render_futures(browser, base, width, theme, bracket):
    ctx, page, errs = _page(browser, width, theme, _futures_routes(bracket))
    page.goto(base + "betting/index.html#section=futures", wait_until="load", timeout=60_000)
    try:
        page.wait_for_function(
            "() => [...document.querySelectorAll('.bt-panel-hd')].some(e => e.textContent === 'Futures')",
            timeout=60_000)
    except Exception:
        ctx.close()
        pytest.skip("the Futures panel did not render on this checkout")
    page.evaluate("t => document.documentElement.setAttribute('data-theme', t)", theme)
    page.wait_for_timeout(150)
    res = page.evaluate("""() => {
      const doc = document.scrollingElement;
      const panels = [...document.querySelectorAll('.bt-panel')];
      const fut = panels.find(p => (p.querySelector('.bt-panel-hd') || {}).textContent === 'Futures');
      const br = document.querySelector('[data-bt-bracket="1"]');
      const heads = [...fut.querySelectorAll('thead th')].map(th => th.textContent);
      const firstRow = [...fut.querySelectorAll('tbody tr')][0];
      return { pageScrollW: doc.scrollWidth, pageClientW: doc.clientWidth, inner: window.innerWidth,
               futHtml: fut.outerHTML, futText: fut.textContent, heads,
               cells: firstRow ? [...firstRow.querySelectorAll('td')].map(td => td.textContent) : [],
               brRows: br ? br.querySelectorAll('tbody tr').length : 0,
               brText: br ? br.textContent : '',
               rects: panels.map(p => { const r = p.getBoundingClientRect();
                                        return [Math.round(r.left), Math.round(r.right)]; }) };
    }""")
    ctx.close()
    return res, errs


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_the_futures_panel_serves_the_simulator(payloads, width, theme):
    from conftest import serve_site
    with serve_site() as base, _browser()() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:                              # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        res, errs = _render_futures(browser, base, width, theme, payloads["on"])
        browser.close()
    assert not errs, errs
    assert "Pennant (implied, no market)" in res["heads"]
    assert "World Series (implied, no market)" in res["heads"]
    assert payloads["on"]["serve"]["line"] in res["futText"]
    assert "Division, Playoffs, Bye, Proj W and Win band" in res["futText"]
    assert "postseason results are not in these odds" not in res["futText"]
    # the WS interval and the implied price print a dash on every row
    assert res["cells"][-2:] == ["-", "-"]
    assert res["brRows"] == 12
    assert "Postseason simulator record: 1 day logged, 0 crash days" in res["brText"]
    assert res["pageScrollW"] <= res["pageClientW"] + 1, f"sideways page scroll at {width}"
    for left, right in res["rects"]:
        assert left >= -1 and right <= res["inner"] + 1, (width, left, right)


def test_the_flag_off_restores_the_panel_byte_for_byte(payloads):
    from conftest import serve_site
    with serve_site() as base, _browser()() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:                              # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        off, e1 = _render_futures(browser, base, 1280, "light", payloads["off"])
        none, e2 = _render_futures(browser, base, 1280, "light", None)
        browser.close()
    # the absent payload is a 404 the browser logs; nothing else may error
    e2 = [e for e in e2 if "status of 404" not in e]
    assert not e1 and not e2, (e1, e2)
    assert payloads["off"]["serve"]["on"] is False
    assert off["futHtml"] == none["futHtml"]
    assert off["brRows"] == 0 and "Pennant" in off["heads"]
    assert "postseason results are not in these odds" in off["futText"]


def _franchise_overlay(route, bracket):
    # The whole document (board joined with its club files, QCLP10): the page
    # renders a club that carries its sections inline with no second fetch.
    import franchise_export as fe
    doc = fe.load(ROOT / "data" / "franchise_board.json")
    by = {c["team"]: c for c in bracket["clubs"]}
    for club in doc["clubs"]:
        r = by.get(club["code"]) or {}
        club["sections"]["odds"]["bracket"] = {
            "pennant_pct": r.get("pennant_pct", 0.0), "ws_pct": r.get("ws_pct", 0.0),
            "seed": r.get("seed"), "series_now": r.get("series_now_text"),
            "as_of": bracket["as_of"], "label": bracket["label"],
            "registry_row": "postseason_bracket_sim", "verdict": "unvalidated",
            "basis": "fixture"}
    doc["copy"]["odds_bracket_line"] = bracket["serve"]["line"]
    doc["copy"]["odds_division_as_of"] = bracket["serve"]["division_columns_note"]
    route.fulfill(status=200, content_type="application/json", body=json.dumps(doc))


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_the_franchise_pennant_tile_serves_the_simulator(payloads, width, theme):
    if not (ROOT / "data" / "franchise_board.json").exists():
        pytest.skip("no franchise board on this checkout")
    from conftest import serve_site
    bracket = payloads["on"]
    with serve_site() as base, _browser()() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:                              # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        routes = [(re.compile(r".*/data/franchise_board\.json.*"),
                   lambda route: _franchise_overlay(route, bracket))]
        ctx, page, errs = _page(browser, width, theme, routes)
        page.goto(base + "franchise/index.html#view=club&team=TBR", wait_until="load", timeout=60_000)
        try:
            page.wait_for_selector('[data-frsec="odds"] .fr-tile', timeout=60_000)
        except Exception:
            ctx.close()
            browser.close()
            pytest.skip("the ODDS section did not render on this checkout")
        page.evaluate("t => document.documentElement.setAttribute('data-theme', t)", theme)
        page.wait_for_timeout(150)
        res = page.evaluate("""() => {
          const doc = document.scrollingElement;
          const sec = document.querySelector('[data-frsec="odds"]');
          const tiles = [...sec.querySelectorAll('.fr-tile')].map(t => t.textContent);
          return { pageScrollW: doc.scrollWidth, pageClientW: doc.clientWidth,
                   text: sec.textContent, tiles }; }""")
        ctx.close()
        browser.close()
    # external requests (club logos) are aborted by the harness; nothing else may error
    errs = [e for e in errs if "net::ERR_FAILED" not in e]
    assert not errs, errs
    pen = next(t for t in res["tiles"] if t.startswith("Pennant"))
    assert "Pennant (implied, no market)" in pen
    assert "postseason_bracket_sim unvalidated" in pen
    assert "as of " + bracket["as_of"] in pen
    assert bracket["serve"]["line"] in res["text"]
    assert "Division, Playoffs, Bye, Proj W and Win band" in res["text"]
    assert res["pageScrollW"] <= res["pageClientW"] + 1, f"sideways page scroll at {width}"
