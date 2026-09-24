# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The Dugout context block on /betting/, rendered (py_mini_racer; skipped without it).

The block is a <details> closed by default at the foot of every game card and of the
filled slot cards, resolved by game_pk through dugout_context.games (never by parsing
the matchup), absent from the redacted slot, the empty slot and the all-bets board
view, and it prints the payload's own not-priced sentence wherever it renders. Nothing
on the card above it changes by one byte. No plus suffix, no tier class, no ladder, no
sign colour, no sentence the payload did not carry.

The harness is test_betting's: PRELUDE, the fetch router, __show(section) and
_visible_text. The board fixture is test_betting_dugout's, run through
betting_dugout.build_block so the payload block is the real shape.
"""
from __future__ import annotations

import json
import re

import pytest

import betting_dugout as bd
from test_betting import (JS, PRELUDE, _ctx, _fetch_js, _visible_text, LIVE_PAYLOAD,
                          LEARNING_ARTIFACT, EVAL_ARTIFACT, CLV_EMPTY)
from test_betting_dugout import board_fixture, _hook, _row

DETAILS_TOKEN = 'class="bt-dugout"'
DARK_TOKEN = "bt-dugout-dark"
DETAILS_RE = re.compile(r'<details class="bt-dugout">.*?</details>', re.S)


def _board():
    b = _hook(board_fixture())
    rows = b["clubs"]["rows"]
    rows.append(_row("SEA", 2026, z_hook=-0.6, z_pen=1.1, mwpa_pinch_run=None, n_pinch_run=13))
    rows.append(_row("TBR", 2026, z_hook=0.2))
    # BOS has no 2026 row: the row note and the bare link render for it
    return b


def _live() -> dict:
    return json.loads(LIVE_PAYLOAD)


def _block(payload: dict) -> dict:
    bets = list(payload["team_bets"])
    # the pick's game (823104, TBR at SEA) is not among the cards: the map covers it
    bets.append({"game_pk": 823104, "away": {"org": "TBR"}, "home": {"org": "SEA"}})
    return bd.build_block(bets, payload["slate_date"], board=_board())


def _payload(with_block: bool = True, **edits) -> dict:
    d = _live()
    d.update(edits)
    if with_block:
        d["dugout_context"] = _block(d)
    return d


def _routes(d: dict) -> str:
    return _fetch_js(main=json.dumps(d), learning=LEARNING_ARTIFACT, evald=EVAL_ARTIFACT,
                     clv=CLV_EMPTY)


@pytest.fixture(scope="module")
def ctx():
    return _ctx(_routes(_payload()))


@pytest.fixture(scope="module")
def teams(ctx):
    return ctx.eval("__show('teams')")


@pytest.fixture(scope="module")
def potd(ctx):
    return ctx.eval("__show('potd')")


# ---------------------------------------------------------------------------
# where it renders
# ---------------------------------------------------------------------------
def test_the_dugout_block_renders_on_each_game_card_with_both_clubs(teams):
    d = _payload()
    assert teams.count(DETAILS_TOKEN) == len(d["team_bets"]) == 2
    sums = re.findall(r'<summary class="bt-details-sum bt-dugout-sum">(.*?)</summary>', teams)
    assert sums == ["Dugout context, not priced: TBR, SEA", "Dugout context, not priced: BOS, NYY"]
    frags = DETAILS_RE.findall(teams)
    assert len(frags) == 2
    for frag, (away, home) in zip(frags, (("TBR", "SEA"), ("BOS", "NYY"))):
        orgs = re.findall(r'<div class="bt-dugout-org">.*?\s([A-Z]{2,3})</div>', frag)
        assert orgs == [away, home], orgs
    # every block is a closed <details>: no `open` attribute anywhere on it
    assert "<details class=\"bt-dugout\" open" not in teams and "<details open" not in teams


def test_the_dugout_block_renders_on_the_pick_card_by_game_pk_without_parsing_the_matchup():
    d = _payload()
    d["pick_of_the_day"]["matchup"] = "zzz nonsense that names no club"
    c = _ctx(_routes(d))
    html = c.eval("__show('potd')")
    assert html.count(DETAILS_TOKEN) == 1
    frag = DETAILS_RE.findall(html)[0]
    assert "Dugout context, not priced: TBR, SEA" in frag
    assert "zzz nonsense" not in frag
    # the block is the LAST child of the pick card
    pick = html[html.index('<div class="bt-pick">'):]
    assert pick.rstrip().endswith("</details></div>") or frag + "</div>" in pick


def test_the_redacted_and_empty_slots_carry_no_block():
    d = _payload()
    d["pick_of_the_day"] = {"redacted": True, "market": "total", "min_edge_used": 0.06,
                            "game_pk": 823104}
    d["longshot_of_the_day"] = None
    c = _ctx(_routes(d))
    html = c.eval("__show('potd')")
    assert DETAILS_TOKEN not in html
    assert "bt-pick-redacted" in html and "bt-pick-empty" in html
    assert DARK_TOKEN not in html           # a built block has no dark note either


BOARD_VIEW_PRELUDE = """
var __tvBtn = (function () { var hs = [];
  return { getAttribute: function (n) { return n === 'data-teamview' ? 'board' : null; },
           addEventListener: function (t, cb) { if (t === 'click') hs.push(cb); },
           click: function () { hs.forEach(function (h) { h({}); }); } }; })();
var __origGet = document.getElementById;
document.getElementById = function (id) {
  var e = __origGet(id);
  if (id !== 'betting-app-root') return e;
  return new Proxy(e, {
    get: function (t, k) {
      if (k === 'querySelectorAll') return function (sel) { return sel === '[data-teamview]' ? [__tvBtn] : []; };
      return t[k];
    },
    set: function (t, k, v) { t[k] = v; return true; }
  });
};
"""


def test_the_block_is_absent_from_the_all_bets_board_view():
    """S is closure-private and S.teamView starts as "cards" (the localStorage read
    never runs), so the test hands wireTeamView a fake "All bets" button through the
    app root and clicks it: renderSection then paints allBetsTable, which carries no
    management figure."""
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    c = MiniRacer()
    c.eval(PRELUDE + BOARD_VIEW_PRELUDE + _routes(_payload()) + JS)
    cards = c.eval("__show('teams')")
    assert cards.count(DETAILS_TOKEN) == 2                    # the cards view, with blocks
    html = c.eval("__tvBtn.click(); __html['betting-app-root']")
    assert html != cards
    assert 'data-teamview="board" aria-pressed="true"' in html
    assert "<table" in html
    assert "bt-dugout" not in html
    assert "Dugout" not in _visible_text(html)


def test_the_teams_tab_still_costs_one_request():
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    routes = _routes(_payload()).replace("var fetch = function (url) {",
                                         "var __fetched = []; var fetch = function (url) { __fetched.push(url);", 1)
    c = MiniRacer()
    c.eval(PRELUDE + routes + JS)
    before = c.eval("__fetched.length")
    c.eval("__show('teams')")
    c.eval("__show('potd')")
    after = c.eval("__fetched.length")
    assert after == before, "painting the teams or pick tab made a request; the block is in the payload"
    assert c.eval("__fetched[0]") == "/data/betting.json"


# ---------------------------------------------------------------------------
# what it says
# ---------------------------------------------------------------------------
def test_the_not_priced_sentence_is_present_wherever_the_block_renders(teams, potd):
    for html in (teams, potd):
        n_blocks = html.count(DETAILS_TOKEN) + html.count(DARK_TOKEN)
        assert n_blocks >= 1
        assert _visible_text(html).count(bd.NOT_PRICED_SENTENCE) == n_blocks
    dark = _payload()
    dark["dugout_context"] = bd.build_block(dark["team_bets"], dark["slate_date"],
                                            data_dir=__import__("pathlib").Path("/nonexistent"))
    assert dark["dugout_context"]["status"] == "unavailable"
    c = _ctx(_routes(dark))
    for sec in ("teams", "potd"):
        html = c.eval("__show('%s')" % sec)
        assert html.count(DETAILS_TOKEN) == 0
        assert html.count(DARK_TOKEN) == 1, sec
        text = _visible_text(html)
        assert text.count(bd.NOT_PRICED_SENTENCE) == 1
        assert bd.BOARD_ABSENT in text


def test_the_block_carries_no_plus_suffix_no_ladder_and_no_sign_colour(teams, potd):
    frags = DETAILS_RE.findall(teams) + DETAILS_RE.findall(potd)
    assert frags
    for frag in frags:
        for bad in ("bt-pos", "bt-neg", "vt-", "EephusTiers", "bt-tag-ok", "bt-tag-warn",
                    "bt-bestval", "accent-green", "accent-red", "style="):
            assert bad not in frag, bad
        labels = re.findall(r'<span class="bt-dugout-zl">(.*?)</span>', frag)
        assert labels
        for lab in labels:
            assert not _visible_text(lab).rstrip().endswith("+"), lab
        zs = re.findall(r'<span class="bt-dugout-zv">(.*?)</span>', frag)
        assert zs and all(re.fullmatch(r"[+-]\d+\.\d", z) for z in zs), zs
        heads = re.findall(r'<div class="bt-dugout-hd">(.*?)</div>', frag)
        assert not any(h.endswith("+") for h in heads)
        # realized rows: family, n, then a value signed to three places or the dim
        # below-floor sentence; rate and shape rows: label then a plain number
        rows3 = re.findall(r'<tr><td class="bt-l">([^<]*)</td><td>([^<]*)</td><td>(.*?)</td></tr>', frag)
        assert len(rows3) >= 6
        for _fam, n, cell in rows3:
            assert re.fullmatch(r"\d+|-", n), n
            if "bt-dim" in cell:
                assert "below the floor of" in _visible_text(cell)
            else:
                assert re.fullmatch(r"[+-]\d+\.\d{3}", cell), cell
        rows2 = re.findall(r'<tr><td class="bt-l">([^<]*)</td><td>([^<]*)</td></tr>', frag)
        assert len(rows2) >= 6
        for _lab, cell in rows2:
            assert re.fullmatch(r"\d+(\.\d+)?|-", cell), cell     # never signed, never coloured
        assert "mWPA" in frag and "wins, realized value, not skill" in _visible_text(frag)
        # the header cell is the glossary term alone; the board's units sentence is a
        # fine line under the table, never inside a <th> (review: a three-line header
        # cell at 390)
        ths = [_visible_text(t).strip() for t in re.findall(r"<th[^>]*>(.*?)</th>", frag)]
        assert ths and set(ths) == {"Family", "n", "mWPA"}, ths
        fine = re.findall(r'<p class="bt-dugout-fine">(.*?)</p>', frag)
        assert any(_visible_text(f).startswith("mWPA: wins, realized value, not skill") for f in fine), fine
        text = _visible_text(frag)
        assert "DVS" not in text and "best decision" not in text and "worst decision" not in text
        assert "100" not in re.sub(r"\d+\.\d+", "", " ".join(z for z in zs))   # no 100+10z


def test_the_block_never_touches_a_priced_cell(teams, potd):
    """Render the same payload with and without the block: with every dugout details
    fragment removed, the html is byte-identical, and each fragment sat as the last
    child of its card."""
    c0 = _ctx(_routes(_payload(with_block=False)))
    for sec, html in (("teams", teams), ("potd", potd)):
        bare = c0.eval("__show('%s')" % sec)
        stripped = DETAILS_RE.sub("", html)
        assert stripped == bare, sec
        for m in DETAILS_RE.finditer(html):
            assert html[m.end():m.end() + 6] == "</div>", "the block is not the card's last child"
        for cls in ("bt-markets", "bt-game-probs", "bt-game-sp", "bt-pick-nums", "bt-pick-sel",
                    "bt-bestval"):
            a = re.findall(r'class="%s[^"]*"[^>]*>.*?</(?:div|span)>' % cls, html, re.S)
            b = re.findall(r'class="%s[^"]*"[^>]*>.*?</(?:div|span)>' % cls, bare, re.S)
            assert a == b, cls


def test_a_club_without_a_row_prints_the_row_note_and_the_link(teams):
    frag = DETAILS_RE.findall(teams)[1]            # BOS at NYY
    text = _visible_text(frag)
    assert bd.NO_ROW_TEMPLATE.format(season=2026, club="BOS") in text
    assert 'href="/management/#section=clubs&amp;team=BOS"' in frag
    assert 'href="/management/#section=clubs&amp;team=NYY&amp;season=2026"' in frag
    assert "Open BOS on In-Game Management" in text and "Open NYY on In-Game Management" in text


def test_a_null_realized_value_prints_the_below_floor_sentence_in_neutral_ink(teams):
    frag = DETAILS_RE.findall(teams)[0]            # TBR at SEA; SEA pinch_run is null
    assert '<span class="bt-dim">- below the floor of 15 (13 this season)</span>' in frag


def test_the_dugout_css_uses_no_sign_or_tier_token():
    css = JS.split("css.textContent = [", 1)[1].split('].join("");', 1)[0]
    start = css.index('".bt-dugout{')
    end = css.index('".bt-dugout-dark{')
    seg = css[start:end]
    for bad in ("accent-green", "accent-red", "--up", "--down", "vt-"):
        assert bad not in seg, bad
    for tok in ("--border", "--text-primary", "--text-secondary", "--text-tertiary", "--font-retro"):
        assert tok in seg, tok
    assert ".bt-dugout-clubs{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))" in seg
    assert "@media (max-width:640px){" in css
    tail = css.split("@media (max-width:640px){", 1)[1]
    assert ".bt-dugout-body{padding:6px 8px}" in tail and ".bt-dugout-link{display:block" in tail


def test_an_older_payload_without_the_block_renders_exactly_as_before():
    c = _ctx(_routes(_payload(with_block=False)))
    for sec in ("teams", "potd"):
        html = c.eval("__show('%s')" % sec)
        assert "bt-dugout" not in html
        assert "Dugout" not in _visible_text(html)
        assert html.count('class="bt-game"') == (2 if sec == "teams" else 0)


def test_the_client_types_no_sentence_of_its_own():
    """Every sentence in the block comes from the payload. The client's own strings
    inside the dugout functions are glue only."""
    seg = JS[JS.index("function dugoutCtx()"):JS.index("function pickCard(slot)")]
    literals = re.findall(r"'([^']*)'|\"([^\"]*)\"", seg)
    words = [(a or b).lstrip(">") for a, b in literals]
    prose = sorted(set(w for w in words if len(w.split()) >= 3 and "<" not in w
                       and "class=" not in w and not w.startswith("/")))
    assert prose == [" on In-Game Management", "Hook, median pitches (league "], prose
    assert chr(0x2014) not in seg and chr(0x2013) not in seg
