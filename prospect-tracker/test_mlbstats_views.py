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

Three parts:
  1. Rendered (py_mini_racer, the smoke prelude): each board's DEFAULT view shows
     exactly its Standard columns in order; eWAR is visible on it; hidden cells
     never leak into an export; the deep-link keys (rcols / scols / hcols /
     dcols) read and write the way section 7 of the spec says.
  2. Static column contract: no column key or view id that a deep link can name
     is ever lost, `key` precedes `label` in every column object (the
     test_war_rate_plus detector depends on it), every registry key names a
     real column, and every glossary slug the page links resolves.
  3. The vertical budget (wave 2): the methodology fold opens closed at every
     width with a reader's own choice still outranking that default, the Team
     note is one line, every filter bar is the phone drawer, and the shell opts
     every section root into the CSV control.
  4. The eWAR section (wave 5) and the shared team filter (wave 7): the sixth
     board renders both of its views off its own payload, sums nothing itself,
     names both club bases, and reads as "being computed" rather than as an
     error before war_board_export.py has written anything; #team= is one key
     for every board, and the club it cannot fill says so with a Clear.

The Standard lists below carry waves 1, 4 and 6 of the overhaul: eWAR is on
every player board and on the three club rollups (EWAR_ON is the explicit
per-board pin the owner's ask earned). Team Defense is the one board pinned
WITHOUT eWAR: a whole-player number on a fielding rollup would repeat the
lineup total on another frame.

Wave 3 is the GFX cards: each one leads with its board's index and then eWAR,
pinned here as a static read of the spec builder rather than a picture diff.

The payload fields behind waves 4 and 6 come from the exporters (spec E3 to E6).
On a LIVE board, until those land, the column renders the ABSENT token for every
row, which is what the blank-never-zero pins below hold: a blank column is
correct, a column of zeros would be a fabricated number. A HISTORY board is the
other way round, as it has always been: a key no season carries drops out
(coveredCols) rather than serving an empty column, and comes back by itself once
the rebuilt payload carries it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import test_mlbstats_smoke as smoke

MiniRacer = smoke.MiniRacer
ROOT = Path(__file__).parent
# The value ruler (assets/eephus-tiers.js) owns every colour cut and the board
# file calls it, so this harness evaluates it first - the page does the same with
# a head tag right after the nav script, where deferred scripts run in order.
TIERS_JS = (ROOT / "assets" / "eephus-tiers.js").read_text(encoding="utf-8")
JS = TIERS_JS + (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")

# ---------------------------------------------------------------- the Standard views
STANDARD = {
    "rel": ["name", "rem_plus", "rem_plus_3yr", "war", "war_ip_plus", "ip", "saves", "holds",
            "k_bb_pct", "era", "gmli", "riv_plus"],
    "sp": ["name", "sem_plus", "sem_plus_3yr", "war", "war_ip_plus", "ip", "gs", "ip_per_gs",
           "k_bb_pct", "era"],
    "hit": ["name", "hem_plus", "wrc_plus", "war", "war_pa_plus", "pa", "hr", "sb", "avg", "obp", "slg"],
    "def": ["name", "pos", "dem_plus", "dem_plus_3yr", "dem_plus_pos_pct", "fld_total", "def_runs",
            "inn", "hem_plus", "war"],
    "levbat": ["name", "wpa", "pli", "clutch", "wpa_li", "war", "pa"],
    "levsp": ["name", "wpa", "wpa_per_start", "wpa_li", "war", "gs", "starts"],
    "relteam": ["team", "bullpen_plus", "team_war", "leverage_deploy_plus", "n_above_avg",
                "high_lev_core_rem", "relief_ip", "team_wpa", "sd_md"],
    "spteam": ["team", "rotation_plus", "team_war", "front_sem", "n_above_avg", "starter_ip", "total_gs"],
    "hitteam": ["team", "offense_plus", "team_war", "heart_hem", "n_above_avg", "team_pa"],
    "defteam": ["team", "team_dem_plus", "n_above_avg", "team_fld_total", "team_frm_runs",
                "team_pos_runs", "team_pos_runs_fg", "team_inn"],
}
# The phone subset (640px and below) of each Standard view; the identity column
# and the sorted column always show as well.
PHONE = {
    "rel": ["rem_plus", "war", "ip", "saves", "era"],
    "sp": ["sem_plus", "war", "ip", "k_bb_pct", "era"],
    "hit": ["hem_plus", "wrc_plus", "war", "pa", "hr"],
    # Defense is the one Standard view whose phone subset has no eWAR: at 640px
    # and below the board keeps the four fielding columns a reader opened it
    # for (spec 4.5). test_mlbstats_fit.py carries the same exception, so the
    # two files cannot drift apart.
    "def": ["pos", "dem_plus", "fld_total", "inn"],
    "levbat": ["wpa", "wpa_li", "war", "pa"],
    "levsp": ["wpa", "wpa_per_start", "war", "gs"],
    "relteam": ["bullpen_plus", "team_war", "high_lev_core_rem", "relief_ip"],
    "spteam": ["rotation_plus", "team_war", "front_sem", "starter_ip"],
    "hitteam": ["offense_plus", "team_war", "heart_hem", "team_pa"],
    "defteam": ["team_dem_plus", "n_above_avg", "team_fld_total", "team_inn"],
}
# The eWAR column each board carries, and its payload key. Team Defense is
# absent on purpose (spec 4.5), and that absence is pinned too.
EWAR_ON = {"rel": "war", "sp": "war", "hit": "war", "def": "war", "levbat": "war", "levsp": "war",
           "relteam": "team_war", "spteam": "team_war", "hitteam": "team_war"}
# Where each payload keeps the rows a board renders, so a test can stamp or
# strip one field and re-render.
ROWS_KEY = {"rel": "relievers", "sp": "starters", "hit": "hitters", "def": "fielders",
            "levbat": "batters", "levsp": "starters", "relteam": "teams", "spteam": "teams",
            "hitteam": "teams", "defteam": "teams"}


def _render_bullpen(hash_: str) -> str:
    return smoke._render(hash_)


# The sentence defense_export builds from data/ewar.json meta (spec E4). The
# page never types a frame; it reads this one out of the payload.
EWAR_NOTE = ("Its fielding is Baseball-Reference rfield (fielding_blend_w 0.0), a different frame"
             " from Fld and DEM+.")

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


def _cells(html: str, key: str) -> list[str]:
    """Every rendered value in one column, in row order (the row number is CSS
    generated content and never appears here)."""
    i = [k for _, k, _ in _heads(html)].index(key)
    body = _table(html).split("<tbody>")[1]
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        assert len(tds) > i, (key, len(tds))
        out.append(tds[i])
    return out


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


@pytest.mark.parametrize("board", sorted(EWAR_ON))
def test_every_board_the_owner_asked_for_opens_showing_its_ewar(board):
    """The ask, board by board (waves 1 and 4): six player boards and three club
    rollups show eWAR on the view a reader lands on, and the header links the
    glossary entry rather than explaining itself in the table."""
    key = EWAR_ON[board]
    fn, hash_ = DEFAULT_RENDERS[board]
    html = fn(hash_)
    assert key in _visible(html), (board, _visible(html))
    th = _table(html).split('data-col="%s"' % key)[0].rsplit("<th ", 1)[1]
    assert 'data-gl="ewar"' in _table(html).split('data-col="%s"' % key)[1].split("</th>")[0], board
    assert "mlbstats-cv-off" not in th, board


def test_team_defense_is_pinned_without_an_ewar_column():
    """Spec 4.5, deliberate: a whole-player number on a fielding rollup would
    repeat the lineup total on another frame, so this board has none."""
    fn, hash_ = DEFAULT_RENDERS["defteam"]
    table = _table(fn(hash_))
    assert 'data-col="war"' not in table and 'data-col="team_war"' not in table


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


@pytest.mark.parametrize("board", sorted(PHONE))
def test_the_phone_subset_of_every_standard_view(board):
    """At 640px and below a board keeps its identity column and the four or five
    stats in PHONE; everything else carries mlbstats-cv-wide. eWAR survives the
    cut on every board that has one but Defense, whose phone four are the
    fielding ones a reader opened that board for (spec 4.5)."""
    fn, hash_ = DEFAULT_RENDERS[board]
    html = fn(hash_)
    for key in STANDARD[board][1:]:
        wide = "mlbstats-cv-wide" in _cls(html, key)
        assert wide == (key not in PHONE[board]), (board, key)
    assert "mlbstats-cv-wide" not in _cls(html, STANDARD[board][0])
    if board in EWAR_ON and board != "def":
        assert EWAR_ON[board] in PHONE[board], board


def test_the_defense_phone_exception_is_the_only_one():
    """The single Standard view that drops eWAR on a phone, named here so the
    fit test's matching exception cannot outlive it."""
    assert [b for b in EWAR_ON if EWAR_ON[b] not in PHONE[b]] == ["def"]


def test_the_group_rules_on_the_reliever_standard_view():
    grp = [k for cls, k, _ in _heads(_render_bullpen("")) if "mlbstats-cv-grp" in cls.split()]
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


# All carries EVERY column, the Baseball Savant display columns included (owner
# answer M26-3, 2026-09-25: 5 reliever, 6 starter, 5 hitter and 9 defense Savant
# columns). It runs wider than its box, so up to a 1440 window it may scroll
# sideways inside its own frame, never the page (test_mlbstats_fit.py).
SAVANT_COLS = {
    "rel": {"whiff_pct", "chase_pct", "z_contact_pct", "f_strike_pct", "fb_velo"},
    "sp": {"swstr_pct", "whiff_pct", "chase_pct", "z_contact_pct", "f_strike_pct", "fb_velo"},
    "hit": {"chase_pct", "whiff_pct", "z_contact_pct", "sweet_spot_pct", "pull_pct"},
    "def": {"c_blk_runs", "c_blk_aa", "c_blk_pitches", "c_cs_runs", "c_cs_aa", "c_sb_att",
            "c_pop", "c_exchange", "c_arm"},
}


@pytest.mark.parametrize("hash_,fn,n,board", [
    ("#section=bullpen&rcols=all", _render_bullpen, 30, "rel"),
    ("#section=starters&scols=all", smoke._render_starters, 25, "sp"),
    ("#section=hitters&hcols=all", smoke._render_hitters, 30, "hit"),
    ("#section=defense&dcols=all", smoke._render_defense, 26, "def"),
])
def test_the_all_view_shows_every_column_and_wraps_only_spaced_headers(hash_, fn, n, board):
    html = fn(hash_)
    assert '<table class="mlbstats-table mlbstats-cv-all">' in html
    heads = _heads(html)
    assert len(heads) == n and len(_visible(html)) == n
    assert SAVANT_COLS[board] <= set(_visible(html)), sorted(SAVANT_COLS[board] - set(_visible(html)))
    assert "mlbstats-cv-off" not in _table(html) and "mlbstats-cv-wide" not in _table(html)
    for cls, key, tag in heads:
        label = re.search(r'data-export-text="([^"]*)"', tag).group(1)
        assert ("mlbstats-nw" in cls.split()) == (" " not in label), (key, label)


def test_no_column_is_left_out_of_all():
    """The 2026-09-25 allOff carve-out is gone: no column object may opt out of
    All, and All's plan pushes every column it is handed."""
    assert "allOff" not in JS


# ONE Catching view with every catcher column, each sample count beside its rate
# (owner answer M26-4, 2026-09-25). The Blocking and Throwing views it replaced
# are retired ids that still resolve to it, from a link or a stored pick.
CATCHING = ["name", "pos", "dem_plus", "frm_runs", "c_blk_runs", "c_blk_aa", "c_blk_pitches",
            "c_cs_runs", "c_cs_aa", "c_sb_att", "c_pop", "c_exchange", "c_arm", "inn"]


@pytest.mark.parametrize("view", ["catching", "blocking", "throwing"])
def test_the_catching_view_and_its_retired_links(view):
    html = smoke._render_defense("#section=defense&dcols=" + view)
    assert _visible(html) == CATCHING, _visible(html)
    assert 'data-colview="def:catching" aria-pressed="true"' in html
    assert 'data-colview="def:blocking"' not in html and 'data-colview="def:throwing"' not in html


def test_the_all_pill_says_it_may_scroll():
    html = _render_bullpen("")
    m = re.search(r'<button[^>]*data-colview="rel:all"[^>]*>', html)
    assert m and 'title="' in m.group(0), "the All pill must say it can scroll on a narrow screen"


def test_history_boards_reuse_the_live_views_and_skip_missing_keys():
    html = smoke._render_defense("#section=defense&dseason=2025")
    # This fixture is a past board from BEFORE the E6 join, so the eWAR column
    # is not there at all: a history board drops a key no season carries rather
    # than serving a column of absent tokens (coveredCols).
    assert _visible(html) == ["name", "pos", "dem_plus", "fld_total", "def_runs", "inn"]
    assert 'data-col="war"' not in _table(html), "an unjoined eWAR column reached a past board"
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
    # Hitter Luck is xwOBA minus wOBA in wOBA points (2026-09-24), the same
    # unit as the pitcher boards, not xHEM+ minus HEM+ index points.
    assert 'data-export-text="Luck (wOBA)"' in heads["luck_gap"]
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




# ------------------------------------------------- waves 4 and 6: the eWAR joins
# The Leverage, Defense and team columns read payload fields the exporters stamp
# (spec E3 to E6). Two pins per board: the served value renders, and an absent
# one reads BLANK. The second is the one that lets the page ship first: a board
# whose exporter has not landed shows an empty column, never a zero.
_PAYLOAD_RENDER = {
    "rel": (smoke._prelude, "SAMPLE", "mlbstats-app-root", ""),
    "relteam": (smoke._prelude, "SAMPLE", "mlbstats-app-root", "#view=teams"),
    "sp": (smoke._starter_prelude, "STARTER_SAMPLE", "mlbstats-starters-root", "#section=starters"),
    "spteam": (smoke._starter_prelude, "STARTER_SAMPLE", "mlbstats-starters-root",
               "#section=starters&sview=teams"),
    "hit": (smoke._hitter_prelude, "HITTER_SAMPLE", "mlbstats-hitters-root", "#section=hitters"),
    "hitteam": (smoke._hitter_prelude, "HITTER_SAMPLE", "mlbstats-hitters-root",
                "#section=hitters&hview=teams"),
    "levbat": (smoke._leverage_prelude, "LEVERAGE_SAMPLE", "mlbstats-leverage-root", "#section=leverage"),
    "levsp": (smoke._leverage_prelude, "LEVERAGE_SAMPLE", "mlbstats-leverage-root",
              "#section=leverage&lview=starters"),
    "def": (smoke._defense_prelude, "DEFENSE_SAMPLE", "mlbstats-defense-root", "#section=defense"),
    "defteam": (smoke._defense_prelude, "DEFENSE_SAMPLE", "mlbstats-defense-root",
                "#section=defense&dview=teams"),
}


def _render_subs(board: str, subs: dict, hash_: str | None = None) -> str:
    """Re-render a board from its smoke payloads, with `subs` mapping a smoke
    sample name to a function that edits the parsed payload."""
    prelude, _sample, root, default_hash = _PAYLOAD_RENDER[board]
    src_js = prelude(default_hash if hash_ is None else hash_)
    for var, mutate in subs.items():
        old = "var %s=%s;" % (var, getattr(smoke, var))
        assert old in src_js, (board, var)
        payload = json.loads(getattr(smoke, var))
        mutate(payload)
        src_js = src_js.replace(old, "var %s=%s;" % (var, json.dumps(payload)))
    ctx = MiniRacer()
    ctx.eval(src_js + JS)
    return ctx.eval("__html['%s'] || ''" % root)


def _render_with(board: str, mutate, var: str | None = None) -> str:
    return _render_subs(board, {var or _PAYLOAD_RENDER[board][1]: mutate})


@pytest.mark.parametrize("board", sorted(EWAR_ON))
def test_a_served_ewar_value_renders_on_every_board_that_carries_the_column(board):
    key, rows = EWAR_ON[board], ROWS_KEY[board]

    def stamp(p):
        for r in p[rows]:
            r[key] = 3.4

    cells = [c.strip() for c in _cells(_render_with(board, stamp), key)]
    assert cells and all(c == "3.4" for c in cells), (board, cells)


@pytest.mark.parametrize("board", sorted(EWAR_ON))
def test_an_absent_ewar_value_reads_blank_and_never_zero(board):
    """The whole reason this page side can ship before the exporters: a payload
    with no eWAR field renders the site's absent token in every row."""
    key, rows = EWAR_ON[board], ROWS_KEY[board]

    def strip_(p):
        for r in p[rows]:
            r.pop(key, None)

    html = _render_with(board, strip_)
    cells = [c.strip() for c in _cells(html, key)]
    assert cells and all(c == "-" for c in cells), (board, cells)
    assert "0.0" not in "".join(cells)


def test_the_defense_ewar_header_names_its_fielding_frame_from_the_payload():
    """Spec: the page never types a frame. The Defense eWAR title is its own
    terse sentence plus frame.ewar_note, which the exporter builds from
    data/ewar.json, so the v3 switch rewrites it with no JS change."""

    def stamp(p):
        for r in p["fielders"]:
            r["war"] = 2.1
        p.setdefault("frame", {})["ewar_note"] = EWAR_NOTE

    tag = {k: t for _, k, t in _heads(_render_with("def", stamp))}["war"]
    assert "Whole-player eWAR this season." in tag
    assert "a different frame from Fld and DEM+" in tag, tag
    assert 'noteFrom: "ewar_note"' in JS
    assert "fielding_blend_w" not in JS, "the page must not type a frame of its own"


def test_the_defense_ewar_header_says_nothing_extra_when_the_payload_has_no_note():
    def stamp(p):
        for r in p["fielders"]:
            r["war"] = 2.1

    tag = {k: t for _, k, t in _heads(_render_with("def", stamp))}["war"]
    assert "Whole-player eWAR this season." in tag and "frame" not in tag


def test_the_ewar_build_stamp_rides_every_new_ewar_header():
    """E2: a missed nightly is disclosed on the eWAR column itself, so every new
    column is flagged `ewar: true` and picks the stamp up from its payload."""
    def stamp(p):
        p["ewar_vintage"] = {"artifact_generated_at": "2026-09-03T12:35:09", "stale": True,
                             "rebuilds_on_a_schedule": True}
        for r in p["fielders"]:
            r["war"] = 2.1

    tag = {k: t for _, k, t in _heads(_render_with("def", stamp))}["war"]
    assert "eWAR built 2026-09-03" in tag, tag
    block = JS.replace("\r\n", "\n")
    for key in ("war", "team_war"):
        for m in re.finditer(r'\{ key: "%s", label: "eWAR"(.*?)\n' % key, block):
            assert "ewar: true" in m.group(1), (key, m.group(1))


def test_history_boards_keep_the_season_count_and_still_drop_the_war_rates():
    """Wave 6 (E6). eWAR is a season count the history exports join per (player,
    season); the WAR RATES are standardised on the live pool and stay dropped.
    Recorded wOBA joins the hitter history the same way (E8); published wRC+
    does not, because hitter_export joins it on the live board only."""
    src = JS.replace("\r\n", "\n")
    rel = src.split("var REL_HISTORY_KEYS =")[1].split(";")[0]
    sp = src.split("var STARTER_HISTORY_DROP =")[1].split(";")[0]
    hit = src.split("var HITTER_HISTORY_DROP =")[1].split(";")[0]
    dfn = src.split("var DEFENSE_HISTORY_DROP =")[1].split(";")[0]
    assert "war: 1" in rel and "war_ip_plus" not in rel      # allow-list
    assert "war: 1" not in sp and "war_ip_plus: 1" in sp
    assert "war: 1" not in hit and "war_pa_plus: 1" in hit
    assert "woba_raw" not in hit and "wrc_plus: 1" in hit
    assert "war" not in dfn
    # and the two keys the history exports have yet to serve everywhere are the
    # ones a past board drops when a season carries none of them
    joined = src.split("var HISTORY_JOINED =")[1].split(";")[0]
    assert "war: 1" in joined and "woba_raw: 1" in joined


def test_a_past_season_board_renders_the_ewar_it_is_served():
    """The other half of wave 6: once the history export joins the season count,
    the past board prints it in the column the live board uses."""
    def stamp(p):
        for r in p["history"]["2025"]["fielders"]:
            r["war"] = 1.6

    html = _render_subs("def", {"DEFENSE_HISTORY_SAMPLE": stamp}, "#section=defense&dseason=2025")
    assert "war" in _visible(html), _visible(html)
    assert [c.strip() for c in _cells(html, "war")] == ["1.6", "1.6"]


def test_a_past_season_ewar_header_drops_the_sentence_that_is_only_true_live():
    """A history board reuses the live column objects, so its eWAR title is
    rewritten: no "this season" on a board that is not this season, and no
    reference to the WAR rate, a column no history board carries."""
    def stamp(p):
        for r in p["history"]["2025"]["fielders"]:
            r["war"] = 1.6

    html = _render_subs("def", {"DEFENSE_HISTORY_SAMPLE": stamp}, "#section=defense&dseason=2025")
    tag = {k: t for _, k, t in _heads(html)}["war"]
    assert "for the season shown" in tag, tag
    assert "this season" not in tag and "numerator" not in tag, tag
    live = {k: t for _, k, t in _heads(smoke._render_defense("#section=defense"))}["war"]
    assert "this season" in live, live
    src = JS.replace("\r\n", "\n")
    for name in ("REL_HISTORY_COLS", "STARTER_HISTORY_COLS", "HITTER_HISTORY_COLS",
                 "DEFENSE_HISTORY_COLS"):
        body = src.split("var %s = " % name)[1][:400]
        assert "historyTitle(" in body, name
        assert "for the season shown." in body, name


def test_a_past_defense_board_still_names_the_fielding_frame_of_its_ewar():
    """Spec risk 3 (two fielding frames on one row) is mitigated by a sentence
    from the payload, and a past board carries the same two frames, so the note
    rides there too. The live BUILD STAMP does not: it would date a closed
    season with today's build."""
    def stamp_history(p):
        for r in p["history"]["2025"]["fielders"]:
            r["war"] = 1.6

    def stamp_live(p):
        p.setdefault("frame", {})["ewar_note"] = EWAR_NOTE
        p["ewar_vintage"] = {"artifact_generated_at": "2026-09-03T12:35:09", "stale": True,
                             "rebuilds_on_a_schedule": True}

    html = _render_subs("def", {"DEFENSE_HISTORY_SAMPLE": stamp_history, "DEFENSE_SAMPLE": stamp_live},
                        "#section=defense&dseason=2025")
    tag = {k: t for _, k, t in _heads(html)}["war"]
    assert "a different frame from Fld and DEM+" in tag, tag
    assert "eWAR built" not in tag, tag


def test_a_past_season_drops_a_key_no_row_carries_rather_than_serving_it_empty():
    """The rule that lets wave 6's page half ship before its exporter half: the
    eWAR column appears on a past board the season it is joined, and until then
    the board looks exactly as it did."""
    def none(p):
        for r in p["history"]["2025"]["fielders"]:
            r.pop("war", None)

    def some(p):
        rows = p["history"]["2025"]["fielders"]
        rows[0]["war"] = 1.6
        rows[1].pop("war", None)

    off = _render_subs("def", {"DEFENSE_HISTORY_SAMPLE": none}, "#section=defense&dseason=2025")
    assert 'data-col="war"' not in _table(off)
    on = _render_subs("def", {"DEFENSE_HISTORY_SAMPLE": some}, "#section=defense&dseason=2025")
    assert [c.strip() for c in _cells(on, "war")] == ["1.6", "-"], _cells(on, "war")


# ---------------------------------------------------------------- wave 3: the GFX cards
# Each shared-graphic spec leads with the board's index and then eWAR, the
# column the boards themselves lead with. Pinned as a static read of the builder
# (the cards render in a browser, not in this harness): every column list in the
# block, in source order, so a card with a past-season variant is pinned twice
# and a column can never drift away from the value under it.
GFX_CARDS = {
    "relievers": {"labels": [["#", "Player", "REM+", "eWAR", "K-BB%", "ERA", "IP", "gmLI"]],
                  "ewar": (3, "r.war")},
    "bullpens": {"labels": [["#", "Team", "Bullpen+", "eWAR", "Hi-Lev Core", "Relief IP"]],
                 "ewar": (3, "t.team_war")},
    "starters": {"labels": [["#", "Player", "SEM+", "eWAR", "K-BB%", "ERA", "IP", "GS"]],
                 "ewar": (3, "r.war")},
    # Two lists, in source order: the past-season variant is written first in
    # the block, and it carries neither published wRC+ (joined on the live board
    # only) nor, before the E6 join, eWAR, so it keeps the shrunk wOBA under its
    # true label instead of printing a column of absent tokens. "live" says
    # which list the eWAR pin reads.
    "hitters": {"labels": [["#", "Player", "HEM+", "Shrunk wOBA", "OPS", "PA"],
                           ["#", "Player", "HEM+", "wRC+", "eWAR", "PA", "OPS"]],
                "ewar": (4, "r.war"), "live": 1},
    "defense": {"labels": [["#", "Player", "Pos", "DEM+", "DEM+ 3yr", "Fld", "Inn"]]},
    "teamdefense": {"labels": [["#", "Team", "Team DEM+", "Fld", "Inn"]]},
    # The leverage card assembles its cells with push() rather than one array
    # per variant, so only its column lists are pinned here; its cell
    # expressions are covered by test_no_gfx_card_invents_a_zero below.
    "leverage": {"labels": [["#", "Player", "WPA", "WPA/start", "WPA/LI"],
                            ["#", "Player", "WPA", "WPA/LI", "Clutch"]], "paired": False},
    # The sixth board (wave 5): the only card that reads a whole season, so it
    # leads with the total and carries both sides plus the role under it.
    "ewar": {"labels": [["#", "Player", "eWAR", "Bat", "Pitch", "Role"]],
             "ewar": (2, "r.war")},
}


def _gfx_block(view: str) -> str:
    src = JS.replace("\r\n", "\n")
    i = src.index('if (view === "%s") {' % view)
    j = src.find('\n    if (view === ', i + 1)
    k = src.find("\n    return null;", i + 1)
    end = min(x for x in (j, k, len(src)) if x > i)
    return src[i:end]


def _gfx_lists(view: str, pattern: str) -> list[list[str]]:
    """Every top-level [ ... ] in one card's block that matches `pattern`, in
    source order."""
    block, out, depth, start = _gfx_block(view), [], 0, None
    for i, ch in enumerate(block):
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]" and depth:
            depth -= 1
            if depth == 0:
                found = re.findall(pattern, block[start:i + 1])
                if found:
                    out.append(found)
    return out


def _gfx_labels(view: str) -> list[list[str]]:
    return _gfx_lists(view, r'\{ label: "([^"]+)", frac:')


def _gfx_cells(view: str) -> list[list[str]]:
    return _gfx_lists(view, r"\{ t: (.+?) \},")


def _gfx_fracs(view: str) -> list[list[float]]:
    return [[float(f) for f in xs] for xs in _gfx_lists(view, r"frac: ([0-9.]+)")]


@pytest.mark.parametrize("view", sorted(GFX_CARDS))
def test_every_gfx_card_leads_with_its_index_then_ewar(view):
    card = GFX_CARDS[view]
    labels = _gfx_labels(view)
    assert labels == card["labels"], (view, labels)
    for one in labels:
        assert one[0] == "#", (view, one)
    for fracs in _gfx_fracs(view):
        assert 0.9 <= sum(fracs) <= 1.02, (view, sum(fracs))
    if card.get("paired", True):
        cells = _gfx_cells(view)
        assert [len(c) for c in cells] == [len(one) for one in labels], (view, cells, labels)
    if "ewar" in card:
        at, expr = card["ewar"]
        live = card.get("live", 0)
        assert labels[live].index("eWAR") == at, (view, labels[live])
        assert expr in _gfx_cells(view)[live][at], (view, _gfx_cells(view)[live][at])
    else:
        assert not any("eWAR" in one for one in labels), view


def test_the_hitter_card_retired_the_shrunk_woba_it_used_to_call_woba():
    """The live card carried the SHRUNK wOBA under a "wOBA" label, the same
    mislabel the board carried. wRC+ and eWAR replace it there; the past-season
    card keeps the value under its true label, and names it in the caption."""
    block = _gfx_block("hitters")
    assert '{ label: "wOBA", frac:' not in block
    assert '{ label: "Shrunk wOBA", frac:' in block
    assert "Shrunk wOBA = the number it is scaled from" in block


def test_a_published_number_on_a_card_is_labelled_published():
    """House rule 1 on the most shareable surface: a graphic has no tooltip, so
    the provenance of a published number rides the caption."""
    for view in ("hitters", "defense", "teamdefense"):
        assert "FanGraphs, published" in _gfx_block(view), view
    assert "wRC+ = FanGraphs, published" in _gfx_block("hitters")


def test_no_gfx_card_invents_a_zero():
    """Every card cell routes through the shared number-format contract, which
    renders an absent value as the site's null token."""
    for view in sorted(GFX_CARDS):
        for cell in re.findall(r"\{ t: (.+?) \},", _gfx_block(view)):
            assert re.match(r"(i \+ 1|f\d|fInt|fPct|fSigned|r\.|t\.)", cell.strip()), (view, cell)


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
    "TEAM_COLS": ["team", "bullpen_plus", "team_war", "leverage_deploy_plus", "n_above_avg",
                  "high_lev_core_rem", "relief_ip", "team_wpa", "sd_md"],
    "STARTER_COLS": ["name", "sem_plus", "sem_plus_3yr", "xsem_plus", "luck", "war_ip_plus", "war_ip_plus_adj",
                     "war_ip_plus_3yr", "war", "ip", "gs", "ip_per_gs", "k_pct", "bb_pct", "k_bb_pct", "gb_pct",
                     "fip", "era", "hr9"],
    "STARTER_TEAM_COLS": ["team", "rotation_plus", "team_war", "front_sem", "n_above_avg", "starter_ip",
                          "total_gs"],
    "HITTER_COLS": ["name", "hem_plus", "wrc_plus", "hem_plus_3yr", "xhem_plus", "fwdhem_plus", "pwoba",
                    "luck_gap", "war_pa_plus", "war_pa_plus_adj", "war_pa_plus_3yr", "war", "pa", "hr", "sb",
                    "avg", "obp", "slg", "ops", "iso", "woba_raw", "woba", "bb_pct", "k_pct", "babip"],
    "HITTER_TEAM_COLS": ["team", "offense_plus", "team_war", "heart_hem", "n_above_avg", "team_pa"],
    "BAT_LEV_COLS": ["name", "wpa", "pli", "clutch", "wpa_li", "war", "pa"],
    "STARTER_LEV_COLS": ["name", "wpa", "wpa_per_start", "wpa_li", "war", "gs", "starts"],
    "DEFENSE_COLS": ["name", "pos", "dem_plus", "dem_plus_3yr", "dem_plus_pos_pct", "fld_total", "fld_runs",
                     "frm_runs", "pos_runs", "pos_runs_fg", "def_runs", "rate_1000", "rate_1000_shrunk", "inn",
                     "fld_pct", "hem_plus", "war"],
    "DEFENSE_TEAM_COLS": ["team", "team_dem_plus", "n_above_avg", "team_fld_total", "team_frm_runs",
                          "team_pos_runs", "team_pos_runs_fg", "team_inn"],
    # wave 5: the eWAR board's own two tables. wsort= and wtsort= name these
    # keys, so they are frozen the moment the section ships.
    "WAR_COLS": ["name", "pos", "war", "war_bat", "war_pit", "pa", "ip", "gs"],
    "WAR_TEAM_COLS": ["team", "war", "war_earned", "war_bat", "war_sp", "war_rp", "war_sw", "n_players"],
}
# The table each view-registry board renders.
BOARD_ARRAYS = {"rel": "REL_COLS", "sp": "STARTER_COLS", "hit": "HITTER_COLS", "def": "DEFENSE_COLS",
                "levbat": "BAT_LEV_COLS", "levsp": "STARTER_LEV_COLS", "relteam": "TEAM_COLS",
                "spteam": "STARTER_TEAM_COLS", "hitteam": "HITTER_TEAM_COLS", "defteam": "DEFENSE_TEAM_COLS",
                "war": "WAR_COLS", "warteam": "WAR_TEAM_COLS"}
# The view ids a deep link can name (rcols= / scols= / hcols= / dcols=).
FROZEN_VIEWS = {"rel": ["standard", "skill", "value", "leverage", "all"],
                "sp": ["standard", "skill", "value", "all"],
                "hit": ["standard", "skill", "value", "batting", "all"],
                "def": ["standard", "runs", "catching", "all"]}


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
    assert hashkeys == {"rel": "rcols", "sp": "scols", "hit": "hcols", "def": "dcols",
                        "war": "wcols"}


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


def _colboard_values() -> list[str]:
    """Every board id winColBoard() can return: the WIN_COLBOARD map plus the
    leverage ternary, read out of the file rather than re-typed here."""
    blk = re.search(r"var WIN_COLBOARD = \{([^}]*)\}", JS).group(1)
    fn = re.search(r"function winColBoard\(sec\) \{(.*?)\n  \}", JS, re.S).group(1)
    return [v for v in re.findall(r'"([a-z]+)"', blk + fn) if v not in ("leverage", "starters")]


def test_every_render_call_names_a_registry_board():
    reg = _registry()
    calls = _render_calls()
    assert len(calls) >= 13, len(calls)
    for c in calls:
        args = c.split(", ", 4)
        assert len(args) == 5, ("a renderTable call without a board id", c)
        # The window boards resolve their strip from the section, so the id is a
        # call rather than a literal; every value it can return is pinned here
        # the same way a literal would be.
        boards = (_colboard_values() if args[4].startswith("winColBoard(")
                  else re.findall(r'(?:^|[?:])\s*"([a-z]+)"', args[4]))
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


# ---------------------------------------------------------------- wave 2: the vertical budget
# Owner decision O2 (2026-09-11): the methodology fold opens CLOSED at every
# width (a reader's stored choice still wins), the Team note is one line until
# opened, a phone's filter bar is a search box and a Filters button until the
# drawer opens, and every section root opts into the Download CSV control.
# Measured on the served page at 1440x900: the reliever table top moved from
# y 770 to 589 (3 to 8 rows on the first screen); test_mlbstats_fit pins the
# layout, this file pins the markup.

# (board, render function, hash, fold id); the eWAR board joins in wave 5.
SECTIONS = [
    ("rel", _render_bullpen, "", "rel-about"),
    ("sp", smoke._render_starters, "#section=starters", "sp-about"),
    ("hit", smoke._render_hitters, "#section=hitters", "hit-about"),
    ("lev", smoke._render_leverage, "#section=leverage", "lev-about"),
    ("def", smoke._render_defense, "#section=defense", "def-about"),
]
_FILTBTN = '<button type="button" class="chip mlbx-filtbtn" aria-expanded="%s">Filters%s</button>'


@pytest.mark.parametrize("board,fn,hash_,fold", SECTIONS, ids=[s[0] for s in SECTIONS])
def test_the_methodology_fold_opens_closed_on_every_board(board, fn, hash_, fold):
    html = fn(hash_)
    m = re.search(r'<div class="mlbstats-collapse mlbstats-fold( is-collapsed)?" data-collapse="%s">' % fold, html)
    assert m, (board, "no methodology fold on the board")
    assert m.group(1), (board, "the fold opened by default; O2 closes it at every width")
    head = html[m.end():m.end() + 400]
    assert 'aria-expanded="false"' in head and "how to read this board" in head, head


def _fold(store: str) -> str:
    ctx = MiniRacer()
    ctx.eval(smoke._prelude("") + "window.localStorage = { getItem: function (k) { return "
             + store + "; }, setItem: function () {} };" + JS)
    return ctx.eval("__html['mlbstats-app-root'] || ''")


def test_a_readers_stored_choice_still_opens_the_fold():
    """Both legs in one harness, because the pair is the decision: O2 makes
    CLOSED the default at every width, and collapseState reads localStorage
    BEFORE that default, so a reader who opened the fold once keeps it open
    on this board and every visit. Read the stored leg alone and a revert to
    the old open-on-desktop default would still pass."""
    stored = _fold("k === 'mlbstats.collapse.rel-about' ? '0' : null")
    assert '<div class="mlbstats-collapse mlbstats-fold" data-collapse="rel-about">' in stored
    assert 'aria-expanded="true"' in stored.split('data-collapse="rel-about">')[1][:200]
    nothing = _fold("null")
    assert '<div class="mlbstats-collapse mlbstats-fold is-collapsed" data-collapse="rel-about">' in nothing
    assert 'aria-expanded="false"' in nothing.split('data-collapse="rel-about">')[1][:200]


_CAPTURE_DOC = (
    # Two delegated document listeners live on this page now (the phone
    # drawer and the Team note), so the capture keeps a LIST and __fire
    # runs them all: capturing one must never swallow the other.
    "var __doc = {};"
    "document.addEventListener = function (ev, fn) { (__doc[ev] = __doc[ev] || []).push(fn); };"
    "function __fire(ev, e) { (__doc[ev] || []).forEach(function (fn) { fn(e); });"
    " return (__doc[ev] || []).length; }"
)
# A click whose target answers ONE delegated selector and nothing else.
_TARGET = "{target: {closest: function (s) { return s === %s ? %s : null; }}}"
_HIT_FILTBTN = _TARGET % ("'.mlbx-filtbtn'", "{}")
_MISS = "{target: {closest: function () { return null; }}}"


def _hit_note(open_: bool) -> str:
    """A click on the Team note summary. The browser toggles the element
    AFTER the listeners run, so `open` here is the state on screen."""
    return _TARGET % ("'details.mlbstats-teambasis > summary'",
                      "{parentNode: {open: %s}}" % ("true" if open_ else "false"))


def test_the_team_note_is_one_line_until_opened():
    """The defense sample carries a team_basis block (1 of 15 rows moved). The
    summary is the one line; the payload's own sentence and the moved-row
    count sit in the body, so the disclosure is still derived, never typed."""
    html = smoke._render_defense("#section=defense")
    assert '<div class="mlbstats-note mlbstats-teambasis">' not in html, "the old always-open note"
    i = html.index('<details class="mlbstats-note mlbstats-teambasis"')
    note = html[i:html.index("</details>", i)]
    summary, body = note.split("</summary>")
    assert summary == ('<details class="mlbstats-note mlbstats-teambasis"><summary><b>Team column:</b> the club today'
                       '<span class="proj-dim"> (1 row moved)</span>'), summary
    assert body.startswith("Team is the current club. "), body
    assert "1 of 15 rows are credited to a club other than the one they earned the line for." in body
    assert 'data-collapse' not in note, "native details: no collapse state to keep"


def _note(tb: str) -> str:
    ctx = MiniRacer()
    ctx.eval(smoke._prelude("") + "SAMPLE.team_basis = " + tb + ";" + JS)
    return ctx.eval("__html['mlbstats-banner'] || ''")


def test_the_team_note_counts_moved_rows_and_says_nothing_when_none_moved():
    """The count is the reader's handle on how much the convention costs
    him. Zero moved rows is the EMPTY-ORG-MAP outage (bullpen_export logs
    it and serves stats-earned teams under a current_roster basis), where
    "(0 rows moved)" would read as a measurement rather than a miss."""
    tb = "{basis: 'current_roster', scope: 'current', note: 'Team is the club today.'"
    bann = _note(tb + ", n_rows: 30, n_moved_to_current_club: 2}")
    assert '<span class="proj-dim"> (2 rows moved)</span></summary>Team is the club today. 2 of 30 rows' in bann
    bann = _note(tb + ", n_rows: 30, n_moved_to_current_club: 0}")
    assert '<summary><b>Team column:</b> the club today</summary>Team is the club today.' in bann
    assert "moved)" not in bann, bann
    bann = _note(tb + "}")
    assert '<summary><b>Team column:</b> the club today</summary>Team is the club today.</details>' in bann


@pytest.mark.parametrize("basis,scope,lead", [
    ("current_roster", "current", "the club today"),
    ("current_roster", "history", "the club today, not the club of that season"),
    ("stats_earned", "current", "the club the line was earned with"),
    ("stats_earned", "history", "the club the line was earned with"),
    ("", "current", "see the note"),
], ids=["current", "history", "earned", "earned-history", "unknown"])
def test_the_closed_line_reads_the_basis_out_of_the_payload(basis, scope, lead):
    """The summary is the line 100% of readers see, and it is a claim about
    the basis. bullpen_export.TEAM_BASIS is a documented two-value constant
    with a one-line revert and the meta block carries the scope beside it,
    so a typed "the club today" would assert the opposite of the payload's
    own sentence under stats_earned, and would give a history reader the
    mild half of a rule that moves 2,088 of 6,885 served history rows."""
    bann = _note("{basis: '%s', scope: '%s', note: 'PAYLOAD SENTENCE.', n_rows: 30,"
                 " n_moved_to_current_club: 2}" % (basis, scope))
    assert "<summary><b>Team column:</b> " + lead + '<span class="proj-dim">' in bann, bann
    assert "</summary>PAYLOAD SENTENCE." in bann, bann


def test_a_basis_the_page_does_not_know_makes_no_claim_at_all():
    """The fallback is not the current convention wearing a different name:
    a third value of TEAM_BASIS, or a payload written before the field
    existed, leaves the page with nothing to assert, so it points at the
    sentence it does have instead of guessing."""
    bann = _note("{basis: 'by_stint', note: 'PAYLOAD SENTENCE.'}")
    assert "<summary><b>Team column:</b> see the note</summary>PAYLOAD SENTENCE." in bann, bann


def test_an_opened_team_note_survives_the_next_render():
    """Four of the five boards rewrite the note INTO their root on every
    search keystroke, chip and view click (mlbstats.js: bannerHTML(...) +
    teamBasisNote(...)), and a native <details> keeps no state, so an opened
    note snapped shut under the reader. One module flag, flipped by one
    delegated listener, emitted by every render. Measured on Defense, whose
    in-place render is one of those four."""
    ctx = _clicker("#section=defense", prelude=smoke._defense_prelude, extra=_CAPTURE_DOC)
    root = "__html['mlbstats-defense-root']"
    assert '<details class="mlbstats-note mlbstats-teambasis">' in ctx.eval(root)
    ctx.eval("__fire('click', %s)" % _hit_note(False))        # a reader opens it
    ctx.eval("__click('mlbpos:C')")
    assert '<details class="mlbstats-note mlbstats-teambasis" open>' in ctx.eval(root)
    ctx.eval("__fire('click', %s)" % _hit_note(True))         # and closes it again
    ctx.eval("__click('mlbpos:C')")
    assert '<details class="mlbstats-note mlbstats-teambasis">' in ctx.eval(root)
    ctx.eval("__fire('click', %s)" % _MISS)                   # a click elsewhere is not a toggle
    ctx.eval("__click('mlbpos:C')")
    assert '<details class="mlbstats-note mlbstats-teambasis">' in ctx.eval(root)


@pytest.mark.parametrize("board,fn,hash_,fold", SECTIONS, ids=[s[0] for s in SECTIONS])
def test_every_filter_bar_is_the_phone_drawer_led_by_the_filters_button(board, fn, hash_, fold):
    """Spec 3.5: the bar is .mlbstats-bar.mlbx-filters, its first child the
    Filters button (aria-expanded), closed until pressed. The element ids
    inside are unchanged (the fit test unchecks the qualified box by id)."""
    html = fn(hash_)
    bars = re.findall(r'<div class="mlbstats-bar mlbx-filters">(<button[^>]*>Filters</button>)', html)
    assert bars == [_FILTBTN % ("false", "")], (board, bars)
    assert html.count("mlbx-filtbtn") == 1 and html.count("mlbx-filters") == 1, board
    assert re.search(r'class="mlbstats-bar mlbx-filters">.{0,200}<input type="checkbox" id="mlbstats-'
                     r'(?:starter-|hitter-|leverage-|defense-)?qual"', html), board


def test_the_filters_button_counts_the_pressed_chips():
    """A narrowed board must not read as the whole league behind a closed
    drawer: the button carries the count of non-default filters (team, a min
    floor, pressed role or position chips)."""
    ctx = _clicker("#section=bullpen")
    root = "__html['mlbstats-app-root']"
    assert (_FILTBTN % ("false", "")) in ctx.eval(root)
    ctx.eval("__click('mlbrole:Closer')")
    assert (_FILTBTN % ("false", ' <span class="proj-dim">1</span>')) in ctx.eval(root)
    ctx.eval("__click('mlbrole:Middle')")
    assert (_FILTBTN % ("false", ' <span class="proj-dim">2</span>')) in ctx.eval(root)
    ctx.eval("__click('mlbrole:')")                                   # All: back to the default
    assert (_FILTBTN % ("false", "")) in ctx.eval(root)
    ctx = _clicker("#section=defense", prelude=smoke._defense_prelude)
    ctx.eval("__click('mlbpos:C')")
    assert (_FILTBTN % ("false", ' <span class="proj-dim">1</span>')) in ctx.eval("__html['mlbstats-defense-root']")


def test_the_count_names_the_qualified_gate_the_closed_drawer_hides():
    """The qualified box lives IN the drawer and every board defaults it
    ON, so unchecking it is the largest change a closed drawer can hide
    (Relievers 261 rows to the whole league). It counts on all five boards.
    Source, not render: the harness lays nothing out, so it cannot tick a
    checkbox. The search box, which stays visible at every width, is the
    one filter deliberately left out of the count."""
    calls = re.findall(r"filtBtn\(filtCount\(([^)]*)\)\)", JS)
    assert len(calls) == 6, calls
    flags = [c.split(",")[-1].strip() for c in calls]
    assert flags == ["!qualifiedOnly", "!starterQualifiedOnly", "!hitterQualifiedOnly",
                     "!leverageQualifiedOnly", "!defenseQualifiedOnly", "!warQualifiedOnly"], flags
    i = JS.index("function filtCount(")
    assert "qualOff ? 1 : 0" in JS[i:i + 300], JS[i:i + 300]


def test_the_drawer_toggle_is_one_delegated_listener_that_survives_a_rerender():
    """One document-level click listener flips one flag for every section, so
    the drawer stays open across re-renders (a view click here) and section
    switches; a click anywhere else leaves it alone."""
    ctx = _clicker("#section=bullpen", extra=_CAPTURE_DOC)
    root = "__html['mlbstats-app-root']"
    assert ctx.eval("(__doc.click || []).length") >= 1
    ctx.eval("__fire('click', %s)" % _MISS)
    ctx.eval("__click('rel:skill')")
    assert 'class="mlbstats-bar mlbx-filters">' in ctx.eval(root) and (_FILTBTN % ("false", "")) in ctx.eval(root)
    ctx.eval("__fire('click', %s)" % _HIT_FILTBTN)
    ctx.eval("__click('rel:value')")
    html = ctx.eval(root)
    assert 'class="mlbstats-bar mlbx-filters is-open">' in html and (_FILTBTN % ("true", "")) in html
    ctx.eval("__fire('click', %s)" % _HIT_FILTBTN)
    ctx.eval("__click('rel:standard')")
    assert 'class="mlbstats-bar mlbx-filters">' in ctx.eval(root)


def test_the_shell_opts_every_section_root_into_csv_and_uses_short_nav_labels():
    """build_site.build_mlbstats: every section root carries _csv_optin (the
    control exports the columns on screen; hidden view cells carry
    data-export-skip) and the nav reads Bullpen, Starters, Hitters, Leverage,
    Defense. A section added later joins both lists; none leaves."""
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    i = src.index("def build_mlbstats(")
    body = src[i:src.index("\ndef ", i + 1)]
    roots = dict(re.findall(r'<div id="mlbstats-([a-z]+)-root"\{_csv_optin\("([a-z-]+)"\)\}', body))
    for rid, name in {"app": "mlb-leaderboards", "starters": "mlb-starters", "hitters": "mlb-hitters",
                      "leverage": "mlb-leverage", "defense": "mlb-defense", "war": "mlb-ewar"}.items():
        assert roots.get(rid) == name, (rid, roots)
    assert len(set(roots.values())) == len(roots), "two roots share a CSV filename stem"
    assert not re.search(r'<div id="mlbstats-[a-z]+-root"( [^>]*)?></div>', body), "a section root without the CSV opt-in"
    labels = dict(re.findall(r'data-mlbsection="([a-z]+)"[^>]*>([^<]+)</button>', body))
    for sec, label in {"bullpen": "Bullpen", "starters": "Starters", "hitters": "Hitters",
                       "leverage": "Leverage", "defense": "Defense", "war": "Overall"}.items():
        assert labels.get(sec) == label, (sec, labels)
    # ORDER AND LANDING (2026-09-17). The nav order is the owner's; the panel
    # order follows it so tab order and reading order agree; and the shell's
    # active tab has to be the section assets/mlbstats.js opens on, or a reader
    # who lands on a bare URL sees one board with another board's tab lit.
    order = re.findall(r'data-mlbsection="([a-z]+)"', body)
    assert order == ["war", "hitters", "starters", "bullpen", "defense", "leverage"], order
    panels = re.findall(r'<div id="mlbstats-section-([a-z]+)"', body)
    assert panels == order, panels
    active = re.search(r'class="mlbstats-sectionbtn active" data-mlbsection="([a-z]+)"', body).group(1)
    assert active == "war", active
    assert re.search(r'<div id="mlbstats-section-war"[^>]*>', body).group(0).find("hidden") < 0
    assert len(re.findall(r'aria-selected="true"', body)) == 1
    assert len(re.findall(r'hidden>', body)) == len(panels) - 1
    landing = re.search(r"var section = \"([a-z]+)\";", JS).group(1)
    assert landing == active, (landing, active)
    # Owner decision 2026-09-17 REVERSES O1: Overall is first and is what a bare
    # /mlbstats/ URL opens. The hash VALUE stays `war`, so every link ever copied
    # still opens what it named; what changed is the label, the order and the
    # default. The one inbound link that pointed at a bare /mlbstats/ meaning
    # "relievers" (the REM+ hub card) now names its section.
    assert "'/mlbstats/#section=bullpen'" in src, "the REM+ hub card lost its section"
    assert not re.search(r"""href="/mlbstats/"[^#]""", src), "a bare /mlbstats/ link now opens Overall"
    assert not any("Leaderboards" in v for v in labels.values()), labels


@pytest.mark.parametrize("board,fn,hash_,label", [
    ("rel", _render_bullpen, "", 'aria-label="Filter by bullpen role"'),
    ("def", smoke._render_defense, "#section=defense", 'aria-label="Filter by position"'),
])
def test_the_chip_row_follows_its_bar_so_the_closed_drawer_hides_it(board, fn, hash_, label):
    """The drawer hides the chip row with `.mlbx-filters:not(.is-open) +
    .mlbstats-roles`, which holds only while the row is the bar's IMMEDIATE
    next sibling. A wrapper between them leaves a row of Role or Pos chips
    stranded over a closed drawer on a phone."""
    html = fn(hash_)
    assert '</div><div class="mlbstats-seasons mlbstats-roles" role="group" ' + label in html


def test_the_closed_fold_is_a_constant_and_no_longer_a_viewport_read():
    """O2 is one default for every width, so the viewport read that fed the old
    one is gone rather than left behind returning an unused answer."""
    i = JS.index("function proseFold")
    assert "collapsed: true" in JS[i:i + 500]
    assert "isNarrowViewport" not in JS
    # Scoped to the fold: four sibling assets read matchMedia (eephus-nav,
    # eephus-gl, eephus-bg, betting), and a prefers-reduced-motion read
    # elsewhere in this file is not this decision.
    j = JS.index("function collapseState")
    assert "matchMedia" not in JS[j:i + 500], "the fold still reads the viewport"


# ---------------------------------------------------------------- wave 5: the eWAR section
# The sixth section, and the only board on this page that is not a slice of one
# side of the game: every player with a season eWAR block, hitters and pitchers
# on one list, plus Team eWAR on BOTH named club bases (owner decision O8).
# Fixture-shaped like war_board_export.py's payload (spec E7) so the page can be
# pinned before the exporter lands: a two-way player with both sides, a swingman
# on neither pitcher board, an unqualified row, a pitcher with no batting side
# and a club with no mappable stint (war_earned absent, never zero).
WAR_SAMPLE = json.dumps({
    "generated_at": "2026-06-30", "season": 2026, "as_of": "2026-06-29",
    "ewar_vintage": {"artifact_generated_at": "2026-09-03T12:35:09", "stale": False,
                     "rebuilds_on_a_schedule": True},
    "team_basis": {"basis": "current_roster", "scope": "current",
                   "note": "Team is the current club.", "n_rows": 6, "n_moved_to_current_club": 1},
    "qualified_rule": {"min_pa": 100, "min_ip": 30},
    "players": [
        {"mlbam": 660271, "name": "Two Way", "team": "LAD", "role": "TWP", "pos": "DH",
         "qualified": True, "war": 6.2, "war_bat": 3.5, "war_pit": 2.7, "pa": 420, "ip": 78.0,
         "g": 70, "gs": 14},
        {"mlbam": 111, "name": "Center Field", "team": "CHC", "role": "H", "pos": "CF",
         "qualified": True, "war": 8.4, "war_bat": 8.4, "pa": 380, "g": 92},
        {"mlbam": 222, "name": "Ace Adams", "team": "NYY", "role": "SP", "pos": "P",
         "qualified": True, "war": 6.1, "war_pit": 6.1, "ip": 120.1, "g": 19, "gs": 19},
        {"mlbam": 333, "name": "Closer Alpha", "team": "NYY", "role": "RP", "pos": "P",
         "qualified": True, "war": 1.8, "war_pit": 1.8, "ip": 42.1, "g": 45, "gs": 0},
        {"mlbam": 444, "name": "Swing Man", "team": "BOS", "role": "SW", "pos": "P",
         "qualified": True, "war": 1.1, "war_pit": 1.1, "ip": 55.2, "g": 22, "gs": 6},
        {"mlbam": 555, "name": "Thin Sample", "team": "BOS", "role": "H", "pos": "2B",
         "qualified": False, "war": 0.3, "war_bat": 0.3, "pa": 60, "g": 20},
    ],
    "teams": [
        {"team": "CHC", "war": 44.4, "war_earned": 36.4, "war_bat": 26.0, "war_sp": 12.0,
         "war_rp": 4.4, "war_sw": 2.0, "n_players": 41},
        {"team": "NYY", "war": 38.1, "war_bat": 20.0, "war_sp": 13.0, "war_rp": 4.0,
         "war_sw": 1.1, "n_players": 39},
    ],
    "league": {"war": 1000.0, "war_bat": 570.0, "war_pit": 430.0},
})
WAR_STANDARD = {
    "war": ["name", "pos", "war", "war_bat", "war_pit", "pa", "ip", "gs"],
    "warteam": ["team", "war", "war_earned", "war_bat", "war_sp", "war_rp", "war_sw", "n_players"],
}
# The Overall board has named views now (Standard / Rate / All), so PA joined
# its phone subset and Bat/600, Pitch/200 and Also on ride the other two. Age
# and G are absent from THIS harness on purpose: they reach the Current board
# only through data/war_seasons.json, which the harness does not answer, and a
# column with no data drops rather than serving empty - which is what
# test_the_overall_board_drops_age_and_g_without_the_substrate pins.
WAR_PHONE = {"war": ["war", "war_bat", "war_pit", "pa"],
             "warteam": ["war", "war_earned", "war_bat", "war_sp"]}
WAR_HIDDEN = {"war": ["bat_600", "pitch_200", "boards"], "warteam": []}


def _war_prelude(hash_: str, sample: str | None = None, status: int = 200) -> str:
    """The smoke prelude with data/war_leaderboards.json answered. Every OTHER
    URL still gets the bullpen sample, which is exactly what the harness does
    to the real board and what the "being computed" pin below relies on.

    `status` answers the war URL with that HTTP status instead of the sample:
    404 is a box where war_board_export.py has never written the file (the
    tree today, and the deployed site until its first nightly run), 502 the
    transient failure the Retry control exists for. That needs a thenable with
    a REJECTED path, which the smoke FT (a value wrapper whose catch ignores
    its callback) does not have, so the war URL gets FP/FE below and every
    other URL keeps FT."""
    override = f"""
    var WAR_SAMPLE={sample or WAR_SAMPLE};
    var WAR_STATUS={status};
    function FE(err){{return {{then:function(){{return FE(err);}},
      catch:function(cb){{var r=cb(err);return (r&&r.then)?r:FT(r);}}}};}}
    function FP(val){{return {{then:function(cb){{var r;
      try {{ r=cb(val); }} catch (e) {{ return FE(e); }}
      return (r&&r.then)?r:FP(r);}},catch:function(cb){{return FP(val);}}}};}}
    fetch=function(url){{
      if (String(url).indexOf('war_leaderboards')>=0) {{
        return FP({{ok:WAR_STATUS===200,status:WAR_STATUS,
                    json:function(){{return FP(WAR_SAMPLE);}}}});
      }}
      return FT({{ok:true,json:function(){{return FT(SAMPLE);}}}});
    }};
    var EEPHUS_HUB={{
      teamLogo:function(){{return '';}},
      histogram:function(){{return '<svg class="hub-hist"></svg>';}},
      scatter:function(){{return '<svg class="hub-scatter"></svg>';}},
      stripHTML:function(){{return '';}},
      links:function(){{return FT({{byMlbam:{{"111":{{"key":"cf_star","mlbam":111,"name":"Center Field"}}}}}});}}
    }};
    window.EEPHUS_HUB=EEPHUS_HUB;
    """
    return smoke._prelude(hash_) + override


def _render_war(hash_: str = "#section=war", sample: str | None = None, status: int = 200) -> str:
    ctx = MiniRacer()
    ctx.eval(_war_prelude(hash_, sample, status) + JS)
    return ctx.eval("__html['mlbstats-war-root'] || ''")


@pytest.mark.parametrize("board,hash_", [("war", "#section=war"), ("warteam", "#section=war&wview=teams")],
                         ids=["players", "teams"])
def test_the_ewar_board_shows_its_standard_columns_in_order(board, hash_):
    html = _render_war(hash_)
    assert _visible(html) == WAR_STANDARD[board], (board, _visible(html))
    hidden = [k for _, k, _ in _heads(html) if k not in _visible(html)]
    assert hidden == WAR_HIDDEN[board], (board, hidden)
    assert "undefined" not in html and "NaN" not in html


def test_the_overall_board_drops_age_and_g_without_the_substrate():
    """Age is not on war_leaderboards.json at all and its `g` is the pitching
    feed's alone (800 of 1,457 served rows), so both columns reach the Current
    board only through data/war_seasons.json. Absent it, they are DROPPED, not
    served as a column of null markers - the rule coveredCols already applies to
    a history board."""
    html = _render_war()
    assert "age" not in _visible(html) and "g" not in _visible(html), _visible(html)


@pytest.mark.parametrize("board,hash_", [("war", "#section=war"), ("warteam", "#section=war&wview=teams")],
                         ids=["players", "teams"])
def test_the_ewar_board_carries_the_export_contract_and_the_phone_subset(board, hash_):
    html = _render_war(hash_)
    for cls, key, tag in _heads(html):
        m = re.search(r'data-export-text="([^"]*)"', tag)
        assert m and m.group(1), (board, key)
        if key not in _visible(html):
            # A column outside the view is hidden AND kept out of the export,
            # which is the contract every other multi-view board is held to.
            assert "data-export-skip" in tag, (board, key)
            continue
        assert "data-export-skip" not in tag, (board, key)
        if key != WAR_STANDARD[board][0]:
            wide = "mlbstats-cv-wide" in cls.split()
            assert wide == (key not in WAR_PHONE[board]), (board, key)
    assert 'data-export-text="eWAR"' in {k: t for _, k, t in _heads(html)}["war"]


def test_the_ewar_board_sums_both_sides_and_leads_with_the_total():
    """The board exists because the five others cannot show this row: a two-way
    player reads 6.2 here, not the 3.5 Hitters shows him or the 2.7 Starters
    does. The page never adds the sides: the exporter sums them UNROUNDED and
    serves `war`, which is what the column renders."""
    html = _render_war()
    assert _visible(html).index("war") == 2, _visible(html)
    war = [c.strip() for c in _cells(html, "war")]
    assert "<b>8.4</b>" in war and "<b>6.2</b>" in war, war
    names = _cells(html, "name")
    at = [i for i, c in enumerate(names) if "Two Way" in c][0]
    assert _cells(html, "war")[at].strip() == "<b>6.2</b>"
    assert _cells(html, "war_bat")[at].strip() == "3.5"
    assert _cells(html, "war_pit")[at].strip() == "2.7"
    # and the swingman, who is on neither pitcher board, is on this one
    assert "Swing Man" in html and "Swingman" in html


def test_an_absent_side_on_the_ewar_board_reads_blank_and_never_zero():
    """A pitcher has no batting side and a hitter no pitching side. Both read
    the absent token; a zero would be a number nobody measured."""
    html = _render_war()
    i = [k for _, k, _ in _heads(html)].index("war_bat")
    row = re.findall(r"<tr[^>]*>(.*?)</tr>", _table(html).split("<tbody>")[1], re.S)
    ace = [r for r in row if "Ace Adams" in r][0]
    assert re.findall(r"<td[^>]*>(.*?)</td>", ace, re.S)[i].strip() == "-", ace
    assert "0.0" not in ace


def test_team_ewar_names_both_club_bases_and_leaves_an_unmapped_club_blank():
    """Owner decision O8: roster today and club of production differ by up to
    8.0, so both are on the board under their own labels. A club whose stints
    cannot be mapped gets no Earned value rather than a zero."""
    html = _render_war("#section=war&wview=teams")
    heads = {k: t for _, k, t in _heads(html)}
    assert 'data-export-text="eWAR"' in heads["war"] and 'data-export-text="Earned"' in heads["war_earned"]
    assert "the players on the club today" in heads["war"]
    assert "by stint" in heads["war_earned"]
    earned = [c.strip() for c in _cells(html, "war_earned")]
    assert earned == ["36.4", "-"], earned


def test_the_ewar_header_links_the_glossary_and_carries_the_build_stamp_hook():
    for hash_ in ("#section=war", "#section=war&wview=teams"):
        table = _table(_render_war(hash_))
        assert 'data-gl="ewar"' in table.split('data-col="war"')[1].split("</th>")[0], hash_
    block = JS.replace("\r\n", "\n")
    for arr in ("WAR_COLS", "WAR_TEAM_COLS"):
        seg = block[block.index("var %s = [" % arr):]
        seg = seg[:seg.index("\n  ];")]
        m = re.search(r'\{ key: "war", label: "eWAR"(.*?)\n', seg, re.S)
        assert m and "ewar: true" in m.group(1), (arr, m and m.group(1))


def test_a_stale_build_stamp_reaches_the_ewar_board_too():
    """E2 again: the disclosure rides the payload, so the sixth board discloses
    a missed nightly the way the other five do."""
    p = json.loads(WAR_SAMPLE)
    p["ewar_vintage"] = {"artifact_generated_at": "2026-09-03T12:35:09", "stale": True,
                         "rebuilds_on_a_schedule": True}
    tag = {k: t for _, k, t in _heads(_render_war("#section=war", json.dumps(p)))}["war"]
    assert "eWAR built 2026-09-03" in tag, tag


def test_the_ewar_board_reads_its_qualified_rule_out_of_the_payload():
    """The floor is the exporter's (PA >= 100 or IP >= 30, the same constants
    the WAR rates are gated on). The page reports it; it does not type it."""
    html = _render_war()
    assert 'id="mlbstats-war-qual"' in html and " checked" in html.split('id="mlbstats-war-qual"')[1][:20]
    assert "Qualified: 100 plate appearances or 30 innings" in html
    assert "Thin Sample" not in html, "an unqualified row under the default gate"
    p = json.loads(WAR_SAMPLE)
    p.pop("qualified_rule")
    assert "Qualified: 100" not in _render_war("#section=war", json.dumps(p))


def test_the_ewar_filter_bar_is_the_phone_drawer_with_the_role_chips_behind_it():
    """Spec 3.5 counts six bars, not five: the eWAR bar opens the same drawer,
    and its role chip row is the bar's immediate next sibling so the CSS that
    hides the row with the drawer holds."""
    html = _render_war()
    bars = re.findall(r'<div class="mlbstats-bar mlbx-filters">(<button[^>]*>Filters</button>)', html)
    assert bars == ['<button type="button" class="chip mlbx-filtbtn" aria-expanded="false">Filters</button>'], bars
    assert html.count("mlbx-filtbtn") == 1 and html.count("mlbx-filters") == 1
    assert '</div><div class="mlbstats-seasons mlbstats-roles" role="group" aria-label="Filter by role"' in html
    for lbl in ("Hitter", "Starter", "Reliever", "Swingman", "Two-way"):
        assert '>' + lbl + '<span class="proj-dim">' in html, lbl


def test_the_ewar_explainer_is_one_line_and_links_the_entry():
    html = _render_war()
    assert ('<div class="mlbstats-note mlbstats-explainer">' in html
            and "batting plus pitching, summed before rounding." in html)
    assert 'href="/glossary/#g=ewar"' in html


def test_a_payload_without_players_reads_as_being_computed_not_as_an_error():
    """The harness answers every URL with the bullpen sample, which is what a
    browser gets before war_board_export.py has ever run (or after it refuses
    to write under its coverage floor): the board says so instead of raising."""
    ctx = MiniRacer()
    ctx.eval(smoke._prelude("#section=war") + JS)
    html = ctx.eval("__html['mlbstats-war-root'] || ''")
    assert "being computed" in html and "mlbstats-load-error" not in html
    assert "mlbstats-table" not in html


def test_a_payload_that_was_never_written_reads_as_being_computed_not_as_an_error():
    """The 404 case, which is the state of every box until war_board_export.py
    has run once and the standing state of one that refuses under its coverage
    floor: nothing was ever written, so the brand new nav button opens on the
    computing note, not on a red alert about a build that is not mid-run."""
    html = _render_war("#section=war", status=404)
    assert "The eWAR board is being computed. Check back shortly." in html
    assert "mlbstats-load-error" not in html and "mlbstats-table" not in html


def test_a_failed_fetch_offers_the_retry_the_other_five_boards_offer():
    """A 502 on this one payload used to be permanent for the session: the init
    guard was set BEFORE the fetch and never cleared, so the only way back was
    a full page reload, on the only section with no Retry. The loader is its
    own function now, and the guard sits on init, so the chip can rerun it."""
    html = _render_war("#section=war", status=502)
    assert 'class="mlbstats-empty mlbstats-load-error" role="alert"' in html
    assert '<button type="button" class="chip" id="mlbstats-war-retry">Retry</button>' in html
    i = JS.index("function renderWar(")
    assert "loadWar();" in JS[i:JS.index("function initWar(")], "the Retry runs no loader"
    j = JS.index("function initWar(")
    assert "if (warInit) { renderWar(); return; }" in JS[j:j + 220], JS[j:j + 220]


def test_the_ewar_board_carries_the_shareable_card_every_other_board_has():
    """Spec 8 item 10: the sixth board gets its own GFX spec, so the one board
    that reads a whole season is not the one board a reader cannot share. Its
    columns are pinned with the other cards in GFX_CARDS; what is pinned here
    is the chip in the eWAR bar and the rows the handler hands it, which are
    the SAME filtered, sorted rows the table renders."""
    i = JS.index("function renderWarInner(")
    assert 'gfxChip("mlbstats-war-gfx")' in JS[i:JS.index("function renderWar(", i)]
    j = JS.index('root.querySelector("#mlbstats-war-gfx")')
    blk = JS[j:j + 700]
    # Current: the same filtered, sorted rows the table renders. A window: the
    # same fold, filtered by the same matcher, so the card cannot carry a
    # different set of rows from the board it was generated off.
    assert 'sortRows(warRows().filter(warMatch), warCols(), warSort)' in blk, blk
    assert 'foldSeasons(WIN.war.lo, WIN.war.hi)' in blk, blk


def test_the_ewar_deep_links_read_and_write_and_omit_their_defaults():
    """Section 7: #section=war, wview, wsort and wtsort, with the eWAR sort
    default (war.d) omitted from the URL the way every other board's is."""
    ctx = _clicker("#section=war", prelude=_war_prelude)
    root = "__html['mlbstats-war-root']"
    assert "mlbstats-table" in ctx.eval(root)
    ctx.eval("__click('warview:teams')")
    html = ctx.eval(root)
    assert _visible(html) == WAR_STANDARD["warteam"], _visible(html)
    last = ctx.eval("__hashes[__hashes.length - 1]")
    assert last == "#section=war&wview=teams", last
    ctx.eval("__click('warview:players')")
    last = ctx.eval("__hashes[__hashes.length - 1]")
    assert last == "#section=war" and "wsort" not in last and "wtsort" not in last, last
    # an old-style sort link opens sorted; a key the board does not have is
    # ignored rather than trusted (readSort validates against WAR_COLS)
    html = _render_war("#section=war&wsort=war_bat.a")
    assert "is-sorted" in _cls(html, "war_bat")
    assert "Two Way" in _cells(html, "name")[0], _cells(html, "name")[0]
    assert "is-sorted" not in _cls(_render_war("#section=war&wsort=nonsuch.a"), "war_bat")


def test_the_war_role_chips_narrow_the_board():
    ctx = _clicker("#section=war", prelude=_war_prelude)
    root = "__html['mlbstats-war-root']"
    ctx.eval("__click('warrole:SP')")
    html = ctx.eval(root)
    assert "Ace Adams" in html and "Center Field" not in html
    ctx.eval("__click('warrole:')")
    assert "Center Field" in ctx.eval(root)


# ---------------------------------------------------------------- wave 7: the shared team filter
# One team key for the whole page (#team=NYY), section 7 of the spec. Seasons
# stay per section deliberately; the club does not, because a reader who
# narrows to a club means that club on whatever board he opens next.
_TEAM_BOARDS = [
    ("rel", _render_bullpen, "#section=bullpen", "mlbstats-app-root"),
    ("sp", smoke._render_starters, "#section=starters", "mlbstats-starters-root"),
    ("hit", smoke._render_hitters, "#section=hitters", "mlbstats-hitters-root"),
    ("lev", smoke._render_leverage, "#section=leverage", "mlbstats-leverage-root"),
    ("def", smoke._render_defense, "#section=defense", "mlbstats-defense-root"),
]


@pytest.mark.parametrize("board,fn,hash_,root", _TEAM_BOARDS, ids=[b[0] for b in _TEAM_BOARDS])
def test_a_deep_linked_team_narrows_every_board_and_shows_its_clear(board, fn, hash_, root):
    html = fn(hash_ + "&team=NYY")
    assert '<option value="NYY" selected>' in html, board
    assert '<button type="button" class="chip mlbx-teamclear" title="Clear the team filter">NYY' in html, board
    assert "BOS" not in _table(html).split("<tbody>")[1], board


def test_the_ewar_board_takes_the_same_team_key():
    html = _render_war("#section=war&team=NYY")
    names = "".join(_cells(html, "name"))
    assert "Ace Adams" in names and "Center Field" not in names
    assert 'class="chip mlbx-teamclear" title="Clear the team filter">NYY' in html


def test_a_club_with_no_rows_says_so_and_offers_the_one_control_that_undoes_it():
    """BOS has one reliever on the sample and he is below the qualifying
    sample, so the default board is empty under the filter. "No rows match the
    current filters" over a select the reader has to go find is the state this
    replaces."""
    html = _render_bullpen("#section=bullpen&team=BOS")
    assert ('<div class="mlbstats-empty">No BOS rows on this board. '
            '<button type="button" class="chip mlbx-teamclear">Clear</button></div>') in html
    assert "match the current filters" not in html
    # and without a club filter the board keeps the sentence it always had
    assert 'noRowsNote(relTeam, "No relievers match the current filters.")' in JS


def test_an_unknown_team_key_is_ignored_rather_than_trusted():
    for bad in ("NOTATEAM", "ny", "1"):
        html = _render_bullpen("#section=bullpen&team=" + bad)
        assert "mlbx-teamclear" not in html, bad
        assert "Closer Alpha" in html, bad


def test_the_active_sections_team_is_the_one_written_to_the_hash():
    """writeHash carries the club of the board ON SCREEN. A reader on Starters
    copies the starter club, not one left behind on the reliever board."""
    ctx = _clicker("#section=bullpen&team=NYY")
    ctx.eval("__click('rel:value')")
    last = ctx.eval("__hashes[__hashes.length - 1]")
    assert last == "#section=bullpen&rcols=value&team=NYY", last
    ctx = _clicker("#section=starters&team=NYY", prelude=smoke._starter_prelude)
    ctx.eval("__click('sp:value')")
    assert ctx.eval("__hashes[__hashes.length - 1]") == "#section=starters&scols=value&team=NYY"


def test_one_delegated_listener_clears_the_team_on_whichever_board_is_active():
    """The Clear is rendered by the bar AND by the empty board, and every
    render replaces the button the reader is about to press, so it is wired the
    way the drawer and the Team note are: one document listener, one flag."""
    ctx = _clicker("#section=bullpen&team=BOS", extra=_CAPTURE_DOC)
    root = "__html['mlbstats-app-root']"
    assert "No BOS rows on this board." in ctx.eval(root)
    ctx.eval("__fire('click', %s)" % (_TARGET % ("'.mlbx-teamclear'", "{}")))
    html = ctx.eval(root)
    assert "Closer Alpha" in html and "mlbx-teamclear" not in html
    assert ctx.eval("__hashes[__hashes.length - 1]") == "#section=bullpen"
    ctx.eval("__fire('click', %s)" % _MISS)        # a click elsewhere clears nothing
    assert "Closer Alpha" in ctx.eval(root)
