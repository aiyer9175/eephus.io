# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The MLB News type system (HOME_2; site-pass plan 3.1 to 3.3, LANE_HOME 2).

Colour names the family of a news row (Prospects, MLB, Free agency, Trades,
Injuries), the pictogram names the event inside it, the value carries the
number. Pins: every row _collect_events emits carries a type code of the
registry (build_site._WIRE_TYPES); every pictogram key and family mark has a
drawing in the sprite; the browser copy in assets/eephus-hub.js equals the
Python registry; no wire rule in assets/site.css or prospx/index.html colours
an event type with a hex; the ten family tokens are mirrored in PROSPX; the
/history/ ledger rows map onto the registry; and, in Chromium, each family's
computed text and pictogram colour equals its token in both themes, on page
ground and on the terminal panel, at 4.5:1 for text and 3:1 for the pictogram.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import build_site as B

ROOT = Path(__file__).parent
FAMS = ("pro", "mlb", "fa", "trd", "inj")
PAGE = {  # LANE_HOME 2.1, light / dark page ground
    "pro": ("#1A6B35", "#4FFF9E"), "mlb": ("#0B5F8A", "#4FD9FF"), "fa": ("#6B3FC0", "#B47CFF"),
    "trd": ("#9A4307", "#FF9D42"), "inj": ("#A0146E", "#FF6EB4"),
}
PANEL = {"pro": "#6EE7A8", "mlb": "#4EE0FF", "fa": "#C39BFF", "trd": "#FFA94D", "inj": "#FF7AC0"}
_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------- registry

def test_the_registry_holds_every_row_of_the_design_table():
    want = {
        "pro": {"grade_up", "grade_down", "promo", "demo", "debut", "draft_sign", "intl_sign"},
        "mlb": {"callup", "recall", "optioned", "dfa", "outright", "claim", "release", "retire",
                "suspend", "rule5", "award"},
        "fa": {"fa_sign", "minor_deal", "opt_declined", "opt_exercised", "qo", "fa_elect"},
        "trd": {"trade"},
        "inj": {"il_place", "il_return"},
    }
    got: dict = {}
    for code, row in B._WIRE_TYPES.items():
        assert set(row) == {"fam", "ico", "val", "weight", "rail"}, code
        assert row["rail"] in (True, False, "board"), code
        assert isinstance(row["weight"], int) and row["val"], code
        got.setdefault(row["fam"], set()).add(code)
    assert got == want
    assert {k: (f["tag"], f["sr"]) for k, f in B._WIRE_FAMILIES.items()} == {
        "pro": ("PRO", "Prospect:"), "mlb": ("MLB", "MLB:"), "fa": ("FA", "Free agency:"),
        "trd": ("TRD", "Trade:"), "inj": ("IL", "Injury:")}


def test_the_interim_symbols_are_the_plan_s():
    """Plan 3.3: the symbols in use until PX_SYSTEM_SWEEP draws the final set."""
    t = B._WIRE_TYPES
    assert [B._WIRE_FAMILIES[f]["mark"] for f in FAMS] == ["prospx", "franchise", "ev-signing", "ev-trade", "ev-il"]
    assert t["callup"]["ico"] == t["recall"]["ico"] == "ev-promo" and t["optioned"]["ico"] == "ev-demo"
    for code in ("dfa", "outright", "claim", "release", "retire", "suspend", "rule5"):
        assert t[code]["ico"] == "franchise", code
    assert t["award"]["ico"] == "hof" and t["il_return"]["ico"] == "ev-il"
    for code in ("opt_declined", "opt_exercised", "qo"):
        assert t[code]["ico"] == "ev-signing", code
    assert (t["draft_sign"]["ico"], t["intl_sign"]["ico"]) == ("ev-draft", "ev-intl")
    assert (B.ICON_FOR["ev-draft"], B.ICON_FOR["ev-intl"]) == ("px-draft", "px-intl")


def test_every_pictogram_key_and_family_mark_is_in_the_sprite():
    sprite = set(re.findall(r'<symbol id="i-([\w-]+)"', _src("assets/eephus-icons.svg")))
    keys = [r["ico"] for r in B._WIRE_TYPES.values()] + [f["mark"] for f in B._WIRE_FAMILIES.values()]
    for k in keys:
        sym = B.ICON_FOR.get(k, k)
        assert sym in B.ICON_KEYS and sym in sprite, k
    assert B._WIRE_ICON == {c: B.ICON_FOR.get(r["ico"], r["ico"]) for c, r in B._WIRE_TYPES.items()}


def test_every_mlb_events_code_is_in_the_registry():
    import mlb_events
    # arb_salary carries a season, not a date: it never reaches a news row.
    assert set(mlb_events.TYPE_CODES) - {"arb_salary"} <= set(B._WIRE_TYPES)


def _fixture_events(tmp_path, monkeypatch) -> list:
    monkeypatch.setattr(B, "_WIRE_FV_LEDGER", tmp_path / "wire_fv_first_seen.json")
    players = [{
        "player_name": "Board Guy", "player_key": "board_guy", "org": "NYY", "status": "active",
        "stock": {"basis": "xfv", "delta": 4.2, "direction": "up", "to_label": "eFV 52.0",
                  "to_date": "2026-09-30"},
        "level_changes": [{"kind": "promotion", "from_level": "AA", "to_level": "AAA", "date": "2026-09-01"},
                          {"kind": "demotion", "from_level": "AAA", "to_level": "AA", "date": "2026-09-10"}],
        "trades": [{"trade_date": "2026-07-31", "from_org": "NYY", "to_org": "BOS"}],
        "il_status": {"is_on_il": True, "since": "2026-08-01", "type": "15-Day"},
    }, {
        "player_name": "Down Guy", "player_key": "down_guy", "org": "BOS", "status": "active",
        "stock": {"basis": "xfv", "delta": -5.0, "direction": "down", "to_label": "eFV 41.0",
                  "to_date": "2026-09-30"},
    }]
    grads = [{"player_name": "Grad Guy", "player_key": "grad_guy", "org": "SEA", "debut_date": "2026-09-02"}]
    fa = [
        {"date": "2026-11-20", "type": "signing", "key": "ace", "name": "Ace", "to": "NYY", "years": 6,
         "guar": 210_000_000},
        {"date": "2026-11-21", "type": "signing", "key": "arm", "name": "Arm", "to": "SEA", "milb": True},
        {"date": "2026-11-04", "type": "option_declined", "key": "mutual", "name": "Mutual"},
        {"date": "2026-11-04", "type": "option_exercised", "key": "club", "name": "Club"},
        {"date": "2026-11-09", "type": "qo_offered", "key": "qo_guy", "name": "QO Guy"},
    ]
    return B._collect_events(players, grads, fa)


def test_every_collected_row_carries_a_registry_code(tmp_path, monkeypatch):
    events = _fixture_events(tmp_path, monkeypatch)
    types = {e[1] for e in events}
    assert types == {"grade_up", "grade_down", "promo", "demo", "trade", "il_place", "debut",
                     "fa_sign", "minor_deal", "opt_declined", "opt_exercised", "qo"}
    assert types <= set(B._WIRE_TYPES)


def test_fa_rows_take_the_member_club_when_the_event_names_none(tmp_path, monkeypatch):
    """The fa_class option and QO events carry no club; the row takes the club
    of the FA class member (task item 6), and a member-less key stays bare."""
    B._fa_member_teams.cache_clear()
    monkeypatch.setattr(B, "_cached_data_json", lambda name: {"members": [
        {"key": "mutual", "from": "LAD"}, {"key": "qo_guy", "from": "TOR"}]})
    try:
        events = _fixture_events(tmp_path, monkeypatch)
    finally:
        B._fa_member_teams.cache_clear()
    org = {e[6]: e[5] for e in events}
    assert (org["Mutual"], org["QO Guy"], org["Club"], org["Ace"]) == ("LAD", "TOR", None, "NYY")


def test_every_row_surface_carries_family_type_pictogram_and_prefix(tmp_path, monkeypatch):
    """LANE_HOME 2.3: data-fam, data-type, the pictogram at the row lead and the
    family's hidden prefix, on the rail, /news/ and the ticker."""
    events = _fixture_events(tmp_path, monkeypatch)
    for html, tag in ((B._feed_html(events, 50), "a"), (B._news_feed_html(events, {}), "a"),
                      (B._ticker_html(events, 50), "a")):
        rows = re.findall(r'<a [^>]*?data-fam="(\w+)" data-type="(\w+)"[^>]*>(.*?)</a>', html, re.S)
        assert rows and len(rows) >= len(events)
        for fam, code, inner in rows:
            assert B._WIRE_TYPES[code]["fam"] == fam
            assert inner.startswith('<span class="wire-ico"><svg class="ico"'), inner[:80]
            assert f'#i-{B._WIRE_ICON[code]}"' in inner.split("</span>", 1)[0]
            assert f'<span class="visually-hidden">{B._WIRE_FAMILIES[fam]["sr"]} </span>' in inner


def test_history_ledger_rows_map_onto_the_registry():
    acq = lambda m: {"acquisition": {"method": m}}  # noqa: E731
    assert B._hist_tx_type("TR", None, False) == "trade"
    assert B._hist_tx_type("SFA", None, True) == "minor_deal"
    assert B._hist_tx_type("SFA", None, False) == "fa_sign"
    assert B._hist_tx_type("DFA", None, False) == "fa_elect"
    assert B._hist_tx_type("SGN", acq("draft"), False) == "draft_sign"
    assert B._hist_tx_type("SGN", acq("international_fa"), False) == "intl_sign"
    assert B._hist_tx_type("SGN", None, False) == "minor_deal"


def test_history_rows_carry_the_family_and_the_ev_il_pictogram(monkeypatch):
    from datetime import date
    t = date.today()
    mmdd = f"{t.month:02d}-{t.day:02d}"
    iso = f"{t.year - 3}-{mmdd}"
    g = {"player_name": "Board Guy", "position": "SS", "player_key": "k1",
         "acquisition": {"method": "international_fa"}}
    monkeypatch.setattr(B, "_HIST_DB_CACHE", (
        {mmdd: [(iso, "SFA", "k1", "Boston Red Sox", True), (iso, "SGN", "k1", ""),
                (iso, "TR", "unknown-key", ""), (iso, "DFA", "unknown-key", "")]},
        {mmdd: [(iso, "k1", "15-Day")]}))
    html = B.build_this_day({"players": [g], "graduates": []})
    types = re.findall(r'class="otd-row"[^>]*data-fam="(\w+)" data-type="(\w+)"', html)
    assert sorted(types) == sorted([("fa", "minor_deal"), ("pro", "intl_sign"), ("trd", "trade"),
                                    ("fa", "fa_elect"), ("inj", "il_place")])
    assert "✚" not in html and "#i-ev-il" in html
    chips = re.findall(r'data-hist-filter="(\w+)"', html)
    assert chips == ["all", *FAMS]


def test_news_and_rail_filters_are_the_family_key(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "_WIRE_FV_LEDGER", tmp_path / "wire_fv_first_seen.json")
    news = B.build_news()
    assert re.findall(r'data-news-filter="(\w+)"', news) == ["all", *FAMS, "grades"]
    btns = re.findall(r'<button[^>]*data-news-filter="\w+"[^>]*>', news)
    assert len(btns) == 7 and all(re.search(r'aria-pressed="(true|false)"', x) for x in btns)
    assert sum('data-fam="' in x for x in btns) == 5
    assert "t==='grade_up'||t==='grade_down'" in B._NEWS_FILTER_JS
    assert 'id="news-filter-status" role="status" aria-live="polite"' in news
    home = _src("index.html")
    key = home.split('id="wire-key"', 1)[1].split("</div>", 1)[0]
    assert re.findall(r'data-wire-filter="(\w+)"', key) == list(FAMS)
    assert [B._WIRE_FAMILIES[f]["tag"] for f in FAMS] == re.findall(r"</svg></span>(\w+)</button>", key)
    assert key.count('aria-pressed="false"') == 5
    assert 'id="wire-key-status" role="status" aria-live="polite"' in home


# ------------------------------------------------------------- hub mirror

_JS_TOKEN = re.compile(r'("(?:[^"\\]|\\.)*")|\b([A-Za-z_]\w*)\s*:')


def _js_object(src: str, name: str) -> dict:
    m = re.search(r"var %s = (\{.*?\n  \});" % name, src, re.S)
    assert m, name
    body = _JS_TOKEN.sub(lambda t: t.group(1) or f'"{t.group(2)}":', m.group(1))
    body = re.sub(r",(\s*\})", r"\1", body)
    return json.loads(body)


def test_the_hub_table_equals_the_python_registry():
    hub = _src("assets/eephus-hub.js")
    assert _js_object(hub, "wireFamily") == B._WIRE_FAMILIES
    want = {c: {**r, "ico": B._WIRE_ICON[c]} for c, r in B._WIRE_TYPES.items()}
    assert _js_object(hub, "wireType") == want
    assert "dash, DASH, wireType, wireFamily };" in hub


def test_the_news_gfx_maps_read_the_registry():
    js = B._news_gfx_js()
    wt = json.loads(re.search(r"var WT=(\{.*?\}),TYPE=", js).group(1))
    assert set(wt) == set(B._WIRE_TYPES)
    for code, (label, fam, ico) in wt.items():
        assert label.lower() == B._WIRE_TYPES[code]["val"].lower() and fam == B._WIRE_TYPES[code]["fam"]
        assert ico == B._WIRE_ICON[code]
    assert "CLR[k]={light:'--wire-'+WT[k][1],dark:'--wire-'+WT[k][1]+'-panel'}" in js
    gfx = _src("assets/eephus-gfx.js")
    assert gfx.count("var tp = tokPair(k, P);") == 2


# -------------------------------------------------------- no hex per type

_OLD_TYPES = ("up", "down", "promo", "demo", "il", "debut", "trade", "signing")


def _rules(css: str):
    css = _COMMENT.sub("", css)
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        yield m.group(1).strip(), m.group(2)


def _is_type_rule(sel: str) -> bool:
    names = "|".join(_OLD_TYPES + tuple(B._WIRE_TYPES))
    return bool(re.search(r"\[data-(?:fam|type)\b|\.(?:feed-val|g)\.(?:%s)\b|\.ticker-track \.(?:%s)\b"
                          % (names, names), sel))


def test_no_wire_rule_colours_an_event_type_with_a_hex():
    css = _src("assets/site.css")
    prospx_style = "".join(re.findall(r"<style[^>]*>(.*?)</style>", _src("prospx/index.html"), re.S))
    for where, src in (("site.css", css), ("prospx", prospx_style)):
        bad = [s for s, body in _rules(src) if _is_type_rule(s) and re.search(r"#[0-9A-Fa-f]{3,8}\b", body)]
        assert not bad, (where, bad)
    clean = _COMMENT.sub("", css)
    for t in _OLD_TYPES:
        assert not re.search(r"\.feed-val\.%s\b|\.feed-item \.g\.%s\b|\.ticker-track \.%s\b" % (t, t, t), clean), t


def _tokens(src: str, opener: str) -> dict:
    i = src.index(opener)
    block = src[i:src.index("}", i)]
    return {k: v.upper() for k, v in re.findall(r"(--wire-[a-z]+(?:-panel)?):\s*(#[0-9A-Fa-f]{6})", block)}


def test_the_ten_tokens_in_site_css_and_prospx():
    want_light = {**{f"--wire-{f}": PAGE[f][0] for f in FAMS}, **{f"--wire-{f}-panel": PANEL[f] for f in FAMS}}
    want_dark = {f"--wire-{f}": PAGE[f][1] for f in FAMS}
    css = _COMMENT.sub("", _src("assets/site.css"))
    assert _tokens(css, ":root {") == want_light
    assert _tokens(css, '[data-theme="dark"] {') == want_dark
    px = _COMMENT.sub("", _src("prospx/index.html"))
    assert _tokens(px, ":root {") == want_light
    assert _tokens(px, '[data-theme="dark"] {') == want_dark
    # HOME_8: PROSPX's event accents resolve to the family tokens.
    for acc, fam in (("traded", "trd"), ("il", "inj"), ("graduated", "pro")):
        assert re.search(r"--accent-%s:\s*var\(--wire-%s\);" % (acc, fam), px), acc


# ------------------------------------------------------------ in the browser

@pytest.fixture(scope="module")
def server():
    from conftest import serve_site
    with serve_site() as base:
        yield base


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        yield b
        b.close()


# Injects one row per family (the markup the builders emit) into the surface
# under test, then reads each row's computed text and pictogram colour, the
# token it should equal and the first opaque background behind it.
_MEASURE = """([host, rowClass, valClass, icoHTML]) => {
  const parse = (c) => { const m = c.match(/\\d+(\\.\\d+)?/g).map(Number); return m; };
  const lum = (rgb) => { const v = rgb.slice(0, 3).map(x => { x /= 255;
    return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); });
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  const bgOf = (el) => { for (let e = el; e; e = e.parentElement) {
    const c = parse(getComputedStyle(e).backgroundColor); if (c.length < 4 || c[3] > 0.99) return c; }
    return [255, 255, 255]; };
  const probe = document.createElement('span'); document.body.appendChild(probe);
  const hostEl = document.querySelector(host);
  const out = {};
  for (const fam of ['pro', 'mlb', 'fa', 'trd', 'inj']) {
    const row = document.createElement('a');
    row.className = rowClass; row.setAttribute('data-fam', fam); row.href = '#';
    row.innerHTML = '<span class="wire-ico">' + icoHTML + '</span><span class="feed-name">Name</span>'
      + '<span class="' + valClass + '">value</span>';
    hostEl.prepend(row);
    const ico = row.querySelector('.wire-ico'), val = row.querySelector('.' + valClass);
    const panel = !!row.closest('.sb-feed, .home-ticker');
    probe.style.color = 'var(--wire-' + fam + (panel ? '-panel' : '') + ')';
    const want = getComputedStyle(probe).color, bg = bgOf(val);
    out[fam] = { panel, want, text: getComputedStyle(val).color, ico: getComputedStyle(ico).color,
                 textRatio: ratio(parse(getComputedStyle(val).color), bg),
                 icoRatio: ratio(parse(getComputedStyle(ico).color), bg),
                 theme: document.documentElement.getAttribute('data-theme') };
    row.remove();
  }
  return out;
}"""


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("page_path,host,row_class,val_class,panel", [
    ("index.html", "#wire-rows", "feed-item", "feed-val", True),
    ("news/index.html", "#news-feed", "feed-item news-item", "feed-val", True),
    ("history/index.html", "#hist-sections", "otd-row", "wire-val", False),
])
def test_family_colours_equal_their_tokens_and_clear_contrast(server, browser, theme, page_path, host,
                                                             row_class, val_class, panel):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(e.message))
    page.add_init_script(f"try{{localStorage.setItem('prospect-tracker.theme','{theme}')}}catch(e){{}}")
    try:
        page.goto(server + page_path, wait_until="load", timeout=20_000)
        assert page.evaluate("document.documentElement.getAttribute('data-theme')") == theme
        if host == "#hist-sections" and not page.query_selector("#hist-sections"):
            pytest.skip("history page has no sections host")
        ico = B._ico("ev-trade", 12)
        res = page.evaluate(_MEASURE, [host, row_class, val_class, ico])
    finally:
        page.close()
    assert not errors, errors
    for fam, r in res.items():
        assert r["panel"] is panel, (fam, r)
        assert r["text"] == r["want"] == r["ico"], (fam, r)
        assert r["textRatio"] >= 4.5, (page_path, theme, fam, round(r["textRatio"], 2))
        assert r["icoRatio"] >= 3.0, (page_path, theme, fam, round(r["icoRatio"], 2))
