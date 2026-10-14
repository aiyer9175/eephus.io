# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The labelling rule on the rendered /standings/ page (STANDINGS_4;
STANDINGS_PLAN 5.4, the Scores labelling rule of SCORES_PLAN 4):

  * every odds cell (PROJ, DIV%, POST%, PEN%, WS%, SOS) sits inside a
    [data-model-id] element whose visible text names the source and the
    verdict, read from the season file's registry block ("Eephus season
    simulator, provisional"; in October the bracket simulator's Pennant and
    World Series chances read "unvalidated"), and that model id is the one the
    season file's `ours.models` names for the cell's column;
  * no percentage sign outside the ODDS group;
  * no probability inside the bracket mount: no percent sign and no
    [data-model-id] under #st-bracket.

Rendered on the fixture sites of test_standings_render.py, never on real data.
"""
from __future__ import annotations

import pytest

from conftest import serve_site
from test_standings_render import (in_season_file, make_site, october_file, payloads, standings_page)

COL_MODEL = {"PROJ": "proj", "DIV%": "p_div", "POST%": "p_post", "PEN%": "p_pennant", "WS%": "p_ws", "SOS": "sos"}

_AUDIT = """() => {
  const out = {cells: [], loose: [], bracket: null};
  document.querySelectorAll('.st-table').forEach(t => {
    const heads = [...t.querySelectorAll('thead tr:last-child th')].map(th => (th.querySelector('abbr') || th).textContent);
    t.querySelectorAll('tbody tr[data-code] td.st-odds').forEach(td => {
      const w = td.closest('[data-model-id]');
      const lab = w ? w.querySelector(':scope > .st-oddslab') : null;
      out.cells.push([heads[td.cellIndex], w ? w.dataset.modelId : null, lab ? lab.innerText : null]);
    });
  });
  const root = document.getElementById('standings-app-root');
  const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walk.nextNode())) {
    if (!/%/.test(n.nodeValue)) continue;
    if (!n.parentElement.closest('.st-odds')) out.loose.push(n.nodeValue.trim());
  }
  const b = document.getElementById('st-bracket');
  if (b) out.bracket = [b.textContent.includes('%'), b.querySelectorAll('[data-model-id]').length, b.querySelectorAll('.scb').length];
  return out;
}"""


@pytest.fixture(scope="module")
def pw():
    sync = pytest.importorskip("playwright.sync_api")
    with sync.sync_playwright() as p:
        try:
            p.chromium.launch().close()
        except Exception as e:  # pragma: no cover - chromium missing
            pytest.skip(f"chromium unavailable: {e}")
        yield p


def _check(audit, doc):
    reg = {r["model_id"]: r for r in doc["registry"]}
    models = doc["ours"]["models"]
    assert audit["cells"], "no odds cell rendered"
    for head, mid, lab in audit["cells"]:
        assert mid == models[COL_MODEL[head]], (head, mid)
        r = reg[mid]
        assert lab and f"{r['label']}, {r['verdict']}" in lab and "implied, no market" in lab, (head, lab)
    assert audit["loose"] == [], audit["loose"]


@pytest.mark.parametrize("hash_", ["#view=mlb&cols=odds", "#view=division&cols=odds", "#view=wildcard&cols=odds",
                                   "#view=league&cols=odds"])
def test_in_season_odds_cells_are_labelled(tmp_path, pw, hash_):
    doc = in_season_file()
    site = make_site(tmp_path, payloads(doc, today="2026-09-21"))
    with serve_site(site) as base, standings_page(base, pw, width=1280, hash_=hash_) as page:
        a = page.evaluate(_AUDIT)
        _check(a, doc)
        assert {h for h, _m, _l in a["cells"]} == set(COL_MODEL)
        # the detail row's odds lines carry their own label
        page.locator('.st-more[data-code="NYY"]').first.click()
        lines = page.evaluate("""() => [...document.querySelectorAll('.st-detail [data-model-id]')].map(e =>
            [e.dataset.modelId, e.textContent])""")
        assert lines and all("Eephus season simulator, provisional" in t for _m, t in lines)
        assert page.evaluate(_AUDIT)["loose"] == []


def test_october_seeds_carry_the_bracket_verdict_and_the_bracket_none(tmp_path, pw):
    doc = october_file()
    site = make_site(tmp_path, payloads(doc))
    with serve_site(site) as base, standings_page(base, pw, width=1280, hash_="#view=playoffs&cols=odds") as page:
        page.wait_for_selector("#st-bracket .scb", timeout=10000)
        a = page.evaluate(_AUDIT)
        _check(a, doc)
        heads = {(h, m) for h, m, _l in a["cells"]}
        assert ("PEN%", "postseason_bracket_sim") in heads and ("WS%", "postseason_bracket_sim") in heads
        assert ("DIV%", "playoff_odds_sim") in heads
        assert a["bracket"][0] is False and a["bracket"][1] == 0 and a["bracket"][2] >= 1
