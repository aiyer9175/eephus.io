# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Library's one view registry (LIBRARY_3, plan section 3.1).

A view used to need four registration points (the build_site chip, the URL
whitelist, the body map and the dispatch), and a missed point shipped a dead
chip while the suite stayed green (the 2026-06-10 Source Comparison lesson).
Now assets/glossary.js VIEWS generates the whitelist, the body map and the
dispatch, and build_site.GLOSSARY_VIEWS emits the strip and the containers.
Pinned here: the two lists are equal; every legacy #view= value resolves; the
strip is four shelves over the active shelf's leaves, one state attribute per
chip, no dead outbound link; at 390 the chips are 44 px tall, nothing sits off
screen and the active leaf is visible.

Playwright is optional; the browser tests skip cleanly without it."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import serve_site

import build_site as B

ROOT = Path(__file__).parent
GLJS = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")

# Every #view= value a link or bookmark carried before the registry, and the
# view it must open.
LEGACY_VIEWS = {"terms": "terms", "guide": "guide", "methodology": "methodology",
                "source-comparison": "source-comparison",
                "source-accuracy": "source-accuracy", "source-updates": "source-updates",
                "models": "models", "library": "index"}


def _js_registry() -> list[dict]:
    m = re.search(r"const VIEWS = \[\r?\n(.*?)\r?\n\s*\];", GLJS, re.S)
    assert m, "could not find the VIEWS registry in assets/glossary.js"
    out = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue

        def get(k: str, line: str = line):
            hit = re.search(k + r': "([^"]*)"', line)
            return hit.group(1) if hit else None

        al = re.search(r"aliases: \[([^\]]*)\]", line)
        out.append({"id": get("id"), "shelf": get("shelf"), "label": get("label"),
                    "body": get("body"), "href": get("href"),
                    "aliases": tuple(re.findall(r'"([^"]+)"', al.group(1))) if al else (),
                    "listed": "unlisted: true" not in line,
                    "render": "render:" in line})
    return out


def _py_registry() -> list[dict]:
    return [{"id": v["id"], "shelf": v["shelf"], "label": v["label"],
             "body": v.get("body"), "href": v.get("href"),
             "aliases": tuple(v.get("aliases", ())), "listed": v.get("listed", True) is not False}
            for v in B.GLOSSARY_VIEWS]


def test_the_two_registries_are_equal():
    js = _js_registry()
    py = _py_registry()
    assert [v["id"] for v in js] == [v["id"] for v in py]
    for a, b in zip(js, py):
        assert {k: a[k] for k in b} == b, a["id"]
        # an in-page view renders; an outbound leaf is a link and never does
        assert a["render"] == bool(a["body"]) and bool(a["body"]) != bool(a["href"]), a["id"]
    shelves = re.search(r"const SHELVES = \[([^\]]*)\];", GLJS).group(1)
    assert re.findall(r'"([a-z]+)"', shelves) == [s for s, _ in B.GLOSSARY_SHELVES]
    assert [s for s, _ in B.GLOSSARY_SHELVES] == ["reference", "methods", "evidence", "sources"]
    assert {v["shelf"] for v in py} == {s for s, _ in B.GLOSSARY_SHELVES}
    ids = [v["id"] for v in py] + [a for v in py for a in v["aliases"]]
    assert len(ids) == len(set(ids)), "a view id or alias is registered twice"


def test_the_shelves_hold_the_planned_leaves():
    by: dict[str, list[str]] = {}
    for v in B.GLOSSARY_VIEWS:
        by.setdefault(v["shelf"], []).append(v["id"])
    assert by == {
        "reference": ["terms", "guide", "formulas"],
        "methods": ["methodology"],
        "evidence": ["source-comparison", "source-accuracy", "calibration", "models",
                     "models-ledger", "model-updates"],
        "sources": ["source-updates", "data-sources", "index"],
    }
    href = {v["id"]: v.get("href") for v in B.GLOSSARY_VIEWS}
    assert (href["models-ledger"], href["model-updates"], href["data-sources"]) == (
        "/models/", "/models/updates/", "/sources/")
    label = {v["id"]: v["label"] for v in B.GLOSSARY_VIEWS}
    assert label["index"] == "Page Index"


def test_whitelist_body_map_and_dispatch_come_from_the_registry():
    # the hand lists the registry replaced are gone
    assert ".includes(v)) _S.view = v" not in GLJS
    assert "const ids = {" not in GLJS
    assert 'else if (_S.view === "library") renderLibrary();' not in GLJS
    assert '_S.view === "library"' not in GLJS and '_S.view === "index"' not in GLJS
    assert 'const v = VIEW_OF[p.get("view")];' in GLJS
    assert "def.render();" in GLJS


def test_the_shell_mounts_every_in_page_view_once_and_hidden():
    shell = B.build_glossary()
    for v in B.GLOSSARY_VIEWS:
        if not v.get("body"):
            continue
        assert shell.count(f'id="{v["body"]}"') == 1, v["id"]
        if v["id"] == "terms":
            assert '<div id="glossary-rows"></div>' in shell
        else:
            assert f'<div id="{v["body"]}" style="display:none;"></div>' in shell, v["id"]
    built = (ROOT / "glossary" / "index.html").read_text(encoding="utf-8")
    assert built.count('data-gl-shelf-chip="') == 4, "the built shell predates the registry; rebuild it"


def test_every_legacy_view_value_resolves():
    py = _py_registry()
    resolve = {v["id"]: v["id"] for v in py if v["body"]}
    for v in py:
        for a in v["aliases"]:
            resolve[a] = v["id"]
    for old, want in LEGACY_VIEWS.items():
        assert resolve.get(old) == want, old


def test_the_strip_carries_one_state_attribute_per_chip():
    shell = B.build_glossary()
    strip = re.search(r'<nav class="gl-strip".*?</nav>', shell, re.S).group(0)
    assert "aria-pressed" not in strip
    assert f'aria-label="{B.GLOSSARY_DISPLAY_NAME} sections"' in strip
    shelves = re.findall(r'<button class="chip gl-shelf-chip[^"]*" type="button"([^>]*)'
                         r'data-gl-shelf-chip="([a-z]+)"><span class="gl-shelf-name">([^<]+)</span>'
                         r'<span class="gl-shelf-n">(\d+)</span>', strip)
    assert [s[1] for s in shelves] == ["reference", "methods", "evidence", "sources"]
    assert [s[1] for s in shelves if 'aria-current="true"' in s[0]] == ["reference"]
    leaves = re.findall(r'<button class="chip[^"]*" type="button"([^>]*)data-glossary-view="([a-z-]+)">', strip)
    assert [v for a, v in leaves if 'aria-current="page"' in a] == ["terms"]
    # the shelf count is the number of leaves the strip shows on that shelf
    for _a, sid, _label, n in shelves:
        row = re.search(rf'data-gl-leaves="{sid}"[^>]*>(.*?)</div>', strip).group(1)
        shown = len(re.findall(r'<button (?![^>]*\bhidden\b)[^>]*data-glossary-view=', row)) + row.count("<a ")
        assert int(n) == shown, sid
    # unlisted leaves ship hidden until they are current (Formulas is listed
    # since LIBRARY_4 filled it, Calibration since LIBRARY_5 did)
    assert re.search(r'<button class="chip" type="button" data-gl-shelf="reference" data-glossary-view="formulas">', strip)
    assert re.search(r'<button class="chip" type="button" data-gl-shelf="evidence" data-glossary-view="calibration">', strip)
    for v in ("models",):
        assert re.search(rf'data-gl-unlisted hidden data-gl-shelf="[a-z]+" data-glossary-view="{v}"', strip), v
    # only the active shelf's leaf row shows
    assert re.findall(r'data-gl-leaves="([a-z]+)">', strip) == ["reference"]
    # an outbound leaf keeps the Data Sources arrow and never toggles a view
    assert '<a class="chip gl-chip-out" href="/sources/" data-gl-leaf="data-sources">Data Sources →</a>' in strip
    assert '<a class="chip gl-chip-out" href="/models/" data-gl-leaf="models-ledger">Models →</a>' in strip


def test_an_outbound_leaf_whose_page_is_not_built_stays_out(monkeypatch, tmp_path):
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / "index.html").write_text("x", encoding="utf-8")
    monkeypatch.setattr(B, "ROOT", tmp_path)
    strip = B._glossary_strip()
    assert 'href="/sources/"' in strip
    assert 'href="/models/"' not in strip and 'href="/models/updates/"' not in strip
    assert re.search(r'data-gl-shelf-chip="evidence"><span class="gl-shelf-name">Evidence</span>'
                     r'<span class="gl-shelf-n">3</span>', strip)
    monkeypatch.undo()
    # the Model Updates leaf appears once its page is built (LIBRARY_12)
    built = (ROOT / "models" / "updates" / "index.html").is_file()
    assert ('href="/models/updates/"' in B._glossary_strip()) == built


def test_visible_copy_reads_the_display_name():
    shell = B.build_glossary()
    assert f'data-display-name="{B.GLOSSARY_DISPLAY_NAME}"' in shell
    assert "const LIB_NAME = " in GLJS and "dataset.displayName" in GLJS
    # no code line of the client names the module literally (comments aside)
    for n, line in enumerate(GLJS.splitlines(), 1):
        code = re.sub(r"(^|\s)//\s.*$", "", line)
        if code.lstrip().startswith(("//", "*", "/*")):
            continue
        assert not re.search(r"\b(Library|Glossary)\b", code), (n, line.strip()[:120])
    strip = re.search(r'<nav class="gl-strip".*?</nav>', shell, re.S).group(0)
    assert "Glossary" not in strip


# ---- render ------------------------------------------------------------------

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


_PROBE = """() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const chips = [...document.querySelectorAll('.gl-strip .chip')].filter(vis).map(c => {
    const r = c.getBoundingClientRect();
    return { t: c.textContent.trim(), x0: r.left, x1: r.right, h: r.height }; });
  const a = document.querySelector('.gl-strip [aria-current="page"]');
  const r = a ? a.getBoundingClientRect() : null;
  const shown = [...document.querySelectorAll('.gl-app > div[id]')]
    .filter(d => d.id !== 'gl-termbar' && d.style.display !== 'none').map(d => d.id);
  return { chips, active: a ? a.dataset.glossaryView : null,
           activeOn: !!r && r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight,
           pressed: document.querySelectorAll('.gl-strip [aria-pressed]').length,
           scrollW: document.documentElement.scrollWidth, innerW: innerWidth, shown };
}"""


@pytest.mark.parametrize("legacy,want", sorted(LEGACY_VIEWS.items()))
def test_legacy_view_links_open_their_view_at_390(browser, legacy, want):
    errors: list[str] = []
    body = {v["id"]: v.get("body") for v in B.GLOSSARY_VIEWS}[want]
    with serve_site() as base:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda e: errors.append(e.message))
        try:
            page.goto(base + f"glossary/index.html#view={legacy}", wait_until="load", timeout=15_000)
            page.wait_for_function(
                "() => !!document.querySelector('.gl-strip [aria-current=\"page\"]')", timeout=10_000)
            out = page.evaluate(_PROBE)
        finally:
            page.close()
    assert not errors, errors
    assert out["active"] == want
    assert out["shown"] == [body]
    assert out["activeOn"], "the active leaf chip is off screen"
    assert out["pressed"] == 0
    assert out["scrollW"] == out["innerW"]
    assert out["chips"] and all(c["h"] >= 44 for c in out["chips"]), out["chips"]
    assert all(c["x0"] >= 0 and c["x1"] <= out["innerW"] for c in out["chips"]), out["chips"]


def test_a_shelf_chip_opens_its_first_leaf(browser):
    errors: list[str] = []
    with serve_site() as base:
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda e: errors.append(e.message))
        try:
            page.goto(base + "glossary/index.html", wait_until="load", timeout=15_000)
            page.wait_for_selector(".gl-app .glossary-card", timeout=10_000)
            seen = {}
            for sid in ("evidence", "sources", "methods", "reference"):
                page.click(f'[data-gl-shelf-chip="{sid}"]')
                seen[sid] = (page.evaluate(_PROBE)["active"], page.evaluate("location.hash"))
        finally:
            page.close()
    assert not errors, errors
    assert seen == {"evidence": ("source-comparison", "#view=source-comparison"),
                    "sources": ("source-updates", "#view=source-updates"),
                    "methods": ("methodology", "#view=methodology"),
                    "reference": ("terms", "")}
