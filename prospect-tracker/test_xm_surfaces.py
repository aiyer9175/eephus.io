# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""xM$ and Fair $ surfaces, built dark (task XM_3_SURFACES_DARK; owner decisions
XM-1 to XM-4 of 2026-10-19).

What is pinned:
  * XM_DISPLAY_ON is False, and with it False every page that could carry the
    script is byte for byte unchanged: the injector returns the page it is
    given, no builder names assets/xm-surfaces.js, the hand page does not.
  * With the flag True the tag is added once, before </body>, stamped with the
    asset's content hash, and taking the flag back off restores the page bytes.
  * A free agent's xM$ agrees with the /fa/ predicted contract (same model).
  * The script keeps its own lock (display_on in the data), draws no gap
    column and touches no module's own script.
  * The glossary carries the two entries, short and free of em-dashes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import build_site as B
import xm_export as X

ROOT = Path(__file__).parent
DATA = ROOT / "data"
JS = (ROOT / "assets" / "xm-surfaces.js").read_text(encoding="utf-8")

BUILDERS = {
    "projections/index.html": "build_projections",
    "mlbstats/index.html": "build_mlbstats",
    "fa/index.html": "build_fa",
    "arbitration/index.html": "build_arbitration",
    "trademachine/index.html": "build_trademachine",
    "ledger/index.html": "build_ledger",
    "franchise/index.html": "build_franchise",
}


def test_the_display_flag_is_on():
    # owner XM-FLIP 2026-10-22 'MLB + FA rows now'
    assert X.XM_DISPLAY_ON is True
    assert B.xm_display_on() is True


def test_every_surface_page_is_listed_once():
    assert len(set(B.XM_SURFACE_PAGES)) == len(B.XM_SURFACE_PAGES) == 8
    assert set(BUILDERS) | {"prospx/index.html"} == set(B.XM_SURFACE_PAGES)


@pytest.mark.parametrize("rel,fn", sorted(BUILDERS.items()))
def test_flag_off_the_built_page_is_unchanged(monkeypatch, rel, fn):
    monkeypatch.setattr(X, "XM_DISPLAY_ON", False)
    html = getattr(B, fn)()
    assert "xm-surfaces" not in html
    assert B.xm_surfaces_inject(rel, html) == html


def test_flag_off_the_hand_page_is_unchanged(monkeypatch):
    # the served hand page carries the tag while the flag is on; off strips it
    html = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert html.count("xm-surfaces.js") == (1 if X.XM_DISPLAY_ON else 0)
    monkeypatch.setattr(X, "XM_DISPLAY_ON", False)
    off = B.xm_surfaces_inject("prospx/index.html", html)
    assert "xm-surfaces" not in off
    assert B.xm_surfaces_inject("prospx/index.html", off) == off


def test_a_page_outside_the_list_is_never_touched(monkeypatch):
    monkeypatch.setattr(X, "XM_DISPLAY_ON", True)
    page = "<html><body>x</body></html>"
    assert B.xm_surfaces_inject("index.html", page) == page


@pytest.mark.parametrize("rel", sorted(B.XM_SURFACE_PAGES))
def test_flag_on_adds_one_stamped_tag_and_off_restores_the_bytes(monkeypatch, rel):
    page = "<html><head></head><body><main>x</main><script src=\"/assets/a.js\" defer></script></body></html>"
    monkeypatch.setattr(X, "XM_DISPLAY_ON", True)
    on = B.xm_surfaces_inject(rel, page)
    tags = re.findall(r'<script src="/assets/xm-surfaces\.js\?v=([0-9a-f]{8})" defer></script>', on)
    assert tags == [B._asset_ver("assets/xm-surfaces.js")]
    assert on.index("xm-surfaces.js") < on.index("</body>")
    assert B.xm_surfaces_inject(rel, on) == on          # idempotent
    monkeypatch.setattr(X, "XM_DISPLAY_ON", False)
    assert B.xm_surfaces_inject(rel, on) == page        # round trip


def test_write_routes_through_the_injector(monkeypatch, tmp_path):
    monkeypatch.setattr(B, "ROOT", tmp_path)
    monkeypatch.setattr(X, "XM_DISPLAY_ON", False)
    page = "<html><body>x</body></html>"
    B._write("fa/index.html", page)
    assert (tmp_path / "fa" / "index.html").read_text(encoding="utf-8") == page
    monkeypatch.setattr(X, "XM_DISPLAY_ON", True)
    B._write("fa/index.html", page)
    assert "xm-surfaces.js" in (tmp_path / "fa" / "index.html").read_text(encoding="utf-8")


def test_the_data_files_carry_the_display_lock():
    for name in ("xm_players.json", "xm_clubs.json"):
        p = DATA / name
        if p.is_file():
            assert json.loads(p.read_text(encoding="utf-8"))["display_on"] is X.XM_DISPLAY_ON, name
    assert "doc.display_on" in JS and "xm_players.json" in JS and "xm_clubs.json" in JS


def test_a_free_agents_xm_equals_the_fa_board_prediction():
    xp, fc = DATA / "xm_players.json", DATA / "fa_class.json"
    if not (xp.is_file() and fc.is_file()):
        pytest.skip("data files absent")
    doc = json.loads(xp.read_text(encoding="utf-8"))
    cols = doc["columns"]
    board = {m["key"]: m for m in json.loads(fc.read_text(encoding="utf-8"))["members"]}
    n = 0
    for arr in doc["players"].values():
        r = dict(zip(cols, arr))
        if r["pop"] != "fa" or r["key"] not in board:
            continue
        m = board[r["key"]]
        n += 1
        assert (r["aav"], r["years"], r["total"], r["fair"]) == (
            m["projAav"], m["projYears"], m["projGuar"], m["rational"]), r["key"]
        assert r["cf"] is False
    assert n > 150


def test_xm_columns_are_the_ones_the_script_reads():
    for col in ("key", "mlbam", "cf", "clip", "aav", "aav_p10", "aav_p90", "years", "years_p10",
                "years_p90", "total", "total_p10", "total_p90", "fair"):
        assert col in X.COLUMNS, col


def test_the_script_draws_no_gap_and_leaves_modules_alone():
    low = JS.lower()
    for word in ("gap column", "overpay", "underpay", "xm - fair", "fair - xm", "r.fair - r.aav", "r.aav - r.fair"):
        assert word not in low, word
    assert "—" not in JS and "–" not in JS
    # it decorates; it does not write to or replace a module's script
    assert "eval(" not in JS and "document.write" not in JS
    # a counterfactual row is labelled wherever a price is drawn
    assert "as if FA" in JS and "COUNTERFACTUAL" in JS


def test_no_module_asset_names_the_script():
    for p in (ROOT / "assets").glob("*.js"):
        if p.name == "xm-surfaces.js":
            continue
        assert "xm-surfaces" not in p.read_text(encoding="utf-8"), p.name


def test_glossary_entries_are_present_short_and_clean():
    g = json.loads((DATA / "glossary.json").read_text(encoding="utf-8"))
    ids = {e["id"]: e for e in g["entries"]}
    for k in ("xm_dollars", "fair_dollars"):
        e = ids[k]
        blob = json.dumps(e, ensure_ascii=False)
        assert "—" not in blob and "–" not in blob
        assert e["formula"] and e["definition"] and e["methodology"]
        assert len(e["definition"]) < 400
        assert all(s in ids for s in e["seeAlso"]), k
    assert "fa_market" in ids["xm_dollars"]["methodology"]
    assert "fa_rational_value" in ids["fair_dollars"]["methodology"]
    assert "no gap column" in ids["fair_dollars"]["methodology"]


def test_the_ledger_block_never_draws_the_market_surplus():
    # owner answer XM2-Q2: roster and farm on the Ledger, the market-rate surplus
    # on Franchise and in the Trade Machine only
    assert "clubBlockHtml(code, '<h3>Expected market $ (xM$) and Fair $</h3>', \"ledger\")" in JS
    assert "clubBlockHtml(code, '<h3>Expected market $ (xM$) and Fair $</h3>', \"franchise\")" in JS
    assert 'var withSurplus = surface === "franchise";' in JS
    i = JS.index('row("Market-rate surplus over control')
    assert JS[i - 20:i].strip().endswith("(withSurplus ?")
    assert JS.count('row("Market-rate surplus over control') == 1
    # the payroll on file is quoted beside the roster sum and labelled
    assert 'var PAYROLL_NOTE = "not a payroll projection";' in JS
    assert "data-xm-payroll" in JS


def test_the_trade_machine_sums_the_market_surplus_per_side():
    i = JS.index("function tradeMachine()")
    body = JS[i:JS.index("function clubBlockHtml(")]
    assert "r.msur_xm" in body and "r.msur_fair" in body and "data-xm-msur" in body


def test_a_prospect_shows_fair_only_with_xm_withheld():
    # gate section 16 (owner answer XM2B-Q1)
    assert 'var XM_WITHHELD = "outside the market model\'s range";' in JS
    assert "r.xm_withheld" in JS and "r.reach" not in JS
    assert "reach probability" not in JS
    for col in ("arrive", "xm_withheld", "msur_xm", "msur_fair", "ctrl", "pop"):
        assert col in X.COLUMNS, col
    assert "reach" not in X.COLUMNS


def test_the_fa_board_detail_row_gets_a_pad_for_the_xm_column():
    """PORT_RED_TESTS_TRIAGE (2026-10-22): faBoard() widened the header by one
    th and skipped the open detail row, which paints one pad per column past
    its colspan cell (fa.js faDetailRow), so the row drew one cell fewer than
    the header. The pad carries the column's fold class and rides with it."""
    i = JS.index("function faBoard()")
    body = JS[i:JS.index("function ", i + 10)]
    assert 'tr.querySelector("td.fa-dt-cell")' in body
    assert 'pad.className = "fc-xm fa-dt-pad";' in body
    assert 'pad.setAttribute("aria-hidden", "true");' in body
    assert 'if (dt && !tr.querySelector("td.fc-xm"))' in body
