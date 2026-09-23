# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""py_mini_racer render test for assets/management.js (/management/).

test_mgmt_export.py pins the PAYLOAD and greps the JS for the keys it reads;
nothing rendered the page. These tests do, on a small real-shaped payload:

  - the sacrifice bunt family, live in the payload since 2026-09-07, is drawn;
  - the gate lede follows clears_null instead of asserting "No" as a literal;
  - the raw split-half line is built from the gate block's own numbers, never
    from a sentence that quotes figures of its own;
  - the MLB feed's Brier prints beside the model's when the payload has it.

Skips when py_mini_racer is unavailable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "management.js").read_text(encoding="utf-8")

SAMPLE = {
    "gate_doc": "docs/IN_GAME_MANAGEMENT_GATE.md", "gate_frozen_at": "2026-09-06",
    "headline": {"sentence": "The league steals second at break-even.", "games": 100,
                 "net_dv_all_seasons_wins": -0.5, "redistributable_pool_abs_dv_wins": 12.0},
    "running_game": {
        "by_target": {"2B": {"n": 90, "success_rate": 0.75, "swing_weighted_breakeven_p": 0.753,
                             "share_of_attempts_below_their_own_breakeven": 0.5, "sum_dv_wins": -0.4}},
        "by_season": {"2026": {"n": 90, "success_rate": 0.75, "sum_dv_wins": -0.4}},
        "excluded": {"two_outs_crosses_the_boundary": 10},
        "decomposition": {"dv": "the DECISION.", "er": "the EXECUTION RESIDUAL.",
                          "identity": "DV + ER = the realized change"},
        "why_the_league_average_runner": "the runner is league average.",
        "attempt_census_sentence": "The corpus holds 100 attempts.",
        "why_two_out_attempts_are_excluded": "two estimators meet at the boundary.",
    },
    "gate": {"split_half_r": 0.1085, "null_band": [-0.15, 0.1272], "clears_null": False,
             "n_agent_seasons_in_the_split": 238, "smallest_detectable_per_attempt_sd": 0.0005,
             "variance_explained_by_season": 0.787, "variance_explained_by_team": 0.021,
             "raw_split_half_r_for_comparison": 0.7673,
             "why_season_controlled": "both halves sit in one season.",
             "why_the_raw_number_is_not_the_finding": "the RAW split-half is 0.7789 (stale).",
             "null_construction": "permuted within season.",
             "detection_floor_reading": "the smallest effect at 80 percent power.",
             "what_a_null_decides": "a team-season bounds a manager."},
    "reference": {
        "run_expectancy": [{"bases": "empty", "outs": o, "runs": r, "n": 10}
                           for o, r in ((0, 0.5), (1, 0.27), (2, 0.1))],
        "half_inning_start": {"note": "measured.", "tied_game": [
            {"inning": 1, "half": "top", "batting_team_win_prob": 0.47, "n": 100}]},
        "model": {"n_plays_fit": 1000, "seasons": ["2025", "2026"],
                  "calibration": {"brier": 0.157678, "brier_base_rate_only": 0.249754,
                                  "feed_brier": 0.157516}},
        "smoothing_costs_the_tails": "less sharp at the extremes.",
        "state_excludes": "the teams and the park.",
    },
    "teams": {"status": "built", "columns_are_style_not_skill": "style.",
              "rows": [{"team": "MIA", "season": 2026, "attempts": 10, "success_rate": 0.8,
                        "share_2B": 0.8, "share_3B": 0.2, "mean_breakeven_faced": 0.75}]},
    "sections": {
        "team_style": {"why_no_plus_metric": "noise."},
        "sacrifice_bunt": {"live": True, "sentence": "Bunting cost 127 wins.",
                           "cells": [{"bases": "empty", "outs": 0, "n_bunt": 804,
                                      "dv_per_bunt": -0.02514, "dv_total": -20.211},
                                     {"bases": "3B", "outs": 1, "n_bunt": 49,
                                      "dv_per_bunt": 0.02367, "dv_total": 1.1599}],
                           "independent_control": {"total_wins": -75.33,
                                                   "why_it_is_not_the_metric": "realized."},
                           "the_selection_problem": "NOT SOLVED, STATED.",
                           "two_outs_excluded": "two estimators."},
        "manager_attribution": {"live": False, "blocked_on": "M-MWAR-2", "why": "upper bound."},
        "bullpen_and_lineup": {"live": False, "blocked_on": "not yet measured", "why": "unmeasured."},
    },
    "what_this_page_does_not_claim": "that any manager is better than any other.",
}


def _render(section: str = "running", payload: dict | None = None, bunt_tab: bool = False) -> str:
    # The page opens on the League census since the decision ledger landed
    # (2026-09-23); the harness rewrites the default so each section renders alone.
    js = JS.replace('state = { section: "league"', 'state = { section: "%s"' % section, 1)
    assert section == "league" or js != JS, "the section default moved"
    q = ("function(sel){return String(sel).indexOf('bunt')>=0 ? {} : null;}"
         if bunt_tab else "function(){return null;}")
    prelude = """
    var __html={};
    function __el(id){return new Proxy(function(){return __el(id);},{
      get:function(t,k){ if(k==='innerHTML')return __html[id]||'';
        if(k==='querySelectorAll')return function(){return [];};
        if(k==='addEventListener'||k==='setAttribute'||k==='getAttribute')return function(){return null;};
        return __el(id);},
      set:function(t,k,v){if(k==='innerHTML')__html[id]=v;return true;}});}
    function FT(v){return {then:function(cb){var r=cb(v);return (r&&r.then)?r:FT(r);},catch:function(){return FT(v);}};}
    var P=%s;
    var fetch=function(){return FT({ok:true,json:function(){return FT(P);}});};
    var document={readyState:'complete',getElementById:function(id){return __el(id);},
      querySelector:%s,querySelectorAll:function(){return [];},addEventListener:function(){}};
    var window={document:document,EEPHUS_GL:{wire:function(){}}};
    """ % (json.dumps(payload or SAMPLE), q)
    ctx = MiniRacer()
    ctx.eval(prelude + js)
    return ctx.eval("__html['mgmt-app-root'] || ''")


def test_the_sacrifice_bunt_family_is_drawn():
    html = _render("running")
    assert "The sacrifice bunt" in html and "Bunting cost 127 wins." in html
    assert html.count("<tr><td>empty</td>") >= 1 and "+0.0237" in html
    assert "-75.3 wins" in html and "NOT SOLVED, STATED." in html


def test_the_bunt_moves_to_its_own_tab_once_the_shell_has_one():
    assert "The sacrifice bunt" not in _render("running", bunt_tab=True)
    assert "Bunting cost 127 wins." in _render("bunt", bunt_tab=True)


def test_a_dark_bunt_section_draws_nothing():
    d = json.loads(json.dumps(SAMPLE))
    d["sections"]["sacrifice_bunt"] = {"live": False}
    assert "The sacrifice bunt" not in _render("running", d)


def test_the_gate_lede_follows_clears_null():
    assert "Inside its permutation null band" in _render("gate")
    d = json.loads(json.dumps(SAMPLE))
    d["gate"]["clears_null"] = True
    html = _render("gate", d)
    assert "Clears its permutation null." in html
    assert "Inside its permutation null band" not in html


def test_the_raw_split_half_is_read_off_the_gate_block():
    html = _render("gate")
    assert "Raw 0.7673 against 0.1085 season-controlled" in html
    assert "0.7789" not in html, "the sentence with its own stale figures is still drawn"
    d = json.loads(json.dumps(SAMPLE))
    d["gate"].pop("raw_split_half_r_for_comparison")
    assert "0.7789 (stale)" in _render("gate", d), "an older payload lost its only line"


def test_the_feed_brier_prints_beside_the_model():
    html = _render("reference")
    assert "Brier 0.1577; base rate alone 0.2498; MLB feed 0.1575." in html
    assert html.rstrip().endswith("</section>")


def test_no_dashes_in_any_section():
    for sec in ("running", "gate", "reference", "teams", "bunt"):
        html = _render(sec)
        for bad in ("&mdash;", "&ndash;", "\u2014", "\u2013", "undefined", "NaN"):
            assert bad not in html, (sec, bad)


def test_the_served_board_renders_every_section():
    p = ROOT / "data" / "management_board.json"
    if not p.exists():
        pytest.skip("management_board.json not built")
    d = json.loads(p.read_text(encoding="utf-8"))
    for sec in ("running", "gate", "reference", "teams", "league", "managers", "challenges", "lineups", "bunt"):
        html = _render(sec, d)
        assert html and "undefined" not in html and "NaN" not in html, sec


# --------------------------------------------------------------------------
# The decision ledger (2026-09-23): hash router, club pages, drill-down
# --------------------------------------------------------------------------

_FAM = {"label": "Pitching changes", "n": 2, "n_by_season": {"2026": 2}, "floor": 1, "window_rule": "stint",
        "counterfactual_sentence": "The pitcher not used is not observed.", "has_window": True, "summed": True,
        "counted_only": False, "league_sum_mwpa_by_season": {"2026": 0.1}, "within_family_windows": "partition",
        "dvs_identity_max_abs": 1e-17, "thin_cells": {"decisions_in_thin_cells": 0, "cells_thin": 1, "cells_total": 2},
        "mean_li": 1.1, "gate_status": "not run",
        "hook_pitch_count": {"median": 88, "p10": 40, "p90": 100, "n": 2},
        "inherited_runners": {"inherited": 1, "scored": 0, "derivation": "derived, tracked through the bases."}}
_PH = dict(_FAM, label="Pinch hitters", within_family_windows="disjoint")
_DS = dict(_FAM, label="Defensive subs", summed=False, within_family_windows="can overlap")
_MV = dict(_FAM, label="Mound visits", has_window=False, summed=False, counted_only=True,
           within_family_windows="none", league_sum_mwpa_by_season={})
_ROW_MIA = {"club": "MIA", "season": 2026, "agent": "club-season", "games": 140, "n_all": 4,
            "n_pitching_change": 2, "n_pinch_hit": 1, "n_pinch_run": 0, "n_defensive_sub": 1, "n_intentional_walk": 0,
            "n_bunt": 0, "n_steal": 0, "n_mound_visit": 1, "n_ejection": 0, "mean_li": 1.2, "share_li_high": 0.25,
            "mwpa_pitching_change": 0.12, "mwpa_pinch_hit": -0.04, "hook_median_pitches": 85, "pen_per_game": 3.0,
            "bench_per_game": 1.0, "ibb_per_game": 0.1, "visit_per_game": 3.0,
            "best": {"id": "1:6:0", "family": "pitching_change", "game_pk": 1, "ab": 6, "mwpa": 0.09, "date": "2026-04-01"},
            "worst": {"id": "1:8:1", "family": "pinch_hit", "game_pk": 1, "ab": 8, "mwpa": -0.04, "date": "2026-04-01"},
            "partial": True, "z_hook": -1.2, "z_pen": 0.4, "z_bench": 0.0, "z_ibb": 1.1, "z_visit": -0.3}
_ROW_NYY = dict(_ROW_MIA, club="NYY", season=2025, partial=False, mwpa_pitching_change=-0.3, z_hook=0.8,
                best=None, worst=None)
SAMPLE2 = dict(SAMPLE, **{
    "decisions": {
        "status": "built", "live": True, "seasons": [2025, 2026], "through_by_season": {"2026": "2026-09-04", "2025": "2025-09-28"},
        "corpus_built_at": "2026-09-06T07:04:19+00:00", "n_all": 8,
        "chain_break": {"tolerance": 1e-9, "note": "not a row sum.", "by_season": {
            "2026": {"share_of_plays_not_chained": 0.028, "max_gap_points": 30.1, "row_sum_misses_median_points": 2.2,
                     "row_sum_misses_p90_points": 9.0, "row_sum_misses_p99_points": 20.0}}},
        "families": {"pitching_change": _FAM, "pinch_hit": _PH, "defensive_sub": _DS, "mound_visit": _MV},
        "gate_status_by_family": {}, "floors": {"pitching_change": 1, "pinch_hit": 1},
        "games_floor": 40, "realized_sentence": "Realized value, not skill.", "agent_sentence": "The agent is the club-season.",
        "style_sentence": "Style, not skill.", "single_pa_caveat": "single PA caveat.", "overlap_note": "windows overlap.",
        "dvs_note": "above state.", "li_note": "a cut, not a weight.",
        "units": {"li": "null on the leadoff plate appearance"},
        "removed_pitcher": {"derivation": "derived.", "description_agree": 9, "description_checked": 9,
                            "replacing_pitcher_clause_agree": 1, "replacing_pitcher_clause_rows": 1},
        "switch_classification": {"n": 3, "dh_retained": 1, "position_move": 1, "stayed_in_field": 1, "unclassified": 0},
        "hook_hist": {"bins": [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130],
                      "by_season": {"2026": [0, 0, 0, 0, 1, 0, 0, 0, 5, 3, 1, 0, 0, 0]}},
        "baseline": {"min_cell": 25, "identity": "checked.", "where_dvs_lives": "drill-down only.",
                     "selection_caveat": {}, "families": {}},
        "plus_metric": False, "no_cross_family_total": True,
    },
    "clubs": {"live": True, "status": "built", "n_rows": 2, "rows": [_ROW_MIA, _ROW_NYY],
              "statsapi_codes": {"MIA": "MIA", "NYY": "NYY"}, "not_summed": ["defensive_sub"],
              "columns_are_realized_not_skill": "Realized value, not skill.", "agent_sentence": "The agent is the club-season.",
              "style_sentence": "Style, not skill.", "floors": {"pitching_change": 1, "pinch_hit": 1}, "games_floor": 40,
              "realized_header_tag": "realized", "plus_metric": False,
              "sort_by_realized_is_a_rank_by_what_happened": "a rank by what happened."},
    "managers": {"live": False, "blocked_on": "mgmt_managers ingest (M-MWAR-2)", "why": "no manager entity on disk.",
                 "fixture": {"ejection_named_managers": 92, "ejections": 173, "note": "fixture, not a source"},
                 "rows_until_then": "clubs.rows", "agent_sentence": "The agent is the club-season."},
    "challenges": {"live": False, "blocked_on": "mgmt_feeds_2026 (Wave B)", "why": "read in Wave B.",
                   "regime_note": "ABS never mixed.", "value_not_observable": "not observable."},
    "lineups": {"live": False, "blocked_on": "mgmt_feeds_2026 (Wave B)", "why": "2026 only.", "value_not_measured": "not measured."},
    "shards": {"path_template": "/data/mgmt_decisions/{season}-{club}.json",
               "index": [{"season": 2026, "club": "MIA", "n": 4, "bytes": 1000}]},
})
SHARD_MIA = {"season": 2026, "club": "MIA", "n": 4, "rows": [
    {"date": "2026-04-01", "game_pk": 1, "ab": 6, "idx": 0, "opp": "NYY", "home": True, "half": "top", "inning": 6,
     "outs": 0, "base": 0, "score_diff": 1, "li": 1.4, "family": "pitching_change", "kind": "starter_hook",
     "in_id": 2, "out_id": 1, "in_name": "Arm Two", "out_name": "Arm One", "mwpa": 0.09, "dvs": 0.05, "win_len": 2,
     "window": [[6, "Flyout", 60.0, 63.0], [7, "Strikeout", 63.0, 69.0]], "pitch_count": 85, "tto": 3,
     "inherited": 1, "inherited_scored": 0, "first_pa_mwpa": 0.03},
    {"date": "2026-04-01", "game_pk": 1, "ab": 8, "idx": 0, "opp": "NYY", "home": True, "half": "top", "inning": 7,
     "outs": 0, "base": 0, "score_diff": 1, "li": 1.0, "family": "pitching_change", "kind": "reliever_change",
     "in_id": 3, "out_id": 2, "in_name": "Arm Three", "out_name": "Arm Two", "mwpa": 0.03, "win_len": 1,
     "window": [[8, "Groundout", 69.0, 72.0]], "pitch_count": 20, "tto": 1, "inherited": 0, "inherited_scored": 0},
    {"date": "2026-04-01", "game_pk": 1, "ab": 8, "idx": 1, "opp": "NYY", "home": True, "half": "bottom", "inning": 7,
     "outs": 1, "base": 1, "score_diff": 1, "li": 1.8, "family": "pinch_hit", "in_id": 9, "out_id": 8,
     "in_name": "Bat Nine", "out_name": "Bat Eight", "slot": 8, "mwpa": -0.04, "dvs": -0.041, "win_len": 1,
     "window": [[8, "Strikeout", 72.0, 68.0]], "flags": ["stayed_in"]},
    {"date": "2026-04-01", "game_pk": 1, "ab": 2, "idx": 0, "opp": "NYY", "home": True, "half": "top", "inning": 1,
     "outs": 2, "base": 0, "score_diff": 0, "family": "mound_visit", "win_len": 0, "pitcher_id": 1, "pitcher_name": "Arm One"},
]}


def _render2(hash_: str, payload: dict | None = None, shards: dict | None = None) -> tuple:
    """Renders through the hash router: location and history exist, fetch routes a
    shard URL to the shard map (404 when absent) and everything else to the board."""
    shards = {"/data/mgmt_decisions/2026-MIA.json": SHARD_MIA} if shards is None else shards
    prelude = """
    var __html={};
    function __el(id){return new Proxy(function(){return __el(id);},{
      get:function(t,k){ if(k==='innerHTML')return __html[id]||'';
        if(k==='querySelectorAll')return function(){return [];};
        if(k==='addEventListener'||k==='setAttribute'||k==='getAttribute')return function(){return null;};
        return __el(id);},
      set:function(t,k,v){if(k==='innerHTML')__html[id]=v;return true;}});}
    function FT(v){return {then:function(cb){var r=cb(v);return (r&&r.then)?r:FT(r);},catch:function(){return FT(v);}};}
    var P=%s; var SH=%s;
    var fetch=function(url){ var u=String(url); if(u.indexOf('mgmt_decisions')>=0){ var s=SH[u];
      if(!s) return FT({ok:false,status:404,json:function(){return FT({});}});
      return FT({ok:true,json:function(){return FT(s);}}); } return FT({ok:true,json:function(){return FT(P);}});};
    var location={hash:%s};
    var history={replaceState:function(a,b,h){location.hash=h;}};
    var document={readyState:'complete',getElementById:function(id){return __el(id);},
      querySelector:function(){return {};},querySelectorAll:function(){return [];},addEventListener:function(){}};
    var window={document:document,EEPHUS_GL:{wire:function(){}}};
    """ % (json.dumps(payload or SAMPLE2), json.dumps(shards), json.dumps(hash_))
    ctx = MiniRacer()
    ctx.eval(prelude + JS)
    return ctx.eval("__html['mgmt-app-root'] || ''"), ctx.eval("location.hash")


def test_the_hash_router_opens_a_club_page_from_team_and_season():
    html, _ = _render2("#section=clubs&team=MIA&season=2026")
    assert "MIA 2026" in html and "partial" in html
    assert "Realized value, not skill." in html and "The agent is the club-season." in html
    assert "Hook profile" in html and "Bullpen deployment" in html and "Season timeline" in html
    assert "mgmt-spark" in html and "<polyline" in html
    assert 'href="/mlbstats/#section=bullpen&view=teams&team=MIA"' in html
    # the latest season is the default when the hash names none
    html2, _ = _render2("#section=clubs&team=NYY")
    assert "NYY 2025" in html2
    # and the drill-down opens one decision from game and ab
    html3, _ = _render2("#section=decisions&team=MIA&season=2026&game=1&ab=6")
    assert 'id="mgmt-detail"' in html3 and "Arm Two" in html3 and "The plays governed" in html3
    assert "+0.0900" in html3 and "+0.0500" in html3


def test_an_unknown_family_hash_is_ignored_not_thrown():
    for fam in ("constructor", "__proto__", "hasOwnProperty", "zzz"):
        html, _ = _render2("#section=decisions&team=MIA&season=2026&family=" + fam)
        assert "Every family" in html and "Arm Two" in html and "Bat Nine" in html, fam
    html, _ = _render2("#section=decisions&team=MIA&season=2026&family=pinch_hit")
    assert "Bat Nine" in html and "Arm Two" not in html.split("<tbody>")[1]
    html, _ = _render2("#section=nowhere&team=MIA")
    assert "Realized value, not skill." in html, "an unknown section falls back to the default"


def test_a_missing_shard_draws_a_note_not_an_error():
    html, _ = _render2("#section=decisions&team=NYY&season=2025")
    assert "No decisions shard for NYY 2025." in html
    assert "undefined" not in html and "Error" not in html
    # a shard that is indexed but 404s draws the same note
    html2, _ = _render2("#section=clubs&team=MIA&season=2026", shards={})
    assert "No decisions shard for MIA 2026." in html2


def test_realized_cells_colour_only_on_sign():
    html, _ = _render2("#section=managers")
    assert "Club-season leaderboard" in html
    assert '<td class="mgmt-pos">+0.12</td>' in html and '<td class="mgmt-neg">-0.30</td>' in html
    assert 'mgmt-th-tag">realized' in html
    # the style z cells carry no sign colour and no ladder
    assert "<td>-1.2</td>" in html and "<td>+0.8</td>" in html
    for bad in ("tier-", "eephus-tier", "t-elite", "t-plus", "mgmt-tier"):
        assert bad not in html, bad
    club, _ = _render2("#section=clubs&team=MIA&season=2026")
    assert 'class="mgmt-zchip"' in club
    assert 'class="mgmt-zchip mgmt-pos' not in club and 'class="mgmt-zchip mgmt-neg' not in club


def test_club_page_links_only_to_routes_the_payload_says_are_built():
    """/franchise/ (D3) and /ledger/ (D1) have not shipped: no anchor to either
    unless the export found the route on disk and said so in DATA.routes."""
    html, _ = _render2("#section=clubs&team=MIA&season=2026")
    assert 'href="/franchise/' not in html and 'href="/ledger/' not in html
    assert 'href="/projections/#team=MIA"' in html
    built = dict(SAMPLE2, routes={"franchise": True, "ledger": False})
    html2, _ = _render2("#section=clubs&team=MIA&season=2026", payload=built)
    assert 'href="/franchise/#team=MIA"' in html2 and 'href="/ledger/' not in html2


def test_the_census_never_prints_a_sum_for_an_unsummed_family():
    """The defensive sub has a window and is not summed: its census cell reads
    "stored, not summed", carries no sign colour, and the summed family beside it
    still prints its league sum."""
    html, _ = _render2("#section=league")
    assert "<td>Defensive subs</td><td>2</td><td>1.10</td><td>stored, not summed</td>" in html
    assert '<td>Pitching changes</td><td>2</td><td>1.10</td><td class="mgmt-pos">+0.1</td>' in html
    assert "<td>Mound visits</td><td>2</td><td>1.10</td><td>counted</td>" in html


def test_management_js_makes_no_eephus_tiers_call():
    assert "EephusTiers" not in JS
    assert "EEPHUS_TIERS" not in JS


def test_no_dashes_in_any_ledger_section():
    for h in ("#section=league", "#section=managers", "#section=clubs&team=MIA&season=2026",
              "#section=decisions&team=MIA&season=2026", "#section=challenges", "#section=lineups"):
        html, _ = _render2(h)
        for bad in ("&mdash;", "&ndash;", chr(0x2014), chr(0x2013), "undefined", "NaN"):
            assert bad not in html, (h, bad)
