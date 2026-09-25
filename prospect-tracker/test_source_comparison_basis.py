# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Source Comparison head-to-head reads the verdict's basis (census X01-01).

On 2026-09-24 the head-to-head bars, the share card and the per-year chart on
/glossary/#view=source-comparison read accuracy.pooled and accuracy.per_year,
where eFV is scored on its own rows (n 3,272) and the boards on theirs
(n 4,316). They starred eFV at 0.361 against 0.286 and 0.757 AUC, and the
per-year caption counted "7 of 7" cohorts, while the verdict printed under the
bars, read off accuracy.pooled_efv_common_vintage_matched, put eFV at 0.406
against consensus 0.413 (-0.007, floor 0.030, not resolvable).
HEADTOHEAD_FRAME_GATE says every artifact-driven surface follows the corrected
number, and do-not-reopen item 3 says copy may not claim eFV discriminates
better.

Two layers:
1. STATIC (always runs): the head-to-head renderers read no pooled block but
   the vintage-matched one, stars go through the floor helper, the per-year
   chart draws no eFV line, and the share-card engine honours star:false.
2. RENDERED (skips without playwright or data/source_backtest.json): the bars
   print the verdict block's numbers, a star appears only on the floored
   pair's winner when it resolves and tops every bar, no AUC bar is ever
   starred, and the share card carries no AUC tile.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
JS = ROOT / "assets" / "glossary.js"
GFX = ROOT / "assets" / "eephus-gfx.js"
DATA = ROOT / "data" / "source_backtest.json"
VM = "pooled_efv_common_vintage_matched"


def _fn_code(js: str, name: str) -> str:
    m = re.search(r"function " + re.escape(name) + r"\([^)]*\) \{(.*?)\n\}\n", js, re.S)
    assert m, f"{name} not found in assets/glossary.js (renamed?)"
    return "\n".join(ln for ln in m.group(1).split("\n")
                     if not ln.lstrip().startswith("//"))


def _js() -> str:
    return JS.read_text(encoding="utf-8").replace("\r\n", "\n")


# ---------------------------------------------------------------------------
# Static layer

@pytest.mark.parametrize("name", ["_methAccuracyChart", "_scxGfxSpec"])
def test_head_to_head_renderers_read_only_the_verdict_basis(name):
    code = _fn_code(_js(), name)
    blocks = set(re.findall(r"accuracy\.(pooled\w*|per_year\w*)", code))
    assert blocks <= {VM}, (
        f"{name} reads {sorted(blocks - {VM})}; the head-to-head surfaces "
        f"read {VM}, the block head_to_head_verdict is computed on")
    assert "_hhStarRater(bt)" in code, (
        f"{name} no longer routes its star through the floor helper")


def test_star_helper_requires_a_resolved_floor():
    code = _fn_code(_js(), "_hhStarRater")
    assert "hh.resolvable !== true" in code
    assert f'hh.basis !== "{VM}"' in code


def test_per_year_chart_draws_no_efv_line_and_counts_no_wins():
    code = _fn_code(_js(), "_methPerYearChart")
    assert 'r !== "xfv"' in code, "per-year chart no longer excludes eFV"
    assert 'push("xfv")' not in code, "per-year chart adds eFV back"
    assert not re.search(r"\bwins\b", code), (
        "per-year chart counts cohort wins again; no per-cohort floor exists")


def test_share_card_engine_honours_star_false():
    src = GFX.read_text(encoding="utf-8")
    assert "pn.star === false" in src, (
        "eephus-gfx.js stars every panel's longest bar; the Source Comparison "
        "card needs star:false for panels no floor covers")


def test_methodology_ad_card_stars_no_auc_and_gates_spearman():
    """The Sources & Methodology ad card shares the engine: its AUC panel must
    carry star:false and its Spearman star must come from a resolved
    verdict_vs_consensus, never from the longest bar alone."""
    code = _fn_code(_js(), "_methAdGfxSpec")
    assert re.search(r"contributor AUC.*star: false", code), (
        "the methodology ad card stars the longest AUC bar; no floor covers it")
    assert "vv.resolvable === true" in code
    assert "star: spStar" in code
    assert "best in metric" not in code


# ---------------------------------------------------------------------------
# EV-00 progress ledger (docs/efv-v2/PROGRAM.md s5.3, s5.4)

# A literal that could only be a rho, an AUC or a delta: three or more decimal
# places, or a bare 0.2 to 0.9 value. Layout constants (pixels, a 0.12 pad, a
# 0.01 fallback span) do not match.
_STAT_LITERAL = re.compile(r"(?<![\w.])\d*\.\d{3,}(?![\w.])|(?<![\w.])0?\.[2-9]\d*(?![\w.])")


@pytest.mark.parametrize("name", ["_methProgressLedger", "_methProgressChart",
                                  "_progSeriesRows", "_methProgressTable"])
def test_progress_renderers_carry_no_statistic_literal(name):
    code = _fn_code(_js(), name)
    # Static markup attributes (stroke widths, opacities) are layout; a claim
    # typed into copy or code is not an attribute, so it stays in scope.
    code = re.sub(r'[\w-]+="[^"$]*"', "", code)
    hits = _STAT_LITERAL.findall(code)
    assert not hits, f"{name} carries a numeric literal that reads as a statistic: {hits}"


def test_progress_chart_series_excludes_tilted_frames():
    js = _js()
    series = _fn_code(js, "_progSeriesRows")
    assert 'r.role !== "tilted"' in series and "r.tilted !== true" in series
    assert "_PROG_CHART_FRAMES.includes(f)" in series, (
        "the series filter trusts the artifact's frame list without the local whitelist")
    m = re.search(r"const _PROG_CHART_FRAMES = \[([^\]]*)\]", js)
    assert m, "_PROG_CHART_FRAMES not found"
    frames = set(re.findall(r'"(\w+)"', m.group(1)))
    assert not frames & {"predebut", "all_vintages", "disagreement"}
    chart = _fn_code(js, "_methProgressChart")
    assert "_progSeriesRows(prog)" in chart, "the chart builds its own series"


def test_progress_section_reads_the_ledger_row_not_the_backtest():
    """The ledger line prints the row's own numbers and verdict word; the
    backtest is read only for its generated_at (the stale chip)."""
    code = _fn_code(_js(), "_methProgressLedger")
    assert "row.verdict" in code
    assert not re.search(r"bt\.accuracy", code)
    assert "bt.generated_at" in code


# ---------------------------------------------------------------------------
# Rendered layer

def _artifact():
    if not DATA.exists():
        pytest.skip("data/source_backtest.json absent (gitignored build artifact)")
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    acc = doc.get("accuracy") or {}
    if not (acc.get(VM) or {}).get("xfv") or not acc.get("head_to_head_verdict"):
        pytest.skip("source_backtest.json carries no vintage-matched head-to-head")
    return doc


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


_READ = r"""
() => {
  const el = document.getElementById('source-comparison-body');
  const acc = el.querySelector('.meth-accuracy');
  const metrics = acc ? [...acc.querySelectorAll('.meth-metric')] : [];
  const rows = m => [...m.querySelectorAll('.meth-bar-row')].map(r => ({
    label: r.querySelector('.meth-bar-label').innerText.trim(),
    val: r.querySelector('.meth-bar-val').innerText.trim(),
    best: r.querySelector('.meth-bar-val').classList.contains('is-best'),
  }));
  const py = [...el.querySelectorAll('.meth-chart')].find(c => /preseason cohort/.test(c.innerText));
  return {
    sp: metrics[0] ? rows(metrics[0]) : [],
    au: metrics[1] ? rows(metrics[1]) : [],
    perYearLegend: py ? [...py.querySelectorAll('.meth-legend-key')].map(k => k.innerText.trim()) : null,
    text: el.innerText,
  };
}
"""


def _render(server, browser, doc):
    """Render the view against `doc` (served in place of the artifact) and
    capture the share-card spec handed to EEPHUS_GFX.open."""
    errors: list[str] = []
    page = browser.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    body = json.dumps(doc)
    page.route("**/data/source_backtest.json*", lambda route, req=None: route.fulfill(
        status=200, body=body, content_type="application/json"))
    try:
        page.goto(server + "glossary/index.html#view=source-comparison",
                  wait_until="load", timeout=15_000)
        page.wait_for_function(
            "() => { const e = document.getElementById('source-comparison-body');"
            " return !!e && !!e.querySelector('.meth-accuracy'); }", timeout=15_000)
        out = page.evaluate(_READ)
        page.evaluate("() => { window.__spec = null; const g = window.EEPHUS_GFX;"
                      " if (g) g.open = s => { window.__spec = JSON.parse(JSON.stringify(s)); }; }")
        if page.query_selector("#gl-scx-gfx"):
            page.click("#gl-scx-gfx")
        out["spec"] = page.evaluate("() => window.__spec")
    finally:
        page.close()
    assert not errors, "JS errors on source comparison:\n  " + "\n  ".join(errors)
    return out


def test_bars_print_the_verdict_block_and_star_only_past_a_floor(server, browser):
    doc = _artifact()
    acc = doc["accuracy"]
    vm, hh = acc[VM], acc["head_to_head_verdict"]
    out = _render(server, browser, doc)
    efv = [r for r in out["sp"] if r["label"].startswith("eFV")]
    assert efv and efv[0]["val"].startswith(f"{vm['xfv']['spearman']:.3f}"), (
        f"eFV Spearman bar reads {efv}, the verdict block {vm['xfv']['spearman']}")
    assert not any(r["best"] for r in out["au"]), "an AUC bar is starred; no floor covers it"
    starred = [r["label"] for r in out["sp"] if r["best"]]
    if hh.get("resolvable") is not True:
        assert not starred, f"Spearman star {starred} on an unresolved head-to-head"
    else:
        assert len(starred) <= 1
    assert out["perYearLegend"] is None or not any(k.startswith("eFV") for k in out["perYearLegend"])
    assert not re.search(r"best ordering skill in \d+ of \d+", out["text"])
    spec = out["spec"]
    if spec is not None:
        n = acc.get("common_n_efv_vintage_matched") or vm["xfv"]["n"]
        assert f"n={int(n):,}" in spec["subtitle"], spec["subtitle"]
        assert not any("AUC" in (t.get("label") or "") for t in spec["comp"]["tiles"])
        auc_panels = [p for p in spec["comp"]["panels"] if "AUC" in p["title"]]
        assert all(p.get("star") is False for p in auc_panels)
        sp_panel = [p for p in spec["comp"]["panels"] if "Spearman" in p["title"]][0]
        assert sp_panel.get("star") is (hh.get("resolvable") is True and bool(starred))


def _with_verdict(doc, xfv_sp, resolvable, xfv_beats):
    d = json.loads(json.dumps(doc))
    d["accuracy"][VM]["xfv"]["spearman"] = xfv_sp
    d["accuracy"]["head_to_head_verdict"].update(
        {"resolvable": resolvable, "xfv_beats": xfv_beats})
    return d


def test_star_branches(server, browser):
    """Synthetic verdicts over the real block: a resolved eFV win that tops
    every bar earns exactly one star, on eFV; a resolved win that does not top
    every bar earns none; an unresolved gap earns none."""
    doc = _artifact()
    vm = doc["accuracy"][VM]
    top = max(v["spearman"] for k, v in vm.items() if k != "xfv")
    cases = [
        (top + 0.05, True, True, ["eFV"]),
        (top - 0.001, True, True, []),
        (top + 0.05, False, True, []),
    ]
    for xfv_sp, res, beats, want in cases:
        out = _render(server, browser, _with_verdict(doc, xfv_sp, res, beats))
        starred = [r["label"].split(" ")[0] for r in out["sp"] if r["best"]]
        assert starred == want, (xfv_sp, res, beats, starred)
        assert not any(r["best"] for r in out["au"])
