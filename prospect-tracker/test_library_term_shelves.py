# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Library's term shelves and Formulas leaf (LIBRARY_4, Library plan 3.3).

Before: 24 categories in 11 display groups, two categories with no group that
rendered as stray lower-case chips (industry: jaws, war7; method:
committee_horizon), two arbitration models filed under MLB Rules, the display
term P(enter) carried twice (p_enter and enter_prob), and one collapsed card
wall 67,408 px tall at 390. Now every entry carries one of seven sections, set
by tools/glossary_sections.py; the Terms view is an index beside the selected
entry at 900 px and wider and one-line rows that open in place below that; the
Formulas leaf lists every non-blank formula by section.

Playwright is optional; the browser tests skip cleanly without it."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import glossary_sections as GS  # noqa: E402

SECTIONS = ("Prospects", "Players & Stats", "Value & Contracts", "Clubs",
            "Site & Methods", "Diamond", "Hall of Fame")


def _gl() -> dict:
    return json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))


def _formula_ids() -> set[str]:
    return {e["id"] for e in _gl()["entries"]
            if isinstance(e.get("formula"), str) and e["formula"].strip()}


# ---- data ---------------------------------------------------------------------

def test_every_entry_has_a_section_in_the_seven():
    g = _gl()
    assert GS.SECTIONS == SECTIONS
    bad = [e["id"] for e in g["entries"] if e.get("section") not in SECTIONS]
    assert not bad, f"entries without one of the seven sections: {bad}"
    # the stored field is the rule's output (first module, foundations by group)
    drift = [e["id"] for e in g["entries"] if e["section"] != GS.section_for(e, g["groups"])]
    assert not drift, f"section differs from tools/glossary_sections.py: {drift}"
    # the old links still read category and groups
    assert all(e.get("category") for e in g["entries"])
    assert g["groups"].get("fa") == "Free Agency"
    assert g["groups"].get("methodology") == "Platform & Methodology"


def test_the_strays_and_the_arbitration_models_have_their_section():
    by = {e["id"]: e for e in _gl()["entries"]}
    for slug in ("jaws", "war7", "committee_horizon"):
        assert by[slug]["section"] == "Hall of Fame", slug
    for slug in ("arb_award_model", "arb_market_residual"):
        assert by[slug]["section"] == "Value & Contracts", slug


def test_one_p_enter_and_the_retired_slug_resolves():
    g = _gl()
    hits = [e["id"] for e in g["entries"] if e["term"] == "P(enter)"]
    assert hits == ["p_enter"], hits
    by = {e["id"]: e for e in g["entries"]}
    assert "enter_prob" not in by
    keep = by["p_enter"]
    # the merge kept the richer text: the band-priced method, formula and example
    assert "log-normal" in keep["methodology"] and "enterProbSrc" in keep["methodology"]
    assert keep["formula"].startswith("player-held") and keep["example"].startswith("A $20M club option")
    assert {"enter probability", "exercise probability"} <= set(keep["aliases"])
    assert not any("enter_prob" in (e.get("seeAlso") or []) for e in g["entries"])
    js = (ROOT / "assets" / "eephus-gl.js").read_text(encoding="utf-8")
    assert 'const SLUG_ALIASES = { enter_prob: "p_enter" };' in js
    assert "if (map[canon(q)]) return canon(q);" in js


def test_the_section_script_is_idempotent_and_stamps_through_glossary_version():
    assert GS.main(["--check"]) == 0, "data/glossary.json is not the script's output"
    src = (ROOT / "tools" / "glossary_sections.py").read_text(encoding="utf-8")
    assert "from build_glossary_data import glossary_version" in src
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", _gl()["version"])


def test_the_formulas_leaf_is_listed_and_the_shell_carries_the_provenance_row():
    import build_site as B
    v = {x["id"]: x for x in B.GLOSSARY_VIEWS}["formulas"]
    assert v.get("listed", True) is not False
    shell = B.build_glossary()
    assert '<div id="gl-prov" role="group" aria-label="Provenance"></div>' in shell
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert 'render: renderFormulas, aliases: [] },' in js


# ---- render -------------------------------------------------------------------

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
  const q = s => [...document.querySelectorAll(s)];
  const sel = document.querySelector('#gl-entry .gl-entry-card');
  const open = document.querySelector('#gl-index .gl-row.is-open');
  const act = document.querySelector('#gl-cats .chip.active');
  return {
    h: document.documentElement.scrollHeight, sw: document.documentElement.scrollWidth, iw: innerWidth,
    cats: q('#gl-cats .chip').map(b => b.dataset.glCat),
    labels: q('#gl-cats .chip').map(b => b.textContent.replace(/\\s+\\d+\\s*$/, '').trim()),
    heads: q('#gl-index .gl-sec-head').map(h => h.dataset.glSec),
    prov: q('#gl-prov [data-gl-prov]').map(b => b.dataset.glProv),
    active: act ? act.dataset.glCat : null,
    rows: q('#gl-index .gl-row').map(r => r.dataset.slug),
    opened: q('#gl-index .gl-row-body:not([hidden])').length,
    sel: sel ? sel.dataset.slug : null,
    open: open ? open.dataset.slug : null,
    pEnter: q('#gl-index .gl-row-name').filter(n => n.textContent.trim() === 'P(enter)').length,
    fx: q('#formulas-body [data-fx-slug]').map(r => r.dataset.fxSlug),
  };
}"""


def _probe(browser, base, hsh, width, wait="#gl-index .gl-row"):
    errs: list[str] = []
    page = browser.new_page(viewport={"width": width, "height": 900 if width > 900 else 844})
    page.on("pageerror", lambda e: errs.append(e.message))
    try:
        page.goto(base + "glossary/index.html" + hsh, wait_until="load", timeout=15_000)
        page.wait_for_selector(wait, timeout=10_000)
        page.wait_for_timeout(300)
        out = page.evaluate(_PROBE)
    finally:
        page.close()
    assert not errs, errs
    assert out["sw"] == out["iw"], "the page scrolls sideways"
    return out


def test_terms_at_1280_is_short_and_shows_only_the_seven(browser):
    g = _gl()
    with serve_site() as base:
        out = _probe(browser, base, "", 1280)
    assert out["h"] < 8000, f"Terms view at 1280 is {out['h']} px tall"
    assert out["opened"] == 0 and out["sel"] is None
    assert out["cats"] == ["all"] + list(SECTIONS)
    assert out["labels"][1:] == list(SECTIONS), out["labels"]
    assert out["heads"] == list(SECTIONS)
    assert out["prov"] == ["all", "ark", "industry", "foundation"]
    assert sorted(out["rows"]) == sorted(e["id"] for e in g["entries"])
    assert out["pEnter"] == 1


@pytest.mark.parametrize("width", [1280, 390])
def test_the_retired_slug_opens_p_enter(browser, width):
    with serve_site() as base:
        out = _probe(browser, base, "#g=enter_prob", width)
    if width > 900:
        assert out["sel"] == "p_enter"
    else:
        assert out["open"] == "p_enter"


def test_old_category_links_land_on_their_section(browser):
    by = {e["id"]: e for e in _gl()["entries"]}
    with serve_site() as base:
        fa = _probe(browser, base, "#cat=Free%20Agency", 1280)
        plat = _probe(browser, base, "#cat=Platform%20%26%20Methodology", 1280)
    assert fa["active"] == "Value & Contracts"
    assert fa["rows"] and all(by[s]["section"] == "Value & Contracts" and "fa" in by[s]["module"]
                              for s in fa["rows"])
    assert plat["active"] == "Site & Methods"
    assert sorted(plat["rows"]) == sorted(s for s, e in by.items() if e["section"] == "Site & Methods")


@pytest.mark.parametrize("width", [1280, 390])
def test_the_formulas_leaf_lists_exactly_the_non_blank_formulas(browser, width):
    want = _formula_ids()
    with serve_site() as base:
        out = _probe(browser, base, "#view=formulas", width, wait="#formulas-body [data-fx-slug]")
    assert len(out["fx"]) == len(set(out["fx"])) == len(want)
    assert set(out["fx"]) == want
