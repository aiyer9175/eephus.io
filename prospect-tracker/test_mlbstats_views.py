# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /mlbstats/ column views and the column contract.

Owner ask 2026-09-11: eWAR on the MLB Stats boards, the most important stats
first, and a board that fits one screen with no sideways scroll. The answer is
one table per board with several named VIEWS of it (Standard, Skill, Value,
Leverage, Batting, Runs, All): every column still renders into the markup, and a
column outside the active view carries mlbstats-cv-off, which site.css hides
under the .mlbx page scope. That keeps the CSV export, the glossary wiring and
the py_mini_racer harness reading whole rows, so the smoke tests stay honest.

Two halves:
  1. Rendered (py_mini_racer, the smoke prelude): each board's DEFAULT view shows
     exactly its Standard columns in order; eWAR is visible on it; hidden cells
     never leak into an export; the deep-link keys (rcols / scols / hcols /
     dcols) read and write the way section 7 of the spec says.
  2. Static column contract: no column key or view id that a deep link can name
     is ever lost, `key` precedes `label` in every column object (the
     test_war_rate_plus detector depends on it), every registry key names a
     real column, and every glossary slug the page links resolves.

The Standard lists below are wave 1 of the overhaul. The Leverage, Defense and
team boards gain their eWAR columns with the exporter joins (wave 4); their
lists grow then, they never shrink. Hand-off to that wave (spec 9.3, the
owner's ask on six boards): extend STANDARD, PHONE and FROZEN_KEYS with `war`
(levbat, levsp, def) and `team_war` (relteam, spteam, hitteam), and turn the
generic "any eWAR column a board carries is visible" pin below into the explicit
per-board list.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import test_mlbstats_smoke as smoke

MiniRacer = smoke.MiniRacer
ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")

# ---------------------------------------------------------------- the Standard views
STANDARD = {
    "rel": ["name", "rem_plus", "rem_plus_3yr", "war", "war_ip_plus", "ip", "saves", "holds",
            "k_bb_pct", "era", "gmli", "riv_plus"],
    "sp": ["name", "sem_plus", "sem_plus_3yr", "war", "war_ip_plus", "ip", "gs", "ip_per_gs",
           "k_bb_pct", "era"],
    "hit": ["name", "hem_plus", "wrc_plus", "war", "war_pa_plus", "pa", "hr", "sb", "avg", "obp", "slg"],
    "def": ["name", "pos", "dem_plus", "dem_plus_3yr", "dem_plus_pos_pct", "fld_total", "def_runs",
            "inn", "hem_plus"],
    "levbat": ["name", "wpa", "pli", "clutch", "wpa_li", "pa"],
    "levsp": ["name", "wpa", "wpa_per_start", "wpa_li", "gs", "starts"],
    "relteam": ["team", "bullpen_plus", "leverage_deploy_plus", "n_above_avg", "high_lev_core_rem",
                "relief_ip", "team_wpa", "sd_md"],
    "spteam": ["team", "rotation_plus", "front_sem", "n_above_avg", "starter_ip", "total_gs"],
    "hitteam": ["team", "offense_plus", "heart_hem", "n_above_avg", "team_pa"],
    "defteam": ["team", "team_dem_plus", "n_above_avg", "team_fld_total", "team_frm_runs",
                "team_pos_runs", "team_pos_runs_fg", "team_inn"],
}
# The phone subset (640px and below) of each Standard view; the identity column
# and the sorted column always show as well.
PHONE = {
    "rel": ["rem_plus", "war", "ip", "saves", "era"],
    "sp": ["sem_plus", "war", "ip", "k_bb_pct", "era"],
    "hit": ["hem_plus", "wrc_plus", "war", "pa", "hr"],
    "def": ["pos", "dem_plus", "fld_total", "inn"],
}


def _render_bullpen(hash_: str) -> str:
    return smoke._render(hash_)


# (board, render function, hash) for each board's default render.
DEFAULT_RENDERS = {
    "rel": (_render_bullpen, ""),
    "relteam": (_render_bullpen, "#view=teams"),
    "sp": (smoke._render_starters, "#section=starters"),
    "spteam": (smoke._render_starters, "#section=starters&sview=teams"),
    "hit": (smoke._render_hitters, "#section=hitters"),
    "hitteam": (smoke._render_hitters, "#section=hitters&hview=teams"),
    "levbat": (smoke._render_leverage, "#section=leverage"),
    "levsp": (smoke._render_leverage, "#section=leverage&lview=starters"),
    "def": (smoke._render_defense, "#section=defense"),
    "defteam": (smoke._render_defense, "#section=defense&dview=teams"),
}


def _table(html: str) -> str:
    i = html.index('<table class="mlbstats-table')
    return html[i:html.index("</table>", i)]


def _heads(html: str) -> list[tuple[str, str, str]]:
    """[(class list, data-col, whole tag)] for every header of the first board table."""
    head = _table(html).split("<thead>")[1].split("</thead>")[0]
    return [(m.group(1), m.group(2), m.group(0))
            for m in re.finditer(r'<th class="([^"]*)"[^>]*?data-col="([^"]+)"[^>]*>', head)]


def _visible(html: str) -> list[str]:
    return [k for cls, k, _ in _heads(html) if "mlbstats-cv-off" not in cls.split()]


def _cls(html: str, key: str) -> list[str]:
    for cls, k, _ in _heads(html):
        if k == key:
            return cls.split()
    raise AssertionError("no header for " + key)


# ---------------------------------------------------------------- rendered
@pytest.mark.parametrize("board", sorted(DEFAULT_RENDERS))
def test_default_render_shows_exactly_the_standard_columns_in_order(board):
    fn, hash_ = DEFAULT_RENDERS[board]
    html = fn(hash_)
    assert _visible(html) == STANDARD[board], (board, _visible(html))
    assert "undefined" not in html and "NaN" not in html


@pytest.mark.parametrize("board", ["rel", "sp", "hit"])
def test_ewar_is_the_third_column_on_the_pitcher_and_hitter_boards(board):
    """The owner's ask, pinned: eWAR is on the board a reader opens, right after
    the index pair, not in 9th to 12th place behind the WAR rates."""
    fn, hash_ = DEFAULT_RENDERS[board]
    vis = _visible(fn(hash_))
    assert vis.index("war") == 3, vis


@pytest.mark.parametrize("board", sorted(DEFAULT_RENDERS))
def test_any_ewar_column_a_board_carries_is_visible_on_its_standard_view(board):
    """Generic half of the same pin: once a board has an eWAR column (war or
    team_war) at all, its Standard view shows it."""
    fn, hash_ = DEFAULT_RENDERS[board]
    html = fn(hash_)
    for key in ("war", "team_war"):
        if ('data-col="%s"' % key) in _table(html):
            assert key in _visible(html), (board, key)


@pytest.mark.parametrize("board", sorted(DEFAULT_RENDERS))
def test_hidden_cells_never_reach_an_export_and_headers_keep_their_case(board):
    fn, hash_ = DEFAULT_RENDERS[board]
    html = fn(hash_)
    table = _table(html)
    for cls, key, tag in _heads(html):
        m = re.search(r'data-export-text="([^"]*)"', tag)
        assert m and m.group(1), ("no data-export-text", board, key)
        off = "mlbstats-cv-off" in cls.split()
        assert ("data-export-skip" in tag) == off, (board, key, tag)
    for m in re.finditer(r"<td([^>]*)>", table):
        attrs = m.group(1)
        off = re.search(r'class="[^"]*\bmlbstats-cv-off\b', attrs) is not None
        assert ("data-export-skip" in attrs) == off, (board, attrs)


def test_export_text_keeps_the_case_coded_labels():
    heads = {k: tag for _, k, tag in _heads(_render_bullpen(""))}
    assert 'data-export-text="eWAR"' in heads["war"]
    assert 'data-export-text="gmLI"' in heads["gmli"]
    assert 'data-export-text="xREM+"' in heads["xrem_plus"]
    assert 'data-export-text="REM+ 3yr"' in heads["rem_plus_3yr"]


def test_phone_subset_and_group_rules_on_the_reliever_standard_view():
    html = _render_bullpen("")
    for key in STANDARD["rel"][1:]:
        wide = "mlbstats-cv-wide" in _cls(html, key)
        assert wide == (key not in PHONE["rel"]), key
    assert "mlbstats-cv-wide" not in _cls(html, "name")
    grp = [k for cls, k, _ in _heads(html) if "mlbstats-cv-grp" in cls.split()]
    assert grp == ["war", "ip", "k_bb_pct", "gmli"], grp


@pytest.mark.parametrize("board,hash_,fn", [
    ("rel", "", _render_bullpen),
    ("sp", "#section=starters", smoke._render_starters),
    ("hit", "#section=hitters", smoke._render_hitters),
    ("def", "#section=defense", smoke._render_defense),
])
def test_multi_view_boards_carry_the_columns_strip(board, hash_, fn):
    html = fn(hash_)
    assert 'aria-label="Columns"' in html
    assert ('data-colview="%s:standard" aria-pressed="true"' % board) in html
    assert ('data-colview="%s:all"' % board) in html
    assert "mlbstats-toolrow" in html


@pytest.mark.parametrize("hash_,fn", [
    ("#section=leverage", smoke._render_leverage),
    ("#view=teams", _render_bullpen),
    ("#section=defense&dview=teams", smoke._render_defense),
])
def test_single_view_boards_carry_no_strip(hash_, fn):
    assert "data-colview" not in fn(hash_)


def test_rcols_skill_shows_skill_fip_and_hides_ewar():
    vis = _visible(_render_bullpen("#section=bullpen&rcols=skill"))
    assert vis == ["name", "rem_plus", "xrem_plus", "luck", "k_pct", "bb_pct", "k_bb_pct",
                   "swstr_pct", "fip", "era", "ip"], vis
    assert "war" not in vis


def test_an_old_sort_link_pins_its_column_onto_the_view():
    """rsort=k_pct.d predates the views: it still shows K%, after the view's own
    columns, sorted, with a group rule, and on a phone too."""
    html = _render_bullpen("#section=bullpen&rsort=k_pct.d")
    vis = _visible(html)
    assert vis == STANDARD["rel"] + ["k_pct"], vis
    cls = _cls(html, "k_pct")
    assert "is-sorted" in cls and "mlbstats-cv-grp" in cls and "mlbstats-cv-wide" not in cls


def test_an_unknown_view_id_falls_back_to_standard():
    assert _visible(_render_bullpen("#section=bullpen&rcols=bogus")) == STANDARD["rel"]


# A view that lacks the board's sort column gets it pinned at the end (the
# defaults: REM+, SEM+, HEM+, DEM+).
@pytest.mark.parametrize("hash_,fn,board,want", [
    ("#section=starters&scols=value", smoke._render_starters, "sp",
     ["name", "war", "war_ip_plus", "war_ip_plus_adj", "war_ip_plus_3yr", "sem_plus", "ip", "gs", "ip_per_gs"]),
    ("#section=hitters&hcols=batting", smoke._render_hitters, "hit",
     ["name", "pa", "hr", "sb", "avg", "obp", "slg", "ops", "iso", "woba_raw", "bb_pct", "k_pct", "hem_plus"]),
    ("#section=hitters&hcols=skill", smoke._render_hitters, "hit",
     ["name", "hem_plus", "hem_plus_3yr", "xhem_plus", "fwdhem_plus", "luck_gap", "pwoba", "woba_raw",
      "bb_pct", "k_pct", "babip"]),
    ("#section=defense&dcols=runs", smoke._render_defense, "def",
     ["name", "pos", "fld_total", "fld_runs", "frm_runs", "pos_runs", "pos_runs_fg", "def_runs",
      "rate_1000_shrunk", "inn", "dem_plus"]),
    ("#section=bullpen&rcols=leverage", _render_bullpen, "rel",
     ["name", "gmli", "gmli_3yr", "saves", "holds", "sd_md", "riv_plus", "wpa", "wpa_li", "g", "ip",
      "rem_plus"]),
    ("#section=bullpen&rcols=value", _render_bullpen, "rel",
     ["name", "war", "war_ip_plus", "war_ip_plus_adj", "war_ip_plus_3yr", "rem_plus", "riv_plus", "wpa", "ip"]),
])
def test_each_deep_linked_view_shows_its_columns(hash_, fn, board, want):
    html = fn(hash_)
    assert _visible(html) == want, _visible(html)
    view = re.search(r"[sdhr]cols=([a-z]+)", hash_).group(1)
    assert ('data-colview="%s:%s" aria-pressed="true"' % (board, view)) in html


def test_wrc_plus_sits_right_after_hem_plus_in_every_view_that_shows_both():
    """House rule 1, on the default sort AND on a link sorted on either column:
    a wRC+ sort on Skill (which lacks wRC+) pins it beside HEM+, never after
    BABIP; a HEM+ sort on Batting pins HEM+ last and shows no wRC+ at all."""
    for view in ("standard", "skill", "value", "batting", "all"):
        for sort in ("", "&hsort=wrc_plus.d", "&hsort=hem_plus.a", "&hsort=ops.d"):
            vis = _visible(smoke._render_hitters("#section=hitters&hcols=" + view + sort))
            if "hem_plus" in vis and "wrc_plus" in vis:
                assert vis.index("wrc_plus") == vis.index("hem_plus") + 1, (view, sort, vis)
    html = smoke._render_hitters("#section=hitters&hcols=skill&hsort=wrc_plus.d")
    vis = _visible(html)
    assert vis[:3] == ["name", "hem_plus", "wrc_plus"] and vis[-1] == "babip", vis
    cls = _cls(html, "wrc_plus")
    assert "is-sorted" in cls and "mlbstats-cv-grp" not in cls, cls  # joined HEM+, no rule
    vis = _visible(smoke._render_hitters("#section=hitters&hcols=batting&hsort=hem_plus.a"))
    assert vis[-1] == "hem_plus" and "wrc_plus" not in vis, vis


@pytest.mark.parametrize("hash_,fn,n", [
    ("#section=bullpen&rcols=all", _render_bullpen, 25),
    ("#section=starters&scols=all", smoke._render_starters, 19),
    ("#section=hitters&hcols=all", smoke._render_hitters, 25),
    ("#section=defense&dcols=all", smoke._render_defense, 16),
])
def test_the_all_view_shows_every_column_and_wraps_only_spaced_headers(hash_, fn, n):
    html = fn(hash_)
    assert '<table class="mlbstats-table mlbstats-cv-all">' in html
    heads = _heads(html)
    assert len(heads) == n and len(_visible(html)) == n
    assert "mlbstats-cv-off" not in _table(html) and "mlbstats-cv-wide" not in _table(html)
    for cls, key, tag in heads:
        label = re.search(r'data-export-text="([^"]*)"', tag).group(1)
        assert ("mlbstats-nw" in cls.split()) == (" " not in label), (key, label)


def test_the_all_pill_says_it_may_scroll():
    html = _render_bullpen("")
    m = re.search(r'<button[^>]*data-colview="rel:all"[^>]*>', html)
    assert m and 'title="' in m.group(0), "the All pill must say it can scroll on a narrow screen"


def test_history_boards_reuse_the_live_views_and_skip_missing_keys():
    html = smoke._render_defense("#section=defense&dseason=2025")
    assert _visible(html) == ["name", "pos", "dem_plus", "fld_total", "def_runs", "inn"]
    assert 'data-colview="def:standard"' in html          # the strip does not jump


def test_the_relabelled_and_new_columns():
    rel = _render_bullpen("")
    assert ">SV<" in rel and ">HLD<" in rel
    body = _table(rel).split("<tbody>")[1]
    assert re.search(r"<td[^>]*>20</td>", body), "Closer Alpha's 20 saves"
    assert "Luck (wOBA)" in rel
    assert "Luck (wOBA)" in smoke._render_starters("#section=starters")
    hit = smoke._render_hitters("#section=hitters&hcols=all")
    heads = {k: tag for _, k, tag in _heads(hit)}
    assert 'data-export-text="wOBA"' in heads["woba_raw"] and 'data-gl="woba"' in hit
    assert 'data-export-text="Shrunk wOBA"' in heads["woba"]
    assert 'data-export-text="Luck (pts)"' in heads["luck_gap"]
    assert ">.365<" in hit                                 # the recorded wOBA, served
    lev = smoke._render_leverage("#section=leverage&lview=starters")
    lheads = {k: tag for _, k, tag in _heads(lev)}
    assert 'data-export-text="GS"' in lheads["gs"] and 'data-export-text="Starts"' in lheads["starts"]


@pytest.mark.parametrize("hash_,fn,keys", [
    ("#section=bullpen&rcols=all", _render_bullpen, ["k_pct", "bb_pct", "k_bb_pct", "era"]),
    ("#section=starters&scols=all", smoke._render_starters, ["k_pct", "bb_pct", "k_bb_pct", "era"]),
    ("#section=hitters&hcols=all", smoke._render_hitters, ["avg", "obp", "slg", "ops", "iso", "babip"]),
    ("#section=defense&dcols=all", smoke._render_defense, ["def_runs"]),
])
def test_context_columns_link_their_glossary_entries(hash_, fn, keys):
    head = _table(fn(hash_)).split("</thead>")[0]
    for key in keys:
        th = head.split('data-col="%s"' % key)[1].split("</th>")[0]
        assert 'data-gl="%s"' % key in th, key


# ---- click-driven: the strip writes the hash and re-renders in place --------
_CLICK_STUB = r"""
var __listeners = {}, __hashes = [];
history.replaceState = function (a, b, u) { __hashes.push(String(u)); };
function __el(id) { return new Proxy(function () { return __el(id); }, {
  get: function (t, k) {
    if (k === 'innerHTML') return __html[id] || '';
    if (k === 'classList') return {add: function () {}, remove: function () {}, toggle: function () {},
                                   contains: function () { return false; }};
    if (k === 'querySelectorAll') return function (sel) {
      var am = /^\[data-([a-z]+)\]$/.exec(sel);
      if (!am) return [];
      var out = [], re = new RegExp('data-' + am[1] + '="([^"]*)"', 'g'), m, h = __html[id] || '';
      while ((m = re.exec(h))) { (function (v) {
        // A stub element that answers its own attribute and captures its
        // click; everything else falls through to the generic element.
        var name = (am[1] === 'colview') ? v : am[1] + ':' + v, base = __el(id + ':' + name);
        out.push(new Proxy(function () {}, { get: function (t, k) {
          if (k === 'id') return '';
          if (k === 'getAttribute') return function (a) { return (a === 'data-' + am[1]) ? v : null; };
          if (k === 'addEventListener') return function (ev, fn) { if (ev === 'click') __listeners[name] = fn; };
          return base[k];
        }, set: function () { return true; }, apply: function () { return base; } })); })(m[1]); }
      return out;
    };
    if (k === 'getAttribute') return function () { return null; };
    if (k === 'setAttribute' || k === 'addEventListener' || k === 'removeEventListener' || k === 'focus'
        || k === 'setSelectionRange') return function () {};
    if (k === 'querySelector' || k === 'closest') return function () { return __el(id + 'q'); };
    if (k === 'value' || k === 'textContent') return ''; if (k === 'checked') return true;
    if (k === 'selectionStart') return 0;
    return __el(id);
  },
  set: function (t, k, v) { if (k === 'innerHTML') __html[id] = v; return true; },
  apply: function () { return __el(id); } }); }
function __click(v) { if (!__listeners[v]) throw new Error('no button ' + v); __listeners[v](); }
"""
# A reader who remembered the All view on Relievers (localStorage).
_REMEMBER_ALL = "window.localStorage = { getItem: function (k) { return k === 'mlbstats.cols.rel' ? 'all' : null; },"                 " setItem: function () {} };"


def _clicker(hash_: str, prelude=None, extra: str = ""):
    ctx = MiniRacer()
    ctx.eval((prelude or smoke._prelude)(hash_) + _CLICK_STUB + extra + JS)
    return ctx


def test_a_strip_click_rerenders_and_writes_the_hash_and_standard_is_omitted():
    ctx = _clicker("#section=bullpen")
    ctx.eval("__click('rel:skill')")
    html = ctx.eval("__html['mlbstats-app-root']")
    assert "fip" in _visible(html) and "war" not in _visible(html)
    assert ctx.eval("__hashes[__hashes.length - 1]") == "#section=bullpen&rcols=skill"
    ctx.eval("__click('rel:standard')")
    assert _visible(ctx.eval("__html['mlbstats-app-root']")) == STANDARD["rel"]
    last = ctx.eval("__hashes[__hashes.length - 1]")
    assert "rcols" not in last and last == "#section=bullpen", last


def test_a_deep_linked_view_survives_the_next_hash_write():
    ctx = _clicker("#section=bullpen&rcols=value&rsort=k_pct.d")
    ctx.eval("__click('rel:value')")
    last = ctx.eval("__hashes[__hashes.length - 1]")
    assert "rcols=value" in last and "rsort=k_pct.d" in last, last


def test_a_bare_url_stays_bare_when_nothing_is_remembered():
    ctx = _clicker("")
    assert ctx.eval("__hashes.length") == 0
    assert _visible(ctx.eval("__html['mlbstats-app-root']")) == STANDARD["rel"]


def test_a_remembered_view_reopens_and_the_url_says_so_before_any_click():
    """Spec 7 / risk 7: a stored All reopens on All and the URL then says
    rcols=all, so a link copied right after the reload opens the same view."""
    ctx = _clicker("", extra=_REMEMBER_ALL)
    assert '<table class="mlbstats-table mlbstats-cv-all">' in ctx.eval("__html['mlbstats-app-root']")
    assert ctx.eval("__hashes[__hashes.length - 1]") == "#section=bullpen&rcols=all"


def test_the_hash_outranks_the_remembered_view():
    ctx = _clicker("#section=bullpen&rcols=skill", extra=_REMEMBER_ALL)
    vis = _visible(ctx.eval("__html['mlbstats-app-root']"))
    assert "fip" in vis and "war" not in vis and "mlbstats-cv-all" not in ctx.eval("__html['mlbstats-app-root']")
    assert ctx.eval("__hashes[__hashes.length - 1]") == "#section=bullpen&rcols=skill"


def test_the_catcher_chip_alone_adds_frm_to_the_defense_standard_view():
    """Spec 4.5: with only the C chip active, Standard inserts Frm right after
    Fld; a second chip (or Runs, which already carries Frm) leaves the list."""
    ctx = _clicker("#section=defense", prelude=smoke._defense_prelude)
    root = "__html['mlbstats-defense-root']"
    assert _visible(ctx.eval(root)) == STANDARD["def"]
    ctx.eval("__click('mlbpos:C')")
    vis = _visible(ctx.eval(root))
    want = list(STANDARD["def"])
    want.insert(want.index("fld_total") + 1, "frm_runs")
    assert vis == want, vis
    assert "mlbstats-cv-wide" in _cls(ctx.eval(root), "frm_runs")   # not in the phone subset
    other = [v for v in re.findall(r'data-mlbpos="([A-Z0-9]+)"', ctx.eval(root)) if v != "C"][0]
    ctx.eval("__click('mlbpos:%s')" % other)
    assert _visible(ctx.eval(root)) == STANDARD["def"], _visible(ctx.eval(root))
    ctx.eval("__click('mlbpos:%s')" % other)                          # C alone again
    ctx.eval("__click('def:runs')")
    vis = _visible(ctx.eval(root))
    assert vis.count("frm_runs") == 1 and vis[:5] == ["name", "pos", "fld_total", "fld_runs", "frm_runs"], vis


# ---------------------------------------------------------------- static column contract
# Every column key a deep link can sort on today (plus the keys this overhaul
# added). A key may be relabelled (woba, starts) but never renamed or removed.
FROZEN_KEYS = {
    "REL_COLS": ["name", "rem_plus", "rem_plus_3yr", "xrem_plus", "luck", "war_ip_plus", "war_ip_plus_adj",
                 "war_ip_plus_3yr", "war", "ip", "g", "saves", "holds", "k_pct", "bb_pct", "k_bb_pct", "fip",
                 "swstr_pct", "era", "gmli", "gmli_3yr", "riv_plus", "wpa", "wpa_li", "sd_md"],
    "TEAM_COLS": ["team", "bullpen_plus", "leverage_deploy_plus", "n_above_avg", "high_lev_core_rem",
                  "relief_ip", "team_wpa", "sd_md"],
    "STARTER_COLS": ["name", "sem_plus", "sem_plus_3yr", "xsem_plus", "luck", "war_ip_plus", "war_ip_plus_adj",
                     "war_ip_plus_3yr", "war", "ip", "gs", "ip_per_gs", "k_pct", "bb_pct", "k_bb_pct", "gb_pct",
                     "fip", "era", "hr9"],
    "STARTER_TEAM_COLS": ["team", "rotation_plus", "front_sem", "n_above_avg", "starter_ip", "total_gs"],
    "HITTER_COLS": ["name", "hem_plus", "wrc_plus", "hem_plus_3yr", "xhem_plus", "fwdhem_plus", "pwoba",
                    "luck_gap", "war_pa_plus", "war_pa_plus_adj", "war_pa_plus_3yr", "war", "pa", "hr", "sb",
                    "avg", "obp", "slg", "ops", "iso", "woba_raw", "woba", "bb_pct", "k_pct", "babip"],
    "HITTER_TEAM_COLS": ["team", "offense_plus", "heart_hem", "n_above_avg", "team_pa"],
    "BAT_LEV_COLS": ["name", "wpa", "pli", "clutch", "wpa_li", "pa"],
    "STARTER_LEV_COLS": ["name", "wpa", "wpa_per_start", "wpa_li", "gs", "starts"],
    "DEFENSE_COLS": ["name", "pos", "dem_plus", "dem_plus_3yr", "dem_plus_pos_pct", "fld_total", "fld_runs",
                     "frm_runs", "pos_runs", "pos_runs_fg", "def_runs", "rate_1000", "rate_1000_shrunk", "inn",
                     "fld_pct", "hem_plus"],
    "DEFENSE_TEAM_COLS": ["team", "team_dem_plus", "n_above_avg", "team_fld_total", "team_frm_runs",
                          "team_pos_runs", "team_pos_runs_fg", "team_inn"],
}
# The table each view-registry board renders.
BOARD_ARRAYS = {"rel": "REL_COLS", "sp": "STARTER_COLS", "hit": "HITTER_COLS", "def": "DEFENSE_COLS",
                "levbat": "BAT_LEV_COLS", "levsp": "STARTER_LEV_COLS", "relteam": "TEAM_COLS",
                "spteam": "STARTER_TEAM_COLS", "hitteam": "HITTER_TEAM_COLS", "defteam": "DEFENSE_TEAM_COLS"}
# The view ids a deep link can name (rcols= / scols= / hcols= / dcols=).
FROZEN_VIEWS = {"rel": ["standard", "skill", "value", "leverage", "all"],
                "sp": ["standard", "skill", "value", "all"],
                "hit": ["standard", "skill", "value", "batting", "all"],
                "def": ["standard", "runs", "all"]}


def _array_block(name: str) -> str:
    m = re.search(r"\n  var %s = \[\n(.*?)\n  \];" % re.escape(name), JS.replace("\r\n", "\n"), re.S)
    assert m, "column array %s not found" % name
    return m.group(1)


def _array_keys(name: str) -> list[str]:
    return re.findall(r'^    \{ key: "([a-z0-9_]+)"', _array_block(name), re.M)


def _registry() -> dict:
    src = JS.replace("\r\n", "\n")
    m = re.search(r"\n  var COL_VIEWS = \{\n(.*?)\n  \};", src, re.S)
    assert m, "COL_VIEWS not found"
    body = m.group(1)
    starts = [(mm.group(1), mm.start()) for mm in re.finditer(r"^    ([a-z]+): \[", body, re.M)]
    out = {}
    for i, (board, at) in enumerate(starts):
        seg = body[at:starts[i + 1][1] if i + 1 < len(starts) else len(body)]
        views = []
        for vm in re.finditer(r'\{ id: "([a-z]+)", label: "([^"]+)"(.*?)(?=\{ id: "|\Z)', seg, re.S):
            rest = vm.group(3)
            lists = {}
            for fld in ("keys", "phone"):
                lm = re.search(fld + r": (null|\[(.*?)\])", rest, re.S)
                assert lm, (board, vm.group(1), fld)
                lists[fld] = None if lm.group(1) == "null" else re.findall(r'"([^"]+)"', lm.group(2))
            lists["extra"] = re.findall(r'after: "([a-z0-9_]+)", key: "([a-z0-9_]+)"', rest)
            views.append((vm.group(1), lists))
        out[board] = views
    return out


@pytest.mark.parametrize("array", sorted(FROZEN_KEYS))
def test_no_deep_linkable_column_key_is_ever_lost(array):
    missing = set(FROZEN_KEYS[array]) - set(_array_keys(array))
    assert not missing, (array, sorted(missing))


@pytest.mark.parametrize("array", sorted(FROZEN_KEYS))
def test_key_precedes_label_in_every_column_object(array):
    block = _array_block(array)
    objs = re.findall(r"^    \{ ([^\n]*)", block, re.M)
    assert objs, array
    for o in objs:
        assert re.match(r'key: "[a-z0-9_]+", label: "', o), (array, o[:80])


def test_every_registry_board_maps_to_a_table_and_every_key_names_a_real_column():
    reg = _registry()
    assert set(reg) == set(BOARD_ARRAYS), "a board without a table (or a table without a view registry)"
    for board, views in reg.items():
        cols = set(_array_keys(BOARD_ARRAYS[board]))
        ids = [v for v, _ in views]
        assert ids[0] == "standard" and len(ids) == len(set(ids)), (board, ids)
        for vid, lists in views:
            for fld in ("keys", "phone"):
                for k in lists[fld] or []:
                    assert k == "|" or k in cols, (board, vid, fld, k)
            for after, key in lists["extra"]:
                assert after in cols and key in cols, (board, vid, after, key)


def test_no_deep_linkable_view_id_is_ever_lost():
    reg = _registry()
    for board, want in FROZEN_VIEWS.items():
        have = [v for v, _ in reg[board]]
        assert set(want) <= set(have), (board, have)
    hashkeys = dict(re.findall(r'(\w+): "([a-z]cols)"', re.search(r"var COL_VIEW_HASH = \{([^}]*)\}", JS).group(1)))
    assert hashkeys == {"rel": "rcols", "sp": "scols", "hit": "hcols", "def": "dcols"}


def _render_calls() -> list[str]:
    """The argument list of every renderTable( call (the definition excluded)."""
    out, i = [], 0
    while True:
        i = JS.find("renderTable(", i)
        if i < 0:
            return out
        j, depth = i + len("renderTable("), 1
        while depth:
            depth += {"(": 1, ")": -1}.get(JS[j], 0)
            j += 1
        if JS[max(0, i - 9):i] != "function ":
            out.append(JS[i + len("renderTable("):j - 1])
        i = j


def test_every_render_call_names_a_registry_board():
    reg = _registry()
    calls = _render_calls()
    assert len(calls) >= 13, len(calls)
    for c in calls:
        args = c.split(", ", 4)
        assert len(args) == 5, ("a renderTable call without a board id", c)
        boards = re.findall(r'(?:^|[?:])\s*"([a-z]+)"', args[4])
        assert boards and all(b in reg for b in boards), c


def _glossary_ids() -> set[str]:
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    return {e["id"] for e in g["entries"]}


def test_every_glossary_slug_the_page_links_resolves():
    pats = [r'term:\s*"([a-z0-9_]+)"', r'data-gl="([a-z0-9_]+)"',
            r'gloss\("(?:[^"\\]|\\.)*",\s*"([a-z0-9_]+)"\)', r'explainer\("([a-z0-9_]+)"']
    slugs = set()
    for p in pats:
        slugs |= set(re.findall(p, JS))
    assert len(slugs) >= 50, len(slugs)
    missing = sorted(slugs - _glossary_ids())
    assert not missing, missing


def test_the_ewar_entry_is_listed_under_mlbstats():
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    ewar = [e for e in g["entries"] if e["id"] == "ewar"]
    assert ewar and "mlbstats" in ewar[0]["module"]
