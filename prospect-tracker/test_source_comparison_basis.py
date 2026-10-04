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

FP3-1 / FP3-3 (owner answers 2026-09-25): the headline moved to the
timing-pinned frame vm2, and the view reads it from ONE key: every
head-to-head renderer reads accuracy.head_to_head_verdict and follows its
`basis` (_hhBlock), naming no accuracy block of its own. The per-source cells
print a verdict word only where the artifact's Holm family gives one.

Two layers:
1. STATIC (always runs): the head-to-head renderers read no pooled block and
   reach the verdict's block only through _hhBlock, stars go through the floor
   helper, the per-year chart draws no eFV line, and the share-card engine
   honours star:false.
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
VM2 = "pooled_efv_common_vintage_matched_vm2"


# Any decimal literal that could be a statistic (the per-source table prints
# only artifact numbers).
_STAT_LITERAL_ANY = re.compile(r"(?<![\w.])\d*\.\d+(?![\w.])")


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
    blocks = set(re.findall(r"accuracy\.(pooled\w*|per_year\w*|common_n_efv\w*)", code))
    assert not blocks, (
        f"{name} reads {sorted(blocks)}; the head-to-head surfaces reach the "
        "block head_to_head_verdict is computed on only through _hhBlock")
    assert "_hhBlock(bt)" in code
    assert "_hhStarRater(bt)" in code, (
        f"{name} no longer routes its star through the floor helper")


def test_star_helper_requires_a_resolved_floor():
    code = _fn_code(_js(), "_hhStarRater")
    assert "hh.resolvable !== true" in code
    assert "_hhBlock(bt)" in code and "_hhVerdict(bt)" in code


def test_the_headline_block_is_one_key():
    """FP3-1: _hhBlock follows head_to_head_verdict.basis, and no function in
    the view names a vintage-matched block directly."""
    js = _js()
    blk = _fn_code(js, "_hhBlock")
    assert "acc[hh.basis]" in blk
    assert "head_to_head_verdict" in _fn_code(js, "_hhVerdict")
    code = "\n".join(ln for ln in js.split("\n") if not ln.lstrip().startswith("//"))
    for name in (VM, VM2, "common_n_efv_vintage_matched"):
        assert not re.search(r"\." + re.escape(name) + r"\b", code), (
            f"assets/glossary.js reads accuracy.{name} directly; read "
            "head_to_head_verdict and follow its basis")
    for name in ("_methHeroBanner", "_methCaveatHeadToHead", "_hhFloorClause"):
        assert "_hhVerdict(bt)" in _fn_code(js, name), name


def test_per_source_cells_print_only_the_artifacts_words():
    """FP3-3: the per-source table reads the verdict word and the Holm floor
    from the artifact and states the family and alpha from it too."""
    code = _fn_code(_js(), "_methPerSourceCells")
    assert "leg.verdict" in code and "interval only" in code
    assert "h.k" in code and "h.alpha" in code and "h.family" in code
    assert "vs.basis !== hh.basis" in code
    assert not _STAT_LITERAL_ANY.findall(re.sub(r'[\w-]+="[^"$]*"', "", code))


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


# EFV3_B8: the screening lab's collapsed block prints the rows' own numbers and types
# none: no decimal literal at all (a rho, a delta or a floor would be one), and no
# number assigned to a floor, a delta or a bound.
_SCREEN_FNS = ["_progScreenBlock", "_progScreenRowHtml", "_progIsScreen",
               "_progScreenAdmitted"]


@pytest.mark.parametrize("name", _SCREEN_FNS)
def test_screening_block_carries_no_statistic_literal(name):
    code = _fn_code(_js(), name)
    code = re.sub(r'[\w-]+="[^"$]*"', "", code)
    assert not _STAT_LITERAL_ANY.findall(code), (
        f"{name} carries a decimal literal: {_STAT_LITERAL_ANY.findall(code)}")
    assert not re.search(r"(floor|delta|lb95|rho|holm_p)\s*[:=]\s*[-+]?\d", code), name
    assert not re.search(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", code), f"{name} types a date"


def test_screening_rows_sit_in_their_own_block_and_chart_only_when_admitted():
    js = _js()
    block = _fn_code(js, "_progScreenBlock")
    assert "_progRows(prog).filter(r => _progIsScreen(r))" in block
    assert "Screening lab (development; admits candidates to the registered list, proves nothing)" in block
    assert "<details" in block and " open" not in block, "the block must start collapsed"
    assert "_progScreenBlock(prog)" in _fn_code(js, "_methProgressSection")
    assert "!_progIsScreen(r)" in _fn_code(js, "_methProgressTable"), (
        "screening rows leak into the dated table")
    assert "_progScreenAdmitted(r)" in _fn_code(js, "_progSeriesRows")
    chart = _fn_code(js, "_methProgressChart")
    assert "admitted candidate (development, not a claim)" in chart
    # the headline line never reads a screening row
    assert "_progIsScreen" not in _fn_code(js, "_methProgressLedger")



# ---------------------------------------------------------------------------
# PV-08 Provisional track record (PROVISIONAL_V2.md section 4): SERVED and BACKCAST
# as two tables, every number read from its artifact at render time.

@pytest.mark.parametrize("name", ["_ptServedTable", "_ptBackcastTable", "_ptVerdict",
                                  "_methProvTrackSection"])
def test_provisional_track_renderers_carry_no_statistic_literal(name):
    code = _fn_code(_js(), name)
    code = re.sub(r'[\w-]+="[^"$]*"', "", code)
    hits = _STAT_LITERAL.findall(code)
    assert not hits, f"{name} carries a numeric literal that reads as a statistic: {hits}"
    assert not re.search(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", code), f"{name} types a date"


def test_provisional_track_reads_its_two_artifacts_and_never_pools_them():
    js = _js()
    load = _fn_code(js, "_loadProvTrack")
    assert 'fetch("/data/provisional_track_eval.json"' in load
    assert 'fetch("/data/provisional_v2_eval.json"' in load
    served, back = _fn_code(js, "_ptServedTable"), _fn_code(js, "_ptBackcastTable")
    assert "SERVED" in served and "backcast" not in served.lower()
    assert "b.backcast" in back and ".rows" not in back.replace("t1.", "").replace("t2.", "")
    sec = _fn_code(js, "_methProvTrackSection")
    assert "_ptServedTable(t)" in sec and "_ptBackcastTable(s.backcast)" in sec
    # an open window prints the row's own status, never a verdict
    assert "r.status" in _fn_code(js, "_ptVerdict")
    rsc = _fn_code(js, "renderSourceComparison")
    assert "_methProvTrackSection()" in rsc


# ---------------------------------------------------------------------------
# EFV3_A8 label pool panel (EFV3_PLAN.md sections 3 and 6): counts and floors
# read from the label pool census, never a rho, an AUC or a delta.

_LP_FUNCS = ["_loadLabelPool", "_lpFrameAgg", "_lpFramesTable", "_lpCohortTable",
             "_lpJoinTable", "_lpFloorChart", "_lpViewsTable", "_methLabelPoolSection"]
_LP_WHITELIST = {"source", "list_year", "vintage", "side", "debut_cohort", "id_how",
                 "bust_class", "label_view"}


@pytest.mark.parametrize("name", _LP_FUNCS)
def test_label_pool_panel_carries_no_statistic_literal(name):
    code = re.sub(r'[\w-]+="[^"$]*"', "", _fn_code(_js(), name))
    hits = _STAT_LITERAL.findall(code)
    assert not hits, f"{name} carries a numeric literal that reads as a statistic: {hits}"
    assert not re.search(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", code), f"{name} types a date"


def test_label_pool_panel_reads_only_the_census_and_no_score():
    js = _js()
    load = _fn_code(js, "_loadLabelPool")
    assert 'fetch("/data/efv_label_pool_census.json"' in load
    code = "\n".join(_fn_code(js, n) for n in _LP_FUNCS)
    assert code.count("fetch(") == 1, "the label pool panel fetches a second artifact"
    # No score key is read: the census carries label-to-label faithfulness numbers
    # (copied rho values), and the panel prints none of them.
    for key in ("faithfulness", "spearman", ".auc", ".delta", "ci95", "rho"):
        assert key not in code.lower(), f"the label pool panel reads {key}"
    # Nothing grouped by a consensus FV level (docs/PROSPECT_ANCHOR_GATE.md).
    # (the artifact's own name, efv_label_pool_census, is not an FV cell)
    assert not re.search(r"\bfv\b|_fv|(?<!e)fv_|tier", code, re.I), "the panel names an FV cell"
    rsc = _fn_code(js, "renderSourceComparison")
    assert "_methLabelPoolSection()" in rsc


def test_label_pool_min_lag_matches_the_backtest():
    js = _js()
    m = re.search(r"const _LP_VM_MIN_LAG = (\d+);", js)
    assert m, "_LP_VM_MIN_LAG not found"
    src = (ROOT / "source_backtest.py").read_text(encoding="utf-8")
    py = re.search(r"^MIN_LAG_YEARS = (\d+)", src, re.M)
    assert py and int(py.group(1)) == int(m.group(1))


def test_label_pool_census_strata_stay_on_the_whitelist():
    p = ROOT / "data" / "efv_label_pool_census.json"
    if not p.exists():
        pytest.skip("data/efv_label_pool_census.json absent")
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert set(doc.get("strata") or []) <= _LP_WHITELIST

# ---------------------------------------------------------------------------
# EFV3_D4 scoreboard matrix (EFV3_PLAN.md section 6, LANE_D.md 3.4 and 3.8): every
# number and reading word is read from the matrix artifact at render time.

_MX_FUNCS = ["_loadMatrix", "_mxN", "_mxUi", "_mxGridFrames", "_mxFrameLabel", "_mxChipLabel",
             "_mxDimLabel", "_mxCellLabel", "_mxStatTabs", "_mxL6Keys", "_mxStatKey",
             "_mxStatTabLabel", "_mxReadingClass", "_mxFrameLine", "_mxReadingHtml",
             "_mxWhisker", "_mxAxis", "_mxGrid", "_mxLegend", "_mxInner", "_mxBind",
             "_methMatrixSection"]


@pytest.mark.parametrize("name", _MX_FUNCS)
def test_matrix_section_carries_no_statistic_literal(name):
    code = re.sub(r'[\w-]+="[^"$]*"', "", _fn_code(_js(), name))
    hits = _STAT_LITERAL.findall(code)
    assert not hits, f"{name} carries a numeric literal that reads as a statistic: {hits}"
    assert not re.search(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", code), f"{name} types a date"
    # no count, floor, margin or k typed in: each is the artifact's
    assert not re.search(r"(floor|margin|delta|alpha|mde95|k_family_s)\s*[:=]\s*[-+]?\d", code), name


def test_matrix_colour_attaches_only_to_ahead_and_behind():
    js = _js()
    code = {n: _fn_code(js, n) for n in _MX_FUNCS}
    for n, c in code.items():
        if n == "_mxReadingClass":
            continue
        assert "sacc-verdict-win" not in c and "sacc-verdict-loss" not in c, (
            f"{n} attaches a colour class outside _mxReadingClass")
    rc = [ln.strip() for ln in code["_mxReadingClass"].split("\n") if ln.strip()]
    win = [ln for ln in rc if "sacc-verdict-win" in ln]
    loss = [ln for ln in rc if "sacc-verdict-loss" in ln]
    assert len(win) == 1 and 'reading === "AHEAD"' in win[0] and "!dev" in win[0], win
    assert len(loss) == 1 and 'reading === "BEHIND"' in loss[0] and "!dev" in loss[0], loss
    for word in ("EQUIVALENT", "UNRESOLVED", "FLAGGED_UNCORRECTED", "UNPOWERED", "DEVELOPMENT"):
        assert word not in code["_mxReadingClass"], f"_mxReadingClass names {word}"
    assert rc[-1] == 'return "sacc-verdict-null";', rc[-1]


def test_hero_renderers_read_no_matrix_key():
    """Copy contract: no stratum word reaches the hero banner, the share card or the
    eFV verdict sentence."""
    js = _js()
    for name in ("_methHeroBanner", "_scxGfxSpec", "_methEfvVerdict"):
        code = _fn_code(js, name)
        for key in ("_S.matrix", "efv_matrix", "_mx", "matrix", "k_family_s", "in_family_s",
                    "FLAGGED_UNCORRECTED", "stratum", "would_read_on_a_claim_frame"):
            assert key not in code, f"{name} reads the matrix ({key})"
    # The Diamond tiles and every other surface read no matrix key either.
    for p in (ROOT / "assets").glob("*.js"):
        if p.name == "glossary.js":
            continue
        assert "efv_matrix" not in p.read_text(encoding="utf-8", errors="ignore"), p.name


def test_matrix_section_reads_one_artifact_and_sits_under_the_ledger():
    js = _js()
    load = _fn_code(js, "_loadMatrix")
    assert 'fetch("/data/efv_matrix_eval.json"' in load
    code = "\n".join(_fn_code(js, n) for n in _MX_FUNCS)
    assert code.count("fetch(") == 1, "the matrix section fetches a second artifact"
    # No FV-keyed cell (docs/PROSPECT_ANCHOR_GATE.md): the section names no FV key.
    assert not re.search(r"consensus_fv|(?<!e)fv_|\.tier\b|\.rank\b", code), "the matrix names an FV key"
    rsc = _fn_code(js, "renderSourceComparison")
    assert "_loadMatrix()" in rsc and "_mxBind()" in rsc
    i_led = rsc.index("${_methProgressSection(bt)}")
    i_mx = rsc.index("${_methMatrixSection(_S.progress, _S.matrix)}")
    assert i_led < i_mx < rsc.index("${_methLabelPoolSection()}")
    # the frame line prints the artifact's own counts and expected false flags
    line = _fn_code(js, "_mxFrameLine")
    for key in ("sm.k_family_s", "sm.expected_false_flags_by_construction", "sm.alpha",
                "sm.would_read_on_a_claim_frame", "sm.counts"):
        assert key in line, key


# ---------------------------------------------------------------------------
# Rendered layer

def _artifact():
    if not DATA.exists():
        pytest.skip("data/source_backtest.json absent (gitignored build artifact)")
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    acc = doc.get("accuracy") or {}
    hh = acc.get("head_to_head_verdict") or {}
    if not hh or not (acc.get(hh.get("basis")) or {}).get("xfv"):
        pytest.skip("source_backtest.json carries no head-to-head verdict block")
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
    hh = acc["head_to_head_verdict"]
    vm = acc[hh["basis"]]
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
        n = hh.get("n") or vm["xfv"]["n"]
        assert f"n={int(n):,}" in spec["subtitle"], spec["subtitle"]
        assert not any("AUC" in (t.get("label") or "") for t in spec["comp"]["tiles"])
        auc_panels = [p for p in spec["comp"]["panels"] if "AUC" in p["title"]]
        assert all(p.get("star") is False for p in auc_panels)
        sp_panel = [p for p in spec["comp"]["panels"] if "Spearman" in p["title"]][0]
        assert sp_panel.get("star") is (hh.get("resolvable") is True and bool(starred))


def _with_verdict(doc, xfv_sp, resolvable, xfv_beats):
    d = json.loads(json.dumps(doc))
    d["accuracy"][d["accuracy"]["head_to_head_verdict"]["basis"]]["xfv"]["spearman"] = xfv_sp
    d["accuracy"]["head_to_head_verdict"].update(
        {"resolvable": resolvable, "xfv_beats": xfv_beats})
    return d


def test_star_branches(server, browser):
    """Synthetic verdicts over the real block: a resolved eFV win that tops
    every bar earns exactly one star, on eFV; a resolved win that does not top
    every bar earns none; an unresolved gap earns none."""
    doc = _artifact()
    vm = doc["accuracy"][doc["accuracy"]["head_to_head_verdict"]["basis"]]
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


def test_per_source_table_renders_the_holm_words(server, browser):
    """Rendered: a verdict word appears exactly on the cells the artifact gives
    one, the others read "interval only", and the family size and alpha on the
    page are the artifact's."""
    doc = _artifact()
    vs = doc["accuracy"].get("head_to_head_vs_sources") or {}
    if not vs.get("holm"):
        pytest.skip("source_backtest.json predates the FP3-3 Holm family")
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
            "() => !!document.querySelector('#source-comparison-body .scx-per-source')",
            timeout=15_000)
        out = page.evaluate("""() => {
          const t = document.querySelector('#source-comparison-body .scx-per-source');
          return {rows: [...t.querySelectorAll('tbody tr')].map(tr =>
                   [...tr.querySelectorAll('td')].map(td => td.innerText.trim())),
                  text: t.innerText,
                  hero: (document.querySelector('.source-comp-hero-lede') || {}).innerText || ""};
        }""")
    finally:
        page.close()
    assert not errors, errors
    words = {c["label"]: [(c.get(m) or {}).get("verdict") for m in ("spearman", "auc")]
             for c in vs["sources"].values()}
    assert len(out["rows"]) == len(words)
    for tds in out["rows"]:
        want = words[tds[0]]
        got = [tds[3], tds[6]]
        for w, g in zip(want, got):
            assert (g == w) if w else (g == "interval only"), (tds[0], want, got)
    h = vs["holm"]
    assert f"One family of {h['k']} tests" in out["text"]
    assert f"alpha of {h['alpha']}" in out["text"]
    hh = doc["accuracy"]["head_to_head_verdict"]
    if hh.get("mde95_status") == "carried":
        assert "carried from the vm1 frame" in out["hero"]
