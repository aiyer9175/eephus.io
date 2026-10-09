# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Trade Machine board's default order is the surplus it prints (M08-03).

MEASURED 2026-09-25, before the fix: the board loaded sorted on the raw eFV
grade for every row. For an MLB player that is the grade frozen at his last
pre-debut snapshot, and the FV column is blank on MLB rows, so the order had no
visible key. Carlos Correa (minus $60.7M, F) ranked 6th, Kris Bryant 13th,
Xander Bogaerts 14th, and the largest surplus on the board ranked 185th. The
registry row for the board says the headline sort is the surplus.

After: All and MLB load on Surplus, highest first; MiLB loads on the eFV grade;
the "eFV grade (prospects)" option ranks prospects only, so no MLB row sits
above a prospect under it.

Served path, headless Chromium over conftest.serve_site, read-only.
"""
from __future__ import annotations

import contextlib
import re
from pathlib import Path

import pytest

from conftest import serve_site

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def server():
    if not (HERE / "data" / "trade_values.json").exists():
        pytest.skip("trade_values.json not built on this machine")
    with serve_site() as base:
        yield base


@contextlib.contextmanager
def _board(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            pg = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(server + "trademachine/", wait_until="networkidle", timeout=90_000)
            pg.wait_for_selector(".tm-board-table tbody tr", timeout=90_000)
            yield pg, errors
        finally:
            browser.close()


def _money(txt: str):
    """Parse a Surplus cell ("$224M", "-$60.7M", "$810k", "$1.2B")."""
    t = txt.strip().replace(",", "")
    m = re.match(r"^(-?)\$(-?[0-9.]+)([kMB]?)", t)
    if not m:
        return None
    v = float(m.group(2)) * {"k": 0.001, "M": 1.0, "B": 1000.0, "": 1.0}[m.group(3)]
    return -v if m.group(1) else v


def _rows(pg):
    return pg.eval_on_selector_all(
        ".tm-board-table tbody tr",
        "rs => rs.map(r => Array.from(r.cells).map(c => c.innerText.trim()))")


def _col(pg, label):
    heads = pg.eval_on_selector_all(".tm-board-table thead th",
                                    "hs => hs.map(h => h.innerText.trim())")
    for i, h in enumerate(heads):
        if h.upper().split()[0:1] == [label.upper()]:
            return i
    raise AssertionError(f"no {label} column in {heads}")


def _pool(pg, pool):
    pg.eval_on_selector(f"[data-tb-pool={pool}]", "b => b.click()")
    pg.wait_for_timeout(300)


def _sort_value(pg):
    return pg.eval_on_selector("#tb-sort-select", "s => s.value")


def _assert_surplus_order(pg, where):
    ci = _col(pg, "Surplus")
    vals = [_money(r[ci]) for r in _rows(pg)]
    vals = [v for v in vals if v is not None]
    assert len(vals) >= 50, f"{where}: only {len(vals)} priced rows rendered"
    bad = [(i + 1, a, b) for i, (a, b) in enumerate(zip(vals, vals[1:])) if b > a + 0.051]
    assert not bad, f"{where}: surplus rises down the page at {bad[:5]}"


def test_all_and_mlb_pools_load_on_surplus(server):
    with _board(server) as (pg, errors):
        assert _sort_value(pg) == "surplus_desc", "the default board does not name Surplus"
        _assert_surplus_order(pg, "All pool")
        _pool(pg, "mlb")
        assert _sort_value(pg) == "surplus_desc"
        _assert_surplus_order(pg, "MLB pool")
        assert not errors, errors


def test_milb_pool_loads_on_the_efv_grade(server):
    with _board(server) as (pg, errors):
        _pool(pg, "milb")
        assert _sort_value(pg) == "trade_desc", "the MiLB pool does not default to eFV grade"
        ci = _col(pg, "eFV")      # the column is eFV (owner answer Q-E4)
        fvs = [float(r[ci]) for r in _rows(pg) if re.match(r"^[0-9.]+$", r[ci] or "")]
        assert len(fvs) >= 50
        bad = [(i + 1, a, b) for i, (a, b) in enumerate(zip(fvs, fvs[1:])) if b > a]
        assert not bad, f"the eFV grade rises down the MiLB page at {bad[:5]}"
        assert not errors, errors


def test_efv_grade_sort_ranks_prospects_only(server):
    with _board(server) as (pg, errors):
        pg.eval_on_selector("#tb-sort-select", "s => { s.value = 'trade_desc'; "
                            "s.dispatchEvent(new Event('change')); }")
        pg.wait_for_timeout(300)
        status = [r[-1] for r in _rows(pg)]
        mlb = [i + 1 for i, s in enumerate(status) if s.startswith("MLB")]
        assert not mlb, f"an MLB row ranks on the eFV grade sort at rows {mlb[:5]}"
        # A pick survives a pool change.
        _pool(pg, "all")
        assert _sort_value(pg) == "trade_desc"
        assert not errors, errors


def test_grade_header_carries_no_accuracy_claim():
    src = (HERE / "assets" / "trademachine.js").read_text(encoding="utf-8")
    m = re.search(r'_tbTh\("Grade",[^\n]*', src)
    assert m, "Grade header not found"
    assert "better" not in m.group(0) and "realized" not in m.group(0), m.group(0)
