# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Model Updates page at /models/updates/ (LIBRARY_12).

build_site.build_model_updates() is a pure reader of data/model_updates.json,
so these tests build the page in memory and dirty nothing. They pin what the
page promises: every model in the file has its row and its anchor; the eFV
pinned row prints the edge text of the last vm2 ledger row exactly (two legs,
no summed figure: LB-Q1); no lead prints where the interval covers zero; a
'rows changed' cell carries no improvement figure; the unscored states name
themselves; the route rides the sitemap, the footer, the /models/ hub and the
Library's Evidence shelf; the copy passes the lint; the client fetches
nothing; the tables and the ladders carry their accessible names.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

import build_site as B
import model_updates as MU

ROOT = Path(__file__).resolve().parent
_DASHES = ("—", "–")
_INTERVAL = re.compile(r"^([+-]?\d+(?:\.\d+)?) to ([+-]?\d+(?:\.\d+)?)$")


@pytest.fixture(scope="module")
def doc():
    d = MU.load()
    if not d:
        pytest.skip("data/model_updates.json is absent")
    return d


@pytest.fixture(scope="module")
def page(doc):
    return B.build_model_updates()


@pytest.fixture(scope="module")
def soup(page):
    return BeautifulSoup(page, "html.parser")


def _rows_of(soup, mid):
    return soup.select(f'.mu-stands tr.mu-stand[data-model="{mid}"], '
                       f'.mu-stands tr.mu-legrow[data-model="{mid}"]')


def _leg_pairs(soup):
    """(edge text, interval text) for every printed leg on the page: the
    stands rows (one row per leg), eFV's folded source legs, and the
    timetable's legs (paired by data-leg inside a row)."""
    for tr in soup.select(".mu-stands tr.mu-stand, .mu-stands tr.mu-legrow"):
        e, i = tr.select_one(".mu-c-edge"), tr.select_one(".mu-c-int")
        if e and i:
            yield e.get_text(" ", strip=True), i.get_text(" ", strip=True)
    for tr in soup.select("table.mu-legs > tbody > tr"):
        tds = tr.find_all("td")
        yield tds[1].get_text(" ", strip=True), tds[3].get_text(" ", strip=True)
    for tr in soup.select("#mu-rows > tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        edges = {d["data-leg"]: d.get_text(" ", strip=True) for d in cells[5].select(".mu-leg")}
        ints = {d["data-leg"]: d.get_text(" ", strip=True) for d in cells[7].select(".mu-leg")}
        for k, e in edges.items():
            yield e, ints.get(k, "")


def test_every_model_has_its_row_and_anchor(doc, soup):
    anchors = {tr["id"] for tr in soup.select("tr.mu-stand[id]")}
    for m in doc["models"]:
        assert f"model={m['model_id']}" in anchors, m["model_id"]
        drawer = soup.find(id=f"mu-d-{m['model_id']}")
        assert drawer is not None and drawer.get("data-model") == m["model_id"]
        btn = soup.find(id=f"model={m['model_id']}").select_one(".mu-open")
        assert btn["aria-controls"] == f"mu-d-{m['model_id']}"
        assert btn["aria-expanded"] == "false"
    served = [m for m in doc["models"] if m.get("served")]
    assert len(soup.select(".mu-sec tr.mu-stand")) == len(doc["models"])
    assert f"{len(served)} served models" in soup.get_text()


def test_every_event_model_appears_in_the_timetable(doc, soup):
    rows = soup.select("#mu-rows > tr")
    assert len(rows) == len(doc["events"])
    names = {tr.find("th").get_text(strip=True) for tr in rows}
    for ev in doc["events"]:
        assert (ev.get("label") or ev.get("family")) in names, ev["event_id"]
    shown = [tr for tr in rows if not tr.has_attr("hidden")]
    assert len(shown) == sum(1 for e in doc["events"] if e.get("default_view"))
    assert f"Showing {len(shown)} of {len(rows)} updates." in soup.select_one("#mu-status").get_text()


def test_efv_pinned_row_prints_the_last_vm2_ledger_row(doc, soup):
    progress = json.loads((ROOT / "data" / "efv_progress.json").read_text(encoding="utf-8"))
    legs, row = MU.efv_today(progress)
    assert row is not None and row["frame"] == "vm2"
    want = [lg["edge_text"] for lg in legs if lg["role"] == "headline"]
    assert [lg["stat"] for lg in legs if lg["role"] == "headline"] == ["Spearman", "AUC"]
    trs = _rows_of(soup, "efv_v2")
    got = [tr.select_one(".mu-c-edge").get_text(strip=True) for tr in trs]
    assert got == want
    # pinned first in the stands table, two legs, no summed figure
    first = soup.select_one(".mu-stands tr.mu-stand")
    assert first["id"] == "model=efv_v2" and first.has_attr("data-pinned")
    assert len(trs) == 2 and "sum" not in " ".join(got).lower()
    # the four industry legs fold under 'against each source'
    sub = soup.select_one('.mu-stands tr.mu-sub[data-model="efv_v2"] details.mu-src')
    assert sub is not None and "against each source" in sub.summary.get_text()
    folded = [tr.find_all("td")[1].get_text(strip=True) for tr in sub.select("table.mu-legs > tbody > tr")]
    assert folded == [lg["edge_text"] for lg in legs if lg["role"] != "headline"]


def test_no_lead_where_the_interval_covers_zero(soup):
    n = 0
    for edge, interval in _leg_pairs(soup):
        m = _INTERVAL.match(interval)
        if not m:
            continue
        n += 1
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo <= 0 <= hi:
            assert "lead" not in edge, (edge, interval)
    assert n > 20


def test_a_rows_changed_cell_prints_no_improvement(soup):
    seen = 0
    for tr in soup.select("#mu-rows > tr"):
        cell = tr.find_all(["td", "th"], recursive=False)[3].get_text(" ", strip=True)
        if "rows changed" in cell:
            seen += 1
            assert "same rows" not in cell and not re.search(r"\([+-]\d", cell), cell
            assert "improvement" not in cell
        elif "same rows" in cell:
            assert "rows changed" not in cell
    assert seen > 0


def test_unscored_states_name_themselves(soup):
    wag = soup.find(id="model=wag")
    assert wag.select_one(".mu-c-edge").get_text(strip=True) == "no benchmark registered"
    ps = soup.find(id="model=prospect_surplus")
    assert ps.select_one(".mu-c-edge").get_text(strip=True) == "benchmark named; headline not wired yet"
    folds = [d.summary.get_text(" ", strip=True) for d in soup.select("details.mu-fold")]
    assert any(f.startswith("No benchmark registered") for f in folds)
    assert any(f.startswith("Benchmark named; headline not wired yet") for f in folds)


def test_scored_on_is_the_card_stat_never_the_registry_metric(doc, soup):
    for m in doc["models"]:
        if not m.get("today") or m["model_id"] == "efv_v2":
            continue
        stats = [tr.select_one(".mu-c-stat").get_text(strip=True) for tr in _rows_of(soup, m["model_id"])]
        assert stats == [lg["stat"] for lg in m["today"]], m["model_id"]


def test_route_rides_sitemap_footer_hub_and_library():
    assert ("/models/updates/", "daily", "0.6") in B.sitemap_pages()
    foot = B._footer()
    i, j = foot.index('href="/models/"'), foot.index('href="/models/updates/"')
    assert i < j and ">Model Updates</a>" in foot
    assert 'href="/models/updates/"' in B.build_models()
    assert B.PAGE_LABELS["/models/updates/"] == "Model Updates"
    built = (ROOT / "models" / "updates" / "index.html").is_file()
    assert ('href="/models/updates/"' in B._glossary_strip()) == built
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    main = src[src.index("def main() -> None:"):]
    # written before the Library, whose strip shows the leaf only once the page exists
    assert main.index('"models/updates/index.html"') < main.index('"glossary/index.html"')


def test_page_passes_the_copy_lint(page):
    assert not any(d in page for d in _DASHES)
    soup = BeautifulSoup(page, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    text = soup.get_text(" ", strip=True)
    hit = MU._ban_re().search(text)
    assert hit is None, text[max(0, hit.start() - 60):hit.end() + 60]
    for rel in ("assets/model_updates.js", "assets/model_updates.css"):
        body = (ROOT / rel).read_text(encoding="utf-8")
        assert not any(d in body for d in _DASHES), rel


def test_client_fetches_nothing_and_uses_the_state_component():
    js = (ROOT / "assets" / "model_updates.js").read_text(encoding="utf-8")
    for bad in ("fetch(", "XMLHttpRequest", ".json", "innerHTML = '<"):
        assert bad not in js, bad
    assert 'ST.render(empty, "empty"' in js and '"loading"' in js and '"failed"' not in js
    assert "No updates match " in js
    css = (ROOT / "assets" / "model_updates.css").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), "tokens only"
    assert "border-radius:0" in css and not re.search(r"border-radius:\s*[1-9]", css)


def test_tables_filters_and_ladders_carry_accessible_names(page, soup):
    for t in soup.select("table.mu-table, table.mu-legs"):
        assert t.caption is not None and t.caption.get_text(strip=True)
        assert all(th.get("scope") == "col" for th in t.select("thead th"))
    chips = soup.select("[data-mu-fam], [data-mu-kind], [data-mu-layer]")
    assert chips and all(c.name == "button" and c.get("aria-pressed") in ("true", "false") for c in chips)
    assert all(c["aria-pressed"] == "false" for c in soup.select("[data-mu-layer]"))
    lads = soup.select("svg.mu-lad")
    assert lads
    for svg in lads:
        assert svg["role"] == "img"
        lab = svg["aria-label"]
        assert ": latest Result (" in lab and re.search(r"\d+ leads?, \d+ ties?, \d+ trails?", lab), lab
    # the stylesheet loads ahead of the markup (the /models/ QREP05 precedent)
    assert 0 < page.find('href="/assets/model_updates.css?v=') < page.find('class="fa-app mu-app"')
