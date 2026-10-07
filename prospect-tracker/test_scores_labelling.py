# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The labelling rule of plan 4 on the rendered /scores/ page (SCORES_3;
SCORES_6 extends it with the pregame model panel).

  * every [data-model-id] element names an id in index.json's registry block
    and shows that row's sentence, which names the source and the verdict
    together ("MLB, provisional");
  * every percentage on a card sits inside a labelled element;
  * no model or market number on a live or final card: the only model ids
    the page draws are the three scores rows;
  * the betting words (edge, value, EV, Kelly, pick, lean, bet) appear
    nowhere on the page as whole words; SCORES_3 renders neither of the two
    exempt elements (the disclaimer block, the verdict sentence), so there
    is no exemption to allow yet.

Rendered on the fixture site of test_scores_render.py, never on real data.
"""
from __future__ import annotations

import re

import pytest

from conftest import serve_site
from test_scores_render import TODAY, make_site, scores_page

SCORES_IDS = {"scores_mlb_wp", "scores_stars_rule", "scores_biggest_plays_rule"}
BETTING_WORDS = re.compile(r"\b(edge|value|ev|kelly|pick|lean|bet)\b", re.IGNORECASE)
VIEWS = [f"#date={TODAY}", "#date=2026-09-29", "#date=2026-10-01", "#game=849845", "#game=849845&tab=box",
         "#game=849845&tab=plays", "#game=849845&tab=lineups", "#game=849845&tab=info", "#game=849846",
         "#game=849841", "#about"]

_AUDIT = """() => {
  const out = {labels: [], loose: [], ids: []};
  document.querySelectorAll('#scores-app-root [data-model-id]').forEach(el => {
    const src = el.querySelector(':scope > .sc-src');
    out.ids.push(el.dataset.modelId);
    out.labels.push([el.dataset.modelId, src ? src.textContent : null]);
  });
  const walk = document.createTreeWalker(document.getElementById('scores-app-root'), NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walk.nextNode())) {
    if (!/%/.test(n.nodeValue)) continue;
    const card = n.parentElement.closest('.sc-card');
    if (card && !n.parentElement.closest('[data-model-id]')) out.loose.push(n.nodeValue.trim());
  }
  return out;
}"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return make_site(tmp_path_factory.mktemp("scores_label_site"))


@pytest.fixture(scope="module")
def pw():
    sync = pytest.importorskip("playwright.sync_api")
    with sync.sync_playwright() as p:
        try:
            p.chromium.launch().close()
        except Exception as e:  # pragma: no cover
            pytest.skip(f"chromium unavailable: {e}")
        yield p


def test_every_model_number_is_labelled_and_no_betting_word_renders(site, pw):
    import json
    ix = json.loads((site / "data" / "scores" / "index.json").read_text(encoding="utf-8"))
    sentences = {r["model_id"]: r["sentence"] for r in ix["registry"]}
    seen_ids = set()
    with serve_site(site) as base, scores_page(base, pw, hash_=VIEWS[0]) as page:
        page.wait_for_selector("#scores-app-root .sc-card")
        for h in VIEWS:
            page.evaluate(f"location.hash = '{h}'")
            page.wait_for_timeout(500)
            res = page.evaluate(_AUDIT)
            for mid, label in res["labels"]:
                assert mid in sentences, (h, mid)
                assert label and label.strip() == sentences[mid], (h, mid, label)
                assert "provisional" in label and (label.startswith("MLB") or label.startswith("Eephus")), label
            assert set(res["ids"]) <= SCORES_IDS, (h, res["ids"])
            assert res["loose"] == [], (h, res["loose"])
            seen_ids |= set(res["ids"])
            hits = BETTING_WORDS.findall(page.locator(".scores-app").inner_text())
            assert hits == [], (h, hits)
    assert seen_ids == SCORES_IDS


def test_live_and_final_cards_carry_no_betting_or_market_number(site, pw):
    with serve_site(site) as base, scores_page(base, pw, hash_=f"#date={TODAY}") as page:
        page.wait_for_selector('article[data-state="live"]')
        for sel in ('article[data-state="live"]',):
            ids = page.locator(f"{sel} [data-model-id]").evaluate_all("els => els.map(e => e.dataset.modelId)")
            assert set(ids) <= {"scores_mlb_wp"}, ids
        page.evaluate("location.hash = '#date=2026-09-29'")
        page.wait_for_selector('article[data-pk="849845"]')
        ids = page.locator('article[data-state="final"] [data-model-id]').evaluate_all("els => els.map(e => e.dataset.modelId)")
        assert set(ids) <= {"scores_mlb_wp", "scores_stars_rule"}, ids
        html = page.locator(".sc-grid").inner_html()
        for word in ("betting", "p_home", "market", "odds"):
            assert word not in html.lower(), word


def test_the_shell_copy_passes_the_betting_word_rule():
    import build_site
    html = build_site.build_scores()
    head = html.split('id="scores-app-root"')[0]
    body = head[head.find("<main"):] if "<main" in head else head
    sub = re.sub(r"<[^>]+>", " ", body.split("section-head--byline")[-1])
    assert BETTING_WORDS.findall(sub) == []
