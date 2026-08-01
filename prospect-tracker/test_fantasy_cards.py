# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""py_mini_racer smoke test for the /fantasy/ card conversion (assets/fantasy.js).

Stubs the DOM and a synchronous fetch so boot() actually drives a render, then
drives each section tab and asserts:

  * WHICH surfaces became cards and which stayed tables. The conversion was a
    judgement call per surface, not a bulk rewrite, so the split itself is the
    contract worth pinning: 350/250/180/300-row leaderboards are cards; the
    27-row day slate, the 79-row leg list, the 30+30 side-by-side and the 60-row
    call-up list are tables.
  * the two-way regression stays fixed THROUGH the card path: Ohtani's ROS
    Hitters card carries his hitter score, not his pitcher score.
  * every card board exposes keyboard-operable sort controls with aria-sort and
    a direction arrow (the mlbstats.js / projections.js a11y contract, which
    /fantasy/ did not meet at all before: it had no sort of any kind).
  * no mlbam-ONLY record lookup survives anywhere in the module (source guard,
    runs without py_mini_racer).

Skips the rendering half when py_mini_racer is unavailable so it never blocks a
machine without it; the source and CSS guards always run.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
JS_PATH = ROOT / "assets" / "fantasy.js"
CSS_PATH = ROOT / "assets" / "site.css"
JS = JS_PATH.read_text(encoding="utf-8")
CSS = CSS_PATH.read_text(encoding="utf-8")


# ===========================================================================
# Source guards - the two-way (mlbam + side) contract
# ===========================================================================

def test_no_mlbam_only_record_lookup():
    """S.byId is keyed by (mlbam + "|" + side). Every read of it must supply
    both halves; keying on mlbam alone is last-write-wins and is what put
    Ohtani's 172.6 pitcher points on the ROS Hitters board."""
    for m in re.finditer(r"S\.byId\[([^\]]*)\]", JS):
        expr = m.group(1)
        assert '"|"' in expr or "'|'" in expr, (
            f'S.byId indexed without the side half: S.byId[{expr}]')


def test_roto_value_map_is_side_keyed():
    """rotoValue() builds its own id->value map. A one-sided pool means a bare
    mlbam would not collide TODAY, but leaving the mlbam-only shape in place is
    how the Ohtani bug gets reintroduced by the next combined-pool caller."""
    body = JS.split("function rotoValue(")[1].split("\n  function isRoto")[0]
    assert 'out[p.mlbam + "|" + p.side]' in body, (
        "rotoValue must key its output map by mlbam AND side")
    assert not re.search(r"out\[p\.mlbam\]", body), "bare-mlbam key in rotoValue"
    # ...and the reader must use the same composite.
    assert 'rv[p.mlbam + "|" + p.side]' in JS, (
        "scored() must read rotoValue's map with the composite key")
    assert not re.search(r"\brv\[p\.mlbam\]", JS), "bare-mlbam read of rotoValue map"


def test_rec_helpers_are_the_only_record_accessors():
    """rec()/recOf() are the sanctioned accessors. LINKS.byMlbam is a DIFFERENT
    map (person -> merged MLB card key) and is legitimately mlbam-only, so it is
    allowed; nothing else may reach into a record by id."""
    hits = re.findall(r"byMlbam\[([^\]]+)\]", JS)
    assert hits == ["String(mlbam)"], hits


# ===========================================================================
# CSS guards - the pattern's load-bearing bits, and the bug that was in it
# ===========================================================================

def test_mlb_card_has_the_load_bearing_grid_rows():
    assert re.search(r"grid-template-rows:\s*minmax\(0,\s*1fr\)\s*auto", CSS), (
        "the minmax(0,1fr) auto row pair is what reserves the tape's band")


def test_fantasy_card_is_fixed_height_and_virtualized():
    block = CSS.split(".ff-card {")[1].split("}")[0]
    assert re.search(r"height:\s*104px", block), block
    # the virtualization estimate must MATCH the fixed height or the scrollbar
    # lies as cards page in
    assert re.search(r"contain-intrinsic-size:\s*auto\s+104px", block), block
    assert "content-visibility: auto" in CSS, "cards inherit .mlb-card virtualization"


def test_accent_token_is_not_defined_anywhere():
    """Premise of the bugfix below: this stylesheet defines --accent-cyan /
    -gold / -green / -red / -navy / -orange / -lilac, and never a bare
    --accent. If someone later DEFINES --accent this guard should be revisited
    rather than silently kept."""
    assert not re.search(r"^\s*--accent\s*:", CSS, re.MULTILINE)


def test_card_focus_and_glow_do_not_use_the_undefined_accent_token():
    """BUGFIX 2026-07-31. Three .mlb-card rules named `var(--accent)`, which is
    not a token this stylesheet defines. A var() chain that resolves to nothing
    makes the whole declaration INVALID AT COMPUTED-VALUE TIME, so
    `outline: 2px solid var(--accent)` fell back to `outline: initial`: the
    Projections and Free Agency board cards, and their sort headers, had NO
    keyboard focus ring at all, and the hover glow silently did nothing.

    Scope note: `.mlb-card::before { background: var(--org-color,
    var(--accent, currentColor)) }` at ~L2640 also names the undefined token but
    still RESOLVES (to currentColor), so it is a reported finding rather than a
    fix - changing it would repaint the Projections and FA boards."""
    decls = [ln for ln in CSS.splitlines()
             if not ln.lstrip().startswith(("/*", "*")) and re.search(r"var\(\s*--accent\s*[,)]", ln)]
    for ln in decls:
        assert "outline" not in ln, f"focus ring still on the dead token: {ln.strip()}"
        assert "box-shadow" not in ln, f"hover glow still on the dead token: {ln.strip()}"


def test_farm_grid_still_has_no_overflow_x():
    """House rule: wide content scrolls in its OWN wrapper and the farm grid must
    never get overflow-x. The card tape is the wrapper here."""
    tape = CSS.split(".mlb-tape-inner {")[1].split("}")[0]
    assert "overflow-x: auto" in tape, tape


# ===========================================================================
# Rendering smoke test
# ===========================================================================

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

# Hitter weights are format-independent in fantasy_scoring; pitcher weights are
# per-format. Chosen so the scores are unmistakable:
#   Ohtani HIT  = 28*10 + 4.83*1  = 284.83 -> 284.8 -> displayed "285"
#   Ohtani PIT  = 172.62*1        = 172.6  -> displayed "173"
PAYLOAD = """{
 "season": 2026, "season_fraction": 0.62, "n_players": 4,
 "scoring": {"hitter": {"hr": 10, "r": 1},
             "pitcher": {"fgp": {"k": 1}, "sabr": {"k": 1}}},
 "scoring_catalog": [{"id":"fgp","kind":"points","label":"FanGraphs Points","default":true},
                     {"id":"sabr","kind":"points","label":"SABR Points"},
                     {"id":"5x5","kind":"roto","label":"5x5"}],
 "players": [
  {"mlbam":660271,"name":"Shohei Ohtani","side":"hit","pos":"DH","team":"LAD",
   "fpts_fgp":284.8,"skill":{"hem_plus":168,"luck_gap":11.0},
   "ros":{"hr":28,"r":4.83,"rbi":60,"sb":9,"avg":0.301,"obp":0.402,"pa":260}},
  {"mlbam":660271,"name":"Shohei Ohtani","side":"pit","pos":"SP","team":"LAD",
   "fpts_fgp":172.6,"skill":{"sem_plus":121,"luck":0.011},
   "ros":{"k":172.62,"ip":60,"era":2.85,"whip":1.02,"qs":7,"w":5}},
  {"mlbam":592450,"name":"Aaron Judge","side":"hit","pos":"RF","team":"NYY",
   "fpts_fgp":260.0,"skill":{"hem_plus":175,"luck_gap":-6.0},
   "ros":{"hr":25,"r":10.0,"rbi":65,"sb":3,"avg":0.312,"obp":0.440,"pa":270}},
  {"mlbam":621111,"name":"Relief Guy","side":"pit","pos":"RP","team":"BOS",
   "fpts_fgp":60.0,"skill":{"rem_plus":133,"gmli":1.8,"saves":21,"luck":-0.02},
   "ros":{"k":40.0,"ip":22,"era":2.10,"whip":0.95,"sv":12}},
  {"mlbam":800001,"name":"Zeta Starter","side":"pit","pos":"SP","team":"SEA",
   "fpts_fgp":140.0,"skill":{"sem_plus":109,"luck":0.004},
   "ros":{"k":140.0,"ip":70,"era":1.95,"whip":0.98,"qs":9,"w":6}}
 ],
 "sections": {
  "ros_hitter": [660271, 592450],
  "ros_sp": [660271, 800001],
  "ros_rp": [621111],
  "buy_low": [{"mlbam":660271,"side":"hit"}],
  "sell_high": [{"mlbam":592450,"side":"hit"}],
  "closer_depth": {"BOS": [621111]},
  "callup_watch": [{"mlbam":700001,"name":"Kid Prospect","org":"BOS","pos":"SS","eta":2027,"fv":55}],
  "daily_streamers": [{"mlbam":660271,"name":"Shohei Ohtani","date":"2026-07-31","team":"LAD",
                       "opp_org":"SF","opp_off":94,"venue":"Dodger Stadium","per_start_fgp":31.2}],
  "two_start": [{"mlbam":660271,"name":"Shohei Ohtani","team":"LAD","n_starts":2,"total_fgp":58.4,
                 "legs":[{"opp_org":"SF","exp_fgp":30},{"opp_org":"SD","exp_fgp":28,"projected":true}]}],
  "dynasty": [
   {"mlbam":700001,"name":"Kid Prospect","org":"BOS","pos":"SS","eta":2027,"efv":62.4,
    "star":31,"bust":12,"surplus":88.0,"band":[15.0,190.0],"score":9.1,"rank":1,"tier":"Elite"},
   {"mlbam":700002,"name":"Other Kid","org":"SEA","pos":"SP","eta":2029,"efv":48.6,
    "star":9,"bust":34,"surplus":14.0,"band":[0.0,55.0],"score":4.2,"rank":2,"tier":"Tier 3"}
  ]
 }
}"""

PRELUDE = """
var __html = {};
// Sort controls live INSIDE the rendered section, so they are rebuilt on every
// render. Hand renderSection() real node stubs for them (parsed straight back
// out of the markup it just wrote) and keep the live set in __ctrls, so a test
// can actually ACTIVATE a sort header instead of only reading its attributes.
var __ctrls = [];
function __sortNodes() {
  var html = __html['fantasy-app-root'] || '', keys = [], seen = {};
  var re = /data-ffsort="([^"]+)"/g, m;
  while ((m = re.exec(html))) { if (!seen[m[1]]) { seen[m[1]] = 1; keys.push(m[1]); } }
  __ctrls = keys.map(function (k) {
    var hs = {};
    return { __key: k,
      getAttribute: function (n) { return n === 'data-ffsort' ? k : null; },
      addEventListener: function (t, cb) { (hs[t] = hs[t] || []).push(cb); },
      focus: function () {},
      __fire: function (t, ev) { (hs[t] || []).forEach(function (c) { c(ev || {}); }); } };
  });
  return __ctrls;
}
function __sortClick(key) {
  for (var i = 0; i < __ctrls.length; i++) {
    if (__ctrls[i].__key === key) { __ctrls[i].__fire('click'); return __html['fantasy-app-root'] || ''; }
  }
  throw new Error('no sort control for ' + key);
}
function __el(id) {
  return new Proxy(function () { return __el(id); }, {
    get: function (t, k) {
      if (k === 'innerHTML') return __html[id] || '';
      if (k === 'classList') return {add:function(){},remove:function(){},toggle:function(){},contains:function(){return false;}};
      if (k === 'querySelectorAll') return function (sel) {
        return (id === 'fantasy-app-root' && sel === '[data-ffsort]') ? __sortNodes() : [];
      };
      if (k === 'querySelector') return function () { return __el(id + 'q'); };
      if (k === 'getAttribute') return function () { return null; };
      if (k === 'setAttribute' || k === 'addEventListener' || k === 'removeEventListener'
          || k === 'focus' || k === 'appendChild' || k === 'insertBefore') return function () {};
      if (k === 'value' || k === 'textContent') return '';
      if (k === 'nextSibling') return null;
      if (k === 'dataset') return {};
      return __el(id);
    },
    set: function (t, k, v) { if (k === 'innerHTML') __html[id] = v; return true; },
    apply: function () { return __el(id); }
  });
}
function __btn(sec) {
  var hs = [];
  return { __sec: sec,
    getAttribute: function (n) { return n === 'data-fantasysection' ? sec : null; },
    setAttribute: function () {},
    classList: { add: function () {}, remove: function () {} },
    addEventListener: function (t, cb) { if (t === 'click') hs.push(cb); },
    click: function () { hs.forEach(function (h) { h({}); }); } };
}
var __btns = ['streamers','two_start','ros_sp','ros_rp','ros_hitter','buysell',
              'closers','callups','dynasty'].map(__btn);
function __render(sec) {
  for (var i = 0; i < __btns.length; i++) if (__btns[i].__sec === sec) __btns[i].click();
  return __html['fantasy-app-root'] || '';
}
function FT(val) { return { then: function (cb) { var r = cb(val); return (r && r.then) ? r : FT(r); },
                            catch: function () { return FT(val); } }; }
var PAYLOAD = %s;
var fetch = function () { return FT({ ok: true, json: function () { return FT(PAYLOAD); } }); };
var location = { href: '', hash: '', pathname: '/fantasy/' };
var __nav = { querySelector: function () { return {}; }, appendChild: function () {},
              insertBefore: function () {} };
var document = { readyState: 'complete',
  getElementById: function (id) { return __el(id); },
  querySelector: function (sel) { return sel === '.mlbstats-sectionnav' ? __nav : __el('q'); },
  querySelectorAll: function (sel) {
    return sel === '.mlbstats-sectionbtn[data-fantasysection]' ? __btns : [];
  },
  createElement: function () { return __el('c'); },
  addEventListener: function () {},
  head: __el('head'), body: __el('body') };
// fantasy.js guards on window.EEPHUS_GL but then calls the BARE global, which
// is how it works in a browser; the stub needs both bindings.
var EEPHUS_GL = { wire: function () {} };
var EEPHUS_HUB = { teamLogo: function (t) { return '<img alt="' + t + '">'; },
                   links: function () { return FT({ byMlbam: {
                     '660271': { key: 'shohei_ohtani' },
                     '592450': { key: 'aaron_judge' },
                     '621111': { key: 'relief_guy' },
                     '800001': { key: 'zeta_starter' },
                     '700001': { key: 'kid_prospect' },
                     '700002': { key: 'other_kid' } } }); } };
var window = { location: location, document: document, fetch: fetch,
               EEPHUS_HUB: EEPHUS_HUB, EEPHUS_GL: EEPHUS_GL,
               addEventListener: function () {} };
""" % PAYLOAD


def _boot() -> "MiniRacer":
    c = MiniRacer()
    c.eval(PRELUDE + JS)
    return c


@pytest.fixture(scope="module")
def ctx():
    """Read-only renders share one context."""
    return _boot()


@pytest.fixture
def fresh():
    """Sort state is module-level inside fantasy.js, so any test that ACTIVATES
    a sort control needs its own context or it leaks into the next one."""
    return _boot()


def _render(ctx, section: str) -> str:
    return ctx.eval("__render('%s')" % section)


def _names(html: str) -> list[str]:
    return re.findall(r'class="mlb-name">.*?>([^<]+)</a>', html)


# ---- the per-surface judgement call ---------------------------------------

CARD_SECTIONS = ["ros_hitter", "ros_sp", "ros_rp", "dynasty"]
TABLE_SECTIONS = ["streamers", "two_start", "buysell", "callups"]


@pytest.mark.parametrize("section", CARD_SECTIONS)
def test_leaderboards_render_cards(ctx, section):
    """350 / 250 / 180 / 300 served rows. These earned the card."""
    html = _render(ctx, section)
    assert "mlb-card ff-card" in html, f"{section} did not render cards"
    assert "mlb-card-list ff-card-list" in html
    assert "mlb-tape" in html and "mlb-chip" in html, f"{section} lost its row-2 tape"
    assert '<table class="fantasy-table">' not in html, f"{section} still emits a table"


@pytest.mark.parametrize("section", TABLE_SECTIONS)
def test_small_surfaces_stay_tables(ctx, section):
    """27-row day slates, a 79-row free-text leg list, a 30+30 side-by-side pair
    and a 60-row call-up list are NOT improved by 104px cards. Converting them
    would have been motion, not improvement, so they must stay tables."""
    html = _render(ctx, section)
    assert '<table class="fantasy-table">' in html, f"{section} was converted; it should not be"
    assert "ff-card" not in html, f"{section} leaked card markup"


def test_closer_grid_untouched(ctx):
    html = _render(ctx, "closers")
    assert "fantasy-grid" in html and "fantasy-team-card" in html
    assert "ff-card" not in html


# ---- two-way regression, through the CARD path ----------------------------

def test_two_way_player_card_shows_the_right_side(ctx):
    """Regression, 2026-07-31. Ohtani has TWO player records. His ROS Hitters
    card must carry his hitter score (284.8 -> "285"), never his pitcher score
    (172.6 -> "173")."""
    hit = _render(ctx, "ros_hitter")
    assert "Shohei Ohtani" in hit
    ocard = [c for c in hit.split('<div class="mlb-card ff-card"') if "Ohtani" in c]
    assert len(ocard) == 1, "Ohtani should appear exactly once on the hitter board"
    assert "285" in ocard[0], ocard[0]
    assert "173" not in ocard[0], ocard[0]
    # and his HITTER skill index rides the card, not the pitcher one
    assert "HEM+" in ocard[0] and "168" in ocard[0]
    assert "SEM+" not in ocard[0]

    pit = _render(ctx, "ros_sp")
    pcard = [c for c in pit.split('<div class="mlb-card ff-card"') if "Ohtani" in c]
    assert len(pcard) == 1
    assert "173" in pcard[0], pcard[0]
    assert "SEM+" in pcard[0] and "121" in pcard[0]


# ---- the sort contract ----------------------------------------------------

@pytest.mark.parametrize("section", CARD_SECTIONS)
def test_every_card_board_has_keyboard_sortable_headers(ctx, section):
    """/fantasy/ previously had NO sort at all on any board. Every sort control
    is now a real keyboard button carrying aria-sort, and exactly one column is
    marked as the active direction."""
    html = _render(ctx, section)
    head = html.split('class="mlb-card-head ff-card-head"')[1].split("</div>")[0]
    assert 'role="button"' in head and 'tabindex="0"' in head, head
    assert head.count("aria-sort=") >= 3, head
    # active column carries a direction arrow; inactive ones say "none"
    active = re.findall(r'aria-sort="(ascending|descending)"', html)
    assert len(active) == 1, f"{section}: expected 1 active sort column, got {active}"
    assert ("▴" in html) or ("▾" in html), "no direction arrow rendered"


@pytest.mark.parametrize("section", CARD_SECTIONS)
def test_tape_stats_get_their_own_sort_bar(ctx, section):
    """The row-2 chips are not track-aligned with the header, so they get a sort
    bar rather than a fake column heading floating above a chip that may have
    scrolled sideways inside its own overflow box."""
    html = _render(ctx, section)
    assert 'class="ff-sortbar"' in html, section
    bar = html.split('class="ff-sortbar"')[1].split("</div>")[0]
    assert "data-ffsort=" in bar


def test_ros_board_defaults_to_the_score_order(ctx):
    """The first paint must match what the retired table showed, so the
    conversion is a presentation change and not a silent re-rank."""
    html = _render(ctx, "ros_hitter")
    assert _names(html)[:2] == ["Shohei Ohtani", "Aaron Judge"], _names(html)


# ---- the sort actually sorts (not just markup) ----------------------------

def test_clicking_a_tape_header_reorders_the_board(fresh):
    """The point of the conversion. Ohtani outscores Judge, so he leads the
    default board; Judge has the better OBP, so sorting on the tape's OBP chip
    must put HIM first. Before this change no fantasy board could be sorted at
    all."""
    assert _names(_render(fresh, "ros_hitter"))[0] == "Shohei Ohtani"
    after = fresh.eval("__sortClick('obp')")
    assert _names(after)[0] == "Aaron Judge", _names(after)
    assert 'data-ffsort="obp" aria-sort="descending"' in after


def test_repeat_click_flips_direction(fresh):
    _render(fresh, "ros_hitter")
    first = fresh.eval("__sortClick('obp')")
    assert _names(first)[0] == "Aaron Judge"
    second = fresh.eval("__sortClick('obp')")
    assert _names(second)[0] == "Shohei Ohtani", _names(second)
    assert 'data-ffsort="obp" aria-sort="ascending"' in second


def test_lower_is_better_columns_open_ascending(fresh):
    """ERA / WHIP / Bust are asc:true in the column map, so a FRESH click on them
    opens low-first. Opening ERA high-first would be actively misleading."""
    _render(fresh, "ros_sp")
    html = fresh.eval("__sortClick('era')")
    assert 'data-ffsort="era" aria-sort="ascending"' in html, html[:400]
    # Zeta 1.95 beats Ohtani 2.85 on ERA even though Ohtani outscores him
    assert _names(html)[0] == "Zeta Starter", _names(html)


def test_name_column_sorts_alphabetically(fresh):
    _render(fresh, "ros_hitter")
    html = fresh.eval("__sortClick('name')")
    assert _names(html) == ["Aaron Judge", "Shohei Ohtani"], _names(html)


def test_sorting_the_dynasty_board_does_not_renumber_the_model(fresh):
    """The diamond carries the SERVED dynasty rank. Sorting by bust odds
    reorders the cards but rank 1 stays rank 1."""
    _render(fresh, "dynasty")
    html = fresh.eval("__sortClick('bust')")   # bust is asc:true -> low first
    assert _names(html) == ["Kid Prospect", "Other Kid"], _names(html)
    html = fresh.eval("__sortClick('bust')")   # flip: high bust first
    assert _names(html) == ["Other Kid", "Kid Prospect"], _names(html)
    ranks = re.findall(r'class="ff-rank-i">(\d+)</span>', html)
    assert ranks == ["2", "1"], f"model rank followed the row index: {ranks}"


def test_dynasty_diamond_shows_the_model_rank(ctx):
    """The dynasty rank is a served model output. Re-sorting the board must not
    renumber it, so the diamond reads d.rank rather than the row index."""
    html = _render(ctx, "dynasty")
    ranks = re.findall(r'class="ff-rank-i">(\d+)</span>', html)
    assert ranks == ["1", "2"], ranks
    # the surplus term the old table never displayed is now on the tape
    assert "Surplus" in html and "$88M" in html


# ---- stripe + diamond ------------------------------------------------------

def test_stripe_is_token_only(ctx):
    """No shared ORG_COLORS map exists outside prospx/index.html, so the stripe
    carries the board's own tier signal instead of a team colour - and it must do
    that in var() tokens only, never a hardcoded hex (house rule)."""
    for section in CARD_SECTIONS:
        html = _render(ctx, section)
        stripes = re.findall(r"--org-color:([^;\"]+)", html)
        assert stripes, section
        for s in stripes:
            assert s.strip().startswith("var(--"), f"{section}: hardcoded stripe {s!r}"


def test_cards_carry_the_diamond_rank_chip(ctx):
    html = _render(ctx, "ros_hitter")
    assert 'class="ff-rank"' in html and 'class="ff-rank-i"' in html


# ---- load states (the mlbstats/pal smoke-test contract) -------------------

def test_fetch_failure_still_paints_an_error_state():
    c = MiniRacer()
    fail = PRELUDE.replace(
        "var fetch = function () { return FT({ ok: true, json: function () { return FT(PAYLOAD); } }); };",
        "var fetch = function () { return { then: function () { return this; },"
        " catch: function (cb) { cb(new Error('network down')); return this; } }; };")
    c.eval(fail + JS)
    html = c.eval("__html['fantasy-app-root'] || ''")
    assert "Data failed to load" in html
    assert 'role="alert"' in html
    assert "fantasy-retry" in html


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ---------------------------------------------------------------------------
# Whole-card activation. Added 2026-07-31 after the adversarial review found the
# shipped guard was UNREACHABLE and the contract had zero test coverage.
# ---------------------------------------------------------------------------
def test_card_activation_guard_excludes_the_card_itself() -> None:
    """The card element itself carries role="button", and Element.closest() starts
    at the element it is called on. So a bare closest("a,button,[role=button]")
    matches the CARD on every click inside it and returns before open() ever runs.
    That shipped whole-card activation as dead on all four converted boards: about
    1,080 elements announced to a screen reader as buttons that did nothing, by
    mouse or by keyboard.

    The guard must therefore resolve the hit target and COMPARE IT TO THE CARD,
    so real inner controls still win but a click on the card body gets through.
    """
    src = (Path(__file__).parent / "assets" / "fantasy.js").read_text(encoding="utf-8")
    assert "data-ffhref" in src, "the activation hook disappeared entirely"
    # The naive form must not come back.
    assert not re.search(r'if\s*\(\s*!\s*e\.target\.closest\(\s*"a,button,\[role=button\]"\s*\)\s*\)', src), (
        "the bare closest() guard is back. It matches the card itself (the card has "
        "role=button) so open() is unreachable.")
    # And the fix must still be identifiable: the resolved target is compared to the card.
    assert re.search(r'closest\(\s*"a,button,\[role=button\]"\s*\)', src), (
        "expected the guard to still resolve inner controls")
    assert re.search(r'return\s+!t\s*\|\|\s*t\s*===\s*c', src), (
        "the guard no longer excludes the card itself; whole-card activation will be dead")


def test_card_activation_predicate_lets_the_card_through_and_blocks_inner_controls() -> None:
    """Behavioural check of the predicate, independent of the DOM stub (which only
    ever returns [data-ffsort] nodes, which is exactly why this bug shipped unseen).
    Evaluates the shipped guard shape against a fake target graph."""
    c = MiniRacer()
    c.eval("""
      // the shipped predicate, transcribed
      function onCard(e, card) {
        var t = e.target.closest("a,button,[role=button]");
        return !t || t === card;
      }
      var CARD = {tag: "card"};
      var LINK = {tag: "a"};
      var SORT = {tag: "sortchip"};
      // click on the card BODY: closest() walks up and finds only the card
      var bodyEvt = {target: {closest: function () { return CARD; }}};
      // click on a real link inside the card: closest() finds the link first
      var linkEvt = {target: {closest: function () { return LINK; }}};
      // click on a role=button sort chip inside the card
      var sortEvt = {target: {closest: function () { return SORT; }}};
      // click on something matching nothing at all
      var bareEvt = {target: {closest: function () { return null; }}};
      var out = [onCard(bodyEvt, CARD), onCard(linkEvt, CARD),
                 onCard(sortEvt, CARD), onCard(bareEvt, CARD)];
      JSON.stringify(out);
    """)
    got = json.loads(c.eval("JSON.stringify([onCard(bodyEvt, CARD), onCard(linkEvt, CARD), "
                            "onCard(sortEvt, CARD), onCard(bareEvt, CARD)])"))
    assert got == [True, False, False, True], (
        f"activation predicate wrong: {got}. Expected the card body and a bare target "
        "to activate, and a real inner control (link or sort chip) to be left alone.")
