# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Launch smoke test for the unified Glossary & Methodology module
(/glossary/ + assets/glossary.js + assets/eephus-gl.js + data/glossary.json).

Mirrors test_index_html_loads.py: boots the page in headless Chromium and
asserts the JS actually runs — term cards render from the unified data
layer, all four views (Terms / How to Read / Methodology / Source
Comparison) reach a defined state, #g= deep links land on their card, the
site-wide ⌘K palette opens and finds terms, and the retired PROSPX
#tab=glossary deep links redirect here with term + sub-view intact.

Playwright is an OPTIONAL dependency; tests skip cleanly without it."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).parent


@pytest.fixture(scope="module")
def server():
    """Shared harness (conftest.serve_site): HTTP/1.1 + threaded.

    Both settings are load-bearing and the reason this is no longer
    re-typed per module; see conftest._QuietHTTP for the measured
    HTTP/1.0 large-file truncation this fixes."""
    with serve_site() as base:
        yield base


@pytest.fixture(scope="module")
def browser():
    """One chromium per module (was: one launch per test, ~5 per run).
    browser.new_page() gives each test a fresh isolated context, so test
    isolation matches the old fresh-browser-per-test behavior."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        yield b
        b.close()


def _browser_page(browser, page_errors):
    page = browser.new_page()
    page.on("pageerror", lambda err: page_errors.append(err.message))
    return page


def test_glossary_data_layer_is_valid():
    """The canonical layer parses, has no duplicate slugs, and every entry
    carries the fields the runtime renders from."""
    d = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    entries = d["entries"]
    assert len(entries) >= 190, f"expected the full unified layer, got {len(entries)}"
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "duplicate slugs in glossary.json"
    idset = set(ids)
    for e in entries:
        assert e.get("term") and e.get("definition") and e.get("category"), \
            f"{e.get('id')}: missing term/definition/category"
        for ref in e.get("seeAlso", []):
            assert ref in idset, f"{e['id']}: dangling seeAlso → {ref}"
    # Permalink-stable legacy slugs must survive every rebuild (#g= URLs).
    for legacy in ("pwr_plus", "tvi", "sur_plus", "farm_report_card"):
        assert legacy in idset, f"legacy permalink slug missing: {legacy}"


def test_terms_view_renders_from_data_layer(server, browser):
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "glossary/index.html", wait_until="load", timeout=15_000)
        page.wait_for_selector(".gl-app .glossary-card", timeout=10_000)
        n_cards = page.evaluate("document.querySelectorAll('.gl-app .glossary-card').length")
        n_chips = page.evaluate("document.querySelectorAll('#gl-cats .chip').length")
    finally:
        page.close()

    assert not page_errors, "JS errors on load:\n  " + "\n  ".join(page_errors)
    assert n_cards >= 190, f"terms view rendered only {n_cards} cards"
    assert n_chips >= 8, f"group chips missing ({n_chips})"


def test_all_four_views_render(server, browser):
    page_errors: list[str] = []
    results: dict[str, int] = {}
    # Per-view readiness signals: the static views are ready when populated;
    # models + source-comparison lazy-fetch their JSON, so wait for the same
    # rendered markers the assertions below check. These condition waits
    # replace a fixed 900ms sleep per view; timeouts are swallowed so the
    # assertions do the failing.
    ready = {
        "models": " && el.innerHTML.indexOf('gl-verdict') !== -1",
        "source-comparison": (
            " && (el.innerHTML.indexOf('The full head-to-head') !== -1"
            " || el.innerHTML.indexOf('A different kind of Future Value') !== -1"
            " || el.innerHTML.indexOf('no resolved cohorts') !== -1)"),
        # Source Accuracy lazy-fetches source_cohort_accuracy.json; it is ready
        # once the sub-tab bar and the read-first tiles have rendered, never on
        # the loading placeholder.
        "source-accuracy": (
            " && el.innerHTML.indexOf('sacc-tabs') !== -1"
            " && (el.innerHTML.indexOf('meth-find-card') !== -1"
            " || el.innerHTML.indexOf('could not be loaded') !== -1)"),
    }
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "glossary/index.html", wait_until="load", timeout=15_000)
        page.wait_for_selector(".gl-app .glossary-card", timeout=10_000)
        for view, body_id in [("guide", "guide-body"),
                              ("methodology", "methodology-body"),
                              ("models", "models-body"),
                              ("source-comparison", "source-comparison-body"),
                              ("source-accuracy", "source-accuracy-body")]:
            page.click(f'[data-glossary-view="{view}"]')
            try:
                page.wait_for_function(
                    "id => { const el = document.getElementById(id);"
                    " return !!el && el.innerHTML.length >= 200"
                    + ready.get(view, "") + "; }",
                    arg=body_id, timeout=10_000)
            except Exception:
                pass
            results[view] = page.evaluate(
                f"document.getElementById('{body_id}').innerHTML.length")
        # The backtest must actually RENDER, not strand its loading state
        # (the missed-port _RATER_META bug hung here while passing a
        # length-only assertion - never again).
        sc_html = page.evaluate(
            "document.getElementById('source-comparison-body').innerHTML")
        # Models & Proofs must render the registry-driven accountability cards,
        # not strand on loading (same lesson).
        models_html = page.evaluate(
            "document.getElementById('models-body').innerHTML")
        sacc_html = page.evaluate(
            "document.getElementById('source-accuracy-body').innerHTML")
    finally:
        page.close()

    assert not page_errors, "JS errors during view walk:\n  " + "\n  ".join(page_errors)
    empty = [v for v, n in results.items() if n < 200]
    assert not empty, f"views rendered (near-)empty: {empty} — {results}"
    assert "Loading backtest" not in sc_html, "source comparison stranded on its loading state"
    # 2026-07-06: the data-state header is "The full head-to-head", led by the hero
    # verdict banner ("A different kind of Future Value"); the empty-state text is unchanged.
    # COVERAGE GAP CLOSED 2026-08-10. This used to accept the EMPTY-STATE string
    # as a pass, which is how a genuinely broken view shipped green: a
    # ReferenceError inside _hhFloorClause took out _methHeroBanner and blanked
    # the whole view, and "no resolved cohorts" satisfied the assertion. An
    # empty state is only a correct outcome when the artifact is actually empty,
    # so the branch is now chosen by the DATA rather than accepted either way.
    _sb = ROOT / "data" / "source_backtest.json"
    _has_data = False
    if _sb.exists():
        _acc = (json.loads(_sb.read_text(encoding="utf-8")) or {}).get("accuracy") or {}
        _has_data = bool((_acc.get("pooled") or {}).get("xfv"))
    if _has_data:
        assert "A different kind of Future Value" in sc_html, (
            "source_backtest.json carries pooled accuracy, so the hero banner MUST "
            "render; a blank or empty-state view here is the 2026-08-10 failure")
        assert "no resolved cohorts" not in sc_html, (
            "source comparison fell back to its empty state while the artifact has data")
    else:
        assert ("The full head-to-head" in sc_html
                or "no resolved cohorts" in sc_html), \
            "source comparison rendered neither data nor empty-state"
    assert "gl-verdict" in models_html, "Models & Proofs stranded (no verdict badges rendered)"
    assert "Predicts" in models_html, "Models & Proofs cards missing the Predicts row"
    # Source Accuracy (C-A4): the sub-tab bar plus the read-first tiles, never
    # the loading placeholder.
    assert "Loading the cohort accuracy measurement" not in sacc_html, \
        "source accuracy stranded on its loading state"
    assert "sacc-tabs" in sacc_html, "source accuracy rendered no sub-tab bar"
    assert "weights ship from this measurement" in sacc_html, \
        "source accuracy missing the zero-weights tile"


def test_progress_ledger_fetch_resolves_and_renders(server, browser):
    """EV-00: /data/efv_progress.json resolves on the served path and the
    Source Comparison view renders the ledger section from it (headline line,
    chart, dated table), with the tilted frames collapsed and never charted."""
    led = ROOT / "data" / "efv_progress.json"
    if not led.exists():
        pytest.skip("data/efv_progress.json not built")
    doc = json.loads(led.read_text(encoding="utf-8"))
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "glossary/index.html#view=source-comparison",
                  wait_until="load", timeout=15_000)
        status = page.evaluate(
            "() => fetch('/data/efv_progress.json', {cache: 'no-cache'})"
            ".then(r => r.status)")
        page.wait_for_function(
            "() => { const e = document.getElementById('source-comparison-body');"
            " return !!e && e.innerHTML.indexOf('progress ledger') !== -1; }",
            timeout=15_000)
        out = page.evaluate("""() => {
          const el = document.getElementById('source-comparison-body');
          const svg = [...el.querySelectorAll('.meth-chart svg')].find(s =>
            /eFV minus PROSPX consensus/.test(s.getAttribute('aria-label') || ''));
          const det = el.querySelector('details.scx-progress-tilted');
          return {
            marks: svg ? svg.querySelectorAll('circle, path[d$="Z"]').length : -1,
            tilted: det ? det.querySelectorAll('tbody tr').length : 0,
            open: det ? det.open : null,
            text: el.innerText,
          };
        }""")
    finally:
        page.close()
    assert status == 200
    assert not page_errors, "JS errors: " + " | ".join(page_errors)
    rows = doc["rows"]
    charted = [r for r in rows if r.get("role") not in ("tilted", "secondary")
               and r.get("frame") in ("vm", "vm2", "vm_dev", "lv_dev", "lv_res", "vm_pros")]
    assert out["marks"] == len(charted), (out["marks"], len(charted))
    tilted = [r for r in rows if r.get("role") == "tilted"]
    assert out["tilted"] == len(tilted) and out["open"] in (False, None)
    head = [r for r in rows if r["frame"] == doc["headline_frame"]][-1]
    assert f"n {int(head['n']):,}" in out["text"]
    assert head["verdict"] in out["text"]
    assert f"{head['raters']['efv']['spearman']:.3f}" in out["text"]
    # EV-01: the timing-pinned headline candidate prints its own line and row.
    cand = [r for r in rows if r.get("role") == "headline_candidate"]
    if cand:
        c = cand[-1]
        assert "Vintage-matched, timing-pinned" in out["text"]
        assert f"{c['raters']['efv']['spearman']:.3f}" in out["text"]
        assert "headline candidate" in out["text"]


def test_source_accuracy_subtabs_render(server, browser):
    """Every one of the six sub-tabs renders real content, the verdict column
    is three-valued (a source name only where the artifact says the cell is
    answerable), and the precision block honours BOTH branches of
    precision_label_free.identified."""
    art = json.loads(
        (ROOT / "data" / "source_cohort_accuracy.json").read_text(encoding="utf-8"))
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    html: dict[str, str] = {}
    try:
        page.goto(server + "glossary/index.html#view=source-accuracy",
                  wait_until="load", timeout=15_000)
        page.wait_for_function(
            "() => { const el = document.getElementById('source-accuracy-body');"
            " return !!el && el.innerHTML.indexOf('sacc-tabs') !== -1"
            " && el.innerHTML.indexOf('Loading the cohort') === -1; }",
            timeout=15_000)
        for tab in ("read-first", "side", "archetype", "cuts", "precision", "coverage"):
            page.click(f'[data-sacc-tab="{tab}"]')
            page.wait_for_timeout(120)
            html[tab] = page.evaluate(
                "document.getElementById('source-accuracy-body').innerHTML")
    finally:
        page.close()

    assert not page_errors, "JS errors on source accuracy:\n  " + "\n  ".join(page_errors)
    for tab, body in html.items():
        assert len(body) >= 1200, f"sub-tab {tab} rendered near-empty ({len(body)})"

    # The verdict column is the point. Every unanswerable cell carries the
    # literal string, and a source name renders ONLY where answerable is true.
    #
    # DERIVED FROM THE ARTIFACT, NOT PINNED (2026-09-06). This used to assert
    # `by_acquisition.draft_hs.answerable is True` and then look for the literal
    # "MLB Pipeline". The nightly regen on 2026-09-05 flipped that cell to
    # unanswerable on live data (d_rho -0.05159 against mde95 0.05393, a margin
    # of 0.0023) and the test went red for a MEASUREMENT that moved, not a
    # defect. A cell's answerability is a live reading; the RULE is what this
    # test owns. So: read the artifact, require the unanswerable string wherever
    # a cell is unanswerable, and require the winner's name wherever one is
    # answerable. When no cell is answerable the positive branch has nothing to
    # check and says so rather than passing vacuously.
    acc = art["accuracy"]
    side = html["side"]
    cells = {**{f"by_side.{k}": v for k, v in acc["by_side"].items()},
             **{f"by_acquisition.{k}": v for k, v in acc["by_acquisition"].items()}}
    unanswerable = [k for k, v in cells.items() if v.get("answerable") is False]
    answerable = [k for k, v in cells.items() if v.get("answerable") is True]
    assert unanswerable, "every side/acquisition cell became answerable; re-read this tab"
    assert "not resolvable at this power" in side, (
        f"{len(unanswerable)} cell(s) are unanswerable ({unanswerable}) and the tab "
        "renders no unresolvable verdict")
    for key in answerable:
        winner = cells[key].get("winner")
        assert winner and winner != "not_resolvable", (
            f"{key} is answerable with no winner recorded: {cells[key]}")
        label = {"fangraphs": "FanGraphs", "mlb_pipeline": "MLB Pipeline",
                 "prospx_consensus": "PROSPX"}.get(winner, winner)
        assert label in side, f"answerable cell {key} lost its winner {label} from the tab"
    # Archetype tab carries the family test and the A/B receipt, not just rows.
    arch = html["archetype"]
    het = art["multiplicity"]["archetype_heterogeneity"]
    assert f"{het['chi2_p']:.4f}" in arch, "Cochran Q p missing from the archetype tab"
    assert f"{het['permutation_p_labels']:.4f}" in arch, "label-permutation p missing"
    assert "no ship" in arch, "the six-arm A/B receipt did not render its verdicts"
    # The two range/level warnings are artifact fields and must be rendered.
    cuts = html["cuts"]
    assert acc["by_fv_tier_range_restriction_warning"][:60] in cuts
    assert acc["level_at_grading"]["note"][:60] in cuts
    # Precision: the wording block is verbatim and at the TOP of the tab.
    prec = html["precision"]
    assert "Precision is not accuracy." in prec
    assert prec.index("Precision is not accuracy.") < len(prec) // 2, \
        "the precision wording block must lead the tab, not trail it"
    p = art["precision_label_free"]
    if p.get("identified") is False or not p.get("estimator_primary_em_fiml"):
        # UNIDENTIFIED branch: reason + restores_when, and NO table, sigma or alpha.
        assert p["reason"][:50] in prec, "unidentified precision hid its reason"
        assert p["restores_when"][:40] in prec, "unidentified precision hid its restore condition"
        assert "sacc-empty" in prec, "unidentified precision skipped its empty-state"
        # NO table, NO sigma, NO alpha. Matched on the identified branch's own
        # markers, not on loose words: the artifact's `reason` string itself
        # says "no GLS weight and no alpha are computed", so a bare substring
        # check on those words passes for the wrong reason.
        assert "Per-outlet precision" not in prec, \
            "unidentified precision rendered an estimate table"
        for th in ("<th>Sigma</th>", "<th>GLS weight</th>", "<th>Loading b</th>"):
            assert th not in prec, f"unidentified precision rendered {th}"
    else:
        assert "<th>GLS weight</th>" in prec, \
            "identified precision did not render its source table"
    # Coverage tab names the exclusion and its size.
    cov = html["coverage"]
    cs = acc["coverage_selection"]
    assert f"{cs['union_player_year_slots']:,}" in cov, "coverage tab lost the union slot count"
    assert cs["selection_model"]["why_not"][:50] in cov


def test_view_chips_match_whitelist():
    """THE MISSING GATE. A view is registered in FOUR places and there was no
    test that they agree, so a chip without a whitelist entry rendered a dead
    button while the suite stayed green (the 2026-06-10 Source Comparison
    lesson, documented at the top of this module). All four are asserted here:

      (a) the URL whitelist in assets/glossary.js syncFromURL
      (b) the view-id -> container-id map in render()
      (c) the render() dispatch chain
      (d) the chip row in the built glossary/index.html

    Pure file parsing, no browser: this must fail on a mismatch even where
    playwright is absent."""
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    shell = (ROOT / "glossary" / "index.html").read_text(encoding="utf-8")

    m = re.search(r"\[((?:\s*\"[a-z0-9-]+\"\s*,?)+)\]\s*\.includes\(v\)", js)
    assert m, "could not find the URL view whitelist in assets/glossary.js"
    whitelist = set(re.findall(r"\"([a-z0-9-]+)\"", m.group(1)))

    m = re.search(r"const ids = \{(.*?)\};", js, re.S)
    assert m, "could not find the view -> container id map in assets/glossary.js"
    id_map = dict(re.findall(r"\"?([a-z0-9-]+)\"?\s*:\s*\"([a-z0-9-]+)\"", m.group(1)))

    chips = set(re.findall(r'data-glossary-view="([a-z0-9-]+)"', shell))
    assert chips, "the built glossary shell has no view chips"

    assert chips == whitelist, (
        "view chips and the URL whitelist disagree - a chip with no whitelist "
        f"entry is a dead button.\n  chips only: {sorted(chips - whitelist)}"
        f"\n  whitelist only: {sorted(whitelist - chips)}")
    assert set(id_map) == whitelist, (
        "the view -> container map and the whitelist disagree.\n"
        f"  map only: {sorted(set(id_map) - whitelist)}"
        f"\n  whitelist only: {sorted(whitelist - set(id_map))}")
    for view, body_id in id_map.items():
        assert f'id="{body_id}"' in shell, \
            f"view {view!r} maps to #{body_id}, which the built shell does not contain"
        # Every non-default view needs its own dispatch arm; terms is the else.
        if view != "terms":
            assert f'_S.view === "{view}"' in js, \
                f"view {view!r} is whitelisted and mounted but never dispatched"
    # Every non-terms container ships hidden, so the router owns visibility.
    for view, body_id in id_map.items():
        if view == "terms":
            continue
        assert f'<div id="{body_id}" style="display:none;">' in shell, \
            f"#{body_id} does not ship hidden; it will render stacked under Terms"


def test_library_view_renders(server, browser):
    """The Library view (2026-08-04): #view=library renders the standalone-page
    index with all three groups and the recon-verified routes. Registered in
    all four places (build_site chip row, whitelist, view->body map, dispatch)
    or it silently hangs - the 2026-06-10 Source Comparison lesson. Skips
    cleanly while the built shell predates the library-body mount div (the
    orchestrator rebuild republishes it)."""
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "glossary/index.html#view=library", wait_until="load",
                  timeout=15_000)
        has_shell = page.evaluate("!!document.getElementById('library-body')")
        if not has_shell:
            page.close()
            pytest.skip("built glossary shell predates the Library mount div "
                        "(build_site rebuild pending)")
        page.wait_for_function(
            "() => { const el = document.getElementById('library-body');"
            " return !!el && el.innerHTML.indexOf('meth-table') !== -1; }",
            timeout=10_000)
        html = page.evaluate("document.getElementById('library-body').innerHTML")
        visible = page.evaluate(
            "document.getElementById('library-body').style.display !== 'none'")
    finally:
        if not page.is_closed():
            page.close()

    assert not page_errors, "JS errors on library view:\n  " + "\n  ".join(page_errors)
    assert visible, "#view=library did not unhide the library body"
    for group in ("Full pages", "In-module artifact pages", "Player pages"):
        assert group in html, f"library view missing the {group!r} group"
    # Spot-check recon-verified routes from every module family.
    for route in ("/parks/", "/fa/#view=dpw", "/projections/#view=teams",
                  "/prospx/#tab=timemachine", "/pal/#posfit=ladder",
                  "/glossary/#view=models"):
        assert route in html, f"library view missing route {route}"
    # PUBLIC ONLY: the dark previews must never be listed.
    assert "tape=1" not in html and "cards=1" not in html, \
        "library view leaked a dark-preview route"


def test_deep_link_expands_and_highlights_term(server, browser):
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "glossary/index.html#g=wag", wait_until="load",
                  timeout=15_000)
        page.wait_for_selector("#g-wag.is-highlighted", timeout=10_000)
        opened = page.evaluate(
            "!!document.querySelector('#g-wag details[open]')")
    finally:
        page.close()

    assert not page_errors, "JS errors on deep link:\n  " + "\n  ".join(page_errors)
    assert opened, "#g=wag arrived collapsed — direct anchors must open the full read"


def test_quick_search_palette_finds_terms(server, browser):
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "glossary/index.html", wait_until="load", timeout=15_000)
        page.wait_for_selector(".gl-app .glossary-card", timeout=10_000)
        page.keyboard.press("Control+k")
        page.wait_for_selector("#qk-overlay.is-open", timeout=5_000)
        page.fill("#qk-input", "wag")
        page.wait_for_selector(".qk-row", timeout=5_000)
        first = page.evaluate(
            "document.querySelector('.qk-row .qk-row-name').textContent")
        # Ctrl+K must NOT fire while typing in an input (the focus guard the
        # legacy duplicate handler lacked) — overlay stays open, no toggle.
        page.keyboard.press("Control+k")
        still_open = page.evaluate(
            "document.getElementById('qk-overlay').classList.contains('is-open')")
    finally:
        page.close()

    assert not page_errors, "JS errors in palette:\n  " + "\n  ".join(page_errors)
    assert first.strip().upper() == "WAG", f"top palette hit for 'wag' was {first!r}"
    assert still_open, "Ctrl+K stole focus mid-typing — input guard regressed"


def test_legacy_prospx_deep_link_redirects(server, browser):
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.add_init_script(
            "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}"
            "catch(e){}"
        )
        page.goto(server + "prospx/index.html#tab=glossary&g=wag&gview=methodology",
                  wait_until="load", timeout=15_000)
        page.wait_for_url("**/glossary/**", timeout=10_000)
        url = page.url
    finally:
        page.close()

    assert "/glossary/" in url, f"legacy #tab=glossary did not redirect: {url}"
    assert "g=wag" in url, f"redirect dropped the term param: {url}"
    assert "view=methodology" in url, f"redirect dropped the sub-view: {url}"
