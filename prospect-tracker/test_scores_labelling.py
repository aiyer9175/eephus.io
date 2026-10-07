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
    nowhere on the page as whole words outside the two named exemptions:
    the BETTING_DISCLAIMER block and the one element holding the board's
    verdict sentence verbatim (SCORES_6).

SCORES_6 (the pregame block, on the fixture board of test_scores_render):
every pregame number sits in a data-model-id element whose label names its
source and verdict (the model's "Eephus model, unvalidated, provisional",
SEM+ "validated", eFV and the hook median "provisional"); the board's number
prints by the board's own rule (assets/betting.js pct), eFV by PROSPX's
(efvGradeDisplay) and the hook median by the management page's (num), each
pinned by running both formatters in V8; no model number on a started card,
a stale copy, a card past its start time, or a full-board copy while the
Diamond check is gated.

Rendered on the fixture site of test_scores_render.py, never on real data.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import serve_site
from test_scores_render import PRE_REGISTRY, TODAY, _iso, make_site, pregame_payloads, scores_page

ROOT = Path(__file__).resolve().parent
PRE_IDS = {r["model_id"] for r in PRE_REGISTRY}

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


# --------------------------------------------------------------------------- #
# SCORES_6: the pregame block on the fixture board
# --------------------------------------------------------------------------- #
PRE_VIEWS = [f"#date={TODAY}", "#game=900010", "#game=900011", "#game=849848", "#game=849846", "#about"]

#: The page's text with the two exempt elements (the disclaimer block, the
#: verdict sentence) removed from a copy of the DOM.
_TEXT_OUTSIDE_EXEMPTIONS = """() => {
  const c = document.querySelector('.scores-app').cloneNode(true);
  c.querySelectorAll('.betting-disclaimer, .sc-verdict, template').forEach(e => e.remove());
  document.body.appendChild(c);
  const t = c.innerText;
  c.remove();
  return t;
}"""


@pytest.fixture(scope="module")
def pregame_site(tmp_path_factory):
    return make_site(tmp_path_factory.mktemp("scores_label_pregame"), pregame_payloads())


def test_every_pregame_number_is_labelled_and_betting_words_stay_in_the_two_exemptions(pregame_site, pw):
    ix = json.loads((pregame_site / "data" / "scores" / "index.json").read_text(encoding="utf-8"))
    rows = {r["model_id"]: r for r in ix["registry"]}
    seen_ids, exempt_hits = set(), 0
    with serve_site(pregame_site) as base, scores_page(base, pw, hash_=PRE_VIEWS[0]) as page:
        page.wait_for_selector('article[data-pk="900010"] [data-model-id="betting_game_prob"]')
        for h in PRE_VIEWS:
            page.evaluate(f"location.hash = '{h}'")
            page.wait_for_timeout(500)
            res = page.evaluate(_AUDIT)
            for mid, label in res["labels"]:
                assert mid in rows, (h, mid)
                assert label and label.strip() == rows[mid]["sentence"], (h, mid, label)
                assert rows[mid]["verdict"] in label, (h, mid, label)
            assert set(res["ids"]) <= SCORES_IDS | PRE_IDS, (h, res["ids"])
            assert res["loose"] == [], (h, res["loose"])
            seen_ids |= set(res["ids"])
            outside = page.evaluate(_TEXT_OUTSIDE_EXEMPTIONS)
            assert BETTING_WORDS.findall(outside) == [], (h, BETTING_WORDS.findall(outside))
            whole = page.locator(".scores-app").inner_text()
            exempt_hits += len(BETTING_WORDS.findall(whole))
            assert "Eephus model, unvalidated, provisional" in whole or h != "#game=900010"
    assert PRE_IDS <= seen_ids, seen_ids
    assert exempt_hits > 0, "the exemptions were never exercised"


def test_no_model_number_on_a_started_stale_late_or_gated_copy(tmp_path, pw):
    now = datetime.now(timezone.utc)
    p = pregame_payloads(now, inject_live=True)
    doc = p[f"{TODAY}.json"]
    cards = {c["pk"]: c for c in doc["games"]}
    # 900011 becomes a stale copy of 900010's block, and 849848 a card past its start
    stale = copy.deepcopy(cards[900010]["pre"])
    stale["model"]["stale_board"] = True
    cards[900011]["pre"] = stale
    cards[849848]["pre"] = copy.deepcopy(cards[900010]["pre"])
    cards[849848]["start"] = _iso(now - timedelta(minutes=5))
    site = make_site(tmp_path / "site", p)
    with serve_site(site) as base, scores_page(base, pw, hash_=f"#date={TODAY}") as page:
        page.wait_for_selector('article[data-pk="900010"] [data-model-id="betting_game_prob"]')
        ids = page.locator('[data-model-id="betting_game_prob"]').evaluate_all(
            "els => els.map(e => +e.closest('article').dataset.pk)")
        assert ids == [900010], ids
        for state in ("live", "final"):
            assert page.locator(f'article[data-state="{state}"] [data-model-id="betting_game_prob"]').count() == 0
        html = page.locator('article[data-pk="849846"]').inner_html().lower()
        for word in ("eephus model", "p_home", "47.0%", "53.0%"):
            assert word not in html, word
        for pk in (849846, 900011, 849848):
            page.evaluate(f"location.hash = '#game={pk}'")
            page.wait_for_timeout(400)
            assert page.locator('[data-model-id="betting_game_prob"]').count() == 0, pk
            assert page.locator(".betting-disclaimer").count() == 0, pk


# ---- the formatters and the Diamond check, executed in V8 ---------------------------------------
def _v8():
    mr = pytest.importorskip("py_mini_racer")
    ctx = mr.MiniRacer()
    ctx.eval("var window = {}; var document = { getElementById: function () { return null; } };")
    ctx.eval((ROOT / "assets" / "scores-pregame.js").read_text(encoding="utf-8"))
    return ctx


def _fn(src: str, head: str) -> str:
    """One top-level function's source, from its head to the brace closing it."""
    i = src.index(head)
    depth, j = 0, src.index("{", i)
    while True:
        ch = src[j]
        depth += ch == "{"
        depth -= ch == "}"
        j += 1
        if depth == 0:
            return src[i:j]


def test_the_model_number_prints_by_the_boards_own_rule():
    ctx = _v8()
    ctx.eval(_fn((ROOT / "assets" / "betting.js").read_text(encoding="utf-8"), "function pct(v, d)"))
    vals = [0, 1, 0.5, 0.53012, 0.46988, 0.60326, 0.39674, 0.12345, 0.0049, 0.0005, 0.9995, 0.33333, 0.66667, None]
    for v in vals:
        js = "null" if v is None else repr(v)
        assert ctx.eval(f"window.EephusScoresPregame.pctB({js})") == ctx.eval(f"pct({js})"), v
    assert ctx.eval("window.EephusScoresPregame.pctB(0.53012)") == "53.0%"
    assert ctx.eval("window.EephusScoresPregame.pctB(0.46988)") == "47.0%"


def test_efv_prints_as_prospx_prints_it_and_the_hook_median_as_the_management_page():
    ctx = _v8()
    px = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    ctx.eval(_fn(px, "function efvBoardValue(x)") + "\n" + _fn(px, "function efvGradeDisplay(x)"))
    for v in (51.5, 52.49, 37.5, 44.5, 20.0, 79.6, 50.5, 49.49999):
        assert ctx.eval(f"window.EephusScoresPregame.efvG({v})") == ctx.eval(f"efvGradeDisplay({{xfv_grade: {v}}})"), v
    ctx.eval(_fn((ROOT / "assets" / "management.js").read_text(encoding="utf-8"), "function num(v, nd)"))
    for v in (87.5, 88.0, 91.25, 86.5, 100.49):
        assert ctx.eval(f"window.EephusScoresPregame.num0({v})") == ctx.eval(f"num({v}, 0)"), v


def test_the_card_line_obeys_the_diamond_check_the_clock_and_the_state():
    ctx = _v8()
    p = pregame_payloads()
    card = next(c for c in p[f"{TODAY}.json"]["games"] if c["pk"] == 900010)
    start = datetime.strptime(card["start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000
    ctx.eval("var LAB = function (ix, id, inner, tag, cls) { return '<p data-model-id=\"' + id + '\">' + inner + '</p>'; };"
             "function esc(s) { return String(s); }")

    def line(c, *, gated=False, now=start - 3_600_000):
        h = ("{esc: esc, labelled: LAB, player: function (i, n) { return n; }, "
             f"now: function () {{ return {now}; }}, gated: function () {{ return {str(gated).lower()}; }}}}")
        return ctx.eval(f"window.EephusScoresPregame.card({json.dumps(c)}, {{}}, {h})")

    assert line(card) == '<p data-model-id="betting_game_prob">Eephus model: PHI 47.0%, ATL 53.0%</p>'
    assert line(card, gated=True) == ""                       # a full-board copy while gated
    prev = copy.deepcopy(card)
    prev["pre"]["model"]["board"] = "preview"
    assert line(prev, gated=True) != ""                        # the preview slice is what a gated reader sees
    assert line(card, now=start) == ""                         # at the scheduled start
    for state in ("live", "final", "postponed"):
        assert line(dict(card, state=state)) == "", state
    st = copy.deepcopy(card)
    st["pre"]["model"]["stale_board"] = True
    assert line(st) == ""
    assert line(dict(card, sit={"inning": 1})) == "" and line(dict(card, wp={"home": 500, "ab": 0})) == ""
