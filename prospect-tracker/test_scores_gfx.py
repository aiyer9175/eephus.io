# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Scores share cards (SCORES_7c, owner SC7-3): a Generate GFX chip on the
game page and the day view opens the shared eephus-gfx.js modal (kind "draw")
with a Card control over four cards painted by the lazy assets/scores-gfx.js:
the final score, the full box score, the top performers and the day slate.

Static: the shell names both lazy chunks by stamped path on the mount root
(scores.js names neither file), the chunk types no colour, stays inside its
28 KB budget, and the modal carries the Card control and filenameFor.

The fit ladders (pure functions of the chunk): layoutBox never drops a row
(every rung's block fits its canvas, and a box too long for the 19 px floor
grows the canvas in 120 px steps); layoutSlate holds every final.

Chromium, on the fixture payloads of test_scores_render.py served from a
temporary copy (every request off loopback is aborted, so every logo and
headshot fails and the fallbacks draw: the club code and the initials): the
chip shows on a final game's head and on any date with games, where it wakes
at the first final (so a poll never moves a card), and on no live game; every
card renders in both themes at 2x, toDataURL succeeds (never tainted), and
the words each card draws are read back through fillText (every batter and
pitcher on the box card, P/AB and P/IP, the stars, each final on the slate);
the Download button saves <date>-<away>-at-<home>-<card>.png as a PNG.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import build_site
import test_scores_render as R
from conftest import serve_site

ROOT = Path(__file__).resolve().parent
CHUNK = ROOT / "assets" / "scores-gfx.js"
DAY = "2026-09-29"
PK = 849845
INIT = """(() => { const f = CanvasRenderingContext2D.prototype.fillText; window.__ft = [];
  CanvasRenderingContext2D.prototype.fillText = function (t, x, y, m) { window.__ft.push(String(t)); return f.call(this, t, x, y, m); }; })();"""


def _lf(p: Path) -> bytes:
    return p.read_bytes().replace(b"\r\n", b"\n")


# --- static ------------------------------------------------------------------------------------

def test_the_shell_names_both_lazy_chunks_and_scores_js_names_neither():
    html = build_site.build_scores()
    assert f'data-sgfx-src="/assets/scores-gfx.js?v={build_site._SCORES_GFX_VER}"' in html
    assert f'data-gfx-js="/assets/eephus-gfx.js?v={build_site._GFX_VER}"' in html
    assert '<script src="/assets/scores-gfx.js' not in html and '<script src="/assets/eephus-gfx.js' not in html
    js = _lf(ROOT / "assets" / "scores.js").decode()
    assert "scores-gfx.js" not in js and "eephus-gfx.js" not in js
    assert 'root.getAttribute("data-sgfx-src")' in js and "Generate GFX" in js


def test_the_chunk_fits_its_budget_and_types_no_colour():
    b = _lf(CHUNK)
    assert len(b) <= 28 * 1024, len(b)   # lazy: loaded on the first press, never in the first paint
    t = b.decode()
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", t)
    assert not re.search(r"\brgba?\(|\bhsla?\(|gradient\(", t)
    assert chr(0x2014) not in t and chr(0x2013) not in t
    # logos only through the hub helper; every image through the shared crossOrigin loader
    assert "espncdn" not in t and "teamLogoURL" in t and "loadImg" in t and "new Image" not in t


def test_the_modal_carries_the_card_control():
    t = _lf(ROOT / "assets" / "eephus-gfx.js").decode()
    assert 'id="egfx-card"' in t and "card: _opts.card" in t and "_spec.filenameFor(_opts.card)" in t
    assert "fitTxt: fitTxt, loadImg: loadImg, initialsOf: initialsOf, brandHead: brandHead" in t


# --- Chromium ----------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return R.make_site(tmp_path_factory.mktemp("scores_gfx_site"))


@pytest.fixture(scope="module")
def payloads():
    return R.build_payloads()


@pytest.fixture(scope="module")
def pw():
    sync = pytest.importorskip("playwright.sync_api")
    with sync.sync_playwright() as p:
        try:
            p.chromium.launch().close()
        except Exception as e:  # pragma: no cover - chromium missing
            pytest.skip(f"chromium unavailable: {e}")
        yield p


def _page(pw, base, width=1280, theme="light"):
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={"width": width, "height": 900}, accept_downloads=True)
    ctx.add_init_script(INIT + "try{localStorage.setItem('prospect-tracker.theme','%s')}catch(e){}" % theme)
    page = ctx.new_page()
    page._errors = []
    page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base[:-1]) else r.abort())
    page.on("pageerror", lambda e: page._errors.append(str(e)))
    return br, page


def _canvas(page):
    page.wait_for_function("() => { const p = document.getElementById('egfx-preview');"
                           " return p && !p.classList.contains('is-busy') && p.querySelector('canvas'); }", timeout=30000)
    return page.evaluate("""() => { const c = document.querySelector('#egfx-preview canvas'); let ok = false, err = null;
      try { ok = c.toDataURL('image/png').length > 5000; } catch (e) { err = String(e); }
      return {w: c.width, h: c.height, ok, err, text: window.__ft.slice()}; }""")


def test_the_layouts_never_drop_a_row(site, pw):
    with serve_site(site) as base:
        br, page = _page(pw, base)
        try:
            page.goto(base + f"scores/#date={DAY}")
            page.wait_for_selector(".sp-mast .sc-gfx", timeout=15000)
            page.click(".sp-mast .sc-gfx")
            page.wait_for_function("() => window.EephusScoresGfx", timeout=15000)
            boxes = page.evaluate("""() => { const out = [];
              for (const n of [[9, 3], [11, 7], [14, 10], [20, 14], [30, 18]]) {
                const s = {bat: n[0], pit: n[1], notes: ["2B: Turner (31), Harper (30). HR: Schwarber (52)."]};
                out.push(Object.assign({n: n}, EephusScoresGfx.layoutBox(s, s))); }
              return out; }""")
            slates = page.evaluate("() => Array.from({length: 30}, (_, i) => EephusScoresGfx.layoutSlate(i + 1))")
        finally:
            br.close()
    heights = [b["H"] for b in boxes]
    assert heights == sorted(heights) and heights[0] == 675 and heights[-1] > 675
    for b in boxes:
        assert b["units"] * b["rowH"] <= b["H"] - 214 - 52, b
        assert (b["H"] - 675) % 120 == 0 and b["font"] >= 13 and b["rowH"] >= 19
    assert boxes[-1]["cols"] == 2 and boxes[-1]["rowH"] == 19
    for n, s in enumerate(slates, 1):
        assert s["cols"] * s["rows"] >= n and s["rows"] * (s["cellH"] + 14) - 14 <= s["H"] - 116 - 52, (n, s)
    # a full day (15 games, 16 with a makeup) fits the Twitter card; more grows it
    assert [s["H"] for s in slates[:16]] == [675] * 16 and all(s["H"] > 675 for s in slates[20:])


def test_the_chip_wakes_at_a_final_and_never_moves_a_card(site, pw):
    with serve_site(site) as base:
        br, page = _page(pw, base, width=390)
        try:
            page.goto(base + f"scores/#date={DAY}")
            page.wait_for_selector(".sp-mast .sc-gfx", timeout=15000)
            h = page.evaluate("document.querySelector('.sp-mast .sc-gfx').getBoundingClientRect().height")
            assert h >= 44, h
            page.evaluate("location.hash = '#date=2026-10-01'")
            page.wait_for_selector('article[data-pk="900001"]')
            # a date with games and no final keeps the chip in place, asleep, so a poll moves no card
            assert page.locator(".sc-gfx").count() == 1 and page.locator(".sp-mast .sc-gfx").is_disabled()
            page.evaluate(f"location.hash = '#date={DAY}'")
            page.wait_for_selector('article[data-pk="900007"]')
            assert page.locator(".sp-mast .sc-gfx").is_enabled()
            page.evaluate(f"location.hash = '#date={DAY}&game={PK}'")
            page.wait_for_selector(".sc-ghead .sc-gfx", timeout=15000)
            page.evaluate("location.hash = '#date=2026-09-30&game=849846'")
            page.wait_for_selector(".sc-ghead.is-live", timeout=15000)
            assert page.locator(".sc-gfx").count() == 0
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert not page._errors, page._errors
        finally:
            br.close()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_card_renders_untainted_with_every_row(site, pw, payloads, theme):
    g = payloads[f"games/{PK}.json"]
    box = g["box"]
    names = [r["name"] for s in ("away", "home") for k in ("batting", "pitching") for r in box[s][k]]
    with serve_site(site) as base:
        br, page = _page(pw, base, theme=theme)
        try:
            page.goto(base + f"scores/#date={DAY}&game={PK}")
            page.wait_for_selector(".sc-ghead .sc-gfx", timeout=15000)
            page.click(".sc-ghead .sc-gfx")
            page.wait_for_selector("#egfx-overlay.is-open", timeout=15000)
            opts = page.evaluate("() => Array.from(document.querySelectorAll('#egfx-card option')).map(o => o.value)")
            assert opts == ["final", "box", "stars", "slate"]
            assert page.evaluate("getComputedStyle(document.querySelector('.egfx-ctrl-card')).display") != "none"
            got = {}
            for k in opts:
                page.evaluate("window.__ft = []")
                page.select_option("#egfx-card", k)
                page.wait_for_timeout(150)
                got[k] = r = _canvas(page)
                assert r["ok"] and r["err"] is None, (k, r["err"])
                assert r["w"] == 2400 and r["h"] >= 1350, (k, r["w"], r["h"])
            c = g["card"]
            A, H = c["away"]["code"], c["home"]["code"]
            fin = " | ".join(got["final"]["text"])
            assert "FINAL" in fin and A in got["final"]["text"] and H in got["final"]["text"]
            assert any(t.startswith("W ") for t in got["final"]["text"])
            bt = got["box"]["text"]
            assert "P/AB" in bt and "P/IP" in bt and "BOX SCORE" in bt
            missing = [n for n in names if n not in bt]
            assert not missing, missing
            st = got["stars"]["text"]
            for s in g["stars"][:3]:
                assert s["name"] in st, s["name"]
            # headshots are aborted here, so each star draws its initials
            assert "AR" in st and "STARS OF THE GAME" in st
            assert "FINAL SCORES" in got["slate"]["text"]
            assert not page._errors, page._errors
            if theme == "light":
                page.select_option("#egfx-card", "box")
                _canvas(page)
                with page.expect_download() as dl:
                    page.click("#egfx-download")
                d = dl.value
                assert d.suggested_filename == f"{DAY}-{A.lower()}-at-{H.lower()}-box.png"
                assert Path(d.path()).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        finally:
            br.close()


def test_the_day_chip_opens_the_slate_alone(site, pw):
    with serve_site(site) as base:
        br, page = _page(pw, base)
        try:
            page.goto(base + f"scores/#date={DAY}")
            page.wait_for_selector(".sp-mast .sc-gfx", timeout=15000)
            page.click(".sp-mast .sc-gfx")
            page.wait_for_selector("#egfx-overlay.is-open", timeout=15000)
            r = _canvas(page)
            assert r["ok"] and (r["w"], r["h"]) == (2400, 1350)
            assert page.evaluate("getComputedStyle(document.querySelector('.egfx-ctrl-card')).display") == "none"
            assert "FINAL SCORES" in r["text"] and "2 finals" in r["text"]
            assert "FINAL, 12 INNINGS" in r["text"]
            with page.expect_download() as dl:
                page.click("#egfx-download")
            assert dl.value.suggested_filename == f"{DAY}-scores-slate.png"
            assert not page._errors, page._errors
        finally:
            br.close()


def test_a_long_box_grows_the_canvas_and_keeps_every_row(site, pw, payloads):
    g = payloads[f"games/{PK}.json"]
    with serve_site(site) as base:
        br, page = _page(pw, base)
        try:
            page.goto(base + f"scores/#date={DAY}")
            page.wait_for_selector(".sp-mast .sc-gfx", timeout=15000)
            page.click(".sp-mast .sc-gfx")
            page.wait_for_selector("#egfx-overlay.is-open", timeout=15000)
            r = page.evaluate("""async (gm) => {
              const big = JSON.parse(JSON.stringify(gm));
              for (const s of ["away", "home"]) {
                const b = big.box[s], bat = b.batting[0], pit = b.pitching[0];
                for (let i = 0; i < 16; i++) b.batting.push(Object.assign({}, bat, {name: s + " Bench " + i, order: 900 + i}));
                for (let i = 0; i < 9; i++) b.pitching.push(Object.assign({}, pit, {name: s + " Arm " + i}));
              }
              window.__ft = [];
              const env = {scale: 2, palette: EEPHUS_GFX.palette("--accent-lilac"), card: "box"};
              const c = await EephusScoresGfx.draw("box", env, {date: "2026-09-29", card: big.card, game: big,
                finals: [big.card], others: 0, url: "eephus.io/scores/#game=1"});
              return {h: c.height, ok: c.toDataURL("image/png").length > 5000, text: window.__ft.slice()};
            }""", g)
        finally:
            br.close()
    assert r["ok"] and r["h"] > 1350 and (r["h"] // 2 - 675) % 120 == 0
    for s in ("away", "home"):
        for i in range(16):
            assert f"{s} Bench {i}" in r["text"]
        for i in range(9):
            assert f"{s} Arm {i}" in r["text"]
