# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Surface-quality audit 2026-10-02, the Library (/glossary/) and /models/.

One test per finding where a test can pin it:
  QREA06  the two Methodology explorer sliders carry a label
  QREA16  FOUNDATION and deprecated chips, and the sample chips in the term and
          guide visuals, read in a text token at full opacity
  QREA18  the view chips and the Source Accuracy chips say which one is pressed
  QREP05  /models/ links its stylesheet ahead of its markup; the deferred client
          injects none (the tiles moved after first paint, CLS 0.50)
  QREC02  the side calibration panel drops the stale v1 lede and the
          unreceipted "more accurate" verdict
  QREC06  the ledger legend and the rescored rows' trigger and note read in site
          copy at display time, and the pending-headline notes say the frame is
          the headline now; data/efv_progress.json stays as written
  QREC16  the Methodology changelog dates the four changes, each with a receipt
QREA05 (Escape closes a term tooltip) is pinned by test_management_display_a11y.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).parent
GLJS = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
CSS = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")


# ---- QREA06 -------------------------------------------------------------
def test_explorer_sliders_are_labelled():
    for rid in ("gx-grade-in", "gx-surplus-fv"):
        assert re.search(rf'<label class="gx-label" for="{rid}">', GLJS), rid
        assert f'<input id="{rid}"' in GLJS


# ---- QREA16 -------------------------------------------------------------
def _rule(sel: str) -> str:
    m = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", CSS)
    assert m, sel
    return m.group(1)


def test_foundation_and_deprecated_chips_read_at_full_ink():
    for sel in (".gl-app .gl-shelf--foundation", ".gl-app .gl-verdict--deprecated"):
        body = _rule(sel)
        assert "opacity" not in body, sel
        assert "color: var(--text-secondary)" in body, sel


def test_sample_chip_text_uses_text_tokens():
    gl = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    vis = " ".join(str(e.get("visual") or "") for e in gl.get("entries", []))
    # a neon accent may draw a border or a fill, never the text itself
    for tok in ("neon-amber", "neon-violet", "neon-cyan"):
        assert f";color:var(--{tok})" not in vis and f'"color:var(--{tok})' not in vis, tok
    for label in ("$DvM+ 110", "DvM+ 112", "⇄"):
        m = re.search(r'color:var\(--([a-z-]+)\);">' + re.escape(label) + "<", GLJS)
        assert m and m.group(1).startswith("text-"), label


# ---- QREA18 -------------------------------------------------------------
def test_view_and_section_chips_carry_pressed_state():
    # LIBRARY_3 replaced the view chips' aria-pressed with aria-current="page"
    # on the active leaf (one state attribute per chip, never both).
    import build_site as B
    shell = B.build_glossary()
    chips = re.findall(r'<button class="chip[^"]*"([^>]*)data-glossary-view="([a-z-]+)"', shell)
    assert chips and not any("aria-pressed=" in attrs for attrs, _v in chips)
    assert [v for attrs, v in chips if 'aria-current="page"' in attrs] == ["terms"]
    assert 'if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");' in GLJS
    assert 'aria-pressed="${_SACC_TAB === k ? "true" : "false"}" data-sacc-tab=' in GLJS


# ---- QREP05 -------------------------------------------------------------
def test_models_styles_load_before_markup():
    js = (ROOT / "assets" / "accountability.js").read_text(encoding="utf-8")
    assert "createElement(\"style\")" not in js and "textContent = [" not in js
    css = (ROOT / "assets" / "accountability.css").read_text(encoding="utf-8")
    assert re.search(r"\.acct-app \.acct-tiles\{display:grid;", css)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), "tokens only"
    import build_site as B
    page = B.build_models()
    link = page.find('href="/assets/accountability.css?v=')
    app = page.find('class="fa-app mlbstats-app acct-app"')
    assert 0 < link < app
    served = (ROOT / "models" / "index.html").read_text(encoding="utf-8")
    assert f'accountability.css?v={B._asset_ver("assets/accountability.css")}' in served


# ---- QREC02 -------------------------------------------------------------
def test_side_calibration_drops_stale_lede_and_verdict():
    body = GLJS[GLJS.index("function _methSideCalibration"):GLJS.index("function _methScoreboardHTML")]
    for gone in ("far fewer pitchers", "more accurate reading", "not a blind spot",
                 "spending a real difference"):
        assert gone not in body, gone
    assert "so this side gap now sits in the consensus V2 reads" in body


# ---- QREC06 -------------------------------------------------------------
def test_ledger_copy_reads_in_site_words():
    assert "scoring harness" not in GLJS
    assert "to the scoring code or to the rows" in GLJS
    assert 't === "harness_correction" ? "scoring correction"' in GLJS
    assert "escapeHtml(r.note" not in GLJS and "escapeHtml(cand.note" not in GLJS


# ---- QREC16 -------------------------------------------------------------
def test_changelog_dates_the_four_changes_with_receipts():
    # LIBRARY_5 moved the Methodology changelog into the Model Updates note
    # rows (data/model_updates_typed.json -> data/model_updates.json); the four
    # QREC16 lines keep their dates, models and receipts there.
    notes = json.loads((ROOT / "data" / "model_updates.json").read_text(encoding="utf-8"))["events"]
    by_date = {}
    for e in notes:
        if e.get("layer") == "note":
            by_date.setdefault(e["date"], []).append(e)
    want = {
        "2026-09-30": ("eta", ("eta_eval.json", "registry row eta")),
        "2026-09-04": ("xfv_ewar_label_epoch", ("registry row xfv_ewar_label_epoch", "EWAR_LABEL_EPOCH_GATE.md")),
    }
    for d, (mid, needles) in want.items():
        rows = [e for e in by_date.get(d, []) if e.get("model_id") == mid]
        assert rows, d
        assert all(n in rows[0]["change"] for n in needles), d
    sep25 = " ".join(e["change"] for e in by_date.get("2026-09-25", []))
    for n in ("registry row efv_v2", "DS-02", "FP3-1", "FP3-3", "registry row xfv_headtohead_frame"):
        assert n in sep25, n


# ---- rendered: QREC06 and QREA18 on the served page ------------------------
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


def test_rendered_ledger_notes_and_pressed_chips(browser):
    led = ROOT / "data" / "efv_progress.json"
    if not led.exists():
        pytest.skip("data/efv_progress.json not built")
    raw = json.loads(led.read_text(encoding="utf-8"))
    pend = re.compile(r"becomes the headline once [^;.]+")
    n_pend = sum(1 for r in raw["rows"] if pend.search(str(r.get("note") or ""))
                 and r.get("role") not in ("tilted", "secondary") and r.get("tilted") is not True
                 and not str(r.get("model_id") or "").startswith("efv_v2_screen"))
    errs: list[str] = []
    with serve_site() as base:
        page = browser.new_page()
        page.on("pageerror", lambda e: errs.append(e.message))
        try:
            page.goto(base + "glossary/index.html#view=source-comparison", wait_until="load", timeout=15_000)
            page.wait_for_function(
                "() => { const e = document.getElementById('source-comparison-body');"
                " return !!e && e.innerText.indexOf('Every ledger row') !== -1; }", timeout=15_000)
            out = page.evaluate("""() => ({
              text: document.getElementById('source-comparison-body').innerText,
              pressed: [...document.querySelectorAll('[data-glossary-view]')]
                .filter(b => b.getAttribute('aria-current') === 'page').map(b => b.dataset.glossaryView)})""")
        finally:
            page.close()
    assert not errs, errs
    assert out["pressed"] == ["source-comparison"]
    assert not re.search(r"\bharness\b", out["text"], re.I)
    if n_pend:
        assert out["text"].count("(as written; headline since 2026-09-25)") >= n_pend
