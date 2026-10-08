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


def _open_view(page, view):
    """Open a view the way a reader does since LIBRARY_3: its shelf chip, then
    its leaf chip. An unlisted view (Models & Proofs) opens from its URL."""
    leaf = page.locator(f'[data-glossary-view="{view}"]')
    if leaf.get_attribute("data-gl-unlisted") is not None:
        page.evaluate(f"location.hash = '#view={view}'")
        return
    page.click(f'[data-gl-shelf-chip="{leaf.get_attribute("data-gl-shelf")}"]')
    page.click(f'[data-glossary-view="{view}"]')


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
        # Calibration (LIBRARY_5) is ready once both artifacts have answered.
        "calibration": " && el.innerHTML.indexOf('Loading the calibration') === -1",
    }
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "glossary/index.html", wait_until="load", timeout=15_000)
        page.wait_for_selector(".gl-app .glossary-card", timeout=10_000)
        for view, body_id in [("guide", "guide-body"),
                              ("methodology", "methodology-body"),
                              ("models", "models-body"),
                              ("source-comparison", "source-comparison-body"),
                              ("source-accuracy", "source-accuracy-body"),
                              ("calibration", "calibration-body")]:
            _open_view(page, view)
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
    # A row is charted when it sits in a chart frame AND carries the Spearman delta the
    # chart plots (the page's _progSeriesRows rule). The DS-17 P(bust) rows carry an AUC
    # for reaching the majors and no Spearman, so they sit in the table only.
    # FP3-1 (2026-09-25): vm1 is superseded and sits in the table only.
    charted = [r for r in rows if r.get("role") not in ("tilted", "secondary", "superseded")
               and r.get("frame") in ("vm2", "vm_dev", "lv_dev", "lv_res", "vm_pros")
               and ((r.get("deltas") or {}).get("vs_prospx_consensus") or {})
               .get("spearman", {}).get("delta") is not None]
    assert out["marks"] == len(charted), (out["marks"], len(charted))
    tilted = [r for r in rows if r.get("role") == "tilted"]
    assert out["tilted"] == len(tilted) and out["open"] in (False, None)
    head = [r for r in rows if r["frame"] == doc["headline_frame"]][-1]
    assert f"n {int(head['n']):,}" in out["text"]
    assert head["verdict"] in out["text"]
    assert f"{head['raters']['efv']['spearman']:.3f}" in out["text"]
    # FP3-1: the timing-pinned frame is the headline; the vm1 rows print in the
    # table as superseded history, with the role they were written with.
    assert doc["headline_frame"] == "vm2"
    assert "Vintage-matched, timing-pinned" in out["text"]
    if any(r.get("role") == "superseded" for r in rows):
        assert "superseded" in out["text"]
        assert "written as headline" in out["text"]
    if head.get("deltas", {}).get("vs_prospx_consensus", {}).get("spearman", {}).get("mde95_status") == "carried":
        assert "carried from vm1" in out["text"]


def _screen_row(name, side, verdict, *, exploratory=False, cons_delta=0.0123, date="2026-10-02"):
    """A synthetic screening row in efv_progress.py's shape (EFV3_B8)."""
    leg = {"delta": 0.0081, "ci95": [0.0012, 0.0151], "mde95": 0.0049, "lb95": 0.0032,
           "floor": 0.0063, "p_perm": 0.002, "holm_p": 0.014, "resolvable": None}
    cons = dict(leg, delta=cons_delta, ci95=None if cons_delta is None else [-0.01, 0.03])
    return {"run_id": f"t|lv_dev|{name}{side}", "date": date, "trigger": "efv_change",
            "model_id": f"efv_v2_screen:wave1:{name}:{side}",
            "model_version": {"label": "fwar@test", "commit": "deadbeef"},
            "frame": "lv_dev", "frame_version": "lv1_v2", "role": "development",
            "tilted": False, "window": [2017, 2019], "n": 900, "n_by_side": {side: 900},
            "statistic": "Spearman within (side, vintage)",
            "raters": {"efv": {"spearman": 0.2101, "auc": 0.6402, "n": 900}},
            "deltas": {"vs_efv_v2_base": {"spearman": leg},
                       "vs_prospx_consensus": {"spearman": cons}},
            "resolvable": None, "verdict": verdict, "share": None,
            "screening": {"wave": 1, "head": "skill", "admitted_folds": 3,
                          "twin_inside_floor": True, "exploratory": exploratory},
            "sources": [], "note": "screening lab; development frame, spent, not a claim"}


#: Seven screening rows; only the first is ADMITTED (PASS, exploratory false) with a
#: consensus delta, so only it may be drawn.
_SEVEN = [("txt_skill_hit", "hit", "PASS", {}),
          ("txt_skill_pit", "pit", "PASS", {"exploratory": True}),
          ("txt_time_hit", "hit", "NULL", {}),
          ("txt_time_pit", "pit", "NULL_HOLM", {}),
          ("pick_overall_time_hit", "hit", "NOT_ADJUDICATED_EXPLORATORY", {"exploratory": True}),
          ("pick_overall_time_pit", "pit", None, {}),
          ("milb_floor_2005", "both", "PASS", {"cons_delta": None})]


@pytest.mark.parametrize("n_screen", [0, 7])
def test_progress_screening_block_renders(server, browser, n_screen):
    """EFV3_B8: the collapsed screening block renders with no screening row and with
    seven; the chart draws only the admitted one (hollow, dashed), the dated table
    holds none of them, and the headline line is the same either way."""
    led = ROOT / "data" / "efv_progress.json"
    if not led.exists():
        pytest.skip("data/efv_progress.json not built")
    doc = json.loads(led.read_text(encoding="utf-8"))
    doc["rows"] = [r for r in doc["rows"]
                   if not str(r.get("model_id") or "").startswith("efv_v2_screen:")]
    base_charted = [r for r in doc["rows"]
                    if r.get("role") not in ("tilted", "secondary", "superseded")
                    and r.get("frame") in ("vm2", "vm_dev", "lv_dev", "lv_res", "vm_pros")
                    and ((r.get("deltas") or {}).get("vs_prospx_consensus") or {})
                    .get("spearman", {}).get("delta") is not None]
    screen = [_screen_row(n, s, v, **kw) for n, s, v, kw in _SEVEN][:n_screen]
    doc["rows"] = doc["rows"] + screen
    body = json.dumps(doc)
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.route("**/data/efv_progress.json*",
                   lambda route: route.fulfill(status=200, content_type="application/json",
                                               body=body))
        page.goto(server + "glossary/index.html#view=source-comparison",
                  wait_until="load", timeout=15_000)
        page.wait_for_function(
            "() => { const e = document.getElementById('source-comparison-body');"
            " return !!e && e.innerHTML.indexOf('Screening lab (development') !== -1; }",
            timeout=15_000)
        out = page.evaluate("""() => {
          const el = document.getElementById('source-comparison-body');
          const svg = [...el.querySelectorAll('.meth-chart svg')].find(s =>
            /eFV minus PROSPX consensus/.test(s.getAttribute('aria-label') || ''));
          const det = el.querySelector('details.scx-progress-screening');
          const main = [...el.querySelectorAll('.meth-table-title')].find(t =>
            /Every ledger row/.test(t.textContent));
          const mainTable = main ? main.parentElement.querySelector(':scope > .table-scroll-x table') : null;
          return {
            marks: svg ? svg.querySelectorAll('circle, path[d$="Z"]').length : -1,
            dashed: svg ? svg.querySelectorAll('circle[stroke-dasharray]').length : -1,
            rows: det ? det.querySelectorAll('tbody tr').length : -1,
            open: det ? det.open : null,
            summary: det ? det.querySelector('summary').textContent : '',
            block: det ? det.textContent : '',
            mainText: mainTable ? mainTable.textContent : '',
            text: el.innerText,
          };
        }""")
    finally:
        page.close()
    assert not page_errors, "JS errors: " + " | ".join(page_errors)
    admitted = 1 if n_screen == 7 else 0
    assert out["marks"] == len(base_charted) + admitted, (out["marks"], len(base_charted))
    assert out["dashed"] == admitted
    assert out["rows"] == n_screen and out["open"] is False
    assert out["summary"] == ("Screening lab (development; admits candidates to the "
                              f"registered list, proves nothing), {n_screen} rows")
    assert "efv_v2_screen:" not in out["mainText"] and "txt_skill_hit" not in out["mainText"]
    assert "reserved read" in out["block"] and "IL stints" in out["block"]
    assert ("admitted candidate (development, not a claim)" in out["text"]) is bool(admitted)
    if n_screen:
        assert "No screening row is on the ledger yet" not in out["block"]
        for name, side, verdict, _kw in _SEVEN:
            assert name in out["block"]
        assert "+0.0081" in out["block"] and "+0.0032" in out["block"]
        assert "0.0063" in out["block"] and "0.014" in out["block"] and "fwar@test" in out["block"]
        assert "NULL_HOLM" in out["block"] and "exploratory, no verdict formed" in out["block"]
    else:
        assert "No screening row is on the ledger yet" in out["block"]
    head = [r for r in doc["rows"] if r["frame"] == doc["headline_frame"]][-1]
    assert head["verdict"] in out["text"]
    assert f"{head['raters']['efv']['spearman']:.3f}" in out["text"]


def test_label_pool_fetch_resolves_and_renders(server, browser):
    """EFV3_A8: the label pool census resolves on the served path and the
    Source Comparison view renders the panel from it: the census stamp, the
    frame rows, one measured point per floor reference, and no score."""
    p = ROOT / "data" / "efv_label_pool_census.json"
    if not p.exists():
        pytest.skip("data/efv_label_pool_census.json not built")
    doc = json.loads(p.read_text(encoding="utf-8"))
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "glossary/index.html#view=source-comparison",
                  wait_until="load", timeout=15_000)
        status = page.evaluate(
            "() => fetch('/data/efv_label_pool_census.json', {cache: 'no-cache'})"
            ".then(r => r.status)")
        page.wait_for_function(
            "() => !!document.querySelector('#source-comparison-body .scx-label-pool')",
            timeout=15_000)
        out = page.evaluate("""() => {
          const el = document.querySelector('#source-comparison-body .scx-label-pool');
          el.querySelectorAll('details').forEach(d => { d.open = true; });
          const svg = [...el.querySelectorAll('svg')].find(s =>
            /Smallest resolvable difference/.test(s.getAttribute('aria-label') || ''));
          return {
            measured: svg ? svg.querySelectorAll('circle[r="5"]').length : -1,
            curves: svg ? svg.querySelectorAll('polyline').length : -1,
            text: el.innerText,
          };
        }""")
    finally:
        page.close()
    assert status == 200
    assert not page_errors, "JS errors: " + " | ".join(page_errors)
    refs = doc["floor_curve"]["references"]
    assert out["measured"] == len(refs) and out["curves"] == len(refs)
    txt = out["text"]
    assert f"resolved through {doc['label']['resolved_through']}" in txt
    assert doc["label"]["provider"] in txt
    assert doc["generated_at"][:10] in txt
    assert f"{doc['frame']['dev_totals']['rows']:,}" in txt
    assert f"{doc['frame']['reserved_copied']['rows']:,}" in txt
    for r in doc["label_views"]["rows"]:
        assert r["label_view"].replace("_", "-") in txt
    # Counts and floors only: no rho, no AUC, no Spearman on the panel.
    for word in ("AUC", "Spearman", "ρ", "rho "):
        assert word not in txt, f"the label pool panel prints {word!r}"


def _matrix_page(browser, *, width=1280, body=None, missing=False):
    """Open the Source Comparison view with the matrix artifact served as is, replaced
    by `body`, or answered 404 (`missing`)."""
    page_errors: list[str] = []
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.on("pageerror", lambda err: page_errors.append(err.message))
    if missing:
        page.route("**/data/efv_matrix_eval.json*",
                   lambda route: route.fulfill(status=404, body="not found"))
    elif body is not None:
        page.route("**/data/efv_matrix_eval.json*",
                   lambda route: route.fulfill(status=200, content_type="application/json",
                                               body=body))
    return page, page_errors


_MX_READ = """() => {
  const el = document.getElementById('source-comparison-body');
  const mx = document.getElementById('scx-matrix');
  const vis = n => !!n && n.getClientRects().length > 0;
  return {
    present: !!mx,
    text: mx ? mx.innerText : '',
    ledger: el.innerText.indexOf('Is eFV pulling ahead? The progress ledger') !== -1,
    pool: !!el.querySelector('.scx-label-pool'),
    order: [...el.querySelectorAll('h2')].map(h => h.textContent.trim()),
    win: mx ? [...mx.querySelectorAll('.sacc-verdict-win')].map(n => n.textContent) : [],
    loss: mx ? [...mx.querySelectorAll('.sacc-verdict-loss')].map(n => n.textContent) : [],
    dims: mx ? [...mx.querySelectorAll('.mx-dim')].filter(vis).map(n => n.dataset.mxDim) : [],
    select: mx ? vis(mx.querySelector('.mx-dim-pick')) : false,
    docW: document.documentElement.scrollWidth, winW: window.innerWidth,
  };
}"""


def test_matrix_fetch_resolves_and_renders(server, browser):
    """EFV3_D4: /data/efv_matrix_eval.json resolves on the served path and the
    Source Comparison view renders the matrix under the progress ledger: one
    line per frame from the artifact's summary counts, the grid on the claim
    frame, ESPN as no rows, and at 390 px one category at a time with no
    sideways scroll."""
    p = ROOT / "data" / "efv_matrix_eval.json"
    if not p.exists():
        pytest.skip("data/efv_matrix_eval.json not built")
    doc = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for width in (1280, 390):
        page, errs = _matrix_page(browser, width=width)
        try:
            page.goto(server + "glossary/index.html#view=source-comparison",
                      wait_until="load", timeout=15_000)
            status = page.evaluate(
                "() => fetch('/data/efv_matrix_eval.json', {cache: 'no-cache'}).then(r => r.status)")
            page.wait_for_selector("#scx-matrix .mx-grid", timeout=20_000)
            out[width] = page.evaluate(_MX_READ)
            if width == 1280:
                page.click('#scx-matrix [data-mx-k="comp"][data-mx-v="espn"]')
                out["espn"] = page.evaluate(
                    "() => document.getElementById('scx-matrix').innerText")
        finally:
            page.close()
        assert status == 200
        assert not errs, "JS errors: " + " | ".join(errs)
    wide, narrow = out[1280], out[390]
    vm2 = doc["frames"]["vm2"]
    sm, c = vm2["summary"], vm2["summary"]["counts"]
    txt = wide["text"]
    assert f"(n {vm2['n']:,})" in txt
    assert (f"{c['ahead']} cells ahead, {c['behind']} behind, {c['equivalent']} equivalent, "
            f"{c['unresolved']} not resolvable") in txt
    assert f"{c['unpowered']} unpowered of {sm['k_family_s']}" in txt
    assert (f"at alpha {sm['alpha']} the family would flag "
            f"{sm['expected_false_flags_by_construction']} cells by chance") in txt
    pr = doc["design"]["printed"]
    assert pr["RESERVED_PENDING"] in txt and pr["DEVELOPMENT"] in txt
    assert "the registered equivalence margin" in txt
    assert "docs/PROSPECT_ANCHOR_GATE.md" in txt
    # Ties are ties: both words are printed and they are different words.
    assert pr["EQUIVALENT"] in txt and pr["UNRESOLVED"] in txt
    # The section sits under the ledger and above the label pool.
    order = wide["order"]
    i_led = order.index("Is eFV pulling ahead? The progress ledger")
    i_mx = [i for i, h in enumerate(order) if "scoreboard matrix" in h][0]
    assert i_led < i_mx < order.index("The label pool: rows, identity and floors")
    # Colour only where the artifact gives AHEAD or BEHIND on the claim frame.
    assert not wide["win"] and not wide["loss"] or c["ahead"] or c["behind"]
    assert pr["NOT_SCORED"] in out["espn"]
    # Desktop shows every category; 390 px shows the overall cell and one category.
    assert not wide["select"] and len(wide["dims"]) > 2
    assert narrow["select"] and len(narrow["dims"]) == 2 and narrow["dims"][0] == "overall"
    assert narrow["docW"] <= narrow["winW"], (narrow["docW"], narrow["winW"])


def test_matrix_colours_only_ahead_and_behind(server, browser):
    """A synthetic artifact where one family cell reads AHEAD and one BEHIND: only
    those two carry a colour class, and a FLAGGED_UNCORRECTED cell stays neutral."""
    p = ROOT / "data" / "efv_matrix_eval.json"
    if not p.exists():
        pytest.skip("data/efv_matrix_eval.json not built")
    doc = json.loads(p.read_text(encoding="utf-8"))
    cells = doc["frames"]["vm2"]["cells"]
    fam = [(dim, k) for dim, cs in cells.items() for k, cell in cs.items()
           if cell.get("in_family_s") and (cell.get("comparators") or {})
           .get("prospx_consensus", {}).get("family") == "S"]
    assert len(fam) >= 3
    pr = doc["design"]["printed"]
    for (dim, k), word in zip(fam[:3], ("AHEAD", "BEHIND", "FLAGGED_UNCORRECTED")):
        cmp = cells[dim][k]["comparators"]["prospx_consensus"]
        cmp["reading"] = word
        cmp["statistics"][cmp["primary"]["leg"]]["reading"] = word
    page, errs = _matrix_page(browser, body=json.dumps(doc))
    try:
        page.goto(server + "glossary/index.html#view=source-comparison",
                  wait_until="load", timeout=15_000)
        page.wait_for_selector("#scx-matrix .mx-grid", timeout=20_000)
        # the primary statistic of the first family cell is the tab to read
        leg = cells[fam[0][0]][fam[0][1]]["comparators"]["prospx_consensus"]["primary"]["leg"]
        page.click(f'#scx-matrix [data-mx-k="stat"][data-mx-v="{leg}"]')
        out = page.evaluate(_MX_READ)
    finally:
        page.close()
    assert not errs, "JS errors: " + " | ".join(errs)
    legs = {cells[d][k]["comparators"]["prospx_consensus"]["primary"]["leg"] for d, k in fam[:3]}
    if legs == {leg}:
        assert out["win"] == [pr["AHEAD"]] and out["loss"] == [pr["BEHIND"]], out
    else:
        assert set(out["win"]) <= {pr["AHEAD"]} and set(out["loss"]) <= {pr["BEHIND"]}, out
    assert pr["FLAGGED_UNCORRECTED"] not in " ".join(out["win"] + out["loss"])


def test_matrix_absent_drops_the_section_not_the_view(server, browser):
    """Without the artifact the section is absent and the ledger, the label pool
    and the hero render as before."""
    page, errs = _matrix_page(browser, missing=True)
    try:
        page.goto(server + "glossary/index.html#view=source-comparison",
                  wait_until="load", timeout=15_000)
        page.wait_for_function(
            "() => { const e = document.getElementById('source-comparison-body');"
            " return !!e && e.innerHTML.indexOf('progress ledger') !== -1"
            " && !!e.querySelector('.scx-label-pool'); }", timeout=20_000)
        page.wait_for_timeout(500)
        out = page.evaluate(_MX_READ)
    finally:
        page.close()
    assert not errs, "JS errors: " + " | ".join(errs)
    assert not out["present"] and out["ledger"] and out["pool"]
    assert not any("scoreboard matrix" in h for h in out["order"])


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


def test_library_view_renders(server, browser):
    """The Page Index view (2026-08-04; id index since LIBRARY_3): the legacy
    #view=library alias renders the page index with its four groups and the
    recon-verified routes. Since LIBRARY_8 (2026-10-07) the rows are generated
    by build_site.page_index_groups() into the shell (#page-index-data). The view registry (assets/glossary.js
    VIEWS, mirrored by build_site.GLOSSARY_VIEWS, pinned equal by
    test_library_section_registry) replaced the four registration points.
    Skips cleanly while the built shell predates the index-body mount div (the
    orchestrator rebuild republishes it)."""
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "glossary/index.html#view=library", wait_until="load",
                  timeout=15_000)
        has_shell = page.evaluate("!!document.getElementById('index-body')")
        if not has_shell:
            page.close()
            pytest.skip("built glossary shell predates the Library mount div "
                        "(build_site rebuild pending)")
        page.wait_for_function(
            "() => { const el = document.getElementById('index-body');"
            " return !!el && el.innerHTML.indexOf('meth-table') !== -1; }",
            timeout=10_000)
        html = page.evaluate("document.getElementById('index-body').innerHTML")
        visible = page.evaluate(
            "document.getElementById('index-body').style.display !== 'none'")
    finally:
        if not page.is_closed():
            page.close()

    assert not page_errors, "JS errors on library view:\n  " + "\n  ".join(page_errors)
    assert visible, "#view=library did not unhide the page index body"
    for group in ("Modules", "Reference pages", "Views inside a module", "Player cards"):
        assert group in html, f"library view missing the {group!r} group"
    # Spot-check recon-verified routes from every module family.
    for route in ("/parks/", "/fa/#view=dpw", "/projections/#view=teams",
                  "/prospx/#tab=timemachine", "/pal/#posfit=ladder",
                  "/glossary/#view=source-updates", "/prospx/", "/scores/"):
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
        # LIBRARY_4: at this width the index row is selected and the full read
        # (method, formula, example) sits in the right pane.
        opened = page.evaluate(
            "(() => { const a = document.querySelector('#gl-entry .gl-entry-card');"
            " return !!a && a.dataset.slug === 'wag' && !!a.querySelector('.gl-meth')"
            " && !!a.querySelector('.gp-formula'); })()")
    finally:
        page.close()

    assert not page_errors, "JS errors on deep link:\n  " + "\n  ".join(page_errors)
    assert opened, "#g=wag arrived without its full read; direct anchors must open it"


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
