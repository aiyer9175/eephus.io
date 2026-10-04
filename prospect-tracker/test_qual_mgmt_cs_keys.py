# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Surface-quality audit 2026-10-02, QCLA01 / QREA01 / QREA02.

QCLA01: every Management decision row that opens the drill-down card carries a
button in its first cell, the card takes focus when a row opens it, and close
hands focus back to the row's button.

QREA01: every CollegeSavant sortable column header takes keyboard focus, says
its sort state through aria-sort, and sorts on Enter or Space: the generic
table_sort.js headers (Team Tendencies, MiLB Projections) and the re-rendering
th.lb-th boards in app.js and pitcher_app.js.

QREA02: the trans-flag disclosure chip reads in the site's text gold, and the
grey on a not-predictive accuracy row never reaches the flag.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
MGMT_JS = (ROOT / "assets" / "management.js").read_text(encoding="utf-8")
CS = ROOT / "collegesavant"
SORT_JS = (CS / "table_sort.js").read_text(encoding="utf-8")
APP_JS = (CS / "app.js").read_text(encoding="utf-8")
PIT_JS = (CS / "pitcher_app.js").read_text(encoding="utf-8")
CS_CSS = (CS / "styles.css").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# QCLA01: the decision rows open from the keyboard
# --------------------------------------------------------------------------

def _render(hash_: str) -> str:
    pytest.importorskip("py_mini_racer")
    import test_management_render as tmr
    html, _ = tmr._render2(hash_)
    return html


def test_every_decision_row_carries_a_button_in_its_first_cell():
    html = _render("#section=decisions&team=MIA&season=2026")
    body = html.split("<tbody>")[1].split("</tbody>")[0]
    rows = re.findall(r'<tr data-mrow="([^"]+)"[^>]*>(.*?)</tr>', body)
    assert rows, "the listing rendered no decision rows"
    for rid, tr in rows:
        first = re.match(r"<td>(.*?)</td>", tr)
        assert first, (rid, tr[:80])
        cell = first.group(1)
        assert cell.startswith('<button type="button" class="mgmt-rowbtn" data-mopen="%s" aria-expanded="false"' % rid), cell
        assert 'aria-label="' in cell and "open the plays it governed" in cell
        assert cell.endswith("</button>")


def test_the_open_row_says_expanded_and_the_card_takes_focus():
    html = _render("#section=decisions&team=MIA&season=2026&family=pitching_change&game=1&ab=6")
    card = html.split('id="mgmt-detail"')[1].split(">")[0]
    assert 'tabindex="-1"' in card and 'aria-labelledby="mgmt-detail-title"' in card
    assert 'data-mopen="' in card
    assert '<h3 id="mgmt-detail-title">' in html
    opened = re.findall(r'<button type="button" class="mgmt-rowbtn" data-mopen="([^"]+)" aria-expanded="true" aria-controls="mgmt-detail"', html)
    assert len(opened) == 1, opened
    assert 'data-mopen="%s"' % opened[0] in card


def test_the_row_handler_focuses_the_card_and_close_returns_focus():
    wire = MGMT_JS.split("function wire()")[1].split("function boot()")[0]
    row = wire.split('querySelectorAll("tr[data-mrow]")')[1].split('var close = el("mgmt-close")')[0]
    assert re.search(r'render\(\);[\s\S]*el\("mgmt-detail"\)[\s\S]*\.focus\(', row), "the card takes focus after the render"
    close = wire.split('var close = el("mgmt-close")')[1].split("In-page deep links")[0]
    assert 'getAttribute("data-mopen")' in close
    assert re.search(r"render\(\);[\s\S]*button\[data-mopen=[\s\S]*\.focus\(\)", close), "close hands focus back to the row button"


# --------------------------------------------------------------------------
# QREA01: CollegeSavant sort headers answer the keyboard
# --------------------------------------------------------------------------

def test_the_generic_sort_arms_every_header_it_sorts():
    assert "th.tabIndex = 0" in SORT_JS
    assert 'setAttribute("aria-sort", d === "asc" ? "ascending" : d === "desc" ? "descending" : "none")' in SORT_JS
    assert 'th.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending")' in SORT_JS
    kd = SORT_JS.split('document.addEventListener("keydown"')[1]
    assert 'e.key !== "Enter" && e.key !== " "' in kd and "e.preventDefault()" in kd and "sortTable(th)" in kd
    assert "new MutationObserver(arm)" in SORT_JS, "headers painted after load are armed too"


@pytest.mark.parametrize("name,src", [("app.js", APP_JS), ("pitcher_app.js", PIT_JS)], ids=["app", "pitcher_app"])
def test_every_board_header_is_focusable_and_states_its_sort(name, src):
    heads = re.findall(r'<th class="tt-col lb-th[^`]*?</th>`', src)
    assert len(heads) == 2, (name, len(heads))
    for h in heads:
        assert 'tabindex="0" aria-sort="${lbAriaSort(on, dir)}"' in h, (name, h)
    assert src.count('.lb-th").forEach((th) => lbSortKeys(th, ') == 2, name
    assert '.lb-th").forEach((th) => th.addEventListener("click"' not in src, name
    keys = src.split("function lbSortKeys(")[1].split("\n}\n")[0]
    assert 'e.key !== "Enter" && e.key !== " "' in keys and "e.preventDefault()" in keys
    assert "again.focus()" in keys, "focus returns to the same column after the re-render"
    assert 'return on ? (dir < 0 ? "descending" : "ascending") : "none";' in src


# --------------------------------------------------------------------------
# QREA02: the disclosure flags keep reading contrast
# --------------------------------------------------------------------------

def test_the_trans_flag_reads_in_text_gold():
    block = CS_CSS.split(".trans-flag {")[1].split("}")[0]
    assert re.search(r"(?<!-)color: var\(--text-gold, #7D5F08\)", block), block
    assert "border: 1px solid var(--gold)" in block
    assert not re.search(r"(?<![-\w])color: var\(--gold\)", block), block


@pytest.mark.parametrize("name,src", [("app.js", APP_JS), ("pitcher_app.js", PIT_JS)], ids=["app", "pitcher_app"])
def test_no_row_opacity_reaches_a_flag(name, src):
    assert not re.search(r"<tr\$\{", src), "a row-level style would dim the flag inside it"
    assert not re.search(r"<tr[^>]*opacity", src), name


def test_the_not_predictive_row_dims_its_label_and_numbers_not_the_flag():
    proj = APP_JS.split("function renderProjections()")[1].split("function renderTranslation(")[0]
    assert "const lab = notPredictive ? `<span${dim}>${label}</span>` : label;" in proj
    assert '<tr><td class="tt-team">${lab}${flag}</td>' in proj
    assert proj.count('<td class="tt-col"${dim}>') == 5
