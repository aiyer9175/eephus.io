# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /awards/ share cards (AWARDS_10_GFX_SHARE; AWARDS_PLAN 3 'The rename', 5.12 'Theme and
the pixel idiom' and 5.16 'Share cards (GFX)').

Static: the kind:"awards" painter in assets/eephus-gfx.js and its budget (at most 8 KB of
served bytes), the modal wiring (Format shown, Show hidden), and the Awards module share card
in tools/pixel_brand_src.py, which tools/pixel_brand.py writes into assets/og/ only while
awards_core.AWARDS_LIVE is True (the preview otherwise), beside the unchanged hof card.

Chromium (optional, skipped without Playwright): every mode (podium, slate, superlative,
ballot) renders in Twitter, Wide and Portrait, light and dark, at 2x, and toDataURL succeeds
(the canvas is never tainted); the words each card draws are read back through fillText: the
ballot card carries "Choices mine." and no selection, Portrait draws every filled ballot and
Twitter only the first. The page is served from the working tree through page.route, so no
test opens a socket to anything but the browser's own pipe; every other URL is aborted.
"""
from __future__ import annotations

import mimetypes
import re
import sys
from pathlib import Path

import pytest

import awards_core
import build_site as B

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import copy_lint  # noqa: E402
import pixel_brand as PB  # noqa: E402
import pixel_brand_src as SRC  # noqa: E402

GFX = ROOT / "assets" / "eephus-gfx.js"
FORMATS = {"twitter": (1200, 675), "wide": (1600, 900), "portrait": (1080, 1350)}


def _gfx() -> str:
    return GFX.read_text(encoding="utf-8")


def _block() -> str:
    t = _gfx()
    return t[t.index("// ---- canvas awards renderer"):t.index("// ---- render dispatch")]


# --- the painter, statically ------------------------------------------------------------------

def test_the_awards_kind_is_wired_into_the_modal():
    t = _gfx()
    assert 'if (_spec.kind === "awards") return renderAwards(_spec, fmt, accentToken());' in t
    assert '(noBoard || _spec.kind === "awards") ? "none" : ""' in t, "Show hides; Format stays"
    assert "drawAwards: function (spec, format)" in t
    for mode in ('a.mode === "podium"', 'a.mode === "slate"', 'a.mode === "superlative"', 'a.mode === "ballot"'):
        assert mode in _block(), mode


def test_the_painter_fits_its_budget():
    """AWARDS_PLAN 5.14: the GFX painter addition is at most 8 KB (served LF bytes; it measured
    8,123 bytes added to the file at landing, the block alone below)."""
    n = len(_block().replace("\r\n", "\n").encode("utf-8"))
    assert n <= 8 * 1024, n


def test_the_painter_is_taint_free_and_uses_the_shared_pieces():
    b = _block()
    for banned in ("loadImg", "drawImage", "new Image", "fetch(", "crossOrigin"):
        assert banned not in b, banned
    assert "pxPainter()" in b and "palette(acc)" in b and "brandHead(" in b
    assert '"Choices mine. Numbers from eephus.io."' in b
    assert "requestAnimationFrame" not in b


# --- the module share card ---------------------------------------------------------------------

def test_the_awards_card_row_is_the_plans_and_the_hof_card_is_unchanged():
    assert SRC.AWARDS_CARD == ("awards", "MLB Awards", "/awards/",
                               "The eephus selection for MVP, Cy Young, Rookie and Manager of the Year, "
                               "superlatives, and a ballot of your own.")
    assert SRC.AWARDS_CARD_ICON == "aw-podium"
    hof = [m for m in SRC.MODULES if m[0] == "hof"]
    assert hof == [("hof", "Hall of Fame", "/hof/",
                    "Career WAR, WAR7 and JAWS for every ten-season player, with the ballot record.")]
    assert "awards" not in B.OG_CARD_KEYS and all(m[0] != "awards" for m in SRC.MODULES)


def test_the_card_ships_with_the_flag_and_is_held_without_it(monkeypatch):
    """AWARDS_11_FLIP_RENAME turned the flag on, so tools/pixel_brand.py wrote the card into
    assets/og/; with the flag off it is held out again (the preview only)."""
    assert awards_core.AWARDS_LIVE is True
    assert PB.card_modules()[-1] == SRC.AWARDS_CARD
    assert (ROOT / "assets" / "og" / "awards.png").exists()
    monkeypatch.setattr(awards_core, "AWARDS_LIVE", False)
    assert SRC.AWARDS_CARD not in PB.card_modules()


def test_the_preview_card_is_1200_by_630(tmp_path):
    from PIL import Image
    out = PB.awards_card_preview(tmp_path)
    assert out == tmp_path / "assets" / "og" / "awards.png"
    assert Image.open(out).size == (SRC.CARD_W, SRC.CARD_H)


def test_the_awards_page_names_its_card_only_with_both_flags_on(monkeypatch):
    og = re.compile(r'<meta property="og:image" content="([^"]+)"')
    monkeypatch.setattr(B, "PIXEL_BRAND", True)
    assert og.search(B.build_awards(live=True)).group(1) == f"{B.SITE_ORIGIN}/assets/og/awards.png"
    assert og.search(B.build_awards(live=False)).group(1) == f"{B.SITE_ORIGIN}/assets/og/hof.png"
    monkeypatch.setattr(B, "PIXEL_BRAND", False)
    assert og.search(B.build_awards(live=True)).group(1) == B.DEFAULT_SHARE_IMAGE


def test_the_card_copy_is_cut_from_the_page_and_follows_the_copy_rules():
    key, title, route, line = SRC.AWARDS_CARD
    page = B.build_awards(live=True)
    assert f"<title>{title} - eephus.io</title>" in page
    allowed = set(re.findall(r"[a-z]+", (B._AWARDS_SUB + " " + B._AWARDS_DESCRIPTION).lower()))
    assert not [w for w in re.findall(r"[a-z]+", line.lower()) if w not in allowed]
    for text in (title, line, "eephus.io" + route):
        assert chr(0x2014) not in text and chr(0x2013) not in text
        assert not copy_lint.BAN_RE.search(text) and not awards_core.verdict_hits(text)
        assert not re.search(r"\d", text)


# --- Chromium: every mode at every format, both themes -----------------------------------------

ORIGIN = "http://awards-gfx.test"
SHELL = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/assets/site.css"></head><body>
<script src="/assets/eephus-export.js"></script><script src="/assets/eephus-hub.js"></script>
<script src="/assets/eephus-gfx.js"></script></body></html>"""
INIT = """(() => { const f = CanvasRenderingContext2D.prototype.fillText; window.__ft = [];
  CanvasRenderingContext2D.prototype.fillText = function (t, x, y, m) { window.__ft.push(String(t)); return f.call(this, t, x, y, m); }; })();"""
CREDIT = "Data: MLB, FanGraphs, Baseball-Reference via eephus.io"
SPECS = {
    "podium": {"title": "AL MVP: the eephus selection, 2026", "url": "eephus.io/awards/#award=mvp&lg=al", "aw": {
        "mode": "podium", "unit": "eWAR v2", "sub": "The rule line.", "stamp": "The stamp.", "credit": CREDIT,
        "rows": [{"p": "1", "n": "Alpha One", "c": "DET", "t": "7.0", "v": 7.0, "ink": "--vt-elite"},
                 {"p": "T2", "n": "Bravo Two", "c": "HOU", "t": "6.8", "v": 6.8, "ink": "--vt-elite"},
                 {"p": "T2", "n": "Charlie Three", "c": "KCR", "t": "6.8", "v": 6.8, "ink": "--vt-elite"}]}},
    "podium_negative": {"title": "NL Manager of the Year: the eephus selection, 2026", "url": "eephus.io/awards/", "aw": {
        "mode": "podium", "unit": "wins", "credit": CREDIT,
        "rows": [{"p": "1", "n": "Reds", "c": "CIN", "t": "4.0", "v": 4.0},
                 {"p": "2", "n": "Cubs", "c": "CHC", "t": "1.5", "v": 1.5},
                 {"p": "3", "n": "Mets", "c": "NYM", "t": "-0.5", "v": -0.5}]}},
    "slate": {"title": "The eephus selection, 1st place, 2026", "url": "eephus.io/awards/", "aw": {
        "mode": "slate", "stamp": "The stamp.", "credit": CREDIT, "rows": [
            {"a": a, "cells": [{"n": "One", "c": "DET"}, {"n": "Not published", "off": 1} if a == "Manager" else
                               {"n": "T Two / T Three", "c": "CHC / NYM"}]}
            for a in ("MVP", "Cy Young", "Rookie", "Manager")]}},
    "superlative": {"title": "Best glove by DEM+", "url": "eephus.io/awards/#section=superlatives&sl=glove", "aw": {
        "mode": "superlative", "pic": "index", "dec": 0, "sub": "The definition.", "credit": CREDIT,
        "rows": [{"r": i + 1, "n": f"Player {i}", "c": "SEA", "t": str(140 - 5 * i), "v": 140 - 5 * i} for i in range(5)]}},
    "superlative_dumbbell": {"title": "Largest projected drop", "url": "eephus.io/awards/", "aw": {
        "mode": "superlative", "pic": "dumbbell", "dec": 1, "credit": CREDIT,
        "rows": [{"r": i + 1, "n": f"Player {i}", "c": "SEA", "t": f"-{i + 1}.0", "v": -(i + 1.0), "f": 6.0, "to": 5.0 - i}
                 for i in range(5)]}},
    "superlative_signed": {"title": "Results ahead of contact quality", "url": "eephus.io/awards/", "aw": {
        "mode": "superlative", "pic": "signed", "dec": 3, "credit": CREDIT,
        "rows": [{"r": i + 1, "n": f"Player {i}", "c": "TB", "t": f"-0.0{5 - i}", "v": -(5 - i) / 100} for i in range(5)]}},
    "ballot": {"title": "My 2026 AL MVP ballot", "url": "eephus.io/awards/#section=ballot&season=2026&b=al-mvp:h9rk",
               "icon": "aw-ballot", "aw": {
        "mode": "ballot", "allTitle": "My 2026 ballots", "allUrl": "eephus.io/awards/#section=ballot&b=all",
        "ballots": [{"h": "My 2026 AL MVP ballot", "rows": [{"l": f"{i + 1} pts", "n": "Viewer Choice (DET)" if i == 0 else None}
                                                            for i in range(10)]},
                    {"h": "My 2026 NL Cy Young ballot", "rows": [{"l": "1st", "n": "Second Card (PHI)"}]}]}},
}

DRAW_JS = """async ([spec, fmt, theme]) => {
  document.documentElement.setAttribute("data-theme", theme);
  if (window.EephusExport && EephusExport.loadIcons) await EephusExport.loadIcons();
  window.__ft = [];
  const c = EEPHUS_GFX.drawAwards(Object.assign({kind: "awards", module: "Awards", icon: "aw-podium"}, spec), fmt);
  let url = null, err = null;
  try { url = c.toDataURL("image/png"); } catch (e) { err = String(e); }
  return {w: c.width, h: c.height, ok: !!url && url.length > 2000, err, text: window.__ft.slice()};
}"""


@pytest.fixture(scope="module")
def browser_page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            br = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = br.new_page()
        page.add_init_script(INIT)

        def route(r):
            url = r.request.url
            if not url.startswith(ORIGIN + "/"):
                return r.abort()
            rel = url[len(ORIGIN) + 1:].split("?")[0].split("#")[0]
            if rel in ("", "index.html"):
                return r.fulfill(status=200, body=SHELL, content_type="text/html")
            f = ROOT / rel
            if rel.startswith(("assets/", "data/")) and f.is_file():
                return r.fulfill(status=200, body=f.read_bytes(),
                                 content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            return r.fulfill(status=404, body="")
        page.route("**/*", route)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(ORIGIN + "/")
        page.wait_for_function("() => window.EEPHUS_GFX && window.EEPHUS_GFX.drawAwards")
        page._errors = errors
        yield page
        br.close()


@pytest.mark.parametrize("name", list(SPECS))
@pytest.mark.parametrize("fmt", list(FORMATS))
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_mode_renders_untainted_at_every_format(browser_page, name, fmt, theme):
    r = browser_page.evaluate(DRAW_JS, [SPECS[name], fmt, theme])
    W, H = FORMATS[fmt]
    assert (r["w"], r["h"]) == (2 * W, 2 * H)
    assert r["ok"] and r["err"] is None, r["err"]
    text = " | ".join(r["text"])
    for s in r["text"]:
        assert not copy_lint.BAN_RE.search(s) and not awards_core.verdict_hits(s), s
    if name.startswith("podium"):
        for row in SPECS[name]["aw"]["rows"]:
            assert row["n"] in text and f'{row["t"]} {SPECS[name]["aw"]["unit"]}' in text
    if name == "slate":
        assert "Not published" in text and "AL" in r["text"] and "NL" in r["text"]
    assert not browser_page._errors, browser_page._errors


def test_the_ballot_card_is_the_viewers_and_carries_no_selection(browser_page):
    tw = browser_page.evaluate(DRAW_JS, [SPECS["ballot"], "twitter", "light"])
    pt = browser_page.evaluate(DRAW_JS, [SPECS["ballot"], "portrait", "dark"])
    for r in (tw, pt):
        assert "Choices mine. Numbers from eephus.io." in r["text"]
        joined = " ".join(r["text"]).lower()
        for banned in ("selection", "leaders on the rule", "eephus place"):
            assert banned not in joined, banned
        assert CREDIT not in r["text"], "the ballot card's footer is the viewer's line"
    assert "Second Card (PHI)" not in tw["text"] and "My 2026 AL MVP ballot" in tw["text"]
    assert "Second Card (PHI)" in pt["text"] and "My 2026 ballots" in pt["text"]
    assert "eephus.io/awards/#section=ballot&b=all" in pt["text"]


def test_the_modal_opens_the_awards_kind_with_format_and_without_show(browser_page):
    spec = dict(SPECS["podium"], kind="awards", module="Awards", format="twitter", filenameBase="t")
    browser_page.evaluate("(s) => EEPHUS_GFX.open(s)", spec)
    browser_page.wait_for_selector("#egfx-preview canvas", timeout=20000)
    r = browser_page.evaluate("""() => ({
      w: document.querySelector('#egfx-preview canvas').width,
      fmt: getComputedStyle(document.querySelector('.egfx-ctrl-format')).display,
      count: getComputedStyle(document.querySelector('.egfx-ctrl-count')).display,
      accent: document.querySelector('[data-egfx-accent].is-active').dataset.egfxAccent })""")
    assert r == {"w": 2400, "fmt": r["fmt"], "count": "none", "accent": "lilac"} and r["fmt"] != "none"
    browser_page.evaluate("() => EEPHUS_GFX.close()")
